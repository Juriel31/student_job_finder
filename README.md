# Job Watchtower

A GitHub-hosted board that scans the job portals you list, checks new
postings against your keywords, and shows matches on a small web dashboard —
no server required, just GitHub Actions + GitHub Pages.

## How it works

- `config/sources.csv` — one row per company/portal: `company`, `url`,
  `keywords`. `config/sources.csv` already has all 73 companies you listed,
  one per row — you just need to paste each company's careers-page URL into
  the `url` column (see "About the company list" below for why I couldn't
  fill these in myself). Example of a filled-in row:
  ```csv
  company,url,keywords
  Infineon,https://careers.infineon.com/germany,"fpga, asic"
  Rohde & Schwarz,https://careers.rohde-schwarz.com,
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

- `.github/workflows/check-jobs.yml` — runs every 15 minutes (also runs
  automatically any time you edit `sources.csv`, and can be triggered
  manually from the **Actions** tab).

- `scripts/check_jobs.py` — visits each portal, pulls every link on the page,
  and checks whether the link text contains any of your keywords (matching
  is case-insensitive and substring-based, so `"design"` will also catch
  `"Senior Product Designer"`). New matches are written to `docs/data/`.

- `docs/index.html` — the dashboard, served by GitHub Pages, reads
  `docs/data/*.json` and displays matches, a live countdown to the next
  scan, and per-source status (so you can see if a portal is blocking the
  scan or timing out).

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
I wasn't able to look up and verify the actual careers-page URL for each of
your 73 companies — guessing them would risk giving you broken or wrong
links. `config/sources.csv` has every company name pre-filled with an empty
`url` column for exactly this reason.

Two ways to finish this:
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

## Notes and limitations (read before relying on this)

- **This is link-scraping, not a real job-board API.** It works well for
  simple listing pages (e.g. many Greenhouse/Lever/Workable career pages),
  but sites that load listings via JavaScript after the page loads, or that
  actively block scrapers (LinkedIn and Indeed are the notable ones), may
  return no results or get blocked. If a portal shows an error status on
  the dashboard, that's usually why.
- **"Immediate" means within the scan interval.** 15 minutes is the fastest
  practical schedule on GitHub's free tier; a webhook-based instant push
  isn't available because job boards don't offer that.
- **No push notifications are wired up** — per your preference, matches
  only show up on the web dashboard. If you ever want a ping (Telegram,
  email, etc.) the moment a match is found, that's a small addition to
  `check_jobs.py`, and I'm happy to add it later.
- Respect each site's terms of service and `robots.txt` — this is meant for
  your own personal job search, at a modest polling interval.
