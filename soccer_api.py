from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests

app = FastAPI(title="SOCCER 1X2 API", description="AI për Skedinën e Ditës dhe Ndeshjet LIVE")

# Lejet për të komunikuar me faqen vizuale
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Çelësi yt zyrtar i API-së
API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {
    "x-apisports-key": API_KEY
}

# ---------------------------------------------------------
# FAQJA KRYESORE (Për të evituar gabimin 404)
# ---------------------------------------------------------
@app.get("/")
def home():
    return {"mesazhi": "API-ja e Futbollit është LIVE! Përdor /api/skedina ose /api/live"}

# ---------------------------------------------------------
# DERA 1: Skedina e Ditës (Parashikimet për të Nesërmen)
# ---------------------------------------------------------
@app.get("/api/skedina")
def merr_parashikimet():
    data_neser = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"date": data_neser}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        te_dhenat = response.json()
        
        ndeshjet_sugjeruara = []
        koeficienti_total = 1.0
        
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for ndeshje in te_dhenat["response"][:4]:
                ekipi_1 = ndeshje["teams"]["home"]["name"]
                ekipi_2 = ndeshje["teams"]["away"]["name"]
                
                koeficienti_ndeshjes = 1.50
                koeficienti_total *= koeficienti_ndeshjes
                
                ndeshjet_sugjeruara.append({
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "parashikimi": "1X",
                    "koeficienti": koeficienti_ndeshjes
                })
                
        if len(ndeshjet_sugjeruara) == 0:
            return {"mesazhi": "Nuk u gjetën ndeshje për të nesërmen", "koeficienti_total": 0, "skedina": []}
            
        return {
            "mesazhi": "Sukses", 
            "data": data_neser,
            "koeficienti_total": round(koeficienti_total, 2),
            "skedina": ndeshjet_sugjeruara
        }
    except Exception as e:
        return {"mesazhi": "Gabim në server", "detaje": str(e)}

# ---------------------------------------------------------
# DERA 2: Ndeshjet LIVE (Në kohë reale)
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
                ekipi_shtepise = ndeshje["teams"]["home"]["name"]
                ekipi_mik = ndeshje["teams"]["away"]["name"]
                gola_shtepia = ndeshje["goals"]["home"]
                gola_mik = ndeshje["goals"]["away"]
                minuta = ndeshje["fixture"]["status"]["elapsed"]
                
                if gola_shtepia is None: gola_shtepia = 0
                if gola_mik is None: gola_mik = 0
                
                ndeshjet_aktuale.append({
                    "ndeshja": f"{ekipi_shtepise} vs {ekipi_mik}",
                    "rezultati": f"{gola_shtepia} - {gola_mik}",
                    "minuta": f"{minuta}'",
                    "statusi": "LIVE 🔴"
                })
                
        if len(ndeshjet_aktuale) == 0:
            return {"mesazhi": "Nuk ka ndeshje LIVE për momentin.", "ndeshjet": []}
            
        return {"mesazhi": "Sukses", "ndeshjet": ndeshjet_aktuale}
        
    except Exception as e:
        return {"mesazhi": "Gabim në server", "detaje": str(e)}