# AI 10-K Risk Detector

A Python research prototype for comparing risk disclosures across SEC Form 10-K filings. It extracts Item 1A risk factors and uses TF-IDF cosine similarity to identify changes between reporting years.

## Features

- Download available annual filings from SEC EDGAR for Apple (CIK `320193`).
- Extract individual risk headings and their supporting text from Item 1A.
- Compare full text, headings, and bodies across two filings.
- Report mostly unchanged, modified, potentially new, potentially removed, and ambiguous risks.
- Include mutual matches and second-best score gaps to support manual review.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/simobek/AI-10-K-RISK-DETECTOR.git
cd AI-10-K-RISK-DETECTOR
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

## Usage

### 1. Download filings

Set `SEC_USER_AGENT` to your name and contact email before making SEC requests:

```powershell
$env:SEC_USER_AGENT = "Your Name your.email@example.com"
python sec_fetcher.py
```

```bash
SEC_USER_AGENT="Your Name your.email@example.com" python sec_fetcher.py
```

The fetcher saves `10K_YYYY-MM-DD.html` files in the project directory and skips files already present. Downloaded filings are excluded from version control. It reads the SEC submissions endpoint's recent filing list; this is not a complete historical archive.

### 2. Inspect extraction

```bash
python extractor.py
```

Prints extraction diagnostics for the 2024 and 2025 filings, including first and last risk headings and basic section-boundary checks.

### 3. Compare reporting years

```bash
python comparator.py
```

By default, compares `10K_2024-11-01.html` with `10K_2025-10-31.html` and prints a report to the terminal. To compare other filings, update `file_old` and `file_new` in the script's main block.

## How matching works

The comparator fits TF-IDF representations jointly across both filings, then computes cosine similarity. Each risk is matched to its closest counterpart in both directions. A match is mutual when both risks select each other.

| Classification | Current rule |
| --- | --- |
| Mostly unchanged | Mutual match with similarity at least 0.90 |
| Modified | Mutual match with similarity from 0.60 to below 0.90 |
| Candidate removed / new | Non-mutual match with similarity below 0.50 |
| Needs review | All remaining cases |

Classification uses full-text similarity. Heading similarity, body similarity, and the gap between the best and second-best candidates are additional diagnostics. Scores are similarity measures, not probabilities.

## Project structure

| File | Purpose |
| --- | --- |
| `sec_fetcher.py` | Download SEC 10-K filings |
| `extractor.py` | Locate Item 1A and segment risk disclosures |
| `comparator.py` | Match risks and print comparison results |
| `requirements.txt` | Python dependencies |

## Limitations

The extractor currently relies on Apple-specific HTML styling and heuristic section boundaries. Other issuers and older filings may require changes. The matching rules are experimental and can miss splits, mergers, or rewritten disclosures. Review the source filings before drawing conclusions; the output is not investment advice.

## Data source

Filings are downloaded from [SEC EDGAR](https://www.sec.gov/edgar). Follow the SEC's [automated access guidance](https://www.sec.gov/os/accessing-edgar-data) when downloading data.
