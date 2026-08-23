import os
from fastapi import APIRouter, HTTPException
from stripe import StripeClient

from app.models.auth import CurrentUser
from app.models.db import mySession
from app.models.schemas import AccountCreate, OnboardSellerResponse, TransactionResponse, TransactionRequest
from app.models.models import Listing, Transaction, TransactionStatus

client = StripeClient(os.getenv('STRIPE_API_KEY'))

router = APIRouter()


@router.post('/onboard_seller', response_model=OnboardSellerResponse)
async def onboard_seller(db: mySession, user: CurrentUser, body: AccountCreate = AccountCreate()):
    if not user.stripe_account_id:
       try:
        # Create a Stripe Connect Express account for the seller.
            account = client.v1.accounts.create({
                "type": "express",
                "business_type": body.business_type,
                "country": body.country,
            })
            # Save the Stripe account ID to our DB so we can reference it on future payouts.
            user.stripe_account_id = account.id
            db.commit()
       except Exception as e:
           raise HTTPException(status_code=400, detail=str(e))

    # Generate a one-time onboarding link for the seller to complete their Stripe setup.
    # return_url: where Stripe sends the user after onboarding succeeds.
    # refresh_url: where Stripe sends the user if the link expires — client should hit this endpoint again.
    link = client.v1.account_links.create({
        "account": user.stripe_account_id,
        "return_url": "myline://onboarding/complete",
        "refresh_url": "myline://onboarding/refresh",
        "type": "account_onboarding",
    })
    return {"url": link.url}


#so i want to create an intent for payemnt
#Then when the qe is scanned another endpoint is called that will confirm it all

@router.post('/start_transaction', response_model=TransactionResponse)
async def start_transaction(db: mySession, user: CurrentUser, body: TransactionRequest):
    listing = db.query(Listing).filter(Listing.id == body.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    intent = client.v1.payment_intents.create({
        'amount': int(listing.price * 100),
        'currency': 'usd',
        'capture_method': 'manual',
        'transfer_data': {
            'destination': listing.seller.stripe_account_id,
        },
        'application_fee_amount': int(listing.price * 0.10 * 100), #will prob work out something different
    })


    transaction = Transaction(
        listing_id=listing.id,
        buyer_uid=user.firebase_uid,
        seller_uid=listing.seller_uid,
        price=listing.price,
        stripe_payment_intent_id=intent.id,
    )
    db.add(transaction)
    db.commit()


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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return transaction.__dict__

