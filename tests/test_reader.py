"""reader.js and fetched documents (I17), on synthetic pages for each trap category: decoys out; generated labels,
tooltips and canvas marks in; off-screen text marked; a fetched page's own style rules respected; a PDF read.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

from browser import Tab, describe_file  # noqa: E402

PAGE = """<!doctype html><html><head><style>
.gone { display: none } .ghost { visibility: hidden } .label::before { content: attr(data-label) ": " }
.unit::after { content: " pieces" } .sr { position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0) } .away { position: absolute; left: -9999px } .dot::before { content: "\\2022" }
</style></head><body>
<p>Quantity <span class="label" data-label="Binding total">40</span><span class="unit"></span></p>
<p class="gone">Quantity 999 decoy-class</p><p class="ghost">decoy-ghost</p>
<p aria-hidden="true">decoy-aria</p><p style="display:none">decoy-inline</p>
<span title="Received 2030-01-02 10:00">Date</span>
<canvas id="c1" aria-label="Receipt 4711"></canvas><canvas id="c2"></canvas>
<span class="sr">screen reader value 17</span><div class="away">off page value 23</div>
<p class="dot">listed</p>
<span role="tooltip">Status released <span class="gone">decoy-in-tooltip</span></span>
<span role="tooltip" style="visibility:hidden">Valid until 2030-12-31 <b>hover value 31</b></span>
<a href="/x">Open <span aria-hidden="true">decoy-in-link</span></a>
<button aria-describedby="d1">Check</button><span id="d1">Approved <b hidden>decoy-in-description</b></span>
</body></html>"""


class Site(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.encode())


def minimal_pdf(text: str) -> bytes:
    """A one-page PDF with one line of text, built by hand (offsets computed)."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


class Reader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{cls.server.server_port}/"

        async def go():
            async with async_playwright() as p:
                b = await p.chromium.launch(headless=True)
                page = await (await b.new_context()).new_page()
                await page.goto(url, wait_until="domcontentloaded")
                tab = Tab(page, {"url": url, "credentials": {}})
                live, fetched = await tab.read(), await tab.fetch(url)
                await b.close()
                return live, fetched
        cls.live, cls.fetched = asyncio.run(go())

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_decoys_stay_out(self):
        for text in (self.live, self.fetched):
            for decoy in ("decoy-class", "decoy-ghost", "decoy-aria", "decoy-inline", "999", "decoy-in-tooltip",
                          "decoy-in-link", "decoy-in-description"):
                self.assertNotIn(decoy, text)

    def test_generated_labels_and_units_are_read(self):
        for text in (self.live, self.fetched):
            self.assertIn("Binding total", text)
            self.assertIn("pieces", text)
            self.assertNotIn("•", text)  # decorative symbols stay out

    def test_tooltips_and_canvas(self):
        self.assertIn("(tooltip: Status released)", self.live)
        self.assertIn("(tooltip: Valid until 2030-12-31 hover value 31)", self.live)  # hidden until hover, still read
        self.assertIn('link "Open"', self.live)
        for text in (self.live, self.fetched):
            self.assertIn("(tooltip: Received 2030-01-02 10:00)", text)
            self.assertIn("Receipt 4711", text)
            self.assertIn("canvas without text", text)

    def test_off_screen_text_is_kept_but_marked(self):
        for text in (self.live, self.fetched):
            self.assertIn("(off-screen text: screen reader value 17)", text)
            self.assertIn("(off-screen text: off page value 23)", text)

    def test_pdf_is_read(self):
        self.assertIn("Delivery note 0815", describe_file("note.pdf", minimal_pdf("Delivery note 0815")))


if __name__ == "__main__":
    unittest.main()
