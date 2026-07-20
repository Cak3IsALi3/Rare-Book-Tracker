# Rare Book Watchlist

Automatically searches eBay, Etsy, and AbeBooks for specific rare or
collectible books and sends an email — with photo, price, and a link —
the moment a matching listing appears. Runs on a free schedule via GitHub
Actions, so no server or always-on machine is required.

## Features

- **Multi-source search** — eBay and Etsy out of the box, with optional
  support for AbeBooks and Biblio.
- **Edition-aware matching** — filters on ISBN, publisher, publication
  year, first-edition tagging, and a price range, so a $6 reprint doesn't
  trigger an alert meant for a $4,000 first edition.
- **Runs for free in the cloud** — a scheduled GitHub Actions workflow
  checks twice a day; nothing needs to stay running on your end.
- **Expandable watchlist** — add as many books as you want by editing one
  JSON file (or keep it private — see below).
- **No servers to maintain** — state (which listings have already been
  emailed about) is tracked in a small file committed back to the repo.

## How it works

```
books.json (your watchlist)
        │
        ▼
sources.py  ──►  eBay / Etsy / AbeBooks / Biblio APIs
        │
        ▼
matcher.py  ──►  filters out wrong editions, reprints, mispriced listings
        │
        ▼
emailer.py  ──►  sends one email per new match
```

A GitHub Actions workflow (`.github/workflows/check_books.yml`) runs this
twice a day, using API credentials stored as encrypted GitHub secrets.

## Quick start

1. **Get this project into its own GitHub repo:**

   ```bash
   cd rare-book-tracker
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create rare-book-watchlist --private --source=. --push
   # no gh CLI? create an empty repo on github.com, then:
   #   git remote add origin <your-repo-url>
   #   git branch -M main
   #   git push -u origin main
   ```

2. **Get API credentials** for at least eBay (required) — see [Setting up
   each source](#setting-up-each-source) below.

3. **Add your credentials as GitHub secrets:** repo → Settings → Secrets
   and variables → Actions → New repository secret. Full list in
   [Secrets reference](#secrets-reference).

4. **Allow the workflow to commit its own state:** Settings → Actions →
   General → Workflow permissions → "Read and write permissions" → Save.

5. **Edit `books.json`** with the books you're actually looking for (see
   [Configuring your watchlist](#configuring-your-watchlist)).

6. **Test it:** Actions tab → Rare Book Watchlist → Run workflow.

From there it runs itself, twice a day, for free.

## Setting up each source

### eBay (required)

1. Create a free account at [developer.ebay.com](https://developer.ebay.com/) and go to **My Account → Application Keys**.
2. Create a **Production** keyset and copy the **App ID (Client ID)** and **Cert ID (Client Secret)**.
3. On the keyset's **Notifications** page, resolve the **Marketplace Account Deletion** requirement — this is mandatory before eBay will activate the keyset for API calls. If your app only searches public listings and never accesses member account data, you qualify for the **exemption**: toggle it on, pick the closest reason ("doesn't access/store eBay user data"), and save.
4. Set `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` as secrets.

By default, both `EBAY_US` and `EBAY_GB` are searched (eBay's API scopes
each search to one country site at a time, so this covers the two biggest
markets for rare/antiquarian books). To change or expand this, add an
`EBAY_MARKETPLACES` secret with a comma-separated list, e.g.
`EBAY_US,EBAY_GB,EBAY_DE,EBAY_FR,EBAY_AU`. See eBay's
[MarketplaceIdEnum](https://developer.ebay.com/api-docs/buy/browse/types/gct:MarketplaceIdEnum)
for the full list of valid codes — not every listed code is a live
marketplace, so stick to ones eBay's docs describe as an actual site
rather than "reserved for future use."

### Etsy (optional)

1. Register at [etsy.com/developers](https://www.etsy.com/developers/register) and create a new app.
2. Copy the **Keystring** and set it as `ETSY_API_KEY`.

### AbeBooks (optional, most precise filtering)

AbeBooks' Search Web Services supports true server-side filtering on
publisher, exact publication year, first-edition tagging, and price
range — more precise than eBay/Etsy's plain keyword search. Access
requires joining their Affiliate Program:

1. Join the [Affiliate Program](https://www.abebooks.com/books/AffiliateProgram/) (free).
2. Email `affiliate@abebooks.com` requesting a Client Key, including: the IP address you'll make requests from, your URL, your email, a technical contact name, and your Affiliate ID.
3. Set the key you receive as `ABEBOOKS_CLIENT_KEY`.

Note that AbeBooks' application asks for a specific IP address. If your
setup runs from an environment with a dynamic IP (as GitHub Actions
does), confirm with AbeBooks whether Client Key access is IP-restricted
before relying on this source.

### Biblio (optional)

Biblio's API isn't publicly self-serve. Join their free [affiliate
program](https://www.biblio.com/affiliate_program/), then email their
marketing team requesting Inventory API access. Set the key as
`BIBLIO_API_KEY`, and confirm the endpoint/response format in
`search_biblio()` (`sources.py`) against the documentation they send you.

Any source without a configured key is skipped automatically — nothing
else needs to change.

## Configuring your watchlist

Each entry in `books.json` supports:

| Field | Required? | Effect |
|---|---|---|
| `title` | yes | Search query and fuzzy-matched against listing titles |
| `author` | recommended | Last name must appear in the listing text |
| `isbn` | optional | Exact match short-circuits every other text check — most reliable when available |
| `publisher` | optional | Must appear in the listing |
| `year` | optional | Must appear in the listing |
| `edition_keywords` | optional | At least one must appear (e.g. `["first edition", "1st edition"]`) |
| `exclude_keywords` | optional | Rejected if any appear (e.g. `["book club", "reprint", "facsimile"]`) |
| `min_price` | optional | Rejected if priced below this — filters out likely reprints/scams |
| `max_price` | optional | Rejected if priced above this |

Leave a field blank and that check is skipped. The more specific a book
is (ISBN, or publisher + year + edition keywords), the fewer false
positives you'll get.

To tune a tricky entry, run `DEBUG=1 python main.py` locally — it prints,
for every listing found, exactly which check passed or failed and why.
`test_matcher.py` has worked examples.

**Keeping your watchlist private:** add a `BOOKS_JSON` secret containing
your real list as JSON (same shape as `books.json`). `main.py` uses it
automatically if present, and `books.json` on disk becomes just harmless
example data safe to leave in the repo.

## Secrets reference

| Secret | Required? | Value |
|---|---|---|
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | Yes | From eBay setup above |
| `EBAY_MARKETPLACES` | No | Comma-separated eBay sites to search; defaults to `EBAY_US,EBAY_GB` |
| `ETSY_API_KEY` | No | From Etsy setup above |
| `ABEBOOKS_CLIENT_KEY` | No | From AbeBooks setup above |
| `BIBLIO_API_KEY` | No | From Biblio setup above |
| `EMAIL_ADDRESS` | Yes | Gmail address sending alerts |
| `EMAIL_APP_PASSWORD` | Yes | [App password](https://myaccount.google.com/apppasswords) for that account (requires 2-Step Verification) |
| `EMAIL_TO` | No | Recipient(s) — one address or several comma-separated; defaults to `EMAIL_ADDRESS` |
| `BOOKS_JSON` | No | Your real watchlist, if you want it kept out of the repo |

Using a non-Gmail provider? Change the `smtplib.SMTP_SSL(...)` line in
`emailer.py`; nothing else depends on it.

## Security

- No credential is ever hardcoded — everything is read via `os.environ`
  at runtime from GitHub Actions secrets, which are encrypted at rest and
  redacted from logs automatically.
- `.github/workflows/secret-scan.yml` runs [gitleaks](https://github.com/gitleaks/gitleaks)
  on every push as a second layer of defense against an accidentally
  committed credential.
- Your watchlist itself can be kept out of git entirely via the
  `BOOKS_JSON` secret described above.

## Limitations

- Matching is a heuristic, not a certainty — always check the actual
  listing before buying anything expensive.
- eBay's search results include title and subtitle only, not the full
  listing description (usually enough, since sellers pack edition details
  into the title).
- GitHub Actions' scheduled runs are best-effort and can be delayed by a
  few minutes under load — not a hard real-time guarantee.
- Everything here comfortably fits inside eBay's, Etsy's, AbeBooks', and
  GitHub Actions' free usage tiers, even with a large watchlist.

## Project structure

```
books.json                        example watchlist (or template, if using BOOKS_JSON)
main.py                           orchestrates search → match → email
sources.py                        one function per marketplace
matcher.py                        edition-aware filtering logic
emailer.py                        HTML email alerts
storage.py                        tracks already-notified listings
test_matcher.py                   matcher sanity tests
.github/workflows/check_books.yml scheduled search (twice daily)
.github/workflows/secret-scan.yml credential leak scanning
data/                             state committed back by the workflow
```

## Adding another source

Every function in `sources.py` takes `(book, limit)` — the full watchlist
entry — and returns a list of listings in the same normalized shape
(documented at the top of the file). Add a new `search_yoursite()`
function and append it to the `SOURCES` list in `main.py`. Prefer an
official API if the site has one; if it doesn't, check both its
`robots.txt` and its terms of service before writing anything that
fetches its pages automatically.
