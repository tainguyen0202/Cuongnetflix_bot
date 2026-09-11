"""
Supabase client for the minimal bot.

Supabase is the source of truth:
  - cookies table  -> cookie pool (raw_line)
  - profiles table -> user quota / plan / telegram_id

The bot keeps a RAM copy of the cookie pool (loaded at startup) and reads /
writes quota directly on the profiles table.
"""

import datetime
import logging
import threading

logger = logging.getLogger("NetflixBot")

try:
    from supabase import create_client, Client
except Exception:  # pragma: no cover
    create_client = None
    Client = None

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client = None
_client_lock = threading.Lock()

# ── RAM cookie pool ──
_cookies = []
_cookies_lock = threading.Lock()


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not create_client or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    with _client_lock:
        if _client is None:
            try:
                _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            except Exception as e:
                logger.warning("Supabase client init failed: %s", e)
                _client = None
    return _client


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY and create_client)


# ── Cookie pool ──

def load_cookies_from_supabase():
    """Load all Netflix cookie raw_lines from Supabase into RAM."""
    global _cookies
    client = _get_client()
    if client is None:
        logger.warning("Supabase not configured — cookie pool empty")
        _cookies = []
        return 0
    try:
        lines = []
        offset = 0
        page_size = 1000
        while True:
            res = (
                client.table("cookies")
                .select("raw_line")
                .eq("website_name", "Netflix")
                .neq("status", "dead")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                break
            lines.extend(r["raw_line"] for r in rows if r.get("raw_line"))
            if len(rows) < page_size:
                break
            offset += page_size
        with _cookies_lock:
            _cookies = lines
        logger.info("Loaded %d cookies from Supabase", len(lines))
        return len(lines)
    except Exception as e:
        logger.warning("load_cookies_from_supabase failed: %s", e)
        _cookies = []
        return 0


def get_cookie_pool():
    """Return a snapshot of the RAM cookie pool."""
    with _cookies_lock:
        return list(_cookies)


def get_cookie_count():
    with _cookies_lock:
        return len(_cookies)


# ── Profile / quota ──

def _today_vn():
    """YYYY-MM-DD theo giờ Việt Nam (UTC+7)."""
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    return now.strftime("%Y-%m-%d")


def get_profile_by_telegram(telegram_id):
    """Tìm profile theo telegram_id. Trả về dict profile hoặc None."""
    client = _get_client()
    if client is None or not telegram_id:
        return None
    try:
        res = (
            client.table("profiles")
            .select("*")
            .eq("telegram_id", int(telegram_id))
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_profile_by_telegram failed: %s", e)
        return None


def get_user_lang(telegram_id):
    """Đọc ngôn ngữ của user theo telegram_id. Mặc định 'vi'."""
    profile = get_profile_by_telegram(telegram_id)
    if not profile:
        return "vi"
    lang = profile.get("lang") or ""
    return lang if lang in ("vi", "en") else "vi"


def set_user_lang(telegram_id, lang):
    """Lưu ngôn ngữ của user vào profile (Supabase)."""
    client = _get_client()
    if client is None or not telegram_id:
        return False
    if lang not in ("vi", "en"):
        return False
    try:
        res = (
            client.table("profiles")
            .update({"lang": lang, "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            .eq("telegram_id", int(telegram_id))
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.warning("set_user_lang failed: %s", e)
        return False


def _is_expired(profile):
    """Plan hết hạn 30 ngày chưa."""
    exp = profile.get("plan_expires_at")
    if not exp or profile.get("plan") in (None, "free"):
        return False
    try:
        exp_dt = datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        return exp_dt < datetime.datetime.now(datetime.timezone.utc)
    except Exception:
        return False


def _reset_if_new_day(profile):
    """Reset links_used_today nếu last_reset_date khác hôm nay (giờ VN)."""
    today = _today_vn()
    if profile.get("last_reset_date") != today:
        profile["links_used_today"] = 0
        profile["last_reset_date"] = today
    return profile


def get_quota_left(profile):
    """Tính quota còn lại hôm nay. Free plan → 0 (không giới hạn, phải qua gate)."""
    profile = _reset_if_new_day(profile)
    plan = profile.get("plan") or "free"
    if plan == "free":
        return 0
    limit = int(profile.get("quota_limit") or 0)
    used = int(profile.get("links_used_today") or 0)
    return max(0, limit - used)


def consume_quota(profile):
    """Trừ 1 lượt quota (chỉ cho basic/pro). Trả về profile đã cập nhật hoặc None."""
    client = _get_client()
    if client is None:
        return None
    profile = _reset_if_new_day(profile)
    plan = profile.get("plan") or "free"
    if plan == "free":
        return profile
    used = int(profile.get("links_used_today") or 0)
    limit = int(profile.get("quota_limit") or 0)
    if used >= limit:
        return None
    updated = {
        "links_used_today": used + 1,
        "last_reset_date": _today_vn(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        res = (
            client.table("profiles")
            .update(updated)
            .eq("id", profile["id"])
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else {**profile, **updated}
    except Exception as e:
        logger.warning("consume_quota failed: %s", e)
        return None


def downgrade_expired(profile):
    """Nếu plan hết hạn 30 ngày → set plan=free, quota=0. Trả về profile mới."""
    if not _is_expired(profile):
        return profile
    client = _get_client()
    if client is None:
        return profile
    updated = {
        "plan": "free",
        "quota_limit": 0,
        "plan_expires_at": None,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        res = (
            client.table("profiles")
            .update(updated)
            .eq("id", profile["id"])
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else {**profile, **updated}
    except Exception as e:
        logger.warning("downgrade_expired failed: %s", e)
        return profile


def update_cookie_status(raw_line, status, country_code=None, plan_name=None, email=None):
    """Cập nhật trạng thái cookie lên Supabase (sau khi check)."""
    client = _get_client()
    if client is None or not raw_line:
        return
    fields = {
        "status": status,
        "last_checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if country_code:
        fields["country_code"] = country_code.upper()
    if plan_name:
        fields["plan_name"] = str(plan_name)
    if email:
        fields["email"] = str(email)
    try:
        client.table("cookies").update(fields).eq("raw_line", raw_line).execute()
    except Exception as e:
        logger.warning("update_cookie_status failed: %s", e)


def delete_cookie(raw_line):
    """Xóa cookie DEAD khỏi Supabase."""
    client = _get_client()
    if client is None or not raw_line:
        return
    try:
        client.table("cookies").delete().eq("raw_line", raw_line).execute()
    except Exception as e:
        logger.warning("delete_cookie failed: %s", e)
