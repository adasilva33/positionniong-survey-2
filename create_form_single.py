"""
Positioning Survey — ONE branching Google Form (EXPERIMENTAL).

create_form.py makes one form per Sector. This script instead builds a SINGLE
form for the whole workbook: page 1 asks the respondent to pick their SECTOR
(a required radio question), and Google Forms' built-in branching
(Option.goToAction / goToSectionId) jumps straight to that sector's subsector
sections, skipping every other sector entirely. After the last question of
whichever sector was chosen, the form submits directly (no need to click
through the other sectors).

Why this might not scale: Google Forms branching only controls which sections
a given RESPONDENT sees — it does not remove the other sectors' questions from
the form's own definition. ALL sectors' dropdowns still count toward the
per-form ~4000-choice ceiling documented in CAPACITY_MATRIX.md, combined, not
per sector. So this approach only fits a universe small enough that
(total tickers across the WHOLE workbook) x 9 stays under that ceiling — not
per sector as with create_form.py. The plan/dry-run below computes and checks
this aggregate total before creating anything.

Also experimental: branching (goToAction/goToSectionId) is documented to work
for RADIO choice questions; support for DROP_DOWN is unclear from Google's own
docs (contradicts itself). The sector picker here defaults to RADIO, which is
fine for a handful of sectors but unwieldy for dozens. Test with --dry-run and
a small --limit before trusting this at full scale.

Reuses workbook/config loading and auth from create_form.py — run that script's
setup first (credentials.json, survey_config.toml, positioning_survey_universe.xlsx).

Usage
  python create_form_single.py --dry-run          # plan + aggregate choice check, no API calls
  python create_form_single.py --limit 2 --dry-run # just the first 2 sectors, for a cheap test
  python create_form_single.py --limit 2           # actually create a small test form
  python create_form_single.py                     # the whole workbook, one form
"""

import argparse
import sys

import create_form as cf

SECTOR_QUESTION_TITLE = "SECTOR"
SECTOR_QUESTION_HELP = "Choose your sector. You will then only see that sector's subsectors."


def _pagebreak_id(si, ui):
    return f"s{si}_u{ui}"


def build_single_form_requests(sectors, intros, sector_choice_type="RADIO"):
    """One ordered list of requests for the whole form. Every item gets a
    client-chosen itemId (allowed on creation, see Forms API docs), so the
    sector-selector's goToSectionId targets are known up front — no reply
    parsing / second batchUpdate pass needed."""
    requests = []
    idx = 0

    description = "\n\n".join(p for p in (cf.DEFAULT_INTRO_TEXT, cf.SUBMIT_NOTICE) if p)
    if description:
        requests.append(
            {
                "updateFormInfo": {
                    "info": {"description": description},
                    "updateMask": "description",
                }
            }
        )

    for q_title, q_help in cf.IDENTIFICATION_QUESTIONS:
        item = {
            "title": q_title,
            "questionItem": {
                "question": {"required": True, "textQuestion": {"paragraph": False}}
            },
        }
        if q_help:
            item["description"] = q_help
        requests.append({"createItem": {"item": item, "location": {"index": idx}}})
        idx += 1

    sector_names = list(sectors.keys())
    sector_options = [
        {"value": sector, "goToSectionId": _pagebreak_id(si, 0)}
        for si, sector in enumerate(sector_names)
    ]
    requests.append(
        {
            "createItem": {
                "item": {
                    "itemId": "sector_select",
                    "title": SECTOR_QUESTION_TITLE,
                    "description": SECTOR_QUESTION_HELP,
                    "questionItem": {
                        "question": {
                            "required": True,
                            "choiceQuestion": {
                                "type": sector_choice_type,
                                "options": sector_options,
                            },
                        }
                    },
                },
                "location": {"index": idx},
            }
        }
    )
    idx += 1

    for si, (sector, subs) in enumerate(sectors.items()):
        subsector_names = list(subs.items())
        for ui, (subsector, tickers) in enumerate(subsector_names):
            if cf.MAX_OPTIONS_PER_DROPDOWN:
                tickers = tickers[: cf.MAX_OPTIONS_PER_DROPDOWN]
            options = [{"value": t} for t in tickers]

            section_desc = cf.SECTION_INSTRUCTIONS
            if ui == 0 and intros.get(sector):
                section_desc = f"{intros[sector]}\n\n{cf.SECTION_INSTRUCTIONS}"

            requests.append(
                {
                    "createItem": {
                        "item": {
                            "itemId": _pagebreak_id(si, ui),
                            "title": f"{sector}: {subsector}".upper(),
                            "description": section_desc,
                            "pageBreakItem": {},
                        },
                        "location": {"index": idx},
                    }
                }
            )
            idx += 1

            is_last_subsector = ui == len(subsector_names) - 1
            for gi, (group_label, n_ranks) in enumerate(cf.QUESTION_GROUPS):
                is_last_group = gi == len(cf.QUESTION_GROUPS) - 1
                for rank in range(1, n_ranks + 1):
                    is_last_question = (
                        is_last_subsector and is_last_group and rank == n_ranks
                    )
                    q_options = options
                    if is_last_question:
                        # Every option leads to SUBMIT_FORM: whichever ticker the
                        # respondent picks here, the form submits right after —
                        # skipping every other sector's questions.
                        q_options = [
                            {**o, "goToAction": "SUBMIT_FORM"} for o in options
                        ]
                    requests.append(
                        {
                            "createItem": {
                                "item": {
                                    "title": f"{group_label}: TICKER {rank}",
                                    "questionItem": {
                                        "question": {
                                            "required": False,
                                            "choiceQuestion": {
                                                "type": "DROP_DOWN",
                                                "options": q_options,
                                            },
                                        }
                                    },
                                },
                                "location": {"index": idx},
                            }
                        }
                    )
                    idx += 1

    return requests


def plan(sectors):
    n_sub = sum(len(v) for v in sectors.values())
    n_tkr = sum(len(t) for v in sectors.values() for t in v.values())
    n_items = 1 + len(cf.IDENTIFICATION_QUESTIONS) + n_sub * (1 + cf.QUESTIONS_PER_SUBSECTOR)
    n_choices = sum(
        len(t[: cf.MAX_OPTIONS_PER_DROPDOWN] if cf.MAX_OPTIONS_PER_DROPDOWN else t)
        for v in sectors.values()
        for t in v.values()
    ) * cf.QUESTIONS_PER_SUBSECTOR
    return {
        "sectors": len(sectors),
        "subsectors": n_sub,
        "tickers": n_tkr,
        "items": n_items,
        "choices": n_choices,
        "over_limit": n_choices > cf.MAX_TOTAL_CHOICES,
    }


def print_plan(sectors, title):
    p = plan(sectors)
    print(f"\nSingle branching form: {p['sectors']} sector(s), {p['subsectors']} subsector(s), "
          f"{p['tickers']} ticker rows")
    print(f"Title    : {title}")
    print(f"Items    : {p['items']}")
    print(f"Choices  : {p['choices']}  (ALL sectors combined — this is the number that "
          f"matters for the ~{cf.MAX_TOTAL_CHOICES} per-form ceiling)")
    if p["over_limit"]:
        print(f"\n!! OVER LIMIT: {p['choices']} > {cf.MAX_TOTAL_CHOICES}. "
              f"This form WILL be rejected by Google. Reduce sectors/subsectors/"
              f"tickers, set max_options_per_dropdown, or use --limit to test with "
              f"fewer sectors. create_form.py (one form per sector) does not have "
              f"this problem since each sector's choices are counted separately.")
    else:
        print("\nWithin the choice-limit estimate — plausible this fits in one form.")
    return p


def create_single_form(service, sectors, intros, title, sector_choice_type):
    from googleapiclient.errors import HttpError

    form = cf.execute_with_retry(
        service.forms().create(body={"info": {"title": title, "documentTitle": title}})
    )
    form_id = form["formId"]
    edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print(f"Created empty form -> {edit_url}")

    requests = build_single_form_requests(sectors, intros, sector_choice_type)
    n_chunks = max(1, -(-len(requests) // cf.CHUNK_SIZE))
    try:
        for c, chunk in enumerate(cf.chunked(requests, cf.CHUNK_SIZE), 1):
            print(f"  batchUpdate {c}/{n_chunks} ({len(chunk)} requests)")
            cf.execute_with_retry(
                service.forms().batchUpdate(formId=form_id, body={"requests": chunk})
            )
    except HttpError as e:
        msg = str(e)
        print(f"  FAILED: {msg.splitlines()[0]}")
        print(f"  The Forms API cannot delete forms; trash this one in Drive: {edit_url}")
        return None

    print(f"\nDone -> {edit_url}")
    print("Open it, pick a sector in the preview, and confirm branching lands on the "
          "right subsectors and that Submit fires at the end of that sector.")
    return edit_url


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=cf.DEFAULT_INPUT, help="universe workbook")
    p.add_argument("--config", default=cf.DEFAULT_CONFIG, help="TOML config")
    p.add_argument("--dry-run", action="store_true", help="print the plan only; no API calls")
    p.add_argument("--limit", type=int, metavar="N", help="only include the first N sectors (cheap test)")
    p.add_argument("--title", metavar="STR", help="exact form title (default: derived from config)")
    p.add_argument("--sector-choice-type", choices=["RADIO", "DROP_DOWN"], default="RADIO",
                    help="question type for the sector picker (default RADIO; DROP_DOWN is untested for branching)")
    p.add_argument("--max-options", type=int, metavar="N", help="truncate every dropdown to N options (0 = no cap)")
    p.add_argument("--force", action="store_true", help="create even if over the choice-limit estimate")
    args = p.parse_args()

    cf.load_config(args.config)
    if args.max_options is not None:
        cf.MAX_OPTIONS_PER_DROPDOWN = args.max_options

    sectors, intros = cf.load_universe(args.input)
    if args.limit:
        sectors = dict(list(sectors.items())[: args.limit])

    title = args.title or cf.form_title("ALL SECTORS")

    result = print_plan(sectors, title)

    if args.dry_run:
        print("\nDry run — nothing created.")
        return

    if result["over_limit"] and not args.force:
        sys.exit("\nAborting: over the choice-limit estimate. Use --force to try "
                  "anyway, --limit to test fewer sectors, or --max-options to truncate.")

    service = cf.get_forms_service()
    create_single_form(service, sectors, intros, title, args.sector_choice_type)

    print(
        "\nReminder: in the Forms UI set Settings -> Responses -> 'Limit to 1 "
        "response' OFF and email collection OFF. Not exposed by the API."
    )


if __name__ == "__main__":
    main()
