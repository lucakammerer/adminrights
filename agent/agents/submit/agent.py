"""Submit agent: enters and signs the bid, with a TAN sub-agent in the mailbox. See README.md."""
import json
import re
import time
from urllib.parse import urlsplit

import llm
from agents.common import BOOL, STR, SYSTEM, context, login_line, obj

SIGN_BY = 180  # seconds before the deadline: stop entering, omit what is unfinished, sign (TAN look-up ~2 min)
MAIL_URLS = 20  # mailbox pages of the webmail agent the TAN look-up is told about


def german(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def prepare(task, tab, contact: str, deadline) -> dict:
    """The submission's first stage, while the bid is still being calculated: every step before the first page that
    asks for bid values (I6). It saved the time those steps took after the answer (18 s on 2026-10-10)."""
    mission = f"""{context(task)}

{login_line(tab.site)}
The bid is still being calculated and arrives in a few minutes. Your part now: get its submission ready on this tender
portal, following the brief's Submission section, without the bid. Go through every step before the first page that
asks for positions, materials, prices, discount or totals (e.g. an expression of interest, company data with the
contact e-mail {contact or 'shown in the mailbox (unknown here)'}, the type of offer) and stop on that page. Enter
nothing about positions, prices, discount or totals, never request a TAN and never submit. Finish with what you
entered and the page you stopped on."""
    return await llm.investigate(tab, SYSTEM, mission, obj(entered=STR, stopped_on=STR), deadline, "submit-prepare",
                                 max_steps=15)


def mailbox_urls(urls: list | None, site: dict) -> list[str]:
    """The pages of this mailbox another agent opened earlier in the run: their shape (a search URL among them) gets
    the TAN look-up to the TAN message without exploring the mailbox again."""
    host = urlsplit(site.get("url", "")).netloc
    return [u for u in urls or [] if isinstance(u, str) and urlsplit(u).netloc == host][:MAIL_URLS]


async def run(task, tab, mail_tab, answer: dict, omitted: list, specs: dict, contact: str, deadline,
              prepared: str = "", mail_urls: list | None = None):
    seen = mailbox_urls(mail_urls, mail_tab.site)

    async def fetch_tan(args):
        known = ("Earlier in this run the mailbox agent opened these pages of this mailbox; a search URL among them, "
                 "with your search terms instead, gets you to the TAN message in one step:\n" + "\n".join(seen) + "\n"
                 ) if seen else ""
        mission = f"""{login_line(mail_tab.site)}
In this mailbox (you may already be logged in), find the newest signing-TAN message for tender
{answer['tender_reference']}. The tender portal just said: "{args.get('portal_message', '')}". Search for it
yourself: a list on the page may be left from an earlier search, and its newest message is not necessarily a TAN
message. Pick only a message that gives a signing TAN for this tender, the one for that request (highest request
number / newest), open it and finish with found true and the TAN exactly as written.
{known}"""

        async def check(result, _evidence):
            """A look-up that found no TAN keeps searching instead of handing the portal a non-TAN."""
            if result.get("found") and str(result.get("tan") or "").strip():
                return result, ""
            return result, ("Not done: no signing-TAN message found yet. Search the mailbox for it (newest first, "
                            "every folder), open it and finish with found true and its TAN.")

        try:  # an earlier agent may have left this tab inside one of its search lists
            await mail_tab.page.goto(mail_tab.site["url"], wait_until="domcontentloaded", timeout=15000)
        except Exception as error:  # noqa: BLE001  a slow page: the agent opens the mailbox itself
            llm.log("tan", f"start page failed: {type(error).__name__}")
        found = await llm.investigate(mail_tab, SYSTEM, mission, obj(found=BOOL, tan=STR, request=STR, subject=STR),
                                      min(deadline, time.time() + 120), "tan", max_steps=12, check=check)
        found.pop("evidence", None)
        return json.dumps(found, ensure_ascii=False)

    async def verify_summary(_args):
        """Read-back before signing (I6b): every unit price and the total as calculated must be on the summary, and
        the breakdown values too once the summary shows any of them (a run typed one position's bonus as 0)."""
        page = await tab.read() + await tab.read(14000)

        def shows(value: str) -> bool:  # a whole number on the page: 0,50 is not inside 10,50
            return re.search(rf"(?<![\d.,]){re.escape(value)}(?!\d)", page) is not None

        expected = {f"position {p['position']} unit price": german(p["unit_price"]) for p in answer["positions"]}
        expected["total net"] = german(answer["total_net"])
        breakdown = {f"position {p['position']} {label}": german(p[key]) for p in answer["positions"]
                     for key, label in optional if p.get(key)}
        if any(shows(value) for value in breakdown.values()):
            expected |= breakdown
        wrong = [f"{name} {value}" for name, value in expected.items() if not shows(value)]
        llm.log("submit", f"verify_summary: {'; '.join(wrong) or 'all match'}")
        if not wrong:
            return "Every unit price and the total net match the calculated bid."
        return ("Not on this page as calculated: " + "; ".join(wrong) + ". Where the page shows a different value, "
                "correct that entry and verify again; a value this summary doesn't show at all is fine.")

    optional = (("base_unit_price", "base price"), ("surcharge_per_unit", "surcharge per piece"),
                ("packaging_per_unit", "packaging per piece"), ("rebate_total", "project bonus for the position"))
    rows = "\n".join(
        f"- position {p['position']}: material {p['material_number']} ({specs.get(p['position'], '')}), "
        f"quantity {p['quantity']} pieces, unit price {german(p['unit_price'])} EUR, lead time {p['lead_time_weeks']} weeks, "
        + ", ".join(f"{label} {german(p[key])}" if key in p else f"{label} left blank (unknown)"
                    for key, label in optional) for p in answer["positions"])
    mission = f"""{context(task)}

{login_line(tab.site)}
The bid is calculated. Your part: enter and sign it on this tender portal, following the brief's Submission section.
The bidder's own mailbox address, if a contact e-mail is asked for: {contact or 'unknown'}.
Bid ({answer['decision']}), tender {answer['tender_reference']}, discount {german(answer['discount_percent'])} %,
total net {german(answer['total_net'])} EUR (net; a displayed gross amount with VAT is not it):
{rows or '(no positions: no bid)'}
{f"Unfinished positions to omit with the form's omit option (partial submission): {', '.join(omitted)}" if omitted else ''}
Enter every value exactly (German number format, two decimals), one entry per position; positions may come in any
order, so check which position each page is for. Each model step costs time: enter a whole position, or any other
page, with one form call and end it with the page's next-step button. A configurator's dependent choices go into that
same call, each followed by its apply button, without reading a choice's options first: the form tool waits for the
page after every step and picks an option by its exact text, its beginning or any part of it, so a material number
alone is enough where an option shows more after it. Once the first position is accepted, enter all remaining
positions in a single form call: each position's choices with their apply buttons, its values, then the button that
moves to the next position. Name each choice by its field label: refs are
lost when a choice is applied, so a step by ref only works before the first apply of a call. A step that finds no
matching option stops the call and lists the options the page offers (the page may word a value differently than the
specification above): send the rest of that page again in one form call, with that step in the page's wording.
Fields in collapsed sections are opened by the form tool. Never add extra positions, never skip a
position unless it is listed to omit, never tick an option to add our own general terms and conditions. Before you request the signing
TAN, call verify_summary on the summary page and correct what it reports. When the form asks for the signing TAN,
request it once, then call get_tan with the portal's message (the newest request wins; a new request invalidates the
old TAN; a TAN is valid for five minutes). Review the summary, then submit bindingly; the run ends when the bid is accepted.
If a value is rejected, read the message and fix it. Finish with what the portal confirmed.
{f"Done on this tab while the bid was calculated: {prepared}. Continue from the page it shows now." if prepared else ""}"""
    tools = [llm._fn("get_tan", "After requesting a TAN: look up the newest signing TAN in the bidder's mailbox.",
                     {"portal_message": {"type": "string", "description": "what the portal said about the request"}}),
             llm._fn("verify_summary", "On the summary page before the TAN: compare it with the calculated bid.")]
    hurry = ("Time is almost up and an unsigned bid scores nothing. Stop entering values: omit every position not "
             "completely entered yet with the form's omit option, go to the summary, request the TAN unless you already "
             "did, get it with get_tan, and submit the bid bindingly now. Call finish only after the portal accepted it.")
    return await llm.investigate(tab, SYSTEM, mission, obj(confirmation=STR), deadline, "submit",
                                 extra_tools=tools, handlers={"get_tan": fetch_tan, "verify_summary": verify_summary}, max_steps=70,
                                 warn_at=SIGN_BY, warning=hurry)
