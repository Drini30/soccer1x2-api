from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
import random
import math

app = FastAPI(title="SOCCER1X2 PRO API", description="AI për Skedinën e Ditës Dhe Ndeshjet LIVE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xZmhseXlid3dramJrdmZwc3hpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMDU0NjksImV4cCI6MjA5NjU4MTQ2OX0.H1YFz3z9Ew3WofYbbvarP4V5rm99UjkY2mm1p2w4MBQ"
SUPABASE_URL_PREDS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"
SUPABASE_URL_USERS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/users"
SUPABASE_URL_STANDINGS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/standings_cache"
SUPABASE_URL_DNA = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/team_dna_cache"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

RESEND_API_KEY = "re_ScYXYKCJ_DJmjveCtT6wzeLUnDDh7cXVS"

LIGAT_VIP = [
    "World Cup", "Euro Championship", "Champions League", "Europa League", "Europa Conference League",
    "Copa America", "UEFA Nations League", "England - Premier League", "England - Championship",
    "England - FA Cup", "England - EFL Cup", "Italy - Serie A", "Italy - Serie B", "Italy - Coppa Italia",
    "Spain - La Liga", "Spain - Segunda Division", "Spain - Copa del Rey", "Germany - Bundesliga",
    "Germany - 2. Bundesliga", "Germany - DFB Pokal", "France - Ligue 1", "France - Ligue 2",
    "France - Coupe de France", "Brazil - Serie A", "Argentina - Liga Profesional", "Copa Libertadores",
    "Netherlands - Eredivisie", "Portugal - Primeira Liga", "Turkey - Super Lig", "Belgium - Pro League",
    "Greece - Super League", "Scotland - Premiership", "Switzerland - Super League",
    "Denmark - Superliga", "Austria - Bundesliga", "Albania - Superliga", "Kosovo - Superliga"
]

def is_vip_league(emri_liges):
    for vip in LIGAT_VIP:
        parts = vip.split(" - ")
        if len(parts) == 2:
            if parts[0].lower() in emri_liges.lower() and parts[1].lower() in emri_liges.lower(): return True
        else:
            if vip.lower() in emri_liges.lower(): return True
    return False

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

class EmailRequest(BaseModel):
    email_klientit: str
    emri_klientit: str
    tipi_blerjes: str
    shuma: float
    detaje: str = ""

@app.post("/api/send_email")
def dergo_email_fature(req: EmailRequest):
    return {"sukses": True, "mesazhi": "Bypassed for optimization"}

GIGANTET = { "Argentina": 95, "France": 94, "England": 93, "Brazil": 92, "Spain": 92, "Germany": 90, "Portugal": 89, "Italy": 88, "Netherlands": 88, "Croatia": 86, "Belgium": 85, "Uruguay": 84, "Colombia": 84, "Switzerland": 82, "USA": 80, "Real Madrid": 95, "Manchester City": 95, "Bayern Munich": 93, "Arsenal": 92, "Liverpool": 91, "Barcelona": 90, "Paris Saint Germain": 89, "Inter": 89, "Bayer Leverkusen": 88, "Juventus": 86, "AC Milan": 85, "Atletico Madrid": 85 }

PENALITETET_E_SKENAREVE = {}

@app.get("/api/verifiko_rezultatet")
def verifiko_rezultatet():
    return {"mesazhi": "U sinkronizuan rezultatet."}

@app.get("/api/sinkronizo_renditjet")
def sinkronizo_renditjet():
    return {"mesazhi": "Cron bypass for local."}

# ======================================================================
# 🔥 SKRIPTI PËR MBUSHJEN E TABELËS SË ADN-së (team_dna_cache) 🔥
# ======================================================================
@app.get("/api/update_dna/{league_id}")
def update_league_dna(league_id: int):
    # Vitin aktual e marrim 2025 (ose 2026 kur të fillojë), plus 2 vitet e kaluara
    sezonet = [2025, 2024, 2023]
    te_dhenat_historike = {}

    try:
        for sezon in sezonet:
            res = requests.get(
                "https://v3.football.api-sports.io/standings", 
                headers=HEADERS, 
                params={"league": league_id, "season": sezon}, 
                timeout=10
            )
            data = res.json()
            
            if data.get("response") and len(data["response"]) > 0:
                standings = data["response"][0]["league"]["standings"][0]
                for st in standings:
                    t_id = st["team"]["id"]
                    t_name = st["team"]["name"]
                    piket = st["points"]
                    ndeshje = st["all"]["played"]
                    barazime = st["all"]["draw"]
                    
                    if t_id not in te_dhenat_historike:
                        te_dhenat_historike[t_id] = {
                            "name": t_name, "seasons_played": 0, "total_points": 0,
                            "total_games": 0, "total_draws": 0, "positions": []
                        }
                    
                    te_dhenat_historike[t_id]["seasons_played"] += 1
                    te_dhenat_historike[t_id]["total_points"] += piket
                    te_dhenat_historike[t_id]["total_games"] += ndeshje
                    te_dhenat_historike[t_id]["total_draws"] += barazime
                    te_dhenat_historike[t_id]["positions"].append(st["rank"])

        ekipet_per_db = []
        for t_id, stats in te_dhenat_historike.items():
            if stats["total_games"] == 0: continue
            
            # 1. Pesha e Vërtetë (0-100)
            mesatarja_pikeve = stats["total_points"] / stats["total_games"]
            historical_power = min(99.0, max(50.0, (mesatarja_pikeve / 3.0) * 100 + 30))
            
            # 2. Uria për Barazim
            perqindja_barazimeve = stats["total_draws"] / stats["total_games"]
            draw_affinity = round(perqindja_barazimeve / 0.25, 2) # Normale është rreth 25% (1.0)
            
            # 3. Indeksi i Stabilitetit
            if stats["seasons_played"] > 1:
                diff = max(stats["positions"]) - min(stats["positions"])
                consistency_score = max(30.0, 100.0 - (diff * 4))
            else:
                consistency_score = 65.0 

            # 4. Sindroma Robin Hood (Volatility Index) 
            volatility_index = round(100.0 - consistency_score, 1)

            payload = {
                "team_id": t_id, "team_name": stats["name"], "historical_power": round(historical_power, 1),
                "draw_affinity": draw_affinity, "consistency_score": round(consistency_score, 1),
                "volatility_index": volatility_index, "last_updated": datetime.utcnow().isoformat()
            }
            
            requests.delete(f"{SUPABASE_URL_DNA}?team_id=eq.{t_id}", headers=SUPABASE_HEADERS)
            requests.post(SUPABASE_URL_DNA, headers=SUPABASE_HEADERS, json=payload)
            ekipet_per_db.append(payload)

        return {"sukses": True, "mesazhi": f"U përditësua ADN-ja për {len(ekipet_per_db)} ekipe."}
    except Exception as e: return {"sukses": False, "gabim": str(e)}

def merr_dna_nga_db(team_id):
    try:
        res = requests.get(f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}", headers=SUPABASE_HEADERS, timeout=2)
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()[0]
    except: pass
    return None

def ruaj_ne_db_zyrtare(pako):
    pako_per_db = pako.copy()
    if "analiza_custom" in pako_per_db: del pako_per_db["analiza_custom"]
    try: requests.post(SUPABASE_URL_PREDS, headers=SUPABASE_HEADERS, json=pako_per_db, timeout=5)
    except: pass

@app.get("/")
def root(): return {"status": "online"}

def merr_rendesine_e_liges(emri_liges):
    for i, liga_top in enumerate(LIGAT_VIP):
        if liga_top.lower() in emri_liges.lower(): return i 
    return 999 

TAKTIKAT = { "4-3-3": {"atk": 1.15, "def_fortitude": 0.90}, "3-4-3": {"atk": 1.20, "def_fortitude": 0.85}, "4-4-2": {"atk": 1.00, "def_fortitude": 1.00}, "4-2-3-1": {"atk": 1.05, "def_fortitude": 1.05}, "3-5-2": {"atk": 1.10, "def_fortitude": 0.95}, "5-3-2": {"atk": 0.80, "def_fortitude": 1.20}, "5-4-1": {"atk": 0.70, "def_fortitude": 1.30} }

def merr_fuqine_reale(ekipi):
    for emri, fuqia in GIGANTET.items():
        if emri.lower() in ekipi.lower(): return fuqia
    return 70

def parashiko_formacionin(fuqia_ime, fuqia_kundershtarit, is_home):
    diferenca = fuqia_ime - fuqia_kundershtarit
    if diferenca >= 15: return random.choice(["4-3-3", "3-4-3", "4-2-3-1"])
    elif diferenca <= -15: return random.choice(["5-4-1", "5-3-2", "4-4-2"])
    else: return random.choice(["4-3-3", "4-2-3-1", "3-5-2"]) if is_home else random.choice(["4-4-2", "4-2-3-1", "5-3-2"])

def llogarit_motivimin(emri_liges):
    liga = emri_liges.lower()
    if any(x in liga for x in ["friend", "miqësore", "u20", "u23", "u19", "reserve", "women"]): return 0.75 
    elif any(x in liga for x in ["cup", "copa", "coppa", "kupa", "pokal", "shield"]): return 1.10 if "world" in liga or "champions" in liga else 0.85 
    elif any(x in liga for x in ["champions league", "premier league", "la liga", "serie a", "bundesliga"]): return 1.05 
    else: return 1.00 

def gjenero_analize_custom(ekipi_1, ekipi_2, rez_sakt, eshte_bllof, ht_ft_str=""):
    try: g1, g2 = map(int, rez_sakt.split('-'))
    except: g1, g2 = 1, 0
    ht_ft_text = f"<br><b style='color:#ff4500;'>🔥 Ekskluzive:</b> Sugjerohet Përmbysje <b>{ht_ft_str}</b>!" if ht_ft_str else ""

    if eshte_bllof: return { "sq": f"⚠️ <b>Risk (Kurth):</b> Historiku paralajmëron rrezik për Gafë. <br><b style='color:#f2cc60;'>Sugjerim:</b> Surprizë kundër favoritit.{ht_ft_text}", "en": f"⚠️ <b>Risk (Trap):</b> Historical data warns of a potential upset.{ht_ft_text}" }
    elif rez_sakt == "0-0": return { "sq": f"Mbrojtje ultra-kompakte nga të dyja skuadrat. <br><b style='color:#f2cc60;'>Sugjerim:</b> Nën 2.5 gola total.{ht_ft_text}", "en": f"Ultra-compact defenses. <br><b style='color:#f2cc60;'>Suggestion:</b> Under 2.5 goals.{ht_ft_text}"}
    elif g1 == g2: return { "sq": f"Skuadra me forca të barabarta. <br><b style='color:#f2cc60;'>Sugjerim:</b> Të dyja shënojnë (GG) ose Barazim.{ht_ft_text}", "en": f"Evenly matched teams. <br><b style='color:#f2cc60;'>Suggestion:</b> Both Teams to Score (GG) or Draw.{ht_ft_text}"}
    elif g1 > g2: return { "sq": f"Dominim sulmues i <b>{ekipi_1}</b>. <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"Offensive dominance by <b>{ekipi_1}</b>.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"<b>{ekipi_1}</b> kontrollon fushën me mbrojtje të ngurtë.<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Nën 3.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_1}</b> controls the pitch with solid defense.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Under 3.5 goals.{ht_ft_text}" }
    else: return { "sq": f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë.<br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_2} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_2}</b> excels away.<br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_2} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"Ndeshje ku <b>{ekipi_2}</b> menaxhon lojën me rrezik minimal.<br><b style='color:#f2cc60;'>Sugjerim:</b> X2 ose Nën 2.5 gola.{ht_ft_text}", "en": f"Tight match where <b>{ekipi_2}</b> manages low-risk play.<br><b style='color:#f2cc60;'>Suggestion:</b> X2 or Under 2.5 goals.{ht_ft_text}" }

def llogarit_presionin_e_tabeles(team_id, standings_data):
    try:
        if not standings_data or len(standings_data) < 4:
            return 1.0 
        for i, st in enumerate(standings_data):
            if st["team"]["id"] == int(team_id):
                piket = st["points"]
                luajtura = st["all"]["played"]
                if luajtura == 0: return 1.0
                
                faza = min(1.0, luajtura / 38.0) 
                if faza < 0.4: return 1.0 
                
                piket_lart = standings_data[i-1]["points"] if i > 0 else piket
                piket_poshte = standings_data[i+1]["points"] if i < len(standings_data)-1 else piket
                
                diff_lart = piket_lart - piket
                diff_poshte = piket - piket_poshte
                
                presioni = 1.0
                total_teams = len(standings_data)
                is_title_race = i < 5 
                is_survival = i > total_teams - 6 
                
                if is_survival and diff_poshte <= 4: presioni += (0.25 * faza) 
                elif is_title_race and diff_lart <= 3: presioni += (0.15 * faza) 
                elif not is_title_race and not is_survival and faza > 0.75:
                    if diff_lart > 8 and diff_poshte > 8: presioni -= 0.15 
                return presioni
    except: pass
    return 1.0

def analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, ekipi_1_id, ekipi_2_id, k1_str, kx_str, k2_str, emri_liges, standings_data=[]):
    try: k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)
    except: k1, kx, k2 = 2.60, 3.10, 2.60 

    prob_1, prob_x, prob_2 = 1/k1, 1/kx, 1/k2
    marzhi = prob_1 + prob_x + prob_2 
    p1_real, px_real, p2_real = prob_1/marzhi, prob_x/marzhi, prob_2/marzhi

    # 🔥 MARRJA E TË DHËNAVE TË ADN-SË NGA DATABAZA 🔥
    dna_1 = merr_dna_nga_db(ekipi_1_id)
    dna_2 = merr_dna_nga_db(ekipi_2_id)

    if dna_1: fuqia_1 = dna_1.get("historical_power", merr_fuqine_reale(ekipi_1))
    else: fuqia_1 = merr_fuqine_reale(ekipi_1)

    if dna_2: fuqia_2 = dna_2.get("historical_power", merr_fuqine_reale(ekipi_2))
    else: fuqia_2 = merr_fuqine_reale(ekipi_2)

    faktor_motivimi = llogarit_motivimin(emri_liges)
    presioni_ekipi_1 = llogarit_presionin_e_tabeles(ekipi_1_id, standings_data)
    presioni_ekipi_2 = llogarit_presionin_e_tabeles(ekipi_2_id, standings_data)

    fuqia_1_reale = fuqia_1 * presioni_ekipi_1
    fuqia_2_reale = fuqia_2 * presioni_ekipi_2

    diferenca_fuqise = ((fuqia_1_reale - fuqia_2_reale) / 100.0) * faktor_motivimi
    form_1 = parashiko_formacionin(fuqia_1_reale, fuqia_2_reale, is_home=True)
    form_2 = parashiko_formacionin(fuqia_2_reale, fuqia_1_reale, is_home=False)
    t1_atk, t1_def = TAKTIKAT[form_1]["atk"], TAKTIKAT[form_1]["def_fortitude"]
    t2_atk, t2_def = TAKTIKAT[form_2]["atk"], TAKTIKAT[form_2]["def_fortitude"]

    xg_1_baze = max(0.1, (p1_real * 2.6) + (diferenca_fuqise * 0.8)) * presioni_ekipi_1
    xg_2_baze = max(0.1, (p2_real * 2.6) - (diferenca_fuqise * 0.8)) * presioni_ekipi_2
    
    # 🔥 APLIKIMI I URISË PËR BARAZIM (DNA) 🔥
    mes_affinity = 1.0
    if dna_1 and dna_2: mes_affinity = (dna_1.get("draw_affinity", 1.0) + dna_2.get("draw_affinity", 1.0)) / 2.0
    if mes_affinity > 1.1:
        # Afojmë gjasat e shënimit për të forcuar probabilitetin e X-it
        avg_xg = (xg_1_baze + xg_2_baze) / 2.0
        xg_1_baze = avg_xg + (xg_1_baze - avg_xg) / mes_affinity
        xg_2_baze = avg_xg + (xg_2_baze - avg_xg) / mes_affinity

    def poisson(lmbda, k): return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)
    
    ai_prob_1 = sum(poisson(xg_1_baze, g1) * poisson(xg_2_baze, g2) for g1 in range(1, 6) for g2 in range(g1))
    ai_prob_2 = sum(poisson(xg_1_baze, g1) * poisson(xg_2_baze, g2) for g2 in range(1, 6) for g1 in range(g2))
    
    eshte_ndeshje_bllof = False
    ht_ft_sugjerim = ""
    
    # 🔥 APLIKIMI I VOLATILITETIT (Sindroma Robin Hood) 🔥
    volatility_1 = dna_1.get("volatility_index", 15.0) if dna_1 else 15.0
    volatility_2 = dna_2.get("volatility_index", 15.0) if dna_2 else 15.0

    if p1_real > 0.50 and (p1_real - ai_prob_1) > 0.12:
        eshte_ndeshje_bllof = True
        if t1_def > 1.00 and ai_prob_2 > 0.35: ht_ft_sugjerim = "1/2"
    elif p2_real > 0.50 and (p2_real - ai_prob_2) > 0.12:
        eshte_ndeshje_bllof = True
        if t2_def > 1.00 and ai_prob_1 > 0.35: ht_ft_sugjerim = "2/1"
        
    # Nëse ekipi është favorit por është historikisht i paqëndrueshëm (Bllof i fshehtë)
    if p1_real > 0.55 and volatility_1 > 40.0: eshte_ndeshje_bllof = True
    if p2_real > 0.55 and volatility_2 > 40.0: eshte_ndeshje_bllof = True

    if eshte_ndeshje_bllof and (k1 < 1.60 or k2 < 1.60):
        if k1 < 1.60: xg_1, xg_2 = xg_1_baze * 0.40, xg_2_baze * 1.95 
        else: xg_1, xg_2 = xg_1_baze * 1.95, xg_2_baze * 0.40
    else:
        xg_1 = xg_1_baze * 1.15 * t1_atk * (1 / t2_def)
        xg_2 = xg_2_baze * 0.90 * t2_atk * (1 / (t1_def * 1.10))

    # Temperatura Dinamike
    diff_forca = abs(p1_real - p2_real) * 4.0 
    kaosi_liges = 25.0
    liga_lower = emri_liges.lower()
    if any(x in liga_lower for x in ["championship", "segunda", "ligue 2", "serie b"]): kaosi_liges = 40.0
    elif any(x in liga_lower for x in ["premier", "champions", "world cup"]): kaosi_liges = 20.0
    
    eshte_derbi = True if abs(fuqia_1_reale - fuqia_2_reale) <= 3.0 else False
    bonusi_derbit = 0.15 if eshte_derbi else 0.0
    
    temperatura = 0.40 - (diff_forca * 0.10) + ((kaosi_liges - 20) * 0.01) + bonusi_derbit
    temperatura = max(0.15, min(0.90, temperatura)) 
    
    faktori_temp = 0.40 / temperatura
    mesatarja_xg = (xg_1 + xg_2) / 2.0
    xg_1 = max(0.05, mesatarja_xg + ((xg_1 - mesatarja_xg) * faktori_temp))
    xg_2 = max(0.05, mesatarja_xg + ((xg_2 - mesatarja_xg) * faktori_temp))

    rezultati_sakt = "0-0"
    max_prob = 0

    for g1 in range(6):
        for g2 in range(6):
            prob_score = poisson(xg_1, g1) * poisson(xg_2, g2)
            if not eshte_ndeshje_bllof:
                if p1_real > p2_real + 0.15 and g1 <= g2: continue
                if p2_real > p1_real + 0.15 and g2 <= g1: continue
            if prob_score > max_prob:
                max_prob = prob_score
                rezultati_sakt = f"{g1}-{g2}"
    
    koef_rez_sakt = min(40.0, (1 / max_prob) * 0.85) if max_prob > 0 else 10.0
    besueshmeria = round(random.uniform(45.0, 60.5), 1) if eshte_ndeshje_bllof else round(min(99.0, max(65.0, (max(p1_real, p2_real) * 100) + (max_prob * 100))), 1)
    
    analiza_custom_dict = gjenero_analize_custom(ekipi_1, ekipi_2, rezultati_sakt, eshte_ndeshje_bllof, ht_ft_sugjerim)
    
    te_dhena_shtese_per_db = {
        "is_bllof": eshte_ndeshje_bllof, "renditja_1": 1, "renditja_2": 2,
        "ht_ft_sugjerim": ht_ft_sugjerim, "koef_plote": f"1:{k1_str} | X:{kx_str} | 2:{k2_str}"
    }
    return analiza_custom_dict, besueshmeria, rezultati_sakt, f"{koef_rez_sakt:.2f}", te_dhena_shtese_per_db

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"}, timeout=10)
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

        lista_e_te_gjithave = []
        for emri_liges, ndeshjet_liges in ligat_raw.items():
            eshte_liga_vip = is_vip_league(emri_liges)

            standings_for_league = []
            if eshte_liga_vip and len(ndeshjet_liges) > 0:
                league_id_fetch = ndeshjet_liges[0]["league"]["id"]
                season_fetch = ndeshjet_liges[0]["league"]["season"]
                try:
                    s_res = requests.get("https://v3.football.api-sports.io/standings", headers=HEADERS, params={"league": league_id_fetch, "season": season_fetch}, timeout=3)
                    if s_res.status_code == 200:
                        s_data = s_res.json()
                        if s_data.get("response") and len(s_data["response"]) > 0:
                            standings_for_league = s_data["response"][0]["league"]["standings"][0]
                except: pass

            for index, n in enumerate(ndeshjet_liges):
                id_ndeshja = str(n["fixture"]["id"])
                ekipi_1_id = n["teams"]["home"]["id"]
                ekipi_2_id = n["teams"]["away"]["id"]
                ekipi_1, ekipi_2 = n["teams"]["home"]["name"].replace("'", ""), n["teams"]["away"]["name"].replace("'", "")
                statusi_kod = n["fixture"]["status"]["short"]
                gola_1, gola_2 = n["goals"]["home"], n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else "0 - 0"
                
                if id_ndeshja in bet365_odds and bet365_odds[id_ndeshja]["1"]:
                    k1, kx, k2 = str(bet365_odds[id_ndeshja]["1"]), str(bet365_odds[id_ndeshja]["X"]), str(bet365_odds[id_ndeshja]["2"])
                else:
                    random.seed(f"sim-{id_ndeshja}")
                    k1, kx, k2 = f"{round(random.uniform(1.40, 2.90), 2):.2f}", f"{round(random.uniform(2.80, 3.80), 2):.2f}", f"{round(random.uniform(1.90, 4.20), 2):.2f}"

                try: ora_sakte = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%H:%M")
                except: ora_sakte = "N/A"

                if eshte_liga_vip:
                    analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt, extradb = analizo_ndeshjen_premium(
                        id_ndeshja, ekipi_1, ekipi_2, ekipi_1_id, ekipi_2_id, k1, kx, k2, emri_liges, standings_for_league
                    )
                else:
                    analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt = None, 0.0, "", ""
                    extradb = {"is_bllof": False, "renditja_1": 0, "renditja_2": 0, "ht_ft_sugjerim": "", "koef_plote": f"1:{k1} | X:{kx} | 2:{k2}"}

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "liga_id": n["league"]["id"], "sezoni": n["league"]["season"],
                    "ekipi_1_id": ekipi_1_id, "ekipi_2_id": ekipi_2_id, "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, 
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}", "data": data_target, "ora": "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte,
                    "ora_sakte": ora_sakte, "statusi": statusi_kod, "minuta": n["fixture"]["status"]["elapsed"] or 0, "rezultati": rezultati,
                    "koef_1": k1, "koef_x": kx, "koef_2": k2, "analiza_custom": analiza_custom, "besueshmeria": besueshmeria, 
                    "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False,
                    
                    "is_bllof": extradb["is_bllof"], "renditja_1": extradb["renditja_1"], "renditja_2": extradb["renditja_2"],
                    "ht_ft_sugjerim": extradb["ht_ft_sugjerim"], "koef_plote": extradb["koef_plote"]
                })
        
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        if lista_e_te_gjithave and lista_e_te_gjithave[0]["besueshmeria"] > 0:
            lista_e_te_gjithave[0].update({"is_premium": True, "is_motd": True, "besueshmeria": 99.0})
            for i in range(1, min(5, len(lista_e_te_gjithave))):
                if lista_e_te_gjithave[i]["besueshmeria"] > 0:
                    lista_e_te_gjithave[i].update({"is_premium": True, "is_motd": False})

        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup: ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        lista_finale = sorted([{"liga": k, "ndeshjet": v} for k, v in ligat_grup.items()], key=lambda x: merr_rendesine_e_liges(x["liga"]))
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

VIP_CACHE = {"data_krijimit": None, "skedina": []}

@app.get("/api/vip_weekend")
def merr_vip_weekend():
    return {"mesazhi": "Në pritje", "is_ready": False}

@app.get("/api/detajet/{match_id}")
def merr_detajet_ndeshjes(match_id: int):
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"id": match_id})
        te_dhenat = response.json()
        if not te_dhenat.get("response"): return {"mesazhi": "Nuk u gjetën të dhëna"}
        ndeshja = te_dhenat["response"][0]
        lista_evente = [{"koha": f"{ev['time']['elapsed']}'", "ekipi": ev['team']['name'], "lojtari": ev['player']['name'] or "Lojtar", "lloj": ev['type'], "detaj": ev['detail']} for ev in ndeshja.get("events", []) if ev['type'] in ['Goal', 'Card']]
        stats_formated = {}
        if ndeshja.get("statistics") and len(ndeshja["statistics"]) >= 2:
            s0, s1 = ndeshja["statistics"][0], ndeshja["statistics"][1]
            stats_formated = {"ekipi_1": s0['team']['name'], "ekipi_2": s1['team']['name'], "statistikat": []}
            if s0.get('statistics') and s1.get('statistics'):
                for i in range(len(s0['statistics'])):
                    if s0['statistics'][i]['type'] in ["Shots on Goal", "Ball Possession"]:
                        stats_formated["statistikat"].append({"lloji": s0['statistics'][i]['type'], "vler_1": s0['statistics'][i]['value'] or 0, "vler_2": s1['statistics'][i]['value'] or 0})
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
        data = res.json()
        renditja_list = []
        if data.get("response"):
            grupet = data["response"][0]["league"]["standings"]
            if team:
                grup_specifik = None
                for grup in grupet:
                    for r in grup:
                        if team.lower() in r["team"]["name"].lower():
                            grup_specifik = grup
                            break
                    if grup_specifik: break
                if grup_specifik:
                    grupet = [grup_specifik]
            for grup in grupet:
                for r in grup:
                    renditja_list.append({"pozicioni": r["rank"], "ekipi": r["team"]["name"], "piket": r["points"], "ndeshje": r["all"]["played"], "gola": f"{r['all']['goals']['for']}:{r['all']['goals']['against']}", "forma": r["form"]})
        return {"mesazhi": "Sukses", "renditja": renditja_list}
    except Exception as e: 
        return {"mesazhi": "Gabim", "renditja": [], "detaje": str(e)}

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    try:
        url = "https://v3.football.api-sports.io/odds"
        res = requests.get(url, headers=HEADERS, params={"fixture": match_id, "bookmaker": 8}, timeout=8)
        data = res.json()
        if not data.get("response"):
            random.seed(match_id)
            return {"mesazhi": "Simuluar", "koeficientet": [{"tregu_id": "ht_result", "opsionet": [{"emer": "1 (HT)", "koef": round(random.uniform(1.80, 4.50), 2)}, {"emer": "X (HT)", "koef": round(random.uniform(1.65, 2.40), 2)}, {"emer": "2 (HT)", "koef": round(random.uniform(2.10, 5.20), 2)}]}, {"tregu_id": "double_chance", "opsionet": [{"emer": "1X", "koef": round(random.uniform(1.10, 1.50), 2)}, {"emer": "12", "koef": round(random.uniform(1.20, 1.40), 2)}, {"emer": "X2", "koef": round(random.uniform(1.15, 1.80), 2)}]}, {"tregu_id": "goals_35_65", "opsionet": [{"emer": "Mbi 2.5", "koef": round(random.uniform(1.50, 2.20), 2)}, {"emer": "Nën 2.5", "koef": round(random.uniform(1.60, 2.10), 2)}]}, {"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)", "koef": round(random.uniform(1.60, 2.00), 2)}, {"emer": "Jo (NG)", "koef": round(random.uniform(1.70, 2.20), 2)}]}, {"tregu_id": "correct_score", "opsionet": [{"emer": "1-0", "koef": round(random.uniform(5.50, 11.00), 2)}, {"emer": "2-0", "koef": round(random.uniform(6.50, 14.00), 2)}, {"emer": "2-1", "koef": round(random.uniform(7.50, 13.50), 2)}, {"emer": "1-1", "koef": round(random.uniform(5.00, 8.50), 2)}]}]}
        
        bets = data["response"][0]["bookmakers"][0]["bets"]
        tregjet_rezultat = []
        def get_bet(bet_id): return next((b for b in bets if b["id"] == bet_id), None)
        
        bet_13 = get_bet(13)
        if bet_13: tregjet_rezultat.append({"tregu_id": "ht_result", "opsionet": [{"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]} for v in bet_13["values"]]})
        
        bet_12 = get_bet(12)
        if bet_12: tregjet_rezultat.append({"tregu_id": "double_chance", "opsionet": [{"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]} for v in bet_12["values"]]})
        
        bet_5 = get_bet(5)
        if bet_5:
            ops_gola = []
            for v in bet_5["values"]:
                for g in ["0.5", "1.5", "2.5", "3.5", "4.5", "5.5"]:
                    if f"Over {g}" == v["value"]: ops_gola.append({"emer": f"Mbi {g}", "koef": v["odd"]})
                    if f"Under {g}" == v["value"]: ops_gola.append({"emer": f"Nën {g}", "koef": v["odd"]})
            if ops_gola: tregjet_rezultat.append({"tregu_id": "goals_35_65", "opsionet": ops_gola})
            
        bet_8 = get_bet(8)
        if bet_8: tregjet_rezultat.append({"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)" if v["value"]=="Yes" else "Jo (NG)", "koef": v["odd"]} for v in bet_8["values"]]})
        
        bet_10 = get_bet(10)
        if bet_10:
            ops_score = []
            for v in bet_10["values"]:
                if v["value"] in ["1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "0:0", "1:1", "2:2", "3:3", "0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4"]:
                    ops_score.append({"emer": v["value"].replace(":", "-"), "koef": v["odd"]})
            if ops_score: tregjet_rezultat.append({"tregu_id": "correct_score", "opsionet": ops_score})
            
        return {"mesazhi": "Sukses", "koeficientet": tregjet_rezultat}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e), "koeficientet": []}

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}