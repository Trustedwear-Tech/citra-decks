/**
 * UploadLimitsService.js
 * ======================
 * Fetches and caches upload limits from the API.
 * Falls back to environment variables if API is unavailable.
 */

import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import authService from './authService';
import { API_CONFIG } from '../config/config';

// Cache key and TTL
const CACHE_KEY = 'upload_limits_cache';
const CACHE_TTL = 1000 * 60 * 60; // 1 hour

// Default limits from environment variables (fallback)
const getDefaultLimits = () => ({
  pdf: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxPdfSizeMB || process.env.EXPO_PUBLIC_MAX_PDF_SIZE_MB || '100', 10),
    maxPages: parseInt(Constants.expoConfig?.extra?.maxPdfPages || process.env.EXPO_PUBLIC_MAX_PDF_PAGES || '200', 10),
    description: 'PDF documents'
  },
  powerpoint: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxPdfSizeMB || process.env.EXPO_PUBLIC_MAX_PDF_SIZE_MB || '100', 10),
    maxSlides: parseInt(Constants.expoConfig?.extra?.maxPptSlides || process.env.EXPO_PUBLIC_MAX_PPT_SLIDES || '100', 10),
    description: 'PowerPoint presentations'
  },
  excel_json: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxPdfSizeMB || process.env.EXPO_PUBLIC_MAX_PDF_SIZE_MB || '100', 10),
    maxRecords: parseInt(Constants.expoConfig?.extra?.maxExcelJsonRecords || process.env.EXPO_PUBLIC_MAX_EXCEL_JSON_RECORDS || '1000', 10),
    description: 'Excel spreadsheets and JSON files'
  },
  html: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxPdfSizeMB || process.env.EXPO_PUBLIC_MAX_PDF_SIZE_MB || '100', 10),
    maxChars: parseInt(Constants.expoConfig?.extra?.maxHtmlChars || process.env.EXPO_PUBLIC_MAX_HTML_CHARS || '200000', 10),
    description: 'HTML web pages'
  },
  audio: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxAudioSizeMB || process.env.EXPO_PUBLIC_MAX_AUDIO_SIZE_MB || '100', 10),
    maxDurationMinutes: parseInt(Constants.expoConfig?.extra?.maxAudioDurationMinutes || process.env.EXPO_PUBLIC_MAX_AUDIO_DURATION_MINUTES || '120', 10),
    description: 'Audio files (MP3, WAV, M4A, etc.)'
  },
  video: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxVideoSizeMB || process.env.EXPO_PUBLIC_MAX_VIDEO_SIZE_MB || '2048', 10),
    maxDurationMinutes: parseInt(Constants.expoConfig?.extra?.maxVideoDurationMinutes || process.env.EXPO_PUBLIC_MAX_VIDEO_DURATION_MINUTES || '180', 10),
    description: 'Video files'
  },
  image: {
    maxSizeMB: parseInt(Constants.expoConfig?.extra?.maxImgSizeMB || process.env.EXPO_PUBLIC_MAX_IMG_SIZE_MB || '20', 10),
    description: 'Image files (JPG, PNG, GIF, etc.)'
  },
  ocr: {
    maxPages: parseInt(Constants.expoConfig?.extra?.maxOcrPages || process.env.EXPO_PUBLIC_MAX_OCR_PAGES || '10', 10),
    description: 'OCR scanned documents'
  },
  folder_sync_connections: {
    maxPerUser: 10,
    description: 'Cloud folder sync connections'
  }
});

// Get API base URL from centralized config (handles localhost detection automatically)
const getApiBaseUrl = () => {
  return API_CONFIG.CITRA_SERVICE_URL;
};

/**
 * Fetch upload limits from API with caching
 * @returns {Promise<Object>} Upload limits object
 */
export const fetchUploadLimits = async () => {
  try {
    // Check cache first
    const cached = await getCachedLimits();
    if (cached) {
      console.log('[UploadLimits] Using cached limits');
      return cached;
    }

    // Fetch from API
    const apiUrl = `${getApiBaseUrl()}/api/config/upload-limits`;
    console.log('[UploadLimits] Fetching from API:', apiUrl);

    // Get auth token
    const token = await authService.getToken();

    const response = await fetch(apiUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
      timeout: 5000, // 5 second timeout
    });

    if (response.ok) {
      const data = await response.json();
      if (data.limits) {
        // Cache the response
        await cacheLimits(data.limits);
        console.log('[UploadLimits] Fetched and cached limits from API');
        return data.limits;
      }
    }

    console.warn('[UploadLimits] API response invalid, using defaults');
    return getDefaultLimits();
  } catch (error) {
    console.warn('[UploadLimits] Failed to fetch from API, using defaults:', error.message);
    return getDefaultLimits();
  }
};

/**
 * Get cached limits if not expired
 * @returns {Promise<Object|null>} Cached limits or null
 */
const getCachedLimits = async () => {
  try {
    const cached = await AsyncStorage.getItem(CACHE_KEY);
    if (cached) {
      const { limits, timestamp } = JSON.parse(cached);
      if (Date.now() - timestamp < CACHE_TTL) {
        return limits;
      }
    }
  } catch (error) {
    console.warn('[UploadLimits] Cache read error:', error.message);
  }
  return null;
};

/**
 * Cache limits with timestamp
 * @param {Object} limits - Limits to cache
 */
const cacheLimits = async (limits) => {
  try {
    await AsyncStorage.setItem(CACHE_KEY, JSON.stringify({
      limits,
      timestamp: Date.now()
    }));
  } catch (error) {
    console.warn('[UploadLimits] Cache write error:', error.message);
  }
};

/**
 * Format limits for display in UI
 * @param {Object} limits - Limits object from API/defaults
 * @returns {Array} Array of formatted limit items for display
 */
export const formatLimitsForDisplay = (limits) => {
  const items = [];

  if (limits.pdf) {
    items.push({
      icon: 'document-text',
      color: '#3b82f6',
      text: `PDF: ${limits.pdf.maxSizeMB}MB / ${limits.pdf.maxPages} pages`
    });
  }

  if (limits.powerpoint) {
    items.push({
      icon: 'easel',
      color: '#f59e0b',
      text: `PowerPoint: ${limits.powerpoint.maxSizeMB}MB / ${limits.powerpoint.maxSlides} slides`
    });
  }

  if (limits.excel_json) {
    items.push({
      icon: 'grid',
      color: '#22c55e',
      text: `Excel/JSON: ${limits.excel_json.maxSizeMB}MB / ${limits.excel_json.maxRecords} rows`
    });
  }

  if (limits.html) {
    const charsK = Math.round(limits.html.maxChars / 1000);
    items.push({
      icon: 'code-slash',
      color: '#8b5cf6',
      text: `HTML: ${limits.html.maxSizeMB}MB / ${charsK}K chars`
    });
  }

  if (limits.audio) {
    const hours = limits.audio.maxDurationMinutes / 60;
    items.push({
      icon: 'musical-notes',
      color: '#ec4899',
      text: `Audio: ${limits.audio.maxSizeMB}MB / ${hours} hours`
    });
  }

  if (limits.video) {
    const videoGB = limits.video.maxSizeMB >= 1024 ? `${limits.video.maxSizeMB / 1024}GB` : `${limits.video.maxSizeMB}MB`;
    const hours = limits.video.maxDurationMinutes / 60;
    items.push({
      icon: 'videocam',
      color: '#ef4444',
      text: `Video: ${videoGB} / ${hours} hours`
    });
  }

  if (limits.image) {
    items.push({
      icon: 'image',
      color: '#06b6d4',
      text: `Images: ${limits.image.maxSizeMB}MB each`
    });
  }

  if (limits.ocr) {
    items.push({
      icon: 'scan',
      color: '#6366f1',
      text: `OCR Scan: ${limits.ocr.maxPages} pages max`
    });
  }

  if (limits.folder_sync_connections) {
    items.push({
      icon: 'folder-open',
      color: '#14b8a6',
      text: `Folder Syncs: ${limits.folder_sync_connections.maxPerUser} max`
    });
  }

  return items;
};

/**
 * Clear cached limits (useful after settings change)
 */
export const clearLimitsCache = async () => {
  try {
    await AsyncStorage.removeItem(CACHE_KEY);
    console.log('[UploadLimits] Cache cleared');
  } catch (error) {
    console.warn('[UploadLimits] Cache clear error:', error.message);
  }
};

export default {
  fetchUploadLimits,
  formatLimitsForDisplay,
  clearLimitsCache,
  getDefaultLimits
};
