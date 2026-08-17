// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * ReportAddPageModal.js - Modal for adding new pages to reports
 * 
 * Simplified version:
 * - No layout selection (AI decides layout automatically)
 * - Page outline/topic input
 * - Special instructions
 * - "Create Blank" vs "Generate with AI" modes
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';

const ReportAddPageModal = ({
  visible,
  onClose,
  onCreatePage,
  insertIndex = null,
  theme,
  reportGoal = null,
  existingPages = [],
}) => {
  // State
  const [outlineText, setOutlineText] = useState('');
  const [specialInstructions, setSpecialInstructions] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  const safeTheme = theme || {
    background: '#FFFFFF',
    surface: '#F9FAFB',
    text: '#1F2937',
    textSecondary: '#6B7280',
    primary: '#3B82F6',
    border: '#E5E7EB',
  };

  // Reset state when modal opens
  useEffect(() => {
    if (visible) {
      setOutlineText('');
      setSpecialInstructions('');
      setIsGenerating(false);
    }
  }, [visible]);

  // Handle page creation
  const handleCreateBlank = () => {
    onCreatePage({
      content: '',
      mode: 'blank',
      insertIndex,
    });
    onClose();
  };

  const handleGenerateWithAI = async () => {
    if (!outlineText.trim()) {
      return;
    }

    setIsGenerating(true);
    
    try {
      await onCreatePage({
        outline: outlineText.trim(),
        specialInstructions: specialInstructions.trim(),
        mode: 'ai',
        insertIndex,
        reportGoal: reportGoal?.purpose || '',
        existingPageCount: existingPages.length,
      });
      onClose();
    } catch (error) {
      console.error('Error generating page:', error);
      setIsGenerating(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modalContainer, { backgroundColor: safeTheme.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: safeTheme.border }]}>
            <View style={styles.headerLeft}>
              <MaterialIcons name="add-circle" size={24} color={safeTheme.primary} />
              <Text style={[styles.title, { color: safeTheme.text }]}>New Page</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn} disabled={isGenerating}>
              <Ionicons name="close" size={24} color={safeTheme.text} />
            </TouchableOpacity>
          </View>

          {/* Body */}
          <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
            {/* Outline Input */}
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: safeTheme.text }]}>
                Page Topic / Outline
              </Text>
              <Text style={[styles.inputHint, { color: safeTheme.textSecondary }]}>
                Describe what this page should cover
              </Text>
              <TextInput
                style={[
                  styles.outlineInput,
                  {
                    color: safeTheme.text,
                    borderColor: safeTheme.border,
                    backgroundColor: safeTheme.surface,
                  },
                ]}
                placeholder="e.g., Q4 Revenue Analysis, Market Trends Overview, Executive Summary..."
                placeholderTextColor={safeTheme.textSecondary + '80'}
                value={outlineText}
                onChangeText={setOutlineText}
                multiline
                numberOfLines={3}
                textAlignVertical="top"
                editable={!isGenerating}
              />
            </View>

            {/* Special Instructions */}
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: safeTheme.text }]}>
                Special Instructions (Optional)
              </Text>
              <TextInput
                style={[
                  styles.instructionsInput,
                  {
                    color: safeTheme.text,
                    borderColor: safeTheme.border,
                    backgroundColor: safeTheme.surface,
                  },
                ]}
                placeholder="e.g., Include comparison with last quarter, focus on key metrics, use bullet points..."
                placeholderTextColor={safeTheme.textSecondary + '80'}
                value={specialInstructions}
                onChangeText={setSpecialInstructions}
                multiline
                numberOfLines={2}
                textAlignVertical="top"
                editable={!isGenerating}
              />
            </View>

            {/* Context Info */}
            {reportGoal?.purpose && (
              <View style={[styles.contextBox, { backgroundColor: safeTheme.primary + '08', borderColor: safeTheme.primary + '30' }]}>
                <MaterialIcons name="info-outline" size={16} color={safeTheme.primary} />
                <Text style={[styles.contextText, { color: safeTheme.textSecondary }]}>
                  Report Goal: {reportGoal.purpose.length > 100 ? reportGoal.purpose.substring(0, 100) + '...' : reportGoal.purpose}
                </Text>
              </View>
            )}

            {/* AI Info */}
            <View style={[styles.aiInfoBox, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
              <MaterialIcons name="auto-awesome" size={18} color={safeTheme.primary} />
              <Text style={[styles.aiInfoText, { color: safeTheme.textSecondary }]}>
                AI will choose the best layout based on your content
              </Text>
            </View>
          </ScrollView>

          {/* Footer */}
          <View style={[styles.footer, { borderTopColor: safeTheme.border }]}>
            {/* Generation Progress */}
            {isGenerating && (
              <View style={styles.generatingIndicator}>
                <ActivityIndicator size="small" color={safeTheme.primary} />
                <Text style={[styles.generatingText, { color: safeTheme.primary }]}>
                  Generating page content...
                </Text>
              </View>
            )}

            {/* Action Buttons */}
            <View style={styles.footerButtons}>
              <TouchableOpacity
                style={[styles.blankBtn, { borderColor: safeTheme.border }]}
                onPress={handleCreateBlank}
                disabled={isGenerating}
              >
                <MaterialIcons name="add" size={18} color={safeTheme.text} />
                <Text style={[styles.blankBtnText, { color: safeTheme.text }]}>Create Blank</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.generateBtn,
                  {
                    backgroundColor: outlineText.trim() && !isGenerating ? safeTheme.primary : '#ccc',
                  },
                ]}
                onPress={handleGenerateWithAI}
                disabled={!outlineText.trim() || isGenerating}
              >
                {isGenerating ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Ionicons name="sparkles" size={18} color="#fff" />
                )}
                <Text style={styles.generateBtnText}>
                  {isGenerating ? 'Generating...' : 'Generate with AI'}
                </Text>
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
    width: 500,
    maxWidth: '95%',
    maxHeight: '90%',
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
  },
  bodyContent: {
    padding: 20,
    gap: 20,
  },
  inputGroup: {
    gap: 6,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
  },
  inputHint: {
    fontSize: 12,
    marginBottom: 4,
  },
  outlineInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 80,
    textAlignVertical: 'top',
  },
  instructionsInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 60,
    textAlignVertical: 'top',
  },
  contextBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
  },
  contextText: {
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
  },
  aiInfoBox: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
  },
  aiInfoText: {
    flex: 1,
    fontSize: 13,
  },
  footer: {
    padding: 16,
    borderTopWidth: 1,
    backgroundColor: '#FAFAFA',
  },
  generatingIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginBottom: 12,
  },
  generatingText: {
    fontSize: 13,
    fontWeight: '500',
  },
  footerButtons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
  },
  blankBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
  },
  blankBtnText: {
    fontSize: 14,
    fontWeight: '500',
  },
  generateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    gap: 8,
  },
  generateBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
});

export default ReportAddPageModal;
