"""Tender portal agent: positions and every Q&A from the tender portal. See README.md."""
import re

import llm
from agents.common import STR, NUM, SYSTEM, arr, context, login_line, obj, site


RESULT = obj(
    tender_reference=STR, title=STR,
    positions=arr(obj(position=STR, description=STR, quantity=NUM, unit=STR)),
    clarifications=arr(obj(number=STR, date=STR, question=STR, answer=STR)),
    other_relevant_facts=STR)


async def run(task, tab, deadline):
    ref = re.search(r"\(([^()]+)\)\.", task["brief"])
    mission = f"""{context(task)}

{login_line(site(task, tab.site['siteId']))}
Your part: on this tender portal, find the tender in the brief (exact reference{f' {ref.group(1)}' if ref else ''}).
If its documents need an expression of interest ("Teilnahme bekunden"), give it. Collect:
1. the bill of quantities: every position with its id, description, quantity and unit (Stück, Satz, ...);
2. every bidder Q&A / clarification (all pages), each with its number, date, question and full answer, word for word:
   they change quantities, withdraw earlier answers, and assign keys (Konditionsgruppe, tariffs, delivery
   commitments, setup pools, project bonus, technical amendments to specification revisions);
3. anything else the brief's rules need that you find here (documents, ZIPs).
Keep the bill of quantities and every Q&A page with save_evidence as you read them.
Do not start the bid submission (Angebotsabgabe) yet. Finish with the result."""
    return await llm.investigate(tab, SYSTEM, mission, RESULT, deadline, "tender-portal", max_steps=45)
