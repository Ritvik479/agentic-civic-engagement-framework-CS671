"""
app/tools/pair_d/vision_tool_wrapped.py
════════════════════════════════════════
smolagents @tool wrapper around the existing pair_d vision pipeline.

This file must NOT be modified alongside vision_pipeline_tool.py —
it is a pure adapter layer. All vision logic lives in vision_pipeline_tool.py.
"""

import json
from smolagents import tool

from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
from app.schemas.issue_schema import (
    ExtractedIssue,
    IssueCategory,
    MediaMetadata
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Maps the canonical string returned by run_vision_pipeline → IssueCategory enum
_ISSUE_TYPE_TO_CATEGORY: dict[str, IssueCategory] = {
    "Waste Management":      IssueCategory.SOLID_WASTE,
    "Air Pollution":         IssueCategory.AIR_POLLUTION,
    "Water Pollution":       IssueCategory.WATER_POLLUTION,
    "Road Damage":           IssueCategory.ROAD_DAMAGE,
    "Animal Control":        IssueCategory.UNKNOWN,        # no direct enum value
    "Public Sanitation":     IssueCategory.SEWAGE_OVERFLOW,
    "Infrastructure Damage": IssueCategory.ROAD_DAMAGE,
    "Unknown":               IssueCategory.UNKNOWN,
}

def _map_category(issue_type: str) -> IssueCategory:
    """Return the IssueCategory enum member for a pipeline issue_type string."""
    return _ISSUE_TYPE_TO_CATEGORY.get(issue_type, IssueCategory.UNKNOWN)


def _map_severity(confidence: float) -> int:
    """
    Derive an integer severity (1-5) from the pipeline confidence score.
    ExtractedIssue requires an int between 1 and 5.
    """
    if confidence >= 0.85:
        return 5  # Critical / Emergency
    if confidence >= 0.65:
        return 4  # High
    if confidence >= 0.40:
        return 3  # Medium
    return 2      # Low


# ---------------------------------------------------------------------------
# smolagents tool
# ---------------------------------------------------------------------------

@tool
def vision_tool(media_metadata_json: str) -> str:
    """
    Runs the pair_d three-agent vision pipeline on a civic media asset and
    returns a structured representation of the detected issue.

    The pipeline internally executes three agents in sequence:
      - Agent 0 (context_extractor): downloads the media, extracts a
        representative frame, generates an English transcript, and captures
        any on-screen text.
      - Agent 1 (issue_detector): classifies the civic issue using YOLO +
        Groq Vision + multimodal LLM refinement.
      - Agent 2 (location_resolver): resolves the geographic location from
        the frame, caption, transcript, and user-supplied geotag.

    The smolagents CodeAgent should call this tool once per media asset at
    the start of the pipeline, before routing or complaint-drafting tools.

    Args:
        media_metadata_json: JSON string of a MediaMetadata object,
            produced by MediaMetadata.model_dump_json().
            Required fields consumed by this tool:
              - media_url  (str)  : URL / local path to the video or image.
              - geotag     (str)  : Raw location string from the social post;
                                   may be None.
              - caption    (str)  : Post caption used as supplementary context;
                                   may be None.
              - run_id     (UUID) : Propagated unchanged into the output so all
                                   downstream tools can correlate results.

    Returns:
        On success — JSON string of an ExtractedIssue object.
            Parse with ExtractedIssue.model_validate_json().
            Key output fields:
              - category         : IssueCategory enum value
              - confidence_score : float 0.0–1.0 (below 0.5 triggers review flag)
              - description      : factual issue description from the pipeline
              - location_raw     : location label assembled by the pipeline
              - location_resolved: "district, state" string when both are known
              - detected_objects : list of objects identified visually (may be [])
              - vision_model_id  : always "pair_d-vision-v1"
              - run_id           : echoed from input MediaMetadata

        On failure — JSON string: {"error": "<message>", "run_id": "<uuid>"}
            The caller should inspect for the "error" key before proceeding.
    """
    # ── 0. Parse the incoming JSON ────────────────────────────────────────────
    # Kept outside the main try/except so we can still return a run_id on
    # later failures.  If parsing itself fails we use "unknown" as the run_id.
    try:
        media = MediaMetadata.model_validate_json(media_metadata_json)
    except Exception as parse_err:
        return json.dumps({"error": f"Invalid MediaMetadata JSON: {parse_err}",
                           "run_id": "unknown"})

    # ── 1. Call the existing pipeline ────────────────────────────────────────
    try:
        result: dict = run_vision_pipeline(
            video_path    = str(media.media_url),   # used as local path or URL
            url           = str(media.media_url),   # same value; both params accepted
            user_location = media.geotag or "",
            whatsapp_text = media.caption or "",
        )

        # ── 2. Map issue_type → IssueCategory enum ───────────────────────────
        raw_issue_type = result.get("issue_type", "Unknown")
        category       = _map_category(raw_issue_type)

        # ── 3. Build location_resolved from state + district ─────────────────
        state    = result.get("state", "").strip()
        district = result.get("district", "").strip()

        if district and state:
            location_resolved = f"{district}, {state}"
        elif state:
            location_resolved = state
        elif district:
            location_resolved = district
        else:
            location_resolved = None

        # ── 4. Derive severity from confidence ───────────────────────────────
        confidence = float(result.get("confidence", 0.0))
        severity   = _map_severity(confidence)

        # ── 5. Assemble ExtractedIssue ───────────────────────────────────────
        issue = ExtractedIssue(
            run_id            = media.run_id,
            vision_model_id   = "pair_d-vision-v1",
            category          = category,
            severity          = severity,
            confidence_score  = confidence,
            description       = result.get("transcript") or raw_issue_type,
            location_raw      = result.get("location_label") or None,
            location_resolved = location_resolved,
            detected_objects  = result.get("detected_objects", []),
        )

        # ── 6. Return serialised JSON ─────────────────────────────────────────
        return issue.model_dump_json()

    except Exception as e:
        return json.dumps({
            "error":  str(e),
            "run_id": str(media.run_id),
        })