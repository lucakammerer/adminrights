"""Webmail agent: approvals and condition mails from the sales mailbox. See README.md."""
import llm
from agents.common import STR, SYSTEM, context, login_line, mail_records, obj


RESULT = obj(kept=STR, own_address=STR, other_relevant_facts=STR)


def wanted(brief: str) -> str:
    """The records to find, as this run's brief names them; without any, the model derives them from the rules."""
    found = mail_records(brief)
    if not found["records"]:
        return ("The brief's rules name the records you need (approvals, condition and rate messages); derive each "
                "one's subject and sender from the rules above.")
    domain = found["domain"] or "the bidder's own mailbox domain (the mailbox shows its own address)"
    lines = []
    for r in found["records"]:
        sender = f"from {r['sender']}@" if r["sender"] else "sender as the rule says"
        lines.append(f'- subject "{r["subject"]}", {sender}' if r["subject"]
                     else f"- {sender}, no subject given; the rule: {r['rule']}")
    return (f"The records the brief's rules name, as the brief states them. Every sender is the local part at {domain}; "
            "a sender with another domain, even a similar one, is someone else:\n" + "\n".join(lines))

async def run(task, tab, deadline):
    mission = f"""{context(task)}

{login_line(tab.site)}
Your part: in this sales mailbox, find every message the brief's rules need for this exact tender reference, in every
folder the mailbox has (a search may cover only the open folder).
{wanted(task["brief"])}
First search the exact reference by itself in each folder and read every result page. Then, for each record above
that you have not found yet, search the reference plus one word of its subject in each folder and read every result
page. A record without a subject is recognised by its sender and its meaning (e.g. an approval for this reference).
Be quick: once your first search shows how a search URL looks, fetch the remaining searches and keep their relevant
messages in one turn. Keep each relevant message with save_evidence (its own message URL, so sender, date and full
body are kept). Keep superseded and conditional records too (they are judged later); skip messages for other, merely
similar references and the signing-TAN mails. Finish with a one-line list of what you kept and the
mailbox's own e-mail address (own_address) as shown on the site."""
    return await llm.investigate(tab, SYSTEM, mission, RESULT, deadline, "webmail", max_steps=60)
