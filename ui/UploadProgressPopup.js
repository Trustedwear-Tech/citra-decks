/**
 * UploadProgressPopup.js
 * ======================
 * Floating modeless popup for upload progress tracking.
 * Allows users to continue working while uploads are in progress.
 * 
 * Features:
 * - Draggable floating position
 * - Collapsible/expandable
 * - Shows individual file progress
 * - Non-blocking UI
 */

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Platform,
  Animated,
  Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import ChatUploadBubble from './ChatUploadBubble';

const UploadProgressPopup = ({
  visible,
  enhancedProgress,
  theme,
  onClose,
  onDismissEntry,
  position = { bottom: 20, right: 20 },
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [popupPosition, setPopupPosition] = useState(position);
  const [isDismissed, setIsDismissed] = useState(false);
  const prevSizeRef = useRef(0);

  const safeTheme = theme || {
    background: '#FFFFFF',
    text: '#1F2937',
    textSecondary: '#6B7280',
    borderColor: '#E5E7EB',
    primary: '#3B82F6',
  };

  // Calculate counts
  const getProgressCounts = useCallback(() => {
    if (!enhancedProgress || enhancedProgress.size === 0) {
      return { queued: 0, processing: 0, completed: 0, total: 0 };
    }

    const entries = Array.from(enhancedProgress.values());
    return {
      queued: entries.filter(p => p.stage === 'queued').length,
      processing: entries.filter(p => 
        ['processing', 'analyzing', 'embedding', 'uploading'].includes(p.stage)
      ).length,
      completed: entries.filter(p => p.stage === 'completed' || p.stage === 'success').length,
      total: enhancedProgress.size,
    };
  }, [enhancedProgress]);

  const counts = getProgressCounts();

  // Detect IMAGE_ONLY_PDF errors in the progress entries
  const [dismissedOcrAlerts, setDismissedOcrAlerts] = useState(new Set());
  const ocrAlertEntry = useMemo(() => {
    if (!enhancedProgress || enhancedProgress.size === 0) return null;
    for (const [id, entry] of enhancedProgress.entries()) {
      if (entry.errorCode === 'IMAGE_ONLY_PDF' && !dismissedOcrAlerts.has(id)) {
        return { id, filename: entry.filename || 'file' };
      }
    }
    return null;
  }, [enhancedProgress, dismissedOcrAlerts]);

  const handleDismissOcrAlert = useCallback(() => {
    if (ocrAlertEntry) {
      setDismissedOcrAlerts(prev => new Set(prev).add(ocrAlertEntry.id));
    }
  }, [ocrAlertEntry]);

  // Re-show popup when new uploads are added
  useEffect(() => {
    const currentSize = enhancedProgress ? enhancedProgress.size : 0;
    if (currentSize > prevSizeRef.current) {
      setIsDismissed(false);
    }
    prevSizeRef.current = currentSize;
  }, [enhancedProgress]);

  // Auto-close: when all entries are in a terminal state (complete/error/redis_down/success),
  // clean them up after a short delay
  useEffect(() => {
    if (!enhancedProgress || enhancedProgress.size === 0) return;

    const entries = Array.from(enhancedProgress.entries());
    const terminalStages = ['complete', 'completed', 'success', 'error', 'redis_down'];
    const allTerminal = entries.every(([, p]) => terminalStages.includes(p.stage));

    if (allTerminal && onDismissEntry) {
      // Give 20s for error bubbles, 8s for complete bubbles to show before clearing map
      const hasErrors = entries.some(([, p]) => p.stage === 'error');
      const delay = hasErrors ? 20000 : 8000;

      const timer = setTimeout(() => {
        entries.forEach(([id]) => onDismissEntry(id));
      }, delay);

      return () => clearTimeout(timer);
    }
  }, [enhancedProgress, onDismissEntry]);

  // Handle manual close: dismiss the popup and clear terminal entries
  const handleClose = useCallback(() => {
    if (onDismissEntry && enhancedProgress) {
      const terminalStages = ['complete', 'completed', 'success', 'error', 'redis_down'];
      for (const [id, p] of enhancedProgress.entries()) {
        if (terminalStages.includes(p.stage)) {
          onDismissEntry(id);
        }
      }
    }
    setIsDismissed(true);
    if (onClose) onClose();
  }, [enhancedProgress, onDismissEntry, onClose]);

  // Don't render if not visible or no uploads or manually dismissed
  if (!visible || !enhancedProgress || enhancedProgress.size === 0 || isDismissed) {
    return null;
  }

  // Handle drag for web
  const handleDragStart = (e) => {
    if (Platform.OS !== 'web') return;
    setIsDragging(true);
  };

  const handleDrag = (e) => {
    if (Platform.OS !== 'web' || !isDragging) return;
    // Web drag handling would go here
  };

  const handleDragEnd = () => {
    setIsDragging(false);
  };

  return (
    <>
      {/* OCR Required Alert — rendered at same level as progress popup for guaranteed visibility */}
      {ocrAlertEntry && (
        <View style={styles.ocrAlertOverlay}>
          <View style={styles.ocrAlertCard}>
            <View style={styles.ocrAlertIconRow}>
              <View style={styles.ocrAlertIconCircle}>
                <Ionicons name="warning" size={28} color="#F59E0B" />
              </View>
            </View>
            <Text style={styles.ocrAlertTitle}>OCR Upload Required</Text>
            <Text style={styles.ocrAlertMessage}>
              <Text style={{ fontWeight: '600' }}>"{ocrAlertEntry.filename}"</Text>
              {' '}contains only images with no extractable text.{'\n\n'}
              To process this file, please re-upload using the{' '}
              <Text style={{ fontWeight: '700', color: '#2563EB' }}>OCR Upload</Text>
              {' '}option, which can read text from images, scanned documents & presentations.
            </Text>
            <TouchableOpacity
              style={styles.ocrAlertButton}
              onPress={handleDismissOcrAlert}
              activeOpacity={0.8}
            >
              <Text style={styles.ocrAlertButtonText}>Got it</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

    <View
      style={[
        styles.container,
        {
          bottom: popupPosition.bottom,
          right: popupPosition.right,
        },
      ]}
    >
      <View style={[styles.popup, { backgroundColor: safeTheme.background }]}>
        {/* Header - Always visible */}
        <TouchableOpacity
          style={[styles.header, { borderBottomColor: safeTheme.borderColor }]}
          onPress={() => setIsCollapsed(!isCollapsed)}
          activeOpacity={0.8}
        >
          <View style={styles.headerLeft}>
            <View style={styles.uploadingIndicator}>
              {counts.processing > 0 && (
                <View style={styles.pulsingDot} />
              )}
              <Ionicons 
                name="cloud-upload" 
                size={18} 
                color={counts.processing > 0 ? '#3B82F6' : '#10B981'} 
              />
            </View>
            <Text style={[styles.headerTitle, { color: safeTheme.text }]}>
              {counts.processing > 0 
                ? `Uploading ${counts.processing} file${counts.processing > 1 ? 's' : ''}...`
                : `${counts.total} upload${counts.total > 1 ? 's' : ''}`
              }
            </Text>
          </View>
          <View style={styles.headerRight}>
            <View style={styles.countBadges}>
              {counts.queued > 0 && (
                <View style={[styles.badge, styles.queuedBadge]}>
                  <Text style={styles.badgeText}>{counts.queued}</Text>
                </View>
              )}
              {counts.processing > 0 && (
                <View style={[styles.badge, styles.processingBadge]}>
                  <Text style={styles.badgeText}>{counts.processing}</Text>
                </View>
              )}
              {counts.completed > 0 && (
                <View style={[styles.badge, styles.completedBadge]}>
                  <Text style={styles.badgeText}>{counts.completed}</Text>
                </View>
              )}
            </View>
            <Ionicons 
              name={isCollapsed ? 'chevron-up' : 'chevron-down'} 
              size={18} 
              color={safeTheme.textSecondary} 
            />
            <TouchableOpacity 
              onPress={handleClose} 
              style={styles.closeBtn}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Ionicons name="close" size={16} color={safeTheme.textSecondary} />
            </TouchableOpacity>
          </View>
        </TouchableOpacity>

        {/* Content - Collapsible */}
        {!isCollapsed && (
          <View style={styles.content}>
            {/* Quick Summary */}
            <View style={[styles.summary, { borderBottomColor: safeTheme.borderColor }]}>
              <View style={styles.summaryItem}>
                <Text style={[styles.summaryLabel, { color: safeTheme.textSecondary }]}>Queued</Text>
                <Text style={[styles.summaryValue, { color: '#F59E0B' }]}>{counts.queued}</Text>
              </View>
              <View style={styles.summaryItem}>
                <Text style={[styles.summaryLabel, { color: safeTheme.textSecondary }]}>Processing</Text>
                <Text style={[styles.summaryValue, { color: '#3B82F6' }]}>{counts.processing}</Text>
              </View>
              <View style={styles.summaryItem}>
                <Text style={[styles.summaryLabel, { color: safeTheme.textSecondary }]}>Done</Text>
                <Text style={[styles.summaryValue, { color: '#10B981' }]}>{counts.completed}</Text>
              </View>
            </View>

            {/* Upload Items */}
            <ScrollView 
              style={styles.uploadList} 
              showsVerticalScrollIndicator={false}
              contentContainerStyle={styles.uploadListContent}
            >
              {Array.from(enhancedProgress.entries()).map(([id, progress]) => (
                <ChatUploadBubble
                  key={id}
                  stage={progress.stage}
                  progress={progress.progress}
                  documentId={progress.documentId || id}
                  filename={progress.topic_or_filename || progress.filename}
                  error={progress.error}
                  uploadType={progress.uploadType}
                  queuePosition={progress.queuePosition}
                  style={styles.uploadItem}
                  onDismiss={() => {
                    if (onDismissEntry) onDismissEntry(id);
                  }}
                />
              ))}
            </ScrollView>
          </View>
        )}
      </View>
    </View>
    </>
  );
};

const styles = StyleSheet.create({
  container: {
    position: Platform.OS === 'web' ? 'fixed' : 'absolute',
    zIndex: 99999,
    ...Platform.select({
      web: {
        pointerEvents: 'auto',
      },
    }),
  },
  popup: {
    width: 320,
    maxHeight: 400,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.08)',
    ...Platform.select({
      web: {
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
      },
    }),
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    ...Platform.select({
      web: {
        cursor: 'pointer',
      },
    }),
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  uploadingIndicator: {
    position: 'relative',
  },
  pulsingDot: {
    position: 'absolute',
    top: -2,
    right: -2,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#3B82F6',
    ...Platform.select({
      web: {
        animation: 'pulse 1.5s infinite',
      },
    }),
  },
  headerTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  countBadges: {
    flexDirection: 'row',
    gap: 4,
  },
  badge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  queuedBadge: {
    backgroundColor: '#FEF3C7',
  },
  processingBadge: {
    backgroundColor: '#DBEAFE',
  },
  completedBadge: {
    backgroundColor: '#D1FAE5',
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#374151',
  },
  closeBtn: {
    padding: 4,
    marginLeft: 4,
  },
  content: {
    maxHeight: 320,
  },
  summary: {
    flexDirection: 'row',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 1,
    gap: 16,
  },
  summaryItem: {
    alignItems: 'center',
  },
  summaryLabel: {
    fontSize: 10,
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  summaryValue: {
    fontSize: 16,
    fontWeight: '700',
  },
  uploadList: {
    maxHeight: 250,
  },
  uploadListContent: {
    padding: 12,
    gap: 8,
  },
  uploadItem: {
    marginBottom: 8,
  },
  // ── OCR Alert Overlay ──
  ocrAlertOverlay: {
    position: Platform.OS === 'web' ? 'fixed' : 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 999999,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    justifyContent: 'center',
    alignItems: 'center',
    ...Platform.select({
      web: { pointerEvents: 'auto' },
    }),
  },
  ocrAlertCard: {
    width: Math.min(Dimensions.get('window').width - 48, 400),
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 28,
    alignItems: 'center',
    ...Platform.select({
      web: { boxShadow: '0 8px 32px rgba(0,0,0,0.25)' },
    }),
    elevation: 10,
  },
  ocrAlertIconRow: {
    marginBottom: 12,
  },
  ocrAlertIconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#FEF3C7',
    justifyContent: 'center',
    alignItems: 'center',
  },
  ocrAlertTitle: {
    fontSize: 19,
    fontWeight: '700',
    color: '#1F2937',
    marginBottom: 10,
    textAlign: 'center',
  },
  ocrAlertMessage: {
    fontSize: 14,
    lineHeight: 21,
    color: '#4B5563',
    textAlign: 'center',
    marginBottom: 22,
  },
  ocrAlertButton: {
    backgroundColor: '#2563EB',
    paddingVertical: 12,
    paddingHorizontal: 40,
    borderRadius: 10,
    alignItems: 'center',
    minWidth: 140,
  },
  ocrAlertButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
});

export default UploadProgressPopup;
