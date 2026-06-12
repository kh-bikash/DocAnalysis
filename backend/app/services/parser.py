import os
import io
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PIL import Image
import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from google import genai
from google.genai import types

from backend.app.config import PAGE_IMAGES_DIR, SECURE_STORAGE_DIR, GEMINI_API_KEY
from backend.app.services.security import encrypt_data

logger = logging.getLogger(__name__)

# Try to configure pytesseract path if it's installed in standard Windows location
standard_tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
]
for p in standard_tesseract_paths:
    if os.path.exists(p):
        pytesseract.pytesseract.tesseract_cmd = p
        logger.info(f"Configured Tesseract path to: {p}")
        break

def check_tesseract_available() -> bool:
    """Check if tesseract OCR binary is accessible."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def parse_digital_pdf_tables(page) -> str:
    """Extract tables using pdfplumber and format them as markdown tables."""
    tables_text = ""
    try:
        tables = page.extract_tables()
        if tables:
            for table in tables:
                if not table:
                    continue
                # Format table as Markdown
                markdown_table = "\n\n"
                headers = [str(cell or "").strip() for cell in table[0]]
                markdown_table += "| " + " | ".join(headers) + " |\n"
                markdown_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in table[1:]:
                    row_cells = [str(cell or "").strip() for cell in row]
                    markdown_table += "| " + " | ".join(row_cells) + " |\n"
                markdown_table += "\n"
                tables_text += markdown_table
    except Exception as e:
        logger.warning(f"Failed to extract tables: {e}")
    return tables_text

def run_gemini_ocr(image: Image.Image) -> str:
    """Use Gemini multimodal LLM to perform OCR on a PIL image."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set for remote OCR fallback.")
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Save image to bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()
        
        # Call Gemini
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type='image/png'),
                "Perform high-fidelity OCR on this document page. Transcribe all text accurately. "
                "If there are tables, extract them and format them as clear Markdown tables. "
                "Maintain formatting and structure. Return only the transcribed content without any conversational text."
            ]
        )
        return response.text or ""
    except Exception as e:
        logger.error(f"Gemini OCR failed: {e}")
        raise e

def run_local_ocr(image: Image.Image) -> str:
    """Use pytesseract to perform OCR on a PIL image."""
    try:
        return pytesseract.image_to_string(image)
    except Exception as e:
        logger.error(f"Local Tesseract OCR failed: {e}")
        raise e

def render_pdf_page_to_image(file_path: Path, page_number: int) -> Image.Image:
    """Render a PDF page to a PIL image using pypdfium2 (pure Python PDFium wrapper)."""
    # page_number is 1-indexed, pdfium is 0-indexed
    with pdfium.PdfDocument(str(file_path)) as pdf:
        page = pdf[page_number - 1]
        # Render with high resolution (scale=2)
        bitmap = page.render(scale=2)
        return bitmap.to_pil()

def parse_pdf(file_path: Path, doc_id: str) -> List[Dict[str, Any]]:
    """Parse PDF file page by page, rendering images, extracting text, and applying OCR if needed."""
    pages_data = []
    
    # 1. Open with pdfium for rendering and pdfplumber for digital text
    with pdfium.PdfDocument(str(file_path)) as pdf_renderer:
        with pdfplumber.open(file_path) as pdf:
            num_pages = len(pdf.pages)
            logger.info(f"Parsing PDF: {file_path.name} with {num_pages} pages")
            
            for idx in range(num_pages):
                page_num = idx + 1
                page = pdf.pages[idx]
                
                # Extract digital text
                text = page.extract_text() or ""
                # Extract tables as markdown
                tables_text = parse_digital_pdf_tables(page)
                if tables_text:
                    text += tables_text
                
                # Render page image (always render to store page image)
                try:
                    pdf_page = pdf_renderer[idx]
                    bitmap = pdf_page.render(scale=2)
                    pil_image = bitmap.to_pil()
                except Exception as e:
                    logger.error(f"Failed to render page {page_num} of {file_path.name}: {e}")
                    # Create a placeholder image if render fails
                    pil_image = Image.new('RGB', (800, 1000), color=(240, 240, 240))
                
                # Check if page is scanned/empty text and we should OCR
                if len(text.strip()) < 50:
                    logger.info(f"Page {page_num} has very little text ({len(text)} chars). Running OCR...")
                    # Run OCR
                    ocr_text = ""
                    ocr_success = False
                    
                    # Try local OCR first
                    if check_tesseract_available():
                        try:
                            ocr_text = run_local_ocr(pil_image)
                            ocr_success = True
                            logger.info(f"Page {page_num} local OCR successful.")
                        except Exception:
                            pass
                    
                    # If local OCR failed or unavailable, try Gemini OCR
                    if not ocr_success and GEMINI_API_KEY:
                        try:
                            ocr_text = run_gemini_ocr(pil_image)
                            ocr_success = True
                            logger.info(f"Page {page_num} Gemini OCR successful.")
                        except Exception as e:
                            logger.error(f"Page {page_num} Gemini OCR failed: {e}")
                    
                    if ocr_success:
                        text = ocr_text
                    else:
                        text += "\n[OCR Unavailable: Scanned page, missing Tesseract OCR and Gemini API key]"
                
                # Save and encrypt page image
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='JPEG', quality=85)
                encrypted_img = encrypt_data(img_byte_arr.getvalue())
                
                # Save encrypted file
                image_filename = f"{doc_id}_page_{page_num}.enc"
                image_path = PAGE_IMAGES_DIR / image_filename
                with open(image_path, "wb") as f:
                    f.write(encrypted_img)
                
                pages_data.append({
                    "page_number": page_num,
                    "text": text,
                    "image_path": image_filename
                })
            
    return pages_data

def parse_image(file_path: Path, doc_id: str, mime_type: str) -> List[Dict[str, Any]]:
    """Parse image file (PNG, JPG, etc.) as a single page document."""
    logger.info(f"Parsing image: {file_path.name}")
    try:
        pil_image = Image.open(file_path)
    except Exception as e:
        logger.error(f"Failed to open image file {file_path.name}: {e}")
        raise e
        
    text = ""
    ocr_success = False
    
    # Try local OCR
    if check_tesseract_available():
        try:
            text = run_local_ocr(pil_image)
            ocr_success = True
            logger.info("Image local OCR successful.")
        except Exception:
            pass
            
    # Try Gemini OCR
    if not ocr_success and GEMINI_API_KEY:
        try:
            text = run_gemini_ocr(pil_image)
            ocr_success = True
            logger.info("Image Gemini OCR successful.")
        except Exception as e:
            logger.error(f"Image Gemini OCR failed: {e}")
            
    if not ocr_success:
        text = "[OCR Unavailable: Scanned image, missing Tesseract OCR and Gemini API key]"
        
    # Save and encrypt page image
    img_byte_arr = io.BytesIO()
    # Convert RGBA to RGB for JPEG save
    if pil_image.mode in ('RGBA', 'LA'):
        rgb_image = Image.new('RGB', pil_image.size, (255, 255, 255))
        rgb_image.paste(pil_image, mask=pil_image.split()[3])
        rgb_image.save(img_byte_arr, format='JPEG', quality=85)
    else:
        pil_image.save(img_byte_arr, format='JPEG', quality=85)
        
    encrypted_img = encrypt_data(img_byte_arr.getvalue())
    
    image_filename = f"{doc_id}_page_1.enc"
    image_path = PAGE_IMAGES_DIR / image_filename
    with open(image_path, "wb") as f:
        f.write(encrypted_img)
        
    return [{
        "page_number": 1,
        "text": text,
        "image_path": image_filename
    }]

def parse_text_file(file_path: Path, doc_id: str) -> List[Dict[str, Any]]:
    """Parse a plain text file as a single page document."""
    logger.info(f"Parsing text file: {file_path.name}")
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        logger.error(f"Failed to read text file {file_path.name}: {e}")
        raise e
        
    # Generate a placeholder text page image (renders document content preview as image)
    from PIL import ImageDraw, ImageFont
    # Create an image representing a page
    pil_image = Image.new('RGB', (800, 1000), color=(250, 250, 250))
    draw = ImageDraw.Draw(pil_image)
    
    # Write some header and teaser text onto it
    draw.text((50, 50), f"Plain Text Document: {file_path.name}", fill=(50, 50, 50))
    draw.line((50, 80, 750, 80), fill=(200, 200, 200), width=2)
    
    # Write first few lines of text
    lines = text.split("\n")[:25]
    y = 100
    for line in lines:
        draw.text((50, y), line[:80], fill=(100, 100, 100))
        y += 30
        if y > 950:
            break
            
    img_byte_arr = io.BytesIO()
    pil_image.save(img_byte_arr, format='JPEG', quality=85)
    encrypted_img = encrypt_data(img_byte_arr.getvalue())
    
    image_filename = f"{doc_id}_page_1.enc"
    image_path = PAGE_IMAGES_DIR / image_filename
    with open(image_path, "wb") as f:
        f.write(encrypted_img)
        
    return [{
        "page_number": 1,
        "text": text,
        "image_path": image_filename
    }]

def parse_document(file_path: Path, doc_id: str, mime_type: str) -> List[Dict[str, Any]]:
    """Dispatches parsing based on file mime type."""
    suffix = file_path.suffix.lower()
    
    if suffix == ".pdf":
        return parse_pdf(file_path, doc_id)
    elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
        return parse_image(file_path, doc_id, mime_type)
    elif suffix == ".txt":
        return parse_text_file(file_path, doc_id)
    else:
        raise ValueError(f"Unsupported file suffix: {suffix}")
