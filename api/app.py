"""FastAPI web server providing authenticated REST endpoints for Justapedia Archiver Bot."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bot.archive_client import ArchiveClient
from bot.article_scanner import ArticleScanner
from bot.auto_mode import auto_controller
from bot.config import config
from bot.database import Database
from bot.logging_config import logger
from bot.mediawiki_client import MediaWikiClient
from bot.snapshot_selector import SnapshotSelector
from bot.url_checker import URLChecker, URLStatus

app = FastAPI(
    title="Justapedia Wayback Archiver Bot API",
    version="2.0.0",
    description="MediaWiki Citation Archiving & Broken Link Repair System",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error": "Internal Server Error"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(config.db_path)
default_wiki_client = MediaWikiClient()
archive_client = ArchiveClient(db=db)
url_checker = URLChecker(db=db)


# ------------------ Models ------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LinkCookieRequest(BaseModel):
    cookie: str


class LinkOAuthRequest(BaseModel):
    oauth_token: str
    oauth_verifier: str


class OAuthCallbackRequest(BaseModel):
    oauth_token: str
    oauth_verifier: str


class ScanRequest(BaseModel):
    target_type: str  # "article", "category", "titles"
    target: str
    mode: str = "dry_run"  # "dry_run" or "live_edit"
    max_edits: Optional[int] = None
    limit: int = 20


class AutoModeStartRequest(BaseModel):
    category: str = "Living people"
    dry_run: bool = False


class SingleUrlCheckRequest(BaseModel):
    url: str
    target_date: Optional[str] = None
    bypass_cache: bool = False


class ApplyEditRequest(BaseModel):
    title: str
    wikitext: str
    summary: Optional[str] = None
    basetimestamp: Optional[str] = None


# ------------------ Auth Dependency Helper ------------------


def get_current_user_session(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Validate bearer token or custom session header."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
    elif x_session_token:
        token = x_session_token.strip()

    if not token:
        raise HTTPException(
            status_code=401, detail="Authentication required. Please log in with your Justapedia account."
        )

    session = db.get_session(token)
    if not session:
        raise HTTPException(
            status_code=401, detail="Session expired or invalid. Please log in again."
        )

    return session


def get_user_wiki_client(session: Dict[str, Any]) -> MediaWikiClient:
    """Return a MediaWikiClient bound to the authenticated user's credentials or OAuth token."""
    cookies = session.get("cookies", {})
    return MediaWikiClient(
        username=session["username"],
        session_cookies=cookies,
        oauth_access_token=cookies.get("oauth_access_token"),
        oauth_access_secret=cookies.get("oauth_access_secret"),
    )


# ------------------ Auth Endpoints ------------------


@app.post("/api/auth/oauth/initiate")
def oauth_initiate() -> Dict[str, Any]:
    """Start Justapedia OAuth 1.0a flow and return authorization URL."""
    try:
        init_data = MediaWikiClient.initiate_oauth()
        db.save_pending_oauth(init_data["oauth_token"], init_data["oauth_token_secret"])
        return {
            "success": True,
            "oauth_token": init_data["oauth_token"],
            "authorize_url": init_data["authorize_url"],
        }
    except Exception as e:
        logger.error(f"OAuth initiate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/oauth/callback")
def oauth_callback(req: OAuthCallbackRequest) -> Dict[str, Any]:
    """Exchange OAuth request token + verification PIN for access token and establish session."""
    secret = db.get_pending_oauth_secret(req.oauth_token)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="OAuth session expired or invalid request token. Please click '1. Open Justapedia to Authorize' again.",
        )

    success, msg, session_payload, user_id, username = MediaWikiClient.complete_oauth(
        req_token=req.oauth_token,
        req_secret=secret,
        verifier=req.oauth_verifier,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    token = str(uuid.uuid4())
    db.create_session(
        token=token,
        username=username or "Justapedia Editor",
        user_id=user_id,
        cookies=session_payload,
        ttl_hours=168,
    )

    return {
        "success": True,
        "token": token,
        "username": username or "Justapedia Editor",
        "user_id": user_id,
        "message": msg,
    }


@app.post("/api/auth/login")
def login(req: LoginRequest) -> Dict[str, Any]:
    """
    Authenticate any user using their username and password.
    Validates credentials with secure PBKDF2-HMAC-SHA256 password hashing.
    Establishes an authenticated session that attributes all article edits and Auto Mode actions to the user.
    """
    uname = (req.username or "").strip()
    passwd = (req.password or "").strip()

    if not uname or not passwd:
        raise HTTPException(
            status_code=400,
            detail="Username and password are required.",
        )

    user = db.authenticate_user(uname, passwd)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. Please verify your password.",
        )

    # Establish authenticated user session
    token = str(uuid.uuid4())
    session_payload = {
        "auth_type": "credentials",
        "username": user["username"],
        "user_id": user.get("justapedia_user_id", 1),
    }

    # Automatically restore linked Justapedia OAuth/cookie credentials if previously saved
    saved_creds = user.get("justapedia_credentials") or {}
    if saved_creds:
        session_payload.update(saved_creds)

    db.create_session(
        token=token,
        username=user["username"],
        user_id=user.get("justapedia_user_id", 1),
        cookies=session_payload,
        ttl_hours=168,
    )

    logger.info(f"User '{user['username']}' successfully logged in.")
    return {
        "success": True,
        "token": token,
        "username": user["username"],
        "user_id": user.get("justapedia_user_id", 1),
        "message": f"Welcome back, {user['username']}! Logged in successfully.",
    }


@app.get("/api/auth/wiki-status")
def get_wiki_status(request: Request) -> Dict[str, Any]:
    """Check if current session has active, verified Justapedia credentials."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    user_client = get_user_wiki_client(session)
    cookies = session.get("cookies", {})
    auth_type = cookies.get("auth_type", "credentials")

    try:
        res = user_client._http_client().get(
            user_client.api_url,
            params={
                "action": "query",
                "meta": "userinfo",
                "uiprop": "rights|groups",
                "format": "json",
            },
            timeout=5,
        )
        data = user_client._safe_json(res)
        uinfo = data.get("query", {}).get("userinfo", {})
        uid = uinfo.get("id", 0)
        uname = uinfo.get("name")
        is_anon = uinfo.get("anon") is not None or uid == 0
        groups = uinfo.get("groups", [])

        is_linked = not is_anon and bool(uname)
        return {
            "is_linked": is_linked,
            "username": uname if is_linked else None,
            "user_id": uid if is_linked else None,
            "groups": groups,
            "auth_type": auth_type if is_linked else "none",
        }
    except Exception as e:
        return {
            "is_linked": False,
            "error": str(e),
            "auth_type": auth_type,
        }


@app.post("/api/auth/link-cookie")
def link_cookie(req: LinkCookieRequest, request: Request) -> Dict[str, Any]:
    """Link Justapedia browser session cookie to current user account."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    test_client = MediaWikiClient()
    success, msg, cookies, user_id, username = test_client.login_with_cookie(req.cookie)
    if not success or not cookies:
        raise HTTPException(status_code=400, detail=msg)

    payload = {
        "auth_type": "cookie",
        "username": username or session["username"],
        "user_id": user_id,
        **cookies,
    }
    db.update_session_cookies(session["token"], payload)
    db.save_user_justapedia_credentials(session["username"], payload)
    logger.info(f"User '{session['username']}' successfully linked Justapedia account as {username} (ID: {user_id}).")
    return {
        "success": True,
        "message": f"Justapedia account linked as {username} (ID: {user_id})!",
        "username": username,
        "user_id": user_id,
    }


@app.post("/api/auth/link-oauth")
def link_oauth(req: LinkOAuthRequest, request: Request) -> Dict[str, Any]:
    """Complete OAuth 1.0a verification and link token to current user account."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    secret = db.get_pending_oauth_secret(req.oauth_token)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="OAuth session expired or invalid request token. Please restart authorization.",
        )

    success, msg, payload, user_id, username = MediaWikiClient.complete_oauth(
        req_token=req.oauth_token,
        req_secret=secret,
        verifier=req.oauth_verifier,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    merged = {
        "auth_type": "oauth",
        "username": username or session["username"],
        "user_id": user_id,
        **payload,
    }
    db.update_session_cookies(session["token"], merged)
    db.save_user_justapedia_credentials(session["username"], merged)
    logger.info(f"User '{session['username']}' successfully linked Justapedia account via OAuth as {username}.")
    return {
        "success": True,
        "message": f"Justapedia OAuth successfully connected as {username}!",
        "username": username,
        "user_id": user_id,
    }


@app.get("/api/auth/me")
def get_current_user(request: Request) -> Dict[str, Any]:
    """Return current authenticated user profile."""
    auth_header = request.headers.get("Authorization")
    token_header = request.headers.get("x-session-token")
    session = get_current_user_session(auth_header, token_header)
    return {
        "authenticated": True,
        "username": session["username"],
        "user_id": session["user_id"],
        "expires_at": session["expires_at"],
    }


@app.post("/api/auth/logout")
def logout(request: Request) -> Dict[str, Any]:
    """Invalidate user session."""
    auth_header = request.headers.get("Authorization")
    token_header = request.headers.get("x-session-token")
    try:
        session = get_current_user_session(auth_header, token_header)
        db.delete_session(session["token"])
    except Exception:
        pass
    return {"success": True, "message": "Logged out successfully"}


@app.get("/api/auth/oauth-info")
def get_oauth_consumer_info() -> Dict[str, Any]:
    """Return configured OAuth Consumer details for Justapedia."""
    return {
        "consumer_token": config.oauth_consumer_token,
        "secret_token": config.oauth_secret_token[:6] + "..." + config.oauth_secret_token[-6:],
        "status": "Awaiting administrator approval on Justapedia",
        "wiki_base_url": config.wiki_base_url,
    }


# ------------------ Status & Info ------------------


@app.get("/api/status")
def get_system_status() -> Dict[str, Any]:
    """System health check, developer info, and database metrics."""
    db_stats = db.get_stats()
    wiki_connected = False
    try:
        res = default_wiki_client.session.get(
            default_wiki_client.api_url,
            params={"action": "query", "meta": "siteinfo", "siprop": "general", "format": "json"},
            timeout=5,
        )
        wiki_connected = res.status_code == 200
    except Exception:
        wiki_connected = False

    return {
        "status": "online",
        "wiki_connected": wiki_connected,
        "wiki_api_url": config.wiki_api_url,
        "developer": {
            "name": config.developer_name,
            "email": config.developer_email,
        },
        "db_stats": db_stats,
    }


# ------------------ Auto Mode Endpoints ------------------


@app.post("/api/auto/start")
def start_auto_mode(req: AutoModeStartRequest, request: Request) -> Dict[str, Any]:
    """Start continuous Auto Mode attributed to the logged-in user."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    user_client = get_user_wiki_client(session)

    cookies = session.get("cookies", {})
    has_wiki_auth = bool(
        cookies.get("oauth_access_token")
        or any(k.startswith("justapedia_") for k in cookies.keys())
    )
    if not req.dry_run and not has_wiki_auth:
        raise HTTPException(
            status_code=400,
            detail="Live Edit mode requires an authenticated Justapedia session (OAuth or Session Cookie) to bypass firewall restrictions and attribute edits to your MediaWiki account. Please connect your Justapedia account using the 'Connect Justapedia' button in the header, or enable Dry Run mode to preview edits without live saving.",
        )

    started = auto_controller.start(
        username=session["username"],
        user_client=user_client,
        category=req.category,
        dry_run=req.dry_run,
    )
    if not started:
        raise HTTPException(status_code=400, detail="Auto Mode is already running or paused.")

    return {"success": True, "status": auto_controller.get_status()}


@app.post("/api/auto/pause")
def pause_auto_mode(request: Request) -> Dict[str, Any]:
    """Pause continuous Auto Mode."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    paused = auto_controller.pause()
    return {"success": paused, "status": auto_controller.get_status()}


@app.post("/api/auto/resume")
def resume_auto_mode(request: Request) -> Dict[str, Any]:
    """Resume paused Auto Mode."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    resumed = auto_controller.resume()
    return {"success": resumed, "status": auto_controller.get_status()}


@app.post("/api/auto/stop")
def stop_auto_mode(request: Request) -> Dict[str, Any]:
    """Stop continuous Auto Mode."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    stopped = auto_controller.stop()
    return {"success": stopped, "status": auto_controller.get_status()}


@app.get("/api/auto/status")
def get_auto_mode_status() -> Dict[str, Any]:
    """Get real-time Auto Mode progress, speed, and activity."""
    return auto_controller.get_status()


# ------------------ Article Versions Endpoints ------------------


@app.get("/api/versions")
def get_versions(
    article: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    request: Request = None,
) -> List[Dict[str, Any]]:
    """Fetch saved article update versions."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    return db.get_article_versions(article_title=article, limit=limit)


@app.get("/api/versions/{version_id}")
def get_version_detail(version_id: int, request: Request = None) -> Dict[str, Any]:
    """Fetch full detail of a specific saved article revision."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    ver = db.get_article_version(version_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Version record not found.")
    return ver


# ------------------ Scanner & Edit Endpoints ------------------


@app.post("/api/scan")
def start_scan(req: ScanRequest, request: Request) -> Dict[str, Any]:
    """Run an article scan (synchronous dry-run or live edit) attributed to logged-in user."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    user_client = get_user_wiki_client(session)

    titles: List[str] = []
    if req.target_type == "article":
        titles = [req.target.strip()]
    elif req.target_type == "category":
        titles = user_client.get_category_members(req.target, limit=req.limit)
    elif req.target_type == "titles":
        titles = [
            t.strip()
            for t in req.target.replace(",", "\n").splitlines()
            if t.strip() and not t.strip().startswith("#")
        ][: req.limit]
    else:
        raise HTTPException(status_code=400, detail="Invalid target_type.")

    if not titles:
        return {"error": "No articles found to scan", "report": None}

    is_dry_run = req.mode != "live_edit"
    scanner = ArticleScanner(
        wiki_client=user_client,
        archive_client=archive_client,
        url_checker=url_checker,
        db=db,
        dry_run=is_dry_run,
        max_edits=req.max_edits,
        acting_user=session["username"],
    )

    report = scanner.run_batch(
        titles=titles,
        target_type=req.target_type,
        target_name=req.target,
    )

    return {
        "job_id": report.job_id,
        "report": report.to_dict(),
        "diffs": report.article_diffs,
    }


@app.post("/api/apply")
def apply_page_edit(req: ApplyEditRequest, request: Request) -> Dict[str, Any]:
    """Save an approved article edit directly to Justapedia under the user's account."""
    session = get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    user_client = get_user_wiki_client(session)

    success, msg = user_client.save_page(
        title=req.title,
        new_wikitext=req.wikitext,
        summary=req.summary,
        basetimestamp=req.basetimestamp,
        acting_user=session["username"],
    )
    revid = getattr(user_client, "last_revid", None)

    if success:
        orig_text, _, _ = user_client.get_page(req.title)
        db.save_article_version(
            article_title=req.title,
            username=session["username"],
            mode="manual_apply",
            previous_wikitext=orig_text or "",
            updated_wikitext=req.wikitext,
            diff="",
            citations_updated=1,
            mediawiki_revid=revid,
            summary=req.summary or f"Manual update by {session['username']}",
        )

    return {"success": success, "message": msg, "revid": revid}


@app.post("/api/check-url")
def check_single_url(req: SingleUrlCheckRequest, request: Request) -> Dict[str, Any]:
    """Inspect URL health and query Internet Archive Availability and CDX directly."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )

    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    health_res = url_checker.check_url(clean_url, bypass_cache=req.bypass_cache)
    target_ts = (
        SnapshotSelector.parse_citation_date_to_timestamp(req.target_date)
        if req.target_date
        else None
    )
    snapshot = archive_client.find_best_snapshot(
        clean_url, target_timestamp=target_ts, bypass_cache=req.bypass_cache
    )

    formatted_date = None
    if snapshot and snapshot.timestamp:
        formatted_date = SnapshotSelector.format_timestamp_to_date(
            snapshot.timestamp, style="iso"
        )

    cdx_captures = []
    try:
        cdx_captures = [
            {
                "timestamp": c.timestamp,
                "archive_url": c.archive_url,
                "status_code": c.status_code,
                "mime_type": c.mime_type,
                "date": SnapshotSelector.format_timestamp_to_date(c.timestamp, "iso"),
            }
            for c in archive_client.query_cdx(clean_url, target_timestamp=target_ts, limit=5)
        ]
    except Exception:
        pass

    return {
        "url": clean_url,
        "health": {
            "status": health_res.status.value,
            "http_code": health_res.http_code,
            "final_url": health_res.final_url,
            "is_cached": health_res.is_cached,
            "error_message": health_res.error_message,
        },
        "snapshot": (
            {
                "archive_url": snapshot.archive_url,
                "timestamp": snapshot.timestamp,
                "formatted_date": formatted_date,
                "status_code": snapshot.status_code,
                "source_api": snapshot.source_api,
                "is_cached": snapshot.is_cached,
            }
            if snapshot
            else None
        ),
        "recent_cdx_captures": cdx_captures,
    }


@app.get("/api/jobs")
def get_jobs(
    limit: int = Query(default=20, le=100), request: Request = None
) -> List[Dict[str, Any]]:
    """Get list of past scanning jobs."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    return db.get_recent_jobs(limit=limit)


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str, request: Request = None) -> Dict[str, Any]:
    """Get detailed records and diffs for a specific job."""
    get_current_user_session(
        request.headers.get("Authorization"), request.headers.get("x-session-token")
    )
    articles = db.get_job_articles(job_id)
    return {"job_id": job_id, "articles": articles}


# Mount production React frontend if built
dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if dist_dir.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")
