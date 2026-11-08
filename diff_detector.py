"""Deterministic sentence candidates; scores are diagnostics, not probabilities."""
import difflib
import re
from collections import defaultdict, deque
from extractor import clean_disclosure_text

# Conservative provisional gates, deliberately leave extensive rewriting for review.
SENTENCE_CONFIG = {"sequence_min": 0.65, "lexical_min": 0.35, "gap_min": 0.08}


def detect_text_changes(old_text, new_text):
    """Return word edits for already selected corresponding text units."""
    old, new = old_text.split(), new_text.split()
    result = {"added": [], "removed": [], "replaced": []}
    for op, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        left, right = " ".join(old[a:b]), " ".join(new[c:d])
        if op == "insert":
            result["added"].append(right)
        elif op == "delete":
            result["removed"].append(left)
        elif op == "replace":
            result["replaced"].append({"old": left, "new": right})
    return result


def sentence_similarity(old_sentence, new_sentence):
    """Character sequence ratio, with automatic junk filtering disabled."""
    return difflib.SequenceMatcher(None, old_sentence, new_sentence, autojunk=False).ratio()


def split_sentences(text):
    """Practical splitter protecting common abbreviations; not a full English parser."""
    text = re.sub(r"\r\n?", "\n", text.strip())
    if not text:
        return []
    # Protect internal and terminal abbreviation dots and decimal points.
    protected = re.sub(r"\b(?:U\.S\.|Inc\.|e\.g\.|i\.e\.|Mr\.|Dr\.)", lambda m: m[0].replace('.', '\ue000'), text)
    # A demonstrable Apple case: terminal U.S. followed by a new subject.
    protected = re.sub(r"(U\ue000S)\ue000(?=\s+(?:The Company|This|These|However)\b)", r"\1.", protected)
    protected = re.sub(r"(?<=\d)\.(?=\d)", '\ue000', protected)
    parts = re.split(r'(?<=[.!?])\s+|(?<=[.!?][”"\)])\s+|\n\s*(?:[•*]|[-] )\s*|\n\s*\n', protected)
    return [re.sub(r"\s+", " ", part.replace('\ue000', '.')).strip() for part in parts if part.strip()]


def _lexical(a, b):
    left, right = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(left & right) / len(left | right) if left | right else 0.0


def detect_sentence_changes(old_text, new_text):
    """Match exact occurrences globally; accept only isolated, mutual rewrite candidates.

    Unresolved two-sided text stays in review, including splits and condensations.
    Positions are zero-based indices of cleaned sentence-like segments.
    """
    old = split_sentences(clean_disclosure_text(old_text))
    new = split_sentences(clean_disclosure_text(new_text))
    result = {key: [] for key in ("exact_unchanged", "candidate_modified", "candidate_added", "candidate_removed", "needs_review")}
    occurrences = defaultdict(deque)
    for j, sentence in enumerate(new):
        occurrences[sentence].append(j)
    used_old, used_new = set(), set()
    for i, sentence in enumerate(old):
        if occurrences[sentence]:
            j = occurrences[sentence].popleft()
            used_old.add(i)
            used_new.add(j)
            result["exact_unchanged"].append({"old_index": i, "new_index": j, "text": sentence, "index_shift": j-i})
    remaining_old = [i for i in range(len(old)) if i not in used_old]
    remaining_new = [j for j in range(len(new)) if j not in used_new]
    scores = {(i,j): sentence_similarity(old[i], new[j]) for i in remaining_old for j in remaining_new}
    alternatives = []
    for i in remaining_old:
        ranked = sorted(remaining_new, key=lambda j: (-scores[i,j], j))
        alternatives.append({"old_index": i, "candidates": [{"new_index": j, "sequence_similarity": scores[i,j], "lexical_similarity": _lexical(old[i],new[j])} for j in ranked[:3]]})
        if not ranked:
            continue
        j = ranked[0]
        reverse = sorted(remaining_old, key=lambda k: (-scores[k,j], k))
        row_gap = scores[i,j] - scores[i,ranked[1]] if len(ranked)>1 else 1.0
        col_gap = scores[i,j] - scores[reverse[1],j] if len(reverse)>1 else 1.0
        # A plausible secondary edge can indicate a split/merge: keep it unresolved.
        competing = any(scores[i,k] >= SENTENCE_CONFIG['sequence_min'] for k in ranked[1:]) or any(scores[k,j] >= SENTENCE_CONFIG['sequence_min'] for k in reverse[1:])
        if reverse[0] == i and not competing and scores[i,j] >= SENTENCE_CONFIG['sequence_min'] and _lexical(old[i],new[j]) >= SENTENCE_CONFIG['lexical_min'] and min(row_gap,col_gap) >= SENTENCE_CONFIG['gap_min']:
            result['candidate_modified'].append({"old_index":i,"new_index":j,"old_text":old[i],"new_text":new[j],"sequence_similarity":scores[i,j],"lexical_similarity":_lexical(old[i],new[j]),"word_diff":detect_text_changes(old[i],new[j])})
            used_old.add(i)
            used_new.add(j)
    left = [i for i in remaining_old if i not in used_old]
    right = [j for j in remaining_new if j not in used_new]
    if left and right:
        result['needs_review'].append({"old_indices":left,"new_indices":right,"old_sentences":[old[i] for i in left],"new_sentences":[new[j] for j in right],"reason":"Unresolved rewriting, split/merge, or ambiguous correspondence", "alternatives": alternatives})
    else:
        result['candidate_removed'] = [{"old_index":i,"text":old[i]} for i in left]
        result['candidate_added'] = [{"new_index":j,"text":new[j]} for j in right]
    return result


def find_shifted_sentences(old_text, new_text):
    """Return index shifts; these do not establish genuine relocation."""
    return [match for match in detect_sentence_changes(old_text,new_text)['exact_unchanged'] if match['index_shift']]
