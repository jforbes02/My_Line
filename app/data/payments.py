import datetime
import io
import os
import qrcode
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from starlette.responses import StreamingResponse
from stripe import StripeClient
from typing import Annotated

from app.models.auth import CurrentUser
from app.models.db import mySession
from app.models.schemas import AccountCreate, OnboardSellerResponse, TransactionResponse, TransactionRequest, \
    ListingResponse, ListingRequest, AbandonTransactionResponse
from app.models.models import Listing, Transaction, TransactionStatus, User

client = StripeClient(os.getenv('STRIPE_API_KEY'))

router = APIRouter()


def verify_admin(x_admin_key: Annotated[str | None, Header()] = None):
    if not x_admin_key or x_admin_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail="Admin access required")

@router.post('/onboard_seller', response_model=OnboardSellerResponse)
def onboard_seller(db: mySession, user: CurrentUser, body: AccountCreate = AccountCreate()):
    if not user.email:
        raise HTTPException(status_code=400, detail="An email address is required to become a seller")

    if not user.stripe_account_id:
        try:
            # v2 accounts use configuration.recipient for separate charges & transfers payout flow.
            # dashboard="express" gives the seller a Stripe-hosted dashboard to manage payouts.
            params = {"display_name": user.name, "dashboard": "express", "identity": {
                "country": body.country,
                "entity_type": body.business_type,
            }, "configuration": {
                "recipient": {
                    "capabilities": {
                        "stripe_balance": {
                            "stripe_transfers": {"requested": True},
                        }
                    }
                }
            }, "defaults": {
                "responsibilities": {
                    "fees_collector": "application",
                    "losses_collector": "application",
                }
            }, "contact_email": user.email}

            account = client.v2.core.accounts.create(params)
            user.stripe_account_id = account.id
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    link = client.v2.core.account_links.create({
        "account": user.stripe_account_id,
        "use_case": {
            'type': "account_onboarding",
            "account_onboarding": {
                'configurations': ['recipient'],
                "return_url": "http://localhost:8000/onboarding/complete",
                "refresh_url": "http://localhost:8000/onboarding/refresh",
            },
        },
    })

    return {"url": link.url}



@router.post('/start_transaction', response_model=TransactionResponse)
def start_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    listing = db.query(Listing).filter(Listing.id == body.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    active = db.query(Transaction).filter(
        Transaction.listing_id == listing.id,
        Transaction.status.in_([TransactionStatus.paid, TransactionStatus.completed])
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Listing no longer available")

    intent = client.v1.payment_intents.create({
        'amount': int(listing.price * 100),
        'currency': 'usd',
        'capture_method': 'manual',
        'payment_method_types': ['card'],
        'transfer_data': {
            'destination': listing.seller.stripe_account_id,
        },
        'application_fee_amount': int(listing.price * 0.10 * 100),
    })

    try:
        transaction = Transaction(
            listing_id=listing.id,
            buyer_uid=user.firebase_uid,
            seller_uid=listing.seller_uid,
            price=listing.price,
            stripe_payment_intent_id=intent.id,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


    return {**transaction.__dict__, 'client_secret': intent.client_secret}

@router.post('/confirm_transaction', response_model=TransactionResponse)
def confirm_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    transaction = db.query(Transaction).filter(Transaction.listing_id == body.listing_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.seller_uid != user.firebase_uid:
        raise HTTPException(status_code=403, detail="Only the seller can confirm this transaction")

    if transaction.status == TransactionStatus.completed:
        raise HTTPException(status_code=400, detail="Transaction already completed")

    if transaction.status != TransactionStatus.paid:
        raise HTTPException(status_code=400, detail="Payment has not been confirmed yet")

    listing = db.query(Listing).filter(Listing.id == body.listing_id).first()

    try:
        client.v1.payment_intents.capture(transaction.stripe_payment_intent_id)
        transaction.status = TransactionStatus.completed
        listing.sold = True
        user.completed_transactions += 1
        db.commit()
        db.refresh(transaction)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return transaction.__dict__


@router.post('/webhook')
async def stripe_webhook(request: Request, db: mySession):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')

        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event_dict = event.to_dict()
        event_type = event_dict['type']
        obj = event_dict['data']['object']

        if event_type == 'capability.updated':
            if obj.get('status') == 'active':
                account_id = obj.get('account')
                if account_id:
                    user = db.query(User).filter(User.stripe_account_id == account_id).first()
                    if user and not user.stripe_onboarded:
                        user.stripe_onboarded = True
                        db.commit()

        elif event_type == 'payment_intent.amount_capturable_updated':
            payment_intent_id = obj.get('id')
            if payment_intent_id:
                transaction = db.query(Transaction).filter(
                    Transaction.stripe_payment_intent_id == payment_intent_id,
                    Transaction.status == TransactionStatus.pending
                ).first()
                if transaction:
                    transaction.status = TransactionStatus.paid
                    transaction.qr_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
                    db.commit()

        elif event_type == 'payment_intent.canceled':
            payment_intent_id = obj.get('id')
            if payment_intent_id:
                transaction = db.query(Transaction).filter(
                    Transaction.stripe_payment_intent_id == payment_intent_id,
                    Transaction.status.in_([TransactionStatus.pending, TransactionStatus.paid])
                ).first()
                if transaction:
                    transaction.status = TransactionStatus.cancelled
                    db.commit()

    except Exception as e:
        print(f"[webhook] ERROR: {e}")

    return {"status": "ok"}

@router.post('/abandon_transaction', response_model=AbandonTransactionResponse)
def abandon_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    transaction = db.query(Transaction).filter(Transaction.listing_id == body.listing_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.buyer_uid != user.firebase_uid:
        raise HTTPException(status_code=403, detail="Only the buyer can abandon this transaction")

    if transaction.status != TransactionStatus.pending:
        raise HTTPException(status_code=400, detail="Only a pending transaction can be abandoned")

    try:
        client.v1.payment_intents.cancel(transaction.stripe_payment_intent_id)
        transaction.status = TransactionStatus.cancelled
        db.commit()
        db.refresh(transaction)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return transaction.__dict__

@router.post('/refund_transaction', response_model=TransactionResponse, dependencies=[Depends(verify_admin)])
def refund_transaction(db: mySession, body: TransactionRequest):
    transaction = db.query(Transaction).filter(Transaction.listing_id == body.listing_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status != TransactionStatus.completed:
        raise HTTPException(status_code=400, detail="Only completed transactions can be refunded")

    try:
        client.v1.refunds.create({
            'payment_intent': transaction.stripe_payment_intent_id,
            'reverse_transfer': True,
            'refund_application_fee': True,
        })
        transaction.status = TransactionStatus.refunded
        db.commit()
        db.refresh(transaction)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return transaction.__dict__


@router.get('/transactions/sold', response_model=list[TransactionResponse])
def get_sold_transactions(db: mySession, user: CurrentUser):
    return db.query(Transaction).filter(
        Transaction.seller_uid == user.firebase_uid
    ).order_by(Transaction.created_at.desc()).all()


@router.get('/transactions/bought', response_model=list[TransactionResponse])
def get_bought_transactions(db: mySession, user: CurrentUser):
    return db.query(Transaction).filter(
        Transaction.buyer_uid == user.firebase_uid
    ).order_by(Transaction.created_at.desc()).all()

@router.get('/transactions/{listing_id}/qr')
def get_QR(listing_id: int, db: mySession, user: CurrentUser):
    transaction = db.query(Transaction).filter(
        Transaction.listing_id == listing_id,
        Transaction.buyer_uid == user.firebase_uid,
        Transaction.status == TransactionStatus.paid
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if not transaction.qr_expires_at or transaction.qr_expires_at < datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=410, detail="QR code expired")

    img = qrcode.make(str(listing_id))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return StreamingResponse(buf, media_type='image/png')