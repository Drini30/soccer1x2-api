from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import random

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
SUPABASE_URL = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"
SUPABASE_ANON_KEY = "sb_publishable_zdg-Qz303Sf5VRTXy1msXA_0zyoEJ7y"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def ruaj_ne_sfond(paketa_per_db):
    if SUPABASE_ANON_KEY != "sb_publishable_zdg-Qz303Sf5VRTXy1msXA_0zyoEJ7y" and paketa_per_db:
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

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"}, timeout=8)
        te_dhenat = response.json()
        
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        # Tërheqja e koeficienteve kryesore (1X2) për ekranin e parë
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
                    koef_1 = bet365_odds[id_ndeshja]["1"]
                    koef_x = bet365_odds[id_ndeshja]["X"]
                    koef_2 = bet365_odds[id_ndeshja]["2"]
                else:
                    # Nese skemi koeficient
                    koef_1, koef_x, koef_2 = "N/A", "N/A", "N/A"

                data_sakte = data_target
                ora_sakte = "N/A"
                if n["fixture"]["date"]:
                    try:
                        d_obj = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S")
                        data_sakte = d_obj.strftime("%d/%m/%Y")
                        ora_sakte = d_obj.strftime("%H:%M")
                    except: pass

                # Sugjerimi bazik i AI per ekranin (Random i balancuar per momentin)
                random.seed(id_ndeshja)
                hint_id = random.randint(1, 4)

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "liga_id": liga_id, "sezoni": sezoni,
                    "ekipi_1_id": ekipi_1_id, "ekipi_2_id": ekipi_2_id,
                    "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte, "ora": "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte,
                    "statusi": statusi_kod, "minuta": minuta_loje, "rezultati": rezultati,
                    "koef_1": koef_1, "koef_x": koef_x, "koef_2": koef_2,
                    "hint_id": hint_id, "besueshmeria": 85.0, "rezultati_sakt": "1-0", "koef_rez_sakt": "7.50", "is_premium": False
                })
        
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
    # (Mbetet njësoj - Eventet dhe Statistikat)
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
                        stats_formated["statistikat"].append({"lloji": statistics[0]['statistics'][i]['type'], "vler_1": statistics[0]['statistics'][i]['value'] or 0, "vler_2": statistics[1]['statistics'][i]['value'] or 0})
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

# 🔥 FUNKSIONI I RI PER RENDITJEN E LIGES 🔥
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

# 🔥 KOEFICIENTËT E ZGJERUAR (MË SHUMË REZULTATE E GOLA) 🔥
@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    try:
        url = "https://v3.football.api-sports.io/odds"
        res = requests.get(url, headers=HEADERS, params={"fixture": match_id, "bookmaker": 8}, timeout=8)
        data = res.json()

        if not data.get("response"):
            return {"mesazhi": "S'ka Koeficientë Aktivë", "koeficientet": []}

        bets = data["response"][0]["bookmakers"][0]["bets"]
        tregjet_rezultat = []
        def get_bet(bet_id): return next((b for b in bets if b["id"] == bet_id), None)

        bet_13 = get_bet(13)
        if bet_13:
            tregjet_rezultat.append({"tregu_id": "ht_result", "opsionet": [{"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2"), "koef": v["odd"]} for v in bet_13["values"]]})

        bet_12 = get_bet(12)
        if bet_12:
            tregjet_rezultat.append({"tregu_id": "double_chance", "opsionet": [{"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]} for v in bet_12["values"]]})

        # Zgjerim i Golave Over/Under
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

        # Zgjerim i Rezultatit te Sakte (Me shume variacione)
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