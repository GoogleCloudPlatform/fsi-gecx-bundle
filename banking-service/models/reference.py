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
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from utils.database import Base, UniversalUUID as UUID, generate_uuid

class MerchantCategoryCode(Base):
    """Authoritative industry reference mapping of MCC codes to FDX spend categories (`merchants.merchant_category_codes`)."""
    __tablename__ = "merchant_category_codes"
    __table_args__ = {'schema': 'merchants'}

    id = Column(UUID(), primary_key=True, default=generate_uuid)
    mcc = Column(String(10), nullable=False, unique=True, index=True)
    primary_category = Column(String(50), nullable=False)
    detailed_category = Column(String(100), nullable=False)
    ui_label = Column(String(100), nullable=True)
    canonical_title = Column(String(150), nullable=True)
    canonical_group = Column(String(100), nullable=True)
    risk_level = Column(String(20), nullable=True)
    risk_score = Column(Integer, nullable=True)
    spend_type = Column(String(50), nullable=True)
    recurrence_likelihood = Column(String(20), nullable=True)
    velocity_risk = Column(String(20), nullable=True)
    chargeback_prone = Column(Boolean, nullable=False, default=False)
    is_travel = Column(Boolean, nullable=False, default=False)
    is_subscription_common = Column(Boolean, nullable=False, default=False)
    is_luxury = Column(Boolean, nullable=False, default=False)
    is_essential = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))
