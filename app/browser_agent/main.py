"""
main.py  —  ReACT agent loop for PGPortal complaint submission.

Loop:
    1. Observe  — extract interactive elements from current page
    2. Think    — LLM reasons and emits one action (Thought + Action JSON)
    3. Act      — executor runs the action in Playwright
    4. Record   — store (thought, action, observation) in memory
    5. Repeat   until done / max steps reached
"""

from browser_tools import start_browser
from observer    import extract_elements
from planner_llm     import decide_next_action      # delegates to planner_llm
from executor    import execute_action
from memory      import memory, clear_memory, add_step
from config      import GOAL

# =====================================================
# SETUP
# =====================================================

clear_memory()

playwright, browser, context, page = start_browser()

page.goto("https://pgportal.gov.in/Signin")
page.wait_for_load_state("networkidle")

print("\n" + "=" * 54)
print("  REACT AGENT STARTED")
print("=" * 54)
print("\nGOAL:")
print(GOAL)

# =====================================================
# REACT LOOP
# =====================================================

MAX_STEPS = 25

for step in range(MAX_STEPS):

    print(f"\n{'=' * 20} STEP {step + 1} {'=' * 20}\n")

    # -------------------------------------------------
    # OBSERVE
    # -------------------------------------------------

    elements = extract_elements(page)

    print(f"[OBSERVE] {len(elements)} elements on page\n")
    for e in elements:
        print(" ", e)

    # -------------------------------------------------
    # THINK  (LLM returns thought + action)
    # -------------------------------------------------

    thought, action = decide_next_action(elements, memory)

    print(f"\n[THOUGHT]\n{thought}\n")
    print(f"[ACTION]\n{action}\n")

    # -------------------------------------------------
    # STOP if LLM could not produce a valid action
    # -------------------------------------------------

    if action is None:
        print("[MAIN] No valid action returned — stopping.")
        break

    # -------------------------------------------------
    # STOP on 'done'
    # -------------------------------------------------

    if action.get("type") == "done":
        observation = f"Task marked done. Reason: {action.get('reason', '')}"
        add_step(thought, action, observation)
        print(f"\n[DONE] {observation}")
        break

    # -------------------------------------------------
    # ACT
    # -------------------------------------------------

    observation = execute_action(page, action, memory)

    print(f"\n[OBSERVATION] {observation}")

    # -------------------------------------------------
    # RECORD  (thought + action + observation → history)
    # -------------------------------------------------

    add_step(thought, action, observation)

    # -------------------------------------------------
    # WAIT FOR PAGE STABILISATION
    # -------------------------------------------------

    page.wait_for_timeout(1500)

else:
    print(f"\n[MAIN] Reached MAX_STEPS ({MAX_STEPS}) without completion.")

# =====================================================
# FINAL REPORT
# =====================================================

print("\n" + "=" * 54)
print("  AGENT FINISHED")
print("=" * 54)

print("\nFINAL REACT TRACE:\n")
for i, step in enumerate(memory["react_history"], 1):
    print(f"  Step {i}:")
    print(f"    Thought     : {step['thought'][:120]}...")
    print(f"    Action      : {step['action']}")
    print(f"    Observation : {step['observation']}")

print("\nFINAL FLAGS:\n", memory["flags"])

# =====================================================
# KEEP BROWSER OPEN FOR INSPECTION
# =====================================================

input("\nPress ENTER to close the browser...")

browser.close()
playwright.stop()