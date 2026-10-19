from paths import DATA_DIR
"""
Diagnostico rapido -- NO descarga nada, solo lee matches_footballdata.csv
que ya tenes en data/live/ y te muestra, por liga, que jornadas y estados
(SCHEDULED/FINISHED) hay realmente. Sirve para entender por que la
Bundesliga aparecio en Jornada 5 con jornadas 1-4 "ya jugadas" cuando
todas las ligas deberian estar por arrancar.

Uso:
    python3 diagnostico_calendario.py
"""
import pandas as pd

df = pd.read_csv(str(DATA_DIR / "matches_footballdata.csv"))

for liga in sorted(df["competition"].unique()):
    sub = df[df["competition"] == liga]
    print(f"\n=== {liga} ===")
    print("Estados:", dict(sub["status"].value_counts()))
    finished = sub[sub["status"] == "FINISHED"]
    scheduled = sub[sub["status"] == "SCHEDULED"]
    if not finished.empty:
        print(f"Jornadas FINISHED: {sorted(finished['matchday'].dropna().unique())}")
        print(f"Fechas FINISHED: {finished['date'].min()} a {finished['date'].max()}")
        print("Ejemplo de partido FINISHED:")
        print(" ", finished[["date", "matchday", "home_team", "away_team", "home_score", "away_score"]].iloc[0].to_dict())
    if not scheduled.empty:
        print(f"Jornadas SCHEDULED: {sorted(scheduled['matchday'].dropna().unique())[:10]}")
        print(f"Fechas SCHEDULED: {scheduled['date'].min()} a {scheduled['date'].max()}")
