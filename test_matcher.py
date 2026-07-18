"""Quick sanity checks for matcher.py using realistic synthetic listings.
Not part of the shipped project -- just used to validate the logic once."""

from matcher import evaluate

book_hemingway = {
    "title": "The Old Man and the Sea",
    "author": "Ernest Hemingway",
    "isbn": "",
    "publisher": "Scribner",
    "year": "1952",
    "edition_keywords": ["first edition", "1st edition"],
    "exclude_keywords": ["book club", "reprint", "facsimile", "paperback"],
    "max_price": 8000,
}

book_mccarthy = {
    "title": "Blood Meridian",
    "author": "Cormac McCarthy",
    "isbn": "9780394747420",
    "publisher": "",
    "year": "",
    "edition_keywords": [],
    "exclude_keywords": ["book club"],
    "max_price": 500,
}

cases = [
    # (name, book, listing, expected_is_match)
    (
        "correct first edition",
        book_hemingway,
        {"title": "Hemingway THE OLD MAN AND THE SEA Scribner 1952 First Edition",
         "description": "True first printing, first state dust jacket", "price": 4500},
        True,
    ),
    (
        "same title, book club edition -> reject",
        book_hemingway,
        {"title": "The Old Man and the Sea by Ernest Hemingway - Book Club Edition",
         "description": "Hardcover reprint", "price": 12},
        False,
    ),
    (
        "same title, modern paperback -> reject",
        book_hemingway,
        {"title": "The Old Man and the Sea - Ernest Hemingway paperback",
         "description": "Scribner Classics reprint 1995", "price": 8},
        False,
    ),
    (
        "different book, similar title -> reject",
        book_hemingway,
        {"title": "The Old Man and the Sea - a Study Guide",
         "description": "Companion analysis, not the novel itself", "price": 15},
        False,  # no "Hemingway" text, no edition keywords present
    ),
    (
        "price way over ceiling -> reject",
        book_hemingway,
        {"title": "Hemingway THE OLD MAN AND THE SEA Scribner 1952 First Edition, signed, in slipcase",
         "description": "first edition first printing", "price": 25000},
        False,
    ),
    (
        "ISBN exact match, no other fields needed",
        book_mccarthy,
        {"title": "Blood Meridian (used paperback, Vintage)",
         "description": "Some shelf wear", "isbn": "978-0-394-74742-0", "price": 22},
        True,
    ),
    (
        "ISBN mismatch, weak title similarity -> reject",
        book_mccarthy,
        {"title": "Blood Meridian Study Companion",
         "description": "", "isbn": "9781234567897", "price": 10},
        False,
    ),
]

failures = 0
for name, book, listing, expected in cases:
    listing.setdefault("item_id", "x")
    listing.setdefault("currency", "USD")
    is_match, reasons = evaluate(book, listing)
    ok = is_match == expected
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'} | {name} | got={is_match} expected={expected} | {reasons}")

print(f"\n{len(cases) - failures}/{len(cases)} passed")
if failures:
    raise SystemExit(1)
