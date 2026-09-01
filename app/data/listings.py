from fastapi import APIRouter, HTTPException
from app.models.auth import CurrentUser
from app.models.db import mySession
from app.models.models import Listing
from app.models.schemas import ListingResponse, ListingRequest

router = APIRouter()


@router.post('/create_listing', response_model=ListingResponse)
def create_listing(db: mySession, user: CurrentUser, listing: ListingRequest):
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
def get_listings(db: mySession):
    #todo Implement geolocation filter to get listings closest to you
    #prob will need search engine as well which I can outsource
    return db.query(Listing).filter(Listing.sold == False).all()



@router.get('/listings/mine', response_model=list[ListingResponse])
def get_my_listings(db: mySession, user: CurrentUser):
    return db.query(Listing).filter(Listing.seller_uid == user.firebase_uid).all()


@router.get('/listings/{listing_id}', response_model=ListingResponse)
def get_listing(db: mySession, listing_id: int):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.delete('/listings/{listing_id}')
def delete_listing(db: mySession, user: CurrentUser, listing_id: int):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_uid != user.firebase_uid:
        raise HTTPException(status_code=403, detail="You can only delete your own listings")
    if listing.sold:
        raise HTTPException(status_code=404, detail="Listing already sold")

    try:
        db.delete(listing)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return {"detail": "Listing deleted"}