from app.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password = "super-secret-password"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)
