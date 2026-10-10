"""The model loop: a model works one website through browser tools until it calls `finish` with its findings."""
import asyncio
import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar

from openai import AsyncOpenAI

MODEL = os.environ.get("AGENT_MODEL", "qwen3.8-flash-next")
STEP_EFFORT = os.environ.get("STEP_EFFORT", "low")  # reasoning per browser step; latency is mostly thinking tokens
KEEP_STEPS = 4  # tool results of the latest steps stay in full; older page reads shrink so the context stays small
CALL_TIMEOUT = 180  # one model call; a slower one is retried while its deadline allows (steps took 20-90 s under load,
# a tender finish 132 s: a cut call starts over, so the cap sits above the slowest calls seen)
CHECK_TIMEOUT = 60  # one model call inside a finish check (ERP extract: 13-21 s); one hung call cost a position
TOOL_TIMEOUT = 60  # one browser tool; a fetch that hung 109 s held the tender agent to its cut, its kept pages lost

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
T0 = time.time()


def log(tag: str, text: str):
    print(f"[{tag} {time.time() - T0:4.0f}s] {text}", flush=True)


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # no retries inside the SDK: they would multiply the timeout behind chat's back
        _client = AsyncOpenAI(base_url=os.environ["QWEN_BASE_URL"], api_key=os.environ["QWEN_API_KEY"],
                              timeout=CALL_TIMEOUT, max_retries=0)
    return _client


async def chat(messages: list, tools: list | None = None, **kwargs):
    """One model reply, each attempt bounded by CAP and all of them by UNTIL; raises TimeoutError when time is up."""
    for attempt in range(6):
        left = UNTIL.get() - time.time() - 1
        if left < 3:
            raise TimeoutError("no time left for a model call")
        limit = min(CAP.get(), left)
        call = asyncio.ensure_future(client().chat.completions.create(model=MODEL, messages=messages, tools=tools,
                                                                      timeout=limit, **kwargs))
        call.add_done_callback(lambda c: c.cancelled() or c.exception())  # a dropped call's failure stays quiet
        try:
            # asyncio.wait, not wait_for: wait_for waits until the cancelled call has stopped, a cut never does
            await asyncio.wait({call}, timeout=limit)
            if not call.done():
                raise TimeoutError(f"model call over {limit:.0f} s")
            return call.result()
        except Exception as error:  # noqa: BLE001  the hosted model may hiccup: retry like any provider
            if attempt == 5:
                raise
            print(f"[llm] retry after {type(error).__name__}: {str(error)[:200]}", flush=True)
            await asyncio.sleep(min(2 + 3 * attempt, max(0.0, UNTIL.get() - time.time() - 5)))
        finally:
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
    times faster, while switching thinking off entirely made the model rewrite number formats."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    extra = {"reasoning_effort": effort} if effort else {}
    for _ in range(3):
        reply = await chat(messages, response_format={"type": "json_object"}, **extra)
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
BROWSER_TOOLS = [
    _fn("read", "Read the current page again (text with [n:control] refs). Use offset to continue a long page.",
        {"offset": {"type": "integer"}}),
    _fn("goto", "Open a URL (absolute, or relative to the current page).", {"url": {"type": "string"}}, ["url"]),
    _fn("click", "Click a link, button, summary, menu item or tab by its ref.", REF, ["ref"]),
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
        "opened.", {"url": {"type": "string"}}, ["url"]),
    _fn("save_evidence", "Keep a page as evidence for the bid, word for word (a message, a document, a requirements "
        "page, a Q&A page, a material record). Give its URL (a link target or results page) or leave it empty for the "
        "current page. The analyst reads exactly what you keep, so keep every page that holds facts the rules need, "
        "and nothing unrelated.", {"url": {"type": "string"}, "label": {"type": "string",
                                   "description": "what the page is, e.g. 'approval message in archive'"}},
        ["label"]),
    _fn("note", "Save facts you have verified, so you keep them when old page reads are shortened. Be exact: "
        "copy ids, numbers, dates and wording.", {"text": {"type": "string"}}, ["text"]),
]


HTTP_STATUS = re.compile(r"Fetched \S+ \(HTTP (\d+)\)")
FINISH_NOW = "Time is almost up: call finish now with your best findings."
KEPT_PREFIX = "Kept as evidence #"
SHORTENED = "\n[older page read shortened: what you noted is kept; read it again if you need a value you did not note]"
# a kept page reaches the analyst in full: reopening it to copy values only costs steps (one agent fetched the same
# six Q&A pages 35 times)
SHORTENED_KEPT = ("\n[older page read shortened; the page is kept word for word and the analyst reads it in full, so "
                  "don't open it again just to copy its values]")


async def page_status(tab) -> int:
    """HTTP status of the page the tab shows; 0 if the browser doesn't tell."""
    try:
        return int(await tab.page.evaluate("performance.getEntriesByType('navigation')[0]?.responseStatus || 0"))
    except Exception:  # noqa: BLE001
        return 0


async def investigate(tab, system: str, mission: str, finish_schema: dict, deadline: float, tag: str,
                      extra_tools: list | None = None, handlers: dict | None = None, max_steps: int = 60,
                      check=None, warn_at: float = 60, warning: str = FINISH_NOW) -> dict:
    """Let the model work the tab until it calls finish(result) or the deadline passes.

    check(result, evidence) -> (result, problem): runs on finish, its model calls bounded by CHECK_TIMEOUT and the
    deadline; a problem sends the model back to work, a check that fails or runs out of time lets the result through.
    `warning` goes to the model `warn_at` seconds before the deadline. A finish forced by the deadline or the step
    limit, or sent after the warning, is marked `forced`: whatever it says, the agent did not finish its mission."""
    tools = BROWSER_TOOLS + (extra_tools or []) + [_fn(
        "finish", "Return your findings when the mission is done (or when told time is up: your best findings).",
        {"result": finish_schema}, ["result"])]
    try:  # like every tool, the first read never outlasts TOOL_TIMEOUT: a page that never returns can't eat the stage
        page = await asyncio.wait_for(tab.read(), max(1.0, min(TOOL_TIMEOUT, deadline - time.time())))
    except Exception as error:  # noqa: BLE001
        url = (getattr(tab, "site", None) or {}).get("url")
        page = f"Error: the page did not load ({type(error).__name__}). " + \
            (f"Open {url} to start." if url else "Read it again.")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": mission + "\n\nThe page now:\n" + page}]
    steps: list[list[dict]] = []
    evidence: list[str] = []
    if (stage := KEPT.get()) is not None:
        stage.append(evidence)

    kept: dict[str, int] = {}  # page text -> evidence number, so a page kept twice reaches the analyst once

    async def keep(args):
        """An error page is never evidence: retry a URL a few times, else tell the model it was not kept."""
        url = (args.get("url") or "").strip()
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
        if status >= 400:
            log(tag, f"evidence not kept: HTTP {status} {url or tab.page.url}")
            return (f"Not kept: the page answered HTTP {status} (an error page, usually transient). Open it again and "
                    f"keep it once it shows its content.\n{text[:1500]}")
        if text in kept:
            return f"Already kept as evidence #{kept[text]} (same content); not kept again."
        evidence.append(f"### {args.get('label', '')}\n{text}")
        kept[text] = len(evidence)
        return f"{KEPT_PREFIX}{len(evidence)}.\n{text}"
    warned = False
    for step in range(max_steps):
        left = deadline - time.time()
        if left < warn_at and not warned:
            messages.append({"role": "user", "content": warning})
            warned = True
        if left < 0:
            break
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
        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            log(tag, f"{step}: {name} {json.dumps(args, ensure_ascii=False)[:300]}")
            if name == "finish":
                result = args["result"] if "result" in args else args  # Qwen sometimes drops the wrapper
                if isinstance(result, str):
                    result = parse_object(result)
                    if result is None and deadline - time.time() > 30:
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
            limit = max(1.0, deadline - time.time() if handler else min(TOOL_TIMEOUT, deadline - time.time()))
            try:
                if name == "note":
                    output = "Saved."
                elif name == "save_evidence":
                    output = await asyncio.wait_for(keep(args), limit)
                elif handler:
                    output = await asyncio.wait_for(handler(args), limit)
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
            entry = {"role": "tool", "tool_call_id": call.id, "content": output}
            messages.append(entry)
            results.append(entry)
        for old in (entry for results in steps[:-KEEP_STEPS] for entry in results):
            if len(old["content"]) > 400:
                old["content"] = old["content"][:300] + (SHORTENED_KEPT if old["content"].startswith(KEPT_PREFIX)
                                                         else SHORTENED)
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
