from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI(title="SOCCER 1X2 API", description="AI për Skedinën e Ditës")

# I japim leje aplikacionit vizual të lexojë të dhënat (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- TRURI MATEMATIKOR ---
def analizo_sigurine(k_home, k_draw, k_away):
    try:
        prob_home = 1 / k_home
        prob_draw = 1 / k_draw
        prob_away = 1 / k_away
        
        marzhi = prob_home + prob_draw + prob_away 
        real_home = (prob_home / marzhi) * 100
        real_draw = (prob_draw / marzhi) * 100
        real_away = (prob_away / marzhi) * 100
        
        shanset = {"1": real_home, "X": real_draw, "2": real_away}
        shenja = max(shanset, key=shanset.get)
        siguria = shanset[shenja]
        
        koef_final = k_home if shenja == "1" else (k_draw if shenja == "X" else k_away)
        
        return shenja, siguria, koef_final
    except:
        return None, 0, 0

# --- PORTA E RE PËR SKEDINËN E DITËS ---
@app.get("/api/skedina")
def merr_skedinen():
    API_KEY = "ab4ee376aea19eca742126f9b804fbc5" 
    headers = {
        "x-apisports-key": API_KEY,
        "x-apisports-host": "v3.football.api-sports.io"
    }
    data_sot = "2026-06-08"

    url_fixtures = "https://v3.football.api-sports.io/fixtures"
    resp_fixtures = requests.get(url_fixtures, headers=headers, params={"date": data_sot})
    ndeshjet_dict = {}
    
    for n in resp_fixtures.json().get("response", []):
        ndeshjet_dict[n["fixture"]["id"]] = f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}"

    url_odds = "https://v3.football.api-sports.io/odds"
    resp_odds = requests.get(url_odds, headers=headers, params={"date": data_sot, "bookmaker": 8})
    te_dhenat_odds = resp_odds.json().get("response", [])

    rezultatet_ai = []

    for item in te_dhenat_odds:
        id_ndeshjes = item["fixture"]["id"]
        
        if id_ndeshjes not in ndeshjet_dict:
            continue
            
        emrat_ndeshjes = ndeshjet_dict[id_ndeshjes]
        bastet = item["bookmakers"][0]["bets"]
        koef_1 = koef_X = koef_2 = 0
        
        for bast in bastet:
            if bast["name"] == "Match Winner":
                for vlera in bast["values"]:
                    if str(vlera['value']) == "Home": koef_1 = float(vlera['odd'])
                    if str(vlera['value']) == "Draw": koef_X = float(vlera['odd'])
                    if str(vlera['value']) == "Away": koef_2 = float(vlera['odd'])
                break
        
        if koef_1 and koef_X and koef_2:
            shenja, siguria, koeficienti = analizo_sigurine(koef_1, koef_X, koef_2)
            if siguria > 0:
                rezultatet_ai.append({
                    "ndeshja": emrat_ndeshjes,
                    "parashikimi": shenja,
                    "siguria_perqindje": siguria,
                    "koeficienti": koeficienti
                })

    rezultatet_ai.sort(key=lambda x: x["siguria_perqindje"], reverse=True)
    skedina_top_3 = rezultatet_ai[:3]
    
    koef_total = 1.0
    for r in skedina_top_3:
        koef_total *= r["koeficienti"]

    return {
        "status": "sukses",
        "titulli": "🔥 SKEDINA E DITËS NGA AI",
        "koeficienti_total_skedines": round(koef_total, 2),
        "ndeshjet_e_perzgjedhura": [
            {
                "ndeshja": n["ndeshja"],
                "parashikimi": f"Shenja {n['parashikimi']}",
                "koeficienti": n["koeficienti"],
                "siguria_AI": f"{round(n['siguria_perqindje'], 1)}%"
            } for n in skedina_top_3
        ]
    }