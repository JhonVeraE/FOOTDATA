"""
Cliente minimo para API-Football, pensado para NO desperdiciar el cupo
gratis de 100 requests/dia:

  - Cachea cada respuesta en disco (data/live/_cache/) usando la URL+params
    como clave. Si ya pediste algo hoy, no lo vuelve a pedir.
  - Lleva la cuenta de cuantos requests hiciste en el dia (contador local en
    _cache/quota.json) y CORTA antes de pasarte del limite, en vez de
    quemar el cupo y enterarte por un error 429.
  - Reintenta una vez con backoff si la API devuelve error transitorio.

No lo pude probar contra la API real (este entorno no tiene salida a
internet), asi que antes de usarlo en produccion corré primero
`python3 find_league_ids.py` y `python3 fetch_fixtures.py` a mano y
revisá la respuesta cruda (queda guardada en _cache/) para confirmar que
el formato de campos coincide con lo que espera build_dataset.py.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import requests

from config import API_KEY, BASE_URL

from paths import DATA_DIR
CACHE_DIR = DATA_DIR / "_cache"
DAILY_LIMIT = 95  # dejamos 5 de margen sobre el limite real de 100


def _cache_key(endpoint, params):
    raw = endpoint + json.dumps(params, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _quota_path():
    return os.path.join(CACHE_DIR, "quota.json")


def _load_quota():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _quota_path()
    today = str(datetime.now(timezone.utc).date())
    if os.path.exists(path):
        with open(path) as f:
            q = json.load(f)
        if q.get("date") == today:
            return q
    return {"date": today, "used": 0}


def _save_quota(q):
    with open(_quota_path(), "w") as f:
        json.dump(q, f)


def get(endpoint: str, params: dict, force_refresh: bool = False, ttl_seconds=21600):
    """GET a un endpoint de API-Football, con cache en disco y control de cupo.
    Devuelve el JSON ya parseado (campo "response" de la API)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _cache_key(endpoint, params)
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")

    if not force_refresh and os.path.exists(cache_file) and time.time()-os.path.getmtime(cache_file)<ttl_seconds:
        with open(cache_file, encoding="utf-8") as f:
            cached = json.load(f)
        print(f"  [cache] {endpoint} {params}")
        if not cached.get('errors'):return cached.get('response',[])

    quota = _load_quota()
    if quota["used"] >= DAILY_LIMIT:
        raise RuntimeError(
            f"Cupo diario agotado ({quota['used']}/{DAILY_LIMIT}). "
            f"Esperá al reset (medianoche UTC) o subí de plan. "
            f"Nada te obliga a pedir todo hoy: correlo de nuevo mañana."
        )

    if API_KEY in ("PEGA_TU_API_KEY_ACA", "", None):
        raise RuntimeError(
            "Falta configurar tu API key real en config.py (o en la variable "
            "de entorno API_FOOTBALL_KEY). Registrate gratis en "
            "https://dashboard.api-football.com/register"
        )

    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"

    for intento in range(2):
        if quota['used']>=DAILY_LIMIT:raise RuntimeError('Daily request limit reached')
        quota['used']+=1
        _save_quota(quota)
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 200:
            break
        print(f"  [!] intento {intento+1} fallo: HTTP {resp.status_code} -> {resp.text[:200]}")
        time.sleep(2)
    else:
        raise RuntimeError(f"No se pudo obtener {endpoint} {params} tras 2 intentos.")

    data = resp.json()
    print(f"  [api] {endpoint} {params} -> cupo usado: {quota['used']}/{DAILY_LIMIT}")

    if data.get("errors"):
        raise RuntimeError('API returned errors; prior cache retained')
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return data.get("response", [])
