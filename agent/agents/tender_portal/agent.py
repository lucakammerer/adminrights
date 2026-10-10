"""Tender portal agent: positions and every Q&A from the tender portal. See README.md."""
import llm
from agents.common import ALSO_KEEP, INT, NOT_HERE, NUM, STR, arr, login_line, obj, reference, system


RESULT = obj(
    tender_reference=STR, title=STR,
    positions=arr(obj(position=STR, description=STR, quantity=NUM, unit=STR)),
    clarifications=arr(obj(number=STR, date=STR, evidence=INT)),
    other_relevant_facts=STR)


async def run(task, tab, deadline):
    ref = reference(task["brief"])
    mission = f"""{login_line(tab.site)}
Your part: on this tender portal, find the tender in the brief (exact reference{f' {ref}' if ref else ''}).
If its documents need an expression of interest (the brief's Submission section names that step), give it. Collect:
1. the bill of quantities: every position with its id, description, quantity and unit exactly as written (pieces,
   sets, ...);
2. every bidder Q&A / clarification (all pages), kept with save_evidence so its full question and answer reach the
   analyst word for word: they change quantities, withdraw earlier answers, and assign keys (the condition groups,
   tariffs, delivery commitments, setup pools, project bonus the brief's rules name, technical amendments to
   specification revisions). In the result, list each one only with its number, date and the evidence number it is
   kept as; don't copy the text, not into notes either (a kept page needs no note);
3. anything else the brief's rules need that you find here (documents, ZIPs).
Keep the bill of quantities and every Q&A page with save_evidence as you read them.
{ALSO_KEEP} {NOT_HERE}
Do not start the bid submission yet. Finish with the result."""
    return await llm.investigate(tab, system(task), mission, RESULT, deadline, "tender-portal", max_steps=45)
