"""Webmail agent: approvals and condition mails from the sales mailbox. See README.md."""
import llm
from agents.common import ALSO_KEEP, STR, login_line, mail_records, obj, system, technical_records


RESULT = obj(kept=STR, own_address=STR, search_url=STR, other_relevant_facts=STR)
AGENTS = 3  # agents on the mailbox at once, each in its own tab with its share of the records


def groups(brief: str) -> list[list[dict]]:
    """The brief's records shared out to parallel agents: the technical release alone (the specification resolver and
    with it the ERP searches wait for it), the others in turns. Fewer steps one after another per agent: under load a
    step took 15-30 s, and one agent for every record took 14-20 steps. Too few records for that: one agent for all."""
    records = mail_records(brief)["records"]
    technical = technical_records(brief)
    rest = [r for r in records if r not in technical]
    if len(records) < AGENTS:
        return [records]
    return [part for part in [technical] + [rest[i::AGENTS - 1] for i in range(AGENTS - 1)] if part]


def merge(parts: list[dict]) -> dict:
    """The parallel agents' results as one: every kept page once, the first address and search URL reported."""
    merged = {"kept": " | ".join(str(p.get("kept") or "") for p in parts if p.get("kept")),
              "evidence": list(dict.fromkeys(page for p in parts for page in p.get("evidence") or []))}
    for key in ("own_address", "search_url", "other_relevant_facts"):
        merged[key] = next((p[key] for p in parts if p.get(key)), "")
    if any(p.get("forced") for p in parts):
        merged["forced"] = True
    return merged


def wanted(records: list[dict]) -> str:
    """The records to find, as this run's brief names them; without any, the model derives them from the rules."""
    if not records:
        return ("The brief's rules name the records you need (approvals, condition and rate messages); derive each "
                "one's subject and sender from the rules above.")
    lines = []
    for r in records:
        sender = f"from {r['sender']}@" if r["sender"] else "sender as the rule says"
        lines.append(f'- subject "{r["subject"]}", {sender}' if r["subject"]
                     else f"- {sender}, no subject given; the rule: {r['rule']}")
    return ("The records the brief's rules name, as the brief states them. Every sender is the local part at the "
            "bidder's own mailbox domain (the mailbox shows its own address); a sender with another domain, even a "
            "similar one, is someone else:\n" + "\n".join(lines))


async def run(task, tab, deadline, records: list[dict] | None = None, alone: bool = True, tag: str = "webmail"):
    """records: this agent's share of the brief's records (default all); alone=False tells it other agents look for
    the rest in tabs of their own."""
    records = mail_records(task["brief"])["records"] if records is None else records
    others = "" if alone else ("\nOther agents look for the brief's other records in tabs of their own at the same time: "
                               "look only for the records above.")
    mission = f"""{login_line(tab.site)}
Your part: in this sales mailbox, find every message the brief's rules need for this exact tender reference, in every
folder the mailbox has (a search may cover only the open folder).
{wanted(records)}{others}
First search the exact reference by itself in each folder and read every result page; keep each message of a record
above as soon as a result list shows it, several in one turn, with save_evidence on its own message URL (so sender,
date and full body are kept). Then, only for the records above still missing, search the reference plus one word of
its subject in each folder. Never search without the reference: a word or a sender alone lists other tenders' mail. A
record without a subject is recognised by its sender and its meaning (e.g. an approval for this reference). Once a
search URL's shape is known, fetch independent searches and result pages in one turn. Stop searching once every record
above is kept or its searches came back empty. Keep superseded and conditional records too (they are judged later);
skip messages for other, merely similar references and the signing-TAN mails. {ALSO_KEEP} Finish with a one-line list
of what you kept, the mailbox's own e-mail address (own_address) as shown on the site, and the URL of one search you
ran (search_url; the signing-TAN look-up later searches the same way)."""
    return await llm.investigate(tab, system(task), mission, RESULT, deadline, tag, max_steps=60)
