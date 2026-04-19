"""
VPN / Proxy Manager
===================

Toggle-able outbound proxy layer for the SETUPS webapp.
Supports provider=`free` (rotated public proxies) or `custom` (user URL).
When enabled, installs HTTP_PROXY / HTTPS_PROXY env vars so every outbound
HTTP call (yfinance, NSE, Yahoo v8, Groww, …) routes through the proxy.

Design:
  * All network I/O is done WITHOUT holding the instance lock — the UI
    toggle stays responsive even when probing many proxies.
  * Candidate proxies are tested in parallel (25 at a time) so enable()
    returns within a few seconds.
  * A hard wall-clock timeout bounds enable()/rotate().
  * `_test_proxy` uses an isolated Session with trust_env=False so we don't
    accidentally tunnel the test through an already-installed env proxy.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests

# ── Free proxy source list (no API key required) ────────────────────────────
FREE_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http"
    "&timeout=8000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
]

PROXY_CACHE_TTL = 30 * 60
PROXY_TEST_TIMEOUT = 4
PROXY_TEST_URL = "https://api.ipify.org?format=json"
# A proxy that passes ipify but fails the *real* data endpoint is worse than
# useless — the UI shows "no data". So we require the proxy to also reach
# Yahoo v8 (the single most-used endpoint in this app). If it cannot fetch
# AAPL's 1-day chart in PROXY_REAL_TIMEOUT seconds, we reject it.
PROXY_REAL_TEST_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=1d"
)
PROXY_REAL_TIMEOUT = 6
PROXY_PICK_PARALLEL = 25
PROXY_PICK_BATCHES = 20   # try up to 500 proxies per enable() / rotate() call
# Hard wall-clock cap for enable()/rotate() search. Keep hunting through
# the full 1500+ free-proxy pool (refreshing if exhausted) for up to this
# long before giving up. A shorter cap made the UI close with "no proxy
# found" even though ~5% of free proxies can reach Yahoo if you keep trying.
ENABLE_HARD_TIMEOUT = 300  # 5 minutes

# ── Watchdog (auto-rotate until a working proxy is found) ──────────────────
# When VPN is ON, a background thread probes the current proxy against the
# real data endpoint every WATCHDOG_INTERVAL seconds. On failure it triggers
# an automatic rotate() so the UI self-heals without user intervention.
WATCHDOG_INTERVAL = 45       # seconds between health probes when healthy
WATCHDOG_RETRY_INTERVAL = 8  # seconds between rotate attempts when unhealthy
WATCHDOG_FAILS_BEFORE_ROTATE = 2  # tolerate this many consecutive fails first

# ── Health-check targets ───────────────────────────────────────────────────
HEALTH_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=102400"
HEALTH_LATENCY_URL = "https://www.cloudflare.com/cdn-cgi/trace"
# Each tuple: (key, display_name, url). Add/remove to extend the scan.
HEALTH_APP_TARGETS = [
    ("yahoo",        "Yahoo Finance (US)",  "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=1d"),
    ("yahooIN",      "Yahoo Finance (NSE)", "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?interval=1d&range=1d"),
    ("nse",          "NSE India",           "https://www.nseindia.com/api/marketStatus"),
    ("bse",          "BSE India",           "https://api.bseindia.com/BseIndiaAPI/api/Sensex/w"),
    ("groww",        "Groww",               "https://groww.in/"),
    ("screener",     "Screener.in",         "https://www.screener.in/api/company/search/?q=RELIANCE"),
    ("moneycontrol", "Moneycontrol",        "https://www.moneycontrol.com/stocksmarketsindia/"),
    ("investing",    "Investing.com",       "https://www.investing.com/"),
    ("tradingview",  "TradingView",         "https://www.tradingview.com/"),
]
HEALTH_TIMEOUT = 8


@dataclass
class VpnConfig:
    enabled: bool = False
    provider: str = "free"
    custom_proxy_url: str = ""
    current_proxy: str = ""
    last_tested_at: Optional[float] = None
    last_test_ok: Optional[bool] = None
    last_test_ip: Optional[str] = None
    last_test_error: Optional[str] = None
    proxy_list_fetched_at: Optional[float] = None
    proxy_list_size: int = 0


def _fresh_session() -> requests.Session:
    """Session that IGNORES env proxies — for probing candidate proxies."""
    s = requests.Session()
    s.trust_env = False
    return s


class VpnManager:
    def __init__(self, config_file: Path):
        self._config_file = Path(config_file)
        self._lock = threading.Lock()
        self._config = VpnConfig()
        self._free_proxy_pool: list[str] = []
        self._pool_fetched_at: float = 0.0
        self._orig_env_http = os.environ.get("HTTP_PROXY")
        self._orig_env_https = os.environ.get("HTTPS_PROXY")

        # Watchdog state — see _watchdog_loop().
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()

        self._load()

        # IMPORTANT: VPN ALWAYS starts DISABLED on server boot.
        # Rationale: a free proxy saved in a previous session often goes
        # dead or gets geo-blocked (NSE/BSE block foreign IPs), which would
        # poison EVERY outbound HTTP call (yfinance, NSE, Groww, cache
        # refresh) and silently break every data panel in the UI.
        # The saved `current_proxy` is kept as a hint for display only —
        # the user must explicitly click "Turn ON" each session.
        if self._config.enabled:
            self._config.enabled = False
            self._save()
        # Defensive: make sure no stale env proxy is set by a parent shell
        # that would leak into outbound calls.
        self._revert_env_proxy()

    # ── persistence ──────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            if self._config_file.exists():
                data = json.loads(self._config_file.read_text())
                defaults = VpnConfig().__dict__
                self._config = VpnConfig(**{
                    k: data.get(k, defaults[k]) for k in defaults.keys()
                })
        except Exception:
            self._config = VpnConfig()

    def _save(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self._config_file.write_text(
                json.dumps(asdict(self._config), indent=2, default=str)
            )
        except Exception:
            pass

    # ── free proxy discovery ─────────────────────────────────────────────
    def _fetch_free_proxies(self, force: bool = False) -> list[str]:
        now = time.time()
        if (not force and self._free_proxy_pool
                and now - self._pool_fetched_at < PROXY_CACHE_TTL):
            return self._free_proxy_pool

        collected: set[str] = set()
        sess = _fresh_session()
        for url in FREE_PROXY_SOURCES:
            try:
                r = sess.get(url, timeout=8)
                if not r.ok:
                    continue
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    if line.startswith(("http://", "https://", "socks4://", "socks5://")):
                        collected.add(line)
                    else:
                        parts = line.split(":")
                        if len(parts) != 2 or not parts[1].isdigit():
                            continue
                        collected.add(f"http://{line}")
                    if len(collected) >= 1500:
                        break
            except Exception:
                continue

        pool = list(collected)
        random.shuffle(pool)
        self._free_proxy_pool = pool
        self._pool_fetched_at = now
        self._config.proxy_list_fetched_at = now
        self._config.proxy_list_size = len(pool)
        self._save()
        return pool

    def _test_proxy(self, proxy_url: str, timeout: int = PROXY_TEST_TIMEOUT,
                    require_real: bool = True) -> bool:
        """Return True only if the proxy can reach BOTH ipify (liveness) AND
        the real data endpoint (Yahoo v8). A proxy that passes ipify but 403s
        on Yahoo is the #1 cause of "VPN on, no data" in the UI.

        Set require_real=False for custom-provider soft validation where the
        user may be using a proxy that blocks ipify but works fine.
        """
        sess = _fresh_session()
        proxies = {"http": proxy_url, "https": proxy_url}

        # 1) Liveness probe — ipify (tiny, fast, fails fast on dead proxies).
        try:
            r = sess.get(PROXY_TEST_URL, proxies=proxies, timeout=timeout)
            if not r.ok:
                return False
            try:
                if not r.json().get("ip"):
                    return False
            except Exception:
                return False
        except Exception:
            return False

        if not require_real:
            return True

        # 2) Real-endpoint probe — Yahoo v8 chart. A proxy that 403s or
        # times out here will break actual data fetches in the app.
        try:
            r2 = sess.get(
                PROXY_REAL_TEST_URL,
                proxies=proxies,
                timeout=PROXY_REAL_TIMEOUT,
                headers={
                    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0 Safari/537.36"),
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            if r2.status_code != 200:
                return False
            # Yahoo v8 returns JSON; a transparent proxy/captive portal often
            # returns HTML. Reject if body doesn't look like JSON.
            body = r2.text[:128]
            if not body.lstrip().startswith("{"):
                return False
            return True
        except Exception:
            return False

    def _pick_working_free_proxy(self, deadline_ts: float) -> Optional[str]:
        """Search the free-proxy pool for one that passes BOTH ipify and
        Yahoo v8. Keeps looping through the pool — refreshing it from the
        upstream sources when exhausted — until either a winner is found
        or the wall-clock deadline is hit.
        """
        pool = self._fetch_free_proxies()
        if not pool:
            return None

        tried: set[str] = set()
        pool_refreshes_done = 0
        max_pool_refreshes = 3  # hard cap so we don't spam proxy-list endpoints

        while time.time() < deadline_ts:
            # Pick the next slice of not-yet-tried proxies.
            remaining = [p for p in pool if p not in tried]
            if not remaining:
                # Exhausted the current pool — force-refresh from upstream.
                if pool_refreshes_done >= max_pool_refreshes:
                    return None
                try:
                    pool = self._fetch_free_proxies(force=True)
                    pool_refreshes_done += 1
                    tried.clear()  # retry everything once more
                    continue
                except Exception:
                    return None

            chunk = remaining[:PROXY_PICK_PARALLEL]
            tried.update(chunk)

            with ThreadPoolExecutor(max_workers=PROXY_PICK_PARALLEL) as ex:
                futures = {ex.submit(self._test_proxy, p): p for p in chunk}
                remaining_time = max(1, deadline_ts - time.time())
                try:
                    for fut in as_completed(futures, timeout=remaining_time):
                        try:
                            if fut.result():
                                winner = futures[fut]
                                for other in futures:
                                    if other is not fut:
                                        other.cancel()
                                return winner
                        except Exception:
                            continue
                        if time.time() >= deadline_ts:
                            return None
                except Exception:
                    # Chunk-level timeout — move on to next chunk while we
                    # still have wall-clock budget.
                    if time.time() >= deadline_ts:
                        return None
                    continue
        return None

    # ── env proxy install / revert ───────────────────────────────────────
    def _install_env_proxy(self, proxy_url: str) -> None:
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    def _revert_env_proxy(self) -> None:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)
        if self._orig_env_http:
            os.environ["HTTP_PROXY"] = self._orig_env_http
            os.environ["http_proxy"] = self._orig_env_http
        if self._orig_env_https:
            os.environ["HTTPS_PROXY"] = self._orig_env_https
            os.environ["https_proxy"] = self._orig_env_https

    def _probe_current_routing(self) -> tuple[bool, Optional[str], Optional[str]]:
        """Probe ipify through *current* settings (env proxy if enabled)."""
        sess = requests.Session()
        sess.trust_env = True
        try:
            r = sess.get(PROXY_TEST_URL, timeout=PROXY_TEST_TIMEOUT + 2)
            if r.ok:
                ip = r.json().get("ip")
                return (bool(ip), ip, None)
            return (False, None, f"HTTP {r.status_code}")
        except Exception as e:
            return (False, None, f"{type(e).__name__}: {e}")

    def _probe_real_endpoint_via_env(self) -> bool:
        """Probe the REAL data endpoint (Yahoo v8) through the currently-
        installed env proxy. Used by the watchdog to detect silent breakage
        (proxy goes stale, gets rate-limited, or starts returning HTML/403).
        """
        sess = requests.Session()
        sess.trust_env = True
        try:
            r = sess.get(
                PROXY_REAL_TEST_URL,
                timeout=PROXY_REAL_TIMEOUT,
                headers={
                    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0 Safari/537.36"),
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            if r.status_code != 200:
                return False
            return r.text.lstrip().startswith("{")
        except Exception:
            return False

    # ── watchdog (auto-rotate loop) ──────────────────────────────────────
    def _start_watchdog(self) -> None:
        """Start the background auto-rotate thread. Idempotent."""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        t = threading.Thread(
            target=self._watchdog_loop,
            name="vpn-watchdog",
            daemon=True,
        )
        self._watchdog_thread = t
        t.start()

    def _stop_watchdog(self) -> None:
        """Signal the watchdog to exit. Does not join (daemon)."""
        self._watchdog_stop.set()
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        """While VPN is enabled and provider='free', periodically probe the
        real data endpoint. On repeated failure, rotate to a fresh proxy
        automatically. Keeps rotating until it finds a working one.
        """
        consecutive_fails = 0
        # Initial grace period — let the UI settle before first probe.
        if self._watchdog_stop.wait(5):
            return

        while not self._watchdog_stop.is_set():
            with self._lock:
                enabled = self._config.enabled
                provider = self._config.provider
                current = self._config.current_proxy

            if not enabled:
                return  # VPN turned off → exit thread

            # Custom proxies: don't auto-rotate (user owns the URL). Just idle.
            if provider != "free" or not current:
                if self._watchdog_stop.wait(WATCHDOG_INTERVAL):
                    return
                continue

            healthy = self._probe_real_endpoint_via_env()

            if healthy:
                consecutive_fails = 0
                with self._lock:
                    self._config.last_tested_at = time.time()
                    self._config.last_test_ok = True
                    self._config.last_test_error = None
                    self._save()
                if self._watchdog_stop.wait(WATCHDOG_INTERVAL):
                    return
                continue

            # Unhealthy — tolerate a couple of blips (transient network hiccup).
            consecutive_fails += 1
            with self._lock:
                self._config.last_tested_at = time.time()
                self._config.last_test_ok = False
                self._config.last_test_error = (
                    f"Watchdog: Yahoo probe failed ({consecutive_fails} consec.)"
                )
                self._save()

            if consecutive_fails < WATCHDOG_FAILS_BEFORE_ROTATE:
                if self._watchdog_stop.wait(WATCHDOG_RETRY_INTERVAL):
                    return
                continue

            # Rotate — keep trying until we find one that works or VPN is off.
            consecutive_fails = 0
            try:
                self._auto_rotate_once()
            except Exception:
                pass

            # Shorter sleep after rotate so we re-probe soon.
            if self._watchdog_stop.wait(WATCHDOG_RETRY_INTERVAL):
                return

    def _auto_rotate_once(self) -> bool:
        """Internal rotate invoked by the watchdog. Uses a fresh deadline.
        Returns True if a new working proxy was installed.
        """
        with self._lock:
            if not self._config.enabled or self._config.provider != "free":
                return False
            old = self._config.current_proxy

        deadline = time.time() + ENABLE_HARD_TIMEOUT
        new_proxy = self._pick_working_free_proxy(deadline)
        if not new_proxy or new_proxy == old:
            # Refresh the pool on next miss and try again next tick.
            try:
                self._fetch_free_proxies(force=True)
            except Exception:
                pass
            return False

        self._install_env_proxy(new_proxy)
        ok, ip, err = self._probe_current_routing()

        with self._lock:
            self._config.current_proxy = new_proxy
            self._config.last_tested_at = time.time()
            self._config.last_test_ok = ok
            self._config.last_test_ip = ip
            self._config.last_test_error = err or "auto-rotated by watchdog"
            self._save()
        return True

    # ── public API ───────────────────────────────────────────────────────
    def status(self) -> dict:
        with self._lock:
            d = asdict(self._config)
            d["proxy_pool_size"] = len(self._free_proxy_pool)
            d["watchdog_running"] = bool(
                self._watchdog_thread and self._watchdog_thread.is_alive()
            )
            return d

    def enable(self) -> dict:
        with self._lock:
            provider = self._config.provider
            custom_url = (self._config.custom_proxy_url or "").strip()

        deadline = time.time() + ENABLE_HARD_TIMEOUT
        proxy_url: Optional[str] = None
        warn: Optional[str] = None

        if provider == "custom":
            if not custom_url:
                return {
                    "ok": False, "enabled": False,
                    "error": "Custom provider selected but no URL set. "
                             "Open the VPN panel and save a Custom URL first.",
                }
            proxy_url = custom_url
            # Custom proxies may be paid/private — don't reject them solely
            # because Yahoo blocks the IP; just warn.
            if not self._test_proxy(custom_url, timeout=PROXY_TEST_TIMEOUT + 2,
                                    require_real=False):
                warn = "Custom proxy did not respond to test probe; trying anyway."
            elif not self._test_proxy(custom_url,
                                      timeout=PROXY_TEST_TIMEOUT + 2,
                                      require_real=True):
                warn = ("Custom proxy reachable but cannot fetch Yahoo Finance "
                        "(likely geo-blocked). Data may not load in UI.")
        else:
            proxy_url = self._pick_working_free_proxy(deadline)
            if not proxy_url:
                return {
                    "ok": False, "enabled": False,
                    "error": (f"Could not find a working free proxy within "
                              f"{ENABLE_HARD_TIMEOUT}s (searched entire pool, "
                              f"refreshed up to 3×). Try again later or use a "
                              f"Custom proxy."),
                }

        self._install_env_proxy(proxy_url)
        ok, ip, err = self._probe_current_routing()

        if not ok and provider == "free":
            # Candidate worked in isolation but fails for active routing —
            # revert and report so user can Rotate.
            self._revert_env_proxy()
            with self._lock:
                self._config.enabled = False
                self._config.last_tested_at = time.time()
                self._config.last_test_ok = False
                self._config.last_test_error = err or "routing probe failed"
                self._save()
            return {
                "ok": False, "enabled": False,
                "error": f"Proxy selected but active routing failed: {err}",
                "proxy": proxy_url,
            }

        with self._lock:
            self._config.enabled = True
            self._config.current_proxy = proxy_url
            self._config.last_tested_at = time.time()
            self._config.last_test_ok = ok
            self._config.last_test_ip = ip
            self._config.last_test_error = err or warn
            self._save()

        # Start the auto-rotate watchdog so a proxy that goes stale later
        # will be replaced automatically without user intervention.
        self._start_watchdog()

        return {
            "ok": True, "enabled": True,
            "provider": provider, "proxy": proxy_url,
            "externalIp": ip, "testOk": ok, "error": err or warn,
        }

    def disable(self) -> dict:
        self._stop_watchdog()
        self._revert_env_proxy()
        with self._lock:
            self._config.enabled = False
            self._save()
        return {"ok": True, "enabled": False}

    def toggle(self) -> dict:
        with self._lock:
            currently = self._config.enabled
        return self.disable() if currently else self.enable()

    def set_config(self, provider: Optional[str] = None,
                   custom_proxy_url: Optional[str] = None) -> dict:
        with self._lock:
            if provider is not None:
                if provider not in ("free", "custom"):
                    raise ValueError("provider must be 'free' or 'custom'")
                self._config.provider = provider
            if custom_proxy_url is not None:
                self._config.custom_proxy_url = custom_proxy_url.strip()
            self._save()
            was_enabled = self._config.enabled

        if was_enabled:
            self.disable()
            return self.enable()
        with self._lock:
            return {"ok": True, **asdict(self._config)}

    def rotate(self) -> dict:
        with self._lock:
            if self._config.provider != "free":
                return {"ok": False, "error": "Rotate only applies to 'free' provider"}
            was_enabled = self._config.enabled

        deadline = time.time() + ENABLE_HARD_TIMEOUT
        new_proxy = self._pick_working_free_proxy(deadline)
        if not new_proxy:
            return {"ok": False,
                    "error": "No working free proxy found. Try Refresh pool, then Rotate again."}

        self._install_env_proxy(new_proxy)
        ok, ip, err = self._probe_current_routing()

        with self._lock:
            self._config.current_proxy = new_proxy
            if ok:
                self._config.enabled = True
            elif not was_enabled:
                self._revert_env_proxy()
            self._config.last_tested_at = time.time()
            self._config.last_test_ok = ok
            self._config.last_test_ip = ip
            self._config.last_test_error = err
            self._save()

        return {"ok": ok, "proxy": new_proxy, "externalIp": ip,
                "testOk": ok, "error": err}

    def test(self) -> dict:
        ok, ip, err = self._probe_current_routing()
        with self._lock:
            self._config.last_tested_at = time.time()
            self._config.last_test_ok = ok
            self._config.last_test_ip = ip
            self._config.last_test_error = err
            current = self._config.current_proxy
            enabled = self._config.enabled
            self._save()
        return {"ok": ok, "externalIp": ip, "error": err,
                "proxy": current, "enabled": enabled}

    def refresh_free_pool(self) -> dict:
        pool = self._fetch_free_proxies(force=True)
        return {"ok": True, "size": len(pool)}

    # ── health check ─────────────────────────────────────────────────────
    def _probe_latency_and_speed(self, proxy_url: Optional[str]) -> dict:
        """Measure latency (ms), download speed (KB/s), external IP, and
        reachability/latency for every entry in `HEALTH_APP_TARGETS`.

        If `proxy_url` is None → direct (no proxy).
        If `proxy_url` is a URL → routed through that proxy.
        Uses an isolated Session with trust_env=False so env vars don't leak.
        """
        result = {
            "ok": False, "latency_ms": None, "download_kbps": None,
            "ip": None, "bytes": 0, "error": None,
            # Per-target results populated below.
            "targets": {},
            # Back-compat flat keys (older UI readers):
            "yahoo_ok": None, "yahoo_ms": None,
            "nse_ok": None,   "nse_ms": None,
        }
        sess = _fresh_session()
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        # 1) Latency + external IP (Cloudflare trace)
        try:
            t0 = time.perf_counter()
            r = sess.get(HEALTH_LATENCY_URL, proxies=proxies, timeout=HEALTH_TIMEOUT)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if r.ok:
                for line in r.text.splitlines():
                    if line.startswith("ip="):
                        result["ip"] = line.split("=", 1)[1].strip()
                        break
                result["latency_ms"] = round(latency_ms, 1)
            else:
                result["error"] = f"Latency probe HTTP {r.status_code}"
                return result
        except Exception as e:
            result["error"] = f"Latency probe: {type(e).__name__}: {e}"
            return result

        # 2) Download speed — 100 KB file
        try:
            t0 = time.perf_counter()
            r = sess.get(HEALTH_DOWNLOAD_URL, proxies=proxies,
                         timeout=HEALTH_TIMEOUT, stream=True)
            total = 0
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    total += len(chunk)
            elapsed = time.perf_counter() - t0
            if r.ok and total > 0 and elapsed > 0:
                result["bytes"] = total
                result["download_kbps"] = round((total / 1024.0) / elapsed, 1)
                result["ok"] = True
            elif not r.ok:
                result["error"] = f"Download probe HTTP {r.status_code}"
        except Exception as e:
            result["error"] = f"Download probe: {type(e).__name__}: {e}"

        # 3) Parallel reachability probes for financial targets
        def _probe_one(entry):
            key, name, url = entry
            s = _fresh_session()
            try:
                t0 = time.perf_counter()
                rr = s.get(url, proxies=proxies, timeout=HEALTH_TIMEOUT,
                           headers={
                               "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                                              "Chrome/120.0 Safari/537.36"),
                               "Accept": "*/*",
                               "Accept-Language": "en-US,en;q=0.9",
                           },
                           allow_redirects=True)
                ms = (time.perf_counter() - t0) * 1000.0
                return (key, name, url, bool(rr.ok), round(ms, 1), rr.status_code, None)
            except Exception as e:
                return (key, name, url, False, None, None,
                        f"{type(e).__name__}: {e}")

        with ThreadPoolExecutor(max_workers=min(8, len(HEALTH_APP_TARGETS))) as ex:
            for key, name, url, ok, ms, status, err in ex.map(_probe_one, HEALTH_APP_TARGETS):
                result["targets"][key] = {
                    "name": name, "url": url, "ok": ok, "ms": ms,
                    "status": status, "error": err,
                }
                # Back-compat flat keys (yahoo/nse) so older callers still work.
                if key in ("yahoo", "nse"):
                    result[f"{key}_ok"] = ok
                    result[f"{key}_ms"] = ms
        return result

    def health_check(self) -> dict:
        """Run parallel latency+speed probes — direct vs through current proxy."""
        with self._lock:
            enabled = self._config.enabled
            current_proxy = self._config.current_proxy
            provider = self._config.provider

        probe_proxy: Optional[str] = current_proxy if (enabled and current_proxy) else None

        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_direct = ex.submit(self._probe_latency_and_speed, None)
            fut_proxied = ex.submit(self._probe_latency_and_speed, probe_proxy) if probe_proxy else None
            direct = fut_direct.result()
            proxied = fut_proxied.result() if fut_proxied else None

        summary = {
            "vpnEnabled": enabled, "provider": provider, "proxy": probe_proxy,
            "direct": direct, "proxied": proxied, "comparison": None,
        }

        if direct.get("ok") and proxied and proxied.get("ok"):
            d_lat = direct.get("latency_ms") or 0
            p_lat = proxied.get("latency_ms") or 0
            d_spd = direct.get("download_kbps") or 0
            p_spd = proxied.get("download_kbps") or 0
            latency_overhead_ms = (p_lat - d_lat) if (p_lat and d_lat) else None
            speed_ratio = (p_spd / d_spd) if (d_spd > 0 and p_spd > 0) else None
            if speed_ratio is None:
                verdict = "unknown"
            elif speed_ratio >= 0.75: verdict = "excellent"
            elif speed_ratio >= 0.40: verdict = "ok"
            elif speed_ratio >= 0.15: verdict = "slow"
            else:                     verdict = "very_slow"
            summary["comparison"] = {
                "latencyOverheadMs": round(latency_overhead_ms, 1) if latency_overhead_ms is not None else None,
                "speedRatio": round(speed_ratio, 3) if speed_ratio is not None else None,
                "slowdownPct": round((1 - speed_ratio) * 100, 1) if speed_ratio is not None else None,
                "verdict": verdict,
                "ipChanged": (direct.get("ip") != proxied.get("ip")
                              if direct.get("ip") and proxied.get("ip") else None),
            }
        return summary


# ── module-level singleton ─────────────────────────────────────────────────
_instance: Optional[VpnManager] = None
_instance_lock = threading.Lock()


def get_vpn_manager(config_file: Optional[Path] = None) -> VpnManager:
    global _instance
    if _instance is not None:
        return _instance
    with _instance_lock:
        if _instance is None:
            if config_file is None:
                config_file = Path.cwd() / "trade_data" / "vpn_config.json"
            _instance = VpnManager(config_file)
        return _instance

