"""Paths independent of the invoking shell's working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / 'data' / 'live'
ARTIFACT_DIR = PROJECT_ROOT / 'data' / 'artifacts'
WEB_DIR = PROJECT_ROOT / 'web'
