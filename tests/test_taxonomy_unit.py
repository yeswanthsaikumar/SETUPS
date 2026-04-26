#!/usr/bin/env python3
"""Unit tests for nse_taxonomy module after custom sub-classification changes."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'python'))

from lib import nse_taxonomy as tax

def test_basic_industry_classification():
    """Test that custom sub-classification is loaded correctly."""
    print("\n=== Test: Basic Industry Classification ===")

    tests = {
        # Electrical Equipment splits
        "ABB": "Electrical Equipments - HVDC",
        "VOLTAMP": "Transformers & Switchgear",
        "SUZLON": "Wind Energy Equipment",
        "WAAREEENER": "Solar & Renewable Equipment",

        # IT Services splits
        "TCS": "IT Services - Large Cap",
        "COFORGE": "IT Services - Mid Cap",
        "3IINFOLTD": "IT Services - Small Cap",
        "CYIENT": "IT - Engineering Services",

        # Pharma splits
        "SUNPHARMA": "Pharma - Large Cap Formulations",
        "DIVISLAB": "CDMO & API",
        "LALPATHLAB": "Diagnostics",

        # Banks
        "HDFCBANK": "Private Banks - Large Cap",
        "FEDERALBNK": "Private Banks - Mid Cap",
        "SBIN": "PSU Banks - Large Cap",

        # NBFC
        "BAJFINANCE": "NBFC - Diversified Retail Finance",
        "CHOLAFIN": "NBFC - Vehicle & Equipment Finance",
        "MUTHOOTFIN": "NBFC - Gold Finance",
    }

    passed = 0
    failed = []
    for ticker, expected in tests.items():
        actual = tax.get_basic_industry(ticker)
        if actual == expected:
            passed += 1
            print(f"  ✓ {ticker}: {actual}")
        else:
            failed.append((ticker, expected, actual))
            print(f"  ✗ {ticker}: expected {expected!r}, got {actual!r}")

    print(f"\nResult: {passed}/{len(tests)} passed")
    return len(failed) == 0, failed


def test_multi_label_conglomerates():
    """Test that multi-label conglomerates appear in multiple groups."""
    print("\n=== Test: Multi-label Conglomerates ===")

    tests = {
        "RELIANCE": ["Refineries & Marketing", "Telecom - Cellular & Fixed Line",
                     "Diversified Retail", "Petrochemicals"],
        "ITC": ["Packaged Foods - Large & Mid Cap", "Premium Hotels", "Paper & Paper Products"],
        "M&M": ["Passenger Cars & Utility Vehicles", "Tractors & Farm Equipment",
                "NBFC - Vehicle & Equipment Finance"],
        "TATAPOWER": ["Power - Thermal & Conventional", "Power - Renewable & Green",
                      "Solar & Renewable Equipment"],
        "VEDL": ["Aluminium Copper & Zinc Products", "Oil Exploration & Production",
                 "Steel - Large Cap", "Power - Thermal & Conventional"],
    }

    groups = tax.group_tickers_by("basic_industry")
    passed = 0
    failed = []

    for ticker, expected_groups in tests.items():
        primary = tax.get_basic_industry(ticker)
        print(f"\n  {ticker} (primary: {primary})")

        ticker_passed = True
        for group in expected_groups:
            if group in groups and ticker in groups[group]:
                print(f"    ✓ Found in '{group}'")
                passed += 1
            else:
                print(f"    ✗ NOT in '{group}'")
                failed.append((ticker, group))
                ticker_passed = False

    total_expected = sum(len(g) for g in tests.values())
    print(f"\nResult: {passed}/{total_expected} group memberships verified")
    return len(failed) == 0, failed


def test_breadth_peers():
    """Test that get_breadth_peers uses basic_industry correctly."""
    print("\n=== Test: Breadth Peers ===")

    tests = {
        "CDMO & API": ["DIVISLAB", "LAURUSLABS", "BIOCON", "SYNGENE"],
        "IT Services - Large Cap": ["TCS", "INFY", "WIPRO", "HCLTECH"],
        "Private Banks - Large Cap": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK"],
        "Solar & Renewable Equipment": ["WAAREEENER", "SAATVIKGL"],
    }

    passed = 0
    failed = []

    for group, expected_tickers in tests.items():
        peers = tax.get_breadth_peers(group)
        print(f"\n  {group}: {len(peers)} peers")

        for ticker in expected_tickers:
            if ticker in peers:
                print(f"    ✓ {ticker}")
                passed += 1
            else:
                print(f"    ✗ {ticker} NOT FOUND")
                failed.append((group, ticker))

    total = sum(len(t) for t in tests.values())
    print(f"\nResult: {passed}/{total} peers found")
    return len(failed) == 0, failed


def test_list_functions():
    """Test list_* functions."""
    print("\n=== Test: List Functions ===")

    macros = tax.list_macros()
    sectors = tax.list_sectors()
    industries = tax.list_industries()
    basic_industries = tax.list_basic_industries()

    print(f"  Macros: {len(macros)}")
    print(f"  Sectors: {len(sectors)}")
    print(f"  Industries: {len(industries)}")
    print(f"  Basic Industries: {len(basic_industries)}")

    # Should have many more basic_industries than industries due to custom sub-classification
    assert len(basic_industries) > len(industries), \
        f"Expected more basic_industries ({len(basic_industries)}) than industries ({len(industries)})"

    # Verify some known groups exist
    assert "IT Services - Large Cap" in basic_industries
    assert "CDMO & API" in basic_industries
    assert "Private Banks - Large Cap" in basic_industries

    print("  ✓ All list functions working")
    return True, []


def test_group_tickers_by():
    """Test group_tickers_by for all levels."""
    print("\n=== Test: group_tickers_by ===")

    levels = ["macro", "sector", "industry", "basic_industry", "theme"]
    results = []

    for level in levels:
        try:
            groups = tax.group_tickers_by(level)
            total_tickers = sum(len(tickers) for tickers in groups.values())
            print(f"  {level}: {len(groups)} groups, {total_tickers} total memberships")
            results.append(True)
        except Exception as e:
            print(f"  ✗ {level}: ERROR - {e}")
            results.append(False)

    return all(results), []


def main():
    """Run all unit tests."""
    print("=" * 80)
    print("TAXONOMY MODULE UNIT TESTS")
    print("=" * 80)

    tests = [
        ("Basic Industry Classification", test_basic_industry_classification),
        ("Multi-label Conglomerates", test_multi_label_conglomerates),
        ("Breadth Peers", test_breadth_peers),
        ("List Functions", test_list_functions),
        ("Group Tickers By", test_group_tickers_by),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed, failures = test_func()
            results.append((name, passed, failures))
        except Exception as e:
            print(f"\n✗ {name}: EXCEPTION - {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False, [str(e)]))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for name, passed, failures in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if failures:
            print(f"  Failures: {failures[:5]}")  # Show first 5

    all_passed = all(passed for _, passed, _ in results)
    print("\n" + ("=" * 80))
    if all_passed:
        print("✅ ALL UNIT TESTS PASSED")
    else:
        print("❌ SOME UNIT TESTS FAILED")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

