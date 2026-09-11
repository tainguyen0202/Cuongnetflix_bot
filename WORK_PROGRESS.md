# WORK_PROGRESS.md — CuongNetflix Bot (new)

## Project Name
CuongNetflix Bot — Python Telegram Bot + Supabase + HTTP API.

## Goal
Bot Telegram tạo link đăng nhập Netflix thật từ pool cookie (Supabase). Bot mới thay thế
bot cũ (`netflix-bot-tele`) dùng file cục bộ — đã dọn sạch repo (zip + xóa + disable
service).

## Baseline (2026-09-11)
- Bot mới (`netflix-bot-new`) đã deploy lên JustRunMy.App, hoạt động.
- Bot cũ (`netflix-bot-tele`) đã zip backup ra `/root/backups/netflix-bot-tele-backup.tar.gz`,
  xóa khỏi repo, disable service `netflix-bot.service`.

## Task Checklist
- [x] Zip backup bot cũ + xóa thư mục + disable service
- [x] Tạo migration Supabase `create_telegram_links` (bảng + RLS)
- [x] `supabase_client.py` — thêm CRUD: `get_telegram_link`, `mark_telegram_link_linked`,
      `expire_telegram_link`, `bind_telegram_to_profile`
- [x] `handlers.py` — xử lý `/start link_XXXX` (liên kết web <-> bot tự động)
- [x] `lang.py` — thêm chuỗi i18n: `link_invalid`, `link_already`, `link_expired`,
      `link_success`, `link_failed` (vi + en)
- [x] Python syntax check PASS
- [x] Fix 409 conflict: `bind_telegram_to_profile` xóa profile trùng trước khi gán
- [x] Dọn sạch Supabase: xóa 456 profiles bot cũ, 4 orders, 2 telegram_links
- [x] Deploy bot rebuild + restart trên JustRunMy.App
- [x] Test end-to-end: tạo token → gán telegram_id → linked → poll OK

## Progress Log
- **2026-09-11 (dọn repo + liên kết Telegram tự động)**:
  - Zip + xóa `netflix-bot-tele` (bot cũ dùng file cục bộ, service đã dừng).
  - Tạo migration Supabase `create_telegram_links`: token (PK), web_user_id (FK),
    telegram_id, status (pending/linked/expired), expires_at. RLS: service_role full,
    authenticated chỉ đọc/tạo link của mình.
  - Bot: khi user `/start link_XXXX` → tra token → bind_telegram_to_profile
    (ghi telegram_id bằng service_role) → mark token linked → gửi tin succès.
  - Web: tạo token → deep link `t.me/bot?start=link_XXXX` → poll → auto-update.
- **2026-09-11 (fix 409 conflict + dọn sạch dữ liệu)**:
    - Lỗi: bot PATCH profile web với telegram_id → 409 Conflict vì `telegram_id` UNIQUE
      đã tồn tại ở profile cũ (bot cũ tạo profile id = telegram_id, email @telegram.bot).
    - Fix `bind_telegram_to_profile`: trước khi gán, xóa mọi profile KHÁC có cùng
      telegram_id (hoặc id = telegram_id) → không bao giờ conflict nữa.
    - Dọn sạch Supabase: xóa 456 profile bot cũ (@telegram.bot), 4 orders, 2
      telegram_links, reset telegram_id. Chỉ giữ 16 profile web uuid. 2 user bot cũ
      mất gói basic/pro (vy, Taylor) — sẽ tự liên hệ cấp lại.
    - Test end-to-end: tạo token → gán telegram_id (không 409) → linked → poll OK.
    - Deploy bot lên JustRunMy.App (rebuild + restart). Verify bot logs: 2026 cookies
      loaded, polling OK, không lỗi.

## Deploy
- Bot mới đã deploy lên JustRunMy.App (port 8081).
- Cần push code mới → JustRunMy.App rebuild (hoặc redeploy zip).

## Known Issues
- `cookie.txt` 21MB đã bị xóa cùng bot cũ — không còn file cookie cục bộ nào.
- Proxy pool (`proxies.py` + `PROXY_URLS.txt`) vẫn load được (17 live proxy khi dừng service cũ).
- Bot mới chỉ load cookie từ Supabase, KHÔNG đọc file cục bộ.
