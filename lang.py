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

        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
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
        "link_shrinkme_gate": "🔗 <b>Link của bạn đã sẵn sàng!</b>",
        "link_shrinkme_ad": (
            "📢 Bạn đang dùng gói <b>Free</b> — cần vượt link rút gọn để lấy link đích:\n\n"
            "1️⃣ <b>Copy</b> link bên dưới & mở bằng <b>trình duyệt bên ngoài</b> (Chrome/Safari)\n"
            "2️⃣ Chờ 5 giây rồi bấm <b>Continue</b> / <b>Bỏ qua quảng cáo</b>\n"
            "3️⃣ Link Netflix thật sẽ hiện ra sau khi vượt link\n\n"
            "💎 Nâng cấp <b>Basic/Pro</b> để nhận link trực tiếp, không cần vượt quảng cáo!"
        ),
        "link_shrinkme_btn": "🔗 Mở link (quảng cáo)",
        "link_shrinkme_note": "ℹ️ Gói Free: copy link ra trình duyệt bên ngoài để vượt.",
        "gate_error": "❌ <b>Hệ thống link vượt đang lỗi.</b>\n\nVui lòng thử lại sau ít phút. Nếu vẫn lỗi, hãy liên hệ Admin để được hỗ trợ!",

        "link_invalid": "❌ Liên kết không hợp lệ hoặc đã bị xóa.\n\n👉 Vui lòng vào web và bấm <b>Liên kết Telegram</b> để tạo liên kết mới.",
        "link_already": "✅ Tài khoản Telegram này đã được liên kết với tài khoản web.\n\n🍿 Gõ /loginlink để nhận link xem phim!",
        "link_expired": "⌛ Liên kết đã hết hạn (10 phút).\n\n👉 Vui lòng vào web và bấm <b>Liên kết Telegram</b> để tạo liên kết mới.",
        "link_confirm_body": "🔐 <b>XÁC NHẬN LIÊN KẾT</b>\n\nBạn muốn liên kết tài khoản Telegram này với tài khoản web:\n📧 {email}\n\nĐúng email của bạn chứ?",
        "link_success": "✅ <b>Liên kết thành công!</b>\n\n📧 Web: {email}\n\n🍿 Gói Basic/Pro trên web sẽ được đồng bộ — dùng /loginlink để nhận link trực tiếp, không cần vượt quảng cáo!",
        "link_failed": "❌ Liên kết thất bại. Vui lòng thử lại sau ít phút hoặc liên hệ Admin.",
        "link_cancelled": "❌ Đã hủy liên kết. Bạn có thể tạo liên kết mới bất cứ lúc nào từ web.",
        "link_session_expired": "⌛ Phiên xác nhận đã hết. Vui lòng tạo liên kết mới từ web.",

        "no_uses_left": "❌ Bạn đã hết lượt hôm nay.\n⏰ Quay lại sau 00:00 để lấy link mới.",
        "rate_limited": "⏳ Bạn thao tác quá nhanh. Vui lòng đợi vài phút rồi thử lại.",
        "not_linked": (
            "❌ Bạn chưa liên kết tài khoản.\n\n"
            "1️⃣ Đăng ký/đăng nhập tại: {web}\n"
            "2️⃣ Vào trang <b>Hồ sơ</b>, bấm <b>Liên kết Telegram</b>\n"
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

        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
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
        "link_shrinkme_gate": "🔗 <b>Your link is ready!</b>",
        "link_shrinkme_ad": (
            "📢 You are on the <b>Free</b> plan — pass the shortened link to get the destination link:\n\n"
            "1️⃣ <b>Copy</b> the link below & open it in an <b>external browser</b> (Chrome/Safari)\n"
            "2️⃣ Wait 5 seconds then press <b>Continue</b> / <b>Skip Ad</b>\n"
            "3️⃣ The real Netflix link will appear after you pass the gate\n\n"
            "💎 Upgrade to <b>Basic/Pro</b> to receive direct links, no ads!"
        ),
        "link_shrinkme_btn": "🔗 Open link (ads)",
        "link_shrinkme_note": "ℹ️ Free plan: copy the link into an external browser to pass the gate.",
        "gate_error": "❌ <b>The link gate system is currently down.</b>\n\nPlease try again in a few minutes. If it still fails, contact Admin for support!",

        "link_invalid": "❌ Invalid or removed link.\n\n👉 Please open the website and tap <b>Link Telegram</b> to create a new one.",
        "link_already": "✅ This Telegram account is already linked to a web account.\n\n🍿 Type /loginlink to get a movie link!",
        "link_expired": "⌛ The link has expired (10 minutes).\n\n👉 Please open the website and tap <b>Link Telegram</b> to create a new one.",
        "link_confirm_body": "🔐 <b>CONFIRM LINKING</b>\n\nDo you want to link this Telegram account with the web account:\n📧 {email}\n\nIs this your email?",
        "link_success": "✅ <b>Linked successfully!</b>\n\n📧 Web: {email}\n\n🍿 Your Basic/Pro plan from the web will be synced — use /loginlink to get direct links, no ads!",
        "link_failed": "❌ Linking failed. Please try again in a few minutes or contact Admin.",
        "link_cancelled": "❌ Linking cancelled. You can create a new link anytime from the website.",
        "link_session_expired": "⌛ Confirmation session expired. Please create a new link from the website.",

        "no_uses_left": "❌ You have run out of uses today.\n⏰ Come back after 00:00 to get a new link.",
        "rate_limited": "⏳ You are acting too fast. Please wait a few minutes and try again.",
        "not_linked": (
            "❌ You haven't linked your account.\n\n"
            "1️⃣ Register/login at: {web}\n"
            "2️⃣ Go to <b>Profile</b>, tap <b>Link Telegram</b>\n"
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
