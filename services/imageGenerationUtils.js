// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import ImageGenService from './ImageGenService';
import globalImageCache from '../utils/globalImageCache';

const IMAGE_GEN_CONCURRENCY = 3;
const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

/**
 * Generate images for an array of image_placeholder elements in parallel
 * with a concurrency limit and exponential backoff on rate-limit (429) errors.
 * Mutates placeholder objects in-place (sets type, src, or fallback shape).
 *
 * @param {Array} placeholders - Elements with type === 'image_placeholder'
 * @param {Object} options
 * @param {string} options.generationQuality - Image generation quality tier
 * @param {string} options.style - Style name (e.g. 'professional')
 * @param {string} options.userId - User device ID
 * @param {string} [options.defaultDescription] - Fallback description if placeholder has none
 * @param {Function} [options.handleCreditError] - Callback for credit/billing errors
 */
export async function generateImagesParallel(placeholders, {
  generationQuality,
  style,
  userId,
  defaultDescription = 'Professional image',
  handleCreditError,
} = {}) {
  if (!placeholders || !placeholders.length) return;

  const queue = [...placeholders];

  const processOne = async (ph) => {
    let desc = ph.imageDescription || defaultDescription;
    // GUARD: descriptions must be TEXT. A client bug leaked base64 image data
    // into imageDescription (529K-char prompt observed in prod). Strip embedded
    // data-URIs / long base64 runs and FAIL LOUD so the leak source is visible.
    if (desc.length > 5000 || desc.includes(';base64,')) {
      console.error(`🚨 [IMAGE_GEN] Oversized/binary imageDescription on ${ph.id} (${desc.length} chars) — stripping base64. head=`, desc.slice(0, 80), 'tail=', desc.slice(-120));
      desc = desc.replace(/data:[a-zA-Z0-9/+.\-]+;base64,[A-Za-z0-9+/=\s]+|[A-Za-z0-9+/=]{500,}/g, ' ').slice(0, 3000).trim() || defaultDescription;
    }
    const imageType = ph.imageType || 'photo';
    const w = Math.round(ph.width || 1024);
    const h = Math.round(ph.height || 1024);

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        let imgR;
        imgR = await ImageGenService.generateImage(desc, {
          style,
          width: w,
          height: h,
          imageType,
          userId,
          generationQuality: ph.generationQuality || generationQuality || 'premium',
        });

        // Backend returns snake_case `image_data`; older code paths used camelCase
        // `imageData`. Accept BOTH — the camelCase-only check classified every
        // SUCCESSFUL generation as a failure (root cause of the bricked/stuck
        // image elements: success:true + image_data:<data URI> fell through here).
        const imageData = imgR.imageData || imgR.image_data;
        if (imgR.success && (imageData || imgR.image_url)) {
          ph.type = 'image';
          ph.src = imgR.image_url || imageData;
          if (ph.src?.startsWith('http')) globalImageCache.fetchAndCache(ph.src).catch(() => {});
          return;
        }

        // Check if rate-limited — retry with backoff
        const msg = imgR?.message || '';
        if (attempt < MAX_RETRIES && (imgR?.status === 429 || msg.includes('429') || msg.toLowerCase().includes('rate'))) {
          const delay = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), MAX_DELAY_MS) + Math.random() * 500;
          await new Promise(r => setTimeout(r, delay));
          continue;
        }

        // Non-retryable failure — FAIL LOUD, keep the placeholder. The old
        // silent gray-shape swap permanently bricked the element: once it was a
        // 'shape' it was no longer image-ish, so later description changes never
        // regenerated it again (agent kept "updating" a gray rectangle).
        console.error('🖼️ [IMAGE_GEN] Generation FAILED for element', ph.id, '—', imgR?.message || imgR?.error || JSON.stringify(imgR || {}).slice(0, 300));
        handleCreditError?.(imgR);
        ph.type = 'image_placeholder';
        return;
      } catch (err) {
        const msg = err?.message || '';
        if (attempt < MAX_RETRIES && (err?.status === 429 || msg.includes('429') || msg.toLowerCase().includes('rate'))) {
          const delay = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), MAX_DELAY_MS) + Math.random() * 500;
          await new Promise(r => setTimeout(r, delay));
          continue;
        }
        // FAIL LOUD, keep the placeholder (see comment above).
        console.error('🖼️ [IMAGE_GEN] Generation THREW for element', ph.id, '—', err);
        if (msg) handleCreditError?.({ message: msg });
        ph.type = 'image_placeholder';
        return;
      }
    }
  };

  // Worker pool: N workers pulling from a shared queue
  const workers = Array.from(
    { length: Math.min(IMAGE_GEN_CONCURRENCY, queue.length) },
    async () => {
      while (queue.length > 0) {
        const ph = queue.shift();
        await processOne(ph);
      }
    }
  );

  await Promise.all(workers);
}
