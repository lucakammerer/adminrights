"""Generic browser tools for the model: read a page as text with control refs, act on a ref, read a URL without
navigating, open downloaded files. Nothing here knows any website; the model decides where to go and what to do."""
import asyncio
import io
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin

READER = (Path(__file__).parent / "reader.js").read_text()
MAX_CHARS = 14000


class Tab:
    def __init__(self, page, site: dict):
        self.page = page
        self.site = site
        self.dialogs: list[str] = []
        self.downloads: list[str] = []
        page.on("dialog", self._on_dialog)
        page.on("download", self._on_download)

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
        await asyncio.sleep(1.4)  # popups and banners appear a moment after load
        for frame in self.page.frames:  # in-page popup dialogs only block the page; browser dialogs are accepted above
            try:
                await frame.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
            except Exception:  # noqa: BLE001
                pass

    async def read(self, offset: int = 0) -> str:
        await self.settle()
        result = await self.page.evaluate(f"({READER})({{}})")
        text = result["text"]
        events = ""
        if self.dialogs:
            events += "Browser dialogs (accepted): " + " || ".join(self.dialogs) + "\n"
            self.dialogs.clear()
        if self.downloads:
            events += "Downloaded files:\n" + "\n\n".join(self.downloads) + "\n"
            self.downloads.clear()
        head = f"URL: {self.page.url}\nTitle: {await self.page.title()}\n{events}\n"
        body = text[offset:offset + MAX_CHARS]
        if len(text) > offset + MAX_CHARS:
            body += f"\n[... {len(text) - offset - MAX_CHARS} more chars: call read with offset={offset + MAX_CHARS}]"
        return head + body

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
                try:
                    await loc.scroll_into_view_if_needed(timeout=3000)
                    await loc.click(timeout=5000)
                except Exception:  # noqa: BLE001  covered, off-screen in a scroll box, inert: click it in the DOM
                    await loc.evaluate("e => e.click()")
            elif action == "fill":
                kind = await loc.evaluate("e => e.type")
                if kind == "range":
                    await loc.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true}));"
                                       " e.dispatchEvent(new Event('change', {bubbles: true})) }", str(args["text"]))
                else:
                    await loc.fill(str(args["text"]), timeout=5000)
            elif action == "select":
                await loc.select_option(label=str(args["option"]), timeout=5000)
            elif action == "check":
                await loc.set_checked(bool(args.get("checked", True)), timeout=5000, force=True)
            else:
                return f"unknown action {action}"
        return await self.read()

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
                if step.get("click"):
                    loc = page.get_by_role("button", name=str(step["click"]))
                    if not await loc.count():
                        loc = page.get_by_role("link", name=str(step["click"]))
                    await loc.first.scroll_into_view_if_needed(timeout=3000)
                    await loc.first.click(timeout=5000)
                    await self.settle()
                    log.append(f"clicked {step['click']}")
                    continue
                label, value = str(step["field"]), step.get("value")
                loc = page.get_by_label(label, exact=True)
                if not await loc.count():
                    loc = page.get_by_label(label)
                loc = loc.first
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
                    await loc.fill(str(value), timeout=5000)
                log.append(f"set {label} = {value}")
            except Exception as error:  # noqa: BLE001  stop at the first failing step, the model sees why
                log.append(f"FAILED at {step}: {str(error)[:300]}")
                break
        return "Form steps: " + "; ".join(log) + "\n\n" + await self.read()

    async def fetch(self, url: str) -> str:
        """Read a same-origin URL through the logged-in page without navigating: text only, no refs."""
        result = await self.page.evaluate(
            """async (url) => {
                const r = await fetch(url, {credentials: 'include'})
                const type = r.headers.get('content-type') || ''
                if (!type.includes('html')) {
                    const buf = new Uint8Array(await r.arrayBuffer())
                    let bin = ''; for (const b of buf) bin += String.fromCharCode(b)
                    return {status: r.status, url: r.url, type, b64: btoa(bin)}
                }
                return {status: r.status, url: r.url, type, html: await r.text()}
            }""", urljoin(self.page.url, url))
        head = f"Fetched {result['url']} (HTTP {result['status']})\n"
        if "html" in result:
            text = (await self.page.evaluate(f"({READER})({{doc: {_js(result['html'])}}})"))["text"]
            return head + text[:MAX_CHARS]
        import base64
        return head + describe_file(url.rsplit("/", 1)[-1], base64.b64decode(result["b64"]))


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
