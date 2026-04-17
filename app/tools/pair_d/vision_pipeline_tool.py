"""
vision_pipeline_tool.py
═══════════════════════
Main entry point for the vision pipeline.
Connects orchestrator.py to the three vision tools.

Import in orchestrator as:
    from app.agents.vision_pipeline_tool import run_vision_pipeline

Input:
    video_path    : str  — path to local video file
    url           : str  — YouTube / Instagram URL (alternative to video_path)
    user_location : str  — location typed / pinned by user (optional)
    whatsapp_text : str  — forwarded WhatsApp context text (optional)

Output (orchestrator-compatible):
    {
        "issue_type":     str,   # e.g. "Waste Management"
        "transcript":     str,   # English transcript
        "state":          str,
        "district":       str,
        "location_label": str,   # "District, State"
    }
"""

# ── Three vision tools (to be implemented) ───────────────────────────────────
from app.tools.pair_d.context_extractor_tool  import extract_context   # Agent 0
from app.tools.pair_d.issue_detector_tool     import detect_issue      # Agent 1
from app.tools.pair_d.location_resolver_tool  import resolve_location  # Agent 2


# ─────────────────────────────────────────────────────────────────────────────

def run_vision_pipeline(
    video_path:    str = None,
    url:           str = None,
    user_location: str = '',
    whatsapp_text: str = '',
) -> dict:
    """
    Orchestrates the three-agent vision pipeline.

    Flow:
        Video / URL
            ↓
        Agent 0 — extract_context()
            builds: {frame_b64, transcript, transcript_lang,
                     social_caption, on_screen_text, ...}
            ↓               ↓
        Agent 1          Agent 2
        detect_issue()   resolve_location()
        {issue_type}     {state, district, location_label}
            ↓               ↓
            └──── merge ────┘
                    ↓
        orchestrator-compatible output
    """

    # ── Agent 0: build context object ────────────────────────────────────────
    context = extract_context(
        video_path    = video_path,
        url           = url,
        whatsapp_text = whatsapp_text,
        user_location = user_location,
    )

    if context.get('error') == 'no_video':
        return _empty_result("no_video")

    # ── Agents 1 & 2: run independently on the same context ──────────────────
    # (no interdependency — can be parallelised with ThreadPoolExecutor if needed)

    issue_result    = detect_issue(context)       # Agent 1
    location_result = resolve_location(           # Agent 2
        frame_b64      = context.get('frame_b64', ''),
        user_location  = user_location,
        social_caption = context.get('social_caption', ''),
        transcript     = context.get('transcript_en', ''),
    )

    # ── Assemble orchestrator-compatible output ───────────────────────────────
    state    = location_result.get('state', '')
    district = location_result.get('district', '')

    # Guard: Nominatim sometimes returns a PIN code as state
    if state.isdigit():
        state = user_location  # fall back to whatever user provided

    location_label = (
        f"{district}, {state}".strip(', ')
        if (district or state)
        else user_location
    )

    return {
        "issue_type":     issue_result.get('issue_type', 'Unknown'),
        "transcript":     context.get('transcript_en', ''),
        "state":          state,
        "district":       district,
        "location_label": location_label,
    }


def _empty_result(reason: str = '') -> dict:
    """Returns a safe empty result when pipeline cannot proceed."""
    print(f"[vision_pipeline_tool] Cannot produce result: {reason}")
    return {
        "issue_type":     "Unknown",
        "transcript":     "",
        "state":          "",
        "district":       "",
        "location_label": "",
    }