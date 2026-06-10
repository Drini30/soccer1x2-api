from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import random
import math

app = FastAPI(title="SOCCER 1X2 API", description="AI për Skedinën e Ditës Dhe Ndeshjet LIVE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

# 🔥 KONFIGURIMI I DATABAZËS SUPABASE 🔥
SUPABASE_ANON_KEY = "sb_publishable_zdg-Qz3O3Sf5VRTXy1msXA_0zyoEJ7y"
SUPABASE_URL = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def ruaj_ne_sfond(paketa_per_db):
    if not SUPABASE_ANON_KEY.startswith("VENDOS") and paketa_per_db:
        try:
            for pako in paketa_per_db[:15]:
                requests.post(SUPABASE_URL, headers=SUPABASE_HEADERS, json=pako, timeout=2)
        except: pass 

@app.get("/")
def root(): return {"status": "online"}

LIGAT_KRYESORE = [
    "World Cup", "Euro Championship", "Champions League", "Europa League",
    "England - Premier League", "Spain - La Liga", "Italy - Serie A",
    "Germany - Bundesliga", "France - Ligue 1", "World - Friendlies",
    "World - UEFA Nations League", "Albania - Superliga"
]

def merr_rendesine_e_liges(emri_liges):
    for i, liga_top in enumerate(LIGAT_KRYESORE):
        if liga_top.lower() in emri_liges.lower(): return i 
    return 999 

GIGANTET = {
    "Argentina": 95, "France": 94, "England": 93, "Brazil": 92, "Spain": 92,
    "Germany": 90, "Portugal": 89, "Italy": 88, "Netherlands": 88, "Croatia": 86,
    "Belgium": 85, "Uruguay": 84, "Colombia": 84, "Switzerland": 82, "USA": 80,
    "Costa Rica": 65, "Albania": 70, "Bulgaria": 62, "San Marino": 45, "Andorra": 45,
    "Real Madrid": 95, "Manchester City": 95, "Bayern Munich": 93, "Arsenal": 92,
    "Liverpool": 91, "Barcelona": 90, "Paris Saint Germain": 89, "Inter": 89,
    "Bayer Leverkusen": 88, "Juventus": 86, "AC Milan": 85, "Atletico Madrid": 85,
    "Dortmund": 84, "Tottenham": 86, "Aston Villa": 83, "Chelsea": 84
}

def merr_fuqine_reale(ekipi):
    for emri, fuqia in GIGANTET.items():
        if emri.lower() in ekipi.lower(): return fuqia
    return 70

def analizo_ndeshjen_premium(ekipi_1, ekipi_2, k1_str, kx_str, k2_str):
    try:
        k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)
    except:
        k1, kx, k2 = 2.60, 3.10, 2.60 

    prob_1 = 1 / k1
    prob_x = 1 / kx
    prob_2 = 1 / k2
    marzhi = prob_1 + prob_x + prob_2 
    
    p1_real = prob_1 / marzhi
    px_real = prob_x / marzhi
    p2_real = prob_2 / marzhi

    fuqia_1 = merr_fuqine_reale(ekipi_1)
    fuqia_2 = merr_fuqine_reale(ekipi_2)
    diferenca_fuqise = (fuqia_1 - fuqia_2) / 100.0

    xg_1 = max(0.1, (p1_real * 2.6) + (diferenca_fuqise * 0.6))
    xg_2 = max(0.1, (p2_real * 2.6) - (diferenca_fuqise * 0.6))

    def poisson(lmbda, k): return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)

    rezultati_sakt = "0-0"
    max_prob = 0

    for g1 in range(5):
        for g2 in range(5):
            prob_score = poisson(xg_1, g1) * poisson(xg_2, g2)
            if p1_real > p2_real + 0.1 and g1 <= g2: continue
            if p2_real > p1_real + 0.1 and g2 <= g1: continue
            
            if prob_score > max_prob:
                max_prob = prob_score
                rezultati_sakt = f"{g1}-{g2}"
    
    koef_rez_sakt = min(40.0, (1 / max_prob) * 0.85) if max_prob > 0 else 10.0
    besueshmeria = round(min(98.5, max(55.0, (max(p1_real, p2_real) * 100) + (abs(diferenca_fuqise)*10))), 1)

    if p1_real > 0.65 or p2_real > 0.65: hint_id = 4 
    elif px_real > 0.32 or abs(p1_real - p2_real) < 0.1: hint_id = 2 
    elif xg_1 > 1.3 and xg_2 > 1.3: hint_id = 3 
    else: hint_id = 1 
    
    return hint_id, besueshmeria, rezultati_sakt, f"{koef_rez_sakt:.2f}"

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"}, timeout=8)
        te_dhenat = response.json()
        
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        bet365_odds = {}
        try:
            res_odds = requests.get("https://v3.football.api-sports.io/odds", headers=HEADERS, params={"date": data_target, "bookmaker": 8, "page": 1}, timeout=10)
            d_odds = res_odds.json()
            if "response" in d_odds:
                for item in d_odds["response"]:
                    fix_id = str(item["fixture"]["id"])
                    try:
                        bets = item["bookmakers"][0]["bets"]
                        mw = next((b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"), None)
                        if mw:
                            v = mw["values"]
                            k1 = next((x["odd"] for x in v if x["value"] == "Home"), None)
                            kx = next((x["odd"] for x in v if x["value"] == "Draw"), None)
                            k2 = next((x["odd"] for x in v if x["value"] == "Away"), None)
                            if k1 and kx and k2: bet365_odds[fix_id] = {"1": k1, "X": kx, "2": k2}
                    except: pass
        except: pass

        lista_e_te_gjithave = []
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                liga_id = n["league"]["id"]
                sezoni = n["league"]["season"]
                ekipi_1_id = n["teams"]["home"]["id"]
                ekipi_2_id = n["teams"]["away"]["id"]
                ekipi_1 = n["teams"]["home"]["name"].replace("'", "")
                ekipi_2 = n["teams"]["away"]["name"].replace("'", "")
                
                statusi_kod = n["fixture"]["status"]["short"]
                minuta_loje = n["fixture"]["status"]["elapsed"] or 0
                gola_1 = n["goals"]["home"]
                gola_2 = n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else "0 - 0"
                
                if id_ndeshja in bet365_odds:
                    koef_1 = str(bet365_odds[id_ndeshja]["1"])
                    koef_x = str(bet365_odds[id_ndeshja]["X"])
                    koef_2 = str(bet365_odds[id_ndeshja]["2"])
                else:
                    random.seed(f"sim-{id_ndeshja}")
                    koef_1 = f"{round(random.uniform(1.40, 2.90), 2):.2f}"
                    koef_x = f"{round(random.uniform(2.80, 3.80), 2):.2f}"
                    koef_2 = f"{round(random.uniform(1.90, 4.20), 2):.2f}"

                data_sakte = data_target
                ora_sakte = "N/A"
                if n["fixture"]["date"]:
                    try:
                        d_obj = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S")
                        data_sakte = d_obj.strftime("%d/%m/%Y")
                        ora_sakte = d_obj.strftime("%H:%M")
                    except: pass

                hint_id, besueshmeria, rez_sakt, koef_rez_sakt = analizo_ndeshjen_premium(ekipi_1, ekipi_2, koef_1, koef_x, koef_2)

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "liga_id": liga_id, "sezoni": sezoni,
                    "ekipi_1_id": ekipi_1_id, "ekipi_2_id": ekipi_2_id,
                    "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte, 
                    "ora": "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte,
                    "ora_sakte": ora_sakte,
                    "statusi": statusi_kod, "minuta": minuta_loje, "rezultati": rezultati,
                    "koef_1": koef_1, "koef_x": koef_x, "koef_2": koef_2,
                    "hint_id": hint_id, "besueshmeria": besueshmeria, "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False
                })
        
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        for i in range(min(5, len(lista_e_te_gjithave))):
            lista_e_te_gjithave[i]["is_premium"] = True

        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup: ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        lista_finale = [{"liga": k, "ndeshjet": v} for k, v in ligat_grup.items()]
        lista_finale = sorted(lista_finale, key=lambda x: merr_rendesine_e_liges(x["liga"]))
        
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

@app.get("/api/detajet/{match_id}")
def merr_detajet_ndeshjes(match_id: int):
    url = "https://v3.football.api-sports.io/fixtures"
    try:
        response = requests.get(url, headers=HEADERS, params={"id": match_id})
        te_dhenat = response.json()
        if not te_dhenat.get("response"): return {"mesazhi": "Nuk u gjetën të dhëna"}
        ndeshja = te_dhenat["response"][0]
        events = ndeshja.get("events", [])
        statistics = ndeshja.get("statistics", [])
        lista_evente = []
        for ev in events:
            if ev['type'] in ['Goal', 'Card']:
                lista_evente.append({"koha": f"{ev['time']['elapsed']}'", "ekipi": ev['team']['name'], "lojtari": ev['player']['name'] if ev['player']['name'] else "Lojtar", "lloj": ev['type'], "detaj": ev['detail']})
        stats_formated = {}
        if statistics and len(statistics) >= 2:
            team1, team2 = statistics[0]['team']['name'], statistics[1]['team']['name']
            stats_formated = {"ekipi_1": team1, "ekipi_2": team2, "statistikat": []}
            if statistics[0].get('statistics') and statistics[1].get('statistics'):
                for i in range(len(statistics[0]['statistics'])):
                    if statistics[0]['statistics'][i]['type'] in ["Shots on Goal", "Ball Possession"]:
                        stats_formated["statistikat"].append({"