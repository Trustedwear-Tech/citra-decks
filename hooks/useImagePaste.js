// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import { useEffect } from 'react';
import { Platform } from 'react-native';

const DEFAULT_MAX_BYTES = 8 * 1024 * 1024; // 8 MB raw per image

/**
 * Web clipboard image-paste capture.
 *
 * React Native Web does NOT reliably forward the native `paste` event to a
 * <TextInput>, so relying on the TextInput `onPaste` prop silently fails on
 * many surfaces (this is exactly why quick chat / the composers never caught
 * pasted screenshots). The robust pattern — already proven in the main chat —
 * is a document-level `paste` listener gated on the host input being focused.
 *
 * The hook only CAPTURES images and hands them back as parsed entries; each
 * surface owns its own staging state and per-turn cap. Pasted images are NOT
 * uploaded anywhere here — they ride along on the next send as
 * `multimodal_attachments` / `image_attachments` and are OCR'd server-side.
 *
 * @param {object}   opts
 * @param {() => boolean} opts.isActive  Return true when this surface's input is
 *   focused/active. Prevents one surface from hijacking pastes meant for another.
 * @param {(entries: Array) => void} opts.onImages  Called with parsed image
 *   entries: [{ id, name, mimeType, size, base64, previewUri }].
 * @param {(msg: string) => void} [opts.onError]  Optional error reporter.
 * @param {number} [opts.maxBytes]  Per-image size cap (raw bytes).
 * @param {boolean} [opts.enabled]   Master switch (default true).
 */
export default function useImagePaste({
  isActive,
  onImages,
  onError,
  maxBytes = DEFAULT_MAX_BYTES,
  enabled = true,
}) {
  useEffect(() => {
    if (Platform.OS !== 'web' || !enabled) return undefined;

    const handler = (event) => {
      try {
        // Only act when this surface's input owns the paste.
        if (typeof isActive === 'function' && !isActive()) return;

        const items = event?.clipboardData?.items;
        if (!items || items.length === 0) return;

        const blobs = [];
        for (let i = 0; i < items.length; i++) {
          const it = items[i];
          if (it && it.type && it.type.startsWith('image/')) {
            const blob = it.getAsFile();
            if (blob) blobs.push(blob);
          }
        }
        // No image in the clipboard → let the default text paste happen.
        if (blobs.length === 0) return;

        // We are handling an image — stop the browser from also pasting it.
        event.preventDefault();

        const entries = [];
        let pending = blobs.length;
        const flush = () => {
          if (pending === 0 && entries.length > 0) onImages(entries);
        };

        blobs.forEach((blob) => {
          if (blob.size > maxBytes) {
            onError?.(`Pasted image too large (max ${Math.round(maxBytes / (1024 * 1024))} MB)`);
            pending -= 1;
            flush();
            return;
          }
          const reader = new FileReader();
          reader.onload = () => {
            const dataUrl = String(reader.result || '');
            const base64 = dataUrl.includes(',') ? dataUrl.split(',', 2)[1] : '';
            if (base64) {
              const ts = Date.now();
              const ext = (blob.type.split('/')[1] || 'png').toLowerCase();
              entries.push({
                id: `paste_${ts}_${Math.random().toString(36).slice(2, 6)}`,
                name: `clipboard_image_${ts}.${ext}`,
                mimeType: blob.type || 'image/png',
                size: blob.size,
                base64,
                previewUri: dataUrl,
              });
            }
            pending -= 1;
            flush();
          };
          reader.onerror = () => {
            onError?.('Failed to read pasted image');
            pending -= 1;
            flush();
          };
          reader.readAsDataURL(blob);
        });
      } catch (err) {
        onError?.('Failed to read pasted image');
      }
    };

    document.addEventListener('paste', handler);
    return () => document.removeEventListener('paste', handler);
  }, [isActive, onImages, onError, maxBytes, enabled]);
}
