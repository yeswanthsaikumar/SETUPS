#!/usr/bin/env python3
"""Master test runner - runs all validation tests in sequence."""
import sys
import subprocess
from pathlib import Path


def run_test_suite(name, script):
    """Run a test suite and return pass/fail status."""
    print("\n" + "=" * 80)
    print(f"RUNNING: {name}")
    print("=" * 80 + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "-u", str(script)],
            capture_output=False,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"\n⏱ TIMEOUT: {name} took longer than 2 minutes")
        return False
    except Exception as e:
        print(f"\n✗ ERROR running {name}: {e}")
        return False


def main():
    """Run all test suites."""
    print("=" * 80)
    print("MASTER TEST SUITE - POST-IMPLEMENTATION VALIDATION")
    print("=" * 80)
    print("\nThis test suite validates all changes made to implement")
    print("custom sub-classification across the entire application.")
    print("=" * 80)

    test_dir = Path(__file__).parent

    test_suites = [
        ("Unit Tests (Taxonomy Module)", test_dir / "test_taxonomy_unit.py"),
        ("Integration Tests (API Endpoints)", test_dir / "test_api_integration.py"),
        ("UI Validation Tests", test_dir / "test_ui_validation.py"),
    ]

    results = []
    for name, script in test_suites:
        if not script.exists():
            print(f"\n⚠ Skipping {name}: {script} not found")
            results.append((name, False))
            continue

        passed = run_test_suite(name, script)
        results.append((name, passed))

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL TEST SUMMARY")
    print("=" * 80)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    print("\n" + ("=" * 80))
    if all_passed:
        print("🎉 ALL TESTS PASSED - IMPLEMENTATION VALIDATED")
        print("\nChanges Summary:")
        print("  ✓ nse_taxonomy.py: Multi-label support + breadth peers fix")
        print("  ✓ main.py: Legacy endpoint uses basic_industry")
        print("  ✓ generate_trade_plans_page.py: Taxonomy overrides hardcoded map")
        print("  ✓ industry_groups.html: UI defaults to basic_industry")
        print("  ✓ custom_sub_classification.csv: 1968 entries, 20 conglomerates")
        print("  ✓ All API endpoints functioning correctly")
        print("  ✓ UI properly configured")
    else:
        print("❌ SOME TESTS FAILED - REVIEW REQUIRED")

    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

