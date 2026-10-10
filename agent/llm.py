"""The model loop: a model works one website through browser tools until it calls `finish` with its findings."""
import asyncio
import json
import os
import time

from openai import AsyncOpenAI

MODEL = os.environ.get("AGENT_MODEL", "qwen3.8-flash-next")
KEEP_STEPS = 4  # tool results of the latest steps stay in full; older page reads shrink so the context stays small

_client = None
T0 = time.time()


def log(tag: str, text: str):
    print(f"[{tag} {time.time() - T0:4.0f}s] {text}", flush=True)


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=os.environ["QWEN_BASE_URL"], api_key=os.environ["QWEN_API_KEY"], timeout=360)
    return _client


async def chat(messages: list, tools: list | None = None, **kwargs):
    for attempt in range(6):
        try:
            return await client().chat.completions.create(model=MODEL, messages=messages, tools=tools, **kwargs)
        except Exception as error:  # noqa: BLE001  the hosted model may hiccup: retry like any provider
            if attempt == 5:
                raise
            print(f"[llm] retry after {type(error).__name__}: {str(error)[:200]}", flush=True)
            await asyncio.sleep(2 + 3 * attempt)


def parse_object(text: str) -> dict | None:
    """An object the model sent as a string; raw line breaks inside its strings are tolerated."""
    try:
        value = json.loads(text[text.find("{"):text.rfind("}") + 1], strict=False)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def ask_json(system: str, user: str) -> dict:
    """One reasoning call that must answer with a JSON object."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for _ in range(3):
        reply = await chat(messages, response_format={"type": "json_object"})
        text = reply.choices[0].message.content or ""
        try:
            return json.loads(text[text.find("{"):text.rfind("}") + 1])
        except ValueError:
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
    _fn("press", "Press a key on the focused element, e.g. Enter, Escape, F4, Tab.", {"key": {"type": "string"}},
        ["key"]),
    _fn("back", "Go back in the browser history."),
    _fn("form", "Work through a form in one go: steps run in order, each waits for the page to settle. A step is "
        "{\"field\": \"<label>\", \"value\": \"...\"} (fills an input, picks a select option by its text, or "
        "ticks a checkbox with true/false) or {\"click\": \"<button label>\"}. Labels are the visible labels, so "
        "steps survive page reloads (e.g. pick a value, click 'apply selection', pick the next value). Stops at the "
        "first failing step and says why.",
        {"steps": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "value": {"type": "string"}, "click": {"type": "string"}}}}}, ["steps"]),
    _fn("fetch", "Read a same-site URL (e.g. a link's href, a document, a later results page) without leaving the "
        "current page. Faster than goto when you only need to read; returns text without refs; files and ZIPs are "
        "opened.", {"url": {"type": "string"}}, ["url"]),
    _fn("save_evidence", "Keep a page as evidence for the bid, word for word (a message, a document, a requirements "
        "page, a Q&A page, a material record). Give its URL (a link target or results page) or leave it empty for the "
        "current page. The analyst reads exactly what you keep, so keep every page that holds facts the rules need, "
        "and nothing unrelated.", {"url": {"type": "string"}, "label": {"type": "string",
                                   "description": "what the page is, e.g. 'Rabattfreigabe 24.01. inbox'"}},
        ["label"]),
    _fn("note", "Save facts you have verified, so you keep them when old page reads are shortened. Be exact: "
        "copy ids, numbers, dates and wording.", {"text": {"type": "string"}}, ["text"]),
]


async def investigate(tab, system: str, mission: str, finish_schema: dict, deadline: float, tag: str,
                      extra_tools: list | None = None, handlers: dict | None = None, max_steps: int = 60,
                      check=None) -> dict:
    """check(result, evidence) -> (result, problem): runs on finish; a problem sends the model back to work."""
    """Let the model work the tab until it calls finish(result) or the deadline passes."""
    tools = BROWSER_TOOLS + (extra_tools or []) + [_fn(
        "finish", "Return your findings when the mission is done (or when told time is up: your best findings).",
        {"result": finish_schema}, ["result"])]
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": mission + "\n\nThe page now:\n" + await tab.read()}]
    steps: list[list[dict]] = []
    evidence: list[str] = []

    async def keep(args):
        url = (args.get("url") or "").strip()
        text = await tab.fetch(url) if url else await tab.read()
        evidence.append(f"### {args.get('label', '')}\n{text}")
        return f"Kept as evidence #{len(evidence)}.\n{text}"
    warned = False
    for step in range(max_steps):
        left = deadline - time.time()
        if left < 60 and not warned:
            messages.append({"role": "user", "content": "Time is almost up: call finish now with your best findings."})
            warned = True
        if left < 0:
            break
        reply = await chat(messages, tools)
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
                result = args.get("result")
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
                    result, problem = await check(result, evidence)
                    if problem:
                        log(tag, f"finish refused: {problem}")
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": problem})
                        continue
                return {**result, "evidence": evidence}
            try:
                if name == "note":
                    output = "Saved."
                elif name == "save_evidence":
                    output = await keep(args)
                elif handlers and name in handlers:
                    output = await handlers[name](args)
                elif name == "read":
                    output = await tab.read(int(args.get("offset") or 0))
                else:
                    output = await tab.act(name, args)
            except Exception as error:  # noqa: BLE001  the model sees the error and decides what to do
                output = f"Error: {type(error).__name__}: {str(error)[:500]}"
                try:
                    output += "\n\n" + await tab.read()
                except Exception:  # noqa: BLE001
                    pass
            entry = {"role": "tool", "tool_call_id": call.id, "content": output}
            messages.append(entry)
            results.append(entry)
        for old in (entry for results in steps[:-KEEP_STEPS] for entry in results):
            if len(old["content"]) > 400:
                old["content"] = (old["content"][:300] + "\n[older page read shortened: what you noted is kept; "
                                  "read it again if you need a value you did not note]")
    messages.append({"role": "user", "content": "Stop now and call finish with your best findings."})
    reply = await chat(messages, tools, tool_choice={"type": "function", "function": {"name": "finish"}})
    for call in reply.choices[0].message.tool_calls or []:
        result = (parse_object(call.function.arguments or "{}") or {}).get("result")
        result = parse_object(result) if isinstance(result, str) else result
        return {**(result or {}), "evidence": evidence}
    return {"evidence": evidence}
