import json
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pytest
import requests
import comparator
from comparator import build_similarity_matrix, get_best_candidates, classify_forward_match, classify_reverse_match
from extractor import clean_disclosure_text, extract_risk_units, extract_item_1A
from diff_detector import split_sentences, detect_sentence_changes, detect_text_changes, find_shifted_sentences
from sec_fetcher import download_10k_filings
from evaluate import evaluate
from report import build_report, json_default


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Network forbidden in tests')
    monkeypatch.setattr(requests,'get',forbidden)


@pytest.mark.parametrize('text', ['Apple Inc. | 2024 Form 10-K | 9', '| 2025 Form 10-K | 10'])
def test_clean(text):
    sentence='Revenue was $10.5 billion in 2024.'
    cleaned=clean_disclosure_text(sentence+' '+text+' End.')
    assert cleaned==sentence+' End.'
    assert clean_disclosure_text(cleaned)==cleaned


def filing(tmp_path,body):
    p=tmp_path/'test.html'
    p.write_text('<html><span>Item 1A. Risk Factors</span>'+body+'<span>Item 1B. Unresolved Staff Comments</span><span>Signatures SECRET</span></html>',encoding='utf-8')
    return p


H='<span style="font-weight:700; font-style:italic">Risk heading.</span>'


def test_extraction(tmp_path):
    p=filing(tmp_path,H+'<span>Real <span>nested</span> body. | 2024 Form 10-K | 9</span>')
    risks=extract_risk_units(p)
    assert len(risks)==1
    assert risks[0]['body']=='Real nested body.'
    assert 'Form 10-K' in risks[0]['raw_body']
    assert 'SECRET' not in risks[0]['body']
    assert 'Item 1B' not in extract_item_1A(p)


@pytest.mark.parametrize('body',['',H])
def test_empty_extraction(tmp_path,body):
    with pytest.raises(ValueError): extract_risk_units(filing(tmp_path,body))


def test_missing_boundaries(tmp_path):
    p=tmp_path/'bad.html';p.write_text('<html>Nothing</html>')
    with pytest.raises(ValueError): extract_risk_units(p)


def test_toc(tmp_path):
    p=filing(tmp_path,H+'<span>Only actual body.</span>')
    p.write_text('<span>Item 1A. Risk Factors</span><span>Item 1B. Unresolved Staff Comments</span>'+p.read_text())
    assert extract_risk_units(p)[0]['body']=='Only actual body.'


@pytest.mark.parametrize('text,count', [('The U.S. market grew. Next sentence.',2),('Apple Inc. sells devices. Next.',2),('Examples, e.g. devices, sell.',1),('Sales were 3.14 (up 2.5%). Next.',2),('He said "Stop." Next.',2),('Long sentence; still one sentence.',1),('',0),('Heading\n\nFirst sentence.',2),('First bullet\n• Second bullet',2)])
def test_split(text,count): assert len(split_sentences(text))==count


def test_exact_duplicate_shift():
    r=detect_sentence_changes('Same. Same. End.','Inserted. Same. End. Same.')
    assert len(r['exact_unchanged'])==3
    assert len({m['new_index'] for m in r['exact_unchanged']})==3
    assert len(r['candidate_added'])==1
    assert find_shifted_sentences('Same.','Before. Same.')[0]['index_shift']==1


def test_modified():
    r=detect_sentence_changes('The company sells red devices worldwide.','The company sells blue devices worldwide.')
    assert len(r['candidate_modified'])==1
    assert r['candidate_modified'][0]['word_diff']['replaced']


def test_reordered():
    r=detect_sentence_changes('Alpha. Beta.','Beta. Alpha.')
    assert len(r['exact_unchanged'])==2
    assert not r['candidate_added'] and not r['candidate_removed']


def test_ambiguous():
    r=detect_sentence_changes('The company sells devices. The company sells services.','The company sells devices and services.')
    assert r['needs_review']
    assert not r['candidate_modified']


@pytest.mark.parametrize('old,new,key',[('Gone.','','candidate_removed'),('','New.','candidate_added'),('','','exact_unchanged')])
def test_unmatched(old,new,key):
    r=detect_sentence_changes(old,new)
    assert len(r[key])==(0 if not old and not new else 1)


def test_word_diff(): assert detect_text_changes('a b','a c')['replaced']==[{'old':'b','new':'c'}]


def test_matrix():
    m=build_similarity_matrix(['alpha beta','gamma delta'],['alpha beta'])
    assert m.shape==(2,1)
    assert m[0,0]==pytest.approx(1)
    assert m[1,0]==0
    c=get_best_candidates(np.array([.8,.3,.2]))
    assert c['best_index']==0 and c['second_best_score']==.3
    assert c['score_gap']==pytest.approx(.5)
    assert get_best_candidates(np.array([1.]))['second_best_index'] is None
    assert get_best_candidates(np.array([1.,1.]))['best_index']==0


@pytest.mark.parametrize('old,new',[([],['x']),([''],['']),(['!!!'],['???'])])
def test_invalid_matrix(old,new):
    with pytest.raises(ValueError): build_similarity_matrix(old,new)


@pytest.mark.parametrize('score,mutual,label',[(.9,True,'mostly_unchanged'),(.899,True,'modified'),(.6,True,'modified'),(.599,True,'needs_review'),(.49,False,'candidate_removed'),(.5,False,'needs_review')])
def test_classify(score,mutual,label):
    assert classify_forward_match({'score':score,'mutual':mutual})==label
    assert classify_reverse_match({'score':score,'mutual':mutual})==label.replace('removed','new')


def test_nonmutual_and_ties(monkeypatch):
    risk=lambda text: {'heading':text,'body':text,'full_text':text}
    monkeypatch.setattr(comparator,'extract_risk_units',lambda path: [risk('alpha beta'),risk('alpha beta')] if path=='old' else [risk('alpha beta')])
    r=comparator.compare_years('old','new')
    assert sum(m['mutual'] for m in r['matches_old_to_new'])==1
    assert r['matches_new_to_old'][0]['classification']=='needs_review'


def sec_mock(monkeypatch,html='<html>filing</html>'):
    monkeypatch.setenv('SEC_USER_AGENT','Test test@example.com')
    index=Mock();index.json.return_value={'filings':{'recent':{'form':['10-K'],'filingDate':['2025-10-31'],'accessionNumber':['0000320193-25-000079'],'primaryDocument':['aapl.htm']}}}
    page=Mock(text=html)
    get=Mock(side_effect=[index,page]);monkeypatch.setattr(requests,'get',get)
    monkeypatch.setattr('sec_fetcher.time.sleep',lambda _:None)
    return get,index


def test_fetch_cache(tmp_path,monkeypatch):
    get,index=sec_mock(monkeypatch)
    paths=download_10k_filings('0000320193',tmp_path)
    assert paths[0].read_text()=='<html>filing</html>'
    assert 'CIK0000320193.json' in get.call_args_list[0].args[0]
    assert '/320193/000032019325000079/aapl.htm' in get.call_args_list[1].args[0]
    get.side_effect=[index]
    download_10k_filings(320193,tmp_path)
    assert get.call_count==3


@pytest.mark.parametrize('cik',['abc',0,'12345678901','../'])
def test_invalid_cik(cik):
    with pytest.raises(ValueError): download_10k_filings(cik)


def test_invalid_response(tmp_path,monkeypatch):
    sec_mock(monkeypatch,html='Access denied')
    with pytest.raises(ValueError): download_10k_filings(320193,tmp_path)
    assert not list(tmp_path.glob('*.html'))


def test_http_error(tmp_path,monkeypatch):
    _,index=sec_mock(monkeypatch)
    index.raise_for_status.side_effect=requests.HTTPError('403')
    with pytest.raises(requests.HTTPError): download_10k_filings(320193,tmp_path)


def test_invalid_arrays(tmp_path,monkeypatch):
    _,index=sec_mock(monkeypatch)
    index.json.return_value={'filings':{'recent':{'form':[]}}}
    with pytest.raises(ValueError): download_10k_filings(320193,tmp_path)


def test_evaluation():
    assert evaluate([], {})['verified_samples']==0
    report={'matches_old_to_new':[{'index_old':0,'index_new':1,'classification':'modified'}]}
    rows=[{'old_id':0,'new_id':1,'human_label':'modified','reviewed':True}]
    result=evaluate(rows,report)
    assert result['metrics']['modified']['f1']==1
    assert result['match_correctness']['rate']==1
    rows[0]['reviewed']=False
    assert evaluate(rows,report)['verified_samples']==0


@pytest.mark.integration
def test_apple():
    root=Path(__file__).resolve().parents[1]
    old,new=[root/name for name in ('10K_2024-11-01.html','10K_2025-10-31.html')]
    if not old.exists() or not new.exists(): pytest.skip('Cached Apple filings unavailable')
    r=build_report(old,new)
    assert len(r['risks_old'])==28 and len(r['risks_new'])==27
    assert r['full_similarities'].shape==(28,27)
    for risks in (r['risks_old'],r['risks_new']):
        for risk in risks:
            assert risk['body']
            assert 'Form 10-K |' not in risk['body']
            assert 'Item 1B.' not in risk['body'] and 'SIGNATURES' not in risk['body']
    assert r['removed'][0]['index_old']==16
    assert r['matches_old_to_new'][-1]['index_new']==26
    assert r['matches_old_to_new'][-1]['mutual']
    again=build_report(old,new)
    assert json.dumps(r,default=json_default,sort_keys=True)==json.dumps(again,default=json_default,sort_keys=True)


def test_terminal_us():
    assert len(split_sentences('Facilities located in the U.S. The Company relies on partners.'))==2


def test_category_heading(tmp_path):
    p=filing(tmp_path,H+'<span>Actual body.</span><span style="font-weight:700">Financial Risks</span>')
    assert extract_risk_units(p)[0]['body']=='Actual body.'


def test_missing_identity(monkeypatch):
    monkeypatch.delenv('SEC_USER_AGENT',raising=False)
    with pytest.raises(ValueError): download_10k_filings(320193)


def test_invalid_identifier(tmp_path,monkeypatch):
    _,index=sec_mock(monkeypatch)
    index.json.return_value['filings']['recent']['primaryDocument']=['../escape.html']
    with pytest.raises(ValueError): download_10k_filings(320193,tmp_path)


def test_empty_candidates():
    with pytest.raises(ValueError): get_best_candidates(np.array([]))
