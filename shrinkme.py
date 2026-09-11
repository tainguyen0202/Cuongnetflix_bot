"""
Shrinkme.io gate — rút gọn deep link qua API shrinkme.io
Trả về shortenedUrl hoặc None (caller fallback maintenance). KHÔNG log API key.
"""

import logging

from curl_cffi import requests as curl_requests

from config import SHRINKME_API_KEY

logger = logging.getLogger("NetflixBot")

_API_URL = "https://shrinkme.io/api"


def shorten(url):
    """Rút gọn url qua shrinkme.io API. Returns shortened str or None on any failure."""
    if not SHRINKME_API_KEY or not url:
        return None
    try:
        resp = curl_requests.get(
            _API_URL,
            params={"api": SHRINKME_API_KEY, "url": url, "format": "text"},
            timeout=10,
            impersonate="chrome",
        )
        short = resp.text.strip()
    except Exception as e:
        logger.warning(f"[Shrinkme] shorten failed: {type(e).__name__}")
        return None
    if not short or not short.startswith("http"):
        logger.warning(f"[Shrinkme] API returned invalid response")
        return None
    return short
