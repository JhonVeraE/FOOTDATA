"""Environment-first local settings. No embedded credentials."""
import os
from data_store import today_local
from paths import PROJECT_ROOT

def secret(name):
    if os.environ.get(name):return os.environ[name]
    p=PROJECT_ROOT/'.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip()==name:return value.strip().strip('"').strip("'")
    return ''

def current_season_code():
    override=os.environ.get('FOOTBALL_SEASON_CODE')
    if override:
        if len(override)!=4 or not override.isdigit():raise ValueError('FOOTBALL_SEASON_CODE must be e.g. 2627')
        return override
    now=today_local();year=now.year if now.month>=7 else now.year-1
    return f'{year%100:02d}{(year+1)%100:02d}'
