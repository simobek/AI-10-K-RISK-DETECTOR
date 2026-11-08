
import re
from pathlib import Path

from bs4 import BeautifulSoup


def clean_disclosure_text(text):
    """Remove narrowly identified SEC page furniture and normalize whitespace."""
    text = re.sub(r"(?:Apple Inc\.\s*)?\|\s*20\d{2}\s+Form\s+10-K\s*\|\s*\d+\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------
# 1. LOCATE ITEM 1A
# --------------------------------------------------

def load_item_1a(filename):
    """
    Locate the Item 1A section of an SEC 10-K.

    Keep HTML text-node positions so that risk
    segmentation can preserve the original styling.
    """

    filename = Path(filename)

    if not filename.is_file():
        raise FileNotFoundError(
            f"Filing not found: {filename.resolve()}"
        )

    with open(filename, "r", encoding="utf-8") as file:
        content = file.read()

    soup = BeautifulSoup(content, "html.parser")

    nodes = list(soup.strings)

    node_positions = {}
    chunks = []
    offset = 0

    for node in nodes:

        node_text = str(node)

        node_positions[id(node)] = (
            offset,
            offset + len(node_text)
        )

        chunks.append(node_text)

        offset += len(node_text) + 1

    text = "\n".join(chunks)

    pattern_1a = r"item\s+1a\.?\s+risk\s+factors"
    pattern_1b = (
        r"item\s+1b\.?\s+unresolved\s+"
        r"staff\s+comments"
    )

    matches_1a = list(
        re.finditer(pattern_1a, text, re.IGNORECASE)
    )

    matches_1b = list(
        re.finditer(pattern_1b, text, re.IGNORECASE)
    )

    candidate_sections = []

    for match_1a in matches_1a:

        for match_1b in matches_1b:

            if match_1b.start() > match_1a.start():

                # Reject a TOC occurrence spanning a later real Item 1A.
                if any(match_1a.start() < other.start() < match_1b.start()
                       for other in matches_1a):
                    break
                start = match_1a.start()
                end = match_1b.start()

                candidate_sections.append(
                    (start, end, end - start)
                )

                break

    if not candidate_sections:
        raise ValueError(
            f"Could not locate Item 1A boundaries: {filename}"
        )

    # Provisional heuristic: longest candidate section.
    best_section = max(
        candidate_sections,
        key=lambda section: section[2]
    )

    start, end, _ = best_section

    return soup, text, start, end, node_positions


# --------------------------------------------------
# 2. EXTRACT ITEM 1A PLAIN TEXT
# --------------------------------------------------

def extract_item_1A(filename):
    """
    Return the text belonging to Item 1A.
    """

    _, text, start, end, _ = load_item_1a(filename)

    risk_factors = text[start:end]

    risk_factors = re.sub(
        r"\n\s*\n+",
        "\n",
        risk_factors
    )

    return clean_disclosure_text(risk_factors)


# --------------------------------------------------
# 3. IDENTIFY APPLE RISK HEADINGS
# --------------------------------------------------

def is_risk_heading(tag):
    """
    Detect the Apple-specific bold/italic styling
    currently used by the risk segmentation prototype.
    """

    style = tag.get("style", "")

    normalized_style = re.sub(r"\s+", "", style).lower()

    return (
        "font-weight:700" in normalized_style
        and "font-style:italic" in normalized_style
    )


# --------------------------------------------------
# 4. EXTRACT INDIVIDUAL RISK DISCLOSURES
# --------------------------------------------------

def extract_risk_units(filename):
    """
    Extract individual risks strictly within Item 1A.

    Returns dictionaries containing:
        heading
        body
        full_text

    Raises ValueError if the filing's formatting
    cannot be segmented by the current heuristic.
    """

    soup, _, start, end, node_positions = load_item_1a(
        filename
    )

    risks = []
    current_heading = None
    current_body = []
    source_nodes = []

    def save_risk():
        if current_heading is None:
            return
        raw_body = " ".join(current_body)
        body = clean_disclosure_text(raw_body)
        if not body:
            raise ValueError(f"Empty body for risk: {current_heading}")
        heading = clean_disclosure_text(current_heading)
        risks.append({"heading": heading, "body": body,
                      "full_text": heading + " " + body,
                      "raw_body": raw_body, "source_file": str(filename),
                      "source_text_range": [min(source_nodes), max(source_nodes)]})

    # Visit text nodes once: nested spans must not duplicate disclosure text.
    active_heading_tag = None
    for node in soup.strings:
        left, right = node_positions[id(node)]
        if left < start or right > end or not str(node).strip():
            continue
        heading_tag = next((parent for parent in node.parents
                            if parent.name == "span" and is_risk_heading(parent)), None)
        if heading_tag is not None:
            if heading_tag is not active_heading_tag:
                save_risk()
                current_heading = heading_tag.get_text(" ", strip=True)
                current_body = []
                source_nodes = [left, right]
                active_heading_tag = heading_tag
        elif current_heading is not None:
            # Apple category headings are navigation between risks, not body text.
            category_names = {"Financial Risks", "Business Risks",
                              "Legal and Regulatory Compliance Risks",
                              "Macroeconomic and Industry Risks"}
            if str(node).strip() in category_names and any(
                parent.name == "span" and "font-weight:700" in re.sub(r"\s+", "", parent.get("style", ""))
                for parent in node.parents
            ):
                continue
            current_body.append(str(node))
            source_nodes.extend([left, right])
    save_risk()

    if not risks:
        raise ValueError(
            "Risk segmentation failed or the filing "
            f"uses unsupported HTML formatting: {filename}"
        )

    return risks


# --------------------------------------------------
# 5. VERIFY EXTRACTION
# --------------------------------------------------

def verify_extraction(filename, year):

    risks = extract_risk_units(filename)

    print(f"\n{'=' * 50}")
    print(f"APPLE {year}")
    print(f"{'=' * 50}")

    print("File:", filename)
    print("Number of risks:", len(risks))

    first_risk = risks[0]
    last_risk = risks[-1]

    print("\nFIRST RISK")
    print("Heading:", first_risk["heading"])
    print("Body length:", len(first_risk["body"]))
    print("Body beginning:", first_risk["body"][:300])

    print("\nLAST RISK")
    print("Heading:", last_risk["heading"])
    print("Body length:", len(last_risk["body"]))
    print("Body ending:", last_risk["body"][-500:])

    # Check every risk, not just the final one.
    contaminated = []

    for index, risk in enumerate(risks):

        body = risk["body"].lower()

        contains_item_1b = bool(
            re.search(
                r"item\s+1b\b",
                body
            )
        )

        contains_signatures = bool(
            re.search(
                r"\bsignatures\b",
                body
            )
        )

        if contains_item_1b or contains_signatures:
            contaminated.append(index)

    print("\nBOUNDARY CHECKS")

    print(
        "Last body contains Item 1B:",
        bool(re.search(
            r"item\s+1b\b",
            last_risk["body"],
            re.IGNORECASE
        ))
    )

    print(
        "Last body contains signatures:",
        "signatures" in last_risk["body"].lower()
    )

    print("Risks flagged for contamination:", contaminated)

    if contaminated:
        print("WARNING: Inspect flagged risk bodies.")
    else:
        print(
            "No obvious boundary markers found. "
            "Manual boundary inspection is still needed."
        )


# --------------------------------------------------
# 6. MAIN
# --------------------------------------------------

if __name__ == "__main__":

    project_dir = Path(__file__).resolve().parent

    filenames = {
        2024: project_dir / "10K_2024-11-01.html",
        2025: project_dir / "10K_2025-10-31.html"
    }

    for year, filename in filenames.items():

        try:
            verify_extraction(filename, year)

        except (ValueError, FileNotFoundError) as error:
            print(f"\nERROR extracting {year}: {error}")
