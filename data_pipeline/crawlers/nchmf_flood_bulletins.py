import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


BASE_ARCHIVE_URL = (
    "https://kttv.gov.vn/"
    "kttvsiteE/vi-VN/1/lu-ngap-lut-16-18.html"
)

RAW_DIR = "data/raw/nchmf"
PDF_DIR = os.path.join(RAW_DIR, "pdfs")
INDEX_OUTPUT = os.path.join(RAW_DIR, "index.csv")

# Initial collection range.
# We can expand this after checking the first collection.
START_PAGE = 1
END_PAGE = 10

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.3

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_archive_page(session, page_index):
    url = f"{BASE_ARCHIVE_URL}?pageindex={page_index}"

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    return url, response.text


def discover_bulletin_links(html):
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        title = anchor.get_text(" ", strip=True)

        if "post" not in href.lower():
            continue

        if "Chức năng nhiệm vụ" in title:
            continue

        absolute_url = urljoin(
            BASE_ARCHIVE_URL,
            href,
        )

        if absolute_url not in [
            item["bulletin_url"] for item in links
        ]:
            links.append(
                {
                    "title": title,
                    "bulletin_url": absolute_url,
                }
            )

    return links


def fetch_bulletin_page(session, bulletin_url):
    response = session.get(
        bulletin_url,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    return response.text


def extract_pdf_links(html, bulletin_url):
    soup = BeautifulSoup(html, "html.parser")

    pdf_links = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        absolute_url = urljoin(
            bulletin_url,
            href,
        )

        if ".pdf" in absolute_url.lower():
            if absolute_url not in pdf_links:
                pdf_links.append(absolute_url)

    return pdf_links


def infer_bulletin_datetime(title, text):
    combined = f"{title} {text}"

    patterns = [
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined)

        if not match:
            continue

        try:
            if len(match.groups()) == 2:
                return datetime.strptime(
                    f"{match.group(1)} {match.group(2)}",
                    "%d/%m/%Y %H:%M",
                )

            return datetime.strptime(
                match.group(1),
                "%d/%m/%Y",
            )

        except ValueError:
            continue

    return None


def extract_pdf_text(pdf_path):
    document = pymupdf.open(pdf_path)

    try:
        pages = []

        for page in document:
            pages.append(
                page.get_text("text")
            )

        return "\n".join(pages).strip()

    finally:
        document.close()


def make_safe_filename(pdf_url, index):
    parsed = urlparse(pdf_url)

    filename = os.path.basename(
        parsed.path
    )

    if not filename:
        filename = (
            f"nchmf_bulletin_{index:05d}.pdf"
        )

    filename = (
        filename
        .replace("/", "_")
        .replace("\\", "_")
    )

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def download_pdf(
    session,
    pdf_url,
    output_path,
):
    response = session.get(
        pdf_url,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    with open(output_path, "wb") as file:
        file.write(response.content)

    return (
        len(response.content),
        content_type,
    )


def load_existing_index():
    if not os.path.exists(INDEX_OUTPUT):
        return pd.DataFrame()

    try:
        return pd.read_csv(
            INDEX_OUTPUT
        )
    except Exception:
        return pd.DataFrame()


def save_index(records):
    if not records:
        return

    new_df = pd.DataFrame(records)

    existing_df = load_existing_index()

    if not existing_df.empty:
        combined = pd.concat(
            [
                existing_df,
                new_df,
            ],
            ignore_index=True,
        )
    else:
        combined = new_df

    if "pdf_url" in combined.columns:
        combined = combined.drop_duplicates(
            subset=["pdf_url"],
            keep="last",
        )

    combined.to_csv(
        INDEX_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )


def main():
    print("=" * 80)
    print("NCHMF FLOOD BULLETIN COLLECTOR")
    print("=" * 80)

    print(f"Archive : {BASE_ARCHIVE_URL}")
    print(
        f"Pages   : "
        f"{START_PAGE} -> {END_PAGE}"
    )
    print()

    os.makedirs(
        PDF_DIR,
        exist_ok=True,
    )

    session = get_session()

    records = []

    archive_pages_success = 0
    archive_pages_failed = 0

    bulletin_pages_success = 0
    bulletin_pages_failed = 0

    pdfs_found = 0
    pdfs_downloaded = 0
    pdfs_failed = 0

    discovered_bulletins = {}

    print("STEP 1: DISCOVERING BULLETINS")
    print("-" * 80)

    for page_index in range(
        START_PAGE,
        END_PAGE + 1,
    ):
        print(
            f"[Archive "
            f"{page_index}/{END_PAGE}]"
        )

        try:
            archive_url, html = (
                fetch_archive_page(
                    session,
                    page_index,
                )
            )

            archive_pages_success += 1

            links = discover_bulletin_links(
                html
            )

            print(
                f"    Bulletin links: "
                f"{len(links)}"
            )

            for item in links:
                discovered_bulletins[
                    item["bulletin_url"]
                ] = {
                    "title": item["title"],
                    "bulletin_url": item[
                        "bulletin_url"
                    ],
                    "archive_url": archive_url,
                    "archive_page": page_index,
                }

        except Exception as exc:
            archive_pages_failed += 1

            print(
                f"    ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        time.sleep(
            REQUEST_DELAY
        )

    print()
    print(
        "Unique bulletins discovered: "
        f"{len(discovered_bulletins)}"
    )
    print()

    print("STEP 2: FETCHING BULLETIN PAGES")
    print("-" * 80)

    total_bulletins = len(
        discovered_bulletins
    )

    for bulletin_number, item in enumerate(
        discovered_bulletins.values(),
        start=1,
    ):
        title = item["title"]
        bulletin_url = item[
            "bulletin_url"
        ]

        print(
            f"[Bulletin "
            f"{bulletin_number}/"
            f"{total_bulletins}]"
        )

        print(
            f"    {title[:120]}"
        )

        record = {
            "archive_page": item[
                "archive_page"
            ],
            "archive_url": item[
                "archive_url"
            ],
            "bulletin_url": bulletin_url,
            "bulletin_title": title,
            "bulletin_datetime": None,
            "pdf_url": None,
            "pdf_filename": None,
            "pdf_path": None,
            "pdf_size_bytes": None,
            "pdf_content_type": None,
            "download_status": (
                "not_attempted"
            ),
            "extraction_status": (
                "not_attempted"
            ),
            "text_length": 0,
            "full_text": "",
            "error": None,
            "collected_at": (
                datetime.now().isoformat()
            ),
        }

        try:
            bulletin_html = (
                fetch_bulletin_page(
                    session,
                    bulletin_url,
                )
            )

            bulletin_pages_success += 1

            soup = BeautifulSoup(
                bulletin_html,
                "html.parser",
            )

            page_text = soup.get_text(
                " ",
                strip=True,
            )

            bulletin_datetime = (
                infer_bulletin_datetime(
                    title,
                    page_text,
                )
            )

            if bulletin_datetime is not None:
                record[
                    "bulletin_datetime"
                ] = bulletin_datetime.isoformat()

            pdf_links = extract_pdf_links(
                bulletin_html,
                bulletin_url,
            )

            if not pdf_links:
                record[
                    "download_status"
                ] = "no_pdf_found"

                records.append(record)

                print(
                    "    PDF: NOT FOUND"
                )

                time.sleep(
                    REQUEST_DELAY
                )

                continue

            pdf_url = pdf_links[0]

            record["pdf_url"] = pdf_url

            pdf_filename = (
                make_safe_filename(
                    pdf_url,
                    bulletin_number,
                )
            )

            pdf_path = os.path.join(
                PDF_DIR,
                pdf_filename,
            )

            record[
                "pdf_filename"
            ] = pdf_filename

            record[
                "pdf_path"
            ] = pdf_path

            pdfs_found += 1

            if os.path.exists(
                pdf_path
            ):
                print(
                    "    PDF: "
                    "already downloaded"
                )

                record[
                    "download_status"
                ] = "already_exists"

                record[
                    "pdf_size_bytes"
                ] = os.path.getsize(
                    pdf_path
                )

            else:
                try:
                    (
                        size,
                        content_type,
                    ) = download_pdf(
                        session,
                        pdf_url,
                        pdf_path,
                    )

                    record[
                        "pdf_size_bytes"
                    ] = size

                    record[
                        "pdf_content_type"
                    ] = content_type

                    record[
                        "download_status"
                    ] = "downloaded"

                    pdfs_downloaded += 1

                    print(
                        "    PDF: "
                        f"downloaded "
                        f"({size:,} bytes)"
                    )

                except Exception as exc:
                    pdfs_failed += 1

                    record[
                        "download_status"
                    ] = "failed"

                    record["error"] = (
                        "PDF download: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    print(
                        "    PDF ERROR: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    records.append(
                        record
                    )

                    time.sleep(
                        REQUEST_DELAY
                    )

                    continue

            if os.path.exists(
                pdf_path
            ):
                try:
                    text = extract_pdf_text(
                        pdf_path
                    )

                    record[
                        "full_text"
                    ] = text

                    record[
                        "text_length"
                    ] = len(text)

                    record[
                        "extraction_status"
                    ] = "success"

                    if not record[
                        "bulletin_datetime"
                    ]:
                        extracted_datetime = (
                            infer_bulletin_datetime(
                                title,
                                text,
                            )
                        )

                        if (
                            extracted_datetime
                            is not None
                        ):
                            record[
                                "bulletin_datetime"
                            ] = (
                                extracted_datetime.isoformat()
                            )

                    print(
                        "    Text: "
                        f"{len(text):,} "
                        "characters"
                    )

                except Exception as exc:
                    record[
                        "extraction_status"
                    ] = "failed"

                    record["error"] = (
                        "PDF extraction: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    print(
                        "    TEXT ERROR: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

            records.append(record)

        except Exception as exc:
            bulletin_pages_failed += 1

            record[
                "download_status"
            ] = "bulletin_page_failed"

            record["error"] = (
                "Bulletin page: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            records.append(record)

            print(
                "    PAGE ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        time.sleep(
            REQUEST_DELAY
        )

    print()

    save_index(records)

    print("=" * 80)
    print("NCHMF COLLECTION COMPLETE")
    print("=" * 80)

    print(
        "Archive pages successful : "
        f"{archive_pages_success}"
    )

    print(
        "Archive pages failed     : "
        f"{archive_pages_failed}"
    )

    print(
        "Bulletin pages successful: "
        f"{bulletin_pages_success}"
    )

    print(
        "Bulletin pages failed    : "
        f"{bulletin_pages_failed}"
    )

    print(
        "Unique bulletins         : "
        f"{len(discovered_bulletins)}"
    )

    print(
        "PDF links found          : "
        f"{pdfs_found}"
    )

    print(
        "PDFs newly downloaded    : "
        f"{pdfs_downloaded}"
    )

    print(
        "PDF downloads failed     : "
        f"{pdfs_failed}"
    )

    print()

    print(
        f"PDF directory : {PDF_DIR}"
    )

    print(
        f"Index file    : {INDEX_OUTPUT}"
    )

    print()

    if os.path.exists(
        INDEX_OUTPUT
    ):
        index_df = pd.read_csv(
            INDEX_OUTPUT
        )

        print("INDEX SUMMARY")
        print("-" * 80)

        print(
            f"Rows              : "
            f"{len(index_df)}"
        )

        if (
            "download_status"
            in index_df.columns
        ):
            print(
                "Download statuses:"
            )

            print(
                index_df[
                    "download_status"
                ]
                .value_counts()
                .to_string()
            )

        if (
            "extraction_status"
            in index_df.columns
        ):
            print(
                "Extraction statuses:"
            )

            print(
                index_df[
                    "extraction_status"
                ]
                .value_counts()
                .to_string()
            )

        if (
            "bulletin_datetime"
            in index_df.columns
        ):
            dates = pd.to_datetime(
                index_df[
                    "bulletin_datetime"
                ],
                errors="coerce",
            ).dropna()

            if not dates.empty:
                print(
                    "Bulletin date range : "
                    f"{dates.min()} -> "
                    f"{dates.max()}"
                )

    print()

    print("=" * 80)
    print("RAW NCHMF DATA PRESERVED")
    print("=" * 80)


if __name__ == "__main__":
    main()