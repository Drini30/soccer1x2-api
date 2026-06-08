from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests

app = FastAPI(title="SOCCER 1X2 API", description="AI për Skedinën e Ditës dhe Ndeshjet LIVE")

# Lejet e sigurisë për t'u lidhur me Netlify
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Çelësi yt i API-së
API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

# ---------------------------------------------------------
# FAQJA KRYESORE
# ---------------------------------------------------------
@app.get("/")
def home():
    return {"mesazhi": "API-ja e Futbollit është LIVE! Rrugët: /api/skedina ose /api/live"}

# ---------------------------------------------------------
# DERA 1: Skedina e Ditës (KAPJA E GABIMIT NGA API)
# ---------------------------------------------------------
@app.get("/api/skedina")
def merr_parashikimet():
    # TEST: Po e detyrojmë të kërkojë një datë ku jemi të sigurt që ka pasur ndeshje
    data_target = "2024-06-01" 
    url = "https://v3.football.api-sports.io/fixtures"
    
    try:
        response = requests.get(url, headers=HEADERS, params={"date": data_target})
        te_dhenat = response.json()
        
        # 🚨 KËTU KAPIM GABIMIN E API-së
        if "errors" in te_dhenat and te_dhenat["errors"]:
            gabimi_nga_api = str(te_dhenat["errors"])
            return {
                "mesazhi": "Kufizim API", 
                "skedina": [{
                    "ndeshja": f"Arsyeja nga API: {gabimi_nga_api}", 
                    "parashikimi": "BLOKUAR", 
                    "koeficienti": "0"
                }]
            }
            
        skedina = []
        
        # Nëse gjejmë ndeshje
        if "response" in te_dhenat and len(te_dhenat["response"]) > 0:
            for n in te_dhenat["response"][:5]:
                ekipi_1 = n["teams"]["home"]["name"]
                ekipi_2 = n["teams"]["away"]["name"]
                
                skedina.append({
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}",
                    "parashikimi": "1X", 
                    "koeficienti": "1.50"
                })
        
        # Nëse as kjo datë nuk punon dhe s'ka mesazh gabimi
        if len(skedina) == 0:
            skedina.append({
                "ndeshja": "Ende s'ka ndeshje",
                "parashikimi": "-",
                "koeficienti": "0"
            })
                
        return {"mesazhi": "Sukses", "skedina": skedina}
        
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina": []}

# ---------------------------------------------------------
# DERA 2: Ndeshjet LIVE
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