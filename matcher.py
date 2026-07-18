"""
matcher.py -- Decides whether a specific marketplace listing is actually the
book (and the *edition*) a watchlist entry is looking for.

Rare books are unforgiving: "Blood Meridian" the 1985 First Edition and
"Blood Meridian" the 2010 paperback reprint share a title but are worth
wildly different amounts. Rather than one fuzzy title match, this module
checks several independent, mostly-optional signals -- title similarity,
author, ISBN, publisher, year, required edition keywords, excluded keywords,
and a price ceiling -- so a listing has to clear every signal a watchlist
entry actually specifies. Leave a field blank/empty in books.json and that
check is simply skipped.
"""

import re
import difflib


def _normalize(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(haystack, needle):
    needle = _normalize(needle)
    return bool(needle) and needle in _normalize(haystack)


def _title_similarity(a, b):
    """
    Real auction/listing titles are almost always longer than the plain
    book title -- sellers pack in publisher, year, and edition info, e.g.
    "Hemingway THE OLD MAN AND THE SEA Scribner 1952 First Edition". A
    plain difflib ratio() penalizes that extra (useful!) text as if it were
    noise, so a correct match can score as low as ~0.5. Instead this takes
    the better of two signals:

      - containment: how much of the shorter string's text appears, in
        order, inside the longer one (catches "the extra text is just
        appended/prepended" listings)
      - word overlap: what fraction of the book title's distinct words
        appear anywhere in the listing (catches sellers reordering words,
        e.g. "Old Man and the Sea, The - Hemingway")
    """
    a_norm, b_norm = _normalize(a), _normalize(b)
    if not a_norm or not b_norm:
        return 0.0

    seq = difflib.SequenceMatcher(None, a_norm, b_norm)
    matched_chars = sum(block.size for block in seq.get_matching_blocks())
    containment = matched_chars / min(len(a_norm), len(b_norm))

    a_words, b_words = set(a_norm.split()), set(b_norm.split())
    word_overlap = len(a_words & b_words) / len(a_words) if a_words else 0.0

    return max(containment, word_overlap)


def _clean_isbn(isbn):
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def evaluate(book, listing, title_threshold=0.72):
    """
    Compares one watchlist entry (from books.json) against one listing (from
    sources.py). Returns (is_match: bool, reasons: list[str]).

    `reasons` explains the decision either way -- run with DEBUG=1 (see
    main.py) to print it for every candidate while you're tuning a
    watchlist entry's keywords/threshold.
    """
    text = f"{listing.get('title', '')} {listing.get('description', '')}"

    isbn_wanted = _clean_isbn(book.get("isbn", ""))
    isbn_listed = _clean_isbn(listing.get("isbn", ""))
    isbn_match = bool(isbn_wanted) and isbn_wanted == isbn_listed

    if isbn_match:
        # Exact ISBN is the strongest possible signal -- it already implies
        # the correct title/author/edition, so we skip straight to the
        # exclude-keyword and price checks below.
        reasons = ["ISBN matched exactly"]
    else:
        similarity = _title_similarity(book.get("title", ""), listing.get("title", ""))
        if similarity < title_threshold:
            return False, [f"title similarity {similarity:.2f} below threshold {title_threshold}"]
        reasons = [f"title similarity {similarity:.2f}"]

        author = (book.get("author") or "").strip()
        if author:
            last_name = author.split()[-1]
            if not _contains(text, last_name):
                return False, [f"author '{author}' not found in listing"]
            reasons.append("author matched")

        publisher = (book.get("publisher") or "").strip()
        if publisher and not _contains(text, publisher):
            return False, [f"publisher '{publisher}' not found in listing"]
        if publisher:
            reasons.append("publisher matched")

        year = str(book.get("year", "")).strip()
        if year and year not in text:
            return False, [f"year '{year}' not found in listing"]
        if year:
            reasons.append("year matched")

        edition_keywords = book.get("edition_keywords") or []
        if edition_keywords:
            if not any(_contains(text, kw) for kw in edition_keywords):
                return False, [f"none of edition_keywords {edition_keywords} found"]
            reasons.append("edition keyword matched")

    # Exclude-keywords and the price ceiling always apply, even for an ISBN
    # match -- e.g. you can still rule out a "lot of 10" bundle listing.
    exclude_keywords = book.get("exclude_keywords") or []
    hit = next((kw for kw in exclude_keywords if _contains(text, kw)), None)
    if hit:
        return False, [f"exclude_keyword '{hit}' found in listing"]

    max_price = book.get("max_price")
    price = listing.get("price")
    if max_price and price is not None and price > max_price:
        return False, [f"price {price} exceeds max_price {max_price}"]

    return True, reasons
