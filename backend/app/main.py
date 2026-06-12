import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.app.config import (
    UPLOAD_DIR, SECURE_STORAGE_DIR, MAX_FILE_SIZE, ALLOWED_EXTENSIONS, DB_PATH, PAGE_IMAGES_DIR
)
from backend.app.database import (
    init_db, register_document, update_document_status,
    save_document_classification, insert_page, insert_chunks,
    get_all_documents, get_document, get_document_pages,
    save_chat_message, get_chat_history, delete_document_db
)
from backend.app.services.security import (
    encrypt_data, decrypt_data, sanitize_filename,
    generate_page_token, validate_page_token
)
from backend.app.services.parser import parse_document
from backend.app.services.classifier import classify_document
from backend.app.services.rag import chunk_text, get_gemini_embedding, retrieve_relevant_chunks, synthesize_answer

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Document Intelligence + Agentic RAG API")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "https://doc-analysis-three.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Checking for orphaned database records...")
    from backend.app.database import check_and_cleanup_orphaned_documents
    check_and_cleanup_orphaned_documents()
    
    from backend.app.precompute_samples import populate_database_with_samples
    logger.info("Precomputing samples (if missing)...")
    populate_database_with_samples()

def process_document_background(doc_id: str, file_path: Path, mime_type: str):
    """Asynchronous background document parser, classifier, and indexer."""
    try:
        logger.info(f"Start processing document {doc_id}...")
        
        # 1. Update status to parsing
        update_document_status(doc_id, "parsing")
        
        # 2. Parse text and render page images (which are encrypted at rest)
        pages_data = parse_document(file_path, doc_id, mime_type)
        if not pages_data:
            raise ValueError("No pages or text extracted from document.")
            
        # Save pages to sqlite
        full_text = ""
        for p in pages_data:
            insert_page(doc_id, p["page_number"], p["text"], p["image_path"])
            full_text += f"\n--- Page {p['page_number']} ---\n{p['text']}"
            
        logger.info(f"Document {doc_id} successfully parsed into {len(pages_data)} pages.")
        
        # 3. Update status to classifying
        update_document_status(doc_id, "classifying")
        
        # Classify document using LLM/fallback
        classification = classify_document(full_text)
        save_document_classification(doc_id, classification)
        
        logger.info(f"Document {doc_id} successfully classified.")
        
        # 4. Chunk text and index
        chunks_to_insert = []
        for p in pages_data:
            chunks = chunk_text(p["text"], doc_id, p["page_number"])
            for c in chunks:
                # Generate embedding if Gemini API is active
                emb = get_gemini_embedding(c["content"])
                c["embedding"] = emb
                chunks_to_insert.append(c)
                
        if chunks_to_insert:
            insert_chunks(chunks_to_insert)
            
        logger.info(f"Document {doc_id} successfully chunked and indexed with {len(chunks_to_insert)} chunks.")
        
        # 5. Mark as indexed and clean up original unencrypted file
        update_document_status(doc_id, "indexed")
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")
            
    except Exception as e:
        logger.exception(f"Failed to process document {doc_id}")
        update_document_status(doc_id, "failed", str(e))
        # Ensure cleanup of unencrypted file
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path} on error path: {e}")

@app.post("/api/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Secure file upload endpoint."""
    # 1. Validate extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
        
    # 2. Check file size (spool content to check size safely)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024*1024)}MB"
        )
        
    # Reset read cursor just in case
    await file.seek(0)
    
    # 3. Sanitize filename and generate secure path names
    doc_id = str(uuid.uuid4())
    sanitized_name = sanitize_filename(file.filename)
    
    # Save original copy encrypted at rest
    encrypted_content = encrypt_data(content)
    secure_filename = f"{doc_id}.enc"
    secure_path = SECURE_STORAGE_DIR / secure_filename
    with open(secure_path, "wb") as f:
        f.write(encrypted_content)
        
    # Register document record in DB (status pending)
    doc_record = register_document(
        doc_id=doc_id,
        original_name=sanitized_name,
        secure_name=secure_filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content)
    )
    
    # Write a temporary unencrypted file for the parsing libraries
    temp_path = UPLOAD_DIR / f"temp_{doc_id}{file_ext}"
    with open(temp_path, "wb") as f:
        f.write(content)
        
    # Launch parsing process in background task
    background_tasks.add_task(
        process_document_background,
        doc_id=doc_id,
        file_path=temp_path,
        mime_type=file.content_type or "application/octet-stream"
    )
    
    return doc_record

@app.get("/api/documents")
def list_documents():
    """List metadata for all uploaded documents."""
    return get_all_documents()

@app.get("/api/documents/{doc_id}")
def get_document_by_id(doc_id: str):
    """Retrieve metadata for a single document."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@app.get("/api/documents/{doc_id}/pages/{page_number}")
def get_page_image(
    doc_id: str,
    page_number: int,
    token: str = Query(...)
):
    """Securely serve decrypted page image if token is valid."""
    # 1. Validate access token
    if not validate_page_token(token, doc_id, page_number):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired access token."
        )
        
    # 2. Retrieve page details from DB
    pages = get_document_pages(doc_id)
    target_page = next((p for p in pages if p["page_number"] == page_number), None)
    if not target_page or not target_page["image_path"]:
        raise HTTPException(status_code=404, detail="Page image not found")
        
    # 3. Read and decrypt page image
    image_path = Path(PAGE_IMAGES_DIR) / target_page["image_path"]
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Page image file missing")
        
    with open(image_path, "rb") as f:
        encrypted_data = f.read()
        
    try:
        decrypted_data = decrypt_data(encrypted_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt image content")
        
    return Response(content=decrypted_data, media_type="image/jpeg")

@app.post("/api/chat")
def chat(
    request: Request,
    message: str = Form(...),
    session_id: str = Form(...)
):
    """RAG-enabled multi-turn chat endpoint."""
    message = message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty query message")
        
    # Get chat history
    history = get_chat_history(session_id)
    
    # 1. Retrieve relevant chunks
    retrieved_chunks = retrieve_relevant_chunks(message, top_k=5)
    
    # 2. Synthesize answer using LLM
    answer, citations = synthesize_answer(message, history, retrieved_chunks)
    
    # 3. Generate secure signed image URLs for citations
    base_url = str(request.base_url).rstrip("/")
    secure_citations = []
    for cit in citations:
        token = generate_page_token(cit["document_id"], cit["page_number"])
        secure_citations.append({
            "document_id": cit["document_id"],
            "document_name": cit["document_name"],
            "page_number": cit["page_number"],
            "image_url": f"{base_url}/api/documents/{cit['document_id']}/pages/{cit['page_number']}?token={token}"
        })
        
    # Save user message
    save_chat_message(session_id, "user", message)
    # Save assistant message
    save_chat_message(session_id, "assistant", answer, secure_citations)
    
    return {
        "answer": answer,
        "citations": secure_citations
    }

@app.get("/api/chat/history/{session_id}")
def chat_history(session_id: str):
    """Retrieve chat history for a session."""
    return get_chat_history(session_id)

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document, its database records, and physical files."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # 1. Delete DB records (cascades automatically to pages and chunks)
    delete_document_db(doc_id)
    
    # 2. Delete secure original file from storage
    secure_file_path = Path(SECURE_STORAGE_DIR) / doc["secure_name"]
    if secure_file_path.exists():
        try:
            secure_file_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete secure file {secure_file_path}: {e}")
            
    # 3. Delete page images from pages storage
    try:
        for page_img_file in PAGE_IMAGES_DIR.glob(f"{doc_id}_page_*.enc"):
            try:
                page_img_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete page image {page_img_file}: {e}")
    except Exception as e:
        logger.warning(f"Failed to list page images for deletion: {e}")
        
    return {"status": "success", "message": f"Document {doc_id} deleted successfully."}
