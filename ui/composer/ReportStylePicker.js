// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * ReportStylePicker.js - Style preset selector for reports
 * 
 * Features:
 * - Preset styles: Corporate, Modern, Creative, Financial, Academic, AI Auto
 * - Each style defines colors, fonts, spacing, and overall aesthetic
 * - Live preview with sample content
 * - Used during goal setting and can be changed later
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Modal,
} from 'react-native';
import { Ionicons, MaterialIcons, MaterialCommunityIcons } from '@expo/vector-icons';

// Style presets with comprehensive design definitions
export const REPORT_STYLES = {
  ai_auto: {
    id: 'ai_auto',
    name: 'AI Smart Style',
    description: 'Let AI choose the best style based on your report content and industry',
    icon: 'auto-awesome',
    colors: {
      primary: '#8B5CF6',
      secondary: '#A78BFA',
      accent: '#C4B5FD',
      text: '#1F2937',
      textSecondary: '#6B7280',
      background: '#FFFFFF',
      surface: '#F9FAFB',
    },
    fonts: {
      heading: 'Inter, system-ui, sans-serif',
      body: 'Inter, system-ui, sans-serif',
      headingWeight: '700',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '1.5em',
      paragraphMargin: '1em',
      sectionGap: '2em',
    },
    specialFeatures: ['ai_determined'],
  },
  corporate: {
    id: 'corporate',
    name: 'Corporate Professional',
    description: 'Clean, formal style ideal for business reports and proposals',
    icon: 'business',
    colors: {
      primary: '#1E40AF',
      secondary: '#3B82F6',
      accent: '#60A5FA',
      text: '#111827',
      textSecondary: '#4B5563',
      background: '#FFFFFF',
      surface: '#F3F4F6',
    },
    fonts: {
      heading: 'Georgia, serif',
      body: 'Arial, sans-serif',
      headingWeight: '600',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '1.25em',
      paragraphMargin: '0.75em',
      sectionGap: '2em',
    },
    specialFeatures: ['formal_tone', 'structured_layout'],
  },
  modern: {
    id: 'modern',
    name: 'Modern Minimal',
    description: 'Contemporary design with clean lines and ample white space',
    icon: 'devices',
    colors: {
      primary: '#18181B',
      secondary: '#3F3F46',
      accent: '#A1A1AA',
      text: '#18181B',
      textSecondary: '#71717A',
      background: '#FFFFFF',
      surface: '#FAFAFA',
    },
    fonts: {
      heading: 'Inter, system-ui, sans-serif',
      body: 'Inter, system-ui, sans-serif',
      headingWeight: '600',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '2em',
      paragraphMargin: '1.25em',
      sectionGap: '3em',
    },
    specialFeatures: ['minimal_design', 'generous_whitespace'],
  },
  creative: {
    id: 'creative',
    name: 'Creative & Bold',
    description: 'Vibrant colors and dynamic layouts for engaging presentations',
    icon: 'palette',
    colors: {
      primary: '#7C3AED',
      secondary: '#EC4899',
      accent: '#06B6D4',
      text: '#1F2937',
      textSecondary: '#6B7280',
      background: '#FFFFFF',
      surface: '#FDF4FF',
    },
    fonts: {
      heading: 'Poppins, sans-serif',
      body: 'Open Sans, sans-serif',
      headingWeight: '700',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '1.5em',
      paragraphMargin: '1em',
      sectionGap: '2.5em',
    },
    specialFeatures: ['gradient_accents', 'bold_typography'],
  },
  financial: {
    id: 'financial',
    name: 'Financial & Data',
    description: 'Optimized for numerical data, tables, and financial analysis',
    icon: 'trending-up',
    colors: {
      primary: '#059669',
      secondary: '#10B981',
      accent: '#6EE7B7',
      text: '#064E3B',
      textSecondary: '#047857',
      background: '#FFFFFF',
      surface: '#ECFDF5',
    },
    fonts: {
      heading: 'Roboto, sans-serif',
      body: 'Roboto, sans-serif',
      headingWeight: '500',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '1em',
      paragraphMargin: '0.75em',
      sectionGap: '1.5em',
    },
    specialFeatures: ['data_emphasis', 'table_friendly', 'chart_optimized'],
  },
  academic: {
    id: 'academic',
    name: 'Academic & Research',
    description: 'Scholarly style with proper citation support and formal structure',
    icon: 'school',
    colors: {
      primary: '#7C2D12',
      secondary: '#C2410C',
      accent: '#FB923C',
      text: '#1C1917',
      textSecondary: '#44403C',
      background: '#FFFBEB',
      surface: '#FEF3C7',
    },
    fonts: {
      heading: 'Merriweather, serif',
      body: 'Source Serif Pro, serif',
      headingWeight: '700',
      bodyWeight: '400',
    },
    spacing: {
      headingMargin: '1.5em',
      paragraphMargin: '1em',
      sectionGap: '2em',
    },
    specialFeatures: ['citation_support', 'footnotes', 'bibliography'],
  },
};

// Style categories for grouping
export const STYLE_CATEGORIES = [
  { id: 'recommended', name: 'Recommended', icon: 'star', styles: ['ai_auto'] },
  { id: 'professional', name: 'Professional', icon: 'work', styles: ['corporate', 'financial'] },
  { id: 'contemporary', name: 'Contemporary', icon: 'grid-view', styles: ['modern', 'creative'] },
  { id: 'specialized', name: 'Specialized', icon: 'school', styles: ['academic'] },
];

// Generate CSS for a style
export const getStyleCSS = (styleId) => {
  const style = REPORT_STYLES[styleId] || REPORT_STYLES.corporate;
  
  return `
    /* ${style.name} Style */
    .report-content {
      font-family: ${style.fonts.body};
      font-weight: ${style.fonts.bodyWeight};
      color: ${style.colors.text};
      background-color: ${style.colors.background};
      line-height: 1.7;
    }
    
    .report-content h1,
    .report-content h2,
    .report-content h3,
    .report-content h4 {
      font-family: ${style.fonts.heading};
      font-weight: ${style.fonts.headingWeight};
      color: ${style.colors.primary};
      margin-top: ${style.spacing.headingMargin};
      margin-bottom: 0.5em;
    }
    
    .report-content h1 {
      font-size: 2.25em;
      border-bottom: 2px solid ${style.colors.accent};
      padding-bottom: 0.3em;
    }
    
    .report-content h2 {
      font-size: 1.75em;
      color: ${style.colors.secondary};
    }
    
    .report-content h3 {
      font-size: 1.375em;
    }
    
    .report-content p {
      margin-bottom: ${style.spacing.paragraphMargin};
      color: ${style.colors.text};
    }
    
    .report-content blockquote {
      border-left: 4px solid ${style.colors.primary};
      padding-left: 1em;
      margin: 1em 0;
      color: ${style.colors.textSecondary};
      font-style: italic;
      background-color: ${style.colors.surface};
      padding: 0.75em 1em;
      border-radius: 0 4px 4px 0;
    }
    
    .report-content table {
      width: 100%;
      border-collapse: collapse;
      margin: 1em 0;
    }
    
    .report-content th {
      background-color: ${style.colors.primary};
      color: white;
      padding: 0.75em;
      text-align: left;
    }
    
    .report-content td {
      padding: 0.5em 0.75em;
      border-bottom: 1px solid ${style.colors.surface};
    }
    
    .report-content tr:hover td {
      background-color: ${style.colors.surface};
    }
    
    .report-content a {
      color: ${style.colors.secondary};
      text-decoration: none;
    }
    
    .report-content a:hover {
      text-decoration: underline;
    }
    
    .report-content ul, .report-content ol {
      margin: 0.75em 0;
      padding-left: 1.5em;
    }
    
    .report-content li {
      margin-bottom: 0.25em;
    }
    
    .report-content code {
      background-color: ${style.colors.surface};
      padding: 0.1em 0.3em;
      border-radius: 3px;
      font-family: 'Fira Code', monospace;
      font-size: 0.9em;
    }
    
    .report-content pre {
      background-color: ${style.colors.surface};
      padding: 1em;
      border-radius: 6px;
      overflow-x: auto;
    }
    
    .report-section {
      margin-bottom: ${style.spacing.sectionGap};
    }
  `;
};

const ReportStylePicker = ({
  visible,
  onClose,
  onSelectStyle,
  currentStyle = 'ai_auto',
  theme,
  mode = 'modal', // 'modal' or 'inline'
}) => {
  const [selectedStyle, setSelectedStyle] = useState(currentStyle);
  const [activeCategory, setActiveCategory] = useState('recommended');

  const safeTheme = theme || {
    background: '#FFFFFF',
    surface: '#F9FAFB',
    text: '#1F2937',
    textSecondary: '#6B7280',
    primary: '#3B82F6',
    border: '#E5E7EB',
  };

  useEffect(() => {
    if (visible) {
      setSelectedStyle(currentStyle);
    }
  }, [visible, currentStyle]);

  // Get styles for active category
  const getStylesForCategory = () => {
    const category = STYLE_CATEGORIES.find(c => c.id === activeCategory);
    if (!category) return Object.values(REPORT_STYLES);
    return category.styles.map(id => REPORT_STYLES[id]).filter(Boolean);
  };

  // Handle style selection
  const handleSelect = () => {
    onSelectStyle(selectedStyle);
    if (mode === 'modal') {
      onClose();
    }
  };

  // Render style preview card
  const renderStyleCard = (style) => {
    const isSelected = selectedStyle === style.id;
    const isAI = style.id === 'ai_auto';

    return (
      <TouchableOpacity
        key={style.id}
        style={[
          styles.styleCard,
          {
            borderColor: isSelected ? safeTheme.primary : safeTheme.border,
            backgroundColor: isSelected ? safeTheme.primary + '08' : safeTheme.background,
          },
          isAI && styles.aiStyleCard,
        ]}
        onPress={() => setSelectedStyle(style.id)}
      >
        {/* Color Preview Strip */}
        <View style={[styles.colorStrip, { backgroundColor: style.colors.primary }]}>
          <View style={[styles.colorStripAccent, { backgroundColor: style.colors.secondary }]} />
          <View style={[styles.colorStripAccent2, { backgroundColor: style.colors.accent }]} />
        </View>

        {/* Content */}
        <View style={styles.styleCardContent}>
          {/* Header */}
          <View style={styles.styleCardHeader}>
            <View style={[styles.styleIconBg, { backgroundColor: style.colors.primary + '15' }]}>
              <MaterialIcons name={style.icon} size={20} color={style.colors.primary} />
            </View>
            {isSelected && (
              <Ionicons name="checkmark-circle" size={20} color={safeTheme.primary} />
            )}
            {isAI && !isSelected && (
              <View style={[styles.aiBadge, { backgroundColor: '#8B5CF6' }]}>
                <Text style={styles.aiBadgeText}>AI</Text>
              </View>
            )}
          </View>

          {/* Name & Description */}
          <Text style={[styles.styleName, { color: safeTheme.text }]}>
            {style.name}
          </Text>
          <Text style={[styles.styleDescription, { color: safeTheme.textSecondary }]} numberOfLines={2}>
            {style.description}
          </Text>

          {/* Sample Preview */}
          <View style={[styles.samplePreview, { backgroundColor: style.colors.background, borderColor: safeTheme.border }]}>
            <Text style={[styles.sampleHeading, { fontFamily: style.fonts.heading, color: style.colors.primary }]}>
              Sample Heading
            </Text>
            <Text style={[styles.sampleBody, { fontFamily: style.fonts.body, color: style.colors.text }]}>
              This is how your text will appear with this style applied.
            </Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  // Render category tab
  const renderCategoryTab = (category) => {
    const isActive = activeCategory === category.id;
    
    return (
      <TouchableOpacity
        key={category.id}
        style={[
          styles.categoryTab,
          isActive && { backgroundColor: safeTheme.primary + '15', borderColor: safeTheme.primary },
        ]}
        onPress={() => setActiveCategory(category.id)}
      >
        <MaterialIcons
          name={category.icon}
          size={16}
          color={isActive ? safeTheme.primary : safeTheme.textSecondary}
        />
        <Text style={[styles.categoryTabText, { color: isActive ? safeTheme.primary : safeTheme.textSecondary }]}>
          {category.name}
        </Text>
      </TouchableOpacity>
    );
  };

  const content = (
    <>
      {/* Category Tabs */}
      <View style={styles.categoryTabs}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categoryTabsContent}>
          {STYLE_CATEGORIES.map(renderCategoryTab)}
        </ScrollView>
      </View>

      {/* Styles Grid */}
      <ScrollView style={styles.stylesGrid} contentContainerStyle={styles.stylesGridContent}>
        <View style={styles.stylesRow}>
          {getStylesForCategory().map(renderStyleCard)}
        </View>
      </ScrollView>
    </>
  );

  if (mode === 'inline') {
    return (
      <View style={[styles.inlineContainer, { backgroundColor: safeTheme.background }]}>
        {content}
        <View style={styles.inlineFooter}>
          <TouchableOpacity
            style={[styles.selectBtn, { backgroundColor: safeTheme.primary }]}
            onPress={handleSelect}
          >
            <Text style={styles.selectBtnText}>Apply Style</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modalContainer, { backgroundColor: safeTheme.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: safeTheme.border }]}>
            <View style={styles.headerLeft}>
              <MaterialIcons name="style" size={24} color={safeTheme.primary} />
              <Text style={[styles.title, { color: safeTheme.text }]}>Choose Report Style</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={safeTheme.text} />
            </TouchableOpacity>
          </View>

          {/* Body */}
          <View style={styles.body}>
            {content}
          </View>

          {/* Footer */}
          <View style={[styles.footer, { borderTopColor: safeTheme.border }]}>
            <View style={styles.selectedInfo}>
              {selectedStyle && REPORT_STYLES[selectedStyle] && (
                <>
                  <Text style={[styles.selectedLabel, { color: safeTheme.textSecondary }]}>Selected:</Text>
                  <Text style={[styles.selectedName, { color: safeTheme.text }]}>
                    {REPORT_STYLES[selectedStyle].name}
                  </Text>
                </>
              )}
            </View>
            <View style={styles.footerButtons}>
              <TouchableOpacity
                style={[styles.cancelBtn, { borderColor: safeTheme.border }]}
                onPress={onClose}
              >
                <Text style={[styles.cancelBtnText, { color: safeTheme.text }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.selectBtn, { backgroundColor: safeTheme.primary }]}
                onPress={handleSelect}
              >
                <MaterialIcons name="check" size={18} color="#fff" />
                <Text style={styles.selectBtnText}>Apply Style</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContainer: {
    width: 800,
    maxWidth: '95%',
    height: '80%',
    maxHeight: 600,
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 10,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
  },
  closeBtn: {
    padding: 4,
  },
  body: {
    flex: 1,
    overflow: 'hidden',
  },
  categoryTabs: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  categoryTabsContent: {
    paddingHorizontal: 16,
    gap: 8,
  },
  categoryTab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'transparent',
    gap: 6,
  },
  categoryTabText: {
    fontSize: 13,
    fontWeight: '500',
  },
  stylesGrid: {
    flex: 1,
  },
  stylesGridContent: {
    padding: 16,
  },
  stylesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  styleCard: {
    width: 230,
    borderRadius: 10,
    borderWidth: 2,
    overflow: 'hidden',
  },
  aiStyleCard: {
    borderStyle: 'dashed',
  },
  colorStrip: {
    height: 6,
    flexDirection: 'row',
  },
  colorStripAccent: {
    flex: 1,
    marginLeft: '40%',
  },
  colorStripAccent2: {
    flex: 1,
  },
  styleCardContent: {
    padding: 14,
    gap: 8,
  },
  styleCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  styleIconBg: {
    width: 36,
    height: 36,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  aiBadge: {
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: 4,
  },
  aiBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },
  styleName: {
    fontSize: 15,
    fontWeight: '600',
  },
  styleDescription: {
    fontSize: 12,
    lineHeight: 16,
  },
  samplePreview: {
    padding: 10,
    borderRadius: 6,
    marginTop: 4,
    borderWidth: 1,
  },
  sampleHeading: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
  },
  sampleBody: {
    fontSize: 10,
    lineHeight: 14,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderTopWidth: 1,
    backgroundColor: '#FAFAFA',
  },
  selectedInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  selectedLabel: {
    fontSize: 13,
  },
  selectedName: {
    fontSize: 13,
    fontWeight: '600',
  },
  footerButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
  },
  cancelBtnText: {
    fontSize: 14,
    fontWeight: '500',
  },
  selectBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    gap: 6,
  },
  selectBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
  // Inline mode styles
  inlineContainer: {
    borderRadius: 10,
    overflow: 'hidden',
  },
  inlineFooter: {
    padding: 12,
    alignItems: 'flex-end',
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
});

export default ReportStylePicker;
