"""
Une los 3 tipos de CSV que exporta footiqo.com (Scores, Corners & Cards,
Attack & Poss) por "id" de partido, y los deja en el mismo formato que usa
el resto del proyecto (results-style para elo.py + long-format
favor/contra para stats_extended.py).

LIMITACION HONESTA: footiqo en su version gratis exporta solo los ULTIMOS
~25 partidos por vista (la recta final del torneo), no la temporada
completa. Sirve como muestra real para probar el modelo, pero con pocos
equipos (los que llegaron lejos) y pocos partidos por equipo -- no
alcanza para un promedio confiable de corners/tarjetas de TODOS los
equipos de Champions. Para eso hace falta la base completa (paga) o ir
acumulando estas exportaciones manuales despues de cada jornada.

Uso:
    python3 process_footiqo_export.py
"""
import glob
import os
import pandas as pd

from paths import PROJECT_ROOT
UPLOADS_DIR = os.environ.get('FOOTIQO_UPLOADS_DIR',str(PROJECT_ROOT/'data'/'uploads'))
from paths import DATA_DIR as OUT_DIR


def _load_unique(pattern):
    """Carga todos los CSV que matchean el patron y descarta duplicados exactos."""
    files = glob.glob(os.path.join(UPLOADS_DIR, pattern))
    frames = [pd.read_csv(f) for f in files]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset="id")
    return combined


def main():
    scores = _load_unique("Database_-_Scores_-_*Champions_League*.csv")
    corners_cards = _load_unique("Database_-_Corners__Cards_-_*Champions_League*.csv")
    attack_poss = _load_unique("Database_-_Attack__Poss_-_*Champions_League*.csv")

    print(f"Scores: {len(scores)} partidos unicos")
    print(f"Corners/Cards: {len(corners_cards)} partidos unicos")
    print(f"Attack/Poss: {len(attack_poss)} partidos unicos")

    # Merge por id (algunos partidos pueden no tener las 3 vistas exportadas)
    merged = scores.merge(
        corners_cards[["id", "HCFT", "ACFT", "HYCFT", "AYCFT"]], on="id", how="left"
    ).merge(
        attack_poss[["id", "HTSFT", "ATSFT", "HSONFT", "ASONFT", "HBPFT", "ABPFT"]], on="id", how="left"
    )
    print(f"\nMerge final: {len(merged)} partidos, {merged['HCFT'].notna().sum()} con corners/tarjetas")

    merged["matchDate"] = pd.to_datetime(merged["matchDate"], format="%d-%m-%y %H:%M")
    merged = merged.sort_values("matchDate")

    os.makedirs(OUT_DIR, exist_ok=True)

    # ---- formato results-style (para elo.py) ----
    elo_df = pd.DataFrame({
        "date": merged["matchDate"].dt.strftime("%Y-%m-%d"),
        "home_team": merged["homeTeam"],
        "away_team": merged["awayTeam"],
        "home_score": merged["FTHG"],
        "away_score": merged["FTAG"],
        "tournament": "UEFA Champions League",
        "city": "", "country": "",
        "neutral": False,  # aproximacion: solo semis/final se juegan en cancha neutral, no viene indicado en esta fuente
    })
    elo_path = os.path.join(OUT_DIR, "results_champions_footiqo.csv")
    elo_df.to_csv(elo_path, index=False)
    print(f"OK -> {elo_path}")

    # ---- formato largo favor/contra (para stats_extended.py) ----
    home_rows = pd.DataFrame({
        "match_id": merged["id"], "date": merged["matchDate"], "league": "UEFA Champions League",
        "team": merged["homeTeam"], "opponent": merged["awayTeam"],
        "goals_for": merged["FTHG"], "goals_against": merged["FTAG"],
        "shots_for": merged["HTSFT"], "shots_against": merged["ATSFT"],
        "sot_for": merged["HSONFT"], "sot_against": merged["ASONFT"],
        "corners_for": merged["HCFT"], "corners_against": merged["ACFT"],
        "cards_for": merged["HYCFT"], "cards_against": merged["AYCFT"],
        "possession_for": merged["HBPFT"], "possession_against": merged["ABPFT"],
    })
    away_rows = pd.DataFrame({
        "match_id": merged["id"], "date": merged["matchDate"], "league": "UEFA Champions League",
        "team": merged["awayTeam"], "opponent": merged["homeTeam"],
        "goals_for": merged["FTAG"], "goals_against": merged["FTHG"],
        "shots_for": merged["ATSFT"], "shots_against": merged["HTSFT"],
        "sot_for": merged["ASONFT"], "sot_against": merged["HSONFT"],
        "corners_for": merged["ACFT"], "corners_against": merged["HCFT"],
        "cards_for": merged["AYCFT"], "cards_against": merged["HYCFT"],
        "possession_for": merged["ABPFT"], "possession_against": merged["HBPFT"],
    })
    stats_df = pd.concat([home_rows, away_rows], ignore_index=True)
    stats_path = os.path.join(OUT_DIR, "match_stats_champions_footiqo.csv")
    stats_df.to_csv(stats_path, index=False)
    print(f"OK -> {stats_path}")

    print("\nPartidos por equipo (para que veas la cobertura real):")
    print(stats_df.groupby("team")["match_id"].nunique().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
