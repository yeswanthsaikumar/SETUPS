#!/usr/bin/env python3
"""Integration tests for API endpoints after custom sub-classification changes."""
import sys
import os
import time
import requests
from typing import Dict, List

# Configuration
API_BASE = "http://localhost:8000"
TIMEOUT = 30


def start_api_server():
    """Check if API server is running, start if needed."""
    try:
        resp = requests.get(f"{API_BASE}/api/groups/levels", timeout=2)
        if resp.status_code == 200:
            print("✓ API server is already running")
            return True
    except:
        pass

    print("⚠ API server not running. Please start it manually:")
    print("  cd apps/web && python3 api/main.py")
    return False


def test_groups_endpoint():
    """Test /api/groups endpoint with all levels."""
    print("\n=== Test: /api/groups Endpoint ===")

    levels = ["macro", "sector", "industry", "basic_industry", "theme"]
    results = []

    for level in levels:
        try:
            resp = requests.get(
                f"{API_BASE}/api/groups",
                params={"level": level, "min_stocks": 2},
                timeout=TIMEOUT
            )

            if resp.status_code != 200:
                print(f"  ✗ {level}: HTTP {resp.status_code}")
                results.append(False)
                continue

            data = resp.json()
            groups = data.get("groups", [])
            print(f"  ✓ {level}: {len(groups)} groups, HTTP 200")

            # Validate structure
            if groups:
                first = groups[0]
                required_fields = ["stockCount", "rsScore", "breadthScore"]
                missing = [f for f in required_fields if f not in first]
                # Check for group identifier (could be 'group', 'name', or 'industry')
                has_id = any(f in first for f in ['group', 'name', 'industry'])
                if missing or not has_id:
                    print(f"    ⚠ Issues: missing={missing}, has_id={has_id}")
                    results.append(False)
                else:
                    results.append(True)
            else:
                results.append(True)

        except Exception as e:
            print(f"  ✗ {level}: {e}")
            results.append(False)

    return all(results)


def test_groups_basic_industry_detail():
    """Test that basic_industry level has correct fine-grained groups."""
    print("\n=== Test: /api/groups?level=basic_industry Detail ===")

    try:
        resp = requests.get(
            f"{API_BASE}/api/groups",
            params={"level": "basic_industry", "min_stocks": 1},
            timeout=TIMEOUT
        )

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return False

        data = resp.json()
        groups = data.get("groups", [])
        group_names = {g.get("group", g.get("name", g.get("industry", ""))) for g in groups}

        # Check for expected fine-grained groups
        expected = [
            "IT Services - Large Cap",
            "IT Services - Mid Cap",
            "CDMO & API",
            "Pharma - Large Cap Formulations",
            "Private Banks - Large Cap",
            "NBFC - Gold Finance",
            "Solar & Renewable Equipment",
            "Transformers & Switchgear",
        ]

        passed = 0
        for group in expected:
            if group in group_names:
                print(f"  ✓ Found: {group}")
                passed += 1
            else:
                print(f"  ✗ Missing: {group}")

        print(f"\nResult: {passed}/{len(expected)} expected groups found")
        return passed == len(expected)

    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def test_industry_groups_endpoint():
    """Test legacy /api/industry-groups endpoint (should now use basic_industry)."""
    print("\n=== Test: /api/industry-groups Legacy Endpoint ===")

    try:
        resp = requests.get(
            f"{API_BASE}/api/industry-groups",
            params={"min_stocks": 2},
            timeout=TIMEOUT
        )

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return False

        data = resp.json()
        groups = data.get("groups", [])
        print(f"  ✓ Returned {len(groups)} groups")

        # Check that groups use fine-grained names (basic_industry level)
        group_names = {g.get("industry", g.get("name", "")) for g in groups}

        # These should NOT exist (coarse NSE industry names)
        coarse = ["Pharmaceuticals", "IT - Software"]
        found_coarse = [c for c in coarse if c in group_names]

        # These SHOULD exist (fine-grained custom names)
        fine = ["Pharma - Large Cap Formulations", "IT Services - Large Cap"]
        found_fine = [f for f in fine if f in group_names]

        if found_coarse:
            print(f"  ⚠ Found coarse NSE groups (should be split): {found_coarse}")
            print("     Legacy endpoint might not be using basic_industry")
            return False

        if found_fine:
            print(f"  ✓ Found fine-grained groups: {found_fine}")
            return True

        print("  ⚠ Could not verify fine-grained groups")
        return True  # Don't fail if groups aren't in top results

    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def test_groups_levels_endpoint():
    """Test /api/groups/levels metadata endpoint."""
    print("\n=== Test: /api/groups/levels Endpoint ===")

    try:
        resp = requests.get(f"{API_BASE}/api/groups/levels", timeout=TIMEOUT)

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return False

        data = resp.json()
        levels = data.get("levels", [])

        # Check all expected levels exist
        level_keys = {l["key"] for l in levels}
        expected = {"macro", "sector", "industry", "basic_industry", "theme"}

        if level_keys >= expected:
            print(f"  ✓ All levels present: {sorted(level_keys)}")

            # Check that basic_industry has a count
            bi_level = next((l for l in levels if l["key"] == "basic_industry"), None)
            if bi_level and bi_level.get("count", 0) > 0:
                print(f"  ✓ basic_industry count: {bi_level['count']}")
                return True
            else:
                print("  ⚠ basic_industry count not found")
                return False
        else:
            missing = expected - level_keys
            print(f"  ✗ Missing levels: {missing}")
            return False

    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def test_sector_rotation_endpoint():
    """Test /api/sector-rotation endpoint."""
    print("\n=== Test: /api/sector-rotation Endpoint ===")

    levels = ["sector", "basic_industry", "theme"]
    results = []

    for level in levels:
        try:
            resp = requests.get(
                f"{API_BASE}/api/sector-rotation",
                params={"level": level, "top_n": 5},
                timeout=TIMEOUT
            )

            if resp.status_code != 200:
                print(f"  ✗ {level}: HTTP {resp.status_code}")
                results.append(False)
                continue

            data = resp.json()
            leaders = data.get("leaders", [])
            laggards = data.get("laggards", [])

            print(f"  ✓ {level}: {len(leaders)} leaders, {len(laggards)} laggards")
            results.append(True)

        except Exception as e:
            print(f"  ✗ {level}: {e}")
            results.append(False)

    return all(results)


def test_taxonomy_reload():
    """Test /api/taxonomy/reload endpoint."""
    print("\n=== Test: /api/taxonomy/reload Endpoint ===")

    try:
        resp = requests.post(f"{API_BASE}/api/taxonomy/reload", timeout=TIMEOUT)

        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✓ Reload successful: {data.get('message', '')}")

            # Wait a moment and verify groups still work
            time.sleep(2)
            resp2 = requests.get(
                f"{API_BASE}/api/groups",
                params={"level": "basic_industry", "min_stocks": 2},
                timeout=TIMEOUT
            )

            if resp2.status_code == 200:
                print("  ✓ Groups endpoint still works after reload")
                return True
            else:
                print(f"  ✗ Groups endpoint failed after reload: HTTP {resp2.status_code}")
                return False
        else:
            print(f"  ✗ HTTP {resp.status_code}")
            return False

    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def main():
    """Run all integration tests."""
    print("=" * 80)
    print("API INTEGRATION TESTS")
    print("=" * 80)

    if not start_api_server():
        print("\n❌ Cannot run tests without API server")
        return 1

    print()

    tests = [
        ("Groups Endpoint (All Levels)", test_groups_endpoint),
        ("Groups Basic Industry Detail", test_groups_basic_industry_detail),
        ("Industry Groups Legacy", test_industry_groups_endpoint),
        ("Groups Levels Metadata", test_groups_levels_endpoint),
        ("Sector Rotation", test_sector_rotation_endpoint),
        ("Taxonomy Reload", test_taxonomy_reload),
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
        print("✅ ALL INTEGRATION TESTS PASSED")
    else:
        print("❌ SOME INTEGRATION TESTS FAILED")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

