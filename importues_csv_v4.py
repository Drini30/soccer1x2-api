# ==========================================================
# IMPORTUES CSV v4 → SUPABASE (historik_trajnimi)
# ==========================================================
# NDRYSHIMET kundrejt v3:
#
#   1) ÇELËSI NGA ENV — kurrë i ngulitur në kod.
#        export SUPABASE_SERVICE_KEY="..."
#
#   2) STATISTIKA QË MUNGOJNË → NULL, jo 0.0.
#      v3 shkruante 0.0 kur sezoni s'kishte kolona goditjesh (rreshtat 195-198).
#      Modeli do ta mësonte "0 goditje" si vlerë reale — ekipe që s'gjuajnë kurrë.
#      XGBoost i trajton NULL-et vendas (mëson degën e munguar), ndaj None është korrekt.
#
#   3) HISTORIK KRYQ-SEZONAL brenda ligës.
#      v3 e thërriste përpunimin për një ligë-sezon, dhe h2h kërkonte vetëm brenda tij
#      (rreshti 244). Dy ekipe takohen 2 herë në sezon → h2h_n ishte 0 ose 1 pothuajse
#      gjithmonë, pra 4 kolonat h2h ishin praktikisht të zbrazëta.
#      Tani historiku rrjedh nëpër sezone. Kjo ndreq DY gjëra:
#        • h2h bëhet i përdorshëm (deri në ~20 përballje);
#        • forma e 6 ndeshjeve s'rindizet çdo gusht — pikërisht si backend-i live, që
#          merr 8 ndeshjet e fundit pa i njohur kufijtë e sezonit. Pra ul train/serve skew.
#      Për t'u kthyer te sjellja e v3: KRYQ_SEZONE = False.
#
#   4) match_id i qëndrueshëm (datë+ekipe në vend të indeksit) → ri-ekzekutimi
#      është idempotent dhe s'varet nga lista SEZONET.
#
# ⚠️ PARA ekzekutimit, fshi importin e vjetër:
#      DELETE FROM historik_trajnimi WHERE burimi = 'csv';
#    (match_id-të ndryshuan; pa këtë do të kishe rreshta të dyfishtë.)
#
# Si ta përdorësh:
#   python -m pip install requests pandas
#   export SUPABASE_SERVICE_KEY="..."
#   python importues_csv_v4.py
# ==========================================================

import io
import math
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests

# ── KONFIGURIMI ──
SUPABASE_URL = os.environ.get(
    "SUPABASE_HISTORIK_URL",
    "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/historik_trajnimi",
)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
if not SUPABASE_KEY:
    sys.exit("❌ Vendos SUPABASE_SERVICE_KEY te environment-i (mos e ngul në kod).")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

KRYQ_SEZONE = True   # False = sjellja e vjetër (historik brenda një sezoni)

# ── ZBRITJA KOHORE E FORMËS (Dixon-Coles 1997): w = exp(-ξ · ditë) ──
# 0.0 = e fikur, të gjitha ndeshjet peshojnë njësoj. Vlerë tipike: ~0.0065/ditë.
#
# ⚠️ DUHET TË JETË E NJËJTA VLERË me FORMA_DECAY_XI te soccer_api.py.
# Këto mesatare bëhen veçori të XGB-së. Nëse importi dhe backend-i i llogaritin
# ndryshe, modeli merr në prodhim inpute me përkufizim tjetër nga trajnimi —
# train/serve skew, i njëjti defekt që u hoq te volatility dhe rest_days.
#
# Rendi: vendos ξ te të dyja → ri-importo → ritrajno → deploy bashkë.
FORMA_DECAY_XI = float(os.environ.get("FORMA_DECAY_XI", "0.0"))

LIGAT = {
    "E0": "England - Premier League", "E1": "England - Championship",
    "SP1": "Spain - La Liga", "SP2": "Spain - Segunda Division",
    "I1": "Italy - Serie A", "I2": "Italy - Serie B",
    "D1": "Germany - Bundesliga", "D2": "Germany - 2. Bundesliga",
    "F1": "France - Ligue 1", "F2": "France - Ligue 2",
    "N1": "Netherlands - Eredivisie", "P1": "Portugal - Primeira Liga",
    "T1": "Turkey - Super Lig", "B1": "Belgium - Pro League",
    "G1": "Greece - Super League", "SC0": "Scotland - Premiership",
}
SEZONET = ["1415", "1516", "1617", "1718", "1819",
           "1920", "2021", "2122", "2223", "2324"]


def shkarko_csv(liga_kod, sezoni):
    url = f"https://www.football-data.co.uk/mmz4281/{sezoni}/{liga_kod}.csv"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.text) > 100:
            return pd.read_csv(io.StringIO(r.text), on_bad_lines="skip")
    except Exception as e:
        print(f"  Gabim {liga_kod} {sezoni}: {e}")
    return None


def parse_date(date_str):
    """football-data.co.uk përdor formate: dd/mm/yy ose dd/mm/yyyy"""
    for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(str(date_str), fmt)
        except Exception:
            continue
    return None


def first_col(m, cols):
    """Kthen vlerën e parë jo-bosh nga një listë emrash kolonash (emrat e koefave
    ndryshojnë sipas sezonit: B365 / Avg / Bb / Max / P)."""
    for c in cols:
        if c in m.index:
            try:
                v = m[c]
                if not pd.isna(v):
                    return float(v)
            except Exception:
                pass
    return None


def llogarit_features(df, idx, team, eshte_home, mes_liga_gola):
    """
    Llogarit TË GJITHA features për një ekip PARA një ndeshjeje.
    Ndryshimi kryesor nga v3: goditjet/këndet kthejnë None (jo 0.0) kur mungojnë.
    """
    para = df.iloc[:idx]
    ndeshjet_ekipit = para[(para["HomeTeam"] == team) | (para["AwayTeam"] == team)].tail(6)

    default = {
        "forma_pts": 7.0, "avg_scored": 1.3, "avg_conceded": 1.3,
        "avg_scored_loc": 1.3, "avg_conceded_loc": 1.3,
        "avg_yellow": 1.8, "avg_red": 0.1,
        "attack_strength": 1.0, "defense_strength": 1.0,
        "volatility": 1.0, "rest_days": 7.0,
        # NULL, jo 0.0 — s'kemi asnjë provë për këtë ekip
        "avg_shots": None, "avg_sot": None, "avg_sot_against": None, "avg_corners": None,
    }
    if len(ndeshjet_ekipit) < 2:
        return default

    pts = scored = conceded = 0.0
    pesha_totale = 0.0
    loc_scored = loc_conceded = loc_count = 0.0
    yellow = red = 0.0
    shots_for = shots_against = sot_for = sot_against = corners_for = 0.0
    stat_count = 0   # sa ndeshje patën statistika goditjesh (sezonet e vjetra s'kanë)
    totale_gola_lista = []  # për volatility
    data_e_fundit = None

    data_aktuale = parse_date(df.iloc[idx].get("Date"))

    # Peshat e zbritjes kohore. Referenca është ndeshja më e fundit e dritares —
    # e njëjta zgjedhje si te soccer_api.merr_formen_reale, që të dyja anët të
    # prodhojnë saktësisht të njëjtat numra. Normalizohen që shuma të mbetet sa
    # numri i ndeshjeve, ndaj `forma_pts` ruan shkallën e vet.
    _peshat = []
    if FORMA_DECAY_XI > 0:
        _dt = [parse_date(m.get("Date")) for _, m in ndeshjet_ekipit.iterrows()]
        _valid = [d for d in _dt if d]
        if _valid:
            _ref = max(_valid)
            _raw = [(math.exp(-FORMA_DECAY_XI * max(0, (_ref - d).days)) if d else 1.0) for d in _dt]
            _s = sum(_raw)
            if _s > 0:
                _peshat = [r * len(_raw) / _s for r in _raw]

    for _i, (_, m) in enumerate(ndeshjet_ekipit.iterrows()):
        w = _peshat[_i] if _peshat else 1.0
        ishte_home = (m["HomeTeam"] == team)
        try:
            gf = m["FTHG"] if ishte_home else m["FTAG"]
            ga = m["FTAG"] if ishte_home else m["FTHG"]
        except Exception:
            continue
        if pd.isna(gf) or pd.isna(ga):
            continue
        scored += w * gf
        conceded += w * ga
        pesha_totale += w
        # Volatility mbetet i paponderuar: është devijim standard i mostrës, dhe
        # ponderimi do të kërkonte formulë tjetër. Me ξ=0 s'ka fare ndryshim.
        totale_gola_lista.append(gf + ga)
        if gf > ga:
            pts += 3 * w
        elif gf == ga:
            pts += 1 * w

        if ishte_home == eshte_home:
            loc_scored += w * gf
            loc_conceded += w * ga
            loc_count += w

        # Kartonat
        try:
            yc = m["HY"] if ishte_home else m["AY"]
            rc = m["HR"] if ishte_home else m["AR"]
            if not pd.isna(yc):
                yellow += w * yc
            if not pd.isna(rc):
                red += w * rc
        except Exception:
            pass

        # Goditje / Goditje në portë / Kënde (mungojnë në sezone të vjetra)
        try:
            _sf = m["HS"] if ishte_home else m["AS"]
            _sa = m["AS"] if ishte_home else m["HS"]
            _stf = m["HST"] if ishte_home else m["AST"]
            _sta = m["AST"] if ishte_home else m["HST"]
            _cf = m["HC"] if ishte_home else m["AC"]
            if not (pd.isna(_sf) or pd.isna(_stf)):
                shots_for += _sf
                shots_against += (_sa if not pd.isna(_sa) else 0)
                sot_for += _stf
                sot_against += (_sta if not pd.isna(_sta) else 0)
                corners_for += (_cf if not pd.isna(_cf) else 0)
                stat_count += 1
        except Exception:
            pass

        d = parse_date(m.get("Date"))
        if d and (data_e_fundit is None or d > data_e_fundit):
            data_e_fundit = d

    n = len(ndeshjet_ekipit)
    # Emëruesi është shuma e peshave; me ξ=0 ajo barazohet me n.
    _em = pesha_totale if pesha_totale > 0 else n
    avg_scored = scored / _em
    avg_conceded = conceded / _em

    attack_strength = round(avg_scored / mes_liga_gola, 3) if mes_liga_gola > 0 else 1.0
    defense_strength = round(avg_conceded / mes_liga_gola, 3) if mes_liga_gola > 0 else 1.0

    # Volatility = devijimi standard (mostër, ddof=1) i totalit të golave.
    # I NJËJTI përkufizim si soccer_api.merr_formen_reale — mos e ndrysho njërin pa tjetrin.
    if len(totale_gola_lista) >= 3:
        volatility = round(pd.Series(totale_gola_lista).std(), 3)
    else:
        volatility = 1.0

    rest_days = 7.0
    if data_aktuale and data_e_fundit:
        diff = (data_aktuale - data_e_fundit).days
        rest_days = float(min(max(diff, 1), 30))

    return {
        "forma_pts": round(pts, 1),
        "avg_scored": round(avg_scored, 2),
        "avg_conceded": round(avg_conceded, 2),
        "avg_scored_loc": round(loc_scored / loc_count, 2) if loc_count >= 1 else round(avg_scored, 2),
        "avg_conceded_loc": round(loc_conceded / loc_count, 2) if loc_count >= 1 else round(avg_conceded, 2),
        "avg_yellow": round(yellow / _em, 2),
        "avg_red": round(red / _em, 2),
        "attack_strength": attack_strength,
        "defense_strength": defense_strength,
        "volatility": volatility,
        "rest_days": rest_days,
        # None kur asnjë nga 6 ndeshjet s'kishte statistika — XGBoost e trajton si munguar
        "avg_shots":       round(shots_for / stat_count, 2) if stat_count else None,
        "avg_sot":         round(sot_for / stat_count, 2) if stat_count else None,
        "avg_sot_against": round(sot_against / stat_count, 2) if stat_count else None,
        "avg_corners":     round(corners_for / stat_count, 2) if stat_count else None,
    }


def merr_historikun(liga_kod):
    """Shkarkon TË GJITHË sezonet e një lige dhe i bashkon në një histori kronologjike.
    Kolona `_mes_liga` mbetet PER-SEZON (forca relative krahasohet me sezonin e vet)."""
    frames = []
    for sezoni in SEZONET:
        df = shkarko_csv(liga_kod, sezoni)
        if df is None or len(df) == 0:
            continue
        if "HomeTeam" not in df.columns or "FTHG" not in df.columns:
            continue
        df = df.copy()
        try:
            mes = (df["FTHG"].mean() + df["FTAG"].mean()) / 2
        except Exception:
            mes = 1.35
        df["_sezoni"] = sezoni
        df["_mes_liga"] = mes if mes and mes > 0 else 1.35
        df["_data"] = df["Date"].apply(parse_date)
        frames.append(df)
        time.sleep(0.4)

    if not frames:
        return None
    if not KRYQ_SEZONE:
        return frames   # listë e veçuar — sjellja e vjetër

    out = pd.concat(frames, ignore_index=True, sort=False)
    out = out.dropna(subset=["_data"]).sort_values("_data").reset_index(drop=True)
    return [out]


def perpuno_frame(df, liga_kod, liga_emer):
    rreshtat = []
    for idx in range(len(df)):
        m = df.iloc[idx]
        try:
            home = str(m["HomeTeam"])
            away = str(m["AwayTeam"])
            gh = int(m["FTHG"])
            ga = int(m["FTAG"])
        except Exception:
            continue

        def safe_int_ht(col):
            try:
                v = m[col]
                return int(v) if not pd.isna(v) else None
            except Exception:
                return None
        ght = safe_int_ht("HTHG")
        gat = safe_int_ht("HTAG")

        ah_line = first_col(m, ["AHh", "BbAHh", "AHCh"])
        ah_home = first_col(m, ["B365AHH", "AvgAHH", "BbAvAHH", "MaxAHH", "PAHH", "B365CAHH", "AvgCAHH"])
        ah_away = first_col(m, ["B365AHA", "AvgAHA", "BbAvAHA", "MaxAHA", "PAHA", "B365CAHA", "AvgCAHA"])
        ou_over = first_col(m, ["B365>2.5", "Avg>2.5", "BbAv>2.5", "Max>2.5", "P>2.5"])
        ou_under = first_col(m, ["B365<2.5", "Avg<2.5", "BbAv<2.5", "Max<2.5", "P<2.5"])

        # ── H2H (tani kryq-sezonal kur KRYQ_SEZONE=True) ──
        _hist = df.iloc[:idx]
        _h2h = _hist[((_hist["HomeTeam"] == home) & (_hist["AwayTeam"] == away)) |
                     ((_hist["HomeTeam"] == away) & (_hist["AwayTeam"] == home))]
        h2h_n = len(_h2h)
        h2h_gola_tot = h2h_hw = h2h_dr = h2h_aw = 0
        if h2h_n:
            for _, hm in _h2h.iterrows():
                try:
                    _gh, _ga = hm["FTHG"], hm["FTAG"]
                    if pd.isna(_gh) or pd.isna(_ga):
                        continue
                    h2h_gola_tot += (_gh + _ga)
                    nese_home = (hm["HomeTeam"] == home)
                    _gf = _gh if nese_home else _ga
                    _gc = _ga if nese_home else _gh
                    if _gf > _gc:
                        h2h_hw += 1
                    elif _gf == _gc:
                        h2h_dr += 1
                    else:
                        h2h_aw += 1
                except Exception:
                    pass
        # None kur s'ka asnjë përballje — 0.0 do të lexohej si "ndeshje pa gola"
        h2h_avg_gola = round(h2h_gola_tot / h2h_n, 2) if h2h_n else None

        mes_liga = float(m.get("_mes_liga") or 1.35)
        f_home = llogarit_features(df, idx, home, True, mes_liga)
        f_away = llogarit_features(df, idx, away, False, mes_liga)
        rezultati = "1" if gh > ga else ("X" if gh == ga else "2")

        def safe_odd(col):
            try:
                v = m[col]
                return float(v) if not pd.isna(v) else None
            except Exception:
                return None

        d = m.get("_data") if not pd.isna(m.get("_data")) else parse_date(m.get("Date"))
        data_iso = d.strftime("%Y-%m-%d") if d is not None and d is not pd.NaT else None
        sezoni = str(m.get("_sezoni") or "0000")

        # match_id i qëndrueshëm: s'varet nga indeksi as nga lista SEZONET
        mid = f"csv_{liga_kod}_{data_iso}_{home}_{away}".replace(" ", "_")

        rreshtat.append({
            "match_id": mid, "burimi": "csv",
            "data_ndeshjes": data_iso, "liga": liga_emer,
            "sezoni": int("20" + sezoni[:2]) if sezoni[:2].isdigit() else None,
            "tipi_ndeshjes": 0,
            "home_team": home, "away_team": away,
            "home_forma_pts": f_home["forma_pts"], "away_forma_pts": f_away["forma_pts"],
            "home_avg_scored": f_home["avg_scored"], "away_avg_scored": f_away["avg_scored"],
            "home_avg_conceded": f_home["avg_conceded"], "away_avg_conceded": f_away["avg_conceded"],
            "home_avg_scored_home": f_home["avg_scored_loc"],
            "home_avg_conceded_home": f_home["avg_conceded_loc"],
            "away_avg_scored_away": f_away["avg_scored_loc"],
            "away_avg_conceded_away": f_away["avg_conceded_loc"],
            "home_avg_yellow": f_home["avg_yellow"], "away_avg_yellow": f_away["avg_yellow"],
            "home_avg_red": f_home["avg_red"], "away_avg_red": f_away["avg_red"],
            "home_attack_strength": f_home["attack_strength"],
            "away_attack_strength": f_away["attack_strength"],
            "home_defense_strength": f_home["defense_strength"],
            "away_defense_strength": f_away["defense_strength"],
            "home_volatility": f_home["volatility"], "away_volatility": f_away["volatility"],
            "home_rest_days": f_home["rest_days"], "away_rest_days": f_away["rest_days"],
            # ── GODITJE / SOT / KËNDE (NULL kur mungojnë) ──
            "home_avg_shots": f_home["avg_shots"], "away_avg_shots": f_away["avg_shots"],
            "home_avg_sot": f_home["avg_sot"], "away_avg_sot": f_away["avg_sot"],
            "home_avg_sot_against": f_home["avg_sot_against"],
            "away_avg_sot_against": f_away["avg_sot_against"],
            "home_avg_corners": f_home["avg_corners"], "away_avg_corners": f_away["avg_corners"],
            # ── H2H ──
            "h2h_avg_gola": h2h_avg_gola, "h2h_home_wins": h2h_hw,
            "h2h_draws": h2h_dr, "h2h_away_wins": h2h_aw,
            # ── KOEFAT AH + O/U 2.5 ──
            "ah_line": ah_line, "ah_home_odd": ah_home, "ah_away_odd": ah_away,
            "ou25_over": ou_over, "ou25_under": ou_under,
            # Odds + target
            "odd_home": safe_odd("B365H"), "odd_draw": safe_odd("B365D"),
            "odd_away": safe_odd("B365A"),
            "gola_home": gh, "gola_away": ga, "rezultati_1x2": rezultati,
            "gola_home_ht": ght, "gola_away_ht": gat,
        })

    return rreshtat


def ngarko(rreshtat, batch=200):
    total = 0
    for i in range(0, len(rreshtat), batch):
        pjesa = rreshtat[i:i + batch]
        try:
            r = requests.post(SUPABASE_URL, headers=HEADERS, json=pjesa, timeout=30)
            if r.status_code in [200, 201, 204]:
                total += len(pjesa)
            else:
                print(f"    Gabim: {r.status_code} - {r.text[:120]}")
        except Exception as e:
            print(f"    Gabim: {e}")
        time.sleep(0.3)
    return total


def main():
    print("=" * 58)
    print(f"IMPORTUES CSV v4  (kryq-sezonal={KRYQ_SEZONE}, NULL për të munguarat)")
    print("=" * 58)

    total_global = 0
    mungesa = {"shots": 0, "h2h": 0, "gjithsej": 0}

    for liga_kod, liga_emer in LIGAT.items():
        print(f"\n→ {liga_emer}")
        frames = merr_historikun(liga_kod)
        if not frames:
            print("  (pa të dhëna)")
            continue

        liga_total = 0
        for df in frames:
            rreshtat = perpuno_frame(df, liga_kod, liga_emer)
            if not rreshtat:
                continue
            mungesa["gjithsej"] += len(rreshtat)
            mungesa["shots"] += sum(1 for r in rreshtat if r["home_avg_sot"] is None)
            mungesa["h2h"] += sum(1 for r in rreshtat if r["h2h_avg_gola"] is None)
            liga_total += ngarko(rreshtat)

        print(f"  Total: {liga_total}")
        total_global += liga_total

    print("\n" + "=" * 58)
    print(f"TOTAL GLOBAL: {total_global} ndeshje")
    if mungesa["gjithsej"]:
        g = mungesa["gjithsej"]
        print(f"  SOT NULL: {mungesa['shots']}/{g} ({100*mungesa['shots']/g:.1f}%)  "
              f"— nëse kjo është e lartë, kolonat e goditjeve s'ia vlejnë ende")
        print(f"  H2H NULL: {mungesa['h2h']}/{g} ({100*mungesa['h2h']/g:.1f}%)")
    print("=" * 58)


if __name__ == "__main__":
    main()
