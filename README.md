# Job Watchtower

A GitHub-hosted board that scans the job portals you list, checks new
postings against your keywords, and shows matches on a small web dashboard —
no server required, just GitHub Actions + GitHub Pages.

## How it works

- `config/sources.csv` — one row per company/portal: `company`, `location`,
  `url`, `keywords`. All 74 companies are pre-loaded (including
  Maschinenfabrik Reinhausen GmbH), with the location info you gave me kept
  as a reference column (it isn't used by the scraper, it's just there so
  you can see everything in one place). I've already filled in the `url`
  column for the 5 companies where you gave me a direct link:
  **Devritech, Racyics, Infineon, Teleconnect, Chipglobe.** The other 69
  still have an empty `url` cell for you to fill in — see "About the company
  list" below.

  Example of a fully filled-in row:
  ```csv
  company,location,url,keywords
  Infineon,"Dresden, other",https://www.infineon.com,"fpga, asic"
  ```
  - `keywords` is optional. Leave it blank to pull in *every* listing from
    that company's page (you can still narrow down using the employment-type
    filter and search box on the dashboard). Fill it in (comma-separated,
    whole field in quotes if more than one) to only match postings whose
    title contains one of those words, e.g. `"fpga, asic, hardware"`.

- **Employment-type filter** — the dashboard now has filter chips: All /
  Working student / Internship / Full time / Unspecified. Every matched
  posting is auto-tagged by scanning its title for common English and
  German phrasing (`Werkstudent`, `Praktikum`, `Vollzeit`, `internship`,
  `full-time`, etc.). If a title doesn't mention any of these, it's tagged
  "Unspecified" — many company career pages only show this in the full job
  description, not the listing title, so expect some postings to land here
  even when they do have a clear type.

- `.github/workflows/check-jobs.yml` — runs every **5 minutes** (GitHub's
  practical floor for scheduled workflows — see "Why not faster than 5
  minutes?" below), also runs automatically any time you edit
  `sources.csv`, and can be triggered manually from the **Actions** tab.

- `scripts/check_jobs.py` — visits each portal, pulls every link on the page,
  and checks whether the link text contains any of your keywords (matching
  is case-insensitive and substring-based, so `"design"` will also catch
  `"Senior Product Designer"`). Retries transient network errors twice
  before marking a source as down. New matches are written to `docs/data/`.
  - **Quiet by design**: if a scan finds no new postings and no source's
    health status changed, it writes nothing and the workflow commits
    nothing that run. The board only changes when there's something real to
    show — no flicker, no noise in your git history.
  - **5-day retention**: a matched posting drops off the board 5 days after
    it was first detected (still genuinely new postings always get the
    "NEW" badge; this just keeps the list from growing forever).

- `docs/index.html` — the dashboard, served by GitHub Pages, reads
  `docs/data/*.json` and displays matches, a live countdown to the next
  scan, and per-source status (so you can see if a portal is blocking the
  scan or timing out).

### Why not faster than 5 minutes?

GitHub's scheduled Actions don't run more often than every 5 minutes even if
you write a tighter cron expression, and can run a little late under load —
there's no true "instant" option without a webhook, which job boards don't
offer. 5 minutes is the practical ceiling for "immediate" on this
architecture.

### Reliability additions (since this runs unattended for months)

- **Retry with backoff** — a single flaky response no longer marks a source
  as broken; the script retries twice (4s apart) before giving up.
- **No overlapping runs** — a concurrency lock stops two scans from ever
  running at once and racing each other on the git push.
- **Safe push** — the workflow rebases against the latest commit before
  pushing, in case a manual run and a scheduled run land close together.
- Worth adding later if you want it: a push notification (Telegram/email/
  ntfy.sh) the moment a genuinely new match is found, and/or an alert if a
  source has been erroring for several scans in a row (rather than just a
  status dot you have to notice yourself).

## Setup (10 minutes)

1. **Create a new GitHub repo** and push everything in this folder to it
   (as the root of the repo).

2. **Turn on GitHub Pages**
   Repo → Settings → Pages → Source: "Deploy from a branch" → Branch:
   `main`, folder: `/docs` → Save.
   Your dashboard will be live at `https://<your-username>.github.io/<repo-name>/`.

3. **Let Actions write back to the repo**
   Repo → Settings → Actions → General → Workflow permissions →
   select "Read and write permissions" → Save.
   (The workflow needs this to commit updated match data after each scan.)

4. **Add your portals and keywords**
   Edit `config/sources.csv` (directly on GitHub, or locally and push).
   Committing a change to this file automatically kicks off a scan.

5. **Run it once manually to check it works**
   Repo → Actions → "Check job postings" → Run workflow.
   Then check the Actions log, and refresh your Pages URL.

That's it — from then on it checks every 15 minutes on its own.

## About the company list — one thing I couldn't do

I don't currently have web browsing/search enabled in this conversation, so
I wasn't able to look up and verify the actual careers-page URL for every
company — guessing them would risk giving you broken or wrong links. I
filled in the 5 URLs you gave me directly; the rest are blank for you (or
me, once search is on) to fill in.

**One more thing worth knowing about the 5 I did fill in:** some of those
(e.g. `infineon.com`) are the company's general homepage, not necessarily
their specific job-listings page. The scraper works best pointed directly at
a page that actually lists open roles (often something like
`/careers`, `/karriere`, or `/jobs`) — scanning a homepage may pull in mostly
navigation links and miss the postings, or match nothing at all. Worth
clicking into each site and grabbing the URL of their actual jobs page
before your first scan, especially for the bigger companies.

Two ways to finish the rest:
1. **Fastest** — paste each company's careers-page URL into the sheet
   yourself (this was your original plan anyway).
2. **Turn on web search** in this chat and ask me to look up the URLs — I
   can then fill in the CSV for you (I'd still recommend spot-checking a
   handful, since some of the smaller/regional firms on your list have
   little public web presence and I may not find a direct listings page for
   every one).

**On "Germany only":** since every company on your list is Germany-based,
most of what these pages list will already be German roles. If a company
also has non-German offices publishing to the same page, use the `keywords`
column to add a German city or "Germany" as one of the terms (e.g.
`"fpga, dresden"`), since location isn't reliably reflected in the link text
alone otherwise.

- **Posted date** — each row now shows the date the posting itself claims to
  have gone up (parsed from a `<time>` tag or common date phrasing near the
  listing, EN + DE, including relative phrasing like "3 days ago" / "vor 2
  Tagen"). This is separate from "detected", which is when *our* scan first
  found it — a posting can be a week old the first time we happen to catch
  it. If the page doesn't expose a date anywhere near the listing, it shows
  **"No date"** rather than guessing.

## Notes and limitations (read before relying on this)

- **This is link-scraping, not a real job-board API.** It works well for
  simple listing pages (e.g. many Greenhouse/Lever/Workable career pages),
  but sites that load listings via JavaScript after the page loads, or that
  actively block scrapers (LinkedIn and Indeed are the notable ones), may
  return no results or get blocked. If a portal shows an error status on
  the dashboard, that's usually why.
- **"Immediate" means within 5 minutes.** That's the fastest practical
  schedule on GitHub's free tier; a webhook-based instant push isn't
  available because job boards don't offer that.
- **No push notifications are wired up** — per your preference, matches
  only show up on the web dashboard. If you ever want a ping (Telegram,
  email, etc.) the moment a match is found, that's a small addition to
  `check_jobs.py`, and I'm happy to add it later.
- Respect each site's terms of service and `robots.txt` — this is meant for
  your own personal job search, at a modest polling interval.
