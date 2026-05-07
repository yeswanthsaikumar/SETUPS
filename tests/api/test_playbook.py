"""Tests for the Trading Playbook daily-read endpoints."""
from __future__ import annotations


class TestPlaybookPage:
    def test_page_served(self, api_client):
        r = api_client.get("/playbook")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        body = r.text.lower()
        assert "trading playbook" in body
        # The reader page calls the markdown endpoint
        assert "/api/playbook/markdown" in r.text


class TestPlaybookMarkdown:
    def test_markdown_served(self, api_client):
        r = api_client.get("/api/playbook/markdown")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/markdown" in ct or "text/plain" in ct
        # Must contain recognisable playbook structure
        assert "# The Trading Playbook" in r.text
        assert "TABLE OF CONTENTS" in r.text
        # No-store so the reader always sees today's copy
        assert r.headers.get("cache-control") == "no-store"


class TestPlaybookDownload:
    def test_download_is_self_contained_html(self, api_client):
        r = api_client.get("/api/playbook/download")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        body = r.text
        # Cover page
        assert "<title>The Trading Playbook" in body
        assert "Cmd+P" in body  # print hint
        # Content has been rendered from markdown
        assert "<h2" in body and "Why Chart Patterns Work" in body
        # Self-contained — no remote <script src=…> pulls (styles are inline)
        assert "cdn.jsdelivr.net" not in body
        assert "<script src=\"http" not in body

    def test_download_has_tables_rendered(self, api_client):
        r = api_client.get("/api/playbook/download")
        # The playbook has GFM tables (e.g. the 4-stage table). Must render.
        assert "<table>" in r.text
        assert "<th>" in r.text


class TestPlaybookBlogMeta:
    def test_event_gap_risk_doc_is_exposed_in_meta(self, api_client):
        r = api_client.get("/api/playbook/meta")
        assert r.status_code == 200
        docs = r.json().get("docs", [])
        keys = {d.get("key") for d in docs}
        assert "event-pivot-gap-risk" in keys

    def test_event_gap_risk_markdown_is_served(self, api_client):
        r = api_client.get("/api/playbook/markdown?doc=event-pivot-gap-risk")
        assert r.status_code == 200
        assert "Event Pivot Gap Risk Playbook" in r.text
        assert "Why Stops Fail During Gaps" in r.text


class TestTrailingWinnersBlog:
    def test_trailing_winners_in_meta(self, api_client):
        r = api_client.get("/api/playbook/meta")
        assert r.status_code == 200
        keys = {d.get("key") for d in r.json().get("docs", [])}
        assert "trailing-winners-action-plan" in keys

    def test_trailing_winners_markdown_served(self, api_client):
        r = api_client.get("/api/playbook/markdown?doc=trailing-winners-action-plan")
        assert r.status_code == 200
        assert "Trailing Winners" in r.text
        assert "Five-Stage Trailing System" in r.text or "five-stage" in r.text.lower()

    def test_trailing_winners_download_renders_html(self, api_client):
        r = api_client.get("/api/playbook/download?doc=trailing-winners-action-plan")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "Trailing Winners" in r.text
        assert "<table>" in r.text  # Stage reference table must render


class TestTimeframeAnalysisBlog:
    def test_timeframe_analysis_in_meta(self, api_client):
        r = api_client.get("/api/playbook/meta")
        assert r.status_code == 200
        keys = {d.get("key") for d in r.json().get("docs", [])}
        assert "timeframe-analysis-top-down" in keys

    def test_timeframe_analysis_markdown_served(self, api_client):
        r = api_client.get("/api/playbook/markdown?doc=timeframe-analysis-top-down")
        assert r.status_code == 200
        assert "Top-Down Timeframe Analysis" in r.text
        assert "monthly" in r.text.lower()
        assert "weekly" in r.text.lower()

    def test_timeframe_analysis_download_renders_html(self, api_client):
        r = api_client.get("/api/playbook/download?doc=timeframe-analysis-top-down")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "Top-Down Timeframe Analysis" in r.text
        assert "<table>" in r.text  # Cheat sheet tables must render


