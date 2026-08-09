// ReportComposer.js - AI Report Generator with WYSIWYG Editor
import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Modal,
  Alert,
  ActivityIndicator,
  StyleSheet,
  Platform,
  Image
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import ReportGoalSetting from './ReportGoalSetting';
import ExportModal from './ExportModal';
import { useReportPages } from './hooks/useReportPages';
import { useReportPersistence } from './hooks/useReportPersistence';
import ReportListModal from './ReportListModal';
import { ShareButton } from '../ShareManager';
import ChartStudio from './ChartStudio';
import ChartEditModal from './ChartEditModal';
import AIImageModal from './AIImageModal';

import { renderChartToImage } from '../../utils/chartRenderer';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { navigateToReport } from '../../utils/urlRouter';
import UnifiedUploadModal from '../UnifiedUploadModal'; // Unified upload modal
import UploadProgressPopup from '../UploadProgressPopup'; // Upload progress popup for visibility inside modal

import authService from '../../services/authService';
import { API_CONFIG } from '../../config/config';
import TiptapEditor from './TiptapEditor';
import ComposerToolbar from './ComposerToolbar';
import CollaborationPanel from './CollaborationPanel';
import CollaborationLockIndicator from './CollaborationLockIndicator'; // Imported
import FolderDetailModal from '../FolderDetailModal';
import UpdateInstructionModal from './UpdateInstructionModal'; // Imported
import EditSlideOutlineModal from './EditSlideOutlineModal'; // Edit single section topic/outline
import { useCollaboration } from './hooks/useCollaboration'; // New Import
import ImageGenService from '../../services/ImageGenService'; // Image Generation Service (LLMImageService's backend, /llm-image/*, doesn't exist in citra-decks — this is the one working image-gen path, see call site below)
import Tooltip from '../ui/Tooltip'; // Import Tooltip
import { showDesktopEditingAlert } from '../../utils/mobileEditAlert';
import globalImageCache from '../../utils/globalImageCache'; // Image blob cache for reliable rendering

// New Layout System Imports - ReportPageLayoutPicker removed (layout set at page creation)
import ReportAddPageModal from './ReportAddPageModal';
import ReportHeaderFooterModal from './ReportHeaderFooterModal';
import ReportStylePicker, { REPORT_STYLES, getStyleCSS } from './ReportStylePicker';
import ReportPreviewModal from './ReportPreviewModal';
import { buildPagesSummary } from '../../utils/slideTextExtractor';
import { REPORT_PAGE_LAYOUTS, getLayoutCSS, generateLayoutHTML } from './utils/reportLayoutTemplates';

/**
 * Extract all image URLs from HTML content (skips data: and blob: URLs).
 * Used to bulk pre-cache S3 images via globalImageCache on report load.
 */
function _extractImageUrlsFromHtml(html) {
  if (!html) return [];
  const imgRegex = /<img\s+[^>]*src\s*=\s*["']([^"']+)["'][^>]*>/gi;
  const urls = [];
  let match;
  while ((match = imgRegex.exec(html)) !== null) {
    const url = match[1];
    if (url && !url.startsWith('data:') && !url.startsWith('blob:')) {
      urls.push(url);
    }
  }
  return urls;
}

/**
 * Bulk pre-cache all images found in an array of page objects.
 * Fire-and-forget — does not block rendering.
 */
function _preCachePageImages(pages) {
  const allUrls = pages.flatMap(p => _extractImageUrlsFromHtml(p.content));
  if (allUrls.length > 0) {
    console.log(`📷 [REPORT] Pre-caching ${allUrls.length} images from ${pages.length} pages...`);
    globalImageCache.preCacheAll(allUrls).catch(err =>
      console.warn('⚠️ [REPORT] Bulk pre-cache failed:', err.message)
    );
  }
}

// Flag for Tiptap availability on web
const hasTiptap = Platform.OS === 'web';

// Module-level counter for unique chat message IDs (prevents duplicate React keys when Date.now() collides)
let _chatMsgId = 0;
const chatMsgUid = () => `msg_${Date.now()}_${++_chatMsgId}`;

// ── Agent image markers ──────────────────────────────────────────────────────
// Page HTML can contain base64 data-URI images (Tiptap inserts uploads inline)
// and very long presigned S3 URLs. NEVER send those to the LLM — swap each img
// src for a short {{IMG_n}} marker before sending, and restore after applying
// the agent's operations. The agent keeps/moves/removes the whole <img> tag;
// the marker round-trips the real src.
const markerizeReportImages = (pagesArr) => {
  const map = {};
  let n = 0;
  const swap = (content) => (content || '').replace(
    /(<img\b[^>]*?\ssrc=)(["'])([^"']+)\2/gi,
    (m, pre, q, src) => {
      if (src.startsWith('{{')) return m;            // already a marker
      if (!src.startsWith('data:') && src.length <= 120) return m; // short URL — cheap, keep
      const key = `{{IMG_${++n}}}`;
      map[key] = src;
      return `${pre}${q}${key}${q}`;
    }
  );
  return { pages: pagesArr.map(p => ({ ...p, content: swap(p.content) })), map };
};

const restoreReportImages = (content, map) => {
  let out = content || '';
  for (const [key, src] of Object.entries(map)) {
    out = out.split(key).join(src);
  }
  return out;
};

// ── In-editor chrome preview ─────────────────────────────────────────────────
// Letterhead / header / footer are document settings rendered fully in exports
// and the share view; this lightweight read-only preview makes them visible in
// the editor too (WYSIWYG). Mirrors generateReportHTML's show rules.
const ReportChromePreview = ({ position, pageIndex, totalPages, letterhead, header, footer, title, author }) => {
  const resolve = (text) => (text || '')
    .replaceAll('{date}', new Date().toLocaleDateString('en-GB'))
    .replaceAll('{page}', String(pageIndex + 1))
    .replaceAll('{total}', String(totalPages))
    .replaceAll('{title}', title || '')
    .replaceAll('{author}', author || '');

  const isFirst = pageIndex === 0;
  const lh = letterhead || {};
  const hdr = header || {};
  const ftr = footer || {};

  if (position === 'top') {
    const showLh = lh.enabled && (isFirst || lh.allPages);
    const showHdr = hdr.enabled && (!isFirst || hdr.showOnFirstPage);
    if (!showLh && !showHdr) return null;
    return (
      <View style={{ width: '100%', maxWidth: 1100, alignSelf: 'center', paddingHorizontal: 4 }}>
        {showLh && (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 8 }}>
              {lh.logoUrl ? <Image source={{ uri: lh.logoUrl }} style={{ width: 56, height: 56, borderRadius: 6 }} resizeMode="contain" /> : null}
              <View style={{ flex: 1 }}>
                {!!lh.companyName && <Text style={{ fontSize: 16, fontWeight: '700', color: '#1f2937' }} numberOfLines={1}>{lh.companyName}</Text>}
                {!!lh.address && <Text style={{ fontSize: 11, color: '#4b5563' }} numberOfLines={2}>{lh.address}</Text>}
                {!!([lh.phone, lh.email, lh.website].filter(Boolean).length) && (
                  <Text style={{ fontSize: 11, color: '#4b5563' }} numberOfLines={1}>
                    {[lh.phone, lh.email, lh.website].filter(Boolean).join('  •  ')}
                  </Text>
                )}
              </View>
            </View>
            {lh.showRule !== false && <View style={{ height: 2, backgroundColor: '#1f2937', marginBottom: 8 }} />}
          </>
        )}
        {showHdr && (
          <View style={{ flexDirection: 'row', alignItems: 'center', paddingBottom: 4, borderBottomWidth: 1, borderBottomColor: '#e5e7eb', marginBottom: 6 }}>
            <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'left' }} numberOfLines={1}>{resolve(hdr.leftContent)}</Text>
            <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'center' }} numberOfLines={1}>{resolve(hdr.centerContent)}</Text>
            <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'right' }} numberOfLines={1}>{resolve(hdr.rightContent)}</Text>
          </View>
        )}
      </View>
    );
  }

  // bottom
  const showFtr = ftr.enabled && (!isFirst || ftr.showOnFirstPage !== false);
  if (!showFtr) return null;
  return (
    <View style={{ width: '100%', maxWidth: 1100, alignSelf: 'center', paddingHorizontal: 4, flexDirection: 'row', alignItems: 'center', paddingTop: 4, borderTopWidth: 1, borderTopColor: '#e5e7eb', marginTop: 2, marginBottom: 6 }}>
      <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'left' }} numberOfLines={1}>{resolve(ftr.leftContent)}</Text>
      <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'center' }} numberOfLines={1}>{resolve(ftr.centerContent)}</Text>
      <Text style={{ flex: 1, fontSize: 10, color: '#6b7280', textAlign: 'right' }} numberOfLines={1}>{resolve(ftr.rightContent)}</Text>
    </View>
  );
};

/**
 * Helper function to check if an error/response indicates insufficient credits
 */
const isInsufficientCreditsError = (data) => {
  if (!data) return false;

  // Handle string data (e.g., "402: {'error': 'insufficient_credits', ...}")
  if (typeof data === 'string') {
    const lower = data.toLowerCase();
    if (lower.includes('insufficient_credits') || lower.includes('insufficient credits') ||
      lower.includes('negative balance') || lower.includes('purchase credits')) {
      console.log('💰 [CREDITS] Detected credit error in string data:', data.substring(0, 100));
      return true;
    }
    return false;
  }

  const errorType = data.error || data.error_type || data.detail?.error || '';
  const errorMessage = data.message || data.detail?.message || data.detail || '';
  const errorStr = typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage || '');

  if (errorType === 'insufficient_credits') {
    console.log('💰 [CREDITS] Detected insufficient_credits error type');
    return true;
  }

  if (errorStr) {
    const lowerMessage = errorStr.toLowerCase();
    if (lowerMessage.includes('insufficient credits') || lowerMessage.includes('insufficient_credits') ||
      lowerMessage.includes('negative balance') ||
      lowerMessage.includes('purchase credits')) {
      console.log('💰 [CREDITS] Detected credit error in message:', errorStr);
      return true;
    }
  }

  if (typeof errorType === 'string' && errorType.toLowerCase().includes('insufficient')) {
    console.log('💰 [CREDITS] Detected credit error in error field:', errorType);
    return true;
  }

  return false;
};

/**
 * Trigger the buy credits modal if a credit error is detected
 */
const handleCreditError = (data) => {
  if (isInsufficientCreditsError(data)) {
    const message = data.message || data.detail?.message || 'Insufficient credits. Please purchase more credits to continue.';
    console.log('💰 [CREDITS] Credit error detected! Triggering buy credits modal');
    authService.notifyCreditRequired(message);
    return true;
  }
  return false;
};

// HTML Handler for Tiptap (HTML-First Approach)
// - AI now generates HTML directly (<p>, <strong>, <ul>, <table>, etc.)
// - HTML detection passes it through unchanged
// - Markdown conversion below is LEGACY FALLBACK for old content/pastes
const markdownToHtml = (text, isDark = false) => {
  if (!text) return '';

  let html = text;

  // Improved HTML detection:
  // 1. Check for common block-level HTML tags at the start
  // 2. Check for multiple HTML tags throughout (indicates HTML content)
  // 3. Check for ReactQuill-specific tags like <p> wrapping
  // 4. Check for <br>, <span>, <strong>, <em> which indicate HTML
  // 5. Check for <table> tags which should be preserved
  const hasHTMLTagsAtStart = /^\s*<(p|div|h[1-6]|ul|ol|li|blockquote|br|span|strong|em|table)[^>]*>/i.test(text);
  const tagMatches = text.match(/<[^>]+>/g) || [];
  const tagCount = tagMatches.length;
  const hasHTMLStructure = tagCount > 2;
  const hasCommonHTMLTags = /<(p|div|br|span|strong|em|ul|ol|li|table|tr|td|th)[^>]*>/i.test(text);

  // If it looks like HTML, return as-is
  if (hasHTMLTagsAtStart || hasHTMLStructure || hasCommonHTMLTags) {
    return text;
  }

  // Escape HTML first ONLY if we are fairly sure it's not HTML
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4 style="font-size: 1.1em; font-weight: 600; margin: 14px 0 6px 0; color: #444;">$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3 style="font-size: 1.17em; font-weight: 600; margin: 16px 0 8px 0; color: #333;">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 style="font-size: 1.3em; font-weight: 600; margin: 20px 0 10px 0; color: #333;">$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1 style="font-size: 1.5em; font-weight: 700; margin: 24px 0 12px 0; color: #333;">$1</h1>');

  // Remove empty list items (e.g. "* " or "- " with no text)
  html = html.replace(/^[-*]\s*$/gm, '');
  html = html.replace(/^\d+\.\s*$/gm, '');

  // Lists - Ordered (1. Item)
  // Wrap list items in temp tags to group them later
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<ol-item>$1</ol-item>');

  // Lists - Unordered (- Item or * Item)
  html = html.replace(/^[-*]\s+(.+)$/gm, '<ul-item>$1</ul-item>');

  // Group list items
  html = html.replace(/(<ol-item>.*?<\/ol-item>\s*)+/gs, (match) => {
    return '<ol style="padding-left: 20px; margin-bottom: 12px;">' + match.replace(/<ol-item>(.*?)<\/ol-item>/g, '<li style="margin-bottom: 4px;">$1</li>') + '</ol>';
  });

  html = html.replace(/(<ul-item>.*?<\/ul-item>\s*)+/gs, (match) => {
    return '<ul style="padding-left: 20px; margin-bottom: 12px;">' + match.replace(/<ul-item>(.*?)<\/ul-item>/g, '<li style="margin-bottom: 4px;">$1</li>') + '</ul>';
  });

  // Bold and Italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="font-weight: 600;">$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em style="font-style: italic;">$1</em>');
  html = html.replace(/__(.+?)__/g, '<strong style="font-weight: 600;">$1</strong>');
  html = html.replace(/_(.+?)_/g, '<em style="font-style: italic;">$1</em>');

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em;">$1</code>');

  // Links
  const linkColor = isDark ? '#79c0ff' : '#0066cc';
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" target="_blank" rel="noopener noreferrer" style="color: ${linkColor}; text-decoration: underline;">$1</a>`);


  // Auto-link URLs
  html = html.replace(/(^|[^"])(https?:\/\/[^\s<]+)/g, `$1<a href="$2" target="_blank" rel="noopener noreferrer" style="color: ${linkColor}; text-decoration: underline;">$2</a>`);

  // Blockquotes
  html = html.replace(/^> (.+)$/gm, '<blockquote style="border-left: 3px solid #2196F3; padding-left: 16px; margin: 12px 0; color: #555; font-style: italic;">$1</blockquote>');

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">');

  // Unordered lists
  html = html.replace(/^[\-\*] (.+)$/gm, '<li style="margin: 4px 0; margin-left: 20px;">$1</li>');

  // Numbered lists  
  html = html.replace(/^\d+\. (.+)$/gm, '<li style="margin: 4px 0; margin-left: 20px;">$1</li>');

  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, '</p><p style="margin: 12px 0; line-height: 1.7;">');

  // Single newlines to <br>
  html = html.replace(/\n/g, '<br>');

  // Wrap in paragraph
  html = `<p style="margin: 12px 0; line-height: 1.7;">${html}</p>`;

  return html;
};

// Section word limit - auto-create continuation when exceeded
// Note: "Pages" here are content SECTIONS (like chapters), not physical PDF pages
// PDF/DOCX export handles actual page layout based on content length
const SECTION_WORD_LIMIT = 800;

// ═══════════════════════════════════════════════════════════════════
// PageEditorCard — Memoized wrapper for each page in continuous scroll.
// Only re-renders when its own page data changes, NOT when other pages or currentPageId changes.
// ═══════════════════════════════════════════════════════════════════
const PageEditorCard = React.memo(({
  page,
  pageIndex,
  totalPages,
  isActive,
  isMobile,
  onLayout,
  onContentChange,
  onSelectionChange,
  onChartEdit,
  onTitleChange,
  onFocus,
  editorRefCallback,
  getEditorPlaceholder,
  safeTheme,
  personaText,
  reportMetadata,
  ydoc,
  provider,
  editorUser,
  hasTiptapFlag,
  onSetShowStylePickerModal,
  onSetShowHeaderFooterModal,
  setPages,
  markdownToHtmlFn,
  reportStyle,
}) => {
  return (
    <View
      onLayout={onLayout}
      style={{
        width: '100%',
        maxWidth: isMobile ? undefined : 1100,
        alignSelf: 'center',
        marginBottom: isMobile ? 4 : 8,
        // GPU layer promotion to prevent paint flickering during scroll
        transform: [{ translateX: 0 }],
      }}
    >
      {/* Page Header */}
      <View style={[styles.pageHeader, { marginTop: pageIndex > 0 ? (isMobile ? 6 : 12) : 0 }]}>
        <TextInput
          style={[styles.pageTitleInput, { color: safeTheme.text, fontSize: isMobile ? 14 : 16 }]}
          value={page.title || ''}
          onChangeText={onTitleChange}
          placeholder="Page Title"
          placeholderTextColor="#999"
          editable={true}
          onFocus={onFocus}
        />
        <View style={styles.pageHeaderRight}>
          <Text style={[styles.pageInfo, isMobile && { fontSize: 10 }]}>
            {page.wordCount || 0} words  •  {personaText?.reportComposerSectionLabel || 'Page'} {pageIndex + 1} of {totalPages}
          </Text>
          {/* Per-page layout/style/header-footer toolbar removed — Style and
              Letterhead/Headers & Footers now live in the top toolbar. */}
        </View>
      </View>

      {/* Page Editor Container */}
      <View style={[
        styles.pageContainer,
        { backgroundColor: '#fff', borderColor: isActive ? safeTheme.primary : safeTheme.borderColor },
        isActive && styles.pageContainerActive
      ]}>
        {page.isGenerating ? (
          <View style={styles.generatingOverlay}>
            <ActivityIndicator size="large" color={safeTheme.primary} />
            <Text style={[styles.generatingText, { color: safeTheme.text }]}>
              Generating "{page.title}"...
            </Text>
            <Text style={[styles.generatingHint, { color: safeTheme.textSecondary }]}>
              AI is researching your data store and writing content
            </Text>
            {page.description && (
              <View style={styles.generatingDescBox}>
                <Text style={[styles.generatingDescLabel, { color: safeTheme.textSecondary }]}>Section outline:</Text>
                <Text style={[styles.generatingDesc, { color: safeTheme.text }]}>{page.description}</Text>
              </View>
            )}
          </View>
        ) : page.hasError ? (
          <View style={styles.errorOverlay}>
            <MaterialIcons name="error-outline" size={48} color="#ef4444" />
            <Text style={styles.errorTitle}>Failed to Generate</Text>
            <Text style={styles.errorMessage}>
              {page.errorMessage || 'An error occurred while generating this section'}
            </Text>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={() => {
                setPages(prev => prev.map(p =>
                  p.id === page.id
                    ? { ...p, isGenerating: true, hasError: false, errorMessage: null }
                    : p
                ));
              }}
            >
              <MaterialIcons name="refresh" size={18} color="#fff" />
              <Text style={styles.retryButtonText}>Retry</Text>
            </TouchableOpacity>
            <Text style={styles.errorHint}>Or you can manually write content in this section</Text>
          </View>
        ) : hasTiptapFlag && Platform.OS === 'web' ? (
          <TiptapEditor
            ref={editorRefCallback}
            content={markdownToHtmlFn(page.content || '')}
            onContentChange={onContentChange}
            onSelectionChange={onSelectionChange}
            onChartEdit={onChartEdit}
            placeholder={getEditorPlaceholder()}
            editable={true}
            theme={safeTheme}
            reportStyle={reportStyle}
            ydoc={ydoc}
            provider={provider}
            user={editorUser}
            showToolbar={false}
          />
        ) : (
          <TextInput
            style={styles.pageContent}
            value={page.content || ''}
            onChangeText={(text) => onContentChange(text)}
            multiline
            placeholder={getEditorPlaceholder()}
            placeholderTextColor="#aaa"
            onFocus={onFocus}
          />
        )}
      </View>
    </View>
  );
}, (prevProps, nextProps) => {
  // Custom comparison: only re-render when page-specific data changes
  if (prevProps.page.content !== nextProps.page.content) return false;
  if (prevProps.page.title !== nextProps.page.title) return false;
  if (prevProps.page.wordCount !== nextProps.page.wordCount) return false;
  if (prevProps.page.isGenerating !== nextProps.page.isGenerating) return false;
  if (prevProps.page.hasError !== nextProps.page.hasError) return false;
  if (prevProps.isActive !== nextProps.isActive) return false;
  if (prevProps.isMobile !== nextProps.isMobile) return false;
  if (prevProps.totalPages !== nextProps.totalPages) return false;
  if (prevProps.reportStyle !== nextProps.reportStyle) return false;
  return true;
});

/**
 * AI Report Generator - Section-based Content Management
 * Sections can span multiple physical pages when exported to PDF/DOCX
 */
const ReportComposer = ({
  visible,
  onClose,
  onClearReport,
  theme,
  userDeviceId,
  apiConfig,
  persona,
  personaText,
  initialReport = null,

  selectedFolders = [],
  folders = [],
  onOpenCredits, // Callback to open credits/upgrade modal
  onOpenTemplateUpload, // New prop
  uploadModalProps = null, // Props for internal upload modal
  enhancedProgress = null, // Upload progress for popup visibility inside modals
  onDismissUploadEntry = null, // Callback to remove a single upload entry from progress map
  mobileViewOnly = false, // Mobile web: view-only mode, no editing
  userType = 'free', // User plan type for export branding
}) => {
  const { useUploadedData } = useWorkspace();

  // Page management hooks
  const {
    pages,
    setPages,
    currentPageId,
    setCurrentPageId,
    addPage,
    deletePage,
    insertPage,
    reorderPages,
    updatePageContent,
    updatePageTitle,
    reportMetadata,
    updateReportMetadata,
    // New layout functions
    updatePageLayout,
    updateHeaderFooterConfig,
    updateReportStyle,
    updateDefaultLayout,
    resetToNew,
    togglePageHidden,
  } = useReportPages(initialReport);

  const { saveReport, autoSave, isSaving, lastSaved, saveReportToServer } = useReportPersistence();

  // Track previous visible state to detect false→true transitions
  const prevVisibleRef = useRef(false);

  // State
  const [showGoalSetting, setShowGoalSetting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [showReportList, setShowReportList] = useState(false);
  const [currentReportId, setCurrentReportId] = useState(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [reportGoal, setReportGoal] = useState(null);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editableTitle, setEditableTitle] = useState(reportMetadata.title || 'Untitled Report');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [pageToDelete, setPageToDelete] = useState(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [isSavingManual, setIsSavingManual] = useState(false); // Overlay during manual save
  const [authToken, setAuthToken] = useState(null);
  const [userEmail, setUserEmail] = useState(null);

  // Upload modal state - rendered internally to ensure proper layering
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);

  // Layout System Modal States - showLayoutPicker removed (layout set at page creation)
  const [showAddPageModal, setShowAddPageModal] = useState(false);
  const [showArrangeModal, setShowArrangeModal] = useState(false);
  const [showHeaderFooterModal, setShowHeaderFooterModal] = useState(false);
  const [showStylePickerModal, setShowStylePickerModal] = useState(false);
  const [showCloseConfirmModal, setShowCloseConfirmModal] = useState(false);
  const [showFolderDetailModal, setShowFolderDetailModal] = useState(false);
  const [addPageInsertIndex, setAddPageInsertIndex] = useState(null);

  // Page management state
  const [editingPageTitleId, setEditingPageTitleId] = useState(null);
  const [editingPageTitleText, setEditingPageTitleText] = useState('');

  // Edit page outline modal state
  const [editOutlinePage, setEditOutlinePage] = useState(null);

  // Mobile segmented control state - toggle between tools and AI chat
  const [mobileEditMode, setMobileEditMode] = useState('tools'); // 'tools' | 'chat'

  // Check if current user owns this item (for hiding share controls on shared items)
  const isItemOwner = initialReport?.user_id != null ? initialReport.user_id === userDeviceId : true;

  // AI Chat state
  const [chatInput, setChatInput] = useState('');
  const [isAiProcessing, setIsAiProcessing] = useState(false);
  const [showChartStudio, setShowChartStudio] = useState(false);
  const [showChartEditModal, setShowChartEditModal] = useState(false);
  const [editingChartConfig, setEditingChartConfig] = useState(null);
  const [editingChartNodePos, setEditingChartNodePos] = useState(null);
  const [showAIImageModal, setShowAIImageModal] = useState(false);
  const [selectedText, setSelectedText] = useState('');
  const [cursorPosition, setCursorPosition] = useState(0);
  const [hasSelection, setHasSelection] = useState(false);
  const [selectionRange, setSelectionRange] = useState({ from: 0, to: 0 });
  const [aiChatMessages, setAiChatMessages] = useState([]); // AI chat message history

  // Auto Update progress tracking
  const [isAutoUpdating, setIsAutoUpdating] = useState(false);
  const [autoUpdateProgress, setAutoUpdateProgress] = useState({ current: 0, total: 0 });
  const [showCollaborationPanel, setShowCollaborationPanel] = useState(false);
  const [showUpdateInstructionModal, setShowUpdateInstructionModal] = useState(false);
  const [isRefreshingOutline, setIsRefreshingOutline] = useState(false);

  // Edit scope is GONE as a UI concept — the agentic editor auto-detects intent
  // and target from chat (selected text is sent as selected_text). The constant
  // remains only because the legacy handleAiChatSubmit (now unreachable from the
  // UI; TODO(cleanup): delete with the rest of the legacy edit flow) reads it.
  const editScope = 'page';

  // Stable user object for collaboration - memoize to prevent reconnection loops
  const collabUser = useMemo(() => ({
    name: persona?.name || 'User ' + (userDeviceId?.slice(0, 4) || 'Anon'),
    email: userDeviceId,
    color: '#' + Math.floor(Math.random() * 16777215).toString(16)
  }), [persona?.name, userDeviceId]); // Only recreate when name/email changes

  // Stable user object for TiptapEditor instances (avoid re-renders from random colors)
  const editorUser = useMemo(() => ({
    name: persona?.name || 'User',
    color: collabUser.color
  }), [persona?.name, collabUser.color]);

  // Determine collaboration mode from sharing metadata
  const sharingInfo = initialReport?.sharing;
  const isOwner = sharingInfo?.is_owner ?? true;
  const isSharedForCollaboration = sharingInfo?.is_shared_for_collaboration ?? false;
  const userPermission = sharingInfo?.user_permission;

  const canCollaborate = isSharedForCollaboration &&
    (userPermission === 'owner' || userPermission === 'write');

  const isReadOnly = !isOwner && userPermission === 'read';

  // Collaboration Hook
  const collaboration = useCollaboration({
    docId: currentReportId ? `report-${currentReportId}` : null,
    user: collabUser,
    enabled: !!currentReportId && canCollaborate
  });

  const {
    ydoc,
    provider,
    collaborators,
    aiLockedBy,
    requestAiLock,
    releaseAiLock,
    refreshAiLock,
    // Granular locks
    documentLock,
    pageLocks,
    requestDocumentLock,
    releaseDocumentLock,
    requestPageLock,
    releasePageLock,
    isPageLocked,
    releaseAllLocks
  } = collaboration;

  // Check if AI is locked by someone else (legacy)
  const isAiLocked = canCollaborate && aiLockedBy && ydoc && aiLockedBy.clientId !== ydoc.clientID;
  const lockedByUser = aiLockedBy ? aiLockedBy.user : null;

  // Check if document is locked (for Update button)
  const isDocumentLocked = canCollaborate && documentLock && ydoc && documentLock.clientId !== ydoc.clientID;
  const documentLockedBy = documentLock ? documentLock.user : null;

  // Page panel view mode: 'thumbnail' or 'list'
  const [pagePanelViewMode, setPagePanelViewMode] = useState('thumbnail');

  // Load page panel view preference from AsyncStorage
  useEffect(() => {
    const loadViewPreference = async () => {
      try {
        const savedMode = await AsyncStorage.getItem('@page_panel_view_mode');
        if (savedMode && (savedMode === 'thumbnail' || savedMode === 'list')) {
          setPagePanelViewMode(savedMode);
        }
      } catch (err) {
        console.log('[REPORT_COMPOSER] Failed to load view preference:', err);
      }
    };
    loadViewPreference();
  }, []);

  // Toggle page panel view and save preference
  const togglePagePanelView = useCallback(async () => {
    const newMode = pagePanelViewMode === 'thumbnail' ? 'list' : 'thumbnail';
    setPagePanelViewMode(newMode);
    try {
      await AsyncStorage.setItem('@page_panel_view_mode', newMode);
    } catch (err) {
      console.log('[REPORT_COMPOSER] Failed to save view preference:', err);
    }
  }, [pagePanelViewMode]);

  // Refs
  const contentScrollRef = useRef(null);
  const editorRef = useRef(null);
  const loadReportRef = useRef(null);

  // Multi-page continuous scroll refs
  // Visible pages (excludes hidden) — used for Preview, Export
  const visiblePages = useMemo(() => pages.filter(p => !p.hidden), [pages]);

  const editorRefsMap = useRef({}); // {pageId: editorInstance} - stores refs to all TiptapEditor instances
  const pageLayoutsRef = useRef({}); // {pageId: {y, height}} - stores layout positions for scroll tracking
  const scrollTrackingEnabled = useRef(true); // Disable during programmatic scroll to prevent feedback loops
  const scrollDebounceTimer = useRef(null); // Debounce timer for scroll-based page tracking
  const lastScrollPositionRef = useRef({ scrollY: 0, viewportHeight: 0 }); // Latest scroll position for visible page sync
  const currentPageIdRef = useRef(null); // Ref mirror of currentPageId for stable callbacks
  currentPageIdRef.current = currentPageId; // Keep in sync for stable callbacks
  const actionBtnGuard = useRef(false); // Prevent parent onPress when action button clicked on web

  // Normalize profession - always returns 'general' (General Professional only)
  const normalizeProfession = (persona) => {
    return 'general';
  };

  // Get editor placeholder - generic for all users
  const getEditorPlaceholder = useCallback(() => {
    return 'Edit project or generate charts (e.g. "Show bar chart of sales")...';
  }, []);

  // Default theme — memoized to prevent re-render cascades from new object refs
  const defaultTheme = useMemo(() => ({
    background: '#ffffff',
    text: '#333333',
    primary: '#2196F3',
    surface: '#f5f5f5',
    borderColor: '#e0e0e0',
    isDark: false
  }), []);
  const safeTheme = theme || defaultTheme;

  // Reset all state when ReportComposer opens for a new report
  // Handles the null→null initialReport case where useEffect([initialReport]) won't fire
  useEffect(() => {
    const wasHidden = !prevVisibleRef.current;
    prevVisibleRef.current = visible;

    if (visible && wasHidden && initialReport === null) {
      // Opening composer for a brand new report — reset everything
      resetToNew();
      setCurrentReportId(null);
      setEditableTitle('Untitled Report');
      setReportGoal(null);
      setShowGoalSetting(true);
      setAiChatMessages([]);
    }
  }, [visible, initialReport, resetToNew]);

  // Handle initialReport prop changes (when loading from App.js)
  useEffect(() => {
    if (initialReport && initialReport.id) {
      setCurrentReportId(initialReport.id);
      setEditableTitle(initialReport.title || 'Untitled Report');
      if (initialReport.goal) {
        setReportGoal({ purpose: initialReport.goal });
      }
      // Don't show goal setting when loading an existing report
      setShowGoalSetting(false);

      // Bulk pre-cache images if pages are available
      if (initialReport.pages?.length > 0) {
        _preCachePageImages(initialReport.pages);
      }
    } else if (initialReport === null) {
      // Reset internal state when initialReport becomes null (Create New Report)
      setCurrentReportId(null);
      setEditableTitle('Untitled Report');
      setReportGoal(null);
      setShowGoalSetting(true);
    }
  }, [initialReport]);

  // Show goal setting on first open (only for new reports)
  useEffect(() => {
    if (visible && !reportGoal && pages.length === 1 && !pages[0].content && !isLoadingReport && !currentReportId && !initialReport) {
      setShowGoalSetting(true);
    }
  }, [visible, reportGoal, pages, isLoadingReport, currentReportId, initialReport]);

  // Load Auth Data
  useEffect(() => {
    const loadAuthData = async () => {
      try {
        const token = await authService.getToken();
        const email = await authService.getCurrentUserEmail();
        setAuthToken(token);
        setUserEmail(email);
      } catch (err) {
        console.warn('Failed to load auth data:', err);
      }
    };
    loadAuthData();
  }, []);

  // Auto-save
  useEffect(() => {
    if (pages.some(p => p.hasUnsavedChanges)) {
      const timeoutId = setTimeout(() => {
        autoSave({ pages, reportMetadata, reportGoal, folderIds: selectedFolders.map(f => f.id || f) });
      }, 3000);
      return () => clearTimeout(timeoutId);
    }
  }, [pages, reportMetadata, reportGoal, autoSave]);

  // Handle AI page content generation event (from Add Page modal)
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const handleGeneratePageContent = async (event) => {
      const { pageId, outline, specialInstructions, generateImages, layout } = event.detail;

      console.log('[REPORT_COMPOSER] AI Page Generation triggered:', { pageId, outline, layout });

      try {
        const token = await AsyncStorage.getItem('@auth_token');
        if (!token) {
          console.error('[REPORT_COMPOSER] No auth token for AI generation');
          // Update page to remove generating state
          updatePageContent(pageId, '<p>Authentication error. Please log in and try again.</p>');
          return;
        }

        // Use the generate-section API for new pages (not ai-edit)
        const response = await fetch(`${apiConfig.API_URL}/composer/generate-section`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            section: {
              title: outline,
              description: specialInstructions || outline,
              search_query: outline
            },
            goal: reportGoal || { purpose: '' },
            report_type: reportMetadata?.format || 'document',
            folder_ids: useUploadedData && selectedFolders?.length > 0 ? selectedFolders.map(f => f.id || f) : [],
            special_instructions: specialInstructions || null,
            section_index: pages.findIndex(p => p.id === pageId),
            total_sections: pages.length + 1,
            // Pass layout preference
            layout: layout !== 'ai_auto' ? layout : null,
            generate_images: generateImages || false,
          })
        });

        if (response.status === 402) {
          const errData = await response.json().catch(() => ({}));
          handleCreditError(errData);
          updatePageContent(pageId, '<p>Insufficient credits. Please purchase more credits to continue.</p>');
          return;
        }

        if (response.ok) {
          const data = await response.json();

          if (data.success && data.page && data.page.content) {
            console.log('[REPORT_COMPOSER] AI generated content for new page:', pageId);

            let finalContent = data.page.content;
            const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
            const matches = [...finalContent.matchAll(chartConfigRegex)];

            if (matches.length > 0) {
              for (const match of matches) {
                try {
                  const configJson = match[1];
                  const chartConfig = JSON.parse(configJson);
                  const dataUrl = await renderChartToImage(chartConfig);
                  let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
                  if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                    const labels = chartConfig.data.labels;
                    const summary = chartConfig.data.datasets.map(ds => {
                      return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                    }).join('; ');
                    altText += ` | Data: ${summary}`;
                  }
                  const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                  finalContent = finalContent.replace(match[0], imgHtml);
                } catch (err) {
                  console.error('Failed to render chart:', err);
                  finalContent = finalContent.replace(match[0], '<!-- Chart rendering failed -->');
                }
              }
            }

            // Update page content and remove generating state
            updatePageContent(pageId, finalContent);

            // Update page title if provided by API
            if (data.page.title) {
              updatePageTitle(pageId, data.page.title);
            }

            // Add chat message about generation
            setAiChatMessages(prev => [...prev.slice(-9), {
              id: chatMsgUid(),
              text: `Generated content for new page: "${data.page.title || outline.slice(0, 50)}..."`,
              timestamp: new Date(),
              actionType: 'create_new'
            }]);
          } else {
            console.warn('[REPORT_COMPOSER] AI generation failed:', data.message);
            updatePageContent(pageId, `<p>Content generation failed: ${data.message || 'Unknown error'}</p>`);
          }
        } else {
          console.error('[REPORT_COMPOSER] AI API error:', response.status);
          updatePageContent(pageId, '<p>Failed to generate content. Please try again.</p>');
        }
      } catch (error) {
        console.error('[REPORT_COMPOSER] AI generation error:', error);
        updatePageContent(pageId, `<p>Error generating content: ${error.message}</p>`);
      }
    };

    window.addEventListener('report:generatePageContent', handleGeneratePageContent);
    return () => window.removeEventListener('report:generatePageContent', handleGeneratePageContent);
  }, [apiConfig, reportGoal, reportMetadata, userDeviceId, selectedFolders, updatePageContent, updatePageTitle, pages]);

  // Handle goal set
  const handleGoalSet = useCallback((goal) => {
    setReportGoal(goal);
    updateReportMetadata({
      title: goal.purpose?.slice(0, 50) || 'AI Report',
      overall_goal: goal.purpose
    });
    setEditableTitle(goal.purpose?.slice(0, 50) || 'AI Report');
  }, [updateReportMetadata]);

  // Handle opening add page modal
  const handleOpenAddPageModal = useCallback((insertIndex = pages.length) => {
    setAddPageInsertIndex(insertIndex);
    setShowAddPageModal(true);
  }, [pages.length]);

  // Handle creating a new page from the modal
  const handleCreatePage = useCallback(async (pageData) => {
    const { layout, content, title, isAiGenerated, mode, outline, specialInstructions, generateImages } = pageData;

    // Determine layout - use 'single_column' as default for ai_auto before actual generation
    const finalLayout = (layout === 'ai_auto') ? 'single_column' : (layout || reportMetadata.defaultLayout || 'single_column');

    // Generate page title from outline or use default
    const pageTitle = title || (outline ? outline.slice(0, 50) + (outline.length > 50 ? '...' : '') : `Page ${(addPageInsertIndex || pages.length) + 1}`);

    if (mode === 'blank') {
      // Create blank page immediately
      // For single column, use empty content (TipTap default)
      // For multi-column layouts, generate HTML structure with placeholders
      let initialContent = '';
      if (finalLayout !== 'single_column' && finalLayout !== 'ai_auto') {
        initialContent = generateLayoutHTML(finalLayout, {});
      }

      const newPageId = insertPage(addPageInsertIndex, {
        title: pageTitle,
        content: initialContent,
        layout: finalLayout,
        outline: outline || '',
      });
      console.log('[REPORT_COMPOSER] Created blank page with layout:', finalLayout, newPageId);

      setShowAddPageModal(false);
      setAddPageInsertIndex(null);

      // Scroll to the new page after it renders
      setTimeout(() => {
        setCurrentPageId(newPageId);
        if (contentScrollRef.current && pageLayoutsRef.current[newPageId]) {
          scrollTrackingEnabled.current = false;
          contentScrollRef.current.scrollTo({ y: pageLayoutsRef.current[newPageId].y, animated: true });
          setTimeout(() => { scrollTrackingEnabled.current = true; }, 600);
        }
      }, 400);

      return newPageId;
    }

    if (mode === 'ai') {
      // Store outline in memory and trigger AI generation
      const newPageId = insertPage(addPageInsertIndex, {
        title: pageTitle,
        content: '', // Will be filled by AI
        layout: finalLayout,
        outline: outline || '',
        specialInstructions: specialInstructions || '',
        isGenerating: true, // Mark as generating
      });

      console.log('[REPORT_COMPOSER] Created AI page placeholder:', newPageId, 'with outline:', outline);

      setShowAddPageModal(false);
      setAddPageInsertIndex(null);

      // Navigate to the new page and scroll to it
      setCurrentPageId(newPageId);
      setTimeout(() => {
        if (contentScrollRef.current && pageLayoutsRef.current[newPageId]) {
          scrollTrackingEnabled.current = false;
          contentScrollRef.current.scrollTo({ y: pageLayoutsRef.current[newPageId].y, animated: true });
          setTimeout(() => { scrollTrackingEnabled.current = true; }, 600);
        }
      }, 400);

      // Trigger AI generation for this page using the AI edit flow
      setTimeout(() => {
        // Use the AI assistant to generate content based on outline
        const aiPrompt = `Generate content for this page based on the outline:\n\n${outline}${specialInstructions ? `\n\nSpecial Instructions: ${specialInstructions}` : ''}`;

        // Call AI generation - this will use the existing AI chat/edit flow
        if (typeof window !== 'undefined' && window.dispatchEvent) {
          window.dispatchEvent(new CustomEvent('report:generatePageContent', {
            detail: {
              pageId: newPageId,
              outline,
              specialInstructions,
              generateImages,
              layout: finalLayout,
            }
          }));
        }
      }, 100);

      return newPageId;
    }

    // Fallback - just create the page with provided content
    const newPageId = insertPage(addPageInsertIndex, {
      title: pageTitle,
      content: content || '',
      layout: finalLayout,
    });

    // If AI generated content, mark it
    if (isAiGenerated && content) {
      console.log('[REPORT_COMPOSER] Created AI-generated page:', newPageId);
    }

    setShowAddPageModal(false);
    setAddPageInsertIndex(null);

    // Scroll to the new page after it renders
    setTimeout(() => {
      setCurrentPageId(newPageId);
      if (contentScrollRef.current && pageLayoutsRef.current[newPageId]) {
        scrollTrackingEnabled.current = false;
        contentScrollRef.current.scrollTo({ y: pageLayoutsRef.current[newPageId].y, animated: true });
        setTimeout(() => { scrollTrackingEnabled.current = true; }, 600);
      }
    }, 400);

    return newPageId;
  }, [insertPage, addPageInsertIndex, reportMetadata.defaultLayout, pages.length, setCurrentPageId]);

  // Handle header/footer save
  const handleHeaderFooterSave = useCallback((config) => {
    updateHeaderFooterConfig(config);
    setShowHeaderFooterModal(false);
  }, [updateHeaderFooterConfig]);

  // Handle style change
  const handleStyleChange = useCallback((styleId) => {
    updateReportStyle(styleId);
    setShowStylePickerModal(false);
  }, [updateReportStyle]);

  // 🆕 PROGRESSIVE RENDERING: Handle generation start - create placeholder pages
  const handleGenerationStart = useCallback((startData) => {
    console.log('🚀 [PROGRESSIVE] Generation started with', startData.totalSections, 'placeholder pages');

    const placeholderPages = startData.placeholderPages.map((page, index) => ({
      id: `page_${Date.now()}_${index}`,
      order: page.order || (index + 1),
      title: page.title || `Page ${index + 1}`,
      description: page.description || '',
      content: '',
      wordCount: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: false,
      isGenerating: true, // 🆕 Loading state
      hasError: false,
      errorMessage: null,
      sectionId: page.sectionId,
    }));

    setPages(placeholderPages);

    if (placeholderPages.length > 0) {
      setCurrentPageId(placeholderPages[0].id);
    }

    // Hide goal setting modal so user sees pages immediately
    setShowGoalSetting(false);

    // Update report metadata
    if (startData.reportStyle) {
      updateReportStyle(startData.reportStyle);
    }
  }, [setPages, setCurrentPageId, updateReportStyle]);

  // 🆕 PROGRESSIVE RENDERING: Handle batch completion - update pages incrementally
  const handlePageBatchGenerated = useCallback(async (batchData) => {
    console.log(`📦 [PROGRESSIVE] Batch ${batchData.batchIndex + 1}/${batchData.totalBatches} received with ${batchData.pages.length} pages`);

    // Process each page in the batch
    for (const incomingPage of batchData.pages) {
      let content = incomingPage.content || '';

      // Process chart configs if present
      const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
      const matches = [...content.matchAll(chartConfigRegex)];

      if (matches.length > 0) {
        console.log(`📊 [PROGRESSIVE] Processing ${matches.length} charts in page ${incomingPage.order}`);

        for (const match of matches) {
          try {
            const configJson = match[1];
            const chartConfig = JSON.parse(configJson);
            const dataUrl = await renderChartToImage(chartConfig);

            let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
            if (chartConfig.data?.labels && chartConfig.data?.datasets) {
              const labels = chartConfig.data.labels;
              const summary = chartConfig.data.datasets.map(ds => {
                return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
              }).join('; ');
              altText += ` | Data: ${summary}`;
            }

            const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
            content = content.replace(match[0], imgHtml);
          } catch (err) {
            console.error('Failed to render chart:', err);
            content = content.replace(match[0], '<!-- Chart rendering failed -->');
          }
        }
      }

      // Update the corresponding placeholder page
      setPages(currentPages => {
        return currentPages.map(page => {
          // Match by order (sectionIndex + 1)
          if (page.order === incomingPage.order || page.sectionId === incomingPage.sectionId) {
            return {
              ...page,
              title: incomingPage.title || page.title,
              content: content,
              wordCount: content.trim().split(/\s+/).filter(w => w.length > 0).length,
              updated_at: new Date().toISOString(),
              isGenerating: false,
              hasError: incomingPage.hasError || false,
              errorMessage: incomingPage.errorMessage || null,
              citations: incomingPage.citations || [],
            };
          }
          return page;
        });
      });
    }

    console.log(`✅ [PROGRESSIVE] Updated ${batchData.completedSections}/${batchData.totalSections} pages`);
  }, [setPages]);

  // 🆕 PROGRESSIVE RENDERING: Handle page error
  const handlePageError = useCallback((errorData) => {
    console.error(`❌ [PROGRESSIVE] Page ${errorData.sectionIndex + 1} failed:`, errorData.error);

    setPages(currentPages => {
      return currentPages.map(page => {
        if (page.order === (errorData.sectionIndex + 1) || page.sectionId === errorData.sectionId) {
          return {
            ...page,
            isGenerating: false,
            hasError: true,
            errorMessage: errorData.error,
          };
        }
        return page;
      });
    });
  }, [setPages]);

  // Handle report generated from vault (final callback - kept for compatibility)
  // With progressive rendering, pages are already updated incrementally.
  // This callback now just handles the final state and closes the modal.
  const handleReportGenerated = useCallback(async (reportData) => {
    console.log('📄 [FINAL] Report generation complete:', reportData.pages?.length, 'pages');

    // Check if we already have pages from progressive rendering
    // If pages exist and have content, don't overwrite them
    const existingPagesHaveContent = pages.some(p => p.content && p.content.length > 0);

    if (existingPagesHaveContent) {
      console.log('📄 [FINAL] Pages already populated via progressive rendering, skipping bulk update');
      // Just ensure modal is closed
      setShowGoalSetting(false);
      return;
    }

    // Fallback: If progressive rendering didn't work, process pages the old way
    if (reportData.pages && reportData.pages.length > 0) {
      console.log('📄 [FINAL] Using fallback bulk page update');
      const sortedPages = [...reportData.pages].sort((a, b) => a.order - b.order);

      // Process pages to render any charts
      const processedPages = await Promise.all(sortedPages.map(async (page, index) => {
        let content = page.content || '';

        // Check for chart configs
        const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
        const matches = [...content.matchAll(chartConfigRegex)];

        if (matches.length > 0) {
          console.log(`📊 [REPORT_COMPOSER] Found ${matches.length} charts in page ${index + 1}`);

          // Replace each match with rendered image
          for (const match of matches) {
            try {
              const configJson = match[1];
              const chartConfig = JSON.parse(configJson);

              const dataUrl = await renderChartToImage(chartConfig);

              // Create rich alt text with data summary
              let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
              if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                const labels = chartConfig.data.labels;
                const summary = chartConfig.data.datasets.map(ds => {
                  return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                }).join('; ');
                altText += ` | Data: ${summary}`;
              }

              const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;

              content = content.replace(match[0], imgHtml);
            } catch (err) {
              console.error('Failed to render chart from config:', err);
              // Fallback: remove the config block to hide the raw JSON
              content = content.replace(match[0], '<!-- Chart rendering failed -->');
            }
          }
        }

        return {
          id: `page_${Date.now()}_${index}`,
          order: page.order || (index + 1),
          title: page.title || `Page ${index + 1}`,
          content: content, // Use processed content
          wordCount: content.trim().split(/\s+/).filter(w => w.length > 0).length,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        };
      }));

      setPages(processedPages);

      // Bulk pre-cache S3 images in AI-generated pages (fire-and-forget)
      _preCachePageImages(processedPages);

      if (processedPages.length > 0) {
        setCurrentPageId(processedPages[0].id);
      }
    }

    setShowGoalSetting(false);
  }, [pages, setPages, setCurrentPageId]);

  // Get current page
  const currentPage = pages.find(p => p.id === currentPageId) || pages[0];
  const currentPageIndex = pages.findIndex(p => p.id === currentPageId);

  // Handle content change with auto-split on word limit
  const handleContentChange = useCallback((pageId, newContent) => {
    const wordCount = newContent.trim().split(/\s+/).filter(w => w.length > 0).length;

    if (wordCount > SECTION_WORD_LIMIT) {
      // Find a good split point (last paragraph break before limit)
      const words = newContent.split(/\s+/);
      const contentBeforeLimit = words.slice(0, SECTION_WORD_LIMIT).join(' ');

      // Find last paragraph break (double newline or period followed by newline)
      const lastParagraphBreak = Math.max(
        contentBeforeLimit.lastIndexOf('\n\n'),
        contentBeforeLimit.lastIndexOf('.\n'),
        contentBeforeLimit.lastIndexOf('. ')
      );

      let splitPoint = lastParagraphBreak > SECTION_WORD_LIMIT * 0.5
        ? lastParagraphBreak + 1
        : contentBeforeLimit.length;

      const contentForCurrent = newContent.substring(0, splitPoint).trim();
      const overflowContent = newContent.substring(splitPoint).trim();

      if (overflowContent.length > 0) {
        // Update current page with content up to split
        updatePageContent(pageId, contentForCurrent);

        // Get current page info
        const currentIdx = pages.findIndex(p => p.id === pageId);
        const currentPage = pages[currentIdx];
        if (!currentPage) {
          // Page not found (stale closure) — just do a normal update
          updatePageContent(pageId, newContent);
          return;
        }

        // Create continuation section
        const continuationTitle = `${currentPage.title} (continued)`;
        const newPageId = insertPage(currentIdx + 1);

        // Set the new page content and title after a brief delay
        setTimeout(() => {
          updatePageContent(newPageId, overflowContent);
          updatePageTitle(newPageId, continuationTitle);
          setCurrentPageId(newPageId);

          Alert.alert(
            'Section Split',
            `Content exceeded ${SECTION_WORD_LIMIT} words. A continuation section "${continuationTitle}" has been created.`,
            [{ text: 'OK' }]
          );
        }, 100);

        return;
      }
    }

    // Normal update if under limit
    updatePageContent(pageId, newContent);
  }, [pages, updatePageContent, insertPage, updatePageTitle, setCurrentPageId]);

  // Page reorder functions
  const handleMovePageUp = useCallback((index) => {
    if (index <= 0) return;
    reorderPages(index, index - 1);
  }, [reorderPages]);

  const handleMovePageDown = useCallback((index) => {
    if (index >= pages.length - 1) return;
    reorderPages(index, index + 1);
  }, [reorderPages, pages.length]);

  // Selecting a page
  const handleSelectPage = useCallback((pageId) => {
    setCurrentPageId(pageId);

    // Continuous scroll: scroll to the selected page
    if (contentScrollRef.current && pageLayoutsRef.current[pageId]) {
      scrollTrackingEnabled.current = false; // Disable scroll tracking during programmatic scroll
      const targetY = pageLayoutsRef.current[pageId].y;
      contentScrollRef.current.scrollTo({ y: targetY, animated: true });
      // Re-enable scroll tracking after animation
      setTimeout(() => { scrollTrackingEnabled.current = true; }, 600);
    }
  }, []);

  // Sync editorRef.current to always point to the active page's editor
  useEffect(() => {
    if (editorRefsMap.current[currentPageId]) {
      editorRef.current = editorRefsMap.current[currentPageId];
    }
  }, [currentPageId]);

  // Handle scroll to track which page is visible (desktop continuous scroll) — debounced
  // Helper: determine the most visible page from stored scroll position
  const getVisiblePageId = useCallback(() => {
    const { scrollY, viewportHeight } = lastScrollPositionRef.current;
    if (!viewportHeight) return null;
    const viewportCenter = scrollY + viewportHeight / 3;
    let bestPageId = null;
    let bestDistance = Infinity;
    for (const [pageId, layout] of Object.entries(pageLayoutsRef.current)) {
      const pageCenter = layout.y + layout.height / 2;
      const distance = Math.abs(viewportCenter - pageCenter);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestPageId = pageId;
      }
    }
    return bestPageId;
  }, []);

  // Uses currentPageIdRef instead of currentPageId to keep stable reference (no re-creation on page change)
  const handleContentScroll = useCallback((event) => {
    // Always store the latest scroll position immediately (no debounce)
    lastScrollPositionRef.current = {
      scrollY: event.nativeEvent.contentOffset.y,
      viewportHeight: event.nativeEvent.layoutMeasurement.height,
    };
    if (!scrollTrackingEnabled.current) return;

    const scrollY = event.nativeEvent.contentOffset.y;
    const viewportHeight = event.nativeEvent.layoutMeasurement.height;
    const viewportCenter = scrollY + viewportHeight / 3; // Use upper-third as focus point

    // Debounce: defer state update to avoid rapid re-renders during scroll
    if (scrollDebounceTimer.current) clearTimeout(scrollDebounceTimer.current);
    scrollDebounceTimer.current = setTimeout(() => {
      let bestPageId = null;
      let bestDistance = Infinity;

      for (const [pageId, layout] of Object.entries(pageLayoutsRef.current)) {
        const pageCenter = layout.y + layout.height / 2;
        const distance = Math.abs(viewportCenter - pageCenter);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestPageId = pageId;
        }
      }

      if (bestPageId && bestPageId !== currentPageIdRef.current) {
        setCurrentPageId(bestPageId);
        if (editorRefsMap.current[bestPageId]) {
          editorRef.current = editorRefsMap.current[bestPageId];
        }
      }
    }, 250);
  }, []); // Stable — uses refs for latest state

  const handleDeletePage = useCallback((pageId) => {
    console.log('[REPORT_COMPOSER] Delete icon pressed', { pageId, pageCount: pages.length });
    if (pages.length <= 1) {
      Alert.alert('Cannot Delete', 'You must have at least one section.');
      return;
    }

    // Show custom delete confirmation modal
    setPageToDelete(pageId);
    setShowDeleteModal(true);
  }, [pages.length]);

  const confirmDeletePage = useCallback(() => {
    if (pageToDelete) {
      console.log('[REPORT_COMPOSER] Confirmed delete, calling deletePage:', pageToDelete);
      // Clean up refs for deleted page
      delete editorRefsMap.current[pageToDelete];
      delete pageLayoutsRef.current[pageToDelete];
      delete stableCallbacksRef.current[pageToDelete];
      deletePage(pageToDelete);
    }
    setShowDeleteModal(false);
    setPageToDelete(null);
  }, [pageToDelete, deletePage]);

  const cancelDeletePage = useCallback(() => {
    setShowDeleteModal(false);
    setPageToDelete(null);
  }, []);

  const startEditingPageTitle = useCallback((page) => {
    setEditingPageTitleId(page.id);
    setEditingPageTitleText(page.title);
  }, []);

  const savePageTitle = useCallback(() => {
    if (editingPageTitleId && editingPageTitleText.trim()) {
      updatePageTitle(editingPageTitleId, editingPageTitleText);
    }
    setEditingPageTitleId(null);
    setEditingPageTitleText('');
  }, [editingPageTitleId, editingPageTitleText, updatePageTitle]);

  const handleSavePageOutline = useCallback(({ title, outline }) => {
    if (editOutlinePage) {
      setPages(prev => prev.map(p =>
        p.id === editOutlinePage.id
          ? { ...p, title: title || p.title, outline, updated_at: new Date().toISOString(), hasUnsavedChanges: true }
          : p
      ));
    }
    setEditOutlinePage(null);
  }, [editOutlinePage, setPages]);

  // Helper to extract base64 images and embeds, replace with placeholders for AI
  const extractImages = (html) => {
    if (!html) return { processedHtml: '', imageMap: {}, embedMap: {} };
    const imageMap = {};
    const embedMap = {};
    let imageCounter = 0;
    let embedCounter = 0;

    // First extract embeds (div elements with data-embed-type attribute)
    // This regex captures the entire embed div and its attributes
    let processedHtml = html.replace(
      /<div[^>]*data-embed-type="([^"]*)"[^>]*data-embed-src="([^"]*)"[^>]*data-embed-provider="([^"]*)"[^>]*data-embed-title="([^"]*)"[^>]*>[\s\S]*?<\/div>/g,
      (match, embedType, src, provider, title) => {
        const id = `UserEmbed_${Date.now()}_${embedCounter++}`;
        embedMap[id] = {
          fullHtml: match,
          embedType,
          src,
          provider,
          title: title || 'Embedded Content'
        };
        // Replace with placeholder that AI understands but won't modify
        return `<!-- {{${id}}} [EMBED: ${provider || embedType} - "${title || 'Untitled'}"] DO NOT MODIFY -->`;
      }
    );

    // Also handle embed node wrapper format from TipTap
    processedHtml = processedHtml.replace(
      /<div[^>]*class="[^"]*embed-node-wrapper[^"]*"[^>]*>[\s\S]*?<div[^>]*data-embed-type="([^"]*)"[\s\S]*?<\/div>[\s\S]*?<\/div>/g,
      (match, embedType) => {
        const id = `UserEmbed_${Date.now()}_${embedCounter++}`;
        embedMap[id] = {
          fullHtml: match,
          embedType: embedType || 'embed'
        };
        return `<!-- {{${id}}} [EMBED: ${embedType}] DO NOT MODIFY -->`;
      }
    );

    // Extract chart configs (data-chart-config attributes) to reduce token count
    let chartConfigCounter = 0;
    const chartConfigMap = {};
    processedHtml = processedHtml.replace(/data-chart-config="([^"]*)"/g, (match, config) => {
      const id = `ChartConfig_${Date.now()}_${chartConfigCounter++}`;
      chartConfigMap[id] = config;
      return `data-chart-config="{{${id}}}"`;
    });

    // Extract chart image srcs separately (AI-editable, not user media)
    processedHtml = processedHtml.replace(
      /<img\b[^>]*>/gi,
      (imgTag) => {
        if (imgTag.includes('ChartConfig_') || imgTag.includes('data-chart-config')) {
          return imgTag.replace(/src=["']((?:data:image\/|https?:\/\/|file:\/\/|blob:|\/)[^"']+)["']/, (m, src) => {
            const id = `ChartImage_${Date.now()}_${imageCounter++}`;
            imageMap[id] = src;
            return `src="{{${id}}}"`;
          });
        }
        return imgTag;
      }
    );

    // Then extract remaining image srcs (user-uploaded, protected)
    processedHtml = processedHtml.replace(/src=["']((?:data:image\/|https?:\/\/|file:\/\/|blob:|\/)[^"']+)["']/g, (match, src) => {
      const id = `UserImage_${Date.now()}_${imageCounter++}`;
      imageMap[id] = src;
      return `src="{{${id}}}"`;
    });

    return { processedHtml, imageMap, embedMap, chartConfigMap };
  };

  // Insert AI Generated Image
  const handleInsertAIImage = useCallback(async (imageUrl, description) => {
    if (editorRef.current && editorRef.current.insertContent) {
      // Pre-cache the image as blob URL for reliable rendering
      // This ensures ImageResizeComponent finds it in cache immediately (sync check)
      if (imageUrl && imageUrl.startsWith('http')) {
        try {
          await globalImageCache.fetchAndCache(imageUrl);
          console.log('✅ [REPORT] Pre-cached AI image for reliable display');
        } catch (e) {
          console.warn('⚠️ [REPORT] Pre-cache failed, image will load via direct URL:', e.message);
        }
      }

      // Use Tiptap JSON node insertion instead of raw HTML for reliable parsing
      // This avoids HTML parsing issues that can lose the src attribute
      const sanitizedAlt = (description || 'AI Image').replace(/["<>]/g, '');
      editorRef.current.insertContent({
        type: 'image',
        attrs: {
          src: imageUrl,
          alt: sanitizedAlt,
          width: '50%',
        }
      });
      editorRef.current.insertContent('<p></p>'); // Add newline after
    } else {
      // Fallback
      updatePageContent(currentPageId, (currentPage?.content || '') + `\n\n![${description || 'AI Image'}](${imageUrl})`);
    }
  }, [updatePageContent, currentPageId, currentPage]);

  // Helper to restore images and embeds from placeholders
  const restoreImages = (html, imageMap, embedMap = {}, chartConfigMap = {}) => {
    if (!html) return '';
    let restoredHtml = html;

    // Restore embeds first (before images since embed placeholders are in comments)
    Object.keys(embedMap).forEach(id => {
      // Match the comment placeholder format: <!-- {{ID}} [EMBED: ...] DO NOT MODIFY -->
      const embedPlaceholderRegex = new RegExp(`<!-- \\{\\{${id}\\}\\}[^>]*-->`, 'g');
      restoredHtml = restoredHtml.replace(embedPlaceholderRegex, embedMap[id].fullHtml);
    });

    // Restore chart configs
    Object.keys(chartConfigMap).forEach(id => {
      const placeholderRegex = new RegExp(`{{${id}}}`, 'g');
      restoredHtml = restoredHtml.replace(placeholderRegex, chartConfigMap[id]);
    });

    // Restore images
    Object.keys(imageMap).forEach(id => {
      // Regex to match the placeholder, allowing for potential AI formatting changes
      const placeholderRegex = new RegExp(`{{${id}}}`, 'g');
      restoredHtml = restoredHtml.replace(placeholderRegex, imageMap[id]);
    });

    // SAFETY NET: Re-inject any user images/embeds that AI dropped entirely from the output
    Object.keys(imageMap).forEach(id => {
      if (!id.startsWith('UserImage_')) return;
      // Check if the original src was restored somewhere in the HTML
      const src = imageMap[id];
      if (src && !restoredHtml.includes(src)) {
        console.warn(`⚠️ [RESTORE] User image ${id} was dropped by AI — re-injecting`);
        restoredHtml += `\n<p><img src="${src}" style="max-width: 100%;" /></p>`;
      }
    });
    Object.keys(embedMap).forEach(id => {
      if (!id.startsWith('UserEmbed_')) return;
      const embed = embedMap[id];
      if (embed?.fullHtml && !restoredHtml.includes(embed.fullHtml)) {
        console.warn(`⚠️ [RESTORE] User embed ${id} was dropped by AI — re-injecting`);
        restoredHtml += `\n${embed.fullHtml}`;
      }
    });

    return restoredHtml;
  };

  // AI Chat submit - handles 3 modes: selection, insertion, full page
  const handleAiChatSubmit = useCallback(async () => {
    if (!chatInput.trim() || isAiProcessing) return;

    // Sync: ensure we target the actually visible page from scroll position
    let effectivePageId = currentPageId;
    let effectivePage = currentPage;
    const visiblePageId = getVisiblePageId();
    if (visiblePageId && visiblePageId !== currentPageIdRef.current) {
      effectivePageId = visiblePageId;
      effectivePage = pages.find(p => p.id === visiblePageId) || currentPage;
      setCurrentPageId(visiblePageId);
      currentPageIdRef.current = visiblePageId;
      if (editorRefsMap.current[visiblePageId]) {
        editorRef.current = editorRefsMap.current[visiblePageId];
      }
    }

    setIsAiProcessing(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      // HANDLE "ALL PAGES" MODE (Smart Orchestrate-All - Single API call)
      if (editScope === 'all') {
        // Check if document is locked
        if (isDocumentLocked) {
          Alert.alert(
            'Document Locked',
            `This document is currently being updated by ${documentLockedBy?.name || 'another user'}. Please wait until they finish.`
          );
          setIsAiProcessing(false);
          return;
        }

        // Acquire document lock first
        const lockAcquired = requestDocumentLock();
        if (!lockAcquired) {
          Alert.alert('Lock Failed', 'Could not acquire document lock. Please try again.');
          setIsAiProcessing(false);
          return;
        }

        setIsAutoUpdating(true);
        setIsAiProcessing(true);
        setAutoUpdateProgress({ current: 0, total: 0 });

        const folderIds = useUploadedData && selectedFolders?.length > 0 ? (selectedFolders || []).map(f => typeof f === 'object' ? (f.id || f) : f) : [];
        if (!folderIds || folderIds.length === 0) {
          console.warn('⚠️ [EDIT_ALL] No folder_ids passed to ai-edit-all — SaaS and vault data retrieval may be limited');
        }
        const instruction = chatInput;
        // Add user message to chat history
        setAiChatMessages(prev => [...prev.slice(-9), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
        setChatInput('');

        try {
          // Filter out hidden pages for AI processing
          const aiPages = pages.filter(p => !p.hidden);
          const aiIndexToFullIndex = aiPages.map(p => pages.indexOf(p));

          // Build lightweight page summaries
          const pagesSummary = buildPagesSummary(aiPages);
          const currentIndex = aiPages.findIndex(p => p.id === effectivePageId);

          // Add AI entry message
          setAiChatMessages(prev => [...prev.slice(-9), {
            id: chatMsgUid(),
            text: `Analyzing ${aiPages.length} pages and planning edits...`,
            timestamp: new Date(),
            actionType: 'edit'
          }]);

          // Extract images/embeds BEFORE sending to backend so AI sees {{UserImage_xxx}} placeholders
          const pageExtractionMaps = {};
          const extractedPages = aiPages.map(p => {
            const extraction = extractImages(p.content || '');
            pageExtractionMaps[p.id] = extraction;
            return {
              content: extraction.processedHtml,
              id: p.id,
              title: p.title,
            };
          });

          // Single API call to ai-edit-all (streaming keepalive response)
          const editAllResponse = await fetch(`${apiConfig.API_URL}/composer/ai-edit-all`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              instruction: instruction,
              pages_summary: pagesSummary,
              full_pages: extractedPages,
              current_page_index: currentIndex >= 0 ? currentIndex : 0,
              folder_ids: folderIds,
              goal: reportGoal?.purpose || '',
              report_type: reportGoal?.documentType || 'report',
              is_update_all: false,
            }),
          });

          if (!editAllResponse.ok) {
            const errorData = await editAllResponse.json().catch(() => ({}));
            if (editAllResponse.status === 402) {
              const message = errorData.detail?.message || errorData.message || 'Insufficient credits.';
              authService.notifyCreditRequired(message);
              setIsAutoUpdating(false);
              setIsAiProcessing(false);
              releaseDocumentLock();
              return;
            }
            throw new Error(errorData.detail || errorData.message || 'Failed to process all pages');
          }

          // Response is a streaming keepalive — read full text then parse JSON
          const editAllText = await editAllResponse.text();
          const trimmedText = editAllText.trim();
          if (!trimmedText) {
            throw new Error('Empty response from server — the AI service may have timed out. Please try again.');
          }
          let allData;
          try {
            allData = JSON.parse(trimmedText);
          } catch (parseErr) {
            console.error('❌ [EDIT_ALL] Failed to parse response:', trimmedText.substring(0, 500));
            throw new Error('Invalid response from server. Please try again.');
          }

          // Handle errors returned in stream body (processing failures send HTTP 200 with error JSON)
          if (allData.error) {
            if (allData.status_code === 402) {
              authService.notifyCreditRequired(allData.detail?.message || allData.detail || 'Insufficient credits.');
              setIsAutoUpdating(false);
              setIsAiProcessing(false);
              releaseDocumentLock();
              return;
            }
            throw new Error(allData.detail || 'Failed to process all pages');
          }

          console.log('🎯 [EDIT_ALL] Response:', allData.total_matched, 'of', allData.total_slides, 'pages matched');

          if (allData.edits && allData.edits.length > 0) {
            let successCount = 0;
            const editAllEditorEntries = []; // Track updated pages for explicit editor sync
            setAutoUpdateProgress({ current: 0, total: allData.edits.length });

            for (let editIdx = 0; editIdx < allData.edits.length; editIdx++) {
              const edit = allData.edits[editIdx];
              setAutoUpdateProgress({ current: editIdx + 1, total: allData.edits.length });
              try {
                // Defensive: validate edit.action before processing
                if (!edit.action || !['create', 'update'].includes(edit.action)) {
                  console.warn(`⚠️ [EDIT_ALL] Skipping edit with unknown action: ${edit.action}`);
                  continue;
                }

                if (edit.action === 'create') {
                  // Handle new page creation — backend now returns full content
                  const newPageId = `page_${Date.now()}_ai_${edit.slide_index}`;
                  const topic = edit.topic || edit.slide_data?.title || 'New Page';
                  let newContent = edit.slide_data?.content || edit.content || `<h2>${topic}</h2><p></p>`;

                  // Sanitize: strip fake image placeholders
                  newContent = newContent.replace(/<img[^>]*src\s*=\s*["']?\{\{UserImage[^}]*\}\}["']?[^>]*\/?>/gi, '');
                  newContent = newContent.replace(/<img[^>]*src\s*=\s*["']?(?!data:|https?:|blob:)[^"'\s>]+["']?[^>]*\/?>/gi, '<!-- Image placeholder removed -->');

                  // Process <chart-config> tags into rendered images
                  const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
                  const chartMatches = [...newContent.matchAll(chartConfigRegex)];
                  if (chartMatches.length > 0) {
                    console.log(`📊 [EDIT_ALL] Processing ${chartMatches.length} charts in new page`);
                    for (const match of chartMatches) {
                      try {
                        const chartConfig = JSON.parse(match[1]);
                        const dataUrl = await renderChartToImage(chartConfig);
                        let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
                        if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                          const labels = chartConfig.data.labels;
                          const summary = chartConfig.data.datasets.map(ds => {
                            return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                          }).join('; ');
                          altText += ` | Data: ${summary}`;
                        }
                        const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                        newContent = newContent.replace(match[0], imgHtml);
                      } catch (err) {
                        console.error('Failed to render chart in new page:', err);
                        newContent = newContent.replace(match[0], '<!-- Chart rendering failed -->');
                      }
                    }
                  }

                  const plainText = newContent.replace(/<[^>]*>/g, '');
                  const wordCount = plainText.trim().split(/\s+/).filter(w => w.length > 0).length;

                  // Compute insertion position: after selected page (from backend), not at end
                  // Defensive: validate after_slide_index bounds
                  let rawAfterIdx = (typeof edit.after_slide_index === 'number' && edit.after_slide_index >= 0)
                    ? edit.after_slide_index
                    : (currentIndex >= 0 ? currentIndex : pages.length - 1);
                  const insertAfterIdx = Math.min(Math.max(rawAfterIdx, 0), pages.length - 1);
                  const newPageOrder = insertAfterIdx + 2 + successCount; // +1 for 0-index, +1 for "after"

                  console.log(`📄 [EDIT_ALL] create_new: insertAfter=${insertAfterIdx}, order=${newPageOrder}, content_len=${newContent.length}`);

                  const newPage = {
                    id: newPageId,
                    order: newPageOrder,
                    title: topic,
                    content: newContent,
                    wordCount: wordCount,
                    hasUnsavedChanges: true,
                  };

                  // Bump orders of existing pages at or after the new position, then insert
                  setPages(prev => {
                    const bumped = prev.map(p => p.order >= newPageOrder ? { ...p, order: p.order + 1 } : p);
                    return [...bumped, newPage].sort((a, b) => a.order - b.order);
                  });
                  successCount++;
                } else if (edit.action === 'update') {
                  const fullIndex = aiIndexToFullIndex[edit.slide_index];
                  const originalPage = pages[fullIndex];
                  if (!originalPage) continue;

                  // Backend returns content at top level (not in slide_data) for reports
                  let editedContent = edit.content || edit.slide_data?.content || '';

                  // Process <chart-config> tags into rendered images
                  const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
                  const chartMatches = [...editedContent.matchAll(chartConfigRegex)];
                  if (chartMatches.length > 0) {
                    console.log(`📊 [EDIT_ALL] Processing ${chartMatches.length} charts in updated page ${edit.slide_index}`);
                    for (const match of chartMatches) {
                      try {
                        const chartConfig = JSON.parse(match[1]);
                        const dataUrl = await renderChartToImage(chartConfig);
                        let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
                        if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                          const labels = chartConfig.data.labels;
                          const summary = chartConfig.data.datasets.map(ds => {
                            return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                          }).join('; ');
                          altText += ` | Data: ${summary}`;
                        }
                        const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                        editedContent = editedContent.replace(match[0], imgHtml);
                      } catch (err) {
                        console.error('Failed to render chart in updated page:', err);
                        editedContent = editedContent.replace(match[0], '<!-- Chart rendering failed -->');
                      }
                    }
                  }

                  // Restore images using pre-extracted maps (AI received content with {{UserImage_xxx}} placeholders)
                  const extraction = pageExtractionMaps[originalPage.id] || extractImages(originalPage.content || '');
                  const restoredContent = restoreImages(editedContent, extraction.imageMap, extraction.embedMap, extraction.chartConfigMap);

                  updatePageContent(originalPage.id, restoredContent);
                  // Sync title if AI returned an updated one (fixes title drift after manual edits)
                  const newTitle = edit.topic || edit.slide_data?.title;
                  if (newTitle) updatePageTitle(originalPage.id, newTitle);
                  editAllEditorEntries.push({ id: originalPage.id, content: restoredContent });
                  successCount++;
                }
              } catch (editErr) {
                console.error(`❌ [EDIT_ALL] Error applying edit for page ${edit.slide_index}:`, editErr);
              }
            }

            // Force-sync Tiptap editors to ensure UI reflects new content
            if (editAllEditorEntries.length > 0) {
              setTimeout(() => {
                editAllEditorEntries.forEach(({ id, content }) => {
                  const editorInstance = editorRefsMap.current[id];
                  if (editorInstance?.setContent) {
                    editorInstance.setContent(markdownToHtml(content));
                  }
                });
              }, 150);
            }

            setAiChatMessages(prev => [...prev.slice(-9), {
              id: chatMsgUid(),
              text: allData.total_matched === 0
                ? 'No pages matched your instruction. Try being more specific.'
                : `Updated ${successCount} of ${allData.total_matched} relevant pages (out of ${allData.total_slides} total).`,
              timestamp: new Date(),
              actionType: 'edit'
            }]);
          } else {
            setAiChatMessages(prev => [...prev.slice(-9), {
              id: chatMsgUid(),
              text: 'No pages were relevant to your instruction. Try a different prompt.',
              timestamp: new Date(),
              actionType: 'info'
            }]);
          }

        } catch (error) {
          console.error('Edit All Pages failed:', error);
          Alert.alert('Error', 'Failed to update all pages. Please try again.');
        } finally {
          setIsAutoUpdating(false);
          setIsAiProcessing(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          releaseDocumentLock();
        }
        return; // Exit function, we handled 'all' mode
      }

      // CHART DETECTION based on simple intent classification (regex)
      const chartRegex = /(create|add|show|generate|insert|make).*(chart|graph|plot)/i;
      const isChartRequest = chartRegex.test(chatInput);

      if (isChartRequest) {
        console.log('📊 [REPORT_AI] Detected chart request:', chatInput);

        // Use presentation chart service - shared logic
        const chartResponse = await fetch(`${apiConfig.API_URL}/presentation/generate-chart-data`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            chart_type: 'bar', // Default, API will refine based on query
            query: chatInput,
            folder_ids: useUploadedData && selectedFolders?.length > 0 ? selectedFolders.map(f => f.id || f) : [],
          })
        });

        const chartData = await chartResponse.json();

        if (chartResponse.status === 402 || handleCreditError(chartData)) {
          setIsAiProcessing(false);
          return;
        }

        if (chartData.success && chartData.chart_config) {
          console.log('📊 [REPORT_AI] Chart config received, rendering...');

          try {
            // Render to image using shared utility
            const chartConfig = chartData.chart_config;
            const dataUrl = await renderChartToImage(chartConfig);

            // Build rich alt text with data summary
            let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
            if (chartConfig.data?.labels && chartConfig.data?.datasets) {
              const labels = chartConfig.data.labels;
              const summary = chartConfig.data.datasets.map(ds => {
                return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
              }).join('; ');
              altText += ` | Data: ${summary}`;
            }

            // Insert image
            if (editorRef.current?.insertContent) {
              // Use 80% width by default, centered
              const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
              editorRef.current.insertContent(imgHtml);
              editorRef.current.insertContent('<p></p>');
            } else {
              // Fallback for non-Tiptap
              updatePageContent(effectivePageId, (effectivePage?.content || '') + `\n\n![Chart](${dataUrl})`);
            }

            setChatInput('');
            setIsAiProcessing(false);
            return; // Exit success
          } catch (renderError) {
            console.error('Chart rendering failed', renderError);
            Alert.alert('Chart Error', 'Failed to render the chart image.');
            setIsAiProcessing(false);
            return;
          }
        } else {
          // If it wasn't a success, maybe the API decided it wasn't a chart request after all?
          // Or just failed. Let's warn and fall through or return? 
          // Better to return and show error for clarity vs doing a weird text edit.
          console.warn('Failed to generate chart data:', chartData.message);
          Alert.alert('Chart Error', chartData.message || 'Could not generate chart.');
          setIsAiProcessing(false);
          return;
        }
      }

      // Determine edit mode based on selection state
      // User requested to remove 'insertion' mode. Default to 'overall' if no selection.
      const editMode = hasSelection ? 'selection' : 'overall';

      // OPTIMIZATION: Extract images and embeds to markers
      const contentToProcess = effectivePage?.content || '';
      const { processedHtml, imageMap, embedMap, chartConfigMap } = extractImages(contentToProcess);

      let processedSelectedText = '';
      if (hasSelection && selectedText) {
        processedSelectedText = selectedText;
      }

      let finalInstruction = chatInput;
      // Add user message to chat history for single-page edits
      setAiChatMessages(prev => [...prev.slice(-9), { id: chatMsgUid(), text: chatInput, timestamp: new Date(), actionType: 'user' }]);
      const hasImages = Object.keys(imageMap).length > 0;
      const hasEmbeds = Object.keys(embedMap).length > 0;
      const hasChartConfigs = Object.keys(chartConfigMap).length > 0;

      if (hasImages || hasEmbeds || hasChartConfigs) {
        finalInstruction += `\n\n[SYSTEM NOTE]: This document contains media represented by placeholders.\n`;
        if (hasImages) {
          finalInstruction += `- USER IMAGES: src="{{UserImage_...}}" - These are user-uploaded. NEVER modify, remove, or replace these <img> tags or their src values under ANY circumstances — even if the user asks. They are immutable. Return them EXACTLY as they appear in the original HTML.\n`;
          finalInstruction += `- CHART IMAGES: src="{{ChartImage_...}}" - These are AI-generated chart/graph images. You can freely MODIFY, REPLACE, or REMOVE them. To update chart data, REPLACE the entire <img> tag with a <chart-config> tag containing Chart.js JSON config. Example: <chart-config>{"type":"bar","data":{"labels":[...],"datasets":[...]}}</chart-config>\n`;
        }
        if (hasChartConfigs) {
          finalInstruction += `- Chart configs: data-chart-config="{{ChartConfig_...}}" - These preserve chart styling. Do NOT modify these attribute values. They will be auto-restored.\n`;
        }
        if (hasEmbeds) {
          finalInstruction += `- Embeds: <!-- {{UserEmbed_...}} [EMBED: ...] DO NOT MODIFY --> - These are embedded videos/content. NEVER modify or remove these comment blocks.\n`;
        }
      }

      console.log('🤖 AI Edit Request:', { mode: editMode, instruction: finalInstruction.substring(0, 50), hasImages });

      const response = await fetch(`${apiConfig.API_URL}/composer/ai-edit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          instruction: finalInstruction,
          current_content: processedHtml,
          selected_text: processedSelectedText,
          // Include node context if an image/chart is selected
          image_context: editorRef.current?.selectedNodeContext?.type === 'image' ? editorRef.current.selectedNodeContext.attributes : null,
          cursor_position: cursorPosition,
          edit_mode: editMode,
          page_id: effectivePageId,
          goal: reportGoal?.purpose || '',
          folder_ids: useUploadedData && selectedFolders?.length > 0 ? selectedFolders.map(f => f.id || f) : [],
          // Scope intelligence
          user_edit_scope: editScope,
          pages_summary: buildPagesSummary(pages.filter(p => !p.hidden)),
        })
      });

      if (response.status === 402) {
        const errData = await response.json().catch(() => ({}));
        handleCreditError(errData);
        setIsAiProcessing(false);
        return;
      }

      if (response.ok) {
        const data = await response.json();

        if (data.success) {
          // Show scope escalation message if AI auto-escalated
          if (data.scope_escalated && data.scope_message) {
            setAiChatMessages(prev => [...prev.slice(-9), {
              id: chatMsgUid(),
              text: `🔄 ${data.scope_message}`,
              timestamp: new Date(),
              actionType: 'info'
            }]);
          }

          // Always add AI message to chat if present
          if (data.ai_message) {
            setAiChatMessages(prev => [...prev.slice(-9), { // Keep last 10 messages
              id: chatMsgUid(),
              text: data.ai_message,
              timestamp: new Date(),
              actionType: data.action_type || 'edit'
            }]);
          }

          // Handle action type
          if (data.action_type === 'create_new') {
            // CREATE NEW PAGE after current
            console.log('✅ AI Create New Page:', data.new_title);

            const newPageId = `page_${Date.now()}`;
            const newPageOrder = (currentPageIndex >= 0 ? currentPageIndex + 2 : pages.length + 1);

            // Sanitize: strip fake image placeholders (e.g. <img src="{{UserImage_...}}">)
            let sanitizedContent = (data.new_content || '');
            const hadFakeImages = /\{\{UserImage/i.test(sanitizedContent);
            sanitizedContent = sanitizedContent.replace(/<img[^>]*src\s*=\s*["']?\{\{UserImage[^}]*\}\}["']?[^>]*\/?>/gi, '');
            sanitizedContent = sanitizedContent.replace(/<img[^>]*src\s*=\s*["']?(?!data:|https?:|blob:)[^"'\s>]+["']?[^>]*\/?>/gi, '<!-- Image placeholder removed -->');
            if (hadFakeImages) console.warn('⚠️ [REPORT_AI] Stripped fake UserImage placeholders from create_new content');

            // Defensive: ensure content is non-empty
            if (!sanitizedContent || sanitizedContent.replace(/<[^>]*>/g, '').trim().length < 5) {
              console.warn('⚠️ [REPORT_AI] create_new returned near-empty content, keeping as-is');
            }

            // Count words in new content
            const plainText = sanitizedContent.replace(/<[^>]*>/g, '');
            const wordCount = plainText.trim().split(/\s+/).filter(w => w.length > 0).length;

            const newPage = {
              id: newPageId,
              order: newPageOrder,
              title: data.new_title || `Page ${pages.length + 1}`,
              content: sanitizedContent,
              wordCount: wordCount,
              hasUnsavedChanges: true
            };

            // Update page orders for pages after current
            const updatedPages = pages.map(p => {
              if (p.order >= newPageOrder) {
                return { ...p, order: p.order + 1 };
              }
              return p;
            });

            // Insert new page and sort by order
            const allPages = [...updatedPages, newPage].sort((a, b) => a.order - b.order);
            setPages(allPages);

            // Navigate to new page
            setCurrentPageId(newPageId);

            setChatInput('');
          } else if (data.edited_content !== undefined) {
            // EDIT existing content (default behavior)
            console.log('✅ AI Edit: Applying content', { mode: editMode, contentLength: data.edited_content.length });

            let newContent = data.edited_content;

            // PROCESS CHARTS in edited content
            const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
            const matches = [...newContent.matchAll(chartConfigRegex)];

            if (matches.length > 0) {
              console.log(`📊 [REPORT_AI] Found ${matches.length} charts in edit response`);
              for (const match of matches) {
                try {
                  const configJson = match[1];
                  const chartConfig = JSON.parse(configJson);
                  const dataUrl = await renderChartToImage(chartConfig);

                  // Create rich alt text with data summary
                  let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
                  if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                    const labels = chartConfig.data.labels;
                    const summary = chartConfig.data.datasets.map(ds => {
                      return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                    }).join('; ');
                    altText += ` | Data: ${summary}`;
                  }

                  const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                  newContent = newContent.replace(match[0], imgHtml);
                } catch (err) {
                  console.error('Failed to render chart from edit config:', err);
                  newContent = newContent.replace(match[0], '<!-- Chart rendering failed -->');
                }
              }
            }

            // RESTORE IMAGES AND EMBEDS (user's original media)
            const restoredContent = restoreImages(newContent, imageMap, embedMap, chartConfigMap);

            // Apply edit based on mode — use server's edit_mode (may differ from local
            // editMode due to backend scope auto-escalation, e.g. selection → overall)
            const effectiveEditMode = data.edit_mode || editMode;
            if (effectiveEditMode === 'selection' && editorRef.current?.replaceSelection) {
              editorRef.current.replaceSelection(restoredContent);
            } else if (effectiveEditMode === 'insertion' && editorRef.current?.insertContent) {
              editorRef.current.insertContent(restoredContent);
            } else {
              if (editorRef.current?.setContent) {
                editorRef.current.setContent(restoredContent);
              }
              updatePageContent(effectivePageId, restoredContent);
            }

            setChatInput('');
            setSelectedText('');
            setHasSelection(false);
          } else if (data.action_type === 'message_only') {
            // Message only - no content changes, just clear input
            setChatInput('');
          } else if (data.action_type === 'generate_image') {
            // GENERATE IMAGE INTENT
            console.log('🖼️ [REPORT_AI] Generating image from prompt:', data.image_prompt);
            console.log('🖼️ [REPORT_AI] Image type:', data.image_type || 'photo');

            // Show loading state
            setAiChatMessages(prev => [...prev.slice(-9), {
              id: chatMsgUid(),
              text: `Generating image: "${data.image_prompt.substring(0, 50)}..."`,
              timestamp: new Date(),
              actionType: 'image_generation_start'
            }]);

            try {
              // Generate the image using LLM Image Service
              const imageResponse = await ImageGenService.generateImage(data.image_prompt, {
                width: 1024,
                height: 1024,
              });

              if (imageResponse && (imageResponse.image_url || imageResponse.image_data)) {
                const imageUrl = imageResponse.image_data || imageResponse.image_url;

                // Insert the generated image (async - pre-caches before insertion)
                await handleInsertAIImage(imageUrl, data.image_prompt);

                // Add success message
                setAiChatMessages(prev => [...prev.slice(-9), {
                  id: chatMsgUid(),
                  text: "Image generated and inserted successfully!",
                  timestamp: new Date(),
                  actionType: 'image_generation_success'
                }]);
              } else {
                throw new Error("No image data received");
              }
            } catch (imgErr) {
              console.error("AI Image Generation failed:", imgErr);
              Alert.alert("Image Generation Failed", "Could not generate image. Please try again.");
              setAiChatMessages(prev => [...prev.slice(-9), {
                id: chatMsgUid(),
                text: "Failed to generate image.",
                timestamp: new Date(),
                actionType: 'error'
              }]);
            }

            setChatInput('');
          } else {
            Alert.alert('Error', data.message || 'Failed to apply edit');
          }
        } else {
          Alert.alert('Error', data.message || 'Failed to apply edit');
        }
      } else {
        const errorData = await response.json();
        Alert.alert('Error', errorData.detail || 'Failed to process edit request');
      }
    } catch (error) {
      console.error('AI edit error:', error);
      Alert.alert('Error', 'Failed to process AI edit. Please try again.');
    } finally {
      setIsAiProcessing(false);
    }
  }, [chatInput, currentPage, currentPageId, currentPageIndex, reportGoal, userDeviceId, selectedFolders, apiConfig, updatePageContent, isAiProcessing, hasSelection, selectedText, cursorPosition, pages, setPages, setCurrentPageId, editScope, getVisiblePageId]);

  // ═══════════════════════════════════════════════════════════════════════
  // AGENTIC WHOLE-REPORT EDITOR — same architecture as the deck composers.
  // The ENTIRE document (per-page HTML) + chat message go to the backend in
  // one shot; the agent works in rounds and streams operations
  // (patch_page/edit_page/add/delete/reorder/update_letterhead/...) we apply
  // here. Tiptap re-renders from the updated page.content.
  // ═══════════════════════════════════════════════════════════════════════

  // Applies a batch of agent operations against MARKERIZED page copies (the
  // same form the server/LLM sees, so patch find/replace strings line up),
  // commits the RESTORED content to state, and returns the markerized array
  // for threading through subsequent streamed batches.
  const applyAgentReportOps = useCallback((operations, basePages, imgMap = {}, liveMeta = null) => {
    const base = basePages || pages;
    if (!operations || operations.length === 0) return base;
    let working = base.map(p => ({ ...p }));
    const newId = () => `page_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    // Track which page ids the agent actually touched this batch — the commit
    // keeps the user's live version of every UNTOUCHED page (so typing during
    // the stream isn't reverted by the snapshot).
    const touched = new Set();
    let structural = false;

    for (const op of operations) {
      try {
        if (op.op === 'patch_page') {
          const idx = working.findIndex(p => p.id === op.page_id);
          if (idx < 0) continue;
          const content = working[idx].content || '';
          if (typeof op.find !== 'string' || !content.includes(op.find)) {
            console.warn('⚠️ [AGENT-REPORT] patch_page find not present client-side — page', op.page_id, 'desynced?');
            continue;
          }
          // LITERAL replacement — String.replace(string, string) performs
          // $-pattern substitution ($&, $', $$ …) and would diverge from the
          // backend's literal Python str.replace.
          let replaced;
          if (op.all) {
            replaced = content.split(op.find).join(op.replace || '');
          } else {
            const at = content.indexOf(op.find);
            replaced = content.slice(0, at) + (op.replace || '') + content.slice(at + op.find.length);
          }
          working[idx] = { ...working[idx], content: replaced, hasUnsavedChanges: true };
          touched.add(op.page_id);
        } else if (op.op === 'edit_page') {
          const idx = working.findIndex(p => p.id === op.page_id);
          if (idx < 0 || typeof op.html !== 'string') continue;
          working[idx] = { ...working[idx], content: op.html, ...(op.title ? { title: op.title } : {}), hasUnsavedChanges: true };
          touched.add(op.page_id);
        } else if (op.op === 'add_page') {
          if (typeof op.html !== 'string') continue;
          const page = {
            id: op.id || newId(), title: op.title || 'New Page', content: op.html,
            wordCount: 0, layout: 'single_column', layoutMeta: {}, hidden: false,
            created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
          };
          let insertAt;
          if (op.after_page_id) {
            const ai = working.findIndex(p => p.id === op.after_page_id);
            insertAt = ai >= 0 ? ai + 1 : working.length;
          } else if (op.position === 'start') insertAt = 0;
          else insertAt = working.length;
          working.splice(insertAt, 0, page);
          touched.add(page.id);
          structural = true;
        } else if (op.op === 'delete_page') {
          if (working.length <= 1) continue;
          working = working.filter(p => p.id !== op.page_id);
          structural = true;
        } else if (op.op === 'reorder_pages') {
          const byId = {};
          working.forEach(p => { byId[p.id] = p; });
          // Dedupe defensively — a duplicated id must not become a duplicated page.
          const seen = new Set();
          const cleanOrder = (op.order || []).filter(id => byId[id] && !seen.has(id) && seen.add(id));
          const ordered = cleanOrder.map(id => byId[id]);
          working.forEach(p => { if (!seen.has(p.id)) ordered.push(p); });
          if (ordered.length === working.length) { working = ordered; structural = true; }
        } else if (op.op === 'update_title') {
          if (op.title) updateReportMetadata({ title: op.title });
        } else if (op.op === 'update_letterhead') {
          if (op.letterhead && liveMeta) {
            const lh = { ...op.letterhead };
            // '__KEEP__' is the sentinel we sent instead of a long/base64 logoUrl —
            // never let it overwrite the real stored logo.
            if (lh.logoUrl === '__KEEP__') delete lh.logoUrl;
            // Merge into the per-turn live meta (NOT the render-time closure,
            // which is frozen for the whole streamed turn).
            liveMeta.letterhead = { ...liveMeta.letterhead, ...lh };
            updateHeaderFooterConfig({ letterhead: { ...liveMeta.letterhead } });
          }
        } else if (op.op === 'update_header_footer') {
          if (liveMeta) {
            if (op.header) liveMeta.header = { ...liveMeta.header, ...op.header };
            if (op.footer) liveMeta.footer = { ...liveMeta.footer, ...op.footer };
            updateHeaderFooterConfig({
              ...(op.header ? { header: { ...liveMeta.header } } : {}),
              ...(op.footer ? { footer: { ...liveMeta.footer } } : {}),
            });
          }
        }
      } catch (opErr) {
        console.error('❌ [AGENT-REPORT] operation failed:', op?.op, opErr);
      }
    }

    working = working.map((p, i) => ({ ...p, order: i + 1 }));
    // Commit: restore image srcs on agent-touched pages; keep the user's LIVE
    // version of untouched pages (typing during the stream survives) unless a
    // structural op changed the page set/order. Return the markerized working
    // copy so the next batch's patch strings still match the server's view.
    setPages(prev => {
      const prevById = {};
      (prev || []).forEach(p => { prevById[p.id] = p; });
      return working.map(p => {
        if (!touched.has(p.id) && prevById[p.id]) {
          return structural ? { ...prevById[p.id], order: p.order } : prevById[p.id];
        }
        return { ...p, content: restoreReportImages(p.content, imgMap) };
      });
    });
    return working;
  }, [pages, setPages, updateReportMetadata, updateHeaderFooterConfig]);

  // Chat entry point — replaces the legacy scope-based submit.
  // Lets the user STOP an in-flight agent edit. Aborting the fetch breaks the
  // SSE read loop (the loop's reader.read() rejects) — already-applied op
  // batches stay on the document; no further rounds are read.
  const agentAbortRef = useRef(null);

  const handleStopAgent = useCallback(() => {
    if (agentAbortRef.current) {
      agentAbortRef.current.abort();
      agentAbortRef.current = null;
    }
    setIsAiProcessing(false);
    setAiChatMessages(prev => {
      const stopped = { id: chatMsgUid(), text: 'Stopped.', timestamp: new Date(), actionType: 'info' };
      if (prev.length > 0 && prev[prev.length - 1].actionType === 'thinking') {
        return [...prev.slice(0, -1), stopped];
      }
      return [...prev.slice(-29), stopped];
    });
  }, []);

  const handleAgentEdit = useCallback(async (overrideInstruction) => {
    const instruction = (typeof overrideInstruction === 'string' ? overrideInstruction : chatInput).trim();
    if (!instruction || isAiProcessing || isAiLocked) return;

    setIsAiProcessing(true);
    setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
    setChatInput('');
    setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: `Looking at your ${pages.length} pages…`, timestamp: new Date(), actionType: 'thinking' }]);

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) { Alert.alert('Authentication Error', 'Please log in again.'); setIsAiProcessing(false); return; }

      const visibleId = getVisiblePageId?.() || currentPageId;
      const currentIndex = Math.max(0, pages.findIndex(p => p.id === visibleId));
      const recentHistory = aiChatMessages
        .filter(m => m.actionType !== 'thinking')
        .slice(-6)
        .map(m => ({ role: m.actionType === 'user' ? 'user' : 'assistant', text: m.text }));
      const finalFolderIds = useUploadedData && selectedFolders?.length > 0 ? selectedFolders.map(f => f.id || f) : [];

      // Swap image srcs (base64 data URIs, long presigned URLs) for {{IMG_n}}
      // markers — the LLM must never receive image binaries. The working copy
      // keeps ALL page fields (layout, timestamps, hidden …) so commits don't
      // strip them; only the wire payload is slimmed down.
      const { pages: markerPages, map: imgMap } = markerizeReportImages(pages.map(p => ({ ...p })));
      const wirePages = markerPages.map(p => ({ id: p.id, order: p.order, title: p.title, content: p.content || '', hidden: !!p.hidden }));
      const lhCfg = reportMetadata?.letterheadConfig || {};
      const lhLogoSafe = lhCfg.logoUrl && lhCfg.logoUrl.length > 200 ? '__KEEP__' : lhCfg.logoUrl;
      // Per-turn live metadata — successive metadata ops in one streamed turn
      // merge into THIS object (the render-time reportMetadata closure is
      // frozen for the whole turn and would drop earlier ops' changes).
      const liveMeta = {
        letterhead: { ...lhCfg },
        header: { ...(reportMetadata?.headerConfig || {}) },
        footer: { ...(reportMetadata?.footerConfig || {}) },
      };

      const abortController = new AbortController();
      agentAbortRef.current = abortController;
      const response = await fetch(`${apiConfig.API_URL}/composer/agent-edit-stream`, {
        method: 'POST',
        signal: abortController.signal,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          instruction,
          pages: wirePages,
          current_page_index: currentIndex,
          metadata: {
            title: reportMetadata?.title,
            goal: reportGoal?.purpose || '',
            author: reportMetadata?.author || '',
            letterheadConfig: { ...lhCfg, logoUrl: lhLogoSafe },
            headerConfig: reportMetadata?.headerConfig,
            footerConfig: reportMetadata?.footerConfig,
          },
          chat_history: recentHistory,
          folder_ids: finalFolderIds,
          selected_text: hasSelection && selectedText ? selectedText : null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 402) { authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.'); setIsAiProcessing(false); return; }
        throw new Error(errorData.message || 'AI edit failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Thread the MARKERIZED document (the server's view) through batches.
      let liveDoc = markerPages.map(p => ({ ...p }));

      const handleEvent = (event) => {
        if (event.type === 'status') {
          if (event.message) {
            setAiChatMessages(prev => {
              const msg = { id: chatMsgUid(), text: event.message, timestamp: new Date(), actionType: 'thinking' };
              if (prev.length > 0 && prev[prev.length - 1].actionType === 'thinking') {
                return [...prev.slice(0, -1), msg];
              }
              return [...prev.slice(-29), msg];
            });
          }
        } else if (event.type === 'operations') {
          liveDoc = applyAgentReportOps(event.operations || [], liveDoc, imgMap, liveMeta);
        } else if (event.type === 'ask_user') {
          setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: event.chat_message || 'Could you clarify?', timestamp: new Date(), actionType: 'ask', chips: event.options || [] }]);
        } else if (event.type === 'finish') {
          if (event.chat_message) {
            setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: event.chat_message, timestamp: new Date(), actionType: 'edit', chips: event.suggestions || [] }]);
          }
        } else if (event.type === 'error') {
          if (event.status_code === 402) authService.notifyCreditRequired(event.message);
          else setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: event.message || 'Sorry, that edit failed. Please rephrase.', timestamp: new Date(), actionType: 'info' }]);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith('data: ')) continue;
          try { handleEvent(JSON.parse(t.slice(6))); } catch (e) { console.warn('⚠️ [AGENT-REPORT] SSE parse:', e); }
        }
      }
      if (buffer.trim().startsWith('data: ')) {
        try { handleEvent(JSON.parse(buffer.trim().slice(6))); } catch { }
      }
    } catch (error) {
      // User pressed Stop — handleStopAgent already posted "Stopped." Swallow.
      if (error?.name === 'AbortError') return;
      console.error('Agent report edit error:', error);
      Alert.alert('Error', 'Failed to process request. Please try again.');
    } finally {
      agentAbortRef.current = null;
      setIsAiProcessing(false);
    }
  }, [chatInput, isAiProcessing, isAiLocked, pages, currentPageId, getVisiblePageId, aiChatMessages, reportMetadata, reportGoal, selectedFolders, useUploadedData, apiConfig, applyAgentReportOps, hasSelection, selectedText]);

  // Handle selection changes from Tiptap editor (with page context for continuous scroll)
  const handleSelectionChangeForPage = useCallback((pageId, selectionInfo) => {
    // When user interacts with a page editor, update currentPageId
    if (pageId && pageId !== currentPageIdRef.current) {
      setCurrentPageId(pageId);
      if (editorRefsMap.current[pageId]) {
        editorRef.current = editorRefsMap.current[pageId];
      }
    }
    // Batch selection state updates to avoid multiple re-renders
    const newSelectedText = selectionInfo.selectedText || '';
    const newCursorPosition = selectionInfo.from || 0;
    const newHasSelection = selectionInfo.hasSelection || false;
    const newSelectionRange = { from: selectionInfo.from, to: selectionInfo.to };
    setSelectedText(prev => prev === newSelectedText ? prev : newSelectedText);
    setCursorPosition(prev => prev === newCursorPosition ? prev : newCursorPosition);
    setHasSelection(prev => prev === newHasSelection ? prev : newHasSelection);
    setSelectionRange(prev => (prev.from === newSelectionRange.from && prev.to === newSelectionRange.to) ? prev : newSelectionRange);

    // Store selected node context (image/chart)
    if (selectionInfo.selectedNodeType === 'image' && selectionInfo.selectedNodeAttributes) {
      // Store relevant attributes for AI context
      editorRef.current.selectedNodeContext = {
        type: 'image',
        attributes: selectionInfo.selectedNodeAttributes
      };
      try {
        console.log('🖼️ [COMPOSER] Selected Image Params:', JSON.stringify(selectionInfo.selectedNodeAttributes));
      } catch (e) {
        console.log('🖼️ [COMPOSER] Selected Image Params: [unable to serialize]');
      }
    } else {
      if (editorRef.current) {
        editorRef.current.selectedNodeContext = null;
      }
    }

    if (selectionInfo.hasSelection) {
      console.log('📝 Selection:', selectionInfo.selectedText?.substring(0, 50));
    }
  }, []); // Uses currentPageIdRef instead of currentPageId

  // Backward-compatible wrapper (used by mobile single-page mode)
  const handleSelectionChange = useCallback((selectionInfo) => {
    handleSelectionChangeForPage(currentPageId, selectionInfo);
  }, [currentPageId, handleSelectionChangeForPage]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedText('');
    setHasSelection(false);
    setCursorPosition(0);
  }, []);

  // Chart edit handler - called from ImageResizeComponent via editor storage
  const handleChartEdit = useCallback((chartConfig, nodePos) => {
    setEditingChartConfig(chartConfig);
    setEditingChartNodePos(nodePos);
    setShowChartEditModal(true);
  }, []);

  const handleChartEditSave = useCallback(async (updatedConfig) => {
    try {
      const dataUrl = await renderChartToImage(updatedConfig);
      const ed = editorRef.current?.getEditor?.();
      if (ed && editingChartNodePos != null) {
        // Replace the image node at the stored position with updated src and config
        const { tr } = ed.state;
        const node = ed.state.doc.nodeAt(editingChartNodePos);
        if (node && node.type.name === 'image') {
          const newAttrs = {
            ...node.attrs,
            src: dataUrl,
            'data-chart-config': encodeURIComponent(JSON.stringify(updatedConfig)),
          };
          tr.setNodeMarkup(editingChartNodePos, undefined, newAttrs);
          ed.view.dispatch(tr);
        }
      }
    } catch (err) {
      console.error('Failed to update chart:', err);
    }
    setShowChartEditModal(false);
    setEditingChartConfig(null);
    setEditingChartNodePos(null);
  }, [editingChartNodePos]);

  // ═══════════════════════════════════════════════════════════════════
  // Stable per-page callbacks for PageEditorCard (avoid inline arrows in .map())
  // ═══════════════════════════════════════════════════════════════════
  const stableCallbacksRef = useRef({});

  const getPageCallbacks = useCallback((pageId) => {
    if (!stableCallbacksRef.current[pageId]) {
      stableCallbacksRef.current[pageId] = {
        onContentChange: (html) => handleContentChange(pageId, html),
        onSelectionChange: (selInfo) => handleSelectionChangeForPage(pageId, selInfo),
        onTitleChange: (text) => updatePageTitle(pageId, text),
        onFocus: () => {
          if (pageId !== currentPageIdRef.current) {
            setCurrentPageId(pageId);
            if (editorRefsMap.current[pageId]) {
              editorRef.current = editorRefsMap.current[pageId];
            }
          }
        },
        onLayout: (e) => {
          pageLayoutsRef.current[pageId] = {
            y: e.nativeEvent.layout.y,
            height: e.nativeEvent.layout.height,
          };
        },
        editorRefCallback: (el) => {
          editorRefsMap.current[pageId] = el;
          if (pageId === currentPageIdRef.current) {
            editorRef.current = el;
          }
        },
      };
    }
    return stableCallbacksRef.current[pageId];
  }, []); // Empty deps — uses refs for latest state

  // Save title
  const handleTitleSave = useCallback(() => {
    updateReportMetadata({ title: editableTitle });
    setIsEditingTitle(false);
  }, [editableTitle, updateReportMetadata]);

  // Generate report thumbnail from first page content
  const generateReportThumbnail = useCallback(async () => {
    if (Platform.OS !== 'web' || pages.length === 0) return null;

    try {
      // Find the editor container element
      const editorContent = document.querySelector('.tiptap-editor-content');
      if (!editorContent) {
        console.log('[REPORT_COMPOSER] Editor content element not found for thumbnail');
        return null;
      }

      // Try to use html2canvas if available (dynamically import)
      try {
        const html2canvas = (await import('html2canvas')).default;
        const canvas = await html2canvas(editorContent, {
          scale: 0.5,
          width: 400,
          height: 300,
          useCORS: true,
          logging: false,
          backgroundColor: '#ffffff',
        });
        const thumbnailDataUrl = canvas.toDataURL('image/jpeg', 0.7);
        console.log('[REPORT_COMPOSER] Thumbnail generated successfully');
        return thumbnailDataUrl;
      } catch (htmlCanvasErr) {
        console.log('[REPORT_COMPOSER] html2canvas not available, skipping thumbnail:', htmlCanvasErr.message);
        return null;
      }
    } catch (err) {
      console.warn('[REPORT_COMPOSER] Failed to generate thumbnail:', err);
      return null;
    }
  }, [pages]);

  // Open save modal with default name from goal text
  const openSaveModal = useCallback(() => {
    // Default the title from goal text if still untitled
    if (!editableTitle || editableTitle === 'Untitled Report') {
      const goalText = reportGoal?.purpose || reportMetadata?.overall_goal || '';
      const defaultName = goalText.slice(0, 50).trim() || 'Untitled Report';
      setEditableTitle(defaultName);
    }
    setShowSaveModal(true);
  }, [editableTitle, reportGoal, reportMetadata]);

  // Save report to MongoDB
  const handleSaveToServer = useCallback(async (titleOverride) => {
    setIsSavingManual(true);
    try {
      // Apply title override immediately (from save modal)
      const finalMetadata = titleOverride
        ? { ...reportMetadata, title: titleOverride }
        : reportMetadata;
      if (titleOverride) updateReportMetadata({ title: titleOverride });

      // Generate thumbnail before saving
      let thumbnail = null;
      if (pages.length > 0) {
        thumbnail = await generateReportThumbnail();
      }

      const reportId = await saveReportToServer(
        { pages, reportMetadata: finalMetadata, reportGoal, thumbnail, folderIds: selectedFolders.map(f => f.id || f) },
        apiConfig,
        currentReportId
      );
      setCurrentReportId(reportId);
      Alert.alert('Saved', 'Report saved to cloud successfully!');
    } catch (err) {
      Alert.alert('Error', 'Failed to save report');
    } finally {
      setIsSavingManual(false);
    }
  }, [pages, reportMetadata, reportGoal, apiConfig, currentReportId, saveReportToServer, generateReportThumbnail]);

  // Save a Copy - creates a completely independent copy with a new ID
  const handleSaveAsCopy = useCallback(async () => {
    setIsSavingManual(true);
    try {
      const copyTitle = editableTitle.endsWith(' (Copy)') ? editableTitle : `${editableTitle} (Copy)`;
      const finalMetadata = { ...reportMetadata, title: copyTitle };

      // Generate thumbnail before saving
      let thumbnail = null;
      if (pages.length > 0) {
        thumbnail = await generateReportThumbnail();
      }

      // Save with reportId = null to force creation of a new document
      const reportId = await saveReportToServer(
        { pages, reportMetadata: finalMetadata, reportGoal, thumbnail, folderIds: selectedFolders.map(f => f.id || f) },
        apiConfig,
        null
      );

      // Switch UI to the new copy
      setCurrentReportId(reportId);
      setEditableTitle(copyTitle);
      updateReportMetadata({ title: copyTitle });
      if (Platform.OS === 'web') navigateToReport(reportId);

      Alert.alert('Saved', 'A copy has been created. You are now editing the new copy.');
    } catch (err) {
      console.error('Failed to save report copy:', err);
      Alert.alert('Error', 'Failed to save copy.');
    } finally {
      setIsSavingManual(false);
    }
  }, [pages, reportMetadata, reportGoal, apiConfig, saveReportToServer, generateReportThumbnail, editableTitle, updateReportMetadata]);

  // Build outline data from current pages for the Update All modal
  const currentOutlineData = useMemo(() => {
    return pages.map((page, index) => {
      // Extract a short text summary from HTML content for the outline field
      let outline = page.outline || '';
      if (!outline && page.content) {
        const plain = page.content.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
        outline = plain.slice(0, 150);
      }
      return {
        slideIndex: index,
        title: page.title || `Page ${index + 1}`,
        outline,
      };
    });
  }, [pages]);

  // Refresh outline using AI - regenerates section outline based on goal + vault
  const handleRefreshOutline = useCallback(async (editedGoal, currentOutline) => {
    setIsRefreshingOutline(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) return null;

      const finalFolderIds = useUploadedData && selectedFolders?.length > 0
        ? selectedFolders.map(f => f.id || f)
        : [];

      const response = await fetch(`${apiConfig.API_URL}/composer/generate-outline`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          report_goal: {
            purpose: editedGoal || reportGoal?.purpose || '',
            targetAudience: reportGoal?.targetAudience || '',
            keyTopics: reportGoal?.keyTopics || [],
            tone: reportGoal?.tone || 'professional',
          },
          folder_ids: finalFolderIds,
          page_count: currentOutline?.length || pages.length,
          existing_outline: currentOutline?.map(item => ({
            id: item.slideIndex + 1,
            title: item.title || '',
            outline: item.outline || '',
          })),
        }),
      });

      if (!response.ok) return null;

      const data = await response.json();
      if (data.success && data.outline?.sections) {
        const suggestedTopic = data.suggested_topic || '';
        const sections = data.outline.sections.map((section, index) => ({
          slideIndex: section.id ? parseInt(String(section.id).replace(/\D/g, ''), 10) - 1 : index,
          title: section.title || `Section ${index + 1}`,
          outline: section.objective || section.key_points?.join(', ') || '',
        }));
        return { topic: suggestedTopic || editedGoal, outline: sections };
      }
      return null;
    } catch (error) {
      console.error('Failed to refresh outline:', error);
      return null;
    } finally {
      setIsRefreshingOutline(false);
    }
  }, [apiConfig, useUploadedData, selectedFolders, reportGoal, pages.length]);

  // Auto Update - Step 1: Show Instruction Modal
  const handleAutoUpdate = useCallback(() => {
    if (isAutoUpdating) return;

    // Check if document is locked
    if (isDocumentLocked) {
      Alert.alert(
        'Document Locked',
        `This document is currently being updated by ${documentLockedBy?.name || 'another user'}. Please wait until they finish.`
      );
      return;
    }

    if (pages.length === 0) {
      Alert.alert('Empty Report', 'There are no pages to update.');
      return;
    }

    setShowUpdateInstructionModal(true);
  }, [isAutoUpdating, isDocumentLocked, documentLockedBy, pages.length]);

  // Auto Update - Step 2: Execute Update with Instruction (Smart ai-edit-all path)
  const handleConfirmUpdate = useCallback(async ({ instruction, updatedGoal, updatedOutline }) => {
    // Acquire document lock first
    const lockAcquired = requestDocumentLock();
    if (!lockAcquired) {
      Alert.alert('Lock Failed', 'Could not acquire document lock. Please try again.');
      setShowUpdateInstructionModal(false);
      return;
    }

    // Update goal if changed
    if (updatedGoal) {
      const newGoal = typeof reportGoal === 'object'
        ? { ...reportGoal, purpose: updatedGoal }
        : { purpose: updatedGoal };
      setReportGoal(newGoal);
    }

    // Update page titles/outlines if changed — use positional mapping:
    // i-th outline item → i-th page (outline may have been refreshed/reordered in the modal, so slideIndex can be stale)
    if (updatedOutline && Array.isArray(updatedOutline)) {
      setPages(prev => prev.map((page, idx) => {
        const outlineItem = updatedOutline[idx];
        if (outlineItem) {
          return {
            ...page,
            title: outlineItem.title || page.title,
            outline: outlineItem.outline || page.outline,
          };
        }
        return page;
      }));
    }

    setIsAutoUpdating(true);
    setShowUpdateInstructionModal(false);
    setAutoUpdateProgress({ current: 0, total: pages.filter(p => !p.hidden).length });

    // Only use vault if folders are explicitly selected (no default to 'general')
    const finalFolderIds = useUploadedData && selectedFolders && selectedFolders.length > 0
      ? selectedFolders.map(f => f.id || f)
      : [];

    const folderIds = finalFolderIds.map(f => typeof f === 'object' ? f.id : f);
    if (!folderIds || folderIds.length === 0) {
      Alert.alert('No Data Store Selected', 'Please select data store folders to update from.');
      setIsAutoUpdating(false);
      releaseDocumentLock();
      return;
    }

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        setIsAutoUpdating(false);
        releaseDocumentLock();
        return;
      }

      const extractGoalString = (goalData) => {
        if (!goalData) return '';
        if (typeof goalData === 'string') return goalData;
        if (goalData.purpose) return extractGoalString(goalData.purpose);
        return '';
      };

      // Filter out hidden pages for AI processing
      const aiPages = pages.filter(p => !p.hidden);
      const aiIndexToFullIndex = aiPages.map(p => pages.indexOf(p));

      // Build summaries with updated outline data (positional: i-th outline → i-th visible page)
      const pagesSummary = buildPagesSummary(aiPages).map((summary, idx) => {
        const outlineItem = updatedOutline?.[idx];
        if (outlineItem) {
          return {
            ...summary,
            title: outlineItem.title || summary.title,
          };
        }
        return summary;
      });

      const goalString = updatedGoal || extractGoalString(reportGoal) || '';
      const baseInstruction = "Update all sections with the latest data, statistics, and information from my data store. You have full freedom to restructure content as needed.";

      // Include the full target outline in the instruction so AI knows desired structure
      let outlineContext = '';
      if (updatedOutline && updatedOutline.length > 0) {
        const outlineList = updatedOutline.map((item, i) => `${i + 1}. ${item.title}${item.outline ? ': ' + item.outline : ''}`).join('\n');
        outlineContext = `\n\nTARGET OUTLINE (${updatedOutline.length} sections):\n${outlineList}\nRedistribute and update content to match this outline structure.`;
      }

      const fullInstruction = (instruction && instruction !== "Update with the latest data from my data store."
        ? `${baseInstruction}\n\nAdditional: ${instruction}`
        : baseInstruction) + outlineContext;

      const currentIndex = aiPages.findIndex(p => p.id === currentPageId);

      // Strip base64 images before sending to reduce payload size (same as Edit via chat flow)
      // Store extraction maps so we can restore images using the SAME placeholder IDs after AI response
      const updateAllExtractionMaps = {};
      const updateAllExtractedPages = aiPages.map(p => {
        const extraction = extractImages(p.content || '');
        updateAllExtractionMaps[p.id] = extraction;
        return {
          content: extraction.processedHtml,
          id: p.id,
          title: p.title,
        };
      });

      // Use smart ai-edit-all endpoint (streaming keepalive response)
      const response = await fetch(`${apiConfig.API_URL}/composer/ai-edit-all`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          instruction: fullInstruction,
          pages_summary: pagesSummary,
          full_pages: updateAllExtractedPages,
          current_page_index: currentIndex >= 0 ? currentIndex : 0,
          folder_ids: folderIds,
          goal: goalString,
          report_type: reportGoal?.documentType || 'report',
          is_update_all: true,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 402) {
          authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.');
          setIsAutoUpdating(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          releaseDocumentLock();
          return;
        }
        if (handleCreditError(errorData)) {
          setIsAutoUpdating(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          releaseDocumentLock();
          return;
        }
        throw new Error(errorData.detail || errorData.message || 'Failed to process update');
      }

      // Response is a streaming keepalive — read full text then parse JSON
      const updateAllText = await response.text();
      const trimmedUpdateText = updateAllText.trim();
      if (!trimmedUpdateText) {
        throw new Error('Empty response from server — the AI service may have timed out. Please try again.');
      }
      let allData;
      try {
        allData = JSON.parse(trimmedUpdateText);
      } catch (parseErr) {
        console.error('❌ [UPDATE_ALL] Failed to parse response:', trimmedUpdateText.substring(0, 500));
        throw new Error('Invalid response from server. Please try again.');
      }

      // Handle errors returned in stream body (processing failures send HTTP 200 with error JSON)
      if (allData.error) {
        if (allData.status_code === 402) {
          authService.notifyCreditRequired(allData.detail?.message || allData.detail || 'Insufficient credits.');
          setIsAutoUpdating(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          releaseDocumentLock();
          return;
        }
        throw new Error(allData.detail || 'Failed to process update');
      }
      console.log('🎯 [UPDATE_ALL] Response:', allData.total_matched, 'of', allData.total_slides, 'pages matched');

      let successCount = 0;
      const totalMatched = allData.total_matched || 0;
      const updatedEditorEntries = []; // Track updated pages for explicit editor sync

      if (allData.edits && allData.edits.length > 0) {
        for (let editIdx = 0; editIdx < allData.edits.length; editIdx++) {
          const edit = allData.edits[editIdx];
          setAutoUpdateProgress({ current: editIdx + 1, total: allData.edits.length });

          try {
            if (!edit.action || !['create', 'update'].includes(edit.action)) {
              console.warn(`⚠️ [UPDATE_ALL] Skipping edit with unknown action: ${edit.action}`);
              continue;
            }

            if (edit.action === 'update') {
              const fullIndex = aiIndexToFullIndex[edit.slide_index];
              const originalPage = pages[fullIndex];
              if (!originalPage) continue;

              let editedContent = edit.content || edit.slide_data?.content || '';

              // Process <chart-config> tags into rendered images
              const chartConfigRegex = /<chart-config>([\s\S]*?)<\/chart-config>/g;
              const chartMatches = [...editedContent.matchAll(chartConfigRegex)];
              if (chartMatches.length > 0) {
                console.log(`📊 [UPDATE_ALL] Processing ${chartMatches.length} charts in page ${edit.slide_index}`);
                for (const match of chartMatches) {
                  try {
                    const chartConfig = JSON.parse(match[1]);
                    const dataUrl = await renderChartToImage(chartConfig);
                    let altText = chartConfig.options?.plugins?.title?.text || 'Chart';
                    if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                      const labels = chartConfig.data.labels;
                      const summary = chartConfig.data.datasets.map(ds => {
                        return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                      }).join('; ');
                      altText += ` | Data: ${summary}`;
                    }
                    const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                    editedContent = editedContent.replace(match[0], imgHtml);
                  } catch (chartErr) {
                    console.error(`❌ [UPDATE_ALL] Failed to render chart on page ${edit.slide_index}:`, chartErr);
                    editedContent = editedContent.replace(match[0], '<!-- Chart rendering failed -->');
                  }
                }
              }

              // Restore images and embeds using the SAME extraction maps from before the API call
              // (re-extracting would generate different Date.now()-based placeholder IDs that won't match AI output)
              const extraction = updateAllExtractionMaps[originalPage.id] || extractImages(originalPage.content || '');
              const restoredContent = restoreImages(editedContent, extraction.imageMap, extraction.embedMap, extraction.chartConfigMap);

              updatePageContent(originalPage.id, restoredContent);
              // Sync title if AI returned an updated one (fixes title drift after manual edits)
              const newTitle = edit.topic || edit.slide_data?.title;
              if (newTitle) updatePageTitle(originalPage.id, newTitle);
              updatedEditorEntries.push({ id: originalPage.id, content: restoredContent });
              successCount++;
              console.log(`✅ [UPDATE_ALL] Page ${edit.slide_index + 1} updated successfully`);
            }
          } catch (editErr) {
            console.error(`❌ [UPDATE_ALL] Error applying edit for page ${edit.slide_index}:`, editErr);
          }
        }
      }

      // Force-sync Tiptap editors to ensure UI reflects new content
      // (React state→prop→useEffect chain can miss updates due to HTML normalization differences)
      if (updatedEditorEntries.length > 0) {
        setTimeout(() => {
          updatedEditorEntries.forEach(({ id, content }) => {
            const editorInstance = editorRefsMap.current[id];
            if (editorInstance?.setContent) {
              editorInstance.setContent(markdownToHtml(content));
            }
          });
        }, 150);
      }

      // Show completion message
      const failCount = (totalMatched || aiPages.length) - successCount;
      if (failCount <= 0) {
        Alert.alert('Update Complete', `Successfully updated all ${successCount} sections.`);
      } else {
        Alert.alert('Update Complete', `Updated ${successCount} sections. ${failCount} sections failed to update.`);
      }

    } catch (error) {
      console.error('Update All failed:', error);
      Alert.alert('Error', 'Failed to update all pages. Please try again.');
    } finally {
      setIsAutoUpdating(false);
      setAutoUpdateProgress({ current: 0, total: 0 });
      releaseDocumentLock();
    }
  }, [isAutoUpdating, pages, selectedFolders, apiConfig, reportGoal, updatePageContent, requestDocumentLock, releaseDocumentLock, currentPageId, setPages]);

  // Copy entire report to clipboard with HTML formatting for MS Word compatibility
  const handleCopyToClipboard = useCallback(async () => {
    try {
      // Combine all pages content as HTML for rich formatting
      const pagesHtml = pages
        .sort((a, b) => a.order - b.order)
        .map(page => {
          // Keep HTML content as-is for formatting
          const content = page.content || '';
          return `<h2 style="font-size: 18px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; color: #333;">${page.title}</h2>\n${content}`;
        })
        .join('\n<hr style="margin: 24px 0; border: none; border-top: 1px solid #ddd;">\n');

      // Only include title if it's different from goal (to avoid duplication)
      const shouldIncludeTitle = !reportGoal?.purpose ||
        editableTitle.toLowerCase().trim() !== reportGoal.purpose.toLowerCase().trim().substring(0, editableTitle.length);

      // Create Word-compatible HTML with proper namespace and styling
      const fullHtml = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<meta name="ProgId" content="Word.Document">
<style>
body { font-family: 'Times New Roman', Georgia, serif; font-size: 12pt; line-height: 1.6; color: #000; font-style: normal; }
h1 { font-size: 24pt; font-weight: bold; margin-bottom: 16px; color: #000; font-style: normal; }
h2 { font-size: 16pt; font-weight: bold; margin-top: 24px; margin-bottom: 12px; color: #333; font-style: normal; }
h3 { font-size: 14pt; font-weight: bold; margin-top: 18px; margin-bottom: 8px; font-style: normal; }
p { margin-bottom: 12px; text-align: justify; font-style: normal; }
ul, ol { margin-left: 24px; margin-bottom: 12px; }
li { margin-bottom: 6px; font-style: normal; }
strong, b { font-weight: bold; font-style: normal; }
em, i { font-style: italic; }
hr { margin: 24px 0; border: none; border-top: 1px solid #ddd; }
.goal { color: #444; margin-bottom: 24px; padding: 12px 16px; background: #f0f7ff; border-left: 4px solid #007acc; font-style: normal; }
</style>
</head>
<body>
${shouldIncludeTitle ? `<h1>${editableTitle}</h1>` : ''}
${reportGoal?.purpose ? `<p class="goal"><strong>Goal:</strong> ${reportGoal.purpose}</p>` : ''}
${pagesHtml}
</body>
</html>`;

      // Also create plain text version for fallback
      const plainText = pages
        .sort((a, b) => a.order - b.order)
        .map(page => {
          let text = page.content || '';
          // Convert HTML to plain text
          text = text.replace(/<br\s*\/?>/gi, '\n');
          text = text.replace(/<\/p>/gi, '\n\n');
          text = text.replace(/<\/h[1-6]>/gi, '\n\n');
          text = text.replace(/<\/li>/gi, '\n');
          text = text.replace(/<li>/gi, '• ');
          text = text.replace(/<[^>]*>/g, '');
          text = text.replace(/&nbsp;/g, ' ')
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'");
          return `${page.title}\n${'='.repeat(page.title.length)}\n\n${text.trim()}`;
        })
        .join('\n\n---\n\n');

      const titleLine = shouldIncludeTitle ? `${editableTitle}\n${'='.repeat(editableTitle.length)}\n\n` : '';
      const fullPlainText = `${titleLine}${reportGoal?.purpose ? `Goal: ${reportGoal.purpose}\n\n` : ''}${plainText}`;

      if (Platform.OS === 'web' && navigator.clipboard) {
        // Try to write HTML for rich paste support (MS Word compatible)
        try {
          const clipboardItem = new ClipboardItem({
            'text/html': new Blob([fullHtml], { type: 'text/html' }),
            'text/plain': new Blob([fullPlainText], { type: 'text/plain' })
          });
          await navigator.clipboard.write([clipboardItem]);
          Alert.alert('Copied!', 'Report copied to clipboard with formatting');
        } catch (htmlErr) {
          // Fallback to plain text if HTML clipboard fails
          console.warn('HTML clipboard failed, using plain text:', htmlErr);
          await navigator.clipboard.writeText(fullPlainText);
          Alert.alert('Copied!', 'Report copied to clipboard as plain text');
        }
      } else {
        Alert.alert('Info', 'Clipboard copy is available on web only');
      }
    } catch (err) {
      console.error('Failed to copy:', err);
      Alert.alert('Error', 'Failed to copy to clipboard');
    }
  }, [pages, editableTitle, reportGoal]);

  // Load report from server
  const handleLoadReport = useCallback((report) => {
    console.log('[HANDLE_LOAD_REPORT] ===== handleLoadReport ENTRY =====');
    console.log('[HANDLE_LOAD_REPORT] This function was called!');
    console.log('[HANDLE_LOAD_REPORT] report param:', report);
    try {
      console.log('[LOAD_REPORT] ========= LOADING REPORT =========');
      setIsLoadingReport(true); // Prevent goal modal from showing
      console.log('[LOAD_REPORT] Report object:', JSON.stringify(report, null, 2).slice(0, 500));
      console.log('[LOAD_REPORT] Report pages count:', report?.pages?.length);

      if (report.pages && report.pages.length > 0) {
        const loadedPages = report.pages.map((page, index) => ({
          id: page.id || `page_${Date.now()}_${index}`,
          order: page.order || index + 1,
          title: page.title || `Page ${index + 1}`,
          content: page.content || '',
          wordCount: (page.content || '').trim().split(/\s+/).filter(w => w.length > 0).length,
          hasUnsavedChanges: false
        }));
        console.log('[LOAD_REPORT] Mapped pages:', loadedPages.map(p => ({ id: p.id, title: p.title })));
        console.log('[LOAD_REPORT] Calling setPages...');
        setPages(loadedPages);
        console.log('[LOAD_REPORT] setPages called successfully');

        // Bulk pre-cache S3 images (fire-and-forget, matches PresentationComposer pattern)
        _preCachePageImages(loadedPages);

        if (loadedPages.length > 0) {
          console.log('[LOAD_REPORT] Setting currentPageId to:', loadedPages[0].id);
          setCurrentPageId(loadedPages[0].id);
        }
      } else {
        console.log('[LOAD_REPORT] No pages found in report, creating default page');
        const defaultPage = {
          id: `page_${Date.now()}`,
          order: 1,
          title: 'Introduction',
          content: '',
          wordCount: 0,
          hasUnsavedChanges: false
        };
        setPages([defaultPage]);
        setCurrentPageId(defaultPage.id);
      }

      console.log('[LOAD_REPORT] Setting report metadata...');
      setCurrentReportId(report.id);
      setEditableTitle(report.title || 'Untitled Report');
      updateReportMetadata({ title: report.title });
      if (report.goal) {
        setReportGoal({ purpose: report.goal });
      }

      // Close goal setting modal if it was open
      setShowGoalSetting(false);

      console.log('[LOAD_REPORT] ========= REPORT LOADED SUCCESSFULLY =========');
    } catch (error) {
      console.error('[LOAD_REPORT] ERROR:', error);
      console.error('[LOAD_REPORT] Error stack:', error.stack);
    } finally {
      setIsLoadingReport(false);
    }
  }, [setPages, setCurrentPageId, updateReportMetadata, setReportGoal]);

  // Keep ref updated with latest handleLoadReport
  useEffect(() => {
    console.log('[REF_UPDATE] Updating loadReportRef with handleLoadReport');
    console.log('[REF_UPDATE] handleLoadReport type:', typeof handleLoadReport);
    loadReportRef.current = handleLoadReport;
    console.log('[REF_UPDATE] loadReportRef.current is now:', typeof loadReportRef.current);
  }, [handleLoadReport]);

  // Stable callback that always uses the latest handleLoadReport
  const stableLoadReport = useCallback((report) => {
    console.log('[STABLE_LOAD_REPORT] ===== stableLoadReport called =====');
    console.log('[STABLE_LOAD_REPORT] report:', report?.id, report?.title);
    console.log('[STABLE_LOAD_REPORT] loadReportRef:', loadReportRef);
    console.log('[STABLE_LOAD_REPORT] loadReportRef.current:', loadReportRef.current);
    console.log('[STABLE_LOAD_REPORT] loadReportRef.current type:', typeof loadReportRef.current);

    if (loadReportRef.current) {
      console.log('[STABLE_LOAD_REPORT] Calling loadReportRef.current(report)...');
      try {
        loadReportRef.current(report);
        console.log('[STABLE_LOAD_REPORT] loadReportRef.current(report) completed');
      } catch (err) {
        console.error('[STABLE_LOAD_REPORT] ERROR in loadReportRef.current:', err);
        console.error('[STABLE_LOAD_REPORT] Error stack:', err.stack);
      }
    } else {
      console.error('[STABLE_LOAD_REPORT] ERROR: loadReportRef.current is null/undefined!');
    }
    console.log('[STABLE_LOAD_REPORT] ===== stableLoadReport END =====');
  }, []);

  // Create new report
  const handleCreateNew = useCallback(() => {
    // Clear the parent's initialReport to prevent useEffect from overriding
    if (onClearReport) {
      onClearReport();
    }
    setPages([{
      id: `page_${Date.now()}`,
      order: 1,
      title: 'Page 1',
      content: '',
      wordCount: 0,
      hasUnsavedChanges: false
    }]);
    setCurrentReportId(null);
    setEditableTitle('Untitled Report');
    setReportGoal(null);
    updateReportMetadata({ title: 'Untitled Report' });
    setShowGoalSetting(true);
  }, [setPages, updateReportMetadata, onClearReport]);

  // Get vault name(s) for display
  const vaultDisplayName = useMemo(() => {
    if (!selectedFolders || selectedFolders.length === 0) return null;
    if (selectedFolders.length === 1) {
      return selectedFolders[0].name || selectedFolders[0].folder_name || 'Data Store';
    }
    return `${selectedFolders.length} data stores`;
  }, [selectedFolders]);

  // Render markdown HTML for preview
  const renderedContent = useMemo(() => {
    return markdownToHtml(currentPage?.content || '', safeTheme.isDark);
  }, [currentPage?.content, safeTheme.isDark]);


  // Mini page preview for thumbnail view - shows layout structure + text snippet
  const renderMiniPagePreview = (page, previewWidth = 180) => {
    const previewHeight = Math.floor(previewWidth * 0.7); // Slightly taller for layout visibility
    const hasContent = page?.content && page.content.length > 0;
    const isGenerating = page?.isGenerating;
    const layout = REPORT_PAGE_LAYOUTS[page?.layout] || REPORT_PAGE_LAYOUTS.single_column;

    // Extract plain text snippet from content (strip markdown/HTML)
    const getTextSnippet = (content) => {
      if (!content) return '';
      const plainText = content
        .replace(/<[^>]*>/g, '')
        .replace(/#{1,6}\s*/g, '')
        .replace(/\*\*|__/g, '')
        .replace(/\*|_/g, '')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/`{1,3}[^`]*`{1,3}/g, '')
        .replace(/\n+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      return plainText.substring(0, 80) + (plainText.length > 80 ? '...' : '');
    };

    // Render layout structure visualization
    const renderLayoutStructure = () => {
      const columns = layout.columns || 1;
      const hasImage = layout.hasImageSlot;
      const imagePos = layout.imagePosition;

      // Layout visualization with placeholder blocks
      if (layout.id === 'single_column' || layout.id === 'ai_auto') {
        return (
          <View style={{ flex: 1, padding: 4 }}>
            <View style={{ height: 6, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 4, width: '70%' }} />
            <View style={{ height: 4, backgroundColor: '#F3F4F6', borderRadius: 2, marginBottom: 2 }} />
            <View style={{ height: 4, backgroundColor: '#F3F4F6', borderRadius: 2, marginBottom: 2 }} />
            <View style={{ height: 4, backgroundColor: '#F3F4F6', borderRadius: 2, width: '85%' }} />
          </View>
        );
      }

      if (columns === 2 && hasImage) {
        return (
          <View style={{ flex: 1, flexDirection: 'row', padding: 4, gap: 4 }}>
            {imagePos === 'left' && (
              <View style={{ width: '35%', backgroundColor: '#E0E7FF', borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                <MaterialIcons name="image" size={12} color="#6366F1" />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <View style={{ height: 5, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3, width: '80%' }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1, marginBottom: 2 }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
            </View>
            {imagePos === 'right' && (
              <View style={{ width: '35%', backgroundColor: '#E0E7FF', borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                <MaterialIcons name="image" size={12} color="#6366F1" />
              </View>
            )}
          </View>
        );
      }

      if (columns === 2) {
        return (
          <View style={{ flex: 1, flexDirection: 'row', padding: 4, gap: 4 }}>
            <View style={{ flex: 1 }}>
              <View style={{ height: 4, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3 }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1, marginBottom: 2 }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ height: 4, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3 }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1, marginBottom: 2 }} />
              <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
            </View>
          </View>
        );
      }

      if (columns === 3) {
        return (
          <View style={{ flex: 1, flexDirection: 'row', padding: 4, gap: 3 }}>
            {[1, 2, 3].map((col) => (
              <View key={col} style={{ flex: 1 }}>
                <View style={{ height: 4, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3 }} />
                <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1, marginBottom: 2 }} />
                <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
              </View>
            ))}
          </View>
        );
      }

      if (layout.id === 'hero_section') {
        return (
          <View style={{ flex: 1, padding: 4 }}>
            <View style={{ height: '40%', backgroundColor: '#E0E7FF', borderRadius: 2, marginBottom: 4, alignItems: 'center', justifyContent: 'center' }}>
              <MaterialIcons name="image" size={14} color="#6366F1" />
            </View>
            <View style={{ height: 5, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3, width: '60%' }} />
            <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
          </View>
        );
      }

      // Default fallback
      return (
        <View style={{ flex: 1, padding: 4 }}>
          <View style={{ height: 5, backgroundColor: '#E5E7EB', borderRadius: 2, marginBottom: 3, width: '65%' }} />
          <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1, marginBottom: 2 }} />
          <View style={{ height: 3, backgroundColor: '#F3F4F6', borderRadius: 1 }} />
        </View>
      );
    };

    return (
      <View
        style={{
          width: previewWidth,
          height: previewHeight,
          backgroundColor: '#ffffff',
          borderRadius: 4,
          overflow: 'hidden',
          position: 'relative',
          borderWidth: 1,
          borderColor: isGenerating ? '#3B82F6' : '#e0e0e0',
        }}
      >
        {/* Generating overlay */}
        {isGenerating && (
          <View style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            zIndex: 10,
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <ActivityIndicator size="small" color="#3B82F6" />
            <Text style={{ fontSize: 8, color: '#3B82F6', marginTop: 4 }}>Generating...</Text>
          </View>
        )}

        {/* Layout structure visualization at top */}
        <View style={{ height: '55%' }}>
          {renderLayoutStructure()}
        </View>

        {/* Content snippet at bottom */}
        <View style={{
          height: '45%',
          borderTopWidth: 1,
          borderTopColor: '#F3F4F6',
          paddingHorizontal: 4,
          paddingVertical: 3,
        }}>
          {isGenerating ? (
            <Text style={{ fontSize: 8, color: '#3B82F6', fontStyle: 'italic' }}>
              {page.outline ? `Outline: ${page.outline.slice(0, 40)}...` : 'Generating content...'}
            </Text>
          ) : hasContent ? (
            <Text
              numberOfLines={2}
              style={{
                fontSize: 8,
                color: '#666',
                lineHeight: 11,
              }}
            >
              {getTextSnippet(page.content)}
            </Text>
          ) : (
            <Text style={{ fontSize: 8, color: '#aaa', fontStyle: 'italic' }}>
              Empty page
            </Text>
          )}
        </View>

        {/* Layout badge */}
        <View style={{
          position: 'absolute',
          top: 3,
          left: 3,
          backgroundColor: 'rgba(59, 130, 246, 0.9)',
          paddingHorizontal: 4,
          paddingVertical: 1,
          borderRadius: 2,
        }}>
          <Text style={{ color: '#fff', fontSize: 7, fontWeight: '600' }}>
            {layout.columns === 1 ? '1 Col' : layout.columns === 2 ? '2 Col' : layout.columns === 3 ? '3 Col' : layout.name?.split(' ')[0]}
          </Text>
        </View>

        {/* Page number overlay */}
        <View style={{
          position: 'absolute',
          bottom: 3,
          right: 3,
          backgroundColor: 'rgba(0,0,0,0.6)',
          paddingHorizontal: 5,
          paddingVertical: 1,
          borderRadius: 2,
        }}>
          <Text style={{ color: '#fff', fontSize: 8, fontWeight: '600' }}>
            {page?.order || 1}
          </Text>
        </View>
      </View>
    );
  };

  // Render page item in sidebar
  const renderPageItem = (page, index) => {
    const isActive = currentPageId === page.id;
    const isEditing = editingPageTitleId === page.id;
    const isGenerating = page.isGenerating;
    const hasError = page.hasError;

    // Thumbnail View Mode
    if (pagePanelViewMode === 'thumbnail') {
      return (
        <View key={page.id} style={[styles.pageItemContainer, page.hidden && { opacity: 0.45 }]}>
          <TouchableOpacity
            style={[
              styles.pageThumbnailItem,
              isActive && styles.pageThumbnailItemActive,
              {
                borderColor: hasError ? '#ef4444' : isActive ? safeTheme.primary : safeTheme.borderColor || '#e0e0e0',
                backgroundColor: hasError ? '#fef2f2' : isGenerating ? '#f0f9ff' : isActive ? safeTheme.primary + '10' : 'transparent',
              },
            ]}
            onPress={() => {
              if (actionBtnGuard.current) { actionBtnGuard.current = false; return; }
              handleSelectPage(page.id);
            }}
            activeOpacity={0.7}
          >
            {/* 🆕 Loading/Error State Overlay */}
            {isGenerating ? (
              <View style={styles.thumbnailGeneratingOverlay}>
                <ActivityIndicator size="small" color="#3b82f6" />
                <Text style={styles.thumbnailGeneratingText}>Generating...</Text>
              </View>
            ) : hasError ? (
              <View style={styles.thumbnailErrorOverlay}>
                <MaterialIcons name="error-outline" size={24} color="#ef4444" />
                <Text style={styles.thumbnailErrorText}>Failed</Text>
              </View>
            ) : (
              /* Mini Page Preview */
              renderMiniPagePreview(page, 100)
            )}

            {/* Title below thumbnail */}
            <View style={{ marginTop: 8, paddingHorizontal: 4, width: '100%' }}>
              {isEditing ? (
                <TextInput
                  style={[styles.pageItemTitleInput, { fontSize: 11 }]}
                  value={editingPageTitleText}
                  onChangeText={setEditingPageTitleText}
                  onBlur={savePageTitle}
                  onSubmitEditing={savePageTitle}
                  autoFocus
                />
              ) : (
                <Text style={[styles.pageItemTitle, { fontSize: 11, textAlign: 'center', color: hasError ? '#dc2626' : undefined }]} numberOfLines={1}>
                  {page.title}
                </Text>
              )}
            </View>

            {/* Hover/Active Actions - hide during generation */}
            {!isGenerating && (
              <View style={[styles.pageThumbnailActions, { opacity: isActive ? 1 : 0.7 }]}>
                {!isReadOnly && (
                  <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); togglePageHidden(page.id); }} style={{ padding: 3 }} title={page.hidden ? "Show Page" : "Hide Page"}>
                    <Ionicons name={page.hidden ? "eye-off-outline" : "eye-outline"} size={12} color="#888" />
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); setEditOutlinePage(page); }} style={{ padding: 3 }}>
                  <MaterialIcons name="edit" size={12} color="#888" />
                </TouchableOpacity>
                {pages.length > 1 && (
                  <TouchableOpacity
                    onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDeletePage(page.id); }}
                    style={{ padding: 3 }}
                  >
                    <MaterialIcons name="delete" size={12} color="#f44336" />
                  </TouchableOpacity>
                )}
              </View>
            )}
          </TouchableOpacity>

          {/* Insert between pages - opens Add Page modal */}
          <TouchableOpacity
            style={styles.insertBetweenBtn}
            onPress={() => handleOpenAddPageModal(index + 1)}
          >
            <MaterialIcons name="add" size={12} color="#2196F3" />
          </TouchableOpacity>
        </View>
      );
    }

    // List View Mode (Original)
    return (
      <View key={page.id} style={[styles.pageItemContainer, page.hidden && { opacity: 0.45 }]}>
        {/* Use View instead of TouchableOpacity for outer container to allow inner buttons to work */}
        <View style={[styles.pageItem, isActive && styles.pageItemActive, hasError && { borderLeftColor: '#ef4444', borderLeftWidth: 3 }]}>
          {/* Page selector area - only this part selects the page */}
          <TouchableOpacity
            style={styles.pageSelectArea}
            onPress={() => handleSelectPage(page.id)}
            activeOpacity={0.7}
          >
            <View style={[
              styles.pageNumber,
              isActive && styles.pageNumberActive,
              isGenerating && { backgroundColor: '#dbeafe' },
              hasError && { backgroundColor: '#fee2e2' },
            ]}>
              {isGenerating ? (
                <ActivityIndicator size={10} color="#3b82f6" />
              ) : hasError ? (
                <MaterialIcons name="error-outline" size={12} color="#ef4444" />
              ) : (
                <Text style={[styles.pageNumberText, isActive && styles.pageNumberTextActive]}>
                  {index + 1}
                </Text>
              )}
            </View>

            {isEditing ? (
              <TextInput
                style={styles.pageItemTitleInput}
                value={editingPageTitleText}
                onChangeText={setEditingPageTitleText}
                onBlur={savePageTitle}
                onSubmitEditing={savePageTitle}
                autoFocus
              />
            ) : (
              <Text style={[styles.pageItemTitle, isActive && styles.pageItemTitleActive, hasError && { color: '#dc2626' }]} numberOfLines={1}>
                {page.title}
                {isGenerating && <Text style={{ color: '#3b82f6', fontStyle: 'italic' }}> (generating...)</Text>}
              </Text>
            )}
          </TouchableOpacity>

          {/* Actions - separate from page selection, hide during generation */}
          {!isGenerating && (
            <View style={styles.pageItemActions}>
              {!isReadOnly && (
                <TouchableOpacity
                  onPress={() => togglePageHidden(page.id)}
                  style={styles.pageActionBtn}
                  title={page.hidden ? "Show Page" : "Hide Page"}
                >
                  <Ionicons name={page.hidden ? "eye-off-outline" : "eye-outline"} size={14} color="#888" />
                </TouchableOpacity>
              )}
              <TouchableOpacity
                onPress={() => setEditOutlinePage(page)}
                style={styles.pageActionBtn}
              >
                <MaterialIcons name="edit" size={14} color="#888" />
              </TouchableOpacity>
              {pages.length > 1 && (
                <TouchableOpacity
                  onPress={() => {
                    console.log('[SIDEBAR] Delete button clicked for page:', page.id);
                    handleDeletePage(page.id);
                  }}
                  style={[styles.pageActionBtn, styles.deleteBtn]}
                >
                  <MaterialIcons name="delete" size={14} color="#f44336" />
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>

        {/* Insert between pages - opens Add Page modal */}
        <TouchableOpacity
          style={styles.insertBetweenBtn}
          onPress={() => handleOpenAddPageModal(index + 1)}
        >
          <MaterialIcons name="add" size={12} color="#2196F3" />
        </TouchableOpacity>
      </View>
    );
  };

  if (!visible) return null;

  // Handle Enter-to-send on web, Shift+Enter for newline
  const handleKeyPress = (e) => {
    if (Platform.OS === 'web') {
      const key = e?.nativeEvent?.key;
      if (key === 'Enter') {
        const shift = e?.shiftKey || e?.nativeEvent?.shiftKey;
        if (!shift && chatInput.trim() && !isAiProcessing && !isAiLocked) {
          e.preventDefault();
          e.stopPropagation();
          handleAgentEdit();
        }
      }
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={() => setShowCloseConfirmModal(true)}>
      <View style={[styles.container, { backgroundColor: safeTheme.background }]}>

        {/* Save Name Modal */}
        <Modal visible={showSaveModal} transparent animationType="fade" onRequestClose={() => setShowSaveModal(false)}>
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)' }}>
            <View style={{ backgroundColor: safeTheme.background || '#fff', borderRadius: 12, padding: 20, width: '85%', maxWidth: 400 }}>
              <Text style={{ fontSize: 16, fontWeight: '600', color: safeTheme.text, marginBottom: 12 }}>Save Report</Text>
              <Text style={{ fontSize: 13, color: safeTheme.textSecondary, marginBottom: 6 }}>Name</Text>
              <TextInput
                style={{ borderWidth: 1, borderColor: safeTheme.borderColor || '#E5E7EB', borderRadius: 8, padding: 10, fontSize: 14, color: safeTheme.text, marginBottom: 16 }}
                value={editableTitle}
                onChangeText={setEditableTitle}
                autoFocus
              />
              <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 10 }}>
                <TouchableOpacity
                  onPress={() => setShowSaveModal(false)}
                  style={{ paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8, borderWidth: 1, borderColor: safeTheme.borderColor || '#E5E7EB' }}
                >
                  <Text style={{ color: safeTheme.text, fontSize: 14 }}>Cancel</Text>
                </TouchableOpacity>
                {currentReportId && (
                  <TouchableOpacity
                    disabled={isSavingManual}
                    onPress={() => { setShowSaveModal(false); handleSaveAsCopy(); }}
                    style={{ paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8, borderWidth: 1, borderColor: safeTheme.primary || '#6366F1', backgroundColor: 'transparent', opacity: isSavingManual ? 0.5 : 1 }}
                  >
                    <Text style={{ color: safeTheme.primary || '#6366F1', fontSize: 14, fontWeight: '600' }}>Save a Copy</Text>
                  </TouchableOpacity>
                )}
                {!isReadOnly && (
                  <TouchableOpacity
                    onPress={() => { setShowSaveModal(false); handleSaveToServer(editableTitle); }}
                    style={{ paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8, backgroundColor: safeTheme.primary || '#6366F1' }}
                  >
                    <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>Save</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          </View>
        </Modal>

        {/* Saving Progress Overlay */}
        {isSavingManual && (
          <View style={{ position: Platform.OS === 'web' ? 'fixed' : 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.35)', zIndex: 99999, justifyContent: 'center', alignItems: 'center' }}>
            <View style={{ backgroundColor: safeTheme.background || '#fff', borderRadius: 16, padding: 28, alignItems: 'center', shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 12, elevation: 8 }}>
              <ActivityIndicator size="large" color={safeTheme.primary || '#6366F1'} />
              <Text style={{ marginTop: 14, fontSize: 15, fontWeight: '600', color: safeTheme.text || '#1F2937' }}>Saving report…</Text>
            </View>
          </View>
        )}

        {/* Header */}
        {mobileViewOnly ? (
          /* Mobile View-Only Top Bar */
          <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: safeTheme.borderColor, backgroundColor: safeTheme.surface }}>
            <TouchableOpacity onPress={() => setShowCloseConfirmModal(true)} style={{ padding: 6 }}>
              <Ionicons name="close" size={22} color={safeTheme.text} />
            </TouchableOpacity>
            {/* Page Navigation */}}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 8 }}>
              <TouchableOpacity
                disabled={currentPageIndex <= 0}
                onPress={() => {
                  if (currentPageIndex > 0) handleSelectPage(pages[currentPageIndex - 1].id);
                }}
                style={{ padding: 4, opacity: currentPageIndex <= 0 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-back" size={18} color={safeTheme.text} />
              </TouchableOpacity>
              <Text style={{ fontSize: 12, color: safeTheme.textSecondary }}>
                {currentPageIndex + 1}/{pages.length}
              </Text>
              <TouchableOpacity
                disabled={currentPageIndex >= pages.length - 1}
                onPress={() => {
                  if (currentPageIndex < pages.length - 1) handleSelectPage(pages[currentPageIndex + 1].id);
                }}
                style={{ padding: 4, opacity: currentPageIndex >= pages.length - 1 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-forward" size={18} color={safeTheme.text} />
              </TouchableOpacity>
            </View>
            {/* Insert Page */}
            <TouchableOpacity
              onPress={() => handleOpenAddPageModal(currentPageIndex + 1)}
              style={{ padding: 6, marginLeft: 4 }}
            >
              <Ionicons name="add-circle-outline" size={22} color={safeTheme.primary || '#6366F1'} />
            </TouchableOpacity>
            {/* Arrange Pages */}
            <TouchableOpacity
              onPress={() => setShowArrangeModal(true)}
              style={{ padding: 6 }}
            >
              <Ionicons name="swap-horizontal-outline" size={20} color={safeTheme.text} />
            </TouchableOpacity>
            <View style={{ flex: 1 }} />
            {currentReportId && isItemOwner && (
              <ShareButton
                contentType="report"
                sourceId={currentReportId}
                title={reportMetadata?.title || 'Report'}
                theme={safeTheme}
                showLabel={false}
                apiConfig={apiConfig}
                authToken={authToken}
                userEmail={userEmail}
                userType={userType}
                onUpgrade={onOpenCredits}
              />
            )}
            <TouchableOpacity onPress={openSaveModal} style={{ padding: 6 }}>
              <Ionicons name="save-outline" size={20} color={safeTheme.primary || '#6366F1'} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowPreviewModal(true)} style={{ padding: 6 }}>
              <Ionicons name="eye-outline" size={20} color={safeTheme.text} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowExportModal(true)} style={{ padding: 6 }}>
              <Ionicons name="download-outline" size={20} color={safeTheme.text} />
            </TouchableOpacity>
          </View>
        ) : (
          <View style={[styles.header, { borderBottomColor: safeTheme.borderColor }]}>
            <TouchableOpacity onPress={() => setShowCloseConfirmModal(true)} style={styles.closeButton}>
              <Ionicons name="close" size={24} color={safeTheme.text} />
            </TouchableOpacity>

            {/* Vault Name Badge — tap to open the folder detail popup */}
            {vaultDisplayName && (
              <TouchableOpacity style={styles.vaultBadge} onPress={() => setShowFolderDetailModal(true)}>
                <MaterialIcons name="folder" size={14} color="#666" />
                <Text style={styles.vaultBadgeText}>{vaultDisplayName}</Text>
              </TouchableOpacity>
            )}
            {currentReportId && (
              <CollaborationLockIndicator
                documentLock={documentLock}
                currentPageLock={pageLocks[pages.findIndex(p => p.id === currentPageId)]}
                ownClientId={ydoc?.clientID}
                type="report"
              />
            )}

            {currentReportId && (
              <CollaborationLockIndicator
                documentLock={documentLock}
                currentPageLock={pageLocks[pages.findIndex(p => p.id === currentPageId)]}
                ownClientId={ydoc?.clientID}
                type="report"
              />
            )}

            {isEditingTitle ? (
              <TextInput
                style={[styles.titleInput, { color: safeTheme.text }]}
                value={editableTitle}
                onChangeText={setEditableTitle}
                onBlur={handleTitleSave}
                onSubmitEditing={handleTitleSave}
                autoFocus
              />
            ) : (
              <TouchableOpacity onPress={() => setIsEditingTitle(true)} style={styles.titleContainer}>
                <Text style={[styles.title, { color: safeTheme.text }]} numberOfLines={1}>
                  {editableTitle}
                </Text>
              </TouchableOpacity>
            )}

            <View style={styles.headerRight}>
              {isSaving && <ActivityIndicator size="small" color={safeTheme.primary} />}

              {/* Open Reports */}
              <TouchableOpacity
                style={styles.ghostBtn}
                onPress={() => setShowReportList(true)}
                title="My Reports"
              >
                <Ionicons name="folder-open-outline" size={20} color={safeTheme.text} />
              </TouchableOpacity>

              {/* Insert Image Button removed, available in Tiptap format toolbar */}

              {/* Insert Chart Button */}
              <Tooltip text="Insert Chart" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={() => setShowChartStudio(true)}
                >
                  <MaterialIcons name="bar-chart" size={20} color={safeTheme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* Insert AI Image Button */}
              <Tooltip text="Generate AI Image" theme={safeTheme}>
                <TouchableOpacity
                  style={[styles.ghostBtn, { flexDirection: 'row', gap: 4, alignItems: 'center' }]}
                  onPress={() => setShowAIImageModal(true)}
                >
                  <Ionicons name="image-outline" size={18} color={safeTheme.text} />
                  <Text style={{ fontSize: 13, color: safeTheme.text, fontWeight: '500' }}>AI Image</Text>
                </TouchableOpacity>
              </Tooltip>

              {/* Collaboration Button — HIDDEN for now (real-time co-editing is an
                  advanced, not-fully-tested feature kept for future). Flip `false`. */}
              {false && currentReportId && (
                <Tooltip text="Collaborate" theme={safeTheme}>
                  <TouchableOpacity
                    style={styles.ghostBtn}
                    onPress={() => setShowCollaborationPanel(true)}
                  >
                    <Ionicons name="people-outline" size={20} color={safeTheme.text} />
                    {collaborators.length > 0 && (
                      <View style={{
                        position: 'absolute', top: -4, right: -4,
                        backgroundColor: '#10B981', borderRadius: 8,
                        width: 16, height: 16, justifyContent: 'center', alignItems: 'center'
                      }}>
                        <Text style={{ color: 'white', fontSize: 10, fontWeight: 'bold' }}>{collaborators.length}</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                </Tooltip>
              )}

              {/* Update ALL Button — HIDDEN: redundant now that the chat agent
                  handles whole-document updates ("update all pages with the
                  latest data"). TODO(cleanup): remove with the legacy edit flow. */}
              {false && (
              <Tooltip text="Update All Pages" theme={safeTheme}>
                <TouchableOpacity
                  style={[
                    {
                      flexDirection: 'row',
                      gap: 6,
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: isAutoUpdating ? '#FCE4EC' : '#E91E63',
                      paddingHorizontal: 14,
                      paddingVertical: 8,
                      borderRadius: 8,
                      opacity: isDocumentLocked ? 0.5 : 1,
                      shadowColor: '#E91E63',
                      shadowOffset: { width: 0, height: 2 },
                      shadowOpacity: 0.3,
                      shadowRadius: 4,
                      elevation: 4,
                    }
                  ]}
                  onPress={handleAutoUpdate}
                  disabled={isAutoUpdating || isAiProcessing || isDocumentLocked}
                >
                  {isAutoUpdating ? (
                    <>
                      <ActivityIndicator size="small" color="#C2185B" />
                      <Text style={{ fontSize: 12, color: '#C2185B', fontWeight: '700' }}>
                        {autoUpdateProgress.current}/{autoUpdateProgress.total}
                      </Text>
                      <View style={{ width: 40, height: 4, backgroundColor: '#F8BBD0', borderRadius: 2, overflow: 'hidden' }}>
                        <View
                          style={{
                            height: '100%',
                            backgroundColor: '#E91E63',
                            borderRadius: 2,
                            width: `${(autoUpdateProgress.current / autoUpdateProgress.total) * 100}%`
                          }}
                        />
                      </View>
                    </>
                  ) : (
                    <>
                      <Ionicons name="refresh" size={16} color="#fff" />
                      <Text style={{ fontSize: 13, color: '#fff', fontWeight: '700', letterSpacing: 0.5 }}>Update ALL</Text>
                    </>
                  )}
                </TouchableOpacity>
              </Tooltip>
              )}

              {/* Document Style (moved from per-page toolbar) */}
              <Tooltip text="Change document style" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={() => setShowStylePickerModal(true)}
                >
                  <MaterialIcons name="palette" size={18} color="#9C27B0" />
                </TouchableOpacity>
              </Tooltip>

              {/* Letterhead / Headers & Footers (moved from per-page toolbar) */}
              <Tooltip text="Letterhead, headers & footers" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={() => setShowHeaderFooterModal(true)}
                >
                  <MaterialIcons name="view-headline" size={18} color={safeTheme.textSecondary || '#666'} />
                </TouchableOpacity>
              </Tooltip>

              <View style={{ width: 1, height: 16, backgroundColor: '#E5E7EB', marginHorizontal: 4 }} />

              {/* Save (Primary) */}
              <TouchableOpacity
                style={styles.primaryBtn}
                onPress={openSaveModal}
              >
                <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
                <Text style={styles.primaryBtnText}>Save</Text>
              </TouchableOpacity>

              {/* Copy to Clipboard */}
              <Tooltip text="Copy" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={handleCopyToClipboard}
                >
                  <Ionicons name="copy-outline" size={20} color={safeTheme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* Preview All Pages */}
              <Tooltip text="Preview" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={() => setShowPreviewModal(true)}
                >
                  <Ionicons name="eye-outline" size={20} color={safeTheme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* Export */}
              <Tooltip text="Export" theme={safeTheme}>
                <TouchableOpacity
                  style={styles.ghostBtn}
                  onPress={() => setShowExportModal(true)}
                >
                  <Ionicons name="download-outline" size={20} color={safeTheme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* Share Button - only show for saved reports owned by current user */}
              {currentReportId && isItemOwner && (
                <ShareButton
                  contentType="report"
                  sourceId={currentReportId}
                  title={reportMetadata?.title || 'Report'}
                  theme={safeTheme}
                  showLabel={false}
                  apiConfig={apiConfig}
                  authToken={authToken}
                  userEmail={userEmail}
                  userType={userType}
                  onUpgrade={onOpenCredits}
                />
              )}
            </View>
          </View>
        )}

        {/* Main Content Area */}
        <View style={mobileViewOnly ? styles.mainContentMobile : styles.mainContent}>

          {/* Mobile Segmented Control - Toggle between Tools and AI Chat */}
          {mobileViewOnly && pages.length > 0 && (
            <View style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 12,
              paddingVertical: 6,
              backgroundColor: safeTheme.surface || '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.borderColor || '#E5E7EB',
            }}>
              <View style={{
                flex: 1,
                flexDirection: 'row',
                backgroundColor: '#F3F4F6',
                borderRadius: 10,
                padding: 3,
              }}>
                <TouchableOpacity
                  style={{
                    flex: 1,
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingVertical: 7,
                    borderRadius: 8,
                    backgroundColor: mobileEditMode === 'tools' ? (safeTheme.primary || '#6366F1') : 'transparent',
                  }}
                  onPress={() => setMobileEditMode('tools')}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="create-outline"
                    size={14}
                    color={mobileEditMode === 'tools' ? '#fff' : '#6B7280'}
                    style={{ marginRight: 5 }}
                  />
                  <Text style={{
                    fontSize: 13,
                    fontWeight: '600',
                    color: mobileEditMode === 'tools' ? '#fff' : '#6B7280',
                  }}>Editor</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={{
                    flex: 1,
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingVertical: 7,
                    borderRadius: 8,
                    backgroundColor: mobileEditMode === 'chat' ? (safeTheme.primary || '#6366F1') : 'transparent',
                  }}
                  onPress={() => setMobileEditMode('chat')}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="sparkles"
                    size={14}
                    color={mobileEditMode === 'chat' ? '#fff' : '#6B7280'}
                    style={{ marginRight: 5 }}
                  />
                  <Text style={{
                    fontSize: 13,
                    fontWeight: '600',
                    color: mobileEditMode === 'chat' ? '#fff' : '#6B7280',
                  }}>AI Chat</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Mobile AI Chat Panel - Shown when AI Chat mode is active */}
          {mobileViewOnly && mobileEditMode === 'chat' && pages.length > 0 && (
            <View style={{
              backgroundColor: '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.borderColor || '#E5E7EB',
              paddingHorizontal: 12,
              paddingVertical: 10,
              maxHeight: 320,
            }}>
              {/* Selection chip — only when text is selected; otherwise the agent
                  auto-detects targets from chat, so no banner. */}
              {hasSelection && (
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  marginBottom: 8,
                  paddingHorizontal: 8,
                  paddingVertical: 6,
                  backgroundColor: '#DCFCE7',
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: '#86EFAC',
                }}>
                  <Ionicons name="create-outline" size={14} color="#166534" style={{ marginRight: 6 }} />
                  <Text style={{ fontSize: 11, fontWeight: '600', color: '#166534', flex: 1 }} numberOfLines={1}>
                    Selected text — chat edits apply to it
                  </Text>
                </View>
              )}

              {/* AI Chat Messages */}
              {aiChatMessages.length > 0 && (
                <ScrollView
                  style={{ maxHeight: 190, marginBottom: 8 }}
                  showsVerticalScrollIndicator={true}
                >
                  {aiChatMessages.map(msg => (
                    <View
                      key={msg.id}
                      style={{
                        backgroundColor: msg.actionType === 'user' ? '#F3F4F6' : (msg.actionType === 'create_new' ? '#E8F5E9' : '#E3F2FD'),
                        borderRadius: 6,
                        padding: 6,
                        marginBottom: 4,
                        alignSelf: msg.actionType === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '85%',
                        borderLeftWidth: msg.actionType === 'user' ? 0 : 3,
                        borderLeftColor: msg.actionType === 'create_new' ? '#4CAF50' : '#2196F3',
                        borderRightWidth: msg.actionType === 'user' ? 3 : 0,
                        borderRightColor: '#9CA3AF',
                      }}
                    >
                      {msg.actionType === 'user' && (
                        <Text style={{ fontSize: 9, color: '#6B7280', marginBottom: 2, fontWeight: '600' }}>You</Text>
                      )}
                      <Text selectable style={{ fontSize: 11, color: msg.actionType === 'user' ? '#374151' : '#333', lineHeight: 15 }}>{msg.content || msg.text}</Text>
                      {Array.isArray(msg.chips) && msg.chips.length > 0 && (
                        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5, marginTop: 6 }}>
                          {msg.chips.map((chip, ci) => (
                            <TouchableOpacity key={ci} onPress={() => !isAiProcessing && handleAgentEdit(chip)}
                              style={{ borderWidth: 1, borderColor: '#93C5FD', backgroundColor: '#EFF6FF', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 4 }}>
                              <Text style={{ fontSize: 10, color: '#1D4ED8', fontWeight: '500' }}>{chip}</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      )}
                    </View>
                  ))}
                </ScrollView>
              )}

              {/* AI Lock Indicators */}
              {isAiLocked && (
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  marginBottom: 6,
                  padding: 6,
                  backgroundColor: '#FEF2F2',
                  borderRadius: 6,
                }}>
                  <MaterialIcons name="lock" size={12} color="#EF4444" />
                  <Text style={{ fontSize: 11, color: '#B91C1C', marginLeft: 4 }}>
                    AI is being used by {lockedByUser?.name || 'another user'}
                  </Text>
                </View>
              )}

              {/* Agentic editor hint — the AI sees the whole document */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name="sparkles" size={12} color="#7C3AED" />
                <Text style={{ fontSize: 11, color: safeTheme.placeholderText || '#6B7280', flex: 1 }} numberOfLines={1}>
                  AI edits the whole document — rewrite, add/remove pages, letterhead, headers & footers. Just ask.
                </Text>
              </View>

              {/* Chat Input + Send */}
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
                <TextInput
                  style={{
                    flex: 1,
                    backgroundColor: isAiLocked ? '#F3F4F6' : (safeTheme.background || '#F9FAFB'),
                    color: isAiLocked ? '#9CA3AF' : (safeTheme.text || '#111827'),
                    borderWidth: 1,
                    borderColor: safeTheme.borderColor || '#D1D5DB',
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 13,
                    maxHeight: 80,
                  }}
                  placeholder={isAiLocked ? "AI is locked..." : (hasSelection ? 'Edit selected text...' : 'Ask anything — rewrite, add pages, letterhead, review…')}
                  placeholderTextColor={safeTheme.textSecondary || '#888'}
                  value={chatInput}
                  onChangeText={(text) => {
                    setChatInput(text);
                    if (!isAiLocked && aiLockedBy) {
                      refreshAiLock?.();
                    }
                  }}
                  multiline
                  editable={!isAiLocked}
                  onFocus={() => {
                    if (!isAiLocked) {
                      requestAiLock();
                    }
                  }}
                  onKeyPress={handleKeyPress}
                />
                <TouchableOpacity
                  style={{
                    backgroundColor: isAiProcessing ? '#EF4444' : ((chatInput.trim() && !isAiLocked) ? (safeTheme.primary || '#6366F1') : '#D1D5DB'),
                    borderRadius: 10,
                    paddingHorizontal: 14,
                    paddingVertical: 10,
                    justifyContent: 'center',
                    alignItems: 'center',
                  }}
                  onPress={() => isAiProcessing ? handleStopAgent() : handleAgentEdit()}
                  disabled={isAiProcessing ? false : (!chatInput.trim() || isAiLocked)}
                >
                  {isAiProcessing ? (
                    <Ionicons name="stop" size={18} color="#fff" />
                  ) : (
                    <Ionicons name="send" size={18} color="#fff" />
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Left Sidebar */}
          {!mobileViewOnly && (
            <View style={[styles.sidebar, { backgroundColor: safeTheme.surface, borderRightColor: safeTheme.borderColor }]}>
              {/* Sidebar Header with View Toggle */}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text style={[styles.sidebarTitle, { color: safeTheme.text, marginBottom: 0 }]}>PAGES</Text>
                <Tooltip text={pagePanelViewMode === 'thumbnail' ? 'Switch to List View' : 'Switch to Thumbnail View'} theme={safeTheme}>
                  <TouchableOpacity
                    style={{
                      padding: 4,
                      backgroundColor: safeTheme.background,
                      borderRadius: 4,
                    }}
                    onPress={togglePagePanelView}
                  >
                    <Ionicons
                      name={pagePanelViewMode === 'thumbnail' ? 'list-outline' : 'grid-outline'}
                      size={16}
                      color={safeTheme.textSecondary || '#888'}
                    />
                  </TouchableOpacity>
                </Tooltip>
              </View>

              <TouchableOpacity style={styles.insertFirstBtn} onPress={() => handleOpenAddPageModal(0)}>
                <MaterialIcons name="add" size={14} color="#2196F3" />
                <Text style={styles.insertFirstText}>Insert at start</Text>
              </TouchableOpacity>

              {/* Auto Update Progress Bar (Visible when isAutoUpdating is true) */}
              {isAutoUpdating && (
                <View style={{
                  marginBottom: 12,
                  backgroundColor: '#E3F2FD',
                  padding: 8,
                  borderRadius: 6,
                  borderWidth: 1,
                  borderColor: '#BBDEFB'
                }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ fontSize: 11, color: '#1565C0', fontWeight: '600' }}>
                      Updating Pages...
                    </Text>
                    <Text style={{ fontSize: 11, color: '#1565C0', fontWeight: '600' }}>
                      {autoUpdateProgress.current}/{autoUpdateProgress.total}
                    </Text>
                  </View>
                  <View style={{ width: '100%', height: 4, backgroundColor: '#BBDEFB', borderRadius: 2, overflow: 'hidden' }}>
                    <View
                      style={{
                        height: '100%',
                        backgroundColor: '#2196F3',
                        borderRadius: 2,
                        width: `${(autoUpdateProgress.current / autoUpdateProgress.total) * 100}%`
                      }}
                    />
                  </View>
                </View>
              )}

              <ScrollView style={styles.pageList}>
                {pages.map(renderPageItem)}
              </ScrollView>

              <TouchableOpacity style={[styles.addPageButton, { borderColor: safeTheme.borderColor }]} onPress={() => handleOpenAddPageModal()}>
                <Ionicons name="add" size={20} color={safeTheme.primary} />
                <Text style={[styles.addPageText, { color: safeTheme.primary }]}>Add Page</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Center - Content Area */}
          <View style={[styles.contentArea, { flex: 1, position: 'relative' }]}>
            {/* Shared Toolbar — fixed above the scroll area */}
            <ComposerToolbar
              editorRef={editorRef}
              theme={safeTheme}
              currentPageId={currentPageId}
              isMobile={mobileViewOnly}
            />

            <ScrollView
              ref={contentScrollRef}
              style={styles.contentScroll}
              contentContainerStyle={mobileViewOnly ? styles.contentContainerMobile : styles.contentContainerDesktop}
              onScroll={handleContentScroll}
              scrollEventThrottle={200}
              showsVerticalScrollIndicator={true}
              removeClippedSubviews={false}
            >
              {pages.map((page, index) => {
                const isActivePage = currentPageId === page.id;
                const callbacks = getPageCallbacks(page.id);
                return (
                  <React.Fragment key={page.id}>
                    <ReportChromePreview
                      position="top"
                      pageIndex={index}
                      totalPages={pages.length}
                      letterhead={reportMetadata?.letterheadConfig}
                      header={reportMetadata?.headerConfig}
                      footer={reportMetadata?.footerConfig}
                      title={reportMetadata?.title}
                      author={reportMetadata?.author}
                    />
                    <PageEditorCard
                      page={page}
                      pageIndex={index}
                      totalPages={pages.length}
                      isActive={isActivePage}
                      isMobile={mobileViewOnly}
                      onLayout={callbacks.onLayout}
                      onContentChange={callbacks.onContentChange}
                      onSelectionChange={callbacks.onSelectionChange}
                      onChartEdit={handleChartEdit}
                      onTitleChange={callbacks.onTitleChange}
                      onFocus={callbacks.onFocus}
                      editorRefCallback={callbacks.editorRefCallback}
                      getEditorPlaceholder={getEditorPlaceholder}
                      safeTheme={safeTheme}
                      personaText={personaText}
                      reportMetadata={reportMetadata}
                      ydoc={ydoc}
                      provider={provider}
                      editorUser={editorUser}
                      hasTiptapFlag={hasTiptap}
                      onSetShowStylePickerModal={setShowStylePickerModal}
                      onSetShowHeaderFooterModal={setShowHeaderFooterModal}
                      setPages={setPages}
                      markdownToHtmlFn={markdownToHtml}
                      reportStyle={reportMetadata?.reportStyle || 'ai_auto'}
                    />
                    <ReportChromePreview
                      position="bottom"
                      pageIndex={index}
                      totalPages={pages.length}
                      letterhead={reportMetadata?.letterheadConfig}
                      header={reportMetadata?.headerConfig}
                      footer={reportMetadata?.footerConfig}
                      title={reportMetadata?.title}
                      author={reportMetadata?.author}
                    />
                    {/* Page Separator between pages */}
                    {index < pages.length - 1 && (
                      <View style={styles.pageSeparator}>
                        <View style={styles.pageSeparatorLine} />
                        <View style={styles.pageSeparatorBadge}>
                          <Ionicons name="remove-outline" size={12} color="#9CA3AF" />
                          <Text style={[styles.pageSeparatorText, mobileViewOnly && { fontSize: 10 }]}>
                            End of {personaText?.reportComposerSectionLabel || 'Page'} {index + 1}
                          </Text>
                          <Ionicons name="remove-outline" size={12} color="#9CA3AF" />
                        </View>
                        <View style={styles.pageSeparatorLine} />
                      </View>
                    )}
                  </React.Fragment>
                );
              })}

              {/* Add Page button at end of scroll */}
              <TouchableOpacity
                style={[styles.addPageButton, { borderColor: safeTheme.borderColor, maxWidth: 300, alignSelf: 'center', marginTop: mobileViewOnly ? 8 : 16, paddingHorizontal: 24 }]}
                onPress={() => handleOpenAddPageModal()}
              >
                <Ionicons name="add" size={20} color={safeTheme.primary} />
                <Text style={[styles.addPageText, { color: safeTheme.primary }]}>Add Page</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>

          {/* Right Sidebar - AI Chat (Moved from bottom) */}
          {!mobileViewOnly && (
            <View style={[styles.chatSidebar, {
              backgroundColor: safeTheme.surface,
              borderLeftColor: '#E2E8F0',
              borderLeftWidth: 1,
              shadowColor: '#000',
              shadowOffset: { width: -4, height: 0 },
              shadowOpacity: 0.05,
              shadowRadius: 12,
              elevation: 5,
              zIndex: 50,
            }]}>
              <Text style={[styles.sidebarTitle, { color: safeTheme.text, marginTop: 4 }]}>AI ASSISTANT</Text>

              {/* Agentic editor hint — the AI sees the whole document and decides
                  what to change; no page/scope selection needed. (User media is
                  protected structurally — no banner required.) */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Ionicons name="sparkles" size={12} color="#7C3AED" />
                <Text style={{ fontSize: 11, color: safeTheme.placeholderText || '#6B7280', flex: 1 }} numberOfLines={2}>
                  AI edits the whole document — rewrite, add/remove pages, letterhead, headers & footers, review. Just ask.
                </Text>
              </View>

              {/* Selection badge */}
              {hasSelection && selectedText && (
                <View style={[styles.selectionBadge, { backgroundColor: safeTheme.primary + '15' }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <MaterialIcons name="format-quote" size={14} color={safeTheme.primary} />
                    <Text style={[styles.selectionLabel, { color: safeTheme.primary }]}>Using selection:</Text>
                  </View>
                  <Text style={[styles.selectionText, { color: safeTheme.text }]} numberOfLines={3}>
                    "{selectedText}"
                  </Text>
                  <TouchableOpacity onPress={clearSelection} style={styles.clearSelectionBtn}>
                    <Ionicons name="close-circle" size={16} color="#999" />
                    <Text style={{ fontSize: 11, color: '#999' }}>Clear</Text>
                  </TouchableOpacity>
                </View>
              )}

              {/* Chat Messages Area - Takes remaining space */}
              <View style={{ flex: 1, minHeight: 0 }}>
                {aiChatMessages.length > 0 && (
                  <ScrollView
                    style={{ flex: 1 }}
                    contentContainerStyle={{ paddingBottom: 8 }}
                    showsVerticalScrollIndicator={true}
                  >
                    {aiChatMessages.slice(-8).map(msg => (
                      <View
                        key={msg.id}
                        style={{
                          backgroundColor: msg.actionType === 'user' ? '#F9FAFB' : (msg.actionType === 'create_new' ? '#F0FDF4' : '#EFF6FF'),
                          borderRadius: 12,
                          padding: 12,
                          marginBottom: 8,
                          alignSelf: msg.actionType === 'user' ? 'flex-end' : 'flex-start',
                          maxWidth: '85%',
                          borderWidth: 1,
                          borderColor: msg.actionType === 'user' ? '#E5E7EB' : (msg.actionType === 'create_new' ? '#BBF7D0' : '#DBEAFE'),
                          shadowColor: '#000',
                          shadowOffset: { width: 0, height: 1 },
                          shadowOpacity: 0.03,
                          shadowRadius: 3,
                        }}
                      >
                        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}>
                          <Ionicons
                            name={msg.actionType === 'user' ? 'person-circle-outline' : (msg.actionType === 'create_new' ? 'add-circle' : 'sparkles')}
                            size={14}
                            color={msg.actionType === 'user' ? '#6B7280' : (msg.actionType === 'create_new' ? '#16A34A' : '#2563EB')}
                          />
                          <Text style={{ fontSize: 11, fontWeight: '600', color: msg.actionType === 'user' ? '#6B7280' : (msg.actionType === 'create_new' ? '#15803D' : '#1D4ED8'), marginLeft: 6 }}>
                            {msg.actionType === 'user' ? 'You' : (msg.actionType === 'create_new' ? 'New Page Created' : 'AI Edit')}
                          </Text>
                        </View>
                        <Text style={{ fontSize: 13, color: msg.actionType === 'user' ? '#374151' : '#334155', lineHeight: 18 }}>{msg.text}</Text>
                        {Array.isArray(msg.chips) && msg.chips.length > 0 && (
                          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                            {msg.chips.map((chip, ci) => (
                              <TouchableOpacity key={ci} onPress={() => !isAiProcessing && handleAgentEdit(chip)}
                                style={{ borderWidth: 1, borderColor: '#93C5FD', backgroundColor: '#EFF6FF', borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5 }}>
                                <Text style={{ fontSize: 11, color: '#1D4ED8', fontWeight: '500' }}>{chip}</Text>
                              </TouchableOpacity>
                            ))}
                          </View>
                        )}
                      </View>
                    ))}
                  </ScrollView>
                )}
              </View>

              {/* Chat Input Container - Fixed at bottom */}
              <View style={styles.chatInputContainer}>

                {/* AI Lock Indicator */}
                {isAiLocked && (
                  <View style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    marginBottom: 8,
                    padding: 8,
                    backgroundColor: '#FEF2F2',
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: '#xFCA5A5'
                  }}>
                    <MaterialIcons name="lock" size={14} color="#EF4444" />
                    <Text style={{ fontSize: 12, color: '#B91C1C', marginLeft: 6 }}>
                      AI is being used by {lockedByUser?.name || 'another user'}
                    </Text>
                  </View>
                )}

                {/* My Lock Indicator & Release */}
                {!isAiLocked && aiLockedBy && (
                  <View style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 8,
                    padding: 6,
                    paddingHorizontal: 10,
                    backgroundColor: '#EFF6FF',
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: '#BFDBFE'
                  }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                      <MaterialIcons name="lock-open" size={14} color="#2563EB" />
                      <Text style={{ fontSize: 11, color: '#1E40AF', marginLeft: 6 }}>
                        You have AI control
                      </Text>
                    </View>
                    <TouchableOpacity onPress={releaseAiLock}>
                      <Text style={{ fontSize: 11, color: '#2563EB', fontWeight: '600' }}>Release</Text>
                    </TouchableOpacity>
                  </View>
                )}

                <TextInput
                  style={[styles.chatInputVertical, {
                    color: isAiLocked ? '#9CA3AF' : safeTheme.text,
                    backgroundColor: isAiLocked ? '#F3F4F6' : '#F8FAFC',
                    borderColor: '#E2E8F0',
                    borderWidth: 1,
                    borderRadius: 12,
                    paddingHorizontal: 16,
                    paddingTop: 12,
                    paddingBottom: 12,
                    fontSize: 13,
                    shadowColor: '#000',
                    shadowOffset: { width: 0, height: 1 },
                    shadowOpacity: 0.02,
                    shadowRadius: 2,
                  }]}
                  value={chatInput}
                  onChangeText={(text) => {
                    setChatInput(text);
                    if (!isAiLocked && aiLockedBy) refreshAiLock?.();
                  }}
                  placeholder={isAiLocked ? "AI is currently locked..." : "Ask anything — rewrite, add pages, letterhead, review…"}
                  placeholderTextColor="#999"
                  multiline
                  textAlignVertical="top"
                  maxLength={2000}
                  editable={!isAiLocked}
                  onFocus={() => {
                    if (!isAiLocked) requestAiLock();
                  }}
                  onKeyPress={handleKeyPress}
                />
                <View style={styles.chatActionsVertical}>
                  {/* Row 1: Upload + Scope Selector (max 2 items) */}
                  <View style={styles.chatActionsRow}>
                    {/* Upload Button */}
                    <TouchableOpacity
                      style={{
                        padding: 8,
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: safeTheme.borderColor,
                        backgroundColor: safeTheme.background,
                        justifyContent: 'center',
                        alignItems: 'center',
                        width: 40,
                        height: 40,
                        opacity: isAiLocked ? 0.5 : 1
                      }}
                      disabled={isAiLocked}
                      onPress={() => {
                        // Use internal state instead of external prop for better layering
                        setShowInternalUploadModal(true);

                        if (onOpenTemplateUpload) {
                          // onOpenTemplateUpload(); 
                        }
                      }}
                    >
                      <Ionicons name="attach" size={20} color={safeTheme.text} />
                    </TouchableOpacity>

                  </View>

                  {/* Row 2: Send Button (full width) */}
                  <TouchableOpacity
                    style={[styles.sendButtonLarge, {
                      backgroundColor: isAiProcessing ? '#EF4444' : ((chatInput.trim() && !isAiLocked) ? '#2563EB' : '#ccc'),
                      width: '100%',
                      justifyContent: 'center',
                      borderRadius: 12,
                      paddingVertical: 12,
                      shadowColor: isAiProcessing ? '#EF4444' : '#2563EB',
                      shadowOffset: { width: 0, height: 2 },
                      shadowOpacity: 0.2,
                      shadowRadius: 4,
                      elevation: 2,
                    }]}
                    onPress={() => isAiProcessing ? handleStopAgent() : handleAgentEdit()}
                    disabled={isAiProcessing ? false : (!chatInput.trim() || isAiLocked)}
                  >
                    {isAiProcessing ? (
                      <>
                        <Text style={{ color: '#fff', fontWeight: '600', marginRight: 6 }}>Stop</Text>
                        <Ionicons name="stop" size={16} color="#fff" />
                      </>
                    ) : (
                      <>
                        <Text style={{ color: '#fff', fontWeight: '600', marginRight: 6 }}>Generate</Text>
                        <Ionicons name="sparkles" size={16} color="#fff" />
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          )}
        </View>

        {/* Modals */}
        <ReportGoalSetting
          visible={showGoalSetting}
          onClose={() => setShowGoalSetting(false)}
          onReportGenerated={handleReportGenerated}
          onGoalSet={setReportGoal}
          onGenerationStart={handleGenerationStart}
          onPageBatchGenerated={handlePageBatchGenerated}
          onPageError={handlePageError}
          existingGoal={reportGoal}
          apiConfig={API_CONFIG}
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          folders={folders}
          persona={persona}
          uploadModalProps={uploadModalProps}
        />

        <ExportModal
          visible={showExportModal}
          onClose={() => setShowExportModal(false)}
          pages={visiblePages}
          reportMetadata={reportMetadata}
          reportGoal={reportGoal}
          theme={safeTheme}
          userType={userType}
          onOpenCredits={onOpenCredits}
        />

        <ReportPreviewModal
          visible={showPreviewModal}
          onClose={() => setShowPreviewModal(false)}
          pages={visiblePages}
          reportMetadata={reportMetadata}
          reportGoal={reportGoal}
          theme={safeTheme}
          userType={userType}
          onExport={() => setShowExportModal(true)}
        />

        <ReportListModal
          visible={showReportList}
          onClose={() => setShowReportList(false)}
          onLoadReport={stableLoadReport}
          onCreateNew={handleCreateNew}
          apiConfig={apiConfig}
          userDeviceId={userDeviceId}
          theme={safeTheme}
        />

        {/* Delete Confirmation Modal */}
        <Modal
          visible={showDeleteModal}
          transparent={true}
          animationType="fade"
          onRequestClose={cancelDeletePage}
        >
          <View style={styles.deleteModalOverlay}>
            <View style={[styles.deleteModalContent, { backgroundColor: safeTheme.background }]}>
              <View style={styles.deleteModalIcon}>
                <Ionicons name="warning" size={48} color="#ef4444" />
              </View>
              <Text style={[styles.deleteModalTitle, { color: safeTheme.text }]}>
                Delete Section?
              </Text>
              <Text style={[styles.deleteModalMessage, { color: safeTheme.text }]}>
                Are you sure you want to delete this section? This action cannot be undone.
              </Text>
              <View style={styles.deleteModalButtons}>
                <TouchableOpacity
                  style={[styles.deleteModalButton, styles.deleteModalCancelButton, { borderColor: safeTheme.borderColor }]}
                  onPress={cancelDeletePage}
                >
                  <Text style={[styles.deleteModalButtonText, { color: safeTheme.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.deleteModalButton, styles.deleteModalDeleteButton]}
                  onPress={confirmDeletePage}
                >
                  <Ionicons name="trash-outline" size={18} color="#fff" style={{ marginRight: 6 }} />
                  <Text style={[styles.deleteModalButtonText, { color: '#fff' }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
        {/* Chart Studio */}
        <ChartStudio
          visible={showChartStudio}
          onClose={() => setShowChartStudio(false)}
          onInsertChart={async (chartConfig, title) => {
            // ChartStudio passes a Chart.js config object — render it to a PNG data URL first
            try {
              const dataUrl = await renderChartToImage(chartConfig);

              // Build rich alt text with data summary for accessibility
              let altText = title || chartConfig.options?.plugins?.title?.text || 'Chart';
              if (chartConfig.data?.labels && chartConfig.data?.datasets) {
                const labels = chartConfig.data.labels;
                const summary = chartConfig.data.datasets.map(ds => {
                  return `${ds.label || 'Data'}: [${ds.data.map((d, i) => `${labels[i]}=${d}`).join(', ')}]`;
                }).join('; ');
                altText += ` | Data: ${summary}`;
              }

              if (editorRef.current?.insertContent) {
                const imgHtml = `<img src="${dataUrl}" style="width: 80%; display: block; margin: 10px auto;" alt="${altText.replace(/"/g, '&quot;')}" data-chart-config="${encodeURIComponent(JSON.stringify(chartConfig))}" />`;
                editorRef.current.insertContent(imgHtml);
                editorRef.current.insertContent('<p></p>');
              } else {
                // Fallback for non-Tiptap
                updatePageContent(currentPageId, (currentPage?.content || '') + `\n\n![${altText}](${dataUrl})`);
              }
            } catch (err) {
              console.error('Failed to render chart from ChartStudio:', err);
              Alert.alert('Error', 'Failed to render chart. Please try again.');
            }
            setShowChartStudio(false);
          }}
          sourceContext="report"
          pageContext={currentPage} // NEW: Pass current page for AI context
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          apiConfig={apiConfig}
          theme={safeTheme}
        />

        {/* Chart Edit Modal - for editing existing charts in the report */}
        {showChartEditModal && editingChartConfig && (
          <ChartEditModal
            visible={showChartEditModal}
            onClose={() => {
              setShowChartEditModal(false);
              setEditingChartConfig(null);
              setEditingChartNodePos(null);
            }}
            onSave={handleChartEditSave}
            chartConfig={editingChartConfig}
            theme={safeTheme}
          />
        )}

        <AIImageModal
          visible={showAIImageModal}
          onClose={() => setShowAIImageModal(false)}
          onInsertImage={handleInsertAIImage}
          currentPage={currentPage}
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          apiConfig={apiConfig}
          theme={safeTheme}
        />

        {/* Internal Upload Modal - Rendered inside fullScreen portal to ensure it appears on TOP */}
        <UnifiedUploadModal
          {...(uploadModalProps || {})}
          isVisible={showInternalUploadModal}
          onClose={() => setShowInternalUploadModal(false)}
          theme={theme}
        />

        {/* Upload Progress Popup - Rendered inside modal so it's visible above overlay */}
        <UploadProgressPopup
          visible={enhancedProgress && enhancedProgress.size > 0}
          enhancedProgress={enhancedProgress}
          theme={theme}
          onClose={() => { }}
          onDismissEntry={onDismissUploadEntry}
        />

        {/* Arrange Pages Modal */}
        <Modal visible={showArrangeModal} transparent animationType="fade" onRequestClose={() => setShowArrangeModal(false)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingTop: 16, paddingBottom: 24 }}>
              {/* Handle bar */}
              <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: '#D1D5DB', alignSelf: 'center', marginBottom: 12 }} />
              {/* Header */}
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, marginBottom: 14 }}>
                <Text style={{ fontSize: 17, fontWeight: '700', color: '#111827' }}>Arrange Pages</Text>
                <TouchableOpacity onPress={() => setShowArrangeModal(false)} style={{ padding: 4 }}>
                  <Ionicons name="close" size={22} color="#6B7280" />
                </TouchableOpacity>
              </View>
              {/* Scrollable page cards */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 10 }}>
                {pages.map((page, index) => (
                  <View key={page.id} style={{ alignItems: 'center', width: 110 }}>
                    {/* Card */}
                    <TouchableOpacity
                      onPress={() => { setCurrentPageId(page.id); setShowArrangeModal(false); }}
                      style={{
                        width: 100, height: 70, borderRadius: 10, borderWidth: 2,
                        borderColor: page.id === currentPageId ? '#4F46E5' : '#E5E7EB',
                        backgroundColor: page.id === currentPageId ? '#EEF2FF' : '#F9FAFB',
                        justifyContent: 'center', alignItems: 'center', marginBottom: 6,
                      }}
                    >
                      <Text style={{ fontSize: 20, fontWeight: '700', color: page.id === currentPageId ? '#4F46E5' : '#6B7280' }}>{index + 1}</Text>
                    </TouchableOpacity>
                    {/* Title */}
                    <Text numberOfLines={1} style={{ fontSize: 10, color: '#374151', textAlign: 'center', marginBottom: 6, paddingHorizontal: 2 }}>
                      {page.title || `Page ${index + 1}`}
                    </Text>
                    {/* Reorder arrows */}
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <TouchableOpacity
                        disabled={index === 0}
                        onPress={() => { reorderPages(index, index - 1); }}
                        style={{ padding: 4, opacity: index === 0 ? 0.25 : 1 }}
                      >
                        <Ionicons name="arrow-back" size={16} color="#4F46E5" />
                      </TouchableOpacity>
                      <TouchableOpacity
                        disabled={index === pages.length - 1}
                        onPress={() => { reorderPages(index, index + 1); }}
                        style={{ padding: 4, opacity: index === pages.length - 1 ? 0.25 : 1 }}
                      >
                        <Ionicons name="arrow-forward" size={16} color="#4F46E5" />
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </ScrollView>
            </View>
          </View>
        </Modal>

        {/* Collaboration Panel */}
        <CollaborationPanel
          visible={showCollaborationPanel}
          onClose={() => setShowCollaborationPanel(false)}
          reportId={currentReportId}
          currentUser={{ name: persona?.name || 'You', email: userDeviceId }}
          theme={safeTheme}
          collaborators={collaborators} // Real-time collaborators
        />

        {/* Edit Single Section Topic & Outline Modal */}
        <EditSlideOutlineModal
          visible={!!editOutlinePage}
          onClose={() => setEditOutlinePage(null)}
          onSave={handleSavePageOutline}
          theme={safeTheme}
          itemLabel="Section"
          initialTitle={editOutlinePage?.title || ''}
          initialOutline={editOutlinePage?.outline || editOutlinePage?.sectionTopic || ''}
        />

        {/* Update Instruction Modal */}
        <UpdateInstructionModal
          visible={showUpdateInstructionModal}
          onClose={() => setShowUpdateInstructionModal(false)}
          onConfirm={handleConfirmUpdate}
          isUpdating={isAutoUpdating}
          theme={safeTheme}
          title="Update All Sections"
          itemLabel="Section"
          currentGoal={reportGoal}
          currentOutline={currentOutlineData}
          onRefreshOutline={handleRefreshOutline}
          isRefreshingOutline={isRefreshingOutline}
        />

        {/* Layout System Modals - Layout Picker removed, layout is set at page creation */}

        <ReportAddPageModal
          visible={showAddPageModal}
          onClose={() => {
            setShowAddPageModal(false);
            setAddPageInsertIndex(null);
          }}
          onCreatePage={handleCreatePage}
          insertIndex={addPageInsertIndex}
          apiConfig={apiConfig}
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          theme={safeTheme}
          reportGoal={reportGoal}
          existingPages={pages}
        />

        <ReportHeaderFooterModal
          visible={showHeaderFooterModal}
          onClose={() => setShowHeaderFooterModal(false)}
          onSave={handleHeaderFooterSave}
          headerConfig={reportMetadata?.headerConfig}
          footerConfig={reportMetadata?.footerConfig}
          letterheadConfig={reportMetadata?.letterheadConfig}
          reportMetadata={reportMetadata}
          theme={safeTheme}
        />

        <ReportStylePicker
          visible={showStylePickerModal}
          onClose={() => setShowStylePickerModal(false)}
          onSelectStyle={handleStyleChange}
          currentStyle={reportMetadata?.reportStyle}
          theme={safeTheme}
        />

        <FolderDetailModal
          visible={showFolderDetailModal}
          onClose={() => setShowFolderDetailModal(false)}
          folderId={selectedFolders?.[0]?.id}
          theme={safeTheme}
        />
      </View>

      {/* Close Confirmation Modal */}
      <Modal visible={showCloseConfirmModal} transparent animationType="fade" onRequestClose={() => setShowCloseConfirmModal(false)}>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)' }}>
          <View style={{
            width: '90%',
            maxWidth: 400,
            backgroundColor: '#2C2C2E',
            borderRadius: 12,
            padding: 24,
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 8 },
            shadowOpacity: 0.3,
            shadowRadius: 16,
            elevation: 10,
          }}>
            <Text style={{ fontSize: 16, fontWeight: '600', color: '#FFFFFF', marginBottom: 8 }}>
              Close Editor
            </Text>
            <Text style={{ fontSize: 14, color: '#D1D1D6', marginBottom: 24 }}>
              Are you sure you want to close? You will lose any unsaved changes.
            </Text>
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 12 }}>
              <TouchableOpacity
                onPress={() => setShowCloseConfirmModal(false)}
                style={{
                  paddingVertical: 10,
                  paddingHorizontal: 24,
                  borderRadius: 8,
                  backgroundColor: '#3A3A3C',
                }}
              >
                <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => {
                  setShowCloseConfirmModal(false);
                  onClose();
                }}
                style={{
                  paddingVertical: 10,
                  paddingHorizontal: 24,
                  borderRadius: 8,
                  backgroundColor: '#007AFF',
                }}
              >
                <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>OK</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    gap: 12,
    zIndex: 20, // Ensure tooltips render above content
  },
  closeButton: { padding: 4 },
  goalButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: '#e3f2fd',
    gap: 4
  },
  goalButtonText: { fontSize: 13, fontWeight: '500' },
  vaultBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 4
  },
  vaultBadgeText: {
    fontSize: 12,
    color: '#666',
    fontWeight: '500'
  },
  titleContainer: { flex: 1 },
  title: { fontSize: 18, fontWeight: '600' },
  titleInput: {
    fontSize: 18,
    fontWeight: '600',
    flex: 1,
    padding: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#2196F3',
    color: '#000'
  },
  modeToggle: {
    flexDirection: 'row',
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    padding: 2
  },
  modeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4
  },
  modeBtnActive: { backgroundColor: '#2196F3' },
  modeBtnText: { fontSize: 12, color: '#666' },
  modeBtnTextActive: { color: '#fff' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerButton: {
    width: 36,
    height: 36,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center'
  },
  headerButtonWithLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 6
  },
  headerButtonLabel: {
    fontSize: 13,
    fontWeight: '500'
  },
  // New Professional Buttons
  ghostBtn: {
    padding: 8,
    borderRadius: 6,
    backgroundColor: 'transparent', // Ghost
  },
  primaryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2563EB',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 6,
    shadowColor: '#2563EB',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 2,
  },
  primaryBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  mainContent: { flex: 1, flexDirection: 'row', overflow: 'hidden' },
  mainContentMobile: { flex: 1, flexDirection: 'column' },
  sidebar: {
    width: 160,
    minWidth: 160,
    maxWidth: 160,
    flexBasis: 160,
    flexGrow: 0,
    flexShrink: 0,
    borderRightWidth: 1,
    padding: 12,
    flexDirection: 'column',
    overflow: 'hidden',
  },
  sidebarTitle: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
    opacity: 0.6
  },
  insertFirstBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: '#2196F3',
    borderRadius: 6,
    marginBottom: 8,
    gap: 4
  },
  insertFirstText: { fontSize: 11, color: '#2196F3' },
  pageList: { flex: 1, flexShrink: 1, minHeight: 0 },
  pageItemContainer: { marginBottom: 8, position: 'relative' },
  pageItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent',
    backgroundColor: 'transparent',
    gap: 8,
    marginBottom: 2
  },
  pageItemActive: { backgroundColor: '#EFF6FF', borderLeftColor: '#2563EB' },
  // Thumbnail view styles
  pageThumbnailItem: {
    borderRadius: 8,
    borderWidth: 2,
    padding: 8,
    marginBottom: 4,
    alignItems: 'center',
  },
  pageThumbnailItemActive: {
    borderWidth: 2,
  },
  pageThumbnailActions: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 4,
    marginTop: 6,
  },
  reorderButtons: { flexDirection: 'column', marginRight: 4 },
  reorderBtn: { padding: 0 },
  reorderBtnDisabled: { opacity: 0.3 },
  pageNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#ddd',
    justifyContent: 'center',
    alignItems: 'center'
  },
  pageNumberActive: { backgroundColor: '#2196F3' },
  pageNumberText: { fontSize: 11, fontWeight: '600', color: '#666' },
  pageNumberTextActive: { color: '#fff' },
  pageItemTitle: { flex: 1, fontSize: 12, color: '#333', lineHeight: 16 },
  pageItemTitleActive: { fontWeight: '500', color: '#1976D2' },
  pageItemTitleInput: {
    flex: 1,
    fontSize: 12,
    padding: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#2196F3',
    color: '#000'
  },
  pageItemActions: { flexDirection: 'row', gap: 4, marginLeft: 4 },
  pageActionBtn: { padding: 6 },
  deleteBtn: { padding: 6, borderRadius: 4, backgroundColor: 'rgba(244, 67, 54, 0.1)' },
  pageSelectArea: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  insertBetweenBtn: {
    position: 'absolute',
    bottom: -6,
    left: '50%',
    marginLeft: -10,
    width: 20,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#e3f2fd',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 5
  },
  addPageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: 8,
    gap: 6,
    marginTop: 8
  },
  addPageText: { fontSize: 13, fontWeight: '500' },
  contentArea: { flex: 1, overflow: 'hidden' },
  contentScroll: { flex: 1, backgroundColor: '#f0f0f0' },
  contentScrollInner: { padding: 24, alignItems: 'center' },
  pageHeader: {
    width: '100%',
    maxWidth: 1100,
    marginBottom: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    gap: 12,
  },
  pageHeaderRight: {
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: 8,
  },
  pageTitleInput: { fontSize: 21, fontWeight: '700', marginBottom: 4, color: '#000', flex: 1, minWidth: 200 },
  pageInfo: { fontSize: 12, color: '#888' },
  // Layout Toolbar styles
  layoutToolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  layoutToolbarBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 6,
    gap: 6,
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  layoutToolbarText: {
    fontSize: 12,
    fontWeight: '500',
  },
  pageContainer: {
    width: '100%',
    maxWidth: 1100,
    minHeight: 400,
    borderRadius: 8,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
    overflow: 'hidden'
  },
  pageContainerActive: {
    borderWidth: 2,
    shadowOpacity: 0.12,
    shadowRadius: 8,
    elevation: 4,
  },
  contentContainerMobile: {
    padding: 6,
    alignItems: 'center',
    paddingBottom: 80,
  },
  contentContainerDesktop: {
    padding: 16,
    alignItems: 'center',
    paddingBottom: 120,
  },
  pageContent: {
    flex: 1,
    padding: 32,
    fontSize: 15,
    lineHeight: 24,
    color: '#333',
    minHeight: 500,
    textAlignVertical: 'top'
  },
  // Page separator between pages in continuous scroll
  pageSeparator: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 16,
    paddingHorizontal: 20,
  },
  pageSeparatorLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#E5E7EB',
  },
  pageSeparatorBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 4,
    gap: 6,
    backgroundColor: '#F9FAFB',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  pageSeparatorText: {
    fontSize: 11,
    color: '#9CA3AF',
    fontWeight: '500',
  },
  // Replaced .chatContainer with .chatSidebar and added support styles
  chatSidebar: {
    width: 320,
    minWidth: 320,
    maxWidth: 320,
    flexBasis: 320,
    flexGrow: 0,
    flexShrink: 0,
    borderLeftWidth: 1,
    padding: 16,
    flexDirection: 'column',
    gap: 12,
    overflow: 'hidden',
  },
  modeIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 8,
    marginBottom: 4
  },
  modeIndicatorText: {
    fontSize: 12,
    color: '#888',
    fontWeight: '500',
    flex: 1
  },
  selectionBadge: {
    padding: 10,
    borderRadius: 8,
    gap: 6,
    borderWidth: 1,
    borderColor: 'transparent'
  },
  selectionLabel: {
    fontSize: 11,
    fontWeight: '600'
  },
  selectionText: {
    fontSize: 12,
    fontStyle: 'italic',
    opacity: 0.8
  },
  clearSelectionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
    alignSelf: 'flex-start'
  },

  chatInputContainer: {
    padding: 12,
    borderTopWidth: 1,
    backgroundColor: 'transparent',
    gap: 8,
    flexShrink: 0,
  },
  chatInputVertical: {
    width: '100%',
    minHeight: 48,
    maxHeight: 140, // Up to ~6 lines
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    fontSize: 15,
    textAlignVertical: 'top'
  },
  chatActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  chatActionsVertical: {
    flexDirection: 'column',
    gap: 8,
    width: '100%',
  },
  chatActionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    flexWrap: 'nowrap',
  },
  sendButtonLarge: {
    flexDirection: 'row',
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center'
  },
  // Delete Modal Styles
  deleteModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20
  },
  deleteModalContent: {
    width: '100%',
    maxWidth: 400,
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 8
  },
  deleteModalIcon: {
    marginBottom: 16
  },
  deleteModalTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center'
  },
  deleteModalMessage: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 24,
    opacity: 0.8,
    lineHeight: 20
  },
  deleteModalButtons: {
    flexDirection: 'row',
    gap: 12,
    width: '100%'
  },
  deleteModalButton: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10
  },
  deleteModalCancelButton: {
    backgroundColor: 'transparent',
    borderWidth: 1
  },
  deleteModalDeleteButton: {
    backgroundColor: '#ef4444'
  },
  deleteModalButtonText: {
    fontSize: 15,
    fontWeight: '600'
  },
  // 🆕 Progressive Rendering - Loading & Error States
  generatingOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
    minHeight: 400,
    backgroundColor: '#fafafa',
  },
  generatingText: {
    fontSize: 18,
    fontWeight: '600',
    marginTop: 20,
    textAlign: 'center',
  },
  generatingHint: {
    fontSize: 14,
    marginTop: 8,
    textAlign: 'center',
  },
  generatingDescBox: {
    marginTop: 24,
    padding: 16,
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    maxWidth: 500,
  },
  generatingDescLabel: {
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 6,
  },
  generatingDesc: {
    fontSize: 14,
    lineHeight: 20,
  },
  errorOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
    minHeight: 400,
    backgroundColor: '#fef2f2',
  },
  errorTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#dc2626',
    marginTop: 16,
  },
  errorMessage: {
    fontSize: 14,
    color: '#7f1d1d',
    marginTop: 8,
    textAlign: 'center',
    maxWidth: 400,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3b82f6',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
    marginTop: 24,
    gap: 8,
  },
  retryButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  errorHint: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 16,
    fontStyle: 'italic',
  },
  // 🆕 Thumbnail loading/error overlays
  thumbnailGeneratingOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f0f9ff',
    minHeight: 100,
    borderRadius: 4,
  },
  thumbnailGeneratingText: {
    fontSize: 10,
    color: '#3b82f6',
    marginTop: 6,
    fontWeight: '500',
  },
  thumbnailErrorOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#fef2f2',
    minHeight: 100,
    borderRadius: 4,
  },
  thumbnailErrorText: {
    fontSize: 10,
    color: '#ef4444',
    marginTop: 4,
    fontWeight: '500',
  },

});

export default ReportComposer;
