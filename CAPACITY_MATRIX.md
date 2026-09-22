# Google Forms capacity — sections × tickers per section

**Applies as-is to `create_form.py`: one form = one Sector. One section = one
Subsector.**

**For `create_form_single.py`** (one branching form for the whole workbook),
the same ~4000 ceiling applies, but to the **sum across every sector
combined** — branching only changes which sections a respondent sees, not
what's stored in the form. Use `sections` = total subsectors across the whole
workbook, not per sector, when reading this grid for that script.

Each section has **9 dropdown questions** (3 Consensus Long, 3 Consensus Short, 
3 Contentious). Every dropdown in a section is populated with that section's full 
ticker list, so:

```
total dropdown options in a form = sections × tickers-per-section × 9
```

Google Forms rejects a form once that total exceeds **~4000** 
(`"Batch update failed: update results in the schema exceeding the choice limit"`). 
This was found empirically: 3960 options built fine, 4950 was rejected. 
The number is undocumented and may shift — treat it as a soft ceiling.

- ✅ = within the safe working ceiling (3600)
- ⚠️ = between 3600 and 4000 — usually works, no margin
- ❌ = over ~4000 — Google will reject the form

| sections \ tickers | 5 | 10 | 15 | 20 | 25 | 30 | 40 | 50 | 75 | 100 |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | 45 ✅ | 90 ✅ | 135 ✅ | 180 ✅ | 225 ✅ | 270 ✅ | 360 ✅ | 450 ✅ | 675 ✅ | 900 ✅ |
| **2** | 90 ✅ | 180 ✅ | 270 ✅ | 360 ✅ | 450 ✅ | 540 ✅ | 720 ✅ | 900 ✅ | 1350 ✅ | 1800 ✅ |
| **3** | 135 ✅ | 270 ✅ | 405 ✅ | 540 ✅ | 675 ✅ | 810 ✅ | 1080 ✅ | 1350 ✅ | 2025 ✅ | 2700 ✅ |
| **4** | 180 ✅ | 360 ✅ | 540 ✅ | 720 ✅ | 900 ✅ | 1080 ✅ | 1440 ✅ | 1800 ✅ | 2700 ✅ | 3600 ✅ |
| **5** | 225 ✅ | 450 ✅ | 675 ✅ | 900 ✅ | 1125 ✅ | 1350 ✅ | 1800 ✅ | 2250 ✅ | 3375 ✅ | 4500 ❌ |
| **6** | 270 ✅ | 540 ✅ | 810 ✅ | 1080 ✅ | 1350 ✅ | 1620 ✅ | 2160 ✅ | 2700 ✅ | 4050 ❌ | 5400 ❌ |
| **8** | 360 ✅ | 720 ✅ | 1080 ✅ | 1440 ✅ | 1800 ✅ | 2160 ✅ | 2880 ✅ | 3600 ✅ | 5400 ❌ | 7200 ❌ |
| **10** | 450 ✅ | 900 ✅ | 1350 ✅ | 1800 ✅ | 2250 ✅ | 2700 ✅ | 3600 ✅ | 4500 ❌ | 6750 ❌ | 9000 ❌ |
| **12** | 540 ✅ | 1080 ✅ | 1620 ✅ | 2160 ✅ | 2700 ✅ | 3240 ✅ | 4320 ❌ | 5400 ❌ | 8100 ❌ | 10800 ❌ |
| **15** | 675 ✅ | 1350 ✅ | 2025 ✅ | 2700 ✅ | 3375 ✅ | 4050 ❌ | 5400 ❌ | 6750 ❌ | 10125 ❌ | 13500 ❌ |
| **20** | 900 ✅ | 1800 ✅ | 2700 ✅ | 3600 ✅ | 4500 ❌ | 5400 ❌ | 7200 ❌ | 9000 ❌ | 13500 ❌ | 18000 ❌ |
| **25** | 1125 ✅ | 2250 ✅ | 3375 ✅ | 4500 ❌ | 5625 ❌ | 6750 ❌ | 9000 ❌ | 11250 ❌ | 16875 ❌ | 22500 ❌ |
| **30** | 1350 ✅ | 2700 ✅ | 4050 ❌ | 5400 ❌ | 6750 ❌ | 8100 ❌ | 10800 ❌ | 13500 ❌ | 20250 ❌ | 27000 ❌ |

## Max tickers per section, by section count

`floor(4000 / (sections × 9))` — hard ceiling; use ~10% less for safety.

| sections | max tickers/section (hard) | recommended |
|---|---|---|
| 2 | 222 | 200 |
| 3 | 148 | 133 |
| 4 | 111 | 100 |
| 5 | 88 | 80 |
| 6 | 74 | 66 |
| 8 | 55 | 50 |
| 10 | 44 | 40 |
| 12 | 37 | 33 |
| 15 | 29 | 26 |
| 20 | 22 | 20 |
| 25 | 17 | 16 |
| 30 | 14 | 13 |
| 40 | 11 | 10 |
| 50 | 8 | 8 |

## Notes

- The limit is **per form (per Sector)**, not per section and not global. 
  10 sections × 40 tickers is fine; 10 × 50 is not.
- Number of **forms** (sectors) is not constrained by this — 2 or 200 forms 
  are equivalent, each subject to its own per-form total.
- `--max-options N` truncates every dropdown to N options as an escape hatch 
  for an oversized section.
- `max_total_choices` in `survey_config.toml` sets the pre-flight guard; a sector 
  over it is skipped before any form is created (unless `--force`).
- Flat dropdowns get unwieldy past ~50–100 options anyway (no type-ahead search).
- Google Forms also has an item cap (~300 items/form). sections × 10 + 3 items — 
  so ≲29 sections regardless of ticker count. The choice limit usually bites first.
