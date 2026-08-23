from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)



# --- Signup ---

def test_signup(override_db):
    mock_fb_user = MagicMock()
    mock_fb_user.uid = "test-uid-123"

    with patch('app.data.users.firebase_signup', return_value=mock_fb_user):
        response = client.post("/signup", json={
            "email": "test@example.com",
            "password": "Test123!",
            "phone": "914-343-4288"
        })

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+19143434288"
    assert "firebase_uid" not in response.json()


def test_signup_invalid_phone():
    response = client.post("/signup", json={
        "email": "test@example.com",
        "password": "Test123!",
        "phone": "notaphone"
    })
    assert response.status_code == 422


# --- Login ---

def test_login(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.name = "Justin"
    mock_user.phone_number = "+19143434288"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.main.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/login?token=fake-token")

    assert response.status_code == 200
    assert "firebase_uid" not in response.json()


def test_login_user_not_found(override_db):
    mock_decoded = {"uid": "nonexistent-uid"}

    with patch('app.main.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/login?token=fake-token")

    assert response.status_code == 404


# --- Delete ---

def test_delete_user(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.main.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.main.firebase_auth.delete_user') as mock_delete:
        response = client.delete("/delete_user?token=fake-token")

    assert response.status_code == 200
    assert response.json() == {"user": "DELETED"}
    mock_delete.assert_called_once_with("test-uid-123")


def test_delete_user_not_found(override_db):
    mock_decoded = {"uid": "nonexistent-uid"}

    with patch('app.main.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.delete("/delete_user?token=fake-token")

    assert response.status_code == 404


# --- Update Name ---

def test_update_name(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.name = "Justin"
    mock_user.phone_number = "+19143434288"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.main.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/update_name?token=fake-token", json={"name": "Justin"})

    assert response.status_code == 200
    assert response.json()["name"] == "Justin"


# --- Create Listing ---

def test_create_listing(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    mock_listing = MagicMock()
    mock_listing.id = 1
    mock_listing.price = 50.0
    mock_listing.spot_in_queue = 3
    mock_listing.lat = 40.7128
    mock_listing.lng = -74.0060
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.Listing', return_value=mock_listing):
        response = client.post("/create_listing?token=fake-token", json={
            "price": 50.0,
            "lat": 40.7128,
            "lng": -74.0060,
            "spot_in_queue": 3
        })

    assert response.status_code == 200
    assert response.json()["price"] == 50.0
    assert response.json()["lat"] == 40.7128
    assert response.json()["spot_in_queue"] == 3
