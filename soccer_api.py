# ==========================================
# SOCCER1X2 PRO API - ML ENHANCED VERSION
# Monte Carlo + Dynamic ELO + XGBoost Hybrid
# ==========================================

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
import random
import math
import time
import os
import json
import numpy as np

# ==========================================
# ML IMPORTS - instalo: pip install scikit-learn xgboost joblib numpy
# ==========================================
try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.calibration import CalibratedClassifierCV
    import xgboost as xgb
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ ML libraries nuk janë instaluar. Duke punuar vetëm me sistemin klasik.")
    print("   Instalo me: pip install scikit-learn xgboost joblib numpy")

app = FastAPI(
    title="SOCCER1X2 PRO API - ML Enhanced",
    description="Monte Carlo + Dynamic ELO + XGBoost Hybrid Prediction Engine"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# KREDENCIALET
# ==========================================
API_KEY = "ab4ee376aea19eca742126f9b804fbc5"
HEADERS = {"x-apisports-key": API_KEY}

SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xZmhseXlid3dramJrdmZwc3hpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMDU0NjksImV4cCI6MjA5NjU4MTQ2OX0.H1YFz3z9Ew3WofYbbvarP4V5rm99UjkY2mm1p2w4MBQ"
SUPABASE_URL_PREDS = "[oqfhlyybwwkjbkvfpsxi.supabase.co](https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/predictions)"
SUPABASE_URL_USERS = "[oqfhlyybwwkjbkvfpsxi.supabase.co](https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/users)"
SUPABASE_URL_DNA   = "[oqfhlyybwwkjbkvfpsxi.supabase.co](https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/team_dna_cache)"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

LIGAT_VIP_MAP = {
    39:  "England - Premier League",
    140: "Spain - La Liga",
    135: "Italy - Serie A",
    78:  "Germany - Bundesliga",
    61:  "France - Ligue 1",
    2:   "Champions League",
}

# ==========================================
# ML ENGINE - MOTORI I MACHINE LEARNING
# ==========================================

class MLPredictionEngine:
    """
    Motor parashikimi bazuar në XGBoost + Kalibrim.
    Plotëson sistemin klasik Monte Carlo + ELO.
    """

    def __init__(self):
        self.model_1x2   = None
        self.model_goals = None
        self.model_btts  = None
        self.scaler      = StandardScaler() if ML_AVAILABLE else None
        self.is_trained  = False
        self.model_path  = "models/"
        if ML_AVAILABLE:
            os.makedirs(self.model_path, exist_ok=True)

    def extract_features(self, match_data: dict) -> list:
        """
        Nxjerr 20 features nga të dhënat e ndeshjes.
        Çdo feature lidhet direkt me variablat që sistemi klasik tashmë llogarit.
        """
        home = match_data.get("home_stats", {})
        away = match_data.get("away_stats", {})
        return [
            # ELO & Fuqia
            float(home.get("elo_rating", 1500)),
            float(away.get("elo_rating", 1500)),
            float(home.get("elo_rating", 1500)) - float(away.get("elo_rating", 1500)),
            # Forma e fundit 5 ndeshje
            float(home.get("form_points_5", 7.5)),
            float(away.get("form_points_5", 7.5)),
            float(home.get("form_goals_scored_5", 1.5)),
            float(home.get("form_goals_conceded_5", 1.5)),
            float(away.get("form_goals_scored_5", 1.5)),
            float(away.get("form_goals_conceded_5", 1.5)),
            # Mesatare sezonale
            float(home.get("avg_goals_scored_home", 1.5)),
            float(home.get("avg_goals_conceded_home", 1.2)),
            float(away.get("avg_goals_scored_away", 1.1)),
            float(away.get("avg_goals_conceded_away", 1.4)),
            # Head-to-Head
            float(match_data.get("h2h_home_wins", 0)),
            float(match_data.get("h2h_draws", 0)),
            float(match_data.get("h2h_away_wins", 0)),
            float(match_data.get("h2h_avg_goals", 2.5)),
            # Kontekst
            float(match_data.get("home_advantage_index", 1.0)),
            float(match_data.get("is_derby", 0)),
            # Probabilitetet klasike (nga ELO/odds) si features shtesë
            float(match_data.get("p1_real", 0.40)),
            float(match_data.get("px_real", 0.28)),
            float(match_data.get("p2_real", 0.32)),
            # xG baze
            float(match_data.get("xg_home", 1.3)),
            float(match_data.get("xg_away", 1.1)),
            # DNA faktors
            float(match_data.get("clutch_home", 1.0)),
            float(match_data.get("clutch_away", 1.0)),
            float(match_data.get("volatility_home", 15.0)),
            float(match_data.get("volatility_away", 15.0)),
        ]

    def prepare_training_data(self, historical_matches: list):
        X, y_1x2, y_goals, y_btts = [], [], [], []
        for match in historical_matches:
            try:
                features = self.extract_features(match)
                if any(f != f for f in features):  # NaN check
                    continue
                X.append(features)
                hg = match.get("actual_home_goals", 0)
                ag = match.get("actual_away_goals", 0)
                tg = hg + ag
                y_1x2.append(0 if hg > ag else (1 if hg == ag else 2))
                y_goals.append(1 if tg > 2.5 else 0)
                y_btts.append(1 if hg > 0 and ag > 0 else 0)
            except Exception:
                continue
        return np.array(X), np.array(y_1x2), np.array(y_goals), np.array(y_btts)

    def train(self, historical_matches: list) -> float:
        if not ML_AVAILABLE:
            print("⚠️ ML nuk është i disponueshëm.")
            return 0.0

        print(f"🔄 Duke trajnuar modelet ML me {len(historical_matches)} ndeshje...")
        X, y_1x2, y_goals, y_btts = self.prepare_training_data(historical_matches)

        if len(X) < 50:
            print(f"⚠️ Nevojiten min 50 ndeshje. Ke {len(X)}.")
            return 0.0

        X_scaled = self.scaler.fit_transform(X)

        # Model 1X2
        X_tr, X_te, y_tr, y_te = train_test_split(X_scaled, y_1x2, test_size=0.2, random_state=42)
        base = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric='mlogloss', random_state=42
        )
        self.model_1x2 = CalibratedClassifierCV(base, cv=3, method='isotonic')
        self.model_1x2.fit(X_tr, y_tr)

        # Model Goals Over/Under 2.5
        Xg_tr, _, yg_tr, _ = train_test_split(X_scaled, y_goals, test_size=0.2, random_state=42)
        self.model_goals = CalibratedClassifierCV(
            xgb.XGBClassifier(n_estimators=200, max_depth=5, random_state=42,
                               use_label_encoder=False, eval_metric='logloss'),
            cv=3, method='sigmoid'
        )
        self.model_goals.fit(Xg_tr, yg_tr)

        # Model BTTS
        Xb_tr, _, yb_tr, _ = train_test_split(X_scaled, y_btts, test_size=0.2, random_state=42)
        self.model_btts = CalibratedClassifierCV(
            xgb.XGBClassifier(n_estimators=200, max_depth=5, random_state=42,
                               use_label_encoder=False, eval_metric='logloss'),
            cv=3, method='sigmoid'
        )
        self.model_btts.fit(Xb_tr, yb_tr)

        self.is_trained = True
        self._save_models()
        accuracy = float(self.model_1x2.score(X_te, y_te))
        print(f"✅ Trajnimi u krye! Accuracy 1X2: {accuracy:.2%}")
        return accuracy

    def predict(self, match_data: dict):
        """
        Kthe probabilitete ML ose None nëse modeli nuk është trajnuar.
        """
        if not ML_AVAILABLE or not self.is_trained:
            return None
        try:
            features = np.array(self.extract_features(match_data), dtype=float).reshape(1, -1)
            features_scaled = self.scaler.transform(features)

            p1x2  = self.model_1x2.predict_proba(features_scaled)[0]
            p_g   = self.model_goals.predict_proba(features_scaled)[0]
            p_b   = self.model_btts.predict_proba(features_scaled)[0]

            # Shannon entropy → confidence
            entropy     = -np.sum(p1x2 * np.log(p1x2 + 1e-9))
            max_entropy = np.log(len(p1x2))
            confidence  = float(1 - entropy / max_entropy)

            return {
                "ml_home_win": float(p1x2[0]),
                "ml_draw":     float(p1x2[1]),
                "ml_away_win": float(p1x2[2]),
                "ml_over_25":  float(p_g[1]),
                "ml_under_25": float(p_g[0]),
                "ml_btts_yes": float(p_b[1]),
                "ml_btts_no":  float(p_b[0]),
                "ml_confidence": round(confidence, 4),
            }
        except Exception as e:
            print(f"⚠️ ML predict error: {e}")
            return None

    def _save_models(self):
        try:
            joblib.dump(self.model_1x2,   f"{self.model_path}model_1x2.pkl")
            joblib.dump(self.model_goals, f"{self.model_path}model_goals.pkl")
            joblib.dump(self.model_btts,  f"{self.model_path}model_btts.pkl")
            joblib.dump(self.scaler,      f"{self.model_path}scaler.pkl")
            print("💾 Modelet ML u ruajtën.")
        except Exception as e:
            print(f"⚠️ Gabim ruajtja modelet: {e}")

    def load_models(self):
        if not ML_AVAILABLE:
            return
        try:
            self.model_1x2   = joblib.load(f"{self.model_path}model_1x2.pkl")
            self.model_goals = joblib.load(f"{self.model_path}model_goals.pkl")
            self.model_btts  = joblib.load(f"{self.model_path}model_btts.pkl")
            self.scaler      = joblib.load(f"{self.model_path}scaler.pkl")
            self.is_trained  = True
            print("✅ Modelet ML u ngarkuan nga disku.")
        except FileNotFoundError:
            print("ℹ️ Modelet ML nuk gjenden — do trajnohen herën e parë.")


# ==========================================
# PREDICTION TRACKER - FEEDBACK LOOP
# ==========================================

class PredictionTracker:
    """
    Gjurmon çdo parashikim dhe rezultatin real.
    Kjo është baza e feedback loop-it për retrajnim automatik.
    """

    def __init__(self, db_path="prediction_history.json"):
        self.db_path = db_path
        self.data    = self._load()

    def record(self, match_id: str, prediction: dict, match_data: dict):
        self.data[str(match_id)] = {
            "prediction":    prediction,
            "match_data":    match_data,
            "timestamp":     datetime.utcnow().isoformat(),
            "actual_result": None
        }
        self._save()

    def update_result(self, match_id: str, home_goals: int, away_goals: int):
        key = str(match_id)
        if key in self.data:
            self.data[key]["actual_result"] = {
                "home_goals": home_goals,
                "away_goals": away_goals,
                "outcome":    "H" if home_goals > away_goals else ("D" if home_goals == away_goals else "A")
            }
            self._save()

    def get_accuracy_stats(self) -> dict:
        completed = [v for v in self.data.values() if v.get("actual_result")]
        if not completed:
            return {"total": 0, "correct": 0, "accuracy": 0.0}
        correct = 0
        for item in completed:
            pred = item["prediction"]
            best = max(
                [("H", pred.get("home_win", 0)),
                 ("D", pred.get("draw", 0)),
                 ("A", pred.get("away_win", 0))],
                key=lambda x: x[1]
            )[0]
            if best == item["actual_result"]["outcome"]:
                correct += 1
        return {
            "total":    len(completed),
            "correct":  correct,
            "accuracy": round(correct / len(completed), 4)
        }

    def get_training_data(self) -> list:
        return [
            {
                **item["match_data"],
                "actual_home_goals": item["actual_result"]["home_goals"],
                "actual_away_goals": item["actual_result"]["away_goals"],
            }
            for item in self.data.values()
            if item.get("actual_result") is not None
        ]

    def _load(self):
        try:
            with open(self.db_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self):
        try:
            with open(self.db_path, "w") as f:
                json.dump(self.data, f)
        except Exception as e:
            print(f"⚠️ Tracker save error: {e}")


# ==========================================
# INICIALIZIMI I ML ENGINE & TRACKER
# ==========================================

ml_engine         = MLPredictionEngine()
ml_engine.load_models()
prediction_tracker = PredictionTracker()


# ==========================================
# FUNKSIONI HYBRID - ML + KLASIK I KOMBINUAR
# ==========================================

def hybrid_blend(classical: dict, ml_result: dict) -> dict:
    """
    Kombinon probabilitetet klasike (Monte Carlo + ELO) me ML.
    Pesha e ML rritet me besueshmërinë e modelit (max 70%).
    Nën pragun 0.52 → sistemi klasik mbizotëron plotësisht.
    """
    if ml_result is None or ml_result.get("ml_confidence", 0) < 0.52:
        return {**classical, "prediction_source": "classical", "ml_confidence": 0.0}

    w_ml  = min(ml_result["ml_confidence"], 0.70)
    w_cls = 1.0 - w_ml

    blended = {
        "home_win": round(ml_result["ml_home_win"] * w_ml + classical.get("home_win", 0.4) * w_cls, 4),
        "draw":     round(ml_result["ml_draw"]     * w_ml + classical.get("draw",     0.28) * w_cls, 4),
        "away_win": round(ml_result["ml_away_win"] * w_ml + classical.get("away_win", 0.32) * w_cls, 4),
        "over_25":  round(ml_result["ml_over_25"]  * w_ml + classical.get("over_25",  0.52) * w_cls, 4),
        "btts_yes": round(ml_result["ml_btts_yes"] * w_ml + classical.get("btts_yes", 0.50) * w_cls, 4),
        "prediction_source": "hybrid",
        "ml_confidence":     round(ml_result["ml_confidence"], 4),
        "ml_weight_used":    round(w_ml, 2),
    }
    return blended


# ==========================================
# MODULI 1: HISTORIKU & DNA E SKUADRAVE
# ==========================================

GIGANTET_ELO = {
    "Real Madrid": 950, "Manchester City": 945, "Bayern Munich": 920,
    "Arsenal": 910, "Liverpool": 905, "Barcelona": 890,
    "Paris Saint Germain": 885, "Inter": 880, "Bayer Leverkusen": 870,
    "Juventus": 850, "AC Milan": 845, "Atletico Madrid": 840,
    "Argentina": 960, "France": 950, "England": 930, "Spain": 920,
    "Brazil": 910, "Germany": 890, "Portugal": 880, "Italy": 870,
    "Netherlands": 860
}

def merr_elo_baze(ekipi):
    for emri, elo in GIGANTET_ELO.items():
        if emri.lower() in ekipi.lower():
            return elo
    return 600

def merr_dna_nga_db(team_id):
    try:
        res = requests.get(
            f"{SUPABASE_URL_DNA}?team_id=eq.{team_id}",
            headers=SUPABASE_HEADERS, timeout=2
        )
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()[0]
    except Exception:
        pass
    return None

def is_vip_league(emri_liges):
    return any(vip.lower() in emri_liges.lower() for vip in LIGAT_VIP_MAP.values())


# ==========================================
# MODULI 2: DINAMIKA E SË TASHMES
# ==========================================

def llogarit_lodhjen_e_series(k_wins, prob_baze_fitore):
    alpha = 0.08
    f_s = 1 - math.pow((1 - alpha), k_wins)
    prob_re_fitore = prob_baze_fitore * (1 - f_s)
    diff = prob_baze_fitore - prob_re_fitore
    return prob_re_fitore, diff * 0.70, diff * 0.30

def llogarit_desperation_index(ekipi_id, standings):
    if not standings:
        return 1.0
    try:
        for r in standings:
            if r.get("team", {}).get("id") == ekipi_id:
                pozicioni   = r.get("rank", 10)
                total_ekipe = len(standings)
                if pozicioni >= total_ekipe - 3 or pozicioni <= 3:
                    return 1.15
    except Exception:
        pass
    return 1.0

def apliko_kaosin_e_liges(emri_liges):
    liga_lower = emri_liges.lower()
    if any(x in liga_lower for x in ["world cup", "euro", "copa america", "nations league"]):
        return 1.30
    elif any(x in liga_lower for x in ["championship", "segunda", "ligue 2", "serie b", "superliga"]):
        return 1.25
    elif any(x in liga_lower for x in ["premier", "champions league", "la liga", "bundesliga"]):
        return 1.05
    return 1.10

def detect_value_bet(prob_modeli, koef_bookmaker):
    try:
        koef = float(koef_bookmaker)
        if koef <= 1.0:
            return None
        prob_impl = 1 / koef
        value = (prob_modeli * koef) - 1
        if value > 0.05:
            return round(value * 100, 1)
    except Exception:
        pass
    return None


# ==========================================
# MODULI 3: MONTE CARLO SIMULATION
# ==========================================

def simulim_monte_carlo(xg_1, xg_2, kaos_factor, is_derbi):
    iteracione = 10000
    rezultatet_freq = {}
    if is_derbi:
        kaos_factor *= 1.20

    def poisson_gola(lmbda):
        L = math.exp(-lmbda)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= random.uniform(0, 1)
        return k - 1

    for _ in range(iteracione):
        xg1_virtual = max(0.1, random.gauss(xg_1, xg_1 * 0.2 * kaos_factor))
        xg2_virtual = max(0.1, random.gauss(xg_2, xg_2 * 0.2 * kaos_factor))
        gola_1 = poisson_gola(xg1_virtual)
        gola_2 = poisson_gola(xg2_virtual)
        rez = f"{gola_1}-{gola_2}"
        rezultatet_freq[rez] = rezultatet_freq.get(rez, 0) + 1

    rez_max  = max(rezultatet_freq, key=rezultatet_freq.get)
    prob_max = rezultatet_freq[rez_max] / iteracione
    return rez_max, prob_max, rezultatet_freq


# ==========================================
# MODULI 4: ANALIZUESI PREMIUM MASTER (HYBRID)
# ==========================================

def analizo_ndeshjen_premium_master(
    id_ndeshja, ekipi_1, ekipi_2,
    ekipi_1_id, ekipi_2_id,
    k1_str, kx_str, k2_str,
    emri_liges, standings
):
    k1, kx, k2 = float(k1_str), float(kx_str), float(k2_str)

    prob_1, prob_x, prob_2 = 1/k1, 1/kx, 1/k2
    marzhi = prob_1 + prob_x + prob_2
    p1_real, px_real, p2_real = prob_1/marzhi, prob_x/marzhi, prob_2/marzhi

    dna_1 = merr_dna_nga_db(str(ekipi_1_id))
    dna_2 = merr_dna_nga_db(str(ekipi_2_id))

    elo_1 = dna_1.get("historical_power", merr_elo_baze(ekipi_1)) if dna_1 else merr_elo_baze(ekipi_1)
    elo_2 = dna_2.get("historical_power", merr_elo_baze(ekipi_2)) if dna_2 else merr_elo_baze(ekipi_2)

    clutch_1 = float(dna_1.get("clutch_factor",    1.0))  if dna_1 else 1.0
    clutch_2 = float(dna_2.get("clutch_factor",    1.0))  if dna_2 else 1.0
    vol_1    = float(dna_1.get("volatility_index", 15.0)) if dna_1 else 15.0
    vol_2    = float(dna_2.get("volatility_index", 15.0)) if dna_2 else 15.0

    desp_1     = llogarit_desperation_index(ekipi_1_id, standings)
    desp_2     = llogarit_desperation_index(ekipi_2_id, standings)
    kaosi_liges = apliko_kaosin_e_liges(emri_liges)

    if vol_1 > 20.0 or vol_2 > 20.0:
        kaosi_liges *= 1.15
    is_derbi = abs(elo_1 - elo_2) <= 30

    k_wins_sim = random.randint(0, 4)
    p1_adj, px_add1, p2_add1 = llogarit_lodhjen_e_series(k_wins_sim, p1_real)
    p2_adj, px_add2, p1_add2 = llogarit_lodhjen_e_series(random.randint(0, 2), p2_real)

    vb_1_val = detect_value_bet(p1_adj, k1)
    vb_2_val = detect_value_bet(p2_adj, k2)
    vb_text_sq = (
        f"<br><b style='color:#00ff00;'>💎 Value Bet:</b> Fiton 1 (Vlera: {vb_1_val}%)" if vb_1_val else
        (f"<br><b style='color:#00ff00;'>💎 Value Bet:</b> Fiton 2 (Vlera: {vb_2_val}%)" if vb_2_val else "")
    )

    diferenca_elo = (elo_1 * desp_1) - (elo_2 * desp_2)
    xg_1_baze = max(0.40, (p1_adj * 3.15) + (diferenca_elo / 850.0))
    xg_2_baze = max(0.40, (p2_adj * 3.15) - (diferenca_elo / 850.0))

    if is_derbi:
        xg_1_baze *= clutch_1 * 0.92
        xg_2_baze *= clutch_2 * 0.92
    else:
        xg_1_baze *= clutch_1
        xg_2_baze *= clutch_2

    draw_1 = float(dna_1.get("draw_affinity", 30.0)) if dna_1 else 30.0
    draw_2 = float(dna_2.get("draw_affinity", 30.0)) if dna_2 else 30.0
    if draw_1 > 35.0 and draw_2 > 35.0:
        xg_1_baze *= 0.85
        xg_2_baze *= 0.85

    if is_derbi or px_real > 0.30:
        xg_1_baze *= 1.25
        xg_2_baze *= 1.25

    # ---- MONTE CARLO (sistemi klasik) ----
    rezultati_sakt_mc, probabiliteti_rez_sakt, rezultatet_freq = simulim_monte_carlo(
        xg_1_baze, xg_2_baze, kaosi_liges, is_derbi
    )

    # ---- ML HYBRID BLEND ----
    match_data_for_ml = {
        "home_stats": {
            "elo_rating":             elo_1,
            "form_points_5":          7.5,
            "form_goals_scored_5":    xg_1_baze,
            "form_goals_conceded_5":  xg_2_baze,
            "avg_goals_scored_home":  xg_1_baze,
            "avg_goals_conceded_home": xg_2_baze,
        },
        "away_stats": {
            "elo_rating":             elo_2,
            "form_points_5":          7.5,
            "form_goals_scored_5":    xg_2_baze,
            "form_goals_conceded_5":  xg_1_baze,
            "avg_goals_scored_away":  xg_2_baze,
            "avg_goals_conceded_away": xg_1_baze,
        },
        "h2h_home_wins":       0,
        "h2h_draws":           0,
        "h2h_away_wins":       0,
        "h2h_avg_goals":       xg_1_baze + xg_2_baze,
        "home_advantage_index": 1.0,
        "is_derby":            1 if is_derbi else 0,
        "p1_real":             p1_real,
        "px_real":             px_real,
        "p2_real":             p2_real,
        "xg_home":             xg_1_baze,
        "xg_away":             xg_2_baze,
        "clutch_home":         clutch_1,
        "clutch_away":         clutch_2,
        "volatility_home":     vol_1,
        "volatility_away":     vol_2,
    }

    # Probabilitetet klasike (nga MC + ELO)
    total_sims = sum(rezultatet_freq.values())
    home_wins  = sum(v for k, v in rezultatet_freq.items() if int(k.split("-")[0]) > int(k.split("-")[1]))
    draws      = sum(v for k, v in rezultatet_freq.items() if int(k.split("-")[0]) == int(k.split("-")[1]))
    away_wins  = sum(v for k, v in rezultatet_freq.items() if int(k.split("-")[0]) < int(k.split("-")[1]))
    over_25    = sum(v for k, v in rezultatet_freq.items() if (int(k.split("-")[0]) + int(k.split("-")[1])) > 2)
    btts       = sum(v for k, v in rezultatet_freq.items() if int(k.split("-")[0]) > 0 and int(k.split("-")[1]) > 0)

    classical_probs = {
        "home_win": home_wins / total_sims,
        "draw":     draws     / total_sims,
        "away_win": away_wins / total_sims,
        "over_25":  over_25   / total_sims,
        "btts_yes": btts      / total_sims,
    }

    ml_result  = ml_engine.predict(match_data_for_ml)
    final_pred = hybrid_blend(classical_probs, ml_result)

    # ---- Regjistro parashikimin për feedback loop ----
    prediction_tracker.record(
        match_id=str(id_ndeshja),
        prediction={
            "home_win": final_pred["home_win"],
            "draw":     final_pred["draw"],
            "away_win": final_pred["away_win"],
        },
        match_data=match_data_for_ml
    )

    # ---- Besueshmëria finale (ML e rrit nëse confidence e lartë) ----
    g1_str, g2_str = rezultati_sakt_mc.split("-")
    g1, g2 = int(g1_str), int(g2_str)

    ml_boost  = int(ml_result["ml_confidence"] * 10) if ml_result else 0
    besueshmeria = min(95, max(55,
        int(probabiliteti_rez_sakt * 100) + 5 + ml_boost +
        (5 if vb_1_val or vb_2_val else 0) +
        (3 if is_derbi else 0)
    ))

    koef_rez_sakt = rezultatet_freq.get(rezultati_sakt_mc, 1) / total_sims
    koef_rez_sakt = round(1 / koef_rez_sakt, 2) if koef_rez_sakt > 0 else 99.0
    eshte_ndeshje_bllof = besueshmeria >= 78 and koef_rez_sakt >= 4.0

    # ML info string për analizë
    ml_info = ""
    if ml_result and ml_result["ml_confidence"] >= 0.52:
        src = "🤖 ML+Klasik"
        ml_info = f"<br><b style='color:#00bfff;'>{src} ({int(ml_result['ml_confidence']*100)}% besim)</b>"

    ht_ft_text = ""

    # Analiza tekstuale (mbetet si sistemi origjinal)
    if g1 == g2:
        anal_dict = {
            "sq": f"Ndeshje e balancuar mes <b>{ekipi_1}</b> dhe <b>{ekipi_2}</b>.<br>"
                  f"<b style='color:#f2cc60;'>Sugjerim:</b> Barazim ose Nën 2.5 gola.{ht_ft_text}{vb_text_sq}{ml_info}"
        }
    elif g1 > g2:
        anal_dict = {
            "sq": (
                f"<b>{ekipi_1}</b> dominon me ELO <b>{int(elo_1)}</b>.<br>"
                f"<b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Mbi 2.5 gola.{ht_ft_text}{vb_text_sq}{ml_info}"
                if (g1 + g2) >= 3 else
                f"<b>{ekipi_1}</b> kontrollon taktikisht.<br>"
                f"<b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_1} ose Nën 3.5 gola.{ht_ft_text}{vb_text_sq}{ml_info}"
            )
        }
    else:
        anal_dict = {
            "sq": (
                f"<b>{ekipi_2}</b> performon shkëlqyeshëm në transfertë.<br>"
                f"<b style='color:#f2cc60;'>Sugjerim:</b> Fiton {ekipi_2} ose Mbi 2.5 gola.{ht_ft_text}{vb_text_sq}{ml_info}"
                if (g1 + g2) >= 3 else
                f"Ndeshje ku <b>{ekipi_2}</b> menaxhon lojën.<br>"
                f"<b style='color:#f2cc60;'>Sugjerim:</b> X2 ose Nën 2.5 gola.{ht_ft_text}{vb_text_sq}{ml_info}"
            )
        }

    return (
        anal_dict,
        besueshmeria,
        rezultati_sakt_mc,
        f"{koef_rez_sakt:.2f}",
        {
            "is_bllof":  eshte_ndeshje_bllof,
            "koef_plote": f"1:{k1_str} | X:{kx_str} | 2:{k2_str}"
        }
    )


# ==========================================
# ENDPOINTI KRYESOR - SKEDINA & PPM
# ==========================================

SKEDINA_CACHE       = {}
SKEDINA_LAST_UPDATE = {}
STANDINGS_CACHE     = {}


@app.get("/api/skedina")
def merr_parashikimet(background_tasks: BackgroundTasks, date: str = None):
    data_target = date if date else datetime.utcnow().strftime('%Y-%m-%d')
    koha_tani   = time.time()

    if data_target in SKEDINA_CACHE and (koha_tani - SKEDINA_LAST_UPDATE.get(data_target, 0) < 600):
        return {"mesazhi": "Sukses", "skedina_grupuar": SKEDINA_CACHE[data_target]}

    try:
        response  = requests.get(
            "[v3.football.api-sports.io](https://v3.football.api-sports.io/fixtures)",
            headers=HEADERS, params={"date": data_target}, timeout=10
        )
        te_dhenat = response.json()
        if "errors" in te_dhenat and te_dhenat["errors"]:
            return {"mesazhi": "Gabim", "skedina_grupuar": [], "error_msg": str(te_dhenat["errors"])}

        bet365_odds = {}
        try:
            res_odds = requests.get(
                "[v3.football.api-sports.io](https://v3.football.api-sports.io/odds)",
                headers=HEADERS, params={"date": data_target, "bookmaker": 8, "page": 1}, timeout=10
            ).json()
            if "response" in res_odds:
                for item in res_odds["response"]:
                    fix_id = str(item["fixture"]["id"])
                    try:
                        bets = item["bookmakers"][0]["bets"]
                        mw   = next((b for b in bets if b["id"] == 1 or b["name"] == "Match Winner"), None)
                        if mw:
                            v = mw["values"]
                            bet365_odds[fix_id] = {
                                "1": next((x["odd"] for x in v if x["value"] == "Home"), None),
                                "X": next((x["odd"] for x in v if x["value"] == "Draw"), None),
                                "2": next((x["odd"] for x in v if x["value"] == "Away"), None),
                            }
                    except Exception:
                        pass
        except Exception:
            pass

        ligat_raw = {}
        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                if emri_liges not in ligat_raw:
                    ligat_raw[emri_liges] = []
                ligat_raw[emri_liges].append(n)

        STANDINGS_CACHE_local = {}

        vip_kandidatet  = []
        lista_e_te_gjithave = []

        for emri_liges, ndeshjet in ligat_raw.items():
            eshte_liga_vip = is_vip_league(emri_liges)
            standings = []

            if eshte_liga_vip:
                try:
                    liga_id = next(
                        (lid for lid, lname in LIGAT_VIP_MAP.items() if lname.lower() in emri_liges.lower()),
                        None
                    )
                    if liga_id and liga_id not in STANDINGS_CACHE_local:
                        sezon = datetime.utcnow().year
                        res_st = requests.get(
                            "[v3.football.api-sports.io](https://v3.football.api-sports.io/standings)",
                            headers=HEADERS, params={"league": liga_id, "season": sezon}, timeout=5
                        ).json()
                        if "response" in res_st and res_st["response"]:
                            STANDINGS_CACHE_local[liga_id] = res_st["response"][0]["league"]["standings"][0]
                    standings = STANDINGS_CACHE_local.get(liga_id, [])
                except Exception:
                    pass

            for n in ndeshjet:
                statusi     = n["fixture"]["status"]["short"]
                id_ndeshja  = str(n["fixture"]["id"])
                ekipi_1     = n["teams"]["home"]["name"]
                ekipi_2     = n["teams"]["away"]["name"]
                odds_data   = bet365_odds.get(id_ndeshja, {})
                k1  = odds_data.get("1")
                kx  = odds_data.get("X")
                k2  = odds_data.get("2")

                base_match = {
                    "id":        id_ndeshja,
                    "liga_emri": emri_liges,
                    "ekipi_1":   ekipi_1,
                    "ekipi_2":   ekipi_2,
                    "statusi":   statusi,
                    "ora":       n["fixture"]["date"],
                    "is_bllof":  False,
                    "koef_plote": f"1:{k1} | X:{kx} | 2:{k2}" if k1 else "N/A",
                }

                if eshte_liga_vip and k1 and kx and k2:
                    try:
                        analiza_custom, besueshmeria, rez_sakt, koef_rez_sakt, extradb = analizo_ndeshjen_premium_master(
                            id_ndeshja, ekipi_1, ekipi_2,
                            n["teams"]["home"]["id"], n["teams"]["away"]["id"],
                            k1, kx, k2, emri_liges, standings
                        )
                        base_match.update({
                            "analiza_custom": analiza_custom,
                            "besueshmeria":   besueshmeria,
                            "rezultati_sakt": rez_sakt,
                            "koef_rez_sakt":  koef_rez_sakt,
                            "is_bllof":       extradb["is_bllof"],
                            "koef_plote":     extradb["koef_plote"],
                        })
                        vip_kandidatet.append(base_match)
                    except Exception:
                        lista_e_te_gjithave.append(base_match)
                else:
                    lista_e_te_gjithave.append(base_match)

        # Rendit VIP sipas besueshmërisë dhe merr top 3
        vip_kandidatet.sort(key=lambda x: x.get("besueshmeria", 0), reverse=True)
        ppm_matches    = vip_kandidatet[:3]
        other_matches  = vip_kandidatet[3:] + lista_e_te_gjithave

        skedina_grupuar = {}
        for m in ppm_matches:
            liga = m.get("liga_emri", "VIP")
            skedina_grupuar.setdefault(liga, []).append(m)
        for m in other_matches:
            liga = m.get("liga_emri", "Të tjera")
            skedina_grupuar.setdefault(liga, []).append(m)

        SKEDINA_CACHE[data_target]       = skedina_grupuar
        SKEDINA_LAST_UPDATE[data_target] = time.time()

        return {"mesazhi": "Sukses", "skedina_grupuar": skedina_grupuar}

    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "skedina_grupuar": []}


# ==========================================
# MIDNIGHT TASK - PËRDITËSIMI I ELO + FEEDBACK
# ==========================================

@app.get("/api/cron/update_elo_midnight")
def update_elo_midnight():
    dje = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        res = requests.get(
            "[v3.football.api-sports.io](https://v3.football.api-sports.io/fixtures)",
            headers=HEADERS, params={"date": dje}, timeout=15
        )
        ndeshjet_dje = res.json().get("response", [])
    except Exception:
        return {"sukses": False, "mesazhi": "Gabim lidhjeje me API-Sports"}

    ekipe_te_perditesuara = 0
    for m in ndeshjet_dje:
        if m["fixture"]["status"]["short"] not in ["FT", "AET", "PEN"]:
            continue

        emri_liges = f"{m['league']['country']} - {m['league']['name']}"
        if not is_vip_league(emri_liges):
            continue

        home_id    = str(m["teams"]["home"]["id"])
        away_id    = str(m["teams"]["away"]["id"])
        home_goals = m["goals"]["home"]
        away_goals = m["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue

        # --- Përditëso feedback loop ---
        fix_id = str(m["fixture"]["id"])
        prediction_tracker.update_result(fix_id, home_goals, away_goals)

        dna_home = merr_dna_nga_db(home_id)
        dna_away = merr_dna_nga_db(away_id)
        if not dna_home and not dna_away:
            continue

        elo_home = dna_home.get("historical_power", 600) if dna_home else 600
        elo_away = dna_away.get("historical_power", 600) if dna_away else 600

        r_home, r_away = elo_home + 65, elo_away
        e_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        e_away = 1 - e_home

        if home_goals > away_goals:   s_home, s_away = 1.0, 0.0
        elif home_goals == away_goals: s_home, s_away = 0.5, 0.5
        else:                          s_home, s_away = 0.0, 1.0

        gd         = abs(home_goals - away_goals)
        multiplier = math.log(gd + 1) + 1 if gd > 0 else 1

        new_elo_home = elo_home + 32 * multiplier * (s_home - e_home)
        new_elo_away = elo_away + 32 * multiplier * (s_away - e_away)

        if dna_home:
            requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{home_id}",
                headers=SUPABASE_HEADERS,
                json={"historical_power": round(new_elo_home, 1)}
            )
            ekipe_te_perditesuara += 1
        if dna_away:
            requests.patch(
                f"{SUPABASE_URL_DNA}?team_id=eq.{away_id}",
                headers=SUPABASE_HEADERS,
                json={"historical_power": round(new_elo_away, 1)}
            )
            ekipe_te_perditesuara += 1

    # --- Auto-retrajnim nëse kemi të dhëna të mjaftueshme ---
    training_data = prediction_tracker.get_training_data()
    retrajnuar    = False
    if ML_AVAILABLE and len(training_data) >= 50 and len(training_data) % 25 == 0:
        ml_engine.train(training_data)
        retrajnuar = True

    return {
        "sukses":              True,
        "ekipe_perditesuar":   ekipe_te_perditesuara,
        "feedback_loop":       len(training_data),
        "ml_retrajnuar":       retrajnuar,
    }


# ==========================================
# ENDPOINT: LIVE NDESHJET
# ==========================================

@app.get("/api/live")
def merr_ndeshjet_live():
    try:
        res = requests.get(
            "[v3.football.api-sports.io](https://v3.football.api-sports.io/fixtures)",
            headers=HEADERS, params={"live": "all"}, timeout=8
        )
        te_dhenat    = res.json()
        ndeshjet_live = []

        if "response" in te_dhenat:
            for n in te_dhenat["response"]:
                statusi_kod = n["fixture"]["status"]["short"]
                if statusi_kod not in ["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]:
                    continue

                id_ndeshja = str(n["fixture"]["id"])
                emri_liges = f"{n['league']['country']} - {n['league']['name']}"
                ekipi_1    = n["teams"]["home"]["name"]
                ekipi_2    = n["teams"]["away"]["name"]
                minuta     = n["fixture"]["status"].get("elapsed", 0)
                gola_1     = n["goals"]["home"] if n["goals"]["home"] is not None else 0
                gola_2     = n["goals"]["away"] if n["goals"]["away"] is not None else 0

                ndeshjet_live.append({
                    "id":        id_ndeshja,
                    "liga_emri": emri_liges,
                    "ekipi_1":   ekipi_1,
                    "ekipi_2":   ekipi_2,
                    "statusi":   statusi_kod,
                    "minuta":    f"{minuta}'",
                    "rezultati": f"{gola_1} - {gola_2}",
                })

        return {"mesazhi": "Sukses", "ndeshjet": ndeshjet_live}
    except Exception as e:
        return {"mesazhi": "Gabim", "detaje": str(e), "ndeshjet": []}


# ==========================================
# ENDPOINT: KOEFICIENTËT E NDESHJES
# ==========================================

@app.get("/api/koeficientet/{match_id}")
def merr_koeficientet(match_id: str):
    try:
        res  = requests.get(
            "[v3.football.api-sports.io](https://v3.football.api-sports.io/odds)",
            headers=HEADERS, params={"fixture": match_id, "bookmaker": 8}, timeout=8
        )
        data = res.json()
        if not data.get("response"):
            return {"mesazhi": "Nuk ka koeficientë realë", "koeficientet": []}

        bets           = data["response"][0]["bookmakers"][0]["bets"]
        tregjet_rezultat = []

        def get_bet(b_id):
            return next((b for b in bets if b["id"] == b_id), None)

        b13 = get_bet(13)
        if b13:
            tregjet_rezultat.append({
                "tregu_id": "ht_result",
                "opsionet": [{"emer": v["value"].replace("Home","1").replace("Draw","X").replace("Away","2") + " (HT)", "koef": v["odd"]} for v in b13["values"]]
            })
        b12 = get_bet(12)
        if b12:
            tregjet_rezultat.append({
                "tregu_id": "double_chance",
                "opsionet": [{"emer": v["value"].replace("Home/Draw","1X").replace("Home/Away","12").replace("Draw/Away","X2"), "koef": v["odd"]} for v in b12["values"]]
            })
        b5 = get_bet(5)
        if b5:
            tregjet_rezultat.append({
                "tregu_id": "goals_35_65",
                "opsionet": [{"emer": f"Mbi {g}" if "Over" in v["value"] else f"Nën {g}", "koef": v["odd"]} for v in b5["values"] for g in ["2.5"] if g in v["value"]]
            })
        b8 = get_bet(8)
        if b8:
            tregjet_rezultat.append({
                "tregu_id": "btts",
                "opsionet": [{"emer": "Po (GG)" if v["value"] == "Yes" else "Jo (NG)", "koef": v["odd"]} for v in b8["values"]]
            })
        b10 = get_bet(10)
        if b10:
            tregjet_rezultat.append({
                "tregu_id": "correct_score",
                "opsionet": [{"emer": v["value"].replace(":", "-"), "koef": v["odd"]} for v in b10["values"] if v["value"] in ["1:0","2:0","2:1","0:0","1:1","0:1","0:2","1:2"]]
            })

        return {"mesazhi": "Sukses", "koeficientet": tregjet_rezultat}
    except Exception:
        return {"mesazhi": "Gabim", "koeficientet": []}


# ==========================================
# ENDPOINT: RENDITJA E LIGËS
# ==========================================

@app.get("/api/renditja/{league_id}/{season}")
def merr_renditjen(league_id: int, season: int, team: str = None):
    try:
        res = requests.get(
            "[v3.football.api-sports.io](https://v3.football.api-sports.io/standings)",
            headers=HEADERS, params={"league": league_id, "season": season}, timeout=8
        )
        data = res.json()
        if not data.get("response"):
            return {"renditja": []}

        standings = data["response"][0]["league"]["standings"][0]
        renditja  = []
        for r in standings:
            ekipi_emer = r["team"]["name"]
            forma_raw  = r.get("form", "")
            forma_html = "".join(
                f"<span style='color:{'#2ea043' if c=='W' else ('#f85149' if c=='L' else '#d29922')}'>{c}</span>"
                for c in forma_raw[-5:]
            )
            row = {
                "pozicioni": r["rank"],
                "ekipi":     ekipi_emer,
                "luajtur":   r["all"]["played"],
                "fitore":    r["all"]["win"],
                "barazim":   r["all"]["draw"],
                "humbje":    r["all"]["lose"],
                "gola":      f"{r['all']['goals']['for']}-{r['all']['goals']['against']}",
                "pike":      r["points"],
                "forma":     forma_html,
            }
            if not team or team.lower() in ekipi_emer.lower():
                renditja.append(row)

        return {"renditja": renditja}
    except Exception as e:
        return {"renditja": [], "error": str(e)}


# ==========================================
# ML ENDPOINTS - TË RINJ
# ==========================================

@app.post("/api/ml/train")
def train_ml_model():
    """
    Trajno modelin ML mbi të dhënat e akumuluara nga feedback loop.
    Thirre këtë manualisht ose nga cron pas 50+ ndeshje të regjistruara.
    """
    if not ML_AVAILABLE:
        return {"status": "error", "message": "ML libraries nuk janë instaluar."}

    training_data = prediction_tracker.get_training_data()
    if len(training_data) < 50:
        return {
            "status":  "error",
            "message": f"Nevojiten min 50 ndeshje të kompletuara. Ke {len(training_data)}."
        }

    accuracy = ml_engine.train(training_data)
    return {
        "status":           "success",
        "ndeshje_trajnim":  len(training_data),
        "accuracy_1x2":     f"{accuracy:.2%}",
        "mesazh":           "Modeli ML u trajnua dhe u ruajt."
    }


@app.get("/api/ml/stats")
def merr_ml_stats():
    """
    Statistikat e modelit dhe accuracy e feedback loop-it.
    """
    stats = prediction_tracker.get_accuracy_stats()
    return {
        "ml_aktiv":          ML_AVAILABLE and ml_engine.is_trained,
        "ml_libraries":      ML_AVAILABLE,
        "total_parashikime": stats["total"],
        "korrekte":          stats["correct"],
        "accuracy":          f"{stats['accuracy']:.2%}" if stats["total"] > 0 else "N/A",
        "feedback_data":     len(prediction_tracker.get_training_data()),
        "mesazh":            "Modeli ML po punon." if (ML_AVAILABLE and ml_engine.is_trained) else "Sistemi klasik aktiv."
    }


@app.post("/api/ml/update-result")
def update_result_manual(match_id: str, home_goals: int, away_goals: int):
    """
    Përditëso manualisht rezultatin real të një ndeshje.
    Përdoret për testim ose korrigjim manual.
    """
    prediction_tracker.update_result(match_id, home_goals, away_goals)
    return {"status": "success", "match_id": match_id, "result": f"{home_goals}-{away_goals}"}


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/")
def root():
    return {
        "app":        "SOCCER1X2 PRO API",
        "version":    "3.0 - ML Enhanced",
        "ml_aktiv":   ML_AVAILABLE and ml_engine.is_trained,
        "ml_libs":    ML_AVAILABLE,
        "status":     "running"
    }
