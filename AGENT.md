# AGENT.md — CuongNetflix Bot (Python Telegram + Supabase)

> Đọc file này TRƯỚC khi sửa code bot. Web: `Web-cuongnetflix/AGENT.md`.

## Project / System Objective
Bot Telegram `@cuongnetflix_bot` tạo link đăng nhập Netflix từ pool cookie. Supabase là
source of truth (cookie pool + profile/quota). Bot là worker mỏng: check cookie, gen
NFToken + 3 device links, phục vụ web API (check-cookie/batch-check). Deploy lên
JustRunMy.App / Tranger Cloud (`cloud.tranger.xyz`) — Python runtime, port 8081.

## Current Status
- Bot mới (thay thế `netflix-bot-tele` cũ đã xóa — bot cũ dùng file cục bộ, không Supabase).
- Cookie pool load từ Supabase `cookies` table (website_name='Netflix', status != 'dead').
- Quota/plan đọc-ghi trực tiếp trên `profiles` table (web quản lý plan qua SePay webhook).
- Chỉ có `/start`, `/loginlink`, `/lang`. Gate shrinkme chỉ cho user free.
- Liên kết web <-> bot TỰ ĐỘNG: web tạo token trong `telegram_links` → user bấm deep link
  `t.me/bot?start=link_XXXX` → bot `/start link_XXXX` ghi `telegram_id` vào profile + đánh
  dấu token linked. Không còn nhập ID thủ công.
- Background auto-checker (`cookie_checker.py`) chạy kiểm tra và dọn pool cookie tự động.

## Current Architecture
```
main.py               — entry: load cookie pool, setup commands, start API server, polling
config.py             — env config (BOT_TOKEN, SUPABASE_URL, WEB_URL, ADMIN_IDS...)
supabase_client.py    — Supabase client: cookie pool + profile/quota + telegram_links CRUD
handlers.py           — /start (gồm link_XXXX + shrinkme_), /loginlink, /lang
checker.py            — check cookie, generate/validate NFToken
cookie_checker.py     — background auto-checker (strike system 3-strikes, purge dead)
api_server.py         — HTTP API cho web (check-cookie, batch-check, combo-check) port 8081
shrinkme.py           — rút gọn link gate (chỉ free user)
lang.py               — i18n vi/en
proxies.py            — proxy pool
```

## Key Technical Decisions
- Supabase service_role key = full access (bot backend). Web dùng anon/authenticated.
- **Shrinkme gate logic**: Free user → shrinkme gate (rút gọn link); Basic/Pro có quota → link trực tiếp; Basic/Pro không còn quota → shrinkme gate. Backend quyết định `isShortened` và trả về trong response.
- **Atomic quota**: `consume_quota()` sử dụng `.lt("links_used_today", limit)` để đảm bảo atomicity — tránh race condition khi nhiều request cùng lúc.
- **Auto Cookie Live/Die Checker & Purge**:
  - Chạy background worker (`cookie_checker.py`) định kỳ theo batch nhỏ (20 cookies, delay 3s).
  - Phân loại: Hard DEAD (`FORMER_MEMBER`, `NEVER_MEMBER`, etc.) xóa ngay lập tức khỏi DB; Soft DEAD (`parse_failed`, `redirect_login`) dùng strike system (cần 3 lần fail liên tiếp mới xóa).
  - Lỗi mạng, HTTP 429, 403, 5xx không bao giờ tính fail để chống die nhầm.
  - Auto-purge: Xóa sạch các cookie status='dead' sau mỗi chu kỳ để dọn dẹp DB.
- **`validate_nftoken()`**: Giữ lại nhưng tạm bỏ khỏi luồng chính để tối ưu tốc độ trả link nftoken.
- **`check_cookie()` redirect check**: Kiểm tra HTTP status + session cookie để xác định cookie có bị redirect login hay không.
- Telegram link: token single-use, TTL 10 phút, bind web_user_id; bot ghi telegram_id
  bằng service_role (không cần gọi API web).
- Rate limit /loginlink: 5 lần/15 phút/user.
- Quota: free → 0 (phải qua gate shrinkme); basic/pro → quota_limit/ngày, reset theo giờ VN.
- Plan hết hạn 30 ngày → tự downgrade free khi dùng /loginlink.

## Env (set trên JustRunMy.App / Tranger Cloud)
- `BOT_TOKEN`, `BOT_USERNAME`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `SHRINKME_API_KEY`, `ADMIN_IDS`, `WEB_URL`
- `CHECKER_ENABLED` (default: 1), `CHECKER_BATCH_SIZE` (default: 20), `CHECKER_INTERVAL_SEC` (default: 300)
- `CHECKER_COOKIE_DELAY_SEC` (default: 3.0), `CHECKER_MAX_FAIL_COUNT` (default: 3), `CHECKER_RECHECK_HOURS` (default: 24)

## ⚠️ CRITICAL RULES — Bắt Buộc Tuân Theo Mỗi Lần Thêm File Python Mới

> **RULE [DOCKERFILE-COPY]**: Dockerfile dùng `COPY` tường minh (liệt kê từng file .py, KHÔNG dùng `COPY . .`).
> **Mỗi khi tạo file Python mới (.py), BẮT BUỘC thêm tên file đó vào dòng `COPY` trong `Dockerfile` ngay lập tức — cùng lúc với commit code.**
> Nếu quên → container build không có file → `ModuleNotFoundError` khi deploy.

Ví dụ: Tạo `foo_module.py` → sửa Dockerfile:
```dockerfile
COPY config.py supabase_client.py ... foo_module.py ./
```
Commit cả hai file trong cùng 1 commit.

> **RULE [SYNTAX-CHECK]**: Sau mỗi lần thay đổi code Python, chạy syntax check toàn bộ:
> ```
> python3 -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['config.py','checker.py','supabase_client.py','cookie_checker.py','main.py','handlers.py']]; print('ALL OK')"
> ```

> **RULE [MIGRATION-SQL]**: Mỗi khi thêm cột / bảng Supabase mới, tạo file `migration_*.sql` kèm theo và ghi rõ trong WORK_PROGRESS.md bước "Anh cần chạy SQL này trên Supabase Dashboard → SQL Editor".

## Testing
- Syntax check tất cả file: `python3 -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['config.py','checker.py','supabase_client.py','cookie_checker.py','main.py','handlers.py']]; print('ALL OK')"`
- Test thật: mở bot → /start → /loginlink; web → Hồ sơ → Liên kết Telegram.
- Verify checker: check logs sau deploy, xem dòng `🔍 Checker: Starting batch check`, `✅ Cookie id=...`, `🗑️ Cookie id=... Hard DEAD`.

## Non-Goals
- Không lưu secret trong code (dùng .env / env hosting).
- Không quản lý plan trực tiếp (web + SePay webhook lo phần đó).
