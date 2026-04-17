# Travel Price Tracker

Tracks flight and hotel prices every day, stores the history, fires GitHub Issue
alerts when prices drop, and publishes a dashboard via GitHub Pages — all for
free, all running in the cloud, no laptop required.

```
┌───────────────────────────────────────────────────────────────┐
│  Every day at 09:00 IST (03:30 UTC):                          │
│                                                               │
│   GitHub Actions  ──►  Amadeus API  ──►  CSV files in repo    │
│                            │                                  │
│                            ├──►  GitHub Issue (price drop)    │
│                            └──►  Dashboard on GitHub Pages    │
└───────────────────────────────────────────────────────────────┘
```

---

## What you'll need

1. A free **GitHub** account (you almost certainly have one)
2. A free **Amadeus for Developers** account (5 minutes to sign up)
3. About **20 minutes** for first-time setup. After that, zero maintenance.

---

## Setup, step by step

### Step 1 — Get an Amadeus API key (free)

1. Go to <https://developers.amadeus.com> and click **Register**.
2. Verify your email and log in.
3. Click **My Self-Service Workspace** → **Apps** → **Create new app**.
4. Give it any name (e.g. `price-tracker`) and click **Create**.
5. You'll see two strings: **API Key** and **API Secret**. Keep this tab open;
   you'll paste these into GitHub in step 4.

You're on the **test environment**, which is free with a generous monthly quota
(thousands of flight searches per month). Plenty for daily tracking.

### Step 2 — Create a GitHub repo from these files

1. On GitHub, click the **+** in the top-right → **New repository**.
2. Name it `travel-price-tracker` (or anything).
3. Choose **Public** (required for free GitHub Pages — your dashboard URL will
   be public, but no one will know it exists unless you share it).
4. Don't tick "Add a README" — we already have one.
5. Click **Create repository**.

Now you need to upload the files from this bundle into that empty repo:

- **Easiest way (browser only):** on the new empty repo page, click
  **uploading an existing file**, drag in every file and folder from this
  bundle, scroll down and click **Commit changes**.
- **Git-CLI way:** clone the empty repo, copy the bundle contents in,
  `git add . && git commit -m "init" && git push`.

### Step 3 — Add your Amadeus keys as secrets

1. In your repo, go to **Settings** (top of repo) → **Secrets and variables**
   (left sidebar) → **Actions** → **New repository secret**.
2. Add two secrets, one at a time:
   - Name: `AMADEUS_API_KEY` → Value: paste the API Key from step 1
   - Name: `AMADEUS_API_SECRET` → Value: paste the API Secret from step 1

Click **Add secret** after each one. They'll be encrypted; even you won't be
able to read them back.

### Step 4 — Enable GitHub Pages

1. Still in **Settings**, click **Pages** in the sidebar.
2. Under **Build and deployment** → **Source**, choose **GitHub Actions**.
3. That's it. No URL yet — it'll appear after the first run.

### Step 5 — Trigger the first run manually

The collector is scheduled to run daily, but the first run won't happen until
tomorrow's scheduled time. To kick it off now:

1. Go to the **Actions** tab in your repo.
2. If GitHub asks "Workflows aren't being run on this forked repository"
   click **I understand my workflows, go ahead and enable them**.
3. Click **Daily price collector** in the left sidebar.
4. Click **Run workflow** → **Run workflow** (the green button).

Wait ~1-2 minutes. The job icon goes from yellow (running) to green (success)
or red (failed). Click into the run to see logs.

### Step 6 — Open your dashboard

Once the workflow has succeeded, go back to **Settings** → **Pages**. There
will now be a URL at the top, something like:

    https://<your-github-username>.github.io/travel-price-tracker/

Open it — you'll see your first day of price data. Each subsequent day, the
collector adds another point and the chart fills in.

---

## Customising what's tracked

Edit **`searches.yaml`** in the repo (you can edit straight in the browser:
click the file → pencil icon → make changes → **Commit changes**). Add or
remove flight/hotel blocks. Format and examples are documented inline.

After committing, the next scheduled run picks up the new searches. You can
also trigger a manual run anytime via the Actions tab.

---

## Customising alerts

Each search has an `alert_below` threshold. When the cheapest result drops
**below** that number **and** sets a new all-time low for that search, the
collector opens a GitHub Issue in your repo. You can:

- Subscribe to repo notifications to get alerts via email
- Install the GitHub mobile app for push notifications
- Use any GitHub-Issue-to-other-tool integration (Slack, Telegram, etc.)

To stop a particular alert, set `alert_below: 0` (or remove the field).

---

## Schedule and timezone

The default schedule runs once a day at **03:30 UTC = 09:00 IST**. Edit
`.github/workflows/daily-collect.yml`, line `- cron: "30 3 * * *"`, to change
it. [crontab.guru](https://crontab.guru) is handy for cron syntax.

> ⚠️ GitHub Actions cron jobs can drift by 5-15 minutes during peak times,
> and may skip a run during heavy load on GitHub's side. For travel price
> tracking, this is fine.

---

## Costs

- **GitHub Actions:** free tier on public repos — unlimited minutes for
  scheduled jobs like this.
- **GitHub Pages:** free for public repos.
- **Amadeus test environment:** free; monthly quota is generous for daily
  tracking of ~10-20 searches.
- **GitHub Issues:** free.

Total: **₹0/month**.

---

## Troubleshooting

**Workflow run failed with "AMADEUS_API_KEY must be set":** secrets weren't
added correctly — re-do step 3 and check the names match exactly.

**Workflow run failed with `429 too many requests`:** you hit the Amadeus
free quota. Either wait until next month or reduce the number of searches
in `searches.yaml`.

**No data appearing in the dashboard:** check the Actions tab → most recent
run → expand "Run collector" step. Errors show up there.

**Hotel API returning empty results:** Amadeus's test environment has limited
hotel data — some cities have very little or no inventory in test. Try
different `city_code` values (BLR, BOM, DEL, DXB usually have good test data),
or move to the production environment (still free up to your monthly quota,
just requires extra signup).

**Want to track *current* prices, not future trip dates:** the dates in
`searches.yaml` must be in the future — Amadeus can't quote prices for past
dates. To track a route generally, pick a fixed date a few months out and
update it once in a while.

---

## File map

```
travel-price-tracker/
├── README.md                          ← you are here
├── searches.yaml                      ← edit this to change what's tracked
├── requirements.txt                   ← Python dependencies
├── .github/workflows/
│   └── daily-collect.yml              ← the cron job
├── collector/
│   ├── collect.py                     ← main entry point
│   ├── amadeus_client.py              ← Amadeus API wrapper
│   ├── storage.py                     ← CSV append / read
│   ├── alerts.py                      ← GitHub Issues alerts
│   └── dashboard.py                   ← HTML dashboard generator
├── data/
│   ├── prices_flights.csv             ← created by first run
│   └── prices_hotels.csv              ← created by first run
└── docs/
    └── index.html                     ← published via GitHub Pages
```
