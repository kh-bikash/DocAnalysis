import logging
import math
import re
from typing import List, Dict, Any, Tuple
import numpy as np
from google import genai
from google.genai import types

from backend.app.config import GEMINI_API_KEY
from backend.app.database import get_all_chunks, get_all_documents

logger = logging.getLogger(__name__)

def chunk_text(text: str, document_id: str, page_number: int, chunk_size: int = 600, overlap: int = 150) -> List[Dict[str, Any]]:
    """Split text into overlapping chunks, maintaining document and page metadata."""
    chunks = []
    text = text.strip()
    if not text:
        return []
        
    words = text.split()
    if not words:
        return []
        
    # Standard character-based chunking with word boundary consideration
    idx = 0
    chunk_index = 0
    
    while idx < len(text):
        start = idx
        end = min(start + chunk_size, len(text))
        
        # Adjust end to the next word boundary if possible, to avoid cutting words
        if end < len(text) and not text[end].isspace():
            space_idx = text.find(' ', end)
            if space_idx != -1 and space_idx - end < 30:
                end = space_idx
                
        chunk_content = text[start:end].strip()
        if chunk_content:
            chunks.append({
                "id": f"{document_id}_p{page_number}_c{chunk_index}",
                "document_id": document_id,
                "page_number": page_number,
                "chunk_index": chunk_index,
                "content": chunk_content
            })
            chunk_index += 1
            
        # Move forward by chunk_size - overlap
        idx = start + (chunk_size - overlap)
        if idx >= len(text) or end >= len(text):
            break
            
    return chunks

# --- Pure Python TF-IDF / BM25 Search Fallback ---
class BM25Retriever:
    """A simple in-memory BM25-like retriever for local text matching."""
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        self.doc_count = len(chunks)
        self.avg_doc_len = 0
        self.doc_lens = []
        self.doc_terms = []
        self.df = {}
        self.idf = {}
        
        if self.doc_count == 0:
            return
            
        total_len = 0
        for c in chunks:
            tokens = self._tokenize(c["content"])
            self.doc_terms.append(tokens)
            self.doc_lens.append(len(tokens))
            total_len += len(tokens)
            
            # Document frequency
            unique_tokens = set(tokens)
            for t in unique_tokens:
                self.df[t] = self.df.get(t, 0) + 1
                
        self.avg_doc_len = total_len / self.doc_count
        
        # Calculate IDF
        for t, f in self.df.items():
            self.idf[t] = math.log((self.doc_count - f + 0.5) / (f + 0.5) + 1.0)
            
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())
        
    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        if self.doc_count == 0:
            return []
            
        query_tokens = self._tokenize(query)
        scores = []
        
        k1 = 1.5
        b = 0.75
        
        for i, c in enumerate(self.chunks):
            score = 0.0
            tokens = self.doc_terms[i]
            doc_len = self.doc_lens[i]
            
            tf = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
                
            for q in query_tokens:
                if q not in self.idf:
                    continue
                q_tf = tf.get(q, 0)
                # BM25 formula
                numerator = q_tf * (k1 + 1)
                denominator = q_tf + k1 * (1 - b + b * (doc_len / self.avg_doc_len))
                score += self.idf[q] * (numerator / denominator)
                
            scores.append((c, score))
            
        # Sort and filter non-zero
        scores = sorted(scores, key=lambda x: x[1], reverse=True)
        return [s for s in scores if s[1] > 0.0][:top_k]

# --- Vector Embedding retrieval using Gemini API ---
def get_gemini_embedding(text: str) -> List[float]:
    """Get embedding vector using Gemini API."""
    if not GEMINI_API_KEY:
        return []
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.embed_content(
            model="gemini-embedding-2",
            contents=text
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"Failed to generate Gemini embedding: {e}")
        return []

def retrieve_relevant_chunks(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve top_k relevant chunks from SQLite. Uses Gemini embeddings or BM25 local fallback."""
    chunks = get_all_chunks()
    if not chunks:
        return []
        
    # Match documents metadata to get original_name
    docs_map = {d["id"]: d for d in get_all_documents()}
    
    # Check if Gemini key is active and we want to use vector search
    query_emb = []
    if GEMINI_API_KEY:
        query_emb = get_gemini_embedding(query)
        
    if query_emb and all(c.get("embedding") for c in chunks):
        # We have embeddings, do cosine similarity search
        logger.info("Running vector search using Cosine Similarity.")
        scored_chunks = []
        q_vec = np.array(query_emb)
        q_norm = np.linalg.norm(q_vec)
        
        for c in chunks:
            c_vec = np.array(c["embedding"])
            if len(c_vec) != len(q_vec):
                # Recalculate if dimensions mismatch
                c_vec_list = get_gemini_embedding(c["content"])
                c_vec = np.array(c_vec_list) if c_vec_list else np.zeros(len(q_vec))
            
            c_norm = np.linalg.norm(c_vec)
            if q_norm > 0 and c_norm > 0:
                sim = np.dot(q_vec, c_vec) / (q_norm * c_norm)
            else:
                sim = 0.0
            scored_chunks.append((c, sim))
            
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        results = []
        for c, score in scored_chunks[:top_k]:
            c_copy = c.copy()
            c_copy["score"] = float(score)
            c_copy["original_name"] = docs_map.get(c["document_id"], {}).get("original_name", "Unknown Document")
            results.append(c_copy)
        return results
    else:
        # Fallback to BM25 Local Text Search
        logger.info("Running keyword search using local BM25.")
        bm25 = BM25Retriever(chunks)
        scored_chunks = bm25.retrieve(query, top_k=top_k)
        
        results = []
        for c, score in scored_chunks:
            c_copy = c.copy()
            c_copy["score"] = float(score)
            c_copy["original_name"] = docs_map.get(c["document_id"], {}).get("original_name", "Unknown Document")
            results.append(c_copy)
            
        # If BM25 yields nothing, but we have text, return top chunks simply as fallback
        if not results:
            for c in chunks[:top_k]:
                c_copy = c.copy()
                c_copy["score"] = 0.0
                c_copy["original_name"] = docs_map.get(c["document_id"], {}).get("original_name", "Unknown Document")
                results.append(c_copy)
        return results

def synthesize_answer(query: str, chat_history: List[Dict[str, Any]], retrieved_chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Uses LLM to synthesize answer with inline citations, or returns fallback summary if offline."""
    if not retrieved_chunks:
        return "I could not find any relevant documents in the knowledge base to answer your question.", []
        
    # Deduplicate and sort citations
    citations = []
    seen_citations = set()
    for chunk in retrieved_chunks:
        cit_key = (chunk["document_id"], chunk["page_number"])
        if cit_key not in seen_citations:
            seen_citations.add(cit_key)
            citations.append({
                "document_id": chunk["document_id"],
                "document_name": chunk["original_name"],
                "page_number": chunk["page_number"]
            })
            
    if not GEMINI_API_KEY:
        # Fallback response for offline mode
        logger.info("GEMINI_API_KEY not set. Synthesizing answer locally.")
        ans = (
            "**[Demo Mode - No API Key]** Here are the most relevant sections found in the documents:\n\n"
        )
        for i, c in enumerate(retrieved_chunks[:3]):
            ans += f"- From **{c['original_name']}** (Page {c['page_number']}):\n  > \"{c['content'][:150]}...\"\n\n"
        ans += "\n*Provide a `GEMINI_API_KEY` in the environment variables to enable full conversational answers.*"
        return ans, citations

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Build prompt
        context_str = ""
        for i, chunk in enumerate(retrieved_chunks):
            context_str += f"--- CONTEXT CHUNK {i+1} (Source: {chunk['original_name']}, Page: {chunk['page_number']}) ---\n"
            context_str += f"{chunk['content']}\n\n"
            
        history_str = ""
        # Include last 4 messages of history
        for msg in chat_history[-4:]:
            history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"
            
        prompt = (
            f"You are an AI assistant powered by grounded Document Intelligence. Your task is to answer the user's query "
            f"accurately using ONLY the text chunks provided below. You must verify every statement you make using these chunks.\n\n"
            f"CRITICAL RULES:\n"
            f"1. Every statement in your answer must be supported by the provided context chunks.\n"
            f"2. You MUST include inline citations in the text exactly in the format '[DocumentName, Page X]'. E.g. 'The revenue increased by 15% [report.pdf, Page 3].'\n"
            f"3. Do NOT cite any document or page number that is not explicitly in the context below.\n"
            f"4. If the provided context does not contain relevant information to answer the question, state exactly: "
            f"'I could not find any relevant information in the uploaded documents to answer this question.' Do NOT hallucinate or use external knowledge.\n\n"
            f"--- CONTEXTS ---\n{context_str}\n"
            f"--- CONVERSATION HISTORY ---\n{history_str}\n"
            f"User Query: {query}\n\n"
            f"Grounded Answer (remember citations like [filename.pdf, Page X]):"
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0
            )
        )
        
        answer = response.text or ""
        return answer, citations
    except Exception as e:
        logger.error(f"Failed to synthesize Gemini answer: {e}")
        # Return fallback on failure
        return "Failed to contact Gemini API. Here is the retrieved source content:\n\n" + "\n\n".join([f"**{c['original_name']} (Page {c['page_number']})**: {c['content']}" for c in retrieved_chunks[:2]]), citations
