"""Unit tests for URL health checker."""

from unittest.mock import MagicMock, patch
import requests
from bot.url_checker import URLChecker, URLStatus


def test_working_url(temp_db):
    checker = URLChecker(db=temp_db)
    with patch.object(checker.session, "head") as mock_head:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com"
        mock_head.return_value = mock_resp

        res = checker.check_url("https://example.com")
        assert res.status == URLStatus.WORKING
        assert res.http_code == 200


def test_dead_url_404_and_410(temp_db):
    checker = URLChecker(db=temp_db)
    for code in (404, 410):
        with patch.object(checker.session, "head") as mock_head:
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_resp.url = f"https://example.com/{code}"
            mock_head.return_value = mock_resp

            res = checker.check_url(f"https://example.com/{code}")
            assert res.status == URLStatus.LIKELY_DEAD
            assert res.http_code == code


def test_inconclusive_responses(temp_db):
    checker = URLChecker(db=temp_db)
    for code in (403, 429, 500, 503):
        with patch.object(checker.session, "head") as mock_head:
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_resp.url = "https://example.com"
            mock_resp.headers = {}
            mock_head.return_value = mock_resp

            res = checker.check_url(f"https://example.com/{code}")
            assert res.status == URLStatus.INCONCLUSIVE


def test_request_timeout(temp_db):
    checker = URLChecker(db=temp_db)
    with patch.object(checker.session, "head", side_effect=requests.exceptions.Timeout("Read timeout")):
        res = checker.check_url("https://timeout-site.org")
        assert res.status == URLStatus.INCONCLUSIVE
        assert "timed out" in res.error_message


def test_dns_resolution_failure(temp_db):
    checker = URLChecker(db=temp_db)
    with patch.object(
        checker.session,
        "head",
        side_effect=requests.exceptions.ConnectionError("Failed to resolve 'nonexistent.xyz'"),
    ):
        res = checker.check_url("https://nonexistent.xyz")
        assert res.status == URLStatus.LIKELY_DEAD


def test_url_cache_hit(temp_db):
    checker = URLChecker(db=temp_db)
    url = "https://cached-site.org"
    temp_db.set_url_cache(url=url, status=URLStatus.WORKING.value, http_code=200)

    # Calling check_url should hit the cache without making HTTP request
    with patch.object(checker.session, "head") as mock_head:
        res = checker.check_url(url)
        assert res.status == URLStatus.WORKING
        assert res.is_cached
        mock_head.assert_not_called()
