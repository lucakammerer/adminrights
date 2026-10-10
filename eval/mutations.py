"""Changes to public-1's recorded evidence that a private dataset could bring, for tools/resolver_eval.py: each case
edits the kept pages and says how the facts in eval/public-1/gather-facts.json change with it. Public-1 values on
purpose: local test data, never copied into agent/.
"""
import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Case:
    name: str
    about: str
    edits: list[Callable[[dict], None]] = field(default_factory=list)
    facts: Callable[[dict], None] = lambda facts: None

    def apply(self, results: dict) -> dict:
        for edit in self.edits:
            edit(results)
        return results

    def expect(self, facts: dict) -> dict:
        self.facts(facts)
        return facts


def page(results: dict, agent: str, *needles: str) -> str:
    """The one kept page of an agent that contains every needle; a recording without it fails loudly."""
    found = [p for p in results[agent]["evidence"] if all(n in p for n in needles)]
    if len(found) != 1:
        raise LookupError(f"{agent}: {len(found)} kept pages contain {needles}")
    return found[0]


def add(agent: str, needles: tuple[str, ...], *subs: tuple[str, str]):
    """Keep one more page: a copy of the page with these needles, rewritten by (regex, replacement) pairs."""
    def edit(results):
        text = page(results, agent, *needles)
        for pattern, replacement in subs:
            text, count = re.subn(pattern, replacement, text)
            if not count:
                raise LookupError(f"{agent}: {pattern!r} not in the page with {needles}")
        results[agent]["evidence"].append(text)
    return edit


def rewrite(agent: str, needles: tuple[str, ...], *subs: tuple[str, str]):
    """Rewrite the page with these needles in place."""
    def edit(results):
        pages = results[agent]["evidence"]
        index = pages.index(page(results, agent, *needles))
        for pattern, replacement in subs:
            pages[index], count = re.subn(pattern, replacement, pages[index])
            if not count:
                raise LookupError(f"{agent}: {pattern!r} not in the page with {needles}")
    return edit


def qa(number: int, utc: str, answer: str):
    """One more tender Q&A answer, on a page of its own, dated `utc` (the portal shows Athens time, UTC+2)."""
    local = f"{utc[8:10]}.{utc[5:7]}.{utc[:4]}, {int(utc[11:13]) + 2:02d}:{utc[14:16]}"
    text = (f"### Tender Q&A answer {number} for VG-2027-7093\n# Antworten der Vergabestelle\n"
            f"| Nr. | Datum (Athen) | Frage und Antwort\n| {number} |\n"
            f"[button \"Eingang\" (info: {local} · {utc})] (tooltip: {local} · {utc}) |\n"
            f"[summary (collapsed, content below)]\n{answer}\nZeitzone: Europe/Athens")
    return lambda results: results["tender_portal"]["evidence"].append(text)


def director(date: str, *subs: tuple[str, str]):
    """Another director approval: a copy of the latest one, dated `date` (dd.mm.yyyy, hh:mm, Berlin time)."""
    day, month = date[:2], date[3:5]
    return add("webmail", ("conditional-7571",), ("conditional-7571", "conditional-7599"),
               (r"24\.01\.2027, 17:00", date), (r"\(24\.01\.2027 17:00\) latest discount approval", f"({date})"),
               (r"01/24 \(MM/TT\)", f"{month}/{day} (MM/TT)"), *subs)


def facts_set(*path_value):
    """Facts changed by the case: (path, value) pairs, a path being the keys from the facts' root."""
    def change(facts):
        for path, value in path_value:
            node = facts
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
    return change


CASES: list[Case] = [
    Case("recorded", "the evidence as recorded"),
    Case("director-newer", "a newer valid approval (25.01 08:00 Berlin) replaces the 5 % one with 7 %",
         [director("25.01.2027, 08:00", ("genehmige ich 5 %", "genehmige ich 7 %"))],
         facts_set((("commercials", "discount_percent"), 7))),
    Case("director-future", "an approval dated after the scenario date (25.01 14:00 Berlin) never applies",
         [director("25.01.2027, 14:00", ("genehmige ich 5 %", "genehmige ich 9 %"))]),
    Case("director-look-alike", "a newer approval for the look-alike reference VG-2027-7093-A never applies",
         [director("25.01.2027, 08:00", ("genehmige ich 5 %", "genehmige ich 9 %"), (r"VG-2027-7093(?!-)", "VG-2027-7093-A"))]),
    Case("director-wrong-sender", "a newer approval from a sender who may not approve never applies",
         [director("25.01.2027, 08:00", ("genehmige ich 5 %", "genehmige ich 9 %"), ("leitung@", "vertrieb@"))]),
    Case("index-window", "the scenario date falls into the older metal-index window (2.75 until 25.01)",
         [rewrite("webmail", ("MET-4607 = 3,15",), ("gültig 01.12.2026 bis 24.01.2027", "gültig 01.12.2026 bis 25.01.2027"),
                  ("gültig 25.01.2027 bis 28.02.2027", "gültig 26.01.2027 bis 28.02.2027"))],
         facts_set((("commercials", "metal_index"), 2.75))),
    Case("packaging-decimal-comma", "the packaging tariff written with a decimal comma (13,25)",
         [rewrite("webmail", ("VP-1134: 13.25",), ("Dezimalpunkt, keine Tausendertrennzeichen", "Dezimalkomma"),
                  ("13.25 EUR", "13,25 EUR"))]),
    Case("quantity-newer", "a newer quantity change for 01.04 (23 Stk, before the scenario date) applies",
         [qa(8164, "2027-01-25T08:30:00Z", "Für Position 01.04 beträgt die verbindliche Gesamtmenge 23 Stk.\n"
             "Mengenänderung\nVerbindliche Gesamtmenge: Position 01.04: 23 (neue Gesamtmenge).")],
         facts_set((("requirements", "01.04", "final_quantity_pieces"), 23))),
    Case("quantity-future", "a quantity change for 01.04 dated after the scenario date never applies",
         [qa(8164, "2027-01-25T12:00:00Z", "Für Position 01.04 beträgt die verbindliche Gesamtmenge 30 Stk.\n"
             "Mengenänderung\nVerbindliche Gesamtmenge: Position 01.04: 30 (neue Gesamtmenge).")]),
    Case("quantity-sets", "a newer change for 01.05 in sets (28 Satz × 5 pieces) applies",
         [qa(8164, "2027-01-25T08:30:00Z", "Für Position 01.05 beträgt die verbindliche Gesamtmenge 28 Satz.\n"
             "Mengenänderung\nVerbindliche Gesamtmenge: Position 01.05: 28 (neue Gesamtmenge).")],
         facts_set((("requirements", "01.05", "final_quantity_pieces"), 140))),
    Case("quantity-withdrawn", "the answer that set 01.01 to 25 is withdrawn: the older 26 applies again",
         [qa(8164, "2027-01-25T08:30:00Z", "Die Antwort auf Rückfrage 3916 wird ersatzlos zurückgezogen "
             "(Übertragungsfehler). Weitere Antworten zu Position 01.01 bleiben unverändert gültig.")],
         facts_set((("requirements", "01.01", "final_quantity_pieces"), 26))),
]
