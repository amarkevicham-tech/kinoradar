
import json
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
MOVIES_FILE = BASE_DIR / "tracked-movies.json"
RESULTS_FILE = BASE_DIR / "results.json"

EXCLUDED_WORDS = [
    "трейлер", "тизер", "фрагмент", "отрывок",
    "интервью", "обзор", "рецензия",
    "making of", "behind the scenes",
    "teaser", "trailer", "clip",
    "interview", "review", "фильм о фильме"
]

def classify_title(title):
    text = title.lower()

    for word in EXCLUDED_WORDS:
        if word in text:
            return "trailer_or_fragment"

    return "unconfirmed"


def parse_duration(value):
    if not value:
        return None

    value = value.strip()

    # Формат ISO 8601: PT1H30M, PT95M, PT2H
    match = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        value,
        re.IGNORECASE
    )

    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    # Формат 01:35:00 или 95:00
    parts = value.split(":")
    try:
        numbers = [int(part) for part in parts]
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
    except ValueError:
        pass

    return None


def check_page(url):
    result = {
        "page_status": "unknown",
        "page_title": "",
        "duration_seconds": None,
        "video_found": False,
        "page_message": "Не удалось проверить страницу."
    }

    try:
        parsed = urllib.parse.urlparse(url)

        if parsed.scheme not in ("http", "https"):
            result["page_message"] = "Неподдерживаемый адрес страницы."
            return result

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Kinoradar/1.0)"
            }
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")

            if "html" not in content_type.lower():
                result["page_message"] = (
                    "Страница не вернула обычный HTML-документ."
                )
                return result

            html = response.read(1500000).decode(
                "utf-8", errors="replace"
            )

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            re.IGNORECASE | re.DOTALL
        )

        if title_match:
            result["page_title"] = re.sub(
                r"\s+", " ", title_match.group(1)
            ).strip()

        duration_values = re.findall(
            r'(?:duration|contentDuration|video:duration)["\']?\s*'
            r'[:=]\s*["\']([^"\']+)',
            html,
            re.IGNORECASE
        )

        # Дополнительный поиск длительности в разметке страницы
        duration_values += re.findall(
            r'<meta[^>]+(?:itemprop|property)=["\']'
            r'(?:duration|video:duration)["\'][^>]+'
            r'content=["\']([^"\']+)',
            html,
            re.IGNORECASE
        )

        durations = [
            parse_duration(value)
            for value in duration_values
        ]
        durations = [value for value in durations if value]

        if durations:
            result["duration_seconds"] = max(durations)

        video_patterns = [
            r"<video\b",
            r"<iframe\b",
            r"VideoObject",
            r"video/mp4",
            r"youtube\.com/embed",
            r"player\.vimeo\.com"
        ]

        result["video_found"] = any(
            re.search(pattern, html, re.IGNORECASE)
            for pattern in video_patterns
        )

        result["page_status"] = "checked"

        if result["duration_seconds"] and result["video_found"]:
            result["page_message"] = (
                "Найдены признаки видео и сведения о длительности."
            )
        elif result["video_found"]:
            result["page_message"] = (
                "Найдены признаки видеоплеера, но длительность неизвестна."
            )
        else:
            result["page_message"] = (
                "Не удалось обнаружить явные признаки видеоплеера."
            )

    except Exception as error:
        result["page_message"] = (
            "Проверка страницы не удалась: " + str(error)[:200]
        )

    return result


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
            link = item.findtext("link", "")

            classification = classify_title(result_title)

            if classification == "trailer_or_fragment":
                page_info = {
                    "page_status": "not_checked",
                    "page_title": "",
                    "duration_seconds": None,
                    "video_found": False,
                    "page_message": "Публикация исключена по заголовку."
                }
                status_label = "Трейлер или фрагмент — не подходит"

            else:
                page_info = check_page(link)

                duration = page_info["duration_seconds"]

                if duration and duration >= 3600 and page_info["video_found"]:
                    classification = "possible_full"
                    status_label = (
                        "Возможно, полный фильм — нужна проверка"
                    )
                else:
                    classification = "unconfirmed"
                    status_label = (
                        "Не подтверждено — полный фильм не проверен"
                    )

            items.append({
                "title": result_title,
                "link": link,
                "date": item.findtext("pubDate", ""),
                "source": item.findtext("source", ""),
                "classification": classification,
                "status_label": status_label,
                "page_check": page_info
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
