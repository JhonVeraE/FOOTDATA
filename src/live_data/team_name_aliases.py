"""
football-data.org usa nombres oficiales completos ("FC Barcelona", "Real
Madrid CF"). datahub/football-data.co.uk usa nombres cortos ("Barcelona",
"Real Madrid"). Sin esto, el cruce de equipos entre el calendario real y
el historial de resultados falla silenciosamente (o, como paso, salta
CASI todos los partidos).

Estrategia en 2 pasos:
  1. Tabla armada a mano con los equipos reales de las 5 ligas (sacada de
     los nombres que devolvio tu propia corrida de fetch_footballdata.py,
     asi que estos SI son exactos).
  2. Si un equipo no esta en la tabla (por ejemplo, se agrega una liga
     nueva mas adelante), fallback automatico: sacar sufijos genericos
     (FC, CF, AFC, Calcio, numeros de fundacion, etc.) y buscar el nombre
     mas parecido dentro de los equipos que SI tienen historial cargado.
"""
import re
import difflib

ALIASES = {
    # La Liga
    "Deportivo Alavés": "Alaves", "Getafe CF": "Getafe", "Sevilla FC": "Sevilla",
    "Rayo Vallecano de Madrid": "Vallecano", "Real Racing Club de Santander": "Santander",
    "Villarreal CF": "Villarreal", "RCD Espanyol de Barcelona": "Espanol", "Levante UD": "Levante",
    "RC Celta de Vigo": "Celta", "CA Osasuna": "Osasuna", "RC Deportivo La Coruña": "La Coruna",
    "Elche CF": "Elche", "Club Atlético de Madrid": "Ath Madrid", "Málaga CF": "Malaga",
    "Valencia CF": "Valencia", "Real Betis Balompié": "Betis", "Real Madrid CF": "Real Madrid",
    "Real Sociedad de Fútbol": "Sociedad", "FC Barcelona": "Barcelona", "Athletic Club": "Ath Bilbao",

    # Premier League
    "Arsenal FC": "Arsenal", "Coventry City FC": "Coventry", "Hull City AFC": "Hull",
    "Manchester United FC": "Man United", "Ipswich Town FC": "Ipswich", "Sunderland AFC": "Sunderland",
    "Nottingham Forest FC": "Nott'm Forest", "Leeds United FC": "Leeds", "Everton FC": "Everton",
    "Crystal Palace FC": "Crystal Palace", "Brentford FC": "Brentford", "Tottenham Hotspur FC": "Tottenham",
    "Manchester City FC": "Man City", "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion FC": "Brighton", "Aston Villa FC": "Aston Villa",
    "Newcastle United FC": "Newcastle", "Liverpool FC": "Liverpool", "Fulham FC": "Fulham",
    "Chelsea FC": "Chelsea",

    # Ligue 1
    "Olympique de Marseille": "Marseille", "RC Strasbourg Alsace": "Strasbourg",
    "Racing Club de Lens": "Lens", "AJ Auxerre": "Auxerre", "Le Mans FC": "Le Mans",
    "Stade Brestois 29": "Brest", "ES Troyes AC": "Troyes", "Paris FC": "Paris FC",
    "OGC Nice": "Nice", "FC Lorient": "Lorient", "Toulouse FC": "Toulouse",
    "Olympique Lyonnais": "Lyon", "Angers SCO": "Angers", "Lille OSC": "Lille",
    "Le Havre AC": "Le Havre", "AS Monaco FC": "Monaco", "Paris Saint-Germain FC": "Paris SG",
    "Stade Rennais FC 1901": "Rennes",

    # Serie A
    "Udinese Calcio": "Udinese", "Como 1907": "Como", "FC Internazionale Milano": "Inter",
    "AC Monza": "Monza", "Genoa CFC": "Genoa", "SSC Napoli": "Napoli",
    "Parma Calcio 1913": "Parma", "Cagliari Calcio": "Cagliari", "Frosinone Calcio": "Frosinone",
    "Juventus FC": "Juventus", "Venezia FC": "Venezia", "US Lecce": "Lecce",
    "Atalanta BC": "Atalanta", "US Sassuolo Calcio": "Sassuolo", "Torino FC": "Torino",
    "AC Milan": "Milan", "Bologna FC 1909": "Bologna", "SS Lazio": "Lazio",
    "AS Roma": "Roma", "ACF Fiorentina": "Fiorentina",

    # Bundesliga
    "1. FSV Mainz 05": "Mainz", "Bayer 04 Leverkusen": "Leverkusen", "SC Paderborn 07": "Paderborn",
    "VfB Stuttgart": "Stuttgart", "1. FC Köln": "FC Koln", "Borussia Mönchengladbach": "M'gladbach",
    "SC Freiburg": "Freiburg", "FC Schalke 04": "Schalke 04", "1. FC Union Berlin": "Union Berlin",
    "SV 07 Elversberg": "Elversberg", "TSG 1899 Hoffenheim": "Hoffenheim", "Hamburger SV": "Hamburg",
    "FC Augsburg": "Augsburg", "FC Bayern München": "Bayern Munich", "Borussia Dortmund": "Dortmund",
    "SV Werder Bremen": "Werder Bremen",
}

ALIASES.update({"Eintracht Frankfurt":"Frankfurt", "Manchester City":"Man City", "Manchester United":"Man United", "Man Utd":"Man United", "Atlético Madrid":"Ath Madrid", "Real Betis":"Betis", "PSG":"Paris SG", "Paris Saint-Germain":"Paris SG", "FK Bodø/Glimt":"Bodo/Glimt", "Bodø/Glimt":"Bodo/Glimt", "Sporting Clube de Portugal":"Sporting CP", "Galatasaray SK":"Galatasaray", "SK Slavia Praha":"Slavia Praha"})

_JUNK_WORDS = [
    "FC", "CF", "AFC", "SC", "AC", "CFC", "AS", "SS", "US", "RC", "RCD", "CA", "UD",
    "Calcio", "Club", "de", "1907", "1913", "1901", "1909", "07", "04", "05",
]


def _strip_junk(name: str) -> str:
    tokens = [t for t in re.split(r"\s+", name) if t not in _JUNK_WORDS]
    return " ".join(tokens).strip()


def normalize_team_name(name, known_names: set) -> str:
    """Devuelve el nombre normalizado (tal cual aparece en el historial de
    resultados) para un nombre que vino del calendario (football-data.org).
    Si no encuentra nada razonable, devuelve el nombre original sin tocar
    (y quien llama decide que hacer con el 'no encontrado')."""
    # Guarda: si algun dato vino roto (celda vacia que pandas leyo como NaN,
    # un float en vez de texto), no intentamos compararlo como si fuera texto.
    known_names = {n for n in known_names if isinstance(n, str)}
    if not isinstance(name, str):
        return name

    if name in known_names:
        return name
    if name in ALIASES and ALIASES[name] in known_names:
        return ALIASES[name]

    # Fallback: sacar palabras genericas y buscar el mas parecido.
    # IMPORTANTE: cutoff alto (0.82) a proposito. Con un cutoff mas laxo
    # (probamos 0.6) aparecen falsos positivos peligrosos, ej. "Le Mans"
    # (sin historial real, equipo recien ascendido) matcheaba con "Lens"
    # (equipo real, con historial) solo por parecido de letras -- eso
    # generaria una prediccion basada en el equipo EQUIVOCADO, mucho peor
    # que simplemente avisar que no hay dato.
    # Unknown identities are explicit. Similar spelling must never select a club.
    return name
