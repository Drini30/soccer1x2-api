from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
import random
import math
import time
import numpy as np

app = FastAPI(title="SOCCER1X2 PRO API - Expert System", description="Advanced Monte Carlo & Dynamic ELO Prediction Engine V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KREDENCIALET
API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xZmhseXlid3dramJrdmZwc3hpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMDU0NjksImV4cCI6MjA5NjU4MTQ2OX0.H1YFz3z9Ew3WofYbbvarP4V5rm99UjkY2mm1p2w4MBQ"
SUPABASE_URL_PREDS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"
SUPABASE_URL_USERS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/users"
SUPABASE_URL_DNA   = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/team_dna_cache"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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

@app.post("/api/register")
def regjistro_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_HEADERS)
    if res.status_code == 200 and len(res.json()) > 0:
        return {"sukses": False, "mesazhi": "ekziston"}
    emri_ndare = data.name.strip().split(" ", 1)
    emri    = emri_ndare[0] if len(emri_ndare) > 0 else "Client"
    mbiemri = emri_ndare[1] if len(emri_ndare) > 1 else ""
    user_payload = {
        "email": email_clean, "password": data.password, "emri": emri, "mbiemri": mbiemri,
        "portofoli": 20.0, "isVip": False, "vip_skadon_me": None,
        "auto_rinovim": False, "blerjet": []
    }
    res_insert = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_HEADERS, json=user_payload)
    if res_insert.status_code in [200, 201, 204]:
        return {"sukses": True, "perdoruesi": user_payload}
    return {"sukses": False, "mesazhi": f"Gabim Databaze: {res_insert.text}"}

@app.post("/api/login")
def login_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(
        f"{SUPABASE_URL_USERS}?email=eq.{email_clean}&password=eq.{data.password}",
        headers=SUPABASE_HEADERS
    )
    if res.status_code == 200:
        users = res.json()
        if len(users) > 0:
            return {"sukses": True, "perdoruesi": users[0]}
    return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}

@app.post("/api/update_user")
def perditeso_perdorues(user_data: dict):
    email = user_data.get("email", "").lower().strip()
    if email:
        is_vip_status = user_data.get("isVip", False)
        if "isvip" in user_data:
            is_vip_status = user_data["isvip"]
        update_payload = {
            "portofoli": user_data.get("portofoli", 0.0),
            "isVip": is_vip_status,
            "blerjet": user_data.get("blerjet", [])
        }
        if "vip_skadon_me" in user_data:
            update_payload["vip_skadon_me"] = user_data["vip_skadon_me"]
        if "auto_rinovim" in user_data:
            update_payload["auto_rinovim"] = user_data["auto_rinovim"]
        requests.patch(
            f"{SUPABASE_URL_USERS}?email=eq.{email}",
            headers=SUPABASE_HEADERS, json=update_payload
        )
    return {"sukses": True}

@app.get("/api/users")
def merr_perdorues_nga_db(email: str):
    try:
        res = requests.get(
            f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}",
            headers=SUPABASE_HEADERS
        )
        if res.status_code == 200:
            return res.json()
        return []
    except:
        return []

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
            headers=SUPABASE_HEADERS, timeout=2
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

def merr_formen_reale(team_id: int, numri_ndeshjeve: int = 5) -> dict:
    """
    Merr 5 ndeshjet e fundit të ekipit dhe llogarit:
    win_rate, xG mesatar, lodhjen e serisë — me të dhëna REALE.
    Zëvendëson: k_wins_sim = random.randint(0, 4)
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

    for n in ndeshjet:
        eshte_shtepie = n["teams"]["home"]["id"] == team_id
        g_ekip = n["goals"]["home"] if eshte_shtepie else n["goals"]["away"]
        g_kund = n["goals"]["away"] if eshte_shtepie else n["goals"]["home"]
        if g_ekip is None or g_kund is None:
            continue
        gola_shenuar += g_ekip
        gola_prane   += g_kund
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
    }
    FORMA_CACHE[team_id] = (rezultati, koha_tani)
    return rezultati

def _forma_boshe() -> dict:
    return {
        "win_rate": 0.40, "avg_gola_shenuar": 1.2, "avg_gola_prane": 1.2,
        "xg_shenuar": 1.25, "xg_prane": 1.20, "k_wins_rresht": 0,
        "lodhja_factor": 1.0, "piket_forma": 0.0, "total_ndeshje": 0,
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
    W_FORMA   = 0.35
    W_ELO     = 0.30
    W_MARKET  = 0.25
    W_SHTEPIE = 0.10

    # Burimi 1: Forma
    xg1_forma = forma_1["xg_shenuar"] * forma_1["lodhja_factor"]
    xg2_forma = forma_2["xg_shenuar"] * forma_2["lodhja_factor"]

    # Burimi 2: ELO
    diff_elo = (elo_1 - elo_2) / 400.0
    p1_elo   = 1 / (1 + 10 ** (-diff_elo))
    p2_elo   = 1 - p1_elo
    xg1_elo  = p1_elo * 2.5
    xg2_elo  = p2_elo * 2.5

    # Burimi 3: Tregu
    xg1_market = p1_real * 2.7
    xg2_market = p2_real * 2.7

    # Burimi 4: Avantazhi shtëpiak
    shtepie_bonus = 1.08
    jashte_minus  = 0.93

    xg_1_final = (W_FORMA * xg1_forma + W_ELO * xg1_elo + W_MARKET * xg1_market) * shtepie_bonus
    xg_2_final = (W_FORMA * xg2_forma + W_ELO * xg2_elo + W_MARKET * xg2_market) * jashte_minus

    xg_1_final = float(np.clip(xg_1_final, 0.30, 3.50))
    xg_2_final = float(np.clip(xg_2_final, 0.30, 3.50))

    return round(xg_1_final, 3), round(xg_2_final, 3)

# ==========================================
# MODULI 4 (V2): MONTE CARLO ME NUMPY
# ==========================================

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
    idx_max    = np.argmax(counts)
    rez_max    = rezultatet_unique[idx_max]
    rez_str    = f"{rez_max[0]}-{rez_max[1]}"
    prob_max   = float(counts[idx_max]) / iteracione

    top_idx = np.argsort(counts)[::-1][:15]
    rezultatet_freq = {
        f"{rezultatet_unique[i][0]}-{rezultatet_unique[i][1]}": int(counts[i])
        for i in top_idx
    }

    return rez_str, round(prob_max, 4), rezultatet_freq, prob_1x2

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
    rez_sakt, prob_rez_sakt, rezultatet_freq, prob_1x2_mc = simulim_monte_carlo_v2(
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

    # ── VALUE BET (nga probabilitetet MC) ──
    p1_mc = prob_1x2_mc["p1"]
    p2_mc = prob_1x2_mc["p2"]
    vb_1  = detect_value_bet(p1_mc, k1)
    vb_2  = detect_value_bet(p2_mc, k2)
    vb_text = (
        f"<br><b style='color:#00ff00;'>💎 Value Bet:</b> Fiton 1 (Vlera: {vb_1}%)" if vb_1
        else f"<br><b style='color:#00ff00;'>💎 Value Bet:</b> Fiton 2 (Vlera: {vb_2}%)" if vb_2
        else ""
    )

    # ── BLLOF DETECTION (i zgjeruar) ──
    eshte_bllof = (
        (k1 < 1.55 and p2_mc > 0.28) or
        (k2 < 1.55 and p1_mc > 0.28)
    )
    ht_ft_text = "<br><b style='color:#ff4500;'>🔥 Ekskluzive:</b> Sugjerohet Përmbysje!" if eshte_bllof else ""

    # ── ANALIZA TEKSTUALE ──
    win1_pct = int(forma_1["win_rate"] * 100)
    win2_pct = int(forma_2["win_rate"] * 100)

    if eshte_bllof:
        anal_dict = {"sq": f"⚠️ <b>Risk (Kurth i Tregut):</b> Analiza Monte Carlo (50k sim.) tregon anomali. <br><b style='color:#f2cc60;'>Sugjerim:</b> Surprizë kundër favoritit.{ht_ft_text}{vb_text}"}
    elif g1 == g2:
        anal_dict = {"sq": f"Përplasje ekuilibri (xG: {xg_1:.1f} vs {xg_2:.1f}). <br><b style='color:#f2cc60;'>Sugjerim:</b> Të dyja shënojnë (GG) ose Barazim.{ht_ft_text}{vb_text}"}
    elif g1 > g2:
        if (g1 + g2) >= 3:
            anal_dict = {"sq": f"<b>{ekipi_1}</b> dominon (ELO: {int(elo_1)}, Forma: {win1_pct}%). <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Mbi 2.5 gola.{ht_ft_text}{vb_text}"}
        else:
            anal_dict = {"sq": f"<b>{ekipi_1}</b> kontrollon taktikisht (Forma: {win1_pct}%, xG: {xg_1:.1f}).<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Nën 3.5 gola.{ht_ft_text}{vb_text}"}
    else:
        if (g1 + g2) >= 3:
            anal_dict = {"sq": f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë (Forma: {win2_pct}%, xG: {xg_2:.1f}).<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_2} ose Mbi 2.5 gola.{ht_ft_text}{vb_text}"}
        else:
            anal_dict = {"sq": f"Ndeshje ku <b>{ekipi_2}</b> menaxhon lojën (xG: {xg_2:.1f} vs {xg_1:.1f}).<br><b style='color:#f2cc60;'>Sugjerim:</b> X2 ose Nën 2.5 gola.{ht_ft_text}{vb_text}"}

    koef_rez_sakt = min(40.0, (1 / prob_rez_sakt) * 0.85) if prob_rez_sakt > 0 else 10.0

    extradb = {
        "is_bllof":     eshte_bllof,
        "koef_plote":   f"1:{k1_str} | X:{kx_str} | 2:{k2_str}",
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
    HEQUR: manipulimi i rezultatit pas ndeshjes (win-rate patching).
    Rezultati ruhet ashtu siç u parashikua — transparencë e plotë.
    """
    headers = SUPABASE_HEADERS.copy()
    headers["Prefer"] = "resolution=merge-duplicates"

    for nd in ndeshjet_premium:
        pako = nd.copy()
        if "analiza_custom" in pako:
            del pako["analiza_custom"]
        if "liga_emri" in pako:
            del pako["liga_emri"]
        if "parashikimi_origjinal_ai" not in pako:
            pako["parashikimi_origjinal_ai"] = pako.get("rezultati_sakt", "")

        try:
            requests.post(SUPABASE_URL_PREDS, headers=headers, json=pako, timeout=5)
        except:
            pass

# ==========================================
# ENDPOINTI KRYESOR - SKEDINA & PPM
# ==========================================

SKEDINA_CACHE       = {}
SKEDINA_LAST_UPDATE = {}

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    koha_tani   = time.time()

    if data_target in SKEDINA_CACHE and (koha_tani - SKEDINA_LAST_UPDATE.get(data_target, 0) < 600):
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
                            mw   = next(
                                (b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"),
                                None
                            )
                            if mw:
                                v = mw["values"]
                                k1 = next((x["odd"] for x in v if x["value"] == "Home"), None)
                                kx = next((x["odd"] for x in v if x["value"] == "Draw"), None)
                                k2 = next((x["odd"] for x in v if x["value"] == "Away"), None)
                                if k1 and kx and k2:
                                    bet365_odds[fix_id] = {"1": k1, "X": kx, "2": k2}
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
# ENDPOINTI LIVE
# ==========================================

@app.get("/api/live")
def merr_ndeshjet_live():
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
            headers=SUPABASE_HEADERS,
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
            headers=SUPABASE_HEADERS, timeout=5
        )
        ekziston = res_check.status_code == 200 and len(res_check.json()) > 0

        if ekziston:
            res = requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
                headers=SUPABASE_HEADERS, json=dna_e_re, timeout=5
            )
            veprimi = "UPDATED"
        else:
            res = requests.post(
                SUPABASE_URL_DNA,
                headers=SUPABASE_HEADERS, json=dna_e_re, timeout=5
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
                    headers=SUPABASE_HEADERS, timeout=3
                )
                ekziston = res_check.status_code == 200 and len(res_check.json()) > 0

                if ekziston:
                    requests.patch(
                        f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
                        headers=SUPABASE_HEADERS, json=dna, timeout=3
                    )
                else:
                    requests.post(
                        SUPABASE_URL_DNA,
                        headers=SUPABASE_HEADERS, json=dna, timeout=3
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
                        headers=SUPABASE_HEADERS,
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
                        headers=SUPABASE_HEADERS,
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
                headers=SUPABASE_HEADERS,
                json={"historical_power": round(new_elo_home, 1)}
            )
            ekipe_te_perditesuara += 1
        if dna_away:
            requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{away_id}",
                headers=SUPABASE_HEADERS,
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
    return {"mesazhi": "Në pritje", "is_ready": False}

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

        b13 = get_bet(13)
        if b13:
            tregjet.append({"tregu_id": "ht_result", "opsionet": [
                {"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]}
                for v in b13["values"]
            ]})
        b12 = get_bet(12)
        if b12:
            tregjet.append({"tregu_id": "double_chance", "opsionet": [
                {"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]}
                for v in b12["values"]
            ]})
        b5 = get_bet(5)
        if b5:
            tregjet.append({"tregu_id": "goals_35_65", "opsionet": [
                {"emer": f"Mbi {g}" if "Over" in v["value"] else f"Nën {g}", "koef": v["odd"]}
                for v in b5["values"] for g in ["2.5"] if g in v["value"]
            ]})
        b8 = get_bet(8)
        if b8:
            tregjet.append({"tregu_id": "btts", "opsionet": [
                {"emer": "Po (GG)" if v["value"]=="Yes" else "Jo (NG)", "koef": v["odd"]}
                for v in b8["values"]
            ]})
        b10 = get_bet(10)
        if b10:
            tregjet.append({"tregu_id": "correct_score", "opsionet": [
                {"emer": v["value"].replace(":", "-"), "koef": v["odd"]}
                for v in b10["values"]
                if v["value"] in ["1:0","2:0","2:1","0:0","1:1","0:1","0:2","1:2"]
            ]})
        return {"mesazhi": "Sukses", "koeficientet": tregjet}
    except:
        return {"mesazhi": "Gabim", "koeficientet": []}

@app.post("/api/lemonsqueezy/webhook")
async def lemonsqueezy_webhook(request: Request):
    try:
        payload = await request.json()
        meta    = payload.get("meta", {})

        if meta.get("event_name") == "order_created":
            attributes  = payload.get("data", {}).get("attributes", {})
            custom_data = attributes.get("custom_data") or {}

            email_raw = custom_data.get("user_email") or attributes.get("user_email")
            if not email_raw:
                return {"status": "injoruar"}

            email       = email_raw.lower().strip()
            blerja_type = custom_data.get("type", "ppm")
            user_res    = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_HEADERS)

            if user_res.status_code == 200 and len(user_res.json()) > 0:
                user        = user_res.json()[0]
                update_data = {}

                if blerja_type == "vip":
                    update_data["isVip"]         = True
                    update_data["vip_skadon_me"] = (datetime.utcnow() + timedelta(days=30)).isoformat()
                    update_data["auto_rinovim"]  = True

                elif blerja_type == "topup":
                    shuma                  = float(custom_data.get("amount", attributes.get("total", 0) / 100.0))
                    update_data["portofoli"] = float(user.get("portofoli", 0.0)) + shuma

                elif blerja_type == "ppm":
                    blerja_e_re = {
                        "id":       str(custom_data.get("match_id", "N/A")),
                        "ndeshja":  custom_data.get("ndeshja", "Ndeshje PPM"),
                        "rezultati": custom_data.get("rezultati", "N/A"),
                        "koef":     str(custom_data.get("koef", "N/A")),
                        "cmimi":    float(custom_data.get("cmimi", attributes.get("total", 0) / 100.0)),
                    }
                    blerjet = user.get("blerjet", [])
                    if not any(b["id"] == blerja_e_re["id"] for b in blerjet):
                        blerjet.append(blerja_e_re)
                        update_data["blerjet"] = blerjet

                if update_data:
                    requests.patch(
                        f"{SUPABASE_URL_USERS}?email=eq.{email}",
                        headers=SUPABASE_HEADERS, json=update_data
                    )

        return {"status": "sukses"}
    except Exception as e:
        return {"status": "gabim", "detaje": str(e)}
