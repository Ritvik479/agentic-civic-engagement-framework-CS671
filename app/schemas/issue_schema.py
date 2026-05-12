"""
app/schemas/issue_schema.py

Core Pydantic state models for the Agentic Civic Engagement Framework.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Union  # <-- ADD Union HERE
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, AnyUrl, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class IssueCategory(str, Enum):
    """Recognised civic issue categories understood by the routing logic."""
    WATER_POLLUTION   = "water_pollution"
    AIR_POLLUTION     = "air_pollution"
    SOLID_WASTE       = "solid_waste"
    NOISE_POLLUTION   = "noise_pollution"
    ILLEGAL_DUMPING   = "illegal_dumping"
    ROAD_DAMAGE       = "road_damage"
    SEWAGE_OVERFLOW   = "sewage_overflow"
    UNKNOWN           = "unknown"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class ComplaintStatus(str, Enum):
    DRAFT     = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    FAILED    = "failed"


# ---------------------------------------------------------------------------
# Model 1 — MediaMetadata  (pipeline INPUT)
# ---------------------------------------------------------------------------

class MediaMetadata(BaseModel):
    """
    Describes a single piece of raw civic media ingested from social platforms.
    """

    run_id: UUID = Field(
        default_factory=uuid4,
        description=(
            "Unique identifier for this processing run. "
            "Propagated unchanged through every subsequent model..."
        ),
    )

    media_url: AnyUrl = Field(
        description=(
            "Publicly accessible URL to the raw image or video file. "
            "Tools in pair_b will download and pass this to the vision model."
        ),
    )

    media_type: MediaType = Field(
        description="Whether the asset is a static image or a video clip.",
    )

    platform: str = Field(
        description=(
            "Social-media platform the media originated from "
            "(e.g. 'twitter', 'instagram', 'youtube', 'whatsapp')."
        ),
    )

    posted_at: datetime = Field(
        description=(
            "UTC timestamp of the original social-media post. "
            "Used for complaint urgency scoring and SLA tracking."
        ),
    )

    reporter_handle: Optional[str] = Field(
        default=None,
        description=(
            "Social handle or anonymised user ID of the person who posted the media. "
            "May be None if the platform does not expose this."
        ),
    )

    geotag: Optional[str] = Field(
        default=None,
        description=(
            "Raw location string attached to the post (e.g. 'Andheri East, Mumbai'). "
            "May be None if the user did not enable location sharing. "
            "The geo-resolution tool in pair_d will parse this further."
        ),
    )

    caption: Optional[str] = Field(
        default=None,
        description=(
            "Original text caption or tweet body accompanying the media. "
            "Used as supplementary context for the vision model."
        ),
    )

    raw_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Catch-all dict for any platform-specific metadata fields "
            "(e.g. EXIF data, engagement metrics) that don't fit the schema above. "
            "Tools may read from this but should never write their outputs here."
        ),
    )


# ---------------------------------------------------------------------------
# Model 2 — ExtractedIssue  (vision tool OUTPUT)
# ---------------------------------------------------------------------------

class ExtractedIssue(BaseModel):
    """
    Structured representation of the civic issue detected by the vision tool.
    """

    run_id: UUID = Field(
        description="Echo of MediaMetadata.run_id — links this output to its source media.",
    )

    category: IssueCategory = Field(
        description=(
            "The top-level category of civic issue detected in the media. "
            "The routing tool in pair_d uses this to select the correct authority."
        ),
    )

    severity: int = Field(
        ge=1, 
        le=5, 
        description="Severity of the issue from 1 (lowest) to 5 (bypass — routes directly to central authority)."
    )

    location_raw: Optional[str] = Field(
        default=None,
        description=(
            "Any location text visible in the media itself (e.g. a road sign, "
            "a building name, a GPS overlay). Distinct from MediaMetadata.geotag."
        ),
    )

    location_resolved: Optional[str] = Field(
        default=None,
        description=(
            "Standardised address or ward/zone string after geo-resolution. "
            "Populated by the geo-resolution tool in pair_d; None until then."
        ),
    )

    description: str = Field(
        description=(
            "Free-text, human-readable description of the issue as observed in "
            "the media. Written in neutral, factual language suitable for "
            "inclusion in an official complaint."
        ),
    )

    detected_objects: list[str] = Field(
        default_factory=list,
        description=(
            "List of specific objects or substances identified in the visual "
            "(e.g. ['black plastic bags', 'stagnant water', 'open drain']). "
            "Used to enrich the complaint narrative."
        ),
    )

    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Vision model's confidence in the category classification, "
            "from 0.0 (no confidence) to 1.0 (certainty). "
            "Complaints below 0.5 are flagged for human review."
        ),
    )

    vision_model_id: str = Field(
        description=(
            "Identifier of the vision model used (e.g. 'gpt-4o', "
            "'Salesforce/blip2-flan-t5-xl'). Stored for auditability."
        ),
    )

    @model_validator(mode="after")
    def flag_low_confidence(self) -> "ExtractedIssue":
        """Warn in the description if confidence is below threshold."""
        from app.constants import ConfidenceThreshold
        if self.confidence_score < ConfidenceThreshold.HUMAN_REVIEW_REQUIRED:
            self.description = (
                f"[LOW CONFIDENCE — REVIEW REQUIRED] {self.description}"
            )
        return self


# ---------------------------------------------------------------------------
# Model 3 — AuthorityContact  (routing/lookup tool OUTPUT)
# ---------------------------------------------------------------------------

class AuthorityContact(BaseModel):
    """
    Contact details for the government authority responsible for resolving
    the detected issue.
    """

    run_id: UUID = Field(
        description="Echo of MediaMetadata.run_id.",
    )

    department_name: str = Field(
        description=(
            "Full official name of the responsible government department "
            "(e.g. 'Brihanmumbai Municipal Corporation — Solid Waste Management')."
        ),
    )

    department_code: str = Field(
        description=(
            "Short code used in complaint submission APIs or portal systems "
            "(e.g. 'BMC-SWM', 'CPCB-WP'). Must match authority database keys."
        ),
    )

    submission_email: Optional[str] = Field(
        default=None,
        description=(
            "Official email address for complaint submission. "
            "Used as fallback when API submission is unavailable."
        ),
    )

    submission_api_url: Optional[HttpUrl] = Field(
        default=None,
        description=(
            "REST endpoint for programmatic complaint submission. "
            "trio_c tools POST the FinalComplaint payload here."
        ),
    )

    portal_url: Optional[HttpUrl] = Field(
        default=None,
        description=(
            "Public citizen-facing portal URL. Included in the complaint "
            "acknowledgement sent back to the reporter."
        ),
    )

    jurisdiction: str = Field(
        description=(
            "Geographic area this authority covers "
            "(e.g. 'Mumbai Municipal Zone 4', 'Delhi NCT')."
        ),
    )

    escalation_authority: Optional[str] = Field(
        default=None,
        description=(
            "Name of the next-level authority to escalate to if the primary "
            "department does not respond within SLA (e.g. 'CPCB Regional Office')."
        ),
    )

    sla_days: int = Field(
        default=30,
        description=(
            "Number of calendar days the authority has to respond, "
            "as per regulatory mandate. Used to compute follow-up dates."
        ),
    )


# ---------------------------------------------------------------------------
# Model 4 — FinalComplaint  (submission OUTPUT / pipeline terminal state)
# ---------------------------------------------------------------------------

class FinalComplaint(BaseModel):
    """
    The complete, submission-ready civic complaint.
    """

    run_id: UUID = Field(
        description="Echo of MediaMetadata.run_id — the end-to-end correlation key.",
    )

    complaint_id: Optional[str] = Field(
        default=None,
        description=(
            "Complaint reference number returned by the authority's submission API. "
            "None until successful submission; populated by the submission tool."
        ),
    )

    status: ComplaintStatus = Field(
        default=ComplaintStatus.DRAFT,
        description=(
            "Lifecycle state of the complaint. Transitions: "
            "DRAFT → VALIDATED → SUBMITTED (or FAILED)."
        ),
    )

    # --- Source information (flattened from MediaMetadata) ---
    source_url: str = Field(
        description="String form of MediaMetadata.media_url for serialisation.",
    )

    platform: str = Field(
        description="Social platform the media was sourced from.",
    )

    reporter_handle: Optional[str] = Field(
        default=None,
        description="Anonymised handle of the original poster, if available.",
    )

    posted_at: datetime = Field(
        description="UTC datetime of the original social post.",
    )

    # --- Issue fields (flattened from ExtractedIssue) ---
    issue_category: IssueCategory = Field(
        description="Top-level category of the civic issue.",
    )

    severity: int = Field(
        ge=1, 
        le=5, 
        description="Severity of the issue from 1 (lowest) to 5 (bypass — routes directly to central authority)."
    )

    issue_location: str = Field(
        description=(
            "Best available resolved location string. "
            "Prefer ExtractedIssue.location_resolved; "
            "fall back to MediaMetadata.geotag."
        ),
    )

    issue_description: str = Field(
        description=(
            "Complaint body text. Written by the narrative-drafting tool in trio_c "
            "using ExtractedIssue.description as input."
        ),
    )

    evidence_urls: list[str] = Field(
        default_factory=list,
        description=(
            "List of URLs to evidence files (original media + any annotated "
            "snapshots produced by the vision tool)."
        ),
    )

    # --- Authority fields (flattened from AuthorityContact) ---
    authority_name: str = Field(
        description="Full name of the responsible government department.",
    )

    authority_code: str = Field(
        description="Short department code used in API payloads.",
    )

    authority_portal: Optional[str] = Field(
        default=None,
        description="Public citizen-facing portal URL for the authority.",
    )

    submission_endpoint: Optional[str] = Field(
        default=None,
        description="API URL or email used for submission.",
    )

    # --- Submission tracking ---
    submitted_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of successful complaint submission.",
    )

    follow_up_due: Optional[datetime] = Field(
        default=None,
        description=(
            "Computed date by which the authority must respond "
            "(submitted_at + AuthorityContact.sla_days)."
        ),
    )

    submission_response: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Raw JSON response body from the authority's submission API. "
            "Stored verbatim for auditability."
        ),
    )

    validation_errors: list[str] = Field(
        default_factory=list,
        description=(
            "List of validation error messages if status is FAILED or "
            "if any upstream tool flagged data quality issues."
        ),
    )

    @model_validator(mode="after")
    def compute_follow_up(self) -> "FinalComplaint":
        """Auto-compute follow_up_due if submitted_at is set."""
        from app.constants import SLADefaults
        if self.submitted_at and self.follow_up_due is None:
            self.follow_up_due = self.submitted_at + timedelta(days=SLADefaults.STANDARD)
        return self