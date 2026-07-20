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

Every function takes (book, limit) -- the full watchlist entry from
books.json, not just a query string -- so a source that supports precise
server-side filters (AbeBooks does: publisher, exact publication year,
first-edition tagging, price range) can use them directly instead of
relying only on a keyword search plus matcher.py's post-hoc filtering.
Sources that only support keyword search (eBay, Etsy) just pull
title/author out of the book dict to build one.

All of these talk to an official, sanctioned API. That's a deliberate
choice: it's also the *only* approach that doesn't eventually get an app
blocked, since you're using the door the site built for this rather than
picking the lock on the front door.

Every function returns a list -- an empty list on "source not
configured", never an exception for that case, so main.py can call every
source for every book without special-casing anything.
"""

import base64
import os
import re
import time
from urllib.parse import quote
from xml.etree import ElementTree

import requests


def _text_query(book):
    """Shared helper for sources that only support keyword search."""
    return f"{book['title']} {book.get('author', '')}".strip()


def _raise_with_body(resp):
    """
    requests' raise_for_status() only reports the HTTP status line (e.g.
    "409 Client Error: Conflict for url: ..."), discarding the response
    body -- which is exactly where eBay/Etsy/AbeBooks put the actually
    useful diagnostic detail (a specific error code and message, not just
    a bare status code). This re-raises with that body attached so a
    workflow log shows what the API actually said instead of needing to
    be reproduced locally to find out.
    """
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(f"{exc} | Response body: {resp.text[:1000]}") from exc


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
    _raise_with_body(resp)
    payload = resp.json()
    _ebay_token_cache["token"] = payload["access_token"]
    _ebay_token_cache["expires_at"] = now + int(payload.get("expires_in", 7200))
    return _ebay_token_cache["token"]


def search_ebay(book, limit=25):
    """
    Searches active eBay listings by keyword via the Browse API.

    The Browse API scopes every call to exactly one eBay site via the
    X-EBAY-C-MARKETPLACE-ID header -- it does not search across sites, so
    a book listed only on eBay.co.uk is invisible to a search scoped to
    EBAY_US, and vice versa. This loops over EBAY_MARKETPLACES -- a
    comma-separated list of MarketplaceIdEnum values ONLY, e.g.
    "EBAY_US,EBAY_GB,EBAY_DE" -- with nothing else in the string (no
    trailing notes, no spaces around commas mattering, but no free text
    either). See
    https://developer.ebay.com/api-docs/buy/browse/types/gct:MarketplaceIdEnum
    for the full list. Defaults to US + UK since rare/antiquarian book
    dealers are heavily concentrated in both. Results are deduped by
    itemId in case the same listing surfaces under more than one
    marketplace query.
    """
    raw_marketplaces = [
        m.strip() for m in os.environ.get("EBAY_MARKETPLACES", "EBAY_US,EBAY_GB").split(",")
        if m.strip()
    ]
    # A real MarketplaceIdEnum value is uppercase letters/underscores only
    # (EBAY_US, EBAY_GB, EBAY_DE, ...) -- anything else (extra words,
    # lowercase, spaces) is almost certainly a malformed EBAY_MARKETPLACES
    # secret, e.g. "EBAY_DE and some other countries" instead of just
    # "EBAY_DE". Skip and warn instead of sending it to eBay and getting
    # back an opaque error.
    marketplaces = []
    for m in raw_marketplaces:
        if re.fullmatch(r"[A-Z_]+", m):
            marketplaces.append(m)
        else:
            print(f"    eBay: skipping invalid EBAY_MARKETPLACES entry {m!r} "
                  f"(expected a plain value like EBAY_US, EBAY_GB, EBAY_DE)")
    if not marketplaces:
        raise RuntimeError(
            f"No valid entries in EBAY_MARKETPLACES ({raw_marketplaces!r}). "
            f"Expected a comma-separated list like 'EBAY_US,EBAY_GB'."
        )
    token = _get_ebay_token()
    query = _text_query(book)

    results = []
    seen_item_ids = set()
    for marketplace in marketplaces:
        try:
            resp = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": marketplace,
                },
                params={"q": query, "limit": limit},
                timeout=30,
            )
            _raise_with_body(resp)
            items = resp.json().get("itemSummaries", [])
            print(f"    eBay [{marketplace}]: {len(items)} raw result(s)")
        except requests.RequestException as exc:
            # One marketplace failing (rate limit, transient error, bad
            # config) shouldn't discard results already fetched from the
            # others -- log it and move on to the next marketplace.
            print(f"    eBay [{marketplace}]: FAILED -- {exc}")
            continue

        for item in items:
            item_id = item.get("itemId", "")
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)

            price = item.get("price") or {}
            image = item.get("image") or {}
            results.append({
                "source": "eBay",
                "item_id": item_id,
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

def search_etsy(book, limit=25):
    """Searches active Etsy listings by keyword via the Open API v3."""
    api_key = os.environ.get("ETSY_API_KEY")
    if not api_key:
        return []  # Source not configured -- silently skipped.

    resp = requests.get(
        "https://api.etsy.com/v3/application/listings/active",
        headers={"x-api-key": api_key},
        params={"keywords": _text_query(book), "limit": min(limit, 100)},
        timeout=30,
    )
    _raise_with_body(resp)
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

def search_biblio(book, limit=25):
    api_key = os.environ.get("BIBLIO_API_KEY")
    if not api_key:
        return []

    resp = requests.get(
        "https://api.biblio.com/v1/search",  # TODO: confirm against Biblio's docs
        headers={"Authorization": f"Bearer {api_key}"},
        params={"q": _text_query(book), "limit": limit},
        timeout=30,
    )
    _raise_with_body(resp)
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


# ---------------------------------------------------------------------------
# AbeBooks -- Search Web Services (SWS)
#
# Requires joining AbeBooks' Affiliate Program and requesting a Client Key
# by emailing affiliate@abebooks.com (see README.md for the application
# email). Unlike the sources above, this one is built from AbeBooks' own
# March 2025 "Search Web Services End User Guide" rather than general
# knowledge, so field names and behavior are as documented there -- the
# one thing that guide doesn't fully specify is the exact XML wrapper
# element around multiple <Book> records, which is why the parsing below
# searches for <Book> anywhere in the tree instead of assuming a specific
# root tag.
#
# SWS supports real server-side filters that map directly onto books.json
# fields -- publisher name, exact publication year, first-edition tagging,
# and a price range -- so this function leans on those instead of relying
# only on matcher.py's post-hoc text matching the way eBay/Etsy do.
# ---------------------------------------------------------------------------

def _encode_latin1(value):
    """
    SWS requires ISO-8859-1 URL encoding, not the UTF-8 `requests` uses by
    default -- matters for accented author/title names (e.g. "Hoelderlin"
    with an umlaut). Falls back to UTF-8 for the rare character that can't
    be represented in Latin-1 at all.
    """
    try:
        return quote(str(value).encode("iso-8859-1"))
    except UnicodeEncodeError:
        return quote(str(value).encode("utf-8"))


def search_abebooks(book, limit=25):
    api_key = os.environ.get("ABEBOOKS_CLIENT_KEY")
    if not api_key:
        return []

    params = {
        "clientkey": api_key,
        "outputsize": "long",
        "maxresults": min(limit, 200),
        "currency": "USD",  # normalizes listingPrice to USD regardless of seller's currency
    }

    # Primary search parameter -- ISBN is the most precise when we have one.
    if book.get("isbn"):
        params["isbn"] = book["isbn"]
    else:
        params["title"] = book["title"]
        if book.get("author"):
            params["author"] = book["author"]

    # Secondary parameters -- real server-side filtering, not just text
    # matching after the fact.
    if book.get("publisher"):
        params["pubname"] = book["publisher"]
    if book.get("year"):
        params["minpubyear"] = book["year"]
        params["maxpubyear"] = book["year"]
    if book.get("min_price"):
        params["minprice"] = int(book["min_price"])
    if book.get("max_price"):
        params["maxprice"] = int(book["max_price"])
    if any("first ed" in kw.lower() or "1st ed" in kw.lower() for kw in book.get("edition_keywords") or []):
        params["firstedition"] = "yes"

    query_string = "&".join(f"{k}={_encode_latin1(v)}" for k, v in params.items())
    resp = requests.get(f"https://search2.abebooks.com/search?{query_string}", timeout=30)
    _raise_with_body(resp)

    root = ElementTree.fromstring(resp.content)
    results = []
    for book_el in root.findall(".//Book"):
        def field(tag, default=""):
            el = book_el.find(tag)
            return el.text if el is not None and el.text else default

        listing_url = field("listingUrl")
        if listing_url and not listing_url.startswith("http"):
            listing_url = f"https://www.{listing_url}"

        price_text = field("listingPrice")
        results.append({
            "source": "AbeBooks",
            "item_id": field("bookId"),
            "title": field("title"),
            "description": " ".join(filter(None, [field("vendorDescription"), field("keywords")])),
            "url": listing_url,
            "image": field("catalogImage") or field("vendorImage"),
            "price": float(price_text) if price_text else None,
            "currency": "USD",
            "isbn": field("isbn13") or field("isbn10"),
        })
    return results
