# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

class UnderwritingDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT_FRAUD = "REJECT_FRAUD"
    REJECT_LEGIBILITY = "REJECT_LEGIBILITY"
    REJECT_DATA_MISMATCH = "REJECT_DATA_MISMATCH"

class DocumentVerificationStatus(BaseModel):
    ssn_verified: bool = Field(..., description="Indicates if SSN on document matches the loan application exactly.")
    employer_verified: bool = Field(..., description="Indicates if Employer Name matches the loan application.")
    calculated_gross_monthly_income: float = Field(..., description="Underwriter-verified gross monthly income calculated from W-2 wages / paystub YTD.")

class UnderwritingOverrideRequest(BaseModel):
    artifact_id: str = Field(..., description="Unique artifact reference ID.")
    customer_id: str = Field(..., description="Associated customer ID for strict tenant context validation.")
    decision: UnderwritingDecision = Field(..., description="The underwriter's structural lending decision.")
    verifications: DocumentVerificationStatus = Field(..., description="Granular field verification check outcomes.")
    corrected_payload: dict[str, Any] = Field(..., description="Key-value mapping of corrected OCR fields (e.g. Wages, SSN).", repr=False)
    underwriter_notes: str = Field(..., description="Mandatory professional underwriter rationale for Fannie Mae audit compliance.")
    underwriter_id: str = Field(..., description="Authenticated Loan Officer ID.")
    expected_version_id: Optional[str] = Field(None, description="Optimistic Concurrency Control (OCC) expected version UUID.")
    document_hash: Optional[str] = Field(None, description="SHA-256 cryptographic hash of the verified PDF blob.")
    interactive_verifications: Optional[dict[str, Any]] = Field(None, description="Interactive micro-verification confirmations (e.g., wages visually matched, tax year visually matched).")

class DocumentSummaryResponse(BaseModel):
    artifact_id: str = Field(..., description="Unique artifact ID.")
    customer_id: str = Field(..., description="Associated customer ID.")
    application_id: Optional[str] = Field(None, description="Associated loan application ID.")
    claimed_artifact_type: Optional[str] = Field(None, description="The document type declared by the borrower.")
    actual_artifact_type: Optional[str] = Field(None, description="The visual document classification returned by AI.")
    status: str = Field(..., description="Ingestion status flag.")
    file_path_gcs: Optional[str] = Field(None, description="The source file path in GCS.")
    extraction_payload: Optional[dict[str, Any]] = Field(None, description="The OCR parsed payload dictionary.", repr=False)
    audit_metadata: Optional[dict[str, Any]] = Field(None, description="Lending audit history metadata metadata.")
    verification_tier: Optional[str] = Field(None, description="Verification tier (TIER_1_MANUAL or TIER_2_SPOT_CHECK).")
    version_id: Optional[str] = Field(None, description="OCC version UUID.")
    user_first_name: Optional[str] = Field(None, description="First name of the borrower.")
    user_last_name: Optional[str] = Field(None, description="Last name of the borrower.")
    user_email: Optional[str] = Field(None, description="Email address of the borrower.")
    requested_amount: Optional[float] = Field(None, description="The loan amount or credit limit requested in the application.")
    product_category: Optional[str] = Field(None, description="Category of product (e.g. LOAN, CARD).")
    product_type: Optional[str] = Field(None, description="Specific type of product (e.g. RESIDENTIAL_MORTGAGE).")
