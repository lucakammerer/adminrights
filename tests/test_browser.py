"""browser.Tab against a local test server (I13): transient errors, an expired session, late content, form steps.
No website and no model: a tiny HTTP server runs inside the test, Chromium headless.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

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
        if path == "/form":
            return self.page('<div style="position:relative"><button id="b" onclick="document.title=\'clicked\'">Go'
                             '</button><div style="position:absolute;inset:0;background:#fff"></div></div>'
                             '<label>Note <input id="n" value="kept"></label>')
        return self.page("start")

    def do_POST(self):
        body = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
        COUNTS["POST " + self.path] = COUNTS.get("POST " + self.path, 0) + 1
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


if __name__ == "__main__":
    unittest.main()
