"""Retrospective holdout audit of recency filtering on original published picks."""
import json
from pathlib import Path
from data_store import load_match_stats
from recommendations import historical_context,evidence,recent_support
from paths import ARTIFACT_DIR

def main():
    stats=load_match_stats();rows=[];seen=set()
    for path in sorted((ARTIFACT_DIR/'daily_reviews').glob('*/recommendation_review.json')):
        review=json.loads(path.read_text(encoding='utf-8'))
        directory=path.parent
        if not (directory/'predictions_before_results.json').exists():continue
        pred={m['fixture_id']:m for m in json.loads((directory/'predictions_before_results.json').read_text(encoding='utf-8'))['matches']}
        fijas={m['fixture_id']:m for m in json.loads((directory/'fijas_before_results.json').read_text(encoding='utf-8'))['matches']}
        for r in review['tiers']:
            key=(r['fixture_id'],r['tier'])
            if r['status'] not in ['won','lost'] or key in seen:continue
            seen.add(key)
            if r['tier']!='Conservadora':continue
            m=pred[r['fixture_id']]
            c=next(t['selection'] for t in fijas[r['fixture_id']]['tiers'] if t['label']==r['tier'])
            recency=evidence(c,historical_context(stats,m),m)
            rows.append({'fixture_id':r['fixture_id'],'date':review['date'],'match':r['match'],
                'selection':r['label'],'won':r['status']=='won',
                'accepted':recent_support({'evidence':recency})})
    def summary(data):
        kept=[r for r in data if r['accepted']]
        return {'baseline':{'n':len(data),'won':sum(r['won'] for r in data)},
                'filtered':{'n':len(kept),'won':sum(r['won'] for r in kept)},
                'excluded':[r for r in data if not r['accepted']]}
    result={'protocol':'Retrospective audit of a fixed 2/3 recency gate; original probabilities and exclusive pre-publication cutoffs. No alternative-pick or profitability claim. Team-market feedback is prospective and not validated by this filter-only audit.',
        'development_through':'2026-10-21','holdout_from':'2026-10-23',
        'development':summary([r for r in rows if r['date']<='2026-10-21']),
        'holdout':summary([r for r in rows if r['date']>='2026-10-23'])}
    a=result['holdout']['baseline'];b=result['holdout']['filtered']
    result['recency_gate_passed']=bool(b['n']>=15 and b['n']>=a['n']*.7 and b['won']/b['n']>=a['won']/a['n'])
    (ARTIFACT_DIR/'recommendation_filter_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':main()
