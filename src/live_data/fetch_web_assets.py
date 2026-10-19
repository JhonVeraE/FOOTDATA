"""Cache provider-supplied club crests locally, without sending credentials to image hosts."""
import json,re,time
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import requests
from paths import WEB_DIR
from settings import secret
from data_store import canonical_team

COMPETITIONS={'La Liga':'PD','Premier League':'PL','Bundesliga':'BL1','Serie A':'SA','Ligue 1':'FL1','UEFA Champions League':'CL'}

def safe_svg(content):
    tree=ET.fromstring(content)
    for parent in list(tree.iter()):
        for child in list(parent):
            if child.tag.split('}')[-1] in ['script','foreignObject']:parent.remove(child)
        for key,value in list(parent.attrib.items()):
            if key.lower().startswith('on') or (key.split('}')[-1] in ['href','src'] and not value.startswith('#')):del parent.attrib[key]
    return ET.tostring(tree,encoding='utf-8',xml_declaration=True)

def main():
    token=secret('FOOTBALL_DATA_KEY')
    if not token:raise RuntimeError('FOOTBALL_DATA_KEY missing')
    assets=WEB_DIR/'assets';(assets/'crests').mkdir(parents=True,exist_ok=True);(assets/'competitions').mkdir(exist_ok=True)
    manifest={'teams':{},'competitions':{},'failures':[],'source':'football-data.org provider crest URLs'}
    def download(url,relative):
        if not url or urlparse(url).scheme!='https':raise ValueError('No HTTPS crest URL')
        ext='.svg' if urlparse(url).path.lower().endswith('.svg') else '.png'
        target=assets/(relative+ext)
        if not target.exists():
            response=requests.get(url,timeout=25);response.raise_for_status();content=response.content
            if ext=='.svg':content=safe_svg(content)
            elif not content.startswith(b'\x89PNG'):raise ValueError('Expected PNG image')
            target.write_bytes(content)
        return 'assets/'+relative+ext
    for league,code in COMPETITIONS.items():
        response=requests.get(f'https://api.football-data.org/v4/competitions/{code}/teams',headers={'X-Auth-Token':token},timeout=30)
        response.raise_for_status();data=response.json()
        emblem=data.get('competition',{}).get('emblem')
        if emblem:
            try:manifest['competitions'][league]={'image':download(emblem,'competitions/'+code),'source':emblem}
            except Exception as e:manifest['failures'].append({'competition':league,'error':str(e)[:100]})
        for team in data.get('teams',[]):
            name=canonical_team(team['name'])
            if name in manifest['teams']:continue
            try:
                manifest['teams'][name]={'name':team['name'],'short_name':team.get('shortName'),'image':download(team.get('crest'),'crests/'+str(team['id'])),'source':team.get('crest'),'provider_id':team['id']}
            except Exception as e:manifest['failures'].append({'team':name,'url':team.get('crest'),'error':str(e)[:100]})
        print(f'{league}: {len(manifest["teams"])} distinct crests cached',flush=True)
    target=WEB_DIR/'data/assets.json';target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    predictions=json.loads((WEB_DIR/'data/predictions.json').read_text(encoding='utf-8'))['matches']
    missing=sorted({t for m in predictions for t in [m['local'],m['visitante']] if t not in manifest['teams']})
    print(json.dumps({'teams':len(manifest['teams']),'competition_logos':len(manifest['competitions']),'missing_predicted_teams':missing,'failures':manifest['failures']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
