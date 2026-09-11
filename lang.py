"""
Language strings — Vietnamese & English (minimal, synced 1:1).
"""

STRINGS = {
    "vi": {
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",
        "lang_saved": "✅ Ngôn ngữ đã đổi sang <b>Tiếng Việt</b>.",

        "welcome": (
            "🎬 <b>CUỒNG NETFLIX</b>\n"
            "\n"
            "👋 Chào {name}, chúc bạn xem phim vui vẻ!\n\n"
            "Nhận link đăng nhập Netflix tức thì chỉ với 1 chạm, hỗ trợ TV 📺, điện thoại 📱 & máy tính 💻 không cần mật khẩu.\n"
            "🎟 Gói: {plan}\n\n"
            "🍿 Gõ /loginlink để nhận link vào xem ngay nhé!"
        ),

        "searching": (
            "⏳ Đang chuẩn bị liên kết đăng nhập...\n\n"
            "<i>Vui lòng đợi trong giây lát, hệ thống đang xử lý...</i>"
        ),
        "link_fail": "❌ Rất tiếc, hệ thống chưa thể tạo link ngay lúc này.\n\n💡 Vui lòng thử lại sau vài phút. Nếu vẫn không được, hãy liên hệ Admin để được hỗ trợ!",
        "no_live_cookie": "Hiện tại hệ thống chưa có tài khoản sẵn sàng. Vui lòng thử lại sau vài phút.",

        "shrinkme_gate_msg": (
            "🔐 <b>XÁC THỰC ĐỂ NHẬN LINK NETFLIX</b>\n"
            "\n"
            "💡 <i>Tài khoản free luôn cần vượt link. Nếu bạn có gói đang hoạt động, bot sẽ tự bỏ qua bước này.</i>\n\n"
            "1️⃣ Copy link dưới đây và mở bằng trình duyệt ngoài (Chrome/Safari):\n"
            "🔗 <code>{url}</code>\n\n"
            "2️⃣ Đợi ~15-30s, hoàn tất các bước trên trang theo hướng dẫn\n"
            "3️⃣ Hệ thống đưa bạn quay lại bot → nhận ngay link Netflix\n\n"
            "💡 <i>Lỡ đóng trang? Copy lại link trên.\n"
            "Chưa nhận được link Netflix? Gõ /loginlink để lấy link mới.</i>"
        ),
        "shrinkme_invalid": (
            "⌛ Liên kết xác thực đã hết hạn hoặc đã được sử dụng.\n\n"
            "👉 Vui lòng gõ /loginlink để lấy liên kết mới nhé!"
        ),
        "gate_maintenance": "⚠️ Hệ thống vượt link đang bảo trì. Vui lòng thử lại sau ít phút.",

        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
        "link_your_plan": "Gói của bạn: {plan}",
        "link_mail": "Mail: {email}",
        "link_han": "Hạn: {billing}",
        "link_admin": "Liên Hệ: {admin}",
        "link_title": "🔗 <b>Link:</b>",
        "link_devices": (
            " 💻 <a href=\"{pc}\">Xem trên máy tính</a>\n"
            "📱 <a href=\"{phone}\">Xem trên điện thoại</a>\n"
            "📺 <a href=\"{tv}\">Xem trên TV</a>"
        ),
        "link_expire": "⏳ Hết hạn sau: ~1 giờ",
        "link_remaining": "📊 Gói hôm nay còn {left}/{limit} lượt không cần vượt",
        "link_remaining_inf": "📊 Còn ∞ lượt hôm nay",

        "no_uses_left": "❌ Bạn đã hết lượt hôm nay.\n⏰ Quay lại sau 00:00 để lấy link mới.",
        "rate_limited": "⏳ Bạn thao tác quá nhanh. Vui lòng đợi vài phút rồi thử lại.",
        "not_linked": (
            "❌ Bạn chưa liên kết tài khoản.\n\n"
            "1️⃣ Đăng ký/đăng nhập tại: {web}\n"
            "2️⃣ Vào trang <b>Hồ sơ</b>, nhập <b>Telegram ID</b> của bạn\n"
            "3️⃣ Quay lại đây dùng /loginlink"
        ),
    },
    "en": {
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",
        "lang_saved": "✅ Language changed to <b>English</b>.",

        "welcome": (
            "🎬 <b>CUỒNG NETFLIX</b>\n"
            "\n"
            "👋 Hello {name}, enjoy your movies!\n\n"
            "Get a Netflix login link instantly with one tap, supporting TV 📺, phone 📱 & computer 💻 without a password.\n"
            "🎟 Plan: {plan}\n\n"
            "🍿 Type /loginlink to get your link now!"
        ),

        "searching": (
            "⏳ Preparing your login link...\n\n"
            "<i>Please wait a moment, the system is processing...</i>"
        ),
        "link_fail": "❌ Sorry, the system could not create a link right now.\n\n💡 Please try again in a few minutes. If it still fails, contact Admin for support!",
        "no_live_cookie": "No accounts are available right now. Please try again in a few minutes.",

        "shrinkme_gate_msg": (
            "🔐 <b>VERIFY TO GET YOUR NETFLIX LINK</b>\n"
            "\n"
            "💡 <i>Free users always need to complete the gate. If you have an active plan, the bot skips this automatically.</i>\n\n"
            "1️⃣ Copy the link below and open in an external browser (Chrome/Safari):\n"
            "🔗 <code>{url}</code>\n\n"
            "2️⃣ Wait ~15-30s and complete the steps on that page\n"
            "3️⃣ You'll be brought back to the bot → get your Netflix link\n\n"
            "💡 <i>Closed the page? Copy the link above.\n"
            "No Netflix link yet? Type /loginlink to get a new one.</i>"
        ),
        "shrinkme_invalid": (
            "⌛ The verification link has expired or was already used.\n\n"
            "👉 Please type /loginlink to get a new one!"
        ),
        "gate_maintenance": "⚠️ The gate link system is under maintenance. Please try again later.",

        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
        "link_your_plan": "Your plan: {plan}",
        "link_mail": "Mail: {email}",
        "link_han": "Billing: {billing}",
        "link_admin": "Contact: {admin}",
        "link_title": "🔗 <b>Link:</b>",
        "link_devices": (
            " 💻 <a href=\"{pc}\">Watch on computer</a>\n"
            "📱 <a href=\"{phone}\">Watch on phone</a>\n"
            "📺 <a href=\"{tv}\">Watch on TV</a>"
        ),
        "link_expire": "⏳ Expires in: ~1 hour",
        "link_remaining": "📊 Plan left today: {left}/{limit} no-gate uses",
        "link_remaining_inf": "📊 ∞ uses left today",

        "no_uses_left": "❌ You have run out of uses today.\n⏰ Come back after 00:00 to get a new link.",
        "rate_limited": "⏳ You are acting too fast. Please wait a few minutes and try again.",
        "not_linked": (
            "❌ You haven't linked your account.\n\n"
            "1️⃣ Register/login at: {web}\n"
            "2️⃣ Go to <b>Profile</b>, enter your <b>Telegram ID</b>\n"
            "3️⃣ Come back and use /loginlink"
        ),
    },
}


def t(key, lang="vi", **kwargs):
    """Translate a key with optional format args. Fallback to vi then raw key."""
    lang = lang if lang in STRINGS else "vi"
    template = STRINGS[lang].get(key) or STRINGS["vi"].get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
