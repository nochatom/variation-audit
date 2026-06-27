"""Normalized internal schema (engine ingest + baseline output).

This is the canonical structured form the engine produces from raw, unstructured
Australian construction communications. The variation-detection stage (.10)
consumes NormalizedDocument; it is engine-internal and NOT the v1.1 wire schema.

Reference implementation of the changeorder-recovery engine's ingest+baseline
stages. Australia-only scope; all construction trades.
"""
from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    # extra="forbid" -> additionalProperties:false, required by structured outputs.
    model_config = ConfigDict(extra="forbid")


# Mirrors the contract v1.1 source_type vocabulary (.21.1). The engine keeps its
# own copy because it is a separate codebase from the product layer.
class SourceType(str, enum.Enum):
    email = "email"
    rfi = "rfi"
    site_instruction = "site_instruction"
    meeting_note = "meeting_note"
    sms = "sms"
    document = "document"


class PartyRole(str, enum.Enum):
    contractor = "contractor"
    subcontractor = "subcontractor"
    superintendent = "superintendent"
    architect = "architect"
    engineer = "engineer"
    client = "client"
    supplier = "supplier"
    other = "other"


class ReferenceType(str, enum.Enum):
    rfi = "rfi"
    drawing = "drawing"
    specification = "specification"
    variation = "variation"
    contract_clause = "contract_clause"
    purchase_order = "purchase_order"
    other = "other"


class ScopeAction(str, enum.Enum):
    instructed = "instructed"     # a party directed the work be done
    performed = "performed"       # work was actually carried out
    requested = "requested"       # a party asked for the work / a price
    approved = "approved"         # work / variation approved
    rejected = "rejected"         # work / variation rejected
    discussed = "discussed"       # mentioned without a clear directive


class Party(_Strict):
    name: str
    role: PartyRole = PartyRole.other


class Reference(_Strict):
    ref_type: ReferenceType
    value: str = Field(description="e.g. 'RFI-012', 'DWG A-101', 'VO-7', 'Clause 36.1'")


class ScopeItem(_Strict):
    description: str = Field(description="The discrete piece of work or scope change.")
    action: ScopeAction
    potential_variation: bool = Field(
        description="True only when this plausibly represents out-of-contract work "
        "that may be an unclaimed/undocumented variation."
    )
    mentioned_date: str | None = Field(
        default=None, description="ISO-8601 date if a date is tied to this item, else null."
    )


class NormalizedDocument(_Strict):
    document_id: str
    source_type: SourceType
    summary: str = Field(description="One- or two-sentence neutral summary of the document.")
    event_date: str | None = Field(
        default=None,
        description="Primary ISO-8601 date of the communication/event, AU day-first interpreted; null if none.",
    )
    trade: str | None = Field(
        default=None, description="Construction trade if identifiable (e.g. electrical, plumbing, HVAC)."
    )
    parties: list[Party] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    scope_items: list[ScopeItem] = Field(default_factory=list)
