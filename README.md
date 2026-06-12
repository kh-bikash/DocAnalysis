<p align="center">
  <svg width="400" height="90" viewBox="0 0 400 90" fill="none" xmlns="http://www.w3.org/2000/svg">
    <style>
      .text {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        font-weight: 800;
        font-size: 24px;
        animation: glow 3s ease-in-out infinite alternate;
      }
      .subtext {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        font-style: italic;
        font-weight: 500;
        font-size: 13px;
        fill: #64748b;
      }
      @keyframes glow {
        from {
          text-shadow: 0 0 4px rgba(124, 58, 237, 0.2), 0 0 10px rgba(124, 58, 237, 0.4);
          fill: #7c3aed;
        }
        to {
          text-shadow: 0 0 12px rgba(192, 132, 252, 0.6), 0 0 22px rgba(192, 132, 252, 0.8);
          fill: #c084fc;
        }
      }
    </style>
    <text x="50%" y="40" dominant-baseline="middle" text-anchor="middle" class="text">🔮 DOCINTEL RAG AGENT</text>
    <text x="50%" y="68" dominant-baseline="middle" text-anchor="middle" class="subtext">Secure Ingestion, Multimodal OCR & Agentic RAG</text>
  </svg>
</p>

<p align="center">
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI" /></a>
  <a href="https://nextjs.org"><img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js" /></a>
  <a href="https://ai.google.dev"><img src="https://img.shields.io/badge/Gemini%20API-8E75C2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini API" /></a>
  <a href="https://neon.tech"><img src="https://img.shields.io/badge/Neon%20Postgres-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="Neon Postgres" /></a>
  <img src="https://img.shields.io/badge/Security-AES--256-success?style=for-the-badge&logo=lock" alt="AES-256 Encrypted" />
</p>

---

A state-of-the-art, secure enterprise web application designed to ingest messy, real-world documents (digital/scanned PDFs, handwritten pages, image-heavy reports, plain text), structurally extract tables, automatically classify files across multiple dimensions, and power a multi-turn RAG chatbot with grounded page citations and secure image visualization.

---

## 🏗️ System Architecture

Our architecture is split into a **Next.js frontend** and an **asynchronous FastAPI backend** communicating over a secure API gateway. The system enforces strict isolation and encryption boundaries at rest and in transit.

```mermaid
graph TD
    User([User Browser]) <--> |HTTP/WS / Audio Input| FE[Next.js Frontend]
    FE <--> |API requests| BE[FastAPI Backend]
    
    subgraph FastAPI Backend App
        BE --> |Auth/JWT Signatures| Security[Security Service]
        BE --> |Ingest/OCR| Parser[Document Parser]
        BE --> |Structured JSON| Classifier[Gemini Classifier]
        BE --> |Embeddings/Retriever| RAG[Agentic RAG Engine]
    end
    
    subgraph "Data & Storage (AES-256 Encrypted)"
        Security --> |Encrypt/Decrypt| Storage[(Local Secure Storage)]
        Parser --> |Save Page Images| PageStorage[(Encrypted Page Images)]
        RAG --> |Vector & Text Index| DB[(SQLite / Neon PostgreSQL)]
    end
    
    RAG -.-> |Fallback Index| BM25[Local BM25 Index]
    RAG -.-> |Vector Search| VectorSearch[Cosine Similarity NumPy]
    Parser -.-> |Fallback OCR| GeminiOCR[Gemini Multimodal API]
    Parser -.-> |Local OCR| Tesseract[Tesseract OCR Binary]
```

---

## 🔄 Document Ingestion Workflow

When a document is uploaded, it transitions through a secured pipeline executing asynchronous background threads:

```mermaid
sequenceDiagram
    autonumber
    actor User as User Browser
    participant API as FastAPI Ingestion Endpoint
    participant Sec as Security Service
    participant Disk as Encrypted Disk Storage
    participant Parser as Doc Parser (pdfium/pdfplumber)
    participant Class as Gemini Classifier
    participant RAG as RAG Indexer (gemini-embedding-2)
    participant DB as SQLite / Neon Postgres DB

    User->>API: Upload File (pdf/png/txt)
    API->>API: Validate file extensions & size (<10MB)
    API->>Sec: Sanitize filename & Encrypt content (AES-256)
    Sec->>Disk: Save encrypted original content (doc_id.enc)
    API->>DB: Register document status as 'pending'
    API-->>User: Return upload success metadata (polling starts)
    Note over API,DB: Background Task Starts
    API->>Parser: Parse text & render page screenshots
    Parser->>Sec: Encrypt page screenshots (AES-256)
    Sec->>Disk: Save encrypted page images (page_id.enc)
    Parser->>DB: Save extracted page text & status to 'parsing'
    API->>Class: Classify full text (Gemini API / Heuristics)
    Class->>DB: Save structured JSON metadata & status to 'classifying'
    API->>RAG: Chunk text and generate vector embeddings
    RAG->>DB: Save text chunks & JSON vectors, update status to 'indexed'
    User->>API: Poll status -> Status is 'indexed' (Frontend active!)
```

---

## 🛡️ Data Security Implementation

Security is integrated at every layer of the system:

### 1. Upload Boundary (Defense-in-Depth)
* **File Validation**: Strict white-list filtering of mime types and extensions (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.txt`).
* **Payload Limits**: Max file size is capped at `10MB` to prevent memory exhaustion.
* **Filename Sanitization**: Sanitizes input strings using regular expressions to strip directory traversal sequences (`../`, etc.).
* **Decoupled Identifiers**: Renames files on disk to random `UUID4` sequences, preventing exposure of company/project names.

### 2. Encryption at Rest
* **AES-256 Symmetric Encryption**: Files (both uploads and rendered page images) are encrypted on disk using `cryptography.fernet`.
* **Dynamic Keys**: Encryption key is dynamically generated on launch and saved inside the git-ignored `.env` file. On-disk files are unreadable binary blobs.

### 3. Ephemeral Processing
* **Sandboxed Workspaces**: Any unencrypted files needed during rendering are kept in isolated workspace folders and deleted (`Path.unlink()`) immediately upon task completion or failure.

### 4. API signed URLs
* **Signed Retrievals**: Dynamic token signatures are required to fetch page images.
* **JWT Access Control**: Tokens contain the `document_id`, `page_number`, and a `15-minute expiration`. Expired or unsigned requests yield a `403 Forbidden`.

---

## 🛠️ Technology Stack

* **Backend**: Python 3.11, FastAPI (Asynchronous framework), Uvicorn (Server), SQLite (Local metadata), NumPy (Vector similarity math).
* **Frontend**: Next.js 15, React, TypeScript, Vanilla CSS (Premium design with Outfit typography, custom glassmorphism, and smooth transitions).
* **AI & Parsing Libraries**: `pdfplumber` (Table structure extraction), `pypdfium2` (Pure Python page rendering), `pytesseract` (OCR), `google-genai` (`gemini-2.5-flash` for QA/OCR, `gemini-embedding-2` for vectors).

---

## 🚀 Quick Setup & Run

### Prerequisites
* Python 3.11+
* Node.js 18+
* Active Internet Connection (for Gemini API and voice transcription)

### Step 1: Configure Environment
In the `backend/` folder, create a `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key_here
# Optional: Set this to connect to a live database (e.g. Neon PostgreSQL)
# DATABASE_URL=postgresql://neondb_owner:...
```
*(Note: If no API key is provided, the application falls back to offline mode using BM25 and pre-cached sample files. If no `DATABASE_URL` is provided, it defaults to SQLite).*

### Step 2: Set Up & Start Backend
Navigate to the `backend/` directory:
```powershell
# Create virtual environment
python -m venv venv
# Activate it
venv\Scripts\Activate.ps1
# Install dependencies
pip install -r requirements.txt
# Populate SQLite sample database with vector embeddings
python app/precompute_samples.py
# Start the dev server
python run.py
```
FastAPI will run at `http://localhost:8000`.

### Step 3: Set Up & Start Frontend
Navigate to the `frontend/` directory:
```bash
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🧪 Step-by-Step Testing Guide

Follow this guide to verify the primary features of the application:

### 1. Multi-turn Chat, Citations & Lightbox
* **Browser Requirement**: Open the app using **Google Chrome** or **Microsoft Edge**.
* Ask a question about the pre-seeded handwritten note:
  > *"What was the revenue and margin in Q2 for Business Performance?"*
* The agent retrieves the relevant chunks using cosine similarity, synthesizes the answer, and inserts an inline citation badge: **`[handwritten_note.png Page 1]`**.
* **Hover Preview**: Hover over the citation badge to view the page thumbnail.
* **Interactive Lightbox**: Click the badge to open the overlay. Use the **Zoom In**, **Zoom Out**, and **Drag to Pan** controls to inspect the handwritten chart and table values.
* **Voice Input**: Click the microphone icon, allow microphone permission, and speak your query. It will transcribe in real-time.
  > *Note on Brave Browser: Brave blocks Google's speech recognition integration by default. To run voice input in Brave, you must enable "Use Google services for push messaging and voice search" in `brave://settings/privacy` or use Chrome/Edge.*

### 2. Bulk Ingestion Pipeline
* Navigate to the **Upload Documents** page.
* Upload a document (digital PDF, image, scanned page).
* Observe the real-time status tracker pipeline:
  $$\text{Queued} \rightarrow \text{Parsing} \rightarrow \text{Classifying} \rightarrow \text{Indexed}$$
* Once indexed, click the row in the document table to slide open the metadata drawer, showing the structured JSON classification: summary, topic, sensitivity level, and key entities.

---

## 🌐 Live Production Deployment

### Frontend: Vercel
Deploy the Next.js frontend to **Vercel** with one click.
* Configure the environment variable `NEXT_PUBLIC_API_URL` to point to your live backend endpoint.

### Database: Neon PostgreSQL
The backend database adapter dynamically switches to PostgreSQL when a `DATABASE_URL` (such as a **Neon database connection string**) is supplied. It automatically initializes tables and processes upserts using Postgres-compliant syntax:
```env
DATABASE_URL=postgresql://neondb_owner:your_password@ep-square-bar-addv7u5z.us-east-1.aws.neon.tech/neondb?sslmode=require
```

### Backend: Persistent Host (Render, Railway, AWS, GCP)
**Vercel is NOT sufficient for hosting the Python backend** due to:
1. **Background Tasks**: Ingestion pipelines run in background threads (`BackgroundTasks`) to process large uploads. Vercel's serverless functions will terminate these threads prematurely.
2. **Binary Dependencies**: Scanning and OCR require `pytesseract`, which depends on the Tesseract OCR binary installed on the host OS. This cannot be installed easily on Vercel serverless.
3. **Encrypted Storage**: Uploads and page images are encrypted and stored inside local storage folders on disk. Vercel's filesystem is read-only and stateless.
4. **Recommendation**: Deploy the FastAPI app to **Render** or **Railway** with your Neon PostgreSQL URL configured in the environment variables.
