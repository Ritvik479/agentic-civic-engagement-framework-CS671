"""
app/constants.py

Shared constants for the Agentic Civic Engagement Framework pipeline.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pipeline Stage Names
# ---------------------------------------------------------------------------

class PipelineStage:
    """String constants for each named stage in the processing pipeline."""

    MEDIA_INGESTION       = "media_ingestion"
    VISION_ANALYSIS       = "vision_analysis"
    GEO_RESOLUTION        = "geo_resolution"
    AUTHORITY_ROUTING     = "authority_routing"
    SEVERITY_ASSESSMENT   = "severity_assessment"
    COMPLAINT_DRAFTING    = "complaint_drafting"
    COMPLAINT_VALIDATION  = "complaint_validation"
    COMPLAINT_SUBMISSION  = "complaint_submission"
    ESCALATION_CHECK      = "escalation_check"
    COMPLETED             = "completed"
    FAILED                = "failed"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"

    ORDERED: list[str] = [
        MEDIA_INGESTION,
        VISION_ANALYSIS,
        GEO_RESOLUTION,
        AUTHORITY_ROUTING,
        SEVERITY_ASSESSMENT,
        COMPLAINT_DRAFTING,
        COMPLAINT_VALIDATION,
        COMPLAINT_SUBMISSION,
    ]


# ---------------------------------------------------------------------------
# Confidence Thresholds
# ---------------------------------------------------------------------------

class ConfidenceThreshold:
    """Vision model confidence cut-offs."""
    HUMAN_REVIEW_REQUIRED: float = 0.50
    DISCARD: float = 0.20
    HIGH_QUALITY: float = 0.85


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------

class RetryPolicy:
    """Max retry attempts per pipeline stage."""
    VISION_ANALYSIS:       int = 3
    GEO_RESOLUTION:        int = 2
    AUTHORITY_ROUTING:     int = 2
    COMPLAINT_SUBMISSION:  int = 3
    BACKOFF_BASE_SECONDS: float = 2.0
    MAX_WAIT_SECONDS: float = 30.0


# ---------------------------------------------------------------------------
# SLA Defaults (calendar days)
# ---------------------------------------------------------------------------

class SLADefaults:
    """Default SLA windows in calendar days."""
    STANDARD: int   = 30   
    URGENT: int     = 7    
    CRITICAL: int   = 2    
    ESCALATION: int = 15   


# ---------------------------------------------------------------------------
# Severity → SLA Mapping
# ---------------------------------------------------------------------------

SEVERITY_TO_SLA_DAYS: dict[int, int] = {
    1: SLADefaults.STANDARD,
    2: SLADefaults.MEDIUM if hasattr(SLADefaults, 'MEDIUM') else SLADefaults.STANDARD,
    3: SLADefaults.URGENT if hasattr(SLADefaults, 'URGENT') else SLADefaults.URGENT, 
    4: SLADefaults.CRITICAL,
    5: SLADefaults.CRITICAL,
}

# Note: Based on provided SLADefaults class content, I used logic matching:
# 1: STANDARD, 2: STANDARD (no MEDIUM provided in file), 3: URGENT, 4: CRITICAL, 5: CRITICAL
SEVERITY_TO_SLA_DAYS: dict[int, int] = {
    1: SLADefaults.STANDARD,
    2: SLADefaults.STANDARD,
    3: SLADefaults.URGENT,
    4: SLADefaults.CRITICAL,
    5: SLADefaults.CRITICAL,
}


# ---------------------------------------------------------------------------
# Issue Category → Default Department Code
# ---------------------------------------------------------------------------

CATEGORY_TO_DEFAULT_DEPT: dict[str, str] = {
    "water_pollution":  "PCB-WP",
    "air_pollution":    "PCB-AP",
    "solid_waste":      "ULB-SWM",
    "noise_pollution":  "PCB-NP",
    "illegal_dumping":  "ULB-SWM",
    "road_damage":      "PWD-RD",
    "sewage_overflow":  "ULB-SWG",
    "unknown":          "GENERIC-CIV",
}


# ---------------------------------------------------------------------------
# Submission Channel Priority
# ---------------------------------------------------------------------------

class SubmissionChannel:
    API   = "api"
    EMAIL = "email"
    PORTAL = "portal"
    PRIORITY_ORDER: list[str] = [API, EMAIL, PORTAL]


# ---------------------------------------------------------------------------
# Field Length Limits
# ---------------------------------------------------------------------------

class FieldLimits:
    MAX_DESCRIPTION_CHARS:     int = 2000
    MAX_CAPTION_CHARS:         int = 500
    MAX_LOCATION_STRING_CHARS: int = 300
    MAX_DETECTED_OBJECTS:      int = 20


# ---------------------------------------------------------------------------
# Logging / Observability
# ---------------------------------------------------------------------------

class LogFields:
    RUN_ID        = "run_id"
    STAGE         = "stage"
    DURATION_MS   = "duration_ms"
    SUCCESS       = "success"
    ERROR_CODE    = "error_code"
    RETRY_ATTEMPT = "retry_attempt"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

UNKNOWN_LOCATION_PLACEHOLDER: str = "Location not determined"
UNKNOWN_MODEL_ID: str = "unknown-model"