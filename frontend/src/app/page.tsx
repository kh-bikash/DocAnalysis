'use client';

import React, { useState, useEffect, useRef } from 'react';

interface Citation {
  document_id: string;
  document_name: string;
  page_number: number;
  image_url: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function ChatbotPage() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Voice Input State
  const [isListening, setIsListening] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState('');
  const [speechError, setSpeechError] = useState<string | null>(null);
  
  // Lightbox State
  const [lightboxImage, setLightboxImage] = useState<{ url: string; title: string } | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Initialize session ID and load preloaded welcome message
  useEffect(() => {
    setSessionId(`session-${Math.random().toString(36).substring(2, 11)}`);
    setMessages([
      {
        role: 'assistant',
        content: "Hello! I am your **Document Intelligence Agent**. I can help you search and analyze uploaded contracts, financial sheets, invoices, plain text, and hand-written memos. Ask me any question, and I'll answer with inline citations and matching page screenshots!"
      }
    ]);
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveTranscript]);

  // Initialize Web Speech API
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = 'en-US';

        rec.onresult = (e: any) => {
          let interim = '';
          let final = '';
          for (let i = e.resultIndex; i < e.results.length; ++i) {
            if (e.results[i].isFinal) {
              final += e.results[i][0].transcript;
            } else {
              interim += e.results[i][0].transcript;
            }
          }
          const spokenText = final || interim;
          setLiveTranscript(spokenText);
          setInput(spokenText);
        };

        rec.onerror = (e: any) => {
          console.error('Speech recognition error code:', e.error);
          setIsListening(false);
          if (e.error === 'network') {
            setSpeechError('Speech recognition network error. Google Chrome speech recognition requires an active internet connection.');
          } else if (e.error === 'not-allowed') {
            setSpeechError('Microphone permission blocked. Please grant microphone permissions in your browser settings.');
          } else if (e.error === 'no-speech') {
            console.log('No speech detected.');
          } else {
            setSpeechError(`Speech recognition error: ${e.error}`);
          }
        };

        rec.onend = () => {
          setIsListening(false);
        };

        recognitionRef.current = rec;
      }
    }
  }, []);

  const handleVoiceInput = () => {
    if (!recognitionRef.current) {
      alert('Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
      if (liveTranscript.trim()) {
        handleSubmit(null, liveTranscript);
      }
      setLiveTranscript('');
    } else {
      setInput('');
      setLiveTranscript('');
      setSpeechError(null);
      setIsListening(true);
      recognitionRef.current.start();
    }
  };

  const handleSubmit = async (e: React.FormEvent | null, overrideMessage?: string) => {
    if (e) e.preventDefault();
    
    const messageText = (overrideMessage || input).trim();
    if (!messageText || isLoading) return;

    // Save input and clear
    setInput('');
    setIsListening(false);
    if (recognitionRef.current) recognitionRef.current.stop();

    // Add user message
    const userMsg: Message = { role: 'user', content: messageText };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append('message', messageText);
      formData.append('session_id', sessionId);

      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg: Message = {
          role: 'assistant',
          content: data.answer,
          citations: data.citations
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: "Sorry, I encountered an error. Please verify the server is running."
        }]);
      }
    } catch (err) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Failed to connect to the backend API. Please make sure the backend is active at ${API_URL}.`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Lightbox Zoom & Pan Handlers
  const handleZoom = (factor: number) => {
    setZoomLevel(prev => Math.max(0.5, Math.min(prev * factor, 5)));
  };

  const handleReset = () => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPanOffset({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Parse text for citations like [invoice_sample.pdf, Page 1] and render them as badges
  const renderTextWithCitations = (text: string, citations: Citation[] = []) => {
    // Regex matches [DocumentName, Page X]
    const regex = /(\[[^\]]+,\s*Page\s*\d+\])/g;
    const parts = text.split(regex);

    return parts.map((part, i) => {
      const match = part.match(/\[([^,]+),\s*Page\s*(\d+)\]/);
      if (match) {
        const docName = match[1].trim();
        const pageNum = parseInt(match[2]);
        
        // Find matching citation to get URL
        const citation = citations.find(
          c => c.document_name.toLowerCase() === docName.toLowerCase() && c.page_number === pageNum
        );

        return (
          <button
            key={i}
            onClick={() => {
              if (citation) {
                setLightboxImage({ url: citation.image_url, title: `${citation.document_name} - Page ${citation.page_number}` });
                handleReset();
              } else {
                alert(`Source image for ${docName} Page ${pageNum} is not available in vector context.`);
              }
            }}
            style={{
              background: 'rgba(139, 92, 246, 0.15)',
              border: '1px solid rgba(139, 92, 246, 0.4)',
              borderRadius: '4px',
              padding: '1px 6px',
              margin: '0 3px',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              transition: 'var(--transition-fast)'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(139, 92, 246, 0.3)';
              e.currentTarget.style.boxShadow = '0 0 8px rgba(139, 92, 246, 0.4)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'rgba(139, 92, 246, 0.15)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            {docName.length > 15 ? `${docName.substring(0, 12)}...` : docName} (P. {pageNum})
          </button>
        );
      }

      // Handle bold text formatting simply
      const boldRegex = /\*\*([^*]+)\*\*/g;
      const subParts = part.split(boldRegex);
      return (
        <span key={i}>
          {subParts.map((subPart, j) => {
            if (j % 2 === 1) {
              return <strong key={j} style={{ color: 'var(--text-main)', fontWeight: 600 }}>{subPart}</strong>;
            }
            return subPart;
          })}
        </span>
      );
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', position: 'relative' }}>
      
      {/* Top Header */}
      <header style={{
        padding: '16px 24px',
        borderBottom: '1px solid var(--border-color)',
        background: '#ffffff',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0
      }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', color: 'var(--text-main)' }}>Grounded RAG Assistant</h2>
          <span style={{ fontSize: '0.75rem', color: 'var(--accent-teal)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-teal)', display: 'inline-block' }}></span>
            Active Ingestion & Encrypted Storage
          </span>
        </div>
      </header>

      {/* Messages Scroll Area */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '30px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px'
      }}>
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '75%',
              animation: 'slide-up 0.2s ease-out'
            }}
          >
            {/* Sender header */}
            <span style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              marginBottom: '6px',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              fontWeight: 600
            }}>
              {msg.role === 'user' ? 'You' : 'DocIntel Agent'}
            </span>

            {/* Bubble */}
            <div
              className="glass-panel"
              style={{
                padding: '16px 20px',
                borderRadius: msg.role === 'user' ? '16px 16px 2px 16px' : '16px 16px 16px 2px',
                background: msg.role === 'user' ? 'linear-gradient(135deg, hsl(262, 80%, 55%) 0%, hsl(262, 80%, 48%) 100%)' : 'var(--bg-card)',
                borderColor: msg.role === 'user' ? 'rgba(99, 102, 241, 0.2)' : 'var(--border-color)',
                color: msg.role === 'user' ? '#ffffff' : 'var(--text-main)',
                boxShadow: msg.role === 'user' ? '0 4px 14px rgba(99, 102, 241, 0.15)' : 'var(--shadow-premium)'
              }}
            >
              <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>
                {renderTextWithCitations(msg.content, msg.citations)}
              </div>
            </div>

            {/* Cited page thumbnails */}
            {msg.citations && msg.citations.length > 0 && (
              <div style={{
                marginTop: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>CITED PAGES:</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                  {msg.citations.map((cit, cIdx) => (
                    <div
                      key={cIdx}
                      className="glass-panel"
                      onClick={() => {
                        setLightboxImage({ url: cit.image_url, title: `${cit.document_name} - Page ${cit.page_number}` });
                        handleReset();
                      }}
                      style={{
                        padding: '6px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        background: '#ffffff',
                        border: '1px solid var(--border-color)',
                        transition: 'var(--transition-fast)'
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.borderColor = 'var(--primary)';
                        e.currentTarget.style.transform = 'translateY(-2px)';
                      }}
                      onMouseOut={(e) => {
                        e.currentTarget.style.borderColor = 'var(--border-color)';
                        e.currentTarget.style.transform = 'none';
                      }}
                    >
                      {/* Mini thumbnail wrapper */}
                      <div style={{
                        width: '40px',
                        height: '50px',
                        borderRadius: '4px',
                        overflow: 'hidden',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        position: 'relative'
                      }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={cit.image_url}
                          alt="Thumbnail"
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)', maxWidth: '140px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                          {cit.document_name}
                        </span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Page {cit.page_number}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Live speech transcription bubble */}
        {isListening && liveTranscript && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignSelf: 'flex-end',
            maxWidth: '75%',
            animation: 'slide-up 0.15s ease'
          }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--primary)', marginBottom: '6px', alignSelf: 'flex-end', fontWeight: 600 }}>
              Listening... (Live Transcript)
            </span>
            <div className="glass-panel" style={{
              padding: '16px 20px',
              borderRadius: '16px 16px 2px 16px',
              background: 'rgba(139, 92, 246, 0.05)',
              borderColor: 'var(--primary)',
              boxShadow: 'var(--shadow-glow)',
              opacity: 0.85
            }}>
              <p style={{ color: 'var(--text-main)', fontStyle: 'italic' }}>
                {liveTranscript}
              </p>
            </div>
          </div>
        )}

        {/* Loading status */}
        {isLoading && (
          <div style={{
            alignSelf: 'flex-start',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: 'var(--text-muted)',
            fontSize: '0.85rem',
            padding: '4px 12px'
          }}>
            <span style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              border: '2px solid var(--primary)',
              borderTopColor: 'transparent',
              animation: 'rotate-spin 0.8s linear infinite',
              display: 'inline-block'
            }}></span>
            Synthesizing grounded citations answer...
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Chat Form Area */}
      <div style={{
        padding: '20px 24px',
        borderTop: '1px solid var(--border-color)',
        background: '#ffffff',
        flexShrink: 0
      }}>
        {speechError && (
          <div style={{
            padding: '10px 16px',
            margin: '0 auto 16px auto',
            maxWidth: '1000px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: '10px',
            color: 'var(--accent-red)',
            fontSize: '0.88rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.02)'
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {speechError}
            </span>
            <button 
              type="button" 
              onClick={() => setSpeechError(null)} 
              style={{ 
                background: 'none', 
                border: 'none', 
                color: 'var(--accent-red)', 
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '1.2rem',
                lineHeight: 1,
                padding: '0 4px'
              }}
            >
              &times;
            </button>
          </div>
        )}
        <form onSubmit={(e) => handleSubmit(e)} style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          maxWidth: '1000px',
          margin: '0 auto',
          width: '100%'
        }}>
          
          {/* Voice Input Button */}
          <button
            type="button"
            onClick={handleVoiceInput}
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '12px',
              background: isListening ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255, 255, 255, 0.03)',
              border: isListening ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid var(--border-color)',
              color: isListening ? 'var(--accent-red)' : 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              transition: 'var(--transition-smooth)',
              flexShrink: 0
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.borderColor = isListening ? 'var(--accent-red)' : 'var(--primary)';
              e.currentTarget.style.transform = 'scale(1.04)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = isListening ? 'rgba(239, 68, 68, 0.4)' : 'var(--border-color)';
              e.currentTarget.style.transform = 'none';
            }}
          >
            {isListening ? (
              // Pulse mic icon
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: 'pulse-soft 1s infinite' }}>
                <line x1="12" y1="19" x2="12" y2="23" />
                <path d="M8 23h8" />
                <rect x="6" y="2" width="12" height="13" rx="6" />
              </svg>
            ) : (
              // Idle mic icon
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="19" x2="12" y2="23" />
                <path d="M8 23h8" />
                <rect x="6" y="2" width="12" height="13" rx="6" />
              </svg>
            )}
          </button>

          {/* Text Input Box */}
          <div style={{
            position: 'relative',
            flex: 1,
            display: 'flex',
            alignItems: 'center'
          }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isListening ? "Listening... speak clearly" : "Ask a question about the database documents..."}
              disabled={isLoading}
              style={{
                width: '100%',
                padding: '14px 20px',
                borderRadius: '12px',
                background: '#f8fafc',
                border: '1px solid var(--border-color)',
                color: 'var(--text-main)',
                fontSize: '0.95rem',
                outline: 'none',
                transition: 'var(--transition-smooth)'
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'var(--primary)';
                e.target.style.background = 'rgba(255,255,255,0.04)';
                e.target.style.boxShadow = 'var(--shadow-glow)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--border-color)';
                e.target.style.background = 'rgba(255,255,255,0.02)';
                e.target.style.boxShadow = 'none';
              }}
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '12px',
              background: input.trim() ? 'var(--primary)' : 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border-color)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: input.trim() ? 'pointer' : 'default',
              transition: 'var(--transition-smooth)',
              flexShrink: 0
            }}
            onMouseOver={(e) => {
              if (input.trim()) {
                e.currentTarget.style.background = 'var(--primary-hover)';
                e.currentTarget.style.transform = 'scale(1.04)';
              }
            }}
            onMouseOut={(e) => {
              if (input.trim()) {
                e.currentTarget.style.background = 'var(--primary)';
                e.currentTarget.style.transform = 'none';
              }
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>

      {/* Zoomable / Pannable Lightbox Overlay */}
      {lightboxImage && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'rgba(3, 7, 18, 0.92)',
            backdropFilter: 'blur(20px)',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            animation: 'fade-in 0.2s ease-out'
          }}
        >
          {/* Lightbox Toolbar */}
          <div style={{
            padding: '16px 24px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'rgba(0,0,0,0.4)'
          }}>
            <h3 style={{ color: '#fff', fontSize: '1.1rem' }}>{lightboxImage.title}</h3>
            
            {/* Toolbar Buttons */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <button onClick={() => handleZoom(1.2)} style={toolbarButtonStyle} title="Zoom In">
                Zoom +
              </button>
              <button onClick={() => handleZoom(0.8)} style={toolbarButtonStyle} title="Zoom Out">
                Zoom -
              </button>
              <button onClick={handleReset} style={toolbarButtonStyle} title="Reset Size">
                Reset
              </button>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '0 8px' }}>
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                onClick={() => setLightboxImage(null)}
                style={{
                  ...toolbarButtonStyle,
                  background: 'rgba(239, 68, 68, 0.1)',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  color: 'var(--accent-red)'
                }}
              >
                Close &times;
              </button>
            </div>
          </div>

          {/* Interactive Image Container */}
          <div
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{
              flex: 1,
              overflow: 'hidden',
              position: 'relative',
              cursor: isDragging ? 'grabbing' : 'grab',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightboxImage.url}
              alt="Full view"
              draggable="false"
              style={{
                maxHeight: '88vh',
                maxWidth: '90vw',
                boxShadow: '0 20px 50px rgba(0,0,0,0.8)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '4px',
                userSelect: 'none',
                transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                transition: isDragging ? 'none' : 'transform 0.15s cubic-bezier(0.1, 0.8, 0.3, 1)'
              }}
            />
          </div>
          
          <div style={{
            padding: '10px',
            textAlign: 'center',
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            borderTop: '1px solid rgba(255,255,255,0.03)',
            background: 'rgba(0,0,0,0.2)'
          }}>
            Drag to pan the document page. Use Zoom keys or mouse coordinates. Image decrypted live in-memory.
          </div>
        </div>
      )}

    </div>
  );
}

const toolbarButtonStyle = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '8px',
  color: 'var(--text-secondary)',
  padding: '6px 14px',
  fontSize: '0.85rem',
  cursor: 'pointer',
  fontWeight: 600,
  transition: 'all 0.15s ease'
};
