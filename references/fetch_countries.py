import json
import urllib.request


def get_flag_emoji(country_code):
    return ''.join(chr(ord(c) + 127397) for c in country_code.upper())


def fetch_and_generate():
    url = "https://raw.githubusercontent.com/mledoze/countries/master/dist/countries.json"
    print("Fetching countries from raw github mledoze/countries...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

    import ssl
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, context=context, timeout=15) as response:
            countries_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Failed to fetch countries: {e}")
        return

    result = []
    for item in countries_data:
        iso = item.get("cca2", "")
        if not iso:
            continue

        # Get Russian name
        translations = item.get("translations", {})
        rus = translations.get("rus", {})
        country_name = rus.get("common") or rus.get("official") or item.get("name", {}).get("common")

        # Get Dial Code
        idd = item.get("idd", {})
        root = idd.get("root", "")
        suffixes = idd.get("suffixes", [])

        # Construct full dial code
        if root:
            if len(suffixes) == 1:
                dial_code = f"{root}{suffixes[0]}"
            elif len(suffixes) > 1:
                # If there are multiple suffixes (e.g. USA has many suffixes for territories, but root is +1)
                # We can just use root, or if root is +1, or root+suffix
                if root == "+1":
                    dial_code = "+1"
                else:
                    dial_code = f"{root}{suffixes[0]}"
            else:
                dial_code = root
        else:
            continue

        flag = item.get("flag") or get_flag_emoji(iso)

        result.append({
            "code": dial_code,
            "country": country_name,
            "flag": flag,
            "iso": iso
        })

    # Sort countries by Russian name
    result = sorted(result, key=lambda x: x["country"])

    output_path = "references/country_codes.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {len(result)} countries in {output_path}")


if __name__ == "__main__":
    fetch_and_generate()
