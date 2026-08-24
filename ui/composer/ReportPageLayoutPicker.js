// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * ReportPageLayoutPicker.js - Layout selection modal for report pages
 * 
 * Similar to SlideLayoutPicker.js in presentation flow.
 * Allows users to:
 * - Select a layout for a page (or let AI decide)
 * - Preview layout thumbnails
 * - Navigate by categories
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Modal,
  Platform,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import {
  REPORT_PAGE_LAYOUTS,
  LAYOUT_CATEGORIES,
  getLayoutsByCategory,
  LAYOUT_THUMBNAILS,
} from './utils/reportLayoutTemplates';

const ReportPageLayoutPicker = ({
  visible,
  onClose,
  onSelectLayout,
  currentLayout = 'single_column',
  theme,
  mode = 'change', // 'change' for existing page, 'new' for new page
}) => {
  const [selectedCategory, setSelectedCategory] = useState('ai');
  const [selectedLayoutId, setSelectedLayoutId] = useState(currentLayout);

  // Reset state when modal opens
  useEffect(() => {
    if (visible) {
      setSelectedLayoutId(mode === 'new' ? 'ai_auto' : currentLayout);
      setSelectedCategory(mode === 'new' ? 'ai' : 'basic');
    }
  }, [visible, currentLayout, mode]);

  const safeTheme = theme || {
    background: '#FFFFFF',
    surface: '#F9FAFB',
    text: '#1F2937',
    textSecondary: '#6B7280',
    primary: '#3B82F6',
    border: '#E5E7EB',
  };

  // Render layout thumbnail
  const renderLayoutThumbnail = (layout) => {
    const isSelected = selectedLayoutId === layout.id;
    const thumbnailSvg = LAYOUT_THUMBNAILS[layout.thumbnail] || LAYOUT_THUMBNAILS['single_column'];

    return (
      <TouchableOpacity
        key={layout.id}
        style={[
          styles.layoutCard,
          {
            borderColor: isSelected ? safeTheme.primary : safeTheme.border,
            borderWidth: isSelected ? 2 : 1,
            backgroundColor: isSelected ? safeTheme.primary + '08' : safeTheme.surface,
          },
        ]}
        onPress={() => setSelectedLayoutId(layout.id)}
        activeOpacity={0.7}
      >
        {/* Thumbnail Preview */}
        <View
          style={[
            styles.thumbnailContainer,
            { backgroundColor: isSelected ? safeTheme.primary + '10' : '#F3F4F6' },
          ]}
        >
          {layout.isAIDecide ? (
            <View style={styles.aiDecideContent}>
              <MaterialIcons name="auto-awesome" size={28} color={safeTheme.primary} />
              <Text style={[styles.aiDecideLabel, { color: safeTheme.primary }]}>
                AI DECIDE
              </Text>
            </View>
          ) : (
            <View
              style={[styles.svgContainer, { color: safeTheme.text }]}
              dangerouslySetInnerHTML={Platform.OS === 'web' ? { __html: thumbnailSvg } : undefined}
            >
              {Platform.OS !== 'web' && (
                <MaterialIcons name={layout.icon} size={32} color={safeTheme.textSecondary} />
              )}
            </View>
          )}
        </View>

        {/* Layout Name */}
        <Text
          style={[
            styles.layoutName,
            {
              color: isSelected ? safeTheme.primary : safeTheme.text,
              fontWeight: isSelected ? '600' : '500',
            },
          ]}
          numberOfLines={1}
        >
          {layout.name}
        </Text>

        {/* Selection Check */}
        {isSelected && (
          <View style={[styles.checkBadge, { backgroundColor: safeTheme.primary }]}>
            <Ionicons name="checkmark" size={12} color="#fff" />
          </View>
        )}
      </TouchableOpacity>
    );
  };

  // Render category button
  const renderCategoryButton = (category) => {
    const isActive = selectedCategory === category.id;
    return (
      <TouchableOpacity
        key={category.id}
        style={[
          styles.categoryButton,
          isActive && { backgroundColor: safeTheme.primary + '15' },
        ]}
        onPress={() => setSelectedCategory(category.id)}
      >
        <MaterialIcons
          name={category.icon}
          size={18}
          color={isActive ? safeTheme.primary : safeTheme.textSecondary}
        />
        <Text
          style={[
            styles.categoryText,
            {
              color: isActive ? safeTheme.primary : safeTheme.textSecondary,
              fontWeight: isActive ? '600' : '500',
            },
          ]}
        >
          {category.name}
        </Text>
      </TouchableOpacity>
    );
  };

  const handleConfirm = () => {
    if (selectedLayoutId) {
      onSelectLayout(selectedLayoutId);
      onClose();
    }
  };

  const currentLayouts = getLayoutsByCategory(selectedCategory);
  const selectedLayout = REPORT_PAGE_LAYOUTS[selectedLayoutId];

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modalContainer, { backgroundColor: safeTheme.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: safeTheme.border }]}>
            <Text style={[styles.title, { color: safeTheme.text }]}>
              {mode === 'new' ? 'Choose Page Layout' : 'Change Layout'}
            </Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={safeTheme.text} />
            </TouchableOpacity>
          </View>

          {/* Body */}
          <View style={styles.body}>
            {/* Category Sidebar */}
            <View style={[styles.sidebar, { borderRightColor: safeTheme.border }]}>
              {LAYOUT_CATEGORIES.map(renderCategoryButton)}
            </View>

            {/* Layout Grid */}
            <ScrollView style={styles.gridArea} contentContainerStyle={styles.gridContent}>
              {/* Category Description */}
              <Text style={[styles.categoryDescription, { color: safeTheme.textSecondary }]}>
                {LAYOUT_CATEGORIES.find((c) => c.id === selectedCategory)?.description}
              </Text>

              {/* Layouts Grid */}
              <View style={styles.layoutsGrid}>
                {currentLayouts.map(renderLayoutThumbnail)}
              </View>
            </ScrollView>
          </View>

          {/* Footer with Selection Info */}
          <View style={[styles.footer, { borderTopColor: safeTheme.border }]}>
            {/* Selected Layout Info */}
            <View style={styles.selectionInfo}>
              {selectedLayout && (
                <>
                  <MaterialIcons
                    name={selectedLayout.icon || 'view-agenda'}
                    size={20}
                    color={safeTheme.primary}
                  />
                  <View style={styles.selectionTextContainer}>
                    <Text style={[styles.selectionName, { color: safeTheme.text }]}>
                      {selectedLayout.name}
                    </Text>
                    <Text style={[styles.selectionDesc, { color: safeTheme.textSecondary }]}>
                      {selectedLayout.description}
                    </Text>
                  </View>
                </>
              )}
            </View>

            {/* Action Buttons */}
            <View style={styles.footerButtons}>
              <TouchableOpacity
                style={[styles.cancelBtn, { borderColor: safeTheme.border }]}
                onPress={onClose}
              >
                <Text style={[styles.cancelBtnText, { color: safeTheme.text }]}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.confirmBtn,
                  { backgroundColor: selectedLayoutId ? safeTheme.primary : '#ccc' },
                ]}
                onPress={handleConfirm}
                disabled={!selectedLayoutId}
              >
                <MaterialIcons name="check" size={18} color="#fff" />
                <Text style={styles.confirmBtnText}>Apply Layout</Text>
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
    width: 720,
    maxWidth: '95%',
    height: 560,
    maxHeight: '90%',
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 10,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
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
    flexDirection: 'row',
  },
  sidebar: {
    width: 160,
    borderRightWidth: 1,
    padding: 12,
    backgroundColor: '#FAFAFA',
  },
  categoryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 8,
    marginBottom: 4,
    gap: 10,
  },
  categoryText: {
    fontSize: 14,
  },
  gridArea: {
    flex: 1,
    padding: 20,
  },
  gridContent: {
    paddingBottom: 20,
  },
  categoryDescription: {
    fontSize: 13,
    marginBottom: 16,
    fontStyle: 'italic',
  },
  layoutsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  layoutCard: {
    width: 140,
    borderRadius: 10,
    overflow: 'hidden',
    position: 'relative',
  },
  thumbnailContainer: {
    height: 90,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 8,
  },
  svgContainer: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  aiDecideContent: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  aiDecideLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  layoutName: {
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  checkBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footer: {
    padding: 16,
    borderTopWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FAFAFA',
  },
  selectionInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  selectionTextContainer: {
    flex: 1,
  },
  selectionName: {
    fontSize: 14,
    fontWeight: '600',
  },
  selectionDesc: {
    fontSize: 12,
    marginTop: 2,
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
  confirmBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    gap: 6,
  },
  confirmBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
});

export default ReportPageLayoutPicker;
