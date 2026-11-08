"""Offline JSON report command; no SEC requests are made."""
import argparse
import hashlib
import json
from pathlib import Path
from comparator import compare_years
from diff_detector import detect_sentence_changes, SENTENCE_CONFIG


def build_report(old, new):
    result = compare_years(old, new)
    result['metadata'] = {'algorithm_version':'deterministic-1', 'sentence_config':SENTENCE_CONFIG,
        'risk_thresholds': {'unchanged':0.90,'modified':0.60,'unmatched':0.50},
        'sources':[{'filename':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in (old,new)],
        'interpretation':'Changes in disclosed language only. Thresholds provisional; similarities are not probabilities.',
        'company':'Apple Inc.' if all('Apple Inc.' in Path(p).read_text(encoding='utf-8') for p in (old,new)) else None,
        'filing_dates':[Path(p).stem.removeprefix('10K_') for p in (old,new)]}
    result['summary'] = {k:len(result[k]) for k in ('mostly_unchanged','modified','removed','new','needs_review')}
    result['sentence_changes'] = [{'index_old':m['index_old'],'index_new':m['index_new'], 'changes':detect_sentence_changes(m['risk_old']['body'],m['risk_new']['body'])} for m in result['modified']]
    return result


def json_default(value):
    if hasattr(value,'tolist'):
        return value.tolist()
    raise TypeError(f'Unsupported JSON value: {type(value)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old',default='10K_2024-11-01.html')
    parser.add_argument('--new',default='10K_2025-10-31.html')
    parser.add_argument('--output',default='reports/apple_2024_2025.json')
    args=parser.parse_args()
    report=build_report(args.old,args.new)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,default=json_default,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report['summary']))
