"""Submit agent: enters and signs the bid, with a TAN sub-agent in the mailbox. See README.md."""
import json
import time

import llm
from agents.common import BOOL, STR, SYSTEM, context, login_line, obj

SIGN_BY = 180  # seconds before the deadline: stop entering, omit what is unfinished, sign (TAN look-up ~2 min)


def german(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def run(task, tab, mail_tab, answer: dict, omitted: list, specs: dict, contact: str, deadline):
    async def fetch_tan(args):
        mission = f"""{login_line(mail_tab.site)}
In this mailbox (you may already be logged in), find the newest signing-TAN message for tender
{answer['tender_reference']}. The tender portal just said: "{args.get('portal_message', '')}". Search for it
yourself: a list on the page may be left from an earlier search, and its newest message is not necessarily a TAN
message. Pick only a message that gives a signing TAN for this tender, the one for that request (highest request
number / newest), open it and finish with found true and the TAN exactly as written."""

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
        """Read-back before signing (I6b): every unit price and the total as calculated must be on the summary."""
        page = await tab.read() + await tab.read(14000)
        expected = {f"position {p['position']} unit price": german(p["unit_price"]) for p in answer["positions"]}
        expected["total net"] = german(answer["total_net"])
        wrong = [f"{name} {value}" for name, value in expected.items() if value not in page]
        if not wrong:
            return "Every unit price and the total net match the calculated bid."
        return ("Not on this page as calculated: " + "; ".join(wrong) + ". Where the page shows a different value, "
                "correct that entry and verify again; a value this summary doesn't show at all is fine.")

    rows = "\n".join(
        f"- position {p['position']}: material {p['material_number']} ({specs.get(p['position'], '')}), "
        f"quantity {p['quantity']} pieces, unit price "
        f"{german(p['unit_price'])} EUR, lead time {p['lead_time_weeks']} weeks, base price {german(p['base_unit_price'])}, "
        f"surcharge per piece {german(p['surcharge_per_unit'])}, packaging per piece {german(p['packaging_per_unit'])}, "
        f"project bonus for the position {german(p['rebate_total'])}" for p in answer["positions"])
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
alone is enough where an option shows more after it. Once you know the labels of the configurator's choices (at the
latest after the first position), enter every position in one call. Name each choice by its field label: refs are
lost when a choice is applied, so a step by ref only works before the first apply of a call. A step that finds no
matching option stops the call and lists the options the page offers (the page may word a value differently than the
specification above): send the rest of that page again in one form call, with that step in the page's wording.
Fields in collapsed sections are opened by the form tool. Never add extra positions, never skip a
position unless it is listed to omit, never tick an option to add our own general terms and conditions. Before you request the signing
TAN, call verify_summary on the summary page and correct what it reports. When the form asks for the signing TAN,
request it once, then call get_tan with the portal's message (the newest request wins; a new request invalidates the
old TAN; a TAN is valid for five minutes). Review the summary, then submit bindingly; the run ends when the bid is accepted.
If a value is rejected, read the message and fix it. Finish with what the portal confirmed."""
    tools = [llm._fn("get_tan", "After requesting a TAN: look up the newest signing TAN in the bidder's mailbox.",
                     {"portal_message": {"type": "string", "description": "what the portal said about the request"}}),
             llm._fn("verify_summary", "On the summary page before the TAN: compare it with the calculated bid.")]
    hurry = ("Time is almost up and an unsigned bid scores nothing. Stop entering values: omit every position not "
             "completely entered yet with the form's omit option, go to the summary, request the TAN unless you already "
             "did, get it with get_tan, and submit the bid bindingly now. Call finish only after the portal accepted it.")
    return await llm.investigate(tab, SYSTEM, mission, obj(confirmation=STR), deadline, "submit",
                                 extra_tools=tools, handlers={"get_tan": fetch_tan, "verify_summary": verify_summary}, max_steps=70,
                                 warn_at=SIGN_BY, warning=hurry)
