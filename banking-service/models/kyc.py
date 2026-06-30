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

import datetime
from sqlalchemy import Column, DateTime, LargeBinary, Index, ForeignKey, String, Integer, BigInteger
from utils.database import UniversalUUID as UUID, generate_uuid
from utils.database import Base


class KYCRecord(Base):
    """
    Isolated KYC entity stored within the restricted 'kyc' schema.
    Contains envelope-encrypted sensitive PII (SSN, Tax ID, DOB).
    """
    __tablename__ = "kyc_records"
    __table_args__ = (
        Index("idx_kyc_records_user_id", "user_id"),
        {'schema': 'kyc'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False)
    encrypted_pii = Column(LargeBinary, nullable=False)
    wrapped_dek = Column(LargeBinary, nullable=False)
    encryption_iv = Column(LargeBinary, nullable=False)
    auth_tag = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))


class UserCreditProfile(Base):
    """
    Isolated credit and underwriting profile.
    Contains sensitive financial indicators (NPI) linked back to the user.
    """
    __tablename__ = "user_credit_profiles"
    __table_args__ = {'schema': 'kyc'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Financial metrics for underwriting decisions
    credit_score = Column(Integer, nullable=False)  # FICO Range 300–850
    credit_tier = Column(String(50), nullable=False)  # 'PRIME_EXCELLENT', 'PRIME', 'NEAR_PRIME', 'SUBPRIME'
    stated_annual_income_cents = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

