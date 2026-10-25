"""MediaWiki client for Justapedia with Pywikibot support, user sessions, batch fetching, conflict detection, and rate limiting."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests_oauthlib import OAuth1Session
import jwt

from bot.config import config
from bot.logging_config import logger


def parse_cookie_input(cookie_input: str) -> Dict[str, str]:
    """
    Parse a cookie string or token into a dictionary suitable for requests.Session.cookies.
    Supports:
    - Full cookie strings: 'justapedia_session=...; justapedia_UserID=...'
    - Single session token: 'a8b9c0d1e2f3...' (auto-mapped to session cookie names)
    - Key=Value pairs
    """
    cookies: Dict[str, str] = {}
    cleaned = (cookie_input or "").strip()
    if not cleaned:
        return cookies

    # If raw single token without equals sign (e.g. 16+ hex/base64 string)
    if "=" not in cleaned and len(cleaned) >= 12:
        cookies["justapedia_session"] = cleaned
        cookies["justapedia_mediawiki_session"] = cleaned
        return cookies

    for item in cleaned.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                cookies[k] = v
    return cookies


class MediaWikiClient:
    """Client for querying and editing MediaWiki sites, specifically Justapedia."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_cookies: Optional[Dict[str, Any]] = None,
        oauth_access_token: Optional[str] = None,
        oauth_access_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        rate_limit_delay: Optional[float] = None,
    ) -> None:
        self.api_url = api_url or config.wiki_api_url
        self.username = username or config.bot_username
        self.password = password or config.bot_password
        self.user_agent = user_agent or config.user_agent
        self.rate_limit_delay = (
            rate_limit_delay if rate_limit_delay is not None else config.edit_rate_limit
        )

        self.session = requests.Session()
        # Connection pooling for high throughput
        adapter = HTTPAdapter(
            pool_connections=30,
            pool_maxsize=50,
            max_retries=Retry(total=2, backoff_factor=0.3, status_forcelist=[502, 503, 504]),
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
            }
        )

        # Check OAuth credentials
        cookies = session_cookies or {}
        access_token = oauth_access_token or cookies.get("oauth_access_token")
        access_secret = oauth_access_secret or cookies.get("oauth_access_secret")

        if access_token and access_secret:
            self.oauth_session = OAuth1Session(
                client_key=config.oauth_consumer_token,
                client_secret=config.oauth_secret_token,
                resource_owner_key=access_token,
                resource_owner_secret=access_secret,
            )
            self.oauth_session.headers.update(
                {
                    "User-Agent": self.user_agent,
                    "Accept": "application/json, text/plain, */*",
                }
            )
            self.is_oauth = True
            self.is_logged_in = True
        else:
            self.oauth_session = None
            self.is_oauth = False
            # Inject session cookies if provided (from authenticated user session)
            clean_cookies = {
                str(k): str(v)
                for k, v in cookies.items()
                if not str(k).startswith("oauth_")
                and str(k) not in ("auth_type", "username", "user_id", "created_at", "expires_at")
                and isinstance(v, (str, int, float))
            }
            if clean_cookies:
                self.session.cookies.update(clean_cookies)
            self.is_logged_in = bool(self.username or clean_cookies)

        self._csrf_token: Optional[str] = None
        self._last_edit_time: float = 0.0

    def _http_client(self):
        """Return OAuth1Session or requests.Session depending on authentication type."""
        if self.is_oauth and self.oauth_session:
            return self.oauth_session
        return self.session

    def _safe_json(self, response: requests.Response) -> Dict[str, Any]:
        """
        Safely parse JSON response from MediaWiki, handling Cloudflare blocks and HTML errors cleanly.
        Prevents 'Expecting value: line 1 column 1 (char 0)' JSONDecodeError.
        """
        text = response.text or ""
        status_code = response.status_code

        # Check for Cloudflare / Anti-bot / rate limit blocks
        if (
            status_code in (412, 429, 403, 503)
            or "Request Blocked" in text
            or "hcaptcha" in text.lower()
            or "challenge-platform" in text.lower()
        ):
            raise RuntimeError(
                f"Cloudflare / Bot Protection blocked automated request on Justapedia (HTTP {status_code}). "
                "Automated password logins may be challenged by Cloudflare. "
                "Please use the 'Justapedia OAuth' option to authenticate seamlessly via OAuth."
            )

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" not in content_type and "text/javascript" not in content_type:
            if "<html" in text.lower() or "<!doctype" in text.lower():
                import re
                m = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE)
                page_title = m.group(1).strip() if m else f"HTTP {status_code}"
                raise RuntimeError(
                    f"MediaWiki returned HTML instead of JSON ({page_title}). "
                    "If authenticating with password, Cloudflare may be blocking automated POST requests. "
                    "Please use the 'Justapedia OAuth' method instead."
                )

        try:
            return response.json()
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse MediaWiki API response as JSON (status {status_code}): {e}."
            )

    @staticmethod
    def initiate_oauth() -> Dict[str, Any]:
        """
        Step 1 of MediaWiki OAuth 1.0a flow:
        Fetch temporary request token from Special:OAuth/initiate using Consumer Key & Secret.
        Uses GET request to avoid Cloudflare POST bot blocks.
        """
        oauth = OAuth1Session(
            client_key=config.oauth_consumer_token,
            client_secret=config.oauth_secret_token,
            callback_uri="oob",
        )
        oauth.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/plain, */*",
            }
        )
        resp = oauth.get("https://justapedia.org/Special:OAuth/initiate?format=json", timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Justapedia OAuth initiate failed: {resp.text}")

        data = resp.json()
        req_token = data.get("key")
        req_secret = data.get("secret")
        if not req_token or not req_secret:
            raise RuntimeError(f"Invalid initiate response from Justapedia: {data}")

        authorize_url = (
            f"https://justapedia.org/Special:OAuth/authorize"
            f"?oauth_token={req_token}&oauth_consumer_key={config.oauth_consumer_token}"
        )
        return {
            "success": True,
            "oauth_token": req_token,
            "oauth_token_secret": req_secret,
            "authorize_url": authorize_url,
        }

    @staticmethod
    def complete_oauth(
        req_token: str, req_secret: str, verifier: str
    ) -> Tuple[bool, str, Dict[str, Any], Optional[int], Optional[str]]:
        """
        Step 2 of MediaWiki OAuth 1.0a flow:
        Exchange request token + user verification PIN for permanent access token.
        Uses GET request on Special:OAuth/token to bypass Cloudflare bot restrictions.
        Returns: (success: bool, message: str, session_payload: Dict, user_id: Optional[int], username: Optional[str])
        """
        clean_verifier = (verifier or "").strip()
        if not clean_verifier:
            return False, "Please enter the OAuth verification PIN from Justapedia.", {}, None, None

        oauth = OAuth1Session(
            client_key=config.oauth_consumer_token,
            client_secret=config.oauth_secret_token,
            resource_owner_key=req_token,
            resource_owner_secret=req_secret,
            verifier=clean_verifier,
        )
        oauth.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/plain, */*",
            }
        )
        resp = oauth.get("https://justapedia.org/Special:OAuth/token?format=json", timeout=15)
        if resp.status_code != 200:
            return False, f"OAuth token exchange failed (HTTP {resp.status_code}): {resp.text}", {}, None, None

        token_data = resp.json()
        if "error" in token_data:
            err_msg = token_data.get("message", token_data.get("error"))
            return False, f"OAuth authorization rejected: {err_msg}", {}, None, None

        access_token = token_data.get("key")
        access_secret = token_data.get("secret")
        if not access_token or not access_secret:
            return False, f"Unexpected OAuth token response: {token_data}", {}, None, None

        # Step 3: Identify User
        ident_oauth = OAuth1Session(
            client_key=config.oauth_consumer_token,
            client_secret=config.oauth_secret_token,
            resource_owner_key=access_token,
            resource_owner_secret=access_secret,
        )
        ident_oauth.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/plain, */*",
            }
        )

        username = "Justapedia Editor"
        user_id = None

        try:
            ident_resp = ident_oauth.get("https://justapedia.org/Special:OAuth/identify", timeout=15)
            if ident_resp.status_code == 200 and ident_resp.text:
                claims = jwt.decode(ident_resp.text, options={"verify_signature": False})
                username = claims.get("username", username)
                user_id = claims.get("sub")
        except Exception as e:
            logger.warning(f"Could not parse identify JWT: {e}")

        # Also confirm via userinfo
        try:
            uinfo_resp = ident_oauth.get(
                f"{config.wiki_api_url}?action=query&meta=userinfo&format=json", timeout=15
            )
            if uinfo_resp.status_code == 200:
                uinfo = uinfo_resp.json().get("query", {}).get("userinfo", {})
                if uinfo.get("name"):
                    username = uinfo["name"]
                if uinfo.get("id"):
                    user_id = uinfo["id"]
        except Exception as e:
            logger.warning(f"Could not query userinfo via OAuth: {e}")

        session_payload = {
            "auth_type": "oauth",
            "oauth_access_token": access_token,
            "oauth_access_secret": access_secret,
        }
        return True, f"Welcome, {username}! Successfully authenticated via Justapedia OAuth.", session_payload, user_id, username

    def login_with_cookie(
        self, cookie_input: str
    ) -> Tuple[bool, str, Optional[Dict[str, str]], Optional[int], Optional[str]]:
        """
        Authenticate user using active MediaWiki session cookie(s).
        This completely bypasses Cloudflare CAPTCHA/bot challenges because it uses an existing valid browser session.
        Returns: (success: bool, message: str, cookies: Optional[Dict], user_id: Optional[int], username: Optional[str])
        """
        cookies_dict = parse_cookie_input(cookie_input)
        if not cookies_dict:
            return (
                False,
                "Cookie string is empty or invalid. Example: justapedia_session=abc12345...",
                None,
                None,
                None,
            )

        self.session.cookies.update(cookies_dict)
        # Use desktop browser headers for session validation
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://justapedia.org",
                "Referer": "https://justapedia.org/",
            }
        )

        try:
            res = self.session.get(
                self.api_url,
                params={
                    "action": "query",
                    "meta": "tokens|userinfo",
                    "type": "csrf",
                    "uiprop": "rights|groups",
                    "format": "json",
                },
                timeout=config.request_timeout,
            )
            data = self._safe_json(res)

            user_info = data.get("query", {}).get("userinfo", {})
            user_id = user_info.get("id", 0)
            username = user_info.get("name")

            if not username or user_id == 0 or user_info.get("anon") is not None:
                return (
                    False,
                    "The provided session cookie was not recognized as an active logged-in account on Justapedia. "
                    "Please sign in to Justapedia in your browser first, then copy your current cookie.",
                    None,
                    None,
                    None,
                )

            csrf_token = data.get("query", {}).get("tokens", {}).get("csrftoken")
            if csrf_token and csrf_token != "+\\":
                self._csrf_token = csrf_token

            self.username = username
            self.is_logged_in = True
            all_cookies = self.session.cookies.get_dict()
            logger.info(f"User {username} (ID: {user_id}) successfully authenticated via session cookie.")
            return True, f"Welcome back, {username}!", all_cookies, user_id, username

        except Exception as e:
            logger.error(f"Session cookie validation error: {e}")
            return False, str(e), None, None, None

    def login_user(
        self, username: str, password: str
    ) -> Tuple[bool, str, Optional[Dict[str, str]], Optional[int]]:
        """
        Authenticate a user against MediaWiki action=login with username and password / bot password.
        Returns: (success: bool, message: str, cookies: Optional[Dict], user_id: Optional[int])
        """
        if not username or not password:
            return False, "Username and password cannot be empty", None, None

        try:
            # 1. Fetch login token
            token_res = self.session.get(
                self.api_url,
                params={
                    "action": "query",
                    "meta": "tokens",
                    "type": "login",
                    "format": "json",
                },
                timeout=config.request_timeout,
            )
            token_data = self._safe_json(token_res)

            login_token = token_data.get("query", {}).get("tokens", {}).get("logintoken")
            if not login_token:
                return False, "Failed to retrieve login token from MediaWiki API", None, None

            # 2. Perform login
            login_res = self.session.post(
                self.api_url,
                data={
                    "action": "login",
                    "lgname": username,
                    "lgpassword": password,
                    "lgtoken": login_token,
                    "format": "json",
                },
                timeout=config.request_timeout,
            )

            # Check if Cloudflare blocked the POST login request
            if (
                login_res.status_code in (412, 429, 302, 403)
                or "Request Blocked" in login_res.text
                or "Too Many Requests" in login_res.text
            ):
                return (
                    False,
                    "Cloudflare / Bot Protection challenged automated password login on Justapedia. "
                    "Please use the 'Justapedia OAuth' tab above to authenticate seamlessly via OAuth.",
                    None,
                    None,
                )

            login_data = self._safe_json(login_res)
            status = login_data.get("login", {}).get("result")
            if status == "Success":
                self.is_logged_in = True
                self.username = username

                # 3. Fetch userinfo to confirm user ID and identity
                user_info_res = self.session.get(
                    self.api_url,
                    params={
                        "action": "query",
                        "meta": "userinfo",
                        "format": "json",
                    },
                    timeout=config.request_timeout,
                )
                user_info_data = self._safe_json(user_info_res)
                userinfo = user_info_data.get("query", {}).get("userinfo", {})
                user_id = userinfo.get("id")
                actual_name = userinfo.get("name", username)

                # Capture session cookies
                cookies_dict = self.session.cookies.get_dict()
                logger.info(f"User {actual_name} (ID: {user_id}) successfully authenticated.")
                return True, f"Welcome, {actual_name}!", cookies_dict, user_id
            else:
                reason = login_data.get("login", {}).get("reason", "Invalid credentials")
                logger.warning(f"Login failed for {username}: {reason}")
                return False, reason, None, None

        except Exception as e:
            logger.error(f"Login exception for {username}: {e}")
            return False, str(e), None, None

    def login(self) -> bool:
        """Authenticate using default configured bot credentials."""
        if not self.username or not self.password:
            return False
        success, _, _, _ = self.login_user(self.username, self.password)
        return success

    def get_csrf_token(self) -> Optional[str]:
        """Fetch a CSRF token for editing."""
        if self._csrf_token:
            return self._csrf_token

        try:
            res = self._http_client().get(
                self.api_url,
                params={
                    "action": "query",
                    "meta": "tokens",
                    "type": "csrf",
                    "format": "json",
                },
                timeout=config.request_timeout,
            )
            data = self._safe_json(res)

            token = data.get("query", {}).get("tokens", {}).get("csrftoken")
            if token:
                self._csrf_token = token
                return token
            return None
        except Exception as e:
            logger.error(f"Error obtaining CSRF token: {e}")
            return None

    def get_page(
        self, title: str
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Fetch wikitext, basetimestamp, and revid for a single page.
        Returns: (wikitext, basetimestamp, revision_id)
        """
        batch = self.get_pages_batch([title])
        return batch.get(title, (None, None, None))

    def get_pages_batch(
        self, titles: List[str]
    ) -> Dict[str, Tuple[Optional[str], Optional[str], Optional[int]]]:
        """
        Fetch wikitext, basetimestamp, and revid for multiple pages in ONE batch request.
        Allows processing > 20 articles per minute with minimal network round trips.
        """
        results: Dict[str, Tuple[Optional[str], Optional[str], Optional[int]]] = {}
        if not titles:
            return results

        clean_titles = [t.strip() for t in titles if t.strip()]
        chunk_size = 50

        for i in range(0, len(clean_titles), chunk_size):
            chunk = clean_titles[i : i + chunk_size]
            titles_param = "|".join(chunk)

            try:
                res = self._http_client().get(
                    self.api_url,
                    params={
                        "action": "query",
                        "titles": titles_param,
                        "prop": "revisions",
                        "rvprop": "content|timestamp|ids",
                        "rvslots": "main",
                        "format": "json",
                    },
                    timeout=config.request_timeout,
                )
                data = self._safe_json(res)

                pages = data.get("query", {}).get("pages", {})
                for page_key, page_data in pages.items():
                    title = page_data.get("title")
                    if not title and len(chunk) == 1:
                        title = chunk[0]

                    if not title:
                        continue

                    page_id = int(page_data.get("pageid", page_key if str(page_key).isdigit() else 1))
                    if page_id <= 0:
                        results[title] = (None, None, None)
                        continue

                    revisions = page_data.get("revisions", [])
                    if not revisions:
                        results[title] = (None, None, None)
                        continue

                    rev = revisions[0]
                    revid = rev.get("revid")
                    timestamp = rev.get("timestamp")
                    slots = rev.get("slots", {})
                    main_slot = slots.get("main", {})
                    wikitext = main_slot.get("*", "")
                    results[title] = (wikitext, timestamp, revid)

            except Exception as e:
                logger.error(f"Error fetching batch of {len(chunk)} titles: {e}")
                for t in chunk:
                    if t not in results:
                        results[t] = (None, None, None)

        return results

    def save_page(
        self,
        title: str,
        new_wikitext: str,
        summary: Optional[str] = None,
        basetimestamp: Optional[str] = None,
        minor: bool = True,
        bot: bool = True,
        acting_user: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Save modified wikitext to MediaWiki with conflict detection and attribution to the acting user.
        Returns: (success: bool, message: str)
        """
        token = self.get_csrf_token()
        if not token:
            return False, "Failed to obtain CSRF edit token"

        # High-throughput rate limit pause
        elapsed = time.time() - self._last_edit_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        user_label = acting_user or self.username or "User"
        edit_summary = summary or f"{config.edit_summary} (Operated by User: {user_label})"

        post_data: Dict[str, Any] = {
            "action": "edit",
            "title": title,
            "text": new_wikitext,
            "summary": edit_summary,
            "token": token,
            "format": "json",
        }

        if basetimestamp:
            post_data["basetimestamp"] = basetimestamp
        if minor:
            post_data["minor"] = "1"
        if bot:
            post_data["bot"] = "1"

        try:
            res = self._http_client().post(
                self.api_url,
                data=post_data,
                timeout=config.request_timeout,
            )
            self._last_edit_time = time.time()

            # Check if Cloudflare / CleanTalk firewall challenged the POST edit
            if res.status_code in (412, 429) or "Request Blocked" in res.text or "Too Many Requests" in res.text:
                logger.warning(f"Justapedia firewall challenged edit on '{title}' (HTTP {res.status_code})")
                return False, f"Justapedia firewall challenge (HTTP {res.status_code}). MediaWiki session cookies or bot approval needed to edit live."

            data = self._safe_json(res)

            if "edit" in data:
                result = data["edit"].get("result")
                if result == "Success":
                    new_revid = data["edit"].get("newrevid")
                    self.last_revid = new_revid
                    logger.info(f"Successfully saved page '{title}' by {user_label} (rev {new_revid})")
                    return True, f"Saved rev {new_revid}"
                elif "nochange" in data["edit"]:
                    self.last_revid = None
                    logger.info(f"Page '{title}' had no changes to save.")
                    return True, "No change"

            if "error" in data:
                err = data["error"]
                code = err.get("code")
                info = err.get("info", "")
                if code == "editconflict":
                    logger.warning(f"Edit conflict detected on '{title}'.")
                    return False, f"Edit conflict: {info}"
                if code in ("badtoken", "assertuserfailed"):
                    self._csrf_token = None
                    return False, f"Auth error: {info}"
                return False, f"MediaWiki API error ({code}): {info}"

            return False, f"Unexpected response: {data}"

        except Exception as e:
            logger.error(f"Failed to edit page '{title}': {e}")
            return False, str(e)

    def get_category_members(
        self, category_title: str, limit: int = 500, namespace: int = 0
    ) -> List[str]:
        """Fetch page titles belonging to a category."""
        clean_cat = category_title.strip()
        if not clean_cat.lower().startswith("category:"):
            clean_cat = f"Category:{clean_cat}"

        titles: List[str] = []
        cmcontinue = None

        while len(titles) < limit:
            batch_limit = min(50, limit - len(titles))
            params: Dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": clean_cat,
                "cmlimit": str(batch_limit),
                "cmnamespace": str(namespace),
                "format": "json",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            try:
                res = self._http_client().get(
                    self.api_url, params=params, timeout=config.request_timeout
                )
                data = self._safe_json(res)
                members = data.get("query", {}).get("categorymembers", [])
                for m in members:
                    titles.append(m["title"])

                cmcontinue = data.get("continue", {}).get("cmcontinue")
                if not cmcontinue:
                    break
            except Exception as e:
                logger.error(f"Error fetching category members for {category_title}: {e}")
                break

        return titles
