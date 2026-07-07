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
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Float, Index
from utils.database import UniversalUUID as UUID, generate_uuid
from sqlalchemy.orm import relationship
from utils.database import Base


class User(Base):
    """
    Core customer profile record inside the identity schema.
    Uses 16-byte native UUID as internal surrogate key while storing external Firebase UID.
    """
    __tablename__ = "users"
    __table_args__ = {'schema': 'identity'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    auth_provider_uid = Column(String(128), unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone_number = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    devices = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")
    secure_messages = relationship("UserSecureMessage", back_populates="user", cascade="all, delete-orphan")
    addresses = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan")


class UserAddress(Base):
    """
    3NF Normalized Address table inside the identity schema.
    Supports residential, mailing, work, and historical address tracking.
    """
    __tablename__ = "user_addresses"
    __table_args__ = (
        Index("idx_user_addresses_user_id", "user_id"),
        {'schema': 'identity'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False)
    
    address_type = Column(String(50), nullable=False)  # 'RESIDENTIAL', 'MAILING', 'BILLING', 'WORK', 'PREVIOUS'
    is_primary = Column(Boolean, default=False, nullable=False)
    
    street_line_1 = Column(String(255), nullable=False)
    street_line_2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(50), nullable=False)
    postal_code = Column(String(20), nullable=False)
    country_code = Column(String(3), default="USA", nullable=False)
    
    verified_by_doc_ai = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    user = relationship("User", back_populates="addresses")


class UserDevice(Base):
    """
    MFA and push notification device token registrations for a user.
    """
    __tablename__ = "user_devices"
    __table_args__ = (
        Index("idx_user_devices_user_id", "user_id"),
        {'schema': 'identity'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False)
    device_token = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    user = relationship("User", back_populates="devices")


class UserSecureMessage(Base):
    """
    Secure communication threads between customers and support agents.
    """
    __tablename__ = "user_secure_messages"
    __table_args__ = (
        Index("idx_secure_msgs_user_id", "user_id"),
        Index("idx_secure_msgs_thread_id", "thread_id"),
        {'schema': 'identity'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    message_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(50), nullable=False)  # 'user' or 'agent'
    category = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    thread_id = Column(String(128), nullable=False)
    is_user_read = Column(Boolean, default=True)
    is_agent_read = Column(Boolean, default=False)
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    user = relationship("User", back_populates="secure_messages")


class RetailLocation(Base):
    """
    Bank branches and ATM locations.
    """
    __tablename__ = "retail_locations"
    __table_args__ = {'schema': 'operations'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # 'BRANCH' or 'ATM'
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    hours = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
