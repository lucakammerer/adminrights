// Page text the way assistive technology sees it: hidden decoys out, labels/tooltips/collapsed details in,
// same-origin iframes inlined, every control tagged with a ref the tools can act on.
// CSS-generated text (::before/::after), title tooltips of plain elements and canvases without text are kept or marked;
// off-screen and screen-reader-only text is kept but marked, since real values can live there and decoys too.
// Called as (opts) => {text, next, marked}. opts.doc: a fetched document without layout (only inline styles count);
// opts.root: a fetched document rendered in a hidden frame, so its own style rules decide what is hidden.
(opts) => {
  const ZW = /[​-‍⁠﻿­]/g
  const clean = (s) => (s || "").replace(ZW, "").replace(/[ \t\r\f\v ]+/g, " ")
  const BLOCK = new Set(["P", "DIV", "SECTION", "ARTICLE", "MAIN", "HEADER", "FOOTER", "NAV", "ASIDE", "UL", "OL", "LI",
    "TR", "TABLE", "FORM", "FIELDSET", "DL", "DT", "DD", "H1", "H2", "H3", "H4", "H5", "H6", "BR", "HR", "PRE",
    "BLOCKQUOTE", "DETAILS", "SUMMARY", "DIALOG", "FIGURE", "CAPTION", "LEGEND", "OUTPUT", "LABEL"])
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "META", "LINK"])
  const fetched = !!opts.doc || !!opts.root
  const styled = !opts.doc
  let next = opts.start || 1
  let marked = 0
  const out = []

  // A checkbox or radio made transparent under a styled label is still the control people tick: only display and
  // visibility hide it. Everything else with zero opacity or font size is hidden text (decoys).
  const toggle = (el) => el.tagName === "INPUT" && (el.type === "checkbox" || el.type === "radio")
  const hidden = (el) => {
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return true
    if (!styled) return /display\s*:\s*none|visibility\s*:\s*hidden/i.test(el.getAttribute("style") || "")
    const st = el.ownerDocument.defaultView.getComputedStyle(el)
    if (st.display === "none" || st.visibility === "hidden") return true
    return !toggle(el) && (st.opacity === "0" || parseFloat(st.fontSize) === 0)
  }
  // Positioned outside the page or clipped to (almost) nothing: not on screen, yet read by assistive technology.
  const offscreen = (el) => {
    if (!styled) return false
    const st = el.ownerDocument.defaultView.getComputedStyle(el)
    if (st.position !== "absolute" && st.position !== "fixed") return false
    const r = el.getBoundingClientRect()
    const away = r.right < 0 || r.bottom + el.ownerDocument.defaultView.scrollY < 0 || r.left >= 20000
    const clipped = (/rect\(\s*0(px)?[\s,]+0(px)?[\s,]+0(px)?[\s,]+0(px)?\s*\)/.test(st.clip) ||
      /inset\(\s*50%/.test(st.clipPath)) && r.width <= 2 && r.height <= 2
    return away || clipped
  }
  // Text a style rule adds before or after an element (content: "..." or attr(x)); decorative symbols are skipped.
  const generated = (el, which) => {
    if (!styled) return ""
    const c = el.ownerDocument.defaultView.getComputedStyle(el, which).content
    if (!c || c === "none" || c === "normal") return ""
    const attr = c.match(/^attr\(([\w-]+)\)$/)
    const text = attr ? el.getAttribute(attr[1]) || "" : /^["']/.test(c) ? c.slice(1, -1).replace(/\\(.)/g, "$1") : ""
    return /[\p{L}\p{N}]/u.test(text) ? clean(text).trim() : ""
  }
  // Hidden inside a container that may itself be hidden (a tooltip until hover): `visibility` is inherited, so a
  // child only counts as hidden when it hides itself, not because its container does.
  const hiddenWithin = (el) => {
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return true
    if (!styled) return /display\s*:\s*none|visibility\s*:\s*hidden/i.test(el.getAttribute("style") || "")
    const view = el.ownerDocument.defaultView, st = view.getComputedStyle(el)
    const inherited = el.parentElement && view.getComputedStyle(el.parentElement).visibility === "hidden"
    return st.display === "none" || st.opacity === "0" || parseFloat(st.fontSize) === 0 ||
      (st.visibility === "hidden" && !inherited)
  }
  // An element's text without its hidden descendants (decoys planted inside names, labels and tooltips).
  const textOf = (el) => {
    let t = ""
    for (const n of el.childNodes) {
      if (n.nodeType === 3) t += n.textContent
      else if (n.nodeType === 1 && !SKIP.has(n.tagName) && !hiddenWithin(n)) t += " " + textOf(n) + " "
    }
    return t
  }
  const labelOf = (el) => {
    const doc = el.ownerDocument
    const by = el.getAttribute("aria-labelledby")
    if (by) {
      const t = by.split(/\s+/).map((id) => doc.getElementById(id)).filter(Boolean).map(textOf).join(" ")
      if (clean(t).trim()) return clean(t).trim()
    }
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label")).trim()
    if (el.id) {
      const l = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`)
      if (l && clean(textOf(l)).trim()) return clean(textOf(l)).trim()
    }
    const wrap = el.closest("label")
    if (wrap && clean(textOf(wrap)).trim()) return clean(textOf(wrap)).trim()
    return clean(el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("name") || "").trim()
  }
  const described = (el) => {
    const ids = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean)
    const t = ids.map((id) => el.ownerDocument.getElementById(id)).filter(Boolean).map((e) => clean(textOf(e)).trim())
    return t.filter(Boolean).join("; ")
  }
  const ref = (el) => {
    if (fetched) return ""
    const n = next++
    el.setAttribute("data-aref", String(n))
    return n + ":"
  }
  const disabledMark = (el) => (el.disabled || el.closest("[inert],fieldset[disabled]") ? " (disabled)" : "")

  const control = (el) => {
    const tag = el.tagName
    const role = el.getAttribute("role")
    if (tag === "A" && el.hasAttribute("href")) {
      const name = clean(textOf(el)).trim() || labelOf(el)
      return `[${ref(el)}link "${name}" -> ${el.getAttribute("href")}]`
    }
    if (tag === "BUTTON" || role === "button" || role === "menuitem" || role === "tab" || role === "option" ||
        (tag === "INPUT" && ["submit", "button", "reset"].includes(el.type))) {
      const name = clean(textOf(el)).trim() || labelOf(el) || el.value || ""
      const d = described(el)
      return `[${ref(el)}button "${name}"${d ? ` (info: ${d})` : ""}${disabledMark(el)}]`
    }
    if (tag === "INPUT") {
      const t = el.type
      if (t === "hidden") return ""
      if (t === "checkbox" || t === "radio")
        return `[${ref(el)}${t} "${labelOf(el)}" ${el.checked ? "checked" : "unchecked"}${t === "radio" ? ` value=${el.value}` : ""}${disabledMark(el)}]`
      if (t === "range")
        return `[${ref(el)}slider "${labelOf(el)}" value=${el.value} min=${el.min || 0} max=${el.max || 100}${disabledMark(el)}]`
      return `[${ref(el)}input type=${t} "${labelOf(el)}" value="${el.value}"${disabledMark(el)}]`
    }
    if (tag === "TEXTAREA") return `[${ref(el)}textarea "${labelOf(el)}" value="${el.value}"${disabledMark(el)}]`
    if (tag === "SELECT") {
      const opts = [...el.options].map((o) => (o.selected ? "*" : "") + clean(o.textContent).trim()).join(" | ")
      return `[${ref(el)}select "${labelOf(el)}" options: ${opts}${disabledMark(el)}]`
    }
    if (tag === "SUMMARY") {
      const open = el.parentElement && el.parentElement.open
      return `[${ref(el)}summary${open ? "" : " (collapsed, content below)"}] `
    }
    return null
  }

  const walk = (node) => {
    if (node.nodeType === 3) {
      out.push(clean(node.textContent))
      return
    }
    if (node.nodeType !== 1) return
    const el = node
    const tag = el.tagName
    if (SKIP.has(tag)) return
    const role = el.getAttribute("role")
    if (role === "tooltip") {
      out.push(` (tooltip: ${clean(textOf(el)).trim()}) `)
      return
    }
    if (hidden(el)) return
    if (tag === "IFRAME") {
      let doc = null
      try { doc = el.contentDocument } catch (e) {}
      out.push(`\n[iframe src=${el.getAttribute("src") || ""}]\n`)
      if (doc && doc.body) {
        doc.querySelectorAll("[data-aref]").forEach((e) => e.removeAttribute("data-aref"))
        walk(doc.body)
      }
      out.push("\n[/iframe]\n")
      return
    }
    if (tag === "CANVAS" || tag === "IMG" || tag === "SVG" || role === "img") {
      const l = el.getAttribute("aria-label") || el.getAttribute("alt") || el.getAttribute("title") || clean(textOf(el))
      if (clean(l).trim()) out.push(` ${clean(l).trim()} `)
      else if (tag === "CANVAS") out.push(" [canvas without text: its value is drawn, look for it elsewhere on the page] ")
      return
    }
    if (offscreen(el)) {
      marked++
      out.push(" (off-screen text: ")
      for (const ch of el.childNodes) walk(ch)
      out.push(") ")
      return
    }
    if (tag === "DIALOG") {
      if (!el.open) return
      out.push("\n=== DIALOG OPEN ===\n")
    }
    const c = control(el)
    if (c !== null) {
      out.push(` ${c} `)
      if (tag === "SUMMARY" || tag === "A" || tag === "BUTTON" || tag === "SELECT" || tag === "TEXTAREA" || tag === "INPUT") return
    }
    const block = BLOCK.has(tag)
    if (block) out.push("\n")
    if (/^H[1-6]$/.test(tag)) out.push("#".repeat(+tag[1]) + " ")
    if (tag === "TD" || tag === "TH") out.push(" | ")
    const before = generated(el, "::before")
    if (before) out.push(` ${before} `)
    const start = out.length
    if (el.shadowRoot) for (const ch of el.shadowRoot.childNodes) walk(ch)
    for (const ch of el.childNodes) walk(ch)
    const after = generated(el, "::after")
    if (after) out.push(` ${after} `)
    const title = clean(el.getAttribute("title")).trim()
    if (title && c === null && !clean(out.slice(start).join("")).includes(title)) out.push(` (tooltip: ${title}) `)
    if (tag === "DIALOG") out.push("\n=== END DIALOG ===\n")
    if (block) out.push("\n")
  }

  const doc = opts.root || (opts.doc ? new DOMParser().parseFromString(opts.doc, "text/html") : document)
  if (!fetched) document.querySelectorAll("[data-aref]").forEach((e) => e.removeAttribute("data-aref"))
  walk(doc.body || doc.documentElement)
  const text = out.join("").replace(/[ ]*\n[ \n]*/g, "\n").replace(/ {2,}/g, " ").trim()
  return { text, next, marked }
}
