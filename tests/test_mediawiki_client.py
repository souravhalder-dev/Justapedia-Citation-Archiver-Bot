"""Unit tests for MediaWiki client and conflict handling."""

from unittest.mock import MagicMock, patch
from bot.mediawiki_client import MediaWikiClient


def test_get_page_success():
    client = MediaWikiClient()
    mock_payload = {
        "query": {
            "pages": {
                "123": {
                    "revisions": [
                        {
                            "revid": 456,
                            "timestamp": "2026-01-01T00:00:00Z",
                            "slots": {"main": {"*": "== Content =="}},
                        }
                    ]
                }
            }
        }
    }

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        wikitext, ts, revid = client.get_page("Example Article")
        assert wikitext == "== Content =="
        assert ts == "2026-01-01T00:00:00Z"
        assert revid == 456


def test_edit_conflict_detection():
    client = MediaWikiClient()
    client._csrf_token = "test_token+\\"

    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "error": {
                "code": "editconflict",
                "info": "An edit conflict occurred",
            }
        }
        mock_post.return_value = mock_resp

        success, msg = client.save_page(
            title="Conflict Page",
            new_wikitext="New text",
            basetimestamp="2026-01-01T00:00:00Z",
        )
        assert not success
        assert "Edit conflict" in msg


def test_category_members_pagination():
    client = MediaWikiClient()

    with patch.object(client.session, "get") as mock_get:
        page1 = {
            "query": {"categorymembers": [{"title": "Art 1"}, {"title": "Art 2"}]},
            "continue": {"cmcontinue": "cont_token"},
        }
        page2 = {
            "query": {"categorymembers": [{"title": "Art 3"}]},
        }

        resp1 = MagicMock()
        resp1.json.return_value = page1
        resp2 = MagicMock()
        resp2.json.return_value = page2

        mock_get.side_effect = [resp1, resp2]
        members = client.get_category_members("Test Category", limit=10)
        assert len(members) == 3
        assert members == ["Art 1", "Art 2", "Art 3"]


def test_login_with_cookie_success():
    client = MediaWikiClient()
    mock_payload = {
        "query": {
            "userinfo": {"id": 42, "name": "Sourav"},
            "tokens": {"csrftoken": "test_csrf_token+\\"},
        }
    }

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"batchcomplete":""}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        success, msg, cookies, user_id, uname = client.login_with_cookie(
            "justapedia_session=abc12345; justapedia_UserID=42"
        )
        assert success is True
        assert user_id == 42
        assert uname == "Sourav"
        assert "Sourav" in msg
        assert client.is_logged_in is True
        assert client.username == "Sourav"


def test_safe_json_catches_cloudflare_html():
    client = MediaWikiClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 412
    mock_resp.text = "<!DOCTYPE html><html><head><title>412 Request Blocked</title></head><body>hcaptcha</body></html>"
    mock_resp.headers = {"content-type": "text/html"}

    # Should raise RuntimeError with friendly guidance, NEVER JSONDecodeError
    import pytest
    with pytest.raises(RuntimeError) as exc_info:
        client._safe_json(mock_resp)

    assert "Cloudflare / Bot Protection" in str(exc_info.value)
    assert "OAuth" in str(exc_info.value)


def test_oauth_initiate_flow():
    with patch("requests_oauthlib.OAuth1Session.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"key": "tok_123", "secret": "sec_456"}
        mock_get.return_value = mock_resp

        res = MediaWikiClient.initiate_oauth()
        assert res["success"] is True
        assert res["oauth_token"] == "tok_123"
        assert res["oauth_token_secret"] == "sec_456"
        assert "Special:OAuth/authorize" in res["authorize_url"]
