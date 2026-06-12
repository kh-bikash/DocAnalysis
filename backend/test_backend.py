import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Add current folder to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.main import app
from backend.app.database import get_all_documents, get_document_pages
from backend.app.services.security import decrypt_data

client = TestClient(app)

class TestBackendAPI(unittest.TestCase):

    def test_list_documents(self):
        """Test that documents endpoint lists preloaded files."""
        response = client.get("/api/documents")
        self.assertEqual(response.status_code, 200)
        docs = response.json()
        self.assertGreater(len(docs), 0)
        
        # Verify sample invoice is present
        invoice = next((d for d in docs if d["original_name"] == "invoice_sample.pdf"), None)
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice["status"], "indexed")
        
        # Verify classification is parsed
        self.assertIsNotNone(invoice["classification"])
        self.assertEqual(invoice["classification"]["document_type"], "Invoice")

    def test_chat_and_citations(self):
        """Test chat queries, citations, and signed URLs."""
        # Query about invoice
        response = client.post("/api/chat", data={
            "message": "What is the total due on the invoice from ACME?",
            "session_id": "test_session_123"
        })
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        
        self.assertIn("answer", res_data)
        self.assertIn("citations", res_data)
        
        citations = res_data["citations"]
        self.assertGreater(len(citations), 0)
        
        # Check citations format
        cited_names = [c["document_name"] for c in citations]
        self.assertIn("invoice_sample.pdf", cited_names)
        
        # Verify the citation image URL is present
        cit = citations[0]
        self.assertIn("image_url", cit)
        
        # Attempt to access the page image with the token
        from urllib.parse import urlparse
        parsed = urlparse(cit["image_url"])
        img_url = f"{parsed.path}?{parsed.query}"
        img_response = client.get(img_url)
        self.assertEqual(img_response.status_code, 200)
        self.assertEqual(img_response.headers["content-type"], "image/jpeg")
        
        # Verify it can be decrypted (content returned is already decrypted by the endpoint)
        self.assertGreater(len(img_response.content), 0)

    def test_security_signed_url_failure(self):
        """Test that accessing page images without a valid signature token fails."""
        # Get pages for sample invoice
        docs = get_all_documents()
        invoice = next(d for d in docs if d["original_name"] == "invoice_sample.pdf")
        doc_id = invoice["id"]
        
        # Try to access without token
        response = client.get(f"/api/documents/{doc_id}/pages/1")
        self.assertEqual(response.status_code, 422) # Missing query parameter 'token'
        
        # Try to access with invalid token
        response = client.get(f"/api/documents/{doc_id}/pages/1?token=badtoken123")
        self.assertEqual(response.status_code, 403) # Forbidden
        self.assertIn("Invalid or expired access token", response.json()["detail"])

    def test_encryption_at_rest(self):
        """Test that page images and original uploads are stored encrypted on disk."""
        docs = get_all_documents()
        invoice = next(d for d in docs if d["original_name"] == "invoice_sample.pdf")
        doc_id = invoice["id"]
        
        # Check original file
        secure_name = invoice["secure_name"]
        from backend.app.config import SECURE_STORAGE_DIR, PAGE_IMAGES_DIR
        
        original_storage_path = SECURE_STORAGE_DIR / secure_name
        self.assertTrue(original_storage_path.exists())
        
        with open(original_storage_path, "rb") as f:
            encrypted_data = f.read()
            
        # Verify it's encrypted (should not start with standard PDF header '%PDF-')
        self.assertFalse(encrypted_data.startswith(b"%PDF-"))
        
        # Verify it decrypts back to PDF
        decrypted_data = decrypt_data(encrypted_data)
        self.assertTrue(decrypted_data.startswith(b"%PDF-"))
        
        # Check page image encryption
        pages = get_document_pages(doc_id)
        page_image_name = pages[0]["image_path"]
        page_image_path = PAGE_IMAGES_DIR / page_image_name
        
        self.assertTrue(page_image_path.exists())
        with open(page_image_path, "rb") as f:
            encrypted_img = f.read()
            
        # Verify it's encrypted (JPEG magic numbers are usually FF D8 FF)
        self.assertFalse(encrypted_img.startswith(b"\xff\xd8\xff"))
        
        # Verify it decrypts back to JPEG
        decrypted_img = decrypt_data(encrypted_img)
        self.assertTrue(decrypted_img.startswith(b"\xff\xd8\xff"))

if __name__ == "__main__":
    unittest.main()
