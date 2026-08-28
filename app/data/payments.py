import os
import stripe
from fastapi import APIRouter, HTTPException, Request
from stripe import StripeClient

from app.models.auth import CurrentUser
from app.models.db import mySession
from app.models.schemas import AccountCreate, OnboardSellerResponse, TransactionResponse, TransactionRequest, \
    ListingResponse, ListingRequest
from app.models.models import Listing, Transaction, TransactionStatus, User

client = StripeClient(os.getenv('STRIPE_API_KEY'))

router = APIRouter()


@router.post('/create_listing', response_model=ListingResponse)
async def create_listing(db: mySession, user: CurrentUser, listing: ListingRequest):
    if not user.stripe_onboarded:
        raise HTTPException(status_code=400, detail="You must complete seller onboarding before creating a listing")

    listing = Listing(
        seller_uid=user.firebase_uid,
        price=listing.price,
        lat=listing.lat,
        lng=listing.lng,
        spot_in_queue=listing.spot_in_queue,
    )

    try:
        db.add(listing)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return listing

@router.post('/onboard_seller', response_model=OnboardSellerResponse)
async def onboard_seller(db: mySession, user: CurrentUser, body: AccountCreate = AccountCreate()):
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


#so i want to create an intent for pay emnt
#Then when the qe is scanned another endpoint is called that will confirm it all

@router.post('/start_transaction', response_model=TransactionResponse)
async def start_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    listing = db.query(Listing).filter(Listing.id == body.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    if db.query(Transaction).filter(Transaction.listing_id == listing.id).first():
        raise HTTPException(status_code=400, detail="Listing no_longer_available")

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
async def confirm_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    transaction = db.query(Transaction).filter(Transaction.listing_id == body.listing_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.seller_uid != user.firebase_uid:
        raise HTTPException(status_code=403, detail="Only the seller can confirm this transaction")

    if transaction.status == TransactionStatus.completed:
        raise HTTPException(status_code=400, detail="Transaction already completed")

    try:
        client.v1.payment_intents.capture(transaction.stripe_payment_intent_id)
        transaction.status = TransactionStatus.completed
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
        if event_dict['type'] == 'capability.updated':
            capability = event_dict['data']['object']
            if capability.get('status') == 'active':
                account_id = capability.get('account')
                if account_id:
                    user = db.query(User).filter(User.stripe_account_id == account_id).first()
                    if user and not user.stripe_onboarded:
                        user.stripe_onboarded = True
                        db.commit()
    except Exception as e:
        print(f"[webhook] ERROR: {e}")

    return {"status": "ok"}

