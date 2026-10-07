"""Refresh the Smart Mirror's compact Livostyle dress catalog from its open dataset."""
from __future__ import annotations

from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "smart-mirror-embeddinggemma"
OUTPUT = APP / "python" / "catalog.json"
DATA_URL = "https://raw.githubusercontent.com/arturayupov/womens-fashion-catalog-open-data/main/data/products.json"
STATS_URL = "https://raw.githubusercontent.com/arturayupov/womens-fashion-catalog-open-data/main/data/stats.json"
DATASET_URL = "https://github.com/arturayupov/womens-fashion-catalog-open-data"
LICENSE_URL = DATASET_URL + "/blob/main/LICENSE"


def read_json(url: str):
    request = Request(url, headers={"User-Agent": "VENTUNO-Q-Smart-Mirror/1.0"})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def sized_image_url(url: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["width"] = "480"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def clean_description(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    return " ".join(value.split())[:900]


def main() -> None:
    products = read_json(DATA_URL)
    stats = read_json(STATS_URL)
    dresses = []
    for item in products:
        category = item.get("category") or {}
        if category.get("full_path") != "Apparel & Accessories > Clothing > Dresses":
            continue
        product_url = item.get("url", "")
        if not product_url.startswith("https://livostyle.com/products/"):
            continue
        image_url = item.get("featured_image_url")
        if not image_url:
            images = item.get("images") or []
            image_url = next((image.get("url") for image in images if image.get("url")), None)
        if not image_url or urlsplit(image_url).netloc != "cdn.shopify.com":
            continue

        product_type = item.get("product_type") or "Dress"
        tags = [tag for tag in item.get("tags", []) if tag and tag.lower() not in {"issues", "test"}]
        details = [product_type]
        if tags:
            details.append("Style details: " + ", ".join(tags[:12]))
        description = clean_description(item.get("description", ""))
        if description:
            details.append(description)
        price = item.get("price") or {}
        reviews = item.get("reviews") or {}
        dresses.append({
            "id": str(item.get("id") or item.get("handle")),
            "title": item.get("title") or product_type,
            "category": product_type,
            "description": ". ".join(details),
            "image_url": sized_image_url(image_url),
            "url": product_url,
            "price_usd": price.get("min_usd"),
            "vendor": item.get("vendor"),
            "rating": reviews.get("rating"),
            "review_count": reviews.get("count"),
        })

    dresses.sort(key=lambda item: item["title"].casefold())
    payload = {
        "source": "Livostyle Women's Fashion Catalog — Open Data",
        "source_url": DATASET_URL,
        "license_url": LICENSE_URL,
        "attribution": "Livostyle / Arcada LLC; product images remain hosted on Livostyle's Shopify CDN.",
        "license": "MIT (dataset repository)",
        "snapshot_date": (stats.get("last_synced") or "unknown")[:10],
        "products": dresses,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dresses)} dress products from snapshot {payload['snapshot_date']} to {OUTPUT}")


if __name__ == "__main__":
    main()
