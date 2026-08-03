"""Typed contracts for the non-authoritative external-framework crosswalk."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CrosswalkFramework(StrEnum):
    """External frameworks this platform maps its controls against."""

    NIST_AI_RMF = "nist_ai_rmf"
    NIST_AI_600_1 = "nist_ai_600_1"
    OWASP_LLM_TOP10 = "owasp_llm_top10"
    OWASP_AGENTIC_TOP10 = "owasp_agentic_top10"
    MITRE_ATLAS = "mitre_atlas"
    ISO_IEC_42001 = "iso_iec_42001"


class CrosswalkReference(BaseModel):
    """One best-effort reference from a control to an external framework locator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    framework: CrosswalkFramework
    reference: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class ControlCrosswalkEntry(BaseModel):
    """External-framework references for one baseline control."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    control_id: str = Field(pattern=r"^GOV-[A-Z]{3}-\d{3}$")
    references: tuple[CrosswalkReference, ...] = Field(min_length=1)


class ControlCrosswalk(BaseModel):
    """Versioned, non-authoritative crosswalk from controls to external frameworks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    crosswalk_id: str = Field(min_length=3, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    frameworks_covered: tuple[CrosswalkFramework, ...]
    frameworks_pending: tuple[CrosswalkFramework, ...]
    disclaimer: str = Field(min_length=10, max_length=2000)
    entries: tuple[ControlCrosswalkEntry, ...] = Field(min_length=1)
