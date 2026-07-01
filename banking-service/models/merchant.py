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
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Index
from utils.database import Base, UniversalUUID as UUID, generate_uuid


class MerchantMaster(Base):
    """
    Authoritative Master Merchant Database (`merchants.merchant_master`) storing clean brand entities,
    raw POS terminal regex patterns, MCC industry mappings, CDN logo links, and international fraud flags.
    """
    __tablename__ = "merchant_master"
    __table_args__ = (
        Index("idx_merchants_mcc_country", "mcc", "country_code"),
        Index("idx_merchants_category", "category"),
        Index("idx_merchants_international", "is_international", "risk_score"),
        Index("idx_merchants_domain", "merchant_domain"),
        {'schema': 'ref_data'}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(100), unique=True, nullable=False, index=True)
    clean_name = Column(String(100), nullable=False)
    raw_descriptor_pattern = Column(String(150), nullable=False)
    mcc = Column(String(10), nullable=False)
    category = Column(String(50), nullable=False)
    country_code = Column(String(3), nullable=False, default="USA")
    logo_url = Column(String(255), nullable=True)
    merchant_domain = Column(String(100), nullable=True)
    is_subscription = Column(Boolean, nullable=False, default=False)
    is_international = Column(Boolean, nullable=False, default=False)
    risk_score = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))


# Type alias for cleaner referencing across services and routers
Merchant = MerchantMaster
