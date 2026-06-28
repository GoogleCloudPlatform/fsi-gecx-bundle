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

import os
import logging
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud import kms
from google.api_core.exceptions import GoogleAPICallError

from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

PROJECT_ID = get_project_id()
KMS_KEY_NAME = os.getenv(
    "KMS_KEK_RESOURCE_NAME",
    f"projects/{PROJECT_ID}/locations/global/keyRings/banking-keyring/cryptoKeys/kyc-kek"
)

# Mock KEK for local testing when KMS is unreachable or disabled
_MOCK_LOCAL_KEK = b"0123456789abcdef0123456789abcdef"

try:
    _kms_client = kms.KeyManagementServiceClient()
except Exception as e:
    logger.warning(f"Could not initialize KeyManagementServiceClient: {e}")
    _kms_client = None


def zeroize(buffer: bytearray) -> None:
    """Explicitly overwrites sensitive memory buffer elements with zeros."""
    if isinstance(buffer, bytearray):
        for i in range(len(buffer)):
            buffer[i] = 0


def generate_dek() -> bytearray:
    """Generates an ephemeral 256-bit (32-byte) AES-GCM Data Encryption Key."""
    return bytearray(os.urandom(32))


def wrap_dek(dek: bytes | bytearray, kek_name: str | None = None, mock_kek: bytes | None = None) -> bytes:
    """Wraps (encrypts) the ephemeral DEK using Google Cloud KMS KEK."""
    key_to_use = kek_name or KMS_KEY_NAME
    if _kms_client and os.getenv("USE_REAL_KMS") == "true" and not mock_kek:
        try:
            response = _kms_client.encrypt(
                request={"name": key_to_use, "plaintext": bytes(dek)}
            )
            return response.ciphertext
        except GoogleAPICallError as e:
            logger.error(f"KMS encryption call failed: {e}")
            raise RuntimeError("Failed to wrap DEK via Cloud KMS") from e
    else:
        # Mock envelope wrapping for local tests / offline mode
        local_key = mock_kek or _MOCK_LOCAL_KEK
        aesgcm = AESGCM(local_key)
        nonce = b"mocknonce123"
        return nonce + aesgcm.encrypt(nonce, bytes(dek), b"wrap_aad")


def unwrap_dek(wrapped_dek: bytes, kek_name: str | None = None, mock_kek: bytes | None = None) -> bytearray:
    """Unwraps (decrypts) the wrapped DEK using Google Cloud KMS KEK."""
    key_to_use = kek_name or KMS_KEY_NAME
    if _kms_client and os.getenv("USE_REAL_KMS") == "true" and not mock_kek:
        try:
            response = _kms_client.decrypt(
                request={"name": key_to_use, "ciphertext": wrapped_dek}
            )
            return bytearray(response.plaintext)
        except GoogleAPICallError as e:
            logger.error(f"KMS decryption call failed: {e}")
            raise RuntimeError("Failed to unwrap DEK via Cloud KMS") from e
    else:
        local_key = mock_kek or _MOCK_LOCAL_KEK
        aesgcm = AESGCM(local_key)
        nonce = wrapped_dek[:12]
        ciphertext = wrapped_dek[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, b"wrap_aad")
        return bytearray(plaintext)


def encrypt_pii(plaintext_pii: str, user_id: str, record_id: str, kek_name: str | None = None, mock_kek: bytes | None = None) -> Tuple[bytes, bytes, bytes, bytes]:
    """
    Encrypts sensitive PII string using AES-256-GCM envelope encryption with AAD binding.
    Returns (encrypted_pii, wrapped_dek, encryption_iv, auth_tag).
    Explicitly zeroizes plaintext memory buffers before returning.
    """
    dek_buffer = generate_dek()
    pii_buffer = bytearray(plaintext_pii.encode("utf-8"))
    
    try:
        iv = os.urandom(12)
        aad = f"{user_id}:{record_id}".encode("utf-8")
        
        aesgcm = AESGCM(bytes(dek_buffer))
        ciphertext_and_tag = aesgcm.encrypt(iv, bytes(pii_buffer), aad)
        
        # In AESGCM, auth tag is the final 16 bytes
        encrypted_pii = ciphertext_and_tag[:-16]
        auth_tag = ciphertext_and_tag[-16:]
        
        wrapped_dek = wrap_dek(dek_buffer, kek_name=kek_name, mock_kek=mock_kek)
        return encrypted_pii, wrapped_dek, iv, auth_tag
    finally:
        zeroize(dek_buffer)
        zeroize(pii_buffer)


def decrypt_pii(encrypted_pii: bytes, wrapped_dek: bytes, iv: bytes, auth_tag: bytes, user_id: str, record_id: str, kek_name: str | None = None, mock_kek: bytes | None = None) -> str:
    """
    Decrypts sensitive PII bytes using unwrapped DEK and verifies GCM tag and AAD binding.
    Explicitly zeroizes unwrapped DEK and plaintext output buffer before returning string.
    """
    dek_buffer = unwrap_dek(wrapped_dek, kek_name=kek_name, mock_kek=mock_kek)
    plaintext_buffer = None
    
    try:
        aad = f"{user_id}:{record_id}".encode("utf-8")
        aesgcm = AESGCM(bytes(dek_buffer))
        
        combined_payload = encrypted_pii + auth_tag
        decrypted_bytes = aesgcm.decrypt(iv, combined_payload, aad)
        plaintext_buffer = bytearray(decrypted_bytes)
        
        result_str = plaintext_buffer.decode("utf-8")
        return result_str
    finally:
        zeroize(dek_buffer)
        if plaintext_buffer is not None:
            zeroize(plaintext_buffer)


def rotate_record_dek(
    wrapped_dek: bytes,
    old_kek_name: str | None = None,
    old_mock_kek: bytes | None = None,
    new_kek_name: str | None = None,
    new_mock_kek: bytes | None = None
) -> bytes:
    """
    Unwraps a DEK with an existing/legacy KEK and re-wraps it with a target KEK.
    Zeroizes plaintext buffer in memory.
    """
    dek_buffer = unwrap_dek(wrapped_dek, kek_name=old_kek_name, mock_kek=old_mock_kek)
    try:
        return wrap_dek(dek_buffer, kek_name=new_kek_name, mock_kek=new_mock_kek)
    finally:
        zeroize(dek_buffer)
