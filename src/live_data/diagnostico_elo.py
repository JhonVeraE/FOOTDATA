"""
Diagnostico -- NO descarga nada. Usa los mismos CSV que ya tenes en
data/live/ y te muestra el Elo FINAL calculado para un puñado de equipos
bien conocidos, para poder confirmar a ojo si el modelo distingue bien
entre equipos fuertes y flojos (ej: Manchester City deberia tener MUCHO
mas Elo que Bournemouth).

Uso:
    python3 diagnostico_elo.py
"""
import pandas as pd
from league_core import build_elo_ratings

from paths import DATA_DIR

frames = []
for fname in ["results_4ligas.csv", "results_uefa_history.csv", "results_footballdata.csv"]:
    import os
    p = os.path.join(DATA_DIR, fname)
    if os.path.exists(p):
        df = pd.read_csv(p)
        frames.append(df.drop(columns=["season"], errors="ignore"))
results = pd.concat(frames, ignore_index=True)

print(f"Total de partidos cargados: {len(results)}")
print(f"Con marcador (jugados): {results.dropna(subset=['home_score','away_score']).shape[0]}")
print()

elo = build_elo_ratings(results)

EQUIPOS_CHEQUEO = [
    "Man City", "Bournemouth", "Arsenal", "Coventry",
    "Real Madrid", "Barcelona", "Alaves", "Getafe",
    "Bayern Munich", "Augsburg", "Inter", "Monza",
    "Paris SG", "Le Havre",
]

print("Elo final de equipos de referencia:")
for eq in EQUIPOS_CHEQUEO:
    if eq in elo:
        print(f"  {eq:20s} {elo[eq]:.0f}")
    else:
        print(f"  {eq:20s} NO ENCONTRADO -- revisar nombre exacto")

print()
print("Cuantos partidos jugo cada uno (para ver si el Elo se calculo con poca o mucha info):")
for eq in EQUIPOS_CHEQUEO:
    n = ((results["home_team"] == eq) | (results["away_team"] == eq)).sum()
    print(f"  {eq:20s} {n} partidos en el historial cargado")

print()
print("Duplicados posibles (mismo partido en 2 fuentes distintas, ej. datahub Y football-data.org):")
chk = results.dropna(subset=["home_score", "away_score"])
dups = chk[chk.duplicated(subset=["home_team", "away_team", "home_score", "away_score"], keep=False)]
print(f"  {len(dups)} filas duplicadas de {len(chk)} totales ({len(dups)/len(chk)*100:.1f}%)")
