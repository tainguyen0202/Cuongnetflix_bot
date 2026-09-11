"""
Proxy pool manager — đọc PROXY_URLS.txt (ip:port mỗi dòng), tự detect loại
(http / socks5 / socks4), health check theo vòng batch, giữ top proxy sống.

- get_proxy(): xoay ngẫu nhiên trong các proxy sống (ưu tiên latency thấp)
- mark_bad(url): proxy lỗi giữa chừng → tạm cooldown, scanner sẽ quét lại
- start_proxy_scanner(): thread nền scan vòng batch 200 proxy mỗi ~10 phút
"""

import os
import time
import random
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests as curl_requests

logger = logging.getLogger("NetflixBot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "PROXY_URLS.txt")

_lock = threading.RLock()
_live = {}           # proxy_url -> {"latency": float, "checked": ts}
_bad_until = {}      # proxy_url -> ts (cooldown sau khi fail runtime)
_fail_count = {}     # host -> số lần fail liên tiếp khi test
_file_total = 0
_dead_removed = 0
_scan_offset = 0
_scanner_started = False

BATCH = 200
MAX_LIVE = 30
SCAN_INTERVAL = 600
TEST_TIMEOUT = 5
BAD_COOLDOWN = 300
STALE_AFTER = 1800
MAX_FAIL = 3         # fail liên tiếp bao nhiêu lần thì xóa khỏi PROXY_URLS.txt


def _read_proxy_hosts():
    """Đọc toàn bộ dòng ip:port trong file."""
    global _file_total
    if not os.path.exists(PROXY_FILE):
        return []
    out = []
    try:
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                out.append(line)
    except Exception as e:
        logger.warning(f"Proxy file read error: {e}")
        return []
    with _lock:
        _file_total = len(out)
    return out


def _test_proxy(host):
    """Thử 3 loại scheme, trả (proxy_url, latency) hoặc None."""
    for scheme in ("http", "socks5", "socks4"):
        url = f"{scheme}://{host}"
        try:
            start = time.time()
            s = curl_requests.Session(impersonate="chrome120", timeout=TEST_TIMEOUT)
            r = s.get(
                "https://www.netflix.com/",
                proxies={"https": url, "http": url},
                timeout=TEST_TIMEOUT,
                allow_redirects=True,
            )
            s.close()
            latency = time.time() - start
            if r.status_code < 500:
                return url, latency
        except Exception:
            continue
    return None


def _matches_host(proxy_url, host):
    return proxy_url.endswith("://" + host)


def _remove_dead_hosts(hosts):
    """Xóa các host chết khỏi PROXY_URLS.txt + pool. Gọi khi đã giữ _lock."""
    global _file_total, _dead_removed
    if not hosts:
        return 0
    remove_set = set(hosts)
    removed = 0
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            kept = [ln for ln in lines if ln.strip() not in remove_set]
            removed = len(lines) - len(kept)
            if removed:
                import tempfile
                fd, tmp = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write("\n".join(kept))
                        if kept:
                            f.write("\n")
                    os.replace(tmp, PROXY_FILE)
                except Exception:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise
        except Exception as e:
            logger.warning(f"Proxy remove error: {e}")
            return 0
    for h in remove_set:
        _fail_count.pop(h, None)
        for key in [u for u in list(_live) if _matches_host(u, h)]:
            _live.pop(key, None)
        for key in [u for u in list(_bad_until) if _matches_host(u, h)]:
            _bad_until.pop(key, None)
        logger.info(f"removed dead proxy {h} (fail x{MAX_FAIL})")
    _file_total = max(_file_total - removed, 0)
    _dead_removed += removed
    return removed


def _scan_batch():
    """Quét 1 batch proxy tiếp theo trong file, cập nhật pool sống, xóa proxy dead."""
    global _scan_offset, _live
    hosts = _read_proxy_hosts()
    if not hosts:
        return
    with _lock:
        offset = _scan_offset
        _scan_offset = (offset + BATCH) % max(len(hosts), 1)
    batch = hosts[offset:offset + BATCH]
    if not batch:
        return

    results = []
    try:
        with ThreadPoolExecutor(max_workers=40) as ex:
            results = list(ex.map(_test_proxy, batch))
    except Exception as e:
        logger.warning(f"Proxy scan error: {e}")
        return

    now = time.time()
    dead_hosts: list[str] = []
    with _lock:
        for host, res in zip(batch, results):
            if res:
                url, latency = res
                _fail_count.pop(host, None)
                if _bad_until.get(url, 0) > now:
                    continue
                _live[url] = {"latency": latency, "checked": now}
            else:
                _fail_count[host] = _fail_count.get(host, 0) + 1
                if _fail_count[host] >= MAX_FAIL:
                    dead_hosts.append(host)
        _remove_dead_hosts(dead_hosts)
        # Giữ tối đa MAX_LIVE proxy nhanh nhất
        if len(_live) > MAX_LIVE:
            top = sorted(_live.items(), key=lambda kv: kv[1]["latency"])[:MAX_LIVE]
            _live = dict(top)
        # Loại proxy chưa được retest quá lâu
        stale = [u for u, v in _live.items() if now - v["checked"] > STALE_AFTER]
        for u in stale:
            _live.pop(u, None)
    logger.info(f"Proxy pool: {len(_live)} live (batch {len(batch)} scanned, offset {_scan_offset})")


def _scanner_loop():
    while True:
        try:
            _scan_batch()
        except Exception as e:
            logger.warning(f"Proxy scanner error: {e}")
        time.sleep(SCAN_INTERVAL)


def start_proxy_scanner():
    """Khởi động scanner nền (idempotent)."""
    global _scanner_started
    with _lock:
        if _scanner_started:
            return
        _scanner_started = True
    threading.Thread(target=_scanner_loop, daemon=True).start()
    threading.Thread(target=_scan_batch, daemon=True).start()
    logger.info("🔄 Proxy scanner started")


def get_proxy():
    """Trả 1 proxy sống ngẫu nhiên (ưu tiên latency thấp) hoặc None."""
    with _lock:
        now = time.time()
        candidates = [u for u in _live if _bad_until.get(u, 0) <= now]
        if not candidates:
            return None
        top = sorted(candidates, key=lambda u: _live[u]["latency"])[:10]
        return random.choice(top)


def mark_bad(proxy_url):
    """Proxy lỗi khi đang dùng → cooldown tạm, scanner sẽ quét lại."""
    if not proxy_url:
        return
    with _lock:
        _live.pop(proxy_url, None)
        _bad_until[proxy_url] = time.time() + BAD_COOLDOWN


def add_proxy_lines(lines):
    """Append proxy host mới (ip:port) vào PROXY_URLS.txt, cập nhật _file_total."""
    if not lines:
        return 0
    with _lock:
        existing = set(_read_proxy_hosts())
        to_add = [ln for ln in lines if ln not in existing]
        if not to_add:
            return 0
        with open(PROXY_FILE, "a", encoding="utf-8") as f:
            for ln in to_add:
                f.write(ln + "\n")
        _read_proxy_hosts()
    return len(to_add)


def get_proxy_stats():
    """Return {"live", "file_total", "removed"}."""
    with _lock:
        return {
            "live": len(_live),
            "file_total": _file_total,
            "removed": _dead_removed,
        }
