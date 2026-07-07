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
from sqlalchemy import Column, String, DateTime
from utils.database import Base

class MerchantCategoryCode(Base):
    """Authoritative industry reference mapping of MCC codes to FDX spend categories (`merchants.merchant_category_codes`)."""
    __tablename__ = "merchant_category_codes"
    __table_args__ = {'schema': 'merchants'}

    mcc = Column(String(10), primary_key=True, index=True)
    primary_category = Column(String(50), nullable=False)
    detailed_category = Column(String(100), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))
