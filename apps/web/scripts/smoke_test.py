#!/usr/bin/env python3
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from apps.web.api.main import app  # noqa: E402


def main() -> None:
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    payload = health.json()
    assert payload.get("ok") is True

    ui = client.get("/")
    assert ui.status_code == 200, ui.text
    ui_text = ui.text
    assert "compare output vs live" in ui_text, "UI is missing compare mode"

    jobs = client.get("/api/jobs")
    assert jobs.status_code == 200, jobs.text
    assert isinstance(jobs.json().get("jobs"), list)

    brief = client.get("/api/assistant/scan-brief", params={"market": "india", "timeframe": "daily", "setups": "full", "top_n": 3})
    assert brief.status_code == 200, brief.text
    brief_payload = brief.json().get("brief", {})
    assert isinstance(brief_payload.get("lines"), list)

    output_analyze = client.get(
        "/api/stock/analyze",
        params={"symbol": "HINDCOPPER.NS", "market": "india", "timeframe": "daily", "setups": "full", "source": "output"},
    )
    assert output_analyze.status_code == 200, output_analyze.text
    output_analysis = output_analyze.json().get("analysis", {})
    assert output_analysis.get("analysisSource") == "output", output_analysis
    assert "symbol" in output_analysis, f"analysis missing symbol: {output_analysis}"
    assert "status" in output_analysis, f"analysis missing status: {output_analysis}"
    assert "actionVerdict" in output_analysis, f"analysis missing actionVerdict: {output_analysis}"
    assert "reasoning" in output_analysis, f"analysis missing reasoning: {output_analysis}"
    assert any("Execution:" in line or "Portfolio context" in line for line in output_analysis.get("reasoning", [])), output_analysis.get("reasoning", [])

    live_analyze = client.get(
        "/api/stock/analyze",
        params={"symbol": "AAPL", "market": "us", "timeframe": "daily", "setups": "full", "source": "live"},
    )
    assert live_analyze.status_code == 200, live_analyze.text
    live_analysis = live_analyze.json().get("analysis", {})
    assert live_analysis.get("analysisSource") == "live", live_analysis
    assert "symbol" in live_analysis, f"analysis missing symbol: {live_analysis}"
    assert "status" in live_analysis, f"analysis missing status: {live_analysis}"
    assert "actionVerdict" in live_analysis, f"analysis missing actionVerdict: {live_analysis}"
    assert "reasoning" in live_analysis, f"analysis missing reasoning: {live_analysis}"

    rejected = client.get(
        "/api/stock/analyze",
        params={"symbol": "RELIANCE.NS", "market": "india", "timeframe": "daily", "setups": "full", "source": "live"},
    )
    assert rejected.status_code == 200, rejected.text
    rej_analysis = rejected.json().get("analysis", {})
    assert rej_analysis.get("status") == "REJECTED", rej_analysis
    assert any("Next step" in line for line in rej_analysis.get("reasoning", [])), rej_analysis.get("reasoning", [])

    watchlist_path = ROOT / "output" / "watchlist_india_daily_full_LATEST.json"
    if watchlist_path.exists():
        rows = json.loads(watchlist_path.read_text(encoding="utf-8"))
        if rows:
            symbol = str(rows[0].get("symbol", "")).strip()
            if symbol:
                watch = client.get(
                    "/api/stock/analyze",
                    params={"symbol": symbol, "market": "india", "timeframe": "daily", "setups": "full", "source": "output"},
                )
                assert watch.status_code == 200, watch.text
                watch_analysis = watch.json().get("analysis", {})
                if watch_analysis.get("status") == "WATCHLIST":
                    assert any("Trigger condition" in line for line in watch_analysis.get("reasoning", [])), watch_analysis.get("reasoning", [])

    print("Smoke test passed: UI, /api/health, /api/jobs, /api/assistant/scan-brief, /api/stock/analyze")


if __name__ == "__main__":
    main()

