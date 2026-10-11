"""Supplier portal agent: the current specification revision from the supplier portal. See README.md."""
import llm
from agents.common import ALSO_KEEP, NOT_HERE, NUM, STR, SYSTEM, arr, context, login_line, obj


RESULT = obj(
    document=STR, current_revision=STR, revisions=arr(obj(revision=STR, date=STR, status=STR)),
    requirements=arr(obj(requirement=STR, position=STR, bore_mm=NUM, stroke_mm=NUM, pressure_bar=NUM, mounting=STR,
                         certification=STR, catalogue_group=STR)),
    other_relevant_facts=STR)


async def run(task, tab, deadline):
    mission = f"""{context(task)}

{login_line(tab.site)}
Your part: on this supplier portal, find the buyer's technical specification for the tender in the brief. Find out
which revision is marked current/valid (its status, not whichever opens first). Read every requirement of that
revision (all pages) with bore, stroke, pressure, mounting, certification and catalogue group (the brief names the
term the specification uses). Its wording may make the stroke a usable stroke with an end-reserve key, as the brief's
technical rule describes, or give pieces per set: the kept pages carry it word for word, so don't copy it out. Also
list all revisions with date and status. Keep the revision list and every requirement page of the current revision
with save_evidence.
{ALSO_KEEP} {NOT_HERE} Finish with the result."""
    return await llm.investigate(tab, SYSTEM, mission, RESULT, deadline, "supplier-portal", max_steps=40)
