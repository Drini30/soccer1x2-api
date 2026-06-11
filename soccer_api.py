from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import requests
import random
import math

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

# 🔥 KONFIGURIMI I DATABAZËS REALE SUPABASE 🔥
SUPABASE_ANON_KEY = "sb_publishable_zdg-Qz3O3Sf5VRTXy1msXA_0zyoEJ7y"
SUPABASE_URL_PREDS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions"
SUPABASE_URL_USERS = "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/users"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- MODELET E TË DHËNAVE PËR AUTENTIFIKIM ---
class LoginData(BaseModel):
    email: str
    password: str
    name: str = ""

@app.post("/api/register")
def regjistro_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}", headers=SUPABASE_HEADERS)
    if res.status_code == 200 and len(res.json()) > 0: return {"sukses": False, "mesazhi": "ekziston"}

    emri_ndare = data.name.strip().split(" ", 1)
    emri = emri_ndare[0] if len(emri_ndare) > 0 else "Client"
    mbiemri = emri_ndare[1] if len(emri_ndare) > 1 else ""

    user_payload = { "email": email_clean, "password": data.password, "emri": emri, "mbiemri": mbiemri, "portofoli": 0.0, "isVip": False, "blerjet": [] }
    res_insert = requests.post(SUPABASE_URL_USERS, headers=SUPABASE_HEADERS, json=user_payload)
    
    if res_insert.status_code in [200, 201, 204]: return {"sukses": True, "perdoruesi": user_payload}
    else: return {"sukses": False, "mesazhi": f"Gabim Databaze: {res_insert.text}"}

@app.post("/api/login")
def login_perdorues(data: LoginData):
    email_clean = data.email.lower().strip()
    res = requests.get(f"{SUPABASE_URL_USERS}?email=eq.{email_clean}&password=eq.{data.password}", headers=SUPABASE_HEADERS)
    if res.status_code == 200:
        users = res.json()
        if len(users) > 0: return {"sukses": True, "perdoruesi": users[0]}
    return {"sukses": False, "mesazhi": "Llogaria nuk u gjet ose fjalëkalimi i gabuar!"}

@app.post("/api/update_user")
def perditeso_perdorues(user_data: dict):
    email = user_data.get("email", "").lower().strip()
    if email:
        is_vip_status = user_data.get("isVip", False)
        if "isvip" in user_data: is_vip_status = user_data["isvip"]
        update_payload = { "portofoli": user_data.get("portofoli", 0.0), "isVip": is_vip_status, "blerjet": user_data.get("blerjet", []) }
        requests.patch(f"{SUPABASE_URL_USERS}?email=eq.{email}", headers=SUPABASE_HEADERS, json=update_payload)
    return {"sukses": True}

@app.get("/api/verifiko_rezultatet")
def verifiko_rezultatet():
    res = requests.get(f"{SUPABASE_URL_PREDS}?rezultati_real=is.null", headers=SUPABASE_HEADERS)
    if res.status_code != 200: return {"mesazhi": "Gabim në leximin e Databazës."}
    
    ndeshjet_e_pambyllura = res.json()
    updatuara = 0

    for nd in ndeshjet_e_pambyllura:
        match_id = nd.get("id")
        if not match_id: continue
        
        api_res = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"id": match_id}, timeout=5)
        if api_res.status_code == 200:
            data = api_res.json()
            if data.get("response") and len(data["response"]) > 0:
                fixture = data["response"][0]
                statusi = fixture["fixture"]["status"]["short"]
                if statusi in ["FT", "AET", "PEN"]:
                    gola_1 = fixture["goals"]["home"]
                    gola_2 = fixture["goals"]["away"]
                    rez_real = f"{gola_1}-{gola_2}"
                    requests.patch(f"{SUPABASE_URL_PREDS}?id=eq.{match_id}", headers=SUPABASE_HEADERS, json={"rezultati_real": rez_real})
                    updatuara += 1

    return {"mesazhi": f"U verifikuan dhe u sinkronizuan {updatuara} ndeshje në Supabase."}

# ---------------------------------------------

def ruaj_ne_db_zyrtare(pako):
    pako_per_db = pako.copy()
    if "analiza_custom" in pako_per_db: del pako_per_db["analiza_custom"]
    try: requests.post(SUPABASE_URL_PREDS, headers=SUPABASE_HEADERS, json=pako_per_db, timeout=5)
    except: pass

@app.get("/")
def root(): return {"status": "online"}

LIGAT_KRYESORE = ["World Cup", "Euro Championship", "Champions League", "Europa League", "England - Premier League", "Spain - La Liga", "Italy - Serie A", "Germany - Bundesliga", "France - Ligue 1", "World - Friendlies", "World - UEFA Nations League", "Albania - Superliga"]
def merr_rendesine_e_liges(emri_liges):
    for i, liga_top in enumerate(LIGAT_KRYESORE):
        if liga_top.lower() in emri_liges.lower(): return i 
    return 999 

GIGANTET = { "Argentina": 95, "France": 94, "England": 93, "Brazil": 92, "Spain": 92, "Germany": 90, "Portugal": 89, "Italy": 88, "Netherlands": 88, "Croatia": 86, "Belgium": 85, "Uruguay": 84, "Colombia": 84, "Switzerland": 82, "USA": 80, "Real Madrid": 95, "Manchester City": 95, "Bayern Munich": 93, "Arsenal": 92, "Liverpool": 91, "Barcelona": 90, "Paris Saint Germain": 89, "Inter": 89, "Bayer Leverkusen": 88, "Juventus": 86, "AC Milan": 85, "Atletico Madrid": 85 }
TAKTIKAT = { "4-3-3": {"atk": 1.15, "def_fortitude": 0.90}, "3-4-3": {"atk": 1.20, "def_fortitude": 0.85}, "4-4-2": {"atk": 1.00, "def_fortitude": 1.00}, "4-2-3-1": {"atk": 1.05, "def_fortitude": 1.05}, "3-5-2": {"atk": 1.10, "def_fortitude": 0.95}, "5-3-2": {"atk": 0.80, "def_fortitude": 1.20}, "5-4-1": {"atk": 0.70, "def_fortitude": 1.30} }

def merr_fuqine_reale(ekipi):
    for emri, fuqia in GIGANTET.items():
        if emri.lower() in ekipi.lower(): return fuqia
    return 70

def parashiko_formacionin(fuqia_ime, fuqia_kundershtarit, is_home):
    diferenca = fuqia_ime - fuqia_kundershtarit
    if diferenca >= 15: return random.choice(["4-3-3", "3-4-3", "4-2-3-1"])
    elif diferenca <= -15: return random.choice(["5-4-1", "5-3-2", "4-4-2"])
    else: return random.choice(["4-3-3", "4-2-3-1", "3-5-2"]) if is_home else random.choice(["4-4-2", "4-2-3-1", "5-3-2"])

def llogarit_motivimin(emri_liges):
    liga = emri_liges.lower()
    if any(x in liga for x in ["friend", "miqësore", "u20", "u23", "u19", "reserve", "women"]): return 0.75 
    elif any(x in liga for x in ["cup", "copa", "coppa", "kupa", "pokal", "shield"]): return 1.10 if "world" in liga or "champions" in liga else 0.85 
    elif any(x in liga for x in ["champions league", "premier league", "la liga", "serie a", "bundesliga"]): return 1.05 
    else: return 1.00 

def gjenero_analize_custom(ekipi_1, ekipi_2, rez_sakt, eshte_bllof, ht_ft_str=""):
    try: g1, g2 = map(int, rez_sakt.split('-'))
    except: g1, g2 = 1, 0
    
    # Shtojmë Përmbysjen nëse ka
    ht_ft_text = f"<br><b style='color:#ff4500;'>🔥 Ekskluzive:</b> Sugjerohet Përmbysje <b>{ht_ft_str}</b>!" if ht_ft_str else ""

    if eshte_bllof: return { "sq": f"⚠️ <b>Risk (Kurth):</b> Historiku paralajmëron rrezik për Gafë nga favoriti. <br><b style='color:#f2cc60;'>Sugjerim:</b> Surprizë kundër favoritit.{ht_ft_text}", "en": f"⚠️ <b>Risk (Trap):</b> Historical data warns of a potential upset.{ht_ft_text}", "de": f"⚠️ <b>Risiko (Falle):</b> Historische Daten warnen vor einer Überraschung.{ht_ft_text}", "fr": f"⚠️ <b>Risque (Piège):</b> L'historique avertit d'une surprise potentielle.{ht_ft_text}", "it": f"⚠️ <b>Rischio (Trappola):</b> I dati storici avvertono di una possibile sorpresa.{ht_ft_text}" }
    elif rez_sakt == "0-0": return { "sq": f"Mbrojtje ultra-kompakte nga të dyja skuadrat. <br><b style='color:#f2cc60;'>Sugjerim:</b> Nën 2.5 gola total.{ht_ft_text}", "en": f"Ultra-compact defenses. <br><b style='color:#f2cc60;'>Suggestion:</b> Under 2.5 goals.{ht_ft_text}"}
    elif g1 == g2: return { "sq": f"Skuadra me forca të barabarta. <br><b style='color:#f2cc60;'>Sugjerim:</b> Të dyja shënojnë (GG) ose Barazim.{ht_ft_text}", "en": f"Evenly matched teams. <br><b style='color:#f2cc60;'>Suggestion:</b> Both Teams to Score (GG) or Draw.{ht_ft_text}"}
    elif g1 > g2: return { "sq": f"Dominim sulmues i <b>{ekipi_1}</b>. <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"Offensive dominance by <b>{ekipi_1}</b>. <br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"<b>{ekipi_1}</b> kontrollon fushën me mbrojtje të ngurtë. <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Nën 3.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_1}</b> controls the pitch with solid defense. <br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_1} to win or Under 3.5 goals.{ht_ft_text}" }
    else: return { "sq": f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë. <br><b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_2} ose Mbi 2.5 gola.{ht_ft_text}", "en": f"<b>{ekipi_2}</b> excels away. <br><b style='color:#f2cc60;'>Suggestion:</b> {ekipi_2} to win or Over 2.5 goals.{ht_ft_text}" } if (g1 + g2) >= 3 else { "sq": f"Ndeshje ku <b>{ekipi_2}</b> menaxhon lojën me rrezik minimal. <br><b style='color:#f2cc60;'>Sugjerim:</b> X2 ose Nën 2.5 gola.{ht_ft_text}", "en": f"Tight match where <b>{ekipi_2}</b> manages low-risk play. <br><b style='color:#f2cc60;'>Suggestion:</b> X2 or Under 2.5 goals.{ht_ft_text}" }

def analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, k1_str, kx_str, k2_str, emri_liges, eshte_ndeshje_bllof):
    try: k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)
    except: k1, kx, k2 = 2.60, 3.10, 2.60 

    prob_1, prob_x, prob_2 = 1/k1, 1/kx, 1/k2
    marzhi = prob_1 + prob_x + prob_2 
    p1_real, px_real, p2_real = prob_1/marzhi, prob_x/marzhi, prob_2/marzhi

    fuqia_1, fuqia_2 = merr_fuqine_reale(ekipi_1), merr_fuqine_reale(ekipi_2)
    faktor_motivimi = llogarit_motivimin(emri_liges)
    diferenca_fuqise = ((fuqia_1 - fuqia_2) / 100.0) * faktor_motivimi
    
    # 🔥 Përllogaritja e Renditjes së Simuluar (Për Machine Learning)
    renditja_sim_1 = max(1, int(20 - (fuqia_1/5) - (1/k1 * 5)))
    renditja_sim_2 = max(1, int(20 - (fuqia_2/5) - (1/k2 * 5)))

    form_1 = parashiko_formacionin(fuqia_1, fuqia_2, is_home=True)
    form_2 = parashiko_formacionin(fuqia_2, fuqia_1, is_home=False)
    t1_atk, t1_def = TAKTIKAT[form_1]["atk"], TAKTIKAT[form_1]["def_fortitude"]
    t2_atk, t2_def = TAKTIKAT[form_2]["atk"], TAKTIKAT[form_2]["def_fortitude"]

    xg_1_baze = max(0.1, (p1_real * 2.6) + (diferenca_fuqise * 0.8))
    xg_2_baze = max(0.1, (p2_real * 2.6) - (diferenca_fuqise * 0.8))

    # 🔥 Logjika Përmbysje (HT/FT 1/2 ose 2/1)
    ht_ft_sugjerim = ""
    if eshte_ndeshje_bllof:
        # Nëse është bllof dhe koficienti i favoritit vuan jashtë
        if k1 > 2.50 and k2 < 2.00:
            if random.random() < 0.15: ht_ft_sugjerim = "1/2" # Vendasit shënojnë në HT, por thyhen në FT
        elif k2 > 2.50 and k1 < 2.00:
            if random.random() < 0.15: ht_ft_sugjerim = "2/1" # Miqtë shënojnë në HT, thyhen në FT

    if eshte_ndeshje_bllof and (k1 < 1.60 or k2 < 1.60):
        if k1 < 1.60: xg_1, xg_2 = xg_1_baze * 0.40, xg_2_baze * 1.95 
        else: xg_1, xg_2 = xg_1_baze * 1.95, xg_2_baze * 0.40
    else:
        xg_1 = xg_1_baze * 1.15 * t1_atk * (1 / t2_def)
        xg_2 = xg_2_baze * 0.90 * t2_atk * (1 / (t1_def * 1.10))

    def poisson(lmbda, k): return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)
    rezultati_sakt = "0-0"
    max_prob = 0

    for g1 in range(6):
        for g2 in range(6):
            prob_score = poisson(xg_1, g1) * poisson(xg_2, g2)
            if not eshte_ndeshje_bllof:
                if p1_real > p2_real + 0.15 and g1 <= g2: continue
                if p2_real > p1_real + 0.15 and g2 <= g1: continue
            if prob_score > max_prob:
                max_prob = prob_score
                rezultati_sakt = f"{g1}-{g2}"
    
    koef_rez_sakt = min(40.0, (1 / max_prob) * 0.85) if max_prob > 0 else 10.0
    besueshmeria = round(random.uniform(45.0, 60.5), 1) if eshte_ndeshje_bllof else round(min(99.0, max(65.0, (max(p1_real, p2_real) * 100) + (max_prob * 100))), 1)
    
    analiza_custom_dict = gjenero_analize_custom(ekipi_1, ekipi_2, rezultati_sakt, eshte_ndeshje_bllof, ht_ft_sugjerim)
    
    # Kthejmë vlerat shtesë për t'i ruajtur në DB
    te_dhena_shtese_per_db = {
        "is_bllof": eshte_ndeshje_bllof,
        "renditja_1": renditja_sim_1,
        "renditja_2": renditja_sim_2,
        "ht_ft_sugjerim": ht_ft_sugjerim,
        "koef_plote": f"1:{k1_str} | X:{kx_str} | 2:{k2_str}"
    }

    return analiza_custom_dict, besueshmeria, rezultati_sakt, f"{koef_rez_sakt:.2f}", te_dhena_shtese_per_db

@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"date": data_target, "timezone": "Europe/Tirane"}, timeout=10)
        te_dhenat = response.json()
        if "errors" in te_dhenat and te_dhenat["errors"]: return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        bet365_odds = {}
        try:
            res_odds = requests.get("https://v3.football.api-sports.io/odds", headers=HEADERS, params={"date": data_target, "bookmaker": 8, "page": 1}, timeout=10).json()
            if "response" in res_odds:
                for item in res_odds["response"]:
                    fix_id = str(item["fixture"]["id"])
                    try:
                        bets = item["bookmakers"][0]["bets"]
                        mw = next((b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"), None)
                        if mw:
                            v = mw["values"]
                            bet365_odds[fix_id] = { "1": next((x["odd"] for x in v if x["value"] == "Home"), None), "X": next((x["odd"] for x in v if x["value"] == "Draw"), None), "2": next((x["odd"] for x in v if x["value"] == "Away"), None)}
                    except: pass
        except: pass

        ligat_raw = {}
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                if emri_liges not in ligat_raw: ligat_raw[emri_liges] = []
                ligat_raw[emri_liges].append(n)

        lista_e_te_gjithave = []
        for emri_liges, ndeshjet_liges in ligat_raw.items():
            totali_ndeshjeve = len(ndeshjet_liges)
            numri_bllofeve = int(totali_ndeshjeve * random.uniform(0.20, 0.30)) if totali_ndeshjeve > 3 else (1 if random.random() < 0.25 else 0)
            indekset_bllof = random.sample(range(totali_ndeshjeve), numri_bllofeve) if numri_bllofeve > 0 else []

            for index, n in enumerate(ndeshjet_liges):
                id_ndeshja = str(n["fixture"]["id"])
                ekipi_1, ekipi_2 = n["teams"]["home"]["name"].replace("'", ""), n["teams"]["away"]["name"].replace("'", "")
                statusi_kod = n["fixture"]["status"]["short"]
                gola_1, gola_2 = n["goals"]["home"], n["goals"]["away"]
                rezultati = f"{gola_1} - {gola_2}" if gola_1 is not None else "0 - 0"
                
                if id_ndeshja in bet365_odds and bet365_odds[id_ndeshja]["1"]:
                    k1, kx, k2 = str(bet365_odds[id_ndeshja]["1"]), str(bet365_odds[id_ndeshja]["X"]), str(bet365_odds[id_ndeshja]["2"])
                else:
                    random.seed(f"sim-{id_ndeshja}")
                    k1, kx, k2 = f"{round(random.uniform(1.40, 2.90), 2):.2f}", f"{round(random.uniform(2.80, 3.80), 2):.2f}", f"{round(random.uniform(1.90, 4.20), 2):.2f}"

                try: ora_sakte = datetime.strptime(n["fixture"]["date"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%H:%M")
                except: ora_sakte = "N/A"

                analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt, extradb = analizo_ndeshjen_premium(id_ndeshja, ekipi_1, ekipi_2, k1, kx, k2, emri_liges, index in indekset_bllof)

                lista_e_te_gjithave.append({
                    "id": id_ndeshja, "liga_emri": emri_liges, "liga_id": n["league"]["id"], "sezoni": n["league"]["season"],
                    "ekipi_1_id": n["teams"]["home"]["id"], "ekipi_2_id": n["teams"]["away"]["id"], "ekipi_1": ekipi_1, "ekipi_2": ekipi_2, 
                    "ndeshja": f"{ekipi_1} vs {ekipi_2}", "data": data_target, "ora": "FT" if statusi_kod in ["FT","AET","PEN"] else ora_sakte,
                    "ora_sakte": ora_sakte, "statusi": statusi_kod, "minuta": n["fixture"]["status"]["elapsed"] or 0, "rezultati": rezultati,
                    "koef_1": k1, "koef_x": kx, "koef_2": k2, "analiza_custom": analiza_custom, "besueshmeria": besueshmeria, 
                    "rezultati_sakt": rez_sakt, "koef_rez_sakt": koef_rez_sakt, "is_premium": False,
                    
                    # Te dhenat e reja per tu ruajtur ne Supabase
                    "is_bllof": extradb["is_bllof"],
                    "renditja_1": extradb["renditja_1"],
                    "renditja_2": extradb["renditja_2"],
                    "ht_ft_sugjerim": extradb["ht_ft_sugjerim"],
                    "koef_plote": extradb["koef_plote"]
                })
        
        lista_e_te_gjithave.sort(key=lambda x: x["besueshmeria"], reverse=True)
        if lista_e_te_gjithave:
            lista_e_te_gjithave[0].update({"is_premium": True, "is_motd": True, "besueshmeria": 99.0})
            ruaj_ne_db_zyrtare(lista_e_te_gjithave[0])
            for i in range(1, min(5, len(lista_e_te_gjithave))):
                lista_e_te_gjithave[i].update({"is_premium": True, "is_motd": False})

        ligat_grup = {}
        for ndeshja in lista_e_te_gjithave:
            liga = ndeshja.pop("liga_emri")
            if liga not in ligat_grup: ligat_grup[liga] = []
            ligat_grup[liga].append(ndeshja)

        lista_finale = sorted([{"liga": k, "ndeshjet": v} for k, v in ligat_grup.items()], key=lambda x: merr_rendesine_e_liges(x["liga"]))
        return {"mesazhi": "Sukses", "skedina_grupuar": lista_finale}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}

@app.get("/api/detajet/{match_id}")
def merr_detajet_ndeshjes(match_id: int):
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"id": match_id})
        te_dhenat = response.json()
        if not te_dhenat.get("response"): return {"mesazhi": "Nuk u gjetën të dhëna"}
        ndeshja = te_dhenat["response"][0]
        lista_evente = [{"koha": f"{ev['time']['elapsed']}'", "ekipi": ev['team']['name'], "lojtari": ev['player']['name'] or "Lojtar", "lloj": ev['type'], "detaj": ev['detail']} for ev in ndeshja.get("events", []) if ev['type'] in ['Goal', 'Card']]
        stats_formated = {}
        if ndeshja.get("statistics") and len(ndeshja["statistics"]) >= 2:
            s0, s1 = ndeshja["statistics"][0], ndeshja["statistics"][1]
            stats_formated = {"ekipi_1": s0['team']['name'], "ekipi_2": s1['team']['name'], "statistikat": []}
            if s0.get('statistics') and s1.get('statistics'):
                for i in range(len(s0['statistics'])):
                    if s0['statistics'][i]['type'] in ["Shots on Goal", "Ball Possession"]:
                        stats_formated["statistikat"].append({"lloji": s0['statistics'][i]['type'], "vler_1": s0['statistics'][i]['value'] or 0, "vler_2": s1['statistics'][i]['value'] or 0})
        return {"mesazhi": "Sukses", "evente": lista_evente, "statistika": stats_formated}
    except: return {"mesazhi": "Gabim"}

@app.get("/api/historia/{team_id}")
def merr_historine(team_id: int):
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures", headers=HEADERS, params={"team": team_id, "last": 5})
        rezultati_hist = []
        for n in response.json().get("response", []):
            ht, ft = n.get("score", {}).get("halftime", {}), n.get("score", {}).get("fulltime", {})
            try: data_sakte = datetime.strptime(n["fixture"]["date"][:10], "%Y-%m-%d").strftime("%d/%m/%y")
            except: data_sakte = "N/A"
            rezultati_hist.append({"data": data_sakte, "ora": "FT", "ndeshja": f"{n['teams']['home']['name']} vs {n['teams']['away']['name']}", "ht": f"{ht.get('home')}-{ht.get('away')}" if ht and ht.get('home') is not None else "0-0", "ft": f"{ft.get('home')}-{ft.get('away')}" if ft and ft.get('home') is not None else "0-0"})
        return {"mesazhi": "Sukses", "historia": rezultati_hist}
    except Exception as e: return {"mesazhi": "Gabim", "detaje": str(e)}

@app.get("/api/renditja/{league_id}/{season}")
def merr_renditjen(league_id: int, season: int):
    try:
        res = requests.get("https://v3.football.api-sports.io/standings", headers=HEADERS, params={"league": league_id, "season": season}, timeout=8)
        data = res.json()
        renditja_list = [{"pozicioni": r["rank"], "ekipi": r["team"]["name"], "piket": r["points"], "ndeshje": r["all"]["played"], "gola": f"{r['all']['goals']['for']}:{r['all']['goals']['against']}", "forma": r["form"]} for r in data.get("response", [{}])[0].get("league", {}).get("standings", [[]])[0]] if data.get("response") else []
        return {"mesazhi": "Sukses", "renditja": renditja_list}
    except Exception as e: return {"mesazhi": "Gabim", "renditja": [], "detaje": str(e)}

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet_shtese(match_id: str):
    return {"mesazhi": "Simuluar", "koeficientet": []}

@app.get("/api/live")
def merr_ndeshjet_live(): return {"mesazhi": "Sukses", "ndeshjet": []}