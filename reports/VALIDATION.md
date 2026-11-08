# Deterministic baseline validation — 2026-11-07

Readiness: **Ready with limitations**. The cached Apple pair is a reproducible baseline; this is not a validated general SEC parser or a measured semantic matching system.

## Implementation and review

Preserved the four core modules and the existing local comparator/diff work. Baseline output was 28/27 risks, matrices (28,27), 20 mostly unchanged, 7 modified, 1 candidate removed, zero candidate new and zero risk-level review. Cleaning and category-heading removal preserve these counts; scores change slightly. `baseline.txt` records the initial execution. Snapshots of pre-existing edited modules are retained under reports.

Extractor now cleans page furniture before risk vectorization, retains raw body and joined-HTML-text offsets (not byte offsets), avoids nested-span duplication, rejects empty bodies, and avoids a TOC start spanning a later actual Item 1A. Removes four observed Apple category headings only when bold. Formatting remains Apple-specific. The removed footer includes `Apple Inc. | 2024 Form 10-K | 9`; its legitimate numeric disclosure neighbors remain. Whitespace normalization is idempotent. Source HTML files are untouched.

Sentence detector removes unreachable duplicate code, handles common abbreviations/decimals/closing quotes, matches exact occurrences globally without duplicate reuse, and returns indexed candidates plus word diffs for accepted pairs. Index shifts do not establish relocation. Extensive rewrites stay in review. Provisional sentence gates: sequence >= .65, lexical Jaccard >= .35, both best-score gaps >= .08, mutual best, no secondary sequence candidate >= .65. These are conservative engineering heuristics checked on synthetic cases and observed excerpts, not calibrated thresholds or validated accuracy claims. Similarity gates can still miss split/merge relationships. A second review caught a terminal U.S. sentence merge and added a targeted regression test. Abbreviation boundaries such as terminal Inc. remain inherently ambiguous. Bullet/paragraph splitting works on directly supplied formatted text, but HTML body whitespace normalization loses some layout evidence.

Risk TF-IDF stays jointly fitted over both years, separately for full text, headings and bodies. Existing .90/.60/.50 thresholds are unchanged. Ties now rank stably and are flagged for review rather than treated as unique matches. Non-mutual nearest candidates are diagnostics, not exclusive assignments. Empty vocabularies/lists raise clear errors. No semantic guarantees are made for low-gap near-ties.

Fetcher now validates CIK/accession/path components, normalizes padded CIK archive URLs, validates parallel index arrays, raises on bad HTTP/HTML responses, returns paths, and writes complete downloads atomically. Default caches are company-specific to prevent same-date cross-company collisions; existing root-level cached Apple files remain usable by the offline pipeline. Submissions index still refreshes on invocation; only document downloads are skipped. Mocked tests make no SEC requests.

## Source review (agent inspection, NOT independent human annotations)

Traced extracted headings and body ends against the supplied HTML text and report:

- Outsourcing old 4 -> new 4, mutual modified: manufacturing/geographical wording changes; a long group of removed/rearranged passages remains unresolved. The observed .976 pair is a wording candidate, not accuracy evidence.
- IP old 8 -> new 8, mutual modified: updated licensing wording and a paragraph on machine learning/AI copyright. Footer no longer appears as a sentence pair. Licensing condensation remains reviewable.
- ESG old 19 -> new 18, mutual modified: heading changes from ESG expectations to varied stakeholder expectations; rewritten legal/stakeholder wording. No claim about underlying ESG risk.
- Personal-data old 21 -> new 20, mutual modified: heading expands collection/use/protection/transfer; new online-safety and age-verification language. Removed the following Financial Risks category label from this body.
- Sales/margins old 22 -> new 21, mutual modified: heading changes from quarterly fluctuation to sales and gross-margin volatility. Candidate unmatched sentences require interpretation; they are not new/eliminated business risks.
- Stock old 27 -> new 26 remains mutual mostly unchanged, with minor Board-definition wording changes.
- Retail-store old 16 has a weak non-mutual nearest candidate (about .295) and remains candidate_removed. This does not prove elimination of retail risk. No candidate_new in this pair.
- Last risk ends before Item 1B; automated checks inspect every extracted body for section/footer contamination.

## Evaluation

`evaluation/annotations.json` contains actual full disclosure texts, filing years, identifiers, nullable human labels, machine proposals, notes and reviewed flags. Includes unchanged, wording/rewriting, apparent removal, ambiguous restructuring and a weakest-reverse-match addition review probe. That probe is deliberately NOT labeled as a real addition because this pair supplies no candidate_new. All human labels remain null and reviewed=false. Agent source inspection does not turn them into ground truth. `evaluate.py` recomputes risk predictions from the saved report, filters verified labels, and provides sample counts, per-class precision/recall/F1, confusion counts and paired match correctness only when reviewed annotations exist. Current result: zero verified samples; reliable accuracy metrics cannot be calculated. Annotation labels must use risk classification names; sentence-level labels need a separate future evaluation protocol.

## Reproduce

Use a working Python installation (the Windows Store `python` alias here did not work):

```
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q -m "not integration"
python -m pytest -q -m integration
python report.py
python evaluate.py
```

JSON report includes source filenames/hashes, filing dates/company, texts/raw bodies, matrices, both match directions, score gaps, classifications, sentence candidates and review blocks, plus algorithm configuration. It has no timestamps and is byte-stable for identical arguments/environment. Default command paths are relative to the working directory; run from project root or pass explicit paths. TF-IDF results may vary slightly across dependency versions.

No LLMs, embeddings, network service, frontend, commits, pushes or deployments introduced. Future embeddings could propose additional risk/sentence correspondences; future LLM explanations could cite selected source units, with these deterministic outputs retained as the baseline. Human annotation and broader issuer/year extraction validation should precede claims of performance.
