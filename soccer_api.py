from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import random
import asyncio

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

# 🔥 KONFIGURIMI I DATABAZËS TËNDE SUPABASE 🔥
SUPABASE_URL = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"
SUPABASE_ANON_KEY = "sb_publishable_zdg-Qz303Sf5VRTXy1msXA_0zyoEJ7y"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# Funksioni super i sigurt për sfondin
def ruaj_ne_sfond(te_dhenat_per_db):
    if SUPABASE_ANON_KEY != "VENDOS_KODIN_TËND_KËTU" and te_dhenat_per_db:
        # Përpiqemi të mos dërgojmë gjithçka përnjëherë që të mos bllokohet
        for pako in te_dhenat_per_db[:10]: # Ruajmë vetëm 10 të parat për test
            try:
                requests.post(SUPABASE_URL, headers=SUPABASE_HEADERS, json=pako, timeout=2)
            except Exception as e:
                print(f"Gabim në sfond: {e}")
                break # Nëse ka gabim, ndalojmë për të mos mbingarkuar serverin

@app.get("/")
def root():
    return {"status": "online", "mesazhi": "Soccer1X2 API është aktiv dhe gati!"}

def llogarit_intuiten_ekipit(ekipi, date_target, is_home):
    random.seed(f"form-{ekipi}-{date_target}")
    forma_piket = random.randint(2, 15) 
    fuqia_sulmuese = round(random.uniform(0.5, 3.0), 2)
    dobesia_mbrojtese = round(random.uniform(0.5, 2.5), 2)
    avantazh_fushe = 1.15 if is_home else 1.00 
    
    ka_lendime = random.choices([True, False], weights=[15, 85])[0]
    penallti_lendimi = 1.00
    
    if ka_lendime:
        penallti_lendimi = 0.85 
        fuqia_sulmuese = fuqia_sulmuese * 0.80 
        
    fuqia_totale = (((forma_piket * 0.4) + (fuqia_sulmuese * 2) - dobesia_mbrojtese) * avantazh_fushe) * penallti_lendimi
    return forma_piket, fuqia_sulmuese, dobesia_mbrojtese, fuqia_totale

def analizo_ndeshjen_premium(match_id, ekipi_1, ekipi_2, date_target):
    form1, atk1, def1, power1 = llogarit_intuiten_ekipit(ekipi_1, date_target, is_home=True)
    form2, atk2, def2, power2 = llogarit_intuiten_ekipit(ekipi_2, date_target, is_home=False)
    
    diferenca = abs(power1 - power2)
    besueshmeria = round(min(65.0 + (diferenca * 3), 98.5), 1)
    
    potenciali_gola_1 = max(0, int(atk1 - (def2 * 0.5) + random.uniform(-0.5, 1.5)))
    potenciali_gola_2 = max(0, int(atk2 - (def1 * 0.5) + random.uniform(-0.5, 1.0))) 
    
    gola_1 = potenciali_gola_1
    gola_2 = potenciali_gola_2
    totali_gola = gola_1 + gola_2
    
    if gola_1 > gola_2: parashikimi = "1"
    elif gola_1 == gola_2: parashikimi = "X"
    else: parashikimi = "2"
        
    if totali_gola > 2.5: hint_id = 1
    elif totali_gola == 0: hint_id = 2
    elif gola_1 > 0 and gola_2 > 0: hint_id = 3
    else: hint_id = 4
    
    rezultati_sakt = f"{gola_1}-{gola_2}"
    
    baza_koef = 2.80
    koef_1 = max(1.15, baza_koef - (power1 - power2) * 0.2)
    koef_2 = max(1.20, baza_koef - (power2 - power1) * 0.2)
    koef_x = max(2.50, 4.00 - diferenca * 0.15)
    
    koef_rez_sakt = round(random.uniform(5.00, 18.00), 2)
        
    return f"{koef_1:.2f}", f"{koef_x:.2f}", f"{koef_2:.2f}", parashikimi, hint_id, besueshmeria, rezultati_sakt, f"{koef_rez_sakt:.2f}"

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    if date:
        data_target = date
    else:
        data_target = datetime.utcnow().strftime('%Y-%m-%d')
        
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"})
        te_dhenat = response.json()
        
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        lista_e_te_gjithave = []
        paketa_per_databazen = [] 
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1_id = n["teams"]["home"]["id"]
                ekipi_2_id = n["teams"]["away"]["id"]
                ekipi_1 = n["teams"]["home"]["name"].replace("'", "")
                ekipi_2 = n["teams"]["away"]["name"].replace("'", "")
                
                data_ora_iso = n["fixture"]["date"]
                try:
                    data_obj = datetime.strptime(data_ora_iso[:19], "%Y-%m-%dT%H:%M:%S")
                    data_sakte = data_obj.strftime("%d/%m/%Y")
                    ora_sakte = data_obj.strftime("%H:%M")
                except:
                    data_sakte = data_target
                    ora_sakte = "N/A"
                
                statusi_kod = n["fixture"]["status"]["short"]
                minuta_loje = n["fixture"]["status"]["elapsed"] or 0
                
                gola_1 = n["goals"]["home"]
                gola_2 = n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else "0 - 0"
                
                koef_1, koef_x, koef_2, parashikimi_ai, hint_id, besueshmeria, rez_sakt, koef_rez_sakt = analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, data_target)
                
                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "ekipi_1_id": ekipi_1_id, "ekipi_2_id": ekipi_2_id,
                    "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte, "ora": "FT" if statusi_kod == "FT" else ora_sakte,
                    "statusi": statusi_kod, "minuta": minuta_loje, "rezultati": rezultati,
                    "koef_1": koef_1, "koef_x": koef_x, "koef_2": koef_2,
                    "parashikimi": parashikimi_ai, "hint_id": hint_id, "besueshmeria": besueshmeria,
                    "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False
                })
                
                # Shtojmë të dhënat në pako
                paketa_per_databazen.append({
                    "match_id": int(id_ndeshja),
                    "ekipi_1": ekipi_1,
                    "ekipi_2": ekipi_2,
                    "predicted_score": rez_sakt
                })
        
        # Super e rëndësishme: Dërgo në sfond vetëm nëse aplikacioni ngarkohet OK
        if paketa_per_databazen:
            background_tasks.add_task(ruaj_ne_sfond, paketa_per_databazen)
        
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        for i in range(min(5, len(lista_e_te_gjithave))):
            lista_e_te_gjithave[i]["is_premium"] = True
            
        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup: ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        lista_finale = []
        for liga, ndeshjet_e_liges in ligat_grup.items():
            lista_finale.append({"liga": liga, "ndeshjet": ndeshjet_e_liges})
            
        lista_finale = sorted(lista_finale, key=lambda x: (x["liga"]))
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

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    random.seed(match_id)
    return {
        "mesazhi": "Sukses",
        "koeficientet": [
            {"tregu_id": "ht_result", "opsionet": [{"emer": "1 (HT)", "koef": round(random.uniform(1.80, 4.50), 2)}, {"emer": "X (HT)", "koef": round(random.uniform(1.65, 2.40), 2)}, {"emer": "2 (HT)", "koef": round(random.uniform(2.10, 5.20), 2)}]},
            {"tregu_id": "double_chance", "opsionet": [{"emer": "1X", "koef": round(random.uniform(1.10, 1.50), 2)}, {"emer": "12", "koef": round(random.uniform(1.20, 1.40), 2)}, {"emer": "X2", "koef": round(random.uniform(1.15, 1.80), 2)}]},
            {"tregu_id": "ht_ft", "opsionet": [{"emer": "1/1", "koef": round(random.uniform(2.50, 4.50), 2)}, {"emer": "X/1", "koef": round(random.uniform(4.00, 7.50), 2)}, {"emer": "2/2", "koef": round(random.uniform(3.50, 6.50), 2)}, {"emer": "X/X", "koef": round(random.uniform(4.50, 6.00), 2)}]},
            {"tregu_id": "goals_25", "opsionet": [{"emer": "Mbi 2.5", "koef": round(random.uniform(1.50, 2.20), 2)}, {"emer": "Nën 2.5", "koef": round(random.uniform(1.60, 2.10), 2)}]},
            {"tregu_id": "goals_35_65", "opsionet": [{"emer": "Mbi 3.5", "koef": round(random.uniform(2.30, 4.50), 2)}, {"emer": "Nën 3.5", "koef": round(random.uniform(1.20, 1.55), 2)}, {"emer": "Mbi 6.5", "koef": round(random.uniform(6.50, 16.00), 2)}, {"emer": "Nën 6.5", "koef": round(random.uniform(1.01, 1.08), 2)}]},
            {"tregu_id": "btts", "opsionet": [{"emer": "Po (GG)", "koef": round(random.uniform(1.60, 2.00), 2)}, {"emer": "Jo (NG)", "koef": round(random.uniform(1.70, 2.20), 2)}]},
            {"tregu_id": "exact_goals", "opsionet": [{"emer": "0", "koef": round(random.uniform(7.00, 12.00), 2)}, {"emer": "1", "koef": round(random.uniform(4.00, 6.50), 2)}, {"emer": "2", "koef": round(random.uniform(3.20, 4.50), 2)}, {"emer": "3+", "koef": round(random.uniform(2.00, 3.80), 2)}]},
            {"tregu_id": "odd_even", "opsionet": [{"emer": "Tek (Odd)", "koef": round(random.uniform(1.85, 1.95), 2)}, {"emer": "Çift (Even)", "koef": round(random.uniform(1.85, 1.95), 2)}]},
            {"tregu_id": "correct_score", "opsionet": [{"emer": "1-0", "koef": round(random.uniform(5.50, 11.00), 2)}, {"emer": "2-0", "koef": round(random.uniform(6.50, 14.00), 2)}, {"emer": "2-1", "koef": round(random.uniform(7.50, 13.50), 2)}, {"emer": "0-0", "koef": round(random.uniform(7.00, 12.00), 2)}, {"emer": "1-1", "koef": round(random.uniform(5.00, 8.50), 2)}, {"emer": "0-1", "koef": round(random.uniform(7.50, 15.00), 2)}, {"emer": "1-2", "koef": round(random.uniform(8.50, 17.00), 2)}, {"emer": "Tjetër", "koef": round(random.uniform(4.50, 7.50), 2)}]}
        ]
    }

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}