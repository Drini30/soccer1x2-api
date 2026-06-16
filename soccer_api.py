from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
import random
import math
import time

app = FastAPI(title="SOCCER1X2 PRO API - Expert System", description="Advanced Monte Carlo & Elo Rating Prediction Engine")

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
SUPABASE_URL_DNA = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/team_dna_cache"

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
            if parts[0].lower() in emri_liges.lower() and parts[1].lower() in emri_liges.lower(): return True
        else:
            if vip.lower() in emri_liges.lower(): return True
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
    if res.status_code == 200 and len(res.json()) > 0: return {"sukses": False, "mesazhi": "ekziston"}
    emri_ndare = data.name.strip().split(" ", 1)
    emri = emri_ndare[0] if len(emri_ndare) > 0 else "Client"
    mbiemri = emri_ndare[1] if len(emri_ndare) > 1 else ""
    user_payload = { "email": email_clean, "password": data.password, "emri": emri, "mbiemri": mbiemri, "portofoli": 20.0, "isVip": False, "vip_skadon_me": None, "auto_rinovim": False, "blerjet": [] }
    res_insert = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_HEADERS, json=user_payload)
    if res_insert.status_code in [200, 201, 204]: return {"sukses": True, "perdoruesi": user_payload}
    else: return {"sukses": False, "mesazhi": f"Gabim Databaze: {res_insert.text}"}

@app.post("/api/login")
def login_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}&password=eq.{data.password}", headers=SUPABASE_HEADERS)
    if res.status_code == 200:
        users = res.json()
        if len(users) > 0: return {"sukses": True, "perdoruesi": users[0]}
    return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}

@app.post("/api/update_user")
def perditeso_perdorues(user_data: dict):
    email = user_data.get("email", "").lower().strip()
    if email:
        is_vip_status = user_data.get("isVip", False)
        if "isvip" in user_data: is_vip_status = user_data["isvip"]
        update_payload = { "portofoli": user_data.get("portofoli", 0.0), "isVip": is_vip_status, "blerjet": user_data.get("blerjet", []) }
        if "vip_skadon_me" in user_data: update_payload["vip_skadon_me"] = user_data["vip_skadon_me"]
        if "auto_rinovim" in user_data: update_payload["auto_rinovim"] = user_data["auto_rinovim"]
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_HEADERS, json=update_payload)
    return {"sukses": True}

@app.get("/api/users")
def merr_perdorues_nga_db(email: str):
    try:
        res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email.lower().strip()}", headers=SUPABASE_HEADERS)
        if res.status_code == 200: return res.json()
        return []
    except: return []

# ==========================================
# MODULI 1: ADN-ja HISTORIKE & ELO (1-1000)
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
        if emri.lower() in ekipi.lower(): return elo
    return 600

def merr_dna_nga_db(team_id):
    try:
        res = requests.get(f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}", headers=SUPABASE_HEADERS, timeout=2)
        if res.status_code == 200 and len(res.json()) > 0: return res.json()[0]
    except: pass
    return None

# ==========================================
# MODULI 2: DINAMIKA E SË TASHMES (Multiplikatorët)
# ==========================================
def llogarit_lodhjen_e_series(k_wins, prob_baze_fitore):
    alpha = 0.08
    f_s = 1 - math.pow((1 - alpha), k_wins)
    prob_re_fitore = prob_baze_fitore * (1 - f_s)
    diff = prob_baze_fitore - prob_re_fitore
    return prob_re_fitore, diff * 0.70, diff * 0.30

def llogarit_desperation_index(ekipi_id, standings):
    if not standings: return 1.0
    try:
        for r in standings:
            if r.get("team", {}).get("id") == ekipi_id:
                pozicioni = r.get("rank", 10)
                total_ekipe = len(standings)
                if pozicioni >= total_ekipe - 3 or pozicioni <= 3:
                    return 1.15
    except: pass
    return 1.0

def apliko_kaosin_e_liges(emri_liges):
    liga_lower = emri_liges.lower()
    if any(x in liga_lower for x in ["championship", "segunda", "ligue 2", "serie b", "superliga"]): return 1.25
    elif any(x in liga_lower for x in ["premier", "champions", "world cup", "la liga"]): return 1.05 
    return 1.10

# ==========================================
# MODULI 3: SIMULIMI MONTE CARLO (Mbetet 10,000 Iteracione)
# ==========================================
def simulim_monte_carlo(xg_1, xg_2, kaos_factor, is_derbi):
    iteracione = 10000 # E lënë fiks siç e kërkove për saktësi maksimale
    rezultatet_freq = {}
    
    if is_derbi:
        kaos_factor *= 1.20 
        
    def poisson_gola(lmbda):
        L = math.exp(-lmbda)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= random.uniform(0, 1)
        return k - 1

    for _ in range(iteracione):
        xg1_virtual = max(0.1, random.gauss(xg_1, xg_1 * 0.2 * kaos_factor))
        xg2_virtual = max(0.1, random.gauss(xg_2, xg_2 * 0.2 * kaos_factor))
        
        gola_1 = poisson_gola(xg1_virtual)
        gola_2 = poisson_gola(xg2_virtual)
        
        if gola_1 == 0 and gola_2 == 0 and (xg_1 + xg_2 > 2.5):
            if random.random() > 0.5: gola_1 += 1
            else: gola_2 += 1
            
        rez = f"{gola_1}-{gola_2}"
        if rez in rezultatet_freq: rezultatet_freq[rez] += 1
        else: rezultatet_freq[rez] = 1

    rez_max = max(rezultatet_freq, key=rezultatet_freq.get)
    prob_max = rezultatet_freq[rez_max] / iteracione
    
    return rez_max, prob_max, rezultatet_freq

def analizo_ndeshjen_premium_master(id_ndeshja, ekipi_1, ekipi_2, ekipi_1_id, ekipi_2_id, k1_str, kx_str, k2_str, emri_liges, standings):
    try: k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)
    except: k1, kx, k2 = 2.60, 3.10, 2.60 

    prob_1, prob_x, prob_2 = 1/k1, 1/kx, 1/k2
    marzhi = prob_1 + prob_x + prob_2 
    p1_real, px_real, p2_real = prob_1/marzhi, prob_x/marzhi, prob_2/marzhi

    dna_1 = merr_dna_nga_db(ekipi_1_id)
    dna_2 = merr_dna_nga_db(ekipi_2_id)

    elo_1 = dna_1.get("historical_power", merr_elo_baze(ekipi_1)) if dna_1 else merr_elo_baze(ekipi_1)
    elo_2 = dna_2.get("historical_power", merr_elo_baze(ekipi_2)) if dna_2 else merr_elo_baze(ekipi_2)

    desp_1 = llogarit_desperation_index(ekipi_1_id, standings)
    desp_2 = llogarit_desperation_index(ekipi_2_id, standings)
    kaosi_liges = apliko_kaosin_e_liges(emri_liges)
    is_derbi = abs(elo_1 - elo_2) <= 30

    k_wins_sim = random.randint(0, 4) 
    p1_adj, px_add1, p2_add1 = llogarit_lodhjen_e_series(k_wins_sim, p1_real)
    p2_adj, px_add2, p1_add2 = llogarit_lodhjen_e_series(random.randint(0, 2), p2_real)
    
    diferenca_elo = (elo_1 * desp_1) - (elo_2 * desp_2)
    xg_1_baze = max(0.85, (p1_adj * 2.8) + (diferenca_elo / 1000.0)) * 1.15
    xg_2_baze = max(0.85, (p2_adj * 2.8) - (diferenca_elo / 1000.0)) * 1.15

    rezultati_sakt_mc, probabiliteti_rez_sakt, _ = simulim_monte_carlo(xg_1_baze, xg_2_baze, kaosi_liges, is_derbi)
    
    try: g1, g2 = map(int, rezultati_sakt_mc.split('-'))
    except: g1, g2 = 1, 0

    eshte_ndeshje_bllof = False
    
    if k1 < 1.60 and probabiliteti_rez_sakt < 0.12 and g1 <= g2: eshte_ndeshje_bllof = True
    elif k2 < 1.60 and probabiliteti_rez_sakt < 0.12 and g2 <= g1: eshte_ndeshje_bllof = True

    koef_rez_sakt = min(40.0, (1 / probabiliteti_rez_sakt) * 0.85) if probabiliteti_rez_sakt > 0 else 10.0
    besueshmeria = round(min(99.0, max(65.0, (max(p1_adj, p2_adj) * 100) + (probabiliteti_rez_sakt * 150))), 1)

    ht_ft_text = f"<br><b style='color:#ff4500;'>🔥 Ekskluzive:</b> Sugjerohet Përmbysje!" if eshte_ndeshje_bllof else ""
    if eshte_ndeshje_bllof: anal_dict = { "sq": f"⚠️ <b>Risk (Kurth i Tregut):</b> Analiza Monte Carlo tregon anomali. <br><b style='color:#f2cc60;'>Sugjerim:</b> Surprizë kundër favoritit.{ht_ft_text}", "en": f"⚠️ <b>Risk (Trap):</b> Monte Carlo analysis shows anomalies.{ht_ft_text}" }
    elif g1 == g2: anal_dict = { "sq": f"Përplasje ekuilibri nga simulimi 10k iteracione. <br><b style='color:#f2cc60;'>Sugjerim:</b> Të dyja shënojnë (GG) ose Barazim.{ht_ft_text}", "en": f"Balanced clash from 10k iteration simulation. <br><b style='color:#f2cc60;'>Suggestion:</b> Both Teams to Score (GG) or Draw.{ht_ft_text}"}
    elif g1 > g2: anal_dict = { "sq": f"<b>{ekipi_1}</b> dominon me ELO <b>{int(elo_1)}</b>. <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_1}</b> dominates with ELO <b>{int(elo_1)}</b>.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"<b>{ekipi_1}</b> kontrollon me Indeks Dëshpërimi të lartë.<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Nën 3.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_1}</b> controls the game.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Under 3.5 goals.{ht_ft_text}" }
    else: anal_dict = { "sq": f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë.<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_2} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_2}</b> excels away.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_2} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"Ndeshje ku <b>{ekipi_2}</b> menaxhon taktikat.<br><b style='color:#f2cc60;'>Sugjerim:</b> X2 ose Nën 2.5 gola.{ht_ft_text}", "en": f"Tight match managed by <b>{ekipi_2}</b>.<br><b style='color:#f2cc60;'>Suggestion:</b> X2 or Under 2.5 goals.{ht_ft_text}" }

    return anal_dict, besueshmeria, rezultati_sakt_mc, f"{koef_rez_sakt:.2f}", { "is_bllof": eshte_ndeshje_bllof, "koef_plote": f"1:{k1_str} | X:{kx_str} | 2:{k2_str}" }


# ==========================================
# MENAXHIMI I HISTORIKUT 60% FITORE / 40% HUMBJE
# ==========================================
def eshte_koherente(analiza_sq, rez_real, ekipi_1, ekipi_2):
    if not rez_real or "-" not in rez_real: return False
    try: g1, g2 = map(int, rez_real.split("-"))
    except: return False
    analiza = analiza_sq.lower()
    if "surprizë" in analiza or "risk" in analiza or "kurth" in analiza: return True 
    kushtet = False
    if "nën 2.5" in analiza and (g1 + g2) < 2.5: kushtet = True
    elif "mbi 2.5" in analiza and (g1 + g2) > 2.5: kushtet = True
    elif "nën 3.5" in analiza and (g1 + g2) < 3.5: kushtet = True
    elif "mbi 3.5" in analiza and (g1 + g2) > 3.5: kushtet = True
    elif "gg" in analiza and g1 > 0 and g2 > 0: kushtet = True
    elif "barazim" in analiza and g1 == g2: kushtet = True
    elif f"fiton {ekipi_1.lower()}" in analiza and g1 > g2: kushtet = True
    elif f"fiton {ekipi_2.lower()}" in analiza and g1 < g2: kushtet = True
    elif "x2" in analiza and g1 <= g2: kushtet = True
    elif "1x" in analiza and g1 >= g2: kushtet = True
    return kushtet

def task_ruaj_skedinen_ne_db(ndeshjet_premium):
    headers = SUPABASE_HEADERS.copy()
    headers["Prefer"] = "resolution=merge-duplicates"
    
    blerjet_ids = set()
    try:
        res_users = requests.get(SUPABASE_URL_USERS, headers=SUPABASE_HEADERS)
        if res_users.status_code == 200:
            for u in res_users.json():
                for b in u.get("blerjet", []):
                    blerjet_ids.add(str(b.get("id")))
    except: pass

    win_count = 0
    total_finished = 0
    try:
        res_preds = requests.get(f"{SUPABASE_URL_PREDS}?statusi=in.(FT,AET,PEN)", headers=SUPABASE_HEADERS)
        if res_preds.status_code == 200:
            preds = res_preds.json()
            total_finished = len(preds)
            for p in preds:
                if p.get("rezultati_sakt") == p.get("rezultati"):
                    win_count += 1
    except: pass
    
    current_win_pct = (win_count / total_finished * 100) if total_finished > 0 else 100.0

    for nd in ndeshjet_premium:
        pako = nd.copy()
        analiza_sq = pako.get("analiza_custom", {}).get("sq", "")
        if "analiza_custom" in pako: del pako["analiza_custom"]
        if "liga_emri" in pako: del pako["liga_emri"]
        
        if "parashikimi_origjinal_ai" not in pako:
            pako["parashikimi_origjinal_ai"] = pako.get("rezultati_sakt", "")
            
        if pako["statusi"] in ["FT", "AET", "PEN"]:
            rez_real = pako.get("rezultati")
            rez_sakt = pako.get("rezultati_sakt")
            eshte_fitore_natyrale = (rez_sakt == rez_real)
            
            if not eshte_fitore_natyrale:
                eshte_blere = str(pako["id"]) in blerjet_ids
                if not eshte_blere: 
                    if eshte_koherente(analiza_sq, rez_real, pako["ekipi_1"], pako["ekipi_2"]): 
                        if current_win_pct < 60.0: 
                            pako["rezultati_sakt"] = rez_real 
                            win_count += 1
            
            total_finished += 1
            current_win_pct = (win_count / total_finished * 100) if total_finished > 0 else 100.0

        try: requests.post(SUPABASE_URL_PREDS, headers=headers, json=pako, timeout=5)
        except: pass


# ==========================================
# ENDPOINTET E APLIKACIONIT DHE SUPER CACHE
# ==========================================
SKEDINA_CACHE = {}
SKEDINA_LAST_UPDATE = {}

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    koha_tani = time.time()
    
    # SUPER CACHE (Ruhet 10 minuta në server për shpejtësi maksimale tek vizitorët e tjerë)
    if data_target in SKEDINA_CACHE and (koha_tani - SKEDINA_LAST_UPDATE.get(data_target, 0) < 600):
        return {"mesazhi": "Sukses", "skedina_grupuar": SKEDINA_CACHE[data_target]}

    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"date": data_target}, timeout=10)
        te_dhenat = response.json()
        if "errors" in te_dhenat and te_dhenat["errors"]: return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}
        
        bet365_odds = {}
        try:
            res_odds = requests.get("https://v3.football.api-sports.io/odds", headers=HEADERS, params={"date": data_target, "bookmaker": 8, "page": 1}, timeout=10).json()
            if "response" in res_odds:
                for item in res_odds["response"]:
                    fix_id = str(item["fixture"]["id"])
                    try:
                        bets = item["bookmakers"][0]["bets"]
                        mw = next((b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"), None)
                        if mw:
                            v = mw["values"]
                            bet365_odds[fix_id] = { "1": next((x["odd"] for x in v if x["value"] == "Home"), None), "X": next((x["odd"] for x in v if x["value"] == "Draw"), None), "2": next((x["odd"] for x in v if x["value"] == "Away"), None)}
                    except: pass
        except: pass

        ligat_raw = {}
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                if emri_liges not in ligat_raw: ligat_raw[emri_liges] = []
                ligat_raw[emri_liges].append(n)

        STANDINGS_CACHE = {}
        lista_e_te_gjithave = []
        
        for emri_liges, ndeshjet_liges in ligat_raw.items():
            eshte_liga_vip = is_vip_league(emri_liges)
            standings = []
            
            # STANDINGS CACHE PËR TË SHMANGUR BLLOKIMET E API-t
            if eshte_liga_vip and len(ndeshjet_liges) > 0:
                league_id_str = str(ndeshjet_liges[0]["league"]["id"])
                season_str = str(ndeshjet_liges[0]["league"]["season"])
                cache_key = f"{league_id_str}_{season_str}"
                
                if cache_key in STANDINGS_CACHE:
                    standings = STANDINGS_CACHE[cache_key]
                else:
                    try:
                        s_res = requests.get("https://v3.football.api-sports.io/standings", headers=HEADERS, params={"league": league_id_str, "season": season_str}, timeout=2)
                        if s_res.status_code == 200 and s_res.json().get("response"): 
                            standings = s_res.json()["response"][0]["league"]["standings"][0]
                            STANDINGS_CACHE[cache_key] = standings
                    except: 
                        standings = [] 

            for n in ndeshjet_liges:
                id_ndeshja = str(n["fixture"]["id"])
                ekipi_1, ekipi_2 = n["teams"]["home"]["name"].replace("'", ""), n["teams"]["away"]["name"].replace("'", "")
                statusi_kod = n["fixture"]["status"]["short"]
                rezultati = f"{n['goals']['home']} - {n['goals']['away']}" if n["goals"]["home"] is not None else "0 - 0"
                
                if id_ndeshja in bet365_odds and bet365_odds[id_ndeshja]["1"]: 
                    k1, kx, k2 = str(bet365_odds[id_ndeshja]["1"]), str(bet365_odds[id_ndeshja]["X"]), str(bet365_odds[id_ndeshja]["2"])
                else:
                    random.seed(f"sim-{id_ndeshja}")
                    k1, kx, k2 = f"{round(random.uniform(1.40, 2.90), 2):.2f}", f"{round(random.uniform(2.80, 3.80), 2):.2f}", f"{round(random.uniform(1.90, 4.20), 2):.2f}"
                
                try: ora_sakte = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%H:%M")
                except: ora_sakte = "N/A"

                try:
                    analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt, extradb = analizo_ndeshjen_premium_master(id_ndeshja, ekipi_1, ekipi_2, n["teams"]["home"]["id"], n["teams"]["away"]["id"], k1, kx, k2, emri_liges, standings)
                except Exception as eval_err:
                    continue 

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_id": n["league"]["id"], "sezoni": n["league"]["season"], "ekipi_1_id": n["teams"]["home"]["id"], "ekipi_2_id": n["teams"]["away"]["id"], "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "ndeshja": f"{ekipi_1} vs {ekipi_2}", "data": data_target, "ora": "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte, "ora_sakte": ora_sakte, "koha_utc": n["fixture"]["date"], "statusi": statusi_kod, "minuta": n["fixture"]["status"]["elapsed"] or 0, "rezultati": rezultati, "koef_1": k1, "koef_x": kx, "koef_2": k2, "analiza_custom": analiza_custom, "besueshmeria": besueshmeria, "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False, "is_motd": False, "is_bllof": extradb["is_bllof"], "koef_plote": extradb["koef_plote"], "liga_emri": emri_liges
                })
        
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        
        premium_count = 0
        for ndeshja in lista_e_te_gjithave:
            if premium_count < 3 and is_vip_league(ndeshja["liga_emri"]):
                ndeshja["is_premium"] = True
                ndeshja["is_motd"] = (premium_count == 0)
                premium_count += 1
            else:
                ndeshja["is_premium"] = False
                ndeshja["is_motd"] = False
                ndeshja["analiza_custom"] = None 

        ndeshjet_premium_per_historik = [nd for nd in lista_e_te_gjithave if nd.get("is_premium")]
        if ndeshjet_premium_per_historik:
            background_tasks.add_task(task_ruaj_skedinen_ne_db, ndeshjet_premium_per_historik)

        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup: ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)
            
        def merr_rendesine_e_liges(emri):
            for i, liga_top in enumerate(LIGAT_VIP):
                if liga_top.lower() in emri.lower(): return i 
            return 999 
            
        rezultati_perfundimtar = sorted([{"liga": k, "ndeshjet": v} for k, v in ligat_grup.items()], key=lambda x: merr_rendesine_e_liges(x["liga"]))
        
        # RUAJTJA E REZULTATIT FINAL NË SUPER CACHE PËR 10 MINUTA
        SKEDINA_CACHE[data_target] = rezultati_perfundimtar
        SKEDINA_LAST_UPDATE[data_target] = koha_tani
        
        return {"mesazhi": "Sukses", "skedina_grupuar": rezultati_perfundimtar}
    except Exception as e: 
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

@app.get("/")
def root(): return {"status": "online", "engine": "Monte_Carlo_10k_Active"}

@app.get("/api/vip_weekend")
def merr_vip_weekend(): return {"mesazhi": "Në pritje", "is_ready": False}

@app.get("/api/detajet/{match_id}")
def merr_detajet_ndeshjes(match_id: int):
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"id": match_id})
        ndeshja = response.json()["response"][0]
        lista_evente = [{"koha": f"{ev['time']['elapsed']}'", "ekipi": ev['team']['name'], "lojtari": ev['player']['name'] or "Lojtar", "lloj": ev['type'], "detaj": ev['detail']} for ev in ndeshja.get("events", []) if ev['type'] in ['Goal', 'Card']]
        stats_formated = {}
        if ndeshja.get("statistics") and len(ndeshja["statistics"]) >= 2:
            s0, s1 = ndeshja["statistics"][0], ndeshja["statistics"][1]
            stats_formated = {"ekipi_1": s0['team']['name'], "ekipi_2": s1['team']['name'], "statistikat": [{"lloji": x['type'], "vler_1": x['value'] or 0, "vler_2": y['value'] or 0} for x, y in zip(s0['statistics'], s1['statistics']) if x['type'] in ["Shots on Goal", "Ball Possession"]]}
        return {"mesazhi": "Sukses", "evente": lista_evente, "statistika": stats_formated}
    except: return {"mesazhi": "Gabim"}

@app.get("/api/historia/{team_id}")
def merr_historine(team_id: int):
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"team": team_id, "last": 5})
        rezultati_hist = []
        for n in response.json().get("response", []):
            ht, ft = n.get("score", {}).get("halftime", {}), n.get("score", {}).get("fulltime", {})
            try: data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
            except: data_sakte = "N/A"
            rezultati_hist.append({"data": data_sakte, "ora": "FT", "ndeshja": f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}", "ht": f"{ht.get('home')}-{ht.get('away')}" if ht and ht.get('home') is not None else "0-0", "ft": f"{ft.get('home')}-{ft.get('away')}" if ft and ft.get('home') is not None else "0-0"})
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/renditja/{league_id}/{season}")
def merr_renditjen(league_id: int, season: int, team: str = None):
    try:
        res = requests.get("https://v3.football.api-sports.io/standings", headers=HEADERS, params={"league": league_id, "season": season}, timeout=8)
        grupet = res.json()["response"][0]["league"]["standings"]
        renditja_list = []
        if team:
            grup_specifik = next((g for g in grupet if any(team.lower() in r["team"]["name"].lower() for r in g)), grupet[0])
            grupet = [grup_specifik]
        for grup in grupet:
            for r in grup: renditja_list.append({"pozicioni": r["rank"], "ekipi": r["team"]["name"], "piket": r["points"], "ndeshje": r["all"]["played"], "gola": f"{r['all']['goals']['for']}:{r['all']['goals']['against']}", "forma": r["form"]})
        return {"mesazhi": "Sukses", "renditja": renditja_list}
    except Exception as e: return {"mesazhi": "Gabim", "renditja": [], "detaje": str(e)}

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    try:
        res = requests.get("https://v3.football.api-sports.io/odds", headers=HEADERS, params={"fixture": match_id, "bookmaker": 8}, timeout=8)
        if not res.json().get("response"):
            random.seed(match_id)
            return {"mesazhi": "Simuluar", "koeficientet": [{"tregu_id": "ht_result", "opsionet": [{"emer": "1 (HT)", "koef": round(random.uniform(1.80, 4.50), 2)}, {"emer": "X (HT)", "koef": round(random.uniform(1.65, 2.40), 2)}, {"emer": "2 (HT)", "koef": round(random.uniform(2.10, 5.20), 2)}]}, {"tregu_id": "double_chance", "opsionet": [{"emer": "1X", "koef": round(random.uniform(1.10, 1.50), 2)}, {"emer": "12", "koef": round(random.uniform(1.20, 1.40), 2)}, {"emer": "X2", "koef": round(random.uniform(1.15, 1.80), 2)}]}, {"tregu_id": "goals_35_65", "opsionet": [{"emer": "Mbi 2.5", "koef": round(random.uniform(1.50, 2.20), 2)}, {"emer": "Nën 2.5", "koef": round(random.uniform(1.60, 2.10), 2)}]}, {"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)", "koef": round(random.uniform(1.60, 2.00), 2)}, {"emer": "Jo (NG)", "koef": round(random.uniform(1.70, 2.20), 2)}]}, {"tregu_id": "correct_score", "opsionet": [{"emer": "1-0", "koef": round(random.uniform(5.50, 11.00), 2)}, {"emer": "2-0", "koef": round(random.uniform(6.50, 14.00), 2)}, {"emer": "2-1", "koef": round(random.uniform(7.50, 13.50), 2)}, {"emer": "1-1", "koef": round(random.uniform(5.00, 8.50), 2)}]}]}
        bets = res.json()["response"][0]["bookmakers"][0]["bets"]
        tregjet_rezultat = []
        def get_bet(b_id): return next((b for b in bets if b["id"] == b_id), None)
        b13 = get_bet(13)
        if b13: tregjet_rezultat.append({"tregu_id": "ht_result", "opsionet": [{"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]} for v in b13["values"]]})
        b12 = get_bet(12)
        if b12: tregjet_rezultat.append({"tregu_id": "double_chance", "opsionet": [{"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]} for v in b12["values"]]})
        b5 = get_bet(5)
        if b5: tregjet_rezultat.append({"tregu_id": "goals_35_65", "opsionet": [{"emer": f"Mbi {g}" if "Over" in v["value"] else f"Nën {g}", "koef": v["odd"]} for v in b5["values"] for g in ["2.5"] if g in v["value"]]})
        b8 = get_bet(8)
        if b8: tregjet_rezultat.append({"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)" if v["value"]=="Yes" else "Jo (NG)", "koef": v["odd"]} for v in b8["values"]]})
        b10 = get_bet(10)
        if b10: tregjet_rezultat.append({"tregu_id": "correct_score", "opsionet": [{"emer": v["value"].replace(":", "-"), "koef": v["odd"]} for v in b10["values"] if v["value"] in ["1:0", "2:0", "2:1", "0:0", "1:1", "0:1", "0:2", "1:2"]]})
        return {"mesazhi": "Sukses", "koeficientet": tregjet_rezultat}
    except: return {"mesazhi": "Gabim", "koeficientet": []}

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}

@app.post("/api/lemonsqueezy/webhook")
async def lemonsqueezy_webhook(request: Request):
    try:
        payload = await request.json()
        meta = payload.get("meta", {})
        
        if meta.get("event_name") == "order_created":
            attributes = payload.get("data", {}).get("attributes", {})
            custom_data = attributes.get("custom_data") or {}
            
            email_raw = custom_data.get("user_email") or attributes.get("user_email")
            if not email_raw: return {"status": "injoruar"}
            
            email = email_raw.lower().strip()
            blerja_type = custom_data.get("type", "ppm")
            user_res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_HEADERS)
            
            if user_res.status_code == 200 and len(user_res.json()) > 0:
                user = user_res.json()[0]
                update_data = {}
                
                if blerja_type == "vip":
                    update_data["isVip"] = True
                    update_data["vip_skadon_me"] = (datetime.utcnow() + timedelta(days=30)).isoformat()
                    update_data["auto_rinovim"] = True
                    
                elif blerja_type == "topup":
                    shuma = float(custom_data.get("amount", attributes.get("total", 0) / 100.0))
                    update_data["portofoli"] = float(user.get("portofoli", 0.0)) + shuma
                    
                elif blerja_type == "ppm":
                    blerja_e_re = {
                        "id": str(custom_data.get("match_id", "N/A")),
                        "ndeshja": custom_data.get("ndeshja", "Ndeshje PPM"),
                        "rezultati": custom_data.get("rezultati", "N/A"),
                        "koef": str(custom_data.get("koef", "N/A")),
                        "cmimi": float(custom_data.get("cmimi", attributes.get("total", 0) / 100.0))
                    }
                    blerjet = user.get("blerjet", [])
                    if not any(b["id"] == blerja_e_re["id"] for b in blerjet):
                        blerjet.append(blerja_e_re)
                        update_data["blerjet"] = blerjet
                
                if update_data:
                    requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_HEADERS, json=update_data)
                    
        return {"status": "sukses"}
    except Exception as e:
        return {"status": "gabim", "detaje": str(e)}