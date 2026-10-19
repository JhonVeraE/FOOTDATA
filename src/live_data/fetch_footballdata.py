"""
Trae fixtures/resultados REALES y en tiempo real de Champions League y
Brasil Serie A desde football-data.org (12 competiciones gratis, 10
requests/minuto, sin limite diario).

IMPORTANTE - que SI trae y que NO trae el plan gratis:
  SI: resultados, fixtures programados, tabla de posiciones, goleadores
  NO: corners, tarjetas, remates por partido (eso es un add-on pago,
      €15/mes, aca no lo usamos)

O sea que con esto el modelo puede calcular 1X2 / marcador probable /
goleador probable para Champions y Brasil (con el mismo motor Elo+Poisson
que ya usa el Mundial), pero TODAVIA no puede calcular corners/tarjetas
para estas 2 competiciones -- eso queda pendiente hasta que se resuelva
con otra fuente (paga, o revisando footiqo.com a mano para los partidos
mas importantes).

## Como conseguir tu API key (gratis, separada de la de API-Football)
1. https://www.football-data.org/client/register
2. Te llega un token por email
3. Configuralo iguel que la otra key:
   setx FOOTBALL_DATA_KEY "tu-token-aca"   (y abri una ventana nueva)
   o directamente en este archivo, en FOOTBALL_DATA_KEY mas abajo.

Uso:
    python3 fetch_footballdata.py
"""
import os
import time
import requests
import pandas as pd

from settings import secret
FOOTBALL_DATA_KEY = secret("FOOTBALL_DATA_KEY")
BASE_URL = "https://api.football-data.org/v4"

COMPETITIONS = {
    "UEFA Champions League": "CL",
    "Brasileirao Serie A": "BSA",
    "La Liga": "PD",
    "Premier League": "PL",
    "Bundesliga": "BL1",
    "Serie A": "SA",
    "Ligue 1": "FL1",
}

from paths import DATA_DIR


def _headers():
    if FOOTBALL_DATA_KEY in ("PEGA_TU_TOKEN_ACA", "", None):
        raise RuntimeError(
            "Falta tu token de football-data.org. Registrate gratis en "
            "https://www.football-data.org/client/register y configuralo "
            "en FOOTBALL_DATA_KEY (variable de entorno o directo en este archivo)."
        )
    return {"X-Auth-Token": FOOTBALL_DATA_KEY}


def fetch_matches(comp_name: str, comp_code: str) -> pd.DataFrame:
    print(f"Fixtures de {comp_name} ({comp_code})...")
    url = f"{BASE_URL}/competitions/{comp_code}/matches"
    resp = requests.get(url, headers=_headers(), timeout=20)
    if resp.status_code != 200:
        print(f"  [!] HTTP {resp.status_code}: {resp.text[:200]}")
        return pd.DataFrame()
    data = resp.json()
    rows = []
    for m in data.get("matches", []):
        rows.append({
            "match_id": m["id"],
            "date": m["utcDate"][:10],
            "kickoff_time_utc": m["utcDate"][11:16],
            "status": m["status"],  # SCHEDULED, FINISHED, IN_PLAY, POSTPONED, etc.
            "competition": comp_name,
            "stage": m.get("stage"),
            "matchday": m.get("matchday"),  # numero de jornada -- clave para agrupar por fecha real
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
            "home_score": (m.get("score", {}).get("fullTime", {}) or {}).get("home"),
            "away_score": (m.get("score", {}).get("fullTime", {}) or {}).get("away"),
            "referee": None,  # no viene en el plan free de forma consistente
        })
    print(f"  [ok] {len(rows)} partidos")
    return pd.DataFrame(rows)


def fetch_scorers(comp_name: str, comp_code: str) -> pd.DataFrame:
    print(f"Goleadores de {comp_name} ({comp_code})...")
    url = f"{BASE_URL}/competitions/{comp_code}/scorers"
    resp = requests.get(url, headers=_headers(), timeout=20)
    if resp.status_code != 200:
        print(f"  [!] HTTP {resp.status_code}: {resp.text[:200]}")
        return pd.DataFrame()
    data = resp.json()
    rows = []
    for s in data.get("scorers", []):
        rows.append({
            "competition": comp_name,
            "player_name": s["player"]["name"],
            "team": s["team"]["name"],
            "goals": s.get("goals"),
            "assists": s.get("assists"),
            "matches_played": s.get("playedMatches"),
        })
    print(f"  [ok] {len(rows)} goleadores")
    return pd.DataFrame(rows)


def normalize_for_elo(matches: pd.DataFrame) -> pd.DataFrame:
    df = matches.dropna(subset=["home_score", "away_score"]).copy()
    return pd.DataFrame({
        "date": df["date"],
        "home_team": df["home_team"],
        "away_team": df["away_team"],
        "home_score": df["home_score"].astype(int),
        "away_score": df["away_score"].astype(int),
        "tournament": df["competition"],
        "city": "",
        "country": "",
        "neutral": df.get("stage", pd.Series("", index=df.index)).eq("FINAL"),  # CL suele jugarse en cancha del local igual, pero eliminatorias finales son neutrales; ajustable
    })


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_matches, all_scorers = [], []

    for i, (name, code) in enumerate(COMPETITIONS.items()):
        if i > 0:
            time.sleep(6)  # 10 req/min de margen -- no hace falta mas que esto
        m = fetch_matches(name, code)
        if not m.empty:
            all_matches.append(m)
        time.sleep(6)
        s = fetch_scorers(name, code)
        if not s.empty:
            all_scorers.append(s)

    if all_matches:
        matches_df = pd.concat(all_matches, ignore_index=True)
        matches_path = os.path.join(DATA_DIR, "matches_footballdata.csv")
        matches_df.to_csv(matches_path, index=False)
        print(f"\nOK -> {matches_path} ({len(matches_df)} partidos)")

        elo_df = normalize_for_elo(matches_df)
        elo_path = os.path.join(DATA_DIR, "results_footballdata.csv")
        elo_df.to_csv(elo_path, index=False)
        print(f"OK -> {elo_path} ({len(elo_df)} filas, listo para elo.py)")

    if all_scorers:
        scorers_df = pd.concat(all_scorers, ignore_index=True)
        scorers_path = os.path.join(DATA_DIR, "scorers_footballdata.csv")
        scorers_df.to_csv(scorers_path, index=False)
        print(f"OK -> {scorers_path} ({len(scorers_df)} goleadores)")

    print("\nNOTA: esto NO trae corners/tarjetas (no esta en el plan gratis).")
    print("Para 1X2/marcador/goleador de Champions y Brasil ya alcanza. Para")
    print("corners/tarjetas de estas 2 competiciones sigue pendiente.")


if __name__ == "__main__":
    main()
