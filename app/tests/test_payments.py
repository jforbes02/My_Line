from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.models import TransactionStatus

client = TestClient(app)


class FakeTransaction:
    """Simple object with a real __dict__ so {**transaction.__dict__} works in endpoints."""
    def __init__(self, seller_uid="seller-uid-123", status=TransactionStatus.pending):
        self.listing_id = 1
        self.buyer_uid = "buyer-uid-123"
        self.seller_uid = seller_uid
        self.price = 50.0
        self.created_at = datetime(2026, 8, 23)
        self.stripe_payment_intent_id = "pi_test_123"
        self.status = status


# --- Onboard Seller ---

def test_onboard_seller_new_account(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.stripe_account_id = None
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_account = MagicMock()
    mock_account.id = "acct_test_123"
    mock_link = MagicMock()
    mock_link.url = "https://connect.stripe.com/setup/test"

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.accounts.create', return_value=mock_account), \
         patch('app.data.payments.client.v1.account_links.create', return_value=mock_link):
        response = client.post("/onboard_seller?token=fake-token")

    assert response.status_code == 200
    assert response.json()["url"] == "https://connect.stripe.com/setup/test"
    assert mock_user.stripe_account_id == "acct_test_123"


def test_onboard_seller_existing_account(override_db):
    """User already has a stripe_account_id — skips account creation, returns fresh link."""
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.stripe_account_id = "acct_existing_123"
    override_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_link = MagicMock()
    mock_link.url = "https://connect.stripe.com/setup/existing"

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.accounts.create') as mock_create, \
         patch('app.data.payments.client.v1.account_links.create', return_value=mock_link):
        response = client.post("/onboard_seller?token=fake-token")

    assert response.status_code == 200
    assert response.json()["url"] == "https://connect.stripe.com/setup/existing"
    mock_create.assert_not_called()


# --- Start Transaction ---

def test_start_transaction(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    mock_listing = MagicMock()
    mock_listing.id = 1
    mock_listing.price = 50.0
    mock_listing.seller_uid = "seller-uid-123"
    mock_listing.seller.stripe_account_id = "acct_seller_123"

    mock_intent = MagicMock()
    mock_intent.id = "pi_test_123"
    mock_intent.client_secret = "pi_test_123_secret_key"

    mock_transaction = FakeTransaction()

    # first call returns user (for CurrentUser), second returns listing (for start_transaction)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_listing]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.create', return_value=mock_intent), \
         patch('app.data.payments.Transaction', return_value=mock_transaction):
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 200
    assert response.json()["client_secret"] == "pi_test_123_secret_key"
    assert response.json()["price"] == 50.0
    assert response.json()["stripe_payment_intent_id"] == "pi_test_123"


def test_start_transaction_listing_not_found(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 999})

    assert response.status_code == 404


# --- Confirm Transaction ---

def test_confirm_transaction(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    mock_transaction = FakeTransaction(seller_uid="seller-uid-123", status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.capture') as mock_capture:
        response = client.post("/confirm_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 200
    mock_capture.assert_called_once_with("pi_test_123")


def test_confirm_transaction_not_found(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/confirm_transaction?token=fake-token", json={"listing_id": 999})

    assert response.status_code == 404


def test_confirm_transaction_wrong_user(override_db):
    """Buyer tries to confirm — should be rejected."""
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    mock_transaction = FakeTransaction(seller_uid="seller-uid-123")
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/confirm_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 403


def test_confirm_transaction_already_completed(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    mock_transaction = FakeTransaction(seller_uid="seller-uid-123", status=TransactionStatus.completed)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/confirm_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 400