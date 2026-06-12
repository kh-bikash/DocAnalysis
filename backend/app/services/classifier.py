import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from backend.app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Pydantic classification schema for structured LLM outputs
class DocumentClassification(BaseModel):
    document_type: str = Field(description="Type of document, e.g., Invoice, Contract, Report, Handwritten Note, Memo, Plain Text, Form.")
    topic: str = Field(description="Primary topic/domain, e.g., Finance, Legal, Technical, Human Resources, Personal, Operations.")
    sensitivity_level: str = Field(description="Sensitivity rating: Public, Internal, Confidential, Highly Sensitive.")
    content_characteristics: List[str] = Field(description="Key attributes, e.g., tabular, handwritten, image-heavy, dense, long-form, unstructured.")
    summary: str = Field(description="A 2-3 sentence summary of the document's core content.")
    key_entities: List[str] = Field(description="Key entities extracted (names, companies, dates, total amounts, etc.).")

def run_local_classifier_fallback(text: str) -> Dict[str, Any]:
    """Fallback classifier using keyword rules if Gemini API is unavailable."""
    text_lower = text.lower()
    
    # Document Type heuristics
    doc_type = "Unstructured Document"
    topic = "General"
    sensitivity = "Internal"
    characteristics = []
    entities = []
    
    if "invoice" in text_lower or "bill to" in text_lower or "total due" in text_lower or "amount" in text_lower:
        doc_type = "Invoice"
        topic = "Finance"
        sensitivity = "Confidential"
        characteristics.append("tabular")
        if "$" in text_lower or "€" in text_lower or "total" in text_lower:
            characteristics.append("financial")
    elif "agreement" in text_lower or "contract" in text_lower or "hereby" in text_lower or "parties" in text_lower:
        doc_type = "Contract"
        topic = "Legal"
        sensitivity = "Confidential"
        characteristics.append("structured")
    elif "handwritten" in text_lower or "[handwritten]" in text_lower:
        doc_type = "Handwritten Note"
        topic = "Personal"
        sensitivity = "Internal"
        characteristics.append("handwritten")
    elif "report" in text_lower or "introduction" in text_lower or "results" in text_lower:
        doc_type = "Report"
        topic = "Technical"
        sensitivity = "Internal"
        characteristics.append("long-form")
    elif len(text.strip()) < 500:
        doc_type = "Memo"
        topic = "General"
        sensitivity = "Internal"
        characteristics.append("unstructured")
        
    if "confidential" in text_lower or "proprietary" in text_lower or "secret" in text_lower:
        sensitivity = "Confidential"
    if "social security" in text_lower or "ssn" in text_lower or "passport" in text_lower:
        sensitivity = "Highly Sensitive"
        characteristics.append("pii")

    # Crude entity extraction
    import re
    # Extract total money
    money = re.findall(r'\$\d+(?:\.\d{2})?', text)
    if money:
        entities.extend(money[:3])
    # Extract years/dates
    dates = re.findall(r'\b(?:19|20)\d{2}\b', text)
    if dates:
        entities.extend([f"Year {d}" for d in dates[:2]])

    summary = f"A {doc_type.lower()} discussing {topic.lower()} details. "
    if len(text.strip()) > 10:
        summary += f"Preview: {text.strip()[:100]}..."
    else:
        summary += "The document contains no readable text."

    return {
        "document_type": doc_type,
        "topic": topic,
        "sensitivity_level": sensitivity,
        "content_characteristics": characteristics,
        "summary": summary,
        "key_entities": list(set(entities))
    }

def classify_document(text: str) -> Dict[str, Any]:
    """Classify the document text using Gemini structured JSON generation (or fallback)."""
    if not text.strip():
        return {
            "document_type": "Empty Document",
            "topic": "None",
            "sensitivity_level": "Public",
            "content_characteristics": ["empty"],
            "summary": "This document contains no text content.",
            "key_entities": []
        }

    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set. Using rule-based fallback classifier.")
        return run_local_classifier_fallback(text)

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Request structured classification using the Pydantic schema
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=(
                f"Analyze the following document text and classify it across multiple dimensions. "
                f"You must populate all schema fields. Here is the document text:\n\n{text[:15000]}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DocumentClassification,
                temperature=0.1
            )
        )
        
        # Parse JSON output
        parsed_classification = json.loads(response.text)
        logger.info("Document successfully classified using Gemini API.")
        return parsed_classification
    except Exception as e:
        logger.error(f"Structured Gemini classification failed: {e}. Falling back...")
        return run_local_classifier_fallback(text)
