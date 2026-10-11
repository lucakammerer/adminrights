"""reader.js and fetched documents (I17), on synthetic pages for each trap category: decoys out; generated labels,
tooltips and canvas marks in; off-screen text marked; a fetched page's own style rules respected; values of
styled rows kept apart; ARIA widgets and clickable elements given refs; a table row on one line and a tooltip a
control names read once; a PDF read.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import io
import sys
import threading
import unittest
import zipfile
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
<table><tr><th>Ref</th><th>Value</th></tr><tr><td><div>R-1</div></td><td><p>12</p><p>units</p></td></tr></table>
<button aria-describedby="t9">Date</button><span id="t9" role="tooltip">2031-05-06</span>
<div style="display:flex"><span>Bore</span><span>63</span></div>
<div role="row"><span role="gridcell">250</span><span role="gridcell">17,40</span></div>
<span role="link">Open record</span><div role="checkbox" aria-checked="false">Confirm</div>
<div style="cursor:pointer" onmousedown="0">Next results <span>page</span></div>
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

    def test_a_table_row_is_one_line(self):
        for text in (self.live, self.fetched):
            self.assertIn("| Ref | Value\n| R-1 | 12 units\n", text)

    def test_a_tooltip_a_control_names_is_read_once(self):
        for text in (self.live, self.fetched):
            self.assertIn('button "Date" (info: 2031-05-06)', text)
            self.assertEqual(text.count("2031-05-06"), 1)

    def test_values_of_styled_rows_stay_apart_and_widgets_get_refs(self):
        self.assertIn("Bore\n63", self.live)
        for text in (self.live, self.fetched):
            self.assertIn("| 250 | 17,40", text)
        self.assertRegex(self.live, r'\[\d+:link "Open record"\]')
        self.assertRegex(self.live, r'\[\d+:checkbox "Confirm" unchecked\]')
        self.assertRegex(self.live, r"\[\d+:clickable\] Next results page")

    def test_pdf_is_read(self):
        self.assertIn("Delivery note 0815", describe_file("note.pdf", minimal_pdf("Delivery note 0815")))

    def test_office_files_and_other_encodings_are_read(self):
        def archive(files):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for name, text in files.items():
                    z.writestr(name, text)
            return buf.getvalue()
        sheet = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        xlsx = archive({
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": f'<workbook {sheet} {rel}><sheets><sheet name="Prices" r:id="a"/>'
                               f'<sheet name="Old" state="hidden" r:id="b"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                                          'relationships"><Relationship Id="a" Target="worksheets/sheet1.xml"/>'
                                          '<Relationship Id="b" Target="/xl/worksheets/sheet2.xml"/></Relationships>',
            "xl/styles.xml": f'<styleSheet {sheet}><numFmts><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
                             f'</numFmts><cellXfs><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>',
            "xl/sharedStrings.xml": f"<sst {sheet}><si><t>Unit price</t></si><si><t>Widget A</t></si></sst>",
            "xl/worksheets/sheet1.xml": f'<worksheet {sheet}><sheetData><row><c r="C1" t="s"><v>0</v></c></row>'
                                        f'<row><c r="A2" t="s"><v>1</v></c><c r="C2"><v>12.5</v></c><c r="D2" s="1"><v>46082</v></c></row>'
                                        f'<row hidden="1"><c r="A3" t="inlineStr"><is><t>9.99</t></is></c></row>'
                                        f"</sheetData></worksheet>",
            "xl/worksheets/sheet2.xml": f'<worksheet {sheet}><sheetData><row><c r="A1" t="inlineStr"><is><t>7.77'
                                        f"</t></is></c></row></sheetData></worksheet>"})
        text = describe_file("prices.xlsx", xlsx)
        self.assertIn("\t\tUnit price\nWidget A\t\t12.5\t2026-03-01", text)
        self.assertNotIn("9.99", text)
        self.assertNotIn("7.77", text)
        word = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        docx = archive({"[Content_Types].xml": "<Types/>", "word/document.xml": (
            f"<w:document {word}><w:body><w:p><w:pPr><w:rPr><w:vanish/></w:rPr></w:pPr><w:r><w:t>Delivery 3 weeks"
            f"</w:t></w:r></w:p><w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>Price 1</w:t></w:r><w:r><w:t>Price 2</w:t>"
            f"</w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Qty</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>40"
            f"</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>")})
        self.assertEqual(describe_file("t.docx", docx), "DOCUMENT t.docx:\nDelivery 3 weeks\nPrice 2\nQty\t40\n")
        export = "Material;Preis €\nGröße;1,50\n"
        for encoding in ("cp1252", "utf-16", "utf-16-le"):
            self.assertIn(export, describe_file("export.csv", export.encode(encoding)))


if __name__ == "__main__":
    unittest.main()
