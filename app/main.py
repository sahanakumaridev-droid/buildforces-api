import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import contact, register

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Build Forces API")

origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contact.router)
app.include_router(register.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
