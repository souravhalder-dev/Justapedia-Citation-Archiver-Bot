"""Unit tests for Internet Archive client."""

from unittest.mock import MagicMock, patch
import requests
from bot.archive_client import ArchiveClient, ArchiveSnapshot


def test_availability_api_success(temp_db):
    client = ArchiveClient(db=temp_db)
    mock_payload = {
        "url": "https://example.com",
        "archived_snapshots": {
            "closest": {
                "status": "200",
                "available": True,
                "url": "http://web.archive.org/web/20200501120000/https://example.com",
                "timestamp": "20200501120000",
            }
        },
    }

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        snapshot = client.query_availability("https://example.com")
        assert snapshot is not None
        assert snapshot.timestamp == "20200501120000"
        # Enforced HTTPS
        assert snapshot.archive_url.startswith("https://web.archive.org")
        assert snapshot.status_code == 200
        assert snapshot.source_api == "availability"


def test_availability_no_snapshots(temp_db):
    client = ArchiveClient(db=temp_db)
    mock_payload = {"url": "https://noarchive.org", "archived_snapshots": {}}

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        snapshot = client.query_availability("https://noarchive.org")
        assert snapshot is None


def test_cdx_server_api_success(temp_db):
    client = ArchiveClient(db=temp_db)
    mock_cdx_data = [
        ["timestamp", "original", "statuscode", "mimetype", "digest"],
        ["20180915103000", "https://example.org/energy", "200", "text/html", "DIGEST123"],
    ]

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_cdx_data
        mock_get.return_value = mock_resp

        results = client.query_cdx("https://example.org/energy")
        assert len(results) == 1
        assert results[0].timestamp == "20180915103000"
        assert results[0].archive_url == "https://web.archive.org/web/20180915103000/https://example.org/energy"
        assert results[0].source_api == "cdx"


def test_api_retry_on_429(temp_db):
    client = ArchiveClient(db=temp_db, max_retries=2, backoff_factor=0.01)

    with patch.object(client.session, "get") as mock_get:
        mock_429 = MagicMock()
        mock_429.status_code = 429

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "status": "200",
                    "url": "https://web.archive.org/web/20210101000000/https://example.com",
                    "timestamp": "20210101000000",
                }
            }
        }

        mock_get.side_effect = [mock_429, mock_200]
        snapshot = client.query_availability("https://example.com")
        assert snapshot is not None
        assert mock_get.call_count == 2


def test_malformed_json_response(temp_db):
    client = ArchiveClient(db=temp_db)
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_resp

        snapshot = client.query_availability("https://example.com")
        assert snapshot is None
