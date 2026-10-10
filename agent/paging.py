"""Pagination for a result set the model has selected.

With `all_pages`, code follows only links that differ from the selected list URL by one numeric page component. It
does not know a site's routes or choose a search: it merely paginates a model-selected list, as the run rules allow.
"""
import asyncio
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

LINK = re.compile(r'\[(?:\d+:)?link ".*?" -> ([^\]\s]+)\]')
MAX_PAGES = 8  # first page included; a larger result set needs a narrower model-selected query
MAX_CHARS = 48_000  # further pages cannot crowd all other context out of one tool result
PARALLEL = 4
HEAD = re.compile(r"^(URL: |Title: |Fetched |Form steps: |Done by code: |Browser dialogs )[^\n]*\n")


def step(url: str, other: str) -> tuple[tuple, int] | None:
    """The one numeric location by which `other` may be a page of the list at `url`, else None."""
    first, second = urlsplit(url), urlsplit(other)
    if (first.scheme, first.netloc) != (second.scheme, second.netloc):
        return None
    first_query = dict(parse_qsl(first.query, keep_blank_values=True))
    second_query = dict(parse_qsl(second.query, keep_blank_values=True))
    if first.path == second.path:
        changed = [key for key in first_query.keys() | second_query.keys()
                   if first_query.get(key) != second_query.get(key)]
        if len(changed) != 1:
            return None
        mine, theirs = first_query.get(changed[0], "0"), second_query.get(changed[0], "0")
        return (("query", changed[0]), int(theirs)) if mine.isdigit() and theirs.isdigit() else None
    first_path, second_path = first.path.rstrip("/").split("/"), second.path.rstrip("/").split("/")
    if first_query != second_query or len(first_path) != len(second_path):
        return None
    changed = [index for index in range(len(first_path)) if first_path[index] != second_path[index]]
    if len(changed) == 1 and second_path[changed[0]].isdigit() and first_path[changed[0]].isdigit():
        return ("path", changed[0]), int(second_path[changed[0]])
    return None


def body(text: str) -> str:
    """Page text without browser-tool headers or volatile reader refs, used for duplicate detection."""
    while (match := HEAD.match(text)) is not None:
        text = text[match.end():]
    return re.sub(r"\s+", " ", re.sub(r"\[\d+:", "[", text)).strip()


def number(url: str, key: tuple) -> int:
    """The numeric value at a list's page key; a missing initial page number is zero."""
    parts = urlsplit(url)
    if key[0] == "query":
        value = dict(parse_qsl(parts.query, keep_blank_values=True)).get(key[1], "0")
    else:
        values = parts.path.rstrip("/").split("/")
        value = values[key[1]] if key[1] < len(values) else "0"
    return int(value) if value.isdigit() else 0


def links(url: str, page_url: str, text: str) -> dict[tuple, dict[int, str]]:
    """Potential sibling pages, grouped by the one numeric list-page component they change."""
    found: dict[tuple, dict[int, str]] = {}
    for href in LINK.findall(text):
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        target = urljoin(page_url, href)
        if (candidate := step(url, target)) is not None:
            found.setdefault(candidate[0], {}).setdefault(candidate[1], target)
    return found


async def rest(fetch, url: str, text: str) -> tuple[list[tuple[str, str]], str]:
    """Fetch later/earlier pages of the selected list in page order, bounded and with an explicit truncation note."""
    candidates = links(url, url, text)
    if not candidates:
        return [], "No links to further pages of this list found: it has one page, or its pager is not a link."
    key = max(candidates, key=lambda candidate: len(candidates[candidate]))
    done, seen = {number(url, key)}, {body(text)}
    pages: list[tuple[int, str, str]] = []
    todo = candidates[key]
    gate = asyncio.Semaphore(PARALLEL)
    chars, left_out = 0, []

    async def read(target: str) -> str:
        async with gate:
            return await fetch(target)

    while todo:
        batch = sorted((page, target) for page, target in todo.items() if page not in done)
        room = MAX_PAGES - 1 - len(pages)
        left_out += [target for _, target in batch[room:]]
        batch = batch[:max(0, room)]
        if not batch:
            break
        done.update(page for page, _ in batch)
        texts = await asyncio.gather(*(read(target) for _, target in batch))
        todo = {}
        for (page_number, target), page in zip(batch, texts):
            if body(page) in seen:
                continue
            if chars + len(page) > MAX_CHARS:
                left_out.append(target)
                continue
            seen.add(body(page))
            chars += len(page)
            pages.append((page_number, target, page))
            for next_number, next_target in links(url, target, page).get(key, {}).items():
                if next_number not in done:
                    todo.setdefault(next_number, next_target)
    pages.sort()
    note = f"Code read {len(pages)} further page(s) of this list"
    if left_out:
        note += (f"; {len(left_out)} more not read (over {MAX_PAGES} pages or {MAX_CHARS} characters): narrow the "
                 f"search, or fetch them: {', '.join(left_out[:10])}")
    return [(target, page) for _, target, page in pages], note + "."
