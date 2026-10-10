// Page text the way assistive technology sees it: hidden decoys out, labels/tooltips/collapsed details in,
// same-origin iframes inlined, every control tagged with a ref the tools can act on.
// Called as (opts) => string. opts.doc set: a fetched document (no layout, so only inline styles count).
(opts) => {
  const ZW = /[​-‍⁠﻿­]/g
  const clean = (s) => (s || "").replace(ZW, "").replace(/[ \t\r\f\v ]+/g, " ")
  const BLOCK = new Set(["P", "DIV", "SECTION", "ARTICLE", "MAIN", "HEADER", "FOOTER", "NAV", "ASIDE", "UL", "OL", "LI",
    "TR", "TABLE", "FORM", "FIELDSET", "DL", "DT", "DD", "H1", "H2", "H3", "H4", "H5", "H6", "BR", "HR", "PRE",
    "BLOCKQUOTE", "DETAILS", "SUMMARY", "DIALOG", "FIGURE", "CAPTION", "LEGEND", "OUTPUT", "LABEL"])
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "META", "LINK"])
  const fetched = !!opts.doc
  let next = opts.start || 1
  const out = []

  const hidden = (el) => {
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return true
    if (fetched) return /display\s*:\s*none|visibility\s*:\s*hidden/i.test(el.getAttribute("style") || "")
    const st = el.ownerDocument.defaultView.getComputedStyle(el)
    return st.display === "none" || st.visibility === "hidden" || st.opacity === "0" || parseFloat(st.fontSize) === 0
  }
  const labelOf = (el) => {
    const doc = el.ownerDocument
    const by = el.getAttribute("aria-labelledby")
    if (by) {
      const t = by.split(/\s+/).map((id) => doc.getElementById(id)).filter(Boolean).map((e) => e.textContent).join(" ")
      if (clean(t).trim()) return clean(t).trim()
    }
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label")).trim()
    if (el.id) {
      const l = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`)
      if (l && clean(l.textContent).trim()) return clean(l.textContent).trim()
    }
    const wrap = el.closest("label")
    if (wrap && clean(wrap.textContent).trim()) return clean(wrap.textContent).trim()
    return clean(el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("name") || "").trim()
  }
  const described = (el) => {
    const ids = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean)
    const t = ids.map((id) => el.ownerDocument.getElementById(id)).filter(Boolean).map((e) => clean(e.textContent).trim())
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
      const name = clean(el.textContent).trim() || labelOf(el)
      return `[${ref(el)}link "${name}" -> ${el.getAttribute("href")}]`
    }
    if (tag === "BUTTON" || role === "button" || role === "menuitem" || role === "tab" || role === "option" ||
        (tag === "INPUT" && ["submit", "button", "reset"].includes(el.type))) {
      const name = clean(el.textContent).trim() || labelOf(el) || el.value || ""
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
      out.push(` (tooltip: ${clean(el.textContent).trim()}) `)
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
      const l = el.getAttribute("aria-label") || el.getAttribute("alt") || el.getAttribute("title") || clean(el.textContent)
      if (clean(l).trim()) out.push(` ${clean(l).trim()} `)
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
    if (el.shadowRoot) for (const ch of el.shadowRoot.childNodes) walk(ch)
    for (const ch of el.childNodes) walk(ch)
    if (tag === "DIALOG") out.push("\n=== END DIALOG ===\n")
    if (block) out.push("\n")
  }

  const doc = opts.doc ? new DOMParser().parseFromString(opts.doc, "text/html") : document
  if (!fetched) document.querySelectorAll("[data-aref]").forEach((e) => e.removeAttribute("data-aref"))
  walk(doc.body || doc.documentElement)
  const text = out.join("").replace(/[ ]*\n[ \n]*/g, "\n").replace(/ {2,}/g, " ").trim()
  return { text, next }
}
