"""
Supabase client for the minimal bot.

Supabase is the source of truth:
  - cookies table  -> cookie pool (raw_line)
  - profiles table -> user quota / plan / telegram_id

The bot queries cookies on-demand in small batches (lazy loading)
to keep RAM usage low (~150MB quota).
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

# ── Cookie pool constants ──
_COOKIE_PAGE_SIZE = 100  # Giảm từ 500 → 100 để tiết kiệm RAM
_COOKIE_CHECK_BATCH = 40  # Số cookie check mỗi lần (check_pool_job)


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


# ── Cookie pool (lazy loading, no RAM cache) ──

def load_cookies_from_supabase():
    """
    Warm-up: query count only, không load toàn bộ vào RAM.
    Trả về tổng số cookie (để log), không lưu vào biến global.
    """
    client = _get_client()
    if client is None:
        logger.warning("Supabase not configured — cookie pool empty")
        return 0
    try:
        # Chỉ đếm, không select raw_line (tiết kiệm bandwidth + RAM)
        res = (
            client.table("cookies")
            .select("id", count="exact")
            .eq("website_name", "Netflix")
            .neq("status", "dead")
            .limit(1)
            .execute()
        )
        count = res.count or 0
        logger.info("Cookie pool size: %d cookies (lazy loading)", count)
        return count
    except Exception as e:
        logger.warning("load_cookies_from_supabase failed: %s", e)
        return 0


def get_cookie_pool():
    """
    Trả về iterator cho 1 batch nhỏ cookie (dùng cho check_pool_job).
    Không load toàn bộ pool vào RAM.
    """
    client = _get_client()
    if client is None:
        return iter([])
    
    def _cookie_generator():
        last_id = None
        while True:
            q = (
                client.table("cookies")
                .select("id, raw_line")
                .eq("website_name", "Netflix")
                .neq("status", "dead")
                .order("id")
                .limit(_COOKIE_PAGE_SIZE)
            )
            if last_id:
                q = q.gt("id", last_id)
            res = q.execute()
            rows = res.data or []
            if not rows:
                break
            for r in rows:
                raw = r.get("raw_line")
                if raw:
                    yield raw
            if len(rows) < _COOKIE_PAGE_SIZE:
                break
            last_id = rows[-1]["id"]
    
    return _cookie_generator()


def get_cookie_pool_batch(batch_size=_COOKIE_CHECK_BATCH):
    """
    Lấy 1 batch nhỏ cookie để check (dùng cho check_pool_job).
    Trả về list có tối đa batch_size phần tử.
    """
    client = _get_client()
    if client is None:
        return []
    try:
        res = (
            client.table("cookies")
            .select("id, raw_line")
            .eq("website_name", "Netflix")
            .neq("status", "dead")
            .order("id")
            .limit(batch_size)
            .execute()
        )
        return [r["raw_line"] for r in (res.data or []) if r.get("raw_line")]
    except Exception as e:
        logger.warning("get_cookie_pool_batch failed: %s", e)
    
    # 3. UU TIEN SO 3: Cookie bi stuck voi status khong chuan (khong phai green/unknown/dead)
    # Vi du: on_hold, die, hoac bat ky gia tri nao khac do import cu / loi logic.
    # Chung se khong bao gio duoc pick o priority 1 va 2 - bi stuck mai mai.
    try:
        res = (
            client.table("cookies")
            .select("id, raw_line, status, check_fail_count")
            .eq("website_name", "Netflix")
            .not_.in_("status", ["green", "unknown", "dead"])
            .order("id")
            .limit(batch_size)
            .execute()
        )
        rows = res.data or []
        if rows:
            logger.info(
                "get_cookies_to_check: %d stuck cookies with unknown status: %s",
                len(rows),
                list({r.get("status") for r in rows}),
            )
            return rows
    except Exception as e:
        logger.warning("get_cookies_to_check (stuck status) failed: %s", e)

    return []


def get_cookie_pool_list(limit=200):
    """
    Trả về list cookie (tối đa limit phần tử) để handlers.py random access.
    Ưu tiên lấy cookie 'green' (đã check LIVE) trước để tạo link tức thì.
    Nếu không đủ thì lấy thêm cookie 'unknown'.
    """
    client = _get_client()
    if client is None:
        return []
    try:
        # 1. Ưu tiên lấy cookie đã check LIVE (status='green')
        res_green = (
            client.table("cookies")
            .select("id, raw_line")
            .eq("website_name", "Netflix")
            .eq("status", "green")
            .limit(limit)
            .execute()
        )
        pool = [r["raw_line"] for r in (res_green.data or []) if r.get("raw_line")]
        if len(pool) >= limit:
            return pool

        # 2. Bổ sung thêm cookie 'unknown' nếu chưa đủ
        needed = limit - len(pool)
        res_unknown = (
            client.table("cookies")
            .select("id, raw_line")
            .eq("website_name", "Netflix")
            .eq("status", "unknown")
            .order("id")
            .limit(needed)
            .execute()
        )
        pool.extend([r["raw_line"] for r in (res_unknown.data or []) if r.get("raw_line")])
        return pool
    except Exception as e:
        logger.warning("get_cookie_pool_list failed: %s", e)
        return []


def get_cookie_count():
    """Query count từ Supabase trực tiếp (không dùng RAM cache)."""
    client = _get_client()
    if client is None:
        return 0
    try:
        res = (
            client.table("cookies")
            .select("id", count="exact")
            .eq("website_name", "Netflix")
            .neq("status", "dead")
            .limit(1)
            .execute()
        )
        return res.count or 0
    except Exception as e:
        logger.warning("get_cookie_count failed: %s", e)
        return 0


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


def get_or_create_profile(telegram_id, username=None, full_name=None):
    """
    Tìm profile theo telegram_id; nếu chưa có → tự tạo profile Free.
    User bot KHÔNG bắt buộc liên kết web — mặc định gói Free (qua gate shrinkme).
    Trả về dict profile hoặc None (lỗi).
    """
    if not telegram_id:
        return None
    profile = get_profile_by_telegram(telegram_id)
    if profile:
        return profile
    client = _get_client()
    if client is None:
        return None
    try:
        row = {
            "id": str(telegram_id),
            "telegram_id": int(telegram_id),
            "username": username or None,
            "full_name": full_name or None,
            "plan": "free",
            "quota_limit": 0,
            "links_used_today": 0,
            "last_reset_date": _today_vn(),
            "lang": "vi",
            "status": "active",
        }
        res = (
            client.table("profiles")
            .upsert(row, on_conflict="id")
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows[0]
        # RLS/service chặn RETURNING → query lại
        return get_profile_by_telegram(telegram_id)
    except Exception as e:
        logger.warning("get_or_create_profile failed: %s", e)
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
        # Atomic: only update if links_used_today < limit (prevent race condition)
        res = (
            client.table("profiles")
            .update(updated)
            .eq("id", profile["id"])
            .lt("links_used_today", limit)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows[0]
        # Quota was exhausted by another request — return None
        return None
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


# ── Telegram links (liên kết web <-> bot) ──

def get_telegram_link(token):
    """Tra token trong bảng telegram_links. Trả về dict hoặc None."""
    client = _get_client()
    if client is None or not token:
        return None
    try:
        res = (
            client.table("telegram_links")
            .select("*")
            .eq("token", str(token))
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_telegram_link failed: %s", e)
        return None


def mark_telegram_link_linked(token, telegram_id):
    """Đánh dấu token đã liên kết + ghi telegram_id. Trả về True/False."""
    client = _get_client()
    if client is None or not token or not telegram_id:
        return False
    try:
        res = (
            client.table("telegram_links")
            .update({
                "status": "linked",
                "telegram_id": int(telegram_id),
            })
            .eq("token", str(token))
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.warning("mark_telegram_link_linked failed: %s", e)
        return False


def expire_telegram_link(token):
    """Đánh dấu token hết hạn (user hủy hoặc quá hạn)."""
    client = _get_client()
    if client is None or not token:
        return False
    try:
        res = (
            client.table("telegram_links")
            .update({"status": "expired"})
            .eq("token", str(token))
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.warning("expire_telegram_link failed: %s", e)
        return False


def bind_telegram_to_profile(web_user_id, telegram_id):
    """Ghi telegram_id vào profile web (liên kết 1 chiều). Trả về True/False."""
    client = _get_client()
    if client is None or not web_user_id or not telegram_id:
        return False
    try:
        # Phòng ngừa unique constraint: xóa mọi profile KHÁC có cùng telegram_id
        # (profile cũ từ bot cũ dùng id = telegram_id, hoặc profile trùng liên kết)
        client.table("profiles").delete() \
            .neq("id", web_user_id) \
            .eq("telegram_id", int(telegram_id)) \
            .execute()
        client.table("profiles").delete() \
            .neq("id", web_user_id) \
            .eq("id", str(telegram_id)) \
            .execute()
        res = (
            client.table("profiles")
            .update({
                "telegram_id": int(telegram_id),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            .eq("id", web_user_id)
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.warning("bind_telegram_to_profile failed: %s", e)
        return False


def update_cookie_status(raw_line, status, country_code=None, plan_name=None, email=None, dead_reason=None):
    """Cập nhật trạng thái cookie lên Supabase (sau khi check)."""
    client = _get_client()
    if client is None or not raw_line:
        return
    fields = {
        "status": status,
        "last_checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if dead_reason:
        fields["dead_reason"] = dead_reason
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
    """Xóa cookie khỏi Supabase bằng raw_line."""
    client = _get_client()
    if client is None or not raw_line:
        return
    try:
        client.table("cookies").delete().eq("raw_line", raw_line).execute()
    except Exception as e:
        logger.warning("delete_cookie failed: %s", e)


def delete_cookie_by_id(cookie_id):
    """Xóa cookie dứt điểm theo ID (an toàn, không miss)."""
    client = _get_client()
    if client is None or not cookie_id:
        return False
    try:
        client.table("cookies").delete().eq("id", cookie_id).execute()
        return True
    except Exception as e:
        logger.warning("delete_cookie_by_id failed for id=%s: %s", cookie_id, e)
        return False


def purge_dead_cookies(limit=100):
    """
    Xóa toàn bộ cookie có status='dead' khỏi DB.
    Chạy định kỳ sau mỗi batch để giữ pool cookie luôn sạch sẽ.
    """
    client = _get_client()
    if client is None:
        return 0
    try:
        # Lấy danh sách ID dead trước để delete
        res = (
            client.table("cookies")
            .select("id")
            .eq("website_name", "Netflix")
            .eq("status", "dead")
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return 0
        ids = [r["id"] for r in rows if "id" in r]
        if ids:
            client.table("cookies").delete().in_("id", ids).execute()
            logger.info("Purged %d dead cookies from Supabase", len(ids))
            return len(ids)
        return 0
    except Exception as e:
        logger.warning("purge_dead_cookies failed: %s", e)
        return 0


def get_cookies_to_check(batch_size=20, recheck_hours=12):
    """
    Lấy batch cookie cần check tự động:
    Ưu tiên 1: status = 'green' cần re-verify (đang phát cho khách, ưu tiên số 1 để tránh lỗi Hold/Dead)
    Ưu tiên 2: status = 'unknown' (chưa check bao giờ)
    Không bao giờ lấy status = 'dead'
    """
    client = _get_client()
    if client is None:
        return []

    # 1. ƯU TIÊN SỐ 1: Kiểm tra cookie GREEN đang live để loại bỏ ngay tài khoản bị Hold/Lỗi thanh toán
    try:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=recheck_hours)
        ).isoformat()
        res = (
            client.table("cookies")
            .select("id, raw_line, status, check_fail_count")
            .eq("website_name", "Netflix")
            .eq("status", "green")
            .or_(f"last_checked_at.is.null,last_checked_at.lt.{cutoff}")
            .order("last_checked_at", nullsfirst=True)
            .limit(batch_size)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows
    except Exception as e:
        logger.warning("get_cookies_to_check (green priority re-check) failed: %s", e)

    # 2. ƯU TIÊN SỐ 2: Kiểm tra cookie unknown
    try:
        res = (
            client.table("cookies")
            .select("id, raw_line, status, check_fail_count")
            .eq("website_name", "Netflix")
            .eq("status", "unknown")
            .order("id")
            .limit(batch_size)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows
    except Exception as e:
        logger.warning("get_cookies_to_check (unknown) failed: %s", e)

    return []


def update_cookie_check_result(
    cookie_id,
    status,
    fail_count=0,
    last_check_error=None,
    country_code=None,
    plan_name=None,
    email=None,
    dead_reason=None,
):
    """Cập nhật kết quả check kèm strike fail_count."""
    client = _get_client()
    if client is None or not cookie_id:
        return False
    fields = {
        "status": status,
        "check_fail_count": fail_count,
        "last_checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if last_check_error is not None:
        fields["last_check_error"] = str(last_check_error)
    if dead_reason is not None:
        fields["dead_reason"] = str(dead_reason)
    if country_code:
        fields["country_code"] = country_code.upper()
    if plan_name:
        fields["plan_name"] = str(plan_name)
    if email:
        fields["email"] = str(email)
    
    try:
        client.table("cookies").update(fields).eq("id", cookie_id).execute()
        return True
    except Exception as e:
        logger.warning("update_cookie_check_result failed for id=%s: %s", cookie_id, e)
        return False

