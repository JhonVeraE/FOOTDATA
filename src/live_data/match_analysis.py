"""
Fase B: cruces (ataque de uno vs defensa del otro), H2H ponderado por
recencia, categoria de confianza / "sin ventaja clara", y el informe
completo de 15 secciones que se pidio.

TRANSPARENCIA: los pesos usados para combinar cruce + H2H (90%/10% por
defecto) y los umbrales de "sin ventaja clara" son heuristicas razonables
de arranque, EXPLICITAMENTE marcadas como pendientes de calibrar con
backtesting real (Fase C) -- no se presentan como numeros optimizados.
"""
import numpy as np
import pandas as pd
from scipy.stats import poisson

from team_profile import build_team_profile, detectar_tendencia, STAT_COLS, DEFAULT_LAMBDA

PESO_H2H = 0.0  # Descriptive only until a temporal comparison supports an adjustment.


def build_full_profiles(match_stats: pd.DataFrame, team: str, lam: float = DEFAULT_LAMBDA) -> dict:
    """Arma el perfil COMPLETO de un equipo: general, como local, como
    visitante -- cada uno con sus 4 ventanas + decay-weighted."""
    df = match_stats.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    tiene_local_visita = "is_home" in df.columns

    general = df[df["team"] == team]
    perfil = {"general": build_team_profile(general, team, lam=lam)}

    if tiene_local_visita:
        local = df[(df["team"] == team) & (df["is_home"] == True)]
        visita = df[(df["team"] == team) & (df["is_home"] == False)]
        perfil["local"] = build_team_profile(local, team, lam=lam) if not local.empty else None
        perfil["visitante"] = build_team_profile(visita, team, lam=lam) if not visita.empty else None
    else:
        perfil["local"] = perfil["visitante"] = None

    return perfil


def head_to_head_ponderado(match_stats: pd.DataFrame, team_a: str, team_b: str, n: int = 5, lam: float = DEFAULT_LAMBDA) -> dict:
    """Enfrentamientos directos, con los mas recientes pesando mas. Se usa
    como AJUSTE chico, no como el factor principal (punto 8 del prompt)."""
    df = match_stats.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    sub = df[(df["team"] == team_a) & (df["opponent"] == team_b)].drop_duplicates('match_id').sort_values(["date","match_id"]).tail(n)
    if sub.empty:
        return {"partidos": 0, "detalle": [], "goles_favor_ponderado": None, "goles_contra_ponderado": None}

    n_real = len(sub)
    antiguedad = (sub.date.max()-sub.date).dt.days.to_numpy()/365.25
    pesos = np.exp(-np.log(2) * antiguedad)
    pesos = pesos / pesos.sum()

    detalle = []
    for _, row in sub.iterrows():
        detalle.append({
            "fecha": str(row["date"].date()) if pd.notna(row["date"]) else "?",
            "marcador": f"{int(row['goals_for'])}-{int(row['goals_against'])}",
            "corners": f"{int(row['corners_for'])}-{int(row['corners_against'])}" if pd.notna(row["corners_for"]) else "?",
            "tarjetas": f"{int(row['cards_for'])}-{int(row['cards_against'])}" if pd.notna(row["cards_for"]) else "?",
        })

    return {
        "partidos": n_real,
        "detalle": detalle,
        "goles_favor_ponderado": round(float(np.sum(sub["goals_for"].to_numpy() * pesos)), 2),
        "goles_contra_ponderado": round(float(np.sum(sub["goals_against"].to_numpy() * pesos)), 2),
    }


def cruzar_ataque_defensa(perfil_home: dict, perfil_away: dict, h2h: dict) -> dict:
    """El corazon de la seccion 6 del prompt: ataque del local (de local)
    contra defensa del visitante (de visita), y viceversa. Usa el numero
    decay-weighted de cada perfil (no el promedio plano)."""
    ctx_home = perfil_home["local"] or perfil_home["general"]
    ctx_away = perfil_away["visitante"] or perfil_away["general"]
    dh = ctx_home["decay_weighted"]
    da = ctx_away["decay_weighted"]

    cruces = {}
    for stat in STAT_COLS:
        base = stat.replace("_for", "").replace("_against", "")
        if not stat.endswith("_for"):
            continue
        contra_col = stat.replace("_for", "_against")
        # Cruce: lo que el local genera "for" combinado con lo que el visitante
        # permite "against" cuando juega de visita (y viceversa para el otro lado)
        vals=[dh[stat],da[contra_col],da[stat],dh[contra_col]]
        if any(v is None or not np.isfinite(v) for v in vals):
            cruces[base]={'home':None,'away':None,'status':'missing_observations'}
            continue
        est_home = (dh[stat] + da[contra_col]) / 2
        est_away = (da[stat] + dh[contra_col]) / 2
        cruces[base] = {"home": round(est_home, 2), "away": round(est_away, 2)}

    # Ajuste chico por H2H (si hay historial suficiente)
    if h2h["partidos"] >= 2 and h2h["goles_favor_ponderado"] is not None:
        cruces["goals"]["home"] = round(
            cruces["goals"]["home"] * (1 - PESO_H2H) + h2h["goles_favor_ponderado"] * PESO_H2H, 2)
        cruces["goals"]["away"] = round(
            cruces["goals"]["away"] * (1 - PESO_H2H) + h2h["goles_contra_ponderado"] * PESO_H2H, 2)

    return cruces


def clasificar_confianza(p_home: float, p_draw: float, p_away: float,
                          partidos_home: int, partidos_away: int) -> dict:
    """Categoria de confianza / 'sin ventaja clara' (puntos 14 y 15 del
    prompt). Heuristica de arranque, no calibrada todavia:
      - Si la probabilidad mas alta no supera claramente a las otras 2, o
      - si alguno de los 2 equipos tiene muestra muy chica,
      entonces la señal es debil o directamente 'sin ventaja'."""
    probs = sorted([p_home, p_draw, p_away], reverse=True)
    gap_top2 = probs[0] - probs[1]
    muestra_min = min(partidos_home, partidos_away)

    if muestra_min < 3:
        return {"nivel": "Sin ventaja / muestra insuficiente",
                "motivo": f"Uno de los 2 equipos tiene solo {muestra_min} partidos en el contexto usado."}

    if probs[0] < 38:
        nivel = "Sin ventaja clara"
    elif gap_top2 < 6:
        nivel = "Débil"
    elif gap_top2 < 12:
        nivel = "Moderada"
    elif gap_top2 < 20:
        nivel = "Fuerte"
    else:
        nivel = "Muy fuerte"

    return {"nivel": nivel, "gap_top2": round(gap_top2, 1), "prob_mayor": round(probs[0], 1)}
