"""The model loop: a model works one website through browser tools until it calls `finish` with its findings."""
import asyncio
import json
import os
import re
import time
from contextlib import contextmanager
from urllib.parse import urljoin
from contextvars import ContextVar

from openai import AsyncOpenAI
from openai.lib.streaming.chat import ChatCompletionStreamState

import paging

MODEL = os.environ.get("AGENT_MODEL", "qwen3.8-flash-next")
# AGENT_MODEL="<provider>/<model>" runs on OpenRouter with the team secret OPENROUTER_API_KEY, through the run's proxy:
# no shared queue (35-47 % of the hosted Qwen's call time was queue wait); Haiku signed 100 in 580-598 s for $0.11.
OPENROUTER = "/" in MODEL
# Anthropic models cache only behind a breakpoint; this top-level one moves with the conversation
CACHE = {"cache_control": {"type": "ephemeral"}} if MODEL.startswith("anthropic/") else {}
STEP_EFFORT = os.environ.get("STEP_EFFORT", "low")  # reasoning per browser step; latency is mostly thinking tokens
KEEP_STEPS = 4  # tool results of the latest steps stay in full; older page reads shrink so the context stays small
# Older reads shrink in batches, not every step: a shortened read changes the history, so the prompt cache only covers
# what comes before it. Trimming each step re-sent the latest pages at full price on every call (50-64% of a run's
# uncached input); between batches the history only grows and is read from the cache. A batch is due once TRIM_EVERY
# steps have left the KEEP_STEPS window, or earlier when their tool results reach TRIM_CHARS.
TRIM_EVERY = 6
TRIM_CHARS = 60_000
# The API returns the model's reasoning with every reply and reads whatever is sent back as input on every later
# step. It stays while its step is in the KEEP_STEPS window (the model's train of thought) and goes in the same
# batches as the older page reads.
REASONING = ("reasoning", "reasoning_content")
CALL_TIMEOUT = 180  # one model call; a slower one is retried while its deadline allows (steps took 20-90 s under load,
# a tender finish 132 s: a cut call starts over, so the cap sits above the slowest calls seen)
CHECK_TIMEOUT = 60  # one model call inside a finish check (ERP extract: 13-21 s); one hung call cost a position
TOOL_TIMEOUT = 60  # one browser tool; a fetch that hung 109 s held the tender agent to its cut, its kept pages lost
# A call that brings no byte for this long is stuck and asked again (a retry waits twice as long, in case the service is
# only slow). Replies are streamed, so a healthy one sends its first chunk within seconds and then one every <1 s; a
# stuck call never reaches the model (none of the 6 in run_76abdc35df9c092b shows in the platform's calls) and held
# its stage to the cap: three of the four ERP searches lost their whole two minutes to their first call.
SILENCE = 30
# An OpenRouter call without an answer after HEDGE seconds gets a twin, and the first answer wins: about one call in six
# never came back (one held a tender agent's first step for 240 s), while answered calls took 3-13 s.
HEDGE = 15
# A streamed call without its first chunk after FIRST_CHUNK seconds gets a twin the same way, and keeps running: 6-10
# hosted Qwen calls a run sat silent until SILENCE (run_ba99f2d4eb2f586e: three on the slowest ERP search), while the
# platform's queue wait for answered calls was p95 1-14 s.
FIRST_CHUNK = 10

# The time by which every model call in this task must be over (set by agent.safe for each stage) and the longest
# one call may take. chat enforces both on the wall clock: the HTTP timeout only bounds the silence between bytes, and
# a call that received a byte now and then ran 184 s under a 120 s timeout.
UNTIL: ContextVar[float] = ContextVar("until", default=float("inf"))
CAP: ContextVar[float] = ContextVar("cap", default=CALL_TIMEOUT)
# The evidence lists of the investigations in this task (agent.start gives each stage one), so a stage that is cut
# at its deadline or crashes still hands on the pages its agents kept.
KEPT: ContextVar[list | None] = ContextVar("kept", default=None)


@contextmanager
def limits(until: float, cap: float | None = None):
    """Model calls inside end by `until` (never later than the stage allows) and take at most `cap` each."""
    tokens = [(UNTIL, UNTIL.set(min(UNTIL.get(), until)))] + ([(CAP, CAP.set(cap))] if cap else [])
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

_client = None
_fallback = None
# An OpenRouter model's last three attempts at a call go to the hosted Qwen, which agent.json keeps warm (its warm-up
# never counts toward the run's time): a provider that fails three times must not end an agent.
FALLBACK = "qwen3.8-flash-next"
T0 = time.time()


def log(tag: str, text: str):
    print(f"[{tag} {time.time() - T0:4.0f}s] {text}", flush=True)


def client(fallback: bool = False) -> AsyncOpenAI:
    global _client, _fallback
    if fallback:
        if _fallback is None:
            _fallback = AsyncOpenAI(base_url=os.environ["QWEN_BASE_URL"], api_key=os.environ["QWEN_API_KEY"],
                                    timeout=CALL_TIMEOUT, max_retries=0)
        return _fallback
    if _client is None:
        # no retries inside the SDK: they would multiply the timeout behind chat's back
        if OPENROUTER:
            proxy = os.environ.get("LLM_PROXY_URL")
            url, key = (f"{proxy}/openrouter/v1" if proxy else "https://openrouter.ai/api/v1"), "OPENROUTER_API_KEY"
        else:
            url, key = os.environ["QWEN_BASE_URL"], "QWEN_API_KEY"
        _client = AsyncOpenAI(base_url=url, api_key=os.environ[key], timeout=CALL_TIMEOUT, max_retries=0)
    return _client


async def reply(messages: list, tools: list | None, silence: float, fallback: bool = False,
                heard: asyncio.Event | None = None, **kwargs):
    """One streamed model reply, assembled like a non-streamed one; every read must bring a byte within `silence`, and
    `heard` is set at the first chunk. The snapshot, not get_final_completion: that raises on a reply cut at its length
    limit, which counted before."""
    extra = {"extra_body": CACHE} if CACHE and not fallback else {}
    if OPENROUTER and not fallback:  # streamed, Haiku repeated the same login 40 times in every tab
        # (run_ac62aa59878278d0); unstreamed it worked (run_0bf3628e04112a0c). Its calls take 3-13 s, so a silent one
        # still ends at `silence`.
        return await client().chat.completions.create(model=MODEL, messages=messages, tools=tools, timeout=silence,
                                                      **extra, **kwargs)
    stream = await client(fallback).chat.completions.create(model=FALLBACK if fallback else MODEL, messages=messages,
                                                            tools=tools, stream=True, timeout=silence,
                                                            stream_options={"include_usage": True}, **extra, **kwargs)
    state, chunks = ChatCompletionStreamState(), 0
    async with stream:
        async for chunk in stream:
            state.handle_chunk(chunk)
            chunks += 1
            if heard:
                heard.set()
    if not chunks or not state.current_completion_snapshot.choices:
        raise ValueError("the reply stream brought no message")
    return state.current_completion_snapshot


async def chat(messages: list, tools: list | None = None, hosted: bool = False, **kwargs):
    """One model reply, each attempt bounded by CAP and all of them by UNTIL; raises TimeoutError when time is up. An
    attempt silent for SILENCE seconds (twice that on a retry) is dropped and asked again. hosted: the hosted Qwen
    answers even when MODEL is an OpenRouter model."""
    for attempt in range(6):
        left = UNTIL.get() - time.time() - 1
        if left < 3:
            raise TimeoutError("no time left for a model call")
        limit = min(CAP.get(), left)
        began = time.time()
        fallback = OPENROUTER and (hosted or attempt >= 3) and "QWEN_BASE_URL" in os.environ
        heard = asyncio.Event()  # never set for an unstreamed OpenRouter reply: its twin waits for the answer

        def ask(heard: asyncio.Event) -> asyncio.Future:
            call = asyncio.ensure_future(reply(messages, tools, min(SILENCE * (2 if attempt else 1), limit), fallback,
                                               heard, **kwargs))
            call.add_done_callback(lambda c: c.cancelled() or c.exception())  # a dropped call's failure stays quiet
            return call
        calls = [ask(heard)]
        listening = asyncio.ensure_future(heard.wait())
        try:
            # asyncio.wait, not wait_for: wait_for waits until the cancelled call has stopped, a cut never does
            await asyncio.wait([calls[0], listening], return_when=asyncio.FIRST_COMPLETED,
                               timeout=min(HEDGE if OPENROUTER and not fallback else FIRST_CHUNK, limit))
            if not calls[0].done() and not heard.is_set():
                print(f"[llm] twin after {time.time() - began:.0f} s without a reply", flush=True)
                calls.append(ask(asyncio.Event()))
            while True:
                answered = [c for c in calls if c.done() and not c.cancelled() and c.exception() is None]
                if answered:
                    return answered[0].result()
                waiting = [c for c in calls if not c.done()]
                if not waiting:
                    raise calls[-1].exception()
                rest = limit - (time.time() - began)
                if rest <= 0:
                    raise TimeoutError(f"model call over {limit:.0f} s")
                await asyncio.wait(waiting, timeout=rest, return_when=asyncio.FIRST_COMPLETED)
        except Exception as error:  # noqa: BLE001  the hosted model may hiccup: retry like any provider
            if attempt == 5:
                raise
            print(f"[llm] retry after {type(error).__name__} at {time.time() - began:.0f} s: {str(error)[:200]}",
                  flush=True)
            await asyncio.sleep(min(2 + 3 * attempt, max(0.0, UNTIL.get() - time.time() - 5)))
        finally:
            listening.cancel()
            for call in calls:
                call.cancel()  # no-op once done; frees the connection of a call over its time or of a cut stage


def parse_object(text: str) -> dict | None:
    """An object the model sent as a string; raw line breaks inside its strings are tolerated."""
    try:
        value = json.loads(text[text.find("{"):text.rfind("}") + 1], strict=False)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def ask_json(system: str, user: str, effort: str | None = None) -> dict:
    """One reasoning call that must answer with a JSON object. effort="low" suits copying values out of pages: several
    times faster, while switching thinking off entirely made the model rewrite number formats. Always on the hosted
    Qwen: the resolvers and the ERP extract are measured on it (tools/resolver_eval.py)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    extra = {"reasoning_effort": effort} if effort else {}
    for _ in range(3):
        reply = await chat(messages, response_format={"type": "json_object"}, hosted=True, **extra)
        text = reply.choices[0].message.content or ""
        value = parse_object(text)
        if value is not None:
            return value
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "That was not valid JSON. Answer with the JSON object only."}]
    raise ValueError("no JSON from the model")


def _fn(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties or {}, "required": required or []}}}


REF = {"ref": {"type": "integer", "description": "the number in [n:...] on the last page read"}}
ALL_PAGES = {"all_pages": {"type": "boolean", "description": (
    "true for a paged list (search results, messages, Q&A): code also reads every further page of it by the list's "
    "own page links and returns them together, so one call does what took one per page")}}
BROWSER_TOOLS = [
    _fn("read", "Read the current page again (text with [n:control] refs). Use offset to continue a long page.",
        {"offset": {"type": "integer"}, **ALL_PAGES}),
    _fn("goto", "Open a URL (absolute, or relative to the current page).", {"url": {"type": "string"}}, ["url"]),
    _fn("click", "Click a link, button, summary, menu item, tab or clickable element by its ref.", REF, ["ref"]),
    _fn("fill", "Type text into an input or textarea by ref (replaces its value). For a slider, the value.",
        {**REF, "text": {"type": "string"}}, ["ref", "text"]),
    _fn("select", "Choose an option of a select by its visible label.", {**REF, "option": {"type": "string"}},
        ["ref", "option"]),
    _fn("check", "Tick (checked=true) or untick a checkbox or radio button by ref.",
        {**REF, "checked": {"type": "boolean"}}, ["ref"]),
    _fn("press", "Press a key on the focused element, e.g. Enter, Escape, Tab.", {"key": {"type": "string"}},
        ["key"]),
    _fn("back", "Go back in the browser history."),
    _fn("form", "Work through a form in one go: steps run in order, each waits for the page to settle. A step is "
        "{\"field\": \"<label>\", \"value\": \"...\"} (fills an input, picks a select option by its text, or "
        "ticks a checkbox with true/false) or {\"click\": \"<button label>\"}. Labels are the visible labels, so "
        "steps survive page reloads (e.g. pick a value, click 'apply selection', pick the next value). A control "
        "without a usable label: {\"ref\": n, \"value\": \"...\"}, or {\"ref\": n} to click it; refs hold only "
        "until the page reloads. Fields in collapsed sections are opened first. Stops at the first failing step and "
        "says why.",
        {"steps": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "value": {"type": "string"}, "click": {"type": "string"},
            "ref": {"type": "integer"}}}}}, ["steps"]),
    _fn("fetch", "Read a same-site URL (e.g. a link's href, a document, a later results page) without leaving the "
        "current page. Faster than goto when you only need to read; returns text without refs; files and ZIPs are "
        "opened.", {"url": {"type": "string"}, **ALL_PAGES}, ["url"]),
    _fn("save_evidence", "Keep a page as evidence for the bid, word for word (a message, a document, a requirements "
        "page, a Q&A page, a material record). Give its URL (a link target or results page) or leave it empty for the "
        "current page. The analyst reads exactly what you keep, so keep every page that holds facts the rules need, "
        "and nothing unrelated. A page you have read already is kept without being shown again. Keep pages as soon "
        "as you know you need them, several in one turn, and in the turn you are done, call finish right after them.",
        {"url": {"type": "string"}, "label": {"type": "string",
                                              "description": "what the page is, e.g. 'approval message in archive'"},
         **ALL_PAGES}, ["label"]),
    _fn("note", "Save facts you have verified, so you keep them when old page reads are shortened. Be exact: "
        "copy ids, numbers, dates and wording.", {"text": {"type": "string"}}, ["text"]),
]


# One finish tool for every agent, its result schema in the mission: the provider caches a prompt prefix only for
# the same tool list, so with the same system message and tools every agent's calls share the first ~5,000 tokens.
FINISH = _fn("finish", "Return your findings when the mission is done (or when told time is up: your best findings). "
             "result is a JSON object with the fields the mission's schema names. Tools of one turn run in order, so call "
             "finish in the same turn as your last save_evidence calls.",
             {"result": {"type": "object", "description": "the findings, as the mission's schema asks"}}, ["result"])

HTTP_STATUS = re.compile(r"Fetched \S+ \(HTTP (\d+)\)")
FINISH_NOW = "Time is almost up: call finish now with your best findings."
KEPT_PREFIX = "Kept as evidence #"
PINNED = "[stays in full] "  # a tool result the model needs until the end (the bid to enter) is never shortened
SHORTENED = "\n[older page read shortened: what you noted is kept; read it again if you need a value you did not note]"
# a kept page reaches the analyst in full: reopening it to copy values only costs steps (one agent fetched the same
# six Q&A pages 35 times)
SHORTENED_KEPT = ("\n[older page read shortened; the page is kept word for word and the analyst reads it in full, so "
                  "don't open it again just to copy its values]")
# Tools whose result is the tab's page after them: of several in one turn, only the last one's result carries the page
# (the earlier pages are gone by the time the model reads them), unless a read reports something code or the browser
# did (a download, a dialog).
PAGE_ACTIONS = {"read", "goto", "click", "fill", "select", "check", "press", "back", "form"}
QUIET_READ = re.compile(r"(Form steps: [^\n]*\n\n)?URL: [^\n]*\nTitle: [^\n]*\n\n")


async def page_status(tab) -> int:
    """HTTP status of the page the tab shows; 0 if the browser doesn't tell."""
    try:
        return int(await tab.page.evaluate("performance.getEntriesByType('navigation')[0]?.responseStatus || 0"))
    except Exception:  # noqa: BLE001
        return 0


async def investigate(tab, system: str, mission: str, finish_schema: dict, deadline: float, tag: str,
                      extra_tools: list | None = None, handlers: dict | None = None, max_steps: int = 60,
                      check=None, warn_at: float = 60, warning: str = FINISH_NOW, news: list | None = None) -> dict:
    """Let the model work the tab until it calls finish(result) or the deadline passes.

    check(result, evidence) -> (result, problem): runs on finish, its model calls bounded by CHECK_TIMEOUT and the
    deadline; a problem sends the model back to work, a check that fails or runs out of time lets the result through.
    `warning` goes to the model `warn_at` seconds before the deadline; messages appended to `news` reach it before its
    next step. A finish forced by the deadline or the step
    limit, or sent after the warning, is marked `forced`: whatever it says, the agent did not finish its mission."""
    tools = BROWSER_TOOLS + [FINISH] + (extra_tools or [])  # the same for every agent but submit's own extra tools
    try:  # like every tool, the first read never outlasts TOOL_TIMEOUT: a page that never returns can't eat the stage
        page = await asyncio.wait_for(tab.read(), max(1.0, min(TOOL_TIMEOUT, deadline - time.time())))
    except Exception as error:  # noqa: BLE001
        url = (getattr(tab, "site", None) or {}).get("url")
        page = f"Error: the page did not load ({type(error).__name__}). " + \
            (f"Open {url} to start." if url else "Read it again.")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": mission + "\n\nfinish takes `result`, a JSON object of this schema:\n" +
                 json.dumps(finish_schema, ensure_ascii=False) + "\n\nThe page now:\n" + page}]
    steps: list[list[dict]] = []
    said: list[dict] = []  # the model's message of each step, beside its tool results in `steps`
    trimmed = 0  # steps before this index are shortened already
    evidence: list[str] = []
    if (stage := KEPT.get()) is not None:
        stage.append(evidence)

    kept: dict[str, int] = {}  # page text -> evidence number, so a page kept twice reaches the analyst once
    shown: set[str] = set()  # pages the model has read (paging.body): keeping one again needn't show it again
    # address -> (evidence number, paging.body): searches spent their last steps fetching kept pages again to re-check
    # values (run_0a26a180075ecc2c: 14 times in one ERP search, which then hit its step limit)
    kept_at: dict[str, tuple[int, str]] = {}

    def address(url: str) -> str:
        page = getattr(tab, "page", None)
        return urljoin(getattr(page, "url", "") or "", url or "")

    async def load(url: str) -> tuple[str, int]:
        """A page to keep and its HTTP status; a URL that answers with an error page is retried a few times."""
        for attempt in range(3):
            if url:
                text = await tab.fetch(url)
                match = HTTP_STATUS.match(text)
                status = int(match.group(1)) if match else 0
            else:
                text, status = await tab.read(), await page_status(tab)
            if status < 400 or not url or attempt == 2:
                break
            await asyncio.sleep(2 + 2 * attempt)
        return text, status

    def store(text: str, status: int, label: str, where: str, url: str | None = None) -> str:
        """An error page is never evidence: the model is told it was not kept."""
        if status >= 400:
            log(tag, f"evidence not kept: HTTP {status} {where}")
            return (f"Not kept: the page answered HTTP {status} (an error page, usually transient). Open it again and "
                    f"keep it once it shows its content.\n{text[:1500]}")
        if text in kept:
            return f"Already kept as evidence #{kept[text]} (same content); not kept again."
        evidence.append(f"### {label}\n{text}")
        kept[text] = len(evidence)
        if url is not None:
            kept_at.setdefault(address(url), (len(evidence), paging.body(text)))
        if paging.body(text) in shown:
            return f"{KEPT_PREFIX}{len(evidence)}: {where}, the page as you read it before, kept word for word."
        shown.add(paging.body(text))
        return f"{KEPT_PREFIX}{len(evidence)}.\n{text}"

    async def keep(args):
        url, label = (args.get("url") or "").strip(), args.get("label", "")
        text, status = await load(url)
        output = store(text, status, label, url or "the current page", url)
        if not args.get("all_pages") or status >= 400:
            return output
        where, statuses = urljoin(tab.page.url, url), {}

        async def fetch(page_url: str) -> str:
            page, statuses[page_url] = await load(page_url)
            return page
        pages, note = await paging.rest(fetch, where, text)
        return "\n\n".join([output] + [store(page, statuses.get(u, 0), f"{label} (further page)", u, u)
                                        for u, page in pages] + [note])

    async def whole_list(name: str, args: dict) -> str:
        """read or fetch with all_pages: the page and every further page of its list, in one result."""
        if name == "read":
            url, first = tab.page.url, await tab.read()
        else:
            url = urljoin(tab.page.url, args.get("url") or "")
            first = await tab.fetch(url)
        pages, note = await paging.rest(tab.fetch, url, first)
        shown.update(paging.body(page) for page in [first] + [page for _, page in pages])
        return "\n\n".join([first] + [page for _, page in pages] + [note])
    warned = refused = False
    for step in range(max_steps):
        left = deadline - time.time()
        if left < warn_at and not warned:
            messages.append({"role": "user", "content": warning})
            warned = True
        if left < 0:
            break
        while news:
            messages.append({"role": "user", "content": news.pop(0)})
        try:
            with limits(deadline):  # a step never eats the grace the forced finish below needs
                reply = await chat(messages, tools, **({"reasoning_effort": STEP_EFFORT} if STEP_EFFORT else {}))
        except Exception as error:  # noqa: BLE001  out of time or the model keeps failing: finish with what is kept
            log(tag, f"step failed: {type(error).__name__}: {str(error)[:200]}")
            break
        message = reply.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if message.content:
            log(tag, message.content.strip()[:300])
        if not message.tool_calls:
            messages.append({"role": "user", "content": "Use the tools. Call finish when the mission is done."})
            continue
        results: list[dict] = []
        steps.append(results)
        said.append(messages[-1])
        names = [call.function.name for call in message.tool_calls]
        last_action = max((i for i, name in enumerate(names) if name in PAGE_ACTIONS), default=-1)
        for i, call in enumerate(message.tool_calls):
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            log(tag, f"{step}: {name} {json.dumps(args, ensure_ascii=False)[:300]}")
            if name == "finish":
                result = args["result"] if "result" in args else args  # Qwen sometimes drops the wrapper
                if isinstance(result, str):
                    text, result = result, parse_object(result)
                    if result is None and refused and not check:  # asked once: the kept pages are what counts
                        log(tag, "finish taken as text: result is still not a JSON object")
                        result = {"summary": text[:3000]}
                    if result is None and deadline - time.time() > 30:
                        refused = True
                        log(tag, "finish refused: result is not a JSON object")
                        messages.append({"role": "tool", "tool_call_id": call.id, "content":
                                         "Not done: result must be a JSON object with the asked fields, not a string. "
                                         "Call finish again with an object."})
                        continue
                result = result or {}
                if check and deadline - time.time() > 45:
                    try:
                        with limits(deadline, CHECK_TIMEOUT):
                            result, problem = await check(result, evidence)
                    except Exception as error:  # noqa: BLE001  out of time or no JSON: keep the finding unchecked
                        log(tag, f"check skipped: {type(error).__name__}: {str(error)[:200]}")
                        problem = ""
                    if problem:
                        log(tag, f"finish refused: {problem}")
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": problem})
                        continue
                if warned:  # told to stop: "best findings", not a finished mission (an ERP agent answered no_match
                    log(tag, "finish after the time warning: marked forced")  # for a search it never completed)
                    return {**result, "evidence": evidence, "forced": True}
                return {**result, "evidence": evidence}
            # a tool never outlasts the deadline, so the forced finish below still returns what was kept
            handler = handlers.get(name) if handlers else None
            listed = bool(args.get("all_pages")) and name in ("read", "fetch", "save_evidence")
            reopened = kept_at.get(address(args["url"])) if name == "fetch" and args.get("url") else None
            limit = max(1.0, deadline - time.time() if handler else
                        min(TOOL_TIMEOUT * (2 if listed else 1), deadline - time.time()))
            try:
                if name == "note":
                    output = "Saved."
                elif name == "save_evidence":
                    output = await asyncio.wait_for(keep(args), limit)
                elif handler:
                    output = await asyncio.wait_for(handler(args), limit)
                elif listed:
                    output = await asyncio.wait_for(whole_list(name, args), limit)
                elif name == "read":
                    output = await asyncio.wait_for(tab.read(int(args.get("offset") or 0)), limit)
                else:
                    output = await asyncio.wait_for(tab.act(name, args), limit)
            except Exception as error:  # noqa: BLE001  the model sees the error and decides what to do
                output = f"Error: {type(error).__name__}: {str(error)[:500]}"
                try:
                    output += "\n\n" + await asyncio.wait_for(tab.read(), 15)
                except Exception:  # noqa: BLE001
                    pass
            quiet = QUIET_READ.match(output) if name in PAGE_ACTIONS and i < last_action else None
            if quiet:  # a later action of this turn shows the page
                output = ((quiet.group(1) or f"Done: {name}.").rstrip() +
                          "\n(The page after this turn's actions is in the result of its last one.)")
            elif (name in PAGE_ACTIONS or name == "fetch") and not listed and not output.startswith("Error"):
                shown.add(paging.body(output))
            if reopened and not listed and paging.body(output) == reopened[1]:  # same address, same content
                output += (f"\n[Unchanged since you kept it as evidence #{reopened[0]}: the analyst reads it word for "
                           "word, so you need not open it again to copy its values.]")
            entry = {"role": "tool", "tool_call_id": call.id, "content": output}
            messages.append(entry)
            results.append(entry)
        stale = [entry for results in steps[trimmed:-KEEP_STEPS] for entry in results]
        if len(steps) - KEEP_STEPS - trimmed >= TRIM_EVERY or sum(len(e["content"]) for e in stale) >= TRIM_CHARS:
            for old in stale:
                if len(old["content"]) > 400 and not old["content"].startswith(PINNED):
                    old["content"] = old["content"][:300] + (SHORTENED_KEPT if old["content"].startswith(KEPT_PREFIX)
                                                             else SHORTENED)
            for old in said[trimmed:-KEEP_STEPS]:
                for key in REASONING:
                    old.pop(key, None)
            trimmed = len(steps) - KEEP_STEPS
    messages.append({"role": "user", "content": "Stop now and call finish with your best findings."})
    log(tag, "finish forced (deadline or step limit)")
    try:
        reply = await chat(messages, tools, tool_choice={"type": "function", "function": {"name": "finish"}})
    except Exception as error:  # noqa: BLE001  out of time: what was kept still counts
        log(tag, f"forced finish failed: {type(error).__name__}")
        return {"evidence": evidence, "forced": True}
    for call in reply.choices[0].message.tool_calls or []:
        result = (parse_object(call.function.arguments or "{}") or {}).get("result")
        result = parse_object(result) if isinstance(result, str) else result
        return {**(result if isinstance(result, dict) else {}), "evidence": evidence, "forced": True}
    return {"evidence": evidence, "forced": True}
