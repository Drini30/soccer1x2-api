from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests

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

@app.get("/")
def home():
    return {"mesazhi": "API-ja e Futbollit është LIVE!"}

@app.get("/api/skedina")
def merr_parashikimet():
    # Kërkojmë datën e nesërme
    data_target = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target})
        te_dhenat = response.json()
        
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina": [], "error_msg": str(te_dhenat["errors"])}
            
        if not te_dhenat.get("response"):
            # Nëse nesër s'ka ndeshje, provojmë sot
            data_target = datetime.utcnow().strftime('%Y-%m-%d')
            response = requests.get(url, headers=HEADERS, params={"date": data_target})
            te_dhenat = response.json()

        # Fjalor për të grupuar ndeshjet sipas ligës
        ligat_grup = {}
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            # Përpunojmë TË GJITHA ndeshjet që kthen API-ja
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1 = n["teams"]["home"]["name"]
                ekipi_2 = n["teams"]["away"]["name"]
                
                # Formatimi i Datës dhe Orës (Nga ISO në format të lexueshëm)
                data_ora_iso = n["fixture"]["date"]
                try:
                    data_obj = datetime.strptime(data_ora_iso[:19], "%Y-%m-%dT%H:%M:%S")
                    data_sakte = data_obj.strftime("%d/%m/%Y")
                    ora_sakte = data_obj.strftime("%H:%M")
                except:
                    data_sakte = data_target
                    ora_sakte = "N/A"
                
                ndeshja_obj = {
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "data": data_sakte,
                    "ora": ora_sakte,
                    "koeficienti": "1.50", # Këtu do të lidhet Endpoint-i i Odds kur të kesh Premium
                    "parashikimi": "1X"
                }
                
                # Shtimi në grup
                if emri_liges not in ligat_grup:
                    ligat_grup[emri_liges] = []
                ligat_grup[emri_liges].append(ndeshja_obj)
        
        # Kthejmë fjalorin në një listë për ta lexuar lehtë JavaScript
        lista_finale = []
        for liga, ndeshjet_e_liges in ligat_grup.items():
            lista_finale.append({
                "liga": liga,
                "ndeshjet": ndeshjet_e_liges
            })
            
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
        
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

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