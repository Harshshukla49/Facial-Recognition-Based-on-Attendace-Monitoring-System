import unittest
from core.security import SecurityService

class TestSecurityRBAC(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        plain = "SuperSecretPassword2026!"
        hashed = SecurityService.hash_password(plain)
        
        self.assertTrue(SecurityService.verify_password(plain, hashed))
        self.assertFalse(SecurityService.verify_password("WrongPassword", hashed))

    def test_jwt_token_flow(self):
        payload = {"user_id": 42, "role": "ADMIN", "email": "admin@institution.edu"}
        token = SecurityService.create_jwt_token(payload, expires_in_hours=1)
        
        decoded = SecurityService.verify_jwt_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["user_id"], 42)
        self.assertEqual(decoded["role"], "ADMIN")

    def test_biometric_vector_encryption_decryption(self):
        vector = [0.1234, -0.5678, 0.9999, 0.0] * 32  # 128 elements
        encrypted_str = SecurityService.encrypt_biometric_vector(vector)
        
        self.assertIsInstance(encrypted_str, str)
        self.assertNotEqual(encrypted_str, str(vector))
        
        decrypted_vector = SecurityService.decrypt_biometric_vector(encrypted_str)
        self.assertIsNotNone(decrypted_vector)
        self.assertEqual(len(decrypted_vector), 128)
        self.assertAlmostEqual(decrypted_vector[0], 0.1234, places=3)

if __name__ == "__main__":
    unittest.main()
