import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

SOURCE_URL = "https://www.ufc.com/news-sitemap.xml"
SITE_URL = "https://www.ufc.com/trending/all"
OUTPUT_FILE = "feed.xml"
MAX_ITEMS = 30

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; UFC-RSS-Feed/1.0)"
}

response = requests.get(SOURCE_URL, headers=headers, timeout=30)
response.raise_for_status()

root = ET.fromstring(response.content)

def find_text(node, local_name):
    for element in node.iter():
        if element.tag.endswith("}" + local_name) or element.tag == local_name:
            if element.text:
                return element.text.strip()
    return ""

items = []

for url_node in root:
    loc = find_text(url_node, "loc")
    title = find_text(url_node, "title")
    pub_date = find_text(url_node, "publication_date") or find_text(url_node, "lastmod")

    if not loc:
        continue

    if not title:
        title = loc.rstrip("/").split("/")[-1].replace("-", " ").title()

    try:
        if pub_date:
            parsed_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            rss_date = format_datetime(parsed_date)
        else:
            rss_date = format_datetime(datetime.now(timezone.utc))
    except Exception:
        rss_date = format_datetime(datetime.now(timezone.utc))

    items.append({
        "title": title,
        "link": loc,
        "guid": loc,
        "pubDate": rss_date,
        "description": f"Latest UFC news: {title}"
    })

items = items[:MAX_ITEMS]

last_build_date = format_datetime(datetime.now(timezone.utc))

rss = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    '    <title>UFC News Feed</title>',
    f'    <link>{escape(SITE_URL)}</link>',
    '    <description>Flux RSS non officiel des dernières actualités UFC.</description>',
    '    <language>en-US</language>',
    f'    <lastBuildDate>{last_build_date}</lastBuildDate>',
    f'    <atom:link href="{escape(SITE_URL)}" rel="self" type="application/rss+xml" />'
]

for item in items:
    rss.extend([
        '    <item>',
        f'      <title>{escape(item["title"])}</title>',
        f'      <link>{escape(item["link"])}</link>',
        f'      <guid isPermaLink="true">{escape(item["guid"])}</guid>',
        f'      <pubDate>{item["pubDate"]}</pubDate>',
        f'      <description>{escape(item["description"])}</description>',
        '    </item>'
    ])

rss.extend([
    '  </channel>',
    '</rss>'
])

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(rss))

print(f"RSS feed generated: {OUTPUT_FILE}")
