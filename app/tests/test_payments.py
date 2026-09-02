import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.models import TransactionStatus

client = TestClient(app)


class FakeTransaction:
    """Simple object with a real __dict__ so {**transaction.__dict__} works in endpoints."""
    def __init__(self, seller_uid="seller-uid-123", status=TransactionStatus.pending, qr_expires_at=None):
        self.listing_id = 1
        self.buyer_uid = "buyer-uid-123"
        self.seller_uid = seller_uid
        self.price = 50.0
        self.created_at = datetime(2026, 8, 23)
        self.stripe_payment_intent_id = "pi_test_123"
        self.status = status
        self.qr_expires_at = qr_expires_at


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
         patch('app.data.payments.client.v2.core.accounts.create', return_value=mock_account), \
         patch('app.data.payments.client.v2.core.account_links.create', return_value=mock_link):
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
         patch('app.data.payments.client.v2.core.accounts.create') as mock_create, \
         patch('app.data.payments.client.v2.core.account_links.create', return_value=mock_link):
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

    # user (CurrentUser), listing, None (no existing transaction)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_listing, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.create', return_value=mock_intent), \
         patch('app.data.payments.Transaction', return_value=mock_transaction):
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 200
    assert response.json()["client_secret"] == "pi_test_123_secret_key"
    assert response.json()["price"] == 50.0
    assert response.json()["stripe_payment_intent_id"] == "pi_test_123"


def test_start_transaction_stripe_failure(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_listing = MagicMock()
    mock_listing.id = 1
    mock_listing.price = 50.0
    mock_listing.seller.stripe_account_id = "acct_seller_123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_listing, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.create', side_effect=Exception("Stripe error")), \
         patch('app.data.payments.client.v1.payment_intents.cancel') as mock_cancel:
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 400
    mock_cancel.assert_not_called()


def test_start_transaction_db_failure_cancels_intent(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_listing = MagicMock()
    mock_listing.id = 1
    mock_listing.price = 50.0
    mock_listing.seller.stripe_account_id = "acct_seller_123"

    mock_intent = MagicMock()
    mock_intent.id = "pi_test_123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_listing, None]
    override_db.commit.side_effect = Exception("DB error")

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.create', return_value=mock_intent), \
         patch('app.data.payments.client.v1.payment_intents.cancel') as mock_cancel:
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 400
    mock_cancel.assert_called_once_with("pi_test_123")


def test_start_transaction_listing_already_taken(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_listing = MagicMock()
    mock_listing.id = 1
    existing_transaction = FakeTransaction(status=TransactionStatus.paid)

    # user, listing, existing paid transaction found
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_listing, existing_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/start_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 400


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

    mock_transaction = FakeTransaction(seller_uid="seller-uid-123", status=TransactionStatus.paid)
    mock_listing = MagicMock()
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction, mock_listing]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.capture') as mock_capture:
        response = client.post("/confirm_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 200
    mock_capture.assert_called_once_with("pi_test_123")
    assert mock_listing.sold == True


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


# --- Abandon Transaction ---

def test_abandon_transaction(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    mock_transaction = FakeTransaction(status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.client.v1.payment_intents.cancel') as mock_cancel:
        response = client.post("/abandon_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 200
    mock_cancel.assert_called_once_with("pi_test_123")
    assert mock_transaction.status == TransactionStatus.cancelled


def test_abandon_transaction_not_found(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/abandon_transaction?token=fake-token", json={"listing_id": 999})

    assert response.status_code == 404


def test_abandon_transaction_wrong_user(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    mock_transaction = FakeTransaction(status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/abandon_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 403


def test_abandon_transaction_not_pending(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    mock_transaction = FakeTransaction(status=TransactionStatus.paid)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.post("/abandon_transaction?token=fake-token", json={"listing_id": 1})

    assert response.status_code == 400


# --- Transaction History ---

def test_get_sold_transactions(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    mock_transaction = FakeTransaction(seller_uid="seller-uid-123", status=TransactionStatus.completed)
    override_db.query.return_value.filter.return_value.first.return_value = mock_user
    override_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/sold?token=fake-token")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["seller_uid"] == "seller-uid-123"


def test_get_sold_transactions_empty(override_db):
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    override_db.query.return_value.filter.return_value.first.return_value = mock_user
    override_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/sold?token=fake-token")

    assert response.status_code == 200
    assert response.json() == []


def test_get_bought_transactions(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    mock_transaction = FakeTransaction(status=TransactionStatus.completed)
    override_db.query.return_value.filter.return_value.first.return_value = mock_user
    override_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/bought?token=fake-token")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["buyer_uid"] == "buyer-uid-123"


def test_get_bought_transactions_empty(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    override_db.query.return_value.filter.return_value.first.return_value = mock_user
    override_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/bought?token=fake-token")

    assert response.status_code == 200
    assert response.json() == []


# --- Get QR ---

def test_get_qr_success(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    future = datetime.now(timezone.utc) + timedelta(hours=2)
    mock_transaction = FakeTransaction(status=TransactionStatus.paid, qr_expires_at=future)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    mock_img = MagicMock()
    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded), \
         patch('app.data.payments.qrcode.make', return_value=mock_img):
        response = client.get("/transactions/1/qr?token=fake-token")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_get_qr_expired(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_transaction = FakeTransaction(status=TransactionStatus.paid, qr_expires_at=past)
    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_transaction]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/1/qr?token=fake-token")

    assert response.status_code == 410


def test_get_qr_not_found(override_db):
    mock_decoded = {"uid": "buyer-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "buyer-uid-123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/999/qr?token=fake-token")

    assert response.status_code == 404


def test_get_qr_wrong_user(override_db):
    """Seller tries to fetch buyer's QR — no matching transaction returned."""
    mock_decoded = {"uid": "seller-uid-123"}
    mock_user = MagicMock()
    mock_user.firebase_uid = "seller-uid-123"

    override_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]

    with patch('app.models.auth.firebase_auth.verify_id_token', return_value=mock_decoded):
        response = client.get("/transactions/1/qr?token=fake-token")

    assert response.status_code == 404


# --- Webhook ---

def _make_webhook_event(event_type, obj):
    mock_event = MagicMock()
    mock_event.to_dict.return_value = {"type": event_type, "data": {"object": obj}}
    return mock_event


def test_webhook_payment_intent_canceled_pending(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    mock_event = _make_webhook_event("payment_intent.canceled", {"id": "pi_test_123"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.cancelled


def test_webhook_payment_intent_canceled_paid(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.paid)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    mock_event = _make_webhook_event("payment_intent.canceled", {"id": "pi_test_123"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.cancelled


def test_webhook_payment_intent_canceled_no_match(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    mock_event = _make_webhook_event("payment_intent.canceled", {"id": "pi_unknown"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200


def test_webhook_amount_capturable_updated(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    mock_event = _make_webhook_event("payment_intent.amount_capturable_updated", {"id": "pi_test_123"})
    before = datetime.now(timezone.utc)
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.paid
    assert mock_transaction.qr_expires_at > before
    assert mock_transaction.qr_expires_at.tzinfo is not None


def test_webhook_amount_capturable_updated_no_match(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    mock_event = _make_webhook_event("payment_intent.amount_capturable_updated", {"id": "pi_unknown"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200

def test_webhook_payment_failed(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.pending)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    mock_event = _make_webhook_event("payment_intent.payment_failed", {"id": "pi_test_123"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.cancelled


def test_webhook_payment_failed_no_match(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    mock_event = _make_webhook_event("payment_intent.payment_failed", {"id": "pi_unknown"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200


def test_webhook_charge_refunded(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.completed)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    mock_event = _make_webhook_event("charge.refunded", {"payment_intent": "pi_test_123"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.refunded


def test_webhook_charge_refunded_no_match(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    mock_event = _make_webhook_event("charge.refunded", {"payment_intent": "pi_unknown"})
    with patch('app.data.payments.stripe.Webhook.construct_event', return_value=mock_event):
        response = client.post("/webhook", content=b"payload", headers={"stripe-signature": "sig"})

    assert response.status_code == 200


# --- Refund Transaction ---

ADMIN_HEADERS = {"x-admin-key": "test-admin-key"}


def test_refund_transaction(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.completed)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    with patch.dict(os.environ, {"ADMIN_KEY": "test-admin-key"}), \
         patch('app.data.payments.client.v1.refunds.create') as mock_refund:
        response = client.post("/refund_transaction", json={"listing_id": 1}, headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert mock_transaction.status == TransactionStatus.refunded
    mock_refund.assert_called_once_with({
        'payment_intent': 'pi_test_123',
        'reverse_transfer': True,
        'refund_application_fee': True,
    })


def test_refund_transaction_not_found(override_db):
    override_db.query.return_value.filter.return_value.first.return_value = None

    with patch.dict(os.environ, {"ADMIN_KEY": "test-admin-key"}):
        response = client.post("/refund_transaction", json={"listing_id": 999}, headers=ADMIN_HEADERS)

    assert response.status_code == 404


def test_refund_transaction_not_completed(override_db):
    mock_transaction = FakeTransaction(status=TransactionStatus.paid)
    override_db.query.return_value.filter.return_value.first.return_value = mock_transaction

    with patch.dict(os.environ, {"ADMIN_KEY": "test-admin-key"}):
        response = client.post("/refund_transaction", json={"listing_id": 1}, headers=ADMIN_HEADERS)

    assert response.status_code == 400


def test_refund_transaction_no_admin_key(override_db):
    with patch.dict(os.environ, {"ADMIN_KEY": "test-admin-key"}):
        response = client.post("/refund_transaction", json={"listing_id": 1})

    assert response.status_code == 403