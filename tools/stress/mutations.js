// Stress level S2 mutations (I24, I20, rule 19): rewrite a page the way another site would show the same facts.
// Applied live by run_agents.py --mutate (each read-only page rewritten before the agent sees it) and offline by
// tests/test_mutations.py (recorded pages). Called as (opts) => {relabelled, decoys, shuffled, rows, reformatted,
// invisible, dates, framed}; opts.seed makes every choice repeatable. It never changes a fact: labels get synonyms, numbers
// that carry an explicit locale hint are rewritten in the other locale with the hint changed to match, menus and the
// rows of plain data tables are shuffled, identifiers get invisible characters inside, some dates show only weekday
// and time with the full moment in a <time> attribute, hidden decoys are added, and
// the main content moves into an extra same-origin frame.
(opts) => {
  let seed = (opts && opts.seed) || 1
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  const doc = (opts && opts.doc) || document
  const stats = { relabelled: 0, decoys: 0, shuffled: 0, rows: 0, reformatted: 0, framed: 0, grids: 0, scripted: 0, invisible: 0, dates: 0 }

  // 1. Labels: whole-word synonyms on controls, headings and table headers only (never in data cells).
  const SYNONYMS = {
    "Suche": "Recherche", "Suchen": "Recherchieren", "Weiter": "Fortfahren", "Zurück": "Vorherige",
    "Anmelden": "Einloggen", "Nachricht": "Mitteilung", "Nachrichten": "Mitteilungen", "Posteingang": "Eingang",
    "Archiv": "Ablage", "Dokumente": "Unterlagen", "Status": "Zustand", "Datum": "Stand", "Menge": "Anzahl",
    "Preis": "Betrag", "Lieferzeit": "Lieferfrist", "Bestand": "Vorrat", "Search": "Find", "Next": "Continue",
    "Date": "Dated", "Quantity": "Amount", "Price": "Cost"}
  const words = new RegExp(`(^|[^\\p{L}])(${Object.keys(SYNONYMS).join("|")})(?=$|[^\\p{L}])`, "gu")
  for (const el of doc.querySelectorAll("button, a, th, h1, h2, h3, h4, label, summary, legend, [role=tab]")) {
    for (const node of el.childNodes) {
      if (node.nodeType !== 3) continue
      const next = node.textContent.replace(words, (m, pre, w) => pre + SYNONYMS[w])
      if (next !== node.textContent) { node.textContent = next; stats.relabelled++ }
    }
  }

  // 2. Number formats: "1,234.5 (en-US)" <-> "1.234,5 (de-DE)", only where the page states the locale, also when the
  // number and its hint sit in separate elements (an aria-label that repeats them is rewritten alike).
  const swap = (n) => n.replace(/[.,]/g, (c) => (c === "." ? "," : "."))
  const other = (loc) => (loc === "de-DE" ? "en-US" : "de-DE")
  const HINTED = /^\s*(\d[\d.,]*\d|\d)\s*\((de-DE|en-US)\)\s*$/
  for (const el of doc.querySelectorAll("body *")) {
    if (!HINTED.test(el.textContent) || [...el.children].some((c) => HINTED.test(c.textContent))) continue
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const node = walker.currentNode
      node.textContent = node.textContent.replace(/\d[\d.,]*\d|\d/g, swap).replace(/de-DE|en-US/g, other)
    }
    const label = el.getAttribute("aria-label")
    if (label) el.setAttribute("aria-label", label.replace(/\d[\d.,]*\d|\d/g, swap).replace(/de-DE|en-US/g, other))
    stats.reformatted++
  }
  // 3. Shuffle lists whose order carries no meaning: navigation menus and option-like lists.
  for (const list of doc.querySelectorAll("nav ul, nav ol, ul[role=menu], ul.menu")) {
    const items = [...list.children]
    if (items.length < 3) continue
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]]
    }
    items.forEach((it) => list.appendChild(it))
    stats.shuffled++
  }

  // 3b. Rows of plain data tables: their order is never what a value depends on (dates and ids are in the rows).
  // Tables with form controls or row spans are left alone.
  for (const body of doc.querySelectorAll("tbody")) {
    const rows = [...body.children].filter((r) => r.tagName === "TR")
    if (rows.length < 3 || body.querySelector("input, select, textarea, button, [rowspan]")) continue
    if (new Set(rows.map((r) => r.children.length)).size !== 1) continue
    for (let i = rows.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [rows[i], rows[j]] = [rows[j], rows[i]]
    }
    rows.forEach((r) => body.appendChild(r))
    stats.rows++
  }

  // 3c. Invisible format characters inside identifiers (trap 10): zero-width, bidi marks, invisible separators, a tag.
  const INVISIBLE = ["\u200b", "\u200e", "\u200f", "\u202c", "\u2060", "\u2063", "\u2066", "\u{e0020}"]
  const ID = /\b(?:[A-Za-z]{1,6}-?\d[\w-]*\d|\d{5,})\b/g
  const texts = doc.createTreeWalker(doc.body || doc.documentElement, NodeFilter.SHOW_TEXT)
  while (texts.nextNode()) {
    const node = texts.currentNode
    if (node.parentElement && node.parentElement.closest("script, style, textarea, select, option")) continue
    const next = node.textContent.replace(ID, (id) => {
      const at = 1 + Math.floor(rand() * (id.length - 1))
      stats.invisible++
      return id.slice(0, at) + INVISIBLE[Math.floor(rand() * INVISIBLE.length)] + id.slice(at)
    })
    if (next !== node.textContent) node.textContent = next
  }

  // 3d. Dates the way mail and portal software shows them (trap 11): about half of the "dd.mm.yyyy[, hh:mm]" and ISO dates
  // become a <time> that shows only the weekday and time and keeps the full moment in its datetime attribute.
  const DATE = /\b(?:(\d{2})\.(\d{2})\.(\d{4})(?:,? (\d{2}:\d{2}))?|(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})[\d:.]*(Z|[+-]\d{2}:?\d{2})?)/g
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  const dated = []
  const walker = doc.createTreeWalker(doc.body || doc.documentElement, NodeFilter.SHOW_TEXT)
  while (walker.nextNode()) {
    const node = walker.currentNode
    if (node.parentElement && node.parentElement.closest("script, style, textarea, select, option, time")) continue
    if (DATE.test(node.textContent)) dated.push(node)
    DATE.lastIndex = 0
  }
  for (const node of dated) {
    const frag = doc.createDocumentFragment()
    let last = 0
    for (const m of node.textContent.matchAll(DATE)) {
      const all = m[0], iso = m[5] !== undefined
      const [d, mo, y, hm] = iso ? [m[7], m[6], m[5], m[8]] : [m[1], m[2], m[3], m[4]]
      const day = new Date(Date.UTC(+y, +mo - 1, +d)).getUTCDay()
      if (rand() < 0.5 || Number.isNaN(day)) continue
      frag.append(node.textContent.slice(last, m.index))
      const time = doc.createElement("time")
      time.setAttribute("datetime", iso ? all : `${y}-${mo}-${d}` + (hm ? `T${hm}` : ""))
      time.textContent = DAYS[day] + (hm ? ` ${hm}` : "")
      frag.append(time)
      last = m.index + all.length
      stats.dates++
    }
    if (!last) continue
    frag.append(node.textContent.slice(last))
    node.replaceWith(frag)
  }

  // 4. Hidden decoys (last, so they never change what the steps above match): a copy of a number-bearing text with other digits, hidden in one of four ways.
  const HIDE = [
    (e) => { e.className = "s2-hidden-rule" },
    (e) => { e.setAttribute("aria-hidden", "true") },
    (e) => { e.style.cssText = "display:none" },
    (e) => { e.hidden = true }]
  const style = doc.createElement("style")
  style.textContent = ".s2-hidden-rule { display: none }"
  ;(doc.head || doc.documentElement).appendChild(style)
  const ownText = (e) => [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("")
  const carriers = [...doc.querySelectorAll("td, dd, p, li, span, div")].filter((e) => /\d/.test(ownText(e)) &&
    ownText(e).length < 160 && !e.closest("script, style, select, button, a"))
  const step = Math.max(1, Math.floor(carriers.length / 12))
  for (const el of carriers.filter((_, i) => i % step === 0).slice(0, 12)) {
    const decoy = doc.createElement("span")
    decoy.textContent = " " + ownText(el).trim().replace(/\d/g, (d) => String((+d + 7) % 10)) + " S2DECOY"
    HIDE[stats.decoys % HIDE.length](decoy)
    el.appendChild(decoy)
    stats.decoys++
  }

  // 5. An extra same-origin frame around the main content (last, so the steps above changed the framed copy): the
  // page's styles go with it; a page with a form keeps its content where it is.
  // opts.widgets: markup of a framework app. Tables become styled rows of spans (no table tags, no roles) and every
  // other link a pointer element without href that a script on the page follows on click.
  if (opts && opts.widgets) {
    for (const table of [...doc.querySelectorAll("table")]) {
      if (table.querySelector("input, select, textarea, button, [rowspan], [colspan], table")) continue
      const grid = doc.createElement("div")
      for (const tr of table.querySelectorAll("tr")) {
        const row = doc.createElement("div")
        row.style.cssText = "display:flex;gap:16px"
        for (const cell of tr.children) {
          const span = doc.createElement("span")
          span.innerHTML = cell.innerHTML
          row.appendChild(span)
        }
        grid.appendChild(row)
      }
      table.replaceWith(grid)
      stats.grids++
    }
    const links = [...doc.querySelectorAll("a[href]")].filter((a) => !/^(#|javascript:|mailto:)/i.test(a.getAttribute("href")))
    links.filter((_, i) => i % 2 === 0).forEach((a) => {
      const span = doc.createElement("span")
      span.innerHTML = a.innerHTML
      try { span.dataset.go = new URL(a.getAttribute("href"), (opts && opts.base) || doc.baseURI).href }
      catch (e) { span.dataset.go = a.getAttribute("href") }
      span.style.cssText = "cursor:pointer;color:#06c"
      a.replaceWith(span)
      stats.scripted++
    })
    if (stats.scripted) {
      const script = doc.createElement("script")
      script.textContent = "document.addEventListener('click', (e) => { const t = e.target.closest('[data-go]'); " +
        "if (t) window.top.location.href = t.dataset.go })"
      const own = doc.querySelector("main") || doc.querySelector("article")  // still listening inside an extra frame
      for (const parent of new Set([own, doc.body || doc.documentElement].filter(Boolean))) parent.appendChild(script.cloneNode(true))
    }
  }

  const main = doc.querySelector("main") || doc.querySelector("article") || doc.body
  if (opts && opts.frame !== false && main && !main.querySelector("form") && rand() < 0.7) {
    const styles = [...doc.querySelectorAll("style, link[rel=stylesheet]")].map((e) => e.outerHTML).join("")
    const frame = doc.createElement("iframe")
    frame.setAttribute("title", "content")
    frame.style.cssText = "width:100%;height:2000px;border:0"
    const base = String((opts && opts.base) || doc.baseURI).replace(/"/g, "&quot;")  // links keep working, on the whole page
    frame.srcdoc = `<!doctype html><html><head><base href="${base}" target="_top">${styles}</head><body>${main.innerHTML}</body></html>`
    main.replaceChildren(frame)
    stats.framed++
  }
  return stats
}
