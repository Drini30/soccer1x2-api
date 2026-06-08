from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

@app.get("/api/skedina")
def merr_parashikimet():
    # Provojmë nesër, nëse s'ka, provojmë sot
    data_target = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
    url = "https://v3.football.api-sports.io/fixtures"
    
    response = requests.get(url, headers=HEADERS, params={"date": data_target})
    te_dhenat = response.json()
    
    # Nëse lista është bosh, provo sot
    if not te_dhenat.get("response"):
        data_target = datetime.utcnow().strftime('%Y-%m-%d')
        response = requests.get(url, headers=HEADERS, params={"date": data_target})
        te_dhenat = response.json()

    skedina = []
    if "response" in te_dhenat and te_dhenat["response"]:
        for n in te_dhenat["response"][:4]:
            skedina.append({
                "ndeshja": f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}",
                "parashikimi": "1X",
                "koeficienti": "1.50"
            })
    else:
        skedina.append({"ndeshja": "Nuk ka ndeshje për momentin", "parashikimi": "-", "koeficienti": "0"})
            
    return {"skedina": skedina}