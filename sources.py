"""
sources.py -- One function per marketplace, each returning listings in the
same normalized shape so matcher.py and main.py don't need to know which
site a result came from:

    {
        "source": "eBay",
        "item_id": "...",       # unique within that source
        "title": "...",
        "description": "...",  # whatever extra text the API exposes
        "url": "...",
        "image": "...",
        "price": 123.45,        # float, or None if not listed
        "currency": "USD",
        "isbn": "",              # filled in only if the API exposes it
    }

Every function here talks to an official, sanctioned API -- eBay's Browse
API and Etsy's Open API v3 are both free to sign up for and are meant for
exactly this kind of programmatic search. That's a deliberate choice: it's
also the *only* approach that doesn't eventually get an app blocked, since
you're using the door the site built for this rather than picking the lock
on the front door. See README.md for why AbeBooks isn't included here, and
for how to add another site of your own later.

All functions take (query, limit) and return a list -- an empty list on
"source not configured", never an exception for that case, so main.py can
call every source for every book without special-casing anything.
"""

import base64
import os
import time

import requests


# ---------------------------------------------------------------------------
# eBay -- Browse API (https://developer.ebay.com/api-docs/buy/browse/overview.html)
# ---------------------------------------------------------------------------

_ebay_token_cache = {"token": None, "expires_at": 0}


def _get_ebay_token():
    """
    Application access tokens are obtained via the client-credentials OAuth
    flow and last ~2 hours -- cached in memory so a run checking many books
    doesn't request a fresh token per book.
    """
    now = time.time()
    if _ebay_token_cache["token"] and now < _ebay_token_cache["expires_at"] - 60:
        return _ebay_token_cache["token"]

    client_id = os.environ.get("EBAY_CLIENT_ID")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET are not set.")

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _ebay_token_cache["token"] = payload["access_token"]
    _ebay_token_cache["expires_at"] = now + int(payload.get("expires_in", 7200))
    return _ebay_token_cache["token"]


def search_ebay(query, limit=25):
    """Searches active eBay listings by keyword via the Browse API."""
    token = _get_ebay_token()
    resp = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
        params={"q": query, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("itemSummaries", [])

    results = []
    for item in items:
        price = item.get("price") or {}
        image = item.get("image") or {}
        results.append({
            "source": "eBay",
            "item_id": item.get("itemId", ""),
            "title": item.get("title", ""),
            # The summary search doesn't return a full description; the
            # subtitle plus title is usually enough to match against since
            # sellers pack edition/publisher info into both. Fetching the
            # full description would mean one extra getItem() call per
            # candidate -- easy to add later if you need it.
            "description": item.get("subtitle", ""),
            "url": item.get("itemWebUrl", ""),
            "image": image.get("imageUrl", ""),
            "price": float(price["value"]) if price.get("value") else None,
            "currency": price.get("currency", ""),
            "isbn": "",
        })
    return results


# ---------------------------------------------------------------------------
# Etsy -- Open API v3 (https://developers.etsy.com/documentation/)
# Vintage/antiquarian books show up here as a secondary market to eBay's.
# Only the "search public active listings" endpoint is used, which needs
# just a static API key (no OAuth/user login required).
# ---------------------------------------------------------------------------

def search_etsy(query, limit=25):
    """Searches active Etsy listings by keyword via the Open API v3."""
    api_key = os.environ.get("ETSY_API_KEY")
    if not api_key:
        return []  # Source not configured -- silently skipped.

    resp = requests.get(
        "https://api.etsy.com/v3/application/listings/active",
        headers={"x-api-key": api_key},
        params={"keywords": query, "limit": min(limit, 100)},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("results", [])

    results = []
    for item in items:
        images = item.get("images") or []
        image_url = ""
        if images:
            img = images[0]
            image_url = img.get("url_570xN") or img.get("url_fullxfull") or img.get("url_170x135") or ""

        price_info = item.get("price") or {}
        amount = price_info.get("amount")
        divisor = price_info.get("divisor") or 100
        price = (amount / divisor) if amount is not None else None

        results.append({
            "source": "Etsy",
            "item_id": str(item.get("listing_id", "")),
            "title": item.get("title", ""),
            "description": (item.get("description") or "")[:500],
            "url": item.get("url", ""),
            "image": image_url,
            "price": price,
            "currency": price_info.get("currency_code", ""),
            "isbn": "",
        })
    return results


# ---------------------------------------------------------------------------
# Biblio.com -- Inventory API
# Biblio does NOT offer a self-serve public API. Access is granted to
# approved affiliates only:
#   1. Join the (free) affiliate program: https://www.biblio.com/affiliate_program/
#   2. Email their marketing team from your account's registered address
#      asking for Inventory API access -- they reply in a few business days
#      with a key and the real documentation.
#   3. Set BIBLIO_API_KEY as a secret, then confirm the endpoint path and
#      response field names below against the docs they send you. Biblio's
#      schema isn't publicly published, so this function is a scaffold, not
#      a verified integration the way search_ebay/search_etsy are.
# Until BIBLIO_API_KEY is set, this source is skipped automatically.
# ---------------------------------------------------------------------------

def search_biblio(query, limit=25):
    api_key = os.environ.get("BIBLIO_API_KEY")
    if not api_key:
        return []

    resp = requests.get(
        "https://api.biblio.com/v1/search",  # TODO: confirm against Biblio's docs
        headers={"Authorization": f"Bearer {api_key}"},
        params={"q": query, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("results", [])  # TODO: confirm response shape

    results = []
    for item in items:
        results.append({
            "source": "Biblio",
            "item_id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "url": item.get("url", ""),
            "image": item.get("image_url", ""),
            "price": item.get("price"),
            "currency": item.get("currency", "USD"),
            "isbn": item.get("isbn", ""),
        })
    return results
