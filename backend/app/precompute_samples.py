import os
import sys
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add current folder to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.app.config import DATA_DIR, PAGE_IMAGES_DIR, SECURE_STORAGE_DIR, DB_PATH
from backend.app.database import init_db, upsert_document_precomputed, insert_page, insert_chunks
from backend.app.services.security import encrypt_data, sanitize_filename
from backend.app.services.rag import chunk_text, get_gemini_embedding

# Ensure database and folders are initialized
init_db()

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "sample_docs"
SAMPLE_DOCS_DIR.mkdir(exist_ok=True)

def create_invoice_pdf(path: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 60, "ACME CORPORATION")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, "123 Business Rd, Suite 100")
    c.drawString(50, height - 95, "New York, NY 10001")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 50, height - 60, "INVOICE")
    
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 50, height - 80, "Invoice #: INV-2026-004")
    c.drawRightString(width - 50, height - 95, "Date: June 12, 2026")
    c.drawRightString(width - 50, height - 110, "Due Date: July 12, 2026")
    
    # Bill to
    c.drawString(50, height - 160, "BILL TO:")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 175, "Build Fast with AI")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 190, "Intern Assessment Dept")
    c.drawString(50, height - 205, "Silicon Valley, CA 94025")
    
    # Line items header
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 260, "Description")
    c.drawRightString(width - 200, height - 260, "Quantity")
    c.drawRightString(width - 120, height - 260, "Unit Price")
    c.drawRightString(width - 50, height - 260, "Amount")
    
    c.setLineWidth(1)
    c.line(50, height - 270, width - 50, height - 270)
    
    # Table Content
    items = [
        ("AI Consulting Services - Ingestion Engine", "10 hrs", "$150.00", "$1,500.00"),
        ("Document Parsing & Custom OCR Pipeline", "1 unit", "$800.00", "$800.00"),
        ("Agentic RAG & Vector Database Integration", "1 unit", "$1,200.00", "$1,200.00"),
        ("Frontend Design - Custom CSS Modules & Chat UI", "1 unit", "$950.00", "$950.00"),
    ]
    
    y = height - 290
    c.setFont("Helvetica", 10)
    for desc, qty, price, amt in items:
        c.drawString(50, y, desc)
        c.drawRightString(width - 200, y, qty)
        c.drawRightString(width - 120, y, price)
        c.drawRightString(width - 50, y, amt)
        y -= 20
        
    c.line(50, y + 10, width - 50, y + 10)
    
    # Totals
    y -= 10
    c.drawRightString(width - 120, y, "Subtotal:")
    c.drawRightString(width - 50, y, "$4,450.00")
    y -= 20
    c.drawRightString(width - 120, y, "Tax (0%):")
    c.drawRightString(width - 50, y, "$0.00")
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 120, y, "Total Due:")
    c.drawRightString(width - 50, y, "$4,450.00")
    
    # Note
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 50, "Thank you for your business! Please remit payments to account details provided in confidential agreement.")
    
    c.save()

def create_report_pdf(path: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    
    # Page 1 - Cover
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(width / 2.0, height - 200, "State of Document AI")
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2.0, height - 240, "A Comprehensive Survey of Ingestion Pipelines")
    
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(width / 2.0, height - 300, "Prepared by: Build Fast with AI Research Team")
    c.drawCentredString(width / 2.0, height - 320, "Published: June 2026")
    
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2.0, 100, "Page 1 of 2")
    c.showPage()
    
    # Page 2 - Content
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "1. Introduction")
    
    c.setFont("Helvetica", 11)
    intro_text = (
        "Document Artificial Intelligence represents a milestone in intelligent process automation. "
        "A typical pipeline comprises document parsing, OCR (Optical Character Recognition) for scanned pages, "
        "document classification, chunking, database storage, and retrieval-augmented generation. "
        "Recent trends focus heavily on data security at every layer, especially when processing sensitive documents."
    )
    
    # Simple word wrap
    textobject = c.beginText(50, height - 90)
    textobject.setFont("Helvetica", 11)
    textobject.setLeading(16)
    words = intro_text.split()
    line = []
    for word in words:
        if len(" ".join(line + [word])) * 6 > width - 100:
            textobject.textLine(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        textobject.textLine(" ".join(line))
    c.drawText(textobject)
    
    # Section 2
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 220, "2. Key Metrics")
    
    metrics_text = (
        "In our assessment of free OCR libraries, Tesseract achieves 92.5% character accuracy on clean documents. "
        "However, for tables and complex layouts, advanced multimodal models like Gemini 2.5 Flash deliver "
        "up to 99.1% accuracy by retaining row-column spatial structures. Security encryption at rest adds "
        "negligible latency (under 5 milliseconds per document) while completely mitigating physical theft risk."
    )
    
    textobject = c.beginText(50, height - 245)
    textobject.setFont("Helvetica", 11)
    textobject.setLeading(16)
    words = metrics_text.split()
    line = []
    for word in words:
        if len(" ".join(line + [word])) * 6 > width - 100:
            textobject.textLine(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        textobject.textLine(" ".join(line))
    c.drawText(textobject)
    
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2.0, 50, "Page 2 of 2")
    c.showPage()
    
    c.save()

def create_handwritten_image(path: Path):
    # If file already exists, don't overwrite it
    if path.exists():
        logger.info(f"Image {path.name} already exists. Skipping dynamic creation.")
        return
    # Fallback to create mockup
    img = Image.new('RGB', (800, 600), color=(253, 251, 241)) # Cream paper color
    draw = ImageDraw.Draw(img)
    
    # Draw paper lines
    for y in range(80, 580, 40):
        draw.line((40, y, 760, y), fill=(210, 225, 240), width=1)
    # Red left margin
    draw.line((100, 20, 100, 580), fill=(240, 180, 180), width=2)
    
    # We will write text line by line. Since standard PIL doesn't have handwritten fonts out of the box,
    # we'll draw it in simple sans-serif, simulating handwritten layout.
    draw.text((120, 95), "June 12, 2026", fill=(30, 50, 120))
    draw.text((120, 135), "To whom it may concern,", fill=(30, 50, 120))
    draw.text((120, 175), "Please refer to project ID 'DI-AGENT-99' for all future", fill=(30, 50, 120))
    draw.text((120, 215), "correspondence. We have reviewed the initial designs.", fill=(30, 50, 120))
    draw.text((120, 255), "Note that the budget limit is set strictly to $10,000.", fill=(30, 50, 120))
    draw.text((120, 295), "Any changes exceeding this amount must be approved.", fill=(30, 50, 120))
    draw.text((120, 375), "Thanks,", fill=(30, 50, 120))
    draw.text((120, 415), "Jane Doe", fill=(30, 50, 120))
    
    img.save(path)

def create_agreement_pdf(path: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2.0, height - 60, "CONFIDENTIAL MUTUAL NDA")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 100, "This Non-Disclosure Agreement ('Agreement') is entered into as of June 12, 2026 by and between:")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 120, "Party A: Build Fast with AI Inc.")
    c.drawString(50, height - 135, "Party B: AI Intern Assessment Candidate")
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 170, "1. Purpose")
    c.setFont("Helvetica", 10)
    
    purpose_text = (
        "The parties wish to explore a business opportunity regarding Document Intelligence and RAG agents. "
        "In connection with this, Party A may disclose proprietary software designs, vector space configurations, "
        "and encrypted dataset structures ('Confidential Information') to Party B. "
        "The receiving party agrees to hold all such information in strict confidence."
    )
    
    textobject = c.beginText(50, height - 190)
    textobject.setFont("Helvetica", 10)
    textobject.setLeading(14)
    words = purpose_text.split()
    line = []
    for word in words:
        if len(" ".join(line + [word])) * 5.5 > width - 100:
            textobject.textLine(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        textobject.textLine(" ".join(line))
    c.drawText(textobject)
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 280, "2. Exclusions & Terms")
    
    terms_text = (
        "This Agreement shall remain in effect for a period of three (3) years from the date of disclosure. "
        "Confidential Information does not include information that is or becomes publicly known through no breach "
        "by the receiving party, or is independently developed without reference to the disclosing party's information."
    )
    
    textobject = c.beginText(50, height - 300)
    textobject.setFont("Helvetica", 10)
    textobject.setLeading(14)
    words = terms_text.split()
    line = []
    for word in words:
        if len(" ".join(line + [word])) * 5.5 > width - 100:
            textobject.textLine(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        textobject.textLine(" ".join(line))
    c.drawText(textobject)
    
    # Signatures
    y = height - 420
    c.drawString(50, y, "Signed for Party A:")
    c.drawString(width - 250, y, "Signed for Party B:")
    y -= 30
    c.line(50, y, 200, y)
    c.line(width - 250, y, width - 100, y)
    y -= 15
    c.drawString(50, y, "Name: Jane Doe, Chief Scientist")
    c.drawString(width - 250, y, "Name: AI Engineer Intern Candidate")
    
    c.save()

def create_memo_txt(path: Path):
    content = """MEMORANDUM

TO: All Engineering Interns
FROM: IT Security Office
DATE: June 12, 2026
SUBJECT: Secure API Key Management & Vector Configurations

This memorandum outlines our mandatory policies regarding credentials and document safety.

1. API KEY STORAGE
Under no circumstances should any API keys (such as GEMINI_API_KEY, OPENAI_API_KEY, or database passwords) be committed to public git repositories. Always load keys using environment variables (e.g. via .env files loaded with python-dotenv).

2. DOCUMENT STORAGE REGULATIONS
All uploaded evaluation files containing financial or corporate project names must be encrypted. Our backend must perform filename hashing, renaming files to secure UUIDs, and encrypting bytes at rest using AES-256 symmetric ciphers.

3. RETRIEVAL SIGNING
When chatbot users request document source visualizations, URLs must contain short-lived signed tokens. Anonymous access to page images is strictly prohibited.

Compliance with these rules is monitored. Thank you for your cooperation.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def populate_database_with_samples():
    """Populates database directly with pre-computed parsed results for all 5 sample files."""
    
    samples_data = [
        {
            "id": "sample-invoice-id",
            "original_name": "invoice_sample.pdf",
            "secure_name": "sample-invoice-id.enc",
            "mime_type": "application/pdf",
            "size_bytes": 15000,
            "classification": {
                "document_type": "Invoice",
                "topic": "Finance",
                "sensitivity_level": "Confidential",
                "content_characteristics": ["tabular", "structured", "financial"],
                "summary": "Invoice INV-2026-004 from ACME Corporation billed to Build Fast with AI for consulting, parsing, and RAG integration services. Total due is $4,450.00.",
                "key_entities": ["ACME Corporation", "Build Fast with AI", "$4,450.00", "INV-2026-004", "June 12, 2026"]
            },
            "pages": [
                {
                    "page_number": 1,
                    "text": """ACME CORPORATION
123 Business Rd, Suite 100
New York, NY 10001

INVOICE
Invoice #: INV-2026-004
Date: June 12, 2026
Due Date: July 12, 2026

BILL TO:
Build Fast with AI
Intern Assessment Dept
Silicon Valley, CA 94025

| Description | Quantity | Unit Price | Amount |
|---|---|---|---|
| AI Consulting Services - Ingestion Engine | 10 hrs | $150.00 | $1,500.00 |
| Document Parsing & Custom OCR Pipeline | 1 unit | $800.00 | $800.00 |
| Agentic RAG & Vector Database Integration | 1 unit | $1,200.00 | $1,200.00 |
| Frontend Design - Custom CSS Modules & Chat UI | 1 unit | $950.00 | $950.00 |

Subtotal: $4,450.00
Tax (0%): $0.00
Total Due: $4,450.00

Thank you for your business! Please remit payments to account details provided in confidential agreement.""",
                    "image_generator": lambda p: create_invoice_pdf(p)
                }
            ]
        },
        {
            "id": "sample-report-id",
            "original_name": "research_report.pdf",
            "secure_name": "sample-report-id.enc",
            "mime_type": "application/pdf",
            "size_bytes": 28000,
            "classification": {
                "document_type": "Report",
                "topic": "Technical",
                "sensitivity_level": "Internal",
                "content_characteristics": ["long-form", "structured"],
                "summary": "A comprehensive survey report discussing Document AI ingestion pipelines, OCR accuracy rates (Tesseract vs Gemini), and performance impacts of encryption at rest.",
                "key_entities": ["Tesseract", "Gemini 2.5 Flash", "92.5%", "99.1%", "June 2026", "Build Fast with AI Research Team"]
            },
            "pages": [
                {
                    "page_number": 1,
                    "text": """State of Document AI
A Comprehensive Survey of Ingestion Pipelines
Prepared by: Build Fast with AI Research Team
Published: June 2026

Page 1 of 2""",
                    "image_generator": None # generated below by rendering PDF
                },
                {
                    "page_number": 2,
                    "text": """1. Introduction
Document Artificial Intelligence represents a milestone in intelligent process automation. A typical pipeline comprises document parsing, OCR (Optical Character Recognition) for scanned pages, document classification, chunking, database storage, and retrieval-augmented generation. Recent trends focus heavily on data security at every layer, especially when processing sensitive documents.

2. Key Metrics
In our assessment of free OCR libraries, Tesseract achieves 92.5% character accuracy on clean documents. However, for tables and complex layouts, advanced multimodal models like Gemini 2.5 Flash deliver up to 99.1% accuracy by retaining row-column spatial structures. Security encryption at rest adds negligible latency (under 5 milliseconds per document) while completely mitigating physical theft risk.

Page 2 of 2""",
                    "image_generator": None
                }
            ],
            "pdf_generator": lambda p: create_report_pdf(p)
        },
        {
            "id": "sample-handwritten-id",
            "original_name": "handwritten_note.png",
            "secure_name": "sample-handwritten-id.enc",
            "mime_type": "image/png",
            "size_bytes": 365334,
            "classification": {
                "document_type": "Handwritten Note",
                "topic": "Finance",
                "sensitivity_level": "Internal",
                "content_characteristics": ["handwritten", "tabular", "financial"],
                "summary": "A handwritten business performance report outlining quarterly revenue, costs, and margins for Q1, Q2, and Q3. It indicates stable financial performance with upward trends.",
                "key_entities": ["Q1", "Q2", "Q3", "$120,000", "$138,000", "$155,000", "Business Performance"]
            },
            "pages": [
                {
                    "page_number": 1,
                    "text": """Business Performance
1. Overview
This sample report provides a brief review of quarterly business performance. It focuses on revenue growth, operating costs, and margin improvement across the reporting period. The goal is to present a snapshot of business progress and support planning decisions.
2. Key Points
- Revenue increased steadily over the quarter.
- Operating costs remained stable.
- Productivity improved as processes became more efficient.
3. Revenue Table
Quarter | Revenue | Cost | Margin
Q1 | $120,000 | $82,000 | 31.7%
Q2 | $138,000 | $90,000 | 34.8%
Q3 | $155,000 | $98,000 | 36.8%

The table shows a consistent upward trend in revenue and margin across all three quarters. This indicates stable financial performance and improving operational efficiency.
4. Conclusion
The results show steady business growth across the reporting period. Revenue increased each quarter, while margins improved, suggesting that the company is becoming more efficient as it scales.""",
                    "image_generator": lambda p: create_handwritten_image(p)
                }
            ]
        },
        {
            "id": "sample-nda-id",
            "original_name": "confidential_agreement.pdf",
            "secure_name": "sample-nda-id.enc",
            "mime_type": "application/pdf",
            "size_bytes": 18000,
            "classification": {
                "document_type": "Contract",
                "topic": "Legal",
                "sensitivity_level": "Confidential",
                "content_characteristics": ["structured", "legal"],
                "summary": "A mutual Non-Disclosure Agreement (NDA) between Build Fast with AI Inc. and the AI Intern Candidate, signed on June 12, 2026, protecting software designs and dataset configurations.",
                "key_entities": ["Build Fast with AI Inc.", "AI Intern Assessment Candidate", "NDA", "June 12, 2026", "Jane Doe"]
            },
            "pages": [
                {
                    "page_number": 1,
                    "text": """CONFIDENTIAL MUTUAL NDA
This Non-Disclosure Agreement ('Agreement') is entered into as of June 12, 2026 by and between:
Party A: Build Fast with AI Inc.
Party B: AI Intern Assessment Candidate

1. Purpose
The parties wish to explore a business opportunity regarding Document Intelligence and RAG agents. In connection with this, Party A may disclose proprietary software designs, vector space configurations, and encrypted dataset structures ('Confidential Information') to Party B. The receiving party agrees to hold all such information in strict confidence.

2. Exclusions & Terms
This Agreement shall remain in effect for a period of three (3) years from the date of disclosure. Confidential Information does not include information that is or becomes publicly known through no breach by the receiving party, or is independently developed without reference to the disclosing party's information.

Signed for Party A:                        Signed for Party B:
___________________                        ___________________
Name: Jane Doe, Chief Scientist            Name: AI Engineer Intern Candidate""",
                    "image_generator": lambda p: create_agreement_pdf(p)
                }
            ]
        },
        {
            "id": "sample-memo-id",
            "original_name": "unstructured_memo.txt",
            "secure_name": "sample-memo-id.enc",
            "mime_type": "text/plain",
            "size_bytes": 1500,
            "classification": {
                "document_type": "Memo",
                "topic": "Human Resources",
                "sensitivity_level": "Internal",
                "content_characteristics": ["unstructured", "text-only"],
                "summary": "An IT security memo describing API key handling, regulations regarding encrypted document storage (AES-256), and requirements for signed retrieval tokens.",
                "key_entities": ["IT Security Office", "June 12, 2026", "All Engineering Interns", "AES-256", "GEMINI_API_KEY"]
            },
            "pages": [
                {
                    "page_number": 1,
                    "text": """MEMORANDUM

TO: All Engineering Interns
FROM: IT Security Office
DATE: June 12, 2026
SUBJECT: Secure API Key Management & Vector Configurations

This memorandum outlines our mandatory policies regarding credentials and document safety.

1. API KEY STORAGE
Under no circumstances should any API keys (such as GEMINI_API_KEY, OPENAI_API_KEY, or database passwords) be committed to public git repositories. Always load keys using environment variables (e.g. via .env files loaded with python-dotenv).

2. DOCUMENT STORAGE REGULATIONS
All uploaded evaluation files containing financial or corporate project names must be encrypted. Our backend must perform filename hashing, renaming files to secure UUIDs, and encrypting bytes at rest using AES-256 symmetric ciphers.

3. RETRIEVAL SIGNING
When chatbot users request document source visualizations, URLs must contain short-lived signed tokens. Anonymous access to page images is strictly prohibited.

Compliance with these rules is monitored. Thank you for your cooperation.""",
                    "image_generator": lambda p: create_memo_txt(p)
                }
            ]
        }
    ]
    
    # Now run generation and insertion
    for doc in samples_data:
        doc_id = doc["id"]
        logger.info(f"Populating sample: {doc['original_name']}...")
        
        # 1. Generate local sample files in sample_docs folder
        temp_file_path = SAMPLE_DOCS_DIR / doc["original_name"]
        
        # Check generator
        if "pdf_generator" in doc:
            doc["pdf_generator"](temp_file_path)
        elif doc["pages"][0]["image_generator"]:
            doc["pages"][0]["image_generator"](temp_file_path)
            
        # 2. Encrypt original content and write to secure storage
        if temp_file_path.exists():
            with open(temp_file_path, "rb") as f:
                content = f.read()
            enc_content = encrypt_data(content)
            with open(SECURE_STORAGE_DIR / doc["secure_name"], "wb") as f:
                f.write(enc_content)
                
        # 3. Create document record
        now = datetime.utcnow().isoformat()
        upsert_document_precomputed(
            doc_id=doc_id,
            name=doc["original_name"],
            secure_name=doc["secure_name"],
            mime_type=doc["mime_type"],
            size_bytes=doc["size_bytes"],
            status="indexed",
            classification=doc["classification"],
            created_at=now
        )
        
        # 4. Save page details and render images
        for page in doc["pages"]:
            page_number = page["page_number"]
            page_id = f"{doc_id}_page_{page_number}"
            
            # Generate page image and save encrypted
            page_img_path = PAGE_IMAGES_DIR / f"{page_id}.enc"
            
            # Use actual image if it is an image document
            if doc["mime_type"].startswith("image/"):
                pil_img = Image.open(temp_file_path)
            else:
                # Draw page image mockup for visual references
                pil_img = Image.new('RGB', (800, 1000), color=(255, 255, 255))
                draw = ImageDraw.Draw(pil_img)
                
                # Write page text cleanly to simulate page screenshot
                draw.text((40, 40), f"Document: {doc['original_name']} | Page {page_number}", fill=(120, 120, 120))
                draw.line((40, 60, 760, 60), fill=(220, 220, 220), width=1)
                
                y = 90
                lines = page["text"].split("\n")
                for line in lines:
                    draw.text((40, y), line[:85], fill=(50, 50, 50))
                    y += 20
                    if y > 950:
                        break
                    
            import io
            img_byte_arr = io.BytesIO()
            save_img = pil_img.convert('RGB') if pil_img.mode in ('RGBA', 'LA') else pil_img
            save_img.save(img_byte_arr, format='JPEG', quality=80)
            enc_page_img = encrypt_data(img_byte_arr.getvalue())
            
            with open(page_img_path, "wb") as f:
                f.write(enc_page_img)
                
            insert_page(
                document_id=doc_id,
                page_number=page_number,
                extracted_text=page["text"],
                image_path=f"{page_id}.enc"
            )
            
            # 5. Chunk and insert
            chunks = chunk_text(page["text"], doc_id, page_number)
            for c in chunks:
                c["embedding"] = get_gemini_embedding(c["content"])
            insert_chunks(chunks)
    logger.info("Sample database populated successfully!")

if __name__ == "__main__":
    populate_database_with_samples()
