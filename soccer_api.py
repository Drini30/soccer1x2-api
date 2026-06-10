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

# 🔥 KONFIGURIMI I DATABAZËS SUPABASE (I RREGULLUAR) 🔥
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

TAKTIKAT = {
    "4-3-3": {"atk": 1.15, "def_fortitude": 0.90},  
    "3-4-3": {"atk": 1.20, "def_fortitude": 0.85},  
    "4-4-2": {"atk": 1.00, "def_fortitude": 1.00},  
    "4-2-3-1": {"atk": 1.05, "def_fortitude": 1.05}, 
    "3-5-2": {"atk": 1.10, "def_fortitude": 0.95},  
    "5-3-2": {"atk": 0.80, "def_fortitude": 1.20},  
    "5-4-1": {"atk": 0.70, "def_fortitude": 1.30},  
}

def merr_fuqine_reale(ekipi):
    for emri, fuqia in GIGANTET.items():
        if emri.lower() in ekipi.lower(): return fuqia
    return 70

def parashiko_formacionin(fuqia_ime, fuqia_kundershtarit, is_home):
    diferenca = fuqia_ime - fuqia_kundershtarit
    if diferenca >= 15:
        return random.choice(["4-3-3", "3-4-3", "4-2-3-1"])
    elif diferenca <= -15:
        return random.choice(["5-4-1", "5-3-2", "4-4-2"])
    else:
        if is_home: return random.choice(["4-3-3", "4-2-3-1", "3-5-2"])
        else: return random.choice(["4-4-2", "4-2-3-1", "5-3-2"])

# 🔥 ALGORITMI I ZBRETUR ME FAKTORIN BLLOF HISTORIK (20-30%) 🔥
def analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, k1_str, kx_str, k2_str):
    try:
        k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)
    except:
        k1, kx, k2 = 2.60, 3.10, 2.60 

    prob_1 = 1 / k1
    prob_x = 1 / kx
    prob_2 = 1 / k2
    marzhi = prob_1 + prob_x + prob_2 
    p1_real, px_real, p2_real = prob_1 / marzhi, prob_x / marzhi, prob_2 / marzhi

    fuqia_1 = merr_fuqine_reale(ekipi_1)
    fuqia_2 = merr_fuqine_reale(ekipi_2)
    diferenca_fuqise = (fuqia_1 - fuqia_2) / 100.0

    form_1 = parashiko_formacionin(fuqia_1, fuqia_2, is_home=True)
    form_2 = parashiko_formacionin(fuqia_2, fuqia_1, is_home=False)
    
    t1_atk = TAKTIKAT[form_1]["atk"]
    t1_def = TAKTIKAT[form_1]["def_fortitude"]
    t2_atk = TAKTIKAT[form_2]["atk"]
    t2_def = TAKTIKAT[form_2]["def_fortitude"]

    # 1. Gjurmimi i prirjes historike për gafë (Ndarë mes 20% dhe 30%)
    random.seed(f"gafa-{ekipi_1}")
    prirja_historike_bllof = random.randint(20, 30) 

    # 2. Shansi i ndeshjes aktuale për të qenë kurth
    random.seed(f"kurth-{id_ndeshja}")
    shansi_aktual_kurth = random.randint(1, 100)

    eshte_ndeshje_bllof = False
    # Nëse ka një favorit të fortë por shansi i ditës kap prirjen historike të gafës
    if (k1 < 1.55 or k2 < 1.55) and (shansi_aktual_kurth <= prirja_historike_bllof):
        eshte_ndeshje_bllof = True

    # 3. Ndërtimi i xG (Expected Goals)
    xg_1_baze = max(0.1, (p1_real * 2.6) + (diferenca_fuqise * 0.8))
    xg_2_baze = max(0.1, (p2_real * 2.6) - (diferenca_fuqise * 0.8))

    if eshte_ndeshje_bllof:
        # Përmbysim logjikën e golave: favoriti bllokohet, autsajderi merr fuqi
        if k1 < 1.55:
            xg_1 = xg_1_baze * 0.45 # Sulmi i favoritit Vritet me më shumë se gjysmën
            xg_2 = xg_2_baze * 1.85 # Autsajderi shpërthen në kundërsulm
        else:
            xg_1 = xg_1_baze * 1.85
            xg_2 = xg_2_baze * 0.45
        hint_id = random.choice([5, 6]) # Aktivizojmë sinjalin Faktori Risk / Zonë e Kuqe
    else:
        # Logjika normale e balancuar
        xg_1 = xg_1_baze * 1.15 * t1_atk * (1 / t2_def)
        xg_2 = xg_2_baze * 0.90 * t2_atk * (1 / (t1_def * 1.10))
        
        if p1_real > 0.65 or p2_real > 0.65: hint_id = 4 
        elif xg_1 > 1.4 and xg_2 > 1.4: hint_id = 3 
        else: hint_id = 1

    # 4. Shpërndarja Poisson
    def poisson(lmbda, k): return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)

    rezultati_sakt = "0-0"
    max_prob = 0

    for g1 in range(6):
        for g2 in range(6):
            prob_score = poisson(xg_1, g1) * poisson(xg_2, g2)
            
            # Nëse është bllof, lejojmë që autsajderi të fitojë ose barazojë në parashikim
            if not eshte_ndeshje_bllof:
                if p1_real > p2_real + 0.15 and g1 <= g2: continue
                if p2_real > p1_real + 0.15 and g2 <= g1: continue
            
            if prob_score > max_prob:
                max_prob = prob_score
                rezultati_sakt = f"{g1}-{g2}"
    
    koef_rez_sakt = min(40.0, (1 / max_prob) * 0.85) if max_prob > 0 else 10.0
    
    # Nëse është bllof, ulim besueshmërinë e skedines që përdoruesi ta shohë rrezikun
    if eshte_ndeshje_bllof:
        besueshmeria = round(random.uniform(55.0, 64.5), 1)
    else:
        besueshmeria = round(min(98.5, max(65.0, (max(p1_real, p2_real) * 100) + (abs(diferenca_fuqise)*15))), 1)
    
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

                # Thirrja e Algoritmit të ri me id_ndeshja brenda
                hint_id, besueshmeria, rez_sakt, koef_rez_sakt = \
                    analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, koef_1, koef_x, koef_2)

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
                        stats_formated["statistikat"].append({
                            "lloji": statistics[0]['statistics'][i]['type'], 
                            "vler_1": statistics[0]['statistics'][i]['value'] or 0, 
                            "vler_2": statistics[1]['statistics'][i]['value'] or 0
                        })
        return {"mesazhi": "Sukses", "evente": lista_evente, "statistika": stats_formated}
    except: return {"mesazhi": "Gabim"}

@app.get("/api/historia/{team_id}")
def merr_historine(team_id: int):
    url = "https://v3.football.api-sports.io/fixtures"
    try:
        response = requests.get(url, headers=HEADERS, params={"team": team_id, "last": 5})
        rezultati_hist = []
        for n in response.json().get("response", []):
            ht = n.get("score", {}).get("halftime", {})
            ft = n.get("score", {}).get("fulltime", {})
            ht_str = f"{ht.get('home')}-{ht.get('away')}" if ht and ht.get('home') is not None else "0-0"
            ft_str = f"{ft.get('home')}-{ft.get('away')}" if ft and ft.get('home') is not None else "0-0"
            try: data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
            except: data_sakte = "N/A"
            rezultati_hist.append({"data": data_sakte, "ora": "FT", "ndeshja": f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}", "ht": ht_str, "ft": ft_str})
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/renditja/{league_id}/{season}")
def merr_renditjen(league_id: int, season: int):
    url = "https://v3.football.api-sports.io/standings"
    try:
        res = requests.get(url, headers=HEADERS, params={"league": league_id, "season": season}, timeout=8)
        data = res.json()
        renditja_list = []
        if "response" in data and len(data["response"]) > 0:
            standings = data["response"][0]["league"]["standings"][0]
            for rank in standings:
                renditja_list.append({
                    "pozicioni": rank["rank"],
                    "ekipi": rank["team"]["name"],
                    "piket": rank["points"],
                    "ndeshje": rank["all"]["played"],
                    "gola": f"{rank['all']['goals']['for']}:{rank['all']['goals']['against']}",
                    "forma": rank["form"]
                })
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
            return {
                "mesazhi": "Simuluar",
                "koeficientet": [
                    {"tregu_id": "ht_result", "opsionet": [{"emer": "1 (HT)", "koef": round(random.uniform(1.80, 4.50), 2)}, {"emer": "X (HT)", "koef": round(random.uniform(1.65, 2.40), 2)}, {"emer": "2 (HT)", "koef": round(random.uniform(2.10, 5.20), 2)}]},
                    {"tregu_id": "double_chance", "opsionet": [{"emer": "1X", "koef": round(random.uniform(1.10, 1.50), 2)}, {"emer": "12", "koef": round(random.uniform(1.20, 1.40), 2)}, {"emer": "X2", "koef": round(random.uniform(1.15, 1.80), 2)}]},
                    {"tregu_id": "goals_25", "opsionet": [{"emer": "Mbi 2.5", "koef": round(random.uniform(1.50, 2.20), 2)}, {"emer": "Nën 2.5", "koef": round(random.uniform(1.60, 2.10), 2)}]},
                    {"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)", "koef": round(random.uniform(1.60, 2.00), 2)}, {"emer": "Jo (NG)", "koef": round(random.uniform(1.70, 2.20), 2)}]},
                    {"tregu_id": "correct_score", "opsionet": [{"emer": "1-0", "koef": round(random.uniform(5.50, 11.00), 2)}, {"emer": "2-0", "koef": round(random.uniform(6.50, 14.00), 2)}, {"emer": "2-1", "koef": round(random.uniform(7.50, 13.50), 2)}, {"emer": "1-1", "koef": round(random.uniform(5.00, 8.50), 2)}]}
                ]
            }

        bets = data["response"][0]["bookmakers"][0]["bets"]
        tregjet_rezultat = []
        def get_bet(bet_id): return next((b for b in bets if b["id"] == bet_id), None)

        bet_13 = get_bet(13)
        if bet_13:
            tregjet_rezultat.append({"tregu_id": "ht_result", "opsionet": [{"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]} for v in bet_13["values"]]})

        bet_12 = get_bet(12)
        if bet_12:
            tregjet_rezultat.append({"tregu_id": "double_chance", "opsionet": [{"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]} for v in bet_12["values"]]})

        bet_5 = get_bet(5)
        if bet_5:
            ops_gola = []
            allowed_goals = ["0.5", "1.5", "2.5", "3.5", "4.5", "5.5"]
            for v in bet_5["values"]:
                for g in allowed_goals:
                    if f"Over {g}" == v["value"]: ops_gola.append({"emer": f"Mbi {g}", "koef": v["odd"]})
                    if f"Under {g}" == v["value"]: ops_gola.append({"emer": f"Nën {g}", "koef": v["odd"]})
            if ops_gola: tregjet_rezultat.append({"tregu_id": "goals_35_65", "opsionet": ops_gola})

        bet_8 = get_bet(8)
        if bet_8:
            tregjet_rezultat.append({"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)" if v["value"]=="Yes" else "Jo (NG)", "koef": v["odd"]} for v in bet_8["values"]]})

        bet_10 = get_bet(10)
        if bet_10:
            ops_score = []
            pop_scores = ["1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "0:0", "1:1", "2:2", "3:3", "0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4"]
            for v in bet_10["values"]:
                if v["value"] in pop_scores:
                    ops_score.append({"emer": v["value"].replace(":", "-"), "koef": v["odd"]})
            if ops_score: tregjet_rezultat.append({"tregu_id": "correct_score", "opsionet": ops_score})

        return {"mesazhi": "Sukses", "koeficientet": tregjet_rezultat}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "koeficientet": []}

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}