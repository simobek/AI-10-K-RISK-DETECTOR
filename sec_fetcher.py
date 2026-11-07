import os
import requests


def download_10k_filings(cik):
    padded_cik = str(cik).zfill(10)

    headers = {
        "User-Agent": "simobek simobek1333@gmail.com"
    }

    submissions_url = (
        f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    )

    response = requests.get(submissions_url, headers=headers)

    print("Submissions status:", response.status_code)

    if response.status_code != 200:
        print("Could not fetch submissions data.")
        return

    data = response.json()

    print("Company:", data["name"])

    recent = data["filings"]["recent"]

    for i in range(len(recent["form"])):
        if recent["form"][i] == "10-K":

            filing_date = recent["filingDate"][i]
            accession_number = recent["accessionNumber"][i]
            primary_document = recent["primaryDocument"][i]

            clean_accession_number = accession_number.replace("-", "")

            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik}/{clean_accession_number}/{primary_document}"
            )

            filename = f"10K_{filing_date}.html"

            if os.path.exists(filename):
                print("Already downloaded:", filename)
                continue

            print()
            print("10-K found")
            print("Date:", filing_date)
            print("Accession number:", accession_number)
            print("Primary document:", primary_document)
            print("URL:", filing_url)

            filing_response = requests.get(
                filing_url,
                headers=headers
            )

            print("HTML status:", filing_response.status_code)

            if filing_response.status_code == 200:
                with open(filename, "w", encoding="utf-8") as file:
                    file.write(filing_response.text)

                print("Saved:", filename)
            else:
                print("Could not download:", filename)


download_10k_filings(320193)