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
        except:
            pass 

@app.get("/")
def root():
    return {"status": "online", "mesazhi": "Soccer1X2 API është aktiv dhe i lidhur me Supabase!"}

def merr_koeficientet_bet365(date_str):
    odds_map = {}
    try:
        url = "https://v3.football.api-sports.io/odds"
        res = requests.get(url, headers=HEADERS, params={"date": date_str, "bookmaker": 8, "page": 1}, timeout=10)
        data = res.json()
        
        def parse_odds(response_list):
            for item in response_list:
                fix_id = str(item["fixture"]["id"])
                try:
                    bets = item["bookmakers"][0]["bets"]
                    mw = next((b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"), None)
                    if mw:
                        v = mw["values"]
                        k1 = next((x["odd"] for x in v if x["value"] == "Home"), None)
                        kx = next((x["odd"] for x in v if x["value"] == "Draw"), None)
                        k2 = next((x["odd"] for x in v if x["value"] == "Away"), None)
                        if k1 and kx and k2:
                            odds_map[fix_id] = {"1": k1, "X": kx, "2": k2}
                except:
                    pass
                    
        if "response" in data:
            parse_odds(data["response"])
            total_pages = data.get("paging", {}).get("total", 1)
            pages_to_fetch = min(total_pages, 2)
            for p in range(2, pages_to_fetch + 1):
                res_p = requests.get(url, headers=HEADERS, params={"date": date_str, "bookmaker": 8, "page": p}, timeout=5)
                parse_odds(res_p.json().get("response", []))
    except Exception as e:
        print("Gabim me Bet365:", e)
    return odds_map

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
    random.seed(ekipi)
    return random.randint(65, 75)

def llogarit_intuiten_ekipit(ekipi, date_target, is_home):
    random.seed(f"form-{ekipi}-{date_target}")
    fuqia_baze = merr_fuqine_reale(ekipi)
    forma_piket = random.randint(2, 15) 
    fuqia_sulmuese = (fuqia_baze / 100) * round(random.uniform(1.5, 3.0), 2)
    dobesia_mbrojtese = ((100 - fuqia_baze) / 100) * round(random.uniform(1.0, 2.5), 2)
    avantazh_fushe = 1.10 if is_home else 1.00 
    
    ka_lendime = random.choices([True, False], weights=[15, 85])[0]
    penallti_lendimi = 1.00
    if ka_lendime:
        penallti_lendimi = 0.85 
        fuqia_sulmuese *= 0.85 
        
    fuqia_totale = ((fuqia_baze * 0.7) + (forma_piket * 2)) * avantazh_fushe * penallti_lendimi
    return forma_piket, fuqia_sulmuese, dobesia_mbrojtese, fuqia_totale

def analizo_ndeshjen_premium(match_id, ekipi_1, ekipi_2, date_target):
    form1, atk1, def1, power1 = llogarit_intuiten_ekipit(ekipi_1, date_target, is_home=True)
    form2, atk2, def2, power2 = llogarit_intuiten_ekipit(ekipi_2, date_target, is_home=False)
    
    diferenca = power1 - power2
    
    baza_k1 = 2.60 - (diferenca * 0.05)
    baza_k2 = 2.60 + (diferenca * 0.05)
    koef_1_sim = f"{round(max(1.20, min(8.00, baza_k1)), 2):.2f}"
    koef_2_sim = f"{round(max(1.20, min(8.00, baza_k2)), 2):.2f}"
    koef_x_sim = f"{round(random.uniform(3.10, 4.50), 2):.2f}"
    
    potenciali_gola_1 = max(0, int(atk1 - (def2 * 0.5) + (diferenca * 0.05)))
    potenciali_gola_2 = max(0, int(atk2 - (def1 * 0.5) - (diferenca * 0.05)))
    
    is_bluff = random.choices([True, False], weights=[35, 65])[0]
    
    if is_bluff and abs(diferenca) > 10: 
        if diferenca > 0:
            gola_1 = max(0, potenciali_gola_1 - random.randint(1, 2))
            gola_2 = potenciali_gola_2 + random.randint(1, 2)
        else:
            gola_1 = potenciali_gola_1 + random.randint(1, 2)
            gola_2 = max(0, potenciali_gola_2 - random.randint(1, 2))
            
        hint_id = random.choice([5, 6])
        besueshmeria = round(random.uniform(50.0, 70.0), 1) 
        koef_rez_sakt = round(random.uniform(15.00, 28.00), 2) 
    else:
        gola_1 = potenciali_gola_1
        gola_2 = potenciali_gola_2
        besueshmeria = round(min(65.0 + (abs(diferenca) * 1.5), 98.5), 1)
        koef_rez_sakt = round(random.uniform(5.00, 12.00), 2)
        
        totali_gola = gola_1 + gola_2
        if totali_gola > 2.5: hint_id = 1
        elif totali_gola == 0: hint_id = 2
        elif gola_1 > 0 and gola_2 > 0: hint_id = 3
        else: hint_id = 4
    
    if gola_1 > gola_2: parashikimi = "1"
    elif gola_1 == gola_2: parashikimi = "X"
    else: parashikimi = "2"
        
    rezultati_sakt = f"{gola_1}-{gola_2}"
        
    return koef_1_sim, koef_x_sim, koef_2_sim, parashikimi, hint_id, besueshmeria, rezultati_sakt, f"{koef_rez_sakt:.2f}"

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

        bet365_odds = merr_koeficientet_bet365(data_target)

        lista_e_te_gjithave = []
        paketa_per_db = []
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1_id = n["teams"]["home"]["id"]
                ekipi_2_id = n["teams"]["away"]["id"]
                ekipi_1 = n["teams"]["home"]["name"].replace("'", "")
                ekipi_2 = n["teams"]["away"]["name"].replace("'", "")
                
                statusi_kod = n["fixture"]["status"]["short"]
                minuta_loje = n["fixture"]["status"]["elapsed"] or 0
                gola_1 = n["goals"]["home"]
                gola_2 = n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else "0 - 0"
                
                k1_s, kx_s, k2_s, parashikimi_ai, hint_id, besueshmeria, rez_sakt, koef_rez_sakt = analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, data_target)
                
                if id_ndeshja in bet365_odds:
                    koef_1 = bet365_odds[id_ndeshja]["1"]
                    koef_x = bet365_odds[id_ndeshja]["X"]
                    koef_2 = bet365_odds[id_ndeshja]["2"]
                else:
                    koef_1 = k1_s
                    koef_x = kx_s
                    koef_2 = k2_s

                data_sakte = data_target
                ora_sakte = "N/A"
                if n["fixture"]["date"]:
                    try:
                        d_obj = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S")
                        data_sakte = d_obj.strftime("%d/%m/%Y")
                        ora_sakte = d_obj.strftime("%H:%M")
                    except: pass

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "ekipi_1_id": ekipi_1_id, "ekipi_2_id": ekipi_2_id,
                    "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte, "ora": "FT" if statusi_kod == "FT" else ora_sakte,
                    "statusi": statusi_kod, "minuta": minuta_loje, "rezultati": rezultati,
                    "koef_1": koef_1, "koef_x": koef_x, "koef_2": koef_2,
                    "parashikimi": parashikimi_ai, "hint_id": hint_id, "besueshmeria": besueshmeria,
                    "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False
                })
                
                paketa_per_db.append({"match_id": int(id_ndeshja), "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "predicted_score": rez_sakt})
        
        if paketa_per_db:
            background_tasks.add_task(ruaj_ne_sfond, paketa_per_db)
        
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
                lista_evente.append({
                    "koha": f"{ev['time']['elapsed']}'", "ekipi": ev['team']['name'],
                    "lojtari": ev['player']['name'] if ev['player']['name'] else "Lojtar",
                    "lloj": ev['type'], "detaj": ev['detail']
                })
        
        stats_formated = {}
        if statistics and len(statistics) >= 2:
            team1 = statistics[0]['team']['name']
            team2 = statistics[1]['team']['name']
            stats_formated = {"ekipi_1": team1, "ekipi_2": team2, "statistikat": []}
            kriteret = ["Shots on Goal", "Ball Possession"]
            if statistics[0].get('statistics') and statistics[1].get('statistics'):
                for i in range(len(statistics[0]['statistics'])):
                    stat_name = statistics[0]['statistics'][i]['type']
                    if stat_name in kriteret:
                        val1 = statistics[0]['statistics'][i]['value']
                        val2 = statistics[1]['statistics'][i]['value']
                        if val1 is None: val1 = 0
                        if val2 is None: val2 = 0
                        stats_formated["statistikat"].append({"lloji": stat_name, "vler_1": val1, "vler_2": val2})
        return {"mesazhi": "Sukses", "evente": lista_evente, "statistika": stats_formated}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/historia/{team_id}")
def merr_historine(team_id: int):
    url = "https://v3.football.api-sports.io/fixtures"
    try:
        response = requests.get(url, headers=HEADERS, params={"team": team_id, "last": 5})
        te_dhenat = response.json()
        rezultati_hist = []
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                home_name = n["teams"]["home"]["name"]
                away_name = n["teams"]["away"]["name"]
                score = n.get("score", {})
                ht = score.get("halftime", {})
                ft = score.get("fulltime", {})
                ht_str = f"{ht.get('home')}-{ht.get('away')}" if ht and ht.get('home') is not None else "0-0"
                ft_str = f"{ft.get('home')}-{ft.get('away')}" if ft and ft.get('home') is not None else "0-0"
                random.seed(n["fixture"]["id"])
                koef_1 = f"{round(random.uniform(1.40, 2.90), 2)}"
                koef_x = f"{round(random.uniform(2.80, 3.80), 2)}"
                koef_2 = f"{round(random.uniform(1.90, 4.20), 2)}"
                try: data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
                except: data_sakte = "N/A"
                rezultati_hist.append({"data": data_sakte, "ora": "FT", "ndeshja": f"{home_name} vs {away_name}", "ht": ht_str, "ft": ft_str, "koef_1": koef_1, "koef_x": koef_x, "koef_2": koef_2})
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e)}

# 🔥 MAGJIA E RE: KOEFICIENTËT REALË TË BET365 NË POP-UP 🔥
@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    try:
        url = "https://v3.football.api-sports.io/odds"
        # Bëjmë 1 kërkesë ekzakte për këtë ndeshje te Bet365 (bookmaker=8)
        res = requests.get(url, headers=HEADERS, params={"fixture": match_id, "bookmaker": 8}, timeout=8)
        data = res.json()

        if not data.get("response"):
            # Nese Bet365 nuk ka koeficiente per kete ndeshje (psh. ka mbaruar), i simulojme qe klienti te mos shohe bosh
            random.seed(match_id)
            return {
                "mesazhi": "Simuluar (Ndeshja s'ka koeficientë aktivë)",
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

        def get_bet(bet_id):
            return next((b for b in bets if b["id"] == bet_id), None)

        # 1. Pjesa e Pare (HT) - API id 13
        bet_13 = get_bet(13)
        if bet_13:
            ops = []
            for v in bet_13["values"]:
                emer = v["value"].replace("Home", "1").replace("Draw", "X").replace("Away", "2") + " (HT)"
                ops.append({"emer": emer, "koef": v["odd"]})
            tregjet_rezultat.append({"tregu_id": "ht_result", "opsionet": ops})

        # 2. Double Chance - API id 12
        bet_12 = get_bet(12)
        if bet_12:
            ops = []
            for v in bet_12["values"]:
                emer = v["value"].replace("Home/Draw", "1X").replace("Home/Away", "12").replace("Draw/Away", "X2")
                ops.append({"emer": emer, "koef": v["odd"]})
            tregjet_rezultat.append({"tregu_id": "double_chance", "opsionet": ops})

        # 3. Over/Under Goals - API id 5 (Zgjedhim 1.5, 2.5, 3.5 qe te mos dalin 50 opsione)
        bet_5 = get_bet(5)
        if bet_5:
            ops_25 = []
            ops_other = []
            for v in bet_5["values"]:
                if v["value"] == "Over 2.5": ops_25.append({"emer": "Mbi 2.5", "koef": v["odd"]})
                if v["value"] == "Under 2.5": ops_25.append({"emer": "Nën 2.5", "koef": v["odd"]})
                if v["value"] == "Over 3.5": ops_other.append({"emer": "Mbi 3.5", "koef": v["odd"]})
                if v["value"] == "Under 3.5": ops_other.append({"emer": "Nën 3.5", "koef": v["odd"]})
                if v["value"] == "Over 1.5": ops_other.append({"emer": "Mbi 1.5", "koef": v["odd"]})
                if v["value"] == "Under 1.5": ops_other.append({"emer": "Nën 1.5", "koef": v["odd"]})
            if ops_25: tregjet_rezultat.append({"tregu_id": "goals_25", "opsionet": ops_25})
            if ops_other: tregjet_rezultat.append({"tregu_id": "goals_35_65", "opsionet": ops_other[:4]}) # Shfaqim vetem 4 te tjerat

        # 4. BTTS (Të Dyja Shënojnë) - API id 8
        bet_8 = get_bet(8)
        if bet_8:
            ops = []
            for v in bet_8["values"]:
                emer = "Po (GG)" if v["value"] == "Yes" else "Jo (NG)"
                ops.append({"emer": emer, "koef": v["odd"]})
            tregjet_rezultat.append({"tregu_id": "btts", "opsionet": ops})

        # 5. HT/FT - API id 15
        bet_15 = get_bet(15)
        if bet_15:
            ops = []
            pop_htft = ["Home/Home", "Draw/Home", "Away/Away", "Draw/Draw"]
            for v in bet_15["values"]:
                if v["value"] in pop_htft:
                    emer = v["value"].replace("Home", "1").replace("Draw", "X").replace("Away", "2")
                    ops.append({"emer": emer, "koef": v["odd"]})
            if ops: tregjet_rezultat.append({"tregu_id": "ht_ft", "opsionet": ops})

        # 6. Correct Score - API id 10
        bet_10 = get_bet(10)
        if bet_10:
            ops = []
            popular = ["1:0", "2:0", "2:1", "0:0", "1:1", "0:1", "1:2"]
            for v in bet_10["values"]:
                if v["value"] in popular:
                    ops.append({"emer": v["value"].replace(":", "-"), "koef": v["odd"]})
            if ops: tregjet_rezultat.append({"tregu_id": "correct_score", "opsionet": ops})

        return {"mesazhi": "Sukses", "koeficientet": tregjet_rezultat}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "koeficientet": []}

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}