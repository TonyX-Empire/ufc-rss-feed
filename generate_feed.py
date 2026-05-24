import json
import time
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape


SOURCE_URL = "https://www.ufc.com/news-sitemap.xml"
SITE_URL = "https://www.ufc.com/trending/all"
FEED_URL = "https://tonyx-empire.github.io/ufc-rss-feed/feed.xml"
JSON_URL = "https://tonyx-empire.github.io/ufc-rss-feed/feed.json"

OUTPUT_RSS_FILE = "feed.xml"
OUTPUT_JSON_FILE = "feed.json"

MAX_ITEMS = 30

# Mets True si tu veux exclure les contenus BJJ / Boxing.
MMA_ONLY = False

EXCLUDED_KEYWORDS = [
    "zuffa-boxing",
    "zuffa boxing",
    "ufc-bjj",
    "ufc bjj",
    "bjj",
    "grappling"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UFC-RSS-Feed/2.0; +https://tonyx-empire.github.io/ufc-rss-feed/feed.xml)"
}


def find_text(node, local_name):
    """
    Récupère le texte d'une balise XML, même avec namespace.
    Exemple : news:title, news:publication_date, loc, lastmod.
    """
    for element in node.iter():
        if element.tag.endswith("}" + local_name) or element.tag == local_name:
            if element.text:
                return element.text.strip()
    return ""


def parse_date(date_string):
    """
    Convertit une date sitemap en date RSS propre.
    """
    if not date_string:
        return datetime.now(timezone.utc)

    try:
        clean_date = date_string.replace("Z", "+00:00")
        parsed_date = datetime.fromisoformat(clean_date)

        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)

        return parsed_date.astimezone(timezone.utc)

    except Exception:
        return datetime.now(timezone.utc)


def format_rss_date(date_object):
    """
    Formate une date pour RSS.
    """
    return format_datetime(date_object, usegmt=True)


def clean_text(value):
    """
    Nettoie les textes pour éviter les espaces inutiles.
    """
    if not value:
        return ""

    return " ".join(value.split()).strip()


def get_meta_content(soup, property_name=None, name=None):
    """
    Récupère une balise meta HTML.
    Exemples :
    - og:description
    - og:image
    - description
    """
    if property_name:
        tag = soup.find("meta", property=property_name)
        if tag and tag.get("content"):
            return clean_text(tag.get("content"))

    if name:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_text(tag.get("content"))

    return ""


def fetch_article_metadata(url):
    """
    Récupère image, description et titre depuis la page article UFC.
    Si UFC bloque ou ralentit, le script continue avec des valeurs fallback.
    """
    metadata = {
        "title": "",
        "description": "",
        "image": ""
    }

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        metadata["title"] = (
            get_meta_content(soup, property_name="og:title")
            or get_meta_content(soup, name="twitter:title")
        )

        metadata["description"] = (
            get_meta_content(soup, property_name="og:description")
            or get_meta_content(soup, name="description")
            or get_meta_content(soup, name="twitter:description")
        )

        metadata["image"] = (
            get_meta_content(soup, property_name="og:image")
            or get_meta_content(soup, name="twitter:image")
        )

    except Exception as error:
        print(f"Metadata fallback for {url}: {error}")

    return metadata


def detect_category(title, link):
    """
    Détecte une catégorie simple selon le titre et l'URL.
    """
    text = f"{title} {link}".lower()

    if "zuffa-boxing" in text or "zuffa boxing" in text or "boxing" in text:
        return "Boxing"

    if "ufc-bjj" in text or "ufc bjj" in text or "bjj" in text:
        return "UFC BJJ"

    if "road-to-ufc" in text or "road to ufc" in text:
        return "Road to UFC"

    if "fight-night" in text or "ufc-fight-night" in text:
        return "UFC Fight Night"

    if "ufc-" in text or "ufc " in text:
        return "UFC"

    return "News"


def should_keep_item(title, link):
    """
    Filtre optionnel pour ne garder que les contenus MMA/UFC.
    """
    if not MMA_ONLY:
        return True

    text = f"{title} {link}".lower()

    for keyword in EXCLUDED_KEYWORDS:
        if keyword in text:
            return False

    return True


def build_rss_description(item):
    """
    Description RSS enrichie avec image si disponible.
    """
    description_parts = []

    if item.get("image"):
        description_parts.append(
            f'<p><img src="{escape(item["image"])}" alt="{escape(item["title"])}" /></p>'
        )

    if item.get("description"):
        description_parts.append(f'<p>{escape(item["description"])}</p>')
    else:
        description_parts.append(f'<p>Latest UFC news: {escape(item["title"])}</p>')

    description_parts.append(f'<p>Category: {escape(item["category"])}</p>')

    return "<![CDATA[" + "\n".join(description_parts) + "]]>"


def fetch_sitemap_items():
    """
    Récupère les articles depuis le sitemap officiel UFC News.
    """
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    raw_items = []

    for url_node in root:
        loc = find_text(url_node, "loc")
        sitemap_title = find_text(url_node, "title")
        publication_date = find_text(url_node, "publication_date") or find_text(url_node, "lastmod")

        if not loc:
            continue

        fallback_title = loc.rstrip("/").split("/")[-1].replace("-", " ").title()
        title = clean_text(sitemap_title) or fallback_title

        if not should_keep_item(title, loc):
            continue

        date_object = parse_date(publication_date)

        raw_items.append({
            "title": title,
            "link": loc,
            "guid": loc,
            "date_object": date_object,
            "pubDate": format_rss_date(date_object),
        })

    raw_items.sort(key=lambda item: item["date_object"], reverse=True)

    return raw_items[:MAX_ITEMS]


def enrich_items(raw_items):
    """
    Enrichit les items avec description, image et catégorie.
    """
    enriched_items = []

    for index, item in enumerate(raw_items, start=1):
        print(f"Enriching item {index}/{len(raw_items)}: {item['link']}")

        metadata = fetch_article_metadata(item["link"])

        final_title = metadata.get("title") or item["title"]
        final_description = metadata.get("description") or f"Latest UFC news: {final_title}"
        final_image = metadata.get("image") or ""

        category = detect_category(final_title, item["link"])

        enriched_items.append({
            "title": final_title,
            "link": item["link"],
            "guid": item["guid"],
            "pubDate": item["pubDate"],
            "published_at": item["date_object"].isoformat(),
            "description": final_description,
            "image": final_image,
            "category": category,
            "source": "UFC",
        })

        # Petite pause pour éviter de taper trop fort sur UFC.
        time.sleep(0.5)

    return enriched_items


def generate_rss(items):
    """
    Génère le fichier feed.xml.
    """
    last_build_date = format_rss_date(datetime.now(timezone.utc))

    rss = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>UFC News Feed</title>',
        f'    <link>{escape(SITE_URL)}</link>',
        '    <description>Flux RSS non officiel enrichi des dernières actualités UFC.</description>',
        '    <language>en-US</language>',
        f'    <lastBuildDate>{last_build_date}</lastBuildDate>',
        f'    <atom:link href="{escape(FEED_URL)}" rel="self" type="application/rss+xml" />',
    ]

    for item in items:
        rss.extend([
            '    <item>',
            f'      <title>{escape(item["title"])}</title>',
            f'      <link>{escape(item["link"])}</link>',
            f'      <guid isPermaLink="true">{escape(item["guid"])}</guid>',
            f'      <pubDate>{item["pubDate"]}</pubDate>',
            f'      <category>{escape(item["category"])}</category>',
            f'      <description>{build_rss_description(item)}</description>',
            '    </item>'
        ])

    rss.extend([
        '  </channel>',
        '</rss>'
    ])

    with open(OUTPUT_RSS_FILE, "w", encoding="utf-8") as file:
        file.write("\n".join(rss))

    print(f"RSS feed generated: {OUTPUT_RSS_FILE}")


def generate_json(items):
    """
    Génère un fichier feed.json pratique pour automatisation.
    """
    payload = {
        "title": "UFC News Feed",
        "source_url": SITE_URL,
        "feed_url": FEED_URL,
        "json_url": JSON_URL,
        "last_build_date": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "items": items
    }

    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"JSON feed generated: {OUTPUT_JSON_FILE}")


def main():
    raw_items = fetch_sitemap_items()
    enriched_items = enrich_items(raw_items)

    generate_rss(enriched_items)
    generate_json(enriched_items)


if __name__ == "__main__":
    main()
