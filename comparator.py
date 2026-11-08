
from pathlib import Path

from extractor import extract_risk_units

from diff_detector import (
    detect_text_changes,
    split_sentences,
    detect_sentence_changes,
    find_shifted_sentences,
    sentence_similarity
)

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# --------------------------------------------------
# 1. CLASSIFICATION
# --------------------------------------------------

def classify_forward_match(match):

    score = match["score"]
    mutual = match["mutual"]

    if not mutual and score < 0.50:
        return "candidate_removed"

    if mutual and score >= 0.90:
        return "mostly_unchanged"

    if mutual and score >= 0.60:
        return "modified"

    return "needs_review"


def classify_reverse_match(match):

    score = match["score"]
    mutual = match["mutual"]

    if not mutual and score < 0.50:
        return "candidate_new"

    if mutual and score >= 0.90:
        return "mostly_unchanged"

    if mutual and score >= 0.60:
        return "modified"

    return "needs_review"


# --------------------------------------------------
# 2. TF-IDF SIMILARITY
# --------------------------------------------------

def build_similarity_matrix(texts_old, texts_new):

    if not texts_old or not texts_new:
        raise ValueError(
            "Cannot compare filings: one or both "
            "risk lists are empty."
        )

    all_texts = texts_old + texts_new

    vectorizer = TfidfVectorizer()

    try:
        tfidf_matrix = vectorizer.fit_transform(all_texts)

    except ValueError as error:
        raise ValueError(
            "Cannot build TF-IDF matrix: "
            "no usable vocabulary."
        ) from error

    n_old = len(texts_old)

    tfidf_old = tfidf_matrix[:n_old]
    tfidf_new = tfidf_matrix[n_old:]

    return cosine_similarity(
        tfidf_old,
        tfidf_new
    )


# --------------------------------------------------
# 3. BEST AND SECOND-BEST CANDIDATES
# --------------------------------------------------

def get_best_candidates(scores):
    """
    Find the highest and second-highest similarity
    scores in a row or column.

    Score gaps are diagnostics, not probabilities.
    """

    if len(scores) == 0:
        raise ValueError("Candidate scores cannot be empty")
    ranked_indices = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))

    best_index = int(ranked_indices[0])
    best_score = float(scores[best_index])

    second_index = None
    second_score = None
    score_gap = None

    if len(ranked_indices) > 1:

        second_index = int(ranked_indices[1])
        second_score = float(scores[second_index])

        score_gap = best_score - second_score

    return {
        "best_index": best_index,
        "best_score": best_score,
        "second_best_index": second_index,
        "second_best_score": second_score,
        "score_gap": score_gap
    }


# --------------------------------------------------
# 4. COMPARE TWO YEARS
# --------------------------------------------------

def compare_years(file_old, file_new, *, verbose=False):

    # Extract disclosures
    risks_old = extract_risk_units(file_old)
    risks_new = extract_risk_units(file_new)

    if not risks_old or not risks_new:
        raise ValueError(
            "Comparison stopped: extraction returned "
            "no risks for at least one filing."
        )

    if verbose:
        print("Old year risks:", len(risks_old))
    if verbose:
        print("New year risks:", len(risks_new))

    # ----------------------------------------------
    # Prepare texts
    # ----------------------------------------------

    full_texts_old = [
        risk["full_text"] for risk in risks_old
    ]

    full_texts_new = [
        risk["full_text"] for risk in risks_new
    ]

    headings_old = [
        risk["heading"] for risk in risks_old
    ]

    headings_new = [
        risk["heading"] for risk in risks_new
    ]

    bodies_old = [
        risk["body"] for risk in risks_old
    ]

    bodies_new = [
        risk["body"] for risk in risks_new
    ]

    # ----------------------------------------------
    # Build similarity matrices
    # ----------------------------------------------

    full_similarities = build_similarity_matrix(
        full_texts_old,
        full_texts_new
    )

    heading_similarities = build_similarity_matrix(
        headings_old,
        headings_new
    )

    body_similarities = build_similarity_matrix(
        bodies_old,
        bodies_new
    )

    # ----------------------------------------------
    # Old -> New matches
    # ----------------------------------------------

    matches_old_to_new = []

    for i in range(len(risks_old)):

        candidates = get_best_candidates(
            full_similarities[i]
        )

        j = candidates["best_index"]

        matches_old_to_new.append({
            "direction": "old_to_new",

            "index_old": i,
            "index_new": j,

            "risk_old": risks_old[i],
            "risk_new": risks_new[j],

            "score": candidates["best_score"],

            "heading_score": float(
                heading_similarities[i][j]
            ),

            "body_score": float(
                body_similarities[i][j]
            ),

            "second_best_index":
                candidates["second_best_index"],

            "second_best_score":
                candidates["second_best_score"],

            "score_gap": candidates["score_gap"]
        })

    # ----------------------------------------------
    # New -> Old matches
    # ----------------------------------------------

    matches_new_to_old = []

    for j in range(len(risks_new)):

        candidates = get_best_candidates(
            full_similarities[:, j]
        )

        i = candidates["best_index"]

        matches_new_to_old.append({
            "direction": "new_to_old",

            "index_new": j,
            "index_old": i,

            "risk_new": risks_new[j],
            "risk_old": risks_old[i],

            "score": candidates["best_score"],

            "heading_score": float(
                heading_similarities[i][j]
            ),

            "body_score": float(
                body_similarities[i][j]
            ),

            "second_best_index":
                candidates["second_best_index"],

            "second_best_score":
                candidates["second_best_score"],

            "score_gap": candidates["score_gap"]
        })

    # ----------------------------------------------
    # Mutual matching
    # ----------------------------------------------

    for match in matches_old_to_new:

        i = match["index_old"]
        j = match["index_new"]

        reverse_match = matches_new_to_old[j]

        match["mutual"] = (
            reverse_match["index_old"] == i
        )

    for match in matches_new_to_old:

        i = match["index_old"]
        j = match["index_new"]

        forward_match = matches_old_to_new[i]

        match["mutual"] = (
            forward_match["index_new"] == j
        )

    # ----------------------------------------------
    # Classification
    # ----------------------------------------------

    for match in matches_old_to_new:
        match["classification"] = classify_forward_match(
            match
        )

    for match in matches_new_to_old:
        match["classification"] = classify_reverse_match(
            match
        )

    # ----------------------------------------------
    # Aggregate categories
    # ----------------------------------------------

    # Exact ties have no unique best match, even when argmax is reciprocal.
    for matches in (matches_old_to_new, matches_new_to_old):
        for match in matches:
            if match["score_gap"] is not None and match["score_gap"] <= 1e-12:
                match["classification"] = "needs_review"
    mostly_unchanged = [m for m in matches_old_to_new if m["classification"] == "mostly_unchanged"]
    modified = [m for m in matches_old_to_new if m["classification"] == "modified"]
    removed = [m for m in matches_old_to_new if m["classification"] == "candidate_removed"]
    new = [m for m in matches_new_to_old if m["classification"] == "candidate_new"]
    needs_review = [m for m in matches_old_to_new if m["classification"] == "needs_review"]
    seen = {(m["index_old"], m["index_new"]) for m in needs_review}
    needs_review += [m for m in matches_new_to_old if m["classification"] == "needs_review" and (m["index_old"],m["index_new"]) not in seen]

    return {
        "file_old": str(file_old),
        "file_new": str(file_new),

        "risks_old": risks_old,
        "risks_new": risks_new,

        "full_similarities": full_similarities,
        "heading_similarities": heading_similarities,
        "body_similarities": body_similarities,

        "matches_old_to_new": matches_old_to_new,
        "matches_new_to_old": matches_new_to_old,

        "mostly_unchanged": mostly_unchanged,
        "modified": modified,
        "removed": removed,
        "new": new,
        "needs_review": needs_review
    }


# --------------------------------------------------
# 5. PRINT COMPARISON RESULTS
# --------------------------------------------------

def print_results(results):

    print("\n========== SUMMARY ==========")

    print(
        "Mostly unchanged:",
        len(results["mostly_unchanged"])
    )

    print(
        "Modified:",
        len(results["modified"])
    )

    print(
        "Candidate removed:",
        len(results["removed"])
    )

    print(
        "Candidate new:",
        len(results["new"])
    )

    print(
        "Needs review:",
        len(results["needs_review"])
    )

    print("\n========== MODIFIED ==========")

    for match in results["modified"]:

        print()
        print("Old:", match["risk_old"]["heading"])
        print("New:", match["risk_new"]["heading"])

        print(
            "Full score:",
            round(match["score"], 3)
        )

        print(
            "Heading score:",
            round(match["heading_score"], 3)
        )

        print(
            "Body score:",
            round(match["body_score"], 3)
        )

        print(
            "Score gap:",
            round(match["score_gap"], 3)
            if match["score_gap"] is not None
            else "N/A"
        )

    print("\n========== CANDIDATE REMOVED ==========")

    for match in results["removed"]:

        print()
        print("Old:", match["risk_old"]["heading"])
        print("Best new:", match["risk_new"]["heading"])
        print("Full score:", round(match["score"], 3))
        print("Mutual:", match["mutual"])

    print("\n========== CANDIDATE NEW ==========")

    for match in results["new"]:

        print()
        print("New:", match["risk_new"]["heading"])
        print("Best old:", match["risk_old"]["heading"])
        print("Full score:", round(match["score"], 3))
        print("Mutual:", match["mutual"])

    print("\n========== NEEDS REVIEW ==========")

    for match in results["needs_review"]:

        print()
        print("Direction:", match["direction"])
        print("Old:", match["risk_old"]["heading"])
        print("New:", match["risk_new"]["heading"])
        print("Full score:", round(match["score"], 3))
        print("Mutual:", match["mutual"])

        print(
            "Score gap:",
            round(match["score_gap"], 3)
            if match["score_gap"] is not None
            else "N/A"
        )

    print("\n========== LAST OLD-YEAR RISK ==========")

    last_index = len(results["risks_old"]) - 1

    last_match = results["matches_old_to_new"][last_index]

    print("Old:", last_match["risk_old"]["heading"])
    print("New:", last_match["risk_new"]["heading"])

    print(
        "Full score:",
        round(last_match["score"], 3)
    )

    print(
        "Heading score:",
        round(last_match["heading_score"], 3)
    )

    print(
        "Body score:",
        round(last_match["body_score"], 3)
    )

    print("Mutual:", last_match["mutual"])
    print("Classification:", last_match["classification"])


# --------------------------------------------------
# 6. DIFF DIAGNOSTICS
# --------------------------------------------------

def print_diff_diagnostics(results):

    if not results["modified"]:
        print("\nNo modified matches to inspect.")
        return

    match = results["modified"][0]

    old_body = match["risk_old"]["body"]
    new_body = match["risk_new"]["body"]

    print("\n========== TEXTUAL CHANGES ==========")
    print("Risk:", match["risk_old"]["heading"])

    print("\nOld body length:", len(old_body))
    print("New body length:", len(new_body))

    print("\nOld body ending:", old_body[-250:])
    print("\nNew body ending:", new_body[-250:])

    # ----------------------------------------------
    # Word-level changes
    # ----------------------------------------------

    changes = detect_text_changes(
        old_body,
        new_body
    )

    print("\nADDED:")
    for passage in changes["added"]:
        print("+", passage[:300])

    print("\nREMOVED:")
    for passage in changes["removed"]:
        print("-", passage[:300])

    print("\nREPLACED:")
    for change in changes["replaced"]:
        print("Old:", change["old"][:300])
        print("New:", change["new"][:300])
        print()

    # ----------------------------------------------
    # Sentence splitting
    # ----------------------------------------------

    print(
        "\n========== SENTENCE SPLITTING EXPERIMENT =========="
    )

    old_sentences = split_sentences(old_body)
    new_sentences = split_sentences(new_body)

    print("2024 sentence-like segments:", len(old_sentences))
    print("2025 sentence-like segments:", len(new_sentences))

    print(
        "\nFirst 2024 segment:",
        old_sentences[0] if old_sentences else "N/A"
    )

    print(
        "\nFirst 2025 segment:",
        new_sentences[0] if new_sentences else "N/A"
    )

    print(
        "\nNOTE: The regex may split abbreviations "
        "such as U.S. incorrectly."
    )

    # ----------------------------------------------
    # Structured sentence-level changes
    # ----------------------------------------------

    print("\n========== SENTENCE-LEVEL CHANGES ==========")

    sentence_changes = detect_sentence_changes(
        old_body,
        new_body
    )

    print(
        "Exact unchanged:",
        len(sentence_changes["exact_unchanged"])
    )

    print(
        "Candidate added:",
        len(sentence_changes["candidate_added"])
    )

    print(
        "Candidate removed:",
        len(sentence_changes["candidate_removed"])
    )

    print(
        "Replacement blocks needing review:",
        len(sentence_changes["needs_review"])
    )

    for block in sentence_changes["needs_review"]:

        print()
        print("Old sentences:", len(block["old_sentences"]))
        print("New sentences:", len(block["new_sentences"]))
        print("Reason:", block["reason"])

    # ----------------------------------------------
    # Index-shift diagnostic
    # ----------------------------------------------

    print("\n========== INDEX SHIFTS ==========")

    find_shifted_sentences(
        old_body,
        new_body
    )

    # ----------------------------------------------
    # Unresolved one-to-one sentence-pair similarity experiment
    # ----------------------------------------------

    print("\n========== SENTENCE PAIR SCORES ==========")

    for block in sentence_changes["needs_review"]:

        old_block = block["old_sentences"]
        new_block = block["new_sentences"]

        if len(old_block) == 1 and len(new_block) == 1:

            score = sentence_similarity(
                old_block[0],
                new_block[0]
            )

            print("\nOld:", old_block[0][:180])
            print("New:", new_block[0][:180])
            print("Sequence similarity:", round(score, 3))

def analyze_all_modified_sentences(results):

    print("\n========== ALL MODIFIED RISK SENTENCE SCORES ==========")

    total_pairs = 0
    all_scores = []

    for risk_number, match in enumerate(results["modified"], start=1):

        old_body = match["risk_old"]["body"]
        new_body = match["risk_new"]["body"]

        sentence_changes = detect_sentence_changes(
            old_body,
            new_body
        )

        print("\n" + "=" * 60)
        print("RISK:", risk_number)
        print("HEADING:", match["risk_old"]["heading"])

        print(
            "Replacement blocks:",
            len(sentence_changes["needs_review"])
        )

        for block in sentence_changes["needs_review"]:

            old_sentences = block["old_sentences"]
            new_sentences = block["new_sentences"]

            # One-to-one blocks may still be semantically ambiguous.
            if len(old_sentences) != 1 or len(new_sentences) != 1:
                continue

            old_sentence = old_sentences[0]
            new_sentence = new_sentences[0]

            score = sentence_similarity(
                old_sentence,
                new_sentence
            )

            total_pairs += 1
            all_scores.append(score)

            print("\n--- SENTENCE PAIR ---")

            print("Old:", old_sentence)
            print("New:", new_sentence)
            print("Similarity:", round(score, 3))

    print("\n========== OVERALL SENTENCE SCORE SUMMARY ==========")

    print("One-to-one replacement pairs:", total_pairs)

    if all_scores:
        print("Minimum similarity:", round(min(all_scores), 3))
        print("Maximum similarity:", round(max(all_scores), 3))
        print(
            "Average similarity:",
            round(sum(all_scores) / len(all_scores), 3)
        )
    else:
        print("No one-to-one replacement pairs were found.")
# --------------------------------------------------
# 7. MAIN
# --------------------------------------------------

if __name__ == "__main__":

    project_dir = Path(__file__).resolve().parent

    file_old = project_dir / "10K_2024-11-01.html"
    file_new = project_dir / "10K_2025-10-31.html"

    results = compare_years(
        file_old,
        file_new
    )

    print_results(results)

    print_diff_diagnostics(results)

    analyze_all_modified_sentences(results)