from fastapi import FastAPI, BackgroundTasks, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
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
]

# Vlera mesatare (nga trajnimi) për features që s'i kemi live.
# Përdoren si imputation — kishin rëndësi të ulët, efekt minimal.
XGB_DEFAULTS = {
    "home_avg_yellow": 1.75, "away_avg_yellow": 1.75,
    "home_avg_red": 0.10, "away_avg_red": 0.10,
    "home_volatility": 1.47, "away_volatility": 1.47,
    "home_rest_days": 7.0, "away_rest_days": 7.0,
}

def _ngarko_modelet_xgb():
    """Ngarkon modelet XGBoost një herë në nisje. Fail-safe."""
    global XGB_MODEL_HOME, XGB_MODEL_AWAY, XGB_GATI
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
    except Exception as e:
        print(f"⚠️ XGBoost nuk u ngarkua ({e}) — fallback te formula.")
        XGB_GATI = False

_ngarko_modelet_xgb()

app = FastAPI(title="SOCCER1X2 PRO API - Expert System", description="Advanced Monte Carlo & Dynamic ELO Prediction Engine V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KREDENCIALET (nga env vars — Render → Environment)
API_KEY = os.environ.get("API_SPORTS_KEY", "")
HEADERS = {"x-apisports-key": API_KEY}

SUPABASE_BASE = os.environ.get(
    "SUPABASE_URL", "https://oqfhlyybwwkjbkvfpsxi.supabase.co"
).rstrip("/")

SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
# Service key për shkrime të privilegjuara (auth/admin/Cryptomus/Modulator):
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

SUPABASE_URL_PREDS = f"{SUPABASE_BASE}/rest/v1/predictions"
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

# ── SIGURIA: helpers për hashim + service headers + admin ──
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

SUPABASE_SERVICE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def _eshte_hash(s):
    # Formati ynë: pbkdf2$<iterations>$<salt_hex>$<hash_hex>
    return isinstance(s, str) and s.startswith("pbkdf2$")

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
        return {"sukses": False, "mesazhi": "ekziston"}
    emri_ndare = data.name.strip().split(" ", 1)
    emri    = emri_ndare[0] if len(emri_ndare) > 0 else "Client"
    mbiemri = emri_ndare[1] if len(emri_ndare) > 1 else ""
    user_payload = {
        "email": email_clean,
        "password": _hash_fjalekalimi(data.password),   # HASH, jo plaintext
        "emri": emri, "mbiemri": mbiemri,
        "portofoli": 20.0, "isVip": False, "vip_skadon_me": None,
        "auto_rinovim": False, "blerjet": []
    }
    res_insert = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_SERVICE_HEADERS, json=user_payload)
    if res_insert.status_code in [200, 201, 204]:
        u = dict(user_payload); u.pop("password", None)
        return {"sukses": True, "perdoruesi": u}
    return {"sukses": False, "mesazhi": f"Gabim Databaze: {res_insert.text}"}


@app.post("/api/login")
def login_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_SERVICE_HEADERS)
    if res.status_code != 200:
        return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    users = res.json()
    if not users:
        return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    u = users[0]
    ruajtur = u.get("password", "")
    if not _verifiko_fjalekalimi(data.password, ruajtur):
        return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}
    # MIGRIM: nëse ishte plaintext, hashoje tani (pa fërkim)
    if not _eshte_hash(ruajtur):
        try:
            requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}",
                           headers=SUPABASE_SERVICE_HEADERS,
                           json={"password": _hash_fjalekalimi(data.password)})
        except Exception:
            pass
    u.pop("password", None)
    return {"sukses": True, "perdoruesi": u}


@app.post("/api/update_user")
def perditeso_perdorues(user_data: dict):
    # I MBYLLUR: fushat monetare (isVip/portofoli/blerjet/vip_skadon_me) ndryshohen
    # VETËM nga endpoint-et server-autoritare (ppm/vip/cryptomus webhook).
    # Klienti lejohet të ndryshojë vetëm profilin jo-monetar.
    email = user_data.get("email", "").lower().strip()
    if not email:
        return {"sukses": False, "mesazhi": "email mungon"}
    LEJUARA = {"emri", "mbiemri", "auto_rinovim"}
    payload = {k: v for k, v in user_data.items() if k in LEJUARA}
    if payload:
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}",
                       headers=SUPABASE_SERVICE_HEADERS, json=payload)
    return {"sukses": True}


@app.get("/api/users")
def merr_perdorues_nga_db(email: str):
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
        return {"sukses": False, "mesazhi": "shuma e pavlefshme"}
    if not email or shuma == 0:
        return {"sukses": False, "mesazhi": "email ose shuma mungon"}
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli",
                       headers=SUPABASE_SERVICE_HEADERS)
    rows = res.json() if res.status_code == 200 else []
    if not rows:
        return {"sukses": False, "mesazhi": "perdoruesi s'u gjet"}
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
        return {"sukses": False, "mesazhi": "email mungon"}
    skadon = (datetime.utcnow() + timedelta(days=dite)).strftime("%Y-%m-%d")
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
PPM_TIER1 = 49.99   # koef < 5.0
PPM_TIER2 = 59.99   # 5.0 - 7.9
PPM_TIER3 = 99.99   # koef >= 8.0
CMIMI_DITORE = 10.0   # zhbllokon Skedinën + Kombinimin e Ditës

CRYPTOMUS_MERCHANT_ID = os.environ.get("CRYPTOMUS_MERCHANT_ID", "")
CRYPTOMUS_PAYMENT_KEY = os.environ.get("CRYPTOMUS_PAYMENT_KEY", "")
PUBLIC_API_URL  = os.environ.get("PUBLIC_API_URL", "https://soccer1x2-api.onrender.com").rstrip("/")
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://soccer1x2pro.com").rstrip("/")
SUPABASE_URL_POROSITE = f"{SUPABASE_BASE}/rest/v1/porosite"


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
def ppm_blej_me_kredite(payload: dict):
    email = payload.get("email", "").lower().strip()
    match_id = payload.get("match_id")
    if not email or not match_id:
        return {"sukses": False, "mesazhi": "Të dhëna mungojnë"}
    # Çmimi nga SERVERI (jo nga klienti) — bazuar te koeficienti
    pres = requests.get(
        f"{SUPABASE_URL_PREDS}?id=eq.{match_id}&select=id,ndeshja,rezultati_sakt,koef_rez_sakt",
        headers=SUPABASE_SERVICE_HEADERS)
    preds = pres.json() if pres.status_code == 200 else []
    if not preds:
        return {"sukses": False, "mesazhi": "Ndeshja s'u gjet"}
    nd = preds[0]
    cmimi = _cmimi_ppm(nd.get("koef_rez_sakt"))
    ures = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,blerjet",
                        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return {"sukses": False, "mesazhi": "Përdoruesi s'u gjet"}
    u = users[0]
    portofoli = float(u.get("portofoli", 0) or 0)
    blerjet = u.get("blerjet") or []
    if any(str(b.get("id")) == str(match_id) for b in blerjet):
        return {"sukses": True, "mesazhi": "Tashmë e blerë", "portofoli": round(portofoli, 2)}
    if portofoli < cmimi:
        return {"sukses": False, "mesazhi": "Kredite të pamjaftueshme",
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
def vip_blej_me_kredite(payload: dict):
    email = payload.get("email", "").lower().strip()
    if not email:
        return {"sukses": False, "mesazhi": "email mungon"}
    ures = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,vip_skadon_me",
                        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return {"sukses": False, "mesazhi": "Përdoruesi s'u gjet"}
    portofoli = float(users[0].get("portofoli", 0) or 0)
    if portofoli < CMIMI_VIP:
        return {"sukses": False, "mesazhi": "Kredite të pamjaftueshme",
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


@app.post("/api/cryptomus/create-invoice")
def crypto_krijo_fature(payload: dict):
    email = payload.get("email", "").lower().strip()
    tipi  = payload.get("tipi")   # "vip" | "topup" | "ppm"
    if not email or tipi not in ("vip", "topup", "ppm", "donate", "ditore"):
        return {"sukses": False, "mesazhi": "Të dhëna të pavlefshme"}

    match_id = payload.get("match_id")
    ndeshja = rezultati = koef = None

    if tipi == "vip":
        shuma = CMIMI_VIP
    elif tipi == "ditore":
        shuma = CMIMI_DITORE
    elif tipi in ("topup", "donate"):
        try:
            shuma = float(payload.get("shuma", 0))
        except Exception:
            shuma = 0.0
        if shuma <= 0:
            return {"sukses": False, "mesazhi": "Shuma e pavlefshme"}
    else:  # ppm — çmimi nga serveri
        pres = requests.get(
            f"{SUPABASE_URL_PREDS}?id=eq.{match_id}&select=ndeshja,rezultati_sakt,koef_rez_sakt",
            headers=SUPABASE_SERVICE_HEADERS)
        preds = pres.json() if pres.status_code == 200 else []
        if not preds:
            return {"sukses": False, "mesazhi": "Ndeshja s'u gjet"}
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
        return {"sukses": False, "mesazhi": "Përgjigje e papritur nga Cryptomus"}

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
    order_id = data.get("order_id")
    if not order_id:
        return {"state": 0}

    # GATE AUTORITATIV: pyet VETË Cryptomus (webhook i falsifikuar s'kalon dot)
    info = _crypto_info(order_id)
    status = info.get("payment_status") or data.get("status")
    if status not in ("paid", "paid_over"):
        return {"state": 0}

    pres = requests.get(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}&select=*",
                        headers=SUPABASE_SERVICE_HEADERS)
    pros = pres.json() if pres.status_code == 200 else []
    if not pros or pros[0].get("status") == "paid":
        return {"state": 0}
    po = pros[0]
    email = po.get("email"); tipi = po.get("tipi")

    ures = requests.get(
        f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,isVip,vip_skadon_me,blerjet",
        headers=SUPABASE_SERVICE_HEADERS)
    users = ures.json() if ures.status_code == 200 else []
    if not users:
        return {"state": 0}
    u = users[0]
    update = {}

    if tipi == "topup":
        try:
            shuma = float(po.get("amount", 0))
        except Exception:
            shuma = 0.0
        update["portofoli"] = round(float(u.get("portofoli", 0) or 0) + shuma, 2)
    elif tipi == "vip":
        baza = datetime.utcnow()
        if u.get("vip_skadon_me"):
            try:
                d = datetime.strptime(str(u["vip_skadon_me"])[:10], "%Y-%m-%d")
                if d > baza:
                    baza = d
            except Exception:
                pass
        update["isVip"] = True
        update["vip_skadon_me"] = (baza + timedelta(days=VIP_DITE)).strftime("%Y-%m-%d")
    elif tipi == "donate":
        pass  # donacion — s'ndryshon llogarinë
    elif tipi == "ditore":
        update["ditore_unlock_date"] = datetime.utcnow().strftime("%Y-%m-%d")
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
    requests.patch(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}",
                   headers=SUPABASE_SERVICE_HEADERS,
                   json={"status": "paid", "paguar": datetime.utcnow().isoformat()})
    return {"state": 0}


@app.get("/api/cryptomus/order-status")
def crypto_order_status(order_id: str):
    pres = requests.get(f"{SUPABASE_URL_POROSITE}?order_id=eq.{order_id}&select=status",
                        headers=SUPABASE_SERVICE_HEADERS)
    pros = pres.json() if pres.status_code == 200 else []
    if not pros:
        return {"status": "panjohur"}
    st = pros[0].get("status")
    if st != "paid":
        info = _crypto_info(order_id)
        if info.get("payment_status") in ("paid", "paid_over"):
            return {"status": "paid"}
    return {"status": st}


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


def _legs_per_match(p, market_set):
    tregjet = p.get("tregjet") or {}
    odds = p.get("odds_reale") or {}
    legs = []
    for m in market_set:
        if m not in tregjet:
            continue
        try:
            prob = float(tregjet[m])
        except Exception:
            continue
        if prob <= 0:
            continue
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
    if m in ("1", "X", "2", "1X", "X2", "12"):
        return "rezultat"
    if m.startswith("Over") or m.startswith("Under"):
        return "ou"
    if m in ("GG", "NG"):
        return "btts"
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
        legs_out.append({"ndeshja": m["ndeshja"], "pjeset": [zgjedhja["market"]],
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
    try:
        sot = datetime.utcnow().strftime("%Y-%m-%d")
        r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}&select=ditore_unlock_date",
                         headers=SUPABASE_SERVICE_HEADERS)
        u = r.json() if r.status_code == 200 else []
        return bool(u) and str(u[0].get("ditore_unlock_date") or "")[:10] == sot
    except Exception:
        return False


@app.post("/api/ditore/unlock")
def ditore_unlock_me_kredite(payload: dict):
    email = payload.get("email", "").lower().strip()
    if not email:
        return {"sukses": False, "mesazhi": "email mungon"}
    r = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}&select=portofoli,ditore_unlock_date",
                     headers=SUPABASE_SERVICE_HEADERS)
    u = r.json() if r.status_code == 200 else []
    if not u:
        return {"sukses": False, "mesazhi": "Përdoruesi s'u gjet"}
    sot = datetime.utcnow().strftime("%Y-%m-%d")
    portofoli = float(u[0].get("portofoli", 0) or 0)
    if str(u[0].get("ditore_unlock_date") or "")[:10] == sot:
        return {"sukses": True, "mesazhi": "Tashmë e zhbllokuar sot",
                "ditore_unlock_date": sot, "portofoli": round(portofoli, 2)}
    if portofoli < CMIMI_DITORE:
        return {"sukses": False, "mesazhi": "Kredite të pamjaftueshme",
                "kerkohet": CMIMI_DITORE, "portofoli": round(portofoli, 2)}
    portofoli_ri = round(portofoli - CMIMI_DITORE, 2)
    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_SERVICE_HEADERS,
                   json={"portofoli": portofoli_ri, "ditore_unlock_date": sot})
    return {"sukses": True, "portofoli": portofoli_ri, "ditore_unlock_date": sot}


@app.get("/api/ditore")
def skedina_dhe_kombinimi_ditore(email: str = ""):
    res = requests.get(
        f"{SUPABASE_URL_PREDS}?select=id,ndeshja,data,ora,statusi,best_bet,tregjet,odds_reale,dist_gola"
        f"&best_bet=not.is.null"
        f"&statusi=not.in.(FT,AET,PEN,AWD,WO,CANC,PST,ABD)"
        f"&order=id.desc&limit=300",
        headers=SUPABASE_SERVICE_HEADERS)
    preds = res.json() if res.status_code == 200 else []
    preds = [p for p in preds if p.get("best_bet")]

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

def merr_formen_reale(team_id: int, numri_ndeshjeve: int = 8) -> dict:
    """
    Merr ndeshjet e fundit të ekipit dhe llogarit:
    win_rate, xG mesatar, lodhjen e serisë — me të dhëna REALE.
    SHTUAR: home/away split (gola shtëpi vs jashtë veçmas).
    """
    koha_tani = time.time()
    if team_id in FORMA_CACHE:
        te_dhenat, koha_ruajtur = FORMA_CACHE[team_id]
        if koha_tani - koha_ruajtur < FORMA_CACHE_TTL:
            return te_dhenat

    try:
        res = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS,
            params={"team": team_id, "last": numri_ndeshjeve, "status": "FT"},
            timeout=5
        )
        ndeshjet = res.json().get("response", [])
    except:
        return _forma_boshe()

    if not ndeshjet:
        return _forma_boshe()

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
    FORMA_CACHE[team_id] = (rezultati, koha_tani)
    return rezultati

def _forma_boshe() -> dict:
    return {
        "win_rate": 0.40, "avg_gola_shenuar": 1.2, "avg_gola_prane": 1.2,
        "xg_shenuar": 1.25, "xg_prane": 1.20, "k_wins_rresht": 0,
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
    xg1_forma = (xg1_forma_raw * 0.85 + 0.25) * forma_1["lodhja_factor"]
    xg2_forma = (xg2_forma_raw * 0.85 + 0.25) * forma_2["lodhja_factor"]

    # Burimi 2: ELO (multiplikator i rritur 2.5 → 3.0)
    diff_elo = (elo_1 - elo_2) / 400.0
    p1_elo   = 1 / (1 + 10 ** (-diff_elo))
    p2_elo   = 1 - p1_elo
    xg1_elo  = p1_elo * 3.0
    xg2_elo  = p2_elo * 3.0

    # Burimi 3: Tregu (multiplikator i rritur 2.7 → 3.2)
    xg1_market = p1_real * 3.2
    xg2_market = p2_real * 3.2

    # Burimi 4: Baza e golave (mesatarja globale e futbollit ~1.35 gola/ekip)
    xg1_base = 1.35
    xg2_base = 1.35

    # Avantazhi shtëpiak (rritur pak)
    shtepie_bonus = 1.12
    jashte_minus  = 0.95

    xg_1_final = (W_FORMA * xg1_forma + W_ELO * xg1_elo + W_MARKET * xg1_market + W_BASE * xg1_base) * shtepie_bonus
    xg_2_final = (W_FORMA * xg2_forma + W_ELO * xg2_elo + W_MARKET * xg2_market + W_BASE * xg2_base) * jashte_minus

    # Kufijtë e rritur (3.50 → 4.20) që të lejojë rezultate me shumë gola
    xg_1_final = float(np.clip(xg_1_final, 0.35, 4.20))
    xg_2_final = float(np.clip(xg_2_final, 0.35, 4.20))

    return round(xg_1_final, 3), round(xg_2_final, 3)

# ==========================================
# MODULI 3.5: HYBRID — XGBOOST + FALLBACK
# ==========================================

def llogarit_xg_hybrid(
    forma_1: dict, forma_2: dict,
    p1_real: float, p2_real: float,
    k1: float, kx: float, k2: float,
    emri_liges: str,
    xg_math_1: float, xg_math_2: float,
) -> tuple:
    """
    HYBRID: kombinon XGBoost (nëse gati) me xG matematikore.
    - XGBoost jep golat bazë nga 26 features.
    - Kombinohet 55% XGBoost + 45% math (XGBoost peshë më të madhe).
    - Nëse XGBoost s'është gati → kthen vetëm math (fallback i plotë).
    Kthen: (xg_1, xg_2, burimi)
    """
    if not XGB_GATI:
        return xg_math_1, xg_math_2, "math"

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
        }
        vektori = np.array([[vlerat[f] for f in XGB_FEATURES]], dtype=float)

        xgb_h = float(XGB_MODEL_HOME.predict(vektori)[0])
        xgb_a = float(XGB_MODEL_AWAY.predict(vektori)[0])

        # Kombinim: 55% XGBoost + 45% math
        W_XGB = 0.55
        xg_1 = W_XGB * xgb_h + (1 - W_XGB) * xg_math_1
        xg_2 = W_XGB * xgb_a + (1 - W_XGB) * xg_math_2

        xg_1 = float(np.clip(xg_1, 0.30, 4.20))
        xg_2 = float(np.clip(xg_2, 0.30, 4.20))
        return round(xg_1, 3), round(xg_2, 3), "hybrid"

    except Exception as e:
        # Çdo gabim → fallback i sigurt te math
        print(f"⚠️ Hybrid dështoi ({e}) — fallback math.")
        return xg_math_1, xg_math_2, "math"


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
    return {k: v for k, v in out.items() if v is not None}


# Tregjet kandidate për "best bet" (rendit sipas prob. më të lartë).
# Për piket më interesante, hiq "12"/"1X"/"X2"/"Under 3.5"/"Over 1.5".
TREGJET_KANDIDATE = ["1", "X", "2", "Under 1.5", "Over 2.5",
                     "Under 2.5", "Over 3.5", "GG", "NG"]


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


def simulim_monte_carlo_v2(
    xg_1: float, xg_2: float,
    kaos_factor: float = 1.0,
    is_derbi: bool = False,
    iteracione: int = 50_000
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

    rng = np.random.default_rng()
    xg1_virtual = np.clip(rng.normal(xg_1, sigma_1, iteracione), 0.05, 6.0)
    xg2_virtual = np.clip(rng.normal(xg_2, sigma_2, iteracione), 0.05, 6.0)

    gola_1 = rng.poisson(xg1_virtual)
    gola_2 = rng.poisson(xg2_virtual)

    prob_1x2 = {
        "p1": round(float(np.sum(gola_1 > gola_2)  / iteracione), 4),
        "px": round(float(np.sum(gola_1 == gola_2) / iteracione), 4),
        "p2": round(float(np.sum(gola_1 < gola_2)  / iteracione), 4),
    }

    rezultatet_unique, counts = np.unique(
        np.stack([gola_1, gola_2], axis=1), axis=0, return_counts=True
    )

    # Top 15 rezultatet më të shpeshta
    top_idx = np.argsort(counts)[::-1][:15]
    rezultatet_freq = {
        f"{rezultatet_unique[i][0]}-{rezultatet_unique[i][1]}": int(counts[i])
        for i in top_idx
    }

    # ── ZGJEDHJA E REZULTATIT (e korrigjuar kundër nënvlerësimit) ──
    # Problem i njohur: modusi i Poisson jep gjithmonë pak gola.
    # Zgjidhje: ndër top-5 rezultatet, zgjedh atë që është më afër
    # totalit të pritur (xg_1 + xg_2), jo thjesht më të shpeshtin.
    total_pritur = xg_1 + xg_2

    top5_idx = np.argsort(counts)[::-1][:5]
    kandidatet = []
    for i in top5_idx:
        g1c = int(rezultatet_unique[i][0])
        g2c = int(rezultatet_unique[i][1])
        freq = int(counts[i])
        total_c = g1c + g2c
        # Score: kombinim i frekuencës dhe afërsisë me totalin e pritur
        diff_total = abs(total_c - total_pritur)
        score = freq * (1.0 / (1.0 + diff_total * 0.5))
        kandidatet.append((g1c, g2c, freq, score))

    # Zgjedh kandidatin me score më të lartë
    kandidatet.sort(key=lambda x: x[3], reverse=True)
    rez_g1, rez_g2, freq_zgjedhur, _ = kandidatet[0]
    rez_str  = f"{rez_g1}-{rez_g2}"
    prob_max = freq_zgjedhur / iteracione

    # ── TREGJET: probabiliteti i çdo tregu nga shpërndarja MC ──
    total = gola_1 + gola_2
    def _pf(mask):
        return round(float(np.sum(mask)) / iteracione, 4)
    tregjet = {
        "1": prob_1x2["p1"], "X": prob_1x2["px"], "2": prob_1x2["p2"],
        "1X": round(prob_1x2["p1"] + prob_1x2["px"], 4),
        "X2": round(prob_1x2["px"] + prob_1x2["p2"], 4),
        "12": round(prob_1x2["p1"] + prob_1x2["p2"], 4),
        "Over 1.5": _pf(total >= 2), "Under 1.5": _pf(total <= 1),
        "Over 2.5": _pf(total >= 3), "Under 2.5": _pf(total <= 2),
        "Over 3.5": _pf(total >= 4), "Under 3.5": _pf(total <= 3),
        "GG": _pf((gola_1 > 0) & (gola_2 > 0)),
        "NG": _pf((gola_1 == 0) | (gola_2 == 0)),
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

def analizo_ndeshjen_premium_master(
    id_ndeshja, ekipi_1, ekipi_2,
    ekipi_1_id, ekipi_2_id,
    k1_str, kx_str, k2_str,
    emri_liges, standings,
    dna_1=None, dna_2=None
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

    # ── FORMA REALE (me cache) ──
    forma_1 = merr_formen_reale(ekipi_1_id)
    forma_2 = merr_formen_reale(ekipi_2_id)

    # ── XG TË AVANCUARA ──
    kaosi_liges = apliko_kaosin_e_liges(emri_liges, vol_1, vol_2)
    is_derbi    = abs(elo_1 * desp_1 - elo_2 * desp_2) <= 30

    xg_1, xg_2 = llogarit_xg_te_perparuara(
        forma_1, forma_2,
        elo_1 * desp_1, elo_2 * desp_2,
        p1_real, p2_real
    )

    # ── HYBRID: kombino me XGBoost (nëse gati; ndryshe mban math) ──
    xg_1, xg_2, burimi_xg = llogarit_xg_hybrid(
        forma_1, forma_2, p1_real, p2_real,
        k1, kx, k2, emri_liges,
        xg_1, xg_2
    )

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

    # Kap brenda kufijve pas modifikimeve
    xg_1 = float(np.clip(xg_1, 0.30, 3.50))
    xg_2 = float(np.clip(xg_2, 0.30, 3.50))

    # ── MONTE CARLO V2 (numpy, 50k) ──
    rez_sakt, prob_rez_sakt, rezultatet_freq, prob_1x2_mc, tregjet_mc = simulim_monte_carlo_v2(
        xg_1, xg_2, kaosi_liges, is_derbi, iteracione=50_000
    )

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

    koef_rez_sakt = min(40.0, (1 / prob_rez_sakt) * 0.85) if prob_rez_sakt > 0 else 10.0

    # ── BEST BET: tregu me probabilitetin më të lartë ──
    _kand = [t for t in TREGJET_KANDIDATE if t in tregjet_mc]
    _best_t = max(_kand, key=lambda t: tregjet_mc[t]) if _kand else "1X"
    _best_p = float(tregjet_mc.get(_best_t, 0))
    best_bet = {"tregu": _best_t, "prob": round(_best_p, 4),
                "koef": round(1.0 / _best_p, 2) if _best_p > 0 else None}

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
        "liga_emri", "parashikimi_origjinal_ai"
    }

    for nd in ndeshjet_premium:
        # Ndërto payload vetëm me kolonat valide
        pako = {k: v for k, v in nd.items() if k in KOLONAT_VALIDE}

        # Sigurohu parashikimi_origjinal_ai ekziston
        if "parashikimi_origjinal_ai" not in pako:
            pako["parashikimi_origjinal_ai"] = pako.get("rezultati_sakt", "")

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
        res = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,statusi&statusi=not.in.(FT,AET,PEN,AWD,WO)",
            headers=SUPABASE_SERVICE_HEADERS, timeout=8
        )
        if res.status_code != 200:
            return
        ndeshjet_pa_mbaruar = res.json()
        if not ndeshjet_pa_mbaruar:
            return

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
                    rezultati_str = f"{gola_h} - {gola_a}"
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
    except:
        pass


@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    koha_tani   = time.time()

    # ── AUTO-REFRESH PPM TË PËRFUNDUARA (në sfond, pa bllokuar user) ──
    background_tasks.add_task(task_perditeso_ppm_te_perfunduara)

    # Cache 2 minuta (e ulim që përditësimet të vijnë më shpejt)
    if data_target in SKEDINA_CACHE and (koha_tani - SKEDINA_LAST_UPDATE.get(data_target, 0) < 120):
        return {"mesazhi": "Sukses", "skedina_grupuar": SKEDINA_CACHE[data_target]}

    try:
        response   = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS, params={"date": data_target}, timeout=10
        )
        te_dhenat = response.json()
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

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
                            dna_1=dna_1, dna_2=dna_2
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
                ndeshja["analiza_custom"] = None
            lista_e_te_gjithave.append(ndeshja)

        # Ruaj vetëm 3 PPM në DB (pa manipulim)
        if ndeshjet_premium_per_historik:
            background_tasks.add_task(task_ruaj_skedinen_ne_db, ndeshjet_premium_per_historik)

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

        SKEDINA_CACHE[data_target]       = rezultati_perfundimtar
        SKEDINA_LAST_UPDATE[data_target] = koha_tani

        return {"mesazhi": "Sukses", "skedina_grupuar": rezultati_perfundimtar}

    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

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

@app.get("/api/refresh_results")
def perditeso_rezultatet_perfunduara():
    """
    Lexon ndeshjet PPM të paplotësuara dhe i përditëson nga API-Sports.
    Konfigurim UptimeRobot:
      URL: https://soccer1x2-api.onrender.com/api/refresh_results
      Interval: 30 minuta (ose 60 min nëse ke API limit)
    """
    try:
        # Merr të gjitha ndeshjet që nuk kanë mbaruar
        res = requests.get(
            f"{SUPABASE_URL_PREDS}?select=id,ndeshja,statusi&statusi=not.in.(FT,AET,PEN,AWD,WO)",
            headers=SUPABASE_SERVICE_HEADERS,
            timeout=10
        )
        if res.status_code != 200:
            return {"sukses": False, "mesazhi": f"DB error: {res.status_code}"}

        ndeshjet_pa_mbaruar = res.json()
        if not ndeshjet_pa_mbaruar:
            return {"sukses": True, "perditesuara": 0, "mesazhi": "Të gjitha ndeshjet janë të përditësuara."}

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
                    rezultati_str = f"{gola_h} - {gola_a}"
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
        response   = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=HEADERS, params={"live": "all"}, timeout=10
        )
        te_dhenat = response.json()

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
                    "rezultati":  f"{gola_1} - {gola_2}",
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
            headers=HEADERS, params={"date": dje}, timeout=15
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
                headers=HEADERS, params={"date": data_target}, timeout=10
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
                        params={"date": data_target, "bookmaker": bookmaker_id, "page": page},
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
                            mw = next((b for b in bets if b["id"] == 1), None)
                            if mw:
                                v = mw["values"]
                                k1 = next((x["odd"] for x in v if x["value"] == "Home"), None)
                                kx = next((x["odd"] for x in v if x["value"] == "Draw"), None)
                                k2 = next((x["odd"] for x in v if x["value"] == "Away"), None)
                                if k1 and kx and k2:
                                    odds_dite[fix_id] = {"1": k1, "X": kx, "2": k2}
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
                    k1, kx, k2, emri_liges, [], dna_1=dna_1, dna_2=dna_2
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
