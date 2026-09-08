import os
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional, Tuple
from config import Config

class SecurityService:
    """Enterprise security service for hashing, JWT handling, and biometric encryption."""
    
    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> str:
        """Hashes a password with PBKDF2-HMAC-SHA256 and a cryptographically secure salt."""
        if not salt:
            salt = os.urandom(16).hex()
        # 100,000 iterations PBKDF2
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return f"pbkdf2:sha256:100000${salt}${key.hex()}"
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verifies a plain password against a stored PBKDF2 hash."""
        try:
            if not hashed or '$' not in hashed:
                # Support legacy plain text fallback check for seamless migration
                return password == hashed
            parts = hashed.split('$')
            if len(parts) != 3:
                return False
            _, salt, original_hex = parts
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hmac.compare_digest(key.hex(), original_hex)
        except Exception:
            return False

    @staticmethod
    def create_jwt_token(payload: Dict[str, Any], expires_in_hours: int = Config.JWT_EXPIRATION_HOURS) -> str:
        """Generates a signed JWT access token."""
        header = {"alg": "HS256", "typ": "JWT"}
        exp_time = int(time.time()) + (expires_in_hours * 3600)
        token_payload = payload.copy()
        token_payload["exp"] = exp_time
        token_payload["iat"] = int(time.time())

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode('utf-8')).decode('utf-8').rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(token_payload).encode('utf-8')).decode('utf-8').rstrip('=')

        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            Config.JWT_SECRET_KEY.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')

        return f"{message}.{sig_b64}"

    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
        """Verifies and decodes a signed JWT access token."""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None
            header_b64, payload_b64, sig_b64 = parts

            message = f"{header_b64}.{payload_b64}"
            expected_sig = hmac.new(
                Config.JWT_SECRET_KEY.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode('utf-8').rstrip('=')

            if not hmac.compare_digest(sig_b64, expected_sig_b64):
                return None

            # Add padding back if necessary
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += '=' * (4 - rem)

            payload_data = json.loads(base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8'))
            
            # Check expiration
            if payload_data.get("exp", 0) < time.time():
                return None

            return payload_data
        except Exception:
            return None

    @staticmethod
    def encrypt_biometric_vector(vector_floats: list) -> str:
        """
        Encrypts sensitive facial embedding vector using AES-like XOR-CTR stream cipher
        with HMAC-SHA256 authentication (Privacy-By-Design).
        """
        raw_json = json.dumps(vector_floats).encode('utf-8')
        iv = os.urandom(16)
        
        # Keystream generator using HMAC-SHA256 over counter blocks
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(raw_json):
            block = hmac.new(
                Config.BIOMETRIC_ENCRYPTION_KEY,
                iv + counter.to_bytes(4, 'big'),
                hashlib.sha256
            ).digest()
            keystream.extend(block)
            counter += 1

        encrypted_bytes = bytes(a ^ b for a, b in zip(raw_json, keystream[:len(raw_json)]))
        
        # Calculate HMAC tag for integrity
        mac = hmac.new(
            Config.BIOMETRIC_ENCRYPTION_KEY,
            iv + encrypted_bytes,
            hashlib.sha256
        ).digest()

        payload = iv + mac + encrypted_bytes
        return base64.b64encode(payload).decode('utf-8')

    @staticmethod
    def decrypt_biometric_vector(encrypted_str: str) -> Optional[list]:
        """Decrypts and validates the encrypted biometric vector."""
        try:
            payload = base64.b64decode(encrypted_str.encode('utf-8'))
            if len(payload) < 48:  # 16 IV + 32 MAC
                return None
            iv = payload[:16]
            mac = payload[16:48]
            encrypted_bytes = payload[48:]

            # Verify MAC
            expected_mac = hmac.new(
                Config.BIOMETRIC_ENCRYPTION_KEY,
                iv + encrypted_bytes,
                hashlib.sha256
            ).digest()

            if not hmac.compare_digest(mac, expected_mac):
                return None

            keystream = bytearray()
            counter = 0
            while len(keystream) < len(encrypted_bytes):
                block = hmac.new(
                    Config.BIOMETRIC_ENCRYPTION_KEY,
                    iv + counter.to_bytes(4, 'big'),
                    hashlib.sha256
                ).digest()
                keystream.extend(block)
                counter += 1

            decrypted_raw = bytes(a ^ b for a, b in zip(encrypted_bytes, keystream[:len(encrypted_bytes)]))
            return json.loads(decrypted_raw.decode('utf-8'))
        except Exception as e:
            print(f"Biometric decryption error: {e}")
            return None
