from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ContactMessage
from app.schemas import ContactMessageCreate, ContactMessageOut

router = APIRouter(prefix="/api/contact", tags=["contact"])


@router.post("", response_model=ContactMessageOut, status_code=201)
def create_contact_message(payload: ContactMessageCreate, db: Session = Depends(get_db)):
    contact_message = ContactMessage(**payload.model_dump())
    db.add(contact_message)
    db.commit()
    db.refresh(contact_message)
    return contact_message
