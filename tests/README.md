# Test Suite Organization

This directory contains all tests for the SETUPS project, organized by test type.

## Structure

```
tests/
├── README.md                      # This file
├── run_all_tests.py              # Master test runner
├── conftest.py                   # Shared pytest fixtures
│
├── test_taxonomy_unit.py         # Core taxonomy module tests
├── test_api_integration.py       # API endpoint integration tests
├── test_ui_validation.py         # UI validation tests
│
├── unit/                         # Unit tests
│   ├── test_taxonomy_fixes.py
│   ├── test_taxonomy_enriched.py
│   ├── test_market_breadth.py
│   ├── test_custom_alert_rules.py
│   ├── test_groww_client.py
│   ├── test_html_js_integrity.py
│   ├── test_refresh_cache.py
│   ├── test_setup_detector_math.py
│   ├── test_trading_wisdom.py
│   ├── test_utils.py
│   └── test_vpn_manager.py
│
├── api/                          # API integration tests
│   ├── test_cache_refresh.py
│   ├── test_cache_staleness_integration.py
│   ├── test_custom_alert_rules_api.py
│   ├── test_groups_endpoints.py
│   ├── test_health_and_vpn.py
│   ├── test_periodic_refresh.py
│   ├── test_playbook.py
│   ├── test_trade_board.py
│   ├── test_watchlist_and_scan.py
│   ├── test_wisdom_api.py
│   └── test_wisdom_freshness.py
│
├── ui/                           # UI/browser tests
│   ├── conftest.py
│   ├── test_card_hover.py
│   ├── test_equity_chart.py
│   ├── test_features.py
│   ├── test_trade_board_ui.py
│   ├── test_wisdom_layer.py
│   ├── test_wisdom_navigation.py
│   └── test_wisdom_panel.py
│
└── e2e/                          # End-to-end tests
    ├── test_scan_pipeline.py
    └── test_smoke.py
```

## Running Tests

### Run All Tests

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 tests/run_all_tests.py
```

### Run Specific Test Suites

#### Main Test Suites
```bash
python3 tests/test_taxonomy_unit.py       # Taxonomy module unit tests
python3 tests/test_api_integration.py     # API endpoint integration tests
python3 tests/test_ui_validation.py       # UI validation tests
```

#### Unit Tests
```bash
python3 tests/unit/test_taxonomy_fixes.py
python3 tests/unit/test_taxonomy_enriched.py
python3 tests/unit/test_market_breadth.py
python3 tests/unit/test_custom_alert_rules.py
```

#### API Tests
```bash
python3 tests/api/test_groups_endpoints.py
python3 tests/api/test_wisdom_api.py
python3 tests/api/test_trade_board.py
```

#### End-to-End Tests
```bash
python3 tests/e2e/test_smoke.py           # Quick smoke test
python3 tests/e2e/test_scan_pipeline.py   # Full pipeline test
```

### Run with pytest

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 -m pytest tests/                  # All tests
python3 -m pytest tests/unit/             # Unit tests only
python3 -m pytest tests/api/              # API tests only
python3 -m pytest tests/ui/               # UI tests only
python3 -m pytest tests/e2e/              # E2E tests only
```

## Test Categories

### Unit Tests (`unit/`)
Fast, isolated tests for individual functions and modules. No external dependencies.

### API Tests (`api/`)
Integration tests for API endpoints. Requires the web server to be running.

### UI Tests (`ui/`)
Browser-based tests for UI functionality. May require Selenium or similar tools.

### E2E Tests (`e2e/`)
End-to-end tests that exercise the full application pipeline.

## Test Requirements

Most tests require:
- Python 3.x
- Dependencies from `requirements-dev.txt`

API and E2E tests may also require:
- Running web server (`uvicorn apps.web.api.main:app`)
- Dependencies from `requirements-web.txt`

## Recent Changes

**April 26, 2026**: All test files moved to the `tests/` directory structure:
- Moved `scripts/test_taxonomy_fixes.py` → `tests/unit/test_taxonomy_fixes.py`
- Moved `apps/web/scripts/smoke_test.py` → `tests/e2e/test_smoke.py`
- Updated `apps/web/README.md` to reflect new test locations
- All tests passing after reorganization

## Contributing

When adding new tests:
1. Place them in the appropriate subdirectory based on test type
2. Follow the naming convention: `test_*.py`
3. Add fixtures to `conftest.py` if shared across multiple tests
4. Update this README if adding new test categories

