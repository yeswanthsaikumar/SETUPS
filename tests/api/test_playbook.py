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

