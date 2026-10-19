from paths import DATA_DIR
"""
Descarga La Liga, Premier League, Serie A y Bundesliga desde datahub.io,
que espeja football-data.co.uk: CSV publico, SIN api key, SIN limite de
requests, actualizado a diario, con estadisticas completas por partido
(remates, corners, tarjetas, faltas) desde temporada 2000/01 en adelante.

Esto es MEJOR que el pipeline de API-Football para estas 4 ligas
especificamente: no hay que administrar cupo, no hace falta registrarse
en ningun lado, y el historial es mucho mas largo (25 años vs. lo que
tengas cargado a mano).

Uso:
    python3 fetch_datahub_leagues.py                # ultimas 5 temporadas + actual
    python3 fetch_datahub_leagues.py --seasons 10    # ultimas 10 temporadas + actual
"""
import argparse
import os
import pandas as pd
import requests

BASE = "https://datahub.io/football"

LEAGUES = {
    "La Liga": "spanish-la-liga",
    "Premier League": "english-premier-league",
    "Serie A": "italian-serie-a",
    "Bundesliga": "german-bundesliga",
    "Ligue 1": "french-ligue-1",
}

# Temporadas disponibles como codigo de 4 digitos (season-2526.csv = 2025/26).
# Se arma la lista de las ultimas N automaticamente a partir de la actual.
from paths import DATA_DIR
from settings import current_season_code
CURRENT_SEASON_CODE = current_season_code()


def season_codes(n_seasons: int, current=CURRENT_SEASON_CODE):
    """Genera codigos tipo '2425','2324',... para las ultimas n temporadas
    (incluye la actual)."""
    start_year = int(current[:2])
    codes = []
    for i in range(n_seasons):
        y0 = start_year - i
        y1 = y0 + 1
        codes.append(f"{y0:02d}{y1:02d}")
    return codes


def fetch_league(league_name: str, slug: str, n_seasons: int) -> pd.DataFrame:
    frames = []
    for code in season_codes(n_seasons):
        url = f"{BASE}/{slug}/_r/-/season-{code}.csv"
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200 or not resp.text.strip():
                print(f"  [!] {league_name} {code}: no disponible (HTTP {resp.status_code})")
                continue
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text))
            if df.empty:
                continue
            df["league"] = league_name
            df["season"] = f"20{code[:2]}/{code[2:]}"
            frames.append(df)
            print(f"  [ok] {league_name} {code}: {len(df)} partidos")
        except Exception as e:
            print(f"  [!] {league_name} {code}: error -> {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def normalize_for_elo(raw: pd.DataFrame) -> pd.DataFrame:
    """Convierte al formato que usa elo.py / goals_model_v2.py
    (mismo esquema que results.csv: date, home_team, away_team,
    home_score, away_score, tournament, neutral)."""
    df = raw.dropna(subset=["FTHG", "FTAG"]).copy()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"], dayfirst=True, errors="raise").dt.strftime("%Y-%m-%d"),
        "home_team": df["HomeTeam"],
        "away_team": df["AwayTeam"],
        "home_score": df["FTHG"].astype(int),
        "away_score": df["FTAG"].astype(int),
        "tournament": df["league"],
        "city": "",
        "country": "",
        "neutral": False,  # partidos de liga domestica, nunca neutrales
    })
    return out


def normalize_for_stats(raw: pd.DataFrame) -> pd.DataFrame:
    """Formato 'largo' (una fila por equipo por partido, con su propio stat
    Y el del rival), directamente compatible con la logica de
    stats_extended.team_for_against() del Mundial -- mismo patron favor/contra."""
    df = raw.dropna(subset=["FTHG", "FTAG"]).copy()
    df["match_id"] = df["league"] + "_" + df["season"].astype(str) + "_" + df.index.astype(str)
    # football-data.co.uk usa fechas DD/MM/YY -- se normaliza a ISO (YYYY-MM-DD)
    # para poder ordenar cronologicamente sin ambiguedad mas adelante (forma reciente).
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")

    home_rows = pd.DataFrame({
        "match_id": df["match_id"], "date": df["Date"], "league": df["league"], "is_home": True,
        "team": df["HomeTeam"], "opponent": df["AwayTeam"],
        "goals_for": df["FTHG"], "goals_against": df["FTAG"],
        "shots_for": df["HS"], "shots_against": df["AS"],
        "sot_for": df["HST"], "sot_against": df["AST"],
        "fouls_for": df["HF"], "fouls_against": df["AF"],
        "corners_for": df["HC"], "corners_against": df["AC"],
        "cards_for": df["HY"].fillna(0) + df["HR"].fillna(0),
        "cards_against": df["AY"].fillna(0) + df["AR"].fillna(0),
    })
    away_rows = pd.DataFrame({
        "match_id": df["match_id"], "date": df["Date"], "league": df["league"], "is_home": False,
        "team": df["AwayTeam"], "opponent": df["HomeTeam"],
        "goals_for": df["FTAG"], "goals_against": df["FTHG"],
        "shots_for": df["AS"], "shots_against": df["HS"],
        "sot_for": df["AST"], "sot_against": df["HST"],
        "fouls_for": df["AF"], "fouls_against": df["HF"],
        "corners_for": df["AC"], "corners_against": df["HC"],
        "cards_for": df["AY"].fillna(0) + df["AR"].fillna(0),
        "cards_against": df["HY"].fillna(0) + df["HR"].fillna(0),
    })
    return pd.concat([home_rows, away_rows], ignore_index=True)


def main(n_seasons: int):
    all_raw = []
    for name, slug in LEAGUES.items():
        print(f"\nDescargando {name}...")
        raw = fetch_league(name, slug, n_seasons)
        if not raw.empty:
            all_raw.append(raw)

    if not all_raw:
        print("No se pudo descargar nada -- revisa tu conexion.")
        return

    combined = pd.concat(all_raw, ignore_index=True)
    print(f"\nTotal descargado: {len(combined)} partidos de {len(LEAGUES)} ligas")

    os.makedirs(DATA_DIR, exist_ok=True)

    elo_df = normalize_for_elo(combined)
    elo_path = str(DATA_DIR / "results_4ligas.csv")
    elo_df.to_csv(elo_path, index=False)
    print(f"OK -> {elo_path} ({len(elo_df)} filas, listo para elo.py)")

    stats_df = normalize_for_stats(combined)
    stats_path = str(DATA_DIR / "match_stats_4ligas.csv")
    stats_df.to_csv(stats_path, index=False)
    print(f"OK -> {stats_path} ({len(stats_df)} filas, formato favor/contra)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=5, help="Cuantas temporadas hacia atras traer (incluye la actual)")
    args = ap.parse_args()
    main(args.seasons)
