from fastapi import FastAPI, BackgroundTasks, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import requests
import random
import math
import time
import os
import numpy as np
import hashlib
import hmac
import json
import base64
import hashlib
import secrets

# ==========================================
# NGARKIMI I MODELEVE XGBOOST (HYBRID)
# ==========================================
# Modelet trajnohen JASHTË (Colab) dhe vendosen në repo si .json.
# Nëse mungojnë ose dështojnë → fallback te formula matematikore.
XGB_MODEL_HOME = None
XGB_MODEL_AWAY = None
XGB_GATI = False
XGB_MODEL_HOME_HT = None
XGB_MODEL_AWAY_HT = None
XGB_HT_GATI = False

# Rendi EKZAKT i features siç u trajnua modeli (mos e ndrysho!)
XGB_FEATURES = [
    "home_forma_pts", "away_forma_pts",
    "home_avg_scored", "away_avg_scored",
    "home_avg_conceded", "away_avg_conceded",
    "home_avg_scored_home", "home_avg_conceded_home",
    "away_avg_scored_away", "away_avg_conceded_away",
    "home_avg_yellow", "away_avg_yellow",
    "home_avg_red", "away_avg_red",
    "home_attack_strength", "away_attack_strength",
    "home_defense_strength", "away_defense_strength",
    "home_volatility", "away_volatility",
    "home_rest_days", "away_rest_days",
    "odd_home", "odd_draw", "odd_away",
    "tipi_ndeshjes",
    "ah_line", "ah_home_odd", "ah_away_odd",
    "ou25_over", "ou25_under",
]

# Vlera mesatare (nga trajnimi) për features që s'i kemi live.
# Përdoren si imputation — kishin rëndësi të ulët, efekt minimal.
XGB_DEFAULTS = {
    "home_avg_yellow": 1.75, "away_avg_yellow": 1.75,
    "home_avg_red": 0.10, "away_avg_red": 0.10,
    "home_volatility": 1.47, "away_volatility": 1.47,
    "home_rest_days": 7.0, "away_rest_days": 7.0,
    "ah_line": 0.0, "ah_home_odd": 1.90, "ah_away_odd": 1.90,
    "ou25_over": 1.90, "ou25_under": 1.90,
}

def _ngarko_modelet_xgb():
    """Ngarkon modelet XGBoost një herë në nisje. Fail-safe."""
    global XGB_MODEL_HOME, XGB_MODEL_AWAY, XGB_GATI, XGB_MODEL_HOME_HT, XGB_MODEL_AWAY_HT, XGB_HT_GATI
    try:
        import xgboost as xgb
        rruga_home = os.path.join(os.path.dirname(__file__), "model_gola_home.json")
        rruga_away = os.path.join(os.path.dirname(__file__), "model_gola_away.json")
        if os.path.exists(rruga_home) and os.path.exists(rruga_away):
            XGB_MODEL_HOME = xgb.XGBRegressor()
            XGB_MODEL_HOME.load_model(rruga_home)
            XGB_MODEL_AWAY = xgb.XGBRegressor()
            XGB_MODEL_AWAY.load_model(rruga_away)
            XGB_GATI = True
            print("✅ Modelet XGBoost u ngarkuan — Hybrid AKTIV.")
        else:
            print("⚠️ Modelet XGBoost nuk u gjetën — përdoret vetëm formula matematikore.")
        # Modelet HT (gjysmë-fushë) — për tregun HT/FT
        rruga_home_ht = os.path.join(os.path.dirname(__file__), "model_gola_home_ht.json")
        rruga_away_ht = os.path.join(os.path.dirname(__file__), "model_gola_away_ht.json")
        if os.path.exists(rruga_home_ht) and os.path.exists(rruga_away_ht):
            XGB_MODEL_HOME_HT = xgb.XGBRegressor()
            XGB_MODEL_HOME_HT.load_model(rruga_home_ht)
            XGB_MODEL_AWAY_HT = xgb.XGBRegressor()
            XGB_MODEL_AWAY_HT.load_model(rruga_away_ht)
            XGB_HT_GATI = True
            print("✅ Modelet HT u ngarkuan — HT/FT AKTIV.")
        else:
            print("⚠️ Modelet HT nuk u gjetën — HT/FT joaktiv.")
    except Exception as e:
        print(f"⚠️ XGBoost nuk u ngarkua ({e}) — fallback te formula.")
        XGB_GATI = False

_ngarko_modelet_xgb()

app = FastAPI(title="SOCCER1X2 PRO API - Expert System", description="Advanced Monte Carlo & Dynamic ELO Prediction Engine V2")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://(www\.)?soccer1x2pro\.com$|^https://([a-z0-9-]+\.)?rapidapi\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# RATE LIMITING — mbrojtje nga skrapimi automatik (bot/kopjues)
# Per-IP, dritare rreshkitese (60s + 3600s). Fail-open: kurre s'bllokon per gabim.
# Env: RATE_LIMIT_PER_MIN (default 120), RATE_LIMIT_PER_HOUR (default 2000).
# ============================================================
from collections import deque as _deque
import threading as _threading
from fastapi.responses import JSONResponse as _JSONResponse

_RL_LOCK = _threading.Lock()
_RL_MIN = {}    # ip -> deque[timestamp] (dritarja 60s)
_RL_HOUR = {}   # ip -> deque[timestamp] (dritarja 3600s)
try:
    RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "120").strip())
except Exception:
    RATE_LIMIT_PER_MIN = 120
try:
    RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "2000").strip())
except Exception:
    RATE_LIMIT_PER_HOUR = 2000
WATERMARK_ON = os.environ.get("WATERMARK_ON", "true").strip().lower() not in ("0", "false", "off", "no")

# Rruget e perjashtuara: RapidAPI (ka limitet e veta + IP e perbashket proxy),
# cron (frekuence e ulet), webhook (pagesa - kurre mos blloko), admin (i mbrojtur me sekret).
_RL_EXEMPT = ("/v1/", "/api/cron/", "/api/cryptomus/", "/api/admin/", "/api/social/")

def _rl_ip(request):
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    try:
        path = request.url.path
        if request.method == "OPTIONS" or path == "/" or any(path.startswith(p) for p in _RL_EXEMPT):
            return await call_next(request)
        ip = _rl_ip(request)
        now = time.time()
        bllokuar = False
        with _RL_LOCK:
            dq = _RL_MIN.setdefault(ip, _deque())
            dh = _RL_HOUR.setdefault(ip, _deque())
            while dq and now - dq[0] > 60:
                dq.popleft()
            while dh and now - dh[0] > 3600:
                dh.popleft()
            if len(dq) >= RATE_LIMIT_PER_MIN or len(dh) >= RATE_LIMIT_PER_HOUR:
                bllokuar = True
            else:
                dq.append(now); dh.append(now)
            # Pastrim periodik i IP-ve te vjetra (mbron memorjen)
            if len(_RL_MIN) > 5000:
                for k in list(_RL_MIN.keys()):
                    if not _RL_MIN.get(k) or now - _RL_MIN[k][-1] > 3600:
                        _RL_MIN.pop(k, None); _RL_HOUR.pop(k, None)
        if bllokuar:
            return _JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Ju lutem ngadalësoni dhe provoni pas pak."},
                headers={"Retry-After": "60"})
        return await call_next(request)
    except Exception:
        # Fail-open: nese middleware deshton per çfardo arsye, LEJO kerkesen (mos blloko trafik legjitim)
        return await call_next(request)

# KREDENCIALET (nga env vars — Render → Environment)
API_KEY = os.environ.get("API_SPORTS_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_CRON_KEY = os.environ.get("TELEGRAM_CRON_KEY", "").strip()
HEADERS = {"x-apisports-key": API_KEY}
_ngjyra_live_cache = {}

def _api_sports_get(endpoint, params=None, retries=3, timeout=10):
    """Thirrje E QËNDRUESHME te API-Football me retry + backoff eksponencial.
    Kthen JSON (dict) ose None nëse të gjitha përpjekjet dështojnë.
    Trajtimi i rate-limit (429) dhe gabimeve të serverit (5xx) me ri-provë.
    endpoint: p.sh. 'fixtures', 'odds', 'fixtures/statistics'."""
    import time as _t
    url = f"https://v3.football.api-sports.io/{endpoint}"
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                errs = data.get("errors")
                # rate-limit i raportuar brenda 200 → ri-provë me backoff
                if errs and isinstance(errs, dict) and any(
                    ("limit" in str(v).lower() or "rate" in str(v).lower()) for v in errs.values()):
                    last = errs
                    _t.sleep(1.5 * (attempt + 1))
                    continue
                return data
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                _t.sleep(1.5 * (attempt + 1))
                continue
            last = f"HTTP {r.status_code}"
            return None
        except Exception as e:
            last = e
            _t.sleep(1.0 * (attempt + 1))
    print(f"[API-SPORTS] Dështoi '{endpoint}' pas {retries} përpjekjesh: {last}")
    return None

SUPABASE_BASE = os.environ.get(
    "SUPABASE_URL", "https://oqfhlyybwwkjbkvfpsxi.supabase.co"
).strip().rstrip("/")

SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
# Service key për shkrime të privilegjuara (auth/admin/Cryptomus/Modulator):
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

SUPABASE_URL_PREDS = f"{SUPABASE_BASE}/rest/v1/predictions"
SUPABASE_URL_TRAINING = f"{SUPABASE_BASE}/rest/v1/training_results"
SUPABASE_URL_USERS = f"{SUPABASE_BASE}/rest/v1/users"
SUPABASE_URL_DNA   = f"{SUPABASE_BASE}/rest/v1/team_dna_cache"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

_mungojne_env = [k for k, v in {
    "API_SPORTS_KEY": API_KEY,
    "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
}.items() if not v]
if _mungojne_env:
    print(f"⚠️ KUJDES: env vars mungojnë → {_mungojne_env}. Vendosi te Render → Environment.")
else:
    print("✅ Kredencialet u lexuan nga env vars.")


LIGAT_VIP_MAP = {
    39: "England - Premier League", 140: "Spain - La Liga", 135: "Italy - Serie A",
    78: "Germany - Bundesliga", 61: "France - Ligue 1", 2: "Champions League",
    3: "Europa League", 848: "Europa Conference League", 1: "World Cup",
    4: "Euro Championship", 9: "Copa America", 5: "UEFA Nations League",
    40: "England - Championship", 136: "Italy - Serie B", 141: "Spain - Segunda Division",
    79: "Germany - 2. Bundesliga", 62: "France - Ligue 2", 71: "Brazil - Serie A",
    103: "Argentina - Liga Profesional", 88: "Netherlands - Eredivisie",
    94: "Portugal - Primeira Liga", 203: "Turkey - Super Lig", 144: "Belgium - Pro League",
    197: "Greece - Super League", 179: "Scotland - Premiership", 207: "Switzerland - Super League",
    119: "Denmark - Superliga", 218: "Austria - Bundesliga", 311: "Albania - Superliga"
}

LIGAT_VIP = list(LIGAT_VIP_MAP.values())

def is_vip_league(emri_liges):
    for vip in LIGAT_VIP:
        parts = vip.split(" - ")
        if len(parts) == 2:
            if parts[0].lower() in emri_liges.lower() and parts[1].lower() in emri_liges.lower():
                return True
        else:
            if vip.lower() in emri_liges.lower():
                return True
    return False

# ==========================================
# MODULI USER / AUTH
# ==========================================
class LoginData(BaseModel):
    email: str
    password: str
    name: str = ""

class GoogleLoginInput(BaseModel):
    access_token: str = ""

class ForgotInput(BaseModel):
    email: str = ""

class ResetInput(BaseModel):
    token: str = ""
    password: str = ""

# ── SIGURIA: helpers për hashim + service headers + admin ──
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()

# ── EMAIL (Resend) ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "SOCCER1X2 PRO <noreply@soccer1x2pro.com>")
SITE_URL = os.environ.get("SITE_URL", "https://soccer1x2pro.com").strip()

def _dergo_email(to_email, subject, html):
    """Dergon nje email permes Resend. Kthen (ok, mesazh)."""
    if not RESEND_API_KEY:
        return False, "Email service jo i konfiguruar."
    try:
        r = requests.post("https://api.resend.com/emails",
                          headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                                   "Content-Type": "application/json"},
                          json={"from": EMAIL_FROM, "to": [to_email],
                                "subject": subject, "html": html}, timeout=10)
        if r.status_code in (200, 201):
            return True, "OK"
        return False, f"Resend {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)

SUPABASE_SERVICE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def _eshte_hash(s):
    # Formati ynë: pbkdf2$<iterations>$<salt_hex>$<hash_hex>
    return isinstance(s, str) and s.startswith("pbkdf2$")

# ================== AUTENTIKIM ME TOKEN (JWT vetjak, HMAC-SHA256) ==================
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip()
TOKEN_TTL = 30 * 24 * 3600  # 30 ditë
AUTH_STRICT = True   # Faza 1: backward-compatible (s'bllokon). Vëre True (Faza 2) -> mbyll IDOR.

def _b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def _b64u_dec(x):
    return base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))

def _krijo_token(email):
    """Token i nënshkruar: base64(payload).signature (HMAC-SHA256 me JWT_SECRET)."""
    email = (email or "").lower().strip()
    if not JWT_SECRET or not email:
        return ""
    payload = _b64u(json.dumps({"email": email, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = _b64u(hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + sig

def _verifiko_token(auth_header):
    """Kthen email nga token-i i vlefshëm (nënshkrim + skadencë OK), ndryshe None."""
    if not JWT_SECRET or not auth_header:
        return None
    try:
        tok = auth_header.split(" ", 1)[1].strip() if " " in auth_header else auth_header.strip()
        payload_b64, sig = tok.split(".", 1)
        pritur = _b64u(hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, pritur):
            return None
        data = json.loads(_b64u_dec(payload_b64))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return (data.get("email") or "").lower().strip()
    except Exception:
        return None

def _email_auth(authorization, fallback="", strict=None):
    """Email i VËRTETUAR nga token-i. Faza 1: bie te 'fallback' (payload) nëse s'ka token.
    Faza 2 (AUTH_STRICT=True): kërkon token të vlefshëm, ndryshe 401."""
    em = _verifiko_token(authorization)
    if em:
        return em
    _strict = AUTH_STRICT if strict is None else strict
    if _strict and JWT_SECRET:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    return (fallback or "").lower().strip()
# ===================================================================================


# ============================================================
# WATERMARK I PADUKSHEM — gjurmim per-perdorues (VIP/akses i plote)
# Fut nje sekuence zero-width (te padukshme) ne tekstin e analizes, qe kodon
# nje identitet determinist te perdoruesit (HMAC me JWT_SECRET). NUK prek vlerat
# e parashikimit (skor/koef). Aplikohet ne SHERBIM (jo gjenerim) => per-perdorues.
# ============================================================
_ZW0 = "\u200b"    # zero-width space  -> bit 0
_ZW1 = "\u200c"    # zero-width non-joiner -> bit 1
_ZWM = "\u2060"    # word joiner -> kufizues (fillim/fund i shenjes)

def _wm_code(email):
    """Kod determinist 3-byte (hex) per email — HMAC-SHA256 me JWT_SECRET."""
    if not email or not JWT_SECRET:
        return None
    h = hmac.new(JWT_SECRET.encode("utf-8"), str(email).lower().strip().encode("utf-8"), hashlib.sha256).digest()
    return h[:3]  # 24 bit — mjafton per te dalluar perdoruesit

def _wm_encode(email):
    """Sekuenca zero-width qe kodon kodin e perdoruesit (ose '' nese s'ka)."""
    code = _wm_code(email)
    if not code:
        return ""
    bits = "".join("{:08b}".format(b) for b in code)  # 24 bit
    return _ZWM + "".join(_ZW1 if b == "1" else _ZW0 for b in bits) + _ZWM

def _wm_inject_raw(text, mark):
    """Fut shenjen e para-llogaritur pas fjalise se pare (ose ne fund)."""
    if not text or not isinstance(text, str) or not mark:
        return text
    idx = text.find(". ")
    return (text[:idx+1] + mark + text[idx+1:]) if idx != -1 else (text + mark)

def _wm_extract(text):
    """Nxjerr kodin (hex) nga tekst i watermark-uar, ose None."""
    if not text or _ZWM not in text:
        return None
    try:
        for seg in text.split(_ZWM):
            zw = [c for c in seg if c in (_ZW0, _ZW1)]
            if len(zw) == 24:
                bits = "".join("1" if c == _ZW1 else "0" for c in zw)
                return bytes(int(bits[i:i+8], 2) for i in range(0, 24, 8)).hex()
    except Exception:
        pass
    return None

def _wm_apply(grouped, email):
    """Injekton watermark-un ne analiza_custom per perdoruesin — NDERTON KOPJE (s'prek cache)."""
    try:
        mark = _wm_encode(email)
        if not mark:
            return grouped
        out = []
        for liga in grouped:
            lc = dict(liga); nds = []
            for nd in (liga.get("ndeshjet") or []):
                ac = nd.get("analiza_custom") if isinstance(nd, dict) else None
                if isinstance(ac, dict):
                    ndc = dict(nd)
                    ndc["analiza_custom"] = {k: (_wm_inject_raw(v, mark) if isinstance(v, str) else v)
                                             for k, v in ac.items()}
                    nds.append(ndc)
                else:
                    nds.append(nd)
            lc["ndeshjet"] = nds
            out.append(lc)
        return out
    except Exception:
        return grouped


def _hash_fjalekalimi(pw):
    import os as _os
    salt = _os.urandom(16)
    iteracionet = 200000
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iteracionet)
    return f"pbkdf2${iteracionet}${salt.hex()}${dk.hex()}"

def _verifiko_fjalekalimi(pw, ruajtur):
    try:
        if _eshte_hash(ruajtur):
            _, iter_str, salt_hex, hash_hex = ruajtur.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iter_str))
            return hmac.compare_digest(dk.hex(), hash_hex)
        return pw == ruajtur   # plaintext i vjetër (do migrohet automatikisht)
    except Exception:
        return False

def _hiq_passwordin(rows):
    for r in (rows or []):
        if isinstance(r, dict):
            r.pop("password", None)
    return rows


@app.post("/api/register")
def regjistro_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code == 200 and len(res.json()) > 0:
        return {"sukses": False, "kod": "EMAIL_EXISTS", "mesazhi": "ekziston"}
    emri_ndare = data.name.strip().split(" ", 1)
    emri    = emri_ndare[0] if len(emri_ndare) > 0 else "Client"
    mbiemri = emri_ndare[1] if len(emri_ndare) > 1 else ""
    user_payload = {
        "email": email_clean,
        "password": _hash_fjalekalimi(data.password),   # HASH, jo plaintext
        "emri": emri, "mbiemri": mbiemri,
        "portofoli": 10.0, "isVip": False, "vip_skadon_me": None,
        "auto_rinovim": False, "blerjet": []
    }
    res_insert = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_SERVICE_HEADERS, json=user_payload)
    if res_insert.status_code in [200, 201, 204]:
        u = dict(user_payload); u.pop("password", None)
        return {"sukses": True, "perdoruesi": u, "token": _krijo_token(u.get("email", ""))}
    return {"sukses": False, "mesazhi": f"Gabim Databaze: {res_insert.text}"}


@app.post("/api/login")
def login_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code != 200:
        return {"sukses": False, "kod": "LOGIN_FAILED", "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    users = res.json()
    if not users:
        return {"sukses": False, "kod": "LOGIN_FAILED", "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    u = users[0]
    ruajtur = u.get("password", "")
    if not _verifiko_fjalekalimi(data.password, ruajtur):
        return {"sukses": False, "kod": "LOGIN_FAILED", "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    # MIGRIM: nëse ishte plaintext, hashoje tani (pa fërkim)
    if not _eshte_hash(ruajtur):
        try:
            requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"password": _hash_fjalekalimi(data.password)})
        except Exception:
            pass
    u.pop("password", None)
    return {"sukses": True, "perdoruesi": u, "token": _krijo_token(u.get("email", ""))}


@app.post("/api/google-login")
def google_login(data: GoogleLoginInput):
    """Hyrje me Google: verifikon access_token-in me Google userinfo, gjen/krijon perdoruesin."""
    tok = (data.access_token or "").strip()
    if not tok:
        return {"sukses": False, "kod": "TOKEN_MISSING", "mesazhi": "Token mungon."}
    try:
        r = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=8)
    except Exception:
        return {"sukses": False, "kod": "GOOGLE_VERIFY_ERR", "mesazhi": "Gabim verifikimi me Google."}
    if r.status_code != 200:
        return {"sukses": False, "kod": "TOKEN_INVALID", "mesazhi": "Token i pavlefshem."}
    info = r.json()
    email_clean = (info.get("email") or "").lower().strip()
    if not email_clean:
        return {"sukses": False, "kod": "GOOGLE_NO_EMAIL", "mesazhi": "Email mungon nga Google."}
    if str(info.get("email_verified", "")).lower() not in ("true", "1"):
        return {"sukses": False, "kod": "EMAIL_UNVERIFIED", "mesazhi": "Email i paverifikuar."}
    emri = info.get("given_name") or (info.get("name") or email_clean.split("@")[0])
    mbiemri = info.get("family_name") or ""
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code == 200 and res.json():
        u = res.json()[0]
        u.pop("password", None)
        return {"sukses": True, "perdoruesi": u, "token": _krijo_token(u.get("email", ""))}
    # Perdorues i ri (password i rastesishem; hyn vetem me Google derisa te beje reset)
    user_payload = {
        "email": email_clean,
        "password": _hash_fjalekalimi(os.urandom(24).hex()),
        "emri": emri, "mbiemri": mbiemri,
        "portofoli": 10.0, "isVip": False, "vip_skadon_me": None,
        "auto_rinovim": False, "blerjet": []
    }
    ins = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_SERVICE_HEADERS, json=user_payload)
    if ins.status_code in (200, 201, 204):
        u = dict(user_payload); u.pop("password", None)
        return {"sukses": True, "perdoruesi": u, "token": _krijo_token(u.get("email", ""))}
    return {"sukses": False, "kod": "DB_ERROR", "mesazhi": "Gabim databaze."}


@app.post("/api/forgot-password")
def forgot_password(data: ForgotInput):
    """Gjeneron token reset-i dhe dergon link me email. Kthen gjithmone sukses (privatesi)."""
    email_clean = (data.email or "").lower().strip()
    ok = {"sukses": True, "kod": "RESET_SENT", "mesazhi": "Nese email-i ekziston, do marresh nje link."}
    if not email_clean:
        return ok
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code != 200 or not res.json():
        return ok  # mos zbulo qe email-i nuk ekziston
    token = os.urandom(32).hex()
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    try:
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS,
                       json={"reset_token": token, "reset_expires": expires})
    except Exception:
        return ok
    link = f"{SITE_URL}/?reset={token}"
    html = (
        '<div style="background:#0a162e;padding:30px;font-family:Arial,sans-serif;">'
        '<div style="max-width:480px;margin:0 auto;background:#0d1b33;border:1px solid rgba(212,175,55,0.3);border-radius:12px;padding:28px;">'
        '<h2 style="color:#d4af37;text-align:center;margin:0 0 16px;">SOCCER1X2 PRO</h2>'
        '<p style="color:#c9d1d9;font-size:14px;line-height:1.6;">Kerkove te rivendosesh fjalekalimin. Kliko butonin me poshte (vlen per 1 ore):</p>'
        '<div style="text-align:center;margin:24px 0;">'
        f'<a href="{link}" style="background:#d4af37;color:#0a162e;text-decoration:none;padding:13px 26px;border-radius:8px;font-weight:bold;display:inline-block;">Rivendos fjalekalimin</a>'
        '</div>'
        '<p style="color:#8ba898;font-size:12px;line-height:1.5;">Nese nuk e kerkove ti, injoroje kete email. Linku skadon per 1 ore.</p>'
        f'<p style="color:#5a6b7a;font-size:11px;word-break:break-all;">{link}</p>'
        '</div></div>'
    )
    _dergo_email(email_clean, "Rivendos fjalekalimin — SOCCER1X2 PRO", html)
    return ok


@app.post("/api/reset-password")
def reset_password(data: ResetInput):
    """Verifikon token-in (jo te skaduar) dhe vendos fjalekalimin e ri."""
    token = (data.token or "").strip()
    pw = data.password or ""
    if not token or len(pw) < 6:
        return {"sukses": False, "kod": "PW_TOO_SHORT", "mesazhi": "Te dhena te pavlefshme (fjalekalimi min 6 karaktere)."}
    res = requests.get(f"{SUPABASE_URL_USERS}?reset_token=eq.{token}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code != 200 or not res.json():
        return {"sukses": False, "kod": "RESET_INVALID", "mesazhi": "Link i pavlefshem ose i skaduar."}
    u = res.json()[0]
    expires = u.get("reset_expires")
    try:
        if expires:
            exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                return {"sukses": False, "kod": "RESET_EXPIRED", "mesazhi": "Link i skaduar. Kerko nje te ri."}
    except Exception:
        pass
    email_clean = u.get("email")
    upd = requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS,
                         json={"password": _hash_fjalekalimi(pw), "reset_token": None, "reset_expires": None})
    if upd.status_code in (200, 201, 204):
        return {"sukses": True, "kod": "PW_RESET_OK", "mesazhi": "Fjalekalimi u rivendos! Tani mund te hysh."}
    return {"sukses": False, "kod": "DB_ERROR", "mesazhi": "Gabim databaze."}


@app.post("/api/update_user")
def perditeso_perdorues(user_data: dict):
    # I MBYLLUR: fushat monetare (isVip/portofoli/blerjet/vip_skadon_me) ndryshohen
    # VETËM nga endpoint-et server-autoritare (ppm/vip/cryptomus webhook).
    # Klienti lejohet të ndryshojë vetëm profilin jo-monetar.
    email = user_data.get("email", "").lower().strip()
    if not email:
        return {"sukses": False, "kod": "EMAIL_MISSING", "mesazhi": "email mungon"}
    LEJUARA = {"emri", "mbiemri", "auto_rinovim"}
    payload = {k: v for k, v in user_data.items() if k in LEJUARA}
    if payload:
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                       headers=SUPABASE_SERVICE_HEADERS, json=payload)
    return {"sukses": True}


@app.get("/api/users")
def merr_perdorues_nga_db(email: str, authorization: str = Header(None)):
    email = _email_auth(authorization, email)
    try:
        res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}",
                           headers=SUPABASE_SERVICE_HEADERS)
        if res.status_code == 200:
            return _hiq_passwordin(res.json())
        return []
    except Exception:
        return []


# ── ADMIN (i mbrojtur me ADMIN_TOKEN) ──
def _kontrollo_admin(token):
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="I paautorizuar")

@app.post("/api/admin/add_credits")
def admin_shto_kredite(payload: dict, x_admin_token: str = Header(None)):
    _kontrollo_admin(x_admin_token)
    email = payload.get("email", "").lower().strip()
    try:
        shuma = float(payload.get("shuma", 0))
    except Exception:
        return {"sukses": False, "kod": "AMOUNT_INVALID", "mesazhi": "shuma e pavlefshme"}
    if not email or shuma == 0:
        return {"sukses": False, "kod": "EMAIL_OR_AMOUNT_MISSING", "mesazhi": "email ose shuma mungon"}
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli",
                       headers=SUPABASE_SERVICE_HEADERS)
    rows = res.json() if res.status_code == 200 else []
    if not rows:
        return {"sukses": False, "kod": "USER_NOT_FOUND", "mesazhi": "perdoruesi s'u gjet"}
    e_re = round(float(rows[0].get("portofoli", 0) or 0) + shuma, 2)
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                   headers=SUPABASE_SERVICE_HEADERS, json={"portofoli": e_re})
    return {"sukses": True, "email": email, "portofoli": e_re}

@app.post("/api/admin/set_vip")
def admin_set_vip(payload: dict, x_admin_token: str = Header(None)):
    _kontrollo_admin(x_admin_token)
    email = payload.get("email", "").lower().strip()
    try:
        dite = int(payload.get("dite", 30))
    except Exception:
        dite = 30
    if not email:
        return {"sukses": False, "kod": "EMAIL_MISSING", "mesazhi": "email mungon"}
    skadon = _data_lokale(dite)
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                   headers=SUPABASE_SERVICE_HEADERS,
                   json={"isVip": True, "vip_skadon_me": skadon})
    return {"sukses": True, "email": email, "vip_skadon_me": skadon}


# ==========================================
# MODULI I PAGESAVE — PPM (kredite) + CRYPTOMUS (server-autoritar)
# Çmimet në USD (TEST — ndryshohen lehtë këtu).
# ==========================================
CMIMI_VIP = 69.99
VIP_DITE  = 30
PPM_TIER1 = 20.0    # çmim FIKS $20 për ndeshje
PPM_TIER2 = 20.0
PPM_TIER3 = 20.0
CMIMI_DITORE = 10.0   # zhbllokon Skedinën + Kombinimin e Ditës
CMIMI_TRIAL  = 4.90   # provë 1-javore me pagesë (jo falas — bllokon llogari fallso)
TRIAL_DITE   = 7

# -- ARGETOHU (Gemini): kuote motivuese + kuiz trivie --
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

CRYPTOMUS_MERCHANT_ID = os.environ.get("CRYPTOMUS_MERCHANT_ID", "").strip()
CRYPTOMUS_PAYMENT_KEY = os.environ.get("CRYPTOMUS_PAYMENT_KEY", "").strip()
PUBLIC_API_URL  = os.environ.get("PUBLIC_API_URL", "https://soccer1x2-api.onrender.com").rstrip("/")
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://soccer1x2pro.com").rstrip("/")
SUPABASE_URL_POROSITE = f"{SUPABASE_BASE}/rest/v1/porosite"

# ── PAYPAL (paralel me Cryptomus; ripERdor _kredito_porosine, tabela e njEjtE me prefiks pp_) ──
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_SECRET    = os.environ.get("PAYPAL_SECRET", "").strip()
PAYPAL_BASE      = os.environ.get("PAYPAL_BASE", "https://api-m.paypal.com").rstrip("/")  # sandbox: https://api-m.sandbox.paypal.com


def _data_lokale(offset_ditesh=0):
    """Data lokale e Shqiperise (Europe/Tirane) + offset ditesh.
       Filtra date duhet te perputhen me oren LOKALE te ndeshjeve, jo UTC.
       Fallback ne UTC+2 nese mungon tzdata."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Tirane"))
    except Exception:
        now = datetime.utcnow() + timedelta(hours=2)
    return (now + timedelta(days=offset_ditesh)).strftime("%Y-%m-%d")


def _cmimi_ppm(koef):
    try:
        k = float(koef)
    except Exception:
        k = 0.0
    if k >= 8.0:
        return PPM_TIER3
    if k >= 5.0:
        return PPM_TIER2
    return PPM_TIER1


# ── PPM me KREDITE (serveri zbret; klienti s'e bën më vetë) ──
@app.post("/api/ppm/purchase")
def ppm_blej_me_kredite(payload: dict, authorization: str = Header(None)):
    email = _email_auth(authorization, payload.get("email", ""))
    match_id = payload.get("match_id")
    if not email or not match_id:
        return {"sukses": False, "kod": "DATA_MISSING", "mesazhi": "Të dhëna mungojnë"}
    # Çmimi nga SERVERI (jo nga klienti) — bazuar te koeficienti
    pres = requests.get(
        f"{SUPABASE_URL_PREDS}?id=eq.{match_id}&select=id,ndeshja,rezultati_sakt,koef_rez_sakt",
        headers=SUPABASE_SERVICE_HEADERS)
    preds = pres.json() if pres.status_code == 200 else []
    if not preds:
        return {"sukses": False, "kod": "MATCH_NOT_FOUND", "mesazhi": "Ndeshja s'u gjet"}
    nd = preds[0]
    cmimi = _cmimi_ppm(nd.get("koef_rez_sakt"))
    ures = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,blerjet",
                        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return {"sukses": False, "kod": "USER_NOT_FOUND", "mesazhi": "Përdoruesi s'u gjet"}
    u = users[0]
    portofoli = float(u.get("portofoli", 0) or 0)
    blerjet = u.get("blerjet") or []
    if any(str(b.get("id")) == str(match_id) for b in blerjet):
        return {"sukses": True, "kod": "ALREADY_BOUGHT", "mesazhi": "Tashmë e blerë", "portofoli": round(portofoli, 2)}
    if portofoli < cmimi:
        return {"sukses": False, "kod": "NO_CREDITS", "mesazhi": "Kredite të pamjaftueshme",
                "kerkohet": cmimi, "portofoli": round(portofoli, 2)}
    portofoli_ri = round(portofoli - cmimi, 2)
    blerjet.append({"id": nd["id"], "ndeshja": nd.get("ndeshja"),
                    "rezultati": nd.get("rezultati_sakt"), "koef": nd.get("koef_rez_sakt"),
                    "cmimi": cmimi})
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                   headers=SUPABASE_SERVICE_HEADERS,
                   json={"portofoli": portofoli_ri, "blerjet": blerjet})
    return {"sukses": True, "portofoli": portofoli_ri, "blerja": blerjet[-1]}


# ── VIP me KREDITE (server-autoritar) ──
@app.post("/api/vip/purchase")
def vip_blej_me_kredite(payload: dict, authorization: str = Header(None)):
    email = _email_auth(authorization, payload.get("email", ""))
    if not email:
        return {"sukses": False, "kod": "EMAIL_MISSING", "mesazhi": "email mungon"}
    ures = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,vip_skadon_me",
                        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return {"sukses": False, "kod": "USER_NOT_FOUND", "mesazhi": "Përdoruesi s'u gjet"}
    portofoli = float(users[0].get("portofoli", 0) or 0)
    if portofoli < CMIMI_VIP:
        return {"sukses": False, "kod": "NO_CREDITS", "mesazhi": "Kredite të pamjaftueshme",
                "kerkohet": CMIMI_VIP, "portofoli": round(portofoli, 2)}
    baza = datetime.utcnow()
    if users[0].get("vip_skadon_me"):
        try:
            d = datetime.strptime(str(users[0]["vip_skadon_me"])[:10], "%Y-%m-%d")
            if d > baza:
                baza = d
        except Exception:
            pass
    skadon = (baza + timedelta(days=VIP_DITE)).strftime("%Y-%m-%d")
    portofoli_ri = round(portofoli - CMIMI_VIP, 2)
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_SERVICE_HEADERS,
                   json={"portofoli": portofoli_ri, "isVip": True,
                         "vip_skadon_me": skadon, "auto_rinovim": True})
    return {"sukses": True, "portofoli": portofoli_ri, "vip_skadon_me": skadon}


# ── CRYPTOMUS (server-autoritar; webhook → tabela users) ──
def _crypto_sign(body_str):
    enc = base64.b64encode(body_str.encode("utf-8")).decode("utf-8")
    return hashlib.md5((enc + CRYPTOMUS_PAYMENT_KEY).encode("utf-8")).hexdigest()

def _crypto_info(order_id):
    body_str = json.dumps({"order_id": order_id}, separators=(",", ":"))
    try:
        r = requests.post("https://api.cryptomus.com/v1/payment/info", data=body_str,
                          headers={"merchant": CRYPTOMUS_MERCHANT_ID, "sign": _crypto_sign(body_str),
                                   "Content-Type": "application/json"}, timeout=15)
        return r.json().get("result", {}) or {}
    except Exception:
        return {}


def _paypal_token():
    """Merr access token nga PayPal (client_credentials)."""
    try:
        r = requests.post(f"{PAYPAL_BASE}/v1/oauth2/token",
                          auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
                          data={"grant_type": "client_credentials"},
                          headers={"Accept": "application/json"}, timeout=20)
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _paypal_paid(pp_id):
    """GATE AUTORITATIV: verifiko VETE te PayPal qe porosia eshte COMPLETED."""
    tok = _paypal_token()
    if not tok:
        return False
    try:
        r = requests.get(f"{PAYPAL_BASE}/v2/checkout/orders/{pp_id}",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        return r.status_code == 200 and (r.json().get("status") == "COMPLETED")
    except Exception:
        return False

@app.post("/api/cryptomus/create-invoice")
def crypto_krijo_fature(payload: dict):
    email = payload.get("email", "").lower().strip()
    tipi  = payload.get("tipi")   # "vip" | "topup" | "ppm"
    if not email or tipi not in ("vip", "topup", "ppm", "donate", "ditore", "trial"):
        return {"sukses": False, "kod": "DATA_INVALID", "mesazhi": "Të dhëna të pavlefshme"}

    match_id = payload.get("match_id")
    ndeshja = rezultati = koef = None

    if tipi == "vip":
        shuma = CMIMI_VIP
    elif tipi == "trial":
        shuma = CMIMI_TRIAL
    elif tipi == "ditore":
        shuma = CMIMI_DITORE
    elif tipi in ("topup", "donate"):
        try:
            shuma = float(payload.get("shuma", 0))
        except Exception:
            shuma = 0.0
        if shuma <= 0:
            return {"sukses": False, "kod": "AMOUNT_INVALID", "mesazhi": "Shuma e pavlefshme"}
    else:  # ppm — çmimi nga serveri
        pres = requests.get(
            f"{SUPABASE_URL_PREDS}?id=eq.{match_id}&select=ndeshja,rezultati_sakt,koef_rez_sakt",
            headers=SUPABASE_SERVICE_HEADERS)
        preds = pres.json() if pres.status_code == 200 else []
        if not preds:
            return {"sukses": False, "kod": "MATCH_NOT_FOUND", "mesazhi": "Ndeshja s'u gjet"}
        ndeshja = preds[0].get("ndeshja"); rezultati = preds[0].get("rezultati_sakt")
        koef = preds[0].get("koef_rez_sakt")
        shuma = _cmimi_ppm(koef)

    order_id = f"s1x2_{secrets.token_hex(8)}"
    cd = {
        "amount": f"{shuma:.2f}", "currency": "USD", "order_id": order_id,
        "url_callback": f"{PUBLIC_API_URL}/api/cryptomus/webhook",
        "url_return": f"{PUBLIC_SITE_URL}/?pagesa=sukses",
        "lifetime": 3600,
    }
    body_str = json.dumps(cd, separators=(",", ":"))
    try:
        r = requests.post("https://api.cryptomus.com/v1/payment", data=body_str,
                          headers={"merchant": CRYPTOMUS_MERCHANT_ID, "sign": _crypto_sign(body_str),
                                   "Content-Type": "application/json"}, timeout=20)
        res = r.json()
    except Exception as e:
        return {"sukses": False, "mesazhi": f"Gabim Cryptomus: {e}"}
    result = res.get("result")
    if not result or "url" not in result:
        return {"sukses": False, "kod": "CRYPTOMUS_ERR", "mesazhi": "Përgjigje e papritur nga Cryptomus"}

    requests.post(SUPABASE_URL_POROSITE,
                  headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "resolution=merge-duplicates"},
                  json={"order_id": order_id, "email": email, "tipi": tipi, "amount": f"{shuma:.2f}",
                        "match_id": str(match_id) if match_id else None,
                        "ndeshja": ndeshja, "rezultati": rezultati,
                        "koef": str(koef) if koef is not None else None,
                        "status": "wait", "krijuar": datetime.utcnow().isoformat()})
    return {"sukses": True, "url": result["url"], "order_id": order_id}


@app.post("/api/cryptomus/webhook")
async def crypto_webhook(request: Request):
    raw = await request.body()
    try:
        data = json.loads(raw)
    except Exception:
        return {"state": 0}
    _kredito_porosine(data.get("order_id"))
    return {"state": 0}


def _kredito_porosine(order_id):
    """Krediton porosinë NËSE është paguar (verifikim autoritar me Cryptomus). IDEMPOTENT.
    Përdoret nga webhook DHE nga order-status DHE nga rakordimi — kështu pagesa kompletohet
    edhe kur webhook-u humbet (Render në gjumë). Kthen True nëse krediton tani."""
    if not order_id:
        return False
    pres = requests.get(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}&select=*",
                        headers=SUPABASE_SERVICE_HEADERS)
    pros = pres.json() if pres.status_code == 200 else []
    if not pros or pros[0].get("status") == "paid":
        return False   # s'ekziston ose tashmë e kredituar (idempotent)
    po = pros[0]

    # GATE AUTORITATIV: pyet VETË Cryptomus (webhook/thirrje e falsifikuar s'kalon dot)
    if str(order_id).startswith("pp_"):
        if not _paypal_paid(order_id[3:]):
            return False
    else:
        info = _crypto_info(order_id)
        if (info.get("payment_status") or "") not in ("paid", "paid_over"):
            return False

    email = po.get("email"); tipi = po.get("tipi")
    ures = requests.get(
        f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,isVip,vip_skadon_me,blerjet",
        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return False
    u = users[0]
    update = {}

    if tipi == "topup":
        try:
            shuma = float(po.get("amount", 0))
        except Exception:
            shuma = 0.0
        update["portofoli"] = round(float(u.get("portofoli", 0) or 0) + shuma, 2)
    elif tipi in ("vip", "trial"):
        baza = datetime.utcnow()
        if u.get("vip_skadon_me"):
            try:
                d = datetime.strptime(str(u["vip_skadon_me"])[:10], "%Y-%m-%d")
                if d > baza:
                    baza = d
            except Exception:
                pass
        dite = VIP_DITE if tipi == "vip" else TRIAL_DITE
        update["isVip"] = True
        update["vip_skadon_me"] = (baza + timedelta(days=dite)).strftime("%Y-%m-%d")
    elif tipi == "donate":
        pass  # donacion — s'ndryshon llogarinë
    elif tipi == "ditore":
        update["ditore_unlock_date"] = _data_lokale()
    elif tipi == "combo":
        update["vipcombo_fundit"] = _data_lokale()
    elif tipi == "gjenero":
        update["generate_fundit"] = _data_lokale()
    elif tipi == "ppm":
        blerjet = u.get("blerjet") or []
        if not any(str(b.get("id")) == str(po.get("match_id")) for b in blerjet):
            blerjet.append({"id": po.get("match_id"), "ndeshja": po.get("ndeshja"),
                            "rezultati": po.get("rezultati"), "koef": po.get("koef"),
                            "cmimi": po.get("amount")})
        update["blerjet"] = blerjet

    if update:
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                       headers=SUPABASE_SERVICE_HEADERS, json=update)
        try:
            _FULL_ACCESS_CACHE.pop(str(email).lower().strip(), None)   # VIP/trial → pastro cache aksesi
        except Exception:
            pass
    requests.patch(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}",
                   headers=SUPABASE_SERVICE_HEADERS,
                   json={"status": "paid", "paguar": datetime.utcnow().isoformat()})
    return True


def task_rakordo_porosite():
    """Rakordim: kalon porositë 'wait' të 24h të fundit dhe i krediton nëse janë paguar
    (mburojë kur webhook-u humbet). Thirret nga cron-i."""
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        r = requests.get(f"{SUPABASE_URL_POROSITE}?status=eq.wait&krijuar=gte.{cutoff}&select=order_id&limit=50",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        for o in (r.json() if r.status_code == 200 else []):
            try:
                _kredito_porosine(o.get("order_id"))
            except Exception:
                pass
    except Exception:
        pass


@app.get("/api/cryptomus/order-status")
def crypto_order_status(order_id: str):
    _kredito_porosine(order_id)   # MBUROJË: krediton nëse është paguar por webhook-u humbi
    pres = requests.get(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}&select=status",
                        headers=SUPABASE_SERVICE_HEADERS)
    pros = pres.json() if pres.status_code == 200 else []
    if not pros:
        return {"status": "panjohur"}
    return {"status": pros[0].get("status")}


@app.post("/api/paypal/create-order")
def paypal_krijo_porosi(payload: dict):
    email = payload.get("email", "").lower().strip()
    tipi  = payload.get("tipi")
    if not email or tipi not in ("vip", "topup", "ppm", "donate", "ditore", "trial", "combo", "gjenero"):
        return {"sukses": False, "kod": "DATA_INVALID", "mesazhi": "Te dhena te pavlefshme"}
    if not PAYPAL_CLIENT_ID:
        return {"sukses": False, "kod": "PAYPAL_OFF", "mesazhi": "PayPal s'eshte konfiguruar"}

    match_id = payload.get("match_id")
    ndeshja = rezultati = koef = None
    if tipi == "vip":
        shuma = CMIMI_VIP
    elif tipi == "trial":
        shuma = CMIMI_TRIAL
    elif tipi == "ditore":
        shuma = CMIMI_DITORE
    elif tipi == "combo":
        shuma = CMIM_VIPCOMBO
    elif tipi == "gjenero":
        shuma = CMIM_GENERATE
    elif tipi in ("topup", "donate"):
        try:
            shuma = float(payload.get("shuma", 0))
        except Exception:
            shuma = 0.0
        if shuma <= 0:
            return {"sukses": False, "kod": "AMOUNT_INVALID", "mesazhi": "Shuma e pavlefshme"}
    else:  # ppm
        pres = requests.get(
            f"{SUPABASE_URL_PREDS}?id=eq.{match_id}&select=ndeshja,rezultati_sakt,koef_rez_sakt",
            headers=SUPABASE_SERVICE_HEADERS)
        preds = pres.json() if pres.status_code == 200 else []
        if not preds:
            return {"sukses": False, "kod": "MATCH_NOT_FOUND", "mesazhi": "Ndeshja s'u gjet"}
        ndeshja = preds[0].get("ndeshja"); rezultati = preds[0].get("rezultati_sakt")
        koef = preds[0].get("koef_rez_sakt")
        shuma = _cmimi_ppm(koef)

    tok = _paypal_token()
    if not tok:
        return {"sukses": False, "kod": "PAYPAL_AUTH", "mesazhi": "PayPal auth deshtoi"}
    trupi = {
        "intent": "CAPTURE",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": f"{shuma:.2f}"}}],
        "application_context": {
            "brand_name": "SOCCER1X2 PRO", "user_action": "PAY_NOW", "landing_page": "BILLING",
            "return_url": f"{PUBLIC_SITE_URL}/?paypal=return",
            "cancel_url": f"{PUBLIC_SITE_URL}/?paypal=anulluar",
        },
    }
    try:
        r = requests.post(f"{PAYPAL_BASE}/v2/checkout/orders",
                          headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                          json=trupi, timeout=20)
        res = r.json()
    except Exception as e:
        return {"sukses": False, "mesazhi": f"Gabim PayPal: {e}"}
    pp_id = res.get("id")
    approve = next((l["href"] for l in res.get("links", []) if l.get("rel") == "approve"), None)
    if not pp_id or not approve:
        return {"sukses": False, "kod": "PAYPAL_ERR", "mesazhi": "Pergjigje e papritur nga PayPal"}

    order_id = "pp_" + pp_id
    requests.post(SUPABASE_URL_POROSITE,
                  headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "resolution=merge-duplicates"},
                  json={"order_id": order_id, "email": email, "tipi": tipi, "amount": f"{shuma:.2f}",
                        "match_id": str(match_id) if match_id else None,
                        "ndeshja": ndeshja, "rezultati": rezultati,
                        "koef": str(koef) if koef is not None else None,
                        "status": "wait", "krijuar": datetime.utcnow().isoformat()})
    return {"sukses": True, "url": approve, "order_id": order_id}


@app.get("/api/paypal/capture")
def paypal_kap(order_id: str = None, token: str = None):
    """Kap pagesen te PayPal, pastaj krediton (idempotent). Pranon order_id ('pp_'+id) ose token (id nga PayPal)."""
    if not order_id and token:
        order_id = "pp_" + token
    if not order_id:
        return {"status": "panjohur"}
    pp_id = order_id[3:] if str(order_id).startswith("pp_") else order_id
    tok = _paypal_token()
    if tok:
        try:
            requests.post(f"{PAYPAL_BASE}/v2/checkout/orders/{pp_id}/capture",
                          headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                          timeout=20)
        except Exception:
            pass
    _kredito_porosine(order_id)   # porta verifikon COMPLETED te PayPal (idempotent)
    pres = requests.get(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}&select=status",
                        headers=SUPABASE_SERVICE_HEADERS)
    pros = pres.json() if pres.status_code == 200 else []
    if not pros:
        return {"status": "panjohur"}
    return {"status": pros[0].get("status")}



# ==========================================================
# SKEDINA E DITËS (top 4) + KOMBINIMI I DITËS (10 skedina nga top 5)
# Lexon best_bet/tregjet e ruajtura — pa rillogaritje MC.
# ==========================================================
def _top2_tregje(tregjet):
    if not tregjet:
        return []
    return sorted(tregjet.items(), key=lambda kv: kv[1], reverse=True)[:2]


# ── Motori i kombinimeve (banker+hedge, korrelacion real, koef>=10, 6 skedina) ──
COMBO_MARKETS  = ["1", "X", "2", "Over 1.5", "Under 1.5", "Over 2.5",
                  "Under 2.5", "Over 3.5", "Under 3.5", "GG", "NG"]
DOUBLE_MARKETS = COMBO_MARKETS + ["1X", "X2", "12"]
KOEF_MIN_SKEDINE = 10.0
KOEF_MIN_BAZE    = 1.40   # shmang piket trivialë si bazë


def _parse_score(s):
    try:
        a, b = str(s).replace(" ", "").split("-")
        return int(a), int(b)
    except Exception:
        return None


def _score_satisfies(gh, ga, market):
    tot = gh + ga
    if market == "1": return gh > ga
    if market == "X": return gh == ga
    if market == "2": return gh < ga
    if market == "1X": return gh >= ga
    if market == "X2": return gh <= ga
    if market == "12": return gh != ga
    if market == "Over 1.5": return tot >= 2
    if market == "Under 1.5": return tot <= 1
    if market == "Over 2.5": return tot >= 3
    if market == "Under 2.5": return tot <= 2
    if market == "Over 3.5": return tot >= 4
    if market == "Under 3.5": return tot <= 3
    if market == "GG": return gh > 0 and ga > 0
    if market == "NG": return gh == 0 or ga == 0
    return False


def _joint_prob(dist_gola, markets):
    if not dist_gola:
        return None
    total = 0.0; hit = 0.0
    for sc, freq in dist_gola.items():
        try:
            f = float(freq)
        except Exception:
            continue
        total += f
        pr = _parse_score(sc)
        if pr and all(_score_satisfies(pr[0], pr[1], m) for m in markets):
            hit += f
    return (hit / total) if total > 0 else None


def _etiketa_margjines(dist_gola, e1="", e2=""):
    """Nga shperndarja e skoreve nxjerr profilin e margjines (per AH +/-1.5).
    Kthen {label, detaje, ah, tipi, kush, p} ose None."""
    if not dist_gola:
        return None
    tot = ph2 = ph1 = px = pa1 = pa2 = 0.0
    for sc, freq in dist_gola.items():
        try:
            f = float(freq)
        except Exception:
            continue
        pr = _parse_score(sc)
        if not pr:
            continue
        d = pr[0] - pr[1]
        tot += f
        if d >= 2:
            ph2 += f
        elif d == 1:
            ph1 += f
        elif d == 0:
            px += f
        elif d == -1:
            pa1 += f
        else:
            pa2 += f
    if tot <= 0:
        return None
    ph2 /= tot; ph1 /= tot; px /= tot; pa1 /= tot; pa2 /= tot
    e1 = e1 or "Ekipi 1"; e2 = e2 or "Ekipi 2"
    pw_h = ph1 + ph2; pw_a = pa1 + pa2
    if pw_h >= pw_a:
        fwin, fdom, fteam, funder = pw_h, ph2, e1, e2
    else:
        fwin, fdom, fteam, funder = pw_a, pa2, e2, e1
    if fdom >= 0.35:
        return {"tipi": "dominim", "kush": fteam, "p": round(fdom, 3),
                "label": f"Dominim {fteam}", "detaje": "diferencë 2+ gola", "ah": f"{fteam} -1.5"}
    if fwin >= 0.45:
        return {"tipi": "ngushte", "kush": fteam, "p": round(fwin, 3),
                "label": f"Fitore e ngushtë {fteam}", "detaje": "~1 gol diferencë", "ah": f"{funder} +1.5"}
    return {"tipi": "ekuiliber", "kush": "", "p": round(px, 3),
            "label": "Ekuilibër", "detaje": "ndeshje e ngushtë", "ah": "+1.5 të dyja"}


def _marg_suffix_html(marg, gj):
    """Etiketa e margjinës si HTML shumëgjuhësh (shtohet te analiza tekstuale)."""
    if not marg:
        return ""
    tipi = marg.get("tipi"); kush = marg.get("kush", ""); ah = marg.get("ah", "")
    TLAB = {
        "dominim":   {"sq": "Dominim", "en": "Dominance", "de": "Dominanz", "fr": "Domination", "it": "Dominio"},
        "ngushte":   {"sq": "Fitore e ngushtë", "en": "Narrow win", "de": "Knapper Sieg", "fr": "Victoire serrée", "it": "Vittoria di misura"},
        "ekuiliber": {"sq": "Ekuilibër", "en": "Balanced", "de": "Ausgeglichen", "fr": "Équilibré", "it": "Equilibrato"},
    }
    DET = {
        "dominim":   {"sq": "diferencë 2+ gola", "en": "2+ goal margin", "de": "2+ Tore Abstand", "fr": "écart de 2+ buts", "it": "scarto di 2+ gol"},
        "ngushte":   {"sq": "~1 gol diferencë", "en": "~1 goal margin", "de": "~1 Tor Abstand", "fr": "écart de ~1 but", "it": "scarto di ~1 gol"},
        "ekuiliber": {"sq": "ndeshje e ngushtë", "en": "tight match", "de": "enges Spiel", "fr": "match serré", "it": "partita equilibrata"},
    }
    tl = TLAB.get(tipi, {}).get(gj, "")
    dl = DET.get(tipi, {}).get(gj, "")
    head = tl + ((" " + kush) if kush else "")
    ahpart = ""
    if ah:
        ahpart = " &middot; <b style='color:#3fb950;'>AH: " + ah + "</b>"
    return "<br><b style='color:#d4af37;'>\U0001F4CA " + head + "</b> <span style='color:#8b949e;'>(" + dl + ")</span>" + ahpart


def _legs_per_match(p, market_set):
    tregjet = p.get("tregjet") or {}
    odds = p.get("odds_reale") or {}
    legs = []
    _pr_km = _parse_score(p.get("rezultati_sakt") or "")
    for m in market_set:
        if m not in tregjet:
            continue
        try:
            prob = float(tregjet[m])
        except Exception:
            continue
        if prob <= 0:
            continue
        if _pr_km and not _treg_koherent(m, _pr_km):
            continue   # KOHERENCA: kurrë treg kundër skorit të parashikuar
        od_real = None
        if m in odds:
            try:
                od_real = float(odds[m])
            except Exception:
                od_real = None
        od = od_real if (od_real and od_real > 1) else round(1.0 / prob, 2)
        legs.append({"market": m, "prob": prob, "koef": round(od, 2), "real": bool(od_real)})
    return legs


def _grupi_tregut(m):
    if m.startswith("HT/FT"):
        return "htft"
    if m.startswith("HT "):          # HT si mini-FT (HT 1, HT Over 0.5, HT GG, HT CS ...)
        return "ht"
    if m in ("1", "X", "2", "1X", "X2", "12"):
        return "rezultat"
    if m.startswith("Over") or m.startswith("Under"):
        return "ou"
    if m in ("GG", "NG"):
        return "btts"
    if m.startswith("AH "):
        return "ah"
    if m.startswith("CS "):
        return "cs"
    return "tjeter"


def _baza_leg(legs):
    me_koef = [l for l in legs if l["koef"] >= KOEF_MIN_BAZE]
    pool = me_koef if me_koef else legs
    return max(pool, key=lambda l: l["prob"]) if pool else None


def _shto_double_options(rendit, legs_out, koef_total, prob_total):
    """Shton leg të dytë te ndeshjet e sigurta, duke zgjedhur atë me KORRELACION
    pozitiv + boost koef-i (maksimizon jp × koef), derisa koef >= 10."""
    for pos, m in enumerate(rendit):
        if koef_total >= KOEF_MIN_SKEDINE:
            break
        baza = legs_out[pos]
        if len(baza["pjeset"]) >= 2:
            continue
        market_baza = baza["pjeset"][0]
        best = None; best_score = -1.0
        grupi_baza = _grupi_tregut(market_baza)
        for k in m["legs_full"]:
            if k["market"] == market_baza or k["koef"] < 1.30:
                continue
            if _grupi_tregut(k["market"]) == grupi_baza:
                continue   # mos kombino brenda të njëjtit grup (p.sh. dy Over/Under)
            jp = _joint_prob(m["dist"], [market_baza, k["market"]])
            if jp is None:
                jp = baza["prob"] * k["prob"]
            if jp <= 0.05:
                continue
            score = jp * k["koef"]          # EV e shtuar
            if score > best_score:
                best_score = score; best = (k, jp)
        if not best:
            continue
        k, jp = best
        koef_total *= k["koef"]
        if baza["prob"] > 0:
            prob_total = prob_total / baza["prob"] * jp
        baza["koef"] = round(baza["koef"] * k["koef"], 2)
        baza["prob"] = round(jp, 4)
        baza["pjeset"].append(k["market"])
    return koef_total, prob_total


def _ndderto_skedine(kater, varianti=0):
    rendit = sorted(kater, key=lambda mm: mm["conf"], reverse=True)
    legs_out = []; koef_total = 1.0; prob_total = 1.0
    for pos, m in enumerate(rendit):
        legs = m["legs"]
        if not legs:
            return None
        if pos < 2:
            zgjedhja = _baza_leg(legs)
        else:
            top2 = sorted([l for l in legs if l["koef"] >= KOEF_MIN_BAZE] or legs,
                          key=lambda l: l["prob"], reverse=True)[:2]
            zgjedhja = top2[min(varianti % 2, len(top2) - 1)] if top2 else None
        if not zgjedhja:
            return None
        legs_out.append({"ndeshja": m["ndeshja"], "liga": m.get("liga_emri"), "pjeset": [zgjedhja["market"]],
                         "prob": zgjedhja["prob"], "koef": zgjedhja["koef"]})
        koef_total *= zgjedhja["koef"]; prob_total *= zgjedhja["prob"]
    if koef_total < KOEF_MIN_SKEDINE:
        koef_total, prob_total = _shto_double_options(rendit, legs_out, koef_total, prob_total)
    return {"ndeshjet": legs_out, "koef_total": round(koef_total, 2), "prob": round(prob_total, 4)}


def _gjenero_kombinimet(top5):
    mature = []
    for p in top5:
        legs = _legs_per_match(p, COMBO_MARKETS)
        if not legs:
            continue
        legs.sort(key=lambda l: l["prob"], reverse=True)
        mature.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"),
                       "dist": p.get("dist_gola") or {}, "legs": legs,
                       "legs_full": _legs_per_match(p, DOUBLE_MARKETS),
                       "conf": legs[0]["prob"]})
    if len(mature) < 4:
        return []
    mature.sort(key=lambda mm: mm["conf"], reverse=True)
    n = len(mature)
    plan = []
    if n >= 5:
        for i in range(5):
            plan.append([m for j, m in enumerate(mature) if j != i])
        plan.append(mature[:4])
    else:
        for _ in range(6):
            plan.append(mature[:4])
    out = []
    for idx, kater in enumerate(plan[:6]):
        sked = _ndderto_skedine(kater, varianti=idx)
        if sked:
            out.append({"nr": len(out) + 1, **sked})
    return out[:6]


def _eshte_zhbllokuar_ditore(email):
    if not email:
        return False
    if _eshte_vip(email):          # VIP = akses i plotë (përfshin produktet ditore)
        return True
    try:
        sot = _data_lokale()
        r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}&select=ditore_unlock_date",
                         headers=SUPABASE_SERVICE_HEADERS)
        u = r.json() if r.status_code == 200 else []
        return bool(u) and str(u[0].get("ditore_unlock_date") or "")[:10] == sot
    except Exception:
        return False


@app.post("/api/ditore/unlock")
def ditore_unlock_me_kredite(payload: dict, authorization: str = Header(None)):
    email = _email_auth(authorization, payload.get("email", ""))
    if not email:
        return {"sukses": False, "kod": "EMAIL_MISSING", "mesazhi": "email mungon"}
    r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,ditore_unlock_date",
                     headers=SUPABASE_SERVICE_HEADERS)
    u = r.json() if r.status_code == 200 else []
    if not u:
        return {"sukses": False, "kod": "USER_NOT_FOUND", "mesazhi": "Përdoruesi s'u gjet"}
    sot = _data_lokale()
    portofoli = float(u[0].get("portofoli", 0) or 0)
    if str(u[0].get("ditore_unlock_date") or "")[:10] == sot:
        return {"sukses": True, "kod": "ALREADY_UNLOCKED", "mesazhi": "Tashmë e zhbllokuar sot",
                "ditore_unlock_date": sot, "portofoli": round(portofoli, 2)}
    if portofoli < CMIMI_DITORE:
        return {"sukses": False, "kod": "NO_CREDITS", "mesazhi": "Kredite të pamjaftueshme",
                "kerkohet": CMIMI_DITORE, "portofoli": round(portofoli, 2)}
    portofoli_ri = round(portofoli - CMIMI_DITORE, 2)
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_SERVICE_HEADERS,
                   json={"portofoli": portofoli_ri, "ditore_unlock_date": sot})
    return {"sukses": True, "portofoli": portofoli_ri, "ditore_unlock_date": sot}


@app.get("/api/ditore")
def skedina_dhe_kombinimi_ditore(email: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email, strict=False)
    res = requests.get(
        f"{SUPABASE_URL_PREDS}?select=id,ndeshja,data,ora,statusi,best_bet,tregjet,odds_reale,dist_gola"
        f"&best_bet=not.is.null"
        f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)"
        f"&order=id.desc&limit=300",
        headers=SUPABASE_SERVICE_HEADERS)
    preds = res.json() if res.status_code == 200 else []
    preds = [p for p in preds if p.get("best_bet") and float((p.get("best_bet") or {}).get("koef", 0) or 0) >= 1.7]

    def _prob(p):
        try:
            return float((p.get("best_bet") or {}).get("prob", 0))
        except Exception:
            return 0.0
    preds.sort(key=_prob, reverse=True)

    # SKEDINA E DITËS = top 4 (një skedinë e vetme)
    top4 = preds[:4]
    sked = []
    koef_total = 1.0
    for p in top4:
        bb = p.get("best_bet") or {}
        koef = bb.get("koef")
        if koef:
            koef_total *= float(koef)
        sked.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"),
                     "tregu": bb.get("tregu"), "prob": bb.get("prob"), "koef": koef})
    skedina_ditore = {"ndeshjet": sked, "koef_total": round(koef_total, 2) if sked else 0}

    # KOMBINIMI I DITËS = top 5 → 10 skedina nga 4
    kombinimi_ditore = _gjenero_kombinimet(preds[:5])

    # ── GATING: kthe picks vetëm nëse përdoruesi e ka zhbllokuar sot ──
    if _eshte_zhbllokuar_ditore(email):
        return {
            "unlocked": True,
            "skedina_ditore": skedina_ditore,
            "kombinimi_ditore": kombinimi_ditore,
            "nr_ndeshjeve_analizuara": len(preds),
            "perditesuar": datetime.utcnow().isoformat(),
        }
    # I KYÇUR: vetëm emrat e ndeshjeve (pa tregje/prob/koef) + numri i skedinave
    sked_teaser = [{"ndeshja": x.get("ndeshja")} for x in skedina_ditore["ndeshjet"]]
    return {
        "unlocked": False,
        "cmimi": CMIMI_DITORE,
        "skedina_ditore": {"ndeshjet": sked_teaser, "nr": len(sked_teaser)},
        "kombinimi_ditore": {"nr_skedinash": len(kombinimi_ditore)},
        "nr_ndeshjeve_analizuara": len(preds),
        "perditesuar": datetime.utcnow().isoformat(),
    }


# ==========================================
# HISTORIKU I SKEDINËS SË DITËS (snapshot + vlerësim + %)
# ==========================================
SKEDINA_HIST_URL = f"{SUPABASE_BASE}/rest/v1/skedina_historik"


def _snapshot_skedina_ditore():
    """Ruan Skedinën e Ditës (top-4) si snapshot ditor. Nuk e mbishkruan një ditë të finalizuar."""
    try:
        sot = _data_lokale()
        rr = requests.get(f"{SKEDINA_HIST_URL}?data=eq.{sot}&select=statusi",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        ekz = rr.json() if rr.status_code == 200 else []
        if ekz and ekz[0].get("statusi") in ("fituese", "humbur"):
            return  # e finalizuar → mos e prek
        res = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,best_bet&best_bet=not.is.null"
            f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&order=id.desc&limit=300",
            headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        preds = [p for p in (res.json() if res.status_code == 200 else []) if p.get("best_bet") and float((p.get("best_bet") or {}).get("koef", 0) or 0) >= 1.7]
        preds.sort(key=lambda p: float((p.get("best_bet") or {}).get("prob", 0)), reverse=True)
        top4 = preds[:4]
        if len(top4) < 4:
            return  # jo mjaft ndeshje për një skedinë të plotë
        pikat = [{"id": p["id"], "ndeshja": p.get("ndeshja"),
                  "tregu": (p.get("best_bet") or {}).get("tregu"),
                  "koef": (p.get("best_bet") or {}).get("koef"),
                  "prob": (p.get("best_bet") or {}).get("prob")} for p in top4]
        koef_total = 1.0
        for pk in pikat:
            if pk.get("koef"):
                koef_total *= float(pk["koef"])
        rec = {"data": sot, "pikat": pikat,
               "koef_total": round(koef_total, 2),
               "statusi": "pezull",
               "krijuar": datetime.utcnow().isoformat()}
        if ekz:
            # ekziston tashmë rresht(a) 'pezull' për sot → përditësoje (mos krijo dublikat të ri)
            requests.patch(f"{SKEDINA_HIST_URL}?data=eq.{sot}",
                           headers=SUPABASE_SERVICE_HEADERS, json=rec, timeout=5)
        else:
            headers = SUPABASE_SERVICE_HEADERS.copy()
            headers["Prefer"] = "resolution=merge-duplicates"
            requests.post(SKEDINA_HIST_URL, headers=headers, json=rec, timeout=5)
    except Exception as e:
        print(f"[HISTORIK] snapshot gabim: {e}")


def _vlereso_skedina_historik():
    """Vlerëson skedinat 'pezull' kur TË GJITHA ndeshjet kanë mbaruar (fiton vetëm nëse të 4 goditen)."""
    try:
        r = requests.get(f"{SKEDINA_HIST_URL}?statusi=eq.pezull&select=data,pikat",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        rows = r.json() if r.status_code == 200 else []
        for row in rows:
            pikat = row.get("pikat") or []
            ids = [str(p["id"]) for p in pikat if p.get("id")]
            if not ids:
                continue
            rr = requests.get(
                f"{SUPABASE_URL_PREDS}?id=in.({','.join(ids)})&select=id,statusi,rezultati",
                headers=SUPABASE_SERVICE_HEADERS, timeout=5)
            mm = {str(m["id"]): m for m in (rr.json() if rr.status_code == 200 else [])}
            te_mbaruara = all(
                mm.get(str(p["id"]), {}).get("statusi") in ("FT", "AET", "PEN", "AWD", "WO")
                for p in pikat)
            if not te_mbaruara:
                continue
            te_gjitha_goditen = True
            detaje = []
            for p in pikat:
                m = mm.get(str(p["id"]), {})
                rez = m.get("rezultati") or ""
                pr = _parse_score(rez)
                hit = bool(pr and _score_satisfies(pr[0], pr[1], p.get("tregu")))
                if not hit:
                    te_gjitha_goditen = False
                detaje.append({**p, "rezultati": rez, "goditi": hit})
            statusi = "fituese" if te_gjitha_goditen else "humbur"
            h2 = SUPABASE_SERVICE_HEADERS.copy()
            requests.patch(f"{SKEDINA_HIST_URL}?data=eq.{row['data']}",
                           headers=h2, json={"statusi": statusi, "pikat": detaje}, timeout=5)
    except Exception as e:
        print(f"[HISTORIK] vleresim gabim: {e}")


@app.get("/api/skedina/historik")
def skedina_historik(email: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email)
    try:
        r = requests.get(
            f"{SKEDINA_HIST_URL}?select=data,pikat,koef_total,statusi,krijuar&order=data.desc&limit=60",
            headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    # ── SKEDINA E DITËS: 1 rresht/ditë (hiq dublikatat nga snapshot-et e shumta) ──
    # Përparësi: fituese > humbur > pezull; barazim → koeficienti më i lartë.
    _STAT_RANK = {"fituese": 2, "humbur": 1, "pezull": 0}
    def _koef_sk(x):
        try:
            return float(x.get("koef_total") or 0)
        except Exception:
            return 0.0
    def _rank_sk(x):
        return (_STAT_RANK.get(x.get("statusi"), 0), _koef_sk(x))
    _sk_best = {}
    for _r in rows:
        _dita = str(_r.get("data") or "")[:10]
        if not _dita:
            continue
        if _dita not in _sk_best or _rank_sk(_r) > _rank_sk(_sk_best[_dita]):
            _sk_best[_dita] = _r
    rows = sorted(_sk_best.values(), key=lambda x: str(x.get("data") or ""), reverse=True)

    finalizuar = [x for x in rows if x.get("statusi") in ("fituese", "humbur")]
    fituese = sum(1 for x in finalizuar if x.get("statusi") == "fituese")
    total = len(finalizuar)
    # ── VIP COMBO: vetëm fituese, 1/ditë me KOEFICIENTIN më të lartë ──
    try:
        vc = requests.get(
            f"{VIP_COMBO_HIST_URL}?select=data,nr,rez,statusi,fituesi,krijuar"
            f"&statusi=eq.fituese&order=krijuar.desc&limit=60",
            headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        vip_combo = vc.json() if vc.status_code == 200 else []
    except Exception:
        vip_combo = []

    # Përparësi: MË SHUMË ndeshje fituese (3 > 2), pastaj koeficienti më i lartë.
    # (koef_total mund të mungojë te vlerësimet e vjetra → renditja s'duhet të varet vetëm nga ai)
    def _rank_vc(c):
        f = c.get("fituesi") or {}
        try:
            k = float(f.get("koef_total") or 0)
        except Exception:
            k = 0.0
        n = f.get("total") or len(f.get("rreshtat") or [])
        return (n, k)
    _vc_best = {}
    for _c in vip_combo:
        _dita = _c.get("data")
        if _dita not in _vc_best or _rank_vc(_c) > _rank_vc(_vc_best[_dita]):
            _vc_best[_dita] = _c
    vip_combo = sorted(_vc_best.values(), key=lambda x: (x.get("data") or ""), reverse=True)

    # ── GJENERO SKEDINËN (personale): vetëm fituese, 1/ditë me KOEFICIENTIN më të lartë ──
    gjeneruar = []
    if email and email.strip():
        _em = email.strip().lower()
        try:
            gr = requests.get(
                f"{SKEDINA_IME_URL}?email=eq.{_em}&tipi=eq.ticket&statusi=eq.fituese"
                f"&select=data,krijuar,permbajtja,fituesi&order=krijuar.desc&limit=80",
                headers=SUPABASE_SERVICE_HEADERS, timeout=6)
            gr_rows = gr.json() if gr.status_code == 200 else []
        except Exception:
            gr_rows = []

        def _permb(g):
            p = g.get("permbajtja") or {}
            if isinstance(p, str):
                try: p = json.loads(p)
                except Exception: p = {}
            return p

        def _koef_gt(g):
            return float((_permb(g).get("koef_total")) or 0)

        def _data_gt(g):
            if g.get("data"): return str(g.get("data"))[:10]
            return (g.get("krijuar") or "")[:10]

        _gt_best = {}
        for _g in gr_rows:
            _dita = _data_gt(_g)
            if _dita not in _gt_best or _koef_gt(_g) > _koef_gt(_gt_best[_dita]):
                _gt_best[_dita] = _g
        gjeneruar = sorted(_gt_best.values(), key=lambda x: _data_gt(x), reverse=True)

    # ── COMBO NDESHJESH (personale): vetëm fituese, 1/ditë me koeficientin fitues më të lartë ──
    combo_nde = []
    if email and email.strip():
        _em2 = email.strip().lower()
        try:
            cn = requests.get(
                f"{SKEDINA_IME_URL}?email=eq.{_em2}&tipi=eq.combonde&statusi=eq.fituese"
                f"&select=data,krijuar,permbajtja,fituesi&order=krijuar.desc&limit=80",
                headers=SUPABASE_SERVICE_HEADERS, timeout=6)
            cn_rows = cn.json() if cn.status_code == 200 else []
        except Exception:
            cn_rows = []
        def _cn_permb(g):
            p = g.get("permbajtja") or {}
            if isinstance(p, str):
                try: p = json.loads(p)
                except Exception: p = {}
            return p
        def _cn_koef(g):
            p = _cn_permb(g); f = g.get("fituesi") or {}
            komb = p.get("kombinimet") or []
            best = 0.0
            for ki in (f.get("fitues_idx") or []):
                if 0 <= ki < len(komb):
                    try: best = max(best, float(komb[ki].get("koef_total") or 0))
                    except Exception: pass
            return best
        def _cn_data(g):
            if g.get("data"): return str(g.get("data"))[:10]
            return (g.get("krijuar") or "")[:10]
        _cn_best = {}
        for _g in cn_rows:
            _dita = _cn_data(_g)
            if _dita not in _cn_best or _cn_koef(_g) > _cn_koef(_cn_best[_dita]):
                _cn_best[_dita] = _g
        combo_nde = sorted(_cn_best.values(), key=lambda x: _cn_data(x), reverse=True)

    return {
        "historik": rows,
        "fituese": fituese,
        "total_finalizuar": total,
        "perqindja": round(100.0 * fituese / total, 1) if total else None,
        "vip_combo": vip_combo,
        "gjeneruar": gjeneruar,
        "combo_nde": combo_nde,
    }


# ==========================================
# GJENERATORI VIP "GJENERO SKEDINËN" (parametrik)
# ==========================================
GRUPET_GJENERATOR = {
    "1x2": ["1", "X", "2"],
    "dc":  ["1X", "X2", "12"],
    "ou":  ["Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"],
    "gg":  ["GG", "NG"],
}


def _eshte_vip(email):
    if not email:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}&select=isVip,vip_skadon_me",
            headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        u = r.json() if r.status_code == 200 else []
        if not u or not u[0].get("isVip"):
            return False
        skadon = u[0].get("vip_skadon_me")
        if not skadon:
            return True
        return str(skadon)[:10] >= _data_lokale()
    except Exception:
        return False


def _treg_koherent(m, pr):
    """A përputhet tregu m me skorin e parashikuar pr=(h,a)?
    Parimi: skori i saktë është IDENTITETI i ndeshjes — çdo treg FT duhet të rrjedhë prej tij.
    Tregjet HT/HTFT/CS/AH trajtohen te ndërtuesit e vet (kanë kontekst shtesë)."""
    try:
        h, a = int(pr[0]), int(pr[1])
    except Exception:
        return True
    m = str(m).strip()
    if m == "1":  return h > a
    if m == "X":  return h == a
    if m == "2":  return h < a
    if m == "1X": return h >= a
    if m == "X2": return h <= a
    if m == "12": return h != a
    if m == "GG": return h > 0 and a > 0
    if m == "NG": return not (h > 0 and a > 0)
    if m.startswith("Over "):
        try:    return (h + a) > float(m.split()[1])
        except Exception: return True
    if m.startswith("Under "):
        try:    return (h + a) < float(m.split()[1])
        except Exception: return True
    return True


GEN_LEG_FLOOR  = 0.25     # prob min për një leg të vetëm (përjashton baste kundër favoritit, p.sh. barazim te favoriti)
GEN_DOPT_FLOOR = 0.18     # prob min për një double-option (dy tregje bashkë)


def _prob_ah(dist, side, hcap, tot=0.0):
    """Probabiliteti që favoriti mbulon handicap-in (nga shpërndarja e skoreve).
    side='Home'/'Away'; hcap pozitiv (p.sh. 1.5 -> favoriti -1.5)."""
    s = 0.0
    for sc, freq in dist.items():
        try:
            h, a = map(int, str(sc).split("-"))
        except Exception:
            continue
        marg = (h - a) if side == "Home" else (a - h)
        if marg - hcap > 0:
            s += float(freq or 0)
    if tot and tot > 0:
        s = s / tot
    return round(s, 4)


def _legs_gjenerator(p, grupet_lejuara):
    """Legs të PËRPUTHURA me parashikimin: VETËM ana e favorizuar e çdo tregu.
    Kurrë kundër favoritit (s'luan 'X2' te një favorit vendas, etj.)."""
    tregjet = p.get("tregjet") or {}
    odds = p.get("odds_reale") or {}
    dist_gola = p.get("dist_gola") or {}

    def P(m):
        try:
            return float(tregjet.get(m, 0) or 0)
        except Exception:
            return 0.0

    # Profili i parashikimit (nga skori i parashikuar)
    _pr = _parse_score(p.get("rezultati_sakt") or "")
    _tot = (_pr[0] + _pr[1]) if _pr else None
    _marg = abs(_pr[0] - _pr[1]) if _pr else 0
    _dominim = _marg >= 2                              # 0:3, 1:3, 2:0... → dominim i qartë
    # 1X2 i PËRPUTHUR me skorin e parashikuar (kurrë kundër parashikimit):
    #   vendas > mik → "1", mik > vendas → "2", barazim → "X".
    if _pr:
        fav = "1" if _pr[0] > _pr[1] else ("2" if _pr[0] < _pr[1] else "X")
    else:
        fav = max([("1", P("1")), ("X", P("X")), ("2", P("2"))], key=lambda x: x[1])[0]
    aligned = []
    if "1x2" in grupet_lejuara and P(fav) > 0:
        aligned.append(fav)
    if "dc" in grupet_lejuara and not _dominim:       # DC VETËM kur JO dominim; te dominimi → favoriti/Over (jo timid)
        if fav == "1":
            aligned += ["1X", "12"]
        elif fav == "X":
            aligned += ["1X", "X2"]
        else:
            aligned += ["12", "X2"]
    if "ou" in grupet_lejuara:                        # linja O/U e PËRPUTHUR me golat e parashikuara
        if _tot is None:
            ou_lines = ["1.5", "2.5", "3.5"]           # fallback: si më parë
        elif _tot >= 4:
            ou_lines = ["2.5", "3.5"]                  # dominim me shumë gola (1:3, 0:4)
        elif _tot == 3:
            ou_lines = ["2.5"]                         # 3 gola (0:3, 2:1, 1:2) → Over 2.5, jo 1.5
        else:
            ou_lines = ["1.5"]                         # ≤2 gola → Over/Under 1.5
        for ln in ou_lines:
            o, u = P("Over " + ln), P("Under " + ln)
            if o <= 0 and u <= 0:
                continue
            if _tot is not None:
                # KOHERENCA: ana detyrohet nga golat e skorit të parashikuar (kurrë kundër vetes)
                side = ("Over " + ln) if _tot > float(ln) else ("Under " + ln)
                if P(side) > 0:
                    aligned.append(side)
            else:
                aligned.append("Over " + ln if o >= u else "Under " + ln)
    if "gg" in grupet_lejuara and (P("GG") > 0 or P("NG") > 0):
        if _pr:
            # KOHERENCA: GG vetëm nëse skori parashikon gol nga të dy; ndryshe NG
            gg_m = "GG" if (_pr[0] > 0 and _pr[1] > 0) else "NG"
            if P(gg_m) > 0:
                aligned.append(gg_m)
        else:
            aligned.append("GG" if P("GG") >= P("NG") else "NG")

    legs = []
    for m in aligned:
        prob = P(m)
        if prob <= 0:
            continue
        od_real = None
        if m in odds:
            try:
                od_real = float(odds[m])
            except Exception:
                od_real = None
        od = od_real if (od_real and od_real > 1) else round(1.0 / prob, 2)
        legs.append({"market": m, "prob": prob, "koef": round(od, 2), "grup": _grupi_tregut(m)})

    # ── TREGJE TË REJA: Rezultati i Saktë, HT/FT, AH ──
    _dist_tot = sum(float(v or 0) for v in dist_gola.values()) if dist_gola else 0.0

    # Rezultati i Saktë (CS)
    if "cs" in grupet_lejuara:
        sc = (p.get("rezultati_sakt") or "").strip()
        if sc and "-" in sc:
            prob_cs = float(dist_gola.get(sc, 0) or 0)
            if _dist_tot > 0:
                prob_cs = prob_cs / _dist_tot
            if prob_cs > 0:
                cs_odds = odds.get("CS") or {}
                od_real = cs_odds.get(sc)
                try:
                    od_real = float(od_real) if od_real else None
                except Exception:
                    od_real = None
                od = od_real if (od_real and od_real > 1) else round(1.0 / max(prob_cs, 0.001), 2)
                legs.append({"market": "CS " + sc, "prob": round(prob_cs, 4), "koef": round(od, 2), "grup": "cs"})

    # HT/FT — KOHERENT: FT detyrohet = shenja e skorit të parashikuar; HT = shenja e skor_ht (nëse ka).
    # Kurrë "1/1" kur parashikimi është 1-1 (barazim). Nëse s'ka qelizë koherente → pa leg HT/FT.
    if "htft" in grupet_lejuara:
        htft = {k: v for k, v in (tregjet.get("ht_ft") or {}).items() if "/" in str(k)}
        if isinstance(htft, dict) and htft:
            _ht_pr = _parse_score(str(tregjet.get("skor_ht") or ""))
            _ht_shenja = None
            if _ht_pr:
                _ht_shenja = "1" if _ht_pr[0] > _ht_pr[1] else ("2" if _ht_pr[0] < _ht_pr[1] else "X")
            def _hf_koherent(cell):
                pj = str(cell).split("/")
                if len(pj) != 2:
                    return False
                ht_p, ft_p = pj[0].strip(), pj[1].strip()
                if _pr and ft_p != fav:
                    return False              # FT kundër parashikimit → i ndaluar
                if _ht_shenja and ht_p != _ht_shenja:
                    return False              # HT kundër parashikimit të pjesës → i ndaluar
                return True
            koherent = {k: v for k, v in htft.items() if _hf_koherent(k)}
            if koherent:
                best_k = max(koherent, key=lambda k: float(koherent.get(k, 0) or 0))
                prob_hf = float(koherent.get(best_k, 0) or 0)
                if prob_hf > 0:
                    od = round(1.0 / prob_hf, 2)
                    legs.append({"market": "HT/FT " + best_k, "prob": round(prob_hf, 4), "koef": round(od, 2), "grup": "htft"})

    # AH — vetëm te favoriti (jo barazim), linja sipas margjinës
    if "ah" in grupet_lejuara and fav in ("1", "2") and dist_gola:
        ah_odds = odds.get("AH") or {}
        side = "Home" if fav == "1" else "Away"
        hcap = 1.5 if _dominim else 0.5
        prob_ah = _prob_ah(dist_gola, side, hcap, _dist_tot)
        if prob_ah > 0:
            line_key = side + " -" + str(hcap)
            od_real = ah_odds.get(line_key)
            try:
                od_real = float(od_real) if od_real else None
            except Exception:
                od_real = None
            od = od_real if (od_real and od_real > 1) else round(1.0 / prob_ah, 2)
            legs.append({"market": "AH " + side + " -" + str(hcap), "prob": round(prob_ah, 4), "koef": round(od, 2), "grup": "ah"})

    # ── HT si MINI-FT — KOHERENT me skorin HT të parashikuar (identiteti i pjesës së parë) ──
    if "ht" in grupet_lejuara:
        def _addht(m):
            pr = P(m)
            if pr > 0:
                legs.append({"market": m, "prob": round(pr, 4), "koef": round(1.0 / pr, 2), "grup": "ht"})
        _ht_pr2 = _parse_score(str(tregjet.get("skor_ht") or ""))
        if _ht_pr2:
            _hs = "1" if _ht_pr2[0] > _ht_pr2[1] else ("2" if _ht_pr2[0] < _ht_pr2[1] else "X")
            _addht("HT " + _hs)
            _dc_map = {"1": ("1X", "12"), "X": ("1X", "X2"), "2": ("X2", "12")}
            _dc_koh = [("HT " + d, P("HT " + d)) for d in _dc_map[_hs] if P("HT " + d) > 0]
            if _dc_koh:
                _addht(max(_dc_koh, key=lambda x: x[1])[0])
            _ht_tot = _ht_pr2[0] + _ht_pr2[1]
            _addht("HT Over 0.5" if _ht_tot > 0 else "HT Under 0.5")
            _addht("HT GG" if (_ht_pr2[0] > 0 and _ht_pr2[1] > 0) else "HT NG")
            _ht_cs_key = "HT CS " + str(_ht_pr2[0]) + "-" + str(_ht_pr2[1])
            if P(_ht_cs_key) > 0:
                _addht(_ht_cs_key)
        else:
            # Pa parashikim HT në DB: qeliza më e mundshme e modelit (s'ka parashikim për ta kundërshtuar)
            _ht1x2 = max([("HT 1", P("HT 1")), ("HT X", P("HT X")), ("HT 2", P("HT 2"))], key=lambda x: x[1])
            if _ht1x2[1] > 0:
                _addht(_ht1x2[0])
            _htdc = max([("HT 1X", P("HT 1X")), ("HT X2", P("HT X2")), ("HT 12", P("HT 12"))], key=lambda x: x[1])
            if _htdc[1] > 0:
                _addht(_htdc[0])
            if P("HT Over 0.5") >= P("HT Under 0.5"):
                _addht("HT Over 0.5")
            else:
                _addht("HT Under 0.5")
            if P("HT GG") >= P("HT NG"):
                _addht("HT GG")
            else:
                _addht("HT NG")
            _htcs = [(k, float(v or 0)) for k, v in tregjet.items() if str(k).startswith("HT CS ")]
            if _htcs:
                _hb = max(_htcs, key=lambda x: x[1])
                if _hb[1] > 0:
                    _addht(_hb[0])

    # ── RRJETA E SIGURISË: asnjë leg FT nuk del kurrë kundër skorit të parashikuar ──
    if _pr:
        legs = [l for l in legs if l["grup"] not in ("1x2", "dc", "ou", "gg") or _treg_koherent(l["market"], _pr)]

    return legs


def _opsionet_ndeshje(p, grupet_lejuara):
    """Opsionet për një ndeshje: legs të vetme + double-options (cross-group, korrelacion real nga dist_gola)."""
    legs = _legs_gjenerator(p, grupet_lejuara)
    if not legs:
        return []
    dist = p.get("dist_gola") or {}
    opsionet = [{"pjeset": [l["market"]], "prob": l["prob"], "koef": l["koef"]} for l in legs]
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            a, b = legs[i], legs[j]
            if a["grup"] == b["grup"]:
                continue   # vetëm cross-group (rezultat + O/U + GG)
            if a["grup"] in ("cs", "htft", "ah", "ht") or b["grup"] in ("cs", "htft", "ah", "ht"):
                continue   # CS/HT-FT/AH/HT korrelohen me 1X2/O/U -> vetëm single-leg (jo combo i fryrë)
            jp = _joint_prob(dist, [a["market"], b["market"]])
            if jp is None:
                jp = a["prob"] * b["prob"]
            if jp < GEN_DOPT_FLOOR:
                continue
            opsionet.append({"pjeset": [a["market"], b["market"]],
                             "prob": round(jp, 4), "koef": round(a["koef"] * b["koef"], 2)})
    return opsionet


def _gjenero_target_v2(pool, nr, koef_target, grupet_lejuara, tol=0.06):
    """nr ndeshje; DP që MAKSIMIZON probabilitetin total me produkt koeficienti në bandën [target±tol].
    Shpërndarje e drejtë (jo një leg i vetëm i rrezikshëm), gjithmonë anë e favorizuar."""
    matches = []
    for p in pool:
        ops = _opsionet_ndeshje(p, grupet_lejuara)
        if not ops:
            continue
        ops.sort(key=lambda o: o["prob"], reverse=True)
        ops = ops[:24]   # kufizo për shpejtësi
        matches.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"), "parashikimi": p.get("rezultati_sakt"),
                        "liga": p.get("liga_emri"), "ops": ops, "conf": ops[0]["prob"]})
    if len(matches) < nr:
        return None
    matches.sort(key=lambda m: m["conf"], reverse=True)
    perdor = matches[:nr]

    lo, hi = koef_target * (1 - tol), koef_target * (1 + tol)
    W = 0.03   # gjerësia e bucket-it në hapësirën log të koeficientit
    # DP: bucket(log-koef) -> (logprob_max, rruga e indekseve të opsioneve)
    dp = {0: (0.0, [])}
    for m in perdor:
        ndp = {}
        for b, (lp, path) in dp.items():
            for oi, op in enumerate(m["ops"]):
                nb = b + int(round(math.log(op["koef"]) / W))
                nlp = lp + math.log(max(op["prob"], 1e-9))
                cur = ndp.get(nb)
                if cur is None or nlp > cur[0]:
                    ndp[nb] = (nlp, path + [oi])
        dp = ndp
        if len(dp) > 4000:   # prune: mbaj bucket-et më të mira
            top = sorted(dp.items(), key=lambda kv: kv[1][0], reverse=True)[:4000]
            dp = dict(top)

    lo_b, hi_b = math.log(lo) / W, math.log(hi) / W
    ne_bande = [(lp, path) for b, (lp, path) in dp.items() if lo_b - 0.5 <= b <= hi_b + 0.5]
    if ne_bande:
        _, path = max(ne_bande, key=lambda x: x[0])
    else:
        tb = math.log(koef_target) / W
        b = min(dp.keys(), key=lambda x: abs(x - tb))
        path = dp[b][1]

    ndeshjet = []; ktot = 1.0; ptot = 1.0
    for m, oi in zip(perdor, path):
        op = m["ops"][oi]
        ktot *= op["koef"]; ptot *= op["prob"]
        ndeshjet.append({"id": m.get("id"), "ndeshja": m["ndeshja"], "tregu": " + ".join(op["pjeset"]),
                         "prob": round(op["prob"], 4), "koef": op["koef"],
                         "parashikimi": m.get("parashikimi"), "liga": m.get("liga")})
    return {"ndeshjet": ndeshjet, "koef_total": round(ktot, 2),
            "prob": round(ptot, 4), "nr": len(ndeshjet)}


def _gjenero_skedine_fleksibel(pool, nr_min, nr_max, koef_target, grupet_lejuara, tol=0.06):
    """Provon çdo numër ndeshjesh; kthen skedinën NË BANDË me probabilitetin më të lartë (ose më të afërtën)."""
    e_mundur = len([p for p in pool if _opsionet_ndeshje(p, grupet_lejuara)])
    nr_max = min(nr_max, e_mundur)
    if nr_max < nr_min:
        return None
    lo, hi = koef_target * (1 - tol), koef_target * (1 + tol)
    ne_band = []; te_gjitha = []
    for n in range(nr_min, nr_max + 1):
        s = _gjenero_target_v2(pool, n, koef_target, grupet_lejuara, tol)
        if not s:
            continue
        te_gjitha.append(s)
        if lo <= s["koef_total"] <= hi:
            ne_band.append(s)
    if ne_band:
        best = max(ne_band, key=lambda s: s["prob"])       # më e mundshmja brenda bandës
        best["arritur"] = True
        return best
    if te_gjitha:
        mbi = [s for s in te_gjitha if s["koef_total"] >= lo]   # e arrijnë ose e TEJKALOJNË targetin
        if mbi:
            best = min(mbi, key=lambda s: s["koef_total"])       # tejkalimi më i vogël (më afër targetit nga lart)
            best["arritur"] = True                               # arritur/tejkaluar = sukses (pa paralajmërim)
        else:
            best = min(te_gjitha, key=lambda s: abs(s["koef_total"] - koef_target))  # më e afërta (NËN target)
            best["arritur"] = False                              # vetëm nën-target => paralajmërim
        return best
    return None


# ============ LIMITET & PAGESAT (VIP COMBO / GENERATE TICKET) ============
# VIP: 1 herë falas/ditë secilin, pastaj bllokohet deri nesër.
# Jo-VIP: paguan nga portofoli për çdo gjenerim.
CMIM_VIPCOMBO = 30.0   # jo-VIP paguan kaq për 1 VIP Combo
CMIM_GENERATE = 10.0   # jo-VIP paguan kaq për 1 Generate Ticket

# PRAGU I BESUESHMËRISË PËR VIP: abonentët VIP marrin VETËM ndeshje me besueshmëri
# >= këtë vlerë (pretendimi "75–92%" te veçoritë VIP). Një ndeshje me 65% nuk i
# gjenerohet VIP-it. Jo-VIP-i (që paguan) merr të gjitha ndeshjet pa këtë filtër.
# Drini: ule në 70.0 nëse del shumë restriktive (pak ndeshje kualifikohen).
BESU_PRAG_VIP = 75.0
BESU_PRAG_VIPCOMBO = 70.0   # kufi më i ulët vetëm për VIP Combo

def _nm_key(p):
    return (p.get("ndeshja") or "").strip().lower()


def _id_set(s):
    """Bashkësi id-sh (int) nga string me presje, p.sh. '123,456'."""
    out = set()
    for x in (s or "").replace(" ", "").split(","):
        if x:
            try: out.add(int(x))
            except Exception: pass
    return out


def _filtro_besu(pool, prag=BESU_PRAG_VIP):
    """Mban vetëm ndeshjet me besueshmëri >= prag. Përdoret për skedinat VIP."""
    out = []
    for p in pool:
        b = p.get("besueshmeria")
        try:
            if b is not None and float(b) >= prag:
                out.append(p)
        except (TypeError, ValueError):
            pass
    return out

def _kontrollo_te_drejten(email: str, produkt: str, cmimi: float, paguaj: bool = False):
    """KONTROLLON pa ndryshuar asgjë (pa zbritur para, pa shënuar datën).
    produkt: 'vipcombo' ose 'generate'.
    Logjikë: VIP merr 1 gjenerim FALAS/ditë; pasi e përdor, mund të gjenerojë
    përsëri DUKE PAGUAR (njësoj si jo-VIP). 'paguaj=True' = përdoruesi e konfirmoi pagesën.
    Kthen dict {ok, is_vip, falas, kerko_pagese, mungojne_kredite, portofoli, cmimi, arsye}."""
    fusha = "vipcombo_fundit" if produkt == "vipcombo" else "generate_fundit"
    emri = "VIP Combo" if produkt == "vipcombo" else "Generate Ticket"
    dt = _data_lokale(0)
    is_vip = _eshte_vip(email)
    portofoli = 0.0
    fundit = None
    try:
        r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,{fusha}",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        if r.status_code == 200 and r.json():
            row = r.json()[0]
            portofoli = float(row.get("portofoli", 0) or 0)
            fundit = row.get(fusha)
    except Exception:
        pass

    # 1) VIP → akses i PAKUFIZUAR, falas (sa here te doje, cdo dite)
    if is_vip:
        return {"ok": True, "is_vip": True, "falas": True,
                "portofoli": portofoli, "cmimi": cmimi, "arsye": ""}

    # 2) Jo-VIP qe KA PAGUAR tashme sot → akses i pakufizuar sot, FALAS
    if fundit == dt:
        return {"ok": True, "is_vip": False, "falas": True,
                "portofoli": portofoli, "cmimi": cmimi, "arsye": ""}

    # 3) Jo-VIP, s'ka paguar sot, pa kredite te mjaftueshme
    if portofoli < cmimi:
        return {"ok": False, "is_vip": False, "falas": False, "mungojne_kredite": True,
                "portofoli": portofoli, "cmimi": cmimi,
                "kod": "PPM_NO_CREDITS", "arsye": f"{emri}: akses i pakufizuar për sot ${int(cmimi)}. Nuk ke kredite të mjaftueshme — mbush portofolin."}

    # 4) Jo-VIP, ka kredite, s'ka konfirmuar → kerko konfirmim (1 here, pastaj pa fund)
    if not paguaj:
        return {"ok": False, "is_vip": False, "falas": False, "kerko_pagese": True,
                "portofoli": portofoli, "cmimi": cmimi,
                "kod": "PPM_PAY_ONCE", "arsye": f"Paguaj ${int(cmimi)} një herë → gjenero PA FUND sot."}

    # 5) Konfirmuar + ka kredite → vazhdo (paguhet 1 here sot)
    return {"ok": True, "is_vip": False, "falas": False,
            "portofoli": portofoli, "cmimi": cmimi, "arsye": ""}

def _konfirmo_perdorimin(email: str, produkt: str, cmimi: float, is_vip: bool, portofoli: float, falas: bool = False):
    """THIRRET VETËM PAS gjenerimit të suksesshëm.
    VIP ose 'falas' (pagoi tashme sot) → s'ndryshon asgjë (akses i pakufizuar).
    Jo-VIP hera e PARE sot → zbrit çmimin DHE shëno datën (day-pass → pa fund sot)."""
    fusha = "vipcombo_fundit" if produkt == "vipcombo" else "generate_fundit"
    dt = _data_lokale(0)
    try:
        if is_vip or falas:
            return portofoli   # akses i pakufizuar — pa pagese te dyte
        ri = round(portofoli - cmimi, 2)
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                       headers=SUPABASE_SERVICE_HEADERS,
                       json={"portofoli": ri, fusha: dt}, timeout=8)
        _FULL_ACCESS_CACHE.pop(str(email).lower().strip(), None)   # akses ndryshoi → pastro cache
        return ri
    except Exception:
        return portofoli


# ============ LARMIA E GJENERIMEVE (NO-REPEAT PER PERDORUES) ============
# Mban id-te e ndeshjeve te dhena SOT cdo perdoruesi, ndaras per produkt
# (generate / vipcombo). Rivendoset vete cdo dite. Kolona: users.gen_historik (jsonb).
def _lexo_gen_historik(email):
    try:
        r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=gen_historik",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=6)
        if r.status_code == 200 and r.json():
            gh = r.json()[0].get("gen_historik") or {}
            if isinstance(gh, str):
                try: gh = json.loads(gh)
                except Exception: gh = {}
            if isinstance(gh, dict):
                return gh
    except Exception:
        pass
    return {}

def _shkruaj_gen_historik(email, gh):
    try:
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                       headers=SUPABASE_SERVICE_HEADERS,
                       json={"gen_historik": json.dumps(gh, ensure_ascii=False)}, timeout=6)
    except Exception:
        pass

def _merr_given_ids(email, produkt):
    """Id-te e ndeshjeve te dhena SOT per kete produkt (boshe nese dita ndryshoi)."""
    dt = _data_lokale()
    gh = _lexo_gen_historik(email)
    if gh.get("data") != dt:
        return []
    return [int(x) for x in (gh.get(produkt) or []) if x is not None]

def _ruaj_given_ids(email, produkt, ids_te_reja):
    """Shton id-te e reja te lista e SOTME e produktit (rifillon nese dita ndryshoi)."""
    dt = _data_lokale()
    gh = _lexo_gen_historik(email)
    if gh.get("data") != dt:
        gh = {"data": dt}
    ekz = [int(x) for x in (gh.get(produkt) or []) if x is not None]
    for i in ids_te_reja:
        try:
            ii = int(i)
            if ii not in ekz:
                ekz.append(ii)
        except Exception:
            pass
    gh["data"] = dt
    gh[produkt] = ekz
    _shkruaj_gen_historik(email, gh)

def _rivendos_given(email, produkt):
    """Zeron listen e produktit per sot (rifillon ciklin kur shterohet pool-i)."""
    dt = _data_lokale()
    gh = _lexo_gen_historik(email)
    if gh.get("data") != dt:
        gh = {"data": dt}
    gh["data"] = dt
    gh[produkt] = []
    _shkruaj_gen_historik(email, gh)

print("LARMIA: gjurmimi i gjenerimeve aktiv (users.gen_historik) — Generate + VIP Combo")


# ============ SKEDINA IME (regjistri i skedinave te gjeneruara) ============
SKEDINA_IME_URL = f"{SUPABASE_BASE}/rest/v1/skedina_ime"

def _leg_goditi(rh, ra, tregu):
    """Goditja e nje leg-u; mbulon tregje te kombinuara me '+' (psh '1 + Over 2.5')."""
    if rh is None:
        return False
    pjeset = [t.strip() for t in str(tregu).split("+") if t.strip()]
    return bool(pjeset) and all(_score_satisfies(rh, ra, p) for p in pjeset)

def _nenshkrim_ticket(sked):
    try:
        legs = sorted(f"{n.get('id')}:{n.get('tregu')}" for n in (sked.get("ndeshjet") or []))
        return "T:" + hashlib.md5("|".join(legs).encode()).hexdigest()[:16]
    except Exception:
        return ""

def _nenshkrim_combo(ndeshjet, nr, rez):
    try:
        ids = sorted(str(n.get("id")) for n in (ndeshjet or []))
        return "C:" + hashlib.md5(f"{nr}:{rez}:{chr(124).join(ids)}".encode()).hexdigest()[:16]
    except Exception:
        return ""

def _ekziston_nenshkrim(email, nenshkrim):
    """A ka tashme nje skedine me kete nenshkrim sot (per anti-identik, Hapi 3)."""
    if not nenshkrim:
        return False
    try:
        dt = _data_lokale()
        r = requests.get(f"{SKEDINA_IME_URL}?email=eq.{email}&nenshkrim=eq.{nenshkrim}&data=eq.{dt}&select=id",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=6)
        return r.status_code == 200 and len(r.json()) > 0
    except Exception:
        return False

def _ruaj_skedine_ime(email, tipi, permbajtja, nenshkrim):
    try:
        hdr = dict(SUPABASE_SERVICE_HEADERS)
        hdr["Prefer"] = "return=minimal"
        requests.post(SKEDINA_IME_URL, headers=hdr,
                      json={"email": email, "tipi": tipi, "permbajtja": permbajtja,
                            "nenshkrim": nenshkrim, "statusi": "pezull"}, timeout=6)
    except Exception:
        pass

def _vleso_skedina_ime(email):
    """Vlereson skedinat 'pezull' te perdoruesit kur ndeshjet kane mbaruar."""
    fund = ("FT", "AET", "PEN", "AWD", "WO")
    try:
        r = requests.get(f"{SKEDINA_IME_URL}?email=eq.{email}&statusi=eq.pezull&select=id,tipi,permbajtja",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
        for rec in rows:
            permb = rec.get("permbajtja") or {}
            if isinstance(permb, str):
                try: permb = json.loads(permb)
                except Exception: permb = {}
            ndeshjet = permb.get("ndeshjet") or []
            ids = [str(n.get("id")) for n in ndeshjet if n.get("id")]
            if not ids:
                continue
            pr = requests.get(f"{SUPABASE_URL_PREDS}?id=in.({','.join(ids)})&select=id,statusi,rezultati",
                              headers=SUPABASE_SERVICE_HEADERS, timeout=8)
            mm = {str(p["id"]): p for p in (pr.json() if pr.status_code == 200 else [])}
            if not all(mm.get(i, {}).get("statusi") in fund for i in ids):
                continue
            reale = {}
            for i in ids:
                ps = _parse_score(mm.get(i, {}).get("rezultati") or "")
                reale[i] = ps if ps else (None, None)
            if rec.get("tipi") == "ticket":
                detaje = []; te_gjitha = True
                for n in ndeshjet:
                    i = str(n.get("id"))
                    rh, ra = reale.get(i, (None, None))
                    hit = _leg_goditi(rh, ra, n.get("tregu"))
                    if not hit: te_gjitha = False
                    rshf = f"{rh}-{ra}" if rh is not None else "—"
                    detaje.append({**n, "real": rshf, "goditi": hit})
                statusi = "fituese" if te_gjitha else "humbur"
                fituesi = {"ndeshjet": detaje}
            elif rec.get("tipi") == "combonde":
                # Combo Ndeshjesh: çdo skedinë = nën-grup 2-3 ndeshjesh; mapo sipas EMRIT.
                by_name = {}
                for n in ndeshjet:
                    by_name[(n.get("ndeshja") or "").strip()] = reale.get(str(n.get("id")), (None, None))
                kombinimet = permb.get("kombinimet") or []
                fitues_idx = []
                for ki, k in enumerate(kombinimet):
                    ok = True
                    for leg in (k.get("skedina") or []):
                        rh, ra = by_name.get((leg.get("ndeshja") or "").strip(), (None, None))
                        real_norm = f"{rh}-{ra}" if rh is not None else None
                        if str(leg.get("skor", "")).replace(" ", "") != (real_norm or "__no__"):
                            ok = False; break
                    if ok: fitues_idx.append(ki)
                statusi = "fituese" if fitues_idx else "humbur"
                reale_shf = {i: (f"{v[0]}-{v[1]}" if v[0] is not None else "—") for i, v in reale.items()}
                fituesi = {"fitues_idx": fitues_idx, "reale": reale_shf}
            else:
                kombinimet = permb.get("kombinimet") or []
                fitues_idx = []
                for ki, k in enumerate(kombinimet):
                    sk = k.get("skedina") or []
                    ok = True
                    for j, leg in enumerate(sk):
                        n = ndeshjet[j] if j < len(ndeshjet) else {}
                        rh, ra = reale.get(str(n.get("id")), (None, None))
                        real_norm = f"{rh}-{ra}" if rh is not None else None
                        if str(leg.get("skor", "")).replace(" ", "") != (real_norm or "__no__"):
                            ok = False; break
                    if ok: fitues_idx.append(ki)
                statusi = "fituese" if fitues_idx else "humbur"
                reale_shf = {i: (f"{v[0]}-{v[1]}" if v[0] is not None else "—") for i, v in reale.items()}
                fituesi = {"fitues_idx": fitues_idx, "reale": reale_shf}
            requests.patch(f"{SKEDINA_IME_URL}?id=eq.{rec['id']}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"statusi": statusi, "fituesi": fituesi}, timeout=6)
    except Exception as e:
        print(f"[SKEDINA_IME] vleresim gabim: {e}")

@app.get("/api/skedina-ime")
def skedina_ime_lista(email: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email)
    """Kthen skedinat e ruajtura te perdoruesit (me te rejat te parat), pasi vlereson pezullet."""
    if not email or not email.strip():
        return {"sukses": False, "kod": "EMAIL_MISSING", "arsye": "Mungon email."}
    _vleso_skedina_ime(email)
    try:
        r = requests.get(f"{SKEDINA_IME_URL}?email=eq.{email}"
                         f"&select=id,tipi,data,krijuar,permbajtja,statusi,fituesi&order=krijuar.desc&limit=50",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    return {"sukses": True, "skedinat": rows}


@app.post("/api/skedina/ruaj")
def ruaj_skedinen_e_zgjedhur(payload: dict, authorization: str = Header(None)):
    """Ruan MANUALISHT skedinen/combo-n qe perdoruesi ZGJEDH te luaje -> Bileta Ime."""
    email = _email_auth(authorization, payload.get("email"))
    tipi = payload.get("tipi")
    permb = payload.get("permbajtja") or {}
    if not email or tipi not in ("ticket", "combo", "combonde") or not permb:
        return {"sukses": False, "kod": "DATA_MISSING", "arsye": "Të dhëna mungojnë."}
    if tipi == "ticket":
        nen = _nenshkrim_ticket(permb)
    elif tipi == "combonde":
        _legs = []
        for k in (permb.get("kombinimet") or []):
            for s in (k.get("skedina") or []):
                _legs.append(f"{s.get('ndeshja')}|{s.get('skor')}")
        nen = hashlib.md5(("combonde:" + ";".join(sorted(set(_legs)))).encode()).hexdigest()
    else:
        nen = _nenshkrim_combo(permb.get("ndeshjet") or [], permb.get("nr", 2), permb.get("rez", 4))
    # mos ruaj dy here te njejten
    try:
        ek = requests.get(f"{SKEDINA_IME_URL}?email=eq.{email}&nenshkrim=eq.{nen}&select=id&limit=1",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=6)
        if ek.status_code == 200 and ek.json():
            return {"sukses": True, "kod": "ALREADY_SAVED", "mesazhi": "Tashmë e ruajtur", "dyfishim": True}
    except Exception:
        pass
    if "tipi" not in permb:
        permb = dict(permb); permb["tipi"] = tipi
    _ruaj_skedine_ime(email, tipi, permb, nen)
    return {"sukses": True, "kod": "SAVED_OK", "mesazhi": "U ruajt te Bileta Ime ✓"}


def _tregu_kategoria(par):
    """Kategoria e tregut nga teksti i parashikimit."""
    import re as _re
    x = str(par or "").strip()
    if x.upper().startswith("HT/FT"):
        return "HT/FT"
    if x.startswith("Over") or x.startswith("Under"):
        return "O/U"
    if x in ("GG", "NG"):
        return "GG/NG"
    if x in ("1", "X", "2"):
        return "1X2"
    if x in ("1X", "12", "X2"):
        return "DC"
    if x.upper().startswith("AH") or "Handicap" in x:
        return "AH"
    if _re.match(r"^\d+\s*-\s*\d+$", x):
        return "CS"
    return "?"


def _rendit_pozicionet(pool, key_nd="ndeshja", key_lg="liga_emri"):
    """Pozicionet sipas besueshmerise (zbritese): (gpos, gtot, lpos, ltot)."""
    ranked = sorted([p for p in pool if p.get("besueshmeria") is not None],
                    key=lambda p: float(p.get("besueshmeria") or 0), reverse=True)
    gpos = {p.get(key_nd): i + 1 for i, p in enumerate(ranked)}
    gtot = len(ranked)
    by_lg = {}
    for p in ranked:
        by_lg.setdefault(p.get(key_lg), []).append(p)
    lpos, ltot = {}, {}
    for lg, items in by_lg.items():
        for i, p in enumerate(items):
            lpos[p.get(key_nd)] = i + 1
            ltot[p.get(key_nd)] = len(items)
    return gpos, gtot, lpos, ltot


def _ruaj_gjenero_legs(email, sked, pool):
    """Ruan kembet e nje skedine Gjenero te skedina_gjenero."""
    try:
        legs = (sked or {}).get("ndeshjet") or []
        if not legs:
            return
        pmap = {p.get("ndeshja"): p for p in pool}
        gpos, gtot, lpos, ltot = _rendit_pozicionet(pool)
        sid = "G:" + hashlib.md5(("|".join(str(l.get("ndeshja", "")) for l in legs) + os.urandom(6).hex()).encode()).hexdigest()[:16]
        rows = []
        for i, l in enumerate(legs):
            nd = l.get("ndeshja")
            pm = pmap.get(nd, {})
            pj = l.get("pjeset") or []
            par = pj[0] if pj else ""
            rows.append({
                "skedina_id": sid, "user_email": (email or None),
                "pozicioni_leg": i + 1, "total_legs": len(legs),
                "match_id": (str(pm.get("id")) if pm.get("id") is not None else None),
                "ndeshja": nd, "liga": l.get("liga"),
                "pozicioni_global": gpos.get(nd), "total_global": gtot,
                "pozicioni_liga": lpos.get(nd), "total_liga": ltot.get(nd),
                "tregu": _tregu_kategoria(par), "parashikimi": par,
                "koeficienti": l.get("koef"), "besueshmeria": pm.get("besueshmeria"),
            })
        requests.post(f"{SUPABASE_BASE}/rest/v1/skedina_gjenero",
                      headers=SUPABASE_SERVICE_HEADERS, json=rows, timeout=10)
    except Exception as e:
        print(f"⚠️ Ruajtja skedina_gjenero deshtoi: {e}")


def _ruaj_vip_legs(email, ndeshjet, pool):
    """Ruan ndeshjet e nje VIP Combo te skedina_vip (set skoresh)."""
    try:
        if not ndeshjet:
            return
        pmap = {p.get("ndeshja"): p for p in pool}
        gpos, gtot, lpos, ltot = _rendit_pozicionet(pool)
        sid = "V:" + hashlib.md5(("|".join(str(n.get("ndeshja", "")) for n in ndeshjet) + os.urandom(6).hex()).encode()).hexdigest()[:16]
        rows = []
        for i, n in enumerate(ndeshjet):
            nd = n.get("ndeshja")
            pm = pmap.get(nd, {})
            rezt = n.get("rezultatet") or []
            skoret = "|".join(str(r.get("skor", "")) for r in rezt)
            koef0 = (rezt[0].get("koef") if rezt else None)
            rows.append({
                "skedina_id": sid, "user_email": (email or None),
                "pozicioni_leg": i + 1, "total_legs": len(ndeshjet),
                "match_id": (str(n.get("id")) if n.get("id") is not None else None),
                "ndeshja": nd, "liga": n.get("liga_emri"),
                "pozicioni_global": gpos.get(nd), "total_global": gtot,
                "pozicioni_liga": lpos.get(nd), "total_liga": ltot.get(nd),
                "tregu": "CS", "parashikimi": skoret,
                "koeficienti": koef0, "besueshmeria": pm.get("besueshmeria"),
            })
        requests.post(f"{SUPABASE_BASE}/rest/v1/skedina_vip",
                      headers=SUPABASE_SERVICE_HEADERS, json=rows, timeout=10)
    except Exception as e:
        print(f"⚠️ Ruajtja skedina_vip deshtoi: {e}")


@app.get("/api/ndeshjet_gjenerueshme")
def ndeshjet_gjenerueshme(email: str = "", authorization: str = Header(None)):
    """Lista e ndeshjeve të disponueshme për zgjedhje/përjashtim (autocomplete)."""
    _email_auth(authorization, email, strict=False)
    dt = _data_lokale(0); dt_neser = _data_lokale(1)
    url = (f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ora,liga_emri,data"
           f"&best_bet=not.is.null&dist_gola=not.is.null&rezultati_sakt=not.is.null&tregjet=not.is.null"
           f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&order=id.desc&limit=300")
    try:
        r = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    seen = set(); out = []
    for p in rows:
        i = p.get("id")
        if i in seen: continue
        seen.add(i)
        out.append({"id": i, "ndeshja": p.get("ndeshja"), "ora": p.get("ora"), "liga": p.get("liga_emri")})
    return {"ndeshjet": out}


@app.get("/api/gjenero")
def gjenero_skedine_vip(email: str = "", nr: int = 4, nr_max: int = 0, koef: float = 20.0, tregjet: str = "1x2,ou,gg", liga: str = "", paguaj: int = 0, perjashto: str = "", vetem: str = "", perjashto_emra: str = "", vetem_emra: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email)
    if not email or not email.strip():
        return {"sukses": False, "kod": "LOGIN_FIRST", "arsye": "Hyr së pari në llogari."}
    _drejta = _kontrollo_te_drejten(email, "generate", CMIM_GENERATE, bool(paguaj))
    if not _drejta["ok"]:
        return {"sukses": False, "bllokuar": True,
                "kerko_pagese": _drejta.get("kerko_pagese", False),
                "mungojne_kredite": _drejta.get("mungojne_kredite", False),
                "arsye": _drejta["arsye"],
                "portofoli": _drejta["portofoli"], "is_vip": _drejta["is_vip"], "cmimi": CMIM_GENERATE}
    nr = max(2, min(15, int(nr)))
    nr_max = int(nr_max) if nr_max else nr
    nr_max = max(nr, min(15, nr_max))
    koef = max(2.0, min(3000.0, float(koef)))
    grupet = [g.strip().lower() for g in tregjet.split(",") if g.strip()]
    grupet = [g for g in grupet if g in ("1x2", "dc", "ou", "gg", "cs", "htft", "ah", "ht")]
    if not grupet:
        grupet = ["1x2", "ou", "gg"]

    gen_url = (f"{SUPABASE_URL_PREDS}?select=id,ndeshja,liga_emri,best_bet,tregjet,odds_reale,dist_gola,rezultati_sakt,besueshmeria"
               f"&best_bet=not.is.null&dist_gola=not.is.null&rezultati_sakt=not.is.null&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&order=id.desc&limit=300")
    if liga and liga.strip():
        gen_url += f"&liga_emri=eq.{requests.utils.quote(liga.strip(), safe='')}"
    res = requests.get(gen_url, headers=SUPABASE_SERVICE_HEADERS)
    pool_plot = [p for p in (res.json() if res.status_code == 200 else []) if p.get("tregjet")]
    _perj = _id_set(perjashto); _vet = _id_set(vetem)
    _perj_em = {(x or "").strip().lower() for x in (perjashto_emra or "").split("|") if x.strip()}
    _vet_em = {(x or "").strip().lower() for x in (vetem_emra or "").split("|") if x.strip()}
    _manual = bool(_vet or _vet_em)
    if _manual:
        _kane = {_nm_key(p) for p in pool_plot}
        _mung = [x for x in _vet_em if x not in _kane]
        if _mung:
            try:
                _or = ",".join("ndeshja.ilike." + requests.utils.quote(x, safe='') for x in _mung)
                _r2 = requests.get(f"{SUPABASE_URL_PREDS}?select=id,ndeshja,liga_emri,best_bet,tregjet,odds_reale,dist_gola,rezultati_sakt,besueshmeria&or=({_or})&limit=50", headers=SUPABASE_SERVICE_HEADERS, timeout=8)
                for _p in (_r2.json() if _r2.status_code == 200 else []):
                    if _p.get("tregjet") and _nm_key(_p) not in _kane:
                        pool_plot.append(_p); _kane.add(_nm_key(_p))
            except Exception:
                pass
        pool_plot = [p for p in pool_plot if p.get("id") in _vet or _nm_key(p) in _vet_em]
    if _perj or _perj_em:
        pool_plot = [p for p in pool_plot if p.get("id") not in _perj and _nm_key(p) not in _perj_em]
    pool_hi = pool_plot if _manual else _filtro_besu(pool_plot)   # manual: pikërisht ndeshjet e zgjedhura (pa filtër)

    _mkts = [m for m in (tregjet or "").lower().replace(" ", "").split(",") if m]
    _prod_key = "gen:" + (",".join(sorted(set(_mkts))) or "default")   # perjashtim per market-kombinim
    given = set() if _manual else _merr_given_ids(email, _prod_key)

    def _provo_gjen(pool_x):
        """Ndërton skedinë nga pool_x; rivendos 'given' dhe riprovon nëse s'del."""
        pf = [p for p in pool_x if p.get("id") not in given]
        s = _gjenero_skedine_fleksibel(pf, nr, nr_max, koef, grupet)
        rif = False
        if not s and given:
            _rivendos_given(email, _prod_key)
            s = _gjenero_skedine_fleksibel(pool_x, nr, nr_max, koef, grupet)
            rif = True
        return s, rif

    # TË DY provojnë fillimisht ndeshjet me besueshmëri >= 75 (pretendimi 75–92%)
    sked, rifilluar = _provo_gjen(pool_hi)
    pool = pool_hi
    if not sked:
        if _manual:
            _mapg = {"1x2": "1X2", "dc": "Double Chance", "ou": "Over/Under", "gg": "GG/NG", "cs": "Correct Score", "htft": "HT/FT", "ah": "AH", "ht": "Half-Time"}
            _emundur = len([p for p in pool_hi if _opsionet_ndeshje(p, grupet)])
            _disp = [_mapg[g] for g in ["1x2", "dc", "ou", "gg", "cs", "htft", "ah", "ht"] if sum(1 for p in pool_hi if _opsionet_ndeshje(p, [g])) >= nr]
            _diag = "Diag: id=[%s] emra=[%s] -> në sistem=%d, opsione=%d (duhen >=%d)." % (str(vetem)[:45], str(vetem_emra)[:60], len(pool_hi), _emundur, nr)
            _msg = ("Tregjet ku ndeshjet e zgjedhura kanë mjaft të dhëna: " + ", ".join(_disp) + ". ") if _disp else "Ndeshjet e zgjedhura s'kanë mjaft të dhëna. "
            return {"sukses": False, "arsye": _msg + _diag}
        if _drejta["is_vip"]:
            # VIP: premtim i rreptë 75–92% — pa fallback te ndeshjet e dobëta
            return {"sukses": False, "kod": "NOT_ENOUGH_CONF", "arsye": "Sot s'ka mjaft ndeshje me besueshmëri të lartë (≥75%) për këto parametra. Provo më vonë."}
        # Jo-VIP (që paguan): kalon tek ndeshjet e tjera
        sked, rifilluar = _provo_gjen(pool_plot)
        pool = pool_plot
    if not sked:
        return {"sukses": False, "kod": "NOT_ENOUGH", "arsye": "Jo mjaft ndeshje për këto parametra."}
    _porto_ri = _konfirmo_perdorimin(email, "generate", CMIM_GENERATE, _drejta["is_vip"], _drejta["portofoli"], _drejta.get("falas", False))
    if not _manual: _ruaj_given_ids(email, _prod_key, [n.get("id") for n in sked.get("ndeshjet", []) if n.get("id")])
    _ruaj_gjenero_legs(email, sked, pool)
    return {"sukses": True, "skedina": sked, "rifilluar": rifilluar,
            "portofoli": _porto_ri, "u_pagua": (not _drejta["is_vip"] and not _drejta.get("falas", False)),
            "cmimi": CMIM_GENERATE,
            "kerkesa": {"nr_min": nr, "nr_max": nr_max, "koef_target": koef, "tregjet": grupet}}


@app.get("/api/live/stats")
def live_stats(fixture: str = ""):
    """Statistikat live për një ndeshje: posedimi, gjuajtjet, këndet, rezultati, minuta, ngjyrat e skuadrave."""
    if not fixture or not API_KEY:
        return {"sukses": False, "kod": "FIXTURE_OR_KEY_MISSING", "arsye": "Mungon fixture ose API key."}
    base = "https://v3.football.api-sports.io"
    try:
        rf = requests.get(f"{base}/fixtures?id={fixture}", headers=HEADERS, timeout=12)
        fxr = rf.json().get("response", []) if rf.status_code == 200 else []
        if not fxr:
            return {"sukses": False, "kod": "MATCH_NOT_FOUND", "arsye": "Ndeshja s'u gjet."}
        fx = fxr[0]
        teams = fx.get("teams", {}) or {}
        goals = fx.get("goals", {}) or {}
        status = (fx.get("fixture", {}) or {}).get("status", {}) or {}
        idA = teams.get("home", {}).get("id"); idB = teams.get("away", {}).get("id")
        emriA = teams.get("home", {}).get("name"); emriB = teams.get("away", {}).get("name")

        rs = requests.get(f"{base}/fixtures/statistics?fixture={fixture}", headers=HEADERS, timeout=12)
        st = rs.json().get("response", []) if rs.status_code == 200 else []

        def stat_dict(team_id):
            for e in st:
                if (e.get("team", {}) or {}).get("id") == team_id:
                    return {s.get("type"): s.get("value") for s in (e.get("statistics", []) or [])}
            return {}
        sA, sB = stat_dict(idA), stat_dict(idB)

        def n(d, k):
            v = d.get(k)
            try:
                return int(v) if v is not None else 0
            except Exception:
                return 0

        def poss(d):
            v = d.get("Ball Possession")
            try:
                return int(str(v).replace("%", "").strip()) if v else None
            except Exception:
                return None
        possA = poss(sA); possB = poss(sB)
        if possA is None and possB is None:
            possA = 50
        elif possA is None:
            possA = 100 - (possB or 50)

        ng = _ngjyra_live_cache.get(str(fixture))
        if not ng:
            ng = {"A": None, "B": None}
            try:
                rl = requests.get(f"{base}/fixtures/lineups?fixture={fixture}", headers=HEADERS, timeout=12)
                lu = rl.json().get("response", []) if rl.status_code == 200 else []
                for e in lu:
                    tid = (e.get("team", {}) or {}).get("id")
                    prim = (((e.get("team", {}) or {}).get("colors", {}) or {}).get("player", {}) or {}).get("primary")
                    if prim:
                        hexc = prim if str(prim).startswith("#") else "#" + str(prim)
                        if tid == idA: ng["A"] = hexc
                        elif tid == idB: ng["B"] = hexc
                if lu:
                    _ngjyra_live_cache[str(fixture)] = ng
            except Exception:
                pass

        return {"sukses": True, "emriA": emriA, "emriB": emriB,
                "golA": goals.get("home"), "golB": goals.get("away"),
                "minuta": status.get("elapsed"), "statusi": status.get("short"),
                "ngjyraA": ng.get("A") or "#e23b3b", "ngjyraB": ng.get("B") or "#3b6fe2",
                "possA": possA, "possB": 100 - possA,
                "gjuajtjeA": n(sA, "Total Shots"), "gjuajtjeB": n(sB, "Total Shots"),
                "neporteA": n(sA, "Shots on Goal"), "neporteB": n(sB, "Shots on Goal"),
                "kenderA": n(sA, "Corner Kicks"), "kenderB": n(sB, "Corner Kicks"),
                "faullA": n(sA, "Fouls"), "faullB": n(sB, "Fouls")}
    except Exception as e:
        return {"sukses": False, "arsye": str(e)}


@app.get("/api/training/accuracy")
def training_accuracy():
    """Saktësia kumulative nga training_results (rritet me kohën)."""
    try:
        r = requests.get(
            f"{SUPABASE_URL_TRAINING}?select=hit_rezultat,hit_1x2,hit_ou25",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
        ntot = len(rows)
        if ntot == 0:
            return {"sukses": True, "total": 0, "mesazh": "Ende pa të dhëna të mbledhura."}

        def pct(k):
            c = sum(1 for x in rows if x.get(k))
            return {"sakte": c, "perqindja": round(c / ntot * 100, 1)}

        return {"sukses": True, "total": ntot,
                "rezultat_sakte": pct("hit_rezultat"),
                "fituesi_1x2": pct("hit_1x2"),
                "over_under_25": pct("hit_ou25")}
    except Exception as e:
        return {"sukses": False, "arsye": str(e)}


# ===================== TELEGRAM — NDESHJA E DITËS =====================
PICK_MARKETS = ["1", "X", "2", "Over 1.5", "Under 1.5", "Over 2.5",
                "Under 2.5", "Over 3.5", "Under 3.5", "GG", "NG"]


def _emri_tregut(m, ndeshja):
    home = away = ""
    if " - " in (ndeshja or ""):
        home, away = ndeshja.split(" - ", 1)
    harta = {"1": ("Fiton " + home).strip(), "X": "Barazim",
             "2": ("Fiton " + away).strip(),
             "GG": "Të dyja shënojnë (GG)", "NG": "Nuk shënojnë të dyja (NG)"}
    if m in harta:
        return harta[m]
    if m.startswith("Over"):
        return "Mbi " + m.split()[1] + " gola"
    if m.startswith("Under"):
        return "Nën " + m.split()[1] + " gola"
    return m


def _zgjidh_pick_ditor(data_str):
    """Gjen pick-un me besueshmërinë më të lartë (jo trivial) për një datë."""
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=ndeshja,ora,liga_emri,tregjet,odds_reale,rezultati_sakt"
            f"&data=eq.{data_str}&tregjet=not.is.null"
            f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
        best = None
        for p in rows:
            tg_ = p.get("tregjet") or {}
            od = p.get("odds_reale") or {}
            for m in PICK_MARKETS:
                try:
                    prob = float(tg_.get(m, 0) or 0)
                except Exception:
                    prob = 0.0
                if prob <= 0 or prob > 0.90:   # përjashto trivialet (gati 100%)
                    continue
                if best is None or prob > best["prob"]:
                    try:
                        koef = float(od.get(m, 0) or 0)
                    except Exception:
                        koef = 0.0
                    if koef <= 1.0:
                        koef = round(1 / prob, 2)
                    best = {"ndeshja": p.get("ndeshja"), "ora": p.get("ora"),
                            "liga": p.get("liga_emri"), "tregu": m,
                            "tregu_emri": _emri_tregut(m, p.get("ndeshja")),
                            "prob": prob, "koef": koef,
                            "parashikimi": p.get("rezultati_sakt")}
        return best
    except Exception:
        return None


def _ndertoMesazhTelegram(p):
    return ("🎁 <b>FREE PICK OF THE DAY</b> — SOCCER1X2 PRO\n\n"
            f"🏆 {p.get('liga','')}\n"
            f"🆚 <b>{p['ndeshja']}</b>\n"
            f"🕐 Time: {p.get('ora','')}\n\n"
            f"🎯 Prediction: <b>{p['tregu_emri']}</b>\n"
            f"💰 Odds: <b>{p['koef']}</b>\n\n"
            "✅ <b>High confidence</b> — a gift from our team.\n\n"
            "Maximize your profit: play with <b>COMBOS</b>, unlock the <b>Daily Ticket</b> and become <b>VIP</b>.\n"
            "👉 https://soccer1x2pro.com\n\n"
            "💎 Daily ticket with a winning combo\n"
            "💎 VIP access with premium predictions\n"
            "💎 Profit maximization\n\n"
            "📈 <b>With us, you invest.</b>\n\n"
            "⚠️ 18+ • Play responsibly")


def _zgjidh_skedine_ditore(data_str, nr=3, prob_max=0.90, koef_min=3.0):
    """Skedine ditore per Telegram: nr ndeshjet me besimin me te larte
       (tregu me i mire per secilen ndeshje). Kthen pikat + koef_total."""
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=ndeshja,ora,liga_emri,tregjet,odds_reale,rezultati_sakt,besueshmeria"
            f"&data=eq.{data_str}&tregjet=not.is.null"
            f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
        kand = []
        for p in rows:
            tg_ = p.get("tregjet") or {}
            od = p.get("odds_reale") or {}
            try:
                besu_p = float(p.get("besueshmeria")) if p.get("besueshmeria") is not None else None
            except (TypeError, ValueError):
                besu_p = None
            bm = None
            for m in PICK_MARKETS:
                try:
                    prob = float(tg_.get(m, 0) or 0)
                except Exception:
                    prob = 0.0
                if prob <= 0 or prob > prob_max:
                    continue
                if bm is None or prob > bm["prob"]:
                    try:
                        koef = float(od.get(m, 0) or 0)
                    except Exception:
                        koef = 0.0
                    if koef <= 1.0:
                        koef = round(1 / prob, 2)
                    bm = {"ndeshja": p.get("ndeshja"), "ora": p.get("ora"),
                          "liga": p.get("liga_emri"), "tregu": m,
                          "tregu_emri": _emri_tregut(m, p.get("ndeshja")),
                          "prob": prob, "koef": koef, "besu": besu_p}
            if bm:
                kand.append(bm)
        if len(kand) < 2:
            return None
        # PREFERENCA E BESUESHMËRISË: ndeshjet ≥75 kanë përparësi; nëse s'mjaftojnë, kalon tek të tjerat (soft)
        prag = BESU_PRAG_VIP
        def _hi(c):
            return c.get("besu") is not None and c["besu"] >= prag
        nr = min(nr, len(kand))
        # LIMITI: koef total >= koef_min. Floor per pick = koef_min^(1/nr) e garanton.
        floor = koef_min ** (1.0 / nr) if koef_min and koef_min > 1.0 else 1.0
        eligible = [c for c in kand if c["koef"] >= floor]
        eligible.sort(key=lambda x: (_hi(x), x["prob"]), reverse=True)
        if len(eligible) >= nr:
            zgjedhur = eligible[:nr]            # me te bindurit qe kalojne limitin
        else:
            kand.sort(key=lambda x: (_hi(x), x["koef"]), reverse=True)
            zgjedhur = kand[:nr]                # s'ka mjaft -> maksimizo koefin
        if len(zgjedhur) < 2:
            return None
        koef_total = 1.0
        for k in zgjedhur:
            koef_total *= float(k["koef"])
        return {"pikat": zgjedhur, "koef_total": round(koef_total, 2),
                "nr": len(zgjedhur), "koef_min": koef_min}
    except Exception:
        return None


def _ndertoMesazhTelegramSkedine(sk):
    nl = chr(10)
    pikat = sk.get("pikat", [])
    L = ["🎁 <b>FREE TICKET OF THE DAY</b> — SOCCER1X2 PRO", "",
         f"🎟️ <b>{sk.get('nr', len(pikat))}-match high-confidence ticket</b>", ""]
    for i, p in enumerate(pikat, 1):
        L.append(f"{i}) 🏆 {p.get('liga','')}")
        L.append(f"🆚 <b>{p['ndeshja']}</b>  🕐 {p.get('ora','')}")
        L.append(f"🎯 <b>{p['tregu_emri']}</b>  •  💰 {p['koef']}")
        L.append("")
    L += [f"🔢 <b>Total odds: {sk.get('koef_total')}</b>", "",
          "✅ <b>High confidence</b> — a gift from our team.", "",
          "Maximize your profit: play with <b>COMBOS</b>, unlock the <b>Daily Ticket</b> and become <b>VIP</b>.",
          "👉 https://soccer1x2pro.com", "",
          "💎 Daily ticket with a winning combo",
          "💎 VIP access with premium predictions",
          "💎 Profit maximization", "",
          "📈 <b>With us, you invest.</b>", "",
          "⚠️ 18+ • Play responsibly"]
    return nl.join(L)


def _dergo_telegram(text, chat_id=None):
    if not TELEGRAM_BOT_TOKEN:
        return False, "Mungon TELEGRAM_BOT_TOKEN"
    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid:
        return False, "Mungon TELEGRAM_CHAT_ID"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": False}, timeout=15)
        j = r.json() if r.status_code == 200 else {}
        return bool(j.get("ok")), (j if j else r.text)
    except Exception as e:
        return False, str(e)


@app.get("/api/telegram/top")
def telegram_top(date: str = None):
    dt = date or _data_lokale()
    sk = _zgjidh_skedine_ditore(dt)
    if not sk:
        return {"sukses": False, "kod": "NOT_ENOUGH_DATE", "arsye": "S'ka mjaft ndeshje me parashikim për këtë datë."}
    return {"sukses": True, "skedina": sk, "mesazhi": _ndertoMesazhTelegramSkedine(sk)}


@app.get("/api/telegram/dergo")
def telegram_dergo(key: str = "", date: str = None):
    if not TELEGRAM_CRON_KEY or key != TELEGRAM_CRON_KEY:
        return {"sukses": False, "kod": "KEY_INVALID", "arsye": "Çelës i pavlefshëm."}
    dt = date or _data_lokale()
    sk = _zgjidh_skedine_ditore(dt)
    if not sk:
        return {"sukses": False, "kod": "NOT_ENOUGH_DATE", "arsye": "S'ka mjaft ndeshje për këtë datë."}
    ok, info = _dergo_telegram(_ndertoMesazhTelegramSkedine(sk))
    return {"sukses": bool(ok), "info": info, "skedina": sk}


# ===================== VIP COMBO (vetëm VIP) — 2 ndeshje × 4 rezultate të sakta =====================
def _tip_rezultati(skor):
    h, a = _parse_score(skor)
    if h is None:
        return "?"
    return "1" if h > a else ("2" if a > h else "X")


def _top_rezultate_sakta(p, n=4):
    """TOP-N: kthen thjesht N skoret me te mundshme nga shperndarja e golave.
       (Prove mbi 5292 ndeshje: top-N godet me shume se cdo skeme diversiteti/simetrie.)"""
    dist = p.get("dist_gola") or {}
    rez_sakt = p.get("rezultati_sakt")
    if not dist:
        return []
    try:
        total = sum(float(v) for v in dist.values())
    except Exception:
        total = 0.0
    if total <= 0:
        return []
    items = sorted(dist.items(), key=lambda kv: float(kv[1]), reverse=True)
    zgjedhur, seen = [], set()

    def mk(k, v=None):
        if v is None:
            v = dist.get(k, dist.get(str(k).replace(" ", ""), 0))
        prob = (float(v) / total) if total else 0.0
        return {"skor": k, "prob": round(prob, 4), "koef": round(1.0 / prob, 2) if prob > 0 else 0}

    def shto(k, v=None):
        zgjedhur.append(mk(k, v)); seen.add(k)

    # TOP-N i paster: thjesht N skoret me te mundshme nga shperndarja
    for k, v in items:
        if len(zgjedhur) >= n:
            break
        shto(k, v)
    return zgjedhur[:n]


@app.get("/api/ligat-disponueshme")
def ligat_disponueshme():
    """Kthen vetëm ligat që kanë vërtet ndeshje të gjenerueshme (gjenerator) ose VIP Combo."""
    fund = "FT,AET,PEN,AWD,WO,CANC,PST,ABD"
    def distinct(url):
        try:
            r = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=8)
            rows = r.json() if r.status_code == 200 else []
            return sorted({(x.get("liga_emri") or "").strip() for x in rows if x.get("liga_emri")})
        except Exception:
            return []
    gen = distinct(f"{SUPABASE_URL_PREDS}?select=liga_emri&best_bet=not.is.null"
                   f"&statusi=not.in.({fund})&order=id.desc&limit=400")
    dt = _data_lokale()
    vc = distinct(f"{SUPABASE_URL_PREDS}?select=liga_emri&data=eq.{dt}"
                  f"&dist_gola=not.is.null&rezultati_sakt=not.is.null&statusi=not.in.({fund})&limit=400")
    return {"gjenerator": gen, "vip_combo": vc}


VIP_COMBO_HIST_URL = f"{SUPABASE_BASE}/rest/v1/vip_combo_historik"

# ===================== PROVABLY FAIR (commit-reveal) =====================
PF_URL = f"{SUPABASE_BASE}/rest/v1/provably_fair"
ARKIV_URL = f"{SUPABASE_BASE}/rest/v1/arkiv_rezultatesh"


def _shenja_1x2(sc):
    """1 / X / 2 nga një skor 'h-a' (ose None)."""
    p = _parse_score(sc)
    if not p:
        return None
    return "1" if p[0] > p[1] else ("2" if p[0] < p[1] else "X")


def _num_opt(x):
    try:
        v = float(x)
        return v if v == v else None   # filtro NaN
    except Exception:
        return None


def _rezultati_ft(fx):
    """Rezultati i 90 minutave (FT) për 1X2/PPM — JO pas shtesave (AET) ose penallteve (PEN).
    API-Football: score.fulltime = fundi i 90-tES. Bie te goals nEse fulltime mungon (AWD/WO)."""
    try:
        ft = ((fx.get("score") or {}).get("fulltime") or {})
        gh, ga = ft.get("home"), ft.get("away")
        if gh is None or ga is None:
            g = fx.get("goals") or {}
            gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            return None
        return f"{gh} - {ga}"
    except Exception:
        return None


def _arkivo_ndeshje(pred, ht_str=None):
    """Arkivon NJË ndeshje të mbaruar te arkiv_rezultatesh. Idempotent (match_id UNIQUE)."""
    mid = str(pred.get("id") or "")
    ft = pred.get("rezultati")
    if not mid or not ft:
        return
    par = pred.get("rezultati_sakt") or ""
    treg = pred.get("tregjet") or {}
    rec = {
        "match_id":     mid,
        "ndeshja":      pred.get("ndeshja"),
        "ekipi_1":      pred.get("ekipi_1"),
        "ekipi_2":      pred.get("ekipi_2"),
        "liga":         pred.get("liga_emri"),
        "data":         pred.get("data"),
        "ora":          pred.get("ora_sakte") or pred.get("ora"),
        "koef_1":       _num_opt(pred.get("koef_1")),
        "koef_x":       _num_opt(pred.get("koef_x")),
        "koef_2":       _num_opt(pred.get("koef_2")),
        "odds_reale":   pred.get("odds_reale") or {},
        "parashikimi":  par,
        "prob_1":       _num_opt(treg.get("1")),
        "prob_x":       _num_opt(treg.get("X")),
        "prob_2":       _num_opt(treg.get("2")),
        "best_bet":     pred.get("best_bet") or {},
        "rezultati_ht": ht_str,
        "rezultati_ft": ft,
        "parashikimi_ht": (str(treg.get("skor_ht")).replace("-", " - ") if treg.get("skor_ht") else None),
        "besueshmeria": _num_opt(pred.get("besueshmeria")),
        "goditi_1x2":   (_shenja_1x2(par) == _shenja_1x2(ft)) if (par and _shenja_1x2(par) and _shenja_1x2(ft)) else None,
        "goditi_skor":  (_parse_score(par) == _parse_score(ft)) if (par and _parse_score(par) and _parse_score(ft)) else None,
        # ── FOTOGRAFIA E PLOTE E TRAJNIMIT (inputet+llogaritja+shperndarja, lidhur me rezultatin real) ──
        "training_data": pred.get("training_data") or {},
        "dist_gola":     pred.get("dist_gola") or {},
        "tregjet_full":  treg,
    }
    try:
        requests.post(ARKIV_URL,
                      headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "resolution=ignore-duplicates"},
                      json=rec, timeout=8)
    except Exception:
        pass


def _arkivo_sweep():
    """SWEEP i sigurt (jo-transicional): arkivon çdo parashikim TË MBARUAR që ende
    s'është në arkiv — pa varësi nga rruga që e vuri statusin FT. Njësoj si
    /api/arkiv/rindertimi, por i lehtë (vetëm të rejat) dhe automatik nga cron-i.
    Zgjidh rastin kur gjenerimi (cron) e vë statusin FT direkt nga API dhe arkivuesi
    transicional e humb ndeshjen (p.sh. France–Suedi). Idempotent (match_id UNIQUE)."""
    fund = "FT,AET,PEN,AWD,WO"
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ekipi_1,ekipi_2,liga_emri,data,ora,ora_sakte,"
            f"koef_1,koef_x,koef_2,odds_reale,rezultati_sakt,tregjet,best_bet,besueshmeria,training_data,dist_gola,rezultati"
            f"&statusi=in.({fund})&rezultati=not.is.null"
            f"&order=data.desc&limit=150",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        preds = r.json() if r.status_code == 200 else []
    except Exception:
        preds = []
    if not preds:
        return
    # ID-të tashmë në arkiv → mos i ripatch/refetch (ignore-duplicates i bën no-op gjithsesi)
    try:
        ar = requests.get(f"{ARKIV_URL}?select=match_id&order=data.desc&limit=800",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        ekzistuese = {str(x.get("match_id")) for x in (ar.json() if ar.status_code == 200 else [])}
    except Exception:
        ekzistuese = set()
    mungojne = [p for p in preds if str(p.get("id")) not in ekzistuese]
    if not mungojne:
        return
    # HT nga API vetëm për ato që mungojnë (batch 20) — steady-state: 0 thirrje API
    ht_map = {}
    ids = [str(p.get("id")) for p in mungojne if p.get("id")]
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        try:
            api_res = requests.get("https://v3.football.api-sports.io/fixtures",
                                   headers=HEADERS, params={"ids": "-".join(batch)}, timeout=10)
            for fx in api_res.json().get("response", []):
                fid = str(fx["fixture"]["id"])
                ht = (fx.get("score") or {}).get("halftime") or {}
                if ht.get("home") is not None:
                    ht_map[fid] = f"{ht.get('home')} - {ht.get('away')}"
        except Exception:
            pass
    for p in mungojne:
        try:
            _arkivo_ndeshje(p, ht_map.get(str(p.get("id"))))
        except Exception:
            pass


def _pf_hash(ndeshja, parashikimi, seed):
    """Hash publik = sha256(ndeshja | parashikimi | server_seed)."""
    msg = f"{ndeshja}|{parashikimi}|{seed}"
    return hashlib.sha256(msg.encode("utf-8")).hexdigest()

def _gjenero_pf():
    """Krijon 'commitment' (hash i kyçur) për ndeshjet premium të sotme që s'e kanë ende."""
    dt_sot = _data_lokale(0); dt_neser = _data_lokale(1)
    fund = "FT,AET,PEN,AWD,WO,CANC,PST,ABD"
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,liga_emri,ora,data,rezultati_sakt,ekipi_1_id,ekipi_2_id,is_premium"
            f"&data=in.({dt_sot},{dt_neser})&dist_gola=not.is.null&rezultati_sakt=not.is.null&statusi=not.in.({fund})"
            f"&order=koef_rez_sakt.asc&limit=8",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    for p in rows:
        nd = p.get("ndeshja"); par = p.get("rezultati_sakt")
        if not nd or not par:
            continue
        # Ndeshja PPM bëhet is_premium → shfaqet te Historiku PPM pasi të zbulohet
        if not p.get("is_premium") and p.get("id"):
            try:
                requests.patch(f"{SUPABASE_URL_PREDS}?id=eq.{p['id']}",
                               headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=minimal"},
                               json={"is_premium": True}, timeout=8)
                # Ndeshje e re premium -> zbraz cache-in qe maskimi te aplikohet MENJEHERE
                try:
                    _PF_NAMES_CACHE["ts"] = 0.0
                    if p.get("data"):
                        SKEDINA_CACHE.pop(p.get("data"), None)
                except Exception:
                    pass
            except Exception:
                pass
        seed = secrets.token_hex(8)
        rec = {"ndeshja": nd, "liga_emri": p.get("liga_emri"), "data": p.get("data"),
               "ora": p.get("ora"), "parashikimi": par, "server_seed": seed,
               "hash_publik": _pf_hash(nd, par, seed), "statusi": "kycur",
               "ekipi_1_id": p.get("ekipi_1_id"), "ekipi_2_id": p.get("ekipi_2_id")}
        try:
            requests.post(PF_URL,
                headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "resolution=ignore-duplicates"},
                json=rec, timeout=8)
        except Exception:
            pass

_pf_premium_backfilled = False


def _zbulo_pf():
    """Zbulon parashikimet e kyçura sapo ndeshja të mbarojë me rezultat real."""
    global _pf_premium_backfilled
    fund = "FT,AET,PEN,AWD,WO"
    try:
        r = requests.get(f"{PF_URL}?select=id,ndeshja,data&statusi=eq.kycur",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        locked = r.json() if r.status_code == 200 else []
    except Exception:
        locked = []
    for pf_row in locked:
        nd = pf_row.get("ndeshja"); dt = pf_row.get("data")
        if not nd:
            continue
        try:
            url = (f"{SUPABASE_URL_PREDS}?select=rezultati,statusi"
                   f"&ndeshja=eq.{requests.utils.quote(nd, safe='')}"
                   + (f"&data=eq.{dt}" if dt else "")
                   + f"&statusi=in.({fund})&rezultati=not.is.null&limit=1")
            rr = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=8)
            mm = rr.json() if rr.status_code == 200 else []
        except Exception:
            mm = []
        if mm:
            try:
                requests.patch(f"{PF_URL}?id=eq.{pf_row['id']}",
                    headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=minimal"},
                    json={"statusi": "zbuluar", "rezultati_real": mm[0].get("rezultati"),
                          "zbuluar_me": datetime.utcnow().isoformat()}, timeout=8)
            except Exception:
                pass
            try:   # etiketo si is_premium → shfaqet te Historiku PPM
                requests.patch(
                    f"{SUPABASE_URL_PREDS}?ndeshja=eq.{requests.utils.quote(nd, safe='')}"
                    + (f"&data=eq.{dt}" if dt else "") + "&is_premium=is.false",
                    headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=minimal"},
                    json={"is_premium": True}, timeout=8)
            except Exception:
                pass

    # Backfill një-herësh: ndeshjet PPM tashmë të zbuluara → is_premium (që dalin te Historiku PPM)
    if not _pf_premium_backfilled:
        _pf_premium_backfilled = True
        try:
            rz = requests.get(f"{PF_URL}?select=ndeshja&statusi=eq.zbuluar",
                              headers=SUPABASE_SERVICE_HEADERS, timeout=10)
            names = list({x.get("ndeshja") for x in (rz.json() if rz.status_code == 200 else []) if x.get("ndeshja")})
        except Exception:
            names = []
        for nm in names:
            try:
                requests.patch(
                    f"{SUPABASE_URL_PREDS}?ndeshja=eq.{requests.utils.quote(nm, safe='')}&is_premium=is.false",
                    headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=minimal"},
                    json={"is_premium": True}, timeout=8)
            except Exception:
                pass

_ARG_CACHE = {}   # gjuha -> {"quote","quiz"} — përgjigja e fundit e suksesshme (fallback kur Gemini 503)
_GEMINI_REZERVA = ["gemini-2.5-flash-lite", "gemini-2.0-flash"]   # provohen kur modeli kryesor mbingarkohet


@app.get("/api/argetohu")
def argetohu(gjuha: str = "sq", authorization: str = Header(None)):
    """Kuote motivuese origjinale + pyetje kuiz trivie futbolli (Gemini), sipas gjuhes.
    Qëndrueshmëri: zinxhir modelesh (503 → provo rezervën) + kujtesa e fundit e mirë për gjuhë."""
    _email_auth(authorization, "", strict=False)
    gj = gjuha if gjuha in ("en", "sq", "de", "fr", "it") else "sq"
    emri_gj = {"en": "English", "sq": "Albanian", "de": "German", "fr": "French", "it": "Italian"}[gj]
    if not GEMINI_API_KEY:
        return {"ok": False, "quote": "", "quiz": None, "arsye": "GEMINI_API_KEY mungon"}
    prompt = (
        "You create short fun content for a football fan app. Write in " + emri_gj + ". "
        "Return ONLY a valid JSON object, no markdown fences, exactly: "
        '{"quote":"...","quiz":{"question":"...","answer":"..."}}. '
        "Rules: quote = an ORIGINAL, uplifting one-line message about football, passion, teamwork, effort or winning (max 16 words); "
        "do NOT quote or attribute it to any real person. "
        "quiz = ONE football trivia question about a widely-known, verifiable fact (World Cup winners, legendary players, famous clubs), "
        "and answer = the correct answer in max 5 words. Make sure the answer is factually correct."
    )
    modelet = [GEMINI_MODEL] + [m for m in _GEMINI_REZERVA if m != GEMINI_MODEL]
    arsye_fundit = ""
    for _model in modelet:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + _model + ":generateContent?key=" + GEMINI_API_KEY
            r = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 1.0, "maxOutputTokens": 1024, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}
            }, timeout=25)
            if r.status_code in (503, 429):
                arsye_fundit = "gemini %d (%s)" % (r.status_code, _model)
                continue   # model i mbingarkuar → provo rezervën
            if r.status_code != 200:
                arsye_fundit = "gemini %d: %s" % (r.status_code, (r.text or "")[:160])
                break      # gabim real (çelës/model) — s'ndihmoi ndërrimi
            jd = r.json()
            cands = jd.get("candidates") or []
            if not cands:
                arsye_fundit = "pa-candidates: " + str(jd)[:160]
                continue
            parts = ((cands[0].get("content") or {}).get("parts")) or []
            txt = ""
            for _p in parts:
                if _p.get("text"):
                    txt = _p["text"]; break
            if not txt:
                arsye_fundit = "pa-tekst (finishReason=%s)" % cands[0].get("finishReason", "?")
                continue
            txt = txt.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(txt)
            q = data.get("quiz") or {}
            rez = {"ok": True,
                   "quote": (data.get("quote") or "").strip(),
                   "quiz": {"question": (q.get("question") or "").strip(), "answer": (q.get("answer") or "").strip()}}
            if rez["quote"]:
                _ARG_CACHE[gj] = {"quote": rez["quote"], "quiz": rez["quiz"]}   # ruaj të fundit e mirë
            return rez
        except Exception as e:
            arsye_fundit = "gabim: " + str(e)[:160]
            continue
    # Të gjitha modelet dështuan → kthe të fundit e mirë për këtë gjuhë (nëse ka)
    ck = _ARG_CACHE.get(gj)
    if ck and ck.get("quote"):
        return {"ok": True, "quote": ck["quote"], "quiz": ck.get("quiz"), "burimi": "cache", "arsye": arsye_fundit}
    return {"ok": False, "quote": "", "quiz": None, "arsye": arsye_fundit}


@app.get("/api/pf/risinkro")
def pf_risinkro():
    """Ri-sinkronizon rezultati_real te provably_fair nga predictions.rezultati (FT) për rreshtat e zbuluar.
    Rregullon rastet ku rezultati u ndryshua manualisht (p.sh. AET Belgium-Senegal 3-2 -> 2-2). I ri-ekzekutueshëm."""
    try:
        r = requests.get(f"{PF_URL}?select=id,ndeshja,data,rezultati_real&statusi=eq.zbuluar",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=15)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    kontrolluar = 0; korrigjuar = 0; ndryshimet = []
    for pf_row in rows:
        nd = pf_row.get("ndeshja"); dt = pf_row.get("data")
        if not nd:
            continue
        kontrolluar += 1
        try:
            url = (f"{SUPABASE_URL_PREDS}?select=rezultati&ndeshja=eq.{requests.utils.quote(nd, safe='')}"
                   + (f"&data=eq.{dt}" if dt else "")
                   + "&rezultati=not.is.null&order=id.desc&limit=1")
            rr = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=8)
            mm = rr.json() if rr.status_code == 200 else []
        except Exception:
            mm = []
        if mm:
            ri = mm[0].get("rezultati")
            vjeter = pf_row.get("rezultati_real")
            if ri and ri != vjeter:
                try:
                    requests.patch(f"{PF_URL}?id=eq.{pf_row['id']}",
                        headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=minimal"},
                        json={"rezultati_real": ri}, timeout=8)
                    korrigjuar += 1
                    ndryshimet.append({"ndeshja": nd, "nga": vjeter, "ne": ri})
                except Exception:
                    pass
    return {"kontrolluar": kontrolluar, "korrigjuar": korrigjuar, "ndryshimet": ndryshimet}


@app.get("/api/pf/list")
def pf_list(email: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email, strict=False)
    """Lista e ndeshjeve me hash. Të kyçurat NUK e tregojnë parashikimin; të zbuluarat po.
    VIP-unlock: abonentët VIP e shohin parashikimin edhe te të kyçurat (pa server_seed)."""
    _gjenero_pf(); _zbulo_pf()
    vip = _eshte_vip(email) if (email and email.strip()) else False
    try:
        r = requests.get(f"{PF_URL}?select=*&order=krijuar.desc&limit=20",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    name2id = {}
    name_only2id = {}
    try:
        pr = requests.get(f"{SUPABASE_URL_PREDS}?select=id,ndeshja,data&order=id.desc&limit=400",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        for _p in (pr.json() if pr.status_code == 200 else []):
            name2id[(_p.get("ndeshja"), _p.get("data"))] = _p.get("id")
            _nm = _p.get("ndeshja")
            if _nm and _nm not in name_only2id:   # i pari = me i ri (order=id.desc)
                name_only2id[_nm] = _p.get("id")
    except Exception:
        pass
    out = []
    for pf_row in rows:
        item = {"id": pf_row.get("id"), "ndeshja": pf_row.get("ndeshja"),
                "liga_emri": pf_row.get("liga_emri"), "ora": pf_row.get("ora"),
                "data": pf_row.get("data"), "hash_publik": pf_row.get("hash_publik"),
                "statusi": pf_row.get("statusi"), "ekipi_1_id": pf_row.get("ekipi_1_id"),
                "ekipi_2_id": pf_row.get("ekipi_2_id")}
        item["match_id"] = name2id.get((pf_row.get("ndeshja"), pf_row.get("data"))) or name_only2id.get(pf_row.get("ndeshja"))
        if pf_row.get("statusi") == "zbuluar":
            item["parashikimi"] = pf_row.get("parashikimi")
            item["server_seed"] = pf_row.get("server_seed")
            item["rezultati_real"] = pf_row.get("rezultati_real")
        elif vip:
            # VIP-unlock: parashikimi falas për abonentët VIP. PA server_seed —
            # hash-i mbetet i paverifikueshëm para ndeshjes, pra provably-fair s'cenohet.
            item["parashikimi"] = pf_row.get("parashikimi")
            item["vip_open"] = True
        out.append(item)
    return {"pikat": out}

@app.get("/api/pf/verify")
def pf_verify(id: int):
    """Verifikim transparent: rikalkulon hash-in nga parashikimi+fara e zbuluar."""
    try:
        r = requests.get(f"{PF_URL}?select=*&id=eq.{id}&limit=1",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    if not rows:
        return {"ok": False, "mesazh": "Nuk u gjet"}
    pf_row = rows[0]
    if pf_row.get("statusi") != "zbuluar":
        return {"ok": False, "statusi": "kycur", "hash_publik": pf_row.get("hash_publik"),
                "formula": "sha256(ndeshja | parashikimi | server_seed)",
                "mesazh": "Parashikimi eshte ende i kycur. Hash-i u publikua para ndeshjes dhe zbulohet pas saj."}
    nd = pf_row.get("ndeshja"); par = pf_row.get("parashikimi"); seed = pf_row.get("server_seed")
    rikalk = _pf_hash(nd, par, seed)
    return {"ok": True, "statusi": "zbuluar", "ndeshja": nd, "parashikimi": par,
            "server_seed": seed, "hash_publik": pf_row.get("hash_publik"),
            "hash_rikalkuluar": rikalk, "vlefshem": (rikalk == pf_row.get("hash_publik")),
            "formula": "sha256(ndeshja | parashikimi | server_seed)",
            "rezultati_real": pf_row.get("rezultati_real")}


@app.get("/api/diag")
def diag(email: str = ""):
    """Mjet verifikimi: datë UTC vs Tiranë, lidhja+kuota e API-Football, statusi VIP, premium picks.
    Thirre: /api/diag?email=EMAIL_YT  (email opsional, për të parë statusin VIP)."""
    out = {
        "data_utc":    datetime.utcnow().strftime("%Y-%m-%d %H:%M") + " UTC",
        "data_tirane": _data_lokale() + " (lokale Shqipëri)",
        "api_key_vendosur": bool(API_KEY),
    }
    # 1) Lidhja + kuota e API-Football (përdor /status — nuk konsumon kuotë)
    try:
        r = requests.get("https://v3.football.api-sports.io/status", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            d = r.json().get("response", {}) or {}
            sub = d.get("subscription", {}) or {}
            req = d.get("requests", {}) or {}
            out["api_ok"]            = True
            out["api_plan"]          = sub.get("plan")
            out["api_aktiv"]         = sub.get("active")
            out["api_thirrje_sot"]   = f"{req.get('current')} / {req.get('limit_day')}"
        else:
            out["api_ok"] = False
            out["api_status_code"] = r.status_code
            out["api_pergjigje"] = (r.text or "")[:200]
    except Exception as e:
        out["api_ok"] = False
        out["api_gabim"] = str(e)
    # 2) Statusi VIP (nëse jepet email)
    if email and email.strip():
        out["email"]     = email.strip().lower()
        out["eshte_vip"] = _eshte_vip(email)
    # 3) Premium picks (provably_fair)
    try:
        r = requests.get(f"{PF_URL}?select=id,statusi&order=krijuar.desc&limit=20",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
        out["pf_total"]  = len(rows)
        out["pf_kycur"]  = sum(1 for x in rows if x.get("statusi") == "kycur")
        out["pf_zbuluar"]= sum(1 for x in rows if x.get("statusi") == "zbuluar")
    except Exception:
        pass
    return out


def _ruaj_vip_combo(dt, nr, rez, ndeshjet):
    """Ruan përkufizimin e VIP Combo-s (një herë/ditë për çdo konfigurim) për vlerësim të mëvonshëm."""
    try:
        trim = [{"id": n.get("id"), "ndeshja": n.get("ndeshja"), "liga": n.get("liga"),
                 "rezultati_sakt": n.get("rezultati_sakt"),
                 "rezultatet": [{"skor": x.get("skor"), "koef": x.get("koef")} for x in (n.get("rezultatet") or [])]}
                for n in ndeshjet]
        hdr = dict(SUPABASE_SERVICE_HEADERS)
        hdr["Prefer"] = "resolution=ignore-duplicates"
        requests.post(VIP_COMBO_HIST_URL, headers=hdr,
                      json={"data": dt, "nr": nr, "rez": rez, "ndeshjet": trim, "statusi": "pezull"},
                      timeout=6)
    except Exception:
        pass


def _vleso_vip_combot():
    """Pas FT të të gjitha ndeshjeve: cakton kombon fituese ose, nëse s'ka, skedinën me më shumë ndeshje të kapura."""
    try:
        r = requests.get(f"{VIP_COMBO_HIST_URL}?statusi=eq.pezull&select=id,ndeshjet",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
        fund = ("FT", "AET", "PEN", "AWD", "WO")
        for rec in rows:
            ndeshjet = rec.get("ndeshjet") or []
            ids = [str(n.get("id")) for n in ndeshjet if n.get("id")]
            if not ids:
                continue
            pr = requests.get(f"{SUPABASE_URL_PREDS}?id=in.({','.join(ids)})&select=id,statusi,rezultati",
                              headers=SUPABASE_SERVICE_HEADERS, timeout=8)
            preds = {str(p["id"]): p for p in (pr.json() if pr.status_code == 200 else [])}
            if not all(preds.get(i, {}).get("statusi") in fund for i in ids):
                continue  # ende jo të gjitha kanë mbaruar
            rreshtat = []; korrekte = 0; koef_total = 1.0
            for n in ndeshjet:
                pid = str(n.get("id"))
                rh, ra = _parse_skor(preds.get(pid, {}).get("rezultati"))
                real_norm = f"{rh}-{ra}" if rh is not None else None
                real_shf = real_norm or "—"
                matched = None; matched_koef = None
                for s in (n.get("rezultatet") or []):
                    if str(s.get("skor", "")).replace(" ", "") == (real_norm or "__nomatch__"):
                        matched = s.get("skor"); matched_koef = s.get("koef"); break
                if matched:
                    korrekte += 1
                    if matched_koef:
                        koef_total *= float(matched_koef)
                    rreshtat.append({"ndeshja": n.get("ndeshja"), "liga": n.get("liga"),
                                     "parashikim": matched, "koef": matched_koef,
                                     "real": real_shf, "goditi": True})
                else:
                    rreshtat.append({"ndeshja": n.get("ndeshja"), "liga": n.get("liga"),
                                     "parashikim": n.get("rezultati_sakt"), "koef": None,
                                     "real": real_shf, "goditi": False})
            statusi = "fituese" if korrekte == len(ndeshjet) else "humbur"
            fituesi = {"rreshtat": rreshtat, "korrekte": korrekte, "total": len(ndeshjet),
                       "koef_total": round(koef_total, 2) if korrekte == len(ndeshjet) else None}
            requests.patch(f"{VIP_COMBO_HIST_URL}?id=eq.{rec['id']}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"statusi": statusi, "fituesi": fituesi}, timeout=6)
    except Exception:
        pass


def _ndeshjet_vipcombo(rows, nr, rez):
    """Nderton listen e ndeshjeve per VIP Combo (deri ne nr). PA DUBLIKATA (sipas emrit)."""
    out = []
    _pare = set()
    for p in rows:
        _k = _nm_key(p)
        if _k and _k in _pare:
            continue   # e njejta ndeshje dy here ne pool -> merret vetem nje here
        topr = _top_rezultate_sakta(p, rez)
        if len(topr) >= rez:
            out.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"), "ora": p.get("ora"),
                        "liga": p.get("liga_emri"), "rezultati_sakt": p.get("rezultati_sakt"),
                        "besueshmeria": p.get("besueshmeria"), "rezultatet": topr})
            if _k:
                _pare.add(_k)
        if len(out) >= nr:
            break
    return out


@app.get("/api/vip-combo")
def vip_combo(email: str = "", nr: int = 2, rez: int = 4, liga: str = "", paguaj: int = 0, perjashto: str = "", vetem: str = "", perjashto_emra: str = "", vetem_emra: str = "", authorization: str = Header(None)):
    email = _email_auth(authorization, email)
    """VIP COMBO: nr ndeshje (2 ose 3) × rez rezultate të sakta (3 ose 4) = rez^nr skedina."""
    if not email or not email.strip():
        return {"sukses": False, "kod": "LOGIN_FIRST", "arsye": "Hyr së pari në llogari."}
    _drejta = _kontrollo_te_drejten(email, "vipcombo", CMIM_VIPCOMBO, bool(paguaj))
    if not _drejta["ok"]:
        return {"sukses": False, "bllokuar": True,
                "kerko_pagese": _drejta.get("kerko_pagese", False),
                "mungojne_kredite": _drejta.get("mungojne_kredite", False),
                "arsye": _drejta["arsye"],
                "portofoli": _drejta["portofoli"], "is_vip": _drejta["is_vip"], "cmimi": CMIM_VIPCOMBO}
    nr = 3 if int(nr) == 3 else 2
    rez = 3 if int(rez) == 3 else 4
    dt = _data_lokale(0); dt_neser = _data_lokale(1)
    vc_url = (f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ora,liga_emri,rezultati_sakt,koef_rez_sakt,dist_gola,besueshmeria"
              f"&data=in.({dt},{dt_neser})&dist_gola=not.is.null&rezultati_sakt=not.is.null"
              f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&order=besueshmeria.desc.nullslast,koef_rez_sakt.asc&limit=30")
    if liga and liga.strip():
        vc_url += f"&liga_emri=eq.{requests.utils.quote(liga.strip(), safe='')}"
    r = requests.get(vc_url, headers=SUPABASE_SERVICE_HEADERS, timeout=10)
    rows_plot = r.json() if r.status_code == 200 else []
    _perj = _id_set(perjashto); _vet = _id_set(vetem)
    _perj_em = {(x or "").strip().lower() for x in (perjashto_emra or "").split("|") if x.strip()}
    _vet_em = {(x or "").strip().lower() for x in (vetem_emra or "").split("|") if x.strip()}
    _manual = bool(_vet or _vet_em)
    if _manual:
        _kane = {_nm_key(p) for p in rows_plot}
        _mung = [x for x in _vet_em if x not in _kane]
        if _mung:
            try:
                _or = ",".join("ndeshja.ilike." + requests.utils.quote(x, safe='') for x in _mung)
                _r2 = requests.get(f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ora,liga_emri,rezultati_sakt,koef_rez_sakt,dist_gola,besueshmeria&or=({_or})&limit=50", headers=SUPABASE_SERVICE_HEADERS, timeout=8)
                for _p in (_r2.json() if _r2.status_code == 200 else []):
                    if _nm_key(_p) not in _kane:
                        rows_plot.append(_p); _kane.add(_nm_key(_p))
            except Exception:
                pass
        rows_plot = [p for p in rows_plot if p.get("id") in _vet or _nm_key(p) in _vet_em]
    if _perj or _perj_em:
        rows_plot = [p for p in rows_plot if p.get("id") not in _perj and _nm_key(p) not in _perj_em]
    given = set() if _manual else _merr_given_ids(email, "vipcombo")

    def _provo_vc(rows_x):
        """Zgjedh ndeshjet për VIP Combo nga rows_x; rivendos 'given' dhe riprovon."""
        nd = _ndeshjet_vipcombo([p for p in rows_x if p.get("id") not in given], nr, rez)
        rif = False
        if len(nd) < nr and given:
            _rivendos_given(email, "vipcombo")
            nd = _ndeshjet_vipcombo(rows_x, nr, rez)
            rif = True
        return nd, rif

    # SHKALLËZIMI I BESUESHMËRISË: nis GJITHMONË nga % më e lartë (renditja besueshmeria.desc).
    # Nëse s'plotësohet kërkesa me pragun 70, ulet me shkallë (65→60→55→50). Kurrë nën 50.
    ndeshjet, rifilluar, rows, prag_perdorur = [], False, rows_plot, None
    if _manual:
        ndeshjet, rifilluar = _provo_vc(rows_plot)   # manual: pikërisht ndeshjet e zgjedhura, pa prag
    else:
        for _prag in (BESU_PRAG_VIPCOMBO, 65.0, 60.0, 55.0, 50.0):
            rows_p = _filtro_besu(rows_plot, prag=_prag)
            nd, rif = _provo_vc(rows_p)
            if len(nd) >= nr:
                ndeshjet, rifilluar, rows, prag_perdorur = nd, rif, rows_p, _prag
                break
        if len(ndeshjet) < nr and not _drejta["is_vip"]:
            # Jo-VIP (që paguan): si mundësi e fundit, i gjithë pool-i (i renditur nga besueshmëria)
            ndeshjet, rifilluar = _provo_vc(rows_plot)
            rows = rows_plot
    if len(ndeshjet) < nr:
        return {"sukses": False, "kod": "VIPCOMBO_NOT_ENOUGH_CONF", "arsye": f"Sot s'ka {nr} ndeshje me besueshmëri të mjaftueshme (u provua deri në ≥50%). Provo më vonë."}

    ndeshjet = ndeshjet[:nr]
    # prodhimi kartezian i rezultateve (rez^nr skedina)
    def prodhim(listat):
        rez_list = [[]]
        for lst in listat:
            rez_list = [r + [x] for r in rez_list for x in lst]
        return rez_list

    listat = [n["rezultatet"] for n in ndeshjet]
    kombinimet = []
    for kombo in prodhim(listat):
        jp = 1.0; kt = 1.0
        skedina = []
        for i, rr in enumerate(kombo):
            jp *= (rr["prob"] or 0)
            kt *= (rr["koef"] or 1)
            skedina.append({"ndeshja": ndeshjet[i]["ndeshja"], "skor": rr["skor"], "koef": rr["koef"]})
        kombinimet.append({"skedina": skedina, "prob": round(jp, 5), "koef_total": round(kt, 2)})
    kombinimet.sort(key=lambda k: k["prob"], reverse=True)

    mbulim = 1.0
    for n in ndeshjet:
        mbulim *= sum(x["prob"] for x in n["rezultatet"])
    _ruaj_vip_combo(dt, nr, rez, ndeshjet)
    _porto_ri = _konfirmo_perdorimin(email, "vipcombo", CMIM_VIPCOMBO, _drejta["is_vip"], _drejta["portofoli"], _drejta.get("falas", False))
    if not _manual: _ruaj_given_ids(email, "vipcombo", [n.get("id") for n in ndeshjet if n.get("id")])
    _ruaj_vip_legs(email, ndeshjet, rows)
    _bv = [float(n["besueshmeria"]) for n in ndeshjet if n.get("besueshmeria") is not None]
    besu_mesatare = round(sum(_bv) / len(_bv)) if _bv else None
    return {"sukses": True, "nr_ndeshje": nr, "nr_rezultate": rez, "rifilluar": rifilluar,
            "prag_besueshmerie": prag_perdorur,
            "besu_mesatare": besu_mesatare,
            "ndeshjet": ndeshjet, "kombinimet": kombinimet,
            "nr_kombinimesh": len(kombinimet),
            "portofoli": _porto_ri, "u_pagua": (not _drejta["is_vip"] and not _drejta.get("falas", False)),
            "cmimi": CMIM_VIPCOMBO,
            "mbulimi_perqind": round(mbulim * 100, 1)}


# ==========================================
# MODULI 1: ELO BAZË & VALUE BET
# ==========================================
GIGANTET_ELO = {
    "Real Madrid": 950, "Manchester City": 945, "Bayern Munich": 920, "Arsenal": 910,
    "Liverpool": 905, "Barcelona": 890, "Paris Saint Germain": 885, "Inter": 880,
    "Bayer Leverkusen": 870, "Juventus": 850, "AC Milan": 845, "Atletico Madrid": 840,
    "Argentina": 960, "France": 950, "England": 930, "Spain": 920, "Brazil": 910,
    "Germany": 890, "Portugal": 880, "Italy": 870, "Netherlands": 860
}

def merr_elo_baze(ekipi):
    for emri, elo in GIGANTET_ELO.items():
        if emri.lower() in ekipi.lower():
            return float(elo)
    return 600.0

def detect_value_bet(p_model, odds_bookmaker):
    try:
        odds = float(odds_bookmaker)
        if odds <= 1.01:
            return None
        value = (p_model * odds) - 1
        if value > 0.05:
            return round(value * 100, 1)
    except:
        pass
    return None

def merr_dna_nga_db(team_id):
    try:
        res = requests.get(
            f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
            headers=SUPABASE_SERVICE_HEADERS, timeout=2
        )
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()[0]
    except:
        pass
    return None

# ==========================================
# MODULI 2 (V2): FORMA REALE NGA API
# ==========================================

# Cache për formën e ekipeve — shmang thirrje të tepërta API
FORMA_CACHE = {}
FORMA_CACHE_TTL = 3600  # 1 orë

def merr_formen_reale(team_id: int, liga_emri: str = None, numri_ndeshjeve: int = 8) -> dict:
    """
    Merr ndeshjet e fundit të ekipit dhe llogarit:
    win_rate, xG mesatar, lodhjen e serisë — me të dhëna REALE.
    SHTUAR: home/away split (gola shtëpi vs jashtë veçmas).
    """
    koha_tani = time.time()
    _cache_key = (team_id, liga_emri)
    if _cache_key in FORMA_CACHE:
        te_dhenat, koha_ruajtur = FORMA_CACHE[_cache_key]
        if koha_tani - koha_ruajtur < FORMA_CACHE_TTL:
            return te_dhenat

    try:
        res = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS,
            params={"team": team_id, "last": max(25, numri_ndeshjeve), "status": "FT"},
            timeout=5
        )
        ndeshjet = res.json().get("response", [])
    except:
        return _forma_boshe()

    if not ndeshjet:
        return _forma_boshe()

    # ── FILTRI I LIGES: vetem ndeshjet nga e njejta lige (fallback nese < 5) ──
    if liga_emri:
        _same = [n for n in ndeshjet
                 if f"{(n.get('league') or {}).get('country', '')} - {(n.get('league') or {}).get('name', '')}" == liga_emri]
        ndeshjet = _same[:numri_ndeshjeve] if len(_same) >= 5 else ndeshjet[:numri_ndeshjeve]
    else:
        ndeshjet = ndeshjet[:numri_ndeshjeve]

    fitore = barazime = humbje = 0
    gola_shenuar = gola_prane = 0
    piket_forma = 0.0

    # Statistika të ndara HOME / AWAY
    h_gola_shenuar = h_gola_prane = h_ndeshje = 0
    a_gola_shenuar = a_gola_prane = a_ndeshje = 0

    for n in ndeshjet:
        eshte_shtepie = n["teams"]["home"]["id"] == team_id
        g_ekip = n["goals"]["home"] if eshte_shtepie else n["goals"]["away"]
        g_kund = n["goals"]["away"] if eshte_shtepie else n["goals"]["home"]
        if g_ekip is None or g_kund is None:
            continue
        gola_shenuar += g_ekip
        gola_prane   += g_kund

        # Ndaje sipas vendndodhjes
        if eshte_shtepie:
            h_gola_shenuar += g_ekip
            h_gola_prane   += g_kund
            h_ndeshje      += 1
        else:
            a_gola_shenuar += g_ekip
            a_gola_prane   += g_kund
            a_ndeshje      += 1

        if g_ekip > g_kund:
            fitore += 1
            piket_forma += 3.0
        elif g_ekip == g_kund:
            barazime += 1
            piket_forma += 1.0
        else:
            humbje += 1

    total = fitore + barazime + humbje
    if total == 0:
        return _forma_boshe()

    win_rate          = fitore / total
    avg_gola_shenuar  = gola_shenuar / total
    avg_gola_prane    = gola_prane   / total
    xg_shenuar        = avg_gola_shenuar * 0.85 + 0.25
    xg_prane          = avg_gola_prane   * 0.85 + 0.20
    k_wins_rresht     = _llogarit_wins_rresht(ndeshjet, team_id)
    lodhja_factor     = 1.0 - (0.04 * max(0, k_wins_rresht - 2))
    # Kongjestioni: sa ndeshje brenda 14 ditëve nga ndeshja më e fundit (përafrim lodhjeje)
    ndeshje_14d = 0
    try:
        _datat = []
        for _n in ndeshjet:
            _d = (_n.get("fixture") or {}).get("date")
            if _d:
                _datat.append(datetime.fromisoformat(_d.replace("Z", "+00:00")))
        if _datat:
            _maxd = max(_datat)
            ndeshje_14d = sum(1 for _x in _datat if (_maxd - _x).days <= 14)
    except Exception:
        ndeshje_14d = 0

    # Mesataret home/away (me fallback te mesatarja e përgjithshme nëse s'ka mjaft)
    avg_shenuar_home = (h_gola_shenuar / h_ndeshje) if h_ndeshje >= 2 else avg_gola_shenuar
    avg_prane_home   = (h_gola_prane   / h_ndeshje) if h_ndeshje >= 2 else avg_gola_prane
    avg_shenuar_away = (a_gola_shenuar / a_ndeshje) if a_ndeshje >= 2 else avg_gola_shenuar
    avg_prane_away   = (a_gola_prane   / a_ndeshje) if a_ndeshje >= 2 else avg_gola_prane

    rezultati = {
        "win_rate":         round(win_rate, 3),
        "avg_gola_shenuar": round(avg_gola_shenuar, 2),
        "avg_gola_prane":   round(avg_gola_prane, 2),
        "xg_shenuar":       round(xg_shenuar, 3),
        "xg_prane":         round(xg_prane, 3),
        "k_wins_rresht":    k_wins_rresht,
        "ndeshje_14d":      ndeshje_14d,
        "lodhja_factor":    round(lodhja_factor, 3),
        "piket_forma":      round(piket_forma, 1),
        "total_ndeshje":    total,
        # Home/away split
        "avg_shenuar_home": round(avg_shenuar_home, 2),
        "avg_prane_home":   round(avg_prane_home, 2),
        "avg_shenuar_away": round(avg_shenuar_away, 2),
        "avg_prane_away":   round(avg_prane_away, 2),
        "h_ndeshje":        h_ndeshje,
        "a_ndeshje":        a_ndeshje,
    }
    FORMA_CACHE[_cache_key] = (rezultati, koha_tani)
    return rezultati

def _forma_boshe() -> dict:
    return {
        "win_rate": 0.40, "avg_gola_shenuar": 1.2, "avg_gola_prane": 1.2,
        "xg_shenuar": 1.25, "xg_prane": 1.20, "k_wins_rresht": 0, "ndeshje_14d": 2,
        "lodhja_factor": 1.0, "piket_forma": 0.0, "total_ndeshje": 0,
        "avg_shenuar_home": 1.2, "avg_prane_home": 1.2,
        "avg_shenuar_away": 1.2, "avg_prane_away": 1.2,
        "h_ndeshje": 0, "a_ndeshje": 0,
    }

def _llogarit_wins_rresht(ndeshjet: list, team_id: int) -> int:
    wins = 0
    for n in sorted(ndeshjet, key=lambda x: x["fixture"]["date"], reverse=True):
        eshte_shtepie = n["teams"]["home"]["id"] == team_id
        g_e = n["goals"]["home"] if eshte_shtepie else n["goals"]["away"]
        g_k = n["goals"]["away"] if eshte_shtepie else n["goals"]["home"]
        if g_e is None or g_k is None:
            break
        if g_e > g_k:
            wins += 1
        else:
            break
    return wins

# ==========================================
# MODULI 3 (V2): XG ME PESHIM TË KOMBINUAR
# ==========================================

def llogarit_xg_te_perparuara(
    forma_1: dict, forma_2: dict,
    elo_1: float, elo_2: float,
    p1_real: float, p2_real: float,
) -> tuple:
    """
    xG final = kombinim i peshuar i 4 burimeve:
    35% forma reale + 30% ELO + 25% tregu (koeficientët) + 10% avantazhi shtëpiak
    Zëvendëson: xg_1_baze = max(0.40, (p1_adj * 3.15) + (diferenca_elo / 850.0))
    """
    W_FORMA   = 0.40
    W_ELO     = 0.25
    W_MARKET  = 0.25
    W_BASE    = 0.10

    # Burimi 1: Forma me HOME/AWAY SPLIT
    # Ekipi 1 luan në SHTËPI → përdor sulmin e tij në shtëpi vs mbrojtjen e ekipit 2 jashtë
    # Ekipi 2 luan JASHTË → përdor sulmin e tij jashtë vs mbrojtjen e ekipit 1 në shtëpi
    sulm_1 = forma_1.get("avg_shenuar_home", forma_1["avg_gola_shenuar"])
    mbrojtje_2 = forma_2.get("avg_prane_away", forma_2["avg_gola_prane"])
    sulm_2 = forma_2.get("avg_shenuar_away", forma_2["avg_gola_shenuar"])
    mbrojtje_1 = forma_1.get("avg_prane_home", forma_1["avg_gola_prane"])

    # xG i pritur = mesatarja e (sulmit të vet) dhe (dobësisë mbrojtëse të kundërshtarit)
    xg1_forma_raw = (sulm_1 + mbrojtje_2) / 2.0
    xg2_forma_raw = (sulm_2 + mbrojtje_1) / 2.0
    xg1_forma = (xg1_forma_raw * 0.85 + 0.25)
    xg2_forma = (xg2_forma_raw * 0.85 + 0.25)

    # Burimi 2: ELO — pjerresi e plote 3.0 + dysheme e vogel XG_FLOOR (0 = origjinali p*3).
    # Underdogu ngrihet vetem pak; favoriti ruan gamen e plote qe te arrije 3-0.
    diff_elo = (elo_1 - elo_2) / 400.0
    p1_elo   = 1 / (1 + 10 ** (-diff_elo))
    p2_elo   = 1 - p1_elo
    xg1_elo  = XG_FLOOR + p1_elo * (3.0 - XG_FLOOR)
    xg2_elo  = XG_FLOOR + p2_elo * (3.0 - XG_FLOOR)

    # Burimi 3: Tregu — pjerresi 3.2 (si 27/06) + e njejta dysheme e vogel.
    xg1_market = XG_FLOOR + p1_real * (3.2 - XG_FLOOR)
    xg2_market = XG_FLOOR + p2_real * (3.2 - XG_FLOOR)

    # Burimi 4: Baza e golave (mesatarja globale e futbollit ~1.35 gola/ekip)
    xg1_base = 1.35
    xg2_base = 1.35

    # Avantazhi shtëpiak (rritur pak)
    shtepie_bonus = 1.12
    jashte_minus  = 0.95

    xg_1_final = (W_FORMA * xg1_forma + W_ELO * xg1_elo + W_MARKET * xg1_market + W_BASE * xg1_base) * shtepie_bonus
    xg_2_final = (W_FORMA * xg2_forma + W_ELO * xg2_elo + W_MARKET * xg2_market + W_BASE * xg2_base) * jashte_minus

    # Kufijtë e rritur (3.50 → 4.20) që të lejojë rezultate me shumë gola
    xg_1_final = float(np.clip(xg_1_final, 0.35, 5.00))
    xg_2_final = float(np.clip(xg_2_final, 0.35, 5.00))


    return round(xg_1_final, 3), round(xg_2_final, 3)

# ==========================================
# MODULI 3.5: HYBRID — XGBOOST + FALLBACK
# ==========================================

def _f_safe(v, d):
    """float(v) ose default d nese None/i pavlefshem."""
    try:
        if v is None:
            return d
        return float(v)
    except Exception:
        return d


def _ah_kryesore(ah_dict):
    """Nga dict-i AH live ({'Home -0.5': 1.9, 'Away +0.5': 1.9, ...}) zgjedh linjen
    kryesore (me te balancuaren) -> (line, home_odd, away_odd). None nese s'gjendet."""
    if not ah_dict:
        return None
    home_odds, away_odds = {}, {}
    for k, v in ah_dict.items():
        try:
            od = float(v)
        except Exception:
            continue
        parts = str(k).rsplit(" ", 1)
        if len(parts) != 2:
            continue
        side = parts[0].strip().lower()
        hc = parts[1].strip().replace("+", "")
        try:
            hcv = float(hc)
        except Exception:
            continue
        if "home" in side:
            home_odds[hcv] = od
        elif "away" in side:
            away_odds[hcv] = od
    best = None
    for L, ho in home_odds.items():
        ao = away_odds.get(-L)
        if ao is None:
            continue
        bal = abs(ho - ao)
        if best is None or bal < best[0]:
            best = (bal, L, ho, ao)
    if best is None:
        if home_odds:
            L = min(home_odds, key=lambda x: abs(x))
            return (L, home_odds[L], None)
        return None
    return (best[1], best[2], best[3])


def llogarit_xg_hybrid(
    forma_1: dict, forma_2: dict,
    p1_real: float, p2_real: float,
    k1: float, kx: float, k2: float,
    emri_liges: str,
    xg_math_1: float, xg_math_2: float,
    ah_line=None, ah_home=None, ah_away=None,
    ou_over=None, ou_under=None,
) -> tuple:
    """
    HYBRID: kombinon XGBoost (nëse gati) me xG matematikore.
    - XGBoost jep golat bazë nga 26 features.
    - Kombinohet 55% XGBoost + 45% math (XGBoost peshë më të madhe).
    - Nëse XGBoost s'është gati → kthen vetëm math (fallback i plotë).
    Kthen: (xg_1, xg_2, burimi)
    """
    if not XGB_GATI:
        return xg_math_1, xg_math_2, "math", None, None

    try:
        # Tipi i ndeshjes (0=ligë, 1=kupë klubesh, 2=kombëtare)
        tipi = _percakto_tipi_ndeshjes(emri_liges)

        # Forca relative (attack/defense vs mesatarja ~1.35)
        MES = 1.35
        h_scored = forma_1.get("avg_gola_shenuar", 1.3)
        h_conceded = forma_1.get("avg_gola_prane", 1.3)
        a_scored = forma_2.get("avg_gola_shenuar", 1.3)
        a_conceded = forma_2.get("avg_gola_prane", 1.3)

        # Ndërto vektorin e features në RENDIN EKZAKT të trajnimit
        vlerat = {
            "home_forma_pts": forma_1.get("piket_forma", 7.0),
            "away_forma_pts": forma_2.get("piket_forma", 7.0),
            "home_avg_scored": h_scored,
            "away_avg_scored": a_scored,
            "home_avg_conceded": h_conceded,
            "away_avg_conceded": a_conceded,
            "home_avg_scored_home": forma_1.get("avg_shenuar_home", h_scored),
            "home_avg_conceded_home": forma_1.get("avg_prane_home", h_conceded),
            "away_avg_scored_away": forma_2.get("avg_shenuar_away", a_scored),
            "away_avg_conceded_away": forma_2.get("avg_prane_away", a_conceded),
            "home_avg_yellow": XGB_DEFAULTS["home_avg_yellow"],
            "away_avg_yellow": XGB_DEFAULTS["away_avg_yellow"],
            "home_avg_red": XGB_DEFAULTS["home_avg_red"],
            "away_avg_red": XGB_DEFAULTS["away_avg_red"],
            "home_attack_strength": round(h_scored / MES, 3),
            "away_attack_strength": round(a_scored / MES, 3),
            "home_defense_strength": round(h_conceded / MES, 3),
            "away_defense_strength": round(a_conceded / MES, 3),
            "home_volatility": XGB_DEFAULTS["home_volatility"],
            "away_volatility": XGB_DEFAULTS["away_volatility"],
            "home_rest_days": XGB_DEFAULTS["home_rest_days"],
            "away_rest_days": XGB_DEFAULTS["away_rest_days"],
            "odd_home": k1, "odd_draw": kx, "odd_away": k2,
            "tipi_ndeshjes": tipi,
            "ah_line": _f_safe(ah_line, XGB_DEFAULTS["ah_line"]),
            "ah_home_odd": _f_safe(ah_home, XGB_DEFAULTS["ah_home_odd"]),
            "ah_away_odd": _f_safe(ah_away, XGB_DEFAULTS["ah_away_odd"]),
            "ou25_over": _f_safe(ou_over, XGB_DEFAULTS["ou25_over"]),
            "ou25_under": _f_safe(ou_under, XGB_DEFAULTS["ou25_under"]),
        }
        vektori = np.array([[vlerat[f] for f in XGB_FEATURES]], dtype=float)

        xgb_h = float(XGB_MODEL_HOME.predict(vektori)[0])
        xgb_a = float(XGB_MODEL_AWAY.predict(vektori)[0])

        # Fraksioni HT — sa pjesë e golave FT pritet në gjysmën e parë (nga modelet HT)
        frac_ht_1 = frac_ht_2 = None
        if XGB_HT_GATI and XGB_MODEL_HOME_HT is not None:
            try:
                xght_h = float(XGB_MODEL_HOME_HT.predict(vektori)[0])
                xght_a = float(XGB_MODEL_AWAY_HT.predict(vektori)[0])
                frac_ht_1 = float(np.clip(xght_h / max(0.30, xgb_h), 0.20, 0.65))
                frac_ht_2 = float(np.clip(xght_a / max(0.30, xgb_a), 0.20, 0.65))
            except Exception:
                frac_ht_1 = frac_ht_2 = None

        # Kombinim: 55% XGBoost + 45% math
        W_XGB = 0.55
        xg_1 = W_XGB * xgb_h + (1 - W_XGB) * xg_math_1
        xg_2 = W_XGB * xgb_a + (1 - W_XGB) * xg_math_2

        xg_1 = float(np.clip(xg_1, 0.30, 5.00))
        xg_2 = float(np.clip(xg_2, 0.30, 5.00))
        return round(xg_1, 3), round(xg_2, 3), "hybrid", frac_ht_1, frac_ht_2

    except Exception as e:
        # Çdo gabim → fallback i sigurt te math
        print(f"⚠️ Hybrid dështoi ({e}) — fallback math.")
        return xg_math_1, xg_math_2, "math", None, None


def _percakto_tipi_ndeshjes(emri_liges: str) -> int:
    """0=ligë, 1=kupë klubesh, 2=kombëtare."""
    e = emri_liges.lower()
    kupa_klub = ["champions league", "europa league", "conference league"]
    kombetare = ["world cup", "euro", "copa america", "nations league"]
    for k in kupa_klub:
        if k in e:
            return 1
    for k in kombetare:
        if k in e:
            return 2
    return 0

# ==========================================
# MODULI 4 (V2): MONTE CARLO ME NUMPY
# ==========================================

def _nxirr_odds_reale(bets):
    """Nxjerr odds reale (1X2, O/U, BTTS, Double Chance, Exact Score) nga /odds."""
    def gjej(bid, name=None):
        return next((b for b in bets if b.get("id") == bid or (name and b.get("name") == name)), None)
    def val(bet, target):
        if not bet:
            return None
        return next((x.get("odd") for x in bet.get("values", []) if str(x.get("value")) == target), None)
    out = {}
    mw = gjej(1, "Match Winner")
    out["1"] = val(mw, "Home"); out["X"] = val(mw, "Draw"); out["2"] = val(mw, "Away")
    ou = gjej(5, "Goals Over/Under")
    for ln in ("1.5", "2.5", "3.5"):
        out["Over " + ln] = val(ou, "Over " + ln)
        out["Under " + ln] = val(ou, "Under " + ln)
    btts = gjej(8, "Both Teams Score")
    out["GG"] = val(btts, "Yes"); out["NG"] = val(btts, "No")
    dc = gjej(12, "Double Chance")
    out["1X"] = val(dc, "Home/Draw"); out["12"] = val(dc, "Home/Away"); out["X2"] = val(dc, "Draw/Away")
    es = gjej(10, "Exact Score")
    if es:
        cs = {}
        for x in es.get("values", []):
            v = str(x.get("value", "")).replace(":", "-")
            od = x.get("odd")
            if v and od:
                cs[v] = od
        if cs:
            out["CS"] = cs
    ah = gjej(33, "Asian Handicap")
    if ah:
        ahd = {}
        for x in ah.get("values", []):
            v = str(x.get("value", "")).strip()   # p.sh. "Home -1.5"
            od = x.get("odd")
            if v and od:
                ahd[v] = od
        if ahd:
            out["AH"] = ahd
    return {k: v for k, v in out.items() if v is not None}


# Tregjet kandidate për "best bet" (rendit sipas prob. më të lartë).
# Për piket më interesante, hiq "12"/"1X"/"X2"/"Under 3.5"/"Over 1.5".
TREGJET_KANDIDATE = ["1", "X", "2", "Under 1.5", "Over 2.5",
                     "Under 2.5", "Over 3.5", "GG", "NG"]


_ODDS_FIXTURE_CACHE = {}   # fix_id -> (timestamp, parsed_or_None)
_ODDS_FIXTURE_TTL = 1800   # 30 min (cache edhe rezultatet bosh, per te kursyer API)

def _merr_odds_per_fixture(fix_id):
    """Odds per NJE fixture specifik — fallback kur marrja sipas dates s'i kap
    (p.sh. World Cup i pritur jashte 10 faqeve). Provon bookmakers me prioritet.
    Cache 30-min (perfshire 'pa odds') qe te mos hamendesohet API-ja."""
    key = str(fix_id)
    now = time.time()
    ck = _ODDS_FIXTURE_CACHE.get(key)
    if ck and now - ck[0] < _ODDS_FIXTURE_TTL:
        return ck[1]
    result = None
    for _bm in [8, 4, 6, 2, 11]:   # Bet365, Pinnacle, 1xBet, Marathon, William Hill
        try:
            r = requests.get("https://v3.football.api-sports.io/odds", headers=HEADERS,
                             params={"fixture": fix_id, "bookmaker": _bm}, timeout=10).json()
            resp = r.get("response") or []
            if not resp:
                continue
            bets = resp[0]["bookmakers"][0]["bets"]
            parsed = _nxirr_odds_reale(bets)
            if parsed.get("1") and parsed.get("X") and parsed.get("2"):
                result = parsed
                break
        except Exception:
            continue
    _ODDS_FIXTURE_CACHE[key] = (now, result)
    return result


def _best_bet_value(tregjet, odds_reale):
    """Best bet me VALUE: midis tregjeve të sigurta (prob>=0.5) zgjedh value-n më
    të lartë (prob_model × koef_real). Përdor odds reale ku ka, përndryshe fair."""
    kand = []
    for t in TREGJET_KANDIDATE:
        if t not in (tregjet or {}):
            continue
        try:
            p = float(tregjet.get(t, 0))
        except Exception:
            p = 0.0
        if p <= 0:
            continue
        od_real = None
        if odds_reale and t in odds_reale:
            try:
                od_real = float(odds_reale[t])
            except Exception:
                od_real = None
        od = od_real if (od_real and od_real > 1) else round(1.0 / p, 2)
        kand.append({"tregu": t, "prob": round(p, 4), "koef": round(od, 2),
                     "value": round(p * od, 3), "real": bool(od_real)})
    if not kand:
        return None
    confident = [k for k in kand if k["prob"] >= 0.5]
    if confident:
        return max(confident, key=lambda k: k["value"])
    return max(kand, key=lambda k: k["prob"])


RHO_DC = -0.12  # Dixon-Coles: korrelacioni i skoreve te uleta (0 = Poisson i paster)
# Kufiri i rrumbullakimit te skorit nga xG (kalibruar me te dhena reale: 0.65 optimal).
# xG 1.65+ -> 2 gola, 2.65+ -> 3 gola. Env-kalibrueshem pa prekur kod.
try:
    SKOR_TAU = float(os.environ.get("SKOR_TAU", "0.65").strip())
except Exception:
    SKOR_TAU = 0.65

# Dysheme e vogel per golat e underdog-ut (tunable). 0 = origjinali 27/06 (p*3).
try:
    XG_FLOOR = float(os.environ.get("XG_FLOOR", "0.10").strip())
except Exception:
    XG_FLOOR = 0.10

# ── MODULATORI: de-kompresim per-ekip drejt tregut + ELO (sinjalet me spekter real) ──
# xG baze ngjeshet nga forma+baza. Modulatori e shtyn drejt tregut/ELO-s, per-ekip.
# Kufij ASIMETRIK: me shume liri per te ULUR underdog-un e fryre (-0.45) se per te ngritur (+0.35).
# k_treg/k_elo tunable (env) -> me vone kalibrohen nga arkivi.
try:
    MOD_K_TREG = float(os.environ.get("MOD_K_TREG", "0.50").strip())
except Exception:
    MOD_K_TREG = 0.50
try:
    MOD_K_ELO = float(os.environ.get("MOD_K_ELO", "0.20").strip())
except Exception:
    MOD_K_ELO = 0.20
try:
    MOD_KUFI_POSHTE = float(os.environ.get("MOD_KUFI_POSHTE", "-0.45").strip())
except Exception:
    MOD_KUFI_POSHTE = -0.45
try:
    MOD_KUFI_LART = float(os.environ.get("MOD_KUFI_LART", "0.35").strip())
except Exception:
    MOD_KUFI_LART = 0.35

# ── LËNDIMET (API-Football): dënim i vogël xG per lojtar te lenduar/pezulluar (tunable). ──
try:
    INJURY_PEN_PER = float(os.environ.get("INJURY_PEN_PER", "0.025").strip())
except Exception:
    INJURY_PEN_PER = 0.025
try:
    INJURY_PEN_CAP = float(os.environ.get("INJURY_PEN_CAP", "0.12").strip())
except Exception:
    INJURY_PEN_CAP = 0.12

# ── MODULATORI I TOTALIT: fut variancE te totali (nga forma + treg O/U) — ruan drejtimin. ──
# total_xg eshte i ngjeshur (std ~0.18); kjo e shtyn drejt sinjalit real (korr +0.53). K tunable.
try:
    TOTAL_K = float(os.environ.get("TOTAL_K", "0.70").strip())
except Exception:
    TOTAL_K = 0.70
try:
    TOTAL_MIN = float(os.environ.get("TOTAL_MIN", "1.20").strip())
except Exception:
    TOTAL_MIN = 1.20
try:
    TOTAL_MAX = float(os.environ.get("TOTAL_MAX", "4.50").strip())
except Exception:
    TOTAL_MAX = 4.50

# ── RREGULLI I FITUESIT: pragu i "favoritit te qarte" (diferenca p_fitues - p_barazim).
# Nen kete prag -> ndeshje e ngushte -> lejo barazim. Mbi -> skori DETYROHET te respektoje favoritin.
try:
    WINNER_PRAG = float(os.environ.get("WINNER_PRAG", "0.15").strip())
except Exception:
    WINNER_PRAG = 0.15


def _ht_ft_distribuim(xg_ht_1, xg_ht_2, xg_2h_1, xg_2h_2, max_g=6):
    """
    Shpërndarja e përbashkët HT/FT -> 9 rezultate (1/1, 1/X, ... 2/2).
    Poisson convolution: gjysma e parë + gjysma e dytë (e pavarur).
    Kthen dict {"1/1": prob, ...} (probabilitete 0-1, shuma=1).
    """
    def _pois(lam, kmax):
        out = []; p = math.exp(-lam)
        for k in range(kmax + 1):
            out.append(p); p = p * lam / (k + 1)
        return out
    ph_ht = _pois(xg_ht_1, max_g); pa_ht = _pois(xg_ht_2, max_g)
    ph_2h = _pois(xg_2h_1, max_g); pa_2h = _pois(xg_2h_2, max_g)
    cells = {k: 0.0 for k in ["1/1","1/X","1/2","X/1","X/X","X/2","2/1","2/X","2/2"]}
    def _sgn(h, a):
        return "1" if h > a else ("2" if a > h else "X")
    for hh in range(max_g + 1):
        for ah in range(max_g + 1):
            p_ht = ph_ht[hh] * pa_ht[ah]
            if p_ht < 1e-9:
                continue
            s_ht = _sgn(hh, ah)
            for h2 in range(max_g + 1):
                for a2 in range(max_g + 1):
                    p = p_ht * ph_2h[h2] * pa_2h[a2]
                    if p < 1e-10:
                        continue
                    cells[s_ht + "/" + _sgn(hh + h2, ah + a2)] += p
    tot = sum(cells.values())
    if tot > 0:
        for k in cells:
            cells[k] = round(cells[k] / tot, 4)
    return cells

def simulim_ht_ft_mc(xg_ht_1, xg_ht_2, xg_2h_1, xg_2h_2, iteracione=40_000, seed=None):
    """
    Simulim Monte Carlo i PAVARUR — HT trajtohet si një "MINI-FT" i plotë.
    Gjysma e parë dhe e dytë simulohen veçmas. Nga golat e gjysmës së parë (h_ht, a_ht)
    llogariten TË GJITHA tregjet HT (1X2, Double Chance, O/U, GG/NG, skor i saktë),
    pikërisht ashtu si llogariten për FT. HT NUK derivohet nga skori FT.
    Kthen: (cells_htft {"1/1":prob,...}, skor_ht_str, prob_skor_ht, ht_mkt {"HT 1":prob,...}).
    """
    rng = np.random.default_rng(seed)
    h_ht = rng.poisson(max(0.05, xg_ht_1), iteracione)
    a_ht = rng.poisson(max(0.05, xg_ht_2), iteracione)
    h_ft = h_ht + rng.poisson(max(0.05, xg_2h_1), iteracione)
    a_ft = a_ht + rng.poisson(max(0.05, xg_2h_2), iteracione)
    n = float(iteracione)
    # shenjat: 1 (vendas), 2 (mysafir), 0 (barazim/X)
    s_ht = np.where(h_ht > a_ht, 1, np.where(a_ht > h_ht, 2, 0))
    s_ft = np.where(h_ft > a_ft, 1, np.where(a_ft > h_ft, 2, 0))
    _m = {1: "1", 2: "2", 0: "X"}
    cells = {}
    for hv in (1, 0, 2):
        mh = (s_ht == hv)
        for fv in (1, 0, 2):
            cells[_m[hv] + "/" + _m[fv]] = round(float(np.count_nonzero(mh & (s_ft == fv))) / n, 4)

    # ── HT si MINI-FT: TË GJITHA tregjet nga golat e gjysmës së parë ──
    tot_ht = h_ht + a_ht
    p1 = float(np.count_nonzero(h_ht > a_ht)) / n
    pX = float(np.count_nonzero(h_ht == a_ht)) / n
    p2 = float(np.count_nonzero(a_ht > h_ht)) / n
    ht_mkt = {
        "HT 1": round(p1, 4), "HT X": round(pX, 4), "HT 2": round(p2, 4),
        "HT 1X": round(p1 + pX, 4), "HT X2": round(pX + p2, 4), "HT 12": round(p1 + p2, 4),
        "HT Over 0.5":  round(float(np.count_nonzero(tot_ht >= 1)) / n, 4),
        "HT Under 0.5": round(float(np.count_nonzero(tot_ht == 0)) / n, 4),
        "HT Over 1.5":  round(float(np.count_nonzero(tot_ht >= 2)) / n, 4),
        "HT Under 1.5": round(float(np.count_nonzero(tot_ht <= 1)) / n, 4),
        "HT GG": round(float(np.count_nonzero((h_ht > 0) & (a_ht > 0))) / n, 4),
        "HT NG": round(float(np.count_nonzero((h_ht == 0) | (a_ht == 0))) / n, 4),
    }
    # HT skor i saktë (top 6) + skori HT më i probabël
    hc = np.clip(h_ht, 0, 4); ac = np.clip(a_ht, 0, 4)
    combo = hc * 10 + ac
    vals, counts = np.unique(combo, return_counts=True)
    order = np.argsort(counts)[::-1]
    for idx in order[:6]:
        v = int(vals[idx])
        ht_mkt[f"HT CS {v // 10}-{v % 10}"] = round(float(counts[idx]) / n, 4)
    _b = int(vals[int(np.argmax(counts))])
    skor_ht = f"{_b // 10}-{_b % 10}"
    prob_ht = round(float(np.max(counts)) / n, 4)
    return cells, skor_ht, prob_ht, ht_mkt

def simulim_monte_carlo_v2(
    xg_1: float, xg_2: float,
    kaos_factor: float = 1.0,
    is_derbi: bool = False,
    iteracione: int = 50_000,
    rho: float = RHO_DC,
    seed: int = None
) -> tuple:
    """
    Monte Carlo vectorized me numpy — 50,000 simulime në ~60ms.
    Zëvendëson: loop Python me 10,000 iteracione (~800ms).
    Kthen: (rezultati_sakt, prob_max, rezultatet_freq, prob_1x2)
    """
    if is_derbi:
        kaos_factor *= 1.15

    sigma_1 = xg_1 * 0.18 * kaos_factor
    sigma_2 = xg_2 * 0.18 * kaos_factor

    rng = np.random.default_rng(seed)
    xg1_virtual = np.clip(rng.normal(xg_1, sigma_1, iteracione), 0.05, 6.0)
    xg2_virtual = np.clip(rng.normal(xg_2, sigma_2, iteracione), 0.05, 6.0)

    gola_1 = rng.poisson(xg1_virtual)
    gola_2 = rng.poisson(xg2_virtual)

    # ── Matrica e perbashket nga simulimet (per Dixon-Coles) ──
    GMAX = 10
    _g1 = np.clip(gola_1, 0, GMAX)
    _g2 = np.clip(gola_2, 0, GMAX)
    H = np.zeros((GMAX + 1, GMAX + 1), dtype=float)
    np.add.at(H, (_g1, _g2), 1.0)
    H = H / H.sum()

    # ── DIXON-COLES: korrigjim korrelacioni per skoret e uleta (0-0,0-1,1-0,1-1) ──
    _l = max(float(xg_1), 0.05)
    _m = max(float(xg_2), 0.05)
    H[0, 0] *= max(1.0 - _l * _m * rho, 1e-6)
    H[0, 1] *= max(1.0 + _l * rho, 1e-6)
    H[1, 0] *= max(1.0 + _m * rho, 1e-6)
    H[1, 1] *= max(1.0 - rho, 1e-6)
    H = H / H.sum()

    _ii, _jj = np.indices(H.shape)
    prob_1x2 = {
        "p1": round(float(H[_ii > _jj].sum()), 4),
        "px": round(float(H[_ii == _jj].sum()), 4),
        "p2": round(float(H[_ii < _jj].sum()), 4),
    }

    # Top 15 rezultatet (si numra, per perputhshmeri me dist_gola)
    _flat = H.flatten()
    _order = np.argsort(_flat)[::-1]
    rezultatet_freq = {}
    for _idx in _order[:15]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _c = int(round(float(_flat[_idx]) * iteracione))
        if _c > 0:
            rezultatet_freq[f"{_i}-{_j}"] = _c

    # ── ZGJEDHJA E REZULTATIT: midis top-5, me afer totalit te pritur (metoda 27/06) ──
    total_pritur = xg_1 + xg_2
    kandidatet = []
    for _idx in _order[:5]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _freq = float(_flat[_idx])
        _difft = abs((_i + _j) - total_pritur)
        _score = _freq * (1.0 / (1.0 + _difft * 0.5))
        kandidatet.append((_i, _j, _freq, _score))
    kandidatet.sort(key=lambda x: x[3], reverse=True)
    # ── RREGULLI I FITUESIT: skori respekton favoritin e QARTE (nga p1/px/p2). ──
    # NUK prek frekuencat/Dixon-Coles; vetem filtron kandidatet kur ka favorit te qarte.
    _wp1 = prob_1x2["p1"]; _wpx = prob_1x2["px"]; _wp2 = prob_1x2["p2"]
    if _wp1 >= _wp2 and (_wp1 - _wpx) > WINNER_PRAG:
        _fkand = [_k for _k in kandidatet if _k[0] > _k[1]]   # favorit vendas -> vetem fitore vendase
    elif _wp2 > _wp1 and (_wp2 - _wpx) > WINNER_PRAG:
        _fkand = [_k for _k in kandidatet if _k[1] > _k[0]]   # favorit mysafir -> vetem fitore mysafiri
    else:
        _fkand = kandidatet                                    # ngushte -> lejo barazim
    if _fkand:
        kandidatet = _fkand                                    # mbrojtje: mos zbraz listen
    rez_g1, rez_g2, freq_zgjedhur, _ = kandidatet[0]
    rez_str  = f"{rez_g1}-{rez_g2}"
    prob_max = float(freq_zgjedhur)

    # ── TREGJET nga matrica (Dixon-Coles e perfshire) ──
    _tot = _ii + _jj
    def _pf(mask):
        return round(float(H[mask].sum()), 4)
    tregjet = {
        "1": prob_1x2["p1"], "X": prob_1x2["px"], "2": prob_1x2["p2"],
        "1X": round(prob_1x2["p1"] + prob_1x2["px"], 4),
        "X2": round(prob_1x2["px"] + prob_1x2["p2"], 4),
        "12": round(prob_1x2["p1"] + prob_1x2["p2"], 4),
        "Over 1.5": _pf(_tot >= 2), "Under 1.5": _pf(_tot <= 1),
        "Over 2.5": _pf(_tot >= 3), "Under 2.5": _pf(_tot <= 2),
        "Over 3.5": _pf(_tot >= 4), "Under 3.5": _pf(_tot <= 3),
        "GG": _pf((_ii > 0) & (_jj > 0)),
        "NG": _pf((_ii == 0) | (_jj == 0)),
    }

    return rez_str, round(prob_max, 4), rezultatet_freq, prob_1x2, tregjet

# ==========================================
# MODULI 5 (V2): BESUESHMËRIA ME KONSENSUS
# ==========================================

def llogarit_besueshmeria_v2(
    prob_1x2_mc: dict,
    p1_market: float, p2_market: float, px_market: float,
    prob_rez_sakt: float,
    forma_1: dict, forma_2: dict,
) -> float:
    """
    Besueshmëria = konsensus midis MC, tregut dhe formës.
    Skalim realist: 55% - 92% (jo 65-99% arbitrar).
    """
    p1_mc = prob_1x2_mc["p1"]
    p2_mc = prob_1x2_mc["p2"]
    px_mc = prob_1x2_mc["px"]

    diff_total    = abs(p1_mc - p1_market) + abs(p2_mc - p2_market) + abs(px_mc - px_market)
    konsensus     = 1.0 - min(1.0, diff_total / 1.5)

    max_prob      = max(p1_mc, p2_mc, px_mc)
    sinjal        = (max_prob - 0.33) / 0.67

    if p1_mc > p2_mc and p1_mc > px_mc:
        forma_score = forma_1["win_rate"]
    elif p2_mc > p1_mc and p2_mc > px_mc:
        forma_score = forma_2["win_rate"]
    else:
        forma_score = 0.35

    bonus_rez     = prob_rez_sakt * 0.5
    raw           = 0.35 * konsensus + 0.30 * sinjal + 0.25 * forma_score + 0.10 * bonus_rez
    besueshmeria  = 55.0 + (raw * 37.0)
    return round(float(np.clip(besueshmeria, 55.0, 92.0)), 1)

# ==========================================
# MODULI 6: DESPERATION & KAOS LIGES
# ==========================================

INJURIES_CACHE = {}
INJURIES_CACHE_TTL = 6 * 3600  # 6 orE — lendimet nuk ndryshojne shpesh

def _merr_lendimet(fixture_id):
    """Numri i lojtareve te lenduar/pezulluar per ekip nga API-Football (/injuries?fixture).
    Kthen {team_id: count}. Cache per fixture 6h. Bosh nese s'ka mbulim (kualifikime/klube te vogla)."""
    if not fixture_id:
        return {}
    ck = str(fixture_id)
    tani = time.time()
    cached = INJURIES_CACHE.get(ck)
    if cached and (tani - cached[1] < INJURIES_CACHE_TTL):
        return cached[0]
    out = {}
    try:
        data = _api_sports_get("injuries", {"fixture": fixture_id})
        for it in (data.get("response", []) if data else []):
            tid = (it.get("team", {}) or {}).get("id")
            if tid is not None:
                out[tid] = out.get(tid, 0) + 1
    except Exception:
        pass
    INJURIES_CACHE[ck] = (out, tani)
    return out

def llogarit_desperation_index(ekipi_id, standings):
    if not standings:
        return 1.0
    try:
        for r in standings:
            if r.get("team", {}).get("id") == ekipi_id:
                pozicioni  = r.get("rank", 10)
                total_ekipe = len(standings)
                if pozicioni >= total_ekipe - 3 or pozicioni <= 3:
                    return 1.15
    except:
        pass
    return 1.0

def _info_renditje(ekipi_id, standings):
    """Nxjerr pozicionin/piket/diferencen/ndeshjet e nje ekipi nga tabela (standings).
    Kthen {} nese s'ka tabele (knockout/kombetare) ose ekipi s'gjendet."""
    if not standings:
        return {}
    try:
        for r in standings:
            if r.get("team", {}).get("id") == ekipi_id:
                _all = r.get("all", {}) or {}
                return {
                    "pozicion": r.get("rank"),
                    "pike": r.get("points"),
                    "diferenca_golash": r.get("goalsDiff"),
                    "ndeshje_luajtura": _all.get("played"),
                    "total_ekipe": len(standings),
                }
    except Exception:
        pass
    return {}

def apliko_kaosin_e_liges(emri_liges: str, vol_1: float = 15.0, vol_2: float = 15.0) -> float:
    liga = emri_liges.lower()
    if any(x in liga for x in ["world cup", "euro", "copa america", "nations league"]):
        base = 1.25
    elif any(x in liga for x in ["championship", "segunda", "ligue 2", "serie b", "superliga"]):
        base = 1.20
    elif any(x in liga for x in ["premier", "champions league", "la liga", "bundesliga"]):
        base = 1.05
    else:
        base = 1.10
    if vol_1 > 20.0 or vol_2 > 20.0:
        base *= 1.12
    return base

# ==========================================
# MOTORI KRYESOR I ANALIZËS V2
# ==========================================

def _lambda_nga_p_over(p_over):
    """Gjej lambda (totali i pritur i golave) qe jep kete P(mbi 2.5) sipas Poisson. Bisection."""
    import math
    def _p_mbi(lam):
        return 1.0 - math.exp(-lam) * (1.0 + lam + lam * lam / 2.0)
    lo, hi = 0.4, 6.0
    p_over = min(0.98, max(0.02, float(p_over)))
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _p_mbi(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 3)

def llogarit_modulator(forma, lendime=0):
    """MODULATORI — rregullim i xG-së në FUND, nga fakte të verifikueshme.
    Aktive tani: regresion i serisë së fitoreve + kongjestioni (ndeshje në 14 ditë)
    + LËNDIME/pezullime (API-Football). Hapësirë e ardhshme: formacione, lëvizje kuotash, mot."""
    k    = int(forma.get("k_wins_rresht", 0) or 0)
    cong = int(forma.get("ndeshje_14d", 0) or 0)
    streak_pen = 0.030 * max(0, k - 3)      # mean reversion pas serive të gjata
    cong_pen   = 0.035 * max(0, cong - 3)   # lodhje nga kongjestioni
    injury_pen = min(INJURY_PEN_CAP, INJURY_PEN_PER * max(0, int(lendime or 0)))  # lëndime (tunable)
    mod = 1.0 - min(0.20, streak_pen + cong_pen) - injury_pen
    return round(max(0.60, mod), 3)         # dysheme që të mos bjerë shumë


def analizo_ndeshjen_premium_master(
    id_ndeshja, ekipi_1, ekipi_2,
    ekipi_1_id, ekipi_2_id,
    k1_str, kx_str, k2_str,
    emri_liges, standings,
    dna_1=None, dna_2=None, odds_full=None
):
    """
    Versioni V2 i plotë — zëvendëson funksionin origjinal.
    Ndryshimet:
      - Forma reale (jo random)
      - xG i peshuar nga 4 burime
      - Monte Carlo numpy 50k iteracione
      - Besueshmëria me konsensus
      - Pa manipulim rezultatesh
    """
    k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)

    marzhi  = 1/k1 + 1/kx + 1/k2
    p1_real = (1/k1) / marzhi
    px_real = (1/kx) / marzhi
    p2_real = (1/k2) / marzhi

    # DNA / ELO
    elo_1    = float(dna_1.get("historical_power", merr_elo_baze(ekipi_1))) if dna_1 else merr_elo_baze(ekipi_1)
    elo_2    = float(dna_2.get("historical_power", merr_elo_baze(ekipi_2))) if dna_2 else merr_elo_baze(ekipi_2)
    clutch_1 = float(dna_1.get("clutch_factor", 1.0))    if dna_1 else 1.0
    clutch_2 = float(dna_2.get("clutch_factor", 1.0))    if dna_2 else 1.0
    vol_1    = float(dna_1.get("volatility_index", 15.0)) if dna_1 else 15.0
    vol_2    = float(dna_2.get("volatility_index", 15.0)) if dna_2 else 15.0
    draw_1   = float(dna_1.get("draw_affinity", 30.0))   if dna_1 else 30.0
    draw_2   = float(dna_2.get("draw_affinity", 30.0))   if dna_2 else 30.0

    desp_1 = llogarit_desperation_index(ekipi_1_id, standings)
    desp_2 = llogarit_desperation_index(ekipi_2_id, standings)

    _rend_1 = _info_renditje(ekipi_1_id, standings)
    _rend_2 = _info_renditje(ekipi_2_id, standings)

    # ── FORMA REALE (me cache) ──
    forma_1 = merr_formen_reale(ekipi_1_id, emri_liges)
    forma_2 = merr_formen_reale(ekipi_2_id, emri_liges)

    # ── XG TË AVANCUARA ──
    kaosi_liges = apliko_kaosin_e_liges(emri_liges, vol_1, vol_2)
    is_derbi    = abs(elo_1 * desp_1 - elo_2 * desp_2) <= 30

    xg_1, xg_2 = llogarit_xg_te_perparuara(
        forma_1, forma_2,
        elo_1 * desp_1, elo_2 * desp_2,
        p1_real, p2_real
    )

    # ── HYBRID: kombino me XGBoost (nëse gati; ndryshe mban math) ──
    # ── AH (linja kryesore) + O/U 2.5 nga odds reale -> veçori per XGBoost ──
    _ahk = _ah_kryesore((odds_full or {}).get("AH")) if odds_full else None
    _ah_l = _ahk[0] if _ahk else None
    _ah_h = _ahk[1] if _ahk else None
    _ah_a = _ahk[2] if _ahk else None
    _ou_o = (odds_full or {}).get("Over 2.5") if odds_full else None
    _ou_u = (odds_full or {}).get("Under 2.5") if odds_full else None

    xg_1, xg_2, burimi_xg, _frac_ht_1, _frac_ht_2 = llogarit_xg_hybrid(
        forma_1, forma_2, p1_real, p2_real,
        k1, kx, k2, emri_liges,
        xg_1, xg_2,
        ah_line=_ah_l, ah_home=_ah_h, ah_away=_ah_a,
        ou_over=_ou_o, ou_under=_ou_u
    )

    # ── MODULATORI (treg/ELO) — PAS hibridit, mbi xG-nE FINALE (jo te holluar nga XGBoost) ──
    # De-kompreson xG-nE reale drejt tregut+ELO. Underdog i fryrE -> ulet -> decisivitet.
    _p1e_m = 1.0 / (1.0 + 10 ** (-((elo_1 * desp_1) - (elo_2 * desp_2)) / 400.0))
    _p2e_m = 1.0 - _p1e_m
    _xg1_mkt = XG_FLOOR + p1_real * (3.2 - XG_FLOOR)
    _xg2_mkt = XG_FLOOR + p2_real * (3.2 - XG_FLOOR)
    _xg1_elo = XG_FLOOR + _p1e_m * (3.0 - XG_FLOOR)
    _xg2_elo = XG_FLOOR + _p2e_m * (3.0 - XG_FLOOR)
    _mod1 = (_xg1_mkt - xg_1) * MOD_K_TREG + (_xg1_elo - xg_1) * MOD_K_ELO
    _mod2 = (_xg2_mkt - xg_2) * MOD_K_TREG + (_xg2_elo - xg_2) * MOD_K_ELO
    _mod1 = float(np.clip(_mod1, MOD_KUFI_POSHTE, MOD_KUFI_LART))
    _mod2 = float(np.clip(_mod2, MOD_KUFI_POSHTE, MOD_KUFI_LART))
    xg_1 = float(np.clip(xg_1 + _mod1, 0.30, 5.00))
    xg_2 = float(np.clip(xg_2 + _mod2, 0.30, 5.00))

    # Apliko clutch
    xg_1 *= clutch_1
    xg_2 *= clutch_2

    # Draw affinity — ulë xG nëse të dyja skuadrat janë barazi-prirëse
    if draw_1 > 35.0 and draw_2 > 35.0:
        xg_1 *= 0.90
        xg_2 *= 0.90

    # Derbi — rrit pak pasigurinë
    if is_derbi:
        xg_1 *= 1.10
        xg_2 *= 1.10

    # ── MODULATORI (lodhje + kongjestion + lëndime) — aplikohet në FUND mbi xG ──
    _lend = _merr_lendimet(id_ndeshja)
    _lend_1 = int(_lend.get(ekipi_1_id, 0))
    _lend_2 = int(_lend.get(ekipi_2_id, 0))
    _mod_1 = llogarit_modulator(forma_1, _lend_1)
    _mod_2 = llogarit_modulator(forma_2, _lend_2)
    xg_1 *= _mod_1
    xg_2 *= _mod_2

    # Kap brenda kufijve pas modifikimeve
    xg_1 = float(np.clip(xg_1, 0.30, 5.00))
    xg_2 = float(np.clip(xg_2, 0.30, 5.00))

    # ── MODULATORI I TOTALIT: shtyn totalin drejt sinjalit real (forma + treg O/U) — RUAN drejtimin ──
    # total_xg eshte i ngjeshur; kjo fut variancE (rishkallezon te dyja me te njejtin faktor -> raporti/drejtimi s'ndryshon).
    _total_aktual = xg_1 + xg_2
    _home_form_g = (float(forma_1.get("avg_gola_shenuar", 1.3)) + float(forma_2.get("avg_gola_prane", 1.3))) / 2.0
    _away_form_g = (float(forma_2.get("avg_gola_shenuar", 1.3)) + float(forma_1.get("avg_gola_prane", 1.3))) / 2.0
    _total_form = _home_form_g + _away_form_g
    _total_target = _total_form
    if _ou_o and _ou_u:
        try:
            _p_over = (1.0 / float(_ou_o)) / (1.0 / float(_ou_o) + 1.0 / float(_ou_u))
            _lam_treg = _lambda_nga_p_over(_p_over)
            _total_target = 0.5 * _total_form + 0.5 * _lam_treg   # blend forma + treg (kur ka odds O/U)
        except Exception:
            pass
    _total_i_ri = _total_aktual + TOTAL_K * (_total_target - _total_aktual)
    _total_i_ri = float(np.clip(_total_i_ri, TOTAL_MIN, TOTAL_MAX))
    if _total_aktual > 0.10:
        _shk_total = _total_i_ri / _total_aktual
        xg_1 = float(np.clip(xg_1 * _shk_total, 0.20, 5.00))
        xg_2 = float(np.clip(xg_2 * _shk_total, 0.20, 5.00))

    # ── MONTE CARLO V2 (numpy, 50k) ──
    _seed_ndeshja = int(hashlib.sha256(str(id_ndeshja).encode()).hexdigest()[:8], 16)
    rez_sakt, prob_rez_sakt, rezultatet_freq, prob_1x2_mc, tregjet_mc = simulim_monte_carlo_v2(
        xg_1, xg_2, kaosi_liges, is_derbi, iteracione=50_000, seed=_seed_ndeshja
    )

    # ── HT/FT — SIMULIM I PAVARUR (gjysma e parë simulohet veçmas, jo nga skori FT) ──
    _frac_h1 = _frac_ht_1 if _frac_ht_1 is not None else 0.44
    _frac_h2 = _frac_ht_2 if _frac_ht_2 is not None else 0.44
    _xg_ht_1 = max(0.05, _frac_h1 * xg_1)
    _xg_ht_2 = max(0.05, _frac_h2 * xg_2)
    _xg_2h_1 = max(0.05, xg_1 - _xg_ht_1)
    _xg_2h_2 = max(0.05, xg_2 - _xg_ht_2)
    try:
        _htft_dist, _skor_ht, _prob_ht, _ht_mkt = simulim_ht_ft_mc(_xg_ht_1, _xg_ht_2, _xg_2h_1, _xg_2h_2, seed=_seed_ndeshja)
        tregjet_mc["ht_ft"] = _htft_dist
        tregjet_mc["skor_ht"] = _skor_ht   # skori HT i pavarur nga FT
        tregjet_mc.update(_ht_mkt)          # HT si mini-FT: të gjitha tregjet HT
    except Exception as _e:
        # GARANCIA: HT s'lejohet të mungojë — fallback analitik Poisson (deterministik)
        # nga të NJËJTAT xG hibride të gjysmëve. Skori HT = moda e rrjetës Poisson.
        print(f"⚠️ HT/FT MC dështoi ({_e}) — fallback analitik Poisson")
        try:
            tregjet_mc["ht_ft"] = _ht_ft_distribuim(_xg_ht_1, _xg_ht_2, _xg_2h_1, _xg_2h_2)
        except Exception:
            pass
        try:
            def _pmf_ht(lam, kmax=6):
                out = []; p = math.exp(-lam)
                for k in range(kmax + 1):
                    out.append(p); p = p * lam / (k + 1)
                return out
            _ph, _pa = _pmf_ht(max(0.05, _xg_ht_1)), _pmf_ht(max(0.05, _xg_ht_2))
            _grid = {(i, j): _ph[i] * _pa[j] for i in range(7) for j in range(7)}
            _tot_g = sum(_grid.values()) or 1.0
            _bi, _bj = max(_grid, key=_grid.get)
            tregjet_mc["skor_ht"] = f"{_bi}-{_bj}"
            # Tregjet bazë HT nga e njëjta rrjetë (koherente me skor_ht)
            _p1 = sum(v for (i, j), v in _grid.items() if i > j) / _tot_g
            _px = sum(v for (i, j), v in _grid.items() if i == j) / _tot_g
            _p2 = sum(v for (i, j), v in _grid.items() if i < j) / _tot_g
            _po05 = sum(v for (i, j), v in _grid.items() if i + j > 0) / _tot_g
            _pgg = sum(v for (i, j), v in _grid.items() if i > 0 and j > 0) / _tot_g
            tregjet_mc.update({
                "HT 1": round(_p1, 4), "HT X": round(_px, 4), "HT 2": round(_p2, 4),
                "HT 1X": round(_p1 + _px, 4), "HT X2": round(_px + _p2, 4), "HT 12": round(_p1 + _p2, 4),
                "HT Over 0.5": round(_po05, 4), "HT Under 0.5": round(1 - _po05, 4),
                "HT GG": round(_pgg, 4), "HT NG": round(1 - _pgg, 4),
                ("HT CS " + str(_bi) + "-" + str(_bj)): round(_grid[(_bi, _bj)] / _tot_g, 4),
            })
        except Exception:
            tregjet_mc.setdefault("skor_ht", "0-0")   # mburoja e fundit — kurrë pa skor HT

    try:
        g1, g2 = map(int, rez_sakt.split("-"))
    except:
        g1, g2 = 1, 0

    # Fallback: nëse total gola shumë i ulët por xG tregon lojë të hapur
    if (g1 + g2 <= 1) and (xg_1 + xg_2 > 2.5):
        for r, freq in sorted(rezultatet_freq.items(), key=lambda x: x[1], reverse=True):
            try:
                rg1, rg2 = map(int, r.split("-"))
                if rg1 + rg2 > 1:
                    rez_sakt       = r
                    g1, g2         = rg1, rg2
                    prob_rez_sakt  = freq / 50_000
                    break
            except:
                continue

    # ── BESUESHMËRIA V2 ──
    besueshmeria = llogarit_besueshmeria_v2(
        prob_1x2_mc, p1_real, p2_real, px_real,
        prob_rez_sakt, forma_1, forma_2
    )

    # ── VALUE BET (nga probabilitetet MC) — tani gjenerohet brenda anal_dict per gjuhe ──
    p1_mc = prob_1x2_mc["p1"]
    p2_mc = prob_1x2_mc["p2"]
    px_mc = prob_1x2_mc["px"]

    # ── BLLOF DETECTION (i zgjeruar) ──
    eshte_bllof = (
        (k1 < 1.55 and p2_mc > 0.28) or
        (k2 < 1.55 and p1_mc > 0.28)
    )

    # ── ANALIZA TEKSTUALE NË 5 GJUHË (Versioni i ri - i përgjithshëm) ──

    # Përkthimet e zgjedhura
    vb_translations = {"sq": "💎 Value Bet:", "en": "💎 Value Bet:",
                       "de": "💎 Value Bet:", "fr": "💎 Pari Valeur:",
                       "it": "💎 Value Bet:"}
    sugg_label = {"sq": "Sugjerim", "en": "Suggestion",
                  "de": "Empfehlung", "fr": "Suggestion", "it": "Suggerimento"}
    fitues_label = {"sq": "Fiton", "en": "Wins",
                    "de": "Gewinnt", "fr": "Gagne", "it": "Vince"}
    over_label = {"sq": "Mbi", "en": "Over", "de": "Über", "fr": "Plus de", "it": "Oltre"}
    under_label = {"sq": "Nën", "en": "Under", "de": "Unter", "fr": "Moins de", "it": "Sotto"}
    gola_label = {"sq": "gola", "en": "goals", "de": "Tore", "fr": "buts", "it": "gol"}

    # Përcaktimi i FAVORITIT bazuar në PARASHIKIMIN (jo në probabilitete teknike)
    # g1 = parashikimi gola_ekipi_1, g2 = parashikimi gola_ekipi_2
    if g1 > g2:
        fituesi_id = 1
        fituesi_emer = ekipi_1
        humbsi_emer = ekipi_2
        p_fituesi = p1_mc
        koef_fituesi = k1
    elif g2 > g1:
        fituesi_id = 2
        fituesi_emer = ekipi_2
        humbsi_emer = ekipi_1
        p_fituesi = p2_mc
        koef_fituesi = k2
    else:
        fituesi_id = 0  # barazim
        fituesi_emer = ""
        humbsi_emer = ""
        p_fituesi = px_mc
        koef_fituesi = kx

    # VALUE BET: kontrollohet VETËM në drejtimin që përputhet me parashikimin
    def gjeneroVbText(gj):
        if fituesi_id == 0:
            # Për barazim, kontrollo VB në X
            vb = detect_value_bet(px_mc, kx)
            if vb:
                draw_label = {"sq": "Barazim", "en": "Draw", "de": "Unentschieden",
                              "fr": "Match Nul", "it": "Pareggio"}
                return f"<br><b style='color:#00ff00;'>{vb_translations[gj]}</b> {draw_label[gj]} (Vlera: {vb}%)"
            return ""
        vb = detect_value_bet(p_fituesi, koef_fituesi)
        if vb:
            return f"<br><b style='color:#00ff00;'>{vb_translations[gj]}</b> {fitues_label[gj]} {fituesi_emer} (Vlera: {vb}%)"
        return ""

    bllof_msg = {
        "sq": "🔥 Ekskluzive: Sugjerohet Përmbysje!",
        "en": "🔥 Exclusive: Comeback suggested!",
        "de": "🔥 Exklusiv: Comeback vorgeschlagen!",
        "fr": "🔥 Exclusif: Retournement suggéré!",
        "it": "🔥 Esclusivo: Rimonta suggerita!"
    }

    def gjeneroHtFt(gj):
        return f"<br><b style='color:#ff4500;'>{bllof_msg[gj]}</b>" if eshte_bllof else ""

    # ── ANALIZAT E PËRGJITHSHME (pa detaje teknike si ELO, xG, Forma %) ──
    # User-it i japim VETËM 20-30% të informacionit teknik. Fjalori i butë.
    anal_dict = {}

    for gj in ["sq", "en", "de", "fr", "it"]:
        vb_text_gj = gjeneroVbText(gj)
        ht_ft_text_gj = gjeneroHtFt(gj)

        if eshte_bllof:
            # Risk - kurth i tregut
            risk_text = {
                "sq": f"⚠️ <b>Vëmendje:</b> Tregjet po reagojnë në kah të kundërt me të dhënat tona statistikore. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Mundësi për surprizë.",
                "en": f"⚠️ <b>Attention:</b> Markets are reacting opposite to our statistical data. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Possible upset.",
                "de": f"⚠️ <b>Achtung:</b> Märkte reagieren gegensätzlich zu unseren statistischen Daten. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Überraschung möglich.",
                "fr": f"⚠️ <b>Attention:</b> Les marchés réagissent à l'opposé de nos données statistiques. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Possible surprise.",
                "it": f"⚠️ <b>Attenzione:</b> I mercati reagiscono in modo opposto ai nostri dati statistici. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Possibile sorpresa.",
            }
            anal_dict[gj] = f"{risk_text[gj]}{ht_ft_text_gj}{vb_text_gj}"

        elif g1 == g2:
            # Barazim
            if (g1 + g2) >= 2:
                # Barazim me gola (1-1, 2-2)
                bal_text = {
                    "sq": f"Ndeshje e ekuilibruar mes dy ekipeve me potencial të mirë sulmues. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Të dyja shënojnë (GG) ose barazim.",
                    "en": f"Balanced match between two teams with good attacking potential. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Both teams to score (BTTS) or Draw.",
                    "de": f"Ausgeglichenes Spiel zwischen zwei Teams mit guter Angriffsstärke. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Beide treffen (BTTS) oder Unentschieden.",
                    "fr": f"Match équilibré entre deux équipes avec un bon potentiel offensif. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Les deux marquent (BTTS) ou Match Nul.",
                    "it": f"Partita equilibrata tra due squadre con buon potenziale offensivo. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Entrambe segnano (GG) o Pareggio.",
                }
            else:
                # Barazim taktik (0-0)
                bal_text = {
                    "sq": f"Ndeshje taktike, ku të dyja ekipet ruajnë ekuilibrin defensiv. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Barazim ose nën 2.5 gola.",
                    "en": f"Tactical match where both teams maintain defensive balance. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Draw or Under 2.5 goals.",
                    "de": f"Taktisches Spiel, bei dem beide Teams das defensive Gleichgewicht halten. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Unentschieden oder Unter 2.5 Tore.",
                    "fr": f"Match tactique où les deux équipes maintiennent l'équilibre défensif. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Match Nul ou Moins de 2.5 buts.",
                    "it": f"Partita tattica dove entrambe le squadre mantengono l'equilibrio difensivo. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> Pareggio o Sotto 2.5 gol.",
                }
            anal_dict[gj] = f"{bal_text[gj]}{ht_ft_text_gj}{vb_text_gj}"

        elif g1 > g2:
            # Ekipi 1 fiton
            if (g1 + g2) >= 3:
                # Fitore me shumë gola - DOMINIM
                dom_text = {
                    "sq": f"<b>{ekipi_1}</b> tregon avantazh të qartë sulmues dhe pritet të imponojë ritmin. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} ose {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "en": f"<b>{ekipi_1}</b> shows clear attacking advantage and is expected to dictate the pace. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} or {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "de": f"<b>{ekipi_1}</b> zeigt klaren Angriffsvorteil und wird das Tempo bestimmen. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} oder {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "fr": f"<b>{ekipi_1}</b> montre un net avantage offensif et devrait imposer le rythme. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} ou {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "it": f"<b>{ekipi_1}</b> mostra chiaro vantaggio offensivo e dovrebbe dettare il ritmo. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} o {over_label[gj]} 2.5 {gola_label[gj]}.",
                }
                anal_dict[gj] = f"{dom_text[gj]}{ht_ft_text_gj}{vb_text_gj}"
            else:
                # Fitore taktike (1-0, 2-1)
                ctrl_text = {
                    "sq": f"<b>{ekipi_1}</b> ka avantazhin e fushës dhe pritet të menaxhojë lojën. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} ose {under_label[gj]} 3.5 {gola_label[gj]}.",
                    "en": f"<b>{ekipi_1}</b> has the home advantage and is expected to control the game. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} or {under_label[gj]} 3.5 {gola_label[gj]}.",
                    "de": f"<b>{ekipi_1}</b> hat den Heimvorteil und wird das Spiel kontrollieren. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} oder {under_label[gj]} 3.5 {gola_label[gj]}.",
                    "fr": f"<b>{ekipi_1}</b> a l'avantage du terrain et devrait contrôler le jeu. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} ou {under_label[gj]} 3.5 {gola_label[gj]}.",
                    "it": f"<b>{ekipi_1}</b> ha il vantaggio del campo e dovrebbe controllare il gioco. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_1} o {under_label[gj]} 3.5 {gola_label[gj]}.",
                }
                anal_dict[gj] = f"{ctrl_text[gj]}{ht_ft_text_gj}{vb_text_gj}"

        else:
            # Ekipi 2 fiton
            if (g1 + g2) >= 3:
                # Fitore në transfertë me gola
                away_text = {
                    "sq": f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë dhe është favorit i fshehur. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} ose {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "en": f"<b>{ekipi_2}</b> performs excellently away and is a hidden favorite. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} or {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "de": f"<b>{ekipi_2}</b> spielt auswärts hervorragend und ist ein versteckter Favorit. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} oder {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "fr": f"<b>{ekipi_2}</b> performe excellemment à l'extérieur et est un favori caché. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} ou {over_label[gj]} 2.5 {gola_label[gj]}.",
                    "it": f"<b>{ekipi_2}</b> performa eccellentemente in trasferta ed è un favorito nascosto. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} o {over_label[gj]} 2.5 {gola_label[gj]}.",
                }
                anal_dict[gj] = f"{away_text[gj]}{ht_ft_text_gj}{vb_text_gj}"
            else:
                # Fitore taktike e transfertës
                manage_text = {
                    "sq": f"<b>{ekipi_2}</b> ka momentum të mirë dhe pritet të menaxhojë ndeshjen. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} ose X2.",
                    "en": f"<b>{ekipi_2}</b> has good momentum and is expected to manage the match. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} or X2.",
                    "de": f"<b>{ekipi_2}</b> hat guten Schwung und wird das Spiel verwalten. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} oder X2.",
                    "fr": f"<b>{ekipi_2}</b> a un bon élan et devrait gérer le match. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} ou X2.",
                    "it": f"<b>{ekipi_2}</b> ha un buon slancio e dovrebbe gestire la partita. <br><b style='color:#f2cc60;'>{sugg_label[gj]}:</b> {fitues_label[gj]} {ekipi_2} o X2.",
                }
                anal_dict[gj] = f"{manage_text[gj]}{ht_ft_text_gj}{vb_text_gj}"

    # ── ETIKETA E MARGJINËS (AH ±1.5) → shtohet te analiza tekstuale ──
    _marg = _etiketa_margjines(rezultatet_freq, ekipi_1, ekipi_2)
    if _marg:
        for _gj in anal_dict:
            anal_dict[_gj] += _marg_suffix_html(_marg, _gj)

    koef_rez_sakt = min(40.0, (1 / prob_rez_sakt) * 0.85) if prob_rez_sakt > 0 else 10.0

    # ── BEST BET: tregu me probabilitetin më të lartë ──
    _kand = [t for t in TREGJET_KANDIDATE if t in tregjet_mc]
    _best_t = max(_kand, key=lambda t: tregjet_mc[t]) if _kand else "1X"
    _best_p = float(tregjet_mc.get(_best_t, 0))
    best_bet = {"tregu": _best_t, "prob": round(_best_p, 4),
                "koef": round(1.0 / _best_p, 2) if _best_p > 0 else None}
    best_bet["margjina"] = _marg

    extradb = {
        "is_bllof":     eshte_bllof,
        "koef_plote":   f"1:{k1_str} | X:{kx_str} | 2:{k2_str}",
        "tregjet":      tregjet_mc,
        "dist_gola":    rezultatet_freq,
        "best_bet":     best_bet,
        "prob_1x2_mc":  prob_1x2_mc,
        "xg_debug":     {"xg_1": round(xg_1, 3), "xg_2": round(xg_2, 3)},
        "forma_1":      {k: forma_1[k] for k in ["win_rate", "k_wins_rresht", "lodhja_factor"]},
        "forma_2":      {k: forma_2[k] for k in ["win_rate", "k_wins_rresht", "lodhja_factor"]},
        "training_data": {
            # ── OUTPUTET FINALE ──
            "xg_1": round(float(xg_1), 3), "xg_2": round(float(xg_2), 3),
            "prob_1x2_mc": prob_1x2_mc,
            # ── FORCA / VLERESIMI ──
            "elo_1": round(float(elo_1), 1), "elo_2": round(float(elo_2), 1),
            "p_market_1": round(float(p1_real), 4), "p_market_2": round(float(p2_real), 4),
            "burimi_xg": burimi_xg,
            # ── MODULUESIT E APLIKUAR (per te rikrijuar zinxhirin) ──
            "modulator_1": round(float(_mod_1), 3), "modulator_2": round(float(_mod_2), 3),
            "clutch_1": round(float(clutch_1), 3), "clutch_2": round(float(clutch_2), 3),
            "draw_aff_1": round(float(draw_1), 1), "draw_aff_2": round(float(draw_2), 1),
            "desp_1": round(float(desp_1), 3), "desp_2": round(float(desp_2), 3),
            "vol_1": round(float(vol_1), 3), "vol_2": round(float(vol_2), 3),
            "kaos_liges": round(float(kaosi_liges), 3), "is_derbi": bool(is_derbi),
            "frac_ht_1": round(float(_frac_ht_1), 3) if _frac_ht_1 is not None else None,
            "frac_ht_2": round(float(_frac_ht_2), 3) if _frac_ht_2 is not None else None,
            # ── FEATURES-ET E FORMES (inputet qe prodhuan xG — per ritrajnim) ──
            "home_avg_scored": round(float(forma_1.get("avg_gola_shenuar", 1.3)), 3),
            "home_avg_conceded": round(float(forma_1.get("avg_gola_prane", 1.3)), 3),
            "away_avg_scored": round(float(forma_2.get("avg_gola_shenuar", 1.3)), 3),
            "away_avg_conceded": round(float(forma_2.get("avg_gola_prane", 1.3)), 3),
            "home_scored_home": round(float(forma_1.get("avg_shenuar_home", forma_1.get("avg_gola_shenuar", 1.3))), 3),
            "home_conceded_home": round(float(forma_1.get("avg_prane_home", forma_1.get("avg_gola_prane", 1.3))), 3),
            "away_scored_away": round(float(forma_2.get("avg_shenuar_away", forma_2.get("avg_gola_shenuar", 1.3))), 3),
            "away_conceded_away": round(float(forma_2.get("avg_prane_away", forma_2.get("avg_gola_prane", 1.3))), 3),
            "home_forma_pts": float(forma_1.get("piket_forma", 7.0)),
            "away_forma_pts": float(forma_2.get("piket_forma", 7.0)),
            "home_win_rate": round(float(forma_1.get("win_rate", 0.5)), 3),
            "away_win_rate": round(float(forma_2.get("win_rate", 0.5)), 3),
            # ── RENDITJA NE ATE MOMENT (nga tabela; bosh per knockout/kombetare) ──
            "pozicion_1": _rend_1.get("pozicion"), "pozicion_2": _rend_2.get("pozicion"),
            "pike_1": _rend_1.get("pike"), "pike_2": _rend_2.get("pike"),
            "diferenca_golash_1": _rend_1.get("diferenca_golash"), "diferenca_golash_2": _rend_2.get("diferenca_golash"),
            "ndeshje_luajtura_1": _rend_1.get("ndeshje_luajtura"), "ndeshje_luajtura_2": _rend_2.get("ndeshje_luajtura"),
            "total_ekipe_liga": _rend_1.get("total_ekipe") or _rend_2.get("total_ekipe"),
            # ── LINJAT E TREGUT (O/U 2.5 + AH — sinjali qe mungonte per O/U/total) ──
            "p_market_x": round(float(px_real), 4),
            "ah_line": _ah_l, "ah_home_odds": _ah_h, "ah_away_odds": _ah_a,
            "ou_over_odds": _ou_o, "ou_under_odds": _ou_u,
            # ── INPUTET E MODULATORIT (per akordim me vone) ──
            "streak_1": int(forma_1.get("k_wins_rresht", 0) or 0), "streak_2": int(forma_2.get("k_wins_rresht", 0) or 0),
            "kongjestion_1": int(forma_1.get("ndeshje_14d", 0) or 0), "kongjestion_2": int(forma_2.get("ndeshje_14d", 0) or 0),
            "lendime_1": _lend_1, "lendime_2": _lend_2,
            "total_form": round(float(_total_form), 3), "total_target": round(float(_total_target), 3),
        },
    }

    return anal_dict, besueshmeria, rez_sakt, f"{koef_rez_sakt:.2f}", extradb

# ==========================================
# RUAJTJA NË DB — PA MANIPULIM REZULTATESH
# ==========================================

def task_ruaj_skedinen_ne_db(ndeshjet_premium):
    """
    Ruan vetëm 3 ndeshjet PPM në Supabase.
    Dërgon VETËM kolonat që ekzistojnë në tabelën predictions.
    Ruan analiza_custom (jsonb) për historikun.
    """
    headers = SUPABASE_SERVICE_HEADERS.copy()
    headers["Prefer"] = "resolution=merge-duplicates"

    # Kolonat e sakta që ekzistojnë në tabelën predictions
    KOLONAT_VALIDE = {
        "id", "liga_id", "sezoni", "ekipi_1_id", "ekipi_2_id",
        "ekipi_1", "ekipi_2", "ndeshja", "data", "ora", "ora_sakte",
        "koha_utc", "statusi", "minuta", "rezultati", "koef_1", "koef_x",
        "koef_2", "analiza_custom", "besueshmeria", "rezultati_sakt",
        "koef_rez_sakt", "is_premium", "is_bllof", "koef_plote", "tregjet", "best_bet", "odds_reale", "dist_gola",
        "liga_emri", "parashikimi_origjinal_ai", "training_data"
    }

    # FREEZE: ngri VETËM fushat që tashmë kanë vlerë në DB (lejon backfill të null-eve, p.sh. dist_gola)
    FUSHA_NGRIRA = ("rezultati_sakt", "dist_gola", "koef_rez_sakt", "parashikimi_origjinal_ai")
    _ids = [str(nd.get("id")) for nd in ndeshjet_premium if nd.get("id") is not None]
    ekziston_fusha = {}   # id -> set e fushave që tashmë kanë vlerë (jo null)
    if _ids:
        try:
            _sel = "id," + ",".join(FUSHA_NGRIRA)
            _q = requests.get(
                f"{SUPABASE_URL_PREDS}?id=in.({','.join(_ids)})&select={_sel}",
                headers=headers, timeout=8)
            if _q.status_code == 200:
                for rr in _q.json():
                    ekziston_fusha[str(rr.get("id"))] = {f for f in FUSHA_NGRIRA if rr.get(f) is not None}
        except:
            pass

    for nd in ndeshjet_premium:
        # Ndërto payload vetëm me kolonat valide
        pako = {k: v for k, v in nd.items() if k in KOLONAT_VALIDE}

        # Sigurohu parashikimi_origjinal_ai ekziston
        if "parashikimi_origjinal_ai" not in pako:
            pako["parashikimi_origjinal_ai"] = pako.get("rezultati_sakt", "")

        # FREEZE: mos mbishkruaj VETËM fushat që tashmë kanë vlerë (null-et lejohen të mbushen)
        for _f in ekziston_fusha.get(str(pako.get("id")), ()):
            pako.pop(_f, None)

        try:
            r = requests.post(SUPABASE_URL_PREDS, headers=headers, json=pako, timeout=5)
            # Nëse insert dështon (p.sh. kolonë e panjohur), provo update
            if r.status_code not in [200, 201, 204]:
                requests.patch(
                    f"{SUPABASE_URL_PREDS}?id=eq.{pako['id']}",
                    headers=headers, json=pako, timeout=5
                )
        except:
            pass

# ==========================================
# ENDPOINTI KRYESOR - SKEDINA & PPM
# ==========================================

SKEDINA_CACHE       = {}
SKEDINA_LAST_UPDATE = {}

# ==========================================
# BACKGROUND TASK: Auto-update PPM finished matches
# ==========================================

def task_perditeso_ppm_te_perfunduara():
    """
    Kontrollon në Supabase për ndeshje PPM të paplotësuara dhe i përditëson.
    Thirret AUTOMATIKISHT në sfond çdo herë që ngarkohet skedina.
    Përdoruesi nuk pret — vetëm ata që hapin /api/skedina pas mbarimit do ta marrin.
    """
    try:
        # select i plotë → mundëson arkivim automatik në të njëjtin hap
        res = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,statusi,ndeshja,ekipi_1,ekipi_2,liga_emri,data,ora,ora_sakte,"
            f"koef_1,koef_x,koef_2,odds_reale,rezultati_sakt,tregjet,best_bet,besueshmeria,training_data,dist_gola"
            f"&statusi=not.in.(FT,AET,PEN,AWD,WO)",
            headers=SUPABASE_SERVICE_HEADERS, timeout=8
        )
        if res.status_code != 200:
            return
        ndeshjet_pa_mbaruar = res.json()
        if not ndeshjet_pa_mbaruar:
            return

        preds_by_id = {str(p.get("id")): p for p in ndeshjet_pa_mbaruar}
        match_ids = [str(n["id"]) for n in ndeshjet_pa_mbaruar]
        # Batch deri 20 IDs sipas API-Sports limit
        for i in range(0, len(match_ids), 20):
            batch = match_ids[i:i+20]
            ids_str = "-".join(batch)
            try:
                api_res = requests.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers=HEADERS, params={"ids": ids_str}, timeout=10
                )
                fixtures = api_res.json().get("response", [])
            except:
                continue

            for fx in fixtures:
                fix_id = str(fx["fixture"]["id"])
                status = fx["fixture"]["status"]["short"]
                gola_h = fx["goals"]["home"]
                gola_a = fx["goals"]["away"]

                if status in ["FT", "AET", "PEN", "AWD", "WO"] and gola_h is not None:
                    rezultati_str = _rezultati_ft(fx) or f"{gola_h} - {gola_a}"
                    update_payload = {
                        "statusi":   status,
                        "rezultati": rezultati_str,
                        "ora":       "FT",
                        "minuta":    90,
                    }
                    try:
                        requests.patch(
                            f"{SUPABASE_URL_PREDS}?id=eq.{fix_id}",
                            headers=SUPABASE_SERVICE_HEADERS,
                            json=update_payload, timeout=5
                        )
                    except:
                        pass
                    # ── ARKIVIM AUTOMATIK (PPM History + Performanca përditësohen menjëherë) ──
                    try:
                        _ht = (fx.get("score") or {}).get("halftime") or {}
                        _hth, _hta = _ht.get("home"), _ht.get("away")
                        _ht_str = f"{_hth} - {_hta}" if _hth is not None else None
                        _pred = preds_by_id.get(fix_id)
                        if _pred is not None:
                            _pred["rezultati"] = rezultati_str
                            _arkivo_ndeshje(_pred, _ht_str)
                    except Exception:
                        pass
    except:
        pass


# ==========================================
# CACHE I SKEDINËS NË DB (i qëndrueshëm — mbijeton restart-et e Render)
# ==========================================
SKEDINA_CACHE_URL = f"{SUPABASE_BASE}/rest/v1/skedina_cache"


def _lexo_cache_db(data_target, max_age_min=60):
    """Kthen (payload, fresh). fresh=True nëse u përditësua brenda max_age_min minutave."""
    try:
        r = requests.get(
            f"{SKEDINA_CACHE_URL}?data=eq.{data_target}&select=payload,perditesuar",
            headers=SUPABASE_SERVICE_HEADERS, timeout=5
        )
        rows = r.json()
        if not rows:
            return None, False
        payload = rows[0].get("payload")
        fresh = True
        ts = rows[0].get("perditesuar")
        if ts:
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
                fresh = (datetime.utcnow() - t).total_seconds() < max_age_min * 60
            except Exception:
                fresh = True
        return payload, fresh
    except Exception:
        return None, False


def _ruaj_cache_db(data_target, payload):
    try:
        headers = SUPABASE_SERVICE_HEADERS.copy()
        headers["Prefer"] = "resolution=merge-duplicates"
        requests.post(
            SKEDINA_CACHE_URL, headers=headers,
            json={"data": data_target, "payload": payload,
                  "perditesuar": datetime.utcnow().isoformat()},
            timeout=5
        )
    except Exception:
        pass


_LIVE_STATUSES_SET = {"1H","HT","2H","ET","BT","P","SUSP","INT","LIVE"}
_LIVE_REFRESH_TS = {}

def _me_live_fresh(payload, data_target):
    """Rifreskon ndeshjet LIVE ekzistuese DHE injekton live të reja që mungojnë në skedinë
    (p.sh. ndeshje që filluan pas gjenerimit nga cron-i). Kështu live-t shfaqen GJITHMONË."""
    try:
        if payload is None:
            payload = []
        now = time.time()
        if now - _LIVE_REFRESH_TS.get(data_target, 0) < 25:
            return payload  # u rifreskua së fundmi
        _LIVE_REFRESH_TS[data_target] = now
        # Indekso TË GJITHA ndeshjet ekzistuese sipas id
        ekzistuese = {}
        for liga in payload:
            for nd in liga.get("ndeshjet", []):
                ekzistuese[str(nd.get("id"))] = nd
        is_sot = (data_target == _data_lokale())
        te_reja = []
        live_ids = set()
        # live=all vetëm për SOT (injektim + rifreskim live-sh aktive)
        if is_sot:
            data = _api_sports_get("fixtures", {"live": "all"}, retries=2, timeout=8)
            if data and "response" in data:
                for fx in data["response"]:
                    try:
                        fid = str(fx["fixture"]["id"])
                        live_ids.add(fid)
                        st  = fx["fixture"]["status"]
                        gh  = fx["goals"]["home"]; ga = fx["goals"]["away"]
                        rez = _rezultati_ft(fx) or f"{gh if gh is not None else 0} - {ga if ga is not None else 0}"
                        if fid in ekzistuese:
                            nd = ekzistuese[fid]
                            nd["statusi"]   = st.get("short") or nd.get("statusi")
                            nd["minuta"]    = st.get("elapsed") or 0
                            nd["rezultati"] = rez
                        else:
                            e1 = fx["teams"]["home"]["name"].replace("'", "")
                            e2 = fx["teams"]["away"]["name"].replace("'", "")
                            te_reja.append({
                                "id": fid, "liga_id": fx["league"]["id"], "sezoni": fx["league"].get("season"),
                                "ekipi_1": e1, "ekipi_2": e2, "ndeshja": f"{e1} vs {e2}",
                                "ora_sakte": "", "koha_utc": fx["fixture"]["date"],
                                "statusi": st.get("short") or "1H", "minuta": st.get("elapsed") or 0,
                                "rezultati": rez, "koef_1": "N/A", "koef_x": "N/A", "koef_2": "N/A",
                                "analiza_custom": None, "is_motd": False, "is_premium": False,
                            })
                    except Exception:
                        continue

        # ── NDESHJET E MBARUARA (ÇDO datë): statusi live në cache por s'është (më) live ──
        # (pa këtë, një ndeshje si France-Suedi mbetet ngecur me "2H" edhe pasi mbaron;
        #  vlen edhe kur shikon një datë të kaluar ku cache-ja u ngri kur ndeshja ishte live)
        _STAT_LIVE = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
        te_verifiko = [fid for fid, nd in ekzistuese.items()
                       if str(nd.get("statusi")) in _STAT_LIVE and fid not in live_ids]
        for _i in range(0, len(te_verifiko), 20):
            _batch = te_verifiko[_i:_i + 20]
            _vd = _api_sports_get("fixtures", {"ids": "-".join(_batch)}, retries=1, timeout=8)
            for fx in (_vd or {}).get("response", []):
                try:
                    fid = str(fx["fixture"]["id"])
                    nd = ekzistuese.get(fid)
                    if nd is None:
                        continue
                    st = fx["fixture"]["status"]
                    _short = st.get("short")
                    gh = fx["goals"]["home"]; ga = fx["goals"]["away"]
                    if _short:
                        nd["statusi"] = _short
                    if _short in ("FT", "AET", "PEN", "AWD", "WO"):
                        nd["minuta"] = 90
                        nd["ora"] = "FT"
                    else:
                        nd["minuta"] = st.get("elapsed") or nd.get("minuta") or 0
                    if gh is not None:
                        nd["rezultati"] = _rezultati_ft(fx) or f"{gh} - {ga}"
                except Exception:
                    continue

        if te_reja:
            grup_live = {"liga": "🔴 LIVE", "ndeshjet": te_reja}
            payload = [grup_live] + [l for l in payload if l.get("liga") != "🔴 LIVE"]
        return payload
    except Exception:
        return payload


def _fshih_premium(grupet):
    """Heq rezultatin e sakte premium (rezultati_sakt/koef_rez_sakt) para se t'i dergoje klientit.
    MBUROJA E DYFISHTE: maskon si nga flamuri is_premium i payload-it, ashtu edhe nga lista LIVE
    e emrave premium (tabela PF) — keshtu edhe cache i vjeter (para flamurimit) maskohet sakte."""
    if not grupet:
        return grupet
    premium_live = _emrat_premium_live()
    out = []
    for liga in grupet:
        nd_list = []
        for nd in (liga.get("ndeshjet") or []):
            if isinstance(nd, dict) and (nd.get("is_premium") or ((nd.get("ndeshja") or "") in premium_live)):
                nd = {k: v for k, v in nd.items()
                      if k not in ("rezultati_sakt", "koef_rez_sakt", "analiza_custom",
                                   "besueshmeria", "best_bet", "tregjet", "dist_gola")}
                nd["is_premium"] = True   # frontend-i e stilon si premium/te kycur edhe me cache te vjeter
            nd_list.append(nd)
        lc = dict(liga); lc["ndeshjet"] = nd_list
        out.append(lc)
    return out


_PF_NAMES_CACHE = {"ts": 0.0, "emrat": set()}

def _emrat_premium_live(max_age_sec=300):
    """Emrat e ndeshjeve premium (sot+neser) direkt nga tabela PF, me cache 5-min.
    Mburoje qe maskimi te mos varet nga flamuret e nje payload-i te vjeter."""
    tani = time.time()
    if tani - _PF_NAMES_CACHE["ts"] < max_age_sec:
        return _PF_NAMES_CACHE["emrat"]
    emrat = set()
    try:
        dt_s, dt_n = _data_lokale(0), _data_lokale(1)
        r = requests.get(f"{PF_URL}?select=ndeshja&data=in.({dt_s},{dt_n})&limit=40",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=6)
        for x in (r.json() if r.status_code == 200 else []):
            if x.get("ndeshja"):
                emrat.add(x["ndeshja"])
    except Exception:
        return _PF_NAMES_CACHE["emrat"]   # ne gabim, mbaj listen e fundit
    _PF_NAMES_CACHE["ts"] = tani
    _PF_NAMES_CACHE["emrat"] = emrat
    return emrat


_FULL_ACCESS_CACHE = {}

def _ka_akses_te_plote(email):
    """AKSES I PLOTE (analizat + premium pa maskim): VIP aktiv OSE day-pass i sotem
    (vipcombo_fundit/generate_fundit == sot). Cache 60s per email."""
    if not email or not str(email).strip():
        return False
    em = str(email).lower().strip()
    tani = time.time()
    ck = _FULL_ACCESS_CACHE.get(em)
    if ck and tani - ck[0] < 60:
        return ck[1]
    ok = False
    try:
        r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{em}&select=isVip,vip_skadon_me,vipcombo_fundit,generate_fundit",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=5)
        rows = r.json() if r.status_code == 200 else []
        u = rows[0] if rows else None
        if u:
            if u.get("isVip"):
                sk = str(u.get("vip_skadon_me") or "")[:10]
                ok = (not sk) or (sk >= _data_lokale(0))
            if not ok:
                sot = _data_lokale(0)
                ok = (str(u.get("vipcombo_fundit") or "")[:10] == sot) or (str(u.get("generate_fundit") or "")[:10] == sot)
    except Exception:
        ok = False
    _FULL_ACCESS_CACHE[em] = (tani, ok)
    return ok


@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None, authorization: str = Header(None)):
    data_target = date if date else _data_lokale()
    koha_tani   = time.time()
    _em_fa = _email_auth(authorization, "", strict=False)
    _full  = _ka_akses_te_plote(_em_fa)
    def _maske(x):
        if _full:
            return _wm_apply(x, _em_fa) if (WATERMARK_ON and _em_fa) else x
        return _fshih_premium(x)

    # Auto-refresh PPM të përfunduara (në sfond)
    background_tasks.add_task(task_perditeso_ppm_te_perfunduara)
    background_tasks.add_task(_vleso_vip_combot)

    # 1) Cache në memorie (më i shpejti)
    if data_target in SKEDINA_CACHE and (koha_tani - SKEDINA_LAST_UPDATE.get(data_target, 0) < 600):
        return {"mesazhi": "Sukses", "skedina_grupuar": _maske(_me_live_fresh(SKEDINA_CACHE[data_target], data_target)), "full_access": _full}

    # 2) Cache në DB (mbijeton restart-et) — kthe MENJËHERË, pa llogaritur
    payload, fresh = _lexo_cache_db(data_target, max_age_min=60)
    if payload is not None:
        SKEDINA_CACHE[data_target]       = payload
        SKEDINA_LAST_UPDATE[data_target] = koha_tani
        if not fresh:
            background_tasks.add_task(_kompjuto_dhe_ruaj_skedina, data_target)  # rifresko në sfond
        return {"mesazhi": "Sukses", "skedina_grupuar": _maske(_me_live_fresh(payload, data_target)), "full_access": _full}

    # 3) Asgjë në cache (hera e parë) → gjenero tani; cron-i do e parahapë më pas
    rez = _kompjuto_dhe_ruaj_skedina(data_target)
    return {"mesazhi": "Sukses" if rez else "Gabim", "skedina_grupuar": _maske(rez), "full_access": _full}


def _parse_skor(s):
    """'1 - 3' / '1-3' → (1, 3); ndryshe (None, None)."""
    try:
        if not s:
            return (None, None)
        p = str(s).replace("\u2013", "-").split("-")
        if len(p) != 2:
            return (None, None)
        return (int(p[0].strip()), int(p[1].strip()))
    except Exception:
        return (None, None)


def _regjistro_rezultatet_training():
    """Regjistron çdo ndeshje të mbaruar (parashikim vs real) në training_results.
    Përdoret për monitorim saktësie dhe si burim për ritrajnimin e ardhshëm."""
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,data,liga_emri,tregjet,rezultati_sakt,rezultati"
            f"&statusi=in.(FT,AET,PEN,AWD,WO)&tregjet=not.is.null&rezultati=not.is.null"
            f"&order=id.desc&limit=500",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        preds = r.json() if r.status_code == 200 else []
        if not preds:
            return
        ids = [str(p["id"]) for p in preds]
        rex = requests.get(
            f"{SUPABASE_URL_TRAINING}?fixture_id=in.({','.join(ids)})&select=fixture_id",
            headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        ekzistues = {x["fixture_id"] for x in (rex.json() if rex.status_code == 200 else [])}

        rreshta = []
        for p in preds:
            fid = str(p["id"])
            if fid in ekzistues:
                continue
            rh, ra = _parse_skor(p.get("rezultati"))
            if rh is None:
                continue
            ph, pa = _parse_skor(p.get("rezultati_sakt"))
            tg = p.get("tregjet") or {}

            def fl(k):
                try:
                    return float(tg.get(k, 0) or 0)
                except Exception:
                    return 0.0

            p1, px, p2 = fl("1"), fl("X"), fl("2")
            pred_1x2 = "1" if (p1 >= px and p1 >= p2) else ("X" if px >= p2 else "2")
            pred_ou25 = "Over" if fl("Over 2.5") >= fl("Under 2.5") else "Under"
            real_1x2 = "1" if rh > ra else ("X" if rh == ra else "2")
            real_ou25 = "Over" if (rh + ra) >= 3 else "Under"

            rreshta.append({
                "fixture_id": fid, "ndeshja": p.get("ndeshja"),
                "liga": p.get("liga_emri"), "data": p.get("data"),
                "pred_gola_home": ph, "pred_gola_away": pa,
                "pred_rezultat": p.get("rezultati_sakt"),
                "pred_1x2": pred_1x2, "pred_ou25": pred_ou25,
                "real_gola_home": rh, "real_gola_away": ra,
                "real_rezultat": p.get("rezultati"),
                "real_1x2": real_1x2, "real_ou25": real_ou25,
                "hit_rezultat": (ph is not None and ph == rh and pa == ra),
                "hit_1x2": (pred_1x2 == real_1x2),
                "hit_ou25": (pred_ou25 == real_ou25),
            })

        if rreshta:
            requests.post(
                f"{SUPABASE_URL_TRAINING}?on_conflict=fixture_id",
                headers={**SUPABASE_SERVICE_HEADERS,
                         "Prefer": "resolution=ignore-duplicates,return=minimal"},
                json=rreshta, timeout=20)
    except Exception:
        pass


_LAST_HEAVY_GEN = 0.0
HEAVY_GEN_INTERVAL = 30 * 60   # pjesa e rëndë (Monte Carlo + odds për 3 ditë) maksimum çdo 30 min


@app.post("/api/admin/watermark-check")
async def admin_watermark_check(request: Request, secret: str = ""):
    """Identifikon kush rrjedhi te dhena: ngjit tekstin e rrjedhur (me zero-width),
    dhe kthen perdoruesin qe perputhet. Kerkon B2B_ADMIN_SECRET.
    Body JSON: {"teksti": "<tekst i kopjuar>"}  (POST qe te ruaje zero-width chars)."""
    if not B2B_ADMIN_SECRET or (secret or "").strip() != B2B_ADMIN_SECRET:
        return {"ok": False, "arsye": "Unauthorized"}
    try:
        body = await request.json()
    except Exception:
        body = {}
    teksti = (body or {}).get("teksti", "")
    kodi = _wm_extract(teksti)
    if not kodi:
        return {"ok": True, "gjetur": False, "mesazhi": "S'u gjet watermark ne tekst (mund te jete fshire ose rishkruar me dore)."}
    # Krahaso kundrejt te gjithe perdoruesve
    try:
        r = requests.get(f"{SUPABASE_URL_USERS}?select=email", headers=SUPABASE_SERVICE_HEADERS, timeout=15)
        users = r.json() if r.status_code == 200 else []
    except Exception as e:
        return {"ok": False, "arsye": f"lexim perdoruesish deshtoi: {e}", "kodi": kodi}
    perputhje = []
    for u in users:
        em = u.get("email")
        c = _wm_code(em)
        if c and c.hex() == kodi:
            perputhje.append(em)
    return {"ok": True, "gjetur": bool(perputhje), "kodi": kodi,
            "perdoruesi": perputhje[0] if perputhje else None,
            "te_gjitha_perputhjet": perputhje,
            "mesazhi": ("Watermark-u perket ketij perdoruesi." if perputhje
                        else "Watermark u gjet po s'perputhet me asnje perdorues aktual.")}


@app.get("/api/cron/gjenero")
def cron_gjenero(background_tasks: BackgroundTasks, date: str = None):
    """Cron i PLOTË (thirret nga cron-job.org çdo ~10 min). Kthen përgjigje TË VOGËL.
    NDARJE:
      • E LEHTË (çdo tik): FT+arkivim, sweep, PF gjenero/zbulo, VIP Combo, snapshot,
        vlerësim skedinash, training.
      • E RËNDË (me throttle, maksimum çdo HEAVY_GEN_INTERVAL): rigjenerimi Monte Carlo
        + paginim odds për 3 ditë — që të mos mbivendoset në Render free tier.
    Me ?date=YYYY-MM-DD detyrohet edhe pjesa e rëndë menjëherë (pa throttle).
    Përdore KËTË te cron, jo /api/skedina (që kthen skedinën e plotë dhe është 'too large')."""
    global _LAST_HEAVY_GEN
    if date:
        datat = [date]
    else:
        datat = [_data_lokale(i) for i in range(3)]

    # ── GJITHMONË (e lehtë, çdo ~10 min) ──
    # 1) Përditëso FT + ARKIVO ndeshjet e mbaruara → PPM History + Performanca
    background_tasks.add_task(task_perditeso_ppm_te_perfunduara)
    # 1b) SWEEP arkivimi: kap çdo të mbaruar që s'u arkivua (statusi u vu FT nga gjenerimi)
    background_tasks.add_task(_arkivo_sweep)
    # 1c) PF (premium hash): gjenero commitment-et + zbulo pikët e mbaruara —
    #     s'varet më nga trafiku i faqes (më parë thirreshin vetëm te /api/pf/list)
    background_tasks.add_task(_gjenero_pf)
    background_tasks.add_task(_zbulo_pf)
    # 2) Vlerëso VIP Combo (fituese/humbur) → Won History
    background_tasks.add_task(_vleso_vip_combot)
    # 4) Snapshot Skedina e Ditës + vlerëso skedinat + regjistro training
    background_tasks.add_task(_snapshot_skedina_ditore)
    background_tasks.add_task(_vlereso_skedina_historik)
    background_tasks.add_task(_regjistro_rezultatet_training)
    # 5) Rakordim pagesash Cryptomus: krediton porositë 'wait' të paguara (webhook i humbur)
    background_tasks.add_task(task_rakordo_porosite)

    # ── E RËNDË (me throttle): rigjenerim Monte Carlo + odds për 3 ditë ──
    tani = time.time()
    heavy = bool(date) or (tani - _LAST_HEAVY_GEN >= HEAVY_GEN_INTERVAL)
    if heavy:
        _LAST_HEAVY_GEN = tani
        for dt in datat:
            background_tasks.add_task(_kompjuto_dhe_ruaj_skedina, dt)

    return {"ok": True, "mesazhi": "Cron nisi në sfond", "datat": datat, "heavy": heavy}


def _kompjuto_dhe_ruaj_skedina(data_target):
    """LLOGARITJA E RËNDË: fixtures + odds + Monte Carlo + ruajtje. Kthen skedina_grupuar (listë)."""
    koha_tani = time.time()
    try:
        te_dhenat = _api_sports_get("fixtures", {"date": data_target, "timezone": "Europe/Tirane"})
        # API-Football dështoi / ktheu error → MOS prish cache-n e mirë; kthe të vjetrën
        if te_dhenat is None or ("errors" in te_dhenat and te_dhenat["errors"]):
            vjeter = SKEDINA_CACHE.get(data_target)
            if vjeter:
                return vjeter
            vjeter_db, _ = _lexo_cache_db(data_target, max_age_min=10_000_000)
            return vjeter_db if vjeter_db else []

        # ── KOEFICIENTËT: paginim i plotë + multi-bookmaker fallback ──
        # Bookmakers prioritet: 8=Bet365, 4=Pinnacle, 6=1xBet, 2=Marathon, 11=William Hill
        BOOKMAKERS_PRIORITY = [8, 4, 6, 2, 11]
        bet365_odds = {}  # emër i ruajtur për kompatibilitet (real: të gjithë bookmakers)

        for bookmaker_id in BOOKMAKERS_PRIORITY:
            try:
                page_num = 1
                while page_num <= 10:  # max 10 faqe = 100 ndeshje (mjafton për 1 ditë)
                    res_odds = requests.get(
                        "https://v3.football.api-sports.io/odds",
                        headers=HEADERS,
                        params={
                            "date":      data_target,
                            "bookmaker": bookmaker_id,
                            "page":      page_num
                        },
                        timeout=10
                    ).json()

                    if "response" not in res_odds or not res_odds["response"]:
                        break

                    for item in res_odds["response"]:
                        fix_id = str(item["fixture"]["id"])
                        # Mos rishkruaj nëse e kemi nga bookmaker me prioritet më të lartë
                        if fix_id in bet365_odds and bet365_odds[fix_id]["1"]:
                            continue
                        try:
                            bets = item["bookmakers"][0]["bets"]
                            parsed = _nxirr_odds_reale(bets)
                            if parsed.get("1") and parsed.get("X") and parsed.get("2"):
                                bet365_odds[fix_id] = parsed
                        except:
                            pass

                    # Kontrollo paging — nëse pagination existon në response
                    paging = res_odds.get("paging", {})
                    total_pages = paging.get("total", 1)
                    if page_num >= total_pages:
                        break
                    page_num += 1
            except:
                continue

        # Grupo ndeshjet sipas ligës
        ligat_raw = {}
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                if emri_liges not in ligat_raw:
                    ligat_raw[emri_liges] = []
                ligat_raw[emri_liges].append(n)

        STANDINGS_CACHE  = {}
        lista_e_te_gjithave = []
        vip_kandidatet   = []

        for emri_liges, ndeshjet_liges in ligat_raw.items():
            eshte_liga_vip = is_vip_league(emri_liges)
            standings      = []

            if eshte_liga_vip and len(ndeshjet_liges) > 0:
                league_id_str = str(ndeshjet_liges[0]["league"]["id"])
                season_str    = str(ndeshjet_liges[0]["league"]["season"])
                cache_key     = f"{league_id_str}_{season_str}"

                if cache_key in STANDINGS_CACHE:
                    standings = STANDINGS_CACHE[cache_key]
                else:
                    try:
                        s_res = requests.get(
                            "https://v3.football.api-sports.io/standings",
                            headers=HEADERS,
                            params={"league": league_id_str, "season": season_str},
                            timeout=2
                        )
                        if s_res.status_code == 200 and s_res.json().get("response"):
                            standings = s_res.json()["response"][0]["league"]["standings"][0]
                            STANDINGS_CACHE[cache_key] = standings
                    except:
                        standings = []

            for n in ndeshjet_liges:
                id_ndeshja  = str(n["fixture"]["id"])
                ekipi_1     = n["teams"]["home"]["name"].replace("'", "")
                ekipi_2     = n["teams"]["away"]["name"].replace("'", "")
                statusi_kod = n["fixture"]["status"]["short"]
                rezultati   = (
                    f"{n['goals']['home']} - {n['goals']['away']}"
                    if n["goals"]["home"] is not None else "0 - 0"
                )

                k1 = kx = k2 = None
                if id_ndeshja in bet365_odds and bet365_odds[id_ndeshja]["1"]:
                    k1 = str(bet365_odds[id_ndeshja]["1"])
                    kx = str(bet365_odds[id_ndeshja]["X"])
                    k2 = str(bet365_odds[id_ndeshja]["2"])
                elif eshte_liga_vip and statusi_kod in ("NS", "TBD"):
                    # FALLBACK: liga VIP pa odds nga marrja sipas dates -> merr direkt per fixture
                    _fb = _merr_odds_per_fixture(id_ndeshja)
                    if _fb:
                        bet365_odds[id_ndeshja] = _fb
                        k1 = str(_fb["1"]); kx = str(_fb["X"]); k2 = str(_fb["2"])

                try:
                    ora_sakte = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%H:%M")
                except:
                    ora_sakte = "N/A"

                base_match = {
                    "id":             id_ndeshja,
                    "liga_id":        n["league"]["id"],
                    "sezoni":         n["league"]["season"],
                    "ekipi_1_id":     n["teams"]["home"]["id"],
                    "ekipi_2_id":     n["teams"]["away"]["id"],
                    "ekipi_1":        ekipi_1,
                    "ekipi_2":        ekipi_2,
                    "ndeshja":        f"{ekipi_1} vs {ekipi_2}",
                    "data":           data_target,
                    "ora":            "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte,
                    "ora_sakte":      ora_sakte,
                    "koha_utc":       n["fixture"]["date"],
                    "statusi":        statusi_kod,
                    "minuta":         n["fixture"]["status"]["elapsed"] or 0,
                    "rezultati":      rezultati,
                    "koef_1":         k1 or "N/A",
                    "koef_x":         kx or "N/A",
                    "koef_2":         k2 or "N/A",
                    "odds_reale":     bet365_odds.get(id_ndeshja, {}),
                    "analiza_custom": None,
                    "besueshmeria":   0.0,
                    "rezultati_sakt": "",
                    "koef_rez_sakt":  "N/A",
                    "is_premium":     False,
                    "is_motd":        False,
                    "is_bllof":       False,
                    "koef_plote":     f"1:{k1} | X:{kx} | 2:{k2}" if k1 else "N/A",
                    "liga_emri":      emri_liges,
                }

                if eshte_liga_vip and k1 and kx and k2:
                    try:
                        # Merr DNA për të dyja skuadrat
                        dna_1 = merr_dna_nga_db(n["teams"]["home"]["id"])
                        dna_2 = merr_dna_nga_db(n["teams"]["away"]["id"])

                        # ── THIRRJA E MOTORIT V2 ──
                        analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt, extradb = analizo_ndeshjen_premium_master(
                            id_ndeshja, ekipi_1, ekipi_2,
                            n["teams"]["home"]["id"], n["teams"]["away"]["id"],
                            k1, kx, k2, emri_liges, standings,
                            dna_1=dna_1, dna_2=dna_2,
                            odds_full=bet365_odds.get(id_ndeshja, {})
                        )
                        base_match.update({
                            "analiza_custom": analiza_custom,
                            "besueshmeria":   besueshmeria,
                            "rezultati_sakt": rez_sakt,
                            "koef_rez_sakt":  koef_rez_sakt,
                            "is_bllof":       extradb["is_bllof"],
                            "koef_plote":     extradb["koef_plote"],
                            "tregjet":        extradb["tregjet"],
                            "dist_gola":      extradb["dist_gola"],
                            "best_bet":       _best_bet_value(extradb["tregjet"], bet365_odds.get(id_ndeshja, {})) or extradb["best_bet"],
                            "training_data":  extradb.get("training_data"),
                        })
                        vip_kandidatet.append(base_match)
                    except Exception as eval_err:
                        lista_e_te_gjithave.append(base_match)
                else:
                    lista_e_te_gjithave.append(base_match)

        # Rendit VIP dhe zgjidh 3 PPM
        vip_kandidatet.sort(key=lambda x: x["besueshmeria"], reverse=True)
        premium_count = 0
        ndeshjet_premium_per_historik = []

        for ndeshja in vip_kandidatet:
            if premium_count < 3:
                ndeshja["is_premium"] = True
                ndeshja["is_motd"]    = (premium_count == 0)
                if ndeshja["besueshmeria"] > 0:
                    ndeshjet_premium_per_historik.append(ndeshja)
                premium_count += 1
            else:
                ndeshja["is_premium"] = False
                ndeshja["is_motd"]    = False
                # analiza_custom MBAHET për të gjitha ndeshjet e analizuara (jo vetëm top-3)
            lista_e_te_gjithave.append(ndeshja)

        # Ruaj TË GJITHA ndeshjet VIP të analizuara (për daily products + historik PPM)
        if vip_kandidatet:
            try:
                task_ruaj_skedinen_ne_db(vip_kandidatet)
            except Exception:
                pass

        # Grupo sipas ligës
        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup:
                ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        def merr_rendesine_e_liges(emri):
            for i, liga_top in enumerate(LIGAT_VIP):
                if liga_top.lower() in emri.lower():
                    return i
            return 999

        rezultati_perfundimtar = sorted(
            [{"liga": k, "ndeshjet": v} for k, v in ligat_grup.items()],
            key=lambda x: merr_rendesine_e_liges(x["liga"])
        )

        # MOS mbishkruaj cache-n e mirë me listë BOSH (p.sh. API ktheu pak/asgjë)
        if rezultati_perfundimtar:
            SKEDINA_CACHE[data_target]       = rezultati_perfundimtar
            SKEDINA_LAST_UPDATE[data_target] = koha_tani
            _ruaj_cache_db(data_target, rezultati_perfundimtar)
            return rezultati_perfundimtar
        vjeter = SKEDINA_CACHE.get(data_target)
        if vjeter:
            return vjeter
        vjeter_db, _ = _lexo_cache_db(data_target, max_age_min=10_000_000)
        return vjeter_db if vjeter_db else rezultati_perfundimtar

    except Exception as e:
        print(f"[GJENERIM] Gabim per {data_target}: {e}")
        vjeter = SKEDINA_CACHE.get(data_target)
        if vjeter:
            return vjeter
        vjeter_db, _ = _lexo_cache_db(data_target, max_age_min=10_000_000)
        return vjeter_db if vjeter_db else []

@app.get("/")
def root():
    return {
        "status":      "online",
        "engine":      "VIP_PPM_Engine_V2",
        "monte_carlo": "50k_numpy",
        "uptime":      datetime.utcnow().isoformat()
    }

# ==========================================
# KEEP-ALIVE ENDPOINT (për UptimeRobot)
# ==========================================
# Konfiguro UptimeRobot.com të ping-on këtë URL çdo 5 minuta:
# https://soccer1x2-api.onrender.com/api/ping
# Kështu Render Free nuk fle kurrë → 0 sekonda cold start.

@app.get("/api/ping")
def keep_alive_ping():
    """Endpoint i lehtë për UptimeRobot — vetëm timestamp, asnjë DB call."""
    return {
        "pong":      True,
        "timestamp": datetime.utcnow().isoformat(),
        "service":   "soccer1x2-api"
    }


# ==========================================
# AUTO-UPDATE I REZULTATIVE TË PËRFUNDUARA
# ==========================================
# Ky endpoint duhet të thirret çdo 30 min nga UptimeRobot ose cron.
# Lexon nga predictions ndeshjet që ende NUK kanë mbaruar,
# kontrollon te API-Sports dhe i përditëson me rezultatin final.

@app.get("/api/arkiv")
def lexo_arkivin(limit: int = 200, liga: str = "", vetem_goditje: int = 0):
    """Lexon arkivin e rezultateve (historik + eksport për kalibrim/trajnim)."""
    q = f"{ARKIV_URL}?select=*&order=data.desc,ora.desc&limit={max(1, min(limit, 2000))}"
    if liga.strip():
        q += f"&liga=eq.{requests.utils.quote(liga.strip(), safe='')}"
    if vetem_goditje:
        q += "&goditi_1x2=is.true"
    try:
        r = requests.get(q, headers=SUPABASE_SERVICE_HEADERS, timeout=12)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


@app.get("/api/performanca")
def performanca_modelit(limit: int = 1000):
    """Metrikat e sakteseise nga arkivi (per seksionin publik Performanca e Modelit)."""
    try:
        r = requests.get(
            f"{ARKIV_URL}?select=ndeshja,liga,data,parashikimi,rezultati_ft,goditi_1x2,goditi_skor"
            f"&order=data.desc,ora.desc&limit={max(1, min(limit, 2000))}",
            headers=SUPABASE_SERVICE_HEADERS, timeout=12)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    n1 = n1ok = ns = nsok = ng1 = ng1ok = ngg = nggok = nou = nouok = 0
    for row in rows:
        par = _parse_score(row.get("parashikimi") or "")
        ft = _parse_score(row.get("rezultati_ft") or "")
        if row.get("goditi_1x2") is not None:
            n1 += 1
            if row.get("goditi_1x2"):
                n1ok += 1
        if row.get("goditi_skor") is not None:
            ns += 1
            if row.get("goditi_skor"):
                nsok += 1
        if par and ft:
            ng1 += 1
            if abs(par[0] - ft[0]) <= 1 and abs(par[1] - ft[1]) <= 1:
                ng1ok += 1
            ngg += 1
            if (par[0] > 0 and par[1] > 0) == (ft[0] > 0 and ft[1] > 0):
                nggok += 1
            nou += 1
            if ((par[0] + par[1]) > 2.5) == ((ft[0] + ft[1]) > 2.5):
                nouok += 1
    def pct(o, n):
        return round(100 * o / n) if n else 0
    recent = []
    for row in rows:
        if row.get("parashikimi") and row.get("rezultati_ft"):
            recent.append({
                "ndeshja": row.get("ndeshja"),
                "liga": row.get("liga"),
                "parashikimi": row.get("parashikimi"),
                "rezultati": row.get("rezultati_ft"),
                "goditi_1x2": row.get("goditi_1x2"),
            })
        if len(recent) >= 6:
            break
    return {
        "metrikat": {
            "x1x2": pct(n1ok, n1),
            "brenda1gol": pct(ng1ok, ng1),
            "ggng": pct(nggok, ngg),
            "ou": pct(nouok, nou),
            "skor": pct(nsok, ns),
        },
        "mostra": n1,
        "recent": recent,
        "perditesuar": rows[0].get("data") if rows else None,
    }


@app.get("/api/admin/rikorrigjo_aet")
def admin_rikorrigjo_aet():
    """Korrigjon ndeshjet e vjetra AET/PEN: 1X2/PPM duhet të llogaritet mbi FT (90'),
    jo pas shtesave. Ri-merr FT nga API vetëm për AET/PEN, përditëson predictions.rezultati
    dhe rreshtin e arkivit (goditi_1x2, goditi_skor, rezultati_ft). I hapur si rindertimi
    (deterministik + idempotent). Thirre: /api/admin/rikorrigjo_aet"""
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,rezultati_sakt,rezultati,statusi"
            f"&statusi=in.(AET,PEN)",
            headers=SUPABASE_SERVICE_HEADERS, timeout=15)
        preds = r.json() if r.status_code == 200 else []
    except Exception:
        preds = []
    korrigjuar = []
    for p in preds:
        mid = str(p.get("id") or "")
        if not mid:
            continue
        try:
            rf = requests.get(f"https://v3.football.api-sports.io/fixtures?id={mid}",
                              headers=HEADERS, timeout=12)
            resp = (rf.json() or {}).get("response") or []
        except Exception:
            resp = []
        if not resp:
            continue
        ft = _rezultati_ft(resp[0])
        if not ft:
            continue
        i_vjeter = p.get("rezultati")
        if ft == i_vjeter:
            continue  # tashmë korrekt
        par = p.get("rezultati_sakt") or ""
        try:
            requests.patch(f"{SUPABASE_URL_PREDS}?id=eq.{mid}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"rezultati": ft}, timeout=8)
        except Exception:
            pass
        g1x2 = (_shenja_1x2(par) == _shenja_1x2(ft)) if (par and _shenja_1x2(par) and _shenja_1x2(ft)) else None
        gskor = (_parse_score(par) == _parse_score(ft)) if (par and _parse_score(par) and _parse_score(ft)) else None
        try:
            requests.patch(f"{ARKIV_URL}?match_id=eq.{mid}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"rezultati_ft": ft, "goditi_1x2": g1x2, "goditi_skor": gskor}, timeout=8)
        except Exception:
            pass
        korrigjuar.append({"match_id": mid, "ndeshja": p.get("ndeshja"),
                           "para": i_vjeter, "ft": ft, "goditi_1x2": g1x2})
    return {"sukses": True, "kontrolluar": len(preds),
            "korrigjuar": len(korrigjuar), "detaje": korrigjuar}


@app.get("/api/arkiv/rindertimi")
def rindertimi_arkivit():
    """Backfill një-herësh: arkivon ndeshjet e mbaruara që janë te predictions (HT nga API)."""
    try:
        r = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ekipi_1,ekipi_2,liga_emri,data,ora,ora_sakte,"
            f"koef_1,koef_x,koef_2,odds_reale,rezultati_sakt,tregjet,best_bet,besueshmeria,training_data,dist_gola,rezultati"
            f"&statusi=in.(FT,AET,PEN,AWD,WO)&rezultati=not.is.null&order=data.desc&limit=2000",
            headers=SUPABASE_SERVICE_HEADERS, timeout=15)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    ht_map = {}
    ids = [str(p.get("id")) for p in rows if p.get("id")]
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        try:
            api_res = requests.get("https://v3.football.api-sports.io/fixtures",
                                   headers=HEADERS, params={"ids": "-".join(batch)}, timeout=12)
            for fx in api_res.json().get("response", []):
                fid = str(fx["fixture"]["id"])
                ht = (fx.get("score") or {}).get("halftime") or {}
                if ht.get("home") is not None:
                    ht_map[fid] = f"{ht.get('home')} - {ht.get('away')}"
        except Exception:
            pass
    n = 0
    for p in rows:
        _arkivo_ndeshje(p, ht_map.get(str(p.get("id"))))
        n += 1
    return {"sukses": True, "arkivuara": n, "me_ht": len(ht_map)}


@app.get("/api/refresh_results")
def perditeso_rezultatet_perfunduara():
    """
    Lexon ndeshjet PPM të paplotësuara dhe i përditëson nga API-Sports.
    Konfigurim UptimeRobot:
      URL: https://soccer1x2-api.onrender.com/api/refresh_results
      Interval: 30 minuta (ose 60 min nëse ke API limit)
    """
    try:
        # Merr të gjitha ndeshjet që nuk kanë mbaruar (me fushat për arkivim)
        res = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,statusi,ekipi_1,ekipi_2,liga_emri,data,ora,ora_sakte,"
            f"koef_1,koef_x,koef_2,odds_reale,rezultati_sakt,tregjet,best_bet,besueshmeria,training_data,dist_gola"
            f"&statusi=not.in.(FT,AET,PEN,AWD,WO)",
            headers=SUPABASE_SERVICE_HEADERS,
            timeout=10
        )
        if res.status_code != 200:
            return {"sukses": False, "mesazhi": f"DB error: {res.status_code}"}

        ndeshjet_pa_mbaruar = res.json()
        if not ndeshjet_pa_mbaruar:
            return {"sukses": True, "perditesuara": 0, "mesazhi": "Të gjitha ndeshjet janë të përditësuara."}

        preds_by_id = {str(p.get("id")): p for p in ndeshjet_pa_mbaruar}
        u_perditesuan = 0
        ende_aktive   = 0
        deshtuan      = 0

        # Merr ID-të dhe i kontrollon në batch
        match_ids = [str(n["id"]) for n in ndeshjet_pa_mbaruar]

        # API-Sports lejon max 20 IDs në një kërkesë
        for i in range(0, len(match_ids), 20):
            batch = match_ids[i:i+20]
            ids_str = "-".join(batch)

            try:
                api_res = requests.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers=HEADERS,
                    params={"ids": ids_str},
                    timeout=10
                )
                fixtures = api_res.json().get("response", [])
            except:
                deshtuan += len(batch)
                continue

            for fx in fixtures:
                fix_id    = str(fx["fixture"]["id"])
                status    = fx["fixture"]["status"]["short"]
                gola_h    = fx["goals"]["home"]
                gola_a    = fx["goals"]["away"]

                if status in ["FT", "AET", "PEN", "AWD", "WO"] and gola_h is not None:
                    # Përditëso në DB
                    rezultati_str = _rezultati_ft(fx) or f"{gola_h} - {gola_a}"
                    update_payload = {
                        "statusi":   status,
                        "rezultati": rezultati_str,
                        "ora":       "FT",
                        "minuta":    90,
                    }
                    try:
                        requests.patch(
                            f"{SUPABASE_URL_PREDS}?id=eq.{fix_id}",
                            headers=SUPABASE_SERVICE_HEADERS,
                            json=update_payload,
                            timeout=5
                        )
                        u_perditesuan += 1
                    except:
                        deshtuan += 1
                    # ── ARKIVO (përfshirë HT nga API) ──
                    try:
                        _ht = (fx.get("score") or {}).get("halftime") or {}
                        _hth, _hta = _ht.get("home"), _ht.get("away")
                        _ht_str = f"{_hth} - {_hta}" if _hth is not None else None
                        _pred = preds_by_id.get(fix_id)
                        if _pred is not None:
                            _pred["rezultati"] = rezultati_str
                            _arkivo_ndeshje(_pred, _ht_str)
                    except Exception:
                        pass
                else:
                    ende_aktive += 1

        return {
            "sukses":         True,
            "perditesuara":   u_perditesuan,
            "ende_aktive":    ende_aktive,
            "deshtuan":       deshtuan,
            "total_kontrolla": len(ndeshjet_pa_mbaruar),
        }
    except Exception as e:
        return {"sukses": False, "mesazhi": str(e)}

# ==========================================
# ENDPOINTI LIVE
# ==========================================

@app.get("/api/live")
def merr_ndeshjet_live(background_tasks: BackgroundTasks):
    # Auto-refresh PPM të mbaruara në sfond
    background_tasks.add_task(task_perditeso_ppm_te_perfunduara)
    try:
        te_dhenat = _api_sports_get("fixtures", {"live": "all"}, retries=2)
        if te_dhenat is None:
            return {"mesazhi": "Gabim", "ndeshjet": []}

        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "ndeshjet": []}

        ndeshjet_live = []
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                gola_1     = n["goals"]["home"] if n["goals"]["home"] is not None else 0
                gola_2     = n["goals"]["away"] if n["goals"]["away"] is not None else 0
                ndeshjet_live.append({
                    "id":         str(n["fixture"]["id"]),
                    "liga_emri":  emri_liges,
                    "ekipi_1":    n["teams"]["home"]["name"].replace("'", ""),
                    "ekipi_2":    n["teams"]["away"]["name"].replace("'", ""),
                    "statusi":    n["fixture"]["status"]["short"],
                    "minuta":     f"{n['fixture']['status']['elapsed'] or 0}'",
                    "rezultati":  _rezultati_ft(n) or f"{gola_1} - {gola_2}",
                })

        return {"mesazhi": "Sukses", "ndeshjet": ndeshjet_live}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "ndeshjet": []}


# ==========================================
# DNA ENGINE V2 — Mbushje dhe përditësim i team_dna_cache
# ==========================================

def llogarit_dna_nga_historia(team_id: int, sezoni: int, last_n: int = 30) -> dict:
    """
    Merr last_n ndeshjet e fundit të ekipit dhe llogarit DNA komplete:
    historical_power (ELO), win_rate, avg_gola, clutch_factor,
    volatility_index, draw_affinity, consistency_score.
    """
    try:
        res = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS,
            params={"team": team_id, "last": last_n, "status": "FT"},
            timeout=10
        )
        ndeshjet = res.json().get("response", [])
    except:
        return None

    if not ndeshjet or len(ndeshjet) < 5:
        return None

    fitore = barazime = humbje = 0
    gola_shenuar = gola_prane = 0
    gola_per_ndeshje = []
    clutch_wins = clutch_total = 0
    team_name = ""

    for n in ndeshjet:
        eshte_shtepie = n["teams"]["home"]["id"] == team_id
        team_name = (n["teams"]["home"]["name"] if eshte_shtepie
                     else n["teams"]["away"]["name"])
        g_ekip = n["goals"]["home"] if eshte_shtepie else n["goals"]["away"]
        g_kund = n["goals"]["away"] if eshte_shtepie else n["goals"]["home"]
        if g_ekip is None or g_kund is None:
            continue

        gola_shenuar += g_ekip
        gola_prane   += g_kund
        gola_per_ndeshje.append(g_ekip + g_kund)
        diff = g_ekip - g_kund

        if g_ekip > g_kund:
            fitore += 1
            if abs(diff) <= 1:
                clutch_wins += 1
                clutch_total += 1
        elif g_ekip == g_kund:
            barazime += 1
        else:
            humbje += 1
            if abs(diff) <= 1:
                clutch_total += 1

    total = fitore + barazime + humbje
    if total == 0:
        return None

    win_rate           = round(fitore / total, 3)
    draw_rate          = round((barazime / total) * 100, 2)
    avg_goals_scored   = round(gola_shenuar / total, 2)
    avg_goals_conceded = round(gola_prane / total, 2)

    # ELO i llogaritur nga performanca reale
    base_elo         = 600.0
    bonus_win        = win_rate * 400
    bonus_gd         = (avg_goals_scored - avg_goals_conceded) * 80
    historical_power = round(base_elo + bonus_win + bonus_gd, 1)
    historical_power = float(np.clip(historical_power, 400, 1000))

    # Clutch factor: performanca në ndeshje të ngushta (≤1 gol diferencë)
    if clutch_total > 0:
        clutch_factor = round(0.85 + (clutch_wins / clutch_total) * 0.3, 3)
    else:
        clutch_factor = 1.0
    clutch_factor = float(np.clip(clutch_factor, 0.85, 1.20))

    # Volatility: devijimi standard i golave (sa ndryshon performanca)
    if len(gola_per_ndeshje) >= 3:
        volatility_index = round(float(np.std(gola_per_ndeshje)) * 10, 2)
    else:
        volatility_index = 15.0

    # Consistency: e kundërta e volatility
    consistency_score = round(100 - min(100, volatility_index * 3), 2)

    return {
        "team_id":           team_id,
        "team_name":         team_name,
        "elo_rating":        historical_power,
        "historical_power":  historical_power,
        "win_rate":          win_rate,
        "avg_goals_scored":  avg_goals_scored,
        "avg_goals_conceded": avg_goals_conceded,
        "clutch_factor":     clutch_factor,
        "volatility_index":  volatility_index,
        "draw_affinity":     draw_rate,
        "consistency_score": consistency_score,
        "last_updated":      datetime.utcnow().isoformat(),
    }


@app.get("/api/dna_status")
def merr_dna_status():
    """Tregon sa skuadra ke në team_dna_cache."""
    try:
        res = requests.get(
            f"{SUPABASE_URL_DNA}?select=team_id,team_name,historical_power,win_rate",
            headers=SUPABASE_SERVICE_HEADERS,
            timeout=5
        )
        if res.status_code == 200:
            te_dhenat = res.json()
            return {
                "sukses":        True,
                "total_skuadra": len(te_dhenat),
                "shfaq_20_para": [
                    {
                        "id":   x.get("team_id"),
                        "emri": x.get("team_name"),
                        "elo":  x.get("historical_power"),
                        "wr":   x.get("win_rate"),
                    }
                    for x in te_dhenat[:20]
                ],
            }
        return {"sukses": False, "mesazhi": f"Status code: {res.status_code}"}
    except Exception as e:
        return {"sukses": False, "mesazhi": str(e)}


@app.get("/api/update_dna/{team_id}")
def update_dna_per_skuader(team_id: int, season: int = 2025):
    """
    Llogarit DNA për një skuadër dhe e ruan/përditëson në DB.
    Përdorimi: /api/update_dna/541?season=2025  (541 = Real Madrid)
    """
    dna_e_re = llogarit_dna_nga_historia(team_id, season)
    if not dna_e_re:
        return {"sukses": False, "mesazhi": f"Nuk u gjetën ndeshje për ekipin {team_id}"}

    try:
        res_check = requests.get(
            f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
            headers=SUPABASE_SERVICE_HEADERS, timeout=5
        )
        ekziston = res_check.status_code == 200 and len(res_check.json()) > 0

        if ekziston:
            res = requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
                headers=SUPABASE_SERVICE_HEADERS, json=dna_e_re, timeout=5
            )
            veprimi = "UPDATED"
        else:
            res = requests.post(
                SUPABASE_URL_DNA,
                headers=SUPABASE_SERVICE_HEADERS, json=dna_e_re, timeout=5
            )
            veprimi = "INSERTED"

        if res.status_code in [200, 201, 204]:
            return {"sukses": True, "veprimi": veprimi,
                    "team": dna_e_re["team_name"], "dna": dna_e_re}
        return {"sukses": False,
                "mesazhi": f"DB error: {res.status_code} - {res.text[:200]}"}
    except Exception as e:
        return {"sukses": False, "mesazhi": str(e)}


@app.get("/api/seed_dna")
def seed_dna_per_ligat_vip(season: int = 2025, max_teams: int = 30, start_index: int = 0):
    """
    RUN ONCE: Mbush team_dna_cache për skuadrat e ligave VIP.
    Render free plan = 30s timeout, prandaj max_teams=30 për thirrje.
    
    Përdorimi:
      /api/seed_dna?max_teams=30&start_index=0    (skuadrat 0-29)
      /api/seed_dna?max_teams=30&start_index=30   (skuadrat 30-59)
      /api/seed_dna?max_teams=30&start_index=60   (skuadrat 60-89)
    """
    skuadrat_e_perpunuara = []
    deshtuar              = []
    skuadra_index_global  = 0
    perpunuar_total       = 0

    for league_id, emri_liges in LIGAT_VIP_MAP.items():
        if perpunuar_total >= max_teams:
            break

        try:
            s_res = requests.get(
                "https://v3.football.api-sports.io/standings",
                headers=HEADERS,
                params={"league": league_id, "season": season},
                timeout=8
            )
            if s_res.status_code != 200:
                continue
            response = s_res.json().get("response", [])
            if not response:
                continue
            standings = response[0]["league"]["standings"][0]
        except:
            continue

        for r in standings:
            if perpunuar_total >= max_teams:
                break

            if skuadra_index_global < start_index:
                skuadra_index_global += 1
                continue

            team_id   = r["team"]["id"]
            team_name = r["team"]["name"]

            dna = llogarit_dna_nga_historia(team_id, season, last_n=15)
            if not dna:
                deshtuar.append({"team": team_name, "id": team_id, "arsye": "no fixtures"})
                skuadra_index_global += 1
                continue

            try:
                res_check = requests.get(
                    f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
                    headers=SUPABASE_SERVICE_HEADERS, timeout=3
                )
                ekziston = res_check.status_code == 200 and len(res_check.json()) > 0

                if ekziston:
                    requests.patch(
                        f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
                        headers=SUPABASE_SERVICE_HEADERS, json=dna, timeout=3
                    )
                else:
                    requests.post(
                        SUPABASE_URL_DNA,
                        headers=SUPABASE_SERVICE_HEADERS, json=dna, timeout=3
                    )

                skuadrat_e_perpunuara.append({
                    "team": team_name,
                    "id":   team_id,
                    "elo":  dna["historical_power"],
                    "wr":   dna["win_rate"],
                })
                perpunuar_total += 1
            except Exception as ex:
                deshtuar.append({"team": team_name, "arsye": str(ex)[:100]})

            skuadra_index_global += 1

    return {
        "sukses":             True,
        "start_index":        start_index,
        "skuadra_te_shtuara": perpunuar_total,
        "deshtuara":          len(deshtuar),
        "lista":              skuadrat_e_perpunuara,
        "mesazhi":            f"DNA u krijua/përditësua për {perpunuar_total} skuadra. "
                              f"Për të vazhduar: ?start_index={start_index + max_teams}",
    }


# ==========================================
# MIDNIGHT TASK — PËRDITËSIMI I ELO-S DINAMIKE (me auto-bootstrap)
# ==========================================

@app.get("/api/cron/update_elo_midnight")
def update_elo_midnight():
    dje = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        res = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS, params={"date": dje, "timezone": "Europe/Tirane"}, timeout=15
        )
        ndeshjet_dje = res.json().get("response", [])
    except:
        return {"sukses": False, "mesazhi": "Gabim lidhjeje me API-Sports"}

    ekipe_te_perditesuara = 0
    for m in ndeshjet_dje:
        if m["fixture"]["status"]["short"] not in ["FT", "AET", "PEN"]:
            continue

        emri_liges = f"{m['league']['country']} - {m['league']['name']}"
        if not is_vip_league(emri_liges):
            continue

        home_id    = str(m["teams"]["home"]["id"])
        away_id    = str(m["teams"]["away"]["id"])
        home_goals = m["goals"]["home"]
        away_goals = m["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue

        dna_home = merr_dna_nga_db(home_id)
        dna_away = merr_dna_nga_db(away_id)

        # ── KRIJO DNA NËSE MUNGON (auto-bootstrap) ──
        sezoni = m["league"]["season"]
        if not dna_home:
            dna_e_re = llogarit_dna_nga_historia(int(home_id), sezoni)
            if dna_e_re:
                try:
                    requests.post(
                        SUPABASE_URL_DNA,
                        headers=SUPABASE_SERVICE_HEADERS,
                        json=dna_e_re, timeout=3
                    )
                    dna_home = dna_e_re
                    ekipe_te_perditesuara += 1
                except:
                    pass
        if not dna_away:
            dna_e_re = llogarit_dna_nga_historia(int(away_id), sezoni)
            if dna_e_re:
                try:
                    requests.post(
                        SUPABASE_URL_DNA,
                        headers=SUPABASE_SERVICE_HEADERS,
                        json=dna_e_re, timeout=3
                    )
                    dna_away = dna_e_re
                    ekipe_te_perditesuara += 1
                except:
                    pass

        if not dna_home and not dna_away:
            continue

        elo_home = dna_home.get("historical_power", 600) if dna_home else 600
        elo_away = dna_away.get("historical_power", 600) if dna_away else 600

        r_home = elo_home + 65
        r_away = elo_away
        e_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        e_away = 1 - e_home

        if home_goals > away_goals:
            s_home, s_away = 1.0, 0.0
        elif home_goals == away_goals:
            s_home, s_away = 0.5, 0.5
        else:
            s_home, s_away = 0.0, 1.0

        gd         = abs(home_goals - away_goals)
        multiplier = math.log(gd + 1) + 1 if gd > 0 else 1

        new_elo_home = elo_home + 32 * multiplier * (s_home - e_home)
        new_elo_away = elo_away + 32 * multiplier * (s_away - e_away)

        if dna_home:
            requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{home_id}",
                headers=SUPABASE_SERVICE_HEADERS,
                json={"historical_power": round(new_elo_home, 1)}
            )
            ekipe_te_perditesuara += 1
        if dna_away:
            requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{away_id}",
                headers=SUPABASE_SERVICE_HEADERS,
                json={"historical_power": round(new_elo_away, 1)}
            )
            ekipe_te_perditesuara += 1

        # Pastro cache-in e formës për ekipet që luajtën
        FORMA_CACHE.pop(int(home_id), None)
        FORMA_CACHE.pop(int(away_id), None)

    return {
        "sukses": True,
        "mesazhi": f"Përditësimi përfundoi! {ekipe_te_perditesuara} ekipe VIP u kalibruan nga {dje}."
    }

# ==========================================
# ENDPOINTE TË TJERA (PA NDRYSHIM)
# ==========================================

@app.get("/api/vip_weekend")
def merr_vip_weekend():
    """
    Gjeneron skedinën VIP të fundjavës:
    - Kombinim 3-5 ndeshjesh me besueshmëri më të lartë
    - Total odds duhet të jetë ≥ 10.0
    - Vetëm nga e Premtja deri e Diela (3 ditë)
    - Cache 1 orë (që të mos rilexohet API për çdo user)
    """
    koha_tani = time.time()

    # Kontrollo cache
    if hasattr(merr_vip_weekend, "_cache"):
        cached, cached_time = merr_vip_weekend._cache
        if koha_tani - cached_time < 3600:  # 1 orë
            return cached

    sot = datetime.utcnow()
    dita_jave = sot.weekday()  # 0=Hënë, 4=Premte, 5=Shtunë, 6=Diel

    # VIP gjenerohet vetëm të Premten, Shtunën, Dielën
    if dita_jave not in [4, 5, 6]:
        result = {
            "is_ready": False,
            "mesazhi":  "Skedina VIP gjenerohet vetëm gjatë fundjavës.",
            "skedina":  []
        }
        merr_vip_weekend._cache = (result, koha_tani)
        return result

    # Llogarit datat e fundjavës (e Premtja, Shtuna, Dielë)
    if dita_jave == 4:    # E Premte
        dita_premtje = sot
    elif dita_jave == 5:  # E Shtunë
        dita_premtje = sot - timedelta(days=1)
    else:                 # E Dielë
        dita_premtje = sot - timedelta(days=2)

    # Mbledh kandidatët nga 3 ditët
    kandidatet = []
    for offset in range(3):
        data_target = (dita_premtje + timedelta(days=offset)).strftime('%Y-%m-%d')
        try:
            response = requests.get(
                "https://v3.football.api-sports.io/fixtures",
                headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"}, timeout=10
            )
            te_dhenat = response.json()
        except:
            continue

        if "response" not in te_dhenat:
            continue

        # Merr koeficientët për këtë ditë
        BOOKMAKERS_PRIORITY = [8, 4, 6, 2, 11]
        odds_dite = {}
        for bookmaker_id in BOOKMAKERS_PRIORITY:
            try:
                page = 1
                while page <= 5:
                    res_odds = requests.get(
                        "https://v3.football.api-sports.io/odds",
                        headers=HEADERS,
                        params={"date": data_target, "timezone": "Europe/Tirane", "bookmaker": bookmaker_id, "page": page},
                        timeout=8
                    ).json()
                    if "response" not in res_odds or not res_odds["response"]:
                        break
                    for item in res_odds["response"]:
                        fix_id = str(item["fixture"]["id"])
                        if fix_id in odds_dite and odds_dite[fix_id]["1"]:
                            continue
                        try:
                            bets = item["bookmakers"][0]["bets"]
                            parsed = _nxirr_odds_reale(bets)
                            if parsed.get("1") and parsed.get("X") and parsed.get("2"):
                                odds_dite[fix_id] = parsed
                        except:
                            pass
                    paging = res_odds.get("paging", {})
                    if page >= paging.get("total", 1):
                        break
                    page += 1
            except:
                continue

        # Analizo vetëm ndeshjet VIP
        for n in te_dhenat["response"]:
            emri_liges = f"{n['league']['country']} - {n['league']['name']}"
            if not is_vip_league(emri_liges):
                continue
            id_ndeshja = str(n["fixture"]["id"])
            if id_ndeshja not in odds_dite:
                continue
            statusi_kod = n["fixture"]["status"]["short"]
            if statusi_kod in ["FT", "AET", "PEN"]:
                continue  # Ka mbaruar, skip

            try:
                ekipi_1 = n["teams"]["home"]["name"].replace("'", "")
                ekipi_2 = n["teams"]["away"]["name"].replace("'", "")
                k1 = odds_dite[id_ndeshja]["1"]
                kx = odds_dite[id_ndeshja]["X"]
                k2 = odds_dite[id_ndeshja]["2"]

                dna_1 = merr_dna_nga_db(n["teams"]["home"]["id"])
                dna_2 = merr_dna_nga_db(n["teams"]["away"]["id"])

                analiza, bes, rez_sakt, koef_str, extradb = analizo_ndeshjen_premium_master(
                    id_ndeshja, ekipi_1, ekipi_2,
                    n["teams"]["home"]["id"], n["teams"]["away"]["id"],
                    k1, kx, k2, emri_liges, [], dna_1=dna_1, dna_2=dna_2,
                    odds_full=odds_dite.get(id_ndeshja, {})
                )

                try:
                    ora_sakte = datetime.strptime(
                        n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S"
                    ).strftime("%H:%M")
                except:
                    ora_sakte = "N/A"

                kandidatet.append({
                    "id":              id_ndeshja,
                    "ndeshja":         f"{ekipi_1} vs {ekipi_2}",
                    "data":            data_target,
                    "ora":             ora_sakte,
                    "rezultati_sakt":  rez_sakt,
                    "koef_rez_sakt":   koef_str,
                    "besueshmeria":    bes,
                    "liga":            emri_liges,
                })
            except:
                continue

    # Rendit nga besueshmëria më e lartë
    kandidatet.sort(key=lambda x: x["besueshmeria"], reverse=True)

    # Zgjedh kombinimin që arrin total odds ≥ 10.0
    # Strategjia: fillo me top 1, shto deri ku totali kalon 10
    skedina_final = []
    total_odds = 1.0

    for kandidat in kandidatet:
        if total_odds >= 10.0 and len(skedina_final) >= 3:
            break
        try:
            k = float(kandidat["koef_rez_sakt"])
            if k <= 1.0 or k > 50:
                continue
            skedina_final.append(kandidat)
            total_odds *= k
            if total_odds >= 10.0 and len(skedina_final) >= 3:
                break
        except:
            continue
        if len(skedina_final) >= 5:
            break

    # Nëse nuk arrin 10, dështoi → kthe ekran "kapital protection"
    if total_odds < 10.0 or len(skedina_final) < 2:
        result = {
            "is_ready": False,
            "mesazhi":  "Sistemi nuk gjeti kombinim me siguri të mjaftueshme këtë fundjavë.",
            "skedina":  []
        }
        merr_vip_weekend._cache = (result, koha_tani)
        return result

    result = {
        "is_ready":   True,
        "skedina":    skedina_final,
        "total_odds": round(total_odds, 2),
        "mesazhi":    f"Skedina VIP gati! {len(skedina_final)} ndeshje, koef total: {round(total_odds, 2)}"
    }
    merr_vip_weekend._cache = (result, koha_tani)
    return result

@app.get("/api/detajet/{match_id}")
def merr_detajet_ndeshjes(match_id: int):
    try:
        response    = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS, params={"id": match_id}
        )
        ndeshja     = response.json()["response"][0]
        lista_evente = [
            {
                "koha":    f"{ev['time']['elapsed']}'",
                "ekipi":   ev['team']['name'],
                "lojtari": ev['player']['name'] or "Lojtar",
                "lloj":    ev['type'],
                "detaj":   ev['detail'],
            }
            for ev in ndeshja.get("events", [])
            if ev['type'] in ['Goal', 'Card']
        ]
        stats_formated = {}
        if ndeshja.get("statistics") and len(ndeshja["statistics"]) >= 2:
            s0, s1 = ndeshja["statistics"][0], ndeshja["statistics"][1]
            stats_formated = {
                "ekipi_1":     s0['team']['name'],
                "ekipi_2":     s1['team']['name'],
                "statistikat": [
                    {"lloji": x['type'], "vler_1": x['value'] or 0, "vler_2": y['value'] or 0}
                    for x, y in zip(s0['statistics'], s1['statistics'])
                    if x['type'] in ["Shots on Goal", "Ball Possession"]
                ],
            }
        return {"mesazhi": "Sukses", "evente": lista_evente, "statistika": stats_formated}
    except:
        return {"mesazhi": "Gabim"}

@app.get("/api/historia/{team_id}")
def merr_historine(team_id: int):
    try:
        response       = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS, params={"team": team_id, "last": 5}
        )
        rezultati_hist = []
        for n in response.json().get("response", []):
            ht = n.get("score", {}).get("halftime", {})
            ft = n.get("score", {}).get("fulltime", {})
            try:
                data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
            except:
                data_sakte = "N/A"
            rezultati_hist.append({
                "data":   data_sakte,
                "ora":    "FT",
                "ndeshja": f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}",
                "ht":     f"{ht.get('home')}-{ht.get('away')}" if ht and ht.get('home') is not None else "0-0",
                "ft":     f"{ft.get('home')}-{ft.get('away')}" if ft and ft.get('home') is not None else "0-0",
            })
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/renditja/{league_id}/{season}")
def merr_renditjen(league_id: int, season: int, team: str = None):
    try:
        res    = requests.get(
            "https://v3.football.api-sports.io/standings",
            headers=HEADERS,
            params={"league": league_id, "season": season},
            timeout=8
        )
        grupet = res.json()["response"][0]["league"]["standings"]
        renditja_list = []
        if team:
            grup_specifik = next(
                (g for g in grupet if any(team.lower() in r["team"]["name"].lower() for r in g)),
                grupet[0]
            )
            grupet = [grup_specifik]
        for grup in grupet:
            for r in grup:
                renditja_list.append({
                    "pozicioni": r["rank"],
                    "ekipi":     r["team"]["name"],
                    "piket":     r["points"],
                    "ndeshje":   r["all"]["played"],
                    "gola":      f"{r['all']['goals']['for']}:{r['all']['goals']['against']}",
                    "forma":     r["form"],
                })
        return {"mesazhi": "Sukses", "renditja": renditja_list}
    except Exception as e:
        return {"mesazhi": "Gabim", "renditja": [], "detaje": str(e)}

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    """
    Kthen tregjet shtesë (HT, DC, O/U, GG/NG, CS) për një ndeshje.
    Provojnë bookmakers sipas radhës: Bet365 → Pinnacle → 1xBet → Marathon → William Hill.
    """
    BOOKMAKERS_PRIORITY = [8, 4, 6, 2, 11]
    bets = None

    for bookmaker_id in BOOKMAKERS_PRIORITY:
        try:
            res = requests.get(
                "https://v3.football.api-sports.io/odds",
                headers=HEADERS,
                params={"fixture": match_id, "bookmaker": bookmaker_id},
                timeout=8
            )
            response = res.json().get("response", [])
            if response and response[0].get("bookmakers"):
                bets_provuar = response[0]["bookmakers"][0].get("bets", [])
                if bets_provuar:
                    bets = bets_provuar
                    break
        except:
            continue

    if not bets:
        return {"mesazhi": "Nuk ka koeficientë realë", "koeficientet": []}

    try:
        tregjet = []

        def get_bet(b_id):
            return next((b for b in bets if b["id"] == b_id), None)

        # ── 1X2 FULL TIME (id=1) ──
        b1 = get_bet(1)
        if b1:
            tregjet.append({"tregu_id": "match_winner", "opsionet": [
                {"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2"), "koef": v["odd"]}
                for v in b1["values"]
            ]})

        # ── HT 1X2 (id=13) ──
        b13 = get_bet(13)
        if b13:
            tregjet.append({"tregu_id": "ht_result", "opsionet": [
                {"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]}
                for v in b13["values"]
            ]})

        # ── HALFTIME/FULLTIME (id=22) ──
        b22 = get_bet(22)
        if b22:
            opsionet_htft = []
            for v in b22["values"]:
                val = v["value"].replace("Home","1").replace("Draw","X").replace("Away","2")
                opsionet_htft.append({"emer": f"HT/FT: {val}", "koef": v["odd"]})
            if opsionet_htft:
                tregjet.append({"tregu_id": "ht_ft", "opsionet": opsionet_htft})

        # ── DOUBLE CHANCE (id=12) ──
        b12 = get_bet(12)
        if b12:
            tregjet.append({"tregu_id": "double_chance", "opsionet": [
                {"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]}
                for v in b12["values"]
            ]})

        # ── OVER/UNDER (id=5) — disa linja: 1.5, 2.5, 3.5 ──
        b5 = get_bet(5)
        if b5:
            opsionet_ou = []
            for linja in ["1.5", "2.5", "3.5"]:
                for v in b5["values"]:
                    if linja in v["value"]:
                        emer = f"Mbi {linja}" if "Over" in v["value"] else f"Nën {linja}"
                        opsionet_ou.append({"emer": emer, "koef": v["odd"]})
            if opsionet_ou:
                tregjet.append({"tregu_id": "over_under", "opsionet": opsionet_ou})

        # ── BTTS / GG-NG (id=8) ──
        b8 = get_bet(8)
        if b8:
            tregjet.append({"tregu_id": "btts", "opsionet": [
                {"emer": "Po (GG)" if v["value"]=="Yes" else "Jo (NG)", "koef": v["odd"]}
                for v in b8["values"]
            ]})

        # ── RESULT/BTTS (id=24) — Fitues + GG/NG kombinim ──
        b24 = get_bet(24)
        if b24:
            opsionet_rbtts = []
            for v in b24["values"]:
                val = (v["value"].replace("Home","1").replace("Draw","X").replace("Away","2")
                       .replace("/Yes"," + GG").replace("/No"," + NG"))
                opsionet_rbtts.append({"emer": val, "koef": v["odd"]})
            if opsionet_rbtts:
                tregjet.append({"tregu_id": "result_btts", "opsionet": opsionet_rbtts})

        # ── BTTS + OVER/UNDER (id=25 ose 26) — GG+Over, GG+Under ──
        for b_id in [25, 26, 35]:
            b_combo = get_bet(b_id)
            if b_combo:
                opsionet_combo = []
                for v in b_combo["values"]:
                    val = (v["value"].replace("Yes","GG").replace("No","NG")
                           .replace("Over","Mbi").replace("Under","Nën"))
                    opsionet_combo.append({"emer": val, "koef": v["odd"]})
                if opsionet_combo:
                    tregjet.append({"tregu_id": f"combo_{b_id}", "opsionet": opsionet_combo[:8]})
                break

        # ── WIN TO NIL (id=28) — Fiton pa pësuar ──
        b28 = get_bet(28)
        if b28:
            opsionet_wtn = []
            for v in b28["values"]:
                val = v["value"].replace("Home","1").replace("Away","2")
                opsionet_wtn.append({"emer": f"{val} pa pësuar", "koef": v["odd"]})
            if opsionet_wtn:
                tregjet.append({"tregu_id": "win_to_nil", "opsionet": opsionet_wtn})

        # ── EXACT GOALS (id=38) ──
        b38 = get_bet(38)
        if b38:
            opsionet_eg = []
            for v in b38["values"]:
                if v["value"] in ["0", "1", "2", "3", "4"]:
                    opsionet_eg.append({"emer": f"{v['value']} gola saktë", "koef": v["odd"]})
            if opsionet_eg:
                tregjet.append({"tregu_id": "exact_goals", "opsionet": opsionet_eg})

        # ── CORRECT SCORE (id=10) — më shumë rezultate ──
        b10 = get_bet(10)
        if b10:
            tregjet.append({"tregu_id": "correct_score", "opsionet": [
                {"emer": v["value"].replace(":", "-"), "koef": v["odd"]}
                for v in b10["values"]
                if v["value"] in ["1:0","2:0","2:1","3:0","3:1","0:0","1:1","2:2",
                                  "0:1","0:2","1:2","0:3","1:3"]
            ]})

        return {"mesazhi": "Sukses", "koeficientet": tregjet}
    except:
        return {"mesazhi": "Gabim", "koeficientet": []}

# (Webhook-u LemonSqueezy u HOQ — vrimë sigurie; pagesat tani me Cryptomus.)


# ==========================================
# B2B PUBLIC API (v1) — RapidAPI / APILayer / çelësa direkt
# Auth: X-RapidAPI-Proxy-Secret (proxy) OSE X-API-Key (çelës vetjak në tabelën api_keys)
# ==========================================
import secrets as _secrets

RAPIDAPI_PROXY_SECRET = os.environ.get("RAPIDAPI_PROXY_SECRET", "").strip()
ZYLA_PROXY_SECRET = os.environ.get("ZYLA_PROXY_SECRET", "").strip()
B2B_ADMIN_SECRET = os.environ.get("B2B_ADMIN_SECRET", "").strip()
SUPABASE_URL_APIKEYS = f"{SUPABASE_BASE}/rest/v1/api_keys"
B2B_LIMIT_FREE = 100   # kërkesa/ditë për çelësat pa limit të vendosur


def _b2b_auth(proxy_secret, api_key, zyla_secret=None):
    """Kthen identitetin ose ngre HTTPException me status të saktë HTTP (401/403/429)."""
    # 1) Trafiku përmes RapidAPI/APILayer — proxy secret i platformës
    if RAPIDAPI_PROXY_SECRET and proxy_secret and hmac.compare_digest(str(proxy_secret).strip(), RAPIDAPI_PROXY_SECRET):
        return {"ok": True, "burimi": "proxy", "plan": "proxy"}
    # 1b) Trafiku përmes Zyla API Hub — proxy secret i Zyla-s (header i vendosur te Access Control)
    if ZYLA_PROXY_SECRET and zyla_secret and hmac.compare_digest(str(zyla_secret).strip(), ZYLA_PROXY_SECRET):
        return {"ok": True, "burimi": "zyla", "plan": "proxy"}
    # 2) Çelës vetjak (klientë direkt)
    if not api_key or not str(api_key).strip():
        raise HTTPException(status_code=401, detail="Missing API key. Pass it in the 'X-API-Key' header.")
    try:
        r = requests.get(f"{SUPABASE_URL_APIKEYS}?select=*&celes=eq.{requests.utils.quote(str(api_key).strip(), safe='')}&limit=1",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=8)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    k = rows[0]
    if not k.get("aktiv", True):
        raise HTTPException(status_code=403, detail="API key is disabled.")
    sot = _data_lokale(0)
    perd = int(k.get("perdorime_sot") or 0)
    if str(k.get("data_perdorimit") or "") != sot:
        perd = 0
    lim = int(k.get("limit_ditor") or B2B_LIMIT_FREE)
    if lim > 0 and perd >= lim:
        raise HTTPException(status_code=429, detail=f"Daily limit reached ({lim} requests/day). Resets at midnight Europe/Tirane.")
    try:
        requests.patch(f"{SUPABASE_URL_APIKEYS}?id=eq.{k.get('id')}", headers=SUPABASE_SERVICE_HEADERS,
                       json={"perdorime_sot": perd + 1, "data_perdorimit": sot,
                             "perdorime_total": int(k.get("perdorime_total") or 0) + 1}, timeout=8)
    except Exception:
        pass
    return {"ok": True, "burimi": "key", "plan": k.get("plan") or "free"}


def _b2b_match(p):
    """Formaton një parashikim për API-në publike (anglisht, pa dist_gola të plotë)."""
    nd = (p.get("ndeshja") or "").strip()
    if " vs " in nd:
        home, away = nd.split(" vs ", 1)
    else:
        home, away = nd, ""
    tg = p.get("tregjet") or {}
    od = p.get("odds_reale") or {}
    markets = {}
    for m, v in tg.items():
        try:
            pr = float(v)
        except Exception:
            continue
        if pr <= 0:
            continue
        try:
            o = float(od.get(m, 0) or 0)
        except Exception:
            o = 0.0
        markets[m] = {"probability": round(pr, 4), "odds": round(o, 2) if o > 1 else round(1.0 / pr, 2)}
    top = [{"score": x["skor"], "probability": x["prob"], "fair_odds": x["koef"]}
           for x in _top_rezultate_sakta(p, 3)]
    return {"id": p.get("id"), "match": nd, "home_team": home.strip(), "away_team": away.strip(),
            "league": p.get("liga_emri"), "date": p.get("data"), "kickoff": p.get("ora"),
            "status": p.get("statusi"), "confidence": p.get("besueshmeria"),
            "best_bet": p.get("best_bet"),
            "correct_score": {"score": p.get("rezultati_sakt"), "fair_odds": p.get("koef_rez_sakt")},
            "top_scorelines": top, "markets": markets}


_B2B_SELECT = "id,ndeshja,data,ora,liga_emri,statusi,best_bet,tregjet,odds_reale,rezultati_sakt,koef_rez_sakt,dist_gola,besueshmeria"


@app.get("/v1/status")
def b2b_status():
    return {"api": "SOCCER1X2 PRO — Football Predictions API", "version": "1.0", "status": "ok",
            "engine": "Hybrid XGBoost + Monte Carlo (53k+ matches trained)",
            "coverage": "today + tomorrow fixtures",
            "markets": "1X2, Over/Under 1.5-3.5, BTTS (GG/NG), Double Chance, Correct Score",
            "auth": "X-API-Key header (or via API marketplace)"}


@app.get("/v1/predictions")
def b2b_predictions(date: str = "today", league: str = "", limit: int = 50,
                    x_rapidapi_proxy_secret: str = Header(None), x_api_key: str = Header(None), x_zyla_secret: str = Header(None)):
    _b2b_auth(x_rapidapi_proxy_secret, x_api_key, x_zyla_secret)
    dt_sot, dt_neser = _data_lokale(0), _data_lokale(1)
    d = (date or "today").strip().lower()
    if d in ("today", ""):
        dt = dt_sot
    elif d == "tomorrow":
        dt = dt_neser
    elif d in (dt_sot, dt_neser):
        dt = d
    else:
        raise HTTPException(status_code=400, detail="Only 'today' and 'tomorrow' fixtures are available on this plan.")
    try:
        limit = max(1, min(int(limit or 50), 100))
    except Exception:
        limit = 50
    url = (f"{SUPABASE_URL_PREDS}?select={_B2B_SELECT}"
           f"&data=eq.{dt}&tregjet=not.is.null&order=ora.asc&limit={limit}")
    if league and league.strip():
        url += f"&liga_emri=eq.{requests.utils.quote(league.strip(), safe='')}"
    r = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=12)
    rows = r.json() if r.status_code == 200 else []
    out = [_b2b_match(p) for p in rows]
    return {"success": True, "date": dt, "count": len(out), "predictions": out}


@app.get("/v1/predictions/{pred_id}")
def b2b_prediction_single(pred_id: int,
                          x_rapidapi_proxy_secret: str = Header(None), x_api_key: str = Header(None), x_zyla_secret: str = Header(None)):
    _b2b_auth(x_rapidapi_proxy_secret, x_api_key, x_zyla_secret)
    r = requests.get(f"{SUPABASE_URL_PREDS}?select={_B2B_SELECT}&id=eq.{int(pred_id)}&limit=1",
                     headers=SUPABASE_SERVICE_HEADERS, timeout=10)
    rows = r.json() if r.status_code == 200 else []
    if not rows:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return {"success": True, "prediction": _b2b_match(rows[0])}


@app.get("/v1/leagues")
def b2b_leagues(x_rapidapi_proxy_secret: str = Header(None), x_api_key: str = Header(None), x_zyla_secret: str = Header(None)):
    _b2b_auth(x_rapidapi_proxy_secret, x_api_key, x_zyla_secret)
    dt_sot, dt_neser = _data_lokale(0), _data_lokale(1)
    r = requests.get(f"{SUPABASE_URL_PREDS}?select=liga_emri,data&data=in.({dt_sot},{dt_neser})&tregjet=not.is.null&limit=1000",
                     headers=SUPABASE_SERVICE_HEADERS, timeout=12)
    rows = r.json() if r.status_code == 200 else []
    cnt = {}
    for p in rows:
        lg = p.get("liga_emri") or "?"
        cnt[lg] = cnt.get(lg, 0) + 1
    out = [{"league": k, "fixtures": v} for k, v in sorted(cnt.items(), key=lambda x: -x[1])]
    return {"success": True, "count": len(out), "leagues": out}


# ---------- Admin: krijo / fik çelësa (vetëm me B2B_ADMIN_SECRET) ----------
@app.get("/v1/admin/create-key")
def b2b_admin_create_key(secret: str = "", name: str = "", email: str = "", plan: str = "free", limit: int = 100):
    if not B2B_ADMIN_SECRET or (secret or "").strip() != B2B_ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    celes = "s1x2_" + _secrets.token_hex(24)
    try:
        limit = max(0, int(limit))
    except Exception:
        limit = 100
    body = {"celes": celes, "emri": (name or "").strip()[:80], "email": (email or "").strip()[:120],
            "plan": (plan or "free").strip()[:20], "limit_ditor": limit, "aktiv": True,
            "perdorime_sot": 0, "perdorime_total": 0}
    r = requests.post(SUPABASE_URL_APIKEYS, headers={**SUPABASE_SERVICE_HEADERS, "Prefer": "return=representation"},
                      json=body, timeout=10)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail="Could not create key (is the api_keys table created?).")
    return {"success": True, "api_key": celes, "plan": body["plan"], "daily_limit": limit,
            "usage": "Send it in the 'X-API-Key' header."}


@app.get("/v1/admin/toggle-key")
def b2b_admin_toggle_key(secret: str = "", key: str = "", active: int = 1):
    if not B2B_ADMIN_SECRET or (secret or "").strip() != B2B_ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    if not key.strip():
        raise HTTPException(status_code=400, detail="Missing 'key'.")
    r = requests.patch(f"{SUPABASE_URL_APIKEYS}?celes=eq.{requests.utils.quote(key.strip(), safe='')}",
                       headers=SUPABASE_SERVICE_HEADERS, json={"aktiv": bool(int(active))}, timeout=10)
    return {"success": r.status_code in (200, 204), "key": key.strip()[:14] + "...", "active": bool(int(active))}


# ==========================================
# VIP COMBO NDESHJESH — akumulues 2-3 ndeshjesh nga rezultatet e sakta
# me besueshmërinë më të lartë. C(n,2) + C(n,3) skedina.
# ==========================================
import itertools as _it


def _prob_rez_sakt(p):
    """Probabiliteti i rezultatit të saktë të parashikuar nga dist_gola."""
    dist = p.get("dist_gola") or {}
    rs = p.get("rezultati_sakt")
    try:
        total = sum(float(v or 0) for v in dist.values())
    except Exception:
        total = 0.0
    if not rs or total <= 0:
        return 0.0
    v = dist.get(rs, dist.get(str(rs).replace(" ", ""), 0))
    try:
        return float(v or 0) / total
    except Exception:
        return 0.0


@app.get("/api/vip-combo-nde")
def vip_combo_nde(email: str = "", nr: int = 4, madhesi: str = "23", liga: str = "", paguaj: int = 0,
                  authorization: str = Header(None)):
    """COMBO NDESHJESH: merr nr ndeshjet me besueshmërinë më të lartë (rezultati i saktë 1/ndeshje),
    i kombinon në skedina me 2 dhe/ose 3 ndeshje. Ndan day-pass-in me VIP Combo (produkt 'vipcombo')."""
    email = _email_auth(authorization, email)
    if not email or not email.strip():
        return {"sukses": False, "kod": "LOGIN_FIRST", "arsye": "Hyr së pari në llogari."}
    _drejta = _kontrollo_te_drejten(email, "vipcombo", CMIM_VIPCOMBO, bool(paguaj))
    if not _drejta["ok"]:
        return {"sukses": False, "bllokuar": True,
                "kerko_pagese": _drejta.get("kerko_pagese", False),
                "mungojne_kredite": _drejta.get("mungojne_kredite", False),
                "arsye": _drejta["arsye"],
                "portofoli": _drejta["portofoli"], "is_vip": _drejta["is_vip"], "cmimi": CMIM_VIPCOMBO}
    nr = min(6, max(4, int(nr or 4)))
    madhesi = str(madhesi or "23").strip()
    if madhesi not in ("2", "3", "23"):
        madhesi = "23"
    dt = _data_lokale(0); dt_neser = _data_lokale(1)
    url = (f"{SUPABASE_URL_PREDS}?select=id,ndeshja,ora,liga_emri,rezultati_sakt,koef_rez_sakt,dist_gola,besueshmeria"
           f"&data=in.({dt},{dt_neser})&dist_gola=not.is.null&rezultati_sakt=not.is.null"
           f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&besueshmeria=not.is.null"
           f"&order=besueshmeria.desc&limit=40")
    if liga and liga.strip():
        url += f"&liga_emri=eq.{requests.utils.quote(liga.strip(), safe='')}"
    r = requests.get(url, headers=SUPABASE_SERVICE_HEADERS, timeout=10)
    rows_plot = r.json() if r.status_code == 200 else []

    def _ndertimi_nde(rws):
        """PA DUBLIKATA (sipas emrit); vetëm rreshta me probabilitet real të skorit."""
        nd = []
        _pare = set()
        for p in rws:
            _k = _nm_key(p)
            if _k and _k in _pare:
                continue
            pr = _prob_rez_sakt(p)
            if pr <= 0:
                continue
            try:
                kf = float(p.get("koef_rez_sakt") or 0)
            except Exception:
                kf = 0.0
            if kf <= 1:
                kf = round(1.0 / pr, 2)
            nd.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"), "ora": p.get("ora"),
                       "liga": p.get("liga_emri"), "skor": p.get("rezultati_sakt"),
                       "koef": round(kf, 2), "prob": round(pr, 4),
                       "besueshmeria": p.get("besueshmeria")})
            if _k:
                _pare.add(_k)
            if len(nd) >= nr:
                break
        return nd

    # PËRZGJEDHJA NIS NGA % MË E LARTË (besueshmeria.desc); pragu ulet me shkallë vetëm po s'mjaftoi
    ndeshjet, prag_perdorur = [], None
    for _prag in (BESU_PRAG_VIPCOMBO, 65.0, 60.0, 55.0, 50.0):
        nd = _ndertimi_nde(_filtro_besu(rows_plot, prag=_prag))
        if len(nd) > len(ndeshjet):
            ndeshjet, prag_perdorur = nd, _prag
        if len(nd) >= nr:
            break
    if len(ndeshjet) < 2 or (madhesi == "3" and len(ndeshjet) < 3):
        return {"sukses": False, "kod": "VIPCOMBO_NOT_ENOUGH_CONF",
                "arsye": "Sot s'ka mjaft ndeshje me besueshmëri të mjaftueshme (u provua deri në ≥50%). Provo më vonë."}

    madhesite = {"2": [2], "3": [3], "23": [2, 3]}[madhesi]
    kombinimet = []
    for m in madhesite:
        if len(ndeshjet) < m:
            continue
        for grup in _it.combinations(ndeshjet, m):
            jp = 1.0; kt = 1.0; skedina = []
            for n in grup:
                jp *= n["prob"]; kt *= n["koef"]
                skedina.append({"ndeshja": n["ndeshja"], "skor": n["skor"], "koef": n["koef"]})
            _bv = [float(n["besueshmeria"]) for n in grup if n.get("besueshmeria") is not None]
            kombinimet.append({"skedina": skedina, "prob": round(jp, 5), "koef_total": round(kt, 2),
                               "besu": round(sum(_bv) / len(_bv)) if _bv else None})
    kombinimet.sort(key=lambda k: k["prob"], reverse=True)

    _porto_ri = _konfirmo_perdorimin(email, "vipcombo", CMIM_VIPCOMBO, _drejta["is_vip"], _drejta["portofoli"], _drejta.get("falas", False))
    _bv = [float(n["besueshmeria"]) for n in ndeshjet if n.get("besueshmeria") is not None]
    return {"sukses": True, "nr_ndeshje": len(ndeshjet), "madhesi": madhesi,
            "prag_besueshmerie": prag_perdorur,
            "besu_mesatare": round(sum(_bv) / len(_bv)) if _bv else None,
            "ndeshjet": ndeshjet, "kombinimet": kombinimet, "nr_kombinimesh": len(kombinimet),
            "portofoli": _porto_ri, "u_pagua": (not _drejta["is_vip"] and not _drejta.get("falas", False)),
            "cmimi": CMIM_VIPCOMBO}


@app.get("/api/admin/ht-mbulimi")
def admin_ht_mbulimi():
    """DIAGNOSTIKË: sa % e parashikimeve aktive (sot+nesër) kanë skor HT nga simulimi hibrid."""
    dt, dt_n = _data_lokale(0), _data_lokale(1)
    try:
        r = requests.get(f"{SUPABASE_URL_PREDS}?select=id,ndeshja,data,tregjet&data=in.({dt},{dt_n})&tregjet=not.is.null&limit=500",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=12)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    tot = len(rows); me_skor = 0; me_htft = 0; pa_ht = []
    for p in rows:
        tg = p.get("tregjet") or {}
        if isinstance(tg, str):
            try:
                tg = json.loads(tg)
            except Exception:
                tg = {}
        ka_skor = bool(_parse_score(str(tg.get("skor_ht") or "")))
        ka_htft = bool(tg.get("ht_ft"))
        if ka_skor:
            me_skor += 1
        if ka_htft:
            me_htft += 1
        if not ka_skor and len(pa_ht) < 20:
            pa_ht.append({"id": p.get("id"), "ndeshja": p.get("ndeshja"), "data": p.get("data")})
    return {"sukses": True, "data": [dt, dt_n], "gjithsej": tot,
            "me_skor_ht": me_skor, "me_ht_ft": me_htft,
            "mbulimi_skor_ht_pct": round(100.0 * me_skor / tot, 1) if tot else None,
            "pa_skor_ht_shembuj": pa_ht,
            "shenim": "Rreshtat pa HT sherohen vete ne rigjenerimin e radhes (upsert merge-duplicates)."}


# ==========================================
# PANELI I RRJETEVE SOCIALE (admin) — postime të gatshme për kopjim manual
# IG / TikTok / Facebook · SQ + EN · nga parashikimet, Fitoret dhe Performanca reale
# Hapet: /api/social/postime?secret=B2B_ADMIN_SECRET
# ==========================================
import html as _html

_MKT_SQ = {"1":"Fitore vendase","X":"Barazim","2":"Fitore mysafire","1X":"Vendas ose barazim",
           "X2":"Barazim ose mysafir","12":"Pa barazim","GG":"Të dy shënojnë","NG":"Vetëm njëra shënon",
           "Over 1.5":"Mbi 1.5 gola","Under 1.5":"Nën 1.5 gola","Over 2.5":"Mbi 2.5 gola",
           "Under 2.5":"Nën 2.5 gola","Over 3.5":"Mbi 3.5 gola","Under 3.5":"Nën 3.5 gola"}
_MKT_EN = {"1":"Home win","X":"Draw","2":"Away win","1X":"Home or draw","X2":"Draw or away",
           "12":"No draw","GG":"Both teams score","NG":"Not both score","Over 1.5":"Over 1.5 goals",
           "Under 1.5":"Under 1.5 goals","Over 2.5":"Over 2.5 goals","Under 2.5":"Under 2.5 goals",
           "Over 3.5":"Over 3.5 goals","Under 3.5":"Under 3.5 goals"}

_MODEL_TRAJNIM = "53.000+"   # ndeshje trajnimi (nga historik_trajnimi)


def _social_te_dhenat():
    """Mbledh të dhënat reale për postimet: goditjet e djeshme, piku i sotëm, performanca."""
    dt_sot, dt_dje = _data_lokale(0), _data_lokale(-1)
    out = {"dje": dt_dje, "sot": dt_sot, "goditjet": [], "n_gja1x2": 0, "n_ok1x2": 0,
           "n_okskor": 0, "pik": None, "n_pik_te_tjera": 0,
           "perf": {"x1x2": None, "b1": None, "gg": None, "ou": None, "skor": None, "n": 0}}
    # 1) GODITJET E DJESHME (arkiv)
    try:
        r = requests.get(f"{ARKIV_URL}?select=ndeshja,liga,parashikimi,rezultati_ft,goditi_1x2,goditi_skor"
                         f"&data=eq.{dt_dje}&order=goditi_skor.desc.nullslast,goditi_1x2.desc.nullslast&limit=60",
                         headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        rows = []
    for p in rows:
        if p.get("goditi_1x2") is not None:
            out["n_gja1x2"] += 1
            if p.get("goditi_1x2"):
                out["n_ok1x2"] += 1
        if p.get("goditi_skor"):
            out["n_okskor"] += 1
        if p.get("goditi_1x2") or p.get("goditi_skor"):
            out["goditjet"].append({"ndeshja": p.get("ndeshja"), "ft": p.get("rezultati_ft"),
                                    "parashikimi": p.get("parashikimi"), "skor_ok": bool(p.get("goditi_skor"))})
    # 2) PIKU I SOTËM (parashikimi me besueshmëri më të lartë)
    try:
        rp = requests.get(f"{SUPABASE_URL_PREDS}?select=ndeshja,liga_emri,best_bet,besueshmeria,rezultati_sakt"
                          f"&data=in.({dt_sot},{_data_lokale(1)})&best_bet=not.is.null&besueshmeria=not.is.null"
                          f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)&order=besueshmeria.desc&limit=30",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=10)
        preds = rp.json() if rp.status_code == 200 else []
    except Exception:
        preds = []
    if preds:
        top = preds[0]
        bb = top.get("best_bet") or {}
        out["pik"] = {"ndeshja": top.get("ndeshja"), "tregu": bb.get("tregu"),
                      "besu": top.get("besueshmeria"), "skor": top.get("rezultati_sakt")}
        out["n_pik_te_tjera"] = max(0, len(preds) - 1)
    # 3) PERFORMANCA (nga arkivi, si /api/performanca)
    try:
        ra = requests.get(f"{ARKIV_URL}?select=parashikimi,rezultati_ft,goditi_1x2,goditi_skor&order=data.desc&limit=600",
                          headers=SUPABASE_SERVICE_HEADERS, timeout=12)
        arows = ra.json() if ra.status_code == 200 else []
    except Exception:
        arows = []
    n1=n1ok=ns=nsok=ng1=ng1ok=ngg=nggok=nou=nouok=0
    for row in arows:
        par = _parse_score(row.get("parashikimi") or ""); ft = _parse_score(row.get("rezultati_ft") or "")
        if row.get("goditi_1x2") is not None:
            n1 += 1; n1ok += 1 if row.get("goditi_1x2") else 0
        if row.get("goditi_skor") is not None:
            ns += 1; nsok += 1 if row.get("goditi_skor") else 0
        if par and ft:
            ng1 += 1; ng1ok += 1 if (abs(par[0]-ft[0])<=1 and abs(par[1]-ft[1])<=1) else 0
            ngg += 1; nggok += 1 if ((par[0]>0 and par[1]>0)==(ft[0]>0 and ft[1]>0)) else 0
            nou += 1; nouok += 1 if (((par[0]+par[1])>2.5)==((ft[0]+ft[1])>2.5)) else 0
    def _pc(o,n): return round(100*o/n) if n else None
    out["perf"] = {"x1x2": _pc(n1ok,n1), "b1": _pc(ng1ok,ng1), "gg": _pc(nggok,ngg),
                   "ou": _pc(nouok,nou), "skor": _pc(nsok,ns), "n": n1}
    return out


def _social_postime(d):
    """Ndërton postimet (SQ + EN, IG/FB + TikTok) me TON AGRESIV + ftesë VIP Combo.
    Përmbajtja shoqërohet me foto/pamje nga aplikacioni (sugjerimet e vendosura brenda)."""
    postime = []
    URL = "soccer1x2pro.com"
    FOTO_SQ = "[📸 VENDOS KËTU: pamje nga aplikacioni me parashikimin/rezultatin]"
    FOTO_EN = "[📸 PUT HERE: screenshot from the app showing the prediction/result]"
    CTA_SQ = f"👉 Parashikimet në KOHË REALE + VIP Combo 👑 vetëm te {URL}"
    CTA_EN = f"👉 REAL-TIME predictions + VIP Combo 👑 only at {URL}"
    DIS_SQ = "⚠️ Analizë statistikore · 18+ · Luaj me përgjegjësi"
    DIS_EN = "⚠️ Statistical analysis · 18+ · Bet responsibly"

    # ── 1) DËSHMI REZULTATESH (arma kryesore — agresive) ──
    if d["goditjet"]:
        lst = d["goditjet"][:5]
        def _lines():
            out = []
            for g in lst:
                mark = " 🎯 SKOR SAKTË!" if g["skor_ok"] else " ✅"
                out.append(f"⚽ {g['ndeshja']} → {g['ft']}{mark}")
            return "\n".join(out)
        n_ok, n_tot, n_skor = d["n_ok1x2"], d["n_gja1x2"], d["n_okskor"]
        # Zgjedh titullin sipas statistikës më mbresëlënëse reale
        if n_skor >= 2:
            head_sq = f"🎯🔥 BINGO! {n_skor} REZULTATE TË SAKTA DJE! 🔥🎯"
            head_en = f"🎯🔥 BINGO! {n_skor} EXACT SCORES YESTERDAY! 🔥🎯"
        else:
            head_sq = f"🔥 {n_ok}/{n_tot} GODITJE DJE — AI-ja S'FAL! 🔥"
            head_en = f"🔥 {n_ok}/{n_tot} HITS YESTERDAY — THE AI DELIVERS! 🔥"
        sq_igfb = (f"{head_sq}\n\n{FOTO_SQ}\n\n{_lines()}\n\n"
                   f"📊 {n_ok}/{n_tot} saktë në 1X2" + (f" · {n_skor} rezultate TË SAKTA 🎯" if n_skor else "") + "\n"
                   f"🤖 Hybrid AI — Monte Carlo + XGBoost, {_MODEL_TRAJNIM} ndeshje trajnim\n\n"
                   f"Kush na ndoqi dje FITOI. Mos e humb sot 💰\n{CTA_SQ}\n\n{DIS_SQ}\n"
                   f"#futboll #parashikime #AI #soccer1x2pro #superliga #botërori2026 #bingo #fitim")
        en_igfb = (f"{head_en}\n\n{FOTO_EN}\n\n{_lines()}\n\n"
                   f"📊 {n_ok}/{n_tot} correct on 1X2" + (f" · {n_skor} EXACT scores 🎯" if n_skor else "") + "\n"
                   f"🤖 Hybrid AI — Monte Carlo + XGBoost, {_MODEL_TRAJNIM} matches trained\n\n"
                   f"Whoever followed us yesterday WON. Don't miss today 💰\n{CTA_EN}\n\n{DIS_EN}\n"
                   f"#football #soccer #predictions #AI #bettingtips #worldcup2026 #winning")
        sq_tt = (f"🎬 HOOK (0-2 sek): \"{n_skor} REZULTATE TË SAKTA DJE?! 🤯\" — ose \"{n_ok}/{n_tot} GODITJE 🔥\"\n"
                 f"📸 PAMJA: video/screenshot i aplikacionit duke treguar goditjet një nga një, shpejt me muzikë hype.\n\n"
                 f"CAPTION: AI-ja jonë s'fal 🔥 {n_ok}/{n_tot} dje" + (f" · {n_skor} skor saktë 🎯" if n_skor else "") + f" · Parashikimet sot 👉 {URL} 👑\n"
                 f"#futboll #AI #parashikime #fyp #botërori #bingo #fitim ⚠️ 18+")
        en_tt = (f"🎬 HOOK (0-2s): \"{n_skor} EXACT SCORES YESTERDAY?! 🤯\" — or \"{n_ok}/{n_tot} HITS 🔥\"\n"
                 f"📸 VISUAL: app screen recording showing hits one by one, fast, hype music.\n\n"
                 f"CAPTION: Our AI delivers 🔥 {n_ok}/{n_tot} yesterday · Today's picks 👉 {URL} 👑\n"
                 f"#football #AI #fyp #worldcup #winning ⚠️ 18+")
        postime.append({"titull": "🔥 Dëshmi rezultatesh (dje) — AGRESIV",
                        "sub": f"{n_ok}/{n_tot} 1X2 · {n_skor} skor të saktë",
                        "blloqe": [("Instagram / Facebook · SQ", sq_igfb), ("Instagram / Facebook · EN", en_igfb),
                                   ("TikTok · SQ", sq_tt), ("TikTok · EN", en_tt)]})

    # ── 2) PIKU FALAS I DITËS (teaser drejt VIP Combo) ──
    if d["pik"] and d["pik"].get("tregu"):
        pk = d["pik"]; lab_sq = _MKT_SQ.get(pk["tregu"], pk["tregu"]); lab_en = _MKT_EN.get(pk["tregu"], pk["tregu"])
        conf = pk.get("besu"); nm = d["n_pik_te_tjera"]
        sq_igfb = (f"🎁 PIKU FALAS I DITËS 🎁\n\n{FOTO_SQ}\n\n⚽ {pk['ndeshja']}\n🔮 AI: {lab_sq}\n📊 Besueshmëria: {conf}% 🔒\n\n"
                   f"Ky është VETËM 1 nga {nm} parashikime TOP sot 👑\n"
                   f"VIP Combo të jep disa rezultate/kombinime për të MAKSIMIZUAR fitimin 🚀\n{CTA_SQ}\n\n{DIS_SQ}\n"
                   f"#futboll #parashikime #AI #freepick #soccer1x2pro #vipcombo #botërori")
        en_igfb = (f"🎁 FREE PICK OF THE DAY 🎁\n\n{FOTO_EN}\n\n⚽ {pk['ndeshja']}\n🔮 AI: {lab_en}\n📊 Confidence: {conf}% 🔒\n\n"
                   f"This is just 1 of {nm} TOP predictions today 👑\n"
                   f"VIP Combo gives you multiple results/combos to MAXIMIZE winnings 🚀\n{CTA_EN}\n\n{DIS_EN}\n"
                   f"#football #soccer #freepick #AI #vipcombo #bettingtips #worldcup")
        sq_tt = (f"🎬 HOOK: \"Piku FALAS i sotëm 👇 (të tjerat te faqja)\"\n📸 PAMJA: screenshot i ndeshjes + parashikimit + %.\n\n"
                 f"CAPTION: {pk['ndeshja']} → {lab_sq} ({conf}%) 🎯 +{nm} të tjera + VIP Combo 👉 {URL} 👑\n#futboll #AI #fyp #vipcombo ⚠️ 18+")
        en_tt = (f"🎬 HOOK: \"Today's FREE pick 👇 (rest on the site)\"\n📸 VISUAL: match + prediction + % screenshot.\n\n"
                 f"CAPTION: {pk['ndeshja']} → {lab_en} ({conf}%) 🎯 +{nm} more + VIP Combo 👉 {URL} 👑\n#football #AI #fyp #vipcombo ⚠️ 18+")
        postime.append({"titull": "🎁 Piku falas i ditës → VIP Combo", "sub": f"{pk['ndeshja']} · {conf}%",
                        "blloqe": [("Instagram / Facebook · SQ", sq_igfb), ("Instagram / Facebook · EN", en_igfb),
                                   ("TikTok · SQ", sq_tt), ("TikTok · EN", en_tt)]})

    # ── 3) PERFORMANCA (besim — agresive) ──
    pf = d["perf"]
    if pf["x1x2"] is not None and pf["n"] >= 10:
        sq_igfb = (f"🤖🔥 AI-JA JONË S'GABON SHPESH 🔥🤖\n\n{FOTO_SQ}\n\nMbi {pf['n']} ndeshje të verifikuara AUTOMATIKISHT:\n"
                   f"🎯 1X2: {pf['x1x2']}%\n🎯 Brenda 1 goli: {pf['b1']}%\n🎯 GG/NG: {pf['gg']}%\n🎯 Over/Under: {pf['ou']}%\n\n"
                   f"Pa mashtrime — çdo rezultat verifikohet vetë, publikisht 💯\n{CTA_SQ}\n\n{DIS_SQ}\n"
                   f"#futboll #AI #statistika #parashikime #soccer1x2pro #transparence #fitim")
        en_igfb = (f"🤖🔥 OUR AI RARELY MISSES 🔥🤖\n\n{FOTO_EN}\n\nOver {pf['n']} AUTO-verified matches:\n"
                   f"🎯 1X2: {pf['x1x2']}%\n🎯 Within 1 goal: {pf['b1']}%\n🎯 BTTS: {pf['gg']}%\n🎯 Over/Under: {pf['ou']}%\n\n"
                   f"No tricks — every result verified automatically, publicly 💯\n{CTA_EN}\n\n{DIS_EN}\n"
                   f"#football #soccer #AI #stats #predictions #transparency #winning")
        sq_tt = (f"🎬 HOOK: \"AI-ja jonë: {pf['x1x2']}% saktë në 1X2 mbi {pf['n']} ndeshje 🤯\"\n📸 PAMJA: metrikat një nga një me numra që rriten.\n\n"
                 f"CAPTION: {pf['x1x2']}% 1X2 · s'gabon shpesh 🔥 Provoje 👉 {URL} 👑\n#futboll #AI #fyp #statistika ⚠️ 18+")
        en_tt = (f"🎬 HOOK: \"Our AI: {pf['x1x2']}% correct on 1X2 over {pf['n']} matches 🤯\"\n📸 VISUAL: metrics counting up one by one.\n\n"
                 f"CAPTION: {pf['x1x2']}% 1X2 · rarely misses 🔥 Try it 👉 {URL} 👑\n#football #AI #fyp #stats ⚠️ 18+")
        postime.append({"titull": "🤖 Performanca (besim) — AGRESIV", "sub": f"1X2 {pf['x1x2']}% · {pf['n']} ndeshje",
                        "blloqe": [("Instagram / Facebook · SQ", sq_igfb), ("Instagram / Facebook · EN", en_igfb),
                                   ("TikTok · SQ", sq_tt), ("TikTok · EN", en_tt)]})
    return postime


@app.get("/api/social/postime")
def social_postime(secret: str = ""):
    if not B2B_ADMIN_SECRET or (secret or "").strip() != B2B_ADMIN_SECRET:
        return HTMLResponse("<h3 style='font-family:sans-serif'>401 — Unauthorized. Shto ?secret=… të saktë.</h3>", status_code=401)
    d = _social_te_dhenat()
    postime = _social_postime(d)
    krerё = ""
    for pi, post in enumerate(postime):
        blloqe_html = ""
        for bi, (etiketa, tekst) in enumerate(post["blloqe"]):
            _id = f"t{pi}_{bi}"
            tekst_esc = _html.escape(tekst)
            blloqe_html += (f"<div class='blok'><div class='blok-krye'><span class='etik'>{_html.escape(etiketa)}</span>"
                            f"<button class='btn' onclick=\"kopjo('{_id}',this)\">📋 Kopjo</button></div>"
                            f"<textarea id='{_id}' readonly>{tekst_esc}</textarea></div>")
        krerё += (f"<div class='karte'><div class='karte-krye'><h2>{_html.escape(post['titull'])}</h2>"
                  f"<span class='sub'>{_html.escape(post.get('sub',''))}</span></div>{blloqe_html}</div>")
    if not postime:
        krerё = "<p class='bosh'>Sot s'ka mjaft të dhëna (goditje/pik/performancë). Provo pasi të mbarojnë ndeshjet ose të gjenerohen parashikimet.</p>"
    page = """<!DOCTYPE html><html lang="sq"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Postime Sociale — SOCCER1X2 PRO</title>
<style>
:root{color-scheme:dark}body{margin:0;background:#0d1117;color:#e6edf3;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}
h1{font-size:20px;margin:0 0 4px}.data{color:#8b949e;font-size:13px;margin-bottom:18px}
.karte{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:14px;margin-bottom:18px;max-width:780px}
.karte-krye{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.karte-krye h2{font-size:16px;margin:0;color:#ffd700}.sub{color:#8b949e;font-size:12px}
.blok{margin-bottom:12px}.blok-krye{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.etik{font-size:11px;font-weight:800;color:#58a6ff;letter-spacing:.4px}
.btn{background:#238636;color:#fff;border:none;padding:5px 12px;border-radius:6px;font-weight:800;font-size:12px;cursor:pointer}
.btn.ok{background:#1f6feb}textarea{width:100%;box-sizing:border-box;height:130px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:9px;font-size:12.5px;line-height:1.45;resize:vertical;font-family:inherit}
.bosh{color:#8b949e;max-width:780px}.udhez{max-width:780px;background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:12px;color:#8b949e;font-size:12.5px;line-height:1.6;margin-bottom:18px}
.udhez b{color:#e6edf3}
</style></head><body>
<h1>📣 Postime Sociale — SOCCER1X2 PRO</h1>
<div class="data">Gjeneruar për: __SOT__ · dëshmi nga: __DJE__</div>
<div class="udhez"><b>Si përdoret:</b> kliko <b>📋 Kopjo</b>, ngjit te Instagram/TikTok/Facebook. Për IG/TikTok, shto një pamje/video (rezultatet ose luanin). Hashtag-et trimoji nëse duket shumë. <b>Publiko:</b> Dëshminë e rezultateve në mëngjes, Pikun falas para ndeshjeve, Performancën 1-2 herë në javë. <b>Kujdes:</b> mbaje gjithmonë kornizën "analizë · 18+", kurrë "fitim i garantuar".</div>
__KRERE__
<script>
function kopjo(id,btn){var t=document.getElementById(id);t.select();t.setSelectionRange(0,99999);
try{navigator.clipboard.writeText(t.value);}catch(e){document.execCommand('copy');}
var o=btn.innerHTML;btn.innerHTML='✓ U kopjua';btn.classList.add('ok');setTimeout(function(){btn.innerHTML=o;btn.classList.remove('ok');},1400);}
</script></body></html>"""
    page = page.replace("__SOT__", d["sot"]).replace("__DJE__", d["dje"]).replace("__KRERE__", krerё)
    return HTMLResponse(page)

@app.get("/api/krahaso_predictions")
def krahaso_predictions(date: str = None, limit: int = 40):
    """Krahason parashikimet TONA vs Predictions te API-Football per nje date.
    API-Football perdor Poisson + statistika PA koeficiente -> sinjal i pavarur."""
    dt = date or _data_lokale(0)
    try:
        r = requests.get(
            SUPABASE_URL_PREDS + "?data=eq." + str(dt)
            + "&select=id,ekipi_1,ekipi_2,rezultati_sakt,training_data"
            + "&rezultati_sakt=not.is.null&limit=" + str(int(limit)),
            headers=SUPABASE_SERVICE_HEADERS, timeout=15)
        ndeshjet = r.json() if r.status_code == 200 else []
    except Exception as e:
        return {"sukses": False, "gabim": "supabase: " + str(e)}

    dakord = 0; total = 0; rezultatet = []
    for nd in ndeshjet:
        fid = nd.get("id")
        e1 = nd.get("ekipi_1") or ""; e2 = nd.get("ekipi_2") or ""
        yni_skor = (nd.get("rezultati_sakt") or "").replace(" ", "")
        td = nd.get("training_data") or {}
        try:
            g1, g2 = [int(x) for x in yni_skor.split("-")]
            _yn = "1" if g1 > g2 else ("2" if g2 > g1 else "X")
        except Exception:
            _yn = "?"
        af_adv = ""; af_pct = ""; af_ou = ""; _af = "?"
        if fid:
            try:
                pr = requests.get(
                    "https://v3.football.api-sports.io/predictions?fixture=" + str(fid),
                    headers=HEADERS, timeout=8)
                resp = pr.json().get("response", [])
                if resp:
                    pp = resp[0].get("predictions", {}) or {}
                    w = pp.get("winner") or {}
                    wname = w.get("name") or ""
                    af_adv = pp.get("advice") or ""
                    pc = pp.get("percent") or {}
                    af_pct = str(pc.get("home", "?")) + "/" + str(pc.get("draw", "?")) + "/" + str(pc.get("away", "?"))
                    af_ou = pp.get("under_over") or ""
                    if not wname:
                        _af = "X"
                    elif wname == e1:
                        _af = "1"
                    elif wname == e2:
                        _af = "2"
                    else:
                        _af = "X"
            except Exception:
                _af = "gab"
        pajt = (_yn == _af)
        if _af in ("1", "2", "X"):
            total += 1
            if pajt:
                dakord += 1
        _xg1 = td.get("xg_1"); _xg2 = td.get("xg_2")
        rezultatet.append({
            "ndeshja": e1 + " - " + e2,
            "yni_xg": (str(round(_xg1, 2)) + "/" + str(round(_xg2, 2))) if (_xg1 is not None and _xg2 is not None) else "",
            "yni_skor": yni_skor,
            "yni_fitues": _yn,
            "af_fitues": _af,
            "af_gjasat_H_D_A": af_pct,
            "af_over_under": af_ou,
            "af_keshilla": af_adv,
            "pajtohen": pajt
        })
    perq = round(100.0 * dakord / total, 1) if total else 0.0
    return {
        "sukses": True, "data": dt,
        "gjithsej_ndeshje": len(rezultatet),
        "krahasime_te_vlefshme": total,
        "fitues_qe_pajtohen": dakord,
        "perqindja_pajtimit": str(perq) + "%",
        "shpjegim": "af = API-Football (Poisson, pa koeficiente). Krahaso af_fitues me yni_fitues.",
        "krahasimi": rezultatet
    }
