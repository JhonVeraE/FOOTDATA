"""
Perfil estadistico avanzado por equipo -- Fase A del modelo multicapa.

Dos cosas conviven a proposito, con roles distintos:

1) VENTANAS DISCRETAS (temporada / ultimos 10 / ultimos 5 / ultimos 3):
   sirven para EXPLICAR y DETECTAR TENDENCIAS ("¿el equipo esta mejorando
   o empeorando?"). Son para el informe, no para alimentar el modelo
   directamente -- comparar 4 promedios simples es facil de leer pero
   discontinuo (un partido que "entra o sale" de la ventana de golpe
   cambia el numero).

2) DECAIMIENTO EXPONENCIAL (peso = exp(-lambda * antiguedad_en_partidos)):
   es el numero que REALMENTE alimenta el modelo de cruces (seccion 6 del
   prompt). Cada partido pesa un poco menos que el anterior, sin saltos
   discontinuos. lambda por defecto equivale a una "vida media" de 10
   partidos (el valor efectivo se declara en DEFAULT_HALF_LIFE_PARTIDOS).

   IMPORTANTE (transparencia total): este lambda por defecto es una
   heuristica razonable, NO esta calibrado contra resultados reales
   todavia. La calibracion real (probar distintos lambda y quedarse con
   el que mejor predice en backtesting historico) es la Fase C, que
   requiere correr un backtest de verdad sobre tus datos -- no lo invento
   aca.
"""
import numpy as np
import pandas as pd

STAT_COLS = ["goals_for", "goals_against", "shots_for", "shots_against",
             "sot_for", "sot_against", "corners_for", "corners_against",
             "cards_for", "cards_against", "fouls_for", "fouls_against"]

DEFAULT_HALF_LIFE_PARTIDOS = 5.0
DEFAULT_LAMBDA = np.log(2) / DEFAULT_HALF_LIFE_PARTIDOS

VENTANAS = [("temporada", None), ("ultimos_10", 10), ("ultimos_5", 5), ("ultimos_3", 3)]


def _resultado(row):
    if row["goals_for"] > row["goals_against"]:
        return "V"
    if row["goals_for"] < row["goals_against"]:
        return "D"
    return "E"


def _ventana_stats(sub: pd.DataFrame) -> dict:
    """Stats simples (sin ponderar) de una ventana de partidos -- para
    mostrar/comparar en el informe, no para el modelo."""
    if sub.empty:
        return None
    resultados = sub.apply(_resultado, axis=1)
    n = len(sub)
    victorias = (resultados == "V").sum()
    empates = (resultados == "E").sum()
    derrotas = (resultados == "D").sum()

    out = {
        "partidos": n,
        "victorias": int(victorias), "empates": int(empates), "derrotas": int(derrotas),
        "puntos_por_partido": round((victorias * 3 + empates) / n, 2),
    }
    for c in STAT_COLS:
        out[c] = round(sub[c].mean(), 2)

    # Variables derivadas (seccion 11 del prompt)
    out["conversion"] = round(out["goals_for"] / out["shots_for"], 3) if out["shots_for"] else None
    out["precision"] = round(out["sot_for"] / out["shots_for"], 3) if out["shots_for"] else None
    out["presion_ofensiva"] = round(out["shots_for"] + out["sot_for"] + out["corners_for"], 2)
    out["diferencia_tiros"] = round(out["shots_for"] - out["shots_against"], 2)
    out["diferencia_corners"] = round(out["corners_for"] - out["corners_against"], 2)
    out["diferencia_tiros_arco"] = round(out["sot_for"] - out["sot_against"], 2)
    out["diferencia_goles"] = round(out["goals_for"] - out["goals_against"], 2)
    return out


def _decay_weighted(sub: pd.DataFrame, lam: float = DEFAULT_LAMBDA) -> dict:
    """Promedio ponderado por decaimiento exponencial: el partido mas
    reciente (ultima fila, dado que sub viene ordenado por fecha ascendente)
    pesa exp(0)=1, el anterior exp(-lambda), el anterior a ese exp(-2*lambda),
    etc. Se usa como EL numero que alimenta el modelo (cruces, Poisson)."""
    if sub.empty:
        return None
    n = len(sub)
    antiguedad = np.arange(n - 1, -1, -1)  # el ultimo partido (mas reciente) tiene antiguedad 0
    pesos = np.exp(-lam * antiguedad)
    pesos = pesos / pesos.sum()

    out = {"partidos": n, "peso_efectivo": round(float(1 / np.sum(pesos ** 2)), 1)}
    # "peso_efectivo" = tamaño de muestra efectivo (cuantos partidos "cuentan"
    # de verdad dado el decaimiento) -- util para saber si hay poca informacion
    # aunque el equipo tenga muchos partidos jugados en total.
    out['coverage'] = {}
    for c in STAT_COLS:
        values=pd.to_numeric(sub[c],errors='coerce').to_numpy(float)
        valid=np.isfinite(values)
        out['coverage'][c]=int(valid.sum())
        out[c]=round(float(np.average(values[valid],weights=pesos[valid])),3) if valid.any() else None
    return out


def build_team_profile(team_matches: pd.DataFrame, team_name: str, lam: float = DEFAULT_LAMBDA) -> dict:
    """team_matches: TODAS las filas de un equipo en un contexto ya filtrado
    (general, o solo local, o solo visitante), ordenadas por fecha ascendente."""
    sub = team_matches.sort_values("date")

    ventanas = {}
    for label, n in VENTANAS:
        # A season is not the entire five-year history; decay still uses history.
        if n is None:
            if 'season' in sub and not sub.empty:w=sub[sub.season==team_matches.attrs.get('report_season',sub.season.iloc[-1])]
            elif not sub.empty:
                last=pd.Timestamp(sub.date.iloc[-1]);start=pd.Timestamp(last.year if last.month>=7 else last.year-1,7,1)
                w=sub[pd.to_datetime(sub.date)>=start]
            else:w=sub
        else:w=sub.tail(n)
        stats = _ventana_stats(w)
        if stats:
            ventanas[label] = stats

    decay = _decay_weighted(sub, lam=lam)

    return {"team": team_name, "ventanas": ventanas, "decay_weighted": decay}


def detectar_tendencia(ventanas: dict, stat: str, umbral_pct: float = 15.0) -> dict:
    """Compara temporada -> ultimos_10 -> ultimos_5 -> ultimos_3 para una
    estadistica puntual, y devuelve si hay una tendencia consistente
    (mejorando/empeorando) o si esta estable. Requiere al menos 2 ventanas
    con datos para poder comparar."""
    serie = [(label, ventanas[label][stat]) for label, _ in VENTANAS if label in ventanas and ventanas[label].get(stat) is not None]
    if len(serie) < 2:
        return {"estado": "sin_datos_suficientes", "serie": serie}

    valores = [v for _, v in serie]
    base = valores[0]
    if base == 0:
        return {"estado": "estable", "serie": serie}

    cambios_pct = [(v - base) / abs(base) * 100 for v in valores[1:]]
    subiendo = all(c > 0 for c in cambios_pct) and max(abs(c) for c in cambios_pct) >= umbral_pct
    bajando = all(c < 0 for c in cambios_pct) and max(abs(c) for c in cambios_pct) >= umbral_pct

    if subiendo:
        estado = "subiendo"
    elif bajando:
        estado = "bajando"
    else:
        estado = "estable"
    return {"estado": estado, "serie": serie, "cambio_pct_ultimo": round(cambios_pct[-1], 1) if cambios_pct else 0}
