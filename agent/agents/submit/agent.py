"""Submit agent: enters and signs the bid, with a TAN sub-agent in the mailbox. See README.md."""
import asyncio
import json
import re
import time

import llm
from agents.common import BOOL, STR, login_line, obj, system

SIGN_BY = 180  # seconds before the deadline: stop entering, omit what is unfinished, sign (TAN look-up ~2 min)


def german(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


OPTIONAL = (("base_unit_price", "base price"), ("surcharge_per_unit", "surcharge per piece"),
            ("packaging_per_unit", "packaging per piece"), ("rebate_total", "project bonus for the position"))


def values(answer: dict, omitted: list, specs: dict) -> str:
    """The calculated bid as the submit agent enters it."""
    rows = "\n".join(
        f"- position {p['position']}: material {p['material_number']} ({specs.get(p['position'], '')}), "
        f"quantity {p['quantity']} pieces, unit price {german(p['unit_price'])} EUR, lead time {p['lead_time_weeks']} weeks, "
        + ", ".join(f"{label} {german(p[key])}" if key in p else f"{label} left blank (unknown)"
                    for key, label in OPTIONAL) for p in answer["positions"])
    return f"""Bid ({answer['decision']}), tender {answer['tender_reference']}, discount {german(answer['discount_percent'])} %,
total net {german(answer['total_net'])} EUR (net; a displayed gross amount with VAT is not it):
{rows or ('(none to enter)' if omitted else '(no positions: no bid)')}
{f"Unfinished positions to omit with the form's omit option (partial submission): {', '.join(omitted)}" if omitted else ''}"""


def readable(tan: str) -> bool:
    """A TAN as a message writes it: one short code with digits, not a sentence about it."""
    return len(tan) <= 32 and len(tan.split()) <= 3 and any(c.isdigit() for c in tan)


def number(text) -> float | None:
    """A typed amount in any common format: the last separator is the decimal one if one or two digits follow it."""
    text = re.sub(r"[^\d.,-]", "", str(text))
    if not re.search(r"\d", text):
        return None
    last = max(text.rfind("."), text.rfind(","))
    whole, frac = (text[:last], text[last + 1:]) if last >= 0 and len(text) - last - 1 <= 2 else (text, "")
    try:
        return round(float(re.sub(r"[.,]", "", whole) + "." + (frac or "0")), 2)
    except ValueError:
        return None


def unentered(steps: list, answer: dict) -> list[str]:
    """Breakdown values of a position whose unit price this form call types but which the call itself doesn't:
    found on the summary only after every later position was entered, a fix means walking back through them all."""
    typed = {number(s.get("value")) for s in steps if isinstance(s, dict)} - {None}
    return [f"position {p['position']} {label} {german(p[key])}" for p in answer["positions"]
            if number(german(p["unit_price"])) in typed
            for key, label in OPTIONAL if p.get(key) and round(p[key], 2) not in typed]


async def run(task, tab, mailbox, bid: asyncio.Future, contact: str, deadline, mail_search: str = ""):
    """Starts before the bid is calculated: the agent enters what doesn't depend on it (bidder data, offer kind) and
    then waits in `bid_values`, which returns once `bid` holds (answer, omitted, specs). `mailbox()` opens a tab in the
    mailbox for each TAN look-up."""
    async def bid_values(_args):
        answer, omitted, specs = await bid
        llm.log("submit", "bid values handed over")
        return llm.PINNED + values(answer, omitted, specs)

    async def fetch_tan(args):
        answer, _, _ = await bid
        search = (f"\nA search this mailbox ran earlier, as a URL (change its query to search for the TAN message): "
                  f"{mail_search}" if mail_search else "")
        # a new tab, not the one the mailbox agents left: that tab, idle since then, stopped answering for 45-150 s in
        # 5 of 10 runs (run_bd99f53d4d7d5c7f, run_840f0cd20f29dc8c), while a later look-up got through at once
        mail_tab = await mailbox()
        mission = f"""{login_line(mail_tab.site)}
In this mailbox (you may already be logged in), find the newest signing-TAN message for tender
{answer['tender_reference']}. The tender portal just said: "{args.get('portal_message', '')}". Search for it
yourself: a list on the page may be left from an earlier search, and its newest message is not necessarily a TAN
message. Pick only a message that gives a signing TAN for this tender, the one for that request (highest request
number / newest), open it and finish with found true and the TAN exactly as written.{search}"""

        async def check(result, _evidence):
            """A look-up that found no TAN keeps searching instead of handing the portal a non-TAN."""
            if result.get("found") and readable(str(result.get("tan") or "").strip()):
                return result, ""
            if result.get("found"):
                return result, ("Not done: you found the message but gave no TAN as written in it. Open that message "
                                "and finish with its TAN exactly as written.")
            return result, ("Not done: no signing-TAN message found yet. Search the mailbox for it (newest first, "
                            "every folder), open it and finish with found true and its TAN.")

        found = await llm.investigate(mail_tab, system(task), mission,
                                      obj(found=BOOL, tan=STR, request=STR, subject=STR),
                                      min(deadline, time.time() + 120), "tan", max_steps=16, check=check)
        found.pop("evidence", None)
        if found.get("found") and readable(str(found.get("tan") or "").strip()):
            return json.dumps(found, ensure_ascii=False)
        # a finish forced at the step or time limit skips the check: never hand the portal what isn't a TAN
        llm.log("tan", "no TAN read")
        return json.dumps({"found": False, "reported": found, "next": "No TAN was read: call get_tan again."},
                          ensure_ascii=False)

    held: set[str] = set()  # positions held back once; held again means "this page asks for it elsewhere or not at all"

    async def form(args):
        steps = args.get("steps") or []
        if bid.done() and "off" not in held and (missing := unentered(steps, bid.result()[0])):
            positions = {m.split()[1] for m in missing}
            if positions & held:
                held.add("off")
            else:
                held.update(positions)
                llm.log("submit", f"form held: {'; '.join(missing)}")
                return ("Not run: this call enters a position's unit price but not " + "; ".join(missing) +
                        ". If this page has a field for it (even one already showing another value), add it in this "
                        "page's number format and send the call again; if it has none, send the same call again.")
        return await asyncio.wait_for(tab.act("form", args), llm.TOOL_TIMEOUT)

    async def verify_summary(_args):
        """Read-back before signing (I6b): every unit price and the total as calculated must be on the summary, and
        the breakdown values too once the summary shows any of them (a run typed one position's bonus as 0)."""
        answer, _, _ = await bid
        page = await tab.read() + await tab.read(14000)

        def shows(value: str) -> bool:  # a whole number on the page: 0,50 is not inside 10,50
            return re.search(rf"(?<![\d.,]){re.escape(value)}(?!\d)", page) is not None

        expected = {f"position {p['position']} unit price": german(p["unit_price"]) for p in answer["positions"]}
        expected["total net"] = german(answer["total_net"])
        breakdown = {f"position {p['position']} {label}": german(p[key]) for p in answer["positions"]
                     for key, label in OPTIONAL if p.get(key)}
        if any(shows(value) for value in breakdown.values()):
            expected |= breakdown
        wrong = [f"{name} {value}" for name, value in expected.items() if not shows(value)]
        llm.log("submit", f"verify_summary: {'; '.join(wrong) or 'all match'}")
        if not wrong:
            return "Every unit price and the total net match the calculated bid."
        return ("Not on this page as calculated: " + "; ".join(wrong) + ". Where the page shows a different value, "
                "correct that entry and verify again; a value this summary doesn't show at all is fine.")

    mission = f"""{login_line(tab.site)}
Your part: enter and sign the bid on this tender portal, following the brief's Submission section.
The bid is still being calculated. Start now: open this tender's bid submission and enter everything that doesn't
depend on the bid's values (the bidder's data from the brief, the kind of offer). The bidder's own mailbox address, if
a contact e-mail is asked for: {contact or 'unknown'}. On the first page that needs a value of the bid (a position,
material, price, discount or total), call bid_values: it returns the bid once it is calculated (this can take
minutes; wait for it, don't leave the page).
Enter every value exactly (German number format, two decimals), one entry per position; positions may come in any
order, so check which position each page is for. Each model step costs time: enter a whole position, or any other
page, with one form call and end it with the page's next-step button. A configurator's dependent choices go into that
same call, each followed by its apply button, without reading a choice's options first: the form tool waits for the
page after every step and picks an option by its exact text, its beginning or any part of it, so a material number
alone is enough where an option shows more after it. Once you know the labels of the configurator's choices (at the
latest after the first position), enter every position in one call. Name each choice by its field label: refs are
lost when a choice is applied, so a step by ref only works before the first apply of a call. A step that finds no
matching option stops the call and lists the options the page offers (the page may word a value differently than the
specification bid_values gives): send the rest of that page again in one form call, with that step in the page's wording.
Fields in collapsed sections are opened by the form tool. Never add extra positions, never skip a
position unless it is listed to omit, never tick an option to add our own general terms and conditions. Before you request the signing
TAN, call verify_summary on the summary page and correct what it reports. When the form asks for the signing TAN,
request it once, then call get_tan with the portal's message (the newest request wins; a new request invalidates the
old TAN; a TAN is valid for five minutes). Review the summary, then submit bindingly; the run ends when the bid is accepted.
If a value is rejected, read the message and fix it. Finish with what the portal confirmed."""
    tools = [llm._fn("bid_values", "The calculated bid: positions, materials, quantities, prices, discount, total. "
                     "Waits until the bid is calculated."),
             llm._fn("get_tan", "After requesting a TAN: look up the newest signing TAN in the bidder's mailbox.",
                     {"portal_message": {"type": "string", "description": "what the portal said about the request"}}),
             llm._fn("verify_summary", "On the summary page before the TAN: compare it with the calculated bid.")]
    hurry = ("Time is almost up and an unsigned bid scores nothing. Stop entering values: omit every position not "
             "completely entered yet with the form's omit option, go to the summary, request the TAN unless you already "
             "did, get it with get_tan, and submit the bid bindingly now. Call finish only after the portal accepted it.")
    return await llm.investigate(tab, system(task), mission, obj(confirmation=STR), deadline, "submit",
                                 extra_tools=tools, handlers={"bid_values": bid_values, "get_tan": fetch_tan,
                                           "verify_summary": verify_summary, "form": form}, max_steps=70,
                                 warn_at=SIGN_BY, warning=hurry)
