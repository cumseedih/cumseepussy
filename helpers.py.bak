"""
helpers.py — BIN lookup, proxy parsing/testing, CC extraction, gate classification,
             proxy concatenation splitting, and NopeCHA hCaptcha solver.

Used by thehitterbot.py and adyen_engine.py.
"""
import os
import re
import time
import asyncio
import aiohttp
from cachetools import TTLCache

# ── BIN lookup cache (24hr) ─────────────────────────────────────────────
_bin_lookup_cache: TTLCache = TTLCache(maxsize=5000, ttl=86400)

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_session: aiohttp.ClientSession | None = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=300, ssl=False),
            timeout=aiohttp.ClientTimeout(total=15),
            headers=_DEFAULT_HEADERS,
        )
    return _session

_bin_session: aiohttp.ClientSession | None = None

async def _get_bin_session() -> aiohttp.ClientSession:
    global _bin_session
    if _bin_session is None or _bin_session.closed:
        _bin_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=80, ssl=False),
            timeout=aiohttp.ClientTimeout(total=10),
            headers=_DEFAULT_HEADERS,
        )
    return _bin_session

async def close_session():
    global _session, _bin_session
    if _session and not _session.closed:
        await _session.close()
        _session = None
    if _bin_session and not _bin_session.closed:
        await _bin_session.close()
        _bin_session = None


# ══════════════════════════════════════════════════════════════════════════
#  BIN LOOKUP — 3 APIs in parallel, first success wins
# ══════════════════════════════════════════════════════════════════════════
async def bin_lookup(bin_number: str) -> dict:
    _FALLBACK = {"brand": "-", "type": "-", "level": "-", "bank": "-",
                 "country": "-", "flag": "🏳️"}

    bin_number = (bin_number or "").strip().replace(" ", "")[:6]
    if len(bin_number) < 6:
        return _FALLBACK

    if bin_number in _bin_lookup_cache:
        return _bin_lookup_cache[bin_number]

    session = await _get_bin_session()
    _t = aiohttp.ClientTimeout(total=8)

    async def _try_antipublic():
        async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}", timeout=_t) as res:
            if res.status == 200:
                data = await res.json(content_type=None)
                if isinstance(data, dict) and data.get('brand'):
                    return {
                        "brand":   data.get('brand', '-') or '-',
                        "type":    data.get('type', '-') or '-',
                        "level":   data.get('level', '-') or '-',
                        "bank":    data.get('bank', '-') or '-',
                        "country": data.get('country_name', '-') or '-',
                        "flag":    data.get('country_flag', '🏳️') or '🏳️',
                    }

    async def _try_hexunit():
        async with session.get(f"https://bin.hex-unit.com/{bin_number}", timeout=_t) as res:
            if res.status == 200:
                data = await res.json(content_type=None)
                if isinstance(data, dict) and data.get('brand'):
                    return {
                        "brand":   data.get('brand', '-') or '-',
                        "type":    data.get('type', '-') or '-',
                        "level":   data.get('level', '-') or '-',
                        "bank":    data.get('bank', '-') or '-',
                        "country": data.get('country_name', '-') or '-',
                        "flag":    data.get('country_flag', '🏳️') or '🏳️',
                    }

    async def _try_binlist():
        async with session.get(
            f"https://lookup.binlist.net/{bin_number}",
            headers={"Accept-Version": "3"}, timeout=_t
        ) as res:
            if res.status == 200:
                data = await res.json(content_type=None)
                if isinstance(data, dict):
                    return {
                        "brand":   (data.get('scheme') or '-').upper(),
                        "type":    (data.get('type') or '-').upper(),
                        "level":   (data.get('brand') or '-'),
                        "bank":    (data.get('bank') or {}).get('name', '-') or '-',
                        "country": (data.get('country') or {}).get('name', '-') or '-',
                        "flag":    (data.get('country') or {}).get('emoji', '🏳️') or '🏳️',
                    }

    tasks = [
        asyncio.create_task(_try_antipublic()),
        asyncio.create_task(_try_hexunit()),
        asyncio.create_task(_try_binlist()),
    ]
    try:
        pending = set(tasks)
        while pending:
            finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in finished:
                try:
                    r = t.result()
                    if r:
                        _bin_lookup_cache[bin_number] = r
                        return r
                except Exception:
                    pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    return _FALLBACK


# ══════════════════════════════════════════════════════════════════════════
#  PROXY CONCATENATION SPLITTER
# ══════════════════════════════════════════════════════════════════════════
_CONCAT_SPLIT_RE = re.compile(
    r'(:\d{2,5})'
    r'('
    r'[A-Za-z0-9._\-]+'
    r'(?::[^\s@]+)?'
    r'@'
    r')'
)

def split_concatenated_proxies(raw: str) -> list:
    out: list = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        fixed = _CONCAT_SPLIT_RE.sub(r'\1\n\2', line)
        for sub in fixed.splitlines():
            sub = sub.strip()
            if sub:
                out.append(sub)
    return out


# ══════════════════════════════════════════════════════════════════════════
#  PROXY FORMAT PARSER
# ══════════════════════════════════════════════════════════════════════════
def parse_proxy_format(proxy: str):
    proxy = (proxy or "").strip().strip("`'\"")
    if not proxy:
        return None

    proxy_type = 'http'

    m = re.match(r'^(socks5|socks4|http|https)://(.+)$', proxy, re.IGNORECASE)
    if m:
        proxy_type = m.group(1).lower()
        proxy = m.group(2)

    host = port = username = password = ''

    m = re.match(r'^([^@:]+):([^@]+)@([^:@]+):(\d+)$', proxy)
    if m:
        username, password, host, port = m.groups()
    elif re.match(r'^([a-zA-Z0-9.\-]+):(\d+)@([^:]+):(.+)$', proxy):
        m = re.match(r'^([a-zA-Z0-9.\-]+):(\d+)@([^:]+):(.+)$', proxy)
        host, port, username, password = m.groups()
    elif re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy):
        m = re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy)
        ph, pp, pu, pw = m.groups()
        try:
            if 0 < int(pp) <= 65535:
                host, port, username, password = ph, pp, pu, pw
        except ValueError:
            pass
    elif re.match(r'^([^:@]+):(\d+)$', proxy):
        m = re.match(r'^([^:@]+):(\d+)$', proxy)
        host, port = m.groups()
    elif '@' in proxy:
        at = proxy.rfind('@')
        auth = proxy[:at]
        hp = proxy[at+1:].split(':')
        if len(hp) >= 2:
            host, port = hp[0], hp[1]
            ap = auth.split(':', 1)
            if len(ap) == 2:
                username, password = ap
    else:
        return None

    if not host or not port:
        return None
    try:
        pn = int(port)
        if pn <= 0 or pn > 65535:
            return None
    except ValueError:
        return None

    if username and password:
        if proxy_type in ('socks5', 'socks4'):
            proxy_url = f'{proxy_type}://{username}:{password}@{host}:{port}'
        else:
            proxy_url = f'http://{username}:{password}@{host}:{port}'
    else:
        if proxy_type in ('socks5', 'socks4'):
            proxy_url = f'{proxy_type}://{host}:{port}'
        else:
            proxy_url = f'http://{host}:{port}'

    return {
        'ip': host, 'port': port,
        'username': username or None,
        'password': password or None,
        'proxy_url': proxy_url,
        'type': proxy_type,
    }


def proxy_dict_to_url(proxy_data) -> str | None:
    if not proxy_data:
        return None
    if isinstance(proxy_data, str):
        return proxy_data.strip() or None

    existing = proxy_data.get("proxy_url")
    if existing and isinstance(existing, str) and existing.strip():
        return existing.strip()

    ip    = str(proxy_data.get("ip") or "").strip()
    port  = str(proxy_data.get("port") or "").strip()
    user  = proxy_data.get("username")
    pw    = proxy_data.get("password")
    ptype = (proxy_data.get("type") or "http").lower()
    if not ip or not port:
        return None
    if ptype == "https":
        ptype = "http"
    from urllib.parse import quote
    if user and pw:
        auth = f"{quote(str(user), safe='')}:{quote(str(pw), safe='')}"
        return f"{ptype}://{auth}@{ip}:{port}"
    return f"{ptype}://{ip}:{port}"


def proxy_dict_to_requests(proxy_data) -> dict | None:
    url = proxy_dict_to_url(proxy_data)
    if not url:
        return None
    return {"http": url, "https": url}


# ══════════════════════════════════════════════════════════════════════════
#  PROXY TEST
# ══════════════════════════════════════════════════════════════════════════
async def test_proxy(proxy_url: str):
    try:
        session = await get_session()
        t = aiohttp.ClientTimeout(total=15)
        async with session.get('http://api.ipify.org?format=json', proxy=proxy_url, timeout=t) as res:
            if res.status != 200:
                return False, f"HTTP {res.status}", None
            data = await res.json()
            ip1 = data.get('ip', 'Unknown')
        try:
            async with session.get('http://api.ipify.org?format=json', proxy=proxy_url, timeout=t) as res2:
                if res2.status == 200:
                    data2 = await res2.json()
                    ip2 = data2.get('ip', 'Unknown')
                    rotation = 'Rotating' if ip1 != ip2 else 'Static'
                else:
                    rotation = 'Static'
        except Exception:
            rotation = 'Static'
        return True, ip1, rotation
    except Exception as e:
        return False, str(e), None


# ══════════════════════════════════════════════════════════════════════════
#  CC REGEX EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════
CC_PATTERN = re.compile(
    r'(\d{15,16})\s*[|/]\s*(\d{1,2})\s*[|/]\s*(\d{2,4})\s*[|/]\s*(\d{3,4})'
)

def extract_cc(text: str) -> str | None:
    m = CC_PATTERN.search(text or "")
    if m:
        return f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
    return None


# ══════════════════════════════════════════════════════════════════════════
#  GATE RESPONSE CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════
_GATE_ERROR_CODES = frozenset({
    "proxy_error", "connection_error", "timeout", "captcha_required", "cart_fail",
    "bt_token_fail", "upstream_5xx", "exception", "bad_json", "empty", "failed",
})

_GATE_CHARGED_SIGNALS = (
    "charged", "payment success", "payment successful", "payment complete",
    "payment completed", "order success", "order successful", "order completed",
    "order placed", "order_placed", "order received", "order confirmed",
    "processedreceipt", "successfulreceipt", "thank you for your order",
    "thank you", "transaction successful", "successfully charged",
    "captured", "authorized", "woocommerce_order",
    '"success":true', '"success": true', '"result":"success"',
    'result":"success"', "checkout success", "payment_id", "order_id",
    "razorpay_payment_id",
)

_GATE_CCN_SIGNALS = (
    "incorrect cvv", "incorrect cvc", "invalid cvv", "invalid cvc",
    "invalid security", "security code", "card security code",
    "cvv mismatch", "cvc mismatch", "wrong cvv", "wrong cvc", "ccn",
    "incorrect_cvc", "invalid_cvc", "verification number",
)

_GATE_LIMIT_SIGNALS = (
    "insufficient", "insufficient funds", "not enough fund", "balance",
    "limit exceeded", "maximum transaction", "over limit", "exceeds limit",
    "account balance",
)

_GATE_3DS_SIGNALS = (
    "3ds", "3d secure", "requires_action", "authentication required",
    "challenge_required", "challenge required", "otp", "verify your card",
)

_GATE_DECLINED_SIGNALS = (
    "declined", "rejected", "denied", "do not honour", "pick up",
    "lost card", "stolen", "expired card", "fraud", "not permitted",
    "restricted card",
)


def classify_gate_response(text: str = "", status_hint: str = "", code_hint: str = ""):
    raw_msg = (text or "").strip()
    if len(raw_msg) > 300:
        raw_msg = raw_msg[:300]
    low = f"{raw_msg} {status_hint} {code_hint}".lower()
    out_msg = raw_msg[:120] if raw_msg else (code_hint or status_hint or "")[:120]

    cd = (code_hint or "").lower()
    st = (status_hint or "").lower()

    if cd in _GATE_ERROR_CODES or st == "error":
        return "error", out_msg, cd or "error"

    if any(k in low for k in ("proxy dead", "proxy error", "tunnel",
                              "connection refused", "connection error")):
        return "error", out_msg, "proxy_error"
    if "timed out" in low or ("timeout" in low and "challenge" not in low):
        return "error", out_msg, "timeout"

    if st == "charged" or cd == "charged":
        return "charged", out_msg or "Charged", "charged"

    if any(sig in low for sig in _GATE_CHARGED_SIGNALS):
        if not any(x in low for x in ("declined", "rejected", "failed",
                                       "unsuccessful", "not success", "was not")):
            return "charged", out_msg or "Payment / order success", "charged"

    if cd in ("ccn", "cvv_approved") or any(sig in low for sig in _GATE_CCN_SIGNALS):
        return "approved", out_msg or "CCN / CVV", "ccn"

    if cd in ("live_limit",) or any(sig in low for sig in _GATE_LIMIT_SIGNALS):
        return "approved", out_msg or "Insufficient / limit", "live_limit"

    if cd in ("3ds", "3ds_required", "challenge_3d", "3ds_or_otp") or any(sig in low for sig in _GATE_3DS_SIGNALS):
        if "passed" not in low and "authenticate_successful" not in low:
            return "approved", out_msg or "3DS / OTP", "3ds"

    if st == "approved" or cd == "approved":
        return "approved", out_msg or "Approved", "approved"

    if cd == "declined" or st == "declined" or any(sig in low for sig in _GATE_DECLINED_SIGNALS):
        return "declined", out_msg or "Declined", "declined"

    if "success" in low and any(k in low for k in ("payment", "order", "checkout", "complete", "approved")):
        return "charged", out_msg or "Success", "charged"

    return "declined", out_msg or "declined", "declined"


def gate_is_charged(status: str, code: str, msg: str = "") -> bool:
    st, _, _ = classify_gate_response(msg, status_hint=status, code_hint=code)
    return st == "charged"

def gate_is_approved(status: str, code: str, msg: str = "") -> bool:
    st, _, _ = classify_gate_response(msg, status_hint=status, code_hint=code)
    return st == "approved"


# ══════════════════════════════════════════════════════════════════════════
#  NOPECHA hCaptcha SOLVER (optional — fail-open)
# ══════════════════════════════════════════════════════════════════════════
_NOPECHA_KEY = (os.environ.get('NOPECHA_API_KEY') or '').strip()

def nopecha_enabled() -> bool:
    return bool(_NOPECHA_KEY)

async def solve_hcaptcha(sitekey: str, page_url: str, timeout_s: int = 30) -> str | None:
    """
    Try to solve an hCaptcha via NopeCHA. Returns solution token or None.
    Fail-open — never raises, never blocks for longer than timeout_s.
    """
    if not _NOPECHA_KEY:
        return None
    if not sitekey or not page_url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(
                "https://api.nopecha.com/token",
                json={
                    "key": _NOPECHA_KEY,
                    "type": "hcaptcha",
                    "sitekey": sitekey,
                    "url": page_url,
                },
            ) as r:
                if r.status != 200:
                    return None
                j = await r.json()
                data = j.get('data')
                if not data:
                    return None
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                await asyncio.sleep(3)
                async with s.get(
                    "https://api.nopecha.com/token",
                    params={"key": _NOPECHA_KEY, "id": data},
                ) as r2:
                    if r2.status != 200:
                        continue
                    j2 = await r2.json()
                    if 'data' in j2 and j2['data']:
                        return j2['data']
                    err = j2.get('error')
                    if err and err not in (14,):
                        return None
    except Exception:
        return None
    return None