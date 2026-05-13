"""
planner_llm.py  —  ReACT brain using NVIDIA Nemotron via OpenAI-compat API.

ReACT loop:
    Thought  →  reason about current page + history
    Action   →  emit one JSON action
    (executor runs it, records Observation, loop repeats)
"""

import json
import re

from openai import OpenAI
from config import GOAL, NVIDIA_API_KEY, USERNAME, PASSWORD

# =====================================================
# CLIENT
# =====================================================

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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",
)

# =====================================================
# SYSTEM PROMPT
# =====================================================

SYSTEM_PROMPT = f"""You are a browser automation agent that follows the ReACT framework
(Reason + Act) to complete web tasks step-by-step.

GOAL:
{GOAL}

CREDENTIALS (use exactly as given):
  username : {USERNAME}
  password : {PASSWORD}

AVAILABLE ACTION TYPES — always emit exactly one per turn as valid JSON:

  Fill a text field  : {{"type": "fill",     "target": "<id>", "value": "<text>"}}
  Click element      : {{"type": "click",    "target": "<id>"}}
  Check a checkbox   : {{"type": "check",    "target": "<id>"}}
  Select dropdown    : {{"type": "select",   "target": "<id>", "option": "<visible option text>"}}
  Pause for captcha  : {{"type": "captcha",  "target": "<id>"}}
  Wait / retry       : {{"type": "wait",     "reason": "<why>"}}
  Mark task done     : {{"type": "done",     "reason": "<outcome>"}}

STRICT OUTPUT FORMAT — never deviate:

Thought: <single paragraph reasoning about what has been done and what to do next>
Action: <one JSON object from the list above, nothing else on this line>

RULES:

ERROR DETECTION — check these before deciding any action:
- If the previous step's observation contains "WARNING PAGE ERROR", that action FAILED.
  Reset its flags and retry from that step.
- Only elements with type "alert" AND severity "error" indicate a failure requiring retry.
  Elements with severity "info" are advisory banners (e.g. pension notices, tips) — they
  are NON-BLOCKING. Ignore them completely and proceed with the task.
- "Please enter valid security code" or any captcha/security error means the captcha was
  wrong. Emit {{"type": "captcha", "target": "textbox_2"}} again for the user to re-enter.
  Do NOT proceed to click Login until a fresh captcha is filled in.

TERMS & CONDITIONS PAGE (url = '/NewGrievance') — FIXED RULES, NO DELIBERATION:
1. If checkbox is NOT checked → emit {{"type": "check", "target": "checkbox_0"}}
2. If checkbox IS checked     → emit {{"type": "click", "target": "button_0"}}
   Pension advisory banner is ALWAYS present here — non-blocking, ignore it. Proceed.

MINISTRY SELECTION PAGE (url = '/NewGrievance/Organisation') — FIXED RULES:
*** This page lists ministries as plain LINKS, there is NO dropdown on this page ***
- Look for a link with text containing "Housing and Urban Affairs" and click it.
- Do NOT try to use select/combobox actions on this page.
- Correct action: {{"type": "click", "target": "<link_id of Housing and Urban Affairs>"}}

CATEGORY PAGE (url changes after clicking Housing and Urban Affairs):
- The dropdowns here are select2 comboboxes. Use {{"type": "select"}} which handles them.
- If a select returns an error, retry ONCE with the same action (dropdown may not be open yet).
- After 2 failed retries on the same dropdown, emit {{"type": "done", "reason": "select2 stuck"}}.

LOGIN CONFIRMATION:
- Navigation links like "Lodge Public Grievance" are ALWAYS in the page header, even before
  login. Their presence does NOT mean the user is logged in.
- Login is confirmed ONLY when page_context url no longer contains '/Signin', OR when a
  dashboard/welcome message appears. Always check the page_context url field explicitly.

GENERAL:
- Use element IDs exactly as shown in the current page elements list.
- NEVER guess captcha values — always emit {{"type": "captcha"}}.
- Only emit "done" when the grievance has been successfully submitted.
- Do not repeat actions that already succeeded per the history.
- If stuck on the same page for 3+ steps with no progress, emit
  {{"type": "done", "reason": "stuck — manual intervention needed"}}.
"""

# =====================================================
# LLM CALL  (streaming with thinking tokens)
# =====================================================

def call_llm(messages: list[dict]) -> tuple[str, str]:
    """
    Returns (reasoning_text, response_text).
    Streams both to stdout in real-time.
    """
    reasoning_buf = ""
    content_buf   = ""

    completion = client.chat.completions.create(
        model="nvidia/nvidia-nemotron-nano-9b-v2",
        messages=messages,
        temperature=0.6,
        top_p=0.95,
        max_tokens=2048,
        frequency_penalty=0,
        presence_penalty=0,
        stream=True,
        extra_body={
            "min_thinking_tokens": 512,
            "max_thinking_tokens": 8192,
        },
    )

    print("\n[THINKING]", flush=True)
    in_thinking = True

    for chunk in completion:
        delta     = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)

        if reasoning:
            reasoning_buf += reasoning
            print(reasoning, end="", flush=True)

        if delta.content:
            if in_thinking:
                print("\n\n[RESPONSE]", flush=True)
                in_thinking = False
            content_buf += delta.content
            print(delta.content, end="", flush=True)

    print()  # final newline
    return reasoning_buf, content_buf


# =====================================================
# ACTION PARSER
# =====================================================

def parse_response(text: str) -> tuple[str, dict | None]:
    """
    Extract (thought, action_dict) from LLM output.
    Action must be on a line starting with 'Action:'.
    """
    thought = ""
    action  = None

    # Extract Thought
    thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|$)", text, re.DOTALL | re.IGNORECASE)
    if thought_match:
        thought = thought_match.group(1).strip()

    # Extract Action JSON
    action_match = re.search(r"Action:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
    if action_match:
        try:
            action = json.loads(action_match.group(1))
        except json.JSONDecodeError:
            # Fallback: find any JSON with a "type" key
            fallback = re.search(r'\{"type"\s*:.*?\}', text, re.DOTALL)
            if fallback:
                try:
                    action = json.loads(fallback.group(0))
                except json.JSONDecodeError:
                    pass

    # Emergency fallback: LLM ran out of tokens mid-thought and never
    # reached the Action: line. Try to infer a safe default from the thought.
    if action is None and thought:
        t = thought.lower()
        if "submit" in t and "button" in t:
            action = {"type": "click", "target": "button_0"}
        elif "check" in t and "checkbox" in t:
            action = {"type": "check", "target": "checkbox_0"}

    return thought, action


# =====================================================
# FORMAT HELPERS
# =====================================================

def _fmt_elements(elements: list[dict]) -> str:
    lines = []
    for e in elements:
        t = e["type"]
        if t == "button":
            lines.append(f'  [{e["id"]}] BUTTON    text="{e["text"]}"')
        elif t == "textbox":
            lines.append(
                f'  [{e["id"]}] INPUT     placeholder="{e["placeholder"]}"'
                f'  type={e["input_type"]}  name={e["name"]}'
            )
        elif t == "checkbox":
            lines.append(
                f'  [{e["id"]}] CHECKBOX  label="{e["label"]}"'
                f'  checked={e["checked"]}'
            )
        elif t == "select":
            lines.append(f'  [{e["id"]}] SELECT    label="{e["label"]}"')
        elif t == "link":
            lines.append(f'  [{e["id"]}] LINK      text="{e["text"]}"')
        elif t == "alert":
            sev = e.get("severity", "error")
            if sev == "error":
                # Blocking — insert at top so LLM sees it first
                lines.insert(0, f'  *** ERROR ALERT: "{e["text"]}" ***')
            else:
                # Informational banner — show but deprioritised
                lines.append(f'  [info-banner] ADVISORY (non-blocking, ignore): "{e["text"]}"')
        elif t == "page_context":
            lines.insert(0, f'  [page_context] URL="{e["url"]}"  TITLE="{e["title"]}"')
        elif t == "page_text":
            lines.append(f'  [page_text] PAGE TEXT: {" | ".join(e["content"][:12])}')
    return "\n".join(lines) if lines else "  (no elements found)"


def _fmt_history(history: list[dict]) -> str:
    if not history:
        return "  (no steps yet)"
    lines = []
    for i, step in enumerate(history, 1):
        lines.append(f"  Step {i}:")
        lines.append(f"    Thought     : {step.get('thought', '')[:200]}")
        lines.append(f"    Action      : {json.dumps(step.get('action', {}))}")
        lines.append(f"    Observation : {step.get('observation', '')}")
    return "\n".join(lines)


# =====================================================
# PUBLIC INTERFACE  (called by main.py)
# =====================================================

def decide_next_action(elements: list[dict], memory: dict) -> tuple[str, dict | None]:
    """
    Returns (thought, action_dict).
    action_dict is None if the LLM response could not be parsed.
    """
    user_content = (
        "HISTORY OF COMPLETED STEPS:\n"
        f"{_fmt_history(memory.get('react_history', []))}\n\n"
        "CURRENT PAGE ELEMENTS:\n"
        f"{_fmt_elements(elements)}\n\n"
        "What is the single next action to take?"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    _, response_text = call_llm(messages)

    thought, action = parse_response(response_text)

    if action is None:
        print("[PLANNER] WARNING: could not parse a valid action from LLM response.")

    if action is None and thought:
        t = thought.lower()
        if "submit" in t and "button" in t:
            action = {"type": "click", "target": "button_0"}
        elif "check" in t and "checkbox" in t:
            action = {"type": "check", "target": "checkbox_0"}

    return thought, action