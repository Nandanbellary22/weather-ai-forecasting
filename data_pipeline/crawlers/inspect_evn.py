import requests
import pandas as pd
from io import StringIO


URL = "https://hochuathuydien.evn.com.vn/PageHoChuaThuyDienEmbedEVN.aspx"


def main():
    print("=" * 80)
    print("EVN RESERVOIR EMBEDDED DATA INSPECTION")
    print("=" * 80)

    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    print(f"HTTP status   : {response.status_code}")
    print(f"Content-Type  : {response.headers.get('content-type')}")
    print(f"Response size : {len(response.content):,} bytes")

    response.raise_for_status()

    print("\n" + "-" * 80)
    print("EXTRACTING HTML TABLE")
    print("-" * 80)

    tables = pd.read_html(StringIO(response.text))

    print(f"Number of tables: {len(tables)}")

    if not tables:
        print("No HTML table found.")
        return

    df = tables[0]

    print(f"Raw shape: {df.shape}")

    print("\n" + "-" * 80)
    print("RAW COLUMNS")
    print("-" * 80)

    for i, column in enumerate(df.columns):
        print(f"{i}: {column}")

    print("\n" + "-" * 80)
    print("RAW DATA")
    print("-" * 80)

    print(df.to_string(index=True))

    print("\n" + "-" * 80)
    print("DATA TYPES")
    print("-" * 80)

    print(df.dtypes)

    print("\n" + "-" * 80)
    print("MISSING VALUES")
    print("-" * 80)

    print(df.isna().sum())

    print("\n" + "-" * 80)
    print("FIRST COLUMN VALUES")
    print("-" * 80)

    print(df.iloc[:, 0].to_string(index=False))


if __name__ == "__main__":
    main()