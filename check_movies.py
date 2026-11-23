
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
MOVIES_FILE = BASE_DIR / "tracked-movies.json"
RESULTS_FILE = BASE_DIR / "results.json"

EXCLUDED_WORDS = [
    "трейлер",
    "тизер",
    "фрагмент",
    "отрывок",
    "интервью",
    "обзор",
    "рецензия",
    "making of",
    "behind the scenes",
    "teaser",
    "trailer",
    "clip",
    "interview",
    "review",
    "фильм о фильме"
]

def classify_result(title):
    text = title.lower()

    for word in EXCLUDED_WORDS:
        if word in text:
            return {
                "classification": "trailer_or_fragment",
                "status_label": "Трейлер или фрагмент — не подходит"
            }

    return {
        "classification": "unconfirmed",
        "status_label": "Не подтверждено — полный фильм не проверен"
    }

def check_movie(title):
    query = urllib.parse.quote('"' + title + '"')

    url = (
        "https://news.google.com/rss/search?q="
        + query
        + "&hl=ru&gl=RU&ceid=RU:ru"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 Kinoradar/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = []

        for item in root.findall(".//item")[:10]:
            result_title = item.findtext("title", "")
            classification = classify_result(result_title)

            items.append({
                "title": result_title,
                "link": item.findtext("link", ""),
                "date": item.findtext("pubDate", ""),
                "source": item.findtext("source", ""),
                "classification": classification["classification"],
                "status_label": classification["status_label"]
            })

        return {
            "movie": title,
            "status": "ok",
            "mentions": items
        }

    except Exception as error:
        return {
            "movie": title,
            "status": "error",
            "message": str(error),
            "mentions": []
        }

def main():
    with open(MOVIES_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    results = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "movies": []
    }

    for title in data.get("movies", []):
        print("Проверяю:", title)
        results["movies"].append(check_movie(title))

    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    print("Проверка завершена. Результаты записаны в results.json")

if __name__ == "__main__":
    main()
