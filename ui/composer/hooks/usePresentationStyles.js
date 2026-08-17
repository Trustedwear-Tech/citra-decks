// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * usePresentationStyles - Style definitions for presentations
 * 
 * Provides PRESENTATION_STYLES as an object keyed by ID for easy lookup.
 * Compatible with TemplateSelector and slideTemplates.
 */

// Presentation styles as object keyed by ID
export const PRESENTATION_STYLES = {
  corporate: {
    id: 'corporate',
    name: 'Corporate',
    description: 'Professional and clean design for business presentations',
    accentColor: '#3B82F6',
    slideBackground: '#FFFFFF',
    cardBackground: '#f8fafc',
    cardBorder: '#e2e8f0',
    textPrimary: '#1E3A5F',
    textSecondary: '#475569',
    preview: {
      primary: '#1E3A5F',
      secondary: '#3B82F6',
    },
    textStyles: {
      title: { fontSize: 44, fontWeight: '700', color: '#1E3A5F' },
      subtitle: { fontSize: 28, fontWeight: '500', color: '#1f2937' },
      body: { fontSize: 20, fontWeight: '400', color: '#111827' },
    },
  },

  modern_blue: {
    id: 'modern_blue',
    name: 'Modern Blue',
    description: 'Fresh and modern with vibrant blue accents',
    accentColor: '#2563EB',
    slideBackground: '#FFFFFF',
    cardBackground: '#eff6ff',
    cardBorder: '#bfdbfe',
    textPrimary: '#1e40af',
    textSecondary: '#3b82f6',
    preview: {
      primary: '#2563EB',
      secondary: '#60A5FA',
    },
    textStyles: {
      title: { fontSize: 44, fontWeight: '700', color: '#1e40af' },
      subtitle: { fontSize: 28, fontWeight: '500', color: '#1e3a8a' },
      body: { fontSize: 20, fontWeight: '400', color: '#1f2937' },
    },
  },

  creative: {
    id: 'creative',
    name: 'Creative',
    description: 'Bold and colorful for creative presentations',
    accentColor: '#7C3AED',
    slideBackground: '#FAFAFA',
    cardBackground: '#f5f3ff',
    cardBorder: '#ddd6fe',
    textPrimary: '#7C3AED',
    textSecondary: '#6b21a8',
    preview: {
      primary: '#7C3AED',
      secondary: '#EC4899',
    },
    textStyles: {
      title: { fontSize: 48, fontWeight: '800', color: '#7C3AED' },
      subtitle: { fontSize: 26, fontWeight: '500', color: '#1f2937' },
      body: { fontSize: 18, fontWeight: '400', color: '#111827' },
    },
  },

  minimal: {
    id: 'minimal',
    name: 'Minimal',
    description: 'Clean and simple with focus on content',
    accentColor: '#3B82F6',
    slideBackground: '#FFFFFF',
    cardBackground: '#f9fafb',
    cardBorder: '#e5e7eb',
    textPrimary: '#111827',
    textSecondary: '#6B7280',
    preview: {
      primary: '#111827',
      secondary: '#6B7280',
    },
    textStyles: {
      title: { fontSize: 40, fontWeight: '600', color: '#111827' },
      subtitle: { fontSize: 24, fontWeight: '400', color: '#1f2937' },
      body: { fontSize: 18, fontWeight: '400', color: '#111827' },
    },
  },

  bold_dark: {
    id: 'bold_dark',
    name: 'Bold Dark',
    description: 'High contrast dark theme that makes an impact',
    accentColor: '#EF4444',
    slideBackground: '#111827',
    cardBackground: '#1f2937',
    cardBorder: '#374151',
    textPrimary: '#FFFFFF',
    textSecondary: '#E5E7EB',
    preview: {
      primary: '#111827',
      secondary: '#EF4444',
    },
    textStyles: {
      title: { fontSize: 52, fontWeight: '900', color: '#FFFFFF' },
      subtitle: { fontSize: 28, fontWeight: '600', color: '#EF4444' },
      body: { fontSize: 20, fontWeight: '400', color: '#E5E7EB' },
    },
  },

  nature: {
    id: 'nature',
    name: 'Nature',
    description: 'Earthy greens and organic feel',
    accentColor: '#059669',
    slideBackground: '#f0fdf4',
    cardBackground: '#dcfce7',
    cardBorder: '#86efac',
    textPrimary: '#166534',
    textSecondary: '#15803d',
    preview: {
      primary: '#166534',
      secondary: '#059669',
    },
    textStyles: {
      title: { fontSize: 44, fontWeight: '700', color: '#166534' },
      subtitle: { fontSize: 26, fontWeight: '500', color: '#15803d' },
      body: { fontSize: 18, fontWeight: '400', color: '#1f2937' },
    },
  },

  warm: {
    id: 'warm',
    name: 'Warm',
    description: 'Warm oranges and ambers for friendly presentations',
    accentColor: '#F59E0B',
    slideBackground: '#FFFBEB',
    cardBackground: '#fef3c7',
    cardBorder: '#fcd34d',
    textPrimary: '#92400E',
    textSecondary: '#b45309',
    preview: {
      primary: '#92400E',
      secondary: '#F59E0B',
    },
    textStyles: {
      title: { fontSize: 44, fontWeight: '700', color: '#92400E' },
      subtitle: { fontSize: 26, fontWeight: '500', color: '#b45309' },
      body: { fontSize: 18, fontWeight: '400', color: '#1f2937' },
    },
  },

  elegant: {
    id: 'elegant',
    name: 'Elegant',
    description: 'Sophisticated rose and neutral tones',
    accentColor: '#EC4899',
    slideBackground: '#fdf2f8',
    cardBackground: '#fce7f3',
    cardBorder: '#f9a8d4',
    textPrimary: '#9d174d',
    textSecondary: '#be185d',
    preview: {
      primary: '#9d174d',
      secondary: '#EC4899',
    },
    textStyles: {
      title: { fontSize: 44, fontWeight: '700', color: '#9d174d' },
      subtitle: { fontSize: 26, fontWeight: '500', color: '#be185d' },
      body: { fontSize: 18, fontWeight: '400', color: '#1f2937' },
    },
  },
};

/**
 * Get style by ID
 */
export function getStyleById(styleId) {
  return PRESENTATION_STYLES[styleId] || PRESENTATION_STYLES.corporate;
}

/**
 * Get all styles as array
 */
export function getStyleList() {
  return Object.values(PRESENTATION_STYLES);
}

export default PRESENTATION_STYLES;
