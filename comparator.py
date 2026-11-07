
from pathlib import Path

from extractor import extract_risk_units

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
# 3. BEST AND SECOND-BEST MATCH
# --------------------------------------------------

def get_best_candidates(scores):
    """
    Find the highest and second-highest similarity
    scores in one row or column.

    The gap is a diagnostic, not a probability.
    """

    ranked_indices = scores.argsort()[::-1]

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

def compare_years(file_old, file_new):

    # Extract risks using the corrected extractor.
    risks_old = extract_risk_units(file_old)
    risks_new = extract_risk_units(file_new)

    if not risks_old or not risks_new:
        raise ValueError(
            "Comparison stopped: extraction returned "
            "no risks for at least one filing."
        )

    print("Old year risks:", len(risks_old))
    print("New year risks:", len(risks_new))

    # ----------------------------------------------
    # Prepare text
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
    # Three similarity matrices
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

    print(
        "Full-text similarity matrix:",
        full_similarities.shape
    )

    print(
        "Heading similarity matrix:",
        heading_similarities.shape
    )

    print(
        "Body similarity matrix:",
        body_similarities.shape
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
    # Classify matches
    # ----------------------------------------------

    for match in matches_old_to_new:

        match["classification"] = (
            classify_forward_match(match)
        )

    for match in matches_new_to_old:

        match["classification"] = (
            classify_reverse_match(match)
        )

    # ----------------------------------------------
    # Aggregate categories
    # ----------------------------------------------

    mostly_unchanged = []
    modified = []
    removed = []
    new = []
    needs_review = []

    for match in matches_old_to_new:

        classification = match["classification"]

        if classification == "mostly_unchanged":
            mostly_unchanged.append(match)

        elif classification == "modified":
            modified.append(match)

        elif classification == "candidate_removed":
            removed.append(match)

        elif classification == "needs_review":
            needs_review.append(match)

    for match in matches_new_to_old:

        classification = match["classification"]

        if classification == "candidate_new":
            new.append(match)

        elif classification == "needs_review":

            # Mutual pairs are already represented
            # by the forward-direction aggregation.
            if not match["mutual"]:
                needs_review.append(match)

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
# 5. REPORT RESULTS
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

        print("Full score:", round(match["score"], 3))

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

    # Inspect the final old-year risk explicitly.
    print("\n========== LAST OLD-YEAR RISK ==========")

    last_index = len(results["risks_old"]) - 1

    last_match = results["matches_old_to_new"][last_index]

    print("Old:", last_match["risk_old"]["heading"])
    print("New:", last_match["risk_new"]["heading"])

    print("Full score:", round(last_match["score"], 3))

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
# 6. MAIN
# --------------------------------------------------

if __name__ == "__main__":

    project_dir = Path(__file__).resolve().parent

    file_old = project_dir / "10K_2024-11-01.html"
    file_new = project_dir / "10K_2025-10-31.html"

    results = compare_years(file_old, file_new)

    print_results(results)
