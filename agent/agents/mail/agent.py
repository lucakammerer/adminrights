"""Mail agent: approvals and condition mails from the sales mailbox. See README.md."""
import llm
from agents.common import STR, SYSTEM, context, login_line, obj, site


RESULT = obj(kept=STR, own_address=STR, other_relevant_facts=STR)


async def run(task, tab, deadline):
    mission = f"""{context(task)}

{login_line(site(task, tab.site['siteId']))}
Your part: in this sales mailbox, find every message the brief's rules need for this exact tender reference, in every
folder (inbox and archive are searched separately). Search with the reference plus one topic word at a time:
Rabattfreigabe (discount approvals from leitung@), Konditionsregeln, Preisindizes, Rüstpools (from kalkulation@),
Technikfreigabe (technik@), Verpackungstarife, Terminfreigabe (logistik@), Devisenfixing, Projektbonus (finanzen@).
Be quick: once your first search shows how a search URL looks, fetch all the other searches (every topic, every
folder) in one turn, then keep all relevant messages in one turn. Read every result page. Keep each relevant message
with save_evidence (its own message URL, so sender, date and full
body are kept). Keep superseded and conditional ones too (they are judged later); skip messages for other references
(a suffix like -A is another tender) and the signing-TAN mails. Finish with a one-line list of what you kept and the
mailbox's own e-mail address (own_address) as shown on the site."""
    return await llm.investigate(tab, SYSTEM, mission, RESULT, deadline, "mail", max_steps=60)
