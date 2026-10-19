"""
Motor de prediccion generico, para CUALQUIER partido de cualquier liga o
competicion que tengamos cargada en data/live/ (5 grandes ligas, UEFA
history, etc.) -- a diferencia de predictor_core.py (especifico del
Mundial, con fixture fijo y team_id numericos), este trabaja con nombres
de equipo en texto plano y no necesita una lista fija de partidos: le
pasas cualquier par de equipos y arma el reporte.

Misma metodologia que ya se valido en el proyecto del Mundial:
  - Elo con decaimiento temporal + ventaja de local
  - Regresion de Poisson (sklearn PoissonRegressor) para goles esperados,
    con el Elo ESCALADO /400 antes de entrenar (bug real que encontramos
    antes: sin escalar, el optimizador diverge y el modelo predice lo
    mismo para todos los partidos)
  - Simulacion Monte Carlo para 1X2 y marcadores
  - Corners/tarjetas/remates a favor-en-contra, con shrinkage si el
    equipo tiene pocos partidos
  - Si un equipo juega una competicion sin datos de corners/tarjetas
    propios (ej. Champions League con esta fuente), se usa como
    ESTIMACION el promedio de su liga domestica -- marcado explicitamente
    como estimado, nunca mostrado como si fuera el dato real de esa copa.
"""
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from scipy.stats import poisson

warnings.filterwarnings("ignore", category=RuntimeWarning)

INITIAL_ELO = 1500.0
HOME_ADV = 60.0
ELO_SCALE = 400.0


# ============================= ELO =============================

def _k_factor(tournament: str) -> float:
    t = (tournament or "").lower()
    if "champions league" in t or "world cup" in t or "final" in t:
        return 40
    if "europa" in t or "conference" in t:
        return 32
    return 28  # liga domestica


def build_elo_ratings(results: pd.DataFrame) -> dict:
    """Recorre los partidos en orden cronologico y devuelve el Elo final
    de cada equipo. Espera columnas: date, home_team, away_team,
    home_score, away_score, tournament, neutral."""
    df = results.dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    # Partidos sin fecha (ej. UEFA history con fecha vacia) van al final del
    # orden dentro de su temporada -- no es perfecto pero no rompe nada
    if df['date'].isna().any() or df[['home_team','away_team']].isna().any().any():
        raise ValueError('Elo requires dated results and known team identities; quarantine undated UEFA history')
    df = df.sort_values("date")

    elo = {}
    for row in df.itertuples(index=False):
        h, a = row.home_team, row.away_team
        elo.setdefault(h, INITIAL_ELO)
        elo.setdefault(a, INITIAL_ELO)

        elo_h = elo[h] + (0 if getattr(row, "neutral", False) else HOME_ADV)
        elo_a = elo[a]
        exp_h = 1 / (1 + 10 ** ((elo_a - elo_h) / ELO_SCALE))

        if row.home_score > row.away_score:
            result_h = 1.0
        elif row.home_score < row.away_score:
            result_h = 0.0
        else:
            result_h = 0.5

        gd = abs(row.home_score - row.away_score)
        goal_mult = 1.0 if gd <= 1 else (1.5 if gd == 2 else (1.75 + (gd - 3) / 8))
        k = _k_factor(getattr(row, "tournament", ""))

        delta = k * goal_mult * (result_h - exp_h)
        elo[h] += delta
        elo[a] -= delta

    return elo


# ============================= GOLES ESPERADOS (POISSON) =============================

def train_goal_models(results: pd.DataFrame, elo_snapshot_fn=None):
    """Compatibility Elo regressors using strictly pre-match rating features.
    The production report uses goal_model.AttackDefenceModel instead.
    Undated results are rejected, never assigned an invented date.
    """
    df = results.dropna(subset=["home_score", "away_score"]).copy()
    df['date']=pd.to_datetime(df.date,errors='raise')
    df=df.sort_values('date').reset_index(drop=True)
    snapshots=[];elo_final={}
    # Same-day fixtures see the same ratings. Update only after features are saved.
    for date,g in df.groupby('date',sort=True):
        for idx,row in g.iterrows():snapshots.append((idx,elo_final.get(row.home_team,INITIAL_ELO),elo_final.get(row.away_team,INITIAL_ELO)))
        for row in g.itertuples():
            h,a=row.home_team,row.away_team
            eh=elo_final.get(h,INITIAL_ELO);ea=elo_final.get(a,INITIAL_ELO)
            expected=1/(1+10**((ea-eh-(0 if getattr(row,'neutral',False) else HOME_ADV))/ELO_SCALE))
            result=1. if row.home_score>row.away_score else 0. if row.home_score<row.away_score else .5
            gd=abs(row.home_score-row.away_score);mult=1. if gd<=1 else 1.5 if gd==2 else 1.75+(gd-3)/8
            delta=_k_factor(getattr(row,'tournament',''))*mult*(result-expected)
            elo_final[h]=eh+delta;elo_final[a]=ea-delta
    for idx,h,a in snapshots:df.loc[idx,['elo_home','elo_away']]=[h,a]
    df["elo_diff"] = (df["elo_home"] - df["elo_away"]) / ELO_SCALE
    df["neutral_flag"] = df.get("neutral", pd.Series(False,index=df.index)).astype(int)

    X_home = df[["elo_diff", "neutral_flag"]].to_numpy(dtype=float)
    y_home = df["home_score"].astype(float).to_numpy()
    model_home = PoissonRegressor(alpha=1e-4, max_iter=2000, tol=1e-8)
    model_home.fit(X_home, y_home)

    df["elo_diff_away"] = -df["elo_diff"]
    X_away = df[["elo_diff_away", "neutral_flag"]].to_numpy(dtype=float)
    y_away = df["away_score"].astype(float).to_numpy()
    model_away = PoissonRegressor(alpha=1e-4, max_iter=2000, tol=1e-8)
    model_away.fit(X_away, y_away)

    return model_home, model_away, elo_final


def predict_lambdas(model_home, model_away, elo_home, elo_away, neutral=False):
    diff = (elo_home - elo_away) / ELO_SCALE
    lam_h = model_home.predict(np.array([[diff, int(neutral)]]))[0]
    lam_a = model_away.predict(np.array([[-diff, int(neutral)]]))[0]
    return max(lam_h, 0.05), max(lam_a, 0.05)


# ============================= SIMULACION =============================

def simulate_match(lam_home, lam_away, n=50000, max_goals=8):
    # Compatibility name; deterministic probabilities avoid Monte Carlo noise.
    from goal_model import market_summary
    return market_summary(lam_home,lam_away)


# ============================= CORNERS/TARJETAS/REMATES =============================

STAT_COLS = ["goals_for", "goals_against", "shots_for", "shots_against",
             "sot_for", "sot_against", "corners_for", "corners_against",
             "cards_for", "cards_against", "fouls_for", "fouls_against"]


def build_recent_team_stats(match_stats: pd.DataFrame, n_recent: int = 10) -> dict:
    """Calcula, para cada equipo, sus estadisticas a favor/en contra usando
    PRIORITARIAMENTE sus ultimos `n_recent` partidos (forma reciente, no el
    promedio de toda la temporada/5 temporadas) -- separado en 3 contextos:
    'general' (mezcla local+visita), 'local' (solo de local) y 'visitante'
    (solo de visita), porque el rendimiento cambia bastante segun donde
    juega cada equipo.

    Si un equipo tiene MENOS partidos que n_recent en ese contexto (recien
    ascendido, arranque de temporada), se aplica shrinkage hacia el
    promedio general de la liga -- mismo principio que ya usabamos en el
    Mundial, pero ahora sobre la ventana reciente en vez de la temporada
    completa.

    Requiere que match_stats tenga columna 'is_home' (True/False). Si no
    la tiene (datos viejos, hay que volver a correr fetch_datahub_leagues.py
    una vez), se cae a un unico contexto 'general' sin split local/visita.
    """
    df = match_stats.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date")

    tiene_local_visita = "is_home" in df.columns

    def compute_context(sub_df: pd.DataFrame) -> pd.DataFrame:
        global_means = {c: sub_df[c].mean() for c in STAT_COLS}
        rows = []
        for team, g in sub_df.groupby("team"):
            g_recent = g.tail(n_recent)
            n = len(g_recent)
            w = min(n, n_recent) / n_recent if n_recent else 1.0
            row = {"team": team, "partidos": n}
            for c in STAT_COLS:
                val = g_recent[c].mean() if n > 0 else global_means[c]
                row[c] = round(val * w + global_means[c] * (1 - w), 2)
            rows.append(row)
        return pd.DataFrame(rows)

    out = {"general": compute_context(df)}
    if tiene_local_visita:
        out["local"] = compute_context(df[df["is_home"] == True])
        out["visitante"] = compute_context(df[df["is_home"] == False])
    else:
        out["local"] = out["general"]
        out["visitante"] = out["general"]
    out["_tiene_local_visita"] = tiene_local_visita
    out["_n_recent"] = n_recent
    return out


def project_match_stats(stats: dict, home: str, away: str) -> dict:
    """Proyecta goles/corners/tarjetas/remates/faltas del partido, usando
    el contexto CORRECTO de cada equipo: el LOCAL con su propia forma
    reciente DE LOCAL, el VISITANTE con su propia forma reciente DE
    VISITA -- no un promedio general mezclado, que subestima/sobreestima
    la ventaja de local real de cada equipo."""
    home_ctx, away_ctx = stats["local"], stats["visitante"]

    def row(ctx, team):
        r = ctx[ctx["team"] == team]
        return r.iloc[0] if not r.empty else None

    rh, ra = row(home_ctx, home), row(away_ctx, away)
    if rh is None:
        rh = row(stats["general"], home)
    if ra is None:
        ra = row(stats["general"], away)
    if rh is None or ra is None:
        faltante = home if rh is None else away
        return {"error": f"Sin estadisticas propias para '{faltante}'"}

    def proyeccion(stat_name):
        favor, contra = f"{stat_name}_for", f"{stat_name}_against"
        h = (rh[favor] + ra[contra]) / 2
        a = (ra[favor] + rh[contra]) / 2
        return round(h, 2), round(a, 2)

    def rango(mean_val):
        lo, hi = poisson.ppf([0.25, 0.75], max(mean_val, 0.1))
        return f"{int(lo)}-{int(hi)}"

    goals_h, goals_a = proyeccion("goals")
    corners_h, corners_a = proyeccion("corners")
    cards_h, cards_a = proyeccion("cards")
    shots_h, shots_a = proyeccion("shots")
    sot_h, sot_a = proyeccion("sot")
    fouls_h, fouls_a = proyeccion("fouls")

    return {
        "goals_home_favor": round(rh["goals_for"], 2), "goals_home_contra": round(rh["goals_against"], 2),
        "goals_away_favor": round(ra["goals_for"], 2), "goals_away_contra": round(ra["goals_against"], 2),
        "goals_home": goals_h, "goals_away": goals_a,
        "goals_total": round(goals_h + goals_a, 2), "goals_rango": rango(goals_h + goals_a),

        "corners_home_favor": round(rh["corners_for"], 2), "corners_home_contra": round(rh["corners_against"], 2),
        "corners_away_favor": round(ra["corners_for"], 2), "corners_away_contra": round(ra["corners_against"], 2),
        "corners_home": corners_h, "corners_away": corners_a,
        "corners_total": round(corners_h + corners_a, 2), "corners_rango": rango(corners_h + corners_a),

        "cards_home_favor": round(rh["cards_for"], 2), "cards_home_contra": round(rh["cards_against"], 2),
        "cards_away_favor": round(ra["cards_for"], 2), "cards_away_contra": round(ra["cards_against"], 2),
        "cards_home": cards_h, "cards_away": cards_a,
        "cards_total": round(cards_h + cards_a, 2), "cards_rango": rango(cards_h + cards_a),

        "shots_home_favor": round(rh["shots_for"], 2), "shots_home_contra": round(rh["shots_against"], 2),
        "shots_away_favor": round(ra["shots_for"], 2), "shots_away_contra": round(ra["shots_against"], 2),
        "shots_home": shots_h, "shots_away": shots_a,

        "sot_home_favor": round(rh["sot_for"], 2), "sot_home_contra": round(rh["sot_against"], 2),
        "sot_away_favor": round(ra["sot_for"], 2), "sot_away_contra": round(ra["sot_against"], 2),
        "sot_home": sot_h, "sot_away": sot_a,

        "fouls_home_favor": round(rh["fouls_for"], 2), "fouls_home_contra": round(rh["fouls_against"], 2),
        "fouls_away_favor": round(ra["fouls_for"], 2), "fouls_away_contra": round(ra["fouls_against"], 2),
        "fouls_home": fouls_h, "fouls_away": fouls_a,

        "partidos_home": int(rh["partidos"]), "partidos_away": int(ra["partidos"]),
    }


def head_to_head(match_stats: pd.DataFrame, team_a: str, team_b: str, n: int = 5) -> pd.DataFrame:
    """Ultimos `n` enfrentamientos DIRECTOS entre estos 2 equipos (en
    cualquiera de las 2 fuentes de datos que tengamos cargadas), mas
    recientes primero."""
    df = match_stats.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    sub = df[(df["team"] == team_a) & (df["opponent"] == team_b)].copy()
    sub = sub.sort_values("date", ascending=False).head(n)
    if sub.empty:
        return sub
    sub["marcador"] = sub["goals_for"].astype(int).astype(str) + "-" + sub["goals_against"].astype(int).astype(str)
    return sub[["date", "team", "opponent", "marcador", "corners_for", "corners_against",
                "cards_for", "cards_against"]]
