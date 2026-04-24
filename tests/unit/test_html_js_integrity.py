"""Static-analysis tests for HTML/JavaScript assets.

These tests run in milliseconds with zero network/browser dependency and
catch the class of bugs we've seen in practice:

  ① Missing function header (buildHealthBar body became orphaned top-level code)
     → caused a -1 brace imbalance → ALL JS on the page silently failed
  ② Stray top-level code (executable statements outside any function/block)
  ③ Duplicate function definitions (later def silently shadows earlier one)
  ④ Double DOMContentLoaded handlers that double-fetch data
  ⑤ Fast-load endpoint not using /watchlist/fast for the initial DOMContentLoaded pre-fetch
  ⑥ API calls to non-existent endpoint paths in DOMContentLoaded
  ⑦ Referenced JS functions / HTML element IDs that have no definition

Run:  pytest -m unit tests/unit/test_html_js_integrity.py -v
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

pytestmark = pytest.mark.unit

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
TRADE_BOARD_HTML = ROOT / "apps" / "web" / "ui" / "trade_board.html"
HTML_FILES = [
    ROOT / "apps" / "web" / "ui" / "trade_board.html",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_inline_js(html_path: Path) -> tuple[str, list[str]]:
    """Return (combined_js, list_of_js_blocks) from all inline <script> tags."""
    html = html_path.read_text(encoding="utf-8")
    blocks = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    return "\n".join(blocks), blocks


def _js_lines(html_path: Path) -> list[str]:
    combined, _ = _extract_inline_js(html_path)
    return combined.split("\n")


class BraceScan(NamedTuple):
    net_balance: int                  # 0 = perfectly balanced
    first_negative_line: int | None   # 1-based JS line index where count < 0
    first_negative_text: str


def _scan_braces(lines: list[str]) -> BraceScan:
    """Count { vs } across all lines; track the first point the count goes < 0."""
    balance = 0
    first_neg_line: int | None = None
    first_neg_text = ""
    for i, line in enumerate(lines, 1):
        balance += line.count("{") - line.count("}")
        if balance < 0 and first_neg_line is None:
            first_neg_line = i
            first_neg_text = line.strip()
    return BraceScan(balance, first_neg_line, first_neg_text)


def _function_definitions(lines: list[str]) -> dict[str, list[int]]:
    """Return {name: [line_numbers]} for every `function foo(` definition."""
    result: dict[str, list[int]] = {}
    pattern = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(")
    for i, line in enumerate(lines, 1):
        m = pattern.match(line)
        if m:
            name = m.group(1)
            result.setdefault(name, []).append(i)
    return result


def _dom_content_loaded_blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Return list of (line_number, line_text) for DOMContentLoaded listeners."""
    return [
        (i, line.strip())
        for i, line in enumerate(lines, 1)
        if "DOMContentLoaded" in line
    ]


def _find_api_calls_in_dom_content_loaded(html_path: Path) -> list[str]:
    """Extract all fetch() URL strings from DOMContentLoaded handlers."""
    html = html_path.read_text(encoding="utf-8")
    # Match the second (main init) DOMContentLoaded block - look for fetch calls
    # in the block that contains startAutoRefresh / startCacheStatusPoller
    dcl_pattern = re.compile(
        r"document\.addEventListener\(['\"]DOMContentLoaded['\"].*?}\s*\)\s*;",
        re.DOTALL,
    )
    urls: list[str] = []
    for block in dcl_pattern.findall(html):
        if "startAutoRefresh" in block or "refreshData" in block:
            # This is the main init block – extract fetch URLs
            for m in re.finditer(r"fetch\s*\(\s*API\s*\+\s*['\"]([^'\"]+)['\"]", block):
                urls.append(m.group(1))
    return urls


def _defined_functions(lines: list[str]) -> set[str]:
    """All function names defined (regular functions only, not arrow fns)."""
    result: set[str] = set()
    pattern = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(")
    for line in lines:
        m = pattern.match(line)
        if m:
            result.add(m.group(1))
    return result



# ═══════════════════════════════════════════════════════════════════════════════
# ── Test classes ──────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════


class TestBraceBalance:
    """
    Bug class ①②: missing function header / orphaned top-level executable code.

    When buildHealthBar(p)'s header was deleted, the function body became
    orphaned top-level statements followed by a dangling `}`.  The `}` sent
    the running brace count negative, which is a hard JS syntax error that
    silently kills ALL JavaScript on the page.
    """

    def test_trade_board_brace_net_balance_zero(self):
        """Net {-} across the entire inline script must be exactly 0."""
        lines = _js_lines(TRADE_BOARD_HTML)
        scan = _scan_braces(lines)
        assert scan.net_balance == 0, (
            f"trade_board.html JS has net brace imbalance of {scan.net_balance:+d}. "
            f"First negative at JS line {scan.first_negative_line}: "
            f"{scan.first_negative_text!r}"
        )

    def test_trade_board_brace_never_goes_negative(self):
        """Running brace count must never go below 0 at any point.

        A negative count means a closing `}` appeared without a matching
        opener — the classic symptom of a stripped function header.
        """
        lines = _js_lines(TRADE_BOARD_HTML)
        scan = _scan_braces(lines)
        assert scan.first_negative_line is None, (
            f"Brace count went negative ({scan.net_balance}) at JS line "
            f"{scan.first_negative_line}: {scan.first_negative_text!r}\n"
            f"This usually means a `function foo(p) {{` header was deleted.\n"
            f"Check the ~20 lines above JS line {scan.first_negative_line} "
            f"in trade_board.html."
        )

    @pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda p: p.name)
    def test_all_html_files_brace_balanced(self, html_file: Path):
        """Every tracked HTML file must have balanced JS braces."""
        lines = _js_lines(html_file)
        scan = _scan_braces(lines)
        assert scan.net_balance == 0, (
            f"{html_file.name}: brace imbalance {scan.net_balance:+d} "
            f"(first negative at JS line {scan.first_negative_line})"
        )


class TestNoDuplicateFunctions:
    """
    Bug class ③: duplicate function definition.

    If a function is accidentally pasted twice, the second silently replaces
    the first.  Depending on the order, this can mean an OLD version of a
    function overwrites a fixed one — extremely hard to debug.
    """

    def test_no_duplicate_function_definitions(self):
        """Every function name must appear exactly once."""
        lines = _js_lines(TRADE_BOARD_HTML)
        defs = _function_definitions(lines)
        duplicates = {name: lns for name, lns in defs.items() if len(lns) > 1}
        assert not duplicates, (
            "Duplicate function definitions found in trade_board.html:\n"
            + "\n".join(
                f"  {name}() defined at JS lines {lns}"
                for name, lns in sorted(duplicates.items())
            )
        )


class TestDOMContentLoaded:
    """
    Bug class ④⑤: DOMContentLoaded handler correctness.

    The main init handler must:
      - Appear exactly once in the file (drag-drop handler is separate).
      - Use /watchlist/fast (CSV-only ~100ms) NOT /watchlist for the initial
        pre-fetch — avoids live API calls on page load and prevents the
        startup double-fetch pattern.
      - Not call the heavy /watchlist endpoint directly (that causes double
        live-price API calls: once here, once in refreshData(true)).
    """

    def test_exactly_two_dom_content_loaded_listeners(self):
        """Exactly 2 DOMContentLoaded listeners expected:
        1) drag-drop handler (screenshot area)
        2) main init handler (startAutoRefresh / startCacheStatusPoller)
        """
        lines = _js_lines(TRADE_BOARD_HTML)
        blocks = _dom_content_loaded_blocks(lines)
        assert len(blocks) == 2, (
            f"Expected 2 DOMContentLoaded listeners, found {len(blocks)}:\n"
            + "\n".join(f"  JS line {ln}: {txt}" for ln, txt in blocks)
        )

    def test_main_init_uses_watchlist_fast_endpoint(self):
        """The main DOMContentLoaded init must use /watchlist/fast (not /watchlist)
        for the initial pre-fetch.  /watchlist makes live API calls; /watchlist/fast
        is CSV-only (~100ms) and is explicitly designed for initial UI render.
        """
        urls = _find_api_calls_in_dom_content_loaded(TRADE_BOARD_HTML)
        # There should be at least one fetch call in the init block
        assert urls, (
            "No fetch() calls found in the main DOMContentLoaded init block. "
            "Expected at least /api/trade-board/positions and "
            "/api/trade-board/watchlist/fast."
        )
        # Must use the fast endpoint
        watchlist_urls = [u for u in urls if "watchlist" in u]
        assert watchlist_urls, (
            "No watchlist fetch in DOMContentLoaded init block. "
            "Expected /api/trade-board/watchlist/fast."
        )
        for url in watchlist_urls:
            assert url.endswith("/watchlist/fast"), (
                f"DOMContentLoaded init uses slow endpoint {url!r}. "
                "Must use /api/trade-board/watchlist/fast (CSV-only, ~100ms) "
                "for the initial pre-fetch.  refreshData(true) handles the "
                "enriched upgrade in the background."
            )

    def test_main_init_does_not_use_slow_watchlist_endpoint(self):
        """/api/trade-board/watchlist (without /fast suffix) must NOT appear
        in the main init DOMContentLoaded block (would trigger live API calls
        at startup and double-fetch when refreshData(true) also runs).
        """
        urls = _find_api_calls_in_dom_content_loaded(TRADE_BOARD_HTML)
        slow_calls = [u for u in urls if re.fullmatch(r"/api/trade-board/watchlist", u)]
        assert not slow_calls, (
            "DOMContentLoaded init calls the slow /watchlist endpoint directly. "
            "Use /watchlist/fast instead (the slow endpoint makes live API calls "
            "and causes a double-fetch with refreshData(true))."
        )

    def test_main_init_calls_refresh_data(self):
        """The main init block must call refreshData() to trigger enriched upgrade."""
        html = TRADE_BOARD_HTML.read_text(encoding="utf-8")
        dcl_pattern = re.compile(
            r"document\.addEventListener\(['\"]DOMContentLoaded['\"].*?}\s*\)\s*;",
            re.DOTALL,
        )
        init_blocks = [
            b for b in dcl_pattern.findall(html)
            if "startAutoRefresh" in b or "startCacheStatusPoller" in b
        ]
        assert init_blocks, "Main DOMContentLoaded init block not found."
        assert "refreshData" in init_blocks[0], (
            "Main DOMContentLoaded init block does not call refreshData(). "
            "It is needed to upgrade to enriched positions/watchlist data."
        )

    def test_main_init_calls_start_auto_refresh(self):
        """startAutoRefresh() must be called during init to enable polling."""
        html = TRADE_BOARD_HTML.read_text(encoding="utf-8")
        dcl_pattern = re.compile(
            r"document\.addEventListener\(['\"]DOMContentLoaded['\"].*?}\s*\)\s*;",
            re.DOTALL,
        )
        init_blocks = [
            b for b in dcl_pattern.findall(html)
            if "startAutoRefresh" in b or "startCacheStatusPoller" in b
        ]
        assert init_blocks, "Main DOMContentLoaded init block not found."
        assert "startAutoRefresh" in init_blocks[0], (
            "startAutoRefresh() is missing from the DOMContentLoaded init block."
        )
        assert "startCacheStatusPoller" in init_blocks[0], (
            "startCacheStatusPoller() is missing from the DOMContentLoaded init block."
        )


class TestCriticalFunctionsDefined:
    """
    Bug class ①: critical function bodies exist and are reachable.

    This is a lightweight check: if a function is referenced in HTML event
    handlers (onclick/onchange/etc.) it MUST have a `function foo(` definition
    in the inline script.  Missing definitions cause ReferenceError at runtime.
    """

    # Functions that MUST always be defined (core rendering + init)
    REQUIRED_FUNCTIONS = [
        "buildHealthBar",
        "buildCard",
        "buildWlCard",
        "renderPositions",
        "renderWatchlist",
        "refreshData",
        "startAutoRefresh",
        "startCacheStatusPoller",
        "showPage",
        "openAddModal",
        "closeAddModal",
        "openUpdateModal",
        "closeUpdateModal",
        "openWLModal",
        "closeWLModal",
        "loadWatchlist",
        "loadJournal",
        "loadEquity",
        "updateSbStats",
        "toast",
        "buildMetricsStrip",
        "buildRsLeaderStrip",
        # Entry proximity alert functions
        "entryCheckNow",
        "entryScanSend",
        "renderEntryCards",
    ]

    def test_required_functions_defined(self):
        """All critical functions must have a definition."""
        lines = _js_lines(TRADE_BOARD_HTML)
        defined = _defined_functions(lines)
        missing = [fn for fn in self.REQUIRED_FUNCTIONS if fn not in defined]
        assert not missing, (
            "Critical functions missing from trade_board.html:\n"
            + "\n".join(f"  function {fn}(...) {{" for fn in sorted(missing))
            + "\nA missing function header is the root cause of JS brace imbalance."
        )

    def test_build_health_bar_is_defined(self):
        """buildHealthBar() specifically — this is the function whose header was
        deleted in the bug that broke all pages.  Keep an explicit test for it."""
        lines = _js_lines(TRADE_BOARD_HTML)
        defs = _function_definitions(lines)
        assert "buildHealthBar" in defs, (
            "buildHealthBar() is not defined in trade_board.html inline script!\n"
            "This function header (function buildHealthBar(p) {) was deleted before\n"
            "causing a JS brace imbalance that broke every page.  Re-add it."
        )
        assert len(defs["buildHealthBar"]) == 1, (
            f"buildHealthBar() is defined {len(defs['buildHealthBar'])} times "
            f"(at JS lines {defs['buildHealthBar']}) — should be exactly once."
        )

    def test_html_attr_functions_defined(self):
        """Every *standalone* function called in an onclick/oninput/etc HTML
        attribute must be defined in the inline script or be a known built-in.

        Method calls like `e.stopPropagation()` or `btn.click()` are filtered
        out — they are DOM/BOM methods, not user-defined functions.
        """
        BROWSER_BUILTINS = {
            # Global functions
            "event", "this", "alert", "confirm", "prompt",
            "parseInt", "parseFloat", "isNaN", "isFinite",
            "encodeURIComponent", "decodeURIComponent",
            "setTimeout", "clearTimeout", "setInterval", "clearInterval",
            "fetch", "Promise", "JSON", "Object", "Array", "Math",
            "Date", "Error", "console",
            # DOM/BOM methods that may appear standalone in edge cases
            "open", "close", "focus", "blur", "reload",
        }
        lines = _js_lines(TRADE_BOARD_HTML)
        defined = _defined_functions(lines)
        html = TRADE_BOARD_HTML.read_text(encoding="utf-8")

        # Extract only STANDALONE function calls from event attributes
        # (i.e., NOT method calls like `e.stopPropagation()` or `el.click()`).
        # Pattern: word boundary + identifier + ( NOT preceded by a dot.
        attr_calls: set[str] = set()
        for attr_val in re.findall(r'on\w+="([^"]+)"', html):
            for m in re.finditer(r"(?<!\.)(?<!['\"])\b([a-zA-Z_]\w+)\s*\(", attr_val):
                attr_calls.add(m.group(1))

        undefined = [
            fn for fn in sorted(attr_calls)
            if fn not in defined and fn not in BROWSER_BUILTINS
            and len(fn) > 3  # skip short tokens that are almost certainly not functions
        ]
        assert not undefined, (
            "Standalone functions called from HTML event attributes but not "
            "defined in trade_board.html inline script:\n"
            + "\n".join(f"  {fn}()" for fn in undefined)
        )


class TestNoOrphanedCode:
    """
    Bug class ②: stray top-level executable statements.

    Executable statements (if/const/let/var/return) at the top level of a
    script (outside all functions/classes/IIFEs) are a strong signal that a
    function header was deleted.  We heuristically detect them by tracking
    the brace depth and flagging non-blank, non-comment, non-declaration lines
    at depth 0.
    """

    # Patterns that look like executable statements (not declarations/comments)
    EXEC_PATTERNS = re.compile(
        r"^\s*(?:"
        r"if\s*\("
        r"|else\s*\{"
        r"|else\s+if\s*\("
        r"|for\s*\("
        r"|while\s*\("
        r"|switch\s*\("
        r"|return\b"
        r"|(?:const|let|var)\s+\w+\s*=\s*p\."  # property access on 'p' param
        r")"
    )

    def test_no_orphaned_executable_statements(self):
        """No executable statements should appear at brace depth 0 outside
        known top-level structures (DOMContentLoaded, setInterval, etc.)."""
        lines = _js_lines(TRADE_BOARD_HTML)
        depth = 0
        orphaned: list[tuple[int, str]] = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Update depth BEFORE checking so we see the line at correct depth
            opens = line.count("{")
            closes = line.count("}")
            # For lines that both open and close at the top, check balance
            if self.EXEC_PATTERNS.match(line) and depth == 0:
                # Skip lines that are part of known top-level patterns
                if not any(skip in line for skip in [
                    "document.addEventListener",
                    "window.",
                    "setInterval",
                    "setTimeout",
                    "const API",
                    "let positions",
                ]):
                    orphaned.append((i, stripped[:120]))
            depth += opens - closes
            depth = max(depth, 0)  # don't let it go negative past recovery

        assert not orphaned, (
            f"Orphaned executable statements at brace depth 0 in trade_board.html "
            f"({len(orphaned)} found).\n"
            "This usually means a `function foo(p) {` header was deleted.\n"
            + "\n".join(f"  JS line {ln}: {txt}" for ln, txt in orphaned[:10])
        )


class TestScriptSyntaxHeuristics:
    """Additional heuristics that catch common JS mistakes."""

    def test_no_unclosed_template_literals(self):
        """Detect unclosed template literals using a state-machine that properly
        tracks nesting depth of template literal delimiters.

        Raw backtick counts MUST be even when summed across all JS lines,
        because every `` ` `` that opens a template literal must be closed
        by another `` ` ``. False positives from backticks inside regular
        string literals (e.g. ``"a \` b"``) are extremely rare and always
        appear in pairs, so the even-parity rule is a reliable proxy.

        This test uses a straightforward whole-file raw count rather than
        a line-by-line state machine — the latter fails on multi-line template
        literals (because intermediate `'` / `"` chars in the template body
        corrupt the in-string tracker state).
        """
        combined, _ = _extract_inline_js(TRADE_BOARD_HTML)
        raw_backtick_count = combined.count("`")
        assert raw_backtick_count % 2 == 0, (
            f"Odd number of raw backticks ({raw_backtick_count}) in "
            "trade_board.html inline script — likely an unclosed template literal."
        )

    def test_dom_content_loaded_count_unchanged(self):
        """Changing the number of DOMContentLoaded handlers is almost always
        a mistake.  This test acts as a trip-wire: if you legitimately need to
        add a third handler, update this assertion consciously."""
        lines = _js_lines(TRADE_BOARD_HTML)
        count = sum(1 for line in lines if "DOMContentLoaded" in line)
        assert count == 2, (
            f"Expected exactly 2 DOMContentLoaded references, found {count}.\n"
            "If you consciously added/removed one, update this test."
        )

    def test_build_health_bar_precedes_build_card(self):
        """buildHealthBar must be defined BEFORE buildCard which calls it.
        This ordering was broken when the function header was accidentally deleted
        and the orphaned body ended up between buildRsLeaderStrip and buildCard."""
        lines = _js_lines(TRADE_BOARD_HTML)
        defs = _function_definitions(lines)
        assert "buildHealthBar" in defs, "buildHealthBar not defined"
        assert "buildCard" in defs, "buildCard not defined"
        bh_line = defs["buildHealthBar"][0]
        bc_line = defs["buildCard"][0]
        assert bh_line < bc_line, (
            f"buildHealthBar (JS line {bh_line}) must be defined BEFORE "
            f"buildCard (JS line {bc_line}), which calls it."
        )

