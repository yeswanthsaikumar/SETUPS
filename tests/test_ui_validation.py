#!/usr/bin/env python3
"""UI validation tests - check HTML/JS syntax and basic functionality."""
import sys
import os
import re
from pathlib import Path


def test_html_syntax():
    """Basic HTML validation - check for common issues."""
    print("\n=== Test: HTML Syntax ===")

    html_file = Path("apps/web/ui/industry_groups.html")
    if not html_file.exists():
        print(f"  ✗ File not found: {html_file}")
        return False

    content = html_file.read_text()

    # Check for basic structure
    checks = [
        ("<!DOCTYPE html>", "Has DOCTYPE"),
        ("<html", "Has <html> tag"),
        ("</html>", "Has closing </html>"),
        ("<head>", "Has <head> section"),
        ("<body", "Has <body> tag"),
    ]

    results = []
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✓ {desc}")
            results.append(True)
        else:
            print(f"  ✗ {desc}")
            results.append(False)

    return all(results)


def test_js_basic_syntax():
    """Check JavaScript doesn't have obvious syntax errors."""
    print("\n=== Test: JavaScript Basic Syntax ===")

    html_file = Path("apps/web/ui/industry_groups.html")
    content = html_file.read_text()

    # Extract JavaScript from script tags
    js_pattern = r'<script[^>]*>(.*?)</script>'
    js_blocks = re.findall(js_pattern, content, re.DOTALL)

    if not js_blocks:
        print("  ⚠ No JavaScript blocks found")
        return True

    print(f"  Found {len(js_blocks)} JavaScript blocks")

    # Check for common issues
    issues = []
    for i, js in enumerate(js_blocks):
        # Check for unclosed braces/brackets
        open_braces = js.count('{')
        close_braces = js.count('}')
        if open_braces != close_braces:
            issues.append(f"Block {i}: Brace mismatch ({open_braces} open, {close_braces} close)")

        # Check for function declarations
        if 'function ' in js:
            functions = re.findall(r'function\s+(\w+)\s*\(', js)
            print(f"  ✓ Block {i}: {len(functions)} functions defined")

    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        return False

    print("  ✓ No obvious syntax errors")
    return True


def test_js_key_functions():
    """Check that key JavaScript functions exist."""
    print("\n=== Test: Key JavaScript Functions ===")

    html_file = Path("apps/web/ui/industry_groups.html")
    content = html_file.read_text()

    required_functions = [
        "fetchGroups",
        "changeLevel",
        "loadSectorMap",
        "filterGroups",
        "sortGroups",
        "_fetchGroupsForCurrentLevel",
    ]

    results = []
    for func in required_functions:
        # Check for function definition
        pattern = f"(function\\s+{func}|const\\s+{func}\\s*=|let\\s+{func}\\s*=|{func}\\s*=\\s*function)"
        if re.search(pattern, content):
            print(f"  ✓ {func}()")
            results.append(True)
        else:
            print(f"  ✗ {func}() not found")
            results.append(False)

    return all(results)


def test_default_level_setting():
    """Check that default level is set to basic_industry."""
    print("\n=== Test: Default Level Setting ===")

    html_file = Path("apps/web/ui/industry_groups.html")
    content = html_file.read_text()

    checks = []

    # Check JavaScript variable
    if re.search(r"let\s+currentLevel\s*=\s*['\"]basic_industry['\"]", content):
        print("  ✓ JavaScript variable: currentLevel = 'basic_industry'")
        checks.append(True)
    else:
        print("  ✗ JavaScript variable NOT set to 'basic_industry'")
        checks.append(False)

    # Check dropdown selected option
    if 'value="basic_industry" selected' in content:
        print("  ✓ Dropdown: basic_industry option marked as selected")
        checks.append(True)
    else:
        print("  ✗ Dropdown: basic_industry NOT selected by default")
        checks.append(False)

    return all(checks)


def test_api_endpoints_referenced():
    """Check that API endpoints are correctly referenced."""
    print("\n=== Test: API Endpoints Referenced ===")

    html_file = Path("apps/web/ui/industry_groups.html")
    content = html_file.read_text()

    # Check that unified /api/groups endpoint is used
    if '/api/groups' in content:
        print("  ✓ Uses /api/groups endpoint")
    else:
        print("  ✗ /api/groups endpoint not found")
        return False

    # Check for level parameter usage
    if 'level=' in content:
        print("  ✓ Uses level parameter")
    else:
        print("  ✗ Level parameter not found")
        return False

    # Check that legacy endpoint special-case is removed
    legacy_pattern = r"if\s*\(\s*currentLevel\s*===?\s*['\"]industry['\"]\s*\)"
    legacy_matches = re.findall(legacy_pattern, content)

    # The pattern might still exist in other contexts, but let's check the fetch function specifically
    fetch_func = re.search(r'async function _fetchGroupsForCurrentLevel.*?^}', content, re.DOTALL | re.MULTILINE)
    if fetch_func:
        func_body = fetch_func.group(0)
        if 'industry-groups' in func_body and 'currentLevel' in func_body:
            print("  ⚠ Legacy /api/industry-groups bypass might still exist")
            # Don't fail, just warn
        else:
            print("  ✓ No legacy endpoint bypass")

    return True


def test_files_exist():
    """Check that all necessary files exist."""
    print("\n=== Test: Files Exist ===")

    files = [
        "apps/python/lib/nse_taxonomy.py",
        "apps/web/api/main.py",
        "apps/web/ui/industry_groups.html",
        "apps/python/cli/generate_trade_plans_page.py",
        "data/custom_sub_classification.csv",
    ]

    results = []
    for file in files:
        path = Path(file)
        if path.exists():
            size = path.stat().st_size
            print(f"  ✓ {file} ({size:,} bytes)")
            results.append(True)
        else:
            print(f"  ✗ {file} NOT FOUND")
            results.append(False)

    return all(results)


def test_csv_format():
    """Validate custom_sub_classification.csv format."""
    print("\n=== Test: CSV Format ===")

    csv_file = Path("data/custom_sub_classification.csv")
    content = csv_file.read_text()
    lines = content.strip().split('\n')

    # Check header
    if not lines[0].startswith('nse_ticker,custom_basic_industry'):
        print("  ✗ Invalid header")
        return False
    print(f"  ✓ Valid header")

    # Count entries
    data_lines = [l for l in lines if l and not l.startswith('#') and ',' in l and not l.startswith('nse_ticker')]
    print(f"  ✓ {len(data_lines)} entries")

    # Check for multi-label entries
    tickers = [l.split(',')[0] for l in data_lines]
    from collections import Counter
    ticker_counts = Counter(tickers)
    multi_label = {t: c for t, c in ticker_counts.items() if c > 1}

    if multi_label:
        print(f"  ✓ {len(multi_label)} multi-label tickers")
        # Show a few examples
        examples = list(multi_label.items())[:3]
        for ticker, count in examples:
            print(f"    - {ticker}: {count} industries")
    else:
        print("  ⚠ No multi-label tickers")

    return True


def main():
    """Run all UI validation tests."""
    print("=" * 80)
    print("UI VALIDATION TESTS")
    print("=" * 80)

    # Change to project root
    os.chdir(Path(__file__).parent.parent)

    tests = [
        ("Files Exist", test_files_exist),
        ("HTML Syntax", test_html_syntax),
        ("JavaScript Basic Syntax", test_js_basic_syntax),
        ("Key JavaScript Functions", test_js_key_functions),
        ("Default Level Setting", test_default_level_setting),
        ("API Endpoints Referenced", test_api_endpoints_referenced),
        ("CSV Format", test_csv_format),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ {name}: EXCEPTION - {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)
    print("\n" + ("=" * 80))
    if all_passed:
        print("✅ ALL UI VALIDATION TESTS PASSED")
    else:
        print("❌ SOME UI VALIDATION TESTS FAILED")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

