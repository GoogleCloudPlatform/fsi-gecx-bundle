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

import logging
from sqlalchemy.orm import Session
from models.kyc import KYCRecord
from utils.encryption import rotate_record_dek

logger = logging.getLogger(__name__)


def batch_rotate_kyc_deks(
    db: Session,
    old_kek_name: str | None = None,
    old_mock_kek: bytes | None = None,
    new_kek_name: str | None = None,
    new_mock_kek: bytes | None = None,
    batch_size: int = 100
) -> int:
    """
    Iterates through all stored KYCRecords and rotates their wrapped DEKs
    from an old KEK version to a new target KEK version in batches.
    Returns the total number of re-wrapped records.
    """
    total_rotated = 0
    offset = 0

    while True:
        records = db.query(KYCRecord).order_by(KYCRecord.id).offset(offset).limit(batch_size).all()
        if not records:
            break

        for rec in records:
            try:
                new_wrapped = rotate_record_dek(
                    rec.wrapped_dek,
                    old_kek_name=old_kek_name,
                    old_mock_kek=old_mock_kek,
                    new_kek_name=new_kek_name,
                    new_mock_kek=new_mock_kek
                )
                rec.wrapped_dek = new_wrapped
                total_rotated += 1
            except Exception as e:
                logger.error(f"Failed to rotate DEK for KYC record {rec.id}: {e}")
                raise

        db.commit()
        offset += batch_size

    logger.info(f"Successfully rotated {total_rotated} KYC record DEKs.")
    return total_rotated
