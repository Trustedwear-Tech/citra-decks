// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * globalImageCache.js - Shared in-memory image cache for all UIs
 * 
 * Used by: PresentationCanvas, PrintableCanvas, ImageResizeComponent,
 *          PresentationExport, PrintableExport, ReportComposer
 * 
 * Why: Avoids redundant S3 fetches across components. Once an image is
 *      fetched and converted to a blob URL, it stays in memory for the
 *      session, so exports / re-renders are instant and bypass CORS issues.
 * 
 * Key insight: S3 presigned URLs expire and are different each session,
 *              but the *base key* (path before query params) is stable.
 *              We normalise URLs to that base key for cache lookups.
 */

import { CONFIG } from '../config/config';
import authService from '../services/authService';

// { [normalizedKey]: blobUrl }
const _cache = {};

// Track pending fetches to avoid duplicate requests
// { [normalizedKey]: Promise<string> }
const _pending = {};

// Stats for debugging
let _hits = 0;
let _misses = 0;

// Backend proxy configuration for CORS fallback.
// Auto-configured from app config and auth service.
let _proxyBaseUrl = null;
let _getAuthToken = null;

/**
 * Lazily initialize proxy config from app config/auth on first use.
 */
function _ensureProxyConfigured() {
  if (_proxyBaseUrl) return;
  try {
    _proxyBaseUrl = CONFIG?.CITRA_SERVICE_URL || null;
    _getAuthToken = () => authService.getToken();
  } catch (_) {
    // Config or auth not available yet — proxy will be skipped
  }
}

/**
 * Configure the backend proxy URL and auth for CORS fallback.
 * Usually auto-configured, but can be called manually to override.
 */
function configureProxy(baseUrl, getAuthToken) {
  _proxyBaseUrl = baseUrl;
  _getAuthToken = getAuthToken;
}

/**
 * Extract S3 key from a presigned URL or S3 URL.
 * e.g. "https://citra-ai.s3.amazonaws.com/prod/user/reports/id/images/img.png?X-Amz-..."
 *   -> "prod/user/reports/id/images/img.png"
 */
function _extractS3Key(url) {
  try {
    const parsed = new URL(url);
    // pathname starts with "/" - strip it
    return parsed.pathname.substring(1);
  } catch (_) {
    return null;
  }
}

/**
 * Fallback: Fetch image through the backend proxy (same-origin, no CORS issues).
 * The backend downloads from S3 directly and streams the binary to the client.
 */
async function _fetchViaProxy(originalSrc) {
  _ensureProxyConfigured();
  if (!_proxyBaseUrl || !_getAuthToken) return null;

  const s3Key = _extractS3Key(originalSrc);
  if (!s3Key) return null;

  try {
    const token = await _getAuthToken();
    if (!token) return null;

    const proxyUrl = `${_proxyBaseUrl}/s3-image-proxy?key=${encodeURIComponent(s3Key)}`;
    const res = await fetch(proxyUrl, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Proxy HTTP ${res.status}`);
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch (err) {
    console.warn(`⚠️ [ImageCache] Backend proxy fallback also failed:`, err.message);
    return null;
  }
}

/**
 * Normalise an S3 presigned URL to its stable base key.
 * e.g.  https://citra-ai.s3.amazonaws.com/prod/user/pres/img.jpg?X-Amz-...
 *    -> https://citra-ai.s3.amazonaws.com/prod/user/pres/img.jpg
 *
 * Also handles plain paths, data URIs, blob URLs etc.
 */
function normalizeKey(url) {
  if (!url) return '';
  // data: and blob: URLs are already local - return as-is
  if (url.startsWith('data:') || url.startsWith('blob:')) return url;

  // Strip query params from S3 presigned URLs
  try {
    const idx = url.indexOf('?');
    if (idx > 0) return url.substring(0, idx);
  } catch (_) { /* ignore */ }
  return url;
}

/**
 * Get a cached blob URL for an image, or null if not cached yet.
 * This is synchronous and never triggers a fetch.
 */
function get(originalSrc) {
  if (!originalSrc) return null;
  if (originalSrc.startsWith('data:') || originalSrc.startsWith('blob:')) return originalSrc;

  const key = normalizeKey(originalSrc);
  const cached = _cache[key];
  if (cached) {
    _hits++;
    return cached;
  }
  return null;
}

/**
 * Store a blob URL in the cache.
 * @param {string} originalSrc - The original S3 URL (with or without query params)
 * @param {string} blobUrl     - The blob: URL from URL.createObjectURL()
 */
function set(originalSrc, blobUrl) {
  if (!originalSrc || !blobUrl) return;
  const key = normalizeKey(originalSrc);
  _cache[key] = blobUrl;
}

/**
 * Remove a cached entry so the next fetchAndCache() retries from scratch.
 */
function evict(originalSrc) {
  if (!originalSrc) return;
  const key = normalizeKey(originalSrc);
  delete _cache[key];
  delete _pending[key];
}

/**
 * Fallback: Load image via <img> element and convert to blob URL using canvas.
 * Mobile browsers can often load cross-origin images via <img> even when fetch() fails.
 * @param {string} src - Image URL
 * @returns {Promise<string|null>} - blob URL or null on failure
 */
function _loadViaImageElement(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const timeout = setTimeout(() => {
      img.onload = null;
      img.onerror = null;
      reject(new Error('Image load timeout'));
    }, 15000);
    img.onload = () => {
      clearTimeout(timeout);
      try {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        canvas.toBlob((blob) => {
          if (blob) {
            resolve(URL.createObjectURL(blob));
          } else {
            // toBlob failed (tainted canvas on mobile) — still usable as direct URL
            resolve(null);
          }
        });
      } catch (e) {
        // SecurityError from tainted canvas — image loaded but can't extract blob
        // Return null so caller falls back to direct URL
        resolve(null);
      }
    };
    img.onerror = () => {
      clearTimeout(timeout);
      // Try once more without crossOrigin (some CDNs don't send CORS headers)
      const img2 = new Image();
      img2.onload = () => resolve(null); // Loaded but can't blob it — still loadable by Fabric
      img2.onerror = () => reject(new Error('Image load failed'));
      img2.src = src;
    };
    img.src = src;
  });
}

/**
 * Fetch an image, cache as blob URL, and return the blob URL.
 * If already cached, returns immediately.
 * If a fetch is already in-flight for the same image, awaits that instead
 * of starting a duplicate request.
 *
 * @param {string} originalSrc - S3 presigned URL or any image URL
 * @returns {Promise<string>}  - blob URL or falls back to originalSrc on error
 */
async function fetchAndCache(originalSrc) {
  if (!originalSrc) return originalSrc;
  if (originalSrc.startsWith('data:') || originalSrc.startsWith('blob:')) return originalSrc;

  const key = normalizeKey(originalSrc);

  // 1. Cache hit
  if (_cache[key]) {
    _hits++;
    return _cache[key];
  }

  // 2. Already fetching - wait for the same promise
  if (_pending[key]) {
    return _pending[key];
  }

  // 3. New fetch
  _misses++;
  _pending[key] = (async () => {
    try {
      // Use cache: 'no-store' to bypass browser HTTP cache.
      // Without this, the browser may serve a cached response from a non-CORS <img> load
      // (TipTap editor loads images without crossOrigin), which lacks CORS headers,
      // causing fetch() to fail even though S3 CORS is properly configured.
      const res = await fetch(originalSrc, { mode: 'cors', cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      _cache[key] = blobUrl;
      return blobUrl;
    } catch (err) {
      console.warn(`⚠️ [ImageCache] fetch() failed, trying Image element fallback:`, err.message);
      // Mobile browsers often block fetch() for cross-origin images due to stricter CORS,
      // but <img> tags can still load them. Use canvas drawImage to convert to blob.
      try {
        const blobUrl = await _loadViaImageElement(originalSrc);
        if (blobUrl) {
          _cache[key] = blobUrl;
          return blobUrl;
        }
      } catch (_imgErr) {
        console.warn(`⚠️ [ImageCache] Image element fallback also failed:`, _imgErr.message);
      }

      // Last resort: route through backend proxy (same-origin, no CORS issues).
      // The backend downloads the image from S3 directly and streams it to us.
      try {
        const blobUrl = await _fetchViaProxy(originalSrc);
        if (blobUrl) {
          console.log(`✅ [ImageCache] Backend proxy succeeded for:`, normalizeKey(originalSrc));
          _cache[key] = blobUrl;
          return blobUrl;
        }
      } catch (_proxyErr) {
        console.warn(`⚠️ [ImageCache] Backend proxy fallback also failed:`, _proxyErr.message);
      }

      // Final fallback: return original URL and let <img> tag handle it directly
      return originalSrc;
    } finally {
      delete _pending[key];
    }
  })();

  return _pending[key];
}

/**
 * Pre-cache an array of image URLs (batch).
 * Useful before export - ensures all images are cached locally.
 *
 * @param {string[]} urls - Array of image URLs to pre-cache
 * @returns {Promise<void>}
 */
async function preCacheAll(urls) {
  if (!urls || urls.length === 0) return;

  const unique = [...new Set(urls.filter(u => u && !u.startsWith('data:') && !u.startsWith('blob:')))];
  const uncached = unique.filter(u => !_cache[normalizeKey(u)]);

  if (uncached.length === 0) return;

  console.log(`📦 [ImageCache] Pre-caching ${uncached.length} images...`);

  // Fetch in parallel batches of 5 to avoid overwhelming the browser
  const BATCH_SIZE = 5;
  for (let i = 0; i < uncached.length; i += BATCH_SIZE) {
    const batch = uncached.slice(i, i + BATCH_SIZE);
    await Promise.allSettled(batch.map(url => fetchAndCache(url)));
  }

  console.log(`✅ [ImageCache] Pre-cache complete. Total cached: ${Object.keys(_cache).length}`);
}

/**
 * Get a base64 data URL for an image (needed for PPTX export).
 * Uses the cached blob if available, otherwise fetches fresh.
 *
 * @param {string} originalSrc - S3 presigned URL or any image URL
 * @returns {Promise<string>}  - data:... URL or null on failure
 */
async function getAsBase64(originalSrc) {
  if (!originalSrc) return null;

  // Already a data URL
  if (originalSrc.startsWith('data:')) return originalSrc;

  try {
    // Try to get from cache or fetch
    const blobUrl = await fetchAndCache(originalSrc);

    // Convert blob URL to data URL.
    // If fetchAndCache returned a blob: URL, fetch it directly (same-origin, no CORS).
    // If it fell back to the original S3 URL, use cache: 'no-store' to bypass
    // the browser's cached non-CORS response.
    const isBlobUrl = blobUrl && blobUrl.startsWith('blob:');
    const res = await fetch(blobUrl, isBlobUrl ? {} : { mode: 'cors', cache: 'no-store' });
    const blob = await res.blob();

    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (err) {
    console.error(`❌ [ImageCache] Failed to convert to base64:`, err);
    return null;
  }
}

/**
 * Get cache stats for debugging.
 */
function getStats() {
  return {
    entries: Object.keys(_cache).length,
    hits: _hits,
    misses: _misses,
    pending: Object.keys(_pending).length,
  };
}

/**
 * Clear the entire cache (e.g. on logout).
 */
function clear() {
  // Revoke blob URLs to free memory
  Object.values(_cache).forEach(blobUrl => {
    try {
      if (blobUrl.startsWith('blob:')) URL.revokeObjectURL(blobUrl);
    } catch (_) { /* ignore */ }
  });
  Object.keys(_cache).forEach(k => delete _cache[k]);
  _hits = 0;
  _misses = 0;
}

export default {
  get,
  set,
  evict,
  fetchAndCache,
  preCacheAll,
  getAsBase64,
  getStats,
  clear,
  normalizeKey,
  configureProxy,
};
