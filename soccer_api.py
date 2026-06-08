from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
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
# TRURI I PARASHIKIMEVE (Algoritmi i Përkohshëm)
# ---------------------------------------------------------
def analizo_ndeshjen(ekipi_1, ekipi_2):
    """
    Ky funksion merr dy ekipet dhe nxjerr një parashikim të qëndrueshëm logjik.
    Më vonë, kjo pjesë do të zëvendësohet nga modeli i vërtetë i Machine Learning.
    """
    # Krijojmë një çelës unik për këtë ndeshje që parashikimi të mos ndryshojë sa herë bëjmë refresh
    çelësi_ndeshjes = f"{ekipi_1}-{ekipi_2}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    random.seed(çelësi_ndeshjes)
    
    # Probabilitetet e basteve: Favorizojmë pak më shumë fitoren e vendasve (1) ose (1X)
    opsionet = ["1", "X", "2", "1X", "X2", "12"]
    peshat = [35, 20, 15, 15, 10, 5] 
    
    parashikimi = random.choices(opsionet, weights=peshat, k=1)[0]
    
    # Gjenerojmë një koeficient logjik bazuar tek lloji i parashikimit
    if parashikimi == "1" or parashikimi == "2":
        koeficienti = round(random.uniform(1.40, 2.60), 2)
    elif parashikimi == "X":
        koeficienti = round(random.uniform(2.80, 3.80), 2)
    else: # Për shanset e dyfishta (1X, X2, 12) koeficientët janë më të vegjël
        koeficienti = round(random.uniform(1.15, 1.65), 2)
        
    return parashikimi, f"{koeficienti:.2f}"

# ---------------------------------------------------------
# FAQJA KRYESORE
# ---------------------------------------------------------
@app.get("/")
def home():
    return {"mesazhi": "API-ja e Futbollit është LIVE!"}

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

        ligat_grup = {}
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1 = n["teams"]["home"]["name"]
                ekipi_2 = n["teams"]["away"]["name"]
                
                # Formatimi i kohës
                data_ora_iso = n["fixture"]["date"]
                try:
                    data_obj = datetime.strptime(data_ora_iso[:19], "%Y-%m-%dT%H:%M:%S")
                    data_sakte = data_obj.strftime("%d/%m/%Y")
                    ora_sakte = data_obj.strftime("%H:%M")
                except:
                    data_sakte = data_target
                    ora_sakte = "N/A"
                
                # 🔥 LIDHJA ME TRURIN: Thërrasim algoritmin për këtë ndeshje
                rez_parashikimit, rez_koeficientit = analizo_ndeshjen(ekipi_1, ekipi_2)
                
                ndeshja_obj = {
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte,
                    "ora": ora_sakte,
                    "parashikimi": rez_parashikimit,
                    "koeficienti": rez_koeficientit
                }
                
                if emri_liges not in ligat_grup:
                    ligat_grup[emri_liges] = []
                ligat_grup[emri_liges].append(ndeshja_obj)
        
        lista_finale = []
        for liga, ndeshjet_e_liges in ligat_grup.items():
            lista_finale.append({
                "liga": liga,
                "ndeshjet": ndeshjet_e_liges
            })
            
        if len(lista_finale) == 0:
             return {"mesazhi": "Sukses", "skedina_grupuar": [], "error_msg": "Nuk u gjet asnjë ndeshje sot."}
            
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
        
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": [], "error_msg": "Gabim i brendshëm në server."}

# ---------------------------------------------------------
# NDESHJET LIVE
# ---------------------------------------------------------
@app.get("/api/live")
def merr_ndeshjet_live():
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"live": "all"} 
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        te_dhenat = response.json()
        ndeshjet_aktuale = []
        
        if "response" in te_dhenat:
            for ndeshje in te_dhenat["response"]:
                ndeshjet_aktuale.append({
                    "ndeshja": f"{ndeshje['teams']['home']['name']} vs {ndeshje['teams']['away']['name']}",
                    "rezultati": f"{ndeshje['goals']['home'] or 0} - {ndeshje['goals']['away'] or 0}",
                    "minuta": f"{ndeshje['fixture']['status']['elapsed']}'",
                    "statusi": "LIVE 🔴"
                })
                
        return {"mesazhi": "Sukses", "ndeshjet": ndeshjet_aktuale}
    except Exception as e:
        return {"mesazhi": "Gabim në server", "detaje": str(e)}