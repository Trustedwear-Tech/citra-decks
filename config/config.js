/**
 * Configuration for citra-decks
 *
 * citra-decks is a single standalone FastAPI service (composers + local
 * auth, all in one process) — trimmed from Citra-UI's multi-microservice
 * config.js, which pointed at half a dozen separate platform services
 * that don't exist in this repo. Every URL here resolves to that one
 * backend.
 */

import { Platform } from 'react-native';

const hostname = (typeof window !== 'undefined' && window.location) ? window.location.hostname : '';
const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(hostname);
const isProductionDomain = !isLocalhost && hostname !== '';
const explicitEnv = process.env.EXPO_PUBLIC_ENVIRONMENT; // 'development' | 'production'
let environment = explicitEnv || (process.env.NODE_ENV === 'development' ? 'development' : 'production');
if (isLocalhost) {
  environment = 'development';
}
if (isProductionDomain && !explicitEnv) {
  environment = 'production';
}

const isDevelopment = environment === 'development';
const isProduction = environment === 'production';

// Single backend — same origin serves the composers, folders, and local auth.
const BASE_URL = process.env.EXPO_PUBLIC_CITRA_DECKS_API_URL
  || (isDevelopment ? 'http://localhost:8085' : '');

if (isProduction && !process.env.EXPO_PUBLIC_CITRA_DECKS_API_URL) {
  console.warn('⚠️ [CONFIG] EXPO_PUBLIC_CITRA_DECKS_API_URL is not set in a production build — API calls will fail.');
}

export const CONFIG = {
  environment,
  isDevelopment,
  isProduction,

  // Bypass login for local dev only — never honoured in production, mirrors
  // the same-named server-side gate in citra_auth's DISABLE_AUTH check.
  isAuthDisabled: isDevelopment && process.env.EXPO_PUBLIC_ENABLE_TEST_AUTH_BYPASS === 'true',

  BASE_URL,
  CITRA_SERVICE_URL: BASE_URL,

  AUTH: {
    baseUrl: `${BASE_URL}/api/auth`,
    meEndpoint: '/me',
  },

  TIMEOUT: parseInt(process.env.EXPO_PUBLIC_API_TIMEOUT) || 300000,
  MAX_RETRY_ATTEMPTS: 3,
};

export const API_CONFIG = {
  ...CONFIG,
  isDevelopment,
  isProduction,
  isAuthDisabled: CONFIG.isAuthDisabled,
};

export const ENVIRONMENT = environment;

export default CONFIG;
