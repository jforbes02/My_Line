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


# --- Register ---

def test_register(override_db):
    mock_decoded = {"uid": "phone-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "phone-uid-123"
    mock_user.phone_number = "+19143434288"
    mock_user.name = None
    # first call (CurrentUser) returns the Firebase-verified user, second (existing check) returns None
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/register?token=fake-token", json={"phone": "914-343-4288"})

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+19143434288"


def test_register_already_exists(override_db):
    mock_decoded = {"uid": "phone-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "phone-uid-123"
    # both calls return a user — existing check finds one
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_user]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/register?token=fake-token", json={"phone": "914-343-4288"})

    assert response.status_code == 400


# --- Login ---

def test_login(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.name = "Justin"
    mock_user.phone_number = "+19143434288"
    mock_user.email = None
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.data.users.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/login?token=fake-token")

    assert response.status_code == 200
    assert "firebase_uid" not in response.json()


def test_login_user_not_found(override_db):
    mock_decoded = {"uid": "nonexistent-uid"}

    with patch('app.data.users.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/login?token=fake-token")

    assert response.status_code == 404


# --- Delete ---

def test_delete_user(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.data.users.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.users.firebase_auth.delete_user') as mock_delete:
        response = client.delete("/delete_user?token=fake-token")

    assert response.status_code == 200
    assert response.json() == {"user": "DELETED"}
    mock_delete.assert_called_once_with("test-uid-123")


def test_delete_user_not_found(override_db):
    mock_decoded = {"uid": "nonexistent-uid"}

    with patch('app.data.users.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.delete("/delete_user?token=fake-token")

    assert response.status_code == 404


# --- Update Name ---

def test_update_name(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.name = "Justin"
    mock_user.phone_number = "+19143434288"
    mock_user.email = None
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.data.users.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/update_name?token=fake-token", json={"name": "Justin"})

    assert response.status_code == 200
    assert response.json()["name"] == "Justin"


# --- Update Email ---

def test_update_email(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    mock_user.name = "Justin"
    mock_user.phone_number = "+19143434288"
    mock_user.email = "old@example.com"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.users.firebase_auth.update_user') as mock_fb_update:
        response = client.post("/update_email?token=fake-token", json={"email": "new@example.com"})

    assert response.status_code == 200
    assert mock_user.email == "new@example.com"
    mock_fb_update.assert_called_once_with("test-uid-123", email="new@example.com")


def test_update_email_firebase_error(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.users.firebase_auth.update_user', side_effect=Exception("Firebase error")):
        response = client.post("/update_email?token=fake-token", json={"email": "new@example.com"})

    assert response.status_code == 500


# --- Create Listing ---

def test_create_listing(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "test-uid-123"
    mock_user.stripe_onboarded = True
    mock_listing = MagicMock()
    mock_listing.id = 1
    mock_listing.price = 50.0
    mock_listing.spot_in_queue = 3
    mock_listing.lat = 40.7128
    mock_listing.lng = -74.0060
    mock_listing.sold = False

    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.listings.Listing', return_value=mock_listing):
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
    assert response.json()["sold"] == False


def test_create_listing_not_onboarded(override_db):
    mock_decoded = {"uid": "test-uid-123"}
    mock_user = MagicMock()
    mock_user.stripe_onboarded = False
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/create_listing?token=fake-token", json={
            "price": 50.0,
            "lat": 40.7128,
            "lng": -74.0060,
            "spot_in_queue": 3
        })

    assert response.status_code == 400
