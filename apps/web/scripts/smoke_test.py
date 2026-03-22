#!/usr/bin/env python3
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

    jobs = client.get("/api/jobs")
    assert jobs.status_code == 200, jobs.text
    assert isinstance(jobs.json().get("jobs"), list)

    print("Smoke test passed: /api/health and /api/jobs")


if __name__ == "__main__":
    main()

