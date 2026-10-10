"""Generic browser tools for the model: read a page as text with control refs, act on a ref, read a URL without
navigating, open downloaded files. Nothing here knows any website; the model decides where to go and what to do."""
import asyncio
import difflib
import io
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

READER = (Path(__file__).parent / "reader.js").read_text()
MAX_CHARS = 14000
OPEN_DETAILS = "e => { for (let d = e.closest('details'); d; d = d.parentElement?.closest('details')) d.open = true }"
SETTLE_MAX = 1.5  # seconds a read waits at most for the page to settle (popups appear up to that long after load)
# Every page of the tab tracks its pending short timers and its last DOM change, so a read waits exactly as long as
# something is still due (a delayed popup) instead of a fixed time.
TRACK = """(() => { if (window.__arefTimers) return; const pending = new Set(), st = window.setTimeout, ct = window.clearTimeout;
  window.__arefTimers = pending; window.__arefSetTimeout = st; window.__arefChanged = Date.now();
  window.setTimeout = function (fn, ms, ...rest) {
    if (typeof fn !== 'function') return st.call(this, fn, ms, ...rest);
    const id = st.call(this, function (...a) { pending.delete(id); return fn.apply(this, a) }, ms, ...rest);
    if ((Number(ms) || 0) <= 1500) pending.add(id);
    return id };
  window.clearTimeout = function (id) { pending.delete(id); return ct.call(this, id) };
  new MutationObserver(() => { window.__arefChanged = Date.now() }).observe(document,
    {subtree: true, childList: true, attributes: true, characterData: true}) })()"""
QUIET = """(max) => new Promise((resolve) => {
  if (!window.__arefTimers) return resolve(-1);
  const start = Date.now(), wait = window.__arefSetTimeout;
  const tick = () => {
    const quiet = Date.now() - window.__arefChanged >= 300 && window.__arefTimers.size === 0;
    if (quiet || Date.now() - start >= max) return resolve(Date.now() - start);
    wait(tick, 50) };
  tick() })"""
# A login form: one password field and exactly one other text field in the same form, nothing else to type into.
# Returns its signature (action path and field names): only the very form the tab got past is filled in again.
LOGIN_FORM = """() => {
  const visible = (e) => e.offsetParent !== null && getComputedStyle(e).visibility !== 'hidden'
  const typed = (e) => ['text', 'email', 'password', 'tel', 'number', ''].includes(e.type)
  const pw = [...document.querySelectorAll('input[type=password]')].filter(visible)
  if (pw.length !== 1 || !pw[0].form) return null
  const fields = [...pw[0].form.querySelectorAll('input, textarea, select')].filter(visible)
    .filter((e) => e.tagName === 'INPUT' ? typed(e) : true)
  const user = fields.filter((e) => e !== pw[0])
  if (fields.length !== 2 || user.length !== 1 || user[0].tagName !== 'INPUT') return null
  const action = new URL(pw[0].form.getAttribute('action') || location.href, location.href).pathname
  return [action, user[0].name || user[0].id, pw[0].name || pw[0].id].join('|') }"""
LOGIN_SUBMIT = """([username, password]) => {
  const pw = [...document.querySelectorAll('input[type=password]')].find((e) => e.offsetParent !== null)
  const user = [...pw.form.querySelectorAll('input')].find((e) => e !== pw && e.offsetParent !== null &&
    ['text', 'email', 'tel', 'number', ''].includes(e.type))
  const set = (e, v) => { e.focus(); e.value = v; e.dispatchEvent(new Event('input', {bubbles: true}));
    e.dispatchEvent(new Event('change', {bubbles: true})) }
  set(user, username); set(pw, password)
  pw.form.requestSubmit ? pw.form.requestSubmit() : pw.form.submit() }"""
FRAMED = """async ([html, url]) => {
  const frame = document.createElement('iframe')
  frame.setAttribute('sandbox', 'allow-same-origin')  // no scripts: the fetched page only lays itself out
  frame.style.cssText = 'position:fixed;left:-30000px;top:0;width:1280px;height:900px;border:0'
  const base = `<base href="${url.replace(/"/g, '&quot;')}">`
  frame.srcdoc = /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (m) => m + base) : base + html
  const loaded = new Promise((resolve) => { frame.onload = resolve; setTimeout(resolve, 3000) })
  document.documentElement.appendChild(frame)
  await loaded
  try { return (READER)({root: frame.contentDocument}) } finally { frame.remove() }
}"""
RELOGINS = 3  # automatic logins per tab at most, so a rejected login never loops
# Inside llm.TOOL_TIMEOUT (60 s per tool): a fetch gives up on its own first, so the model gets a clear answer.
FETCH_ABORT = 40  # seconds without an answer before one in-page request is aborted
FETCH_BUDGET = 45  # seconds after which a 5xx is no longer retried
RELOAD_TIMEOUT = 15  # seconds per reload of an error page (two at most)
# Page chrome: a line without a control that earlier reads of this tab showed at least this often. At the top and the
# bottom of the page shown after an action it is left out (the model saw it before; it is 9-28 % of a page's text on
# the recorded sites). Controls always stay, so every ref remains usable; evidence and explicit reads stay complete.
CHROME_SEEN = 2
CONTROL = re.compile(r"\[\d+:")


class Tab:
    def __init__(self, page, site: dict):
        self.page = page
        self.site = site
        self.dialogs: list[str] = []
        self.downloads: list[str] = []
        self.events: list[str] = []  # what code did on the model's behalf (retries, logins), told with the next read
        self.login_form = ""  # signature of the form the model typed this site's password into; seeing it again
        self.past_login = False  # after the tab got past it means the session expired (a TAN form never matches it)
        self.relogins = 0
        self.lines: Counter = Counter()  # lines without controls -> how many reads of this tab showed them
        self.method = "GET"  # of the latest main-frame navigation: only a GET may be reloaded after a server error
        self.status = 0
        page.on("dialog", self._on_dialog)
        page.on("download", self._on_download)
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        self._tracking = asyncio.ensure_future(self._track(page))

    async def _track(self, page):
        try:
            await page.add_init_script(TRACK)
        except Exception:  # noqa: BLE001
            pass

    def _on_request(self, request):
        try:
            if request.is_navigation_request() and request.frame == self.page.main_frame:
                self.method = request.method
        except Exception:  # noqa: BLE001  a request without a frame (service worker)
            pass

    def _on_response(self, response):
        try:
            if response.request.is_navigation_request() and response.frame == self.page.main_frame:
                self.status = response.status
        except Exception:  # noqa: BLE001
            pass

    async def _on_dialog(self, dialog):
        self.dialogs.append(f"{dialog.type}: {dialog.message}")
        await dialog.accept()

    async def _on_download(self, download):
        try:
            path = await download.path()
            self.downloads.append(describe_file(download.suggested_filename, Path(path).read_bytes()))
        except Exception as error:  # noqa: BLE001
            self.downloads.append(f"download {download.suggested_filename} failed: {error}")

    async def settle(self):
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        try:  # until no short timer is pending and the DOM was quiet for 300 ms, at most SETTLE_MAX
            waited = await self.page.evaluate(QUIET, int(SETTLE_MAX * 1000))
        except Exception:  # noqa: BLE001  navigated while waiting
            waited = 500
            await asyncio.sleep(0.5)
        if waited < 0:  # a page loaded before this tab tracked it: popups appear a moment after load
            await asyncio.sleep(SETTLE_MAX)
        for frame in self.page.frames:  # in-page popup dialogs only block the page; browser dialogs are accepted above
            try:
                await frame.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
            except Exception:  # noqa: BLE001
                pass

    async def recover(self):
        """Before the model sees a page: reload a server error page (GET only) up to twice, and log in again when the
        session expired (a login form on a tab that was already past its login). Both are told to the model."""
        for attempt in range(2):
            if self.status < 500 or self.method != "GET":
                break
            await asyncio.sleep(2 + 2 * attempt)
            try:
                await self.page.reload(wait_until="domcontentloaded", timeout=RELOAD_TIMEOUT * 1000)
            except Exception:  # noqa: BLE001
                pass
            await self.settle()
            self.events.append(f"The page answered HTTP 5xx; code reloaded it ({attempt + 1}x), now HTTP {self.status}.")
        try:
            form = await self.page.evaluate(LOGIN_FORM)
        except Exception:  # noqa: BLE001
            form = None
        if not form:
            self.past_login = self.past_login or bool(self.login_form)
            return
        credentials = self.site.get("credentials") or {}
        if form == self.login_form and self.past_login and self.relogins < RELOGINS and credentials.get("password"):
            self.relogins += 1
            await self.page.evaluate(LOGIN_SUBMIT, [credentials.get("username", ""), credentials["password"]])
            await self.settle()
            self.events.append("The session had expired: code logged in again with this site's credentials.")

    def compact(self, window: str, whole: bool) -> str:
        """`window` without the page chrome at its top and, when it is the whole page, at its bottom."""
        lines = window.split("\n")

        def chrome(line: str) -> bool:
            return not CONTROL.search(line) and not line.startswith("===") and self.lines[line.strip()] >= CHROME_SEEN

        def edge(order) -> list[int]:
            """Chrome lines from one end up to the page's own first content line; control lines are passed over."""
            found = []
            for i in order:
                if chrome(lines[i]):
                    found.append(i)
                elif not CONTROL.search(lines[i]):
                    break
            return found

        top = edge(range(len(lines)))
        bottom = [i for i in edge(range(len(lines) - 1, -1, -1)) if i not in top] if whole else []
        if len(top) + len(bottom) < 2:
            return window
        note = "[{} lines repeated from earlier pages of this site left out; read shows the full page]"
        notes = {min(top): note.format(len(top))} if top else {}
        if bottom:
            notes[min(bottom)] = note.format(len(bottom))
        dropped = set(top) | set(bottom)
        return "\n".join(notes[i] if i in notes else line for i, line in enumerate(lines) if i in notes or i not in dropped)

    async def read(self, offset: int = 0, compact: bool = False) -> str:
        """The page as text from `offset`. compact (the page shown after an action): repeated page chrome left out."""
        await self.settle()
        await self.recover()
        result = await self.page.evaluate(f"({READER})({{}})")
        text = result["text"]
        events = ""
        if self.events:
            events += "Done by code: " + " ".join(self.events) + "\n"
            self.events.clear()
        if self.dialogs:
            events += "Browser dialogs (accepted): " + " || ".join(self.dialogs) + "\n"
            self.dialogs.clear()
        if self.downloads:
            events += "Downloaded files:\n" + "\n\n".join(self.downloads) + "\n"
            self.downloads.clear()
        head = f"URL: {self.page.url}\nTitle: {await self.page.title()}\n{events}\n"
        body = text[offset:offset + MAX_CHARS]
        if compact and offset == 0:  # offsets stay those of the full text, so `read` with an offset continues it
            body = self.compact(body, whole=len(text) <= MAX_CHARS)
        self.lines.update({line.strip() for line in text.split("\n") if line.strip() and not CONTROL.search(line)})
        if len(text) > offset + MAX_CHARS:
            body += f"\n[... {len(text) - offset - MAX_CHARS} more chars: call read with offset={offset + MAX_CHARS}]"
        return head + body

    async def credential(self, loc, value: str) -> str:
        """The site's own username or password when the model typed it one or two characters off (models misread
        random credentials); any other value, a TAN included, never resembles them and is typed as given."""
        credentials = self.site.get("credentials") or {}
        try:
            kind = await loc.evaluate("e => e.type")
        except Exception:  # noqa: BLE001
            return value
        want = credentials.get("password" if kind == "password" else "username")
        if want and value != want and difflib.SequenceMatcher(None, value, want).ratio() >= 0.8:
            self.events.append(f"The typed {'password' if kind == 'password' else 'username'} differed from this "
                               "site's credentials by a character or two; code entered it exactly.")
            value = want
        if kind == "password" and value == want:  # only the form the model logged in with is ever filled in again
            try:
                self.login_form = await self.page.evaluate(LOGIN_FORM) or ""
            except Exception:  # noqa: BLE001
                pass
        return value

    async def click(self, loc):
        """Click a control: a checkbox or radio is ticked directly (custom-styled ones never pass Playwright's
        actionability wait); anything else gets a short real click, then a DOM click if it is covered or inert."""
        try:
            kind = await loc.evaluate("e => e.tagName === 'INPUT' ? e.type : ''")
        except Exception:  # noqa: BLE001
            kind = ""
        if kind in ("checkbox", "radio"):
            await loc.set_checked(True, timeout=3000, force=True)
            return
        try:
            await loc.scroll_into_view_if_needed(timeout=1000)
            await loc.click(timeout=2000)
        except Exception:  # noqa: BLE001  covered, off-screen in a scroll box, inert: click it in the DOM
            await loc.evaluate("e => e.click()")

    async def locate(self, ref: int):
        for frame in self.page.frames:
            loc = frame.locator(f'[data-aref="{ref}"]')
            if await loc.count():
                return loc.first
        raise ValueError(f"ref {ref} not on the page any more: read the page again")

    async def act(self, action: str, args: dict) -> str:
        page = self.page
        if action == "goto":
            await page.goto(urljoin(page.url if page.url.startswith("http") else self.site["url"], args["url"]),
                            wait_until="domcontentloaded", timeout=30000)
        elif action == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=30000)
        elif action == "press":
            await page.keyboard.press(args["key"])
        elif action == "fetch":
            return await self.fetch(args["url"])
        elif action == "form":
            return await self.form(args.get("steps") or [])
        else:
            loc = await self.locate(int(args["ref"]))
            if action == "click":
                await self.click(loc)
            elif action == "fill":
                await loc.evaluate(OPEN_DETAILS)
                kind = await loc.evaluate("e => e.type")
                if kind == "range":
                    await loc.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true}));"
                                       " e.dispatchEvent(new Event('change', {bubbles: true})) }", str(args["text"]))
                else:
                    await loc.fill(await self.credential(loc, str(args["text"])), timeout=5000)
            elif action == "select":
                await loc.select_option(label=str(args["option"]), timeout=5000)
            elif action == "check":
                await loc.set_checked(bool(args.get("checked", True)), timeout=5000, force=True)
            else:
                return f"unknown action {action}"
        return await self.read(compact=True)

    async def form(self, steps: list[dict]) -> str:
        """Fill fields and press buttons by their visible label, in order, waiting for the page after each step."""
        page = self.page
        log = []
        for step in steps:
            try:
                if step.get("field") and step.get("click"):  # both in one step: fill, then click
                    steps_left = [{"field": step["field"], "value": step.get("value")}, {"click": step["click"]}]
                    log.append((await self.form(steps_left)).split("\n", 1)[0].removeprefix("Form steps: "))
                    continue
                if step.get("ref") is not None and step.get("value") is None:
                    loc = await self.locate(int(step["ref"]))
                    await loc.evaluate(OPEN_DETAILS)
                    await self.click(loc)
                    await self.settle()
                    log.append(f"clicked ref {step['ref']}")
                    continue
                if step.get("click"):
                    loc = page.get_by_role("button", name=str(step["click"]))
                    if not await loc.count():
                        loc = page.get_by_role("link", name=str(step["click"]))
                    await loc.first.scroll_into_view_if_needed(timeout=3000)
                    await loc.first.click(timeout=5000)
                    await self.settle()
                    log.append(f"clicked {step['click']}")
                    continue
                value = step.get("value")
                if value is None:
                    raise ValueError("no value given for this field")
                if step.get("ref") is not None:
                    label, loc = f"ref {step['ref']}", await self.locate(int(step["ref"]))
                else:
                    label = str(step["field"])
                    loc = page.get_by_label(label, exact=True)
                    if not await loc.count():
                        loc = page.get_by_label(label)
                    loc = loc.first
                await loc.evaluate(OPEN_DETAILS)  # a field in a collapsed section can't be filled
                tag = await loc.evaluate("e => e.tagName + ':' + (e.type || '')")
                if tag.startswith("SELECT"):
                    options = await loc.evaluate("e => [...e.options].map(o => [o.value, o.textContent.trim()])")
                    want = str(value).strip()
                    pick = next((v for v, t in options if t == want), None) or next(
                        (v for v, t in options if v == want), None) or next(
                        (v for v, t in options if t.startswith(want + " ") or t.startswith(want + " ")), None) or next(
                        (v for v, t in options if want in t), None)
                    if pick is None:
                        raise ValueError(f"no option {want!r}; options: {[t for _, t in options][:40]}")
                    await loc.select_option(value=pick, timeout=5000)
                elif tag in ("INPUT:checkbox", "INPUT:radio"):
                    await loc.set_checked(value not in (False, "false", "no", "0"), timeout=5000, force=True)
                else:
                    await loc.fill(await self.credential(loc, str(value)), timeout=5000)
                log.append(f"set {label} = {value}")
            except Exception as error:  # noqa: BLE001  stop at the first failing step, the model sees why
                log.append(f"FAILED at {step}: {str(error)[:300]}")
                break
        return "Form steps: " + "; ".join(log) + "\n\n" + await self.read(compact=True)

    async def fetch(self, url: str) -> str:
        """Read a same-origin URL through the logged-in page without navigating: text only, no refs. A server error
        is retried twice before the model sees it, within FETCH_BUDGET."""
        started = asyncio.get_running_loop().time()
        for attempt in range(3):
            result = await self._fetch(url)
            if result.get("failed"):  # no answer in time (or no connection): the model decides what next
                return (f"Fetched {result['url']} (HTTP 504) no answer within {FETCH_ABORT} s ({result['failed']}): the "
                        "site may be slow; try again or open another page\n")  # a 5xx, so never kept as evidence
            spent = asyncio.get_running_loop().time() - started
            if result["status"] < 500 or attempt == 2 or spent > FETCH_BUDGET:
                break
            await asyncio.sleep(1.5 * (attempt + 1))
        head = f"Fetched {result['url']} (HTTP {result['status']})" + (f" after {attempt} retries" if attempt else "") + "\n"
        if "html" in result:
            return head + (await self.html_text(result["html"], result["url"]))[:MAX_CHARS]
        import base64
        return head + describe_file(url.rsplit("/", 1)[-1], base64.b64decode(result["b64"]))

    async def html_text(self, html: str, url: str) -> str:
        """A fetched page as text, laid out in a hidden script-free frame so its own style rules decide what is
        hidden; without a usable frame (no page document, a blocking policy), parsed without layout instead."""
        try:
            text = (await self.page.evaluate(FRAMED.replace("READER", READER), [html, url]))["text"]
            if text or not html.strip():
                return text
        except Exception:  # noqa: BLE001
            pass
        return (await self.page.evaluate(f"({READER})({{doc: {_js(html)}}})"))["text"]

    async def _fetch(self, url: str) -> dict:
        return await self.page.evaluate(
            """async ([url, abortMs]) => {
                const stop = new AbortController(); const timer = (window.__arefSetTimeout || setTimeout)(() => stop.abort(), abortMs)
                let r
                try { r = await fetch(url, {credentials: 'include', signal: stop.signal}) }
                catch (e) { return {status: 0, url, type: '', html: '', failed: String(e && e.name || e)} }
                finally { clearTimeout(timer) }
                const type = r.headers.get('content-type') || ''
                if (!type.includes('html')) {
                    const buf = new Uint8Array(await r.arrayBuffer())
                    let bin = ''; for (const b of buf) bin += String.fromCharCode(b)
                    return {status: r.status, url: r.url, type, b64: btoa(bin)}
                }
                return {status: r.status, url: r.url, type, html: await r.text()}
            }""", [urljoin(self.page.url, url), FETCH_ABORT * 1000])


def _js(value: str) -> str:
    import json
    return json.dumps(value)


def describe_file(name: str, data: bytes) -> str:
    """Text of a downloaded document; ZIPs are opened and each member described."""
    if data[:2] == b"PK":
        parts = []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    parts.append(describe_file(info.filename, archive.read(info)))
        return f"ZIP {name}:\n" + "\n\n".join(parts)
    if data[:4] == b"%PDF":
        return f"PDF {name}:\n" + pdf_text(data)
    text = data.decode("utf-8", errors="replace")
    if "<html" in text[:500].lower() or name.endswith((".htm", ".html")):
        text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text)
        text = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[​-‍⁠﻿]", "", text)
    return f"FILE {name}:\n" + re.sub(r"[ \t]+", " ", text)[:MAX_CHARS]


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)[:MAX_CHARS]
    except Exception as error:  # noqa: BLE001
        return f"(could not read the PDF: {error})"
