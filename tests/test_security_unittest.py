import unittest

from app.security import hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip(self) -> None:
        password = "super-secret-password"
        password_hash = hash_password(password)

        self.assertNotEqual(password_hash, password)
        self.assertTrue(verify_password(password, password_hash))


if __name__ == "__main__":
    unittest.main()
