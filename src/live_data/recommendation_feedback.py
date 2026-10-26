"""Prior published market outcomes used for ranking, never as probabilities."""
import json
from pathlib import Path
import pandas as pd
from paths import ARTIFACT_DIR

def load_feedback(root=None):
    unique={}
    for file in sorted((Path(root) if root else ARTIFACT_DIR/'daily_reviews').glob('*/recommendation_review.json')):
        data=json.loads(file.read_text(encoding='utf-8'))
        frozen=file.parent/'fijas_before_results.json'
        if not frozen.exists():continue
        selections={}
        for m in json.loads(frozen.read_text(encoding='utf-8'))['matches']:
            for slot in m['tiers']+m['markets']:
                c=slot.get('selection')
                if c:selections[(m['fixture_id'],c['id'])]=(m,c)
        for r in data['unique_selections']:
            key=(r['fixture_id'],r['selection_id'])
            if r['status'] not in ['won','lost'] or key not in selections:continue
            m,c=selections[key]
            unique[key]={'fixture_id':m['fixture_id'],'date':data['date'],
                'reviewed_at':data['reviewed_at'],'kickoff_utc':m['kickoff_utc'],
                'home':m['home'],'away':m['away'],'selection':c,
                'hit':r['status']=='won','probability':c['probability']}
    return sorted(unique.values(),key=lambda r:(r['date'],r['fixture_id']))

def signature(c,home,away):
    scope=c.get('scope','total');side=c['side']
    if scope in ['home','away']:team=home if scope=='home' else away;scope='team'
    elif c['kind'] in ['handicap','result'] and side in ['home','away']:
        team=home if side=='home' else away;side='own'
    else:team='|'.join(sorted([home,away]))
    return (team,c['kind'],scope,side,c.get('line'),c.get('direction'))

def annotate(options,report,records):
    # Completed games and their review must both precede the new publication.
    clock=pd.Timestamp(report['generated_at']);cut=min(pd.Timestamp(report['cutoff']),pd.Timestamp(report['fecha']))
    eligible=[r for r in records if pd.Timestamp(r['date'])<cut and pd.Timestamp(r['reviewed_at'])<clock]
    for c in options:
        family=[r for r in eligible if r['selection']['kind']==c['kind']]
        n=len(family);wins=sum(r['hit'] for r in family);expected=sum(r['probability'] for r in family)
        debt=max(0.,(expected-wins)/(n+20))
        bonus=min(.01,max(0.,(wins-expected)/(n+20))*.10) if n>=8 else 0.
        same=[r for r in eligible if signature(r['selection'],r['home'],r['away'])==signature(c,report['local'],report['visitante'])][-3:]
        repeat=len(same)>=2 and not same[-1]['hit'] and sum(not r['hit'] for r in same)>=2
        streak=min((v.get('current_hit_streak',0) for v in c['evidence']['contexts']),default=0)
        c['performance_review']={'family_observations':n,'family_won':wins,
            'ranking_penalty':min(.06,debt*.25),'ranking_bonus':bonus,
            'same_team_market_recent_results':[r['hit'] for r in same],
            'repeat_failure_block':bool(repeat and streak<2),
            'note':'Historial publicado anterior al corte; ajusta selección, no la probabilidad del modelo.'}
    return options
