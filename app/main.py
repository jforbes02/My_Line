from fastapi import FastAPI
from dotenv import load_dotenv
from app.models.db import engine, Base
from app.data.payments import router as payment_router
from app.data.users import router as users_router
load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(payment_router)
app.include_router(users_router)

@app.get("/")
async def root():
    return {"message": "Kirk..."}


