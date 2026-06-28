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

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.kyc import KYCRecord, Base
from utils.encryption import encrypt_pii, decrypt_pii
from utils.key_rotation import batch_rotate_kyc_deks


@pytest.fixture
def kyc_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_batch_rotate_kyc_deks_success(kyc_db):
    old_mock_key = b"11111111111111111111111111111111"
    new_mock_key = b"22222222222222222222222222222222"

    user_id_str = "123e4567-e89b-12d3-a456-426614174000"
    rec_id = str(uuid.uuid4())
    secret_pii = "999-88-7777"

    # We manually wrap using old_mock_key
    from utils.encryption import generate_dek, wrap_dek, zeroize
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os

    dek = generate_dek()
    iv = os.urandom(12)
    aad = f"{user_id_str}:{rec_id}".encode("utf-8")
    aesgcm = AESGCM(bytes(dek))
    ct = aesgcm.encrypt(iv, secret_pii.encode("utf-8"), aad)
    enc_pii, tag = ct[:-16], ct[-16:]
    wrapped = wrap_dek(dek, mock_kek=old_mock_key)
    zeroize(dek)

    record = KYCRecord(
        id=uuid.UUID(rec_id),
        user_id=uuid.UUID(user_id_str),
        encrypted_pii=enc_pii,
        wrapped_dek=wrapped,
        encryption_iv=iv,
        auth_tag=tag
    )
    kyc_db.add(record)
    kyc_db.commit()

    # Rotate
    rotated = batch_rotate_kyc_deks(kyc_db, old_mock_kek=old_mock_key, new_mock_kek=new_mock_key)
    assert rotated == 1

    # Verify decrypt with new key succeeds
    updated_rec = kyc_db.get(KYCRecord, uuid.UUID(rec_id))
    decrypted = decrypt_pii(
        updated_rec.encrypted_pii,
        updated_rec.wrapped_dek,
        updated_rec.encryption_iv,
        updated_rec.auth_tag,
        user_id_str,
        rec_id,
        mock_kek=new_mock_key
    )
    assert decrypted == secret_pii
