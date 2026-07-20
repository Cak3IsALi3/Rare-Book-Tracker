# Rare Book Watchlist

Watches eBay and Etsy for specific rare/collectible books and emails you
(with photo, price, and a link) the moment a matching listing appears.
Runs twice a day, for free, on GitHub's servers — your computer doesn't
need to be on.

## How this is built, and why

**eBay and Etsy are searched through their official APIs**, not by
scraping the website. This is the actual fix for "how do I stop eBay from
blocking this": sanctioned API access doesn't get rate-limited or banned
the way a scraper impersonating a browser eventually does, because you're
using the door the site built for this instead of picking the lock on the
front door. Both are free to sign up for as an individual developer.

**AbeBooks is not included as an automated source.** It's arguably the
best single site for this use case, but its [Search Web Services
terms](https://www.abebooks.com/docs/affiliateprogram/webservices/terms-printable.shtml)
explicitly prohibit querying their database by "any means other than the
Search Program, including without limitation any robots, spiders,
crawlers, scraping" — and their public affiliate API was discontinued for
new developers some years ago. Building a scraper for it would mean
designing specifically to evade detection on a site whose terms rule that
out, so instead: **AbeBooks has its own native "Want" feature** — tell it
what you're looking for at [abebooks.com/wishlist](https://www.abebooks.com/book-search/title/wishlist/)
and it emails you when a match appears. It doesn't have the same
edition-level filtering this project does, but it's free, official, and a
five-minute setup. Worth adding as a complement.

**Biblio.com** has an inventory API but it's gated, not self-serve —
`sources.py` includes a scaffold for it (see "Optional: Biblio" below).

## Where your secrets actually live

Nothing in this project ever writes a real API key or password into a file
that gets committed. Every credential is read at runtime with
`os.environ.get(...)` (see `sources.py`, `emailer.py`) and supplied by
**GitHub Actions Secrets** — added once via Settings -> Secrets and
variables -> Actions, encrypted at rest, never viewable again through the
UI (only overwritable), decrypted only inside the runner's memory for the
duration of a run, and automatically redacted to `***` if a value ever
does hit the logs. `.gitignore` also excludes `.env` so a local secrets
file can't be committed by accident.

As a second, independent layer, `.github/workflows/secret-scan.yml` runs
[gitleaks](https://github.com/gitleaks/gitleaks) — a free, open-source
scanner — on every push, and would fail the run if a real-looking
credential ever landed in a file. This matters because GitHub's own native
push-protection is free and automatic only for *public* repos; on a
*private* repo under an individual account it requires a paid GitHub
Advanced Security license, so gitleaks is what closes that gap for free.

If you ever do suspect a key leaked (e.g. you see it un-masked in a log,
or you accidentally committed one before adding it to `.gitignore`):
regenerate it at the source (eBay/Etsy/Biblio dashboard, or a fresh Gmail
App Password) and update the GitHub secret. All of these are free and
instant to rotate — none of this data is worth protecting with anything
more elaborate than "don't hardcode it, and regenerate it if you're ever
unsure."

## What you get

- `books.json` — your watchlist. Add/remove/edit books freely; the search
  loop just iterates over whatever's in this file.
- Edition-aware filtering — matches on title/author similarity plus
  whichever of ISBN, publisher, year, required edition keywords, excluded
  keywords, and a price ceiling you fill in per book (see field reference
  below). This is what keeps a $6 paperback reprint from triggering an
  alert meant for a $4,000 first edition.
- One HTML email per new match, with the listing photo inline.
- Runs on a schedule via GitHub Actions — no server, no always-on machine.

## Setup

### 1. Get an eBay API key (free, ~5 minutes)

1. Create an account at [developer.ebay.com](https://developer.ebay.com/) and sign in.
2. Go to **My Account → Application Keys**.
3. Create a **Production** keyset (not Sandbox).
4. Copy the **App ID (Client ID)** and **Cert ID (Client Secret)**.
5. **Required before eBay will activate the keyset for API calls:** on the
   keyset's **Notifications** page, eBay requires every developer to either
   subscribe to or request exemption from "Marketplace Account Deletion"
   notifications (GDPR-driven — it's how eBay tells third-party apps to
   delete a user's data if that user deletes their eBay account). This
   project only searches public listings via the client-credentials OAuth
   flow and never touches any eBay member's personal/account data, so it
   qualifies for the **exemption**: toggle "Exempted from Marketplace
   Account Deletion," pick the reason closest to "doesn't access/store
   eBay user data," and save. No code or endpoint needed. Skipping this
   step entirely is what usually causes a brand-new production keyset to
   silently fail every call.

### 2. Get an Etsy API key (free, ~5 minutes)

1. Register at [etsy.com/developers](https://www.etsy.com/developers/register).
2. Create a new app (any name/description; you don't need a callback URL
   for this use case since we only call public read-only endpoints).
3. Copy the **Keystring** — that's your `ETSY_API_KEY`.

### 3. (Optional) Biblio

Biblio's API isn't public. Join their free [affiliate
program](https://www.biblio.com/affiliate_program/), then email their
marketing team from your registered account address asking for Inventory
API access. When you get a key back, drop it into `BIBLIO_API_KEY` and
fill in the real endpoint/field names in `search_biblio()` in
`sources.py` from the documentation they send you (it isn't public, so
the current function is a scaffold rather than a tested integration).
Leave `BIBLIO_API_KEY` unset and this source is skipped automatically.

### 4. Create a Gmail App Password

Regular Gmail passwords don't work for SMTP anymore.

1. Turn on 2-Step Verification on the sending Gmail account, if it isn't already.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Create an app password (name it anything, e.g. "book watchlist") and copy the 16-character code.

Using a different provider (Outlook, a transactional service, etc.)? Just
change the `smtplib.SMTP_SSL(...)` line in `emailer.py` — the rest of the
project doesn't care how the email gets sent.

### 6. Add your secrets

In the repo on GitHub: **Settings → Secrets and variables → Actions → New
repository secret**. Add:

| Secret | Value |
|---|---|
| `EBAY_CLIENT_ID` | from step 1 |
| `EBAY_CLIENT_SECRET` | from step 1 |
| `ETSY_API_KEY` | from step 2 |
| `BIBLIO_API_KEY` | from step 3 (optional — skip if not using Biblio) |
| `EMAIL_ADDRESS` | the Gmail address sending alerts |
| `EMAIL_APP_PASSWORD` | from step 4 |
| `EMAIL_TO` | where alerts should be sent — one address, or several separated by commas (e.g. `me@example.com, partner@example.com`); optional, defaults to `EMAIL_ADDRESS` |

### 7. Allow the workflow to commit

**Settings → Actions → General → Workflow permissions** → select **"Read
and write permissions"** → Save. (This lets the workflow save its
"already emailed you about this" state back to the repo — see
"How duplicate alerts are avoided" below.)

### 8. Test it

**Actions tab → Rare Book Watchlist → Run workflow.** Check the run's log
to confirm each source found listings; if `books.json` still has the
sample entries, you should see real eBay/Etsy results in the log (an
actual match/email depends on whether a matching copy happens to be
listed right now).

From here it runs itself, twice a day, at 08:00 and 20:00 UTC (edit the
`cron` line in `.github/workflows/check_books.yml` to change the times —
[crontab.guru](https://crontab.guru) helps with the syntax).

## Keeping your watchlist private

By default `books.json` is a plain file in the repo — fine on a private
repo, but visible to anyone if the repo is ever made public (e.g. for the
free secret-scanning benefit mentioned above), and visible to any
collaborator either way.

To keep it out of git entirely: add a `BOOKS_JSON` secret (Settings ->
Secrets and variables -> Actions) containing your real watchlist as JSON —
paste the whole array in, same shape as `books.json`. `main.py` checks for
that secret first and uses it if present; `books.json` on disk is then
just harmless example data that's safe to leave committed.

The tradeoff: editing a secret through GitHub's UI is clunkier than
editing a tracked file — no `git diff`, no history, no easy review before
a change goes live. A reasonable middle ground is to keep a real copy
locally (in a file `.gitignore` already excludes if you name it e.g.
`books.local.json`), edit that with your usual tools, and paste its
contents into the `BOOKS_JSON` secret whenever you change something.

## Editing your watchlist

Each entry in `books.json` supports:

| Field | Required? | Effect |
|---|---|---|
| `title` | yes | Used for the search query and fuzzy-matched against listing titles |
| `author` | recommended | Last name must appear in the listing text |
| `isbn` | optional | If set and the listing exposes an ISBN, an exact match short-circuits every other text check — the most reliable option when the book has one |
| `publisher` | optional | Must appear in the listing text if set |
| `year` | optional | Must appear in the listing text if set |
| `edition_keywords` | optional | At least one must appear (e.g. `["first edition", "1st edition"]`) |
| `exclude_keywords` | optional | Listing is rejected if *any* appear (e.g. `["book club", "reprint", "facsimile"]`) |
| `min_price` | optional | Listing is rejected if priced *below* this — useful for genuinely rare books, where a suspiciously cheap "match" is usually a reprint, misidentified listing, or scam rather than a find |
| `max_price` | optional | Listing is rejected if priced above this |

Leave a field blank/empty and that check is simply skipped — an entry with
just `title` + `author` will cast a much wider net than one with every
field filled in. For anything genuinely rare, filling in `publisher`,
`year`, and `edition_keywords` (or just `isbn` when the book has one) is
what actually prevents false positives.

**To tune a tricky entry**, run `DEBUG=1 python main.py` locally (see
below) — it prints, for every listing found, exactly which check passed or
failed and why. `test_matcher.py` also has some worked examples you can
copy from.

## How duplicate alerts are avoided

`data/seen_items.json` records every listing already emailed about. The
workflow commits this file (and `data/last_run.json`, a timestamp) back to
the repo after every run. That second file matters for a reason that's
easy to miss: GitHub auto-disables a scheduled workflow after 60 days with
no commits to the repo, and a quiet stretch where nothing matches would
otherwise mean no commits at all. The timestamp file changes every run
regardless, which keeps the schedule alive.

## Adding another site later

Every function in `sources.py` returns the same shape (see the module
docstring), so `main.py` doesn't need to know which site a listing came
from — add a new `search_yoursite()` function and append it to the
`SOURCES` list in `main.py`.

If a site has an API, use it — that's always the sturdier option. If it
doesn't, check both its `robots.txt` and its terms of service before
writing a scraper for it (as the AbeBooks example above shows, a site can
allow `robots.txt` crawling in general while still contractually
prohibiting automated querying of its listings — check the actual terms,
not just `robots.txt`). Keep request rates low and identify your script
honestly. This project deliberately doesn't include tooling for rotating
proxies/user-agents or otherwise defeating bot detection — that's a losing
arms race against any site that doesn't want it, and the API-first
approach above is the version of "won't get blocked" that actually holds
up.

## Testing locally

```bash
pip install -r requirements.txt
export EBAY_CLIENT_ID=...
export EBAY_CLIENT_SECRET=...
export ETSY_API_KEY=...
export EMAIL_ADDRESS=...
export EMAIL_APP_PASSWORD=...
python main.py          # normal run
DEBUG=1 python main.py  # verbose: prints match/reject reasoning for every listing found
python test_matcher.py  # matcher logic sanity checks, no API keys needed
```

## Limitations worth knowing about

- Matching is a heuristic, not a certainty — always click through and look
  at the actual listing/photos before buying anything expensive. Treat
  alerts as "worth a look," not "verified."
- eBay's Browse API search summaries don't include the full listing
  description, only title + subtitle — usually enough since sellers pack
  edition details into the title, but occasionally a match will hinge on
  something only in the full description. `sources.py` notes where to add
  a per-item detail fetch if you need this.
- GitHub Actions' scheduled runs can be delayed by a few to dozens of
  minutes during high load — it's not a hard real-time guarantee, which is
  fine for a twice-a-day check but worth knowing.
- Free-tier usage here is small: two runs a day, a handful of API calls
  per book, well inside eBay's, Etsy's, and GitHub Actions' free
  allowances even with a long watchlist.
