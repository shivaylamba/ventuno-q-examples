"""Refresh a 100-item Amazon clothing catalog through the official Creators API.

Credentials are read only from environment variables and are never written to
the exported catalog. Product content and image URLs expire after 24 hours.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "smart-mirror-embeddinggemma" / "data" / "amazon-catalog.json"
API_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
TERMS = (
    "women midi dress", "women maxi dress", "women floral dress", "women wrap dress",
    "women shirt dress", "women cotton dress", "women summer dress", "women formal dress",
    "women evening dress", "women A-line dress", "women linen dress", "women cocktail dress",
    "women casual dress", "women long sleeve dress", "women fit and flare dress",
)
RESOURCES = ["images.primary.large", "itemInfo.title", "itemInfo.features",
             "itemInfo.byLineInfo", "itemInfo.productInfo"]


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Set {name} in this PowerShell session; credentials are not saved.")
    return value


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=data, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1200]
        raise RuntimeError(f"Amazon API returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Amazon Creators API: {exc.reason}") from exc


def token_endpoint(marketplace: str) -> str:
    if marketplace in {"www.amazon.com", "www.amazon.ca", "www.amazon.com.mx", "www.amazon.com.br"}:
        return "https://api.amazon.com/auth/o2/token"
    if marketplace in {"www.amazon.co.jp", "www.amazon.com.au", "www.amazon.sg"}:
        return "https://api.amazon.co.jp/auth/o2/token"
    return "https://api.amazon.co.uk/auth/o2/token"


def display_value(obj: dict | None, key: str = "displayValue") -> str:
    return str((obj or {}).get(key) or "").strip()


def item_to_product(item: dict, marketplace: str) -> dict | None:
    title = display_value((item.get("itemInfo") or {}).get("title"))
    images = item.get("images") or {}
    primary = images.get("primary") or {}
    image = primary.get("large") or primary.get("medium") or primary.get("small") or {}
    image_url = image.get("url")
    asin = str(item.get("asin") or "").strip()
    listing_url = str(item.get("detailPageURL") or "").strip()
    if not title or not image_url or not asin or not listing_url:
        return None
    info = item.get("itemInfo") or {}
    features = ((info.get("features") or {}).get("displayValues") or [])
    product_info = info.get("productInfo") or {}
    color = display_value(product_info.get("color"))
    brand = display_value((info.get("byLineInfo") or {}).get("brand"))
    description = ". ".join([brand, color, *(str(v).strip() for v in features[:5])]).strip(". ")
    return {
        "id": asin, "asin": asin, "title": title,
        "description": description or title,
        "category": "Dress", "image_url": image_url,
        "image_width": image.get("width"), "image_height": image.get("height"),
        "url": listing_url, "marketplace": marketplace,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    client_id = required_env("AMAZON_CREATORS_CLIENT_ID")
    client_secret = required_env("AMAZON_CREATORS_CLIENT_SECRET")
    partner_tag = required_env("AMAZON_PARTNER_TAG")
    marketplace = required_env("AMAZON_MARKETPLACE")
    if not marketplace.startswith("www.amazon."):
        raise SystemExit("AMAZON_MARKETPLACE must be a Creators API marketplace host such as www.amazon.in or www.amazon.com.")
    endpoint = os.environ.get("AMAZON_CREATORS_TOKEN_ENDPOINT", token_endpoint(marketplace)).strip()

    token_data = post_json(endpoint, {
        "grant_type": "client_credentials", "client_id": client_id,
        "client_secret": client_secret, "scope": "creatorsapi::default",
    })
    access_token = token_data["access_token"]
    products: dict[str, dict] = {}
    for term in TERMS:
        payload = {
            "keywords": term, "itemCount": 10, "itemPage": 1,
            "partnerTag": partner_tag, "marketplace": marketplace,
            "resources": RESOURCES,
        }
        response = post_json(API_URL, payload, {
            "Authorization": f"Bearer {access_token}", "x-marketplace": marketplace,
        })
        for item in ((response.get("searchResult") or {}).get("items") or []):
            product = item_to_product(item, marketplace)
            if product:
                products.setdefault(product["asin"], product)
                if len(products) >= 100:
                    break
        print(f"{term}: {len(products)} unique clothing listings", flush=True)
        if len(products) >= 100:
            break
        time.sleep(1.1)

    if len(products) < 100:
        print(f"Only {len(products)} products returned; broaden the searches or check API access and retry.", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "Amazon Creators API", "marketplace": marketplace,
        "generated_at": now.isoformat(), "expires_at": (now + timedelta(hours=23)).isoformat(),
        "products": list(products.values())[:100],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['products'])} listings and image links to {OUT}")
    print("Refresh within 23 hours; product text and image URLs expire with this catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
