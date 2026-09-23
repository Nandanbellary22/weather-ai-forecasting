import requests
import json


URL = "https://pctt.danang.gov.vn/DesktopModules/PCTT/api/PCTTApi/baocaothuydiens_thongke"

PARAMS = {
    "ngaybatdau": "2026-07-13T00:00:00+07:00",
    "ngayketthuc": "2026-07-13T23:59:59+07:00",
    "lst_thuydien_id": "1,2,3,4",
}


def main():

    print("=" * 80)
    print("DA NANG PCTT API INSPECTION")
    print("=" * 80)

    print(f"URL: {URL}")
    print()

    try:

        response = requests.get(
            URL,
            params=PARAMS,
            timeout=30,
        )

        print(f"HTTP status : {response.status_code}")
        print(
            f"Content-Type: "
            f"{response.headers.get('Content-Type')}"
        )

        print()
        print("Final URL:")
        print(response.url)

        print()
        print("Response length:")
        print(len(response.text))

        print()
        print("RAW RESPONSE:")
        print("-" * 80)
        print(response.text[:10000])
        print("-" * 80)

        # Try JSON parsing.
        try:

            data = response.json()

            print()
            print("JSON PARSING: SUCCESS")

            print()
            print("Python type:")
            print(type(data))

            if isinstance(data, list):

                print(
                    f"Number of records: {len(data)}"
                )

                if len(data) > 0:

                    print()
                    print("First record:")

                    print(
                        json.dumps(
                            data[0],
                            indent=2,
                            ensure_ascii=False,
                        )
                    )

                    print()
                    print("First record fields:")

                    if isinstance(data[0], dict):

                        for key, value in data[0].items():

                            print(
                                f"  {key}: "
                                f"{value!r} "
                                f"({type(value).__name__})"
                            )

            elif isinstance(data, dict):

                print("Dictionary keys:")

                for key in data.keys():

                    print(f"  - {key}")

                print()
                print(
                    json.dumps(
                        data,
                        indent=2,
                        ensure_ascii=False,
                    )[:10000]
                )

        except Exception as e:

            print()
            print(
                "JSON PARSING FAILED:"
            )
            print(e)

    except Exception as e:

        print()
        print("REQUEST FAILED:")
        print(type(e).__name__)
        print(e)


if __name__ == "__main__":
    main()