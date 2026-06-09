from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import random

app = FastAPI(title="SOCCER 1X2 API", description="AI për Skedinën e Ditës dhe Ndeshjet LIVE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

def analizo_ndeshjen_premium(ekipi_1, ekipi_2):
    çelësi = f"{ekipi_1}-{ekipi_2}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    random.seed(çelësi)
    koef_1 = round(random.uniform(1.40, 3.20), 2)
    koef_x = round(random.uniform(2.90, 4.20), 2)
    koef_2 = round(random.uniform(1.80, 4.50), 2)
    besueshmeria = round(random.uniform(60.0, 99.0), 1)
    
    gola_1 = random.choices([0, 1, 2, 3], weights=[30, 40, 20, 10])[0]
    gola_2 = random.choices([0, 1, 2, 3], weights=[40, 35, 20, 5])[0]
    totali_gola = gola_1 + gola_2
    
    if gola_1 > gola_2: parashikimi = "1"
    elif gola_1 == gola_2: parashikimi = "X"
    else: parashikimi = "2"
        
    if totali_gola > 2.5: hint = "Ndeshje e hapur, priten mbi 2 gola total."
    elif totali_gola == 0: hint = "Ndeshje shumë e mbyllur, kujdes me golat."
    elif gola_1 > 0 and gola_2 > 0: hint = "Të dyja ekipet kanë potencial për të shënuar."
    else: hint = "Pritet dominim në fushë, nën 3 gola."
        
    return f"{koef_1:.2f}", f"{koef_x:.2f}", f"{koef_2:.2f}", parashikimi, hint, besueshmeria

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
def merr_parashikimet():
    data_target = datetime.utcnow().strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target})
        te_dhenat = response.json()
        
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        lista_e_te_gjithave = []
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                
                # Ruajmë ID-të e ekipeve për Pop-up-in
                ekipi_1_id = n["teams"]["home"]["id"]
                ekipi_2_id = n["teams"]["away"]["id"]
                ekipi_1 = n["teams"]["home"]["name"]
                ekipi_2 = n["teams"]["away"]["name"]
                
                data_ora_iso = n["fixture"]["date"]
                try:
                    data_obj = datetime.strptime(data_ora_iso[:19], "%Y-%m-%dT%H:%M:%S")
                    data_sakte = data_obj.strftime("%d/%m/%Y")
                    ora_sakte = data_obj.strftime("%H:%M")
                except:
                    data_sakte = data_target
                    ora_sakte = "N/A"
                
                statusi_kod = n["fixture"]["status"]["short"]
                gola_1 = n["goals"]["home"]
                gola_2 = n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else ""
                
                koef_1, koef_x, koef_2, parashikimi_ai, hint_ai, besueshmeria = analizo_ndeshjen_premium(ekipi_1, ekipi_2)
                
                lista_e_te_gjithave.append({
                    "id": id_ndeshja,
                    "liga_emri": emri_liges,
                    "ekipi_1_id": ekipi_1_id,
                    "ekipi_2_id": ekipi_2_id,
                    "ekipi_1": ekipi_1,
                    "ekipi_2": ekipi_2,
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte,
                    "ora": ora_sakte,
                    "statusi": statusi_kod,
                    "rezultati": rezultati,
                    "koef_1": koef_1,
                    "koef_x": koef_x,
                    "koef_2": koef_2,
                    "parashikimi": parashikimi_ai,
                    "hint": hint_ai,
                    "besueshmeria": besueshmeria,
                    "is_premium": False
                })
        
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
            
        lista_finale = sorted(lista_finale, key=lambda x: (merr_rendesine_e_liges(x["liga"]), x["liga"]))
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

# API I RI PËR POP-UP (5 NDESHJET E FUNDIT)
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
                
                ht_h = ht.get("home") if ht else None
                ht_a = ht.get("away") if ht else None
                ft_h = ft.get("home") if ft else None
                ft_a = ft.get("away") if ft else None
                
                ht_str = f"{ht_h}-{ht_a}" if ht_h is not None else "?-?"
                ft_str = f"{ft_h}-{ft_a}" if ft_h is not None else "?-?"
                
                if ft_h is not None and ft_a is not None:
                    if ft_h > ft_a: rez_1x2 = "1"
                    elif ft_h == ft_a: rez_1x2 = "X"
                    else: rez_1x2 = "2"
                else: rez_1x2 = "?"
                    
                random.seed(n["fixture"]["id"])
                koef = f"{round(random.uniform(1.50, 4.00), 2)}"
                data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
                
                rezultati_hist.append({
                    "data": data_sakte,
                    "ndeshja": f"{home_name} vs {away_name}",
                    "ht": ht_str,
                    "ft": ft_str,
                    "rezultati": rez_1x2,
                    "koeficienti": koef
                })
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/live")
def merr_ndeshjet_live():
    return {"mesazhi": "Sukses", "ndeshjet": []}