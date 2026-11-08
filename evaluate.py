"""Evaluate only explicitly reviewed human annotations against a saved report."""
import argparse
import json
from collections import Counter
from pathlib import Path


def evaluate(rows, report):
    verified=[r for r in rows if r.get('reviewed') is True and r.get('human_label')]
    if not verified:
        return {'verified_samples':0,'message':'Reliable accuracy metrics cannot be calculated: no verified human annotations.'}
    matrix=Counter()
    match_correct=0
    for row in verified:
        matches=report['matches_old_to_new'] if row['old_id'] is not None else report['matches_new_to_old']
        key='index_old' if row['old_id'] is not None else 'index_new'
        identifier=row['old_id'] if row['old_id'] is not None else row['new_id']
        match=next((m for m in matches if m[key]==identifier),None)
        prediction=match['classification'] if match else 'missing_prediction'
        matrix[row['human_label'],prediction]+=1
        if match and row['new_id'] is not None and row['old_id'] is not None:
            match_correct += int(match['index_old']==row['old_id'] and match['index_new']==row['new_id'])
    metrics={}
    for label in sorted({x for pair in matrix for x in pair}):
        tp=matrix[label,label]; actual=sum(n for (a,b),n in matrix.items() if a==label); predicted=sum(n for (a,b),n in matrix.items() if b==label)
        precision=tp/predicted if predicted else 0.0; recall=tp/actual if actual else 0.0
        metrics[label]={'support':actual,'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0}
    paired=sum(r['old_id'] is not None and r['new_id'] is not None for r in verified)
    return {'verified_samples':len(verified),'metrics':metrics,'confusion_matrix':[{'actual':a,'predicted':b,'count':n} for (a,b),n in sorted(matrix.items())], 'match_correctness':{'correct':match_correct,'samples':paired,'rate':match_correct/paired if paired else None}, 'limitations':'Small selected sample; metrics do not estimate population performance. Zero denominators use zero.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--annotations',default='evaluation/annotations.json');p.add_argument('--report',default='reports/apple_2024_2025.json');a=p.parse_args()
    print(json.dumps(evaluate(json.loads(Path(a.annotations).read_text(encoding='utf-8')),json.loads(Path(a.report).read_text(encoding='utf-8'))),indent=2))
