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

Two-phase creation: a client-supplied itemId (e.g. "sector_select") is
rejected by the API with "Invalid ID" — there's no documented valid format, so
this doesn't try to set one. Instead: phase 1 creates every item letting
Google assign IDs, reads each needed item's real itemId back from the
batchUpdate reply; phase 2 sends one updateItem that adds goToSectionId to the
sector-selector's options, addressed by its position in the form (Location is
index-based, confirmed in the API docs) — not by its own itemId.

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

# Google Forms enforces (at least) TWO independent per-form ceilings, distinct
# API errors for each:
#   "exceeding the choice limit" -> total dropdown/radio/checkbox OPTIONS,
#     ~4000 (see cf.MAX_TOTAL_CHOICES / CAPACITY_MATRIX.md).
#   "exceeding the entry limit"  -> total ITEMS (questions + page breaks),
#     empirically between 200 (succeeded) and 444 (failed) in testing; 300 is
#     a conservative guess, deliberately unverified above that number.
# Both matter here because create_form_single.py must fit the WHOLE workbook's
# subsectors as items in ONE form — create_form.py never approaches either
# ceiling since each sector is its own small form.
MAX_TOTAL_ITEMS = 300


def build_phase1_requests(sectors, intros, sector_choice_type="RADIO"):
    """Phase 1: create every item, letting Google assign itemIds (a client-
    supplied itemId like "sector_select" is rejected with "Invalid ID" — no
    documented format for a valid one, so don't fight it). The sector-selector
    question is created with plain options (no goToSectionId yet) — that needs
    the OTHER items' itemIds, which only exist after this phase's replies come
    back. See build_phase2_request().

    Returns (requests, sector_selector_req_index, sector_first_pb_req_index):
      - sector_selector_req_index: position of the sector-selector's createItem
        within `requests` (== its reply's position after execution).
      - sector_first_pb_req_index: {sector: position} of each sector's FIRST
        subsector page-break createItem within `requests`.
    """
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
    sector_options = [{"value": sector} for sector in sector_names]
    requests.append(
        {
            "createItem": {
                "item": {
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
    sector_selector_req_index = len(requests) - 1
    sector_selector_location_index = idx
    idx += 1

    sector_first_pb_req_index = {}
    for sector, subs in sectors.items():
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
                            "title": f"{sector}: {subsector}".upper(),
                            "description": section_desc,
                            "pageBreakItem": {},
                        },
                        "location": {"index": idx},
                    }
                }
            )
            if ui == 0:
                sector_first_pb_req_index[sector] = len(requests) - 1
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

    return requests, sector_selector_req_index, sector_selector_location_index, sector_first_pb_req_index


def build_phase2_request(sector_choice_type, sector_names, sector_selector_location_index, target_item_ids):
    """Phase 2: one updateItem that rewrites the sector-selector's options to
    add goToSectionId, now that every target page-break's real itemId is
    known from phase 1's replies. Location is index-based (confirmed in the
    Forms API docs), so the item to update is addressed by its position in
    the form, not by an itemId of its own."""
    options = [
        {"value": sector, "goToSectionId": target_item_ids[sector]}
        for sector in sector_names
    ]
    return {
        "updateItem": {
            "item": {
                "questionItem": {
                    "question": {
                        "required": True,
                        "choiceQuestion": {"type": sector_choice_type, "options": options},
                    }
                }
            },
            "location": {"index": sector_selector_location_index},
            "updateMask": "questionItem.question.choiceQuestion.options",
        }
    }


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
        "over_choice_limit": n_choices > cf.MAX_TOTAL_CHOICES,
        "over_item_limit": n_items > MAX_TOTAL_ITEMS,
    }


def print_plan(sectors, title):
    p = plan(sectors)
    p["over_limit"] = p["over_choice_limit"] or p["over_item_limit"]
    print(f"\nSingle branching form: {p['sectors']} sector(s), {p['subsectors']} subsector(s), "
          f"{p['tickers']} ticker rows")
    print(f"Title    : {title}")
    print(f"Items    : {p['items']}  (limit ~{MAX_TOTAL_ITEMS}, unverified above that — "
          f"see 'entry limit' in GUIDE.md §9)")
    print(f"Choices  : {p['choices']}  (limit ~{cf.MAX_TOTAL_CHOICES} — 'choice limit')")
    print("Both are ALL-sectors-combined totals: everything lives in one form.")
    if p["over_item_limit"]:
        print(f"\n!! OVER ITEM LIMIT: {p['items']} > ~{MAX_TOTAL_ITEMS}. Google is likely to "
              f"reject this with \"exceeding the entry limit\" — confirmed empirically at "
              f"444 items, even with choices well under the choice-limit guard. Use --limit "
              f"to test with fewer sectors, or fewer subsectors per sector.")
    if p["over_choice_limit"]:
        print(f"\n!! OVER CHOICE LIMIT: {p['choices']} > {cf.MAX_TOTAL_CHOICES}. Google is "
              f"likely to reject this with \"exceeding the choice limit\". Reduce sectors/"
              f"subsectors/tickers, set max_options_per_dropdown, or use --limit.")
    if not p["over_limit"]:
        print("\nWithin both limit estimates — plausible this fits in one form. "
              "create_form.py (one form per sector) doesn't have either problem, since "
              "each sector's items/choices are counted separately.")
    return p


def create_single_form(service, sectors, intros, title, sector_choice_type):
    from googleapiclient.errors import HttpError

    form = cf.execute_with_retry(
        service.forms().create(body={"info": {"title": title, "documentTitle": title}})
    )
    form_id = form["formId"]
    edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print(f"Created empty form -> {edit_url}")

    (
        requests,
        _,
        sector_selector_location_index,
        sector_first_pb_req_index,
    ) = build_phase1_requests(sectors, intros, sector_choice_type)

    n_chunks = max(1, -(-len(requests) // cf.CHUNK_SIZE))
    all_replies = []
    try:
        print(f"Phase 1/2: creating {len(requests)} items")
        for c, chunk in enumerate(cf.chunked(requests, cf.CHUNK_SIZE), 1):
            print(f"  batchUpdate {c}/{n_chunks} ({len(chunk)} requests)")
            resp = cf.execute_with_retry(
                service.forms().batchUpdate(formId=form_id, body={"requests": chunk})
            )
            all_replies.extend(resp.get("replies", []))
    except HttpError as e:
        msg = str(e)
        print(f"  FAILED: {msg.splitlines()[0]}")
        print(f"  The Forms API cannot delete forms; trash this one in Drive: {edit_url}")
        return None

    target_item_ids = {
        sector: all_replies[req_idx]["createItem"]["itemId"]
        for sector, req_idx in sector_first_pb_req_index.items()
    }
    sector_names = list(sectors.keys())
    phase2 = build_phase2_request(
        sector_choice_type, sector_names, sector_selector_location_index, target_item_ids
    )
    try:
        print("Phase 2/2: wiring sector branching")
        cf.execute_with_retry(
            service.forms().batchUpdate(formId=form_id, body={"requests": [phase2]})
        )
    except HttpError as e:
        msg = str(e)
        print(f"  FAILED (branching): {msg.splitlines()[0]}")
        print(f"  Form was created but branching is not wired up: {edit_url}")
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
