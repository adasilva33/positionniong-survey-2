# Positioning Survey — Automated Form Generation — Project Brief

## Context / goal
Monthly street positioning survey (per Woodline's existing process, see reference
screenshots): for each **sector**, one survey form is sent out; within that form, each
**subsector** is a section asking respondents to rank BBG tickers into:
- Consensus Long: Ticker 1 (strongest) / Ticker 2 / Ticker 3
- Consensus Short: Ticker 1 (strongest) / Ticker 2 / Ticker 3
- Contentious: Ticker 1–3

That's 9 questions per subsector. Example structure seen in the live Woodline MS Forms
survey: **Financials** sector → subsectors **Alternatives, Exchanges, Investment Banks,
Traditional Banks**. Same pattern for **Healthcare** → **BioPharma, Medical Devices**, etc.

Current pain points being solved: manual ticker retyping/harmonization by respondents,
no visibility into who has responded, manual follow-up, and MS Forms not supporting a
real dropdown built from an external list.

## Decision made
Moving off Microsoft Forms (no API for form creation) to the **Google Forms API**,
which does support programmatic form + question creation. IT/compliance approval to be
confirmed for cross-platform use with external (sell-side) respondents.

## What exists today (proof of concept)
File: `create_positioning_survey_form.py` (already built and running successfully).

- Creates ONE Google Form with 3 sections (Consensus Longs / Consensus Shorts /
  Contentious), each with 3 dropdown questions, populated with placeholder tickers
  (`TICKER_1`, `TICKER_2`, ...).
- **Note the section structure differs from the real target**: the POC sections by
  long/short/contentious; the real requirement (per the reference survey) sections by
  **subsector**, with all 9 long/short/contentious questions inside each subsector
  section. This needs to change in the next iteration.
- Auth: OAuth 2.0 **Desktop app** client (not Web app — that caused a
  `redirect_uri_mismatch`). `credentials.json` (downloaded from Google Cloud Console)
  + cached `token.json` after first browser consent. Google Cloud project is currently
  in **Testing** mode with the user's own account added as a test user (not yet
  verified/published — fine for internal/POC use, may need review for broader external
  rollout).
- Confirmed: forms created on a personal (non-Workspace) Google account do **not**
  require respondents to sign in, as long as **Settings → Responses → "Limit to 1
  response"** stays OFF and email collection stays off. This setting is not exposed via
  the API — must be set manually in the Forms UI per form, or handled by cloning a
  pre-configured template form instead of creating from scratch each time.
- Dropdown/choice options: no official hard limit from Google, but usability degrades
  well past ~50–100 options (flat list, no type-ahead search) — worth checking the
  largest subsector's ticker count before assuming plain dropdowns work everywhere.

## New requirements (next build phase)
1. **Excel-driven, multi-sector/subsector generation.**
   Input file: `positioning_survey_universe.xlsx` (template attached), sheet
   `Universe` with columns `Sector | Subsector | Ticker` — one row per ticker.
   Running the script should:
   - Group rows by `Sector`, then by `Subsector` within each sector.
   - Create **one Google Form per Sector**.
   - Within that form, add **one section per Subsector**, each with the 9 questions
     (3 long / 3 short / 3 contentious), and each question's dropdown populated with
     that subsector's tickers only.
   - Re-running the script should create a fresh form each time (v1) — consider later
     whether re-running should instead update an existing form for the same sector.

2. **Intro / description text.**
   The real survey has a consent/compliance banner at the top ("We may consider the
   information you provide... do not want to receive material, non-public
   information..."). Template includes a second sheet, `Intro Text`, with columns
   `Sector | Intro / Description Text` so this can be sector-specific and edited
   without touching code. This should populate the form's `info.description` field
   (or a leading text item) when each form is created.

3. **Respondent tracking** (not yet started) — still on the roadmap: unique
   per-respondent link/token, and a way to see who has/hasn't submitted.

4. **Reconciliation with internal crowding data** (not yet started) — pull form
   responses via `forms.responses.list`, join to internal crowding data by ticker.

5. **Branding — logo/image on the form.**
   Two distinct mechanisms, only one of which is API-controllable:
   - The Google Forms **theme header banner** (Customize Theme → Header) is **not
     exposed via the Forms API** — Google only supports setting it manually in the UI,
     per form. Not viable for a fully automated multi-form pipeline.
   - An **`imageItem` inserted into the form body** (e.g. right under the title) *is*
     scriptable via `batchUpdate`/`createItem`, and can point directly at a public
     image URL (`image.sourceUri`) — no need to download/host the asset. This is the
     recommended approach for automated branding. Needs the actual image file URL from
     woodlinepartners.com (not the page URL — the underlying image asset).

6. **Ticker format** — drop the `Equity` suffix. Template now uses bare tickers (e.g.
   `BNP FP`, not `BNP FP Equity`).

## Files handed off
- `create_positioning_survey_form.py` — working POC script (needs restructuring per
  point 1 above).
- `positioning_survey_universe.xlsx` — template with example rows (yellow = replace
  with real universe) for `Sector | Subsector | Ticker`, plus an `Intro Text` sheet.
- `credentials.json` / `token.json` — OAuth artifacts already generated locally (not
  included here — keep these out of any shared repo; they're user/tenant-specific
  secrets).
