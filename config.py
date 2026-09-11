"""
Config & Constants for the new minimal Netflix Bot.

Supabase is the source of truth for cookies + user quota. The bot is a thin
worker: it checks cookies, generates login links, and serves the web API.
"""

import os


def _load_env_file(path):
    """Đọc file .env thủ công (không cần python-dotenv)."""
    import re
    import logging

    logger = logging.getLogger("NetflixBot")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
                if m:
                    key, val = m.group(1), m.group(2).strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                        val = val[1:-1]
                    os.environ.setdefault(key, val)
    except Exception as e:
        logger.warning("Failed to load env file %s: %s", path, e)


# Load .env trước khi đọc các biến (ưu tiên env hiện tại trước, không ghi đè)
_load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


# ── Bot Config ──
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@cuongnetflix_bot")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "1208795685").split(",") if x.strip().isdigit()]

# ── Files ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Gate shortener (/loginlink phải qua link rút gọn) ──
SHRINKME_API_KEY = os.getenv("SHRINKME_API_KEY", "")  # rỗng = tắt gate
SHRINKME_GATE_TTL = 1800  # token gate sống 30 phút (giây)

# ── Supabase (source of truth) ──
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Web URL (để bot hướng dẫn user đăng ký/liên kết) ──
WEB_URL = os.getenv("WEB_URL", "https://cuongnetflix.vercel.app")

# ── Quota / Plans (đồng bộ với web) ──
PLAN_DURATION_DAYS = 30
PLAN_BASIC_DAILY = 10
PLAN_PRO_DAILY = 20

# ── Group gate (bắt buộc tham gia nhóm) ──
GROUP_USERNAMES = [g for g in os.getenv("GROUP_USERNAMES", "sharefreeall").split(",") if g.strip()]
ADMIN_TAG = os.getenv("ADMIN_TAG", "@lucasng22")
