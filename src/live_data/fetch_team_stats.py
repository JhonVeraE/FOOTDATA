"""
Trae estadisticas por partido (corners, tarjetas, remates, posesion) SOLO
para los fixtures que ya terminaron (status FT) y que todavia no estan en
data/live/match_team_stats_live.csv -- asi cada corrida gasta cupo nada
mas que en los partidos nuevos, nunca repite uno ya guardado.

Costo: 1 request POR PARTIDO nuevo. Con 100 req/dia de cupo, si en un dia
se jugaron 15 partidos entre las 3 ligas, usa 15 requests y sobra cupo de
sobra para fixtures.py + find_league_ids.py.

Si es la primera vez que corres esto (backfill inicial), limitá cuantos
partidos vieja trae con --max para no fundir el cupo en una sola corrida:

Uso:
    python3 fetch_team_stats.py            # trae todos los nuevos (cuidado la primera vez)
    python3 fetch_team_stats.py --max 30   # trae como maximo 30 partidos nuevos esta corrida
"""
import argparse
import os
import pandas as pd

from config import DATA_DIR
from api_client import get


def fetch_stats_for_fixture(fixture_id: int) -> list[dict]:
    data = get("fixtures/statistics", {"fixture": fixture_id})
    rows = []
    for team_block in data:
        tid = team_block["team"]["id"]
        tname = team_block["team"]["name"]
        stats = {s["type"]: s["value"] for s in team_block["statistics"]}
        rows.append({
            "fixture_id": fixture_id,
            "team_id": tid,
            "team_name": tname,
            "possession_pct": stats.get("Ball Possession"),
            "total_shots": stats.get("Total Shots"),
            "shots_on_target": stats.get("Shots on Goal"),
            "corners": stats.get("Corner Kicks"),
            "fouls": stats.get("Fouls"),
            "yellow_cards": stats.get("Yellow Cards"),
            "red_cards": stats.get("Red Cards"),
            "offsides": stats.get("Offsides"),
        })
    return rows


def main(max_nuevos=None):
    matches_path = os.path.join(DATA_DIR, "matches_live.csv")
    if not os.path.exists(matches_path):
        raise SystemExit("Primero corré fetch_fixtures.py")
    matches = pd.read_csv(matches_path)
    finalizados = matches[matches["status"] == "FT"]["fixture_id"].tolist()

    stats_path = os.path.join(DATA_DIR, "match_team_stats_live.csv")
    if os.path.exists(stats_path):
        existentes = pd.read_csv(stats_path)
        required=['total_shots','shots_on_target','corners','fouls','yellow_cards','red_cards']
        valid=existentes.dropna(subset=required)
        ya_tengo=set(valid.groupby('fixture_id').filter(lambda g:len(g)==2 and g.team_id.nunique()==2).fixture_id)
    else:
        existentes = pd.DataFrame()
        ya_tengo = set()

    faltantes = [fid for fid in finalizados if fid not in ya_tengo]
    print(f"Partidos finalizados: {len(finalizados)} | ya en cache: {len(ya_tengo)} | nuevos a traer: {len(faltantes)}")

    if max_nuevos:
        faltantes = faltantes[:max_nuevos]
        print(f"(limitado a {max_nuevos} por --max)")

    for fid in faltantes:
        print(f"Estadisticas del fixture {fid}...")
        rows=fetch_stats_for_fixture(fid)
        if len(rows)!=2 or len({r['team_id'] for r in rows})!=2:
            print(f'  Incomplete fixture {fid}; will retry next run');continue
        # Commit each successful fixture; later quota/network errors cannot lose it.
        previous=existentes[existentes.fixture_id!=fid] if not existentes.empty else existentes
        existentes=pd.concat([previous,pd.DataFrame(rows)],ignore_index=True)
        pending=stats_path+'.tmp';existentes.to_csv(pending,index=False);os.replace(pending,stats_path)
    print(f"\nOK -> {stats_path} ({len(existentes)} filas equipo-partido en total)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="Maximo de partidos NUEVOS a traer en esta corrida")
    args = ap.parse_args()
    main(max_nuevos=args.max)
