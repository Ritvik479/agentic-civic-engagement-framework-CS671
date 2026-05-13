"""
app/tools/pair_d/vision_tool_wrapped.py
"""

from __future__ import annotations
import json
import logging
from smolagents import tool
from app.schemas.issue_schema import MediaMetadata, ExtractedIssue, IssueCategory
from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline

logger = logging.getLogger(__name__)

@tool
def vision_tool(run_id: str, media_url: str, geotag: str = "", caption: str = "") -> str:
    """
    Extracts civic issue details (category, severity, location) from media.
    Args:
        run_id: The unique ID for this report.
        media_url: The URL or path to the media file.
        geotag: User-provided location or GPS data.
        caption: Text context provided with the media.
    """
    try:
        # Call the underlying pipeline
        raw_result = run_vision_pipeline(
            url=media_url,
            user_location=geotag or "",
            whatsapp_text=caption or ""
        )
        
        # Map raw_result to ExtractedIssue
        category_map = {
            "Water Pollution": IssueCategory.WATER_POLLUTION,
            "Air Pollution": IssueCategory.AIR_POLLUTION,
            "Solid Waste": IssueCategory.SOLID_WASTE,
            "Noise Pollution": IssueCategory.NOISE_POLLUTION,
            "Illegal Dumping": IssueCategory.ILLEGAL_DUMPING,
            "Road Damage": IssueCategory.ROAD_DAMAGE,
            "Sewage Overflow": IssueCategory.SEWAGE_OVERFLOW,
        }
        category = category_map.get(raw_result.get("issue_type"), IssueCategory.SOLID_WASTE)
        
        severity = raw_result.get("severity", 3)
        severity = max(1, min(5, int(severity)))

        issue = ExtractedIssue(
            run_id=run_id,
            category=category,
            severity=severity,
            location_raw=geotag,
            location_resolved=raw_result.get("location_label"),
            description=raw_result.get("transcript") or "Civic issue detected",
            detected_objects=[],
            confidence_score=raw_result.get("confidence", 0.9),
            vision_model_id="pair_d-v1"
        )
        
        return issue.model_dump_json()
    except Exception as e:
        logger.exception("[vision_tool] Failed to process media")
        return json.dumps({"error": str(e), "run_id": run_id})