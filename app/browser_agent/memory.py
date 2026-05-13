"""
Memory module.

Structure:
    react_history  — list of {thought, action, observation} dicts (the ReACT trace)
    flags          — lightweight boolean state (login_done, terms_accepted, etc.)
"""

memory: dict = {
    "react_history": [],   # full ReACT trace fed back to LLM each step
    "flags": {},           # quick-check state flags
}


def clear_memory() -> None:
    memory["react_history"].clear()
    memory["flags"].clear()


def add_step(thought: str, action: dict, observation: str) -> None:
    memory["react_history"].append({
        "thought":     thought,
        "action":      action,
        "observation": observation,
    })


def set_flag(key: str, value: bool = True) -> None:
    memory["flags"][key] = value


def get_flag(key: str) -> bool:
    return bool(memory["flags"].get(key, False))