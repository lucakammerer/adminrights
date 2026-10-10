"""Paging in code: the model picks a result list and asks for all of it (`all_pages`); code follows that list's own
page links, so one tool call reads what took a model step per page. The brief allows helpers to "paginate a
model-selected result set". Nothing here knows a website: another page of the list is a link on it that differs from
the list's URL only in one number (a query parameter or a path segment)."""
import asyncio
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

LINK = re.compile(r'\[(?:\d+:)?link ".*?" -> ([^\]\s]+)\]')  # a link as reader.js writes it
MAX_PAGES = 8  # pages of one list at most, the first included: a longer list wants a narrower search
MAX_CHARS = 48_000  # text of the further pages at most, so one result can't crowd out the rest of the context
PARALLEL = 4
HEAD = re.compile(r"^(URL: |Title: |Fetched |Form steps: |Done by code: |Browser dialogs )[^\n]*\n")


def step(url: str, other: str) -> tuple[tuple, int] | None:
    """(where the two differ, the number `other` has there) if `other` may be another page of the list at `url`; the
    first page often has no page number, which counts as 0."""
    a, b = urlsplit(url), urlsplit(other)
    if (a.scheme, a.netloc) != (b.scheme, b.netloc):
        return None
    qa, qb = dict(parse_qsl(a.query, keep_blank_values=True)), dict(parse_qsl(b.query, keep_blank_values=True))
    if a.path == b.path:
        diff = [k for k in qa.keys() | qb.keys() if qa.get(k) != qb.get(k)]
        if len(diff) != 1:
            return None
        mine, theirs = qa.get(diff[0], "0"), qb.get(diff[0], "0")
        return (("query", diff[0]), int(theirs)) if mine.isdigit() and theirs.isdigit() else None
    sa, sb = a.path.rstrip("/").split("/"), b.path.rstrip("/").split("/")
    if qa != qb or len(sa) != len(sb):
        return None
    diff = [i for i in range(len(sa)) if sa[i] != sb[i]]
    if len(diff) == 1 and sa[diff[0]].isdigit() and sb[diff[0]].isdigit():
        return ("path", diff[0]), int(sb[diff[0]])
    return None


def body(text: str) -> str:
    """A page's text without the tool's header lines and ref numbers, to tell whether two reads show the same page."""
    while (match := HEAD.match(text)) is not None:
        text = text[match.end():]
    return re.sub(r"\s+", " ", re.sub(r"\[\d+:", "[", text)).strip()


def number(url: str, key: tuple) -> int:
    """The page number `url` has where the pages of its list differ (`key` as `step` gives it); none counts as 0."""
    parts = urlsplit(url)
    if key[0] == "query":
        value = dict(parse_qsl(parts.query, keep_blank_values=True)).get(key[1], "0")
    else:
        segments = parts.path.rstrip("/").split("/")
        value = segments[key[1]] if key[1] < len(segments) else "0"
    return int(value) if value.isdigit() else 0


def links(url: str, page_url: str, text: str) -> dict[tuple, dict[int, str]]:
    """The links on a page (read at `page_url`) that may lead to other pages of the list at `url`, by where they
    differ: {key: {number: url}}."""
    found: dict[tuple, dict[int, str]] = {}
    for href in LINK.findall(text):
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        target = urljoin(page_url, href)
        if (hit := step(url, target)) is not None:
            found.setdefault(hit[0], {}).setdefault(hit[1], target)
    return found


async def rest(fetch, url: str, text: str) -> tuple[list[tuple[str, str]], str]:
    """The further pages of the list `text` shows (read at `url`), each read with `fetch(url) -> text`, in page order;
    and a note for the model on what was read and what was left out. Follows the page links of every page it reads,
    so a pager that shows a few numbers at a time is read to its end."""
    candidates = links(url, url, text)
    if not candidates:
        return [], "No links to further pages of this list found: it has one page, or its pager is not a link."
    key = max(candidates, key=lambda k: len(candidates[k]))  # the pager: the number with the most links
    done, seen = {number(url, key)}, {body(text)}
    pages: list[tuple[int, str, str]] = []
    todo = candidates[key]
    gate = asyncio.Semaphore(PARALLEL)
    chars, left_out = 0, []

    async def read(target: str) -> str:
        async with gate:
            return await fetch(target)
    while todo:
        batch = sorted((n, u) for n, u in todo.items() if n not in done)
        room = MAX_PAGES - 1 - len(pages)
        left_out += [u for _, u in batch[room:]]
        batch = batch[:max(0, room)]
        if not batch:
            break
        done.update(n for n, _ in batch)
        texts = await asyncio.gather(*(read(u) for _, u in batch))
        todo = {}
        for (n, u), page in zip(batch, texts):
            if body(page) in seen:  # the first page again under another number (page=1 for a list without one)
                continue
            if chars + len(page) > MAX_CHARS:
                left_out.append(u)
                continue
            seen.add(body(page))
            chars += len(page)
            pages.append((n, u, page))
            for n2, u2 in links(url, u, page).get(key, {}).items():
                if n2 not in done:
                    todo.setdefault(n2, u2)
    pages.sort()
    note = f"Code read {len(pages)} further page(s) of this list"
    if left_out:
        note += (f"; {len(left_out)} more not read (over {MAX_PAGES} pages or {MAX_CHARS} characters): narrow the "
                 f"search, or fetch them: {', '.join(left_out[:10])}")
    return [(u, page) for _, u, page in pages], note + "."
