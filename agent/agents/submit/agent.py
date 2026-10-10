"""Submit agent: enters and signs the bid, with a TAN sub-agent in the mailbox. See README.md."""
import json
import time

import llm
from agents.common import STR, SYSTEM, context, login_line, obj, site


def german(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def run(task, tab, mail_tab, answer: dict, omitted: list, specs: dict, contact: str, deadline):
    async def fetch_tan(args):
        mission = f"""{login_line(mail_tab.site)}
In this mailbox (you may already be logged in), find the newest signing-TAN message for tender
{answer['tender_reference']}. The tender portal just said: "{args.get('portal_message', '')}". Pick the message for
that request (highest request number / newest), open it and finish with the TAN exactly as written."""
        found = await llm.investigate(mail_tab, SYSTEM, mission, obj(tan=STR, request=STR, subject=STR),
                                      min(deadline, time.time() + 120), "tan", max_steps=12)
        found.pop("evidence", None)
        return json.dumps(found, ensure_ascii=False)

    rows = "\n".join(
        f"- position {p['position']}: material {p['material_number']} ({specs.get(p['position'], '')}), "
        f"quantity {p['quantity']} Stück, unit price "
        f"{german(p['unit_price'])} EUR, lead time {p['lead_time_weeks']} weeks, base price {german(p['base_unit_price'])}, "
        f"surcharge per piece {german(p['surcharge_per_unit'])}, packaging per piece {german(p['packaging_per_unit'])}, "
        f"project bonus for the position {german(p['rebate_total'])}" for p in answer["positions"])
    mission = f"""{context(task)}

{login_line(site(task, tab.site['siteId']))}
The bid is calculated. Your part: enter and sign it on this tender portal, following the brief's Submission section.
The bidder's own mailbox address, if a contact e-mail is asked for: {contact or 'unknown'}.
Bid ({answer['decision']}), tender {answer['tender_reference']}, discount {german(answer['discount_percent'])} %,
total net {german(answer['total_net'])} EUR (net; a displayed gross amount with VAT is not it):
{rows or '(no positions: no bid)'}
{f"Unfinished positions to omit with the form's omit option (partial submission): {', '.join(omitted)}" if omitted else ''}
Enter every value exactly (German number format, two decimals), one entry per position; positions may come in any
order, so check which position each page is for. Use the form tool to fill a whole page (configurator choices with
their apply buttons, quantity, prices, breakdown, lead time, then the next-step button) in one call. Never add extra
positions, never skip a position unless it is listed to omit, never tick your own terms and conditions (AGB). When the form asks for the signing TAN,
request it once, then call get_tan with the portal's message (the newest request wins; a new request invalidates the
old TAN; a TAN is valid for five minutes). Review the summary, then submit bindingly; the run ends when the bid is accepted.
If a value is rejected, read the message and fix it. Finish with what the portal confirmed."""
    tools = [llm._fn("get_tan", "After requesting a TAN: look up the newest signing TAN in the bidder's mailbox.",
                     {"portal_message": {"type": "string", "description": "what the portal said about the request"}})]
    return await llm.investigate(tab, SYSTEM, mission, obj(confirmation=STR), deadline, "submit",
                                 extra_tools=tools, handlers={"get_tan": fetch_tan}, max_steps=70)
