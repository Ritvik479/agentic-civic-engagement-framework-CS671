"""
app/validators.py

Lightweight validation helpers for every Pydantic model in the pipeline.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.constants import (
    ConfidenceThreshold,
    FieldLimits,
    UNKNOWN_LOCATION_PLACEHOLDER,
    UNKNOWN_MODEL_ID,
)

if TYPE_CHECKING:
    from app.schemas.issue_schema import (
        AuthorityContact,
        ExtractedIssue,
        FinalComplaint,
        MediaMetadata,
    )

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_URL_RE = re.compile(
    r"^https?://"                    
    r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"  
    r"(?::\d+)?"                     
    r"(?:/[^\s]*)?$"                 
)


def _is_blank(value: str | None) -> bool:
    return not value or not value.strip()


def _looks_like_url(value: str | None) -> bool:
    if _is_blank(value):
        return False
    val = value.strip()
    # Support file:// URLs for local development/app uploads
    if val.lower().startswith("file://"):
        return True
    return bool(_URL_RE.match(val))


def _is_future_timestamp(dt: datetime | None) -> bool:
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now).total_seconds() > 3600


# ---------------------------------------------------------------------------
# Public validators
# ---------------------------------------------------------------------------

def validate_media_metadata(obj: "MediaMetadata") -> list[str]:
    errors: list[str] = []
    raw_url = str(obj.media_url) if obj.media_url else ""
    if _is_blank(raw_url):
        errors.append("media_url: must not be blank.")
    elif not _looks_like_url(raw_url):
        errors.append(f"media_url: '{raw_url}' does not look like a valid HTTP(S) URL.")

    if _is_blank(obj.platform):
        errors.append("platform: must not be blank.")

    if _is_future_timestamp(obj.posted_at):
        errors.append(f"posted_at: timestamp '{obj.posted_at}' is more than 1 hour in the future.")

    if obj.caption and len(obj.caption) > FieldLimits.MAX_CAPTION_CHARS:
        errors.append(f"caption: length {len(obj.caption)} exceeds max {FieldLimits.MAX_CAPTION_CHARS} characters.")

    return errors


def validate_extracted_issue(obj: "ExtractedIssue") -> list[str]:
    errors: list[str] = []

    if _is_blank(obj.description):
        errors.append("description: must not be blank.")
    elif len(obj.description) > FieldLimits.MAX_DESCRIPTION_CHARS:
        errors.append(f"description: length {len(obj.description)} exceeds max {FieldLimits.MAX_DESCRIPTION_CHARS} characters.")

    if obj.confidence_score < ConfidenceThreshold.DISCARD:
        errors.append(f"confidence_score: {obj.confidence_score:.2f} is below discard threshold ({ConfidenceThreshold.DISCARD}).")

    if _is_blank(obj.vision_model_id) or obj.vision_model_id == UNKNOWN_MODEL_ID:
        errors.append("vision_model_id: must be a real model identifier, not blank or 'unknown-model'.")

    if obj.category.value == "unknown" and obj.confidence_score >= ConfidenceThreshold.HUMAN_REVIEW_REQUIRED:
        errors.append(f"category: is UNKNOWN despite confidence_score >= {ConfidenceThreshold.HUMAN_REVIEW_REQUIRED}.")

    if len(obj.detected_objects) > FieldLimits.MAX_DETECTED_OBJECTS:
        errors.append(f"detected_objects: contains {len(obj.detected_objects)} items; max is {FieldLimits.MAX_DETECTED_OBJECTS}.")

    return errors


def validate_authority_contact(obj: "AuthorityContact") -> list[str]:
    errors: list[str] = []
    if _is_blank(obj.department_name):
        errors.append("department_name: must not be blank.")
    if _is_blank(obj.department_code):
        errors.append("department_code: must not be blank.")

    has_api   = obj.submission_api_url is not None
    has_email = not _is_blank(obj.submission_email)
    if not has_api and not has_email:
        errors.append("submission channel: at least one of submission_api_url or submission_email must be provided.")

    if obj.submission_api_url:
        raw = str(obj.submission_api_url)
        if not _looks_like_url(raw):
            errors.append(f"submission_api_url: '{raw}' does not look like a valid HTTP(S) URL.")

    if _is_blank(obj.jurisdiction):
        errors.append("jurisdiction: must not be blank.")

    if obj.sla_days <= 0:
        errors.append(f"sla_days: must be positive, got {obj.sla_days}.")

    return errors


def validate_final_complaint(obj: "FinalComplaint") -> list[str]:
    errors: list[str] = []
    if _is_blank(obj.issue_description):
        errors.append("issue_description: must not be blank.")
    elif len(obj.issue_description) > FieldLimits.MAX_DESCRIPTION_CHARS:
        errors.append(f"issue_description: length {len(obj.issue_description)} exceeds max {FieldLimits.MAX_DESCRIPTION_CHARS} characters.")

    if _is_blank(obj.issue_location):
        errors.append("issue_location: must not be blank.")
    elif obj.issue_location.strip() == UNKNOWN_LOCATION_PLACEHOLDER:
        errors.append("issue_location: is still the placeholder value.")

    if _is_blank(obj.authority_name):
        errors.append("authority_name: must not be blank.")
    if _is_blank(obj.authority_code):
        errors.append("authority_code: must not be blank.")

    if _is_blank(obj.source_url):
        errors.append("source_url: must not be blank.")
    elif not _looks_like_url(obj.source_url):
        errors.append(f"source_url: '{obj.source_url}' is not a valid URL (expected http, https, or file).")

    for i, url in enumerate(obj.evidence_urls):
        if not _looks_like_url(url):
            errors.append(f"evidence_urls[{i}]: '{url}' is not a valid URL.")

    if obj.submitted_at and obj.follow_up_due:
        if obj.follow_up_due <= obj.submitted_at:
            errors.append(f"follow_up_due: must be after submitted_at.")

    return errors

def strict_validate_media_metadata(obj: "MediaMetadata") -> None:
    errors = validate_media_metadata(obj)
    if errors: raise ValueError(f"MediaMetadata validation failed:\n" + "\n".join(f"  • {e}" for e in errors))

def strict_validate_extracted_issue(obj: "ExtractedIssue") -> None:
    errors = validate_extracted_issue(obj)
    if errors: raise ValueError(f"ExtractedIssue validation failed:\n" + "\n".join(f"  • {e}" for e in errors))

def strict_validate_authority_contact(obj: "AuthorityContact") -> None:
    errors = validate_authority_contact(obj)
    if errors: raise ValueError(f"AuthorityContact validation failed:\n" + "\n".join(f"  • {e}" for e in errors))

def strict_validate_final_complaint(obj: "FinalComplaint") -> None:
    errors = validate_final_complaint(obj)
    if errors: raise ValueError(f"FinalComplaint validation failed:\n" + "\n".join(f"  • {e}" for e in errors))
