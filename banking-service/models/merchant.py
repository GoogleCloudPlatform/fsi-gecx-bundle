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
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Index, ForeignKey
from sqlalchemy.orm import relationship
from utils.database import Base, UniversalUUID as UUID, generate_uuid


class MerchantMaster(Base):
    """
    Normalized 3NF Corporate Brand Catalog (`merchants.merchant_master`).
    Stores canonical parent entities (e.g. Uber, Starbucks, Target) uniquely by MID.
    """
    __tablename__ = "merchant_master"
    __table_args__ = (
        Index("idx_merchants_mcc", "default_mcc"),
        Index("idx_merchants_domain", "merchant_domain"),
        {'schema': 'merchants'}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(100), unique=True, nullable=False, index=True)
    clean_name = Column(String(100), nullable=False)
    default_mcc = Column(String(10), nullable=False)
    merchant_domain = Column(String(100), nullable=True)
    logo_url = Column(String(255), nullable=True)
    is_subscription = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    stores = relationship("MerchantStore", back_populates="merchant", cascade="all, delete-orphan")

    @property
    def mcc(self) -> str:
        return self.default_mcc


class MerchantStore(Base):
    """
    Normalized 3NF POS Terminal Descriptor & Store Location Catalog (`merchants.merchant_stores`).
    Stores individual physical or online terminal rules (USA + International) linking to parent brand.
    """
    __tablename__ = "merchant_stores"
    __table_args__ = (
        Index("idx_stores_descriptor", "raw_descriptor"),
        Index("idx_stores_country", "country_code", "is_international"),
        Index("idx_stores_risk", "risk_score"),
        {'schema': 'merchants'}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(100), ForeignKey("merchants.merchant_master.merchant_id", ondelete="CASCADE"), nullable=False, index=True)
    location_name = Column(String(100), nullable=False)
    raw_descriptor = Column(String(150), nullable=False, index=True)
    country_code = Column(String(3), nullable=False, default="USA")
    is_international = Column(Boolean, nullable=False, default=False)
    risk_score = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    merchant = relationship("MerchantMaster", back_populates="stores")

    @property
    def clean_name(self) -> str:
        return self.merchant.clean_name if self.merchant else self.location_name

    @property
    def mcc(self) -> str:
        return self.merchant.default_mcc if self.merchant else "0000"


# Type alias for legacy referencing
Merchant = MerchantMaster
