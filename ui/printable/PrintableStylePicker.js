// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// printableStylePicker.js - Component for selecting and customizing printable styles
import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Modal,
  TextInput,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

// ==================== Smart Contrast Detection ====================

/**
 * Convert hex color to RGB
 */
const hexToRgb = (hex) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null;
};

/**
 * Calculate relative luminance using WCAG formula
 * https://www.w3.org/TR/WCAG20/#relativeluminancedef
 */
const getLuminance = (hex) => {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0;

  const [r, g, b] = [rgb.r, rgb.g, rgb.b].map(val => {
    val = val / 255;
    return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
  });

  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/**
 * Get optimal text color (dark or light) based on background luminance
 * Returns dark text for light backgrounds, light text for dark backgrounds
 */
const getContrastTextColor = (backgroundColor) => {
  const luminance = getLuminance(backgroundColor);

  // WCAG recommends 0.5 as threshold
  // Luminance > 0.5 = light background → use dark text
  // Luminance ≤ 0.5 = dark background → use light text
  return luminance > 0.5 ? '#111827' : '#E5E7EB';
};

// Predefined style themes
export const PRESET_STYLES = [
  {
    id: 'ai-auto',
    name: 'Let AI Decide',
    description: 'AI will choose the best colors based on your content',
    preview: {
      primary: '#6366f1', // Indigo placeholder
      secondary: '#a855f7', // Purple placeholder
      accent: '#ec4899', // Pink placeholder
    },
    PAGEBackground: '#ffffff',
    fontFamily: 'Inter, system-ui, sans-serif',
    // Backend rendering properties
    accentColor: '#6366f1',
    cardBackground: '#f8fafc',
    cardBorder: '#e2e8f0',
    textPrimary: '#111827',
    textSecondary: '#6b7280',
    textStyles: {
      title: { fontFamily: 'Inter, sans-serif', fontSize: 44, fontWeight: '700', color: '#111827' },
      subtitle: { fontFamily: 'Inter, sans-serif', fontSize: 28, fontWeight: '500', color: '#1f2937' },
      body: { fontFamily: 'Inter, sans-serif', fontSize: 20, fontWeight: '400', color: getContrastTextColor('#ffffff') },
    },
    accentGradient: 'linear-gradient(135deg, #6366f1 0%, #ec4899 100%)',
    headerStyle: 'gradient',
  },
  {
    id: 'corporate',
    name: 'Corporate',
    description: 'Professional and clean design for business printables',
    preview: {
      primary: '#1E3A5F',
      secondary: '#3B82F6',
      accent: '#10B981',
    },
    PAGEBackground: '#FFFFFF',
    fontFamily: 'Inter, system-ui, sans-serif',
    // Backend rendering properties
    accentColor: '#3B82F6',
    cardBackground: '#f8fafc',
    cardBorder: '#e2e8f0',
    textPrimary: '#1E3A5F',
    textSecondary: '#475569',
    textStyles: {
      title: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 44,
        fontWeight: '700',
        color: '#1E3A5F',
      },
      subtitle: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 28,
        fontWeight: '500',
        color: '#1f2937',
      },
      body: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 20,
        fontWeight: '400',
        color: getContrastTextColor('#FFFFFF'),
      },
    },
    accentGradient: 'linear-gradient(135deg, #1E3A5F 0%, #3B82F6 100%)',
    headerStyle: 'solid', // 'solid', 'gradient', 'minimal'
  },
  {
    id: 'creative',
    name: 'Creative',
    description: 'Bold and colorful design for creative printables',
    preview: {
      primary: '#7C3AED',
      secondary: '#EC4899',
      accent: '#F59E0B',
    },
    PAGEBackground: '#FAFAFA',
    fontFamily: 'Poppins, system-ui, sans-serif',
    // Backend rendering properties
    accentColor: '#7C3AED',
    cardBackground: '#f5f3ff',
    cardBorder: '#ddd6fe',
    textPrimary: '#7C3AED',
    textSecondary: '#6b21a8',
    textStyles: {
      title: {
        fontFamily: 'Poppins, system-ui, sans-serif',
        fontSize: 48,
        fontWeight: '800',
        color: '#7C3AED',
      },
      subtitle: {
        fontFamily: 'Poppins, system-ui, sans-serif',
        fontSize: 26,
        fontWeight: '500',
        color: '#1f2937',
      },
      body: {
        fontFamily: 'Poppins, system-ui, sans-serif',
        fontSize: 18,
        fontWeight: '400',
        color: getContrastTextColor('#FAFAFA'),
      },
    },
    accentGradient: 'linear-gradient(135deg, #7C3AED 0%, #EC4899 100%)',
    headerStyle: 'gradient',
  },
  {
    id: 'minimal',
    name: 'Minimal',
    description: 'Clean and simple design with focus on content',
    preview: {
      primary: '#111827',
      secondary: '#6B7280',
      accent: '#3B82F6',
    },
    PAGEBackground: '#FFFFFF',
    fontFamily: 'Inter, system-ui, sans-serif',
    // Backend rendering properties
    accentColor: '#3B82F6',
    cardBackground: '#f9fafb',
    cardBorder: '#e5e7eb',
    textPrimary: '#111827',
    textSecondary: '#6B7280',
    textStyles: {
      title: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 40,
        fontWeight: '600',
        color: '#111827',
      },
      subtitle: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 24,
        fontWeight: '400',
        color: '#1f2937',
      },
      body: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 18,
        fontWeight: '400',
        color: getContrastTextColor('#FFFFFF'),
      },
    },
    accentGradient: 'none',
    headerStyle: 'minimal',
  },
  {
    id: 'bold',
    name: 'Bold',
    description: 'High contrast design that makes an impact',
    preview: {
      primary: '#000000',
      secondary: '#EF4444',
      accent: '#FBBF24',
    },
    PAGEBackground: '#111827',
    fontFamily: 'Montserrat, system-ui, sans-serif',
    // Backend rendering properties
    accentColor: '#EF4444',
    cardBackground: '#1f2937',
    cardBorder: '#374151',
    textPrimary: '#FFFFFF',
    textSecondary: '#E5E7EB',
    textStyles: {
      title: {
        fontFamily: 'Montserrat, system-ui, sans-serif',
        fontSize: 52,
        fontWeight: '900',
        color: '#FFFFFF',
      },
      subtitle: {
        fontFamily: 'Montserrat, system-ui, sans-serif',
        fontSize: 28,
        fontWeight: '600',
        color: '#EF4444',
      },
      body: {
        fontFamily: 'Montserrat, system-ui, sans-serif',
        fontSize: 20,
        fontWeight: '400',
        color: getContrastTextColor('#111827'),
      },
    },
    accentGradient: 'linear-gradient(135deg, #EF4444 0%, #FBBF24 100%)',
    headerStyle: 'solid',
  },
  {
    id: 'academic',
    name: 'Academic',
    description: 'Scholarly design for educational printables',
    preview: {
      primary: '#1E40AF',
      secondary: '#047857',
      accent: '#7C2D12',
    },
    PAGEBackground: '#FFFBF5',
    fontFamily: 'Georgia, serif',
    // Backend rendering properties
    accentColor: '#1E40AF',
    cardBackground: '#fef3c7',
    cardBorder: '#fcd34d',
    textPrimary: '#1E40AF',
    textSecondary: '#047857',
    textStyles: {
      title: {
        fontFamily: 'Georgia, serif',
        fontSize: 38,
        fontWeight: '700',
        color: '#1E40AF',
      },
      subtitle: {
        fontFamily: 'Georgia, serif',
        fontSize: 24,
        fontWeight: '500',
        color: '#047857',
      },
      body: {
        fontFamily: 'Georgia, serif',
        fontSize: 18,
        fontWeight: '400',
        color: getContrastTextColor('#fef3c7'), // Use card background for contrast
      },
    },
    accentGradient: 'none',
    headerStyle: 'minimal',
  },
  {
    id: 'tech',
    name: 'Tech',
    description: 'Modern tech-inspired design with sleek aesthetics',
    preview: {
      primary: '#06B6D4',
      secondary: '#8B5CF6',
      accent: '#22D3EE',
    },
    PAGEBackground: '#0F172A',
    fontFamily: 'JetBrains Mono, monospace',
    // Backend rendering properties
    accentColor: '#06B6D4',
    cardBackground: '#ffffff', // Set to white as per screenshot
    cardBorder: '#334155',
    textPrimary: '#06B6D4',
    textSecondary: '#CBD5E1',
    textStyles: {
      title: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 44,
        fontWeight: '700',
        color: '#06B6D4',
      },
      subtitle: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 26,
        fontWeight: '500',
        color: '#8B5CF6',
      },
      body: {
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 18,
        fontWeight: '400',
        color: getContrastTextColor('#ffffff'), // Use card background (white) for contrast
      },
    },
    accentGradient: 'linear-gradient(135deg, #06B6D4 0%, #8B5CF6 100%)',
    headerStyle: 'gradient',
  },
];

export const PrintableStylePicker = ({
  theme,
  selectedStyle,
  onSelectStyle,
  onGenerateAIStyle,
  customStyles = [],
  isGeneratingStyle = false,
  apiConfig,
}) => {
  const [showAIStyleModal, setShowAIStyleModal] = useState(false);
  const [aiStylePrompt, setAiStylePrompt] = useState('');
  const [activeTab, setActiveTab] = useState('presets'); // 'presets', 'custom', 'ai'

  const allPresets = [...PRESET_STYLES, ...customStyles];

  const handleSelectStyle = useCallback((style) => {
    onSelectStyle(style);
  }, [onSelectStyle]);

  const handleGenerateAIStyle = useCallback(async () => {
    if (!aiStylePrompt.trim()) return;

    try {
      await onGenerateAIStyle(aiStylePrompt);
      setShowAIStyleModal(false);
      setAiStylePrompt('');
    } catch (error) {
      console.error('Failed to generate AI style:', error);
    }
  }, [aiStylePrompt, onGenerateAIStyle]);

  // Style preview card component
  const StyleCard = ({ style, isSelected }) => (
    <TouchableOpacity
      style={[
        styles.styleCard,
        {
          backgroundColor: theme.surface,
          borderColor: isSelected ? theme.primary : theme.border,
          borderWidth: isSelected ? 2 : 1,
        },
      ]}
      onPress={() => handleSelectStyle(style)}
      activeOpacity={0.7}
    >
      {/* Color preview bar */}
      <View style={styles.colorPreviewBar}>
        <View style={[styles.colorDot, { backgroundColor: style.preview?.primary || '#ccc' }]} />
        <View style={[styles.colorDot, { backgroundColor: style.preview?.secondary || '#ccc' }]} />
        <View style={[styles.colorDot, { backgroundColor: style.preview?.accent || '#ccc' }]} />
      </View>

      {/* Mini PAGE preview */}
      <View
        style={[
          styles.miniPAGEPreview,
          { backgroundColor: style.PAGEBackground || '#fff' },
        ]}
      >
        <View
          style={[
            styles.miniTitle,
            { backgroundColor: style.textStyles?.title?.color || '#000' },
          ]}
        />
        <View
          style={[
            styles.miniSubtitle,
            { backgroundColor: style.textStyles?.subtitle?.color || '#666', opacity: 0.6 },
          ]}
        />
        <View style={styles.miniBodyLines}>
          <View
            style={[
              styles.miniBodyLine,
              { backgroundColor: style.textStyles?.body?.color || '#444', opacity: 0.4 },
            ]}
          />
          <View
            style={[
              styles.miniBodyLine,
              { backgroundColor: style.textStyles?.body?.color || '#444', opacity: 0.4, width: '80%' },
            ]}
          />
        </View>
      </View>

      {/* Style name and description */}
      <Text style={[styles.styleName, { color: theme.text }]}>{style.name}</Text>
      <Text style={[styles.styleDescription, { color: theme.textSecondary }]} numberOfLines={2}>
        {style.description}
      </Text>

      {/* Selected indicator */}
      {isSelected && (
        <View style={[styles.selectedBadge, { backgroundColor: theme.primary }]}>
          <Ionicons name="checkmark" size={14} color="#fff" />
        </View>
      )}

      {/* Custom badge */}
      {style.isCustom && (
        <View style={[styles.customBadge, { backgroundColor: '#8B5CF6' }]}>
          <Text style={styles.customBadgeText}>Custom</Text>
        </View>
      )}
    </TouchableOpacity>
  );

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      {/* Tab selector */}
      <View style={[styles.tabBar, { borderBottomColor: theme.border }]}>
        <TouchableOpacity
          style={[
            styles.tab,
            activeTab === 'presets' && { borderBottomColor: theme.primary, borderBottomWidth: 2 },
          ]}
          onPress={() => setActiveTab('presets')}
        >
          <Ionicons
            name="color-palette-outline"
            size={18}
            color={activeTab === 'presets' ? theme.primary : theme.textSecondary}
          />
          <Text
            style={[
              styles.tabText,
              { color: activeTab === 'presets' ? theme.primary : theme.textSecondary },
            ]}
          >
            Presets
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.tab,
            activeTab === 'custom' && { borderBottomColor: theme.primary, borderBottomWidth: 2 },
          ]}
          onPress={() => setActiveTab('custom')}
        >
          <Ionicons
            name="brush-outline"
            size={18}
            color={activeTab === 'custom' ? theme.primary : theme.textSecondary}
          />
          <Text
            style={[
              styles.tabText,
              { color: activeTab === 'custom' ? theme.primary : theme.textSecondary },
            ]}
          >
            Custom
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.tab,
            activeTab === 'ai' && { borderBottomColor: theme.primary, borderBottomWidth: 2 },
          ]}
          onPress={() => setActiveTab('ai')}
        >
          <Ionicons
            name="sparkles-outline"
            size={18}
            color={activeTab === 'ai' ? theme.primary : theme.textSecondary}
          />
          <Text
            style={[
              styles.tabText,
              { color: activeTab === 'ai' ? theme.primary : theme.textSecondary },
            ]}
          >
            AI Generate
          </Text>
        </TouchableOpacity>
      </View>

      {/* Content based on active tab */}
      {activeTab === 'presets' && (
        <ScrollView
          style={styles.stylesGrid}
          contentContainerStyle={styles.stylesGridContent}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.gridRow}>
            {PRESET_STYLES.map((style) => (
              <StyleCard
                key={style.id}
                style={style}
                isSelected={selectedStyle?.id === style.id}
              />
            ))}
          </View>
        </ScrollView>
      )}

      {activeTab === 'custom' && (
        <ScrollView
          style={styles.stylesGrid}
          contentContainerStyle={styles.stylesGridContent}
          showsVerticalScrollIndicator={false}
        >
          {customStyles.length > 0 ? (
            <View style={styles.gridRow}>
              {customStyles.map((style) => (
                <StyleCard
                  key={style.id}
                  style={style}
                  isSelected={selectedStyle?.id === style.id}
                />
              ))}
            </View>
          ) : (
            <View style={styles.emptyState}>
              <Ionicons name="brush-outline" size={48} color={theme.textSecondary} />
              <Text style={[styles.emptyStateText, { color: theme.textSecondary }]}>
                No custom styles yet
              </Text>
              <Text style={[styles.emptyStateSubtext, { color: theme.textSecondary }]}>
                Use AI Generate to create custom styles
              </Text>
            </View>
          )}
        </ScrollView>
      )}

      {activeTab === 'ai' && (
        <View style={styles.aiStyleContainer}>
          <View style={[styles.aiPromptCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <View style={styles.aiPromptHeader}>
              <Ionicons name="sparkles" size={24} color="#8B5CF6" />
              <Text style={[styles.aiPromptTitle, { color: theme.text }]}>
                Generate Style with AI
              </Text>
            </View>

            <Text style={[styles.aiPromptDescription, { color: theme.textSecondary }]}>
              Describe the visual style you want for your printable. Include colors, mood, industry, or any specific aesthetic preferences.
            </Text>

            <TextInput
              style={[
                styles.aiPromptInput,
                {
                  backgroundColor: theme.background,
                  color: theme.text,
                  borderColor: theme.border,
                },
              ]}
              placeholder="E.g., Modern tech startup with blue gradients, clean lines, and a futuristic feel..."
              placeholderTextColor={theme.textSecondary}
              value={aiStylePrompt}
              onChangeText={setAiStylePrompt}
              multiline
              numberOfLines={4}
              textAlignVertical="top"
            />

            <View style={styles.aiPromptExamples}>
              <Text style={[styles.examplesTitle, { color: theme.textSecondary }]}>
                Quick prompts:
              </Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {[
                  'Professional law firm, navy blue and gold',
                  'Vibrant startup pitch, gradients and modern',
                  'Medical printable, clean and trustworthy',
                  'Educational, friendly and engaging colors',
                  'Dark mode tech printable',
                ].map((prompt, index) => (
                  <TouchableOpacity
                    key={index}
                    style={[styles.quickPrompt, { backgroundColor: theme.background, borderColor: theme.border }]}
                    onPress={() => setAiStylePrompt(prompt)}
                  >
                    <Text style={[styles.quickPromptText, { color: theme.text }]}>{prompt}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>

            <TouchableOpacity
              style={[
                styles.generateButton,
                {
                  backgroundColor: aiStylePrompt.trim() ? '#8B5CF6' : theme.border,
                  opacity: aiStylePrompt.trim() && !isGeneratingStyle ? 1 : 0.6,
                },
              ]}
              onPress={handleGenerateAIStyle}
              disabled={!aiStylePrompt.trim() || isGeneratingStyle}
            >
              {isGeneratingStyle ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <>
                  <Ionicons name="sparkles" size={20} color="#fff" />
                  <Text style={styles.generateButtonText}>Generate Style</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
};

const styles = {
  container: {
    flex: 1,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    paddingHorizontal: 16,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginRight: 8,
    gap: 6,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
  },
  stylesGrid: {
    flex: 1,
    padding: 16,
  },
  stylesGridContent: {
    paddingBottom: 20,
  },
  gridRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  styleCard: {
    width: Platform.OS === 'web' ? 180 : '47%',
    borderRadius: 12,
    padding: 12,
    position: 'relative',
  },
  colorPreviewBar: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: 12,
  },
  colorDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
  },
  miniPAGEPreview: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: 6,
    padding: 8,
    marginBottom: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  miniTitle: {
    width: '60%',
    height: 8,
    borderRadius: 2,
    marginBottom: 6,
  },
  miniSubtitle: {
    width: '40%',
    height: 5,
    borderRadius: 2,
    marginBottom: 10,
  },
  miniBodyLines: {
    width: '80%',
    gap: 4,
  },
  miniBodyLine: {
    width: '100%',
    height: 3,
    borderRadius: 1,
  },
  styleName: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  styleDescription: {
    fontSize: 11,
    lineHeight: 14,
  },
  selectedBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 22,
    height: 22,
    borderRadius: 11,
    justifyContent: 'center',
    alignItems: 'center',
  },
  customBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  customBadgeText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '600',
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
    gap: 12,
  },
  emptyStateText: {
    fontSize: 16,
    fontWeight: '500',
  },
  emptyStateSubtext: {
    fontSize: 13,
  },
  aiStyleContainer: {
    flex: 1,
    padding: 16,
  },
  aiPromptCard: {
    borderRadius: 12,
    padding: 20,
    borderWidth: 1,
  },
  aiPromptHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  aiPromptTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  aiPromptDescription: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 16,
  },
  aiPromptInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 100,
    marginBottom: 12,
  },
  aiPromptExamples: {
    marginBottom: 16,
  },
  examplesTitle: {
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 8,
  },
  quickPrompt: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    marginRight: 8,
  },
  quickPromptText: {
    fontSize: 12,
  },
  generateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
  },
  generateButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
};

export default PrintableStylePicker;
