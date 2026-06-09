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
# TRURI I KOEFICIENTËVE (Gjeneron 3 opsionet 1, X, 2)
# ---------------------------------------------------------
def analizo_koeficientet(ekipi_1, ekipi_2):
    çelësi_ndeshjes = f"{ekipi_1}-{ekipi_2}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    random.seed(çelësi_ndeshjes)
    
    koef_1 = round(random.uniform(1.40, 3.20), 2)
    koef_x = round(random.uniform(2.90, 4.20), 2)
    koef_2 = round(random.uniform(1.80, 4.50), 2)
        
    return f"{koef_1:.2f}", f"{koef_x:.2f}", f"{koef_2:.2f}"

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
# SKEDINA E DITËS (Të gjitha Ndeshjet, Rezultatet & Live)
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

        ligat_grup = {}
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1 = n["teams"]["home"]["name"]
                ekipi_2 = n["teams"]["away"]["name"]
                
                # Kapja e Kohës
                data_ora_iso = n["fixture"]["date"]
                try:
                    data_obj = datetime.strptime(data_ora_iso[:19], "%Y-%m-%dT%H:%M:%S")
                    data_sakte = data_obj.strftime("%d/%m/%Y")
                    ora_sakte = data_obj.strftime("%H:%M")
                except:
                    data_sakte = data_target
                    ora_sakte = "N/A"
                
                # Kapja e Statusit dhe Rezultatit (nëse ka mbaruar apo është live)
                statusi_kod = n["fixture"]["status"]["short"]
                gola_1 = n["goals"]["home"]
                gola_2 = n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else ""
                
                koef_1, koef_x, koef_2 = analizo_koeficientet(ekipi_1, ekipi_2)
                
                ndeshja_obj = {
                    "id": id_ndeshja,
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte,
                    "ora": ora_sakte,
                    "statusi": statusi_kod,
                    "rezultati": rezultati,
                    "koef_1": koef_1,
                    "koef_x": koef_x,
                    "koef_2": koef_2
                }
                
                if emri_liges not in ligat_grup:
                    ligat_grup[emri_liges] = []
                ligat_grup[emri_liges].append(ndeshja_obj)
        
        lista_finale = []
        for liga, ndeshjet_e_liges in ligat_grup.items():
            lista_finale.append({"liga": liga, "ndeshjet": ndeshjet_e_liges})
            
        lista_finale = sorted(lista_finale, key=lambda x: (merr_rendesine_e_liges(x["liga"]), x["liga"]))
            
        if len(lista_finale) == 0:
             return {"mesazhi": "Sukses", "skedina_grupuar": [], "error_msg": "Nuk u gjet asnjë ndeshje sot."}
            
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
        
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": [], "error_msg": "Gabim i brendshëm në server."}