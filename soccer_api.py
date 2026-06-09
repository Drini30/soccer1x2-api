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

# ---------------------------------------------------------
# TRURI I PARASHIKIMEVE & TOP 5 PREMIUM
# ---------------------------------------------------------
def analizo_ndeshjen_premium(ekipi_1, ekipi_2):
    çelësi = f"{ekipi_1}-{ekipi_2}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    random.seed(çelësi)
    
    # 1. Koeficientët bazë
    koef_1 = round(random.uniform(1.40, 3.20), 2)
    koef_x = round(random.uniform(2.90, 4.20), 2)
    koef_2 = round(random.uniform(1.80, 4.50), 2)
    
    # 2. Përqindja e besueshmërisë së algoritmit (60% - 99%)
    besueshmeria = round(random.uniform(60.0, 99.0), 1)
    
    # 3. Simulimi i Rezultatit të Saktë për të nxjerrë "Informacionin e tërthortë"
    gola_1 = random.choices([0, 1, 2, 3], weights=[30, 40, 20, 10])[0]
    gola_2 = random.choices([0, 1, 2, 3], weights=[40, 35, 20, 5])[0]
    totali_gola = gola_1 + gola_2
    
    if gola_1 > gola_2:
        parashikimi = "1"
    elif gola_1 == gola_2:
        parashikimi = "X"
    else:
        parashikimi = "2"
        
    # Informacioni i tërthortë bazuar në golat e simuluar
    if totali_gola > 2.5:
        hint = "Ndeshje e hapur, priten mbi 2 gola total."
    elif totali_gola == 0:
        hint = "Ndeshje shumë e mbyllur, kujdes me golat."
    elif gola_1 > 0 and gola_2 > 0:
        hint = "Të dyja ekipet kanë potencial për të shënuar."
    else:
        hint = "Pritet dominim në fushë, nën 3 gola."
        
    return f"{koef_1:.2f}", f"{koef_x:.2f}", f"{koef_2:.2f}", parashikimi, hint, besueshmeria

# ---------------------------------------------------------
# RENDITJA VIP E LIGAVE
# ---------------------------------------------------------
LIGAT_KRYESORE = [
    "World Cup", "Euro Championship", "Champions League", "Europa League",
    "England - Premier League", "Spain - La Liga", "Italy - Serie A",
    "Germany - Bundesliga", "France - Ligue 1", "World - Friendlies",
    "World - UEFA Nations League", "Albania - Superliga"
]

def merr_rendesine_e_liges(emri_liges):
    for i, liga_top in enumerate(LIGAT_KRYESORE):
        if liga_top.lower() in emri_liges.lower():
            return i 
    return 999 

# ---------------------------------------------------------
# SKEDINA E DITËS
# ---------------------------------------------------------
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
        
        # 1. Mbledhim dhe analizojmë të gjitha ndeshjet
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
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
                    "is_premium": False # Do ta ndryshojmë më poshtë
                })
        
        # 2. GJEJMË TOP 5 NDESHJET ME BESUESHMËRINË MË TË LARTË (PAY PER MATCH)
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        for i in range(min(5, len(lista_e_te_gjithave))):
            lista_e_te_gjithave[i]["is_premium"] = True
            
        # 3. I grupojmë sërish sipas Ligave për t'ia nisur Netlify-t
        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup:
                ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        lista_finale = []
        for liga, ndeshjet_e_liges in ligat_grup.items():
            lista_finale.append({"liga": liga, "ndeshjet": ndeshjet_e_liges})
            
        lista_finale = sorted(lista_finale, key=lambda x: (merr_rendesine_e_liges(x["liga"]), x["liga"]))
            
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
        
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": [], "error_msg": "Gabim i brendshëm në server."}

@app.get("/api/live")
def merr_ndeshjet_live():
    return {"mesazhi": "Sukses", "ndeshjet": []}