"""
Background Auto Cookie Checker & Purge Worker.

Mục tiêu:
1. Tự động kiểm tra pool cookie trên Supabase theo batch nhỏ.
2. Kiểm tra an toàn: cơ chế 3-strikes cho soft dead, không đánh chết oan khi lỗi mạng / IP throttle.
3. Tự động dọn dẹp sạch sẽ cookie DEAD:
   - Xóa ngay lập tức cookie Hard DEAD (FORMER_MEMBER, etc.)
   - Xóa cookie Soft DEAD khi fail_count >= 3
   - Purge toàn bộ status='dead' sau mỗi batch
"""

import logging
import threading
import time

from config import (
    CHECKER_BATCH_SIZE,
    CHECKER_COOKIE_DELAY_SEC,
    CHECKER_ENABLED,
    CHECKER_INTERVAL_SEC,
    CHECKER_MAX_FAIL_COUNT,
    CHECKER_RECHECK_HOURS,
)
from checker import check_cookie, parse_cookie_line
from supabase_client import (
    delete_cookie_by_id,
    get_cookies_to_check,
    purge_dead_cookies,
    update_cookie_check_result,
)

logger = logging.getLogger("NetflixBot.CheckerWorker")

_worker_thread = None
_stop_event = threading.Event()


def _process_single_cookie(cookie_row):
    """
    Xử lý kiểm tra 1 cookie với logic an toàn tuyệt đối.
    Trả về dict thống kê: {"result": "live"|"soft_dead"|"hard_dead"|"error"|"deleted"}
    """
    cid = cookie_row.get("id")
    raw_line = cookie_row.get("raw_line")
    current_status = cookie_row.get("status", "unknown")
    current_fail = int(cookie_row.get("check_fail_count") or 0)

    if not raw_line or not cid:
        return "error"

    nid, sid, extras = parse_cookie_line(raw_line)
    if not nid:
        logger.warning(f"Cookie id={cid} invalid raw_line format -> delete immediately")
        delete_cookie_by_id(cid)
        return "deleted"

    # Check trực tiếp (VPS)
    info = check_cookie(nid, sid, extra_cookies=extras, direct=True)
    status = info.get("status")

    # ── 1. TRƯỜNG HỢP LIVE ──
    if status == "LIVE":
        # Reset strike fail_count về 0, đánh dấu green
        update_cookie_check_result(
            cookie_id=cid,
            status="green",
            fail_count=0,
            last_check_error=None,
            country_code=info.get("country"),
            plan_name=info.get("plan"),
            email=info.get("email"),
        )
        logger.info(f"✅ Cookie id={cid} LIVE ({info.get('plan', '-')}, {info.get('country', '-')})")
        return "live"

    # ── 2. TRƯỜNG HỢP DEAD ──
    if status == "DEAD":
        is_hard_dead = info.get("is_hard_dead", False)
        is_soft_dead = info.get("is_soft_dead", False)
        reason = info.get("dead_reason", "DEAD")

        # 2a. HARD DEAD: Chắc chắn die (FORMER_MEMBER, NEVER_MEMBER...) -> Xóa ngay
        if is_hard_dead:
            logger.info(f"🗑️ Cookie id={cid} Hard DEAD ({reason}) -> deleting immediately")
            delete_cookie_by_id(cid)
            return "hard_dead"

        # 2b. SOFT DEAD: Nghi ngờ (parse_failed, redirect_login) -> Áp dụng strike
        new_fail = current_fail + 1
        if new_fail >= CHECKER_MAX_FAIL_COUNT:
            # Đủ 3 lần fail -> Xóa vĩnh viễn
            logger.info(f"🗑️ Cookie id={cid} Soft DEAD max strikes reached ({new_fail}/{CHECKER_MAX_FAIL_COUNT}, reason: {reason}) -> deleting")
            delete_cookie_by_id(cid)
            return "deleted"
        else:
            # Chưa đủ strike -> Tăng fail count, giữ nguyên status hiện tại (không xóa, không mark dead oan)
            logger.info(f"⚠️ Cookie id={cid} Soft DEAD strike {new_fail}/{CHECKER_MAX_FAIL_COUNT} ({reason}) -> waiting for recheck")
            update_cookie_check_result(
                cookie_id=cid,
                status=current_status,
                fail_count=new_fail,
                last_check_error=f"Strike {new_fail}: {reason}",
                dead_reason=reason,
            )
            return "soft_dead"

    # ── 3. TRƯỜNG HỢP ERROR (429/403/5xx/timeout/mạng) ──
    err = info.get("error", "Unknown error")
    logger.warning(f"⏳ Cookie id={cid} check ERROR: {err} -> skip strike count to prevent false positives")
    update_cookie_check_result(
        cookie_id=cid,
        status=current_status,
        fail_count=current_fail,  # KHÔNG tăng fail count
        last_check_error=f"Temp error: {err}",
    )
    return "error"


def _checker_loop():
    logger.info("🚀 Background Auto-Checker & Purge worker thread started.")
    # Chờ 30s sau khi bot khởi động để các service chính ổn định
    time.sleep(30)

    while not _stop_event.is_set():
        try:
            # 1. Lấy batch cookie cần check
            cookies = get_cookies_to_check(
                batch_size=CHECKER_BATCH_SIZE,
                recheck_hours=CHECKER_RECHECK_HOURS,
            )

            if not cookies:
                logger.info(f"Checker: No cookies pending check. Sleeping for {CHECKER_INTERVAL_SEC}s...")
                # Ngủ ngắn để có thể phản hồi _stop_event
                for _ in range(CHECKER_INTERVAL_SEC):
                    if _stop_event.is_set():
                        break
                    time.sleep(1)
                continue

            logger.info(f"🔍 Checker: Starting batch check of {len(cookies)} cookies...")
            stats = {"live": 0, "soft_dead": 0, "hard_dead": 0, "deleted": 0, "error": 0}

            for row in cookies:
                if _stop_event.is_set():
                    break
                
                res = _process_single_cookie(row)
                if res in stats:
                    stats[res] += 1
                
                # Delay nhỏ giữa mỗi cookie để không spam Netflix và không bị throttle
                if CHECKER_COOKIE_DELAY_SEC > 0:
                    time.sleep(CHECKER_COOKIE_DELAY_SEC)

            logger.info(
                f"📊 Checker Batch Summary: Live={stats['live']}, "
                f"SoftDead(Retrying)={stats['soft_dead']}, HardDead={stats['hard_dead']}, "
                f"Deleted={stats['deleted']}, TempError={stats['error']}"
            )

            # 2. Dọn dẹp triệt để bất kỳ cookie status='dead' nào còn sót lại
            purged = purge_dead_cookies(limit=100)
            if purged > 0:
                logger.info(f"🧹 Purged {purged} additional dead cookies in this cycle.")

        except Exception as e:
            logger.error(f"Unexpected error in checker loop: {e}", exc_info=True)

        # 3. Nghỉ ngơi giữa các batch
        for _ in range(CHECKER_INTERVAL_SEC):
            if _stop_event.is_set():
                break
            time.sleep(1)

    logger.info("🛑 Background Auto-Checker worker stopped.")


def start_auto_checker():
    """Khởi chạy background worker."""
    global _worker_thread
    if not CHECKER_ENABLED:
        logger.info("Auto-Checker is disabled by configuration (CHECKER_ENABLED=0).")
        return

    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _stop_event.clear()
    _worker_thread = threading.Thread(target=_checker_loop, daemon=True, name="cookie-auto-checker")
    _worker_thread.start()
    logger.info("Auto-Checker thread registered.")


def stop_auto_checker():
    """Dừng background worker."""
    _stop_event.set()
