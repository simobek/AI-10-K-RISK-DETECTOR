"""Download recent SEC 10-K filings with explicit identity and local caching."""
import os
import re
import time
from pathlib import Path
import requests


def download_10k_filings(cik, output_dir=None):
    """Return cached/downloaded paths; raise on invalid SEC data or HTTP errors.

    The submissions index is refreshed each call. Filings are cached under a
    company-specific directory to prevent collisions between equal filing dates.
    """
    cik = str(cik)
    if not re.fullmatch(r'\d{1,10}', cik) or int(cik) == 0:
        raise ValueError('CIK must be a positive identifier of at most 10 digits')
    cik = str(int(cik))
    identity = os.environ.get('SEC_USER_AGENT')
    if not identity:
        raise ValueError('Set SEC_USER_AGENT to your name and contact email.')
    headers = {'User-Agent':identity}
    directory = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parent / 'filings' / cik.zfill(10)
    response = requests.get(f'https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json',headers=headers,timeout=30)
    response.raise_for_status()
    recent = response.json()['filings']['recent']
    fields = ('form','filingDate','accessionNumber','primaryDocument')
    if any(not isinstance(recent.get(key),list) for key in fields) or len({len(recent[key]) for key in fields}) != 1:
        raise ValueError('Malformed SEC recent filings arrays')
    directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for form,date,accession,document in zip(*(recent[key] for key in fields)):
        if form != '10-K':
            continue
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession) or not re.fullmatch(r'[\w.-]+',document):
            raise ValueError('Invalid SEC filing identifier')
        path=directory / f'10K_{date}.html'
        paths.append(path)
        if path.exists() and path.stat().st_size:
            continue
        time.sleep(0.2)
        filing=requests.get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-", "")}/{document}',headers=headers,timeout=30)
        filing.raise_for_status()
        if not filing.text.strip() or '<html' not in filing.text.lower():
            raise ValueError('SEC response is not an HTML filing')
        temporary=path.with_suffix('.html.tmp')
        temporary.write_text(filing.text,encoding='utf-8')
        temporary.replace(path)
    return paths


if __name__ == '__main__':
    for path in download_10k_filings(320193):
        print(path)
