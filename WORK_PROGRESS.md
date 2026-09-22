# WORK_PROGRESS.md — CuongNetflix Bot (new)

## Project Name
CuongNetflix Bot — Python Telegram Bot + Supabase + HTTP API.

## Goal
Bot Telegram tạo link đăng nhập Netflix thật từ pool cookie (Supabase). Bot mới thay thế
bot cũ (`netflix-bot-tele`) dùng file cục bộ — đã dọn sạch repo (zip + xóa + disable
service).

## Baseline (2026-09-11)
- Bot mới (`netflix-bot-new`) đã deploy lên Tranger Cloud, hoạt động.
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
- [x] Deploy bot rebuild + restart trên Tranger Cloud
- [x] Test end-to-end: tạo token → gán telegram_id → linked → poll OK
- [x] Auto cookie live/die checker + auto purge dead cookies
- [x] Fix Dockerfile: thêm `cookie_checker.py` vào dòng COPY

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
    - Deploy bot lên Tranger Cloud (rebuild + restart). Verify bot logs: 2026 cookies
      loaded, polling OK, không lỗi.
- **2026-09-18 (tối ưu tốc độ ra link nftoken)**:
  - Bỏ `validate_nftoken()` khỏi luồng chính trong `handlers.py` để giảm độ trễ.
  - Luồng hiện tại: chọn cookie → `check_cookie()` → `generate_nftoken()` → trả link/login.
  - Giữ hàm `validate_nftoken()` trong `checker.py` để dùng lại sau nếu cần.
  - Web vẫn gọi `/api/check-cookie` như cũ; phản hồi nhận token + link nhanh hơn.
  - Đã push `main` lên Tranger Cloud, rebuild image và restart app.
  - Verify container: `/app/handlers.py` không còn gọi `validate_nftoken()`.
- **2026-09-18 (Netflix-only cookie pool complete)**:
  - Import 12,039 Netflix cookie từ `Web-cuongnetflix/Cookies/` vào Supabase `cookies` table.
  - DB `cookies` table: 17,013 unknown + 10 green + 640 dead = ~17,663 rows, tất cả `website_name='Netflix'`.
  - Xóa local `Web-cuongnetflix/Cookies/` (2997 dirs, 18,798 txt files).
  - Cookie pool Supabase hiện tại đủ cho bot rải link liên tục.
- **2026-09-22 (Safe Auto Cookie Live/Die Checker & Auto Purge)**:
  - Tạo `cookie_checker.py`: background thread worker tự động duyệt pool cookie theo batch nhỏ (20 cookie/lần, delay 3s).
  - Strike system (3-strikes): Soft dead (`parse_failed`, `redirect_login`) phải fail 3 lần liên tiếp mới xóa.
  - Hard dead (`FORMER_MEMBER`, `NEVER_MEMBER`, `ANONYMOUS`) lập tức xóa dứt điểm khỏi DB qua `delete_cookie_by_id`.
  - HTTP errors (429/403/5xx/timeout) không đếm fail để bảo vệ cookie, tuyệt đối không die nhầm.
  - Tự động dọn dẹp sạch sẽ: hàm `purge_dead_cookies()` quét và xóa toàn bộ cookie dead còn sót sau mỗi batch.
  - Migration SQL `migration_cookies_strike.sql` — anh chạy trên Supabase Dashboard → SQL Editor.
  - **Fix bug**: Dockerfile COPY tường minh → quên thêm `cookie_checker.py` → `ModuleNotFoundError` khi deploy.
  - **Fix bug /loginlink bị pending mãi mãi**:
    - Nguyên nhân 1: Thiếu import `delete_cookie` trong `handlers.py` khiến Python văng `NameError: name 'delete_cookie' is not defined` khi gặp cookie chết.
    - Nguyên nhân 2: Hàm `_deliver_login_link` thiếu `try...except`, ngoại lệ làm coroutine crash âm thầm khiến bot không bao giờ edit lại tin nhắn chờ ("⏳ Preparing your login link...").
    - Tối ưu hóa: `get_cookie_pool_list` giờ ưu tiên lấy cookie `status='green'` (LIVE) trước để tạo link tức thì 1s, giảm `max_tries` từ 25 xuống 8 để tránh timeout treo thread.

- **2026-09-22 (Đồng bộ chung Supabase & Tối ưu Tranger Cloud 0.15 vCPU / 150MB RAM)**:
  - Dự án Supabase chung: `https://jvokfclberwizzeqmfnc.supabase.co`.
  - Khởi tạo đầy đủ schema bảng: `cookies`, `profiles`, `telegram_links`, view `cookie_status_by_country`, RPC `get_netflix_country_summary`.
  - Đã chạy thành công migration `migration_cookies_strike.sql` trực tiếp qua Supabase MCP (`check_fail_count`, `last_check_error`, `idx_cookies_checker`).
  - Kích hoạt Supabase Realtime publication trên 3 bảng cốt lõi với `REPLICA IDENTITY FULL`.
  - Tối ưu bộ nhớ Bot cho gói Starter Tranger Cloud (0.15 GB RAM / 150MB limit):
    - Tích hợp `gc.collect()` tự động sau mỗi chu kỳ kiểm tra cookie.
    - Giảm `connection_pool_size` trong `main.py` từ 20 xuống 5 để tiết kiệm socket buffer.
    - Codebase tinh gọn (~300KB), khi nén zip upload nhẹ < 1MB, hoàn toàn nằm trong giới hạn 20MB zip của Tranger Cloud.
  - Python syntax check: PASS 100%.

## Deploy
- Bot deploy lên Tranger Cloud (`cloud.tranger.xyz`), port 8081.
- Gói Starter: 0.15 vCPU / 0.15 GB RAM (150MB), 256MB storage, giới hạn 20MB zip upload.
- Push code / upload zip lên dashboard Tranger Cloud và restart container.

## Known Issues
- Giới hạn RAM 150MB trên Tranger Cloud: bot đã được tối ưu lazy-loading và thu gom rác định kỳ, không cache pool vào memory.
- Proxy pool (`proxies.py` + `PROXY_URLS.txt`) giữ nguyên hoạt động bình thường.
- Bot đọc và đồng bộ hoàn toàn trực tiếp với Supabase.

## Supabase Migrations
- `cookies`, `profiles`, `telegram_links` — ✅ ĐÃ CHẠY HOÀN TẤT.
- `migration_cookies_strike.sql` — ✅ ĐÃ CHẠY HOÀN TẤT.
- Realtime publication `supabase_realtime` — ✅ ĐÃ KÍCH HOẠT.
