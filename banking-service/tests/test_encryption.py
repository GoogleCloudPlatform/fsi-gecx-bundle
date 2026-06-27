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

import pytest
from cryptography.exceptions import InvalidTag
from utils.encryption import encrypt_pii, decrypt_pii, zeroize, generate_dek


def test_encryption_and_decryption_success():
    secret_pii = "SSN: 999-00-1234, DOB: 1985-10-25"
    user_id = "user_abc_123"
    record_id = "rec_xyz_789"

    enc_pii, wrapped_dek, iv, tag = encrypt_pii(secret_pii, user_id, record_id)

    # Ensure ciphertext is not plaintext
    assert secret_pii.encode("utf-8") not in enc_pii
    assert len(iv) == 12
    assert len(tag) == 16

    decrypted = decrypt_pii(enc_pii, wrapped_dek, iv, tag, user_id, record_id)
    assert decrypted == secret_pii


def test_splicing_immunity_aad_mismatch():
    secret_pii = "Confidential Tax ID: 12-3456789"
    user_a = "user_A"
    record_a = "record_A"

    enc_pii, wrapped_dek, iv, tag = encrypt_pii(secret_pii, user_a, record_a)

    # Attempt to decrypt under User B's context (transplanting ciphertext)
    user_b = "user_B"
    with pytest.raises(InvalidTag):
        decrypt_pii(enc_pii, wrapped_dek, iv, tag, user_b, record_a)

    # Attempt to decrypt under wrong record ID
    with pytest.raises(InvalidTag):
        decrypt_pii(enc_pii, wrapped_dek, iv, tag, user_a, "record_B")


def test_tampering_immunity():
    secret_pii = "Sensitive DOB"
    user_id = "user_1"
    record_id = "rec_1"

    enc_pii, wrapped_dek, iv, tag = encrypt_pii(secret_pii, user_id, record_id)

    # Tamper with 1 byte of encrypted PII
    tampered_pii = bytearray(enc_pii)
    tampered_pii[0] ^= 0x01

    with pytest.raises(InvalidTag):
        decrypt_pii(bytes(tampered_pii), wrapped_dek, iv, tag, user_id, record_id)


def test_memory_zeroization():
    dek = generate_dek()
    assert any(b != 0 for b in dek)
    
    zeroize(dek)
    assert all(b == 0 for b in dek)
