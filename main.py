"""
main.py -- Entry point. Loads books.json, searches every configured source
for each book, filters results through matcher.evaluate(), and emails any
new match.

Run twice a day by .github/workflows/check_books.yml, or locally with:
    python main.py
    DEBUG=1 python main.py     # also prints why each candidate did/didn't match
"""

import json
import os
import sys
import time

from sources import search_ebay, search_etsy, search_biblio, search_abebooks
from matcher import evaluate
from emailer import send_email
from storage import load_seen, save_seen, write_status

DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

# Add more sources here as you wire them up -- every function in this list
# just needs to accept (book, limit) and return the normalized list shape
# documented at the top of sources.py.
SOURCES = [search_ebay, search_etsy, search_biblio, search_abebooks]


def load_books():
    # If BOOKS_JSON is set (as a GitHub secret), your real watchlist never
    # has to be committed to the repo at all -- it's parsed directly from
    # the environment variable. books.json on disk then stays purely as
    # harmless example/template data, safe to have in git history even on
    # a public repo. Falls back to the file if the secret isn't set, which
    # is also what makes local testing easy without touching secrets.
    books_json_env = os.environ.get("BOOKS_JSON")
    if books_json_env:
        return json.loads(books_json_env)
    with open("books.json", "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    books = load_books()
    seen = load_seen()
    new_matches = 0
    errors = []

    for book in books:
        print(f"\n=== Searching: {book['title']} ===")

        listings = []
        for search_fn in SOURCES:
            try:
                found = search_fn(book)
                listings.extend(found)
                if found or DEBUG:
                    print(f"  {search_fn.__name__}: {len(found)} listing(s)")
            except Exception as exc:
                # One source failing (expired key, rate limit, network
                # blip) shouldn't stop the other sources or the rest of
                # the book list from being checked.
                msg = f"{search_fn.__name__} failed for '{book['title']}': {exc}"
                print(f"  {msg}", file=sys.stderr)
                errors.append(msg)

        for listing in listings:
            key = f"{listing['source']}:{listing['item_id']}"
            if key in seen:
                continue

            is_match, reasons = evaluate(book, listing)
            if DEBUG:
                verdict = "MATCH" if is_match else "skip "
                print(f"    [{verdict}] {listing['source']} - {listing['title'][:70]!r} :: {reasons}")

            if is_match:
                print(f"  >>> MATCH: {listing['title']} ({listing['source']}, {listing.get('price')})")
                send_email(book["title"], listing)
                seen[key] = True
                new_matches += 1

        time.sleep(1)  # small courtesy pause between books

    save_seen(seen)
    write_status(books_checked=len(books), new_matches=new_matches, errors=errors)
    print(f"\nDone. {new_matches} new match(es) emailed.")


if __name__ == "__main__":
    main()
