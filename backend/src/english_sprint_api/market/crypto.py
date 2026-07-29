from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from english_sprint_api.pedagogy.content_store import decode_content_key


class FieldEncryptor:
    def __init__(self, encoded_key: str, key_version: str) -> None:
        self._cipher = AESGCM(decode_content_key(encoded_key))
        self.key_version = key_version

    def encrypt(self, identity: str, value: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, value.encode(), identity.encode())
        return json.dumps(
            {
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
                "nonce": base64.urlsafe_b64encode(nonce).decode(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    def decrypt(self, identity: str, value: str) -> str:
        envelope = json.loads(value)
        nonce = base64.urlsafe_b64decode(envelope["nonce"])
        ciphertext = base64.urlsafe_b64decode(envelope["ciphertext"])
        return self._cipher.decrypt(nonce, ciphertext, identity.encode()).decode()
