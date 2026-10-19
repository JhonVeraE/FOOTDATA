"""
Parsea los resultados de Champions League, Europa League y Conference
League desde el texto plano de kassiesa.net (extraido de los PDF que
subiste con pdftotext -layout).

Es SOLO resultados (fecha no viene por partido, si por temporada) -- no
trae corners/tarjetas/remates, asi que sirve para entrenar el modelo de
Elo/goles esperados de estas 3 competiciones, pero no para la parte de
corners/tarjetas (eso sigue pendiente, ver footiqo).

Uso:
    python3 parse_uefa_history.py /tmp/uefa2425.txt 2025
    python3 parse_uefa_history.py /tmp/uefa2526.txt 2026
"""
import re
import sys
import pandas as pd

COMPETITIONS = {"CHAMPIONS LEAGUE", "EUROPA LEAGUE", "CONFERENCE LEAGUE"}
ROUND_MARKERS = [
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round",
    "Qualifying Play-off Round", "League Stage", "Knockout round play-offs",
    "Round of 16", "Quarter Finals", "Semi Finals", "Final",
]

LINE_RE = re.compile(
    r'^\s*(.+?)\s{2,}([A-Z][a-z]{2})\s+(.+?)\s{2,}([A-Z][a-z]{2})\s+(\d+-\d+)(?:\s+(\d+-\d+))?\s*$'
)


def _clean_ad_contamination(lines: list[str]) -> list[str]:
    """kassiesa.net inserta un bloque de anuncios en medio de la pagina 2 que
    a veces se pega literalmente arriba de una linea de partido real cuando
    se extrae el texto del PDF (pdftotext). En la temporada 2024/25 esto
    corrompe exactamente 2 lineas ("NK Celje vs Slovan Bratislava" y
    "FK Panevezys vs Jagiellonia Bialystok", ambas de la 2nd Qualifying
    Round de Champions League). En vez de reconstruir con regex (probado:
    es fragil y corta mal nombres de equipo como "FK Panevezys"), se
    reemplazan estas lineas puntuales por su version correcta, verificada
    contra el texto limpio de la pagina (mismo dato, sin el anuncio en
    medio)."""
    text = "".join(lines)
    known_fixes = [
        (
            " 1.NK   motor paso a paso NEMA 17\n"
            "    ParCelje                                            Slo      Slovan Bratislava                     Svk   1-1   0-5 ❯\n"
            " 2.FK Panevezyspara perros de SloughiLit\n"
            "    Alojamiento                                                  Jagiellonia Bialystok                 Pol   0-4   1-3 ❯\n",
            "   NK Celje                                             Slo      Slovan Bratislava                     Svk   1-1   0-5\n"
            "   FK Panevezys                                         Lit      Jagiellonia Bialystok                 Pol   0-4   1-3\n"
        ),
    ]
    fixed_count = 0
    for corrupted, fixed in known_fixes:
        if corrupted in text:
            text = text.replace(corrupted, fixed)
            fixed_count += 1
    if fixed_count:
        print(f"  [fix] {fixed_count} bloque(s) de anuncio insertado detectados y corregidos")
    return text.splitlines(keepends=True)


def parse_file(path: str, season_end_year: int) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    lines = _clean_ad_contamination(lines)
    lines = _clean_ad_contamination(lines)

    rows = []
    competition = None
    round_name = None

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped in COMPETITIONS:
            competition = stripped.title()
            continue
        if any(stripped == r or stripped.startswith(r) for r in ROUND_MARKERS):
            round_name = stripped
            continue
        if "Penalty shootout" in stripped or not stripped:
            continue

        m = LINE_RE.match(line)
        if not m:
            continue
        home, home_c, away, away_c, score1, score2 = m.groups()
        if competition is None:
            continue

        def add_row(score, leg_label):
            hs, aws = score.split("-")
            rows.append({
                "competition": competition, "round": round_name,
                "season": f"{season_end_year-1}/{str(season_end_year)[2:]}",
                "home_team": home.strip(), "home_country": home_c,
                "away_team": away.strip(), "away_country": away_c,
                "home_score": int(hs), "away_score": int(aws),
                "leg": leg_label,
            })

        if score2:
            # Ida y vuelta: score1 = local en el partido de ida, score2 = local en el
            # partido de vuelta (kassiesa siempre lista "ida" primero). El segundo
            # partido tiene de local al equipo que aparecia como VISITANTE en la ida.
            add_row(score1, "ida")
            hs2, aws2 = score2.split("-")
            rows.append({
                "competition": competition, "round": round_name,
                "season": f"{season_end_year-1}/{str(season_end_year)[2:]}",
                "home_team": away.strip(), "home_country": away_c,
                "away_team": home.strip(), "away_country": home_c,
                "home_score": int(hs2), "away_score": int(aws2),
                "leg": "vuelta",
            })
        else:
            add_row(score1, "unico")

    return pd.DataFrame(rows)


def normalize_for_elo(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "date": "",  # kassiesa no da fecha exacta por partido, solo temporada
        "home_team": df["home_team"],
        "away_team": df["away_team"],
        "home_score": df["home_score"],
        "away_score": df["away_score"],
        "tournament": df["competition"],
        "city": "", "country": "",
        "neutral": df["round"] == "Final",  # las finales de estas copas son en sede neutral
        "season": df["season"],
    })


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 parse_uefa_history.py <archivo.txt> <año_fin_temporada>")
        sys.exit(1)
    path, season_end = sys.argv[1], int(sys.argv[2])
    df = parse_file(path, season_end)
    print(f"Parseados: {len(df)} partidos")
    print(df["competition"].value_counts())
    print()
    print(df.head(10).to_string(index=False))
