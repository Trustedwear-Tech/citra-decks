// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// ReportPreviewModal.js - Full preview of all report pages combined
// Renders all pages in a continuous scroll view, matching export output exactly
import React, { useMemo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  StyleSheet,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { generateReportHTML } from './utils/generateReportHTML';

const ReportPreviewModal = ({
  visible,
  onClose,
  pages,
  reportMetadata,
  reportGoal,
  theme,
  userType,
  onExport, // Optional: shortcut to open export from preview
}) => {
  const { width: windowWidth } = useWindowDimensions();
  const isMobile = windowWidth < 768;

  // Generate the combined HTML for all pages
  const previewHTML = useMemo(() => {
    if (!visible || !pages || pages.length === 0) return '';
    return generateReportHTML({ pages, reportMetadata, reportGoal, userType });
  }, [visible, pages, reportMetadata, reportGoal, userType]);

  if (!visible) return null;

  const safeTheme = theme || {};

  return (
    <Modal
      visible={visible}
      animationType="slide"
      onRequestClose={onClose}
      supportedOrientations={['portrait', 'landscape']}
    >
      <View style={[styles.container, { backgroundColor: safeTheme.background || '#f5f5f5' }]}>

        {/* Header Bar */}
        <View style={[
          styles.header,
          {
            backgroundColor: safeTheme.surface || '#ffffff',
            borderBottomColor: safeTheme.borderColor || '#E5E7EB',
          }
        ]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={isMobile ? 22 : 24} color={safeTheme.text || '#333'} />
          </TouchableOpacity>

          <View style={styles.headerCenter}>
            <Ionicons name="eye-outline" size={isMobile ? 16 : 18} color={safeTheme.primary || '#6366F1'} />
            <Text
              style={[
                styles.headerTitle,
                { color: safeTheme.text || '#333', fontSize: isMobile ? 15 : 16 }
              ]}
              numberOfLines={1}
            >
              Preview
            </Text>
            <Text style={[styles.headerSubtitle, { color: safeTheme.textSecondary || '#888' }]}>
              {pages.length} {pages.length === 1 ? 'page' : 'pages'}
            </Text>
          </View>

          <View style={styles.headerRight}>
            {onExport && (
              <TouchableOpacity
                onPress={() => {
                  onClose();
                  setTimeout(() => onExport(), 150);
                }}
                style={[styles.exportBtn, { backgroundColor: safeTheme.primary || '#6366F1' }]}
              >
                <Ionicons name="download-outline" size={16} color="#fff" />
                {!isMobile && <Text style={styles.exportBtnText}>Export</Text>}
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Preview Content */}
        <View style={styles.previewBody}>
          {Platform.OS === 'web' ? (
            <iframe
              srcDoc={previewHTML}
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
                backgroundColor: '#fff',
              }}
              title="Report Preview"
              sandbox="allow-same-origin"
            />
          ) : (
            // Native fallback - render a simplified view
            <View style={styles.nativeFallback}>
              <Ionicons name="document-text-outline" size={48} color={safeTheme.textSecondary || '#999'} />
              <Text style={[styles.nativeFallbackText, { color: safeTheme.text || '#333' }]}>
                Full preview is available on web.
              </Text>
              <Text style={[styles.nativeFallbackSub, { color: safeTheme.textSecondary || '#888' }]}>
                Use Export to view the complete report.
              </Text>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    zIndex: 10,
    gap: 12,
  },
  closeButton: {
    padding: 6,
    borderRadius: 6,
  },
  headerCenter: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  headerSubtitle: {
    fontSize: 12,
    marginLeft: 4,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  exportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 6,
    gap: 6,
  },
  exportBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  previewBody: {
    flex: 1,
    overflow: 'hidden',
  },
  nativeFallback: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
    gap: 12,
  },
  nativeFallbackText: {
    fontSize: 16,
    fontWeight: '500',
    textAlign: 'center',
  },
  nativeFallbackSub: {
    fontSize: 14,
    textAlign: 'center',
  },
});

export default ReportPreviewModal;
