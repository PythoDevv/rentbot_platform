from app.services.tenant_db import generate_database_name, normalize_import_row, parse_user_import


def test_generate_database_name_is_safe() -> None:
    name = generate_database_name("My Super Bot!!!")

    assert name.startswith("bot_my_super_bot_")
    assert "!" not in name
    assert len(name) <= 64


def test_normalize_import_row_supports_legacy_json_keys() -> None:
    row = normalize_import_row(
        {
            "full_name": "Ali Valiyev",
            "username": "ali",
            "phone": "+998901234567",
            "score": "12",
            "tg_id": "12345",
        }
    )

    assert row == {
        "full_name": "Ali Valiyev",
        "username": "ali",
        "phone": "+998901234567",
        "score": 12,
        "oldd": None,
        "telegram_id": 12345,
        "user_args": None,
    }


def test_parse_user_import_accepts_csv() -> None:
    payload = (
        "full_name,username,phone,score,telegram_id,user_args\n"
        "Ali,ali,+99890,7,123,start\n"
    ).encode("utf-8")

    rows = parse_user_import("users.csv", payload)

    assert rows == [
        {
            "full_name": "Ali",
            "username": "ali",
            "phone": "+99890",
            "score": 7,
            "oldd": None,
            "telegram_id": 123,
            "user_args": "start",
        }
    ]
