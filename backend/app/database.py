import os
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.app.config import DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

IS_POSTGRES = False
if DATABASE_URL:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        IS_POSTGRES = True
    except ImportError:
        pass

def get_db_connection():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def get_db_cursor(conn):
    if IS_POSTGRES:
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        return conn.cursor()

def execute_query(cursor, query_str: str, params: tuple = ()):
    if IS_POSTGRES:
        query_str = query_str.replace("?", "%s")
    cursor.execute(query_str, params)
    return cursor

def init_db():
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    # Documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            secure_name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL, -- 'pending', 'parsing', 'classifying', 'indexed', 'failed'
            error_message TEXT,
            classification_json TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Pages table (for rendered page images and page texts)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id TEXT PRIMARY KEY, -- doc_id + "_page_" + page_num
            document_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            extracted_text TEXT,
            image_path TEXT, -- relative path inside PAGE_IMAGES_DIR
            FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
        )
    ''')
    
    # Chunks table (for vector retrieval and matching)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding_json TEXT, -- Optional stored embedding
            FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
        )
    ''')
    
    # Conversation History table
    if IS_POSTGRES:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL, -- 'user' or 'assistant'
                content TEXT NOT NULL,
                citations_json TEXT, -- JSON array of page references
                timestamp TEXT NOT NULL
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL, -- 'user' or 'assistant'
                content TEXT NOT NULL,
                citations_json TEXT, -- JSON array of page references
                timestamp TEXT NOT NULL
            )
        ''')
    
    conn.commit()
    conn.close()

def register_document(doc_id: str, original_name: str, secure_name: str, mime_type: str, size_bytes: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    now = datetime.utcnow().isoformat()
    execute_query(cursor, '''
        INSERT INTO documents (id, original_name, secure_name, mime_type, size_bytes, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (doc_id, original_name, secure_name, mime_type, size_bytes, 'pending', now))
    conn.commit()
    conn.close()
    return {
        "id": doc_id,
        "original_name": original_name,
        "status": "pending",
        "created_at": now
    }

def update_document_status(doc_id: str, status: str, error_message: Optional[str] = None):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, '''
        UPDATE documents
        SET status = ?, error_message = ?
        WHERE id = ?
    ''', (status, error_message, doc_id))
    conn.commit()
    conn.close()

def save_document_classification(doc_id: str, classification: Dict[str, Any]):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, '''
        UPDATE documents
        SET classification_json = ?, status = 'classifying'
        WHERE id = ?
    ''', (json.dumps(classification), doc_id))
    conn.commit()
    conn.close()

def insert_page(document_id: str, page_number: int, extracted_text: str, image_path: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    page_id = f"{document_id}_page_{page_number}"
    if IS_POSTGRES:
        cursor.execute('''
            INSERT INTO pages (id, document_id, page_number, extracted_text, image_path)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET 
                document_id = EXCLUDED.document_id,
                page_number = EXCLUDED.page_number,
                extracted_text = EXCLUDED.extracted_text,
                image_path = EXCLUDED.image_path
        ''', (page_id, document_id, page_number, extracted_text, image_path))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO pages (id, document_id, page_number, extracted_text, image_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (page_id, document_id, page_number, extracted_text, image_path))
    conn.commit()
    conn.close()

def insert_chunks(chunks_data: List[Dict[str, Any]]):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    for c in chunks_data:
        if IS_POSTGRES:
            cursor.execute('''
                INSERT INTO chunks (id, document_id, page_number, chunk_index, content, embedding_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    page_number = EXCLUDED.page_number,
                    chunk_index = EXCLUDED.chunk_index,
                    content = EXCLUDED.content,
                    embedding_json = EXCLUDED.embedding_json
            ''', (c["id"], c["document_id"], c["page_number"], c["chunk_index"], c["content"], json.dumps(c.get("embedding", []))))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO chunks (id, document_id, page_number, chunk_index, content, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (c["id"], c["document_id"], c["page_number"], c["chunk_index"], c["content"], json.dumps(c.get("embedding", []))))
    conn.commit()
    conn.close()

def upsert_document_precomputed(doc_id: str, name: str, secure_name: str, mime_type: str, size_bytes: int, status: str, classification: Dict[str, Any], created_at: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    if IS_POSTGRES:
        cursor.execute('''
            INSERT INTO documents (id, original_name, secure_name, mime_type, size_bytes, status, classification_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                original_name = EXCLUDED.original_name,
                secure_name = EXCLUDED.secure_name,
                mime_type = EXCLUDED.mime_type,
                size_bytes = EXCLUDED.size_bytes,
                status = EXCLUDED.status,
                classification_json = EXCLUDED.classification_json,
                created_at = EXCLUDED.created_at
        ''', (doc_id, name, secure_name, mime_type, size_bytes, status, json.dumps(classification), created_at))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO documents (id, original_name, secure_name, mime_type, size_bytes, status, classification_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (doc_id, name, secure_name, mime_type, size_bytes, status, json.dumps(classification), created_at))
    conn.commit()
    conn.close()

def get_all_documents() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, 'SELECT * FROM documents ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    
    docs = []
    for r in rows:
        d = dict(r)
        d["classification"] = json.loads(d["classification_json"]) if d["classification_json"] else None
        del d["classification_json"]
        docs.append(d)
    return docs

def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, 'SELECT * FROM documents WHERE id = ?', (doc_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["classification"] = json.loads(d["classification_json"]) if d["classification_json"] else None
    del d["classification_json"]
    return d

def get_document_pages(doc_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, 'SELECT * FROM pages WHERE document_id = ? ORDER BY page_number ASC', (doc_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_chunks() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, '''
        SELECT chunks.*, documents.original_name
        FROM chunks
        JOIN documents ON chunks.document_id = documents.id
        WHERE documents.status = 'indexed'
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    chunks = []
    for r in rows:
        c = dict(r)
        c["embedding"] = json.loads(c["embedding_json"]) if c["embedding_json"] else []
        del c["embedding_json"]
        chunks.append(c)
    return chunks

def save_chat_message(session_id: str, role: str, content: str, citations: Optional[List[Dict[str, Any]]] = None):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    now = datetime.utcnow().isoformat()
    execute_query(cursor, '''
        INSERT INTO chat_history (session_id, role, content, citations_json, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (session_id, role, content, json.dumps(citations or []), now))
    conn.commit()
    conn.close()

def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    execute_query(cursor, 'SELECT * FROM chat_history WHERE session_id = ? ORDER BY id ASC', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    msgs = []
    for r in rows:
        m = dict(r)
        m["citations"] = json.loads(m["citations_json"]) if m["citations_json"] else []
        del m["citations_json"]
        msgs.append(m)
    return msgs

def check_and_cleanup_orphaned_documents():
    """Verify that all 'indexed' documents actually have their encrypted source files on disk.
    If the storage has been wiped (e.g. on ephemeral deploys) or if they fail to decrypt
    due to encryption key change/loss, mark them as failed.
    """
    import logging
    from backend.app.config import SECURE_STORAGE_DIR
    from pathlib import Path
    from backend.app.services.security import decrypt_data
    
    logger = logging.getLogger(__name__)
    logger.info("Checking for orphaned database records due to ephemeral storage or decryption failures...")
    
    try:
        conn = get_db_connection()
        cursor = get_db_cursor(conn)
        
        # Select all indexed documents that are not samples
        execute_query(cursor, "SELECT id, original_name, secure_name FROM documents WHERE status = 'indexed' AND id NOT LIKE 'sample-%'")
        rows = cursor.fetchall()
        
        for r in rows:
            d = dict(r)
            doc_id = d["id"]
            orig_name = d["original_name"]
            sec_name = d["secure_name"]
            
            secure_file_path = Path(SECURE_STORAGE_DIR) / sec_name
            if not secure_file_path.exists():
                logger.warning(f"Document {orig_name} ({doc_id}) is missing its secure file on disk. Marking as failed.")
                execute_query(cursor, """
                    UPDATE documents 
                    SET status = 'failed', error_message = 'File storage was reset on server restart (ephemeral storage). Please delete and re-upload.'
                    WHERE id = ?
                """, (doc_id,))
            else:
                # Test decryption of the file
                try:
                    with open(secure_file_path, "rb") as f:
                        enc_data = f.read()
                    decrypt_data(enc_data)
                except Exception as dec_err:
                    logger.warning(f"Document {orig_name} ({doc_id}) failed to decrypt (encryption key changed or corrupted): {dec_err}. Marking as failed.")
                    execute_query(cursor, """
                        UPDATE documents 
                        SET status = 'failed', error_message = 'Failed to decrypt file (encryption key was regenerated on server restart). Please delete and re-upload.'
                        WHERE id = ?
                    """, (doc_id,))
                
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to check/update orphaned records: {e}")

def delete_document_db(doc_id: str):
    """Delete document from DB. SQLite cascade deletes pages and chunks automatically if foreign keys are enabled."""
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    if not IS_POSTGRES:
        cursor.execute("PRAGMA foreign_keys = ON")
    execute_query(cursor, "DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
