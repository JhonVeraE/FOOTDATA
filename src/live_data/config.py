"""
Configuracion del pipeline de datos en vivo (API-Football / api-sports.io).

1) Registrate gratis en https://dashboard.api-football.com/register
   (o via RapidAPI: https://rapidapi.com/api-sports/api/api-football)
2) Te dan una API KEY y 100 requests/dia gratis.
3) Pegala aca abajo en API_KEY (o mejor: como variable de entorno API_FOOTBALL_KEY,
   asi no la subis por accidente a ningun repo publico).

Los "league_id" de abajo son EJEMPLOS tipicos para estas competiciones en
API-Football, pero los ids pueden cambiar de temporada a temporada o si la
API reorganiza su catalogo. SIEMPRE confirmalos vos mismo corriendo
`python3 find_league_ids.py` (te lo dejo armado) antes de creer estos
numeros a ciegas -- yo no pude probarlos en vivo porque este entorno no
tiene acceso a internet para llamar la API real.
"""
import os

from settings import secret
API_KEY = secret('API_FOOTBALL_KEY')
BASE_URL = "https://v3.football.api-sports.io"

# Temporada a consultar (ojo: en Sudamerica el "season" en API-Football suele
# ser el anio de arranque del torneo, no siempre calza con el calendario europeo)
SEASON = 2026

# IDs de ejemplo -- CONFIRMAR con find_league_ids.py antes de usar en serio
LEAGUES = {
    "Liga Profesional Argentina": 128,
    "Primera A Colombia": 239,
    "UEFA Champions League": 2,
}

# Carpeta donde se van a guardar los CSV ya procesados (cache local, esto es
# lo que despues lee el modelo / la web -- NUNCA se consulta la API en vivo
# desde el frontend)
from paths import DATA_DIR
