"""Unit tests for FastAPI endpoints with authentication and version tracking."""

import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.app import app, db
from bot.archive_client import ArchiveSnapshot
from bot.url_checker import URLCheckResult, URLStatus

client = TestClient(app)


def test_api_status_includes_developer_info():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "developer" in data
    assert data["developer"]["name"] == "Sourav Halder"
    assert data["developer"]["email"] == "skhsouravhalder@gmail.com"


def test_auth_login_and_me():
    test_token = str(uuid.uuid4())
    db.create_session(token=test_token, username="TestEditor", user_id=42, cookies={"session": "123"})

    # Check /api/auth/me with valid token
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {test_token}"})
    assert res.status_code == 200
    assert res.json()["username"] == "TestEditor"
    assert res.json()["user_id"] == 42

    # Check unauthenticated access rejected with 401
    unauth_res = client.get("/api/auth/me")
    assert unauth_res.status_code == 401


def test_oauth_info_endpoint():
    res = client.get("/api/auth/oauth-info")
    assert res.status_code == 200
    data = res.json()
    assert "9b12e5b4377613f6b46d14f8a6c77798" in data["consumer_token"]


def test_oauth_initiate_and_callback():
    with patch("bot.mediawiki_client.MediaWikiClient.initiate_oauth") as mock_init:
        mock_init.return_value = {
            "oauth_token": "test_req_token_123",
            "oauth_token_secret": "test_req_secret_456",
            "authorize_url": "https://justapedia.org/Special:OAuth/authorize?oauth_token=test_req_token_123",
        }
        res = client.post("/api/auth/oauth/initiate")
        assert res.status_code == 200
        assert res.json()["oauth_token"] == "test_req_token_123"

    with patch("bot.mediawiki_client.MediaWikiClient.complete_oauth") as mock_complete:
        mock_complete.return_value = (
            True,
            "Welcome, Sourav!",
            {"auth_type": "oauth", "oauth_access_token": "acc_tok", "oauth_access_secret": "acc_sec"},
            99,
            "Sourav",
        )
        res_cb = client.post(
            "/api/auth/oauth/callback",
            json={"oauth_token": "test_req_token_123", "oauth_verifier": "987654"},
        )
        assert res_cb.status_code == 200
        data = res_cb.json()
        assert data["success"] is True
        assert data["username"] == "Sourav"
        assert data["user_id"] == 99
        assert "token" in data


def test_api_login_credentials():
    # 1. Test authenticating with seeded credentials (Sourav / 8636521212@)
    res = client.post(
        "/api/auth/login",
        json={"username": "Sourav", "password": "8636521212@"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["username"] == "Sourav"
    assert "token" in data

    # 2. Test wrong password fails with 401
    bad_res = client.post(
        "/api/auth/login",
        json={"username": "Sourav", "password": "incorrect_password"},
    )
    assert bad_res.status_code == 401

    # 3. Test any new user can log in with their credentials
    new_res = client.post(
        "/api/auth/login",
        json={"username": "AliceEditor", "password": "AliceSecret123!"},
    )
    assert new_res.status_code == 200
    assert new_res.json()["username"] == "AliceEditor"


def test_article_versions_lifecycle():
    test_token = str(uuid.uuid4())
    db.create_session(token=test_token, username="Historian", user_id=10)

    # Save a test version
    ver_id = db.save_article_version(
        article_title="Quantum Physics",
        username="Historian",
        mode="manual_apply",
        previous_wikitext="Old wikitext",
        updated_wikitext="New wikitext",
        diff="--- diff ---",
        citations_updated=3,
        mediawiki_revid=101,
        summary="Added 3 archive citations",
    )
    assert ver_id > 0

    # Query via API
    res = client.get("/api/versions?article=Quantum Physics", headers={"Authorization": f"Bearer {test_token}"})
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) >= 1
    assert versions[0]["article_title"] == "Quantum Physics"
    assert versions[0]["username"] == "Historian"
    assert versions[0]["citations_updated"] == 3

    # Query single version
    res_single = client.get(f"/api/versions/{ver_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert res_single.status_code == 200
    assert res_single.json()["version_num"] >= 1


def test_auto_mode_controls():
    test_token = str(uuid.uuid4())
    db.create_session(token=test_token, username="AutoBotOperator", user_id=99)

    # Get status initially
    res = client.get("/api/auto/status")
    assert res.status_code == 200
    assert res.json()["state"] in ("stopped", "running", "paused")


def test_api_check_url_endpoint():
    test_token = str(uuid.uuid4())
    db.create_session(token=test_token, username="Inspector", user_id=77)

    with patch("api.app.url_checker.check_url") as mock_check, \
         patch("api.app.archive_client.find_best_snapshot") as mock_snap:
        mock_check.return_value = URLCheckResult(
            url="https://example.com",
            status=URLStatus.WORKING,
            http_code=200,
        )
        mock_snap.return_value = ArchiveSnapshot(
            original_url="https://example.com",
            archive_url="https://web.archive.org/web/20200101120000/https://example.com",
            timestamp="20200101120000",
            status_code=200,
        )

        response = client.post(
            "/api/check-url",
            json={"url": "https://example.com", "target_date": "2020-01-01"},
            headers={"Authorization": f"Bearer {test_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com"
        assert data["health"]["status"] == "working"
        assert data["snapshot"]["archive_url"] == "https://web.archive.org/web/20200101120000/https://example.com"
