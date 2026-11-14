import React, { useState, useEffect } from 'react';
import { AI_BASE_URL } from '../services/api';
import { ImageOff } from 'lucide-react';

/**
 * Milestone M3.3-F.1: Authenticated Evidence & Snapshot Image Component.
 * Fetches protected evidence media from the backend using the canonical Bearer JWT,
 * converts the response stream to a local Blob URL, and guarantees URL.revokeObjectURL
 * cleanup when the component unmounts or the source changes.
 */
export default function AuthenticatedImage({ src, alt = "Forensic Evidence", className = "" }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl = null;

    if (!src) {
      setBlobUrl(null);
      setError(false);
      setLoading(false);
      return;
    }

    // 1. Data URIs or direct external media bypass backend authentication
    const isLocalBackendUpload = src.startsWith('/uploads/') || src.includes('/uploads/');
    if (!isLocalBackendUpload) {
      setBlobUrl(src);
      setError(false);
      setLoading(false);
      return;
    }

    // 2. Fetch local protected upload with canonical Bearer token
    setLoading(true);
    setError(false);

    const token = localStorage.getItem('ppe_auth_token');
    const headers = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const targetUrl = src.startsWith('http://') || src.startsWith('https://')
      ? src
      : `${AI_BASE_URL}${src.startsWith('/') ? '' : '/'}${src}`;

    fetch(targetUrl, { headers })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Evidence load failed with status: ${res.status}`);
        }
        return res.blob();
      })
      .then((blob) => {
        if (active) {
          objectUrl = URL.createObjectURL(blob);
          setBlobUrl(objectUrl);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          console.warn('[AuthenticatedImage] Error loading evidence:', err);
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      active = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src]);

  if (loading) {
    return (
      <div className={`flex items-center justify-center bg-slate-950 text-slate-500 font-mono text-[10px] ${className}`}>
        <span className="animate-pulse">Loading verified evidence...</span>
      </div>
    );
  }

  if (error || !blobUrl) {
    return (
      <div className={`flex flex-col items-center justify-center gap-1 bg-slate-950 text-slate-500 text-xs p-4 ${className}`}>
        <ImageOff className="w-5 h-5 text-amber-500" />
        <span className="text-[10px] font-mono">Evidence image unavailable</span>
      </div>
    );
  }

  return (
    <img
      src={blobUrl}
      alt={alt}
      className={className}
    />
  );
}
