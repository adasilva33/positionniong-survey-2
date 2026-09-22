# Positioning Survey form generator — setup & run guide

How to stand this up from scratch (e.g. on a work machine / work Google account)
and run it each cycle.

---

## 1. What it does

Two scripts, both reading the same `positioning_survey_universe.xlsx` +
`survey_config.toml`:

- **`create_form.py`** (primary) — one Google Form **per Sector**. Page 1 has
  the consent text + `BROKER` / `NAME OF PERSON COMPLETING` / `EMAIL ADDRESS`,
  then **one section per Subsector** headed `SECTOR: SUBSECTOR`, each with 9
  dropdown questions (`CONSENSUS LONG/SHORT/CONTENTIOUS : TICKER 1-3`). Every
  dropdown holds that subsector's tickers only.
- **`create_form_single.py`** (experimental) — **one form for everything**.
  Page 1 adds a required `SECTOR` question; Google Forms' native branching
  (`goToAction`/`goToSectionId`) jumps straight to that sector's subsector
  pages and submits at the end, so a respondent never sees other sectors. See
  §9 for why this doesn't scale the same way `create_form.py` does, and test
  with `--dry-run` + `--limit` before trusting it.

Each run creates **brand-new forms** — neither script updates a previous run's
forms.

---

## 2. Prerequisites

- Python 3.11+ (needs `tomllib`, stdlib since 3.11).
- Packages:
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib openpyxl
  ```

---

## 3. Google Cloud setup (one-time)

1. **Project** — create or pick one at <https://console.cloud.google.com>.
2. **Enable the API** — APIs & Services → Library → search "Google Forms API" →
   Enable.
3. **OAuth consent screen** — APIs & Services → OAuth consent screen.
   - On a Workspace (work) account choose **Internal** → no Google verification
     needed, any user in your org can authorise. (External works too but shows an
     "unverified app" warning until verified.)
   - Add scope `https://www.googleapis.com/auth/forms.body`.
4. **OAuth client** — APIs & Services → Credentials → Create credentials →
   OAuth client ID → **Application type: Desktop app**.
   - ⚠️ Must be **Desktop app**, not Web — a Web client gives
     `redirect_uri_mismatch` with the local-server auth flow.
   - Download the JSON, save it next to `create_form.py` as **`credentials.json`**.
     `credentials.example.json` in the repo shows the expected shape.
5. **First run** opens a browser for consent and writes **`token.json`** (cached
   refresh token). Subsequent runs are non-interactive until the token expires
   or is revoked.

`credentials.json` and `token.json` are per-user secrets — keep them out of git
(the `.gitignore` in this repo already excludes both; `credentials.example.json`
shows the expected shape of `credentials.json`).

⚠️ **While the GCP project's OAuth consent screen is in "Testing" publishing
status (the default, and fine for personal/internal use), Google caps refresh
tokens at ~7 days** — `token.json` silently stops working after about a week
of inactivity and every `get_forms_service()` call starts failing with
`RefreshError: invalid_grant`. Fix: delete `token.json` and run any script
again to re-trigger the browser consent flow (needs `credentials.json` present
and a real browser — won't work in a headless/SSH session). Publishing the
OAuth consent screen to "In production" (Internal apps on Workspace don't need
Google review) removes this 7-day cap.

---

## 4. Prepare the universe workbook

`positioning_survey_universe.xlsx`, two sheets:

**`Universe`** — one row per ticker:

| Sector | Subsector | Ticker |
|---|---|---|
| Financials | Traditional Banks | BNP FP |
| Financials | Traditional Banks | HSBA LN |
| … | … | … |

- Bare Bloomberg tickers, **no `Equity` suffix**.
- Trailing blank / legend rows are ignored (a row is used only if all three
  cells are non-empty).
- Row order is preserved in the form.

**`Intro Text`** — consent banner per sector:

| Sector | Intro / Description Text |
|---|---|
| Financials | We may consider the information that you provide… |

Sectors missing here fall back to `intro_text` in the config.

---

## 5. Configure

Edit **`survey_config.toml`** (all optional — built-in defaults apply if the file
is absent):

- `title` template + `region` + `period` → form names, or exact per-sector names
  in `[title_overrides]`.
- `intro_text`, `submit_notice`, `section_instructions` → page text.
- `[[identification]]` → the page-1 questions.
- `[questions]` → question group labels + ranked ticker count.
- `[limits] max_total_choices` → pre-flight guard (see §7).

---

## 6. Run

```bash
source .venv/bin/activate

# 1. inspect the plan — no browser, no API calls
python create_form.py --dry-run

# 2. create for real
python create_form.py
```

Useful flags:

| flag | effect |
|---|---|
| `--input FILE` | different workbook |
| `--config FILE` | different config |
| `--dry-run` | plan only |
| `--limit N` | only the first N sectors (smoke-test one real form) |
| `--region STR` / `--period STR` | override title parts |
| `--max-options N` | truncate every dropdown to N options |
| `--force` | build even if over the choice-limit guard |
| `--make-sample F --sectors S --subsectors U --tickers T` | write a synthetic workbook for scale tests |

Output: edit + responder URLs printed and written to `created_forms.csv`.

### 6b. The single branching form (experimental)

```bash
# cheap test: first 2 sectors only
python create_form_single.py --limit 2 --dry-run
python create_form_single.py --limit 2

# whole workbook, one form
python create_form_single.py --dry-run
python create_form_single.py
```

Same `--input` / `--config` / `--max-options` / `--force` flags as
`create_form.py`, plus:

| flag | effect |
|---|---|
| `--limit N` | only include the first N sectors — use this to test cheaply |
| `--title STR` | exact form title (default derived from config, sector token `ALL SECTORS`) |
| `--sector-choice-type RADIO\|DROP_DOWN` | question type for the sector picker (default `RADIO`) |

The printed "Choices" figure is the sum across **every** sector, since — unlike
`create_form.py` — they all live in the same form. See §9.

---

## 7. Limits & gotchas

- **Per-form dropdown-option cap ≈ 4000.** `sections × tickers/section × 9` must
  stay under it or Google rejects the whole form
  (`"exceeding the choice limit"`). Found empirically: 3960 OK, 4950 rejected.
  See `CAPACITY_MATRIX.md` for the full grid. The guard (`max_total_choices`,
  default 4000) skips an oversized sector before creating anything.
- **The Forms API cannot delete forms.** Failed/aborted/test forms are orphans —
  trash them by hand in Google Drive. A form that fails part-way through may be
  partially built.
- **No update-in-place.** Every run makes fresh forms. Running 3 times = 3× the
  forms in Drive. Use `--limit 1` while iterating.
- **The header/logo banner is not API-settable.** Do it by hand per form
  (Customize theme → Header), or clone a pre-branded template form via the Drive
  API (not implemented here).
- **Respondent sign-in.** On a personal Google account, respondents are *not*
  forced to sign in as long as, per form, Settings → Responses →
  "Limit to 1 response" is **OFF** and email collection is **OFF**. On a
  Workspace account this and external sharing may be constrained by admin policy
  — confirm with IT before rollout.
- **Email field** is a plain required text box — the API can't attach
  email-format validation.
- **Item cap** ≈ 300 items/form (`sections × 10 + 3`), so ≲29 sections
  regardless of ticker count. The choice cap usually bites first.

---

## 8. Each cycle (recurring checklist)

1. Refresh `Universe` (and `Intro Text` if changed) in the workbook.
2. Bump `period` in the config, or let it auto-derive the quarter.
3. `python create_form.py --dry-run` — check counts, no warnings.
4. `python create_form.py` — note URLs from `created_forms.csv`.
5. Per form in the UI: response settings (§7), theme/header, then send.
6. Trash any leftover test/orphan forms in Drive.

---

## 9. `create_form_single.py` — how the branching works, and its ceiling

Page 1 (identification + a required `SECTOR` radio question) submits, then
Google Forms' native branching (`Option.goToAction` / `goToSectionId` — see
[Forms API `batchUpdate` reference](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate))
jumps straight to that sector's first subsector page. The very last dropdown
question of that sector's last subsector has `goToAction: SUBMIT_FORM` set on
*every* option, so whichever ticker is picked there, the form submits — no
detour through the other sectors' questions.

**Why this doesn't scale like `create_form.py`:** branching only controls
which sections a given respondent *walks through* — it does not remove the
other sectors' questions from the form's own definition. Every dropdown, for
every sector, still exists in the one form and still counts toward the
per-form ~4000-choice ceiling (`CAPACITY_MATRIX.md`), **combined across the
whole workbook** rather than per sector. `create_form.py`'s 6-sector real
universe (1791 choices total, biggest single sector 414) comfortably fits as
one branching form; a bigger universe or many sectors likely won't — the
`--dry-run` "Choices" line + the pre-flight guard catch this before creating
anything.

Also unverified: Google's own docs are internally inconsistent on whether
`DROP_DOWN` choice questions support branching (`RADIO` is unambiguous). The
sector picker defaults to `RADIO`; `--sector-choice-type DROP_DOWN` is there
to test on a big sector list, but hasn't been confirmed working.

**Not yet checked:** whether an untouched dropdown on a *skipped* sector's
page still shows up as an unanswered response cell, and whether the "Limit to
1 response" / email-collection settings behave identically to the per-sector
forms.

---

## 10. Not built yet

- Per-respondent unique links / tokens and a responded / not-responded view.
- Pulling responses (`forms.responses.list`) and reconciling to internal crowding
  data by ticker.
- Update-in-place for re-runs.
- Template-clone pipeline for automated header/branding + response settings.
- `create_form_single.py` beyond the current experiment (see §9): confirmed
  behaviour at real scale, `DROP_DOWN` branching verification.
