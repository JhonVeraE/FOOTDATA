"""Paths independent of the invoking shell's working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / 'data' / 'live'
ARTIFACT_DIR = PROJECT_ROOT / 'data' / 'artifacts'
WEB_DIR = PROJECT_ROOT / 'web'
# Match results, settled fijas and review pages: never published on the public site.
# Administrators read them from Supabase (sync_supabase.py) in the admin panel.
PRIVATE_DIR = ARTIFACT_DIR / 'resultados_privados'
