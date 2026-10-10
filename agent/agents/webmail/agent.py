"""Webmail agent: approvals and condition mails from the sales mailbox. See README.md."""
import llm
from agents.common import STR, SYSTEM, context, login_line, obj


RESULT = obj(kept=STR, own_address=STR, other_relevant_facts=STR)


async def run(task, tab, deadline):
    mission = f"""{context(task)}

{login_line(tab.site)}
Your part: in this sales mailbox, find every message the brief's rules need for this exact tender reference, in every
folder the mailbox has (a search may cover only the open folder). First search the exact reference by itself in each
folder and read every result page. Then, for each record kind the brief's rules name that you have not found yet,
search the reference plus one word of the subject the brief authorizes for it, and read every result page. The
discount approval is the message from the sender the brief names for it that approves a discount for this reference.
Be quick: once your first search shows how a search URL looks, fetch the remaining searches and keep their relevant
messages in one turn. Keep each relevant message with save_evidence (its own message URL, so sender, date and full
body are kept). Keep superseded and conditional records too (they are judged later); skip messages for other, merely
similar references and the signing-TAN mails. Finish with a one-line list of what you kept and the
mailbox's own e-mail address (own_address) as shown on the site."""
    return await llm.investigate(tab, SYSTEM, mission, RESULT, deadline, "webmail", max_steps=60)
