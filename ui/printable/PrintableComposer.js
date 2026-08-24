// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// printableComposer.js - AI printable Generator with Canvas Editor
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
  Dimensions,
  PanResponder,
  Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import PrintableGoalInput from './PrintableGoalInput';
import PrintableCanvas, { PAGE_WIDTH, PAGE_HEIGHT } from './PrintableCanvas';
import PrintableSharedToolbar from './PrintableSharedToolbar';
import PrintableStylePicker, { PRESET_STYLES } from './PrintableStylePicker';
import PrintableExport from './PrintableExport';
import PrintablePlayer from './PrintablePlayer';
import ChartStudio from '../composer/ChartStudio';
import ChartEditModal from '../composer/ChartEditModal'; // Import Chart Edit Modal for inline editing
import AIImageModal from '../composer/AIImageModal'; // Import AI Image Modal
import AIDiagramModal from '../composer/AIDiagramModal'; // Import AI Diagram (SVG) Modal
import { ShareButton } from '../ShareManager';
import { usePrintablePages } from './hooks/usePrintableSlides';
import { useCollaboration } from '../composer/hooks/useCollaboration';
import CollaborationLockIndicator from '../composer/CollaborationLockIndicator'; // Imported
import CollaborationPanel from '../composer/CollaborationPanel'; // Imported for collaboration features
import UpdateInstructionModal from '../composer/UpdateInstructionModal'; // Imported
import EditSlideOutlineModal from '../composer/EditSlideOutlineModal'; // Edit single page topic/outline
import { usePrintablePersistence } from './hooks/usePrintablePersistence';
import { processPage as processPAGE, processPageAsync as processPAGEAsync } from './utils/pagePostProcessor';
import { mapIconToPathAsync } from '../composer/utils/iconMapper';
import { navigateToPrintable } from '../../utils/urlRouter';
import ImageGenService from '../../services/ImageGenService';
import globalImageCache from '../../utils/globalImageCache';
import { generateImagesParallel } from '../../services/imageGenerationUtils';
import { prefetchIcons } from '../composer/utils/iconMapper';
import UnifiedUploadModal from '../UnifiedUploadModal'; // Unified upload modal
import UploadProgressPopup from '../UploadProgressPopup'; // Upload progress popup for visibility inside modal
import DeckChromeOverlay from '../composer/DeckChromeOverlay';
import { buildSlidesSummary } from '../../utils/slideTextExtractor';
import LayerPanel from '../composer/LayerPanel';
import Tooltip from '../ui/Tooltip'; // Import Tooltip
import { showDesktopEditingAlert } from '../../utils/mobileEditAlert';
import authService from '../../services/authService';
import { API_CONFIG } from '../../config/config';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import SlideLayoutPicker from '../composer/SlideLayoutPicker';
import { createPageFromTemplate, PAGE_TEMPLATES } from './printableTemplates';
import { useClipboard } from '../composer/hooks/useClipboard';
import PrintableAnalyticsModal from './PrintableAnalyticsModal';
import FolderDetailModal from '../FolderDetailModal';
import useImagePaste from '../../hooks/useImagePaste';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Module-level counter for unique chat message IDs (prevents duplicate React keys when Date.now() collides)
let _chatMsgId = 0;
const chatMsgUid = () => `msg_${Date.now()}_${++_chatMsgId}`;

// Deck-level header/footer + page-number defaults. Agentic-editable via chat and
// persisted inside the saved style object (style.headerFooter / style.slideNumbers).
const DEFAULT_HEADER_FOOTER = {
  show_header: false, header_text: '',
  show_footer: false, footer_text: '',
  show_logo: false, align: 'center', color: '#64748b', font_size: 12,
};
const DEFAULT_SLIDE_NUMBERS = {
  show: false, format: 'n_of_total', position: 'bottom-right',
  prefix: '', color: '#94a3b8', font_size: 12, start_at: 1,
};

/**
 * Helper function to check if an error/response indicates insufficient credits
 */
const isInsufficientCreditsError = (data) => {
  if (!data) return false;

  // If data is a string (e.g. "402: {'error': 'insufficient_credits', ...}"), check it directly
  if (typeof data === 'string') {
    const lower = data.toLowerCase();
    if (lower.includes('insufficient_credits') ||
      lower.includes('insufficient credits') ||
      lower.includes('negative balance') ||
      lower.includes('purchase credits')) {
      console.log('💰 [CREDITS] Detected credit error in string data:', data.substring(0, 100));
      return true;
    }
    return false;
  }

  // Check various possible error formats
  // Note: Backend returns { error: "insufficient_credits", ... } so we need to check data.error directly
  const errorType = data.error || data.error_type || data.detail?.error || '';
  const errorMessage = data.message || data.detail?.message || data.detail || '';

  // Check for explicit insufficient_credits error type
  if (errorType === 'insufficient_credits') {
    console.log('💰 [CREDITS] Detected insufficient_credits error type');
    return true;
  }

  // Check for error message patterns
  const messageStr = typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage || '');
  if (messageStr) {
    const lowerMessage = messageStr.toLowerCase();
    if (lowerMessage.includes('insufficient credits') ||
      lowerMessage.includes('insufficient_credits') ||
      lowerMessage.includes('negative balance') ||
      lowerMessage.includes('purchase credits')) {
      console.log('💰 [CREDITS] Detected credit error in message:', messageStr.substring(0, 100));
      return true;
    }
  }

  // Also check if data.error contains credit-related keywords (for dict-like error responses)
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
  console.log('💰 [CREDITS] handleCreditError checking data:', JSON.stringify(data)?.slice(0, 300));
  if (isInsufficientCreditsError(data)) {
    const message = data.message || data.detail?.message || 'Insufficient credits. Please purchase more credits to continue.';
    console.log('💰 [CREDITS] ✅ Credit error detected! Triggering buy credits modal with message:', message);
    authService.notifyCreditRequired(message);
    return true;
  }
  console.log('💰 [CREDITS] ❌ Not a credit error');
  return false;
};

/**
 * printableComposer - AI printable Generator
 * 
 * Features:
 * - Goal-based PAGE outline generation
 * - Per-PAGE AI content generation
 * - Canvas-based visual editing
 * - Style selection (presets + AI-generated)
 * - Export to PPTX, PDF, PNG
 */
// Helper to extract base64 images and replace with placeholders
const extractImagesFromPAGE = (PAGE, selectedElementIds = []) => {
  if (!PAGE || !PAGE.elements) return { processedPAGE: PAGE, imageMap: {}, chartMap: {} };

  // Helper: capture image geometry so restore can fix AI-mangled dimensions
  const captureGeometry = (el) => {
    const geo = {};
    for (const key of ['width', 'height', 'x', 'y', 'scaleX', 'scaleY', 'objectFit', 'objectPosition', 'clipPath']) {
      if (el[key] !== undefined) geo[key] = el[key];
    }
    return geo;
  };

  const imageMap = {};
  const chartMap = {}; // Store chart configs separately
  const selectedSet = new Set(selectedElementIds);
  const processedElements = PAGE.elements.map(element => {
    // USER-UPLOADED IMAGES: If selected by user → convert to image_placeholder (editable)
    // Otherwise → protect with placeholder src
    if (element.type === 'image' && element.isUserMedia && element.src && !element.src.startsWith('{{')) {
      if (selectedSet.has(element.id)) {
        // User selected this user-media image — make it editable
        const origKey = `_orig_${element.id || Date.now()}`;
        imageMap[origKey] = { src: element.src, imageDescription: element.imageDescription || '', isUserMedia: true, geometry: captureGeometry(element) };
        const { src, isUserMedia, ...rest } = element;
        return {
          ...rest,
          type: 'image_placeholder',
          imageDescription: element.imageDescription || 'existing image',
          imageType: element.imageType || 'photo',
        };
      }
      const id = `UserMedia_${element.id || Date.now()}`;
      imageMap[id] = element.src;
      // Also store _orig_ backup so we can recover if AI drops the {{}} placeholder
      const origKey = `_orig_${element.id || Date.now()}`;
      imageMap[origKey] = { src: element.src, imageDescription: element.imageDescription || '', isUserMedia: true, geometry: captureGeometry(element) };
      return { ...element, src: `{{${id}}}` };
    }
    // AI-GENERATED IMAGES/GRAPHS: Convert to image_placeholder so AI can freely decide what to do
    if ((element.type === 'image' || element.type === 'graph') && element.src && !element.src.startsWith('{{')) {
      const origKey = `_orig_${element.id || Date.now()}`;
      imageMap[origKey] = { src: element.src, imageDescription: element.imageDescription || '', geometry: captureGeometry(element) };
      const { src, ...rest } = element;
      return {
        ...rest,
        type: 'image_placeholder',
        imageDescription: element.imageDescription || 'existing image',
        imageType: element.imageType || 'photo',
      };
    }
    // SRCLESS IMAGES: Images that were never generated (no src) — convert to image_placeholder so AI writes a description and they get generated
    if ((element.type === 'image' || element.type === 'graph') && !element.src) {
      const { src, ...rest } = element;
      return {
        ...rest,
        type: 'image_placeholder',
        imageDescription: element.imageDescription || 'professional image matching page context',
        imageType: element.imageType || 'photo',
      };
    }
    // VIDEOS/DIAGRAMS: Keep as media placeholders (AI cannot generate these)
    const isOtherMedia = element.type === 'video' || element.type === 'diagram';
    if (isOtherMedia && element.src && !element.src.startsWith('{{')) {
      const id = `UserMedia_${element.id || Date.now()}`;
      imageMap[id] = element.src;
      return { ...element, src: `{{${id}}}`, isUserMedia: true };
    }
    // STRIP ICON VECTORS: Remove potentially stale SVG data before AI processing
    if (element.type === 'icon') {
      const { svgSrc, svgPath, resolvedIconName, ...cleanIcon } = element;
      return cleanIcon;
    }
    return element;
  });

  return {
    processedPAGE: { ...PAGE, elements: processedElements },
    imageMap,
    chartMap
  };
};

const restoreImagesToPAGE = (PAGE, imageMap) => {
  if (!PAGE || !PAGE.elements) return PAGE;

  // Helper: apply saved geometry — only fill in props the AI zeroed/dropped
  const applyGeometry = (el, geo) => {
    if (!geo) return el;
    const patched = { ...el };
    for (const key of Object.keys(geo)) {
      // Restore geometry if AI dropped it (undefined) or set to zero on a dimension
      if (patched[key] === undefined || ((key === 'width' || key === 'height') && !patched[key])) {
        patched[key] = geo[key];
      }
    }
    return patched;
  };

  const restoredElements = PAGE.elements.map(element => {
    // SMART IMAGE RESTORE: If AI kept the description unchanged, restore original image
    if (element.type === 'image_placeholder') {
      const origKey = `_orig_${element.id}`;
      const original = imageMap[origKey];
      if (original) {
        // User-media images: ALWAYS restore (never regenerate user uploads)
        if (original.isUserMedia && original.src) {
          const { imageDescription, imageType, ...rest } = element;
          return applyGeometry({ ...rest, type: 'image', src: original.src, isUserMedia: true, imageDescription: original.imageDescription }, original.geometry);
        }
        const currentDesc = (element.imageDescription || '').trim();
        const originalDesc = (original.imageDescription || '').trim();
        // Description unchanged (or both empty/default) → restore original image
        if (currentDesc === originalDesc || currentDesc === 'existing image' && !originalDesc) {
          if (original.src) {
            const { imageDescription, imageType, ...rest } = element;
            return applyGeometry({ ...rest, type: 'image', src: original.src, imageDescription: original.imageDescription }, original.geometry);
          }
          // Original had no src (image never generated) — leave as placeholder for regeneration
        }
        // Description changed by AI → leave as image_placeholder for regeneration
      }
      // No original found → new placeholder from AI, leave for generation
      return element;
    }

    // AI MISTAKE RECOVERY: AI sometimes returns type='image' instead of 'image_placeholder' without src
    if (element.type === 'image' && !element.src) {
      const origKey = `_orig_${element.id}`;
      const original = imageMap[origKey];
      if (original && original.src) {
        const restored = applyGeometry({ ...element, src: original.src, imageDescription: original.imageDescription || element.imageDescription }, original.geometry);
        if (original.isUserMedia) restored.isUserMedia = true;
        return restored;
      }
      // Can't restore — convert to image_placeholder so generateImagesParallel picks it up
      return { ...element, type: 'image_placeholder', imageDescription: element.imageDescription || 'professional image' };
    }

    // USER MEDIA + VIDEOS/DIAGRAMS: Restore {{UserMedia_xxx}} placeholders
    const isMediaWithPlaceholder = (element.type === 'image' || element.type === 'video' || element.type === 'diagram')
      && element.src && typeof element.src === 'string' && element.src.startsWith('{{');
    if (isMediaWithPlaceholder) {
      const match = element.src.match(/^{{((?:UserMedia|UserImage)_[^}]+)}}$/);
      if (match && match[1] && imageMap[match[1]]) {
        // Restore src; also apply geometry from _orig_ if available
        const origKey = `_orig_${element.id}`;
        const original = imageMap[origKey];
        const restored = { ...element, src: imageMap[match[1]], isUserMedia: true };
        return original?.geometry ? applyGeometry(restored, original.geometry) : restored;
      }
    }

    // FINAL FALLBACK: If AI changed the element type entirely but _orig_ exists, force-recover
    const origKey = `_orig_${element.id}`;
    const original = imageMap[origKey];
    if (original && original.isUserMedia && original.src && element.type !== 'image') {
      console.warn(`⚠️ [RESTORE] User-media ${element.id} was changed to type '${element.type}' by AI — restoring as image`);
      return applyGeometry({ ...element, type: 'image', src: original.src, isUserMedia: true, imageDescription: original.imageDescription }, original.geometry);
    }

    return element;
  });

  // SAFETY NET: Re-inject any user media elements that AI dropped entirely from the output
  const restoredIds = new Set(restoredElements.map(el => el.id));
  for (const [key, value] of Object.entries(imageMap)) {
    if (!key.startsWith('_orig_')) continue;
    if (!value || !value.isUserMedia || !value.src) continue;
    const elId = key.slice(6); // strip '_orig_' prefix
    if (!restoredIds.has(elId)) {
      console.warn(`⚠️ [RESTORE] User-media ${elId} was dropped by AI — re-injecting from backup`);
      const recovered = { id: elId, type: 'image', src: value.src, isUserMedia: true, imageDescription: value.imageDescription || '' };
      if (value.geometry) {
        Object.assign(recovered, value.geometry);
      }
      restoredElements.push(recovered);
    }
  }

  return { ...PAGE, elements: restoredElements };
};

const PrintableComposer = ({
  visible,
  onClose,
  onClearPrintable,
  theme,
  userDeviceId,
  apiConfig,
  persona,
  personaText,
  initialPrintable = null,
  prefillGoal = null,        // {goal, slide_count, prefetched_corpus} from a chat open_builder handoff
  onUsePrefill = null,       // called once the prefill has been consumed
  selectedFolders = [],
  folders = [],
  onOpenTemplateUpload, // Legacy callback - now using internal modal
  // Upload modal props - rendered inside fullScreen portal to appear on top
  uploadModalProps = null,
  enhancedProgress = null, // Upload progress for popup visibility inside modals
  onDismissUploadEntry = null, // Callback to remove a single upload entry from progress map
  mobileViewOnly = false, // Mobile web: view-only mode, no editing
  userType = 'free', // User plan type for export branding
  onOpenCredits = () => { }, // Callback to open credits/upgrade modal
}) => {
  // DEBUG: Log what props we receive
  // console.log('🎨 [COMPOSER_PROPS] PrintableComposer received:', {
  //   visible,
  //   hasInitialPrintable: !!initialPrintable,
  //   initialPrintableId: initialPrintable?._id || initialPrintable?.id,
  //   initialPrintableTitle: initialPrintable?.title,
  //   initialPrintablePages: initialPrintable?.pages?.length || initialPrintable?.PAGES?.length,
  // });

  const { useUploadedData } = useWorkspace();

  // State Declarations (Moved up to fix ReferenceError)
  const [showGoalSetting, setShowGoalSetting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showprintableList, setShowprintableList] = useState(false);
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [currentPrintableId, setCurrentPrintableId] = useState(null);
  const [isLoadingPrintable, setIsLoadingprintable] = useState(false);
  const [printableGoal, setprintableGoal] = useState(null);
  const [printableStyle, setprintableStyle] = useState(PRESET_STYLES[0]);
  const [headerFooter, setHeaderFooter] = useState(DEFAULT_HEADER_FOOTER);
  const [slideNumbers, setSlideNumbers] = useState(DEFAULT_SLIDE_NUMBERS);
  const [printableTitle, setprintableTitle] = useState('Untitled');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [selectedElementIds, setSelectedElementIds] = useState([]); // Array for multi-select
  const [isGeneratingStyle, setIsGeneratingStyle] = useState(false);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);
  const [insertPAGEIndex, setInsertPAGEIndex] = useState(null);
  const [showArrangeModal, setShowArrangeModal] = useState(false);
  const [targetPAGEIdForLayoutChange, setTargetPAGEIdForLayoutChange] = useState(null);
  const [showAnalyticsModal, setShowAnalyticsModal] = useState(false); // Analytics modal state
  const [showFolderDetailModal, setShowFolderDetailModal] = useState(false); // Folder detail popup state
  const [showCollaborationPanel, setShowCollaborationPanel] = useState(false); // Collaboration panel state
  const [showQualityModal, setShowQualityModal] = useState(false);
  const generationQuality = printableGoal?.generationQuality || 'premium';
  const qualityLabel = generationQuality === 'premium' ? 'Premium' : generationQuality === 'medium' ? 'Medium' : 'Basic';
  const qualityColor = generationQuality === 'premium' ? '#6366F1' : generationQuality === 'medium' ? '#F59E0B' : '#9CA3AF';
  const [authToken, setAuthToken] = useState(null);
  const [userEmail, setUserEmail] = useState(null);
  const [isRefreshingOutline, setIsRefreshingOutline] = useState(false);

  // Collaborative Setup
  // We use currentPrintableId or initialPrintable.id
  // If neither, collaboration is disabled until saved
  const collabDocId = currentPrintableId || initialPrintable?.id;

  // Determine collaboration mode from sharing metadata
  const sharingInfo = initialPrintable?.sharing;
  const isOwner = sharingInfo?.is_owner ?? true;
  const isSharedForCollaboration = sharingInfo?.is_shared_for_collaboration ?? false;
  const userPermission = sharingInfo?.user_permission;

  const isItemOwner = initialPrintable?.user_id != null ? initialPrintable.user_id === userDeviceId : isOwner;

  const canCollaborate = isSharedForCollaboration &&
    (userPermission === 'owner' || userPermission === 'write');

  const isReadOnly = !isOwner && userPermission === 'read';

  const collaboration = useCollaboration({
    docId: collabDocId,
    enabled: !!collabDocId && canCollaborate,
    // User info should ideally come from authService/Context. For now basic stub or we fetch it.
    // Assuming useCollaboration handles user info or we pass it? 
    // If we don't pass user, it might default.
    // Let's rely on useCollaboration defaults or auth context if integrated.
  });

  const {
    aiLockedBy,
    requestAiLock,
    releaseAiLock,
    refreshAiLock,
    // Granular locks
    documentLock,
    PAGELocks,
    requestDocumentLock,
    releaseDocumentLock,
    requestPAGELock,
    releasePAGELock,
    isPAGELocked,
    releaseAllLocks
  } = collaboration;

  // Check if AI is locked by someone else (legacy)
  const isAiLocked = canCollaborate && aiLockedBy && collaboration.ydoc && aiLockedBy.clientId !== collaboration.ydoc.clientID;
  const lockedByUser = aiLockedBy ? aiLockedBy.user : null;

  // Check if document is locked (for Update button)
  const isDocumentLocked = canCollaborate && documentLock && collaboration.ydoc && documentLock.clientId !== collaboration.ydoc.clientID;
  const documentLockedBy = documentLock ? documentLock.user : null;


  // PAGE management hooks
  const {
    PAGES,
    setPAGES,
    currentPAGEId,
    setCurrentPAGEId,
    addPAGE,
    deletePAGE,
    insertPAGE,
    reorderPAGES,
    updatePAGE,
    updatePAGETitle,
    updatePAGEBackground, // For background color changes
    addElement,
    updateElement,
    updateMultipleElements,
    deleteElement,
    deleteMultipleElements,
    getPAGEById,
    applyStyleToAllPAGES,
    togglePAGEHidden,
  } = usePrintablePages(initialPrintable, collaboration);

  const {
    savePrintable,
    savePrintableToServer,
    loadPrintable,
    isSaving,
    lastSaved,
  } = usePrintablePersistence();

  // Clipboard hook for copy/paste/format painter
  const {
    copyElements,
    copySlide: copyPAGE,
    copyFormat,
    parsePastedElements,
    canApplyFormat,
    getApplicableFormat,
  } = useClipboard();

  // Format Painter state
  const [formatPainterActive, setFormatPainterActive] = useState(false);
  const [formatPainterData, setFormatPainterData] = useState(null);

  // Get current PAGE (Moved up to fix initialization error)
  const currentPAGE = useMemo(() => {
    return PAGES.find(s => s.id === currentPAGEId) || PAGES[0];
  }, [PAGES, currentPAGEId]);

  const currentPAGEIndex = useMemo(() => {
    return PAGES.findIndex(s => s.id === currentPAGEId);
  }, [PAGES, currentPAGEId]);

  // Visible pages (excludes hidden) — used for Present, Export
  const visiblePAGES = useMemo(() => PAGES.filter(p => !p.hidden), [PAGES]);

  // State


  // Upload modal state - rendered inside fullScreen portal to appear on top
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);

  // PAGE panel view mode: 'thumbnail' or 'list'
  const [PAGEPanelViewMode, setPAGEPanelViewMode] = useState('thumbnail');

  // Load PAGE panel view preference from AsyncStorage
  useEffect(() => {
    const loadViewPreference = async () => {
      try {
        const savedMode = await AsyncStorage.getItem('@PAGE_panel_view_mode');
        if (savedMode && (savedMode === 'thumbnail' || savedMode === 'list')) {
          setPAGEPanelViewMode(savedMode);
        }
      } catch (err) {
        console.log('[COMPOSER] Failed to load view preference:', err);
      }
    };
    loadViewPreference();
  }, []);

  // Save PAGE panel view preference
  const togglePAGEPanelView = useCallback(async () => {
    const newMode = PAGEPanelViewMode === 'thumbnail' ? 'list' : 'thumbnail';
    setPAGEPanelViewMode(newMode);
    try {
      await AsyncStorage.setItem('@PAGE_panel_view_mode', newMode);
    } catch (err) {
      console.log('[COMPOSER] Failed to save view preference:', err);
    }
  }, [PAGEPanelViewMode]);

  // Canvas scaling state
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  // FIX: Start at 0 — don't render canvas at scale=1 before container is measured.
  // On mobile, scale=1 creates a full 794x1123 canvas; async image loads capture stale
  // positions (scaledX = x*1) that persist after the real scale (~0.42) is applied.
  const [canvasScale, setCanvasScale] = useState(0);

  // Calculate scale when container dimensions change
  // For A4 portrait pages, we scale to fit width and allow vertical scrolling
  useEffect(() => {
    if (containerSize.width > 0 && containerSize.height > 0) {
      // For printable A4 pages, scale to fit width with padding and allow vertical scroll
      // Use width-based scaling only so pages can scroll vertically
      const scaleX = (containerSize.width - 40) / PAGE_WIDTH; // 40px padding
      const newScale = Math.min(scaleX, 1.2) * 0.95; // Cap max scale, add safety margin

      // console.log('📏 [COMPOSER] Recalculating scale for A4 page:', {
      //   container: containerSize,
      //   page: { w: PAGE_WIDTH, h: PAGE_HEIGHT },
      //   newScale
      // });

      setCanvasScale(newScale);
    }
  }, [containerSize]);

  // Selection mode: derive from selectedElementIds
  const selectedElements = useMemo(() => {
    const PAGE = PAGES.find(s => s.id === currentPAGEId);
    if (!PAGE || selectedElementIds.length === 0) return [];
    return PAGE.elements?.filter(el => selectedElementIds.includes(el.id)) || [];
  }, [PAGES, currentPAGEId, selectedElementIds]);

  // Clear element selection when PAGE changes via user interaction (not scroll tracking)
  const pageChangeFromInteraction = useRef(false);
  const scrollDrivenChange = useRef(false); // Flag: page change came from scroll detection (suppress sidebar auto-scroll)
  const actionBtnGuard = useRef(false); // Prevent parent onPress when action button clicked on web
  const skipSidebarScroll = useRef(false); // Skip sidebar auto-scroll on sidebar click
  useEffect(() => {
    if (pageChangeFromInteraction.current) {
      setSelectedElementIds([]);
      pageChangeFromInteraction.current = false;
    }

    // Auto-scroll sidebar to keep active thumbnail visible
    // Skip when: (a) click came from sidebar itself, or (b) change was scroll-driven (user is scrolling main panel)
    if (currentPAGEId && sidebarScrollRef.current && !skipSidebarScroll.current && !scrollDrivenChange.current) {
      const sidebarLayout = sidebarLayoutsRef.current[currentPAGEId];
      if (sidebarLayout) {
        sidebarScrollRef.current.scrollTo({ y: Math.max(0, sidebarLayout.y - 40), animated: true });
      }
    }
    skipSidebarScroll.current = false;
    scrollDrivenChange.current = false;
  }, [currentPAGEId]);

  // Backward compat: single element reference
  const selectedElement = selectedElements.length === 1 ? selectedElements[0] : null;
  const selectedElementId = selectedElementIds.length === 1 ? selectedElementIds[0] : null;

  // Edit mode: 'PAGE', 'element' (single), or 'multi' (multiple)
  const editMode = selectedElements.length === 0 ? 'PAGE' : (selectedElements.length === 1 ? 'element' : 'multi');

  // Helper to get element type label for mode indicator
  const getElementTypeLabel = useCallback((elements) => {
    if (!elements || elements.length === 0) return 'Full PAGE';
    if (elements.length === 1) {
      const element = elements[0];
      switch (element.type) {
        case 'text': return 'Text Box';
        case 'image': return 'Image';
        case 'shape': return 'Shape';
        case 'icon': return 'Icon';
        case 'card': return 'Card';
        case 'chart': return 'Chart';
        case 'image_placeholder': return 'Image Placeholder';
        default: return 'Element';
      }
    }
    return `${elements.length} Elements`;
  }, []);
  const [customStyles, setCustomStyles] = useState([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showSaveModal, setShowSaveModal] = useState(false); // New state for Save Modal
  const [isSavingManual, setIsSavingManual] = useState(false); // Overlay during manual save
  const [isGeneratingThumbnails, setIsGeneratingThumbnails] = useState(false); // Overlay during background thumbnail generation

  // Pre-cache all images and icons across all PAGES before entering presentation mode
  // This ensures zero-delay rendering when navigating between pages
  const startPresentation = useCallback(async () => {
    if (!PAGES || PAGES.length === 0) return;

    // Request fullscreen BEFORE any await — must be in user gesture context
    if (Platform.OS === 'web') {
      try {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
      } catch (e) { /* ignore */ }
    }

    // Collect all image URLs and icon names across all pages
    const imageUrls = [];
    const iconNames = [];

    PAGES.forEach(page => {
      (page.elements || []).forEach(el => {
        if (el.type === 'image' && el.src && el.src.startsWith('http')) {
          imageUrls.push(el.src);
        }
        if (el.type === 'icon') {
          const name = el.iconName || el.resolvedIconName || el.name;
          if (name) iconNames.push(name);
        }
      });
    });

    // Fire-and-forget pre-caching (don't block presentation start)
    // Images and icons will load from cache if ready, or from network if still fetching
    if (imageUrls.length > 0) {
      console.log(`🖼️ [PRESENT] Pre-caching ${imageUrls.length} images for presentation mode`);
      globalImageCache.preCacheAll(imageUrls).catch(() => { });
    }
    if (iconNames.length > 0) {
      console.log(`🎨 [PRESENT] Pre-fetching ${iconNames.length} icons for presentation mode`);
      prefetchIcons(iconNames).catch(() => { });
    }

    setIsPlaying(true);
  }, [PAGES]);

  // Progressive generation progress tracking
  const [isGeneratingPAGES, setIsGeneratingPAGES] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0 });

  // Keep ref in sync with isGeneratingPAGES state for use in callbacks
  useEffect(() => {
    isGeneratingPAGESRef.current = isGeneratingPAGES;
  }, [isGeneratingPAGES]);

  // Auto Update progress tracking
  const [isAutoUpdating, setIsAutoUpdating] = useState(false);

  // Keep ref in sync with isAutoUpdating state for use in callbacks
  useEffect(() => {
    isAutoUpdatingRef.current = isAutoUpdating;
  }, [isAutoUpdating]);
  const [autoUpdateProgress, setAutoUpdateProgress] = useState({ current: 0, total: 0 });
  const [showUpdateInstructionModal, setShowUpdateInstructionModal] = useState(false); // New State

  // PAGE editing state
  const [editingPAGEId, setEditingPAGEId] = useState(null);
  const [editingPAGETitleText, setEditingPAGETitleText] = useState('');

  // Edit page outline modal state
  const [editOutlinePAGE, setEditOutlinePAGE] = useState(null);

  // Delete confirmation modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [PAGEToDelete, setPAGEToDelete] = useState(null);

  // Close confirmation modal
  const [showCloseConfirmModal, setShowCloseConfirmModal] = useState(false);

  // UI State
  const [sidebarWidth, setSidebarWidth] = useState(150);
  const sidebarWidthRef = useRef(150);
  const leftDragStartWidthRef = useRef(150);

  const [rightSidebarWidth, setRightSidebarWidth] = useState(300);
  const rightSidebarWidthRef = useRef(300);
  const rightDragStartWidthRef = useRef(300);

  const sidebarScrollRef = useRef(null); // ScrollView for sidebar thumbnail list
  const sidebarLayoutsRef = useRef({}); // { pageId: { y, height } } from sidebar onLayout

  // PAGE thumbnail cache for sidebar preview
  const [PAGEThumbnails, setPAGEThumbnails] = useState({});
  const thumbnailGenerationRef = useRef(null);
  const initialThumbnailGeneratedRef = useRef(new Set()); // Track PAGES that have had initial thumbnail generated
  const backgroundThumbnailQueueRef = useRef(null); // Track background thumbnail generation queue
  const thumbnailQueueStartedRef = useRef(false); // Prevent queue from restarting during cycling
  const isGeneratingPAGESRef = useRef(false); // Mirror of isGeneratingPAGES for use in callbacks
  const isAutoUpdatingRef = useRef(false); // Mirror of isAutoUpdating for use in callbacks
  const isAiProcessingRef = useRef(false); // Mirror of isAiProcessing for use in callbacks
  const pendingLayoutFixRef = useRef(new Set()); // Track pages needing auto layout fix after render
  const critiquedPagesRef = useRef(new Set()); // Track pages we've already sent through the vision critique loop
  const inFlightCritiquesRef = useRef(new Set()); // Track in-flight critiques to dedupe overlapping render-complete callbacks
  const handleAiEnhanceRef = useRef(null); // Ref to handleAiEnhance for use in effects
  const aiChatScrollRef = useRef(null); // Auto-scroll AI chat (main right panel)
  const aiChatScrollMobileRef = useRef(null); // Auto-scroll AI chat (mobile compact panel)
  const userDismissedGoalModalRef = useRef(false); // Track if user manually dismissed goal modal
  const hasInitializedNewprintableRef = useRef(false); // Track if new printable flow was initialized
  const lastLoadedPrintableIdRef = useRef(null); // Track last loaded printable to prevent re-loading and overwriting local edits

  // Sync refs with state
  useEffect(() => {
    sidebarWidthRef.current = sidebarWidth;
  }, [sidebarWidth]);

  useEffect(() => {
    rightSidebarWidthRef.current = rightSidebarWidth;
  }, [rightSidebarWidth]);

  // Left Resizer PanResponder
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        // Capture the width at the start of the drag
        leftDragStartWidthRef.current = sidebarWidthRef.current;
      },
      onPanResponderMove: (_, gestureState) => {
        const newWidth = Math.max(100, Math.min(600, leftDragStartWidthRef.current + gestureState.dx));
        setSidebarWidth(newWidth);
      },
    })
  ).current;

  // Right Resizer PanResponder
  const rightPanResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        rightDragStartWidthRef.current = rightSidebarWidthRef.current;
      },
      onPanResponderMove: (_, gestureState) => {
        // Dragging left (negative dx) increases width, dragging right (positive dx) decreases width
        const newWidth = Math.max(250, Math.min(600, rightDragStartWidthRef.current - gestureState.dx));
        setRightSidebarWidth(newWidth);
      },
    })
  ).current;

  // Mobile segmented control state - toggle between tools and AI chat
  const [mobileEditMode, setMobileEditMode] = useState('tools'); // 'tools' | 'chat'

  // AI Chat state
  const [chatInput, setChatInput] = useState('');
  // Screenshots pasted into the AI chat — ride along on the next send as
  // `image_attachments`, OCR'd server-side into the instruction context.
  const [aiPastedImages, setAiPastedImages] = useState([]);
  const aiChatFocusedRef = useRef(false);
  const [isAiProcessing, setIsAiProcessing] = useState(false);

  // Keep ref in sync with isAiProcessing state for use in callbacks
  useEffect(() => {
    isAiProcessingRef.current = isAiProcessing;
  }, [isAiProcessing]);

  const [showChartStudio, setShowChartStudio] = useState(false);
  const [showAIImageModal, setShowAIImageModal] = useState(false); // New AI Image State
  const [showAIDiagramModal, setShowAIDiagramModal] = useState(false); // AI SVG Diagram modal
  // When set, the AIDiagramModal opens prefilled and on insert REPLACES the existing element instead of adding a new one.
  const [diagramRegenContext, setDiagramRegenContext] = useState(null); // { elementId, prompt, diagramKind } | null
  const [showChartEditModal, setShowChartEditModal] = useState(false); // Chart edit modal
  const [aiChatMessages, setAiChatMessages] = useState([]); // AI chat message history
  const [editingChartElementId, setEditingChartElementId] = useState(null); // Element being edited
  const [editingChartConfig, setEditingChartConfig] = useState(null); // Chart config being edited

  // Handler for AI Image Gen
  const handleGenerateImage = useCallback(() => {
    setShowAIImageModal(true);
  }, []);

  // Handler for Chart Edit (double-click on chart)
  const handleEditChart = useCallback((elementId, chartConfig) => {
    console.log('📊 [COMPOSER] Opening chart editor for:', elementId);
    setEditingChartElementId(elementId);
    setEditingChartConfig(chartConfig);
    setShowChartEditModal(true);
  }, []);

  // Handler for saving edited chart
  const handleSaveChartEdit = useCallback((newChartConfig) => {
    if (editingChartElementId && currentPAGE?.id) {
      console.log('📊 [COMPOSER] Saving chart edit for:', editingChartElementId);
      updateElement(currentPAGE.id, editingChartElementId, {
        chartConfig: newChartConfig,
      });
    }
    setShowChartEditModal(false);
    setEditingChartElementId(null);
    setEditingChartConfig(null);
  }, [editingChartElementId, currentPAGE?.id, updateElement]);

  // Right panel tab state: 'ai' (default) or 'layers'
  const [rightPanelTab, setRightPanelTab] = useState('ai');

  // Refs
  const canvasRef = useRef(null);
  const canvasRefsMap = useRef(new Map()); // Map<pageId, React.RefObject>
  const activeCanvasRef = useRef(null); // Points to the currently focused canvas ref
  const contentScrollRef = useRef(null); // ScrollView for vertical page scroll
  const pageLayoutsRef = useRef({}); // { pageId: { y, height } } from onLayout
  const scrollTrackingEnabled = useRef(true); // Disable during programmatic scrolls
  const lastScrollPositionRef = useRef({ scrollY: 0, layoutH: 0 }); // Latest scroll position for visible page sync


  // Shared toolbar selection state (updated via onElementSelectionChange from active canvas)
  const [selectionInfo, setSelectionInfo] = useState({ hasSelection: false });

  // Default theme
  const safeTheme = theme || {
    background: '#ffffff',
    text: '#333333',
    primary: '#2196F3',
    surface: '#f5f5f5',
    border: '#e0e0e0',
    isDark: false,
  };
  // Both side panels below are FIXED light surfaces (styles.sidebar with a
  // hardcoded '#ffffff' at each call site), while safeTheme is the APP theme --
  // dark. Taking label colour from it painted every caption and chip at
  // ~#e0e0e0 on white: visible as shapes, reading as disabled. Same fix and
  // same reasoning as TOOLBAR_CHROME in PrintableSharedToolbar, which landed on
  // the toolbar only -- which is why the bar looked right and the panels either
  // side of it looked switched off.
  const panelTheme = {
    ...safeTheme,
    text: '#374151',          // ~10.4:1 on white
    textSecondary: '#6B7280', // ~4.8:1 -- clears the 4.5:1 WCAG AA floor
    border: '#E5E7EB',
    surface: '#F9FAFB',
    isDark: false,
  };



  // Edit Scope State ('element' | 'page' | 'all')
  // Edit scope is GONE as a UI concept — the agentic editor auto-detects intent
  // and target from chat. The constant remains only because the legacy
  // handleAiEnhance (media-element pixel edits) still reads it.
  const editScope = 'page';

  // Get vault name(s) for display
  const vaultDisplayName = useMemo(() => {
    if (!selectedFolders || selectedFolders.length === 0) return null;
    if (selectedFolders.length === 1) {
      return selectedFolders[0].name || selectedFolders[0].folder_name || 'Data Store';
    }
    return `${selectedFolders.length} data stores`;
  }, [selectedFolders]);

  // Generate thumbnail for a specific PAGE (for sidebar preview)
  // Returns true if successful, false otherwise
  // Wait until all image elements on the canvas have loaded (fabric.Image objects with valid _element)
  const waitForCanvasImages = useCallback(async (page, maxWait = 5000) => {
    if (!page?.id || !page?.elements) return;
    const pageRef = canvasRefsMap.current.get(page.id);
    if (!pageRef?.current) return;
    const imageCount = page.elements.filter(e => e.type === 'image' && e.src).length;
    if (imageCount === 0) return; // No images to wait for

    const start = Date.now();
    while (Date.now() - start < maxWait) {
      const canvas = pageRef.current;
      if (!canvas?.getObjects) break;
      const fabricImages = canvas.getObjects().filter(
        o => (o.type === 'image' || (o.type === 'group' && o.elementId)) && o._element
      );
      if (fabricImages.length >= imageCount) return; // All loaded
      await new Promise(r => setTimeout(r, 200));
    }
  }, []);

  const generatePAGEThumbnail = useCallback(async (PAGEId, isInitialGeneration = false) => {
    if (!PAGEId) {
      // console.log('📸 [THUMBNAIL] Skipped - no PAGEId');
      return false;
    }

    const pageRef = canvasRefsMap.current.get(PAGEId);
    if (!pageRef?.current?.toDataURL) {
      // console.log('📸 [THUMBNAIL] Skipped - canvas not ready for PAGE:', PAGEId);
      return false;
    }

    try {
      const dataUrl = await pageRef.current.toDataURL({ format: 'jpeg', quality: 0.5 });

      if (!dataUrl) {
        // console.log('📸 [THUMBNAIL] Skipped - no dataUrl returned for PAGE:', PAGEId);
        return false;
      }

      setPAGEThumbnails(prev => ({
        ...prev,
        [PAGEId]: dataUrl
      }));

      // Only mark as initially generated after successful generation
      if (isInitialGeneration) {
        initialThumbnailGeneratedRef.current.add(PAGEId);
      }

      // console.log('📸 [THUMBNAIL] Generated thumbnail for PAGE:', PAGEId);
      return true;
    } catch (err) {
      console.warn('📸 [THUMBNAIL] Failed to generate PAGE thumbnail:', PAGEId, err);
      return false;
    }
  }, []);

  // Process thumbnail queue - generates thumbnails for PAGES in the background
  // Handle initialPrintable prop changes - must also run when visible changes
  useEffect(() => {
    if (!visible) return; // Only process when composer is visible

    if (initialPrintable && initialPrintable.id) {
      console.log('🔄 [COMPOSER] Loading printable prop:', {
        id: initialPrintable.id,
        title: initialPrintable.title,
        PAGECount: initialPrintable.PAGES?.length || 0,
        hasGoal: !!initialPrintable.goal,
        hasStyle: !!initialPrintable.style
      });

      // If we only have an ID (stub object from URL routing), fetch the full data
      if (!initialPrintable.PAGES && !initialPrintable.title) {
        console.log('🔄 [COMPOSER] Only ID provided, fetching full printable data...');
        // Fetch the full printable data
        const fetchFullPrintable = async () => {
          try {
            const token = await AsyncStorage.getItem('@auth_token');
            const email = await authService.getCurrentUserEmail();
            if (!email) {
              console.warn('⚠️ [COMPOSER] No user email available for fetch');
              return;
            }
            const response = await fetch(
              `${apiConfig.API_URL}/printable/load/${initialPrintable.id}`,
              {
                headers: {
                  'Authorization': `Bearer ${token}`,
                  'Content-Type': 'application/json'
                }
              }
            );
            if (response.ok) {
              const data = await response.json();
              const fullPrintable = data.printable || data;
              console.log('✅ [COMPOSER] Fetched full printable:', fullPrintable.title);

              // Now load the full data
              setCurrentPrintableId(fullPrintable.id);
              setprintableTitle(fullPrintable.title || 'Untitled');
              if (fullPrintable.goal) {
                if (typeof fullPrintable.goal === 'string') {
                  setprintableGoal({ purpose: fullPrintable.goal });
                } else {
                  setprintableGoal(fullPrintable.goal);
                }
              }
              if (fullPrintable.style) {
                // Hydrate deck chrome into its own state and keep it OUT of the
                // style object; ALWAYS set (defaults fallback) so no chrome
                // bleeds across documents.
                const { headerFooter: _hfIn, slideNumbers: _snIn, ...cleanStyle } = fullPrintable.style;
                setprintableStyle(cleanStyle);
                setHeaderFooter({ ...DEFAULT_HEADER_FOOTER, ...(_hfIn || {}) });
                setSlideNumbers({ ...DEFAULT_SLIDE_NUMBERS, ...(_snIn || {}) });
              }
              if (fullPrintable.PAGES && fullPrintable.PAGES.length > 0) {
                const sanitizedPAGES = sanitizeFabricData ? sanitizeFabricData(fullPrintable.PAGES) : fullPrintable.PAGES;

                // Restore per-page thumbnails from saved data
                const restoredThumbnails = {};
                sanitizedPAGES.forEach(page => {
                  if (page.pageThumbnail) {
                    restoredThumbnails[page.id] = page.pageThumbnail;
                    initialThumbnailGeneratedRef.current.add(page.id);
                  }
                });
                if (Object.keys(restoredThumbnails).length > 0) {
                  setPAGEThumbnails(restoredThumbnails);
                  console.log('\ud83d\udcf8 [THUMBNAIL] Restored', Object.keys(restoredThumbnails).length, 'thumbnails from saved data');
                }

                // Strip pageThumbnail from working state. Also strip
                // `critique_recommended` — a transient post-generation signal that
                // drives the per-page vision critique. A saved doc was already
                // critiqued at build time; edits re-set it via the enhance endpoint,
                // so loading alone must not re-run the OCR critique pass.
                const cleanPAGES = sanitizedPAGES.map(
                  ({ pageThumbnail, critique_recommended, ...rest }) => rest
                );
                setPAGES(cleanPAGES);
                setCurrentPAGEId(fullPrintable.PAGES[0].id);
              }
              setShowGoalSetting(false);
            } else {
              console.error('❌ [COMPOSER] Failed to fetch printable:', response.status);
            }
          } catch (err) {
            console.error('❌ [COMPOSER] Error fetching printable:', err);
          }
        };
        fetchFullPrintable();
        return;
      }

      // CRITICAL FIX: Only load printable data when loading a DIFFERENT printable
      // This prevents overwriting local edits when the same printable prop is passed again
      const isNewPrintable = lastLoadedPrintableIdRef.current !== initialPrintable.id;

      if (isNewPrintable) {
        // console.log('📥 [COMPOSER] Loading NEW printable - resetting PAGES');
        lastLoadedPrintableIdRef.current = initialPrintable.id;

        // Clear old thumbnails and abort any background queue
        setPAGEThumbnails({});
        initialThumbnailGeneratedRef.current.clear();
        critiquedPagesRef.current.clear();
        inFlightCritiquesRef.current.clear();
        thumbnailQueueStartedRef.current = false;
        if (backgroundThumbnailQueueRef.current) backgroundThumbnailQueueRef.current.aborted = true;

        setCurrentPrintableId(initialPrintable.id);
        setprintableTitle(initialPrintable.title || 'Untitled');
        if (initialPrintable.goal) {
          // Fix for nested goal object issue: Only wrap if it's a string
          if (typeof initialPrintable.goal === 'string') {
            setprintableGoal({ purpose: initialPrintable.goal });
          } else {
            setprintableGoal(initialPrintable.goal);
          }
        }
        if (initialPrintable.style) {
          // Hydrate deck chrome into its own state and keep it OUT of the style
          // object (stale embedded copies contradict live state in agent
          // payloads); ALWAYS set so no chrome bleeds across documents.
          const { headerFooter: _hfIn, slideNumbers: _snIn, ...cleanStyle } = initialPrintable.style;
          setprintableStyle(cleanStyle);
          setHeaderFooter({ ...DEFAULT_HEADER_FOOTER, ...(_hfIn || {}) });
          setSlideNumbers({ ...DEFAULT_SLIDE_NUMBERS, ...(_snIn || {}) });
        }
        // CRITICAL: Update PAGES with fresh data (new signed URLs) from backend
        if (initialPrintable.PAGES && initialPrintable.PAGES.length > 0) {
          // console.log('🔄 [printable] Updating PAGES from prop (Refreshed URLs)');
          // SANITIZE: cleanup invalid textBaseline from DB data
          const sanitizedPAGES = sanitizeFabricData ? sanitizeFabricData(initialPrintable.PAGES) : initialPrintable.PAGES;

          // Restore per-page thumbnails from saved data
          const restoredThumbnails = {};
          sanitizedPAGES.forEach(page => {
            if (page.pageThumbnail) {
              restoredThumbnails[page.id] = page.pageThumbnail;
              initialThumbnailGeneratedRef.current.add(page.id);
            }
          });
          if (Object.keys(restoredThumbnails).length > 0) {
            setPAGEThumbnails(restoredThumbnails);
            // console.log('📸 [THUMBNAIL] Restored', Object.keys(restoredThumbnails).length, 'thumbnails from saved data');
          }

          // Strip pageThumbnail from working state to avoid duplicate base64 in
          // memory. Also strip `critique_recommended` — a transient post-generation
          // signal that drives the per-page vision critique. A saved doc was already
          // critiqued at build time; edits re-set it via the enhance endpoint, so
          // loading alone must not re-run the OCR critique pass.
          const cleanPAGES = sanitizedPAGES.map(
            ({ pageThumbnail, critique_recommended, ...rest }) => rest
          );
          setPAGES(cleanPAGES);
          // Always start on the first page when loading a printable
          setCurrentPAGEId(initialPrintable.PAGES[0].id);
          // Thumbnails restored from saved data; background queue will fill in any missing ones
        } else {
          console.warn('⚠️ [COMPOSER] Loaded printable has NO PAGES');
        }
        setShowGoalSetting(false);
      } else {
        console.log('🛡️ [COMPOSER] Same printable - preserving local edits');
      }
    } else if (initialPrintable === null && !hasInitializedNewprintableRef.current) {
      // GUARD: Don't run NEW flow if PAGES already contain real data from a previous load
      // This prevents a race condition where the hook loads data but useEffect sees null prop
      const hasLoadedPAGES = PAGES.length > 0 && PAGES[0].id && !PAGES[0].id.startsWith('PAGE_');

      // FIX: If we are explicitly starting a NEW printable (initialPrintable is null),
      // and we haven't initialized yet, we SHOULD overwrite any stale state.
      /*
      if (hasLoadedPAGES) {
        console.log('🛡️ [COMPOSER] Skipping NEW flow - PAGES already loaded with real data:', PAGES[0].id);
        return;
      }
      */

      // Creating new printable - open goal setting (only once)
      hasInitializedNewprintableRef.current = true;
      console.log('📊 [COMPOSER] Starting NEW printable flow (initialPrintable is null)');

      // Clear all old printable state
      setCurrentPrintableId(null);
      setprintableTitle('Untitled');
      setprintableGoal(null);
      setprintableStyle(PRESET_STYLES[0]);
      setHeaderFooter(DEFAULT_HEADER_FOOTER);
      setSlideNumbers(DEFAULT_SLIDE_NUMBERS);

      // Reset to a single blank PAGE
      const newPAGEId = `PAGE_${Date.now()}`;
      setPAGES([{
        id: newPAGEId,
        order: 1,
        title: 'Title PAGE',
        layout: 'title',
        elements: [],
        backgroundColor: '#ffffff',
        hasUnsavedChanges: false,
      }]);
      setCurrentPAGEId(newPAGEId);

      // Clear cached thumbnails and tracking for new printable
      setPAGEThumbnails({});
      initialThumbnailGeneratedRef.current.clear();
      critiquedPagesRef.current.clear();
      inFlightCritiquesRef.current.clear();

      // Clear any selected elements
      setSelectedElementIds([]);

      // Use setTimeout to ensure modal is fully rendered first
      setTimeout(() => {
        setShowGoalSetting(true);
      }, 100);
    }
  }, [initialPrintable, visible, setPAGES, setCurrentPAGEId]); // REMOVED 'PAGES' from deps - it caused re-runs on every edit

  // AI Assistant chat is per-printable + per-session. The composer stays
  // MOUNTED across opens (only `visible` toggles), so without this the chat
  // history from one document leaks into the next one the user opens. Reset it
  // whenever the composer closes OR a different printable is loaded.
  const loadedPrintableChatIdRef = useRef(undefined);
  useEffect(() => {
    const resetChat = () => {
      setAiChatMessages([]);
      setChatInput('');
      setAiPastedImages([]);
      setIsAiProcessing(false);
    };
    if (!visible) {
      loadedPrintableChatIdRef.current = undefined;
      resetChat();
      return;
    }
    const pid = initialPrintable?.id ?? '__new__';
    // Reset only on a genuine switch between documents. Skip the '__new__' →
    // real-id transition (a new doc being saved mid-session) so it can't wipe an
    // active conversation. The close path above covers the new→other case.
    if (loadedPrintableChatIdRef.current !== undefined &&
        loadedPrintableChatIdRef.current !== '__new__' &&
        loadedPrintableChatIdRef.current !== pid) {
      resetChat();
    }
    loadedPrintableChatIdRef.current = pid;
  }, [visible, initialPrintable]);

  // Show goal setting on first open
  useEffect(() => {
    if (visible && !printableGoal && PAGES.length === 1 && !PAGES[0].elements?.length && !isLoadingPrintable && !currentPrintableId && !initialPrintable && !userDismissedGoalModalRef.current) {
      setShowGoalSetting(true);
    }
    // Reset dismissal flag and loaded printable tracking when composer is closed
    if (!visible) {
      userDismissedGoalModalRef.current = false;
      hasInitializedNewprintableRef.current = false;
      lastLoadedPrintableIdRef.current = null; // Reset so re-opening loads fresh data
    }
  }, [visible, printableGoal, PAGES, isLoadingPrintable, currentPrintableId, initialPrintable]);

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

  // Load custom styles from storage on mount
  useEffect(() => {
    const loadCustomStyles = async () => {
      try {
        const savedStyles = await AsyncStorage.getItem('@custom_printable_styles');
        if (savedStyles) {
          const parsedStyles = JSON.parse(savedStyles);
          console.log('🎨 [printable] Loaded custom styles from storage:', parsedStyles.length);
          setCustomStyles(parsedStyles);
        }
      } catch (error) {
        console.error('Failed to load custom styles:', error);
      }
    };
    loadCustomStyles();
  }, []);

  // Auto-save REMOVED - Users must manually save to persist changes
  // This prevents unnecessary server load and quota issues

  // Helper to sanitize Fabric data (fix textBaseline warnings)
  const sanitizeFabricData = useCallback((data) => {
    if (!data) return data;
    const jsonStr = JSON.stringify(data);
    if (!jsonStr.includes('alphabetical')) return data;

    // Recursively traverse and fix
    const sanitize = (obj) => {
      if (typeof obj !== 'object' || obj === null) return obj;
      if (Array.isArray(obj)) return obj.map(sanitize);

      const newObj = { ...obj };
      for (const key in newObj) {
        if (key === 'textBaseline' && newObj[key] === 'alphabetical') {
          newObj[key] = 'alphabetic';
        } else if (typeof newObj[key] === 'object') {
          newObj[key] = sanitize(newObj[key]);
        }
      }
      return newObj;
    };
    console.log('🧹 [COMPOSER] Sanitizing PAGE data for textBaseline...');
    return sanitize(data);
  }, []);

  // Handle printable generated from goal setting - SUPPORTS PROGRESSIVE UPDATES
  const handlePrintableGenerated = useCallback((printableData) => {
    // Sanitize incoming data first
    if (printableData?.PAGES) {
      printableData.PAGES = sanitizeFabricData(printableData.PAGES);
    }

    const PAGECount = printableData.PAGES?.length || 0;
    const isProgressiveUpdate = printableData.isGenerating;

    console.log('🎬 Printable update:', PAGECount, 'PAGES', isProgressiveUpdate ? '(generating...)' : '(complete)');

    if (printableData.PAGES && PAGECount > 0) {
      // Use functional update to preserve any in-progress changes
      setPAGES(prevPAGES => {
        // Build map for fast lookup
        const prevMap = new Map(prevPAGES.map(s => [s.id, s]));
        const newPAGES = [];

        for (const incPAGE of printableData.PAGES) {
          if (prevMap.has(incPAGE.id)) {
            // EXISTING PAGE: Perform Smart Merge
            const existing = prevMap.get(incPAGE.id);

            // We want to keep user edits (existing) but accept AI updates (incPAGE)
            // primarily for Image Placeholders resolving to Images
            const mergedElements = existing.elements.map(existingEl => {
              // Find corresponding element in incoming data
              const incomingEl = incPAGE.elements?.find(e => e.id === existingEl.id);

              // CRITICAL: Only accept update if it's an Image Placeholder turning into an Image
              if (incomingEl && existingEl.type === 'image_placeholder' && incomingEl.type === 'image') {
                console.log(`🖼️ [COMPOSER] Apply AI Image update for element ${existingEl.id}`);
                return incomingEl;
              }
              // Otherwise keep user's version (preserves text edits, positions, etc.)
              return existingEl;
            });

            newPAGES.push({
              ...existing,
              elements: mergedElements,
              // Keep other user-modified props if needed, or prefer existing
            });
          } else {
            // NEW PAGE: Add it
            newPAGES.push({
              ...incPAGE,
              hasUnsavedChanges: false,
            });
            pendingLayoutFixRef.current.add(incPAGE.id);
          }
        }

        // CRITICAL: Sort by order to ensure pages display in correct sequence
        // even when they complete out of order during parallel generation
        return newPAGES.sort((a, b) => (a.order || 0) - (b.order || 0));
      });

      // Only set current PAGE ID if:
      // 1. We don't have a current PAGE yet, OR
      // 2. This is the initial generation (first PAGE appeared)
      setCurrentPAGEId(prevId => {
        if (!prevId || !printableData.PAGES.find(s => s.id === prevId)) {
          return printableData.PAGES[0].id;
        }
        return prevId;
      });
    } else if (!isProgressiveUpdate && PAGECount === 0) {
      // Only show first PAGE data log on initial call
      console.log('🎬 Initial generation starting, no PAGES yet');
    }

    if (printableData.style) {
      // Merge iconSet if available
      const styleUpdate = { ...printableData.style };
      if (printableData.iconSet) {
        styleUpdate.iconSet = printableData.iconSet;
      }
      setprintableStyle(styleUpdate);
    } else if (printableData.iconSet) {
      // Update existing style with iconSet
      setprintableStyle(prev => ({ ...prev, iconSet: printableData.iconSet }));
    }

    if (printableData.goal) {
      setprintableTitle(printableData.goal.substring(0, 50) || 'AI Dashboard');
    }

    // Close goal setting modal on first callback
    setShowGoalSetting(false);

    // Track generation progress
    if (printableData.isGenerating !== undefined) {
      setIsGeneratingPAGES(printableData.isGenerating);
      if (printableData.PAGEOutline) {
        setGenerationProgress({
          current: PAGECount,
          total: printableData.PAGEOutline.length
        });
      }
      // Thumbnails are generated on-demand when user manually navigates to each PAGE
    }
  }, [setPAGES, setCurrentPAGEId]);

  // Handle goal set
  const handleGoalSet = useCallback((goal) => {
    setprintableGoal(goal);
    if (goal.purpose) {
      setprintableTitle(goal.purpose.substring(0, 50) || 'AI Dashboard');
    }
  }, []);

  // Handle style change
  const handleStyleChange = useCallback((newStyle) => {
    setprintableStyle(newStyle);
    applyStyleToAllPAGES(newStyle);
    setShowStylePicker(false);
  }, [applyStyleToAllPAGES]);

  // Navigate PAGES (scrolls to prev/next in vertical scroll)
  const goToNextPAGE = useCallback(() => {
    const nextIndex = currentPAGEIndex + 1;
    if (nextIndex < PAGES.length) {
      const nextId = PAGES[nextIndex].id;
      pageChangeFromInteraction.current = true;
      setCurrentPAGEId(nextId);
      const layout = pageLayoutsRef.current[nextId];
      if (layout && contentScrollRef.current) {
        scrollTrackingEnabled.current = false;
        contentScrollRef.current.scrollTo({ y: layout.y - 16, animated: true });
        setTimeout(() => { scrollTrackingEnabled.current = true; }, 500);
      }
    }
  }, [currentPAGEIndex, PAGES, setCurrentPAGEId]);

  const goToPrevPAGE = useCallback(() => {
    const prevIndex = currentPAGEIndex - 1;
    if (prevIndex >= 0) {
      const prevId = PAGES[prevIndex].id;
      pageChangeFromInteraction.current = true;
      setCurrentPAGEId(prevId);
      const layout = pageLayoutsRef.current[prevId];
      if (layout && contentScrollRef.current) {
        scrollTrackingEnabled.current = false;
        contentScrollRef.current.scrollTo({ y: layout.y - 16, animated: true });
        setTimeout(() => { scrollTrackingEnabled.current = true; }, 500);
      }
    }
  }, [currentPAGEIndex, PAGES, setCurrentPAGEId]);

  // Get or create a canvas ref for a given page
  const getOrCreateCanvasRef = useCallback((pageId) => {
    if (!canvasRefsMap.current.has(pageId)) {
      canvasRefsMap.current.set(pageId, React.createRef());
    }
    return canvasRefsMap.current.get(pageId);
  }, []);

  // Helper: determine the most visible page from stored scroll position
  const getVisiblePageId = useCallback(() => {
    const { scrollY, layoutH } = lastScrollPositionRef.current;
    if (!layoutH) return null;
    const viewportMid = scrollY + (layoutH / 2);
    let closestPageId = null;
    let closestDist = Infinity;
    for (const [pageId, layout] of Object.entries(pageLayoutsRef.current)) {
      const pageMid = layout.y + layout.height / 2;
      const dist = Math.abs(viewportMid - pageMid);
      if (dist < closestDist) {
        closestDist = dist;
        closestPageId = pageId;
      }
    }
    return closestPageId;
  }, []);

  // Keep a ref in sync with currentPAGEId so the scroll handler stays stable
  const currentPAGEIdRef = useRef(currentPAGEId);
  useEffect(() => { currentPAGEIdRef.current = currentPAGEId; }, [currentPAGEId]);

  // STRUCTURAL-CHANGE GUARD: add / delete / duplicate / reorder reflows the
  // vertical page view. That reflow fires handleContentScroll, which would
  // otherwise recompute the "closest" page from the shifted layout and hijack
  // the current selection ("the list reshuffles on its own"). Whenever the
  // page id/order signature changes, suppress scroll-driven selection until the
  // reflow settles. Pure element edits don't change the signature, so they are
  // unaffected.
  const pageOrderSigRef = useRef('');
  useEffect(() => {
    const sig = PAGES.map(s => s.id).join('|');
    if (sig === pageOrderSigRef.current) return;
    const isInitial = pageOrderSigRef.current === '';
    pageOrderSigRef.current = sig;
    if (isInitial) return; // first mount — nothing to protect against yet
    scrollTrackingEnabled.current = false;
    const t = setTimeout(() => { scrollTrackingEnabled.current = true; }, 700);
    return () => clearTimeout(t);
  }, [PAGES]);

  // Keep activeCanvasRef/canvasRef synced with current page so toolbar undo/redo always targets the right canvas
  useEffect(() => {
    if (currentPAGEId && canvasRefsMap.current.has(currentPAGEId)) {
      const ref = canvasRefsMap.current.get(currentPAGEId);
      if (ref?.current) {
        activeCanvasRef.current = ref.current;
        canvasRef.current = ref.current;
      } else {
        // Canvas may not be mounted yet (new page just added) — retry after mount
        const retryTimer = setTimeout(() => {
          const retryRef = canvasRefsMap.current.get(currentPAGEId);
          if (retryRef?.current) {
            activeCanvasRef.current = retryRef.current;
            canvasRef.current = retryRef.current;
          }
        }, 100);
        return () => clearTimeout(retryTimer);
      }
    }
  }, [currentPAGEId]);

  // Scroll-based page tracking (debounced)
  const handleContentScroll = useCallback((e) => {
    // Always store the latest scroll position immediately (no debounce)
    lastScrollPositionRef.current = {
      scrollY: e.nativeEvent.contentOffset.y,
      layoutH: e.nativeEvent.layoutMeasurement.height,
    };
    if (!scrollTrackingEnabled.current) return;
    const scrollY = e.nativeEvent.contentOffset.y;
    const contentH = e.nativeEvent.contentSize.height;
    const layoutH = e.nativeEvent.layoutMeasurement.height;
    const viewportMid = scrollY + (layoutH / 2);

    let closestPageId = null;
    let closestDist = Infinity;

    for (const [pageId, layout] of Object.entries(pageLayoutsRef.current)) {
      const pageMid = layout.y + layout.height / 2;
      const dist = Math.abs(viewportMid - pageMid);
      if (dist < closestDist) {
        closestDist = dist;
        closestPageId = pageId;
      }
    }

    if (closestPageId && closestPageId !== currentPAGEIdRef.current) {
      scrollDrivenChange.current = true;
      setCurrentPAGEId(closestPageId);
    }
  }, [setCurrentPAGEId]);

  // Debounced version of scroll handler
  const scrollDebounceRef = useRef(null);
  const handleContentScrollDebounced = useCallback((e) => {
    // Persist before passing to debounce — deep copy nested objects
    const nativeEvent = {
      contentOffset: { ...e.nativeEvent.contentOffset },
      contentSize: { ...e.nativeEvent.contentSize },
      layoutMeasurement: { ...e.nativeEvent.layoutMeasurement },
    };
    if (scrollDebounceRef.current) clearTimeout(scrollDebounceRef.current);
    scrollDebounceRef.current = setTimeout(() => {
      handleContentScroll({ nativeEvent });
    }, 150);
  }, [handleContentScroll]);

  // Scroll to a specific page (called from sidebar click)
  const handleSelectPAGE = useCallback((pageId) => {
    pageChangeFromInteraction.current = true;
    setCurrentPAGEId(pageId);
    // Discard selection on other canvases
    canvasRefsMap.current.forEach((ref, id) => {
      if (id !== pageId && ref.current?.discardSelection) {
        ref.current.discardSelection();
      }
    });
    // Update active canvas ref
    const targetRef = canvasRefsMap.current.get(pageId);
    if (targetRef?.current) {
      activeCanvasRef.current = targetRef.current;
      canvasRef.current = targetRef.current;
    }
    const layout = pageLayoutsRef.current[pageId];
    if (layout && contentScrollRef.current) {
      scrollTrackingEnabled.current = false;
      contentScrollRef.current.scrollTo({ y: layout.y - 16, animated: true });
      setTimeout(() => {
        scrollTrackingEnabled.current = true;
      }, 500);
    }
  }, [setCurrentPAGEId]);

  // Delete PAGE handlers
  const handleDeletePAGE = useCallback((PAGEId) => {
    if (PAGES.length <= 1) {
      Alert.alert('Cannot Delete', 'You must have at least one page.');
      return;
    }
    setPAGEToDelete(PAGEId);
    setShowDeleteModal(true);
  }, [PAGES.length]);

  const confirmDeletePAGE = useCallback(() => {
    if (PAGEToDelete) {
      // Clean up cached refs and layouts for deleted page
      canvasRefsMap.current.delete(PAGEToDelete);
      delete pageLayoutsRef.current[PAGEToDelete];
      deletePAGE(PAGEToDelete);
    }
    setShowDeleteModal(false);
    setPAGEToDelete(null);
  }, [PAGEToDelete, deletePAGE]);

  const cancelDeletePAGE = useCallback(() => {
    setShowDeleteModal(false);
    setPAGEToDelete(null);
  }, []);

  // Duplicate PAGE handler
  const handleDuplicatePAGE = useCallback((PAGEId) => {
    const PAGEToDuplicate = PAGES.find(s => s.id === PAGEId);
    if (!PAGEToDuplicate) return;

    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);

    const duplicatedPAGE = {
      ...PAGEToDuplicate,
      id: `PAGE_${timestamp}_${random}`,
      title: `${PAGEToDuplicate.title || 'PAGE'} (Copy)`,
      elements: PAGEToDuplicate.elements?.map(el => ({
        ...el,
        id: `${el.id}_copy_${timestamp}`
      })) || [],
      hasUnsavedChanges: true,
    };

    // Insert after original PAGE and re-number `order` so a later sort-by-order
    // (generation merge / Yjs) can't reshuffle the duplicate out of place.
    const originalIndex = PAGES.findIndex(s => s.id === PAGEId);
    const newPAGES = [...PAGES];
    newPAGES.splice(originalIndex + 1, 0, duplicatedPAGE);
    setPAGES(newPAGES.map((s, i) => ({ ...s, order: i + 1 })));

    // Navigate to new PAGE
    setCurrentPAGEId(duplicatedPAGE.id);

    // Copy thumbnail from original PAGE if it exists (duplicates have same content initially)
    if (PAGEThumbnails[PAGEId]) {
      setPAGEThumbnails(prev => ({
        ...prev,
        [duplicatedPAGE.id]: prev[PAGEId]
      }));
      initialThumbnailGeneratedRef.current.add(duplicatedPAGE.id);
      // console.log(`📸 [THUMBNAIL] Copied thumbnail from original PAGE ${PAGEId} to duplicate ${duplicatedPAGE.id}`);
    }

    // console.log(`📄 [COMPOSER] Duplicated PAGE: ${PAGEToDuplicate.title} → ${duplicatedPAGE.title}`);
  }, [PAGES, setPAGES, setCurrentPAGEId, PAGEThumbnails]);

  // PAGE title editing
  const startEditingPAGETitle = useCallback((PAGE) => {
    setEditingPAGEId(PAGE.id);
    setEditingPAGETitleText(PAGE.title);
  }, []);

  const savePAGETitle = useCallback(() => {
    if (editingPAGEId && editingPAGETitleText.trim()) {
      updatePAGETitle(editingPAGEId, editingPAGETitleText);
    }
    setEditingPAGEId(null);
    setEditingPAGETitleText('');
  }, [editingPAGEId, editingPAGETitleText, updatePAGETitle]);

  const handleSavePAGEOutline = useCallback(({ title, outline }) => {
    if (editOutlinePAGE) {
      updatePAGE(editOutlinePAGE.id, { title: title || editOutlinePAGE.title, outline });
    }
    setEditOutlinePAGE(null);
  }, [editOutlinePAGE, updatePAGE]);

  // Handle element selection/updates from canvas (supports single or multi-select)
  const handleSelectElement = useCallback((elementIdOrIds) => {
    if (!elementIdOrIds) {
      setSelectedElementIds([]);
    } else if (Array.isArray(elementIdOrIds)) {
      setSelectedElementIds(elementIdOrIds);
    } else {
      setSelectedElementIds([elementIdOrIds]);
    }
  }, []);

  const handleElementUpdate = useCallback((maybePAGEId, maybeElementId, maybeUpdates) => {
    // Support both (elementId, updates) and (PAGEId, elementId, updates)
    const hasPAGEId = maybeUpdates !== undefined;
    const PAGEId = hasPAGEId ? maybePAGEId : currentPAGE?.id;
    const elementId = hasPAGEId ? maybeElementId : maybePAGEId;
    const updates = hasPAGEId ? maybeUpdates : maybeElementId;

    // Special case: Undo/Redo passes null elementId with updates.elements array
    if (PAGEId && elementId === null && updates?.elements !== undefined) {
      console.log('🔄 [COMPOSER] Full elements replacement for Undo/Redo');
      updateElement(PAGEId, null, updates);
      return;
    }

    if (PAGEId && elementId && updates) {
      updateElement(PAGEId, elementId, updates);
    }
  }, [currentPAGE?.id, updateElement]);

  const handleAddElement = useCallback((maybePAGEId, typeOrElement, maybeElement) => {
    // Support both (element) and (PAGEId, type, element)
    if (maybeElement) {
      // Called with (PAGEId, type, elementData)
      const type = typeOrElement;
      const data = maybeElement;

      // Adapt flat elementData to options expected by addElement
      const options = {
        textType: data.textType,
        content: data.content,
        src: data.src,
        shapeType: data.shapeType,
        iconName: data.iconName,
        chartConfig: data.chartConfig, // CRITICAL: Pass chart config!
        tableConfig: data.tableConfig, // CRITICAL: Pass table config!
        fill: data.fill, // Pass fill color (Important for Icons/Shapes)
        color: data.color, // Pass text color
        // VIDEO PROPERTIES - CRITICAL for thumbnail display
        thumbnail: data.thumbnail,
        videoType: data.videoType,
        videoId: data.videoId,
        // EMBED PROPERTIES
        embedType: data.embedType,
        provider: data.provider,
        title: data.title,
        html: data.html,
        // BUTTON/FORM PROPERTIES
        formType: data.formType,
        url: data.url,
        label: data.label,
        style: data.style,
        // ANIMATION PROPERTIES - For live video animation
        videoSrc: data.videoSrc,
        isPlaying: data.isPlaying,
        loop: data.loop,
        isUserMedia: data.isUserMedia,
        // SVG DIAGRAM PROPERTIES - inline AI-generated SVG markup
        svgContent: data.svgContent,
        svg: data.svg,
        prompt: data.prompt,
        diagramKind: data.diagramKind,
        diagramTitle: data.diagramTitle,
        fillColor: data.fillColor,
        position: {
          x: data.x,
          y: data.y,
          width: data.width,
          height: data.height,
          zIndex: data.zIndex, // CRITICAL: Pass z-index to ensure correct layering
          fill: data.fill, // Also pass in position just in case
        }
      };

      console.log('✅ [COMPOSER] Adding element:', { PAGEId: maybePAGEId, type, options });
      return addElement(maybePAGEId, type, options);
    } else if (currentPAGE && typeOrElement) {
      // Called with (type) - simple add
      console.log('✅ [COMPOSER] Adding simple element:', typeOrElement);
      return addElement(currentPAGE.id, typeOrElement);
    }
  }, [currentPAGE, addElement]);

  const handleDeleteElement = useCallback((maybePAGEId, maybeElementId) => {
    const PAGEId = maybeElementId ? maybePAGEId : currentPAGE?.id;
    const elementId = maybeElementId || maybePAGEId;
    if (PAGEId && elementId) {
      deleteElement(PAGEId, elementId);
    }
  }, [currentPAGE, deleteElement]);

  // Handler for deleting multiple elements at once (e.g., from Ctrl+A + Delete)
  const handleDeleteMultipleElements = useCallback((PAGEId, elementIds) => {
    const actualPAGEId = PAGEId || currentPAGE?.id;
    if (actualPAGEId && elementIds && elementIds.length > 0) {
      deleteMultipleElements(actualPAGEId, elementIds);
    }
  }, [currentPAGE, deleteMultipleElements]);

  // Diagram Handlers
  // The composer's "Insert Diagram" toolbar button opens the AI SVG diagram modal.
  const handleOpenDiagram = () => {
    setDiagramRegenContext(null);
    setShowAIDiagramModal(true);
  };

  const handleRegenerateDiagram = useCallback((element) => {
    if (!element || element.type !== 'svg_diagram') return;
    setDiagramRegenContext({
      elementId: element.id,
      prompt: element.prompt || '',
      diagramKind: element.diagramKind || 'flowchart',
      width: Math.round(element.width || 495),
      height: Math.round(element.height || 280),
      fillColor: element.fillColor || '',
      svgContent: element.svgContent || '',
    });
    setShowAIDiagramModal(true);
  }, []);

  // AI enhancement for current PAGE - uses orchestrator for intent classification
  // Supports background override: handleAiEnhance(instruction, targetPAGE, true) for auto layout fix
  const handleAiEnhance = useCallback(async (overrideInstruction, overridePAGE, isBackground) => {
    const instruction = overrideInstruction || chatInput.trim();
    // Sync: ensure we target the actually visible page from scroll position
    let targetPAGE = overridePAGE || currentPAGE;
    if (!overridePAGE) {
      const visiblePageId = getVisiblePageId();
      if (visiblePageId && visiblePageId !== currentPAGEId) {
        const visiblePage = PAGES.find(s => s.id === visiblePageId);
        if (visiblePage) {
          targetPAGE = visiblePage;
          setCurrentPAGEId(visiblePageId);
        }
      }
    }
    if (!instruction || (!isBackground && isAiProcessing) || !targetPAGE) return;

    if (!isBackground) setIsAiProcessing(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      // HANDLE "ALL PAGES" MODE (Smart Orchestrate-All - Single API call)
      if (editScope === 'all' && !overridePAGE) {
        const instruction = chatInput;
        // Add user message to chat history
        setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
        setChatInput(''); // Clear input

        const finalFolderIds = useUploadedData && selectedFolders.length > 0
          ? selectedFolders.map(f => f.id || f)
          : [];

        // Helper to extract string goal
        const extractGoalString = (goalData) => {
          if (!goalData) return null;
          if (typeof goalData === 'string') return goalData;
          if (goalData.purpose) return extractGoalString(goalData.purpose);
          return null;
        };

        try {
          // Filter out hidden pages for AI processing
          const aiPages = PAGES.filter(p => !p.hidden);
          const aiIndexToFullIndex = aiPages.map(p => PAGES.indexOf(p));

          // Build lightweight summaries for relevance classification
          const pagesSummary = buildSlidesSummary(aiPages);
          const currentIndex = aiPages.findIndex(s => s.id === currentPAGEId);

          // Add AI entry message
          setAiChatMessages(prev => [...prev.slice(-29), {
            id: chatMsgUid(),
            text: `Analyzing ${aiPages.length} pages and planning edits...`,
            timestamp: new Date(),
            actionType: 'edit'
          }]);

          // Single API call to orchestrate-all (SSE streaming)
          const orchestrateAllResponse = await fetch(`${apiConfig.API_URL}/printable/orchestrate-all-stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              instruction: instruction,
              pages_summary: pagesSummary,
              full_pages: aiPages.map(s => {
                const { processedPAGE } = extractImagesFromPAGE(s);
                return { ...processedPAGE, id: s.id };
              }),
              current_page_index: currentIndex >= 0 ? currentIndex : 0,
              folder_ids: finalFolderIds,
              style: printableStyle,
              printable_goal: extractGoalString(printableGoal),
              printable_type: printableGoal?.documentType || 'general',
               icon_set: printableStyle?.iconSet || 'default',
              is_update_all: false,
              deck_profile: printableGoal?.deckProfile || 'corporate',
              deck_plan: printableGoal?.deckPlan || null,
            }),
          });

          if (!orchestrateAllResponse.ok) {
            const errorData = await orchestrateAllResponse.json().catch(() => ({}));
            if (orchestrateAllResponse.status === 402) {
              const message = errorData.detail?.message || errorData.message || 'Insufficient credits.';
              authService.notifyCreditRequired(message);
              setIsAutoUpdating(false);
              setIsAiProcessing(false);
              return;
            }
            if (handleCreditError(errorData)) {
              setIsAutoUpdating(false);
              setIsAiProcessing(false);
              return;
            }
            throw new Error(errorData.message || 'Failed to process all pages');
          }

          // --- Stream SSE events from orchestrate-all-stream ---
          const reader = orchestrateAllResponse.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let successCount = 0;
          const pendingImageTasks = []; // Parallel image generation across pages

          const processSSELine = async (line) => {
            if (!line.startsWith('data: ')) return;
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'classification') {
                console.log(`🎯 [ORCHESTRATE_ALL] ${event.relevant_count} of ${event.total_pages} pages relevant`);
                setAutoUpdateProgress({ current: 0, total: event.relevant_count });
              }
              else if (event.type === 'progress') {
                setAutoUpdateProgress(prev => ({ ...prev, current: event.page_index + 1 }));
                setAiChatMessages(prev => [...prev.slice(-29), {
                  id: chatMsgUid(),
                  text: `Editing page ${event.page_index + 1}...`,
                  timestamp: new Date(),
                  actionType: 'edit',
                }]);
              }
              else if (event.type === 'page_result' && event.slide_data) {
                // Apply this page result immediately (auto-apply)
                const fullIndex = aiIndexToFullIndex[event.page_index];
                const originalPAGE = PAGES[fullIndex];
                if (!originalPAGE) return;

                const { imageMap } = extractImagesFromPAGE(originalPAGE);
                const restoredPAGEData = restoreImagesToPAGE(event.slide_data, imageMap);
                const processedPAGEOutput = await processPAGEAsync(restoredPAGEData);

                // Apply text/layout changes immediately
                const PAGEUpdate = { elements: processedPAGEOutput.elements };
                if (processedPAGEOutput.backgroundColor) PAGEUpdate.backgroundColor = processedPAGEOutput.backgroundColor;
                if (processedPAGEOutput.title) PAGEUpdate.title = processedPAGEOutput.title;
                if (processedPAGEOutput.notes) PAGEUpdate.notes = processedPAGEOutput.notes;
                // Sync outline from AI response (keeps outline fresh after edits)
                PAGEUpdate.outline = processedPAGEOutput.outline || restoredPAGEData.outline || originalPAGE.outline || originalPAGE.sectionTopic || originalPAGE.content_hint || '';
                // Bulk edit changed this page's layout — flag for re-critique.
                PAGEUpdate.critique_recommended = true;
                critiquedPagesRef.current.delete(originalPAGE.id);
                updatePAGE(originalPAGE.id, PAGEUpdate);
                successCount++;
                console.log(`✅ [ORCHESTRATE_ALL] Page ${event.page_index + 1} applied (${successCount} done)`);

                // Fire image generation in parallel (don't block SSE loop)
                const imagePlaceholders = (processedPAGEOutput.elements || []).filter(el => el.type === 'image_placeholder');
                if (imagePlaceholders.length > 0) {
                  const pageId = originalPAGE.id;
                  const imageTask = (async () => {
                    try {
                      await generateImagesParallel(imagePlaceholders, {
                        generationQuality, style: printableStyle?.name || 'professional',
                        userId: userDeviceId, defaultDescription: 'Professional printable image', handleCreditError,
                      });
                      const finalElements = (processedPAGEOutput.elements || []).map(el => {
                        if (el.type === 'image' && !el.src) {
                          return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                        }
                        return el;
                      });
                      updatePAGE(pageId, { elements: finalElements });
                    } catch (imgErr) { console.error(`❌ [ORCHESTRATE_ALL] Image gen failed for page ${event.page_index}:`, imgErr); }
                  })();
                  pendingImageTasks.push(imageTask);
                }
              }
              else if (event.type === 'result' && event.data) {
                // Handle create_new from stream
                const d = event.data;
                if (d.intent === 'create_new' && d.edits?.[0]?.slide_data) {
                  const newPAGEId = `PAGE_${Date.now()}_ai_new`;
                  // Compute insertion position: after current page, not at end
                  // Defensive: validate after_slide_index bounds
                  let rawIdx = (typeof d.edits[0].after_slide_index === 'number' && d.edits[0].after_slide_index >= 0)
                    ? d.edits[0].after_slide_index
                    : (currentIndex >= 0 ? currentIndex : PAGES.length - 1);
                  const insertAfterIdx = Math.min(Math.max(rawIdx, 0), PAGES.length - 1);
                  const insertOrder = insertAfterIdx + 2; // +1 for 0-index, +1 for "after"
                  console.log(`📄 [ORCHESTRATE_ALL] create_new: insertAfter=${insertAfterIdx}, order=${insertOrder}`);
                  const newPAGEData = {
                    id: newPAGEId, order: insertOrder,
                    title: d.edits[0].slide_data.title || 'New Page',
                    layout: d.edits[0].slide_data.layout || 'content',
                    elements: d.edits[0].slide_data.elements || [],
                    backgroundColor: d.edits[0].slide_data.backgroundColor || '#ffffff',
                    notes: d.edits[0].slide_data.notes || '', hasUnsavedChanges: true,
                  };
                  const processedNew = await processPAGEAsync(newPAGEData);

                  // Generate images for any image_placeholder elements
                  const imgPlaceholders = (processedNew.elements || []).filter(el => el.type === 'image_placeholder');
                  await generateImagesParallel(imgPlaceholders, {
                    generationQuality, style: printableStyle?.name || 'professional',
                    userId: userDeviceId, defaultDescription: 'Professional printable image', handleCreditError,
                  });

                  // Safety net: catch any remaining type='image' elements without src
                  const finalNewElements = (processedNew.elements || []).map(el => {
                    if (el.type === 'image' && !el.src) {
                      console.warn(`⚠️ [ORCHESTRATE_ALL_NEW] Image element ${el.id} still has no src — converting to shape`);
                      return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                    }
                    return el;
                  });

                  pendingLayoutFixRef.current.add(newPAGEId);
                  setPAGES(prev => {
                    const bumped = prev.map(p => p.order >= insertOrder ? { ...p, order: p.order + 1 } : p);
                    return [...bumped, { ...newPAGEData, elements: finalNewElements }].sort((a, b) => a.order - b.order);
                  });
                  successCount++;
                }
              }
              else if (event.type === 'complete') {
                console.log(`🎯 [ORCHESTRATE_ALL] Complete: ${event.summary}`);
                setAiChatMessages(prev => [...prev.slice(-29), {
                  id: chatMsgUid(),
                  text: event.summary || `Updated ${successCount} pages.`,
                  timestamp: new Date(),
                  actionType: 'edit',
                }]);
              }
              else if (event.type === 'error') {
                if (event.status_code === 402) {
                  authService.notifyCreditRequired(event.message || 'Insufficient credits.');
                } else {
                  console.error('❌ [ORCHESTRATE_ALL] Stream error:', event.message);
                }
              }
            } catch (parseErr) {
              console.warn('⚠️ SSE parse error:', parseErr);
            }
          };

          // Read SSE stream
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              const trimmed = line.trim();
              if (trimmed) await processSSELine(trimmed);
            }
          }
          // Process any remaining buffer
          if (buffer.trim()) await processSSELine(buffer.trim());

          // Wait for all parallel image generation to complete
          if (pendingImageTasks.length > 0) {
            console.log(`🖼️ [ORCHESTRATE_ALL] Waiting for ${pendingImageTasks.length} parallel image tasks...`);
            await Promise.all(pendingImageTasks);
            console.log(`✅ [ORCHESTRATE_ALL] All image tasks completed`);
          }

        } catch (error) {
          console.error('Orchestrate All Pages failed:', error);
          if (!isInsufficientCreditsError({ message: error.message })) {
            Alert.alert('Error', 'Failed to update all pages.');
          }
        } finally {
          setIsAutoUpdating(false);
          setIsAiProcessing(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
        }
        return; // Exit function
      }

      // --- IMAGE INTERCEPT: If an image element is selected, use Runware for image editing/generation ---
      if (selectedElement && selectedElement.type === 'image') {
        console.log('🖼️ [AI_CHAT_IMAGE] Image element selected, routing via Runware');

        try {
          const elementImageType = selectedElement.imageType || 'photo';
          const imgWidth = Math.round(selectedElement.width || 1024);
          const imgHeight = Math.round(selectedElement.height || 1024);

          // --- Detect intent: new image vs edit existing ---
          const promptLower = instruction.toLowerCase();
          const newImagePatterns = /\b(create|generate|make|new|replace\s+with|replace\s+this|swap|change\s+to|switch\s+to|turn\s+into|convert\s+to|transform\s+into|completely\s+new|brand\s+new|different\s+image|new\s+image|replace\s+image|fresh|from\s+scratch)\b/;
          const isNewImageIntent = newImagePatterns.test(promptLower);
          const editImagePatterns = /\b(edit|adjust|tweak|brighten|darken|lighten|sharpen|blur|crop|resize|add|remove|enhance|improve|fix|increase|decrease|more|less|filter|saturat|contrast|warm|cool|tone|tint|overlay|rotate|flip|mirror)\b/;
          const isEditIntent = editImagePatterns.test(promptLower);

          // If both match, prefer edit (more specific); if neither, default to new image
          const shouldGenerateNew = isNewImageIntent && !isEditIntent;

          let imageResult;

          if (shouldGenerateNew) {
            // ---- GENERATE COMPLETELY NEW IMAGE (no seed) ----
            console.log('🖼️ [AI_CHAT_IMAGE] Intent: NEW IMAGE — generating via ImageGen (' + generationQuality + ')');
            imageResult = await ImageGenService.generateImage(instruction, {
              width: imgWidth,
              height: imgHeight,
              generationQuality: generationQuality,
            });

            if (handleCreditError(imageResult)) { setIsAiProcessing(false); return; }
            if (!imageResult.success || !(imageResult.image_data || imageResult.image_url)) {
              throw new Error(imageResult.message || 'Failed to generate new image');
            }
            console.log('✅ [AI_CHAT_IMAGE] New image generated (' + generationQuality + ')');
          } else {
            // ---- EDIT EXISTING IMAGE (with seed) ----
            console.log('🖼️ [AI_CHAT_IMAGE] Intent: EDIT — modifying existing image via Runware');

            // Get the image source - prefer original URL (high-res) over canvas export (low-res)
            // Canvas export renders at display size (e.g. 400x300) losing original resolution
            let imageSource = null;
            if (selectedElement.src) {
              imageSource = selectedElement.src;
              console.log('🖼️ [AI_CHAT_IMAGE] Using original image source (high quality)');
            }
            const activeCanvas = activeCanvasRef.current || canvasRef.current;
            if (!imageSource && activeCanvas?.getImageAsBase64) {
              try {
                imageSource = await activeCanvas.getImageAsBase64(selectedElement.id);
                console.log('🖼️ [AI_CHAT_IMAGE] Fallback: using canvas export');
              } catch (canvasErr) {
                console.log('🖼️ [AI_CHAT_IMAGE] Canvas export failed (tainted canvas)');
              }
            }
            if (!imageSource) {
              throw new Error('Could not get image data. Cannot edit.');
            }

            console.log('🖼️ [AI_CHAT_IMAGE] Editing via ImageGen');
            imageResult = await ImageGenService.editImage(instruction, {
              sourceImage: imageSource,
            });

            if (handleCreditError(imageResult)) { setIsAiProcessing(false); return; }
            if (!imageResult.success || !(imageResult.image_data || imageResult.image_url)) {
              throw new Error(imageResult.message || 'Failed to edit image');
            }
            console.log('✅ [AI_CHAT_IMAGE] Image edited (' + generationQuality + ')');
          }

          // Update the selected image element with new src
          updateElement(currentPAGE.id, selectedElement.id, {
            src: imageResult.image_data || imageResult.image_url,
            alt: instruction,
          });

          setChatInput('');
          setIsAiProcessing(false);
          return; // Exit early, bypass orchestrator

        } catch (imageError) {
          console.error('🖼️ [AI_CHAT_IMAGE] Image edit/generate error:', imageError);
          if (imageError?.message) handleCreditError({ message: imageError.message });
          Alert.alert('Image Edit Error', imageError.message || 'Failed to process image. Please try again.');
          setIsAiProcessing(false);
          return;
        }
      }
      // --- INTERCEPT: VIDEO EDITING ---
      const selectedVideoEl = selectedElements.find(el => el.type === 'video');
      if (selectedVideoEl) {
        console.log('📹 [AI_CHAT_VIDEO] Video element selected, informing user AI cannot edit videos');
        setAiChatMessages(prev => [...prev.slice(-29), {
          id: chatMsgUid(),
          text: "I can't edit video elements directly. You can manually resize, move, or delete them on the canvas, or replace them by uploading a new video.",
          timestamp: new Date(),
          actionType: 'info'
        }]);
        setChatInput('');
        setIsAiProcessing(false);
        return; // STOP execution
      }

      // --- END VIDEO INTERCEPT ---

      // --- INTERCEPT: CHART EDITING ---
      // If a chart is selected, route to specific Chart AI for data modification
      const selectedChartEl = selectedElements.find(el => el.type === 'chart');
      if (selectedChartEl) {
        console.log('📊 [AI_CHAT_CHART] Chart element selected, routing to Chart AI:', selectedChartEl.id);

        // Chat history lives in this component's own aiChatMessages state —
        // the inline right sidebar renders it, so there is nothing to hand
        // back to a caller here.

        // Only use vault if folders are explicitly selected (no default to 'general')
        try {
          const finalFolderIds = useUploadedData && selectedFolders.length > 0
            ? selectedFolders.map(f => f.id || f)
            : [];

          const response = await fetch(`${apiConfig.API_URL}/printable/generate-chart-data`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              chart_type: selectedChartEl.chartConfig?.type || 'bar',
              query: instruction,
              folder_ids: finalFolderIds,
              // Pass context: PAGE title + CURRENT chart data
              page_context: {
                PAGE_title: currentPAGE.title,
                target_chart_config: selectedChartEl.chartConfig
              },
              source_context: 'printable_chart_edit',
            }),
          });

          const data = await response.json();

          if (response.status === 402 || handleCreditError(data)) {
            setIsAiProcessing(false);
            return;
          }

          if (data.success && data.chart_config) {
            console.log('✅ [AI_CHAT_CHART] Chart updated successfully');
            updateElement(currentPAGE.id, selectedChartEl.id, {
              chartConfig: data.chart_config
            });
            // Clear input
            setChatInput('');
          } else {
            throw new Error(data.message || 'Failed to update chart data');
          }
        } catch (chartErr) {
          console.error('📊 [AI_CHAT_CHART] Error:', chartErr);
          Alert.alert('Chart AI Error', 'Failed to update chart. Please try again.');
        } finally {
          setIsAiProcessing(false);
        }
        return; // STOP execution, do not call orchestrator
      }
      // --- END CHART INTERCEPT ---

      console.log('🎯 [ORCHESTRATOR] Classifying intent:', instruction.substring(0, 50));

      // OPTIMIZATION: Extract images to markers
      const { processedPAGE, imageMap } = extractImagesFromPAGE(targetPAGE, selectedElementIds);
      const hasImages = Object.keys(imageMap).length > 0;

      let finalInstruction = instruction;
      if (hasImages) {
        finalInstruction += `\n\n[SYSTEM NOTE]: The PAGE JSON contains existing media with placeholder values.
1. Elements with "src" like "{{UserMedia_ID}}" are user-uploaded. Do NOT change these src values. PRESERVE them.
2. For 'video' elements: You cannot generate or edit them. Keep them exactly as they are.
3. "image_placeholder" elements can be freely edited - modify their imageDescription to change the image.`;
      }

      // Only use vault if folders are explicitly selected (no default to 'general')
      const finalFolderIds = useUploadedData && selectedFolders.length > 0
        ? selectedFolders.map(f => f.id || f)
        : [];

      // Step 1: Call orchestrator to classify intent

      // Validation: Ensure we have a user ID
      if (!userDeviceId) {
        console.error('❌ [ORCHESTRATOR] Missing user ID (userDeviceId is null/undefined)');
        Alert.alert('Authentication Error', 'User ID not found. Please try logging in again to use AI features.');
        setIsAiProcessing(false);
        return;
      }

      // Helper to extract string goal from potentially nested objects
      const extractGoalString = (goalData) => {
        if (!goalData) return null;
        if (typeof goalData === 'string') return goalData;
        // Recursive check for purpose field
        if (goalData.purpose) return extractGoalString(goalData.purpose);
        return null; // If object but no purpose, meaningful string is missing
      };

      const goalString = extractGoalString(printableGoal);
      console.log('🎯 [ORCHESTRATOR] Extracted goal string:', goalString);

      // Add user message to chat history
      if (!isBackground) {
        setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
      }

      const orchestrateResponse = await fetch(`${apiConfig.API_URL}/printable/orchestrate-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          instruction: isBackground ? instruction : chatInput,
          PAGE_content: processedPAGE,
          folder_ids: finalFolderIds,
          PAGE_id: targetPAGE.id,
          style: printableStyle,
          template_id: (printableGoal?.deckProfile === 'general') ? null : (currentPAGE.template || null),
          edit_mode: editMode,
          selected_elements: selectedElements.length > 0 ? selectedElements : null,
          printable_goal: goalString,
          printable_type: printableGoal?.documentType || 'informative',
          icon_set: printableStyle?.iconSet || 'lucide',
          generation_quality: generationQuality,
          user_edit_scope: editScope,
          pages_summary: buildSlidesSummary(PAGES.filter(p => !p.hidden)),
          deck_profile: printableGoal?.deckProfile || 'corporate',
          deck_plan: printableGoal?.deckPlan || null,
          ...(isBackground ? { fast_path: 'layout_fix' } : {}),
        }),
      });

      if (!orchestrateResponse.ok) {
        const errorData = await orchestrateResponse.json().catch(() => ({}));
        console.log('❌ [ORCHESTRATOR] Error response:', orchestrateResponse.status, JSON.stringify(errorData));
        if (isBackground) { console.warn('⚠️ [AUTO-LAYOUT-FIX] API error:', orchestrateResponse.status); return; }

        if (orchestrateResponse.status === 402) {
          const message = errorData.detail?.message || errorData.message || 'Insufficient credits.';
          authService.notifyCreditRequired(message);
          setIsAiProcessing(false);
          return;
        }
        if (handleCreditError(errorData)) { setIsAiProcessing(false); return; }
        if (orchestrateResponse.status === 422) {
          throw new Error('Request validation failed. Please try again.');
        }
        throw new Error(errorData.message || 'AI processing failed');
      }

      // --- SSE Stream processing for single-page orchestrate ---
      const reader = orchestrateResponse.body.getReader();
      const decoder = new TextDecoder();
      let streamBuffer = '';

      const applyOrchResult = async (orchestrateData) => {
        const { intent, success, enhanced_PAGE: ep, enhanced_element, enhanced_elements,
          chart_config, action_type, ai_message, new_PAGE, scope_escalated, scope_message } = orchestrateData;

        if (!success && handleCreditError(orchestrateData)) return;

        if (!isBackground && scope_escalated && scope_message) {
          setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: `🔄 ${scope_message}`, timestamp: new Date(), actionType: 'info' }]);
        }
        if (!isBackground && ai_message) {
          setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: ai_message, timestamp: new Date(), actionType: action_type || 'edit' }]);
        }

        // CREATE NEW PAGE
        if (action_type === 'create_new' && new_PAGE) {
          const newPAGEId = `PAGE_${Date.now()}_ai`;
          const currentIndex = PAGES.findIndex(s => s.id === currentPAGEId);
          const newPAGEOrder = currentIndex >= 0 ? currentIndex + 2 : PAGES.length + 1;
          const newPAGEData = {
            id: newPAGEId, order: newPAGEOrder,
            title: new_PAGE.title || 'New PAGE', layout: new_PAGE.layout || 'content',
            elements: new_PAGE.elements || [], backgroundColor: new_PAGE.backgroundColor || '#ffffff',
            notes: new_PAGE.notes || '', hasUnsavedChanges: true,
          };

          // Process page through post-processor (normalize text→content, validate elements)
          const processedNew = await processPAGEAsync(newPAGEData);

          // Generate images for any image_placeholder elements
          const imagePlaceholders = (processedNew.elements || []).filter(el => el.type === 'image_placeholder');
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: printableStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: 'Professional printable image', handleCreditError,
          });

          // Safety net: catch any remaining type='image' elements without src
          const safeElements = (processedNew.elements || []).map(el => {
            if (el.type === 'image' && !el.src) {
              console.warn(`⚠️ [CREATE_NEW] Image element ${el.id} still has no src — converting to shape`);
              return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
            }
            return el;
          });

          // Newly authored page — flag it so the post-render callback runs a
          // vision critique on it, same as a page from initial doc generation.
          const finalPAGEData = { ...newPAGEData, elements: safeElements, critique_recommended: true };
          const updatedPAGES = PAGES.map(s => s.order >= newPAGEOrder ? { ...s, order: s.order + 1 } : s);
          const allPAGES = [...updatedPAGES, finalPAGEData].sort((a, b) => a.order - b.order);
          setPAGES(allPAGES);
          setCurrentPAGEId(newPAGEId);
          pendingLayoutFixRef.current.add(newPAGEId);
          return;
        }

        // CHART
        if (chart_config) {
          const activeCanvas = activeCanvasRef.current || canvasRef.current;
          if (activeCanvas?.addChart) { activeCanvas.addChart(chart_config); }
          return;
        }

        // ENHANCED PAGE
        if (ep) {
          let rawPAGEData = ep.PAGE || ep;
          // FIX: single-element returned as page
          if (rawPAGEData.type && !rawPAGEData.elements) {
            const existingElements = targetPAGE?.elements || [];
            const mi = existingElements.findIndex(el => el.id === rawPAGEData.id);
            rawPAGEData = mi >= 0
              ? { elements: existingElements.map((el, i) => i === mi ? { ...el, ...rawPAGEData } : el) }
              : { elements: [...existingElements, rawPAGEData] };
          }

          let restoredPAGEData = restoreImagesToPAGE(rawPAGEData, imageMap);

          const processedPAGEOutput = await processPAGEAsync(restoredPAGEData);

          // Generate images for placeholders
          const imagePlaceholders = (processedPAGEOutput.elements || []).filter(el => el.type === 'image_placeholder');
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: printableStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: 'Professional printable image', handleCreditError,
          });

          // Safety net: catch any remaining type='image' elements without src
          const finalElements = (processedPAGEOutput.elements || []).map(el => {
            if (el.type === 'image' && !el.src) {
              console.warn(`⚠️ [ENHANCE] Image element ${el.id} still has no src after generation — converting to shape`);
              return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
            }
            return el;
          });

          const PAGEUpdate = { elements: finalElements };
          if (processedPAGEOutput.backgroundColor) PAGEUpdate.backgroundColor = processedPAGEOutput.backgroundColor;
          if (processedPAGEOutput.title) PAGEUpdate.title = processedPAGEOutput.title;
          if (processedPAGEOutput.notes || processedPAGEOutput.speaker_notes) PAGEUpdate.notes = processedPAGEOutput.notes || processedPAGEOutput.speaker_notes;
          if (processedPAGEOutput.template || rawPAGEData.template) PAGEUpdate.template = processedPAGEOutput.template || rawPAGEData.template;
          // Preserve outline: use backend value if returned, otherwise keep existing
          PAGEUpdate.outline = rawPAGEData.outline || targetPAGE.outline || targetPAGE.sectionTopic || targetPAGE.content_hint || '';

          // An AI edit changed the page's layout — flag it for a fresh vision
          // critique and clear the per-page dedup guard so the post-render
          // callback re-critiques it (the guard is otherwise session-persistent,
          // which would skip critique on a second edit of the same page).
          PAGEUpdate.critique_recommended = true;
          critiquedPagesRef.current.delete(targetPAGE.id);

          updatePAGE(targetPAGE.id, PAGEUpdate);
          if (isBackground) console.log(`✅ [AUTO-LAYOUT-FIX] PAGE ${targetPAGE.id} fixed`);
          return;
        }

        // SINGLE ELEMENT
        if (enhanced_element) {
          if (selectedElementId && currentPAGE?.id) {
            // If enhanced_element is an image_placeholder, generate the actual image first
            if (enhanced_element.type === 'image_placeholder') {
              console.log('🖼️ [ENHANCED_ELEMENT] Image placeholder detected, generating image...');
              try {
                const placeholderImageType = enhanced_element.imageType || 'photo';
                let imageResult;
                imageResult = await ImageGenService.generateImage(
                  enhanced_element.imageDescription || 'Professional printable image',
                  {
                    width: Math.round(enhanced_element.width || 1024),
                    height: Math.round(enhanced_element.height || 1024),
                    imageType: placeholderImageType, userId: userDeviceId, generationQuality: enhanced_element.generationQuality || generationQuality || 'premium'
                  }
                );
                if (imageResult.success && (imageResult.image_data || imageResult.image_url)) {
                  enhanced_element.type = 'image';
                  enhanced_element.src = imageResult.image_data || imageResult.image_url;
                  if (enhanced_element.src?.startsWith('http')) globalImageCache.fetchAndCache(enhanced_element.src).catch(() => { });
                  console.log('✅ [ENHANCED_ELEMENT] Image generated successfully');
                } else {
                  handleCreditError(imageResult);
                  enhanced_element.type = 'shape'; enhanced_element.fill = '#94a3b8'; enhanced_element.shapeType = 'rectangle'; enhanced_element.rx = 8;
                }
              } catch (imgError) {
                console.error('🖼️ [ENHANCED_ELEMENT] Image generation failed:', imgError);
                if (imgError?.message) handleCreditError({ message: imgError.message });
                enhanced_element.type = 'shape'; enhanced_element.fill = '#94a3b8'; enhanced_element.shapeType = 'rectangle'; enhanced_element.rx = 8;
              }
            }
            const processed = await processPAGEAsync({ elements: [enhanced_element] });
            const final_el = processed.elements?.[0] || enhanced_element;
            updateElement(currentPAGE.id, final_el.id, final_el);
            // Element edit can introduce overlap — flag the page for re-critique.
            updatePAGE(currentPAGE.id, { critique_recommended: true });
            critiquedPagesRef.current.delete(currentPAGE.id);
          }
          return;
        }

        // MULTI ELEMENTS
        if (enhanced_elements && Array.isArray(enhanced_elements)) {
          if (currentPAGE?.id && enhanced_elements.length > 0) {
            const processed = await processPAGEAsync({ elements: enhanced_elements });
            const processedEls = processed.elements || enhanced_elements;
            updateMultipleElements(currentPAGE.id, processedEls.map(el => ({ elementId: el.id, updates: el })));
            // Multi-element edit can introduce overlap — flag the page for re-critique.
            updatePAGE(currentPAGE.id, { critique_recommended: true });
            critiquedPagesRef.current.delete(currentPAGE.id);
          }
          return;
        }
      };

      // Read SSE stream
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        streamBuffer += decoder.decode(value, { stream: true });
        const lines = streamBuffer.split('\n');
        streamBuffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(trimmed.slice(6));
            if (event.type === 'result' && event.data) {
              await applyOrchResult(event.data);
            } else if (event.type === 'error') {
              if (event.status_code === 402) { authService.notifyCreditRequired(event.message); }
              else { console.error('❌ [ORCHESTRATOR] Stream error:', event.message); }
            } else if (event.type === 'chunk') {
              // Streaming text chunk — could show typing indicator
              console.log('📝 AI streaming:', event.text?.substring(0, 40));
            }
          } catch (parseErr) { console.warn('⚠️ SSE parse:', parseErr); }
        }
      }
      if (streamBuffer.trim()?.startsWith('data: ')) {
        try {
          const event = JSON.parse(streamBuffer.trim().slice(6));
          if (event.type === 'result' && event.data) await applyOrchResult(event.data);
        } catch { }
      }

      if (!isBackground) setChatInput('');
    } catch (error) {
      if (isBackground) { console.warn('⚠️ [AUTO-LAYOUT-FIX] Error:', error); return; }
      console.error('AI enhancement error:', error);
      // Check if error message indicates credit issue
      if (error?.message && !isInsufficientCreditsError({ message: error.message })) {
        Alert.alert('Error', 'Failed to process request. Please try again.');
      }
    } finally {
      if (!isBackground) setIsAiProcessing(false);
    }

  }, [chatInput, isAiProcessing, currentPAGE, currentPAGEId, PAGES, setPAGES, setCurrentPAGEId, apiConfig, printableStyle, userDeviceId, selectedFolders, updatePAGE, editMode, selectedElement, selectedElementId, updateElement, updateMultipleElements, selectedElements, printableGoal, getVisiblePageId]);

  handleAiEnhanceRef.current = handleAiEnhance;

  const handleAgentEditRef = useRef(null);
  // Lets the user STOP an in-flight agent edit. Aborting the fetch breaks the
  // SSE read loop (the loop's reader.read() rejects) — already-applied op
  // batches stay on the document; no further rounds are read.
  const agentAbortRef = useRef(null);
  // One id per agent turn, passed to the canvas as externalEditSessionId so all
  // of the turn's streamed op batches coalesce into ONE undo step (PPT-style).
  const agentTurnIdRef = useRef(null);
  // Unsaved-changes tracking for the beforeunload warning. Armed after the
  // first clean render post-load; any content change marks dirty; saves clear it.
  const isDirtyRef = useRef(false);
  const dirtyTrackingArmedRef = useRef(false);

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

  // ═══════════════════════════════════════════════════════════════════════
  // AGENTIC WHOLE-DOCUMENT EDITOR — "Claude on PowerPoint" for printables.
  // The ENTIRE document + chat message go to the backend in one shot; the LLM
  // returns operations (edit/add/delete/duplicate/reorder page, update
  // style/header-footer/page-numbers) applied here. Intent + target are
  // auto-detected — no scope selection.
  // ═══════════════════════════════════════════════════════════════════════

  // Applies a batch of agent operations and returns the new page array. The
  // agent loop streams MULTIPLE batches per turn, so the caller threads the
  // returned array back in as `basePages` to avoid stale-closure loss.
  const applyAgentOperations = useCallback(async (operations, imageMapByPage, basePages) => {
    const base = basePages || PAGES;
    if (!operations || operations.length === 0) return base;

    let working = base.map(s => ({ ...s }));

    const genImagesFor = async (elements) => {
      const placeholders = (elements || []).filter(el => el.type === 'image_placeholder');
      if (placeholders.length > 0) {
        await generateImagesParallel(placeholders, {
          generationQuality, style: printableStyle?.name || 'professional',
          userId: userDeviceId, defaultDescription: 'Professional document image', handleCreditError,
        });
      }
      return (elements || []).map(el => {
        if (el.type === 'image' && !el.src && !el.isUserMedia) {
          return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
        }
        return el;
      });
    };

    // The image map MUST be scoped to the target page — restoreImagesToPAGE has
    // a deck-agnostic safety net that would otherwise re-inject other pages'
    // user media into this one.
    // fallbackBg: the page's REAL background. update_elements ops never carry
    // backgroundColor and edit_slide ops usually omit it, so without this the
    // post-processor resolves the background to '#FFFFFF' and its contrast
    // passes flip perfectly-readable white text on dark pages to
    // #1F2937/#111827 — invisible on the actually-dark page.
    const buildPageFromOp = async (op, pageImageMap, fallbackBg) => {
      const restored = restoreImagesToPAGE(
        { elements: op.elements || [], backgroundColor: op.backgroundColor || fallbackBg }, pageImageMap || {},
      );
      const processed = await processPAGEAsync(restored);
      const finalElements = await genImagesFor(processed.elements);
      return { elements: finalElements, backgroundColor: op.backgroundColor };
    };

    const newId = (tag) => `page_${Date.now()}_${Math.random().toString(36).slice(2, 7)}_${tag}`;

    for (const op of operations) {
      try {
        if (op.op === 'edit_slide') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          const built = await buildPageFromOp(
            op,
            { ...(imageMapByPage.__deckMedia || {}), ...(imageMapByPage[op.slide_id] || {}) },
            working[idx].backgroundColor,
          );
          const update = { ...working[idx], elements: built.elements, critique_recommended: true, hasUnsavedChanges: true };
          if (op.title) update.title = op.title;
          if (op.outline) update.outline = op.outline;
          if (built.backgroundColor) update.backgroundColor = built.backgroundColor;
          working[idx] = update;
          critiquedPagesRef.current?.delete?.(op.slide_id);
        } else if (op.op === 'update_elements') {
          // Surgical merge-patch: only the listed keys of the listed elements
          // change — layout of everything else is untouched.
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          const patchById = {};
          (op.elements || []).forEach(p => { if (p && p.id) patchById[p.id] = p; });
          const merged = (working[idx].elements || []).map(el => {
            const p = patchById[el.id];
            if (!p) return el;
            const next = { ...el, ...p };
            // CHART PATCH: chartConfig is an object — a partial patch ({...el,...p})
            // would replace it WHOLESALE and silently drop data/labels/options.
            // Merge one level deep so a full config still fully overwrites each key
            // while a partial one can't destroy the rest.
            if (p.chartConfig && typeof p.chartConfig === 'object' && el.chartConfig && typeof el.chartConfig === 'object') {
              next.chartConfig = { ...el.chartConfig, ...p.chartConfig };
            }
            // AGENT CHANGED THE IMAGE DESCRIPTION: the live element still carries
            // the OLD src, and genImagesFor only regenerates type==='image_placeholder'
            // — so without this the patch merges new description onto the old image
            // and the image API is never called (old image persists). Drop the stale
            // src and demote to placeholder so the pipeline generates the new image.
            // User media is never regenerated.
            // Also rescue elements a FAILED generation once bricked into a gray
            // 'shape' (they keep their imageDescription) — otherwise they stop
            // being image-ish and no retry can ever regenerate them.
            const isImageish = next.type === 'image' || next.type === 'image_placeholder'
              || el.type === 'image' || el.type === 'image_placeholder'
              || (el.type === 'shape' && el.imageDescription);
            if (isImageish && !next.isUserMedia && typeof p.imageDescription === 'string'
              && p.imageDescription.trim() && p.imageDescription !== el.imageDescription) {
              delete next.src;
              delete next.shapeType; // clear failed-fallback residue
              next.type = 'image_placeholder';
              // REGENERATION = new pixels, SAME box. The op schema makes the
              // model re-emit x/y/width/height alongside the new description,
              // and those regurgitated numbers are often wrong — the fresh
              // image then lands at a different size/position than the box the
              // user had. Pin the live element's geometry; a geometry-only
              // patch (no description change) still moves/resizes normally.
              for (const g of ['x', 'y', 'width', 'height']) {
                if (el[g] !== undefined) next[g] = el[g];
              }
            }
            return next;
          });
          // Only run the heavy image/normalize pipeline when a patch actually
          // introduces image or icon work — pure style/text merges are direct.
          const needsPipeline = (op.elements || []).some(p =>
            p && (p.type === 'image_placeholder' || p.imageDescription !== undefined
              || p.iconName !== undefined || p.icon !== undefined)); // 'icon' = model alias for iconName
          const finalElements = needsPipeline
            ? (await buildPageFromOp(
                { elements: merged },
                { ...(imageMapByPage.__deckMedia || {}), ...(imageMapByPage[op.slide_id] || {}) },
                working[idx].backgroundColor,
              )).elements
            : merged;
          const update = { ...working[idx], elements: finalElements, critique_recommended: true, hasUnsavedChanges: true };
          if (op.title) update.title = op.title;
          working[idx] = update;
          critiquedPagesRef.current?.delete?.(op.slide_id);
        } else if (op.op === 'remove_elements') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          const rm = new Set(op.element_ids || []);
          working[idx] = {
            ...working[idx],
            elements: (working[idx].elements || []).filter(e => !rm.has(e.id)),
            critique_recommended: true, hasUnsavedChanges: true,
          };
          critiquedPagesRef.current?.delete?.(op.slide_id);
        } else if (op.op === 'add_slide') {
          const built = await buildPageFromOp(op, imageMapByPage.__deckMedia || {}); // new page — deck media fallback resolves moved markers
          const page = {
            id: op.id || newId('new'), title: op.title || 'New Page', layout: op.layout || 'content',
            outline: op.outline || '', elements: built.elements,
            backgroundColor: built.backgroundColor || '#ffffff', notes: '',
            critique_recommended: true, hasUnsavedChanges: true,
          };
          let insertAt;
          if (op.after_slide_id) {
            const ai = working.findIndex(s => s.id === op.after_slide_id);
            insertAt = ai >= 0 ? ai + 1 : working.length;
          } else if (op.position === 'start') {
            insertAt = 0;
          } else if (op.position === 'end') {
            insertAt = working.length;
          } else {
            const ci = working.findIndex(s => s.id === currentPAGEId);
            insertAt = ci >= 0 ? ci + 1 : working.length;
          }
          working.splice(insertAt, 0, page);
          pendingLayoutFixRef.current?.add?.(page.id);
        } else if (op.op === 'delete_slide') {
          if (working.length <= 1) continue;
          working = working.filter(s => s.id !== op.slide_id);
        } else if (op.op === 'duplicate_slide') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          // DEEP-COPY the elements: a spread would share the element OBJECTS with
          // the source page, and the post-processor mutates elements in place —
          // a later edit to either page would then corrupt the other (same class
          // of bug as the backend duplicate_slide deepcopy fix).
          const dup = {
            ...working[idx],
            id: op.new_id || newId('dup'),
            elements: JSON.parse(JSON.stringify(working[idx].elements || [])),
            hasUnsavedChanges: true,
          };
          // The dup shares the source's image markers — alias its map so a later
          // edit op targeting the dup can still resolve {{UserMedia_*}}/_orig_ keys.
          if (imageMapByPage && imageMapByPage[op.slide_id]) {
            imageMapByPage[dup.id] = imageMapByPage[op.slide_id];
          }
          working.splice(idx + 1, 0, dup);
        } else if (op.op === 'reorder_slides') {
          const byId = {};
          working.forEach(s => { byId[s.id] = s; });
          const ordered = (op.order || []).map(id => byId[id]).filter(Boolean);
          working.forEach(s => { if (!(op.order || []).includes(s.id)) ordered.push(s); });
          if (ordered.length === working.length) working = ordered;
        } else if (op.op === 'update_style') {
          if (op.style && typeof op.style === 'object') setprintableStyle(prev => ({ ...prev, ...op.style }));
        } else if (op.op === 'update_header_footer') {
          if (op.header_footer && typeof op.header_footer === 'object') setHeaderFooter(prev => ({ ...prev, ...op.header_footer }));
        } else if (op.op === 'update_slide_numbers') {
          if (op.slide_numbers && typeof op.slide_numbers === 'object') setSlideNumbers(prev => ({ ...prev, ...op.slide_numbers }));
        }
      } catch (opErr) {
        console.error('❌ [AGENT-EDIT] operation failed:', op?.op, opErr);
      }
    }

    working = working.map((s, i) => ({ ...s, order: i + 1 }));
    setPAGES(working);
    return working;
  }, [PAGES, currentPAGEId, generationQuality, printableStyle, userDeviceId, handleCreditError, setPAGES]);

  const handleAgentEdit = useCallback(async (overrideInstruction) => {
    const typedInstruction = (typeof overrideInstruction === 'string' ? overrideInstruction : chatInput).trim();
    // Allow a paste-only send (screenshot, no text) with a default ask.
    const imagesForSend = aiPastedImages;
    const instruction = typedInstruction || (imagesForSend.length > 0 ? 'Use the attached screenshot(s) as reference for this edit.' : '');
    if ((!instruction) || isAiProcessing || isAiLocked) return;

    const hasImageSel = selectedElement && selectedElement.type === 'image';
    const hasVideoSel = selectedElements.some(el => el.type === 'video');
    const hasChartSel = selectedElements.some(el => el.type === 'chart');
    if (hasImageSel || hasVideoSel || hasChartSel) {
      return handleAiEnhanceRef.current?.(instruction);
    }

    if (!userDeviceId) {
      Alert.alert('Authentication Error', 'User ID not found. Please log in again to use AI features.');
      return;
    }

    setIsAiProcessing(true);
    // New agent turn — canvas history coalesces every op batch of this turn into
    // one undo step. The state updates below re-render before the first batch,
    // so the canvas sees the id before any operation applies.
    agentTurnIdRef.current = chatMsgUid();
    const userBubbleText = imagesForSend.length > 0
      ? `${instruction}  📎 ${imagesForSend.length} image${imagesForSend.length > 1 ? 's' : ''}`
      : instruction;
    setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: userBubbleText, timestamp: new Date(), actionType: 'user' }]);
    setChatInput('');
    setAiPastedImages([]);

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) { Alert.alert('Authentication Error', 'Please log in again.'); setIsAiProcessing(false); return; }

      // Keep each page's image map SEPARATE (keyed by page id) so restore stays
      // page-scoped (see buildPageFromOp). __deckMedia holds ONLY direct
      // UserMedia_* marker→src entries (no _orig_ backups → safety-net can't
      // re-inject) as a fallback for markers moved onto a different/new page.
      const imageMapByPage = {};
      const deckMediaMap = {};
      const payloadPages = PAGES.map(s => {
        const { processedPAGE, imageMap } = extractImagesFromPAGE(s);
        imageMapByPage[s.id] = imageMap;
        Object.keys(imageMap).forEach(k => { if (k.startsWith('UserMedia_')) deckMediaMap[k] = imageMap[k]; });
        // Strip base64 thumbnails — backend drops them before prompting anyway.
        const { PAGEThumbnail, slideThumbnail, thumbnail, ...rest } = processedPAGE;
        return { ...rest, id: s.id };
      });
      imageMapByPage.__deckMedia = deckMediaMap;

      const extractGoalString = (g) => !g ? null : (typeof g === 'string' ? g : (g.purpose ? extractGoalString(g.purpose) : null));
      const finalFolderIds = useUploadedData && selectedFolders.length > 0 ? selectedFolders.map(f => f.id || f) : [];
      // Auto-detect the page the user is ACTUALLY looking at (scroll position),
      // so "this page" in chat resolves correctly even before a click.
      const visibleId = getVisiblePageId?.() || currentPAGEId;
      if (visibleId && visibleId !== currentPAGEId) setCurrentPAGEId(visibleId);
      const currentIndex = Math.max(0, PAGES.findIndex(s => s.id === visibleId));
      // Skip transient 'thinking' lines — send real conversation turns only, so
      // a prior review's suggestions survive into the next turn ("yes, do it").
      const recentHistory = aiChatMessages
        .filter(m => m.actionType !== 'thinking')
        .slice(-6)
        .map(m => ({ role: m.actionType === 'user' ? 'user' : 'assistant', text: m.text }));

      // Transient 'thinking' line — replaced in place by the agent's live
      // reasoning (see the 'status' handler) and excluded from chat history.
      setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: `Looking at your ${PAGES.length} pages…`, timestamp: new Date(), actionType: 'thinking' }]);

      const abortController = new AbortController();
      agentAbortRef.current = abortController;
      const response = await fetch(`${apiConfig.API_URL}/printable/agent-edit-stream`, {
        method: 'POST',
        signal: abortController.signal,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          instruction,
          pages: payloadPages,
          current_page_index: currentIndex,
          style: printableStyle,
          header_footer: headerFooter,
          slide_numbers: slideNumbers,
          printable_goal: extractGoalString(printableGoal),
          printable_type: printableGoal?.documentType || 'informative',
          chat_history: recentHistory,
          folder_ids: finalFolderIds,
          // Screenshots pasted into the chat — OCR'd server-side and prepended
          // to the instruction context. Separate from page media (image_placeholder).
          image_attachments: imagesForSend.length > 0
            ? imagesForSend.map(p => ({ name: p.name, mimeType: p.mimeType, base64: p.base64 }))
            : null,
          // Non-media selection context — "this"/"it" targets these elements.
          selected_element_ids: selectedElementIds.length > 0 ? selectedElementIds : null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 402) { authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.'); setIsAiProcessing(false); return; }
        if (handleCreditError(errorData)) { setIsAiProcessing(false); return; }
        throw new Error(errorData.message || 'AI edit failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // The agent loop streams multiple op batches per turn — thread the deck
      // through each apply so we don't lose earlier batches to a stale closure.
      let liveDeck = PAGES.map(s => ({ ...s }));

      const handleEvent = async (event) => {
        if (event.type === 'status') {
          // Live "thinking" line — REPLACES the previous thinking line in place
          // (one updating line per turn instead of a stack of similar ones).
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
          // Raw server payload dump — when an apply corrupts a page, this is
          // the ground truth for whether the ops even touched the elements
          // that changed (frontend pipeline bug) or carried bad values
          // (backend emit bug). Keep: ops are small, corruption is rare.
          console.log('📥 [AGENT-EDIT] raw operations:', JSON.stringify(event.operations));
          if (event.chat_message) {
            setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: event.chat_message, timestamp: new Date(), actionType: 'edit' }]);
          }
          liveDeck = await applyAgentOperations(event.operations || [], imageMapByPage, liveDeck);
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
          try { await handleEvent(JSON.parse(t.slice(6))); } catch (e) { console.warn('⚠️ [AGENT-EDIT] SSE parse:', e); }
        }
      }
      if (buffer.trim().startsWith('data: ')) {
        try { await handleEvent(JSON.parse(buffer.trim().slice(6))); } catch { }
      }
    } catch (error) {
      // User pressed Stop — handleStopAgent already posted "Stopped." Swallow.
      if (error?.name === 'AbortError') return;
      console.error('Agent edit error:', error);
      if (error?.message && !isInsufficientCreditsError({ message: error.message })) {
        Alert.alert('Error', 'Failed to process request. Please try again.');
      }
    } finally {
      agentAbortRef.current = null;
      agentTurnIdRef.current = null; // end of turn — next turn gets a fresh coalescing id
      setIsAiProcessing(false);
    }
  }, [chatInput, aiPastedImages, isAiProcessing, isAiLocked, PAGES, currentPAGEId, setCurrentPAGEId, getVisiblePageId, apiConfig, printableStyle, headerFooter, slideNumbers, printableGoal, userDeviceId, selectedFolders, useUploadedData, aiChatMessages, applyAgentOperations, handleCreditError, selectedElement, selectedElements, selectedElementIds]);

  handleAgentEditRef.current = handleAgentEdit;

  // Capture screenshots pasted into the AI chat (web), gated on chat focus.
  const handleAiPastedImages = useCallback((entries) => {
    if (!entries || entries.length === 0) return;
    setAiPastedImages((prev) => {
      const MAX = 4;
      const room = MAX - prev.length;
      if (room <= 0) return prev;
      return [...prev, ...entries.slice(0, room)];
    });
  }, []);
  const isAiPasteActive = useCallback(() => aiChatFocusedRef.current, []);
  useImagePaste({ isActive: isAiPasteActive, onImages: handleAiPastedImages });

  // [DISABLED FOR TESTING] Auto layout fix — thinking tokens in LLM may have fixed layout issues.
  // Uncomment to re-enable if layouts still have overlap/bounds problems.
  // useEffect(() => {
  //   if (pendingLayoutFixRef.current.size > 0) {
  //     const ids = [...pendingLayoutFixRef.current];
  //     pendingLayoutFixRef.current.clear();
  //     const layoutFixInstruction = `Fix layout and overlapping issues on this page.
  //
  // CANVAS: 794×1123 pixels (A4 portrait). ABSOLUTE BOUNDS: Every element must satisfy x ≥ 20, y ≥ 20, x+width ≤ 754, y+height ≤ 1083. NO EXCEPTIONS — nothing may extend below y+height=1083 or past x+width=754.
  //
  // PRIORITY (highest first):
  // 1. BOUNDS — every element fully inside the safe area. This overrides everything else.
  // 2. NO OVERLAPS — at least 10px gap between ALL element bounding boxes. This includes images, cards, text, shapes, icons — EVERY element type. Two elements overlap if their rectangles (x,y,width,height) intersect. Check EVERY pair.
  // 3. READABILITY — minimum fontSize 12px, minimum element height 24px.
  // 4. CONTENT PRESERVATION — keep as much content as possible, but sacrifice content to satisfy rules 1-3.
  //
  // OVERLAP DETECTION (CRITICAL):
  // - For EACH element, compute its bounding box: left=x, top=y, right=x+width, bottom=y+height.
  // - Two elements overlap if: left1 < right2 AND right1 > left2 AND top1 < bottom2 AND bottom1 > top2.
  // - Images, cards, and text blocks ALL have bounding boxes. Do NOT layer cards or text on top of images.
  // - If an overlap is detected, move the lower element further down, or reduce sizes to eliminate the overlap.
  //
  // TEXT HEIGHT FORMULA (use before positioning):
  //   chars_per_line = floor(width / (fontSize × 0.55))
  //   num_lines = ceil(text_length / chars_per_line)
  //   rendered_height = num_lines × fontSize × lineHeight
  // Always compute the bottom edge (y + rendered_height) before placing the next element below.
  //
  // WHEN CONTENT OVERFLOWS THE CANVAS:
  // - First: reduce fontSize (min 12px) and lineHeight (min 1.15).
  // - Second: reduce spacing/gaps between elements.
  // - Third: truncate or condense long descriptions — keep key info, drop filler.
  // - Fourth: remove the least important elements (decorative shapes, redundant icons).
  // - NEVER leave an element partially outside the canvas.
  //
  // Keep the same design, colors, and style. Return the full page JSON.`;
  //     for (const id of ids) {
  //       const page = PAGES.find(p => p.id === id);
  //       if (page) {
  //         handleAiEnhanceRef.current?.(layoutFixInstruction, page, true);
  //       }
  //     }
  //   }
  // }, [PAGES]);



  // Create new printable
  const handleCreateNew = useCallback(() => {
    if (onClearPrintable) {
      onClearPrintable();
    }
    setPAGES([{
      id: `PAGE_${Date.now()}`,
      order: 1,
      title: 'Title PAGE',
      layout: 'title',
      elements: [],
      backgroundColor: '#ffffff',
      hasUnsavedChanges: false,
    }]);
    setCurrentPrintableId(null);
    setprintableTitle('Untitled');
    setprintableGoal(null);
    setprintableStyle(PRESET_STYLES[0]);
    setHeaderFooter(DEFAULT_HEADER_FOOTER);
    setSlideNumbers(DEFAULT_SLIDE_NUMBERS);
    setShowGoalSetting(true);

    // Clear cached thumbnails and tracking for new printable
    setPAGEThumbnails({});
    initialThumbnailGeneratedRef.current.clear();
    critiquedPagesRef.current.clear();
    inFlightCritiquesRef.current.clear();
  }, [setPAGES, onClearPrintable]);

  // Generate thumbnail from first PAGE
  const generateThumbnail = useCallback(async () => {
    try {
      // Use first page's canvas ref (or active canvas) for the printable thumbnail
      const firstPageId = PAGES[0]?.id;
      const ref = firstPageId ? canvasRefsMap.current.get(firstPageId) : null;
      const canvas = ref?.current || canvasRef.current;
      if (canvas && canvas.toDataURL) {
        const dataUrl = await canvas.toDataURL({ format: 'jpeg', quality: 0.6 });
        return dataUrl;
      }
    } catch (err) {
      console.warn('📸 [SAVE] Failed to generate thumbnail:', err);
    }
    return null;
  }, [PAGES]);

  // Vision-critique pass for a single page. Snapshots the rendered fabric
  // canvas, POSTs to /printable/critique-page, and swaps the page's elements
  // with the patched list when the server returns ≥1 applied patch. Mirrors
  // the presentation flow exactly so the two surfaces share a model of
  // post-render polish. Idempotent — guarded by critiquedPagesRef.
  const runVisualCritique = useCallback(async (pageId) => {
    try {
      const canvasRefHandle = canvasRefsMap.current.get(pageId);
      const canvasInstance = canvasRefHandle?.current;
      if (!canvasInstance?.snapshotForCritique) {
        // Canvas ref not ready or older build without the method — skip silently
        return;
      }
      const screenshot = canvasInstance.snapshotForCritique();
      if (!screenshot) return;

      const page = PAGES.find(p => p.id === pageId);
      if (!page || !Array.isArray(page.elements) || page.elements.length === 0) return;

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) return;

      console.log(`🖼️ [CRITIQUE] Sending page ${pageId} for vision review (${page.elements.length} elements)`);

      const response = await fetch(`${apiConfig.API_URL}/printable/critique-page`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          elements: page.elements,
          screenshot,
          page_info: { title: page.title || '', content_hint: page.outline || '' },
          canvas: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
        }),
      });

      if (!response.ok) {
        console.warn(`🖼️ [CRITIQUE] Server returned ${response.status} for page ${pageId}`);
        critiquedPagesRef.current.add(pageId); // don't retry — server is unhappy
        return;
      }

      const result = await response.json();
      const applied = result?.patches_applied || 0;
      const issues = result?.issues || [];
      console.log(`🖼️ [CRITIQUE] Page ${pageId}: ${issues.length} issues, ${applied} patches applied`);

      if (applied > 0 && Array.isArray(result.elements)) {
        // Swap the patched elements into the page. We replace the whole list
        // because the critique can add/delete/modify; partial merging would
        // miss deletions and re-introduce overlap.
        setPAGES(prev => prev.map(p => (p.id === pageId ? { ...p, elements: result.elements } : p)));
        // Force a thumbnail re-render after the patch lands.
        initialThumbnailGeneratedRef.current.delete(pageId);
      }

      critiquedPagesRef.current.add(pageId);
    } catch (err) {
      console.warn(`🖼️ [CRITIQUE] Failed for page ${pageId}:`, err);
      critiquedPagesRef.current.add(pageId);
    }
  }, [PAGES, setPAGES, apiConfig]);

  // Deck-complete parallel critique flush.
  //
  // Per-page critique also fires from handleCanvasRenderComplete as each
  // canvas finishes rendering, but during a fresh deck generation that
  // callback can fire before images settle or before the canvas is even
  // mounted (offscreen pages). When the deck flips from generating →
  // complete, fire critique for every page that hasn't been critiqued yet
  // IN PARALLEL via Promise.all — they run truly concurrently server-side.
  const prevIsGeneratingPagesRef = useRef(false);
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const wasGenerating = prevIsGeneratingPagesRef.current;
    prevIsGeneratingPagesRef.current = isGeneratingPAGES;
    if (!wasGenerating || isGeneratingPAGES) return; // only fire on true→false edge

    const pagesToCritique = PAGES.filter(
      (p) =>
        p &&
        p.critique_recommended === true &&
        !critiquedPagesRef.current.has(p.id) &&
        !inFlightCritiquesRef.current.has(p.id)
    );
    if (pagesToCritique.length === 0) return;

    console.log(`🖼️ [CRITIQUE] Deck complete — flushing critique for ${pagesToCritique.length} page(s) in parallel`);
    pagesToCritique.forEach((p) => inFlightCritiquesRef.current.add(p.id));
    Promise.all(
      pagesToCritique.map(async (p) => {
        try {
          await waitForCanvasImages(p, 5000);
          await new Promise((r) => setTimeout(r, 150));
          await runVisualCritique(p.id);
        } finally {
          inFlightCritiquesRef.current.delete(p.id);
        }
      })
    );
  }, [isGeneratingPAGES, PAGES, runVisualCritique, waitForCanvasImages]);

  // Callback when canvas finishes rendering - generate thumbnail after images load
  const handleCanvasRenderComplete = useCallback((PAGEId) => {
    // console.log('📸 [THUMBNAIL] handleCanvasRenderComplete called with:', PAGEId, 'platform:', Platform.OS);

    if (!PAGEId || Platform.OS !== 'web') {
      // console.log('📸 [THUMBNAIL] Early return - PAGEId:', PAGEId, 'platform:', Platform.OS);
      return;
    }

    const page = PAGES.find(p => p.id === PAGEId);

    // Vision-critique pass — runs even while isGeneratingPAGES is still true
    // (per-page, not per-deck). Each critique is fire-and-forget and safe to
    // run concurrently with other pages still being generated server-side.
    if (
      page &&
      page.critique_recommended === true &&
      !critiquedPagesRef.current.has(PAGEId) &&
      !inFlightCritiquesRef.current.has(PAGEId)
    ) {
      inFlightCritiquesRef.current.add(PAGEId);
      (async () => {
        try {
          await waitForCanvasImages(page, 5000);
          await new Promise(r => setTimeout(r, 150));
          await runVisualCritique(PAGEId);
        } finally {
          inFlightCritiquesRef.current.delete(PAGEId);
        }
      })();
    }

    // Skip thumbnail generation while AI is actively generating/editing pages
    if (isGeneratingPAGESRef.current || isAutoUpdatingRef.current || isAiProcessingRef.current) return;

    // Skip if we already successfully generated thumbnail for this PAGE
    if (initialThumbnailGeneratedRef.current.has(PAGEId)) {
      // console.log('📸 [THUMBNAIL] Skipped - already generated for PAGE:', PAGEId);
      return;
    }

    // console.log('📸 [THUMBNAIL] Waiting for images then generating thumbnail for PAGE:', PAGEId);

    const capture = async () => {
      if (page) await waitForCanvasImages(page, 5000);
      // Extra delay for final paint
      await new Promise(r => setTimeout(r, 150));
      generatePAGEThumbnail(PAGEId, true);
    };
    capture();
  }, [generatePAGEThumbnail, PAGES, waitForCanvasImages, runVisualCritique]);

  // Debounced effect to regenerate thumbnail when content changes (after initial generation)
  useEffect(() => {
    if (!currentPAGEId || Platform.OS !== 'web') return;

    // Skip thumbnail regeneration while AI is actively generating/editing pages
    if (isGeneratingPAGES || isAutoUpdating || isAiProcessing) return;

    // Skip if no thumbnail exists yet (canvas render complete callback handles it)
    if (!initialThumbnailGeneratedRef.current.has(currentPAGEId)) return;

    // Clear any pending thumbnail generation
    if (thumbnailGenerationRef.current) {
      clearTimeout(thumbnailGenerationRef.current);
    }

    // Debounce thumbnail regeneration for content changes
    thumbnailGenerationRef.current = setTimeout(() => {
      generatePAGEThumbnail(currentPAGEId, false);
    }, 500);

    return () => {
      if (thumbnailGenerationRef.current) {
        clearTimeout(thumbnailGenerationRef.current);
      }
    };
  }, [currentPAGEId, currentPAGE, generatePAGEThumbnail, isGeneratingPAGES, isAutoUpdating, isAiProcessing]);

  // Background thumbnail queue: after initial page renders, generate thumbnails for remaining pages
  useEffect(() => {
    if (Platform.OS !== 'web' || !currentPAGEId || PAGES.length <= 1) return;

    // Don't start thumbnail queue while AI is actively generating/editing pages
    if (isGeneratingPAGES || isAutoUpdating || isAiProcessing) return;

    // Don't restart if queue is already running
    if (thumbnailQueueStartedRef.current) return;

    // Wait until first page has been rendered and captured
    if (!initialThumbnailGeneratedRef.current.has(currentPAGEId)) return;

    // Find pages that still have no thumbnail
    const missingPages = PAGES.filter(
      p => !initialThumbnailGeneratedRef.current.has(p.id)
    );

    if (missingPages.length === 0) return;

    // Mark queue as started to prevent re-triggering
    thumbnailQueueStartedRef.current = true;

    // Abort any previous queue
    if (backgroundThumbnailQueueRef.current) {
      backgroundThumbnailQueueRef.current.aborted = true;
    }

    const queueState = { aborted: false };
    backgroundThumbnailQueueRef.current = queueState;
    const firstPAGEId = PAGES[0]?.id;

    // console.log('📸 [THUMBNAIL-QUEUE] Starting background generation for', missingPages.length, 'pages');

    const runQueue = async () => {
      setIsGeneratingThumbnails(true);
      try {
        for (const page of missingPages) {
          if (queueState.aborted) {
            // console.log('📸 [THUMBNAIL-QUEUE] Aborted');
            return;
          }

          // Switch to the page \u2014 canvas will render it and fire handleCanvasRenderComplete
          setCurrentPAGEId(page.id);

          // Wait for canvas to render elements
          await new Promise(resolve => setTimeout(resolve, 300));
          if (queueState.aborted) return;

          // Wait for all images to fully load on the canvas
          await waitForCanvasImages(page, 5000);
          if (queueState.aborted) return;

          // Small extra delay for final paint
          await new Promise(resolve => setTimeout(resolve, 100));
          if (queueState.aborted) return;

          // Capture thumbnail now that images are loaded
          await generatePAGEThumbnail(page.id, true);
        }

        // Always switch to first page after queue completes
        if (!queueState.aborted && firstPAGEId) {
          // console.log('📸 [THUMBNAIL-QUEUE] Complete, switching to first page');
          setCurrentPAGEId(firstPAGEId);
        }
      } finally {
        setIsGeneratingThumbnails(false);
        thumbnailQueueStartedRef.current = false;
      }
    };

    // Small delay before starting queue to let the UI settle
    setTimeout(runQueue, 500);
    // Queue runs uninterrupted \u2014 abort only on new document load via backgroundThumbnailQueueRef
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [PAGES.length, PAGEThumbnails, currentPAGEId, isGeneratingPAGES, isAutoUpdating, isAiProcessing]);

  // Save printable
  const handleSave = useCallback(async () => {
    setIsSavingManual(true);
    try {
      // Generate thumbnail from current (first) PAGE
      let thumbnail = null;
      if (PAGES.length > 0) {
        // Temporarily switch to first PAGE for thumbnail if not already there
        const wasFirstPAGE = currentPAGEId === PAGES[0]?.id;
        if (!wasFirstPAGE) {
          setCurrentPAGEId(PAGES[0]?.id);
          // Small delay to allow canvas to render first PAGE
          await new Promise(resolve => setTimeout(resolve, 300));
        }
        thumbnail = await generateThumbnail();
        if (!wasFirstPAGE) {
          // Switch back to original PAGE
          setCurrentPAGEId(currentPAGEId);
        }
      }

      // CRITICAL: Hydrate icons with SVG paths before saving
      // The backend needs svgPath to upload to S3, but local state might only have iconName
      const hydratedPAGES = await Promise.all(PAGES.map(async (PAGE) => {
        if (!PAGE.elements) return PAGE;

        const hydratedElements = await Promise.all(PAGE.elements.map(async (element) => {
          if (element.type === 'icon' && !element.svgSrc && !element.svgPath && (element.iconName || element.resolvedIconName)) {
            // Resolve icon data locally
            const iconName = element.iconName || element.resolvedIconName;
            try {
              const iconData = await mapIconToPathAsync(iconName);
              // Handle both new format (svg) and legacy format (path)
              // FIX: Don't save "circle" as resolvedIconName if it's just a fallback - preserve original iconName
              const isCircleFallback = iconData.name === 'circle' && iconName !== 'circle';
              if (isCircleFallback) {
                console.warn(`💾 [SAVE] Icon ${iconName} returned circle fallback, preserving original iconName`);
                // Don't set resolvedIconName to circle, keep original iconName for future resolution
                return element;
              }
              if (iconData.svg) {
                console.log(`💾 [SAVE] Hydrating icon ${iconName} with full SVG`);
                return { ...element, svgPath: iconData.svg, resolvedIconName: iconData.name };
              } else if (iconData.path) {
                console.log(`💾 [SAVE] Hydrating icon ${iconName} with path`);
                return { ...element, svgPath: iconData.path, resolvedIconName: iconData.name };
              }
            } catch (e) {
              console.warn(`Failed to hydrate icon ${iconName}:`, e);
            }
          }
          return element;
        }));

        return { ...PAGE, elements: hydratedElements };
      }));

      // Attach per-page thumbnails for persistence (restored on next load)
      const pagesWithThumbnails = hydratedPAGES.map(page => ({
        ...page,
        pageThumbnail: PAGEThumbnails[page.id] || page.pageThumbnail || null,
      }));

      // Save to server with thumbnail
      const saveResult = await savePrintableToServer({
        printableMetadata: {
          id: currentPrintableId,
          title: printableTitle,
          style: { ...printableStyle, headerFooter, slideNumbers },
        },
        PAGES: pagesWithThumbnails,
        printableGoal,
        thumbnail, // Include thumbnail for printable list
        folderIds: selectedFolders.map(f => f.id || f),
      }, apiConfig, currentPrintableId);

      const savedId = saveResult?.id || saveResult;

      // Update ID if this was a new printable
      if (savedId) {
        setCurrentPrintableId(savedId);
      }

      // Update local pages with server-persisted URLs (S3 presigned) to avoid re-uploading on next save
      if (saveResult?.pages) {
        setPAGES(prevPAGES => {
          return prevPAGES.map(localPage => {
            const serverPage = saveResult.pages.find(
              (sp, idx) => sp.id === localPage.id || idx === prevPAGES.indexOf(localPage)
            );
            if (!serverPage) return localPage;

            const updatedPage = { ...localPage };
            if (serverPage.backgroundImage) {
              updatedPage.backgroundImage = serverPage.backgroundImage;
            }

            if (serverPage.elements && localPage.elements) {
              updatedPage.elements = localPage.elements.map(localEl => {
                const serverEl = serverPage.elements.find(se => se.id === localEl.id);
                if (!serverEl) return localEl;

                const merged = { ...localEl };
                if (serverEl.src && localEl.type === 'image') {
                  merged.src = serverEl.src;
                }
                if (serverEl.svgSrc && localEl.type === 'icon') {
                  merged.svgSrc = serverEl.svgSrc;
                }
                if (serverEl.src && localEl.type === 'video') {
                  merged.src = serverEl.src;
                }
                return merged;
              });
            }
            return updatedPage;
          });
        });
      }

      // Also save locally as backup
      await savePrintable({
        id: savedId || currentPrintableId,
        PAGES: hydratedPAGES,
        title: printableTitle,
        goal: printableGoal,
        style: { ...printableStyle, headerFooter, slideNumbers },
      });

      isDirtyRef.current = false; // saved — clear the unsaved-changes flag
      Alert.alert('Saved', 'Dashboard saved successfully.');
    } catch (error) {
      console.error('Failed to save printable:', error);
      Alert.alert('Error', 'Failed to save.');
    } finally {
      setIsSavingManual(false);
    }
  }, [savePrintableToServer, savePrintable, currentPrintableId, PAGES, setPAGES, printableTitle, printableGoal, printableStyle, apiConfig, generateThumbnail, currentPAGEId, setCurrentPAGEId]);

  // PowerPoint-parity keyboard (web): Ctrl+S performs a real app save (the canvas
  // layer already suppresses the browser save dialog but saves nothing), and
  // PgUp/PgDn navigate between pages like PPT. Inputs keep PgUp/PgDn for scrolling.
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        if (!isSavingManual && !isReadOnly) handleSave();
        return;
      }
      if (e.key === 'PageUp' || e.key === 'PageDown') {
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        e.preventDefault();
        if (e.key === 'PageDown') goToNextPAGE(); else goToPrevPAGE();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handleSave, isSavingManual, isReadOnly, goToNextPAGE, goToPrevPAGE]);

  // Unsaved-changes tracking: any content change after the initial load marks the
  // document dirty; a successful save clears it (see handleSave). While a load is
  // in flight the tracker is DISARMED so hydration doesn't count as an edit.
  useEffect(() => {
    if (isLoadingPrintable) {
      dirtyTrackingArmedRef.current = false;
      isDirtyRef.current = false;
      return;
    }
    if (!dirtyTrackingArmedRef.current) {
      dirtyTrackingArmedRef.current = true; // first clean render after mount/load
      return;
    }
    isDirtyRef.current = true;
  }, [PAGES, printableStyle, printableTitle, headerFooter, slideNumbers, isLoadingPrintable]);

  // PowerPoint-parity: warn before closing the tab with unsaved changes.
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const onBeforeUnload = (e) => {
      if (isDirtyRef.current) {
        e.preventDefault();
        e.returnValue = ''; // required by Chrome to show the native prompt
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  // Save a Copy - creates a completely independent copy with a new ID
  const handleSaveAsCopy = useCallback(async () => {
    setIsSavingManual(true);
    try {
      // Generate thumbnail from first PAGE
      let thumbnail = null;
      if (PAGES.length > 0) {
        const wasFirstPAGE = currentPAGEId === PAGES[0]?.id;
        if (!wasFirstPAGE) {
          setCurrentPAGEId(PAGES[0]?.id);
          await new Promise(resolve => setTimeout(resolve, 300));
        }
        thumbnail = await generateThumbnail();
        if (!wasFirstPAGE) {
          setCurrentPAGEId(currentPAGEId);
        }
      }

      // Hydrate icons with SVG paths before saving
      const hydratedPAGES = await Promise.all(PAGES.map(async (PAGE) => {
        if (!PAGE.elements) return PAGE;
        const hydratedElements = await Promise.all(PAGE.elements.map(async (element) => {
          if (element.type === 'icon' && !element.svgSrc && !element.svgPath && (element.iconName || element.resolvedIconName)) {
            const iconName = element.iconName || element.resolvedIconName;
            try {
              const iconData = await mapIconToPathAsync(iconName);
              const isCircleFallback = iconData.name === 'circle' && iconName !== 'circle';
              if (isCircleFallback) return element;
              if (iconData.svg) return { ...element, svgPath: iconData.svg, resolvedIconName: iconData.name };
              if (iconData.path) return { ...element, svgPath: iconData.path, resolvedIconName: iconData.name };
            } catch (e) { console.warn(`Failed to hydrate icon ${iconName}:`, e); }
          }
          return element;
        }));
        return { ...PAGE, elements: hydratedElements };
      }));

      const pagesWithThumbnails = hydratedPAGES.map(page => ({
        ...page,
        pageThumbnail: PAGEThumbnails[page.id] || page.pageThumbnail || null,
      }));

      const copyTitle = printableTitle.endsWith(' (Copy)') ? printableTitle : `${printableTitle} (Copy)`;

      // Save with id: null to force creation of a new document
      const saveResult = await savePrintableToServer({
        printableMetadata: {
          id: null,
          title: copyTitle,
          style: { ...printableStyle, headerFooter, slideNumbers },
        },
        PAGES: pagesWithThumbnails,
        printableGoal,
        thumbnail,
        folderIds: selectedFolders.map(f => f.id || f),
      }, apiConfig, null);

      const savedId = saveResult?.id || saveResult;

      if (savedId) {
        // Switch UI to the new copy
        setCurrentPrintableId(savedId);
        setprintableTitle(copyTitle);
        if (Platform.OS === 'web') navigateToPrintable(savedId);
      }

      // Update local pages with server-persisted URLs
      if (saveResult?.pages) {
        setPAGES(prevPAGES => {
          return prevPAGES.map(localPage => {
            const serverPage = saveResult.pages.find(
              (sp, idx) => sp.id === localPage.id || idx === prevPAGES.indexOf(localPage)
            );
            if (!serverPage) return localPage;
            const updatedPage = { ...localPage };
            if (serverPage.backgroundImage) updatedPage.backgroundImage = serverPage.backgroundImage;
            if (serverPage.elements && localPage.elements) {
              updatedPage.elements = localPage.elements.map(localEl => {
                const serverEl = serverPage.elements.find(se => se.id === localEl.id);
                if (!serverEl) return localEl;
                const merged = { ...localEl };
                if (serverEl.src && localEl.type === 'image') merged.src = serverEl.src;
                if (serverEl.svgSrc && localEl.type === 'icon') merged.svgSrc = serverEl.svgSrc;
                if (serverEl.src && localEl.type === 'video') merged.src = serverEl.src;
                return merged;
              });
            }
            return updatedPage;
          });
        });
      }

      Alert.alert('Saved', 'A copy has been created. You are now editing the new copy.');
    } catch (error) {
      console.error('Failed to save printable copy:', error);
      Alert.alert('Error', 'Failed to save copy.');
    } finally {
      setIsSavingManual(false);
    }
  }, [savePrintableToServer, currentPrintableId, PAGES, setPAGES, printableTitle, printableGoal, printableStyle, apiConfig, generateThumbnail, currentPAGEId, setCurrentPAGEId, PAGEThumbnails]);

  // Build outline data from current pages for the Update All modal
  const currentOutlineData = useMemo(() => {
    return PAGES.map((page, index) => {
      let outline = page.outline || page.sectionTopic || page.content_hint || '';
      // Fallback: extract text from elements for old printables without outline
      if (!outline && page.elements) {
        const textParts = page.elements
          .filter(el => el.type === 'text' && (el.content || el.text))
          .map(el => (el.content || el.text || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim())
          .filter(Boolean);
        outline = textParts.join(' | ').slice(0, 200);
      }
      return {
        slideIndex: index,
        title: page.title || `Page ${index + 1}`,
        outline,
      };
    });
  }, [PAGES]);

  // Refresh outline using AI - regenerates outline suggestions based on goal + vault
  const handleRefreshOutline = useCallback(async (editedGoal, currentOutline) => {
    setIsRefreshingOutline(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) return null;

      const finalFolderIds = useUploadedData && selectedFolders.length > 0
        ? selectedFolders.map(f => f.id || f)
        : [];

      const response = await fetch(`${apiConfig.API_URL}/printable/generate-outline-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          goal: editedGoal || printableGoal?.purpose || '',
          printable_type: printableGoal?.documentType || 'informative',
          target_audience: printableGoal?.targetAudience || '',
          PAGE_count: currentOutline?.length || PAGES.length,
          folder_ids: finalFolderIds,
          use_internet_search: false,
          existing_outline: currentOutline?.map(item => ({
            id: item.slideIndex + 1,
            title: item.title || '',
            outline: item.outline || '',
          })),
        }),
      });

      if (!response.ok) return null;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const streamedPages = [];
      let suggestedTopic = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'topic' && data.topic) {
                suggestedTopic = data.topic;
              } else if (data.type === 'PAGE') {
                streamedPages.push({
                  slideIndex: data.PAGE?.original_id != null ? data.PAGE.original_id - 1 : data.index,
                  title: data.PAGE?.title || `Page ${data.index + 1}`,
                  outline: data.PAGE?.outline || data.PAGE?.content_hint || '',
                });
              }
            } catch (e) {
              // skip parse errors
            }
          }
        }
      }

      if (streamedPages.length > 0) {
        return { topic: suggestedTopic || editedGoal, outline: streamedPages };
      }
      return null;
    } catch (error) {
      console.error('Failed to refresh outline:', error);
      return null;
    } finally {
      setIsRefreshingOutline(false);
    }
  }, [apiConfig, useUploadedData, selectedFolders, printableGoal, PAGES.length]);

  // Auto Update - Refresh all PAGES with latest vault data
  // Auto Update - Step 1: Show Instruction Modal
  const handleAutoUpdate = useCallback(() => {
    if (isAutoUpdating) return;

    if (isDocumentLocked) {
      Alert.alert('Document Locked', `Locked by ${documentLockedBy?.name || 'another user'}.`);
      return;
    }

    if (PAGES.length === 0) {
      Alert.alert('Empty', 'No pages to update.');
      return;
    }

    setShowUpdateInstructionModal(true);
  }, [isAutoUpdating, isDocumentLocked, documentLockedBy, PAGES.length]);

  // Auto Update - Step 2: Execute Update with Instruction (Smart orchestrate-all path)
  const handleConfirmUpdate = useCallback(async ({ instruction, updatedGoal, updatedOutline, outlineChanged }) => {
    if (isAutoUpdating || PAGES.length === 0) return;

    // Acquire lock (only required in collaboration mode)
    if (collaboration?.ydoc && !requestDocumentLock()) {
      Alert.alert('Lock Failed', 'Could not acquire document lock.');
      setShowUpdateInstructionModal(false);
      return;
    }

    // Update goal if changed — always persist regardless of vault selection
    if (updatedGoal) {
      const newGoal = typeof printableGoal === 'object'
        ? { ...printableGoal, purpose: updatedGoal }
        : { purpose: updatedGoal };
      setprintableGoal(newGoal);
    }

    // Update page outlines if changed — always persist regardless of vault selection
    // Use positional mapping: i-th outline item → i-th page (outline may have been
    // refreshed/reordered/added/deleted in the modal, so slideIndex can be stale)
    if (updatedOutline && Array.isArray(updatedOutline)) {
      updatedOutline.forEach((item, idx) => {
        const page = PAGES[idx];
        if (page) {
          updatePAGE(page.id, {
            title: item.title || page.title,
            outline: item.outline || page.outline,
          });
        }
      });
    }

    // Only use vault if folders are explicitly selected (no default to 'general')
    const finalFolderIds = useUploadedData && selectedFolders.length > 0
      ? selectedFolders.map(f => f.id || f)
      : [];

    if (finalFolderIds.length === 0) {
      Alert.alert('No Data Store Selected', 'Please select data store folders to update from.');
      releaseDocumentLock();
      return;
    }

    setIsAutoUpdating(true);
    setShowUpdateInstructionModal(false);
    setAutoUpdateProgress({ current: 0, total: PAGES.length });

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        setIsAutoUpdating(false);
        releaseDocumentLock();
        return;
      }

      const extractGoalString = (goalData) => {
        if (!goalData) return null;
        if (typeof goalData === 'string') return goalData;
        if (goalData.purpose) return extractGoalString(goalData.purpose);
        return null;
      };

      // Filter out hidden pages for AI processing
      const aiPages = PAGES.filter(p => !p.hidden);
      const aiIndexToFullIndex = aiPages.map(p => PAGES.indexOf(p));

      // Build summaries with updated outline data (positional: i-th outline → i-th visible page)
      const pagesSummary = buildSlidesSummary(aiPages).map((summary, idx) => {
        const outlineItem = updatedOutline?.[idx];
        if (outlineItem) {
          return {
            ...summary,
            title: outlineItem.title || summary.title,
            outline: outlineItem.outline || summary.outline,
          };
        }
        return summary;
      });

      // Build the update instruction incorporating goal context
      const goalString = updatedGoal || extractGoalString(printableGoal) || '';
      const baseInstruction = "Update all pages with the latest data, statistics, and information from my data store. You have full freedom to restructure content as needed. IMPORTANT: Refresh imageDescription of image_placeholder elements to match the updated content.";

      // Include the full target outline in the instruction so AI knows desired structure
      let outlineContext = '';
      if (updatedOutline && updatedOutline.length > 0) {
        const outlineList = updatedOutline.map((item, i) => `${i + 1}. ${item.title}${item.outline ? ': ' + item.outline : ''}`).join('\n');
        outlineContext = `\n\nTARGET OUTLINE (${updatedOutline.length} pages):\n${outlineList}\nRedistribute and update content to match this outline structure.`;
      }

      const fullInstruction = (instruction && instruction !== "Update with the latest data from my data store."
        ? `${baseInstruction}\n\nAdditional: ${instruction}`
        : baseInstruction) + outlineContext;

      // Extract images from visible pages before sending to API
      const imageMaps = {};
      const processedFullPages = aiPages.map((page, idx) => {
        const { processedPAGE, imageMap } = extractImagesFromPAGE(page);
        imageMaps[idx] = imageMap;
        return { ...processedPAGE, id: page.id };
      });

      const currentIndex = aiPages.findIndex(s => s.id === currentPAGEId);

      // Use smart orchestrate-all-stream endpoint
      const response = await fetch(`${apiConfig.API_URL}/printable/orchestrate-all-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          instruction: fullInstruction,
          pages_summary: pagesSummary,
          full_pages: processedFullPages,
          current_page_index: currentIndex >= 0 ? currentIndex : 0,
          folder_ids: finalFolderIds,
          style: printableStyle,
          printable_goal: goalString,
          printable_type: printableGoal?.documentType || 'informative',
          icon_set: printableStyle?.iconSet || 'default',
          is_update_all: true,
          outline_changed: !!outlineChanged,
          deck_profile: printableGoal?.deckProfile || 'corporate',
          deck_plan: printableGoal?.deckPlan || null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 402) {
          authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.');
          setIsAutoUpdating(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          return;
        }
        if (handleCreditError(errorData)) {
          setIsAutoUpdating(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
          return;
        }
        throw new Error(errorData.message || 'Failed to process update');
      }

      // Process SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let successCount = 0;
      let totalMatched = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          try {
            const event = JSON.parse(trimmed.slice(6));

            if (event.type === 'classification') {
              totalMatched = event.relevant_count || 0;
              setAutoUpdateProgress({ current: 0, total: totalMatched });
            } else if (event.type === 'progress') {
              setAutoUpdateProgress(prev => ({ ...prev, current: (event.page_index || 0) + 1 }));
            } else if (event.type === 'page_result' && event.slide_data) {
              try {
                const fullIndex = aiIndexToFullIndex[event.page_index];
                const originalPage = PAGES[fullIndex];
                if (!originalPage) continue;

                // Restore images using the image map for this page
                const editImageMap = imageMaps[event.page_index] || {};
                const restoredPageData = restoreImagesToPAGE(event.slide_data, editImageMap);
                const processedPageOutput = await processPAGEAsync(restoredPageData);

                // Generate images for image_placeholder elements
                const imagePlaceholders = (processedPageOutput.elements || []).filter(el => el.type === 'image_placeholder');
                await generateImagesParallel(imagePlaceholders, {
                  generationQuality, style: printableStyle?.name || 'professional',
                  userId: userDeviceId, defaultDescription: 'Professional printable image', handleCreditError,
                });

                // Safety net: catch any remaining type='image' elements without src
                const finalElements = (processedPageOutput.elements || []).map(el => {
                  if (el.type === 'image' && !el.src && !el.isUserMedia) {
                    console.warn(`⚠️ [UPDATE_ALL] Image element ${el.id} still has no src after generation — converting to shape`);
                    return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                  }
                  return el;
                });

                // Apply update
                const pageUpdate = { elements: finalElements };
                if (processedPageOutput.backgroundColor) pageUpdate.backgroundColor = processedPageOutput.backgroundColor;
                if (processedPageOutput.title) pageUpdate.title = processedPageOutput.title;
                // Store re-matched template if backend returned one (e.g. after outline regeneration)
                if (processedPageOutput.template) {
                  pageUpdate.template = processedPageOutput.template;
                  pageUpdate.layout = processedPageOutput.template;
                }
                // Sync outline from AI response (keeps outline fresh after edits)
                pageUpdate.outline = processedPageOutput.outline || restoredPageData.outline || originalPage.outline || originalPage.sectionTopic || originalPage.content_hint || '';
                // Bulk edit changed this page's layout — flag for re-critique.
                pageUpdate.critique_recommended = true;
                critiquedPagesRef.current.delete(originalPage.id);
                updatePAGE(originalPage.id, pageUpdate);
                successCount++;
              } catch (editErr) {
                console.error(`Error applying page ${event.page_index}:`, editErr);
              }
            } else if (event.type === 'complete') {
              const failCount = (totalMatched || PAGES.length) - successCount;
              if (failCount === 0) {
                Alert.alert('Update Complete', `Successfully updated all ${successCount} pages with latest data store content.`);
              } else {
                Alert.alert('Update Complete', `Updated ${successCount} pages. ${failCount} pages failed to update.`);
              }
            } else if (event.type === 'error') {
              if (event.status_code === 402) {
                authService.notifyCreditRequired(event.message);
              } else {
                console.error('Stream error:', event.message);
              }
            }
          } catch (parseErr) {
            console.warn('SSE parse error:', parseErr);
          }
        }
      }
    } catch (error) {
      console.error('Auto update error:', error);
      Alert.alert('Error', 'Failed to complete auto update. Please try again.');
    } finally {
      setIsAutoUpdating(false);
      setAutoUpdateProgress({ current: 0, total: 0 });
      releaseDocumentLock();
    }
  }, [isAutoUpdating, PAGES, useUploadedData, selectedFolders, apiConfig, userDeviceId, printableStyle, printableGoal, updatePAGE, currentPAGEId, generationQuality, extractImagesFromPAGE, restoreImagesToPAGE, releaseDocumentLock]);

  // Mini PAGE preview for thumbnail view
  const renderMiniPAGEPreview = (PAGE, previewWidth = 120) => {
    const previewHeight = (previewWidth * 9) / 16; // 16:9 aspect ratio
    const thumbnail = PAGEThumbnails[PAGE?.id];
    const miniScale = previewWidth / PAGE_WIDTH;

    // Helper to render layout blocks as fallback
    const renderLayoutBlocks = () => (
      <>
        {PAGE?.elements?.slice(0, 8).map((element, idx) => {
          const x = (element.x || 0) * miniScale;
          const y = (element.y || 0) * miniScale;
          const w = (element.width || 100) * miniScale;
          const h = (element.height || 50) * miniScale;

          if (element.type === 'text') {
            return (
              <View
                key={element.id || idx}
                style={{
                  position: 'absolute',
                  left: x,
                  top: y,
                  width: w,
                  height: Math.max(h, 4),
                  backgroundColor: element.fill || '#333',
                  borderRadius: 1,
                  opacity: 0.8,
                }}
              />
            );
          } else if (element.type === 'image' || element.type === 'image_placeholder') {
            return (
              <View
                key={element.id || idx}
                style={{
                  position: 'absolute',
                  left: x,
                  top: y,
                  width: w,
                  height: h,
                  backgroundColor: '#ddd',
                  borderRadius: 2,
                }}
              />
            );
          } else if (element.type === 'shape') {
            return (
              <View
                key={element.id || idx}
                style={{
                  position: 'absolute',
                  left: x,
                  top: y,
                  width: w,
                  height: h,
                  backgroundColor: element.fill || '#ccc',
                  borderRadius: element.rx ? element.rx * miniScale : 0,
                  opacity: element.opacity || 1,
                }}
              />
            );
          } else if (element.type === 'card') {
            return (
              <View
                key={element.id || idx}
                style={{
                  position: 'absolute',
                  left: x,
                  top: y,
                  width: w,
                  height: h,
                  backgroundColor: element.backgroundColor || '#f0f0f0',
                  borderRadius: 2,
                }}
              />
            );
          }
          return null;
        })}
      </>
    );

    return (
      <View
        style={{
          width: previewWidth,
          height: previewHeight,
          backgroundColor: PAGE?.backgroundColor || '#ffffff',
          borderRadius: 4,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Show cached thumbnail if available, otherwise show layout blocks */}
        {thumbnail ? (
          <Image
            source={{ uri: thumbnail }}
            style={{
              width: previewWidth,
              height: previewHeight,
              borderRadius: 4,
            }}
            resizeMode="cover"
          />
        ) : (
          renderLayoutBlocks()
        )}

        {/* PAGE number overlay */}
        <View style={{
          position: 'absolute',
          bottom: 2,
          right: 2,
          backgroundColor: 'rgba(0,0,0,0.6)',
          paddingHorizontal: 4,
          paddingVertical: 1,
          borderRadius: 2,
        }}>
          <Text style={{ color: '#fff', fontSize: 8, fontWeight: '600' }}>
            {PAGE?.order || 1}
          </Text>
        </View>
      </View>
    );
  };

  // Render PAGE thumbnail in sidebar
  const renderPAGEItem = (PAGE, index) => {
    const isActive = currentPAGEId === PAGE.id;
    const isEditing = editingPAGEId === PAGE.id;

    // Thumbnail View Mode
    if (PAGEPanelViewMode === 'thumbnail') {
      return (
        <View
          key={PAGE.id}
          style={[styles.PAGEItemContainer, PAGE.hidden && { opacity: 0.45 }]}
          onLayout={(e) => {
            const layout = e.nativeEvent.layout;
            sidebarLayoutsRef.current[PAGE.id] = { y: layout.y, height: layout.height };
          }}
        >
          <TouchableOpacity
            style={[
              styles.PAGEThumbnailItem,
              isActive && styles.PAGEThumbnailItemActive,
              {
                borderColor: isActive ? safeTheme.primary : safeTheme.borderColor || '#e0e0e0',
                backgroundColor: isActive ? safeTheme.primary + '10' : 'transparent',
              },
            ]}
            onPress={() => {
              if (actionBtnGuard.current) { actionBtnGuard.current = false; return; }
              skipSidebarScroll.current = true;
              handleSelectPAGE(PAGE.id);
              if (selectedElementIds.length > 0) {
                setSelectedElementIds([]);
              }
            }}
            activeOpacity={0.7}
          >
            {/* Mini PAGE Preview */}
            {renderMiniPAGEPreview(PAGE, sidebarWidth - 32)}

            {/* Title below thumbnail */}
            <View style={{ marginTop: 6, paddingHorizontal: 2 }}>
              {isEditing ? (
                <TextInput
                  style={[styles.PAGETitleInput, { color: safeTheme.text, fontSize: 10 }]}
                  value={editingPAGETitleText}
                  onChangeText={setEditingPAGETitleText}
                  onBlur={savePAGETitle}
                  onSubmitEditing={savePAGETitle}
                  autoFocus
                />
              ) : (
                <Text style={[styles.PAGEItemTitle, { color: safeTheme.text, fontSize: 10, textAlign: 'left', flexWrap: 'wrap' }]}>
                  {PAGE.title}
                </Text>
              )}
            </View>

            {/* Hover/Active Actions */}
            <View style={[styles.PAGEThumbnailActions, { opacity: isActive ? 1 : 0.7 }]}>
              <TouchableOpacity
                onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderPAGES(index, index - 1); }}
                disabled={index === 0}
                style={{ opacity: index === 0 ? 0.3 : 1, padding: 2 }}
              >
                <Ionicons name="chevron-up" size={10} color={safeTheme.text} />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderPAGES(index, index + 1); }}
                disabled={index === PAGES.length - 1}
                style={{ opacity: index === PAGES.length - 1 ? 0.3 : 1, padding: 2 }}
              >
                <Ionicons name="chevron-down" size={10} color={safeTheme.text} />
              </TouchableOpacity>
              {!isReadOnly && (
                <Tooltip text={PAGE.hidden ? "Show Page" : "Hide Page"} theme={safeTheme}>
                  <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); togglePAGEHidden(PAGE.id); }} style={{ padding: 2 }}>
                    <Ionicons name={PAGE.hidden ? "eye-off-outline" : "eye-outline"} size={10} color={safeTheme.textSecondary || '#888'} />
                  </TouchableOpacity>
                </Tooltip>
              )}
              <Tooltip text="Copy Page to Clipboard" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); copyPAGE(PAGE); }} style={{ padding: 2 }}>
                  <MaterialIcons name="content-paste" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Duplicate Page" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDuplicatePAGE(PAGE.id); }} style={{ padding: 2 }}>
                  <MaterialIcons name="content-copy" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Edit Page" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); setEditOutlinePAGE(PAGE); }} style={{ padding: 2 }}>
                  <MaterialIcons name="edit" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              {PAGES.length > 1 && (
                <Tooltip text="Delete PAGE" theme={safeTheme}>
                  <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDeletePAGE(PAGE.id); }} style={{ padding: 2 }}>
                    <MaterialIcons name="delete" size={10} color="#f44336" />
                  </TouchableOpacity>
                </Tooltip>
              )}
            </View>
          </TouchableOpacity>
        </View>
      );
    }

    // List View Mode (Original)
    return (
      <View
        key={PAGE.id}
        style={[styles.PAGEItemContainer, PAGE.hidden && { opacity: 0.45 }]}
        onLayout={(e) => {
          const layout = e.nativeEvent.layout;
          sidebarLayoutsRef.current[PAGE.id] = { y: layout.y, height: layout.height };
        }}
      >
        <TouchableOpacity
          style={[
            styles.PAGEItem,
            isActive && styles.PAGEItemActive,
            {
              borderColor: isActive ? '#BFDBFE' : 'transparent',
              backgroundColor: isActive ? '#EFF6FF' : 'transparent',
            },
          ]}
          onPress={() => {
            if (actionBtnGuard.current) { actionBtnGuard.current = false; return; }
            skipSidebarScroll.current = true;
            handleSelectPAGE(PAGE.id);
            if (selectedElementIds.length > 0) {
              setSelectedElementIds([]);
            }
          }}
          activeOpacity={0.7}
        >
          {/* Info & Actions Column */}
          <View style={{ flex: 1, flexDirection: 'column', gap: 4 }}>
            {/* PAGE info */}
            <View style={[styles.PAGEInfo, { flex: 0 }]}>
              {isEditing ? (
                <TextInput
                  style={[styles.PAGETitleInput, { color: safeTheme.text }]}
                  value={editingPAGETitleText}
                  onChangeText={setEditingPAGETitleText}
                  onBlur={savePAGETitle}
                  onSubmitEditing={savePAGETitle}
                  autoFocus
                />
              ) : (
                <Text style={[styles.PAGEItemTitle, { color: safeTheme.text, textAlign: 'left', flexWrap: 'wrap' }]}>
                  {PAGE.title}
                </Text>
              )}
            </View>

            {/* Actions */}
            <View style={styles.PAGEActions}>
              <View style={{ flexDirection: 'column', gap: 2, marginRight: 4 }}>
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderPAGES(index, index - 1); }}
                  disabled={index === 0}
                  style={{ opacity: index === 0 ? 0.3 : 1, padding: 2 }}
                >
                  <Ionicons name="chevron-up" size={12} color={safeTheme.text} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderPAGES(index, index + 1); }}
                  disabled={index === PAGES.length - 1}
                  style={{ opacity: index === PAGES.length - 1 ? 0.3 : 1, padding: 2 }}
                >
                  <Ionicons name="chevron-down" size={12} color={safeTheme.text} />
                </TouchableOpacity>
              </View>

              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); copyPAGE(PAGE); }} style={styles.PAGEActionBtn} title="Copy Page to Clipboard">
                <MaterialIcons name="content-paste" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDuplicatePAGE(PAGE.id); }} style={styles.PAGEActionBtn} title="Duplicate Page">
                <MaterialIcons name="content-copy" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              {!isReadOnly && (
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); togglePAGEHidden(PAGE.id); }} style={styles.PAGEActionBtn} title={PAGE.hidden ? "Show Page" : "Hide Page"}>
                  <Ionicons name={PAGE.hidden ? "eye-off-outline" : "eye-outline"} size={14} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              )}
              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); setEditOutlinePAGE(PAGE); }} style={styles.PAGEActionBtn}>
                <MaterialIcons name="edit" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              {PAGES.length > 1 && (
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDeletePAGE(PAGE.id); }}
                  style={[styles.PAGEActionBtn, styles.deleteBtn]}
                >
                  <MaterialIcons name="delete" size={14} color="#f44336" />
                </TouchableOpacity>
              )}
            </View>
          </View>
        </TouchableOpacity>
      </View>
    );
  };

  // Handle AI Style Generation
  const handleGenerateAIStyle = useCallback(async (stylePrompt) => {
    setIsGeneratingStyle(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log('🎨 [printable] Generating AI style...');

      const response = await fetch(`${apiConfig.API_URL}/printable/generate-style`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: stylePrompt,
        }),
      });

      const data = await response.json();

      if (response.status === 402 || handleCreditError(data)) {
        return;
      }

      if (data.success && data.style) {
        console.log('🎨 [printable] AI style generated:', data.style.name);
        console.log('🎨 [printable] AI style data:', JSON.stringify(data.style, null, 2));

        // Map AI response to internal style structure
        // AI returns: { name, fontFamily, textPrimary, textSecondary, accentColor, PAGEBackground, preview: { titleColor, bodyColor } }
        // Internal expects: { id, name, preview: { primary, secondary, accent }, PAGEBackground, textStyles: { title, subtitle, body } }

        const aiStyle = data.style;
        const newStyle = {
          id: `ai_style_${Date.now()}`,
          name: aiStyle.name || 'Custom AI Style',
          description: `AI generated style: ${stylePrompt}`,
          PAGEBackground: aiStyle.PAGEBackground || '#ffffff',
          fontFamily: aiStyle.fontFamily || 'Inter, system-ui, sans-serif',
          preview: {
            primary: aiStyle.textPrimary || '#000000',
            secondary: aiStyle.textSecondary || '#666666',
            accent: aiStyle.accentColor || '#3B82F6',
          },
          textStyles: {
            title: {
              fontFamily: aiStyle.fontFamily || 'Inter, system-ui, sans-serif',
              fontSize: 44,
              fontWeight: '700',
              color: aiStyle.preview?.titleColor || aiStyle.textPrimary || '#000000',
            },
            subtitle: {
              fontFamily: aiStyle.fontFamily || 'Inter, system-ui, sans-serif',
              fontSize: 28,
              fontWeight: '500',
              color: aiStyle.textSecondary || '#666666',
            },
            body: {
              fontFamily: aiStyle.fontFamily || 'Inter, system-ui, sans-serif',
              fontSize: 20,
              fontWeight: '400',
              color: aiStyle.preview?.bodyColor || aiStyle.textSecondary || '#333333',
            },
          },
          accentGradient: aiStyle.accentColor ? `linear-gradient(135deg, ${aiStyle.textPrimary} 0%, ${aiStyle.accentColor} 100%)` : 'none',
          headerStyle: 'solid',
          isCustom: true,
        };

        const updatedStyles = [...customStyles, newStyle];
        setCustomStyles(updatedStyles);
        setprintableStyle(newStyle);
        applyStyleToAllPAGES(newStyle);

        // Persist to storage
        try {
          await AsyncStorage.setItem('@custom_printable_styles', JSON.stringify(updatedStyles));
          console.log('✅ [printable] Custom styles saved to storage');
        } catch (error) {
          console.error('Failed to save custom styles:', error);
        }
      } else {
        throw new Error(data.message || 'Failed to generate style');
      }
    } catch (error) {
      console.error('Error generating style:', error);
      Alert.alert('Error', 'Failed to generate style. Please try again.');
    } finally {
      setIsGeneratingStyle(false);
    }
  }, [apiConfig, userDeviceId, applyStyleToAllPAGES]);


  const handleAddPAGEClick = (index) => {
    setInsertPAGEIndex(index);
    setShowLayoutPicker(true);
  };

  const handleLayoutSelected = async (templateId, outline = '', mode = 'manual', specialInstructions = '') => {
    setShowLayoutPicker(false);

    // CASE 1: Change Existing PAGE Layout
    if (targetPAGEIdForLayoutChange) {
      try {
        const newPAGEData = createPageFromTemplate(templateId, printableStyle);
        if (newPAGEData) {
          updatePAGE(targetPAGEIdForLayoutChange, {
            layout: templateId,
            elements: newPAGEData.elements,
            backgroundColor: newPAGEData.background || '#ffffff',
            // If outline is provided during layout change (unlikely but possible), save it
            ...(outline ? { outline } : {})
          });
        }
      } catch (error) {
        console.error("Failed to change layout:", error);
      }
      setTargetPAGEIdForLayoutChange(null);
      return;
    }

    // CASE 2: Add New PAGE
    const index = insertPAGEIndex !== null ? insertPAGEIndex : PAGES.length;
    const newPAGEId = `PAGE_${Date.now()}`;

    try {
      // Generate PAGE data from template
      const newPAGEData = createPageFromTemplate(templateId, printableStyle);
      const elements = newPAGEData ? newPAGEData.elements : [];
      const bgColor = newPAGEData ? newPAGEData.background : '#ffffff';

      // Create the new PAGE object
      const newPAGE = {
        id: newPAGEId,
        order: index + 1,
        title: 'New PAGE',
        layout: templateId,
        elements: elements,
        backgroundColor: bgColor,
        hasUnsavedChanges: true,
        outline: outline // Save the outline in metadata
      };

      // Add to state immediately
      // Using addPAGE helper might be cleaner but we need specific ID and properties
      // So let's manipulate state directly or use addPAGE if it supports it.
      // addPAGE(index, templateId, elements) uses generic ID. Let's stick to state injection for control.

      setPAGES(prevPAGES => {
        const newPAGES = [...prevPAGES];
        newPAGES.splice(index, 0, newPAGE);
        // Re-index orders
        return newPAGES.map((s, i) => ({ ...s, order: i + 1 }));
      });

      pageChangeFromInteraction.current = true;
      setCurrentPAGEId(newPAGEId);
      setInsertPAGEIndex(null);

      // Scroll to the new page after it renders
      setTimeout(() => {
        let scrolled = false;
        // On web, use scrollIntoView for reliable positioning
        if (Platform.OS === 'web') {
          const el = document.getElementById(`page-view-${newPAGEId}`);
          if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            scrolled = true;
          }
        }
        // Fallback: use stored layout position
        if (!scrolled) {
          const layout = pageLayoutsRef.current[newPAGEId];
          if (layout && contentScrollRef.current) {
            contentScrollRef.current.scrollTo({ y: layout.y - 16, animated: true });
            scrolled = true;
          }
        }
        if (scrolled) {
          scrollTrackingEnabled.current = false;
          setTimeout(() => { scrollTrackingEnabled.current = true; }, 500);
        }
      }, 400);

      // AI GENERATION MODE
      if (mode === 'ai') {
        // Trigger async generation
        generatePAGEFromOutline(newPAGE, outline, specialInstructions);
      }

    } catch (error) {
      console.error("Failed to create PAGE from template:", error);
      addPAGE(index); // Fallback
    }
  };

  // Helper handling AI Generation for a new PAGE
  const generatePAGEFromOutline = async (PAGE, outline, specialInstructions = '') => {
    if (!outline) {
      console.warn('⚠️ [AI] Cannot generate PAGE without outline');
      return;
    }

    setIsGeneratingPAGES(true);
    // Simplify progress to 0-1 for single PAGE
    setGenerationProgress({ current: 0, total: 1 });

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Error', 'Not authenticated for AI generation');
        return;
      }

      console.log(`🤖 [AI] Generating NEW PAGE from outline: "${outline}"`);

      // Get context from previous pages (up to 2 pages before)
      const currentIndex = PAGES.findIndex(s => s.id === PAGE.id);
      const prevPAGESContext = currentIndex > 0
        ? PAGES.slice(Math.max(0, currentIndex - 2), currentIndex).map(s => ({
          title: s.title || 'Untitled',
          content_summary: s.outline || s.title || ''
        }))
        : [];

      // Use the generate-PAGE API for NEW pages (not orchestrate)
      const response = await fetch(`${apiConfig.API_URL}/printable/generate-PAGE`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          PAGE_info: {
            title: outline,
            content_hint: specialInstructions || outline,
          },
          PAGE_index: currentIndex,
          total_PAGES: PAGES.length,
          printable_goal: printableGoal?.purpose || (typeof printableGoal === 'string' ? printableGoal : ''),
          printable_type: printableGoal?.documentType || 'general',
          style: printableStyle,
          template_id: (printableGoal?.deckProfile === 'general') ? null : PAGE.layout,
          folder_ids: selectedFolders?.map(f => f.id || f) || [],
          previous_PAGES: prevPAGESContext,
          images_remaining: 10, // Default allowance for images
          icon_set: printableStyle?.iconSet || 'default',
          special_instructions: specialInstructions || null,
          deck_profile: printableGoal?.deckProfile || 'corporate',
          deck_plan: printableGoal?.deckPlan || null,
        }),
      });

      const data = await response.json();

      if (response.status === 402 || handleCreditError(data)) {
        return;
      }

      if (data.success && data.PAGE) {
        console.log(`✅ [AI] New PAGE generated successfully`);

        // Process the PAGE (handle icons, etc.)
        let processedPAGEOutput = await processPAGEAsync(data.PAGE);

        // --- GENERATE IMAGES FOR PLACEHOLDERS ---
        // Check for image_placeholder elements and generate actual images
        const imagePlaceholders = (processedPAGEOutput.elements || []).filter(el => el.type === 'image_placeholder');
        if (imagePlaceholders.length > 0) {
          console.log(`🖼️ [NEW_PAGE] Found ${imagePlaceholders.length} image placeholder(s), generating...`);
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: printableStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: outline || 'Professional printable image', handleCreditError,
          });
        }
        // --- END IMAGE GENERATION ---

        // Update the PAGE
        const PAGEUpdate = {
          elements: processedPAGEOutput.elements,
          // Update title if AI generated one
          ...(processedPAGEOutput.title ? { title: processedPAGEOutput.title } : {}),
          // Update notes
          ...(processedPAGEOutput.notes ? { notes: processedPAGEOutput.notes } : {}),
          // Store the actual matched template from backend (resolves ai_auto to real template)
          ...(processedPAGEOutput.template ? { template: processedPAGEOutput.template, layout: processedPAGEOutput.template } : {}),
          // Freshly generated page — carry the backend's critique signal so the
          // post-render callback runs a vision critique on it.
          critique_recommended: data.critique_recommended !== false,
        };
        critiquedPagesRef.current.delete(PAGE.id);

        updatePAGE(PAGE.id, PAGEUpdate);
        console.log(`✅ [AI] PAGE generated successfully`);
        pendingLayoutFixRef.current.add(PAGE.id);
      } else {
        console.error(`❌ [AI] Generation failed:`, data.message);
        Alert.alert('Generation Failed', 'AI could not generate content. You have the blank layout.');
      }

    } catch (error) {
      console.error('AI Generation Error:', error);
      Alert.alert('Error', 'Failed to generate PAGE content.');
    } finally {
      setIsGeneratingPAGES(false);
      setGenerationProgress({ current: 0, total: 0 });
    }
  };

  const openLayoutPickerForPAGE = (PAGEId) => {
    setTargetPAGEIdForLayoutChange(PAGEId);
    setShowLayoutPicker(true);
  };





  if (!visible) return null;

  // Handle Enter-to-send on web, Shift+Enter for newline
  const handleKeyPress = (e) => {
    if (Platform.OS === 'web') {
      const key = e?.nativeEvent?.key;
      if (key === 'Enter') {
        const shift = e?.shiftKey || e?.nativeEvent?.shiftKey;
        if (!shift && chatInput.trim() && !isAiProcessing && !isAiLocked && currentPAGE) {
          e.preventDefault();
          e.stopPropagation();
          handleAgentEdit();
        }
      }
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="PAGE"
      onRequestClose={() => setShowCloseConfirmModal(true)}
      printableStyle="fullScreen"
      supportedOrientations={['portrait', 'landscape']}
    >
      <View style={[styles.container, { backgroundColor: safeTheme.background }]}>
        {/* Header Removed - moved to printableCanvas - Title now in Sidebar */}

        {/* Save Name Modal */}
        <Modal visible={showSaveModal} transparent animationType="fade" onRequestClose={() => setShowSaveModal(false)}>
          <View style={styles.topMiddleModalOverlay}>
            <View style={[styles.saveModal, { backgroundColor: safeTheme.background }]}>
              <Text style={[styles.saveModalTitle, { color: safeTheme.text }]}>Save Dashboard</Text>
              <Text style={[styles.saveModalLabel, { color: safeTheme.textSecondary }]}>Name</Text>
              <TextInput
                style={[styles.saveModalInput, { color: safeTheme.text, borderColor: safeTheme.border }]}
                value={printableTitle}
                onChangeText={setprintableTitle}
                autoFocus
              />
              <View style={styles.saveModalButtons}>
                <TouchableOpacity
                  style={[styles.saveModalBtn, styles.cancelBtn, { borderColor: safeTheme.border }]}
                  onPress={() => setShowSaveModal(false)}
                >
                  <Text style={[styles.saveModalBtnText, { color: safeTheme.text }]}>Cancel</Text>
                </TouchableOpacity>
                {currentPrintableId && (
                  <TouchableOpacity
                    disabled={isSavingManual}
                    style={[styles.saveModalBtn, { borderColor: safeTheme.primary, borderWidth: 1, backgroundColor: 'transparent', opacity: isSavingManual ? 0.5 : 1 }]}
                    onPress={() => {
                      setShowSaveModal(false);
                      handleSaveAsCopy();
                    }}
                  >
                    <Text style={[styles.saveModalBtnText, { color: safeTheme.primary }]}>Save a Copy</Text>
                  </TouchableOpacity>
                )}
                {!isReadOnly && (
                  <TouchableOpacity
                    style={[styles.saveModalBtn, styles.saveBtn, { backgroundColor: safeTheme.primary }]}
                    onPress={() => {
                      setShowSaveModal(false);
                      handleSave();
                    }}
                  >
                    <Text style={[styles.saveModalBtnText, { color: '#fff' }]}>Save</Text>
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
              <Text style={{ marginTop: 14, fontSize: 15, fontWeight: '600', color: safeTheme.text || '#1F2937' }}>Saving Dashboard…</Text>
            </View>
          </View>
        )}

        {/* Thumbnail Generation Overlay */}
        {isGeneratingThumbnails && (
          <View style={{ position: Platform.OS === 'web' ? 'fixed' : 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.35)', zIndex: 99999, justifyContent: 'center', alignItems: 'center' }}>
            <View style={{ backgroundColor: safeTheme.background || '#fff', borderRadius: 16, padding: 28, alignItems: 'center', shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 12, elevation: 8 }}>
              <ActivityIndicator size="large" color={safeTheme.primary || '#6366F1'} />
              <Text style={{ marginTop: 14, fontSize: 15, fontWeight: '600', color: safeTheme.text || '#1F2937' }}>Generating page previews…</Text>
            </View>
          </View>
        )}

        {/* Mobile View-Only Top Bar */}
        {mobileViewOnly && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: safeTheme.border, backgroundColor: '#ffffff' }}>
            <TouchableOpacity onPress={() => setShowCloseConfirmModal(true)} style={{ padding: 6 }}>
              <Ionicons name="close" size={22} color={safeTheme.text} />
            </TouchableOpacity>
            {/* Page Navigation */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 8 }}>
              <TouchableOpacity
                disabled={currentPAGEIndex <= 0}
                onPress={goToPrevPAGE}
                style={{ padding: 4, opacity: currentPAGEIndex <= 0 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-back" size={18} color={safeTheme.text} />
              </TouchableOpacity>
              <Text style={{ fontSize: 12, color: safeTheme.textSecondary }}>
                {currentPAGEIndex + 1}/{PAGES.length}
              </Text>
              <TouchableOpacity
                disabled={currentPAGEIndex >= PAGES.length - 1}
                onPress={goToNextPAGE}
                style={{ padding: 4, opacity: currentPAGEIndex >= PAGES.length - 1 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-forward" size={18} color={safeTheme.text} />
              </TouchableOpacity>
            </View>
            {/* Insert Page */}
            <TouchableOpacity
              onPress={() => handleAddPAGEClick(currentPAGEIndex + 1)}
              style={{ padding: 6, marginLeft: 4 }}
            >
              <Ionicons name="add-circle-outline" size={22} color={safeTheme.primary || '#6366F1'} />
            </TouchableOpacity>
            {/* Arrange Pages */}
            {PAGES.length > 1 && (
              <TouchableOpacity
                onPress={() => setShowArrangeModal(true)}
                style={{ padding: 6 }}
              >
                <Ionicons name="swap-horizontal-outline" size={20} color={safeTheme.text} />
              </TouchableOpacity>
            )}
            <View style={{ flexGrow: 1, flexShrink: 1 }} />
            {currentPrintableId && (
              <ShareButton
                contentType="printable"
                sourceId={currentPrintableId}
                title={printableTitle}
                theme={safeTheme}
                size="small"
                showLabel={false}
                apiConfig={apiConfig}
                authToken={authToken}
                userEmail={userEmail}
                userType={userType}
                onUpgrade={onOpenCredits}
              />
            )}
            {currentPrintableId && (
              <TouchableOpacity onPress={() => setShowAnalyticsModal(true)} style={{ padding: 6 }}>
                <Ionicons name="bar-chart-outline" size={20} color={safeTheme.text} />
              </TouchableOpacity>
            )}
            {PAGES.length > 0 && (
              <TouchableOpacity onPress={() => startPresentation()} style={{ padding: 6 }}>
                <Ionicons name="play-circle-outline" size={22} color={safeTheme.primary || '#6366F1'} />
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={() => setShowSaveModal(true)} style={{ padding: 6 }}>
              <Ionicons name="save-outline" size={20} color={safeTheme.primary || '#6366F1'} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowExportModal(true)} style={{ padding: 6 }}>
              <Ionicons name="download-outline" size={20} color={safeTheme.text} />
            </TouchableOpacity>
          </View>
        )}

        {/* Main content area - Full height now */}
        <View style={mobileViewOnly ? styles.mainContentMobile : styles.mainContent}>

          {/* Mobile Generation Overlay - Shows spinner when sidebar is hidden */}
          {mobileViewOnly && isGeneratingPAGES && (
            <View style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.45)',
              justifyContent: 'center',
              alignItems: 'center',
              zIndex: 999,
            }}>
              <View style={{
                backgroundColor: '#ffffff',
                borderRadius: 16,
                paddingVertical: 24,
                paddingHorizontal: 32,
                alignItems: 'center',
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.2,
                shadowRadius: 12,
                elevation: 10,
                minWidth: 200,
              }}>
                <ActivityIndicator size="large" color="#2563EB" />
                <Text style={{ fontSize: 15, fontWeight: '600', color: '#1E3A5F', marginTop: 14 }}>
                  Generating Pages...
                </Text>
                {generationProgress.total > 0 && (
                  <View style={{ alignItems: 'center', marginTop: 10 }}>
                    <Text style={{ fontSize: 13, color: '#1565C0', fontWeight: '600' }}>
                      {generationProgress.current}/{generationProgress.total}
                    </Text>
                    <View style={{ width: 120, height: 4, backgroundColor: '#BBDEFB', borderRadius: 2, marginTop: 6, overflow: 'hidden' }}>
                      <View style={{ height: '100%', backgroundColor: '#2196F3', borderRadius: 2, width: `${(generationProgress.current / generationProgress.total) * 100}%` }} />
                    </View>
                  </View>
                )}
              </View>
            </View>
          )}

          {/* Mobile Segmented Control - Toggle between Tools and AI Chat */}
          {mobileViewOnly && PAGES.length > 0 && (
            <View style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 12,
              paddingVertical: 6,
              backgroundColor: safeTheme.surface || '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.border || '#E5E7EB',
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
                    name="build-outline"
                    size={14}
                    color={mobileEditMode === 'tools' ? '#fff' : '#6B7280'}
                    style={{ marginRight: 5 }}
                  />
                  <Text style={{
                    fontSize: 13,
                    fontWeight: '600',
                    color: mobileEditMode === 'tools' ? '#fff' : '#6B7280',
                  }}>Tools</Text>
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
          {mobileViewOnly && mobileEditMode === 'chat' && PAGES.length > 0 && (
            <View style={{
              backgroundColor: '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.border || '#E5E7EB',
              paddingHorizontal: 12,
              paddingVertical: 10,
              maxHeight: 320,
            }}>
              {/* Selection chip — only when elements are selected; otherwise the
                  agent auto-detects targets from chat, so no banner. */}
              {editMode !== 'PAGE' && selectedElements.length > 0 && (
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  marginBottom: 8,
                  paddingHorizontal: 8,
                  paddingVertical: 6,
                  backgroundColor: editMode === 'multi' ? '#F3E8FF' : '#DCFCE7',
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: editMode === 'multi' ? '#D8B4FE' : '#86EFAC',
                }}>
                  <Ionicons
                    name={editMode === 'multi' ? 'copy-outline' : 'create-outline'}
                    size={14}
                    color={editMode === 'multi' ? '#7C3AED' : '#166534'}
                    style={{ marginRight: 6 }}
                  />
                  <Text style={{
                    fontSize: 11,
                    fontWeight: '600',
                    color: editMode === 'multi' ? '#7C3AED' : '#166534',
                    flex: 1,
                  }} numberOfLines={1}>
                    {`Selected: ${getElementTypeLabel(selectedElements)} — chat edits apply to it`}
                  </Text>
                </View>
              )}

              {/* AI Chat Messages — auto-scrolls to latest */}
              {aiChatMessages.length > 0 && (
                <ScrollView
                  ref={aiChatScrollMobileRef}
                  onContentSizeChange={() => aiChatScrollMobileRef.current?.scrollToEnd({ animated: true })}
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
                      <Text selectable style={{ fontSize: 11, color: msg.actionType === 'user' ? '#374151' : '#333', lineHeight: 15 }}>{msg.text}</Text>
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

              {/* Agentic editor hint — the AI sees the whole document and decides what to change */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name="sparkles" size={12} color="#7C3AED" />
                <Text style={{ fontSize: 11, color: safeTheme.placeholderText || '#6B7280', flex: 1 }} numberOfLines={1}>
                  AI edits the whole document — add/remove/reorder pages, restyle, header & footer, page numbers. Just ask.
                </Text>
              </View>

              {/* Pasted-screenshot thumbnails — staged for the next send */}
              {aiPastedImages.length > 0 && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 6 }}>
                  {aiPastedImages.map((img) => (
                    <View key={img.id} style={{ position: 'relative' }}>
                      <Image
                        source={{ uri: img.previewUri }}
                        style={{ width: 44, height: 44, borderRadius: 8, borderWidth: 1, borderColor: safeTheme.border || '#E2E8F0' }}
                        resizeMode="cover"
                      />
                      <TouchableOpacity
                        onPress={() => setAiPastedImages((prev) => prev.filter((p) => p.id !== img.id))}
                        style={{ position: 'absolute', top: -6, right: -6, backgroundColor: '#EF4444', borderRadius: 9, width: 18, height: 18, justifyContent: 'center', alignItems: 'center' }}
                      >
                        <Ionicons name="close" size={12} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  ))}
                </View>
              )}

              {/* Chat Input + Send */}
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
                <TextInput
                  style={{
                    flex: 1,
                    backgroundColor: isAiLocked ? '#F3F4F6' : (safeTheme.background || '#F9FAFB'),
                    color: isAiLocked ? '#9CA3AF' : (safeTheme.text || '#111827'),
                    borderWidth: 1,
                    borderColor: safeTheme.border || '#D1D5DB',
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 13,
                    maxHeight: 80,
                  }}
                  placeholder={isAiLocked ? "AI is locked..." : (editMode === 'PAGE' ? 'Ask anything — edit, add, reorder, review pages…' : `Edit ${getElementTypeLabel(selectedElements).toLowerCase()}...`)}
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
                    aiChatFocusedRef.current = true;
                    if (!isAiLocked) {
                      requestAiLock();
                    }
                  }}
                  onBlur={() => { aiChatFocusedRef.current = false; }}
                  onKeyPress={handleKeyPress}
                />
                <TouchableOpacity
                  style={{
                    backgroundColor: isAiProcessing ? '#EF4444' : (((chatInput.trim() || aiPastedImages.length > 0) && !isAiLocked) ? (safeTheme.primary || '#6366F1') : '#D1D5DB'),
                    borderRadius: 10,
                    paddingHorizontal: 14,
                    paddingVertical: 10,
                    justifyContent: 'center',
                    alignItems: 'center',
                  }}
                  onPress={() => isAiProcessing ? handleStopAgent() : handleAgentEdit()}
                  disabled={isAiProcessing ? false : ((!chatInput.trim() && aiPastedImages.length === 0) || isAiLocked)}
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

          {/* Sidebar - PAGE list */}
          {!mobileViewOnly && (
            <View style={[styles.sidebar, { width: sidebarWidth, backgroundColor: '#ffffff', borderRightColor: panelTheme.border }]}>

              {/* Title Area Above PAGE Nav */}
              <View style={{ marginBottom: 16, paddingHorizontal: 4 }}>
                <CollaborationLockIndicator
                  documentLock={documentLock}
                  ownClientId={collaboration.ydoc?.clientID}
                  type="printable"
                  style={{ marginBottom: 8 }}
                />
                <Text style={[styles.sidebarTitle, { color: panelTheme.text, fontSize: 16 }]} numberOfLines={1}>
                  {printableTitle}
                </Text>
                {vaultDisplayName && (
                  <Text style={{ fontSize: 11, color: panelTheme.text, opacity: 0.6, fontStyle: 'italic', marginBottom: 2 }}>
                    Data Store: {vaultDisplayName}
                  </Text>
                )}
                {lastSaved && (
                  <Text style={{ fontSize: 10, color: panelTheme.textSecondary }}>
                    {isSaving ? 'Saving...' : `Saved ${new Date(lastSaved).toLocaleTimeString()}`}
                  </Text>
                )}

                {currentPrintableId && (
                  <View style={{ marginTop: 8 }}>
                    <ShareButton
                      contentType="printable"
                      sourceId={currentPrintableId}
                      title={printableTitle}
                      theme={panelTheme}
                      size="small"
                      showLabel={true}
                      apiConfig={apiConfig}
                      authToken={authToken}
                      userEmail={userEmail}
                      userType={userType}
                      onUpgrade={onOpenCredits}
                    />
                  </View>
                )}
              </View>

              {/* TODO(cleanup): remove this hidden Update-All flow entirely (button + handleAutoUpdate + handleConfirmUpdate + UpdateInstructionModal usage) once the agentic chat path is proven in prod.
                  Auto Update Button — HIDDEN: redundant now that the chat agent
                  handles whole-document updates ("update all pages with the
                  latest data"). Flow (handleAutoUpdate + UpdateInstructionModal)
                  kept for potential re-enable. */}
              {false && (
              <TouchableOpacity
                style={[
                  {
                    marginBottom: 12,
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    backgroundColor: isAutoUpdating ? '#FCE4EC' : '#E91E63',
                    paddingHorizontal: 16,
                    paddingVertical: 10,
                    borderRadius: 8,
                    shadowColor: '#E91E63',
                    shadowOffset: { width: 0, height: 2 },
                    shadowOpacity: 0.3,
                    shadowRadius: 4,
                    elevation: 4,
                  }
                ]}
                onPress={handleAutoUpdate}
                disabled={isAutoUpdating || isGeneratingPAGES}
              >
                {isAutoUpdating ? (
                  <>
                    <ActivityIndicator size="small" color="#C2185B" />
                    <Text style={{ fontSize: 13, color: '#C2185B', fontWeight: '700' }}>
                      Updating {autoUpdateProgress.current}/{autoUpdateProgress.total}
                    </Text>
                    <View style={styles.progressBarContainer}>
                      <View
                        style={[
                          styles.progressBar,
                          { backgroundColor: '#E91E63', width: `${(autoUpdateProgress.current / autoUpdateProgress.total) * 100}%` }
                        ]}
                      />
                    </View>
                  </>
                ) : (
                  <>
                    <Ionicons name="refresh" size={16} color="#fff" />
                    <Text style={{ fontSize: 14, color: '#fff', fontWeight: '700', letterSpacing: 0.5 }}>
                      Refresh Data & Narration
                    </Text>
                  </>
                )}
              </TouchableOpacity>
              )}

              {/* Generation Progress Indicator */}
              {isGeneratingPAGES && generationProgress.total > 0 && (
                <View style={[styles.generationProgress, { marginBottom: 12 }]}>
                  <ActivityIndicator size="small" color="#1565C0" />
                  <Text style={styles.generationProgressText}>
                    {generationProgress.current}/{generationProgress.total}
                  </Text>
                  <View style={styles.progressBarContainer}>
                    <View
                      style={[
                        styles.progressBar,
                        { width: `${(generationProgress.current / generationProgress.total) * 100}%` }
                      ]}
                    />
                  </View>
                </View>
              )}

              <View style={[styles.sidebarHeader, { paddingTop: 0, flexDirection: 'column', gap: 8, alignItems: 'stretch' }]}>
                {/* 1. PAGE Navigation */}
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <TouchableOpacity
                    disabled={currentPAGEIndex <= 0}
                    onPress={goToPrevPAGE}
                    style={{ opacity: currentPAGEIndex <= 0 ? 0.3 : 1, padding: 4 }}
                  >
                    <Ionicons name="chevron-back" size={18} color={panelTheme.text} />
                  </TouchableOpacity>
                  <Text style={[styles.sidebarTitle, { color: panelTheme.text, fontSize: 13, marginBottom: 0 }]}>
                    Page {currentPAGEIndex + 1}/{PAGES.length}
                  </Text>
                  <TouchableOpacity
                    disabled={currentPAGEIndex >= PAGES.length - 1}
                    onPress={goToNextPAGE}
                    style={{ opacity: currentPAGEIndex >= PAGES.length - 1 ? 0.3 : 1, padding: 4 }}
                  >
                    <Ionicons name="chevron-forward" size={18} color={panelTheme.text} />
                  </TouchableOpacity>
                </View>

                {/* 2. View Toggle Button */}
                <Tooltip text={PAGEPanelViewMode === 'thumbnail' ? 'Switch to List View' : 'Switch to Thumbnail View'} theme={panelTheme}>
                  <TouchableOpacity
                    style={{
                      padding: 6,
                      backgroundColor: panelTheme.background,
                      borderRadius: 6,
                      borderWidth: 1,
                      borderColor: panelTheme.border || '#e0e0e0',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                    onPress={togglePAGEPanelView}
                  >
                    <Ionicons
                      name={PAGEPanelViewMode === 'thumbnail' ? 'list-outline' : 'grid-outline'}
                      size={16}
                      color={panelTheme.text}
                    />
                  </TouchableOpacity>
                </Tooltip>

                {/* 3. Add Page Button */}
                <TouchableOpacity
                  style={[styles.addPAGEBtn, {
                    backgroundColor: panelTheme.primary,
                    height: 32,
                    width: '100%',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }]}
                  onPress={() => handleAddPAGEClick(currentPAGEIndex + 1)}
                >
                  <Ionicons name="add" size={20} color="#fff" />
                </TouchableOpacity>
              </View>

              <ScrollView ref={sidebarScrollRef} style={styles.PAGEList} showsVerticalScrollIndicator={false}>
                {PAGES.map((PAGE, index) => renderPAGEItem(PAGE, index))}
              </ScrollView>
            </View>
          )}

          {/* Resizer Splitter (Left) */}
          {!mobileViewOnly && (
            <View
              style={styles.resizer}
              {...panResponder.panHandlers}
            >
              <View style={{ width: 1, height: '100%', backgroundColor: panelTheme.border, marginLeft: 2 }} />
            </View>
          )}

          {/* Canvas area with shared toolbar + vertical scroll for all A4 pages */}
          <View
            style={[styles.canvasContainer, mobileViewOnly && { flex: 1 }]}
            onLayout={(e) => {
              const { width, height } = e.nativeEvent.layout;
              if (width !== containerSize.width || height !== containerSize.height) {
                setContainerSize({ width, height });
              }
            }}
          >
            {/* Shared toolbar – always visible so users know they can edit */}
            <PrintableSharedToolbar
                theme={panelTheme}
                activeCanvasRef={activeCanvasRef}
                selectionInfo={selectionInfo}
                onOpenStylePicker={() => setShowStylePicker(true)}
                onOpenChartHelp={() => setShowChartStudio(true)}
                onOpenDiagram={handleOpenDiagram}
                onGenerateImage={handleGenerateImage}
                formatPainterActive={formatPainterActive}
                printableTitle={printableTitle}
                printableId={currentPrintableId}
                onSave={() => setShowSaveModal(true)}
                onExport={() => setShowExportModal(true)}
                onPresent={() => startPresentation()}
                onClose={() => setShowCloseConfirmModal(true)}
                onShowAnalytics={() => setShowAnalyticsModal(true)}
                onOpenFolder={() => setShowFolderDetailModal(true)}
                onShowCollaboration={() => setShowCollaborationPanel(true)}
                collaborationStatus={collaboration?.status}
                collaborators={collaboration?.collaborators}
                userType={userType}
                onUpgrade={onOpenCredits}
                onShowQualityModal={printableGoal ? () => setShowQualityModal(true) : undefined}
                qualityLabel={qualityLabel}
                qualityColor={qualityColor}
                pageBackgroundColor={currentPAGE?.backgroundColor || '#ffffff'}
                hasBackgroundImage={!!(currentPAGE?.elements?.some(el => el.imageType === 'background'))}
                backgroundImageOpacity={currentPAGE?.elements?.find(el => el.imageType === 'background')?.opacity ?? 0.3}
                onUpdatePAGEBackground={(color) => {
                  if (currentPAGE?.id) {
                    updatePAGEBackground(currentPAGE.id, { backgroundColor: color });
                  }
                }}
                onChangeBackgroundOpacity={(opacity) => {
                  if (currentPAGE?.id) {
                    updatePAGEBackground(currentPAGE.id, { backgroundOpacity: opacity });
                  }
                }}
                onRemoveBackgroundImage={() => {
                  if (currentPAGE?.id) {
                    updatePAGEBackground(currentPAGE.id, { removeBackgroundImage: true });
                  }
                }}
              />

            {/* Vertically scrollable area containing all pages */}
              <div className="printable-scroll-area" style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                <ScrollView
                  ref={contentScrollRef}
                  onScroll={handleContentScrollDebounced}
                  scrollEventThrottle={16}
                  style={{ flex: 1 }}
                  contentContainerStyle={{ paddingVertical: 24, alignItems: 'center' }}
                  showsVerticalScrollIndicator={true}
                >
              {PAGES.map((PAGE, index) => {
                const pageRef = getOrCreateCanvasRef(PAGE.id);
                const isActivePage = PAGE.id === currentPAGEId;
                return (
                  <View
                    key={PAGE.id}
                    nativeID={`page-view-${PAGE.id}`}
                    onLayout={(e) => {
                      const layout = e.nativeEvent.layout;
                      pageLayoutsRef.current[PAGE.id] = { y: layout.y, height: layout.height };
                    }}
                    style={{
                      marginBottom: 24,
                      alignItems: 'center',
                      borderLeftWidth: 4,
                      borderLeftColor: isActivePage ? panelTheme.primary : 'transparent',
                      borderRadius: 8,
                      backgroundColor: isActivePage ? (panelTheme.primary + '08') : 'transparent',
                      paddingLeft: 8,
                      paddingRight: 4,
                      paddingVertical: 8,
                    }}
                  >
                    {/* Page label */}
                    <Text style={{
                      fontSize: 11,
                      color: isActivePage ? panelTheme.primary : (panelTheme.textSecondary || '#888'),
                      marginBottom: 6,
                      fontWeight: isActivePage ? '600' : '400',
                    }}>
                      Page {index + 1} of {PAGES.length}
                    </Text>

                    {/* Content-sized wrapper: PrintableCanvas renders taller than the page
                        drawing (it includes its own info bar), so forcing the page height
                        here squeezes it and creates an inner scrollbar. The overlay is
                        anchored top-left with explicit canvas dims instead. */}
                    <View style={{ position: 'relative' }}>
                    <PrintableCanvas
                      ref={pageRef}
                      PAGE={PAGE}
                      isActivePage={isActivePage}
                      externalEditSessionId={agentTurnIdRef.current}
                      scale={canvasScale}
                      printableStyle={printableStyle}
                      iconSet={printableStyle?.iconSet}
                      awareness={collaboration?.awareness}
                      theme={panelTheme}
                      isEditable={true}
                      hideToolbar={true}
                      selectedElementId={isActivePage ? selectedElementId : null}
                      onSelectElement={handleSelectElement}
                      onUpdateElement={handleElementUpdate}
                      onUpdatePAGEBackground={(color) => {
                        if (PAGE.id) {
                          updatePAGEBackground(PAGE.id, { backgroundColor: color });
                        }
                      }}
                      onAddElement={handleAddElement}
                      onDeleteElement={handleDeleteElement}
                      onDeleteMultipleElements={handleDeleteMultipleElements}
                      onGenerateImage={handleGenerateImage}
                      onOpenStylePicker={() => setShowStylePicker(true)}
                      onOpenChartHelp={() => setShowChartStudio(true)}
                      onOpenDiagram={handleOpenDiagram}
                      onEditChart={handleEditChart}
                      onEditDiagram={handleRegenerateDiagram}
                      onCanvasFocus={() => {
                        // Discard selection on other canvases
                        canvasRefsMap.current.forEach((ref, id) => {
                          if (id !== PAGE.id && ref.current?.discardSelection) {
                            ref.current.discardSelection();
                          }
                        });
                        activeCanvasRef.current = pageRef.current;
                        canvasRef.current = pageRef.current;
                        if (PAGE.id !== currentPAGEId) {
                          pageChangeFromInteraction.current = true;
                          setCurrentPAGEId(PAGE.id);
                        }
                      }}
                      onElementSelectionChange={(info) => {
                        setSelectionInfo(info);
                        // Discard selection on other canvases when selecting on this one
                        if (info.hasSelection) {
                          canvasRefsMap.current.forEach((ref, id) => {
                            if (id !== PAGE.id && ref.current?.discardSelection) {
                              ref.current.discardSelection();
                            }
                          });
                        }
                        activeCanvasRef.current = pageRef.current;
                        canvasRef.current = pageRef.current;
                        if (PAGE.id !== currentPAGEId) {
                          pageChangeFromInteraction.current = true;
                          setCurrentPAGEId(PAGE.id);
                        }
                      }}
                      isGenerating={isGeneratingPAGES}
                      generationProgress={generationProgress}
                      onRenderComplete={handleCanvasRenderComplete}
                      onCopyElements={copyElements}
                      onPasteElements={(clipboardText) => {
                        const pastedData = parsePastedElements(clipboardText);
                        if (!pastedData || !pastedData.data) return;

                        if (pastedData.type === 'slide') {
                          // Paste as a new page after the current one
                          const insertIdx = currentPAGEIndex + 1;
                          const newPage = {
                            ...pastedData.data,
                            order: insertIdx + 1,
                          };
                          setPAGES(currentPAGES => {
                            const updated = [...currentPAGES];
                            updated.splice(insertIdx, 0, newPage);
                            return updated.map((p, i) => ({ ...p, order: i + 1 }));
                          });
                          setCurrentPAGEId(newPage.id);
                          return;
                        }

                        // Elements paste onto the current page
                        if (PAGE.id) {
                          const pageData = PAGES.find(s => s.id === PAGE.id);
                          if (pageData) {
                            const existingElements = pageData.elements || [];
                            const maxZ = existingElements.length > 0
                              ? Math.max(...existingElements.map(e => parseInt(e.zIndex) || 0)) + 1
                              : 1;
                            const newElements = pastedData.data.map((el, idx) => ({
                              ...el,
                              x: Math.min(el.x || 0, PAGE_WIDTH - 20),
                              y: Math.min(el.y || 0, PAGE_HEIGHT - 20),
                              zIndex: maxZ + idx,
                            }));
                            updatePAGE(PAGE.id, { elements: [...existingElements, ...newElements] });
                          }
                        }
                      }}
                      formatPainterActive={formatPainterActive}
                      formatPainterData={formatPainterData}
                      onFormatPainterApply={(targetElement) => {
                        if (formatPainterData && targetElement && canApplyFormat(formatPainterData, targetElement)) {
                          const applicableFormat = getApplicableFormat(formatPainterData, targetElement.type);
                          if (applicableFormat && PAGE.id) {
                            handleElementUpdate(PAGE.id, targetElement.id, applicableFormat);
                          }
                        }
                        setFormatPainterActive(false);
                        setFormatPainterData(null);
                      }}
                      onDeactivateFormatPainter={() => {
                        setFormatPainterActive(false);
                        setFormatPainterData(null);
                      }}
                      onActivateFormatPainter={(sourceElement) => {
                        if (sourceElement) {
                          copyFormat(sourceElement);
                          setFormatPainterActive(true);
                          setFormatPainterData(sourceElement);
                        }
                      }}
                      collaborationStatus={collaboration?.status}
                      collaborators={collaboration?.collaborators}
                      userType={userType}
                      onUpgrade={onOpenCredits}
                      generationQuality={generationQuality}
                      qualityLabel={qualityLabel}
                      qualityColor={qualityColor}
                      onShowQualityModal={printableGoal ? () => setShowQualityModal(true) : undefined}
                    />
                    <DeckChromeOverlay
                      width={PAGE_WIDTH * canvasScale}
                      height={PAGE_HEIGHT * canvasScale}
                      headerFooter={headerFooter}
                      slideNumbers={slideNumbers}
                      index={index}
                      total={PAGES.length}
                      noun="Page"
                    />
                    </View>
                  </View>
                );
              })}
            </ScrollView>
              </div>
          </View>

          {/* Resizer Splitter (Right) */}
          {!mobileViewOnly && (
            <View
              style={styles.resizer}
              {...rightPanResponder.panHandlers}
            >
              <View style={{ width: 1, height: '100%', backgroundColor: panelTheme.border, marginLeft: 2 }} />
            </View>
          )}

          {/* Right Sidebar - AI Assistant / Layer Panel */}
          {!mobileViewOnly && (
            <View
              testID="ai-sidebar"
              nativeID="ai-sidebar"
              style={[
                styles.sidebar,
                {
                  width: rightSidebarWidth,
                  backgroundColor: '#ffffff',
                  borderLeftWidth: 1,
                  borderLeftColor: panelTheme.border,
                  borderRightWidth: 0,
                  paddingBottom: 0,
                }
              ]}>
              {/* Tab Switcher */}
              <View style={[styles.tabSwitcher, { backgroundColor: '#F3F4F6', padding: 4 }]}>
                <TouchableOpacity
                  style={[
                    styles.tabBtn,
                    rightPanelTab === 'ai' && styles.tabBtnActive
                  ]}
                  onPress={() => setRightPanelTab('ai')}
                >
                  <Ionicons
                    name="sparkles"
                    size={14}
                    color={rightPanelTab === 'ai' ? '#2563EB' : '#6B7280'}
                  />
                  <Text style={[
                    styles.tabBtnText,
                    { color: rightPanelTab === 'ai' ? '#111827' : '#6B7280', fontWeight: rightPanelTab === 'ai' ? '600' : '500' }
                  ]}>AI Assistant</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.tabBtn,
                    rightPanelTab === 'layers' && styles.tabBtnActive
                  ]}
                  onPress={() => setRightPanelTab('layers')}
                >
                  <Ionicons
                    name="layers"
                    size={14}
                    color={rightPanelTab === 'layers' ? '#2563EB' : '#6B7280'}
                  />
                  <Text style={[
                    styles.tabBtnText,
                    { color: rightPanelTab === 'layers' ? '#111827' : '#6B7280', fontWeight: rightPanelTab === 'layers' ? '600' : '500' }
                  ]}>Layers</Text>
                </TouchableOpacity>
              </View>

              {/* Tab Content */}
              {rightPanelTab === 'ai' ? (
                /* AI Assistant Content */
                <View style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                  {/* Onboarding examples — only before the conversation starts; once
                      chatting, the chat history takes the full panel height. */}
                  {aiChatMessages.length === 0 && (
                  <ScrollView style={{ flex: 1, marginBottom: 10 }}>
                    <Text style={{ fontSize: 13, color: panelTheme.textSecondary, lineHeight: 20 }}>
                      I can see your whole document — edit, add, delete or reorder pages, restyle, review. Try:
                    </Text>
                    <View style={{ marginTop: 10, gap: 8 }}>
                      {[
                        '🔍 Review all pages and suggest improvements',
                        '✨ Make this page more professional',
                        '➕ Add a summary page at the end',
                        '🔢 Add page numbers and a footer',
                      ].map((example) => (
                        <TouchableOpacity
                          key={example}
                          onPress={() => !isAiProcessing && !isAiLocked && handleAgentEdit(example.replace(/^\S+\s/, ''))}
                          style={{ backgroundColor: panelTheme.background, padding: 8, borderRadius: 6, borderWidth: 1, borderColor: panelTheme.border }}
                        >
                          <Text style={{ fontSize: 12, color: panelTheme.text }}>{example}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </ScrollView>
                  )}

                  <View style={aiChatMessages.length > 0
                    ? { flex: 1, minHeight: 0, marginTop: 12, paddingBottom: 16 }
                    : { marginTop: 'auto', paddingBottom: 16 }}>
                    {/* Selection chip — only when elements are selected (media/element edits).
                        With nothing selected the agent auto-detects targets from chat, so no banner. */}
                    {editMode !== 'PAGE' && selectedElements.length > 0 && (
                      <View style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        marginBottom: 10,
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                        backgroundColor: editMode === 'multi' ? '#F3E8FF' : '#DCFCE7',
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: editMode === 'multi' ? '#D8B4FE' : '#86EFAC',
                      }}>
                        <Ionicons
                          name={editMode === 'multi' ? 'copy-outline' : 'create-outline'}
                          size={14}
                          color={editMode === 'multi' ? '#7C3AED' : '#166534'}
                          style={{ marginRight: 6 }}
                        />
                        <Text style={{ flex: 1, fontSize: 11, fontWeight: '600', color: editMode === 'multi' ? '#7C3AED' : '#166534' }} numberOfLines={1}>
                          {`Selected: ${getElementTypeLabel(selectedElements)} — chat edits apply to it`}
                        </Text>
                      </View>
                    )}

                    {/* User Media Badge - Show when single image/video selected that is user media */}
                    {editMode === 'element' && selectedElement &&
                      (selectedElement.type === 'image' || selectedElement.type === 'video') &&
                      selectedElement.isUserMedia && (
                        <View style={{
                          marginBottom: 12,
                          paddingHorizontal: 12,
                          paddingVertical: 10,
                          backgroundColor: '#EFF6FF',
                          borderRadius: 8,
                          borderWidth: 1,
                          borderColor: '#BFDBFE',
                        }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                            <Ionicons
                              name="shield-checkmark"
                              size={16}
                              color="#2563EB"
                              style={{ marginRight: 8 }}
                            />
                            <View style={{ flex: 1 }}>
                              <Text style={{
                                fontSize: 12,
                                fontWeight: '600',
                                color: '#1D4ED8',
                              }}>
                                User Media (Protected)
                              </Text>
                              <Text style={{
                                fontSize: 10,
                                color: '#3B82F6',
                                marginTop: 2,
                              }}>
                                AI will preserve this {selectedElement.type} unless you explicitly ask to replace it
                              </Text>
                            </View>
                          </View>
                        </View>
                      )}

                    {/* Multi-Select Elements Preview - Show when multiple elements are selected */}
                    {editMode === 'multi' && selectedElements.length > 0 && (
                      <View style={{
                        marginBottom: 12,
                        paddingHorizontal: 10,
                        paddingVertical: 8,
                        backgroundColor: '#FAF5FF',
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: '#E9D5FF',
                      }}>
                        <Text style={{
                          fontSize: 11,
                          fontWeight: '600',
                          color: '#7C3AED',
                          marginBottom: 6,
                        }}>
                          Selected Elements ({selectedElements.length}):
                        </Text>
                        <ScrollView
                          horizontal
                          showsHorizontalScrollIndicator={false}
                          style={{ marginHorizontal: -4 }}
                        >
                          {selectedElements.map((el, index) => (
                            <View
                              key={el.id || index}
                              style={{
                                flexDirection: 'row',
                                alignItems: 'center',
                                backgroundColor: el.isUserMedia ? '#EFF6FF' : '#FFFFFF',
                                paddingHorizontal: 8,
                                paddingVertical: 6,
                                borderRadius: 6,
                                marginRight: 6,
                                borderWidth: 1,
                                borderColor: el.isUserMedia ? '#BFDBFE' : '#DDD6FE',
                                maxWidth: 140,
                              }}
                            >
                              <Ionicons
                                name={
                                  el.type === 'text' ? 'text' :
                                    el.type === 'image' ? 'image' :
                                      el.type === 'video' ? 'videocam' :
                                        el.type === 'shape' ? 'shapes' :
                                          el.type === 'icon' ? 'apps' :
                                            el.type === 'card' ? 'card' :
                                              el.type === 'chart' ? 'bar-chart' :
                                                'cube-outline'
                                }
                                size={14}
                                color={el.isUserMedia ? '#2563EB' : '#8B5CF6'}
                                style={{ marginRight: 6 }}
                              />
                              <Text
                                style={{
                                  fontSize: 10,
                                  color: el.isUserMedia ? '#1D4ED8' : '#6D28D9',
                                  fontWeight: '500',
                                  flex: 1,
                                }}
                                numberOfLines={1}
                                ellipsizeMode="tail"
                              >
                                {el.isUserMedia
                                  ? `📷 ${el.type.charAt(0).toUpperCase() + el.type.slice(1)}`
                                  : (el.type === 'text' && el.text ?
                                    (el.text.length > 15 ? el.text.substring(0, 15) + '...' : el.text) :
                                    el.type.charAt(0).toUpperCase() + el.type.slice(1))
                                }
                              </Text>
                            </View>
                          ))}
                        </ScrollView>
                        <Text style={{
                          fontSize: 10,
                          color: '#9333EA',
                          marginTop: 6,
                          fontStyle: 'italic',
                        }}>
                          AI will edit all selected elements together
                        </Text>
                      </View>
                    )}

                    {/* AI Chat Messages Display — fills the panel, auto-scrolls to latest */}
                    {aiChatMessages.length > 0 && (
                      <ScrollView
                        ref={aiChatScrollRef}
                        onContentSizeChange={() => aiChatScrollRef.current?.scrollToEnd({ animated: true })}
                        style={{ flex: 1, minHeight: 0, marginBottom: 8 }}
                        showsVerticalScrollIndicator={true}
                      >
                        {aiChatMessages.map(msg => (
                          <View
                            key={msg.id}
                            style={{
                              backgroundColor: msg.actionType === 'user' ? '#F9FAFB' : (msg.actionType === 'create_new' ? '#E8F5E9' : '#E3F2FD'),
                              borderRadius: 8,
                              padding: 8,
                              marginBottom: 6,
                              alignSelf: msg.actionType === 'user' ? 'flex-end' : 'flex-start',
                              maxWidth: '85%',
                              borderLeftWidth: msg.actionType === 'user' ? 0 : 3,
                              borderLeftColor: msg.actionType === 'create_new' ? '#4CAF50' : '#2196F3',
                              borderRightWidth: msg.actionType === 'user' ? 3 : 0,
                              borderRightColor: '#D1D5DB',
                            }}
                          >
                            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 2 }}>
                              <Ionicons
                                name={msg.actionType === 'user' ? 'person-circle-outline' : (msg.actionType === 'create_new' ? 'add-circle' : 'sparkles')}
                                size={12}
                                color={msg.actionType === 'user' ? '#6B7280' : (msg.actionType === 'create_new' ? '#4CAF50' : '#2196F3')}
                              />
                              <Text style={{ fontSize: 10, color: msg.actionType === 'user' ? '#6B7280' : '#666', marginLeft: 4 }}>
                                {msg.actionType === 'user' ? 'You' : (msg.actionType === 'create_new' ? 'New Page Created' : 'AI')}
                              </Text>
                            </View>
                            <Text style={{ fontSize: 12, color: msg.actionType === 'user' ? '#374151' : '#333', lineHeight: 16 }}>{msg.text}</Text>
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

                    {/* Chat Input Container with Upload Button */}
                    <View style={{ gap: 8, marginBottom: 10 }}>
                      {/* Top Row: Attachment + Toggle */}
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Tooltip text="Attach File" theme={panelTheme}>
                          <TouchableOpacity
                            style={{
                              padding: 10,
                              backgroundColor: panelTheme.background,
                              borderRadius: 8,
                              borderWidth: 1,
                              borderColor: panelTheme.border,
                              justifyContent: 'center',
                              alignItems: 'center',
                              height: 36,
                              width: 36
                            }}
                            onPress={() => {
                              setShowInternalUploadModal(true);
                              if (onOpenTemplateUpload) {
                                // onOpenTemplateUpload();
                              }
                            }}
                          >
                            <Ionicons name="attach" size={18} color={panelTheme.textSecondary || '#666'} />
                          </TouchableOpacity>
                        </Tooltip>

                      </View>

                      {/* Pasted-screenshot thumbnails — staged for the next send */}
                      {aiPastedImages.length > 0 && (
                        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                          {aiPastedImages.map((img) => (
                            <View key={img.id} style={{ position: 'relative' }}>
                              <Image
                                source={{ uri: img.previewUri }}
                                style={{ width: 44, height: 44, borderRadius: 8, borderWidth: 1, borderColor: panelTheme.border || '#E2E8F0' }}
                                resizeMode="cover"
                              />
                              <TouchableOpacity
                                onPress={() => setAiPastedImages((prev) => prev.filter((p) => p.id !== img.id))}
                                style={{ position: 'absolute', top: -6, right: -6, backgroundColor: '#EF4444', borderRadius: 9, width: 18, height: 18, justifyContent: 'center', alignItems: 'center' }}
                              >
                                <Ionicons name="close" size={12} color="#fff" />
                              </TouchableOpacity>
                            </View>
                          ))}
                        </View>
                      )}

                      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>


                        <TextInput
                          style={[styles.aiChatInput, {
                            backgroundColor: isAiLocked ? '#F3F4F6' : panelTheme.background,
                            color: isAiLocked ? '#9CA3AF' : panelTheme.text,
                            borderColor: panelTheme.border,
                            flex: 1,
                            marginBottom: 0 // Remove bottom margin as container handles it
                          }]}
                          placeholder={isAiLocked ? "AI is currently locked..." : (editMode === 'PAGE' ? 'Ask anything — edit, add, reorder, review pages…' : `Edit ${getElementTypeLabel(selectedElements).toLowerCase()}...`)}
                          placeholderTextColor={panelTheme.textSecondary || '#888'}
                          value={chatInput}
                          onChangeText={(text) => {
                            setChatInput(text);
                            if (!isAiLocked && aiLockedBy) {
                              refreshAiLock?.();
                            }
                          }}
                          multiline
                          autoFocus={false}
                          editable={!isAiLocked}
                          onFocus={() => {
                            aiChatFocusedRef.current = true;
                            if (!isAiLocked) {
                              requestAiLock();
                            }
                          }}
                          onBlur={() => { aiChatFocusedRef.current = false; }}
                          onKeyPress={handleKeyPress}
                        />
                      </View>
                      <TouchableOpacity
                        style={[styles.aiChatBtn, { backgroundColor: isAiProcessing ? '#EF4444' : panelTheme.primary, opacity: isAiProcessing ? 1 : (((chatInput.trim() || aiPastedImages.length > 0) && !isAiLocked) ? 1 : 0.5) }]}
                        onPress={() => isAiProcessing ? handleStopAgent() : handleAgentEdit()}
                        disabled={isAiProcessing ? false : ((!chatInput.trim() && aiPastedImages.length === 0) || isAiLocked)}
                      >
                        {isAiProcessing ? (
                          <>
                            <Ionicons name="stop" size={16} color="#fff" />
                            <Text style={styles.aiChatBtnText}>Stop</Text>
                          </>
                        ) : (
                          <>
                            <Ionicons name="send" size={16} color="#fff" />
                            <Text style={styles.aiChatBtnText}>Enhance</Text>
                          </>
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              ) : (
                /* Layer Panel Content */
                <LayerPanel
                  slide={currentPAGE}
                  selectedElementId={selectedElementId}
                  onSelectElement={handleSelectElement}
                  onUpdateElement={handleElementUpdate}
                  onDeleteElement={handleDeleteElement}
                  theme={panelTheme}
                />
              )}
            </View>
          )}
        </View>

        {/* Goal Setting Modal */}
        {showGoalSetting && (
          <Modal
            visible={showGoalSetting}
            animationType="fade"
            transparent={true}
            onRequestClose={() => {
              userDismissedGoalModalRef.current = true;
              setShowGoalSetting(false);
            }}
          >
            <PrintableGoalInput
              visible={showGoalSetting}
              onClose={() => {
                userDismissedGoalModalRef.current = true;
                setShowGoalSetting(false);
              }}
              onPrintableGenerated={handlePrintableGenerated}
              onGoalSet={handleGoalSet}
              existingGoal={printableGoal}
              prefillGoal={prefillGoal}
              onUsePrefill={onUsePrefill}
              apiConfig={apiConfig}
              userDeviceId={userDeviceId}
              selectedFolders={selectedFolders}
              folders={folders}
              theme={safeTheme}
              persona={persona}
              uploadModalProps={uploadModalProps}
            />
          </Modal>
        )}

        {/* PAGE Layout Picker */}
        <SlideLayoutPicker
          visible={showLayoutPicker}
          onClose={() => setShowLayoutPicker(false)}
          onSelectLayout={handleLayoutSelected}
          theme={safeTheme}
          mobileViewOnly={mobileViewOnly}
        />

        {/* Printable Player */}
        <PrintablePlayer
          visible={isPlaying}
          onClose={() => setIsPlaying(false)}
          PAGES={visiblePAGES}
          initialPAGEId={currentPAGEId}
          theme={safeTheme}
          printableStyle={printableStyle}
        />

        <ChartStudio
          visible={showChartStudio}
          onClose={() => setShowChartStudio(false)}
          onInsertChart={(chartConfig, title) => {
            // Insert chart as interactive fabric.Chart object using canvas ref
            try {
              const activeCanvas = activeCanvasRef.current || canvasRef.current;
              if (currentPAGE?.id && activeCanvas?.addChart) {
                activeCanvas.addChart(chartConfig);
              } else {
                console.warn('addChart method not available on canvas ref');
                Alert.alert('Chart Error', 'Canvas is not ready. Please try again.');
              }
            } catch (err) {
              console.error('Insert chart error:', err);
            }
            setShowChartStudio(false);
          }}
          sourceContext="printable"
          pageContext={currentPAGE} // NEW: Pass current PAGE for AI context
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          apiConfig={apiConfig}
          theme={safeTheme}
        />

        {/* AI Image Modal */}
        <AIImageModal
          visible={showAIImageModal}
          onClose={() => setShowAIImageModal(false)}
          onInsertImage={(imageUrl, prompt) => {
            // Insert generated image
            if (currentPAGE?.id) {
              handleAddElement(currentPAGE.id, 'image', {
                src: imageUrl,
                x: 150,
                y: 100,
                width: 500,
                height: 500,
              });
            }
            setShowAIImageModal(false);
          }}
          currentPage={currentPAGE}
          userDeviceId={userDeviceId}
          selectedFolders={selectedFolders}
          apiConfig={apiConfig}
          theme={safeTheme}
        />

        {/* AI Diagram (SVG) Modal */}
        <AIDiagramModal
          visible={showAIDiagramModal}
          onClose={() => {
            setShowAIDiagramModal(false);
            setDiagramRegenContext(null);
          }}
          onInsertDiagram={(svg, prompt, diagramKind, title) => {
            if (!currentPAGE?.id) {
              setShowAIDiagramModal(false);
              setDiagramRegenContext(null);
              return;
            }
            if (diagramRegenContext?.elementId) {
              updateElement(currentPAGE.id, diagramRegenContext.elementId, {
                svgContent: svg,
                prompt,
                diagramKind,
                diagramTitle: title || '',
              });
            } else {
              handleAddElement(currentPAGE.id, 'svg_diagram', {
                svgContent: svg,
                svg,
                prompt,
                diagramKind,
                diagramTitle: title || '',
                x: 50,
                y: 100,
                width: 495,
                height: 280,
              });
            }
            setShowAIDiagramModal(false);
            setDiagramRegenContext(null);
          }}
          currentPage={currentPAGE}
          userDeviceId={userDeviceId}
          apiConfig={apiConfig}
          theme={safeTheme}
          initialPrompt={diagramRegenContext?.prompt || ''}
          initialKind={diagramRegenContext?.diagramKind || 'flowchart'}
          width={diagramRegenContext?.width || 920}
          height={diagramRegenContext?.height || 440}
          paletteHint={diagramRegenContext?.fillColor || safeTheme?.primary || ''}
          currentSvg={diagramRegenContext?.svgContent || ''}
        />

        {/* Chart Edit Modal - Opens on double-click */}
        <ChartEditModal
          visible={showChartEditModal}
          onClose={() => {
            setShowChartEditModal(false);
            setEditingChartElementId(null);
            setEditingChartConfig(null);
          }}
          chartConfig={editingChartConfig}
          onSave={handleSaveChartEdit}
          theme={safeTheme}
        />

        {/* Generation Quality Modal */}
        <Modal visible={showQualityModal} transparent animationType="fade" onRequestClose={() => setShowQualityModal(false)}>
          <TouchableOpacity style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'center', alignItems: 'center' }} activeOpacity={1} onPress={() => setShowQualityModal(false)}>
            <TouchableOpacity activeOpacity={1} style={{ backgroundColor: safeTheme.background, borderRadius: 16, padding: 20, width: 360, maxWidth: '90%' }} onPress={() => {}}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="sparkles" size={20} color={safeTheme.primary || '#6366F1'} />
                  <Text style={{ fontSize: 16, fontWeight: '700', color: safeTheme.text }}>Generation Type</Text>
                </View>
                <TouchableOpacity onPress={() => setShowQualityModal(false)}>
                  <Ionicons name="close" size={22} color={safeTheme.text} />
                </TouchableOpacity>
              </View>
              {[{ key: 'premium', label: 'Premium', price: '~$0.10 / page', icon: 'diamond', color: safeTheme.primary || '#6366F1', desc: 'Best image quality' },
                { key: 'medium', label: 'Medium', price: '~$0.05 / page', icon: 'flash', color: '#F59E0B', desc: 'Good quality, faster' },
                { key: 'basic', label: 'Basic', price: '~$0.02 / page', icon: 'leaf', color: '#9CA3AF', desc: 'Fast & economical' },
              ].map((opt) => (
                <TouchableOpacity
                  key={opt.key}
                  onPress={() => { setprintableGoal(prev => ({ ...prev, generationQuality: opt.key })); setShowQualityModal(false); }}
                  style={{
                    flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 10, marginBottom: 8,
                    borderWidth: 1.5,
                    borderColor: generationQuality === opt.key ? opt.color : (safeTheme.border || '#E5E7EB'),
                    backgroundColor: generationQuality === opt.key ? opt.color + '12' : (safeTheme.surface || '#F9FAFB'),
                  }}
                >
                  <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: opt.color + '20', justifyContent: 'center', alignItems: 'center', marginRight: 12 }}>
                    <Ionicons name={opt.icon} size={18} color={opt.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 14, fontWeight: '600', color: generationQuality === opt.key ? opt.color : safeTheme.text }}>{opt.label}</Text>
                    <Text style={{ fontSize: 11, color: safeTheme.textSecondary || '#6B7280', marginTop: 2 }}>{opt.desc}</Text>
                  </View>
                  <Text style={{ fontSize: 12, fontWeight: '600', color: opt.color }}>{opt.price}</Text>
                  {generationQuality === opt.key && <Ionicons name="checkmark-circle" size={20} color={opt.color} style={{ marginLeft: 8 }} />}
                </TouchableOpacity>
              ))}
            </TouchableOpacity>
          </TouchableOpacity>
        </Modal>

        {/* Style Picker Modal */}
        <Modal visible={showStylePicker} transparent animationType="fade" onRequestClose={() => setShowStylePicker(false)}>
          <View style={styles.rightSideModalOverlay}>
            <View style={[styles.stylePickerModal, styles.rightSideModal, { backgroundColor: safeTheme.background }]}>
              <View style={[styles.modalHeader, { borderBottomColor: safeTheme.border }]}>
                <Text style={[styles.modalTitle, { color: safeTheme.text }]}>Dashboard Style</Text>
                <TouchableOpacity onPress={() => setShowStylePicker(false)}>
                  <Ionicons name="close" size={24} color={safeTheme.text} />
                </TouchableOpacity>
              </View>
              <PrintableStylePicker
                theme={safeTheme}
                selectedStyle={printableStyle}
                onSelectStyle={handleStyleChange}
                onGenerateAIStyle={handleGenerateAIStyle}
                customStyles={customStyles}
                isGeneratingStyle={isGeneratingStyle}
                apiConfig={apiConfig}
              />
            </View>
          </View>
        </Modal>

        {/* Export Modal */}
        <PrintableExport
          visible={showExportModal}
          onClose={() => setShowExportModal(false)}
          PAGES={visiblePAGES}
          printableTitle={printableTitle}
          style={printableStyle}
          theme={safeTheme}
          userType={userType}
          onOpenCredits={onOpenCredits}
        />

        {/* Delete Confirmation Modal */}
        <Modal visible={showDeleteModal} transparent animationType="fade" onRequestClose={cancelDeletePAGE}>
          <View style={styles.modalOverlay}>
            <View style={[styles.deleteModal, { backgroundColor: safeTheme.background }]}>
              <Text style={[styles.deleteModalTitle, { color: safeTheme.text }]}>Delete PAGE?</Text>
              <Text style={[styles.deleteModalText, { color: safeTheme.textSecondary || '#666' }]}>
                This action cannot be undone.
              </Text>
              <View style={styles.deleteModalButtons}>
                <TouchableOpacity
                  style={[styles.deleteModalBtn, styles.cancelBtn, { borderColor: safeTheme.border }]}
                  onPress={cancelDeletePAGE}
                >
                  <Text style={[styles.deleteModalBtnText, { color: safeTheme.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.deleteModalBtn, styles.confirmDeleteBtn]}
                  onPress={confirmDeletePAGE}
                >
                  <Text style={[styles.deleteModalBtnText, { color: '#fff' }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Close Confirmation Modal */}
        <Modal visible={showCloseConfirmModal} transparent animationType="fade" onRequestClose={() => setShowCloseConfirmModal(false)}>
          <View style={styles.topMiddleModalOverlay}>
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

        {/* Printable Analytics Modal */}
        <PrintableAnalyticsModal
          visible={showAnalyticsModal}
          onClose={() => setShowAnalyticsModal(false)}
          printableId={currentPrintableId}
          printableTitle={printableTitle}
          theme={safeTheme}
          apiBaseUrl={API_CONFIG.CITRA_SERVICE_URL}
          getAuthHeaders={async () => {
            const token = await authService.getToken();
            return token ? { Authorization: `Bearer ${token}` } : {};
          }}
        />

        {/* Folder Detail Modal */}
        <FolderDetailModal
          visible={showFolderDetailModal}
          onClose={() => setShowFolderDetailModal(false)}
          folderId={selectedFolders?.[0]?.id}
          theme={safeTheme}
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
                {PAGES.map((page, index) => (
                  <View key={page.id} style={{ alignItems: 'center', width: 110 }}>
                    {/* Card */}
                    <TouchableOpacity
                      onPress={() => { setCurrentPAGEId(page.id); setShowArrangeModal(false); }}
                      style={{
                        width: 100, height: 70, borderRadius: 10, borderWidth: 2,
                        borderColor: page.id === currentPAGEId ? '#4F46E5' : '#E5E7EB',
                        backgroundColor: page.id === currentPAGEId ? '#EEF2FF' : '#F9FAFB',
                        justifyContent: 'center', alignItems: 'center', marginBottom: 6,
                      }}
                    >
                      <Text style={{ fontSize: 20, fontWeight: '700', color: page.id === currentPAGEId ? '#4F46E5' : '#6B7280' }}>{index + 1}</Text>
                    </TouchableOpacity>
                    {/* Title */}
                    <Text numberOfLines={1} style={{ fontSize: 10, color: '#374151', textAlign: 'center', marginBottom: 6, paddingHorizontal: 2 }}>
                      {page.title || `Page ${index + 1}`}
                    </Text>
                    {/* Reorder arrows */}
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <TouchableOpacity
                        disabled={index === 0}
                        onPress={() => { reorderPAGES(index, index - 1); }}
                        style={{ padding: 4, opacity: index === 0 ? 0.25 : 1 }}
                      >
                        <Ionicons name="arrow-back" size={16} color="#4F46E5" />
                      </TouchableOpacity>
                      <TouchableOpacity
                        disabled={index === PAGES.length - 1}
                        onPress={() => { reorderPAGES(index, index + 1); }}
                        style={{ padding: 4, opacity: index === PAGES.length - 1 ? 0.25 : 1 }}
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
          reportId={currentPrintableId}
          currentUser={collaboration?.ydoc?.clientID}
          theme={safeTheme}
          apiConfig={API_CONFIG}
          collaborators={collaboration?.collaborators}
        />

        {/* Edit Single Page Topic & Outline Modal */}
        <EditSlideOutlineModal
          visible={!!editOutlinePAGE}
          onClose={() => setEditOutlinePAGE(null)}
          onSave={handleSavePAGEOutline}
          theme={safeTheme}
          itemLabel="Page"
          initialTitle={editOutlinePAGE?.title || ''}
          initialOutline={editOutlinePAGE?.outline || editOutlinePAGE?.sectionTopic || editOutlinePAGE?.content_hint || ''}
        />

        {/* Update Instruction Modal */}
        <UpdateInstructionModal
          visible={showUpdateInstructionModal}
          onClose={() => setShowUpdateInstructionModal(false)}
          onConfirm={handleConfirmUpdate}
          isUpdating={isAutoUpdating}
          theme={safeTheme}
          title="Refresh Data & Narration"
          itemLabel="Page"
          currentGoal={printableGoal}
          currentOutline={currentOutlineData}
          onRefreshOutline={handleRefreshOutline}
          isRefreshingOutline={isRefreshingOutline}
        />
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  // Save Modal Styles
  saveModal: {
    width: 400,
    borderRadius: 12,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 10,
    elevation: 10,
  },
  saveModalTitle: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 4,
  },
  saveModalLabel: {
    fontSize: 13,
    marginBottom: 8,
  },
  saveModalInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    marginBottom: 20,
  },
  saveModalButtons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
  },
  saveModalBtn: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    minWidth: 80,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  saveModalBtnText: {
    fontSize: 14,
    fontWeight: '600',
  },
  container: {
    flex: 1,
  },
  // Header styles removed
  mainContent: {
    flex: 1,
    flexDirection: 'row',
  },
  mainContentMobile: {
    flex: 1,
    flexDirection: 'column',
  },
  sidebar: {
    borderRightWidth: 1,
    padding: 12,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden', // Prevent content from spilling out when resized
  },
  resizer: {
    width: 12, // Increased touch area
    backgroundColor: 'transparent',
    cursor: 'col-resize',
    zIndex: 100, // Ensure it's above other elements
    marginLeft: -6, // Centered overlap
  },
  sidebarHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sidebarTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  addPAGEBtn: {
    padding: 6,
    borderRadius: 6,
  },
  PAGEList: {
    flex: 1,
  },
  PAGEItemContainer: {
    marginBottom: 8,
  },
  PAGEItem: {
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent', // Default transparent
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 4,
  },
  PAGEItemActive: {
    borderLeftColor: '#2563EB', // Active Highlight
  },
  // Thumbnail view styles
  PAGEThumbnailItem: {
    borderRadius: 8,
    borderWidth: 2,
    padding: 8,
    marginBottom: 4,
    alignItems: 'center',
  },
  PAGEThumbnailItemActive: {
    borderWidth: 2,
  },
  PAGEThumbnailActions: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  // Legacy thumbnail (small icon in list view)
  PAGEThumbnail: {
    width: 64,
    height: 36,
    borderRadius: 4,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  PAGENumberOverlay: {
    fontSize: 12,
    fontWeight: '600',
    color: '#666',
  },
  PAGEInfo: {
    flex: 1,
    minWidth: 0, // Allow flex items to shrink below content size
  },
  PAGEItemTitle: {
    fontSize: 12,
    fontWeight: '500',
  },
  PAGETitleInput: {
    fontSize: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2196F3',
    paddingVertical: 2,
  },
  PAGEActions: {
    flexDirection: 'row',
    gap: 2,
  },
  PAGEActionBtn: {
    padding: 4,
  },
  deleteBtn: {},
  sidebarFooter: {
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
  },
  sidebarBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
  },
  sidebarBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  canvasContainer: {
    flex: 1,
    position: 'relative',
    padding: 0, // Removed padding for full-bleed
    justifyContent: 'flex-start', // Align to top for vertical scrolling
    alignItems: 'center',
    // overflow: 'hidden' removed to allow vertical scrolling of A4 pages
    backgroundColor: '#F0F0F0', // Light gray background for page contrast
  },
  canvasScrollView: {
    flex: 1,
    width: '100%',
  },
  canvasScrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    paddingVertical: 20,
    paddingHorizontal: 20,
  },
  PAGENavigation: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
    gap: 20,
  },
  navBtn: {
    padding: 8,
  },
  PAGECounter: {
    fontSize: 14,
    fontWeight: '500',
  },
  // Removed aiChatToggle and aiChatPanel styles as they are replaced by the right sidebar
  aiChatTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
  },
  aiChatInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    fontSize: 14,
    minHeight: 60,
    marginBottom: 10,
  },
  aiChatBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 10,
    borderRadius: 8,
    gap: 6,
  },
  aiChatBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
  },
  // Tab switcher styles for AI/Layers panel
  tabSwitcher: {
    flexDirection: 'row',
    marginBottom: 16,
    borderRadius: 8,
    backgroundColor: '#F3F4F6', // Grey-100 background for container
  },
  tabBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    gap: 8,
  },
  tabBtnActive: {
    backgroundColor: '#FFFFFF', // White background for active
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  tabBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
  },
  rightSideModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    justifyContent: 'flex-start',
    alignItems: 'flex-end',
    paddingTop: 70,
    paddingBottom: 20,
    paddingRight: 20,
  },
  topMiddleModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-start',
    alignItems: 'center',
    paddingTop: 50,
  },
  stylePickerModal: {
    width: '100%',
    maxWidth: 600,
    maxHeight: '80%',
    borderRadius: 16,
    overflow: 'hidden',
  },
  rightSideModal: {
    width: 350,
    maxWidth: '100%',
    height: '100%',
    maxHeight: '100%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  deleteModal: {
    width: '100%',
    maxWidth: 350,
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
  },
  deleteModalTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  deleteModalText: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 20,
  },
  deleteModalButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  deleteModalBtn: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    minWidth: 100,
    alignItems: 'center',
  },
  cancelBtn: {
    borderWidth: 1,
  },
  confirmDeleteBtn: {
    backgroundColor: '#f44336',
  },
  deleteModalBtnText: {
    fontSize: 14,
    fontWeight: '500',
  },
  // Generation progress indicator styles
  generationProgress: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E3F2FD',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginHorizontal: 8,
    gap: 8,
  },
  generationProgressText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1565C0',
    lineHeight: 14,
    includeFontPadding: false,
    marginTop: 1, // Optical center alignment
  },
  progressBarContainer: {
    flex: 1,
    minWidth: 20,
    maxWidth: 100,
    height: 4,
    backgroundColor: '#BBDEFB',
    borderRadius: 2,
    overflow: 'hidden',
    transform: [{ translateY: -0.5 }], // Optical center alignment
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#2196F3',
    borderRadius: 2,
  },
});

export default PrintableComposer;
