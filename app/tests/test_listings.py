from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class FakeListing:
    def __init__(self, seller_uid="seller-uid-123", sold=False):
        self.id = 1
        self.price = 50.0
        self.spot_in_queue = 3
        self.lat = 40.7128
        self.lng = -74.0060
        self.seller_uid = seller_uid
        self.sold = sold


# --- Get Listings ---

def test_get_listings(override_db):
    override_db.query.return_value.filter.return_value.all.return_value = [FakeListing()]

    response = client.get("/listings")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["price"] == 50.0
    assert response.json()[0]["sold"] == False


def test_get_listings_empty(override_db):
    override_db.query.return_value.filter.return_value.all.return_value = []

    response = client.get("/listings")

    assert response.status_code == 200
    assert response.json() == []


# --- Get My Listings ---

def test_get_my_listings(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    override_db.query.return_value.filter.return_value.first.return_value = mock_user
    override_db.query.return_value.filter.return_value.all.return_value = [FakeListing()]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/listings/mine?token=fake-token")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["price"] == 50.0


# --- Get Listing by ID ---

def test_get_listing(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = FakeListing()

    response = client.get("/listings/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["price"] == 50.0


def test_get_listing_not_found(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    response = client.get("/listings/999")

    assert response.status_code == 404


# --- Delete Listing ---

def test_delete_listing(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, FakeListing()]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.delete("/listings/1?token=fake-token")

    assert response.status_code == 200
    assert response.json()["detail"] == "Listing deleted"


def test_delete_listing_not_found(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.delete("/listings/999?token=fake-token")

    assert response.status_code == 404


def test_delete_listing_wrong_user(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, FakeListing(seller_uid="seller-uid-123")]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.delete("/listings/1?token=fake-token")

    assert response.status_code == 403