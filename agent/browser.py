"""Generic browser tools for the model: read a page as text with control refs, act on a ref, read a URL without
navigating, open downloaded files. Nothing here knows any website; the model decides where to go and what to do."""
import asyncio
import codecs
import difflib
import html
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from calc import INVISIBLE

READER = (Path(__file__).parent / "reader.js").read_text()
MAX_CHARS = 14000
DISABLED = "e => e.matches(':disabled') || e.getAttribute('aria-disabled') === 'true'"
OPEN_DETAILS = "e => { for (let d = e.closest('details'); d; d = d.parentElement?.closest('details')) d.open = true }"
SETTLE_MAX = 1.5  # seconds a read waits at most for the page to settle (popups appear up to that long after load)
FRAME_WAIT = 3  # seconds a settle waits at most for the page's frames to load
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
# Seconds a navigation may go unanswered (goto's own limit) before code stops it: until it ends, the page runs no
# script for us, so every read, click and form step on the tab would wait out the tool timeout.
NAVIGATION_TIMEOUT = 30
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
        self.navigation = None  # the main-frame navigation request still waiting for its answer
        self.stalled: set = set()  # frames that did not load within FRAME_WAIT: not waited for again
        page.on("framenavigated", lambda frame: self.stalled.discard(frame))  # a reloaded frame may hold a form: wait for it again
        page.on("dialog", self._on_dialog)
        page.on("download", self._on_download)
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_failed)
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
                self.navigation = request
                asyncio.ensure_future(self._stop_unanswered(request))
        except Exception:  # noqa: BLE001  a request without a frame (service worker)
            pass

    def _on_failed(self, request):
        if request is self.navigation:
            self.navigation = None

    async def _stop_unanswered(self, request):
        await asyncio.sleep(NAVIGATION_TIMEOUT)
        if request is not self.navigation:
            return
        self.navigation = None
        if await self.stop():
            self.events.append(f"The site sent no answer to {request.method} {request.url} within {NAVIGATION_TIMEOUT}"
                               " s; code stopped waiting for it. The last action may not have taken effect: check the page.")

    async def stop(self) -> bool:
        """Stop the page's pending navigation, as the browser's stop button does; False when that failed."""
        try:
            session = await self.page.context.new_cdp_session(self.page)
            await session.send("Page.stopLoading")
            await session.detach()
            return True
        except Exception:  # noqa: BLE001  the page closed meanwhile
            return False

    def _on_response(self, response):
        try:
            if response.request.is_navigation_request() and response.frame == self.page.main_frame:
                self.status = response.status
                if response.request is self.navigation:
                    self.navigation = None
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
        async def ready(frame):  # a form inside a frame reloads only that frame, by now under way
            if frame != self.page.main_frame and frame not in self.stalled:
                await frame.wait_for_load_state("domcontentloaded")
            # in-page popup dialogs only block the page; browser dialogs are accepted above
            await frame.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")

        frames = self.page.frames
        tasks = [asyncio.ensure_future(ready(frame)) for frame in frames]
        await asyncio.wait(tasks, timeout=FRAME_WAIT)
        for frame, task in zip(frames, tasks):  # a frame that never loads (ads, chat) is waited for once
            if not task.done():
                self.stalled.add(frame)
                task.cancel()
            elif not task.cancelled():
                task.exception()

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

    async def named(self, label: str, click: bool = False):
        """The field (or with click, the button or link) the model names, in the page or one of its frames. A field
        goes by any name the reader shows for it: its label, then its placeholder, title or name attribute."""
        label = re.sub(r"\s*\(datetime: [^)]*\)", "", label).strip() or label  # the reader's note, not the page's name
        quoted = json.dumps(label, ensure_ascii=False)
        attribute = ", ".join(f"{t}[{a}={quoted}]" for a in ("title", "name")
                              for t in ("input:not([type=hidden])", "select", "textarea"))
        for attempt in range(2):  # a frame the last step reloaded may still be loading: wait for the page once
            for exact in (True, False, None):  # None: by title or name attribute, after every label
                for frame in self.page.frames:
                    if click:
                        found = [frame.get_by_role("button", name=label, exact=exact),
                                 frame.get_by_role("link", name=label, exact=exact)] if exact is not None else []
                    elif exact is None:
                        found = [frame.locator(attribute)]
                    else:
                        found = [frame.get_by_label(label, exact=exact), frame.get_by_placeholder(label, exact=exact)]
                    for loc in found:
                        try:
                            if await loc.count():
                                return loc.first
                        except Exception:  # noqa: BLE001  a frame detached while it was searched
                            pass
            if not attempt:
                await self.settle()
        kind = "button or link" if click else "field (by label, placeholder, title or name)"
        raise ValueError(f"no {kind} {label!r} on this page: use the label the page shows, or its ref")

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
        log = []
        for step in steps:
            try:
                try:
                    log.append(await self.step(step))
                except Exception as error:  # noqa: BLE001
                    # the last click reloaded a frame a moment after the wait: a field by label is found again
                    if "context was destroyed" not in str(error) or step.get("ref") is not None or step.get("click"):
                        raise
                    await self.settle()
                    log.append(await self.step(step))
            except Exception as error:  # noqa: BLE001  stop at the first failing step, the model sees why
                log.append(f"FAILED at {step}: {str(error)[:300]}")
                break
        return "Form steps: " + "; ".join(log) + "\n\n" + await self.read(compact=True)

    async def step(self, step: dict) -> str:
        """One form step; returns what it did."""
        if step.get("field") and step.get("click"):  # both in one step: fill, then click
            steps_left = [{"field": step["field"], "value": step.get("value")}, {"click": step["click"]}]
            return (await self.form(steps_left)).split("\n", 1)[0].removeprefix("Form steps: ")
        if step.get("ref") is not None and step.get("value") is None:
            loc = await self.locate(int(step["ref"]))
            await loc.evaluate(OPEN_DETAILS)
            await self.click(loc)
            await self.settle()
            return f"clicked ref {step['ref']}"
        if step.get("click"):
            loc = await self.named(str(step["click"]), click=True)
            await loc.scroll_into_view_if_needed(timeout=3000)
            await loc.click(timeout=5000)
            await self.settle()
            return f"clicked {step['click']}"
        value = step.get("value")
        if value is None:
            raise ValueError("no value given for this field")
        if step.get("ref") is not None:
            label, loc = f"ref {step['ref']}", await self.locate(int(step["ref"]))
        else:
            label = str(step["field"])
            loc = await self.named(label)
        await loc.evaluate(OPEN_DETAILS)  # a field in a collapsed section can't be filled
        if await loc.evaluate(DISABLED):  # a dependent choice a script may open a moment after the last step
            await self.settle()
            if await loc.evaluate(DISABLED):
                raise ValueError(f"{label} is disabled: if it depends on an earlier choice, apply that choice first (its "
                                 "apply or next button), then send this step again")
        tag = await loc.evaluate("e => e.tagName + ':' + (e.type || '')")
        if tag.startswith("SELECT"):
            want = INVISIBLE.sub("", str(value)).strip()
            for attempt in range(2):  # options a script loads after the last step: wait for the page once
                options = [(v, INVISIBLE.sub("", t).strip())  # option texts as the reader shows them
                           for v, t in await loc.evaluate("e => [...e.options].map(o => [o.value, o.textContent])")]
                pick = next((v for v, t in options if t == want), None) or next(
                    (v for v, t in options if v == want), None) or next(
                    (v for v, t in options if t.startswith(want + " ") or t.startswith(want + " ")), None) or next(
                    (v for v, t in options if want in t), None)
                if pick is not None or attempt:
                    break
                await self.settle()
            if pick is None:
                raise ValueError(f"no option {want!r}; options: {[t for _, t in options][:40]}")
            await loc.select_option(value=pick, timeout=5000)
        elif tag in ("INPUT:checkbox", "INPUT:radio"):
            await loc.set_checked(value not in (False, "false", "no", "0"), timeout=5000, force=True)
        else:
            await loc.fill(await self.credential(loc, str(value)), timeout=5000)
        return f"set {label} = {value}"

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
    """Text of a downloaded document; ZIPs are opened and each member described, office files read as their text."""
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            try:
                office = office_text(archive)
            except Exception:  # noqa: BLE001  a broken or unknown office part: list the members instead
                office = None
            if office is not None:
                return f"DOCUMENT {name}:\n" + INVISIBLE.sub("", office)[:MAX_CHARS]
            parts = [describe_file(info.filename, archive.read(info)) for info in archive.infolist() if not info.is_dir()]
        return f"ZIP {name}:\n" + "\n\n".join(parts)
    if data[:4] == b"%PDF":
        return f"PDF {name}:\n" + INVISIBLE.sub("", pdf_text(data))
    text = decode(data)
    if "<html" in text[:500].lower() or name.endswith((".htm", ".html")):
        text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text)
        text = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
    return f"FILE {name}:\n" + re.sub(r"[ \t]+", " ", INVISIBLE.sub("", text))[:MAX_CHARS]


def decode(data: bytes) -> str:
    """Plain text in whatever encoding an export uses: a byte-order mark, UTF-16 without one, UTF-8, else Windows-1252."""
    if data[:3] == codecs.BOM_UTF8:
        return data[3:].decode("utf-8", errors="replace")
    if data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        return data.decode("utf-16", errors="replace")
    head = data[:2000]
    if len(head) > 1 and head.count(0) > len(head) // 4:
        return data.decode("utf-16-le" if head[1::2].count(0) > head[::2].count(0) else "utf-16-be", errors="replace")
    text = data.decode("utf-8", errors="ignore")
    bad = len(data) - len(text.encode())  # bytes that are no UTF-8
    if bad > sum(ch > "\x7f" for ch in text):
        return data.decode("cp1252", errors="replace")
    return data.decode("utf-8", errors="replace")


# Office text that is not shown: hidden runs (the bounded, tempered gap keeps a hidden paragraph mark from eating the
# next run), deleted or moved-away tracked changes, hidden or collapsed text, rows and slides.
OFFICE_HIDDEN = re.compile(
    r'<(\w+:)?vanish\b(?![^>]*val="(0|false|off)")[^>]*>((?!<(\w+:)?r[ >]|</(\w+:)?pPr>)[\s\S]){0,5000}?</(\w+:)?r>'
    r"|<(\w+:)?(delText|moveFrom|hidden-text|hidden-paragraph)\b[^>]*?(/>|>[\s\S]*?</(\w+:)?\8>)"
    r'|<(\w+:)?table-row\b[^>]*visibility="(collapse|filter)"[^>]*?(/>|>[\s\S]*?</(\w+:)?table-row>)')


def office_text(archive: zipfile.ZipFile) -> str | None:
    """Spreadsheets row by row with their cells tab-separated; text documents and slides paragraph by paragraph.
    None for an archive that is no office file."""
    names = set(archive.namelist())
    if "xl/workbook.xml" in names:
        return xlsx_text(archive, names)
    parts = sorted((n for n in names if re.fullmatch(r"word/document\.xml|content\.xml|ppt/slides/slide\d+\.xml", n)),
                   key=lambda n: [int(d) if d.isdigit() else d for d in re.split(r"(\d+)", n)])
    if not parts or not ({"[Content_Types].xml", "mimetype"} & names):
        return None
    out = []
    for part in parts:
        xml = archive.read(part).decode("utf-8", errors="replace")
        if re.search(r'<(\w+:)?sld\b[^>]*\bshow="(0|false)"', xml):
            continue
        xml = OFFICE_HIDDEN.sub("", xml)
        xml = re.sub(r'<(\w+:)?(covered-)?table-cell\b([^>]*number-columns-repeated="(\d+)")?[^>]*/>',
                     lambda m: "\t" * min(int(m.group(4) or 1), 50), xml)
        xml = re.sub(r"</(\w+:)?(p|h|tr|table-row)>|<(\w+:)?(br|line-break)\b[^>]*/>", "\n", xml)
        xml = re.sub(r"</(\w+:)?(tc|table-cell)>|<(\w+:)?tab\b[^>]*/>", "\t", xml)
        text = html.unescape(re.sub(r"<[^>]+>", "", xml))
        out.append(re.sub(r"\t+\n", "\n", re.sub(r"\n\t", "\t", text)))  # a cell's own paragraph end; empty cells at row end
    return "\n".join(out)


def xlsx_text(archive: zipfile.ZipFile, names: set[str]) -> str | None:
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ns = {"m": m[1:-1], "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    shared = []
    if "xl/sharedStrings.xml" in names:
        shared = ["".join(t.text or "" for t in si.findall("m:t", ns) + si.findall("m:r/m:t", ns))
                  for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", ns)]
    targets = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels")).findall("p:Relationship", ns):
            target = rel.get("Target", "").lstrip("/")
            targets[rel.get("Id")] = target if target.startswith("xl/") else "xl/" + target
    dated = set()  # style indexes whose number format shows a date
    if "xl/styles.xml" in names:
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        codes = {f.get("numFmtId"): f.get("formatCode", "") for f in styles.iter(f"{m}numFmt")}
        xfs = styles.find("m:cellXfs", ns)
        for i, xf in enumerate(xfs.findall("m:xf", ns) if xfs is not None else []):
            fmt = xf.get("numFmtId", "0")
            code = re.sub(r'"[^"]*"|\[[^]]*]|\\.', "", codes.get(fmt, ""))
            if 14 <= int(fmt) <= 17 or fmt == "22" or re.search(r"[dy]", code, re.I):
                dated.add(str(i))
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    pr = workbook.find("m:workbookPr", ns)
    epoch = datetime(1904, 1, 1) if pr is not None and pr.get("date1904") in ("1", "true") else datetime(1899, 12, 30)
    sheets = list(workbook.iter(f"{m}sheet"))
    if not sheets:  # another schema (strict): the member listing at least carries the data
        return None
    out = []
    for sheet in sheets:
        part = targets.get(sheet.get(rid))
        if sheet.get("state") in ("hidden", "veryHidden") or part not in names:
            continue
        root = ET.fromstring(archive.read(part))
        hidden = {k for col in root.iter(f"{m}col") if col.get("hidden") in ("1", "true")
                  for k in range(int(col.get("min")) - 1, int(col.get("max")))}
        rows = [f"Sheet {sheet.get('name')} (numbers as stored, with a decimal point):"]
        for row in root.iter(f"{m}row"):
            if row.get("hidden") in ("1", "true"):
                continue
            cells: dict[int, str] = {}
            for i, c in enumerate(row.findall("m:c", ns)):
                letters = re.match(r"[A-Z]*", c.get("r", "")).group()
                col = sum((ord(ch) - 64) * 26 ** k for k, ch in enumerate(reversed(letters))) - 1 if letters else i
                v = c.find("m:v", ns)
                value = v.text if v is not None and v.text else ""
                if col in hidden:
                    continue
                if c.get("t") == "s" and value:
                    cells[col] = shared[int(value)]
                elif c.get("t") == "inlineStr":
                    cells[col] = "".join(t.text or "" for t in c.iter(f"{m}t"))
                elif value and c.get("s") in dated and c.get("t") in (None, "n") and 0 <= float(value) < 2958466:
                    day = epoch + timedelta(minutes=round(float(value) * 1440))
                    cells[col] = day.strftime("%Y-%m-%d %H:%M" if day.hour or day.minute else "%Y-%m-%d")
                elif value:
                    cells[col] = value
            if cells:
                rows.append("\t".join(cells.get(k, "") for k in range(max(cells) + 1)))
        out.append("\n".join(rows))
    return "\n\n".join(out)


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)[:MAX_CHARS]
    except Exception as error:  # noqa: BLE001
        return f"(could not read the PDF: {error})"
