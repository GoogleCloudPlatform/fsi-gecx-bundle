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

import math
import logging
import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from models.identity import User, UserDevice, UserSecureMessage, RetailLocation
from utils.audit import record_audit_event

logger = logging.getLogger(__name__)


def _user_to_dict(user: User) -> Dict[str, Any]:
    return {
        "user_id": user.auth_provider_uid,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone_number": user.phone_number,
    }


def get_customer(db: Session, auth_provider_uid: str) -> Optional[Dict[str, Any]]:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return None
    return _user_to_dict(user)


def create_customer(
    db: Session,
    auth_provider_uid: str,
    first_name: Optional[str],
    last_name: Optional[str],
    email: Optional[str],
    phone_number: Optional[str],
) -> Dict[str, Any]:
    user = User(
        auth_provider_uid=auth_provider_uid,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
    )
    db.add(user)
    db.flush()

    record_audit_event(
        db,
        "USER_CREATED",
        {
            "user_id": auth_provider_uid,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    db.commit()
    db.refresh(user)
    return _user_to_dict(user)


def update_customer(
    db: Session,
    auth_provider_uid: str,
    first_name: Optional[str],
    last_name: Optional[str],
    phone_number: Optional[str],
) -> Optional[Dict[str, Any]]:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return None

    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if phone_number is not None:
        user.phone_number = phone_number

    record_audit_event(
        db,
        "USER_UPDATED",
        {
            "user_id": auth_provider_uid,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
        },
    )
    db.commit()
    db.refresh(user)
    return _user_to_dict(user)


def get_all_customers(db: Session) -> List[Dict[str, Any]]:
    users = db.query(User).all()
    return [_user_to_dict(u) for u in users]


def save_device_token(db: Session, auth_provider_uid: str, device_token: str) -> None:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        user = User(auth_provider_uid=auth_provider_uid)
        db.add(user)
        db.flush()

    existing = (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user.id, UserDevice.device_token == device_token)
        .first()
    )
    if not existing:
        device = UserDevice(user_id=user.id, device_token=device_token)
        db.add(device)
        record_audit_event(
            db,
            "DEVICE_REGISTERED",
            {"user_id": auth_provider_uid, "device_token": device_token},
        )
        db.commit()


def delete_device_token(db: Session, auth_provider_uid: str, device_token: str) -> None:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return

    db.query(UserDevice).filter(
        UserDevice.user_id == user.id, UserDevice.device_token == device_token
    ).delete()
    record_audit_event(
        db,
        "DEVICE_DELETED",
        {"user_id": auth_provider_uid, "device_token": device_token},
    )
    db.commit()


def get_device_tokens_for_customer(db: Session, auth_provider_uid: str) -> List[str]:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return []
    devices = db.query(UserDevice).filter(UserDevice.user_id == user.id).all()
    return [d.device_token for d in devices]


def create_message(
    db: Session,
    auth_provider_uid: str,
    message_id: str,
    sender: str,
    message: str,
    category: Optional[str],
    thread_id: str,
) -> None:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        # Auto-create basic user if message arrives before profile creation
        user = User(auth_provider_uid=auth_provider_uid)
        db.add(user)
        db.flush()

    msg = UserSecureMessage(
        message_id=message_id,
        user_id=user.id,
        sender=sender,
        category=category,
        message=message,
        thread_id=thread_id,
        is_user_read=(sender == "user"),
        is_agent_read=(sender != "user"),
    )
    db.add(msg)
    record_audit_event(
        db,
        "MESSAGE_SENT",
        {
            "message_id": message_id,
            "user_id": auth_provider_uid,
            "sender": sender,
            "thread_id": thread_id,
        },
    )
    db.commit()


def get_messages_for_customer(db: Session, auth_provider_uid: str) -> List[Dict[str, Any]]:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return []

    msgs = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.user_id == user.id, UserSecureMessage.deleted == False)
        .order_by(UserSecureMessage.created_at.asc())
        .all()
    )
    return [
        {
            "message_id": m.message_id,
            "user_id": auth_provider_uid,
            "sender": m.sender,
            "category": m.category,
            "message": m.message,
            "thread_id": m.thread_id,
            "is_user_read": m.is_user_read,
            "is_agent_read": m.is_agent_read,
            "created_at": m.created_at or datetime.datetime.now(datetime.timezone.utc),
            "deleted": m.deleted,
            "timestamp": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


def soft_delete_message(db: Session, auth_provider_uid: str, message_id: str) -> bool:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return False

    msg = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.user_id == user.id, UserSecureMessage.message_id == message_id)
        .first()
    )
    if not msg:
        return False

    msg.deleted = True
    record_audit_event(
        db,
        "MESSAGE_DELETED",
        {"message_id": message_id, "user_id": auth_provider_uid},
    )
    db.commit()
    return True


def soft_delete_thread(db: Session, auth_provider_uid: str, thread_id: str) -> int:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return 0

    msgs = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.user_id == user.id, UserSecureMessage.thread_id == thread_id)
        .all()
    )
    count = 0
    for m in msgs:
        if not m.deleted:
            m.deleted = True
            count += 1

    if count > 0:
        record_audit_event(
            db,
            "THREAD_DELETED",
            {"thread_id": thread_id, "user_id": auth_provider_uid, "deleted_count": count},
        )
        db.commit()
    return count


def get_user_id_for_thread(db: Session, thread_id: str) -> Optional[str]:
    msg = db.query(UserSecureMessage).filter(UserSecureMessage.thread_id == thread_id).first()
    if not msg or not msg.user:
        return None
    return msg.user.auth_provider_uid


def mark_messages_as_user_read(db: Session, auth_provider_uid: str, thread_id: str) -> None:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return

    msgs = (
        db.query(UserSecureMessage)
        .filter(
            UserSecureMessage.user_id == user.id,
            UserSecureMessage.thread_id == thread_id,
            UserSecureMessage.is_user_read == False,
        )
        .all()
    )
    for m in msgs:
        m.is_user_read = True
    if msgs:
        db.commit()


def mark_messages_as_agent_read(db: Session, thread_id: str) -> None:
    msgs = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.thread_id == thread_id, UserSecureMessage.is_agent_read == False)
        .all()
    )
    for m in msgs:
        m.is_agent_read = True
    if msgs:
        db.commit()


def mark_messages_as_user_read_by_ids(db: Session, auth_provider_uid: str, message_ids: List[str]) -> None:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        return
    msgs = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.user_id == user.id, UserSecureMessage.message_id.in_(message_ids))
        .all()
    )
    for m in msgs:
        m.is_user_read = True
    if msgs:
        db.commit()


def mark_messages_as_agent_read_by_ids(db: Session, message_ids: List[str]) -> None:
    msgs = (
        db.query(UserSecureMessage)
        .filter(UserSecureMessage.message_id.in_(message_ids))
        .all()
    )
    for m in msgs:
        m.is_agent_read = True
    if msgs:
        db.commit()


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def find_nearest_locations(
    db: Session, lat: float, lng: float, location_type: str = "ALL", limit: int = 10
) -> List[Dict[str, Any]]:
    query = db.query(RetailLocation)
    if location_type and location_type.upper() != "ALL":
        query = query.filter(RetailLocation.type == location_type.upper())

    all_locs = query.all()
    results = []
    for loc in all_locs:
        dist = _haversine_distance(lat, lng, loc.latitude, loc.longitude)
        results.append(
            {
                "id": str(loc.id),
                "type": loc.type,
                "name": loc.name,
                "address": loc.address,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "hours": loc.hours,
                "phone_number": loc.phone_number,
                "distance_miles": round(dist, 2),
            }
        )

    results.sort(key=lambda x: x["distance_miles"])
    return results[:limit]


def search_locations_by_text(
    db: Session, query_text: str, location_type: str = "ALL", limit: int = 10
) -> List[Dict[str, Any]]:
    query = db.query(RetailLocation)
    if location_type and location_type.upper() != "ALL":
        query = query.filter(RetailLocation.type == location_type.upper())

    all_locs = query.all()
    q_lower = query_text.lower()
    matching = [
        loc
        for loc in all_locs
        if q_lower in loc.name.lower() or q_lower in loc.address.lower()
    ]
    results = []
    for loc in matching[:limit]:
        results.append(
            {
                "id": str(loc.id),
                "type": loc.type,
                "name": loc.name,
                "address": loc.address,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "hours": loc.hours,
                "phone_number": loc.phone_number,
                "distance_miles": None,
            }
        )
    return results
