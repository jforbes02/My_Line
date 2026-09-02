from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from app.models.auth import CurrentUser
from app.models.db import mySession
from app.models.models import Listing, Transaction, TransactionStatus
from app.models.schemas import ListingResponse, ListingRequest

router = APIRouter()


@router.post('/create_listing', response_model=ListingResponse)
def create_listing(db: mySession, user: CurrentUser, listing: ListingRequest):
    """
    Listing creation
    :param db: session
    :param user: current user
    :param listing: Listing inputs (price, lat, lng, spot_in_queue)
    :return: new listing
    """
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


@router.get('/listings', response_model=list[ListingResponse])
def get_listings(db: mySession, latitude: float, longitude: float, distance: float = 0.05):
    """
    Gets all listing in your area
    :param db: session
    :param latitude: lat
    :param longitude: lng
    :param distance: distance in kilometers
    :return: unsold listings in order of distance
    """

    #Creates distance expression so i can compare listings
    distance_expr = func.sqrt(
        func.pow(Listing.lat - latitude, 2) +
        func.pow(Listing.lng - longitude, 2)
    )

    #returns
    return db.query(Listing).filter(
        Listing.sold == False,
        Listing.lat.between(latitude - distance, latitude + distance),
        Listing.lng.between(longitude - distance, longitude + distance),
    ).order_by(distance_expr).all()



@router.get('/listings/mine', response_model=list[ListingResponse])
def get_my_listings(db: mySession, user: CurrentUser):
    """
    gets all listings you created (sold or not)
    :param db: session
    :param user: current user
    :return: listings
    """
    if not user.stripe_onboarded:
        raise HTTPException(status_code=400, detail="You must complete seller onboarding before getting listings")

    listing = db.query(Listing).filter(Listing.seller_uid == user.firebase_uid).all()

    if not listing:
        raise HTTPException(status_code=404, detail="You have not created a listing")
    return listing


@router.get('/listings/{listing_id}', response_model=ListingResponse)
def get_listing(db: mySession, listing_id: int):
    """
    gets a specific listing
    :param db:
    :param listing_id: listing id
    :return: listing
    """
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.delete('/listings/{listing_id}')
def delete_listing(db: mySession, user: CurrentUser, listing_id: int):
    """
    deletes a listing
    :param db: session
    :param user: current user
    :param listing_id: identification
    :return: listing deleted message
    """
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_uid != user.firebase_uid:
        raise HTTPException(status_code=403, detail="You can only delete your own listings")
    if listing.sold:
        raise HTTPException(status_code=400, detail="Listing already sold")

    active_transaction = db.query(Transaction).filter(
        Transaction.listing_id == listing_id,
        Transaction.status.in_([TransactionStatus.pending, TransactionStatus.paid])
    ).first()
    if active_transaction:
        raise HTTPException(status_code=400, detail="Listing has an active transaction")

    try:
        db.delete(listing)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return {"detail": "Listing deleted"}