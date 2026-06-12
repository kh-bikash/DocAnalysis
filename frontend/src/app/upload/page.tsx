'use client';

import React, { useState, useEffect, useRef } from 'react';

interface Classification {
  document_type: string;
  topic: string;
  sensitivity_level: string;
  content_characteristics: string[];
  summary: string;
  key_entities: string[];
}

interface Document {
  id: string;
  original_name: string;
  secure_name: string;
  mime_type: string;
  size_bytes: number;
  status: 'pending' | 'parsing' | 'classifying' | 'indexed' | 'failed';
  error_message?: string;
  classification?: Classification;
  created_at: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function UploadPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch documents on load
  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_URL}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    
    // Set up polling for pending/processing documents
    const interval = setInterval(() => {
      setDocuments((prevDocs) => {
        const hasProcessing = prevDocs.some(
          (doc) => ['pending', 'parsing', 'classifying'].includes(doc.status)
        );
        if (hasProcessing) {
          fetchDocuments();
        }
        return prevDocs;
      });
    }, 2500);

    return () => clearInterval(interval);
  }, []);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      // Basic client-side validation
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      const allowed = ['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt'];
      
      if (!allowed.includes(ext)) {
        alert(`File ${file.name} has unsupported type. Allowed: PDF, PNG, JPG, WEBP, TXT`);
        continue;
      }

      if (file.size > 10 * 1024 * 1024) {
        alert(`File ${file.name} is too large. Max size: 10MB`);
        continue;
      }

      // Prepare payload
      const formData = new FormData();
      formData.append('file', file);

      // Add optimistic document to list
      const tempId = `temp-${Date.now()}-${file.name}`;
      const optimisticDoc: Document = {
        id: tempId,
        original_name: file.name,
        secure_name: '',
        mime_type: file.type,
        size_bytes: file.size,
        status: 'pending',
        created_at: new Date().toISOString()
      };
      
      setDocuments(prev => [optimisticDoc, ...prev]);

      try {
        const res = await fetch(`${API_URL}/api/upload`, {
          method: 'POST',
          body: formData,
        });

        if (res.ok) {
          const data = await res.json();
          // Update the list with actual registered document metadata
          setDocuments(prev => prev.map(d => d.id === tempId ? data : d));
        } else {
          const errorData = await res.json();
          setDocuments(prev => prev.map(d => d.id === tempId ? {
            ...d,
            status: 'failed',
            error_message: errorData.detail || 'Upload failed'
          } : d));
        }
      } catch (err) {
        console.error('Upload error:', err);
        setDocuments(prev => prev.map(d => d.id === tempId ? {
          ...d,
          status: 'failed',
          error_message: 'Network error or server offline'
        } : d));
      }
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusBadge = (status: Document['status']) => {
    switch (status) {
      case 'pending':
        return <span style={{ color: 'var(--text-muted)' }}>Queued 🕒</span>;
      case 'parsing':
        return <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>Parsing 🔄</span>;
      case 'classifying':
        return <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Classifying 🧠</span>;
      case 'indexed':
        return <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>Indexed ✅</span>;
      case 'failed':
        return <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>Failed ❌</span>;
      default:
        return <span>{status}</span>;
    }
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
      {/* Title */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '8px', color: 'var(--text-main)' }}>Secure Knowledge Base</h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Upload messy real-world files, contracts, text logs, invoices, or scanned documents. They will be encrypted at rest, parsed, classified, and indexed for search.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selectedDoc ? '1fr 380px' : '1fr', gap: '30px', transition: 'all 0.3s ease' }}>
        
        {/* Main Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
          
          {/* Upload Zone */}
          <div
            className="glass-panel"
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={triggerFileInput}
            style={{
              padding: '60px 40px',
              textAlign: 'center',
              cursor: 'pointer',
              borderStyle: dragActive ? 'solid' : 'dashed',
              borderColor: dragActive ? 'var(--primary)' : 'var(--border-color)',
              background: dragActive ? 'rgba(139, 92, 246, 0.08)' : 'var(--bg-card)',
              transition: 'var(--transition-smooth)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '16px'
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              multiple
              style={{ display: 'none' }}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.txt"
            />
            
            {/* Upload Icon */}
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--shadow-premium)'
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
            </div>
            
            <div>
              <h3 style={{ fontSize: '1.25rem', color: 'var(--text-main)', marginBottom: '6px' }}>Drag & Drop Files Here</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                or <span style={{ color: 'var(--primary)', fontWeight: 600 }}>browse files</span> from your computer
              </p>
            </div>
            
            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              Supports PDF, PNG, JPG, WEBP, TXT up to 10MB per file
            </span>
          </div>

          {/* Document list */}
          <div className="glass-panel" style={{ padding: '0px', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1.2rem', color: 'var(--text-main)' }}>Ingested Documents</h3>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{documents.length} Files</span>
            </div>

            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                Loading knowledge base documents...
              </div>
            ) : documents.length === 0 ? (
              <div style={{ padding: '60px 40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                No documents found. Drag & drop files above to populate your database!
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 120px 140px 100px',
                      alignItems: 'center',
                      padding: '16px 24px',
                      borderBottom: '1px solid rgba(255,255,255,0.03)',
                      background: selectedDoc?.id === doc.id ? 'rgba(255,255,255,0.02)' : 'transparent',
                      transition: 'all 0.15s ease',
                      cursor: doc.status === 'indexed' ? 'pointer' : 'default'
                    }}
                    onClick={() => {
                      if (doc.status === 'indexed') {
                        setSelectedDoc(doc);
                      }
                    }}
                  >
                    {/* Filename */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', overflow: 'hidden' }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <span style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--text-main)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {doc.original_name}
                      </span>
                    </div>

                    {/* Size */}
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{formatSize(doc.size_bytes)}</span>

                    {/* Status */}
                    <div style={{ fontSize: '0.85rem' }}>{getStatusBadge(doc.status)}</div>

                    {/* Actions */}
                    <div style={{ textAlign: 'right' }}>
                      {doc.status === 'indexed' && (
                        <button
                          style={{
                            background: 'rgba(139, 92, 246, 0.1)',
                            border: '1px solid rgba(139, 92, 246, 0.3)',
                            borderRadius: '6px',
                            color: 'var(--primary)',
                            padding: '6px 12px',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                            fontWeight: 600,
                            transition: 'var(--transition-fast)'
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDoc(doc);
                          }}
                        >
                          Details
                        </button>
                      )}
                      {doc.status === 'failed' && (
                        <span style={{ color: 'var(--accent-red)', fontSize: '0.8rem', cursor: 'help' }} title={doc.error_message}>
                          Error details
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Side Details Drawer */}
        {selectedDoc && selectedDoc.classification && (
          <div
            className="glass-panel"
            style={{
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '24px',
              position: 'sticky',
              top: '40px',
              height: 'fit-content',
              animation: 'slide-up 0.25s ease'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
              <h3 style={{ color: 'var(--text-main)', fontSize: '1.2rem' }}>Document Analysis</h3>
              <button
                onClick={() => setSelectedDoc(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '1.2rem'
                }}
              >
                &times;
              </button>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Original Name</span>
              <p style={{ color: 'var(--text-main)', fontWeight: 500, fontSize: '0.9rem', wordBreak: 'break-all' }}>{selectedDoc.original_name}</p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Document Type</span>
                <span style={{
                  display: 'inline-block',
                  background: 'rgba(255,255,255,0.04)',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: 'var(--accent-teal)'
                }}>{selectedDoc.classification.document_type}</span>
              </div>
              
              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Sensitivity Level</span>
                <span style={{
                  display: 'inline-block',
                  background: selectedDoc.classification.sensitivity_level === 'Confidential' || selectedDoc.classification.sensitivity_level === 'Highly Sensitive' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(255,255,255,0.04)',
                  border: selectedDoc.classification.sensitivity_level === 'Confidential' || selectedDoc.classification.sensitivity_level === 'Highly Sensitive' ? '1px solid rgba(239, 68, 68, 0.2)' : 'none',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: selectedDoc.classification.sensitivity_level === 'Confidential' || selectedDoc.classification.sensitivity_level === 'Highly Sensitive' ? 'var(--accent-red)' : 'var(--text-secondary)'
                }}>{selectedDoc.classification.sensitivity_level}</span>
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Primary Topic</span>
              <p style={{ color: 'var(--text-main)', fontSize: '0.9rem', fontWeight: 500 }}>{selectedDoc.classification.topic}</p>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Overview Summary</span>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: 1.5 }}>{selectedDoc.classification.summary}</p>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>Content Characteristics</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {selectedDoc.classification.content_characteristics.map((c, i) => (
                  <span key={i} style={{ background: 'rgba(139, 92, 246, 0.08)', color: 'var(--primary)', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
                    {c}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>Extracted Key Entities</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {selectedDoc.classification.key_entities.map((e, i) => (
                  <span key={i} style={{ background: 'rgba(15,23,42,0.03)', color: 'var(--text-main)', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', border: '1px solid var(--border-color)' }}>
                    {e}
                  </span>
                ))}
              </div>
            </div>
            
            <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px', display: 'flex', gap: '8px' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginTop: '2px' }}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                This file is encrypted at rest using AES-256 Fernet. Search queries are authenticated and vector searches are sandboxed.
              </span>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
