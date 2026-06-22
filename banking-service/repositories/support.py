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

from typing import Optional, List
from sqlalchemy.orm import Session
from models.support import Escalation

class SupportRepository:
    """
    Repository encapsulating persistence logic and database access for Escalation support requests.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, escalation_id: int) -> Optional[Escalation]:
        """Retrieves a specific support escalation by its primary key ID."""
        return self.db.query(Escalation).filter(Escalation.id == escalation_id).first()

    def get_pending_by_room(self, room_name: str) -> Optional[Escalation]:
        """Retrieves a pending support escalation matching the specified room name."""
        return self.db.query(Escalation).filter(
            Escalation.room_name == room_name,
            Escalation.status == "PENDING"
        ).first()

    def list_pending(self) -> List[Escalation]:
        """Retrieves all pending escalations sorted by creation time descending."""
        return self.db.query(Escalation).filter(
            Escalation.status == "PENDING"
        ).order_by(Escalation.created_at.desc()).all()

    def save(self, escalation: Escalation) -> Escalation:
        """Adds a new escalation instance or flushes state modifications to the session."""
        self.db.add(escalation)
        self.db.flush()
        return escalation
