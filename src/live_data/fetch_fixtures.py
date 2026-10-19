"""
Trae TODOS los fixtures (jugados + programados) de cada liga en config.py
para la temporada configurada, y los guarda en un CSV normalizado
(data/live/matches_live.csv) con un esquema parecido al que ya usa
predictor_core.py para el Mundial, para poder reusar el mismo modelo mas
adelante.

Costo: 1 request por liga (3 requests totales con la config actual). Se
puede correr todos los dias sin problema -- el cache interno de api_client
evita gastar cupo si ya lo pediste hoy.

Uso:
    python3 fetch_fixtures.py
"""
import os
import pandas as pd

from config import LEAGUES, SEASON, DATA_DIR
from api_client import get


def fetch_league_fixtures(league_name: str, league_id: int) -> list[dict]:
    print(f"Fixtures de {league_name} (id={league_id}, temporada={SEASON})...")
    fixtures = get("fixtures", {"league": league_id, "season": SEASON})
    rows = []
    for f in fixtures:
        fx = f["fixture"]
        lg = f["league"]
        teams = f["teams"]
        goals = f["goals"]
        rows.append({
            "fixture_id": fx["id"],
            "date": fx["date"][:10],
            "kickoff_time_utc": fx["date"][11:16],
            "status": fx["status"]["short"],  # NS=no empezo, FT=finalizado, etc.
            "league": league_name,
            "round": lg.get("round"),
            "venue": (fx.get("venue") or {}).get("name"),
            "referee": fx.get("referee"),
            "home_team": teams["home"]["name"],
            "home_team_id": teams["home"]["id"],
            "away_team": teams["away"]["name"],
            "away_team_id": teams["away"]["id"],
            "home_score": goals["home"],
            "away_score": goals["away"],
        })
    return rows


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    todas = []
    for nombre, lid in LEAGUES.items():
        todas.extend(fetch_league_fixtures(nombre, lid))

    df = pd.DataFrame(todas)
    out_path = os.path.join(DATA_DIR, "matches_live.csv")
    df.to_csv(out_path, index=False)
    print(f"\nOK -> {out_path} ({len(df)} fixtures)")
    print(df["status"].value_counts())
    return df


if __name__ == "__main__":
    main()
