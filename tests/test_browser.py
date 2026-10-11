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
import html as markup
import re
from urllib.parse import parse_qs, parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

from browser import Tab, page_links  # noqa: E402

LOGIN = ('<form method="post" action="/login"><label>User <input name="user"></label>'
         '<label>Secret <input type="password" name="pw"></label><button>Sign in</button></form>')
TAN = ('<form method="post" action="/sign"><label>Request <input name="request" value="7"></label>'
       '<label>Code <input type="password" name="code"></label><button>Sign</button></form>')
COUNTS: dict[str, int] = {}
MAIL_LIST = Path(__file__).resolve().parents[1] / "eval/fixtures/pages/mail-result-list.html"  # a recorded result list


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
        if path == "/list":  # a paged list: page links, plus links that are not pages of it
            query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            n = (query.get("page") or ["1"])[0]
            return self.page(f'<p>Row {n}</p>' + "".join(f'<a href="?q=x&page={i}">{i}</a>' for i in (1, 2, 3)) +
                             '<a href="/record/7">7</a><a href="?q=y&page=2">2</a><a href="?q=x&sort=d">Sort</a>')
        if path == "/" and "folder=" in self.path and MAIL_LIST.exists():
            data = MAIL_LIST.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return self.wfile.write(data)
        if path == "/slowform":
            return self.page('<form method="post" action="/slow"><button>Send</button></form>')
        if path == "/form":
            return self.page('<div style="position:relative"><button id="b" onclick="document.title=\'clicked\'">Go'
                             '</button><div style="position:absolute;inset:0;background:#fff"></div></div>'
                             '<label>Note <input id="n" value="kept"></label>'
                             '<label class="fancy"><input type="checkbox" id="c" style="opacity:0;position:absolute">'
                             '<span style="position:relative;z-index:2;background:#eee">Accept</span></label>')
        return self.page("start")

    def do_POST(self):
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

    def test_a_paged_list_comes_whole_in_one_fetch(self):
        async def steps(tab):
            pages, note = await tab.fetch_list("/list?q=x")
            return pages, note, await tab.act("fetch", {"url": "/list?q=x", "all_pages": True})
        pages, note, text = self.run_tab(steps)
        rows = [line for _, page in pages for line in page.split("\n") if line.startswith("Row")]
        self.assertEqual(sorted(rows), ["Row 1", "Row 2", "Row 3"])  # page 1 again under ?page=1 is not kept twice
        self.assertIn("3 pages read", note)
        self.assertNotIn("/record/7", COUNTS)  # a record link labelled with a number is not a page of the list
        self.assertTrue(all(row in text for row in ("Row 1", "Row 2", "Row 3")))

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

    @unittest.skipUnless(MAIL_LIST.exists(), "no recorded mailbox page")
    def test_a_recorded_mailbox_list_leads_to_its_next_page(self):
        """Its next-page link keeps the open message in the URL: one page number changed, one value added."""
        next_page = markup.unescape(re.search(r'href="([^"]*)"[^>]*>\s*N\S*chste Seite', MAIL_LIST.read_text("utf-8"))
                                    .group(1))
        query = dict(parse_qsl(urlsplit(next_page).query))
        list_url = "/?" + "&".join(f"{k}={query[k]}" for k in ("folder", "q"))
        text = self.run_tab(lambda tab: tab.fetch(list_url))
        self.assertEqual(page_links(self.url + list_url, self.url + list_url, text), [self.url + next_page])

    def test_a_missing_form_field_or_button_fails_at_once(self):
        async def steps(tab):
            await tab.act("goto", {"url": "/form"})
            loop = asyncio.get_running_loop()
            started = loop.time()
            field = await tab.form([{"field": "Nowhere", "value": "x"}])
            button = await tab.form([{"click": "Nowhere"}])
            return field, button, loop.time() - started
        field, button, took = self.run_tab(steps)
        self.assertIn("no field labelled 'Nowhere'", field)
        self.assertIn("no button or link 'Nowhere'", button)
        self.assertLess(took, 8)  # Playwright's own wait took 30 s for a missing field


class PageLinks(unittest.TestCase):
    def test_only_other_pages_of_the_same_list(self):
        text = ('[link "2" -> ?q=x&page=2] [3:link "3" -> /list?q=x&page=3] [link "Next" -> ?q=x&page=2] '
                '[link "7" -> /record/7] [link "2" -> ?q=y&page=2] [link "Sort" -> ?q=x&sort=d] '
                '[link "4" -> https://other.example/list?q=x&page=4]')
        base = "https://site.example/list?q=x"
        self.assertEqual(page_links(base, base, text),
                         ["https://site.example/list?q=x&page=2", "https://site.example/list?q=x&page=3"])

    def test_an_added_value_is_state_a_changed_one_another_list(self):
        text = ('[link "Nächste Seite" -> /?folder=archive&q=r&page=2&message=m-1] '
                '[link "Subject" -> /?folder=archive&q=r&page=1&message=m-2] [link "2" -> /?folder=inbox&q=r&page=2]')
        base = "https://mail.example/?folder=archive&q=r"
        self.assertEqual(page_links(base, base, text), ["https://mail.example/?folder=archive&q=r&page=2&message=m-1"])


if __name__ == "__main__":
    unittest.main()
