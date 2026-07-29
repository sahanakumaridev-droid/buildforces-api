import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, Registration
from app.schemas import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "uploads")
UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    registration_id: int = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    registration = db.query(Registration).filter(Registration.id == registration_id).first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found.")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF, JPEG, PNG, or HEIC files are allowed.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 10 MB.")

    extension = os.path.splitext(file.filename or "")[1]
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    with open(os.path.join(UPLOAD_DIR, stored_filename), "wb") as f:
        f.write(contents)

    document = Document(
        registration_id=registration_id,
        doc_type=doc_type,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        content_type=file.content_type,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.get("/by-registration/{registration_id}", response_model=list[DocumentOut])
def list_documents(registration_id: int, db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.registration_id == registration_id).all()
