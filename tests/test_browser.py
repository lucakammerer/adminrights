"""browser.Tab against a local test server (I13): transient errors, an expired session, late content, form steps.
No website and no model: a tiny HTTP server runs inside the test, Chromium headless.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

import browser  # noqa: E402
from browser import Tab  # noqa: E402

LOGIN = ('<form method="post" action="/login"><label>User <input name="user"></label>'
         '<label>Secret <input type="password" name="pw"></label><button>Sign in</button></form>')
TAN = ('<form method="post" action="/sign"><label>Request <input name="request" value="7"></label>'
       '<label>Code <input type="password" name="code"></label><button>Sign</button></form>')
COUNTS: dict[str, int] = {}


class Site(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def page(self, body: str, status: int = 200, headers: dict | None = None):
        data = f"<!doctype html><html><body>{body}</body></html>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        COUNTS[path] = COUNTS.get(path, 0) + 1
        logged = "session=ok" in (self.headers.get("Cookie") or "")
        if path == "/flaky":
            return self.page("service down", 503) if COUNTS[path] <= 2 else self.page("content ok")
        if path == "/flaky-fetch":
            return self.page("down", 502) if COUNTS[path] <= 1 else self.page("fetched ok")
        if path == "/home":
            return self.page("<h1>Records</h1>secret data" if logged else LOGIN)
        if path == "/expire":
            return self.page("", 302, {"Location": "/home", "Set-Cookie": "session=; Max-Age=0; Path=/"})
        if path == "/tan":
            return self.page(TAN)
        if path == "/late":
            return self.page('<div id="x">first</div><script>setTimeout(() => {'
                             'document.getElementById("x").textContent = "late value"}, 900)</script>')
        if path.startswith("/page"):  # pages of one site: the same banner and footer around their own content
            return self.page('<p>Portal banner for every visitor</p><p>Service hotline weekdays</p>'
                             '<a href="/page1">Overview</a>'
                             f'<h1>Record {path[-1]}</h1><p>Amount {path[-1]}00 pieces</p>'
                             '<p>Imprint and privacy</p><p>All rights reserved</p>')
        if path == "/slowform":
            return self.page('<form method="post" action="/slow"><button>Send</button></form>')
        if path == "/form":
            return self.page('<div style="position:relative"><button id="b" onclick="document.title=\'clicked\'">Go'
                             '</button><div style="position:absolute;inset:0;background:#fff"></div></div>'
                             '<label>Note <input id="n" value="kept"></label>'
                             '<label class="fancy"><input type="checkbox" id="c" style="opacity:0;position:absolute">'
                             '<span style="position:relative;z-index:2;background:#eee">Accept</span></label>')
        if path == "/silent":  # a start page the site never answers
            time.sleep(20)
            return
        if path == "/stuck":
            return self.page('<form method="post" action="/never"><label>Size <input name="s"></label>'
                             '<button>Apply</button></form>')
        if path == "/config":  # a configurator whose dependent choice only opens once the first is applied
            bore = parse_qs(self.path.partition("?")[2]).get("bore", [""])[0]
            strokes = "".join(f"<option>{s}</option>" for s in ("200", "600")) if bore else ""
            return self.page('<form action="/config"><label>Bore <select name="bore"><option value="">choose</option>'
                             + "".join(f'<option{" selected" * (b == bore)}>{b}</option>' for b in ("50", "63"))
                             + f'</select></label><label>Stroke <select name="stroke"{"" if bore else " disabled"}>'
                             + f'<option value="">choose</option>{strokes}</select></label>'
                             + '<button>Apply choice</button></form>')
        if path == "/config-js":  # the same, opened by a script a moment after the first choice changes, its option
            # text with an invisible mark inside
            return self.page('<label>Bore <select id="b"><option value="">choose</option><option>50</option></select>'
                             '</label><label>Stroke <select id="s" disabled><option value="">choose</option></select>'
                             '</label><script>document.getElementById("b").onchange = () => setTimeout(() => {'
                             'const s = document.getElementById("s"); s.add(new Option("6\\u200e00")); s.disabled = false'
                             '}, 600)</script>')
        if path == "/plain":  # fields named only by placeholder or title, as some software ships them
            return self.page('<input name="q" placeholder="Quantity"><input type="hidden" name="Quantity"><select name="p" title="Ø Pressure"><option>choose'
                             '</option><option>16 bar</option></select><div role="button" onclick="document.title='
                             '\'sent\'">Send</div>')
        if path == "/marked":  # names with invisible marks inside, which the reader shows cleaned
            return self.page('<label>Deli\u200eve\u2063ry\u2060 date <input name="d"></label><input name="n" '
                             'placeholder="Re\u00adference/No"><button onclick="document.title=\'sent\'">Se\u200bnd</button>')
        if path == "/icons":  # labels and buttons named only by an icon's text alternative
            return self.page('<label for="r"><span role="img" aria-label="Receipt number"></span></label><input id="r">'
                             '<button onclick="document.title=\'sent\'"><img src="data:," alt="Send">'
                             '<i aria-label="Mail"></i></button>')
        if path == "/stall":  # a frame source that never answers (an ad or chat server)
            time.sleep(20)
            return None
        if path == "/stalled":
            return self.page('<iframe src="/stall"></iframe><p>Main content</p>')
        if path == "/framed":  # the configurator inside a frame of the page
            return self.page('<h1>Order</h1><iframe src="/config" width="600" height="200"></iframe>')
        return self.page("start")

    def do_POST(self):
        if self.path == "/never":  # a request the site never answers
            time.sleep(20)
            return
        body = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
        COUNTS["POST " + self.path] = COUNTS.get("POST " + self.path, 0) + 1
        if self.path == "/slow":  # a submit whose next page takes longer than a click waits for it
            time.sleep(3)
            return self.page("<h1>Sent</h1>")
        if self.path == "/login" and body.get("pw") == ["s3cret"] and body.get("user") == ["agent"]:
            return self.page("", 302, {"Location": "/home", "Set-Cookie": "session=ok; Path=/"})
        return self.page("rejected", 403)


class TabAgainstLocalSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        COUNTS.clear()

    def run_tab(self, steps):
        async def go():
            async with async_playwright() as p:
                b = await p.chromium.launch(headless=True)
                page = await (await b.new_context()).new_page()
                await page.goto(self.url + "/", wait_until="domcontentloaded")
                tab = Tab(page, {"url": self.url, "credentials": {"username": "agent", "password": "s3cret"}})
                await tab._tracking
                try:
                    return await steps(tab)
                finally:
                    await b.close()
        return asyncio.run(go())

    def test_server_error_is_reloaded_before_the_model_sees_it(self):
        text = self.run_tab(lambda tab: tab.act("goto", {"url": "/flaky"}))
        self.assertIn("content ok", text)
        self.assertIn("reloaded", text)

    def test_fetch_retries_a_server_error(self):
        text = self.run_tab(lambda tab: tab.fetch("/flaky-fetch"))
        self.assertIn("HTTP 200", text)
        self.assertIn("fetched ok", text)

    def test_expired_session_logs_in_again_and_a_tan_form_never_does(self):
        async def steps(tab):
            first = await tab.act("goto", {"url": "/home"})  # the first login is the model's
            await tab.form([{"field": "User", "value": "agent"}, {"field": "Secret", "value": "s3cret"},
                            {"click": "Sign in"}])
            expired = await tab.act("goto", {"url": "/expire"})
            await tab.act("goto", {"url": "/tan"})
            await tab.act("goto", {"url": "/home"})
            tan = await tab.act("goto", {"url": "/tan"})  # seen before and left: still never filled in
            return first, expired, tan
        first, expired, tan = self.run_tab(steps)
        self.assertNotIn("logged in again", first)
        self.assertIn("logged in again", expired)
        self.assertIn("secret data", expired)
        self.assertNotIn("logged in again", tan)
        self.assertNotIn("POST /sign", COUNTS)

    def test_a_mistyped_password_is_entered_exactly_and_a_tan_never_is(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/home"})
            login = await tab.form([{"field": "User", "value": "agent"}, {"field": "Secret", "value": "s3cet"},
                                    {"click": "Sign in"}])
            await tab.act("goto", {"url": "/tan"})
            text = await tab.read()
            ref = int(text.split('input type=password "Code"')[0].rsplit("[", 1)[1].rstrip(":"))
            await tab.act("fill", {"ref": ref, "text": "804711"})
            return login, await tab.page.input_value("input[name=code]")
        login, tan = self.run_tab(steps)
        self.assertIn("secret data", login)
        self.assertIn("code entered it exactly", login)
        self.assertEqual(tan, "804711")

    def test_repeated_page_chrome_is_left_out_after_an_action_only(self):
        async def steps(tab):
            for n in (1, 2):
                await tab.act("goto", {"url": f"/page{n}"})
            shown = await tab.act("goto", {"url": "/page3"})
            return shown, await tab.read()  # the explicit read, also what save_evidence keeps of the current page
        shown, full = self.run_tab(steps)
        self.assertIn("Record 3", shown)
        self.assertIn("Amount 300 pieces", shown)
        self.assertIn('link "Overview"', shown)  # controls always stay
        self.assertNotIn("Portal banner", shown)
        self.assertNotIn("All rights reserved", shown)
        self.assertIn("lines repeated from earlier pages", shown)
        for line in ("Portal banner", "Service hotline", "Imprint and privacy", "All rights reserved", "Record 3"):
            self.assertIn(line, full)
        self.assertNotIn("left out", full)

    def test_a_custom_styled_checkbox_by_ref_is_ticked_at_once(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/form"})
            text = await tab.read()
            ref = int(text.split('checkbox "Accept"')[0].rsplit("[", 1)[1].rstrip(":"))
            loop = asyncio.get_running_loop()
            started = loop.time()
            await tab.form([{"ref": ref}])
            return loop.time() - started, await tab.page.is_checked("#c")
        took, checked = self.run_tab(steps)
        self.assertTrue(checked)
        self.assertLess(took, 4)  # a covered checkbox waited 8 s for Playwright before the DOM click

    def test_late_content_is_waited_for(self):
        self.assertIn("late value", self.run_tab(lambda tab: tab.act("goto", {"url": "/late"})))

    def test_settle_is_short_on_a_quiet_page(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/form"})
            loop = asyncio.get_running_loop()
            started = loop.time()
            await tab.settle()
            return loop.time() - started
        self.assertLess(self.run_tab(steps), 1.0)  # the fixed wait this replaced took 1.4 s on every read

    def test_form_ref_click_falls_back_and_null_value_is_not_typed(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/form"})
            text = await tab.read()
            ref_button = int(text.split('button "Go"')[0].rsplit("[", 1)[1].rstrip(":"))
            ref_input = int(text.split('input type=text "Note"')[0].rsplit("[", 1)[1].rstrip(":"))
            clicked = await tab.form([{"ref": ref_button}])
            title = await tab.page.title()
            null = await tab.form([{"ref": ref_input, "value": None}])
            value = await tab.page.input_value("#n")
            return clicked, title, null, value
        clicked, title, null, value = self.run_tab(steps)
        self.assertIn("clicked ref", clicked)
        self.assertEqual(title, "clicked")
        self.assertEqual(value, "kept")
        self.assertNotIn("None", value)

    def test_a_navigation_without_answer_is_stopped(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/stuck"})
            loop = asyncio.get_running_loop()
            started = loop.time()
            shown = await asyncio.wait_for(tab.form([{"field": "Size", "value": "5"}, {"click": "Apply"}]), 15)
            shown += await asyncio.wait_for(tab.act("click", {"ref": 2}), 15)  # its DOM-click fallback waited too
            return loop.time() - started, shown
        timeout, browser.NAVIGATION_TIMEOUT = browser.NAVIGATION_TIMEOUT, 2
        try:
            took, shown = self.run_tab(steps)
        finally:
            browser.NAVIGATION_TIMEOUT = timeout
        self.assertLess(took, 14)  # every script on the page waited for the answer, a read until the tool timeout
        self.assertIn("no answer to POST", shown)
        self.assertIn('value="5"', shown)  # stopped, not reloaded: what was typed is still there

    def test_a_new_tab_whose_start_page_never_answers_still_reads(self):
        import agent

        async def steps(tab):
            open_timeout, agent.OPEN_TIMEOUT = agent.OPEN_TIMEOUT, 1
            try:
                new = await agent.fresh(Tab(tab.page, {"url": self.url + "/silent"}))
            finally:
                agent.OPEN_TIMEOUT = open_timeout
            return await asyncio.wait_for(new.read(), 10)  # the pending load held every script to the tool timeout
        self.assertIn("URL:", self.run_tab(steps))

    def test_a_disabled_dependent_choice_fails_fast_and_says_why(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/config"})
            loop = asyncio.get_running_loop()
            started = loop.time()
            unapplied = await tab.form([{"field": "Bore", "value": "50"}, {"field": "Stroke", "value": "600"}])
            spent = loop.time() - started
            applied = await tab.form([{"field": "Bore", "value": "50"}, {"click": "Apply choice"},
                                      {"field": "Stroke", "value": "600"}])
            await tab.act("goto", {"url": "/config-js"})
            scripted = await tab.form([{"field": "Bore", "value": "50"}, {"field": "Stroke", "value": "600"}])
            return unapplied, spent, applied, scripted
        unapplied, spent, applied, scripted = self.run_tab(steps)
        self.assertIn("FAILED", unapplied.split("\n", 1)[0])
        self.assertIn("disabled", unapplied.split("\n", 1)[0])
        self.assertLess(spent, 4.0)
        self.assertNotIn("FAILED", applied.split("\n", 1)[0])
        self.assertNotIn("FAILED", scripted.split("\n", 1)[0])

    def test_a_frame_that_never_loads_does_not_hold_up_reads(self):
        async def steps(tab):
            await tab.page.goto(self.url + "/stalled", wait_until="commit")
            loop = asyncio.get_running_loop()
            started = loop.time()
            first = await asyncio.wait_for(tab.read(), 30)
            second = await tab.read()
            return first, second, loop.time() - started
        first, second, spent = self.run_tab(steps)
        self.assertIn("Main content", first)
        self.assertIn("Main content", second)
        self.assertLess(spent, 10)

    def test_form_finds_fields_by_the_reader_s_name_and_inside_frames(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/plain"})
            plain = await tab.form([{"field": "Quantity", "value": "7"}, {"field": "Ø Pressure", "value": "16 bar"},
                                    {"click": "Send"}])
            values = await tab.page.input_value("[name=q]"), await tab.page.input_value("[name=p]")
            title = await tab.page.title()
            loop = asyncio.get_running_loop()
            started = loop.time()
            missing = await tab.form([{"field": "Colour", "value": "red"}])
            spent = loop.time() - started
            await tab.act("goto", {"url": "/framed"})
            framed = await tab.form([{"field": "Bore", "value": "50"}, {"click": "Apply choice"},
                                     {"field": "Stroke", "value": "600"}])
            return plain, values, title, missing, spent, framed
        plain, values, title, missing, spent, framed = self.run_tab(steps)
        self.assertNotIn("FAILED", plain.split("\n", 1)[0])
        self.assertEqual(values, ("7", "16 bar"))
        self.assertEqual(title, "sent")
        self.assertIn("FAILED", missing.split("\n", 1)[0])
        self.assertLess(spent, 4.0)
        self.assertNotIn("FAILED", framed.split("\n", 1)[0])

    def test_form_finds_names_with_invisible_marks_inside(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/marked"})
            log = await tab.form([{"field": "Delivery date", "value": "2027-02-01"},
                                  {"field": "Reference/No", "value": "X-1"}, {"click": "Send"}])
            return log, await tab.page.input_value("[name=d]"), await tab.page.input_value("[name=n]"), \
                await tab.page.title()
        log, date, ref, title = self.run_tab(steps)
        self.assertNotIn("FAILED", log.split("\n", 1)[0])
        self.assertEqual((date, ref, title), ("2027-02-01", "X-1", "sent"))


    def test_form_finds_fields_and_buttons_named_by_an_icon(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/icons"})
            text = await tab.read()
            log = await tab.form([{"field": "Receipt number", "value": "64"}, {"click": "Send Mail"}])
            return text, log, await tab.page.input_value("#r"), await tab.page.title()
        text, log, value, title = self.run_tab(steps)
        self.assertRegex(text, r'input type=text "Receipt number"')
        self.assertRegex(text, r'button "Send Mail"')
        self.assertNotIn("FAILED", log.split("\n", 1)[0])
        self.assertEqual((value, title), ("64", "sent"))

    def test_a_click_whose_page_loads_slowly_is_neither_repeated_nor_waited_out(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/slowform"})
            text = await tab.read()
            ref = int(text.split('button "Send"')[0].rsplit("[", 1)[1].rstrip(":"))
            loop = asyncio.get_running_loop()
            started = loop.time()
            page = await tab.act("click", {"ref": ref})
            await tab.act("goto", {"url": "/slowform"})
            form = await tab.form([{"click": "Send"}])
            return page, form, loop.time() - started
        page, form, took = self.run_tab(steps)
        self.assertIn("Sent", page)
        self.assertIn("clicked Send", form)
        self.assertEqual(COUNTS.get("POST /slow"), 2)  # one per click: never sent twice
        self.assertLess(took, 15)  # each click took 32 s, ending in an error: 30 s waiting for a button gone


if __name__ == "__main__":
    unittest.main()
