// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// PresentationComposer.js - AI Presentation Generator with Canvas Editor
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
import PresentationGoalInput from './PresentationGoalInput';
import PresentationCanvas, { SLIDE_WIDTH, SLIDE_HEIGHT } from './PresentationCanvas';
import PresentationStylePicker, { PRESET_STYLES } from './PresentationStylePicker';
import PresentationExport from './PresentationExport';
import PresentationPlayer from './PresentationPlayer';
import ChartStudio from './ChartStudio';
import ChartEditModal from './ChartEditModal'; // Import Chart Edit Modal for inline editing
import AIImageModal from './AIImageModal'; // Import AI Image Modal
import AIDiagramModal from './AIDiagramModal'; // Import AI Diagram (SVG) Modal
import { ShareButton } from '../ShareManager';
import { usePresentationSlides } from './hooks/usePresentationSlides';
import { useCollaboration } from './hooks/useCollaboration';
import CollaborationLockIndicator from './CollaborationLockIndicator'; // Imported
import CollaborationPanel from './CollaborationPanel'; // Imported for collaboration features
import UpdateInstructionModal from './UpdateInstructionModal'; // Imported
import EditSlideOutlineModal from './EditSlideOutlineModal'; // Edit single slide topic/outline
import { usePresentationPersistence } from './hooks/usePresentationPersistence';
import { processSlide, processSlideAsync } from './utils/slidePostProcessor';
import { mapIconToPathAsync } from './utils/iconMapper';
import { navigateToPresentation } from '../../utils/urlRouter';
import ImageGenService from '../../services/ImageGenService';
import globalImageCache from '../../utils/globalImageCache';
import { generateImagesParallel } from '../../services/imageGenerationUtils';
import { prefetchIcons } from './utils/iconMapper';
import UnifiedUploadModal from '../UnifiedUploadModal'; // Unified upload modal
import UploadProgressPopup from '../UploadProgressPopup'; // Upload progress popup for visibility inside modal
import { buildSlidesSummary } from '../../utils/slideTextExtractor';
import DeckChromeOverlay from './DeckChromeOverlay';
import LayerPanel from './LayerPanel';
import Tooltip from '../ui/Tooltip'; // Import Tooltip
import authService from '../../services/authService';
import { API_CONFIG } from '../../config/config';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import SlideLayoutPicker from './SlideLayoutPicker';
import { createSlideFromTemplate } from './utils/slideTemplates';
import { useClipboard } from './hooks/useClipboard';
import PresentationAnalyticsModal from './PresentationAnalyticsModal';
import FolderDetailModal from '../FolderDetailModal';
import PresentationSharedToolbar from './PresentationSharedToolbar';
import { showDesktopEditingAlert } from '../../utils/mobileEditAlert';
import useImagePaste from '../../hooks/useImagePaste';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Module-level counter for unique chat message IDs (prevents duplicate React keys when Date.now() collides)
let _chatMsgId = 0;
const chatMsgUid = () => `msg_${Date.now()}_${++_chatMsgId}`;

// Deck-level header/footer + slide-number defaults. These are agentic-editable
// (the chat AI can flip them on, set text, change position/format) and are
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

  // Check various possible error formats
  // Note: Backend returns { error: "insufficient_credits", ... } so we need to check data.error directly
  const errorType = data.error || data.error_type || data.detail?.error || '';
  const errorMessage = data.message || data.detail?.message || data.detail || '';
  const errorStr = typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage || '');

  // Check for explicit insufficient_credits error type
  if (errorType === 'insufficient_credits') {
    console.log('💰 [CREDITS] Detected insufficient_credits error type');
    return true;
  }

  // Check for error message patterns
  if (errorStr) {
    const lowerMessage = errorStr.toLowerCase();
    if (lowerMessage.includes('insufficient credits') || lowerMessage.includes('insufficient_credits') ||
      lowerMessage.includes('negative balance') ||
      lowerMessage.includes('purchase credits')) {
      console.log('💰 [CREDITS] Detected credit error in message:', errorStr);
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
 * PresentationComposer - AI Presentation Generator
 * 
 * Features:
 * - Goal-based slide outline generation
 * - Per-slide AI content generation
 * - Canvas-based visual editing
 * - Style selection (presets + AI-generated)
 * - Export to PPTX, PDF, PNG
 */
// Helper to extract base64 images and replace with placeholders
const extractImagesFromSlide = (slide, selectedElementIds = []) => {
  if (!slide || !slide.elements) return { processedSlide: slide, imageMap: {}, chartMap: {} };

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
  const processedElements = slide.elements.map(element => {
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
        imageDescription: element.imageDescription || 'professional image matching slide context',
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
    processedSlide: { ...slide, elements: processedElements },
    imageMap,
    chartMap
  };
};

const restoreImagesToSlide = (slide, imageMap) => {
  if (!slide || !slide.elements) return slide;

  // Helper: apply saved geometry — only fill in props the AI zeroed/dropped
  const applyGeometry = (el, geo) => {
    if (!geo) return el;
    const patched = { ...el };
    for (const key of Object.keys(geo)) {
      if (patched[key] === undefined || ((key === 'width' || key === 'height') && !patched[key])) {
        patched[key] = geo[key];
      }
    }
    return patched;
  };

  const restoredElements = slide.elements.map(element => {
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
        }
        // Description changed by AI → leave as image_placeholder for regeneration
      }
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
      return { ...element, type: 'image_placeholder', imageDescription: element.imageDescription || 'professional image' };
    }

    // USER MEDIA + VIDEOS/DIAGRAMS: Restore {{UserMedia_xxx}} placeholders
    const isMediaWithPlaceholder = (element.type === 'image' || element.type === 'video' || element.type === 'diagram')
      && element.src && typeof element.src === 'string' && element.src.startsWith('{{');
    if (isMediaWithPlaceholder) {
      const match = element.src.match(/^{{((?:UserMedia|UserImage)_[^}]+)}}$/);
      if (match && match[1] && imageMap[match[1]]) {
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

  return { ...slide, elements: restoredElements };
};

const PresentationComposer = ({
  visible,
  onClose,
  onClearPresentation,
  theme,
  userDeviceId,
  apiConfig,
  persona,
  personaText,
  initialPresentation = null,
  prefillGoal = null,        // {goal, slide_count, prefetched_corpus} from a chat open_builder handoff
  onUsePrefill = null,       // called once the prefill has been consumed
  selectedFolders = [],
  folders = [],
  onOpenTemplateUpload, // Legacy callback - now using internal modal
  // Upload modal props - rendered inside fullScreen portal to appear on top
  uploadModalProps = null,
  enhancedProgress = null, // Upload progress for popup visibility inside modals
  onDismissUploadEntry = null, // Callback to remove a single upload entry from progress map
  mobileViewOnly = false, // Mobile web: generation works, editing disabled
  userType = 'free', // User plan type for export branding
  onOpenCredits = () => { }, // Callback to open credits/upgrade modal
}) => {
  const { useUploadedData } = useWorkspace();

  // State Declarations (Moved up to fix ReferenceError)
  const [showGoalSetting, setShowGoalSetting] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showPresentationList, setShowPresentationList] = useState(false);
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [currentPresentationId, setCurrentPresentationId] = useState(null);
  const [isLoadingPresentation, setIsLoadingPresentation] = useState(false);
  const [presentationGoal, setPresentationGoal] = useState(null);
  const [presentationStyle, setPresentationStyle] = useState(PRESET_STYLES[0]);
  // Deck-level header/footer + slide-number settings (agentic-editable via chat,
  // persisted inside the saved style object). See DEFAULT_HEADER_FOOTER / DEFAULT_SLIDE_NUMBERS.
  const [headerFooter, setHeaderFooter] = useState(DEFAULT_HEADER_FOOTER);
  const [slideNumbers, setSlideNumbers] = useState(DEFAULT_SLIDE_NUMBERS);
  const [presentationTitle, setPresentationTitle] = useState('Untitled Presentation');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [selectedElementIds, setSelectedElementIds] = useState([]); // Array for multi-select
  const [isGeneratingStyle, setIsGeneratingStyle] = useState(false);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);
  const [insertSlideIndex, setInsertSlideIndex] = useState(null);
  const [showArrangeModal, setShowArrangeModal] = useState(false);
  const [targetSlideIdForLayoutChange, setTargetSlideIdForLayoutChange] = useState(null);
  const [showAnalyticsModal, setShowAnalyticsModal] = useState(false); // Analytics modal state
  const [showFolderDetailModal, setShowFolderDetailModal] = useState(false); // Folder detail popup state
  const [showCollaborationPanel, setShowCollaborationPanel] = useState(false); // Collaboration panel state
  const [showQualityModal, setShowQualityModal] = useState(false);
  const [authToken, setAuthToken] = useState(null);
  const [userEmail, setUserEmail] = useState(null);
  const [isRefreshingOutline, setIsRefreshingOutline] = useState(false);

  // Derive generationQuality from the goal set by GoalInput
  const generationQuality = presentationGoal?.generationQuality || 'premium';
  const qualityLabel = generationQuality === 'premium' ? 'Premium' : generationQuality === 'medium' ? 'Medium' : 'Basic';
  const qualityColor = generationQuality === 'premium' ? '#6366F1' : generationQuality === 'medium' ? '#F59E0B' : '#9CA3AF';

  // Collaborative Setup
  // We use currentPresentationId or initialPresentation.id
  // Collaboration is only enabled when:
  // 1. Document has an ID (saved)
  // 2. Document is shared for collaboration (not just public URL share)
  // 3. User has write permission (owner or write collaborator)
  const collabDocId = currentPresentationId || initialPresentation?.id;

  // Determine collaboration mode from sharing metadata
  const sharingInfo = initialPresentation?.sharing;
  const isOwner = sharingInfo?.is_owner ?? true; // Default to owner for unsaved/new docs
  const isSharedForCollaboration = sharingInfo?.is_shared_for_collaboration ?? false;
  const userPermission = sharingInfo?.user_permission; // 'owner' | 'write' | 'read' | null

  // Check if current user owns this item (for hiding share controls on shared items)
  const isItemOwner = initialPresentation?.user_id != null ? initialPresentation.user_id === userDeviceId : isOwner;

  // Only enable collaboration if:
  // - Document is shared for collaboration AND
  // - User has write permission (owner or write collaborator)
  const canCollaborate = isSharedForCollaboration &&
    (userPermission === 'owner' || userPermission === 'write');

  // Read-only mode: user has read access but cannot edit
  const isReadOnly = !isOwner && userPermission === 'read';

  const collaboration = useCollaboration({
    docId: collabDocId,
    enabled: !!collabDocId && canCollaborate, // Gate collaboration properly
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
    slideLocks,
    requestDocumentLock,
    releaseDocumentLock,
    requestSlideLock,
    releaseSlideLock,
    isSlideLocked,
    releaseAllLocks
  } = collaboration;

  // Check if AI is locked by someone else (legacy)
  const isAiLocked = canCollaborate && aiLockedBy && collaboration.ydoc && aiLockedBy.clientId !== collaboration.ydoc.clientID;
  const lockedByUser = aiLockedBy ? aiLockedBy.user : null;

  // Check if document is locked (for Update button)
  const isDocumentLocked = canCollaborate && documentLock && collaboration.ydoc && documentLock.clientId !== collaboration.ydoc.clientID;
  const documentLockedBy = documentLock ? documentLock.user : null;


  // Slide management hooks
  const {
    slides,
    setSlides,
    currentSlideId,
    setCurrentSlideId,
    addSlide,
    deleteSlide,
    insertSlide,
    reorderSlides,
    updateSlide,
    updateSlideTitle,
    updateSlideBackground, // For background color changes
    addElement,
    updateElement,
    updateMultipleElements,
    deleteElement,
    deleteMultipleElements,
    getSlideById,
    applyStyleToAllSlides,
    toggleSlideHidden,
  } = usePresentationSlides(initialPresentation, collaboration);

  const {
    savePresentation,
    savePresentationToServer,
    loadPresentation,
    isSaving,
    lastSaved,
  } = usePresentationPersistence();

  // Clipboard hook for copy/paste/format painter
  const {
    copyElements,
    copySlide,
    copyFormat,
    parsePastedElements,
    canApplyFormat,
    getApplicableFormat,
  } = useClipboard();

  // Format Painter state
  const [formatPainterActive, setFormatPainterActive] = useState(false);
  const [formatPainterData, setFormatPainterData] = useState(null);

  // Get current slide (Moved up to fix initialization error)
  const currentSlide = useMemo(() => {
    return slides.find(s => s.id === currentSlideId) || slides[0];
  }, [slides, currentSlideId]);

  const currentSlideIndex = useMemo(() => {
    return slides.findIndex(s => s.id === currentSlideId);
  }, [slides, currentSlideId]);

  // Visible slides (excludes hidden) — used for Present, Export
  const visibleSlides = useMemo(() => slides.filter(s => !s.hidden), [slides]);

  // State


  // Upload modal state - rendered inside fullScreen portal to appear on top
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);

  // Slide panel view mode: 'thumbnail' or 'list'
  const [slidePanelViewMode, setSlidePanelViewMode] = useState('thumbnail');

  // Load slide panel view preference from AsyncStorage
  useEffect(() => {
    const loadViewPreference = async () => {
      try {
        const savedMode = await AsyncStorage.getItem('@slide_panel_view_mode');
        if (savedMode && (savedMode === 'thumbnail' || savedMode === 'list')) {
          setSlidePanelViewMode(savedMode);
        }
      } catch (err) {
        console.log('[COMPOSER] Failed to load view preference:', err);
      }
    };
    loadViewPreference();
  }, []);

  // Save slide panel view preference
  const toggleSlidePanelView = useCallback(async () => {
    const newMode = slidePanelViewMode === 'thumbnail' ? 'list' : 'thumbnail';
    setSlidePanelViewMode(newMode);
    try {
      await AsyncStorage.setItem('@slide_panel_view_mode', newMode);
    } catch (err) {
      console.log('[COMPOSER] Failed to save view preference:', err);
    }
  }, [slidePanelViewMode]);

  // Canvas scaling state
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  // FIX: Start at 0 — don't render canvas at scale=1 before container is measured.
  // On mobile, scale=1 creates a full 960x540 canvas; async image loads capture stale
  // positions (scaledX = x*1) that persist after the real scale (~0.42) is applied.
  const [canvasScale, setCanvasScale] = useState(0);

  // Calculate scale when container dimensions change — width-based for vertical scroll
  useEffect(() => {
    if (containerSize.width > 0) {
      const scaleX = (containerSize.width - 40) / SLIDE_WIDTH; // 40px padding
      const newScale = Math.min(scaleX, 1.2) * 0.95; // Cap max scale, safety margin
      setCanvasScale(newScale);
    }
  }, [containerSize]);

  // Selection mode: derive from selectedElementIds
  const selectedElements = useMemo(() => {
    const slide = slides.find(s => s.id === currentSlideId);
    if (!slide || selectedElementIds.length === 0) return [];
    return slide.elements?.filter(el => selectedElementIds.includes(el.id)) || [];
  }, [slides, currentSlideId, selectedElementIds]);

  // Clear element selection when slide changes (for multi-select)
  useEffect(() => {
    setSelectedElementIds([]);
  }, [currentSlideId]);

  // Backward compat: single element reference
  const selectedElement = selectedElements.length === 1 ? selectedElements[0] : null;
  const selectedElementId = selectedElementIds.length === 1 ? selectedElementIds[0] : null;

  // Edit mode: 'slide', 'element' (single), or 'multi' (multiple)
  const editMode = selectedElements.length === 0 ? 'slide' : (selectedElements.length === 1 ? 'element' : 'multi');

  // Helper to get element type label for mode indicator
  const getElementTypeLabel = useCallback((elements) => {
    if (!elements || elements.length === 0) return 'Full Slide';
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

  // Pre-cache all images and icons before entering presentation mode
  const startPresentation = useCallback(async () => {
    // Request fullscreen BEFORE any await — must be in user gesture context
    if (Platform.OS === 'web') {
      try {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
      } catch (e) { /* ignore */ }
    }
    try {
      const imageUrls = [];
      const iconNames = new Set();
      slides.forEach(slide => {
        (slide.elements || []).forEach(el => {
          if (el.type === 'image' && el.src) imageUrls.push(el.src);
          if (el.icon) iconNames.add(el.icon);
        });
        if (slide.backgroundImage) imageUrls.push(slide.backgroundImage);
      });
      const tasks = [];
      if (imageUrls.length > 0) tasks.push(globalImageCache.preCacheAll(imageUrls));
      if (iconNames.size > 0) tasks.push(prefetchIcons([...iconNames]));
      if (tasks.length > 0) await Promise.allSettled(tasks);
    } catch (e) {
      console.warn('[PresentationComposer] Pre-cache before present failed:', e);
    }
    setIsPlaying(true);
  }, [slides]);

  // Progressive generation progress tracking
  const [isGeneratingSlides, setIsGeneratingSlides] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0 });

  // Keep ref in sync with isGeneratingSlides state for use in callbacks
  useEffect(() => {
    isGeneratingSlidesRef.current = isGeneratingSlides;
  }, [isGeneratingSlides]);

  // Auto Update progress tracking
  const [isAutoUpdating, setIsAutoUpdating] = useState(false);

  // Keep ref in sync with isAutoUpdating state for use in callbacks
  useEffect(() => {
    isAutoUpdatingRef.current = isAutoUpdating;
  }, [isAutoUpdating]);
  const [autoUpdateProgress, setAutoUpdateProgress] = useState({ current: 0, total: 0 });
  const [showUpdateInstructionModal, setShowUpdateInstructionModal] = useState(false); // New State

  // Slide editing state
  const [editingSlideId, setEditingSlideId] = useState(null);
  const [editingSlideTitleText, setEditingSlideTitleText] = useState('');

  // Edit slide outline modal state
  const [editOutlineSlide, setEditOutlineSlide] = useState(null);

  // Delete confirmation modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [slideToDelete, setSlideToDelete] = useState(null);

  // Close confirmation modal
  const [showCloseConfirmModal, setShowCloseConfirmModal] = useState(false);

  // UI State
  const [sidebarWidth, setSidebarWidth] = useState(150);
  const sidebarWidthRef = useRef(150);
  const leftDragStartWidthRef = useRef(150);

  const [rightSidebarWidth, setRightSidebarWidth] = useState(300);
  const rightSidebarWidthRef = useRef(300);
  const rightDragStartWidthRef = useRef(300);

  // Slide thumbnail cache for sidebar preview
  const [slideThumbnails, setSlideThumbnails] = useState({});
  const thumbnailGenerationRef = useRef(null);
  const initialThumbnailGeneratedRef = useRef(new Set()); // Track slides that have had initial thumbnail generated
  const backgroundThumbnailQueueRef = useRef(null); // Track background thumbnail generation queue
  const thumbnailQueueStartedRef = useRef(false); // Prevent queue from restarting during cycling
  const isGeneratingSlidesRef = useRef(false); // Mirror of isGeneratingSlides for use in callbacks
  const isAutoUpdatingRef = useRef(false); // Mirror of isAutoUpdating for use in callbacks
  const isAiProcessingRef = useRef(false); // Mirror of isAiProcessing for use in callbacks
  const pendingLayoutFixRef = useRef(new Set()); // Track slides needing auto layout fix after render
  const critiquedSlidesRef = useRef(new Set()); // Track slides we've already sent through the vision critique loop
  const critiqueDisabledRef = useRef(false); // Latched when the server reports CRITIC_VISION_ENABLED=false — stop wasting critique POSTs
  const inFlightCritiquesRef = useRef(new Set()); // Track in-flight critiques to dedupe overlapping render-complete callbacks
  const handleAiEnhanceRef = useRef(null); // Ref to handleAiEnhance for use in effects
  const aiChatScrollRef = useRef(null); // Auto-scroll AI chat (main right panel)
  const aiChatScrollMobileRef = useRef(null); // Auto-scroll AI chat (mobile compact panel)
  const userDismissedGoalModalRef = useRef(false); // Track if user manually dismissed goal modal
  const hasInitializedNewPresentationRef = useRef(false); // Track if new presentation flow was initialized
  const lastLoadedPresentationIdRef = useRef(null); // Track last loaded presentation to prevent re-loading and overwriting local edits

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
  // Screenshots pasted into the AI chat. They ride along on the next send as
  // `image_attachments` and are OCR'd server-side into the instruction context
  // (this does NOT touch the slide image_placeholder stripping path).
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
    if (editingChartElementId && currentSlide?.id) {
      console.log('📊 [COMPOSER] Saving chart edit for:', editingChartElementId);
      updateElement(currentSlide.id, editingChartElementId, {
        chartConfig: newChartConfig,
      });
    }
    setShowChartEditModal(false);
    setEditingChartElementId(null);
    setEditingChartConfig(null);
  }, [editingChartElementId, currentSlide?.id, updateElement]);

  // Right panel tab state: 'ai' (default) or 'layers'
  const [rightPanelTab, setRightPanelTab] = useState('ai');

  // Refs
  const canvasRef = useRef(null);
  const canvasRefsMap = useRef(new Map()); // Map<slideId, React.RefObject>
  const activeCanvasRef = useRef(null); // Points to the currently focused canvas ref
  const contentScrollRef = useRef(null); // ScrollView for vertical slide scroll
  const sidebarScrollRef = useRef(null); // ScrollView for sidebar thumbnail list
  const slideLayoutsRef = useRef({}); // { slideId: { y, height } } from onLayout
  const sidebarLayoutsRef = useRef({}); // { slideId: { y, height } } from sidebar onLayout
  const scrollTrackingEnabled = useRef(true); // Disable during programmatic scrolls
  const lastScrollPositionRef = useRef({ scrollY: 0, layoutH: 0 }); // Latest scroll position for visible slide sync
  const slideChangeFromInteraction = useRef(false); // Flag: slide change was user-initiated
  const scrollDrivenChange = useRef(false); // Flag: slide change came from scroll detection (suppress sidebar auto-scroll)
  const actionBtnGuard = useRef(false); // Prevent parent onPress when action button clicked on web
  const skipSidebarScroll = useRef(false); // Skip sidebar auto-scroll on sidebar click

  // Selection info for shared toolbar
  const [selectionInfo, setSelectionInfo] = useState({ hasSelection: false });

  // Keep canvasRef/activeCanvasRef synced with current slide; scroll if triggered by interaction
  useEffect(() => {
    let retryTimer;
    if (currentSlideId && canvasRefsMap.current.has(currentSlideId)) {
      const ref = canvasRefsMap.current.get(currentSlideId);
      if (ref?.current) {
        activeCanvasRef.current = ref.current;
        canvasRef.current = ref.current;
      } else {
        // Canvas may not be mounted yet (new slide just added) — retry after mount
        retryTimer = setTimeout(() => {
          const retryRef = canvasRefsMap.current.get(currentSlideId);
          if (retryRef?.current) {
            activeCanvasRef.current = retryRef.current;
            canvasRef.current = retryRef.current;
          }
        }, 100);
      }
    }
    // Programmatic scroll when slide changed via sidebar/nav (not scroll-driven)
    if (slideChangeFromInteraction.current && currentSlideId) {
      slideChangeFromInteraction.current = false;
      scrollTrackingEnabled.current = false;
      let scrolled = false;
      if (Platform.OS === 'web') {
        const el = document.getElementById(`slide-view-${currentSlideId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          scrolled = true;
        }
      }
      if (!scrolled) {
        const layout = slideLayoutsRef.current[currentSlideId];
        if (layout && contentScrollRef.current?.scrollTo) {
          contentScrollRef.current.scrollTo({ y: layout.y - 20, animated: true });
          scrolled = true;
        }
      }
      if (scrolled) {
        setTimeout(() => { scrollTrackingEnabled.current = true; }, 800);
      } else {
        scrollTrackingEnabled.current = true;
      }
    }

    // Auto-scroll sidebar to keep active thumbnail visible
    // Skip when: (a) click came from sidebar itself, or (b) change was scroll-driven (user is scrolling main panel)
    if (currentSlideId && sidebarScrollRef.current && !skipSidebarScroll.current && !scrollDrivenChange.current) {
      const sidebarLayout = sidebarLayoutsRef.current[currentSlideId];
      if (sidebarLayout) {
        sidebarScrollRef.current.scrollTo({ y: Math.max(0, sidebarLayout.y - 40), animated: true });
      }
    }
    skipSidebarScroll.current = false;
    scrollDrivenChange.current = false;
    return () => { if (retryTimer) clearTimeout(retryTimer); };
  }, [currentSlideId]);

  // Default theme
  const safeTheme = theme || {
    background: '#ffffff',
    text: '#333333',
    primary: '#2196F3',
    surface: '#f5f5f5',
    border: '#e0e0e0',
    isDark: false,
  };



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

  // Generate thumbnail for a specific slide (for sidebar preview)
  // Wait until all image elements on the canvas have loaded (fabric.Image objects with valid _element)
  const waitForCanvasImages = useCallback(async (slide, maxWait = 5000) => {
    if (!slide?.elements) return;
    // In multi-canvas mode, look up the specific slide's canvas ref
    const slideCanvasRef = canvasRefsMap.current.get(slide.id);
    const canvas = slideCanvasRef?.current || canvasRef.current;
    if (!canvas) return;
    const imageCount = slide.elements.filter(e => e.type === 'image' && e.src).length;
    if (imageCount === 0) return; // No images to wait for

    const start = Date.now();
    while (Date.now() - start < maxWait) {
      if (!canvas?.getObjects) break;
      const fabricImages = canvas.getObjects().filter(
        o => (o.type === 'image' || (o.type === 'group' && o.elementId)) && o._element
      );
      if (fabricImages.length >= imageCount) return; // All loaded
      await new Promise(r => setTimeout(r, 200));
    }
  }, []);

  // Returns true if successful, false otherwise
  const generateSlideThumbnail = useCallback(async (slideId, isInitialGeneration = false) => {
    if (!slideId) {
      // console.log('📸 [THUMBNAIL] Skipped - no slideId');
      return false;
    }

    // In multi-canvas mode, look up the specific slide's canvas ref
    const slideCanvasRef = canvasRefsMap.current.get(slideId);
    const canvas = slideCanvasRef?.current || canvasRef.current;

    if (!canvas?.toDataURL) {
      // console.log('📸 [THUMBNAIL] Skipped - canvas not ready for slide:', slideId);
      return false;
    }

    try {
      const dataUrl = await canvas.toDataURL({ format: 'jpeg', quality: 0.5 });

      if (!dataUrl) {
        // console.log('📸 [THUMBNAIL] Skipped - no dataUrl returned for slide:', slideId);
        return false;
      }

      setSlideThumbnails(prev => ({
        ...prev,
        [slideId]: dataUrl
      }));

      // Only mark as initially generated after successful generation
      if (isInitialGeneration) {
        initialThumbnailGeneratedRef.current.add(slideId);
      }

      // console.log('📸 [THUMBNAIL] Generated thumbnail for slide:', slideId);
      return true;
    } catch (err) {
      console.warn('📸 [THUMBNAIL] Failed to generate slide thumbnail:', slideId, err);
      return false;
    }
  }, []);

  // Process thumbnail queue - generates thumbnails for slides in the background

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
  // Handle initialPresentation prop changes - must also run when visible changes
  useEffect(() => {
    if (!visible) return; // Only process when composer is visible

    if (initialPresentation && initialPresentation.id) {
      // CRITICAL FIX: Only load presentation data when loading a DIFFERENT presentation
      // This prevents overwriting local edits when the same presentation prop is passed again
      const isNewPresentation = lastLoadedPresentationIdRef.current !== initialPresentation.id;

      console.log('🔄 [COMPOSER] Loading presentation prop:', {
        id: initialPresentation.id,
        title: initialPresentation.title,
        slideCount: initialPresentation.slides?.length || 0,
        hasGoal: !!initialPresentation.goal,
        hasStyle: !!initialPresentation.style,
        isNewPresentation,
        lastLoadedId: lastLoadedPresentationIdRef.current
      });

      // Only reset slides if loading a DIFFERENT presentation
      if (isNewPresentation) {
        // console.log('📥 [COMPOSER] Loading NEW presentation - resetting slides');
        lastLoadedPresentationIdRef.current = initialPresentation.id;

        // Clear old thumbnails and abort any background queue
        setSlideThumbnails({});
        initialThumbnailGeneratedRef.current.clear();
        critiquedSlidesRef.current.clear();
        inFlightCritiquesRef.current.clear();
        thumbnailQueueStartedRef.current = false;
        if (backgroundThumbnailQueueRef.current) backgroundThumbnailQueueRef.current.aborted = true;

        setCurrentPresentationId(initialPresentation.id);
        setPresentationTitle(initialPresentation.title || 'Untitled Presentation');
        if (initialPresentation.goal) {
          // Fix for nested goal object issue: Only wrap if it's a string
          if (typeof initialPresentation.goal === 'string') {
            setPresentationGoal({ purpose: initialPresentation.goal });
          } else {
            setPresentationGoal(initialPresentation.goal);
          }
        }
        if (initialPresentation.style) {
          // Hydrate deck-level chrome into its own state and KEEP IT OUT of the
          // style object (it would go stale there and contradict the live state
          // in agent payloads). ALWAYS set — falling back to defaults — so a deck
          // without chrome never inherits the previous deck's footer/numbers.
          const { headerFooter: _hfIn, slideNumbers: _snIn, ...cleanStyle } = initialPresentation.style;
          setPresentationStyle(cleanStyle);
          setHeaderFooter({ ...DEFAULT_HEADER_FOOTER, ...(_hfIn || {}) });
          setSlideNumbers({ ...DEFAULT_SLIDE_NUMBERS, ...(_snIn || {}) });
        }
        // CRITICAL: Update slides with fresh data (new signed URLs) from backend
        if (initialPresentation.slides && initialPresentation.slides.length > 0) {
          // console.log('🔄 [PRESENTATION] Updating slides from prop (Refreshed URLs)');
          // SANITIZE: cleanup invalid textBaseline from DB data
          const sanitizedSlides = sanitizeFabricData ? sanitizeFabricData(initialPresentation.slides) : initialPresentation.slides;

          // Restore per-slide thumbnails from saved data
          const restoredThumbnails = {};
          sanitizedSlides.forEach(slide => {
            if (slide.slideThumbnail) {
              restoredThumbnails[slide.id] = slide.slideThumbnail;
              initialThumbnailGeneratedRef.current.add(slide.id);
            }
          });
          if (Object.keys(restoredThumbnails).length > 0) {
            setSlideThumbnails(restoredThumbnails);
            // console.log('📸 [THUMBNAIL] Restored', Object.keys(restoredThumbnails).length, 'thumbnails from saved data');
          }

          // Strip slideThumbnail from working state to avoid duplicate base64 in memory.
          // Also strip `critique_recommended`: it's a transient signal meaning "this
          // slide was just generated/edited by the backend" and drives the per-slide
          // vision-critique pass. A saved deck was already critiqued at build time, so
          // re-running OCR critique on every load is wasteful. Edits re-set the flag
          // via the enhance endpoint, so editing a loaded slide still triggers critique.
          const cleanSlides = sanitizedSlides.map(
            ({ slideThumbnail, critique_recommended, ...rest }) => rest
          );
          setSlides(cleanSlides);
          // Always start on the first slide when loading a presentation
          setCurrentSlideId(initialPresentation.slides[0].id);
          // Thumbnails restored from saved data; background queue will fill in any missing ones
        } else {
          console.warn('⚠️ [COMPOSER] Loaded presentation has NO slides');
        }
        setShowGoalSetting(false);
      } else {
        console.log('🛡️ [COMPOSER] Same presentation - preserving local edits');
      }
    } else if (initialPresentation === null && !hasInitializedNewPresentationRef.current) {
      // GUARD: Don't run NEW flow if slides already contain real data from a previous load
      // This prevents a race condition where the hook loads data but useEffect sees null prop
      const hasLoadedSlides = slides.length > 0 && slides[0].id && !slides[0].id.startsWith('slide_');

      // FIX: If we are explicitly starting a NEW presentation (initialPresentation is null),
      // and we haven't initialized yet, we SHOULD overwrite any stale state.
      // The only valid case to skip is if we are ALREADY in a new flow (handled by hasInitialized ref)
      // or if the hook somehow miraculously loaded the *right* data while prop was null (unlikely).
      // We will trust the prop: if null, we want NEW.
      /* 
      if (hasLoadedSlides) {
        console.log('🛡️ [COMPOSER] Skipping NEW flow - slides already loaded with real data:', slides[0].id);
        return;
      }
      */

      // Creating new presentation - open goal setting (only once)
      hasInitializedNewPresentationRef.current = true;
      console.log('📊 [COMPOSER] Starting NEW presentation flow (initialPresentation is null)');

      // Clear all old presentation state
      setCurrentPresentationId(null);
      setPresentationTitle('Untitled Presentation');
      setPresentationGoal(null);
      setPresentationStyle(PRESET_STYLES[0]);
      setHeaderFooter(DEFAULT_HEADER_FOOTER);
      setSlideNumbers(DEFAULT_SLIDE_NUMBERS);

      // Reset to a single blank slide
      const newSlideId = `slide_${Date.now()}`;
      setSlides([{
        id: newSlideId,
        order: 1,
        title: 'Title Slide',
        layout: 'title',
        elements: [],
        backgroundColor: '#ffffff',
        hasUnsavedChanges: false,
      }]);
      setCurrentSlideId(newSlideId);

      // Clear cached thumbnails and tracking for new presentation
      setSlideThumbnails({});
      initialThumbnailGeneratedRef.current.clear();
      critiquedSlidesRef.current.clear();
      inFlightCritiquesRef.current.clear();

      // Clear any selected elements
      setSelectedElementIds([]);

      // Use setTimeout to ensure modal is fully rendered first
      setTimeout(() => {
        setShowGoalSetting(true);
      }, 100);
    }
  }, [initialPresentation, visible, setSlides, setCurrentSlideId]); // REMOVED 'slides' from deps - it caused re-runs on every edit

  // AI Assistant chat is per-presentation + per-session. The composer stays
  // MOUNTED across opens (only `visible` toggles), so without this the chat
  // history from one deck leaks into the next deck the user opens. Reset it
  // whenever the composer closes OR a different presentation is loaded.
  const loadedPresChatIdRef = useRef(undefined);
  useEffect(() => {
    const resetChat = () => {
      setAiChatMessages([]);
      setChatInput('');
      setAiPastedImages([]);
      setIsAiProcessing(false);
    };
    if (!visible) {
      loadedPresChatIdRef.current = undefined;
      resetChat();
      return;
    }
    const pid = initialPresentation?.id ?? '__new__';
    // Reset only on a genuine switch between decks. Skip the '__new__' → real-id
    // transition (a new deck being saved mid-session) so it can't wipe an active
    // conversation. The close path above covers the new→other case.
    if (loadedPresChatIdRef.current !== undefined &&
        loadedPresChatIdRef.current !== '__new__' &&
        loadedPresChatIdRef.current !== pid) {
      resetChat();
    }
    loadedPresChatIdRef.current = pid;
  }, [visible, initialPresentation]);

  // Show goal setting on first open
  useEffect(() => {
    if (visible && !presentationGoal && slides.length === 1 && !slides[0].elements?.length && !isLoadingPresentation && !currentPresentationId && !initialPresentation && !userDismissedGoalModalRef.current) {
      setShowGoalSetting(true);
    }
    // Reset dismissal flag and loaded presentation tracking when composer is closed
    if (!visible) {
      userDismissedGoalModalRef.current = false;
      lastLoadedPresentationIdRef.current = null; // Reset so re-opening loads fresh data
      hasInitializedNewPresentationRef.current = false;
    }
  }, [visible, presentationGoal, slides, isLoadingPresentation, currentPresentationId, initialPresentation]);

  // Load custom styles from storage on mount
  useEffect(() => {
    const loadCustomStyles = async () => {
      try {
        const savedStyles = await AsyncStorage.getItem('@custom_presentation_styles');
        if (savedStyles) {
          const parsedStyles = JSON.parse(savedStyles);
          console.log('🎨 [PRESENTATION] Loaded custom styles from storage:', parsedStyles.length);
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
    console.log('🧹 [COMPOSER] Sanitizing slide data for textBaseline...');
    return sanitize(data);
  }, []);

  // Handle presentation generated from goal setting - SUPPORTS PROGRESSIVE UPDATES
  const handlePresentationGenerated = useCallback((presentationData) => {
    // Sanitize incoming data first
    if (presentationData?.slides) {
      presentationData.slides = sanitizeFabricData(presentationData.slides);
    }

    const slideCount = presentationData.slides?.length || 0;
    const isProgressiveUpdate = presentationData.isGenerating;

    console.log('🎬 Presentation update:', slideCount, 'slides', isProgressiveUpdate ? '(generating...)' : '(complete)');

    if (presentationData.slides && slideCount > 0) {
      // Use functional update to preserve any in-progress changes
      setSlides(prevSlides => {
        // Build map for fast lookup
        const prevMap = new Map(prevSlides.map(s => [s.id, s]));
        const newSlides = [];

        for (const incSlide of presentationData.slides) {
          if (prevMap.has(incSlide.id)) {
            // EXISTING SLIDE: Perform Smart Merge
            const existing = prevMap.get(incSlide.id);

            // We want to keep user edits (existing) but accept AI updates (incSlide)
            // primarily for Image Placeholders resolving to Images
            const mergedElements = (existing.elements || []).map(existingEl => {
              // Find corresponding element in incoming data
              const incomingEl = incSlide.elements?.find(e => e.id === existingEl.id);

              // CRITICAL: Only accept update if it's an Image Placeholder turning into an Image with valid src
              if (incomingEl && existingEl.type === 'image_placeholder' && incomingEl.type === 'image' && incomingEl.src) {
                console.log(`🖼️ [COMPOSER] Apply AI Image update for element ${existingEl.id}`);
                return incomingEl;
              }
              // Otherwise keep user's version (preserves text edits, positions, etc.)
              return existingEl;
            });

            newSlides.push({
              ...existing,
              elements: mergedElements,
              // Keep other user-modified props if needed, or prefer existing
            });
          } else {
            // NEW SLIDE: Add it
            newSlides.push({
              ...incSlide,
              hasUnsavedChanges: false,
            });
            pendingLayoutFixRef.current.add(incSlide.id);
          }
        }

        // CRITICAL: Sort by order to ensure slides display in correct sequence
        // even when they complete out of order during parallel generation
        return newSlides.sort((a, b) => (a.order || 0) - (b.order || 0));
      });

      // Only set current slide ID if:
      // 1. We don't have a current slide yet, OR
      // 2. This is the initial generation (first slide appeared)
      setCurrentSlideId(prevId => {
        if (!prevId || !presentationData.slides.find(s => s.id === prevId)) {
          return presentationData.slides[0].id;
        }
        return prevId;
      });
    } else if (!isProgressiveUpdate && slideCount === 0) {
      // Only show first slide data log on initial call
      console.log('🎬 Initial generation starting, no slides yet');
    }

    if (presentationData.style) {
      // Merge iconSet if available
      const styleUpdate = { ...presentationData.style };
      if (presentationData.iconSet) {
        styleUpdate.iconSet = presentationData.iconSet;
      }
      setPresentationStyle(styleUpdate);
    } else if (presentationData.iconSet) {
      // Update existing style with iconSet
      setPresentationStyle(prev => ({ ...prev, iconSet: presentationData.iconSet }));
    }

    if (presentationData.goal) {
      setPresentationTitle(presentationData.goal.substring(0, 50) || 'AI Presentation');
    }

    // Close goal setting modal on first callback
    setShowGoalSetting(false);

    // Track generation progress
    if (presentationData.isGenerating !== undefined) {
      setIsGeneratingSlides(presentationData.isGenerating);
      if (presentationData.slideOutline) {
        setGenerationProgress({
          current: slideCount,
          total: presentationData.slideOutline.length
        });
      }
      // Thumbnails are generated on-demand when user manually navigates to each slide
    }
  }, [setSlides, setCurrentSlideId]);

  // Handle goal set
  const handleGoalSet = useCallback((goal) => {
    setPresentationGoal(goal);
    if (goal.purpose) {
      setPresentationTitle(goal.purpose.substring(0, 50) || 'AI Presentation');
    }
  }, []);

  // Handle style change
  const handleStyleChange = useCallback((newStyle) => {
    setPresentationStyle(newStyle);
    applyStyleToAllSlides(newStyle);
    setShowStylePicker(false);
  }, [applyStyleToAllSlides]);

  // Navigate slides
  const goToNextSlide = useCallback(() => {
    const nextIndex = currentSlideIndex + 1;
    if (nextIndex < slides.length) {
      slideChangeFromInteraction.current = true;
      setCurrentSlideId(slides[nextIndex].id);
    }
  }, [currentSlideIndex, slides, setCurrentSlideId]);

  const goToPrevSlide = useCallback(() => {
    const prevIndex = currentSlideIndex - 1;
    if (prevIndex >= 0) {
      slideChangeFromInteraction.current = true;
      setCurrentSlideId(slides[prevIndex].id);
    }
  }, [currentSlideIndex, slides, setCurrentSlideId]);

  // === Vertical Scroll Helpers ===

  const getOrCreateCanvasRef = useCallback((slideId) => {
    if (!canvasRefsMap.current.has(slideId)) {
      canvasRefsMap.current.set(slideId, React.createRef());
    }
    return canvasRefsMap.current.get(slideId);
  }, []);

  const currentSlideIdRef = useRef(currentSlideId);
  useEffect(() => { currentSlideIdRef.current = currentSlideId; }, [currentSlideId]);

  // STRUCTURAL-CHANGE GUARD: add / delete / duplicate / reorder reflows the
  // vertical slide view. That reflow fires handleContentScroll, which would
  // otherwise recompute the "closest" slide from the shifted layout and hijack
  // the current selection ("the list reshuffles on its own"). Whenever the
  // slide id/order signature changes, suppress scroll-driven selection until
  // the reflow settles. Pure element edits don't change the signature, so they
  // are unaffected.
  const slideOrderSigRef = useRef('');
  useEffect(() => {
    const sig = slides.map(s => s.id).join('|');
    if (sig === slideOrderSigRef.current) return;
    const isInitial = slideOrderSigRef.current === '';
    slideOrderSigRef.current = sig;
    if (isInitial) return; // first mount — nothing to protect against yet
    scrollTrackingEnabled.current = false;
    const t = setTimeout(() => { scrollTrackingEnabled.current = true; }, 700);
    return () => clearTimeout(t);
  }, [slides]);

  // Helper: determine the most visible slide from stored scroll position
  const getVisibleSlideId = useCallback(() => {
    const { scrollY, layoutH } = lastScrollPositionRef.current;
    if (!layoutH) return null;
    const viewportMid = scrollY + (layoutH / 2);
    let closestSlideId = null;
    let closestDist = Infinity;
    for (const [slideId, layout] of Object.entries(slideLayoutsRef.current)) {
      const slideMid = layout.y + layout.height / 2;
      const dist = Math.abs(viewportMid - slideMid);
      if (dist < closestDist) {
        closestDist = dist;
        closestSlideId = slideId;
      }
    }
    return closestSlideId;
  }, []);

  const handleContentScroll = useCallback((e) => {
    // Always store the latest scroll position immediately (no debounce)
    lastScrollPositionRef.current = {
      scrollY: e.nativeEvent.contentOffset.y,
      layoutH: e.nativeEvent.layoutMeasurement.height,
    };
    if (!scrollTrackingEnabled.current) return;
    const scrollY = e.nativeEvent.contentOffset.y;
    const layoutH = e.nativeEvent.layoutMeasurement.height;
    const viewportMid = scrollY + (layoutH / 2);

    let closestSlideId = null;
    let closestDist = Infinity;

    for (const [slideId, layout] of Object.entries(slideLayoutsRef.current)) {
      const slideMid = layout.y + layout.height / 2;
      const dist = Math.abs(viewportMid - slideMid);
      if (dist < closestDist) {
        closestDist = dist;
        closestSlideId = slideId;
      }
    }

    if (closestSlideId && closestSlideId !== currentSlideIdRef.current) {
      scrollDrivenChange.current = true;
      setCurrentSlideId(closestSlideId);
    }
  }, [setCurrentSlideId]);

  const scrollDebounceRef = useRef(null);
  const handleContentScrollDebounced = useCallback((e) => {
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

  // Scroll to a slide by ID — uses scrollIntoView on web for reliability, falls back to scrollTo
  const scrollToSlide = useCallback((slideId, animated = true) => {
    scrollTrackingEnabled.current = false;
    let scrolled = false;
    // On web, use scrollIntoView for reliable positioning (avoids stale onLayout data)
    if (Platform.OS === 'web') {
      const el = document.getElementById(`slide-view-${slideId}`);
      if (el) {
        el.scrollIntoView({ behavior: animated ? 'smooth' : 'auto', block: 'center' });
        scrolled = true;
      }
    }
    // Fallback: use ScrollView.scrollTo with stored layout positions
    if (!scrolled) {
      const layout = slideLayoutsRef.current[slideId];
      if (layout && contentScrollRef.current) {
        contentScrollRef.current.scrollTo({ y: layout.y - 16, animated });
        scrolled = true;
      }
    }
    if (scrolled) {
      // Re-enable scroll tracking after animation settles
      setTimeout(() => { scrollTrackingEnabled.current = true; }, animated ? 800 : 100);
    } else {
      scrollTrackingEnabled.current = true;
    }
  }, []);

  const handleSelectSlide = useCallback((slideId) => {
    setCurrentSlideId(slideId);
    // Discard selection on other canvases
    canvasRefsMap.current.forEach((ref, id) => {
      if (id !== slideId && ref.current?.discardSelection) {
        ref.current.discardSelection();
      }
    });
    // Update active canvas ref
    const targetRef = canvasRefsMap.current.get(slideId);
    if (targetRef?.current) {
      activeCanvasRef.current = targetRef.current;
      canvasRef.current = targetRef.current;
    }
    // Programmatic scroll with tracking disabled
    scrollToSlide(slideId, true);
  }, [setCurrentSlideId, scrollToSlide]);

  // Delete slide handlers
  const handleDeleteSlide = useCallback((slideId) => {
    if (slides.length <= 1) {
      Alert.alert('Cannot Delete', 'You must have at least one slide.');
      return;
    }
    setSlideToDelete(slideId);
    setShowDeleteModal(true);
  }, [slides.length]);

  const confirmDeleteSlide = useCallback(() => {
    if (slideToDelete) {
      deleteSlide(slideToDelete);
    }
    setShowDeleteModal(false);
    setSlideToDelete(null);
  }, [slideToDelete, deleteSlide]);

  const cancelDeleteSlide = useCallback(() => {
    setShowDeleteModal(false);
    setSlideToDelete(null);
  }, []);

  // Duplicate slide handler
  const handleDuplicateSlide = useCallback((slideId) => {
    const slideToDuplicate = slides.find(s => s.id === slideId);
    if (!slideToDuplicate) return;

    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);

    const duplicatedSlide = {
      ...slideToDuplicate,
      id: `slide_${timestamp}_${random}`,
      title: `${slideToDuplicate.title || 'Slide'} (Copy)`,
      elements: slideToDuplicate.elements?.map(el => ({
        ...el,
        id: `${el.id}_copy_${timestamp}`
      })) || [],
      hasUnsavedChanges: true,
    };

    // Insert after original slide and re-number `order` so a later sort-by-order
    // (generation merge / Yjs) can't reshuffle the duplicate out of place.
    const originalIndex = slides.findIndex(s => s.id === slideId);
    const newSlides = [...slides];
    newSlides.splice(originalIndex + 1, 0, duplicatedSlide);
    setSlides(newSlides.map((s, i) => ({ ...s, order: i + 1 })));

    // Navigate to new slide
    setCurrentSlideId(duplicatedSlide.id);

    // Copy thumbnail from original slide if it exists (duplicates have same content initially)
    if (slideThumbnails[slideId]) {
      setSlideThumbnails(prev => ({
        ...prev,
        [duplicatedSlide.id]: prev[slideId]
      }));
      initialThumbnailGeneratedRef.current.add(duplicatedSlide.id);
      // console.log(`📸 [THUMBNAIL] Copied thumbnail from original slide ${slideId} to duplicate ${duplicatedSlide.id}`);
    }

    // console.log(`📄 [COMPOSER] Duplicated slide: ${slideToDuplicate.title} → ${duplicatedSlide.title}`);
  }, [slides, setSlides, setCurrentSlideId, slideThumbnails]);

  // Slide title editing
  const startEditingSlideTitle = useCallback((slide) => {
    setEditingSlideId(slide.id);
    setEditingSlideTitleText(slide.title);
  }, []);

  const saveSlideTitle = useCallback(() => {
    if (editingSlideId && editingSlideTitleText.trim()) {
      updateSlideTitle(editingSlideId, editingSlideTitleText);
    }
    setEditingSlideId(null);
    setEditingSlideTitleText('');
  }, [editingSlideId, editingSlideTitleText, updateSlideTitle]);

  const handleSaveSlideOutline = useCallback(({ title, outline }) => {
    if (editOutlineSlide) {
      updateSlide(editOutlineSlide.id, { title: title || editOutlineSlide.title, outline });
    }
    setEditOutlineSlide(null);
  }, [editOutlineSlide, updateSlide]);

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

  const handleElementUpdate = useCallback((maybeSlideId, maybeElementId, maybeUpdates) => {
    // Support both (elementId, updates) and (slideId, elementId, updates)
    const hasSlideId = maybeUpdates !== undefined;
    const slideId = hasSlideId ? maybeSlideId : currentSlide?.id;
    const elementId = hasSlideId ? maybeElementId : maybeSlideId;
    const updates = hasSlideId ? maybeUpdates : maybeElementId;

    // Special case: Undo/Redo passes null elementId with updates.elements array
    if (slideId && elementId === null && updates?.elements !== undefined) {
      console.log('🔄 [COMPOSER] Full elements replacement for Undo/Redo');
      updateElement(slideId, null, updates);
      return;
    }

    if (slideId && elementId && updates) {
      updateElement(slideId, elementId, updates);
    }
  }, [currentSlide?.id, updateElement]);

  const handleAddElement = useCallback((maybeSlideId, typeOrElement, maybeElement) => {
    // Support both (element) and (slideId, type, element)
    if (maybeElement) {
      // Called with (slideId, type, elementData)
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

      console.log('✅ [COMPOSER] Adding element:', { slideId: maybeSlideId, type, options });
      return addElement(maybeSlideId, type, options);
    } else if (currentSlide && typeOrElement) {
      // Called with (type) - simple add
      console.log('✅ [COMPOSER] Adding simple element:', typeOrElement);
      return addElement(currentSlide.id, typeOrElement);
    }
  }, [currentSlide, addElement]);

  const handleDeleteElement = useCallback((maybeSlideId, maybeElementId) => {
    const slideId = maybeElementId ? maybeSlideId : currentSlide?.id;
    const elementId = maybeElementId || maybeSlideId;
    if (slideId && elementId) {
      deleteElement(slideId, elementId);
    }
  }, [currentSlide, deleteElement]);

  // Handler for deleting multiple elements at once (e.g., from Ctrl+A + Delete)
  const handleDeleteMultipleElements = useCallback((slideId, elementIds) => {
    const actualSlideId = slideId || currentSlide?.id;
    if (actualSlideId && elementIds && elementIds.length > 0) {
      deleteMultipleElements(actualSlideId, elementIds);
    }
  }, [currentSlide, deleteMultipleElements]);

  // Diagram Handlers
  // Legacy `setShowDiagramMode(true)` opened the old DiagramPanel/DiagramBrowser flow.
  // The composer's "Insert Diagram" toolbar button now opens the AI SVG diagram modal instead.
  const handleOpenDiagram = () => {
    setDiagramRegenContext(null);
    setShowAIDiagramModal(true);
  };

  // Open AIDiagramModal prefilled to regenerate an existing svg_diagram element in place.
  const handleRegenerateDiagram = useCallback((element) => {
    if (!element || element.type !== 'svg_diagram') return;
    setDiagramRegenContext({
      elementId: element.id,
      prompt: element.prompt || '',
      diagramKind: element.diagramKind || 'flowchart',
      width: Math.round(element.width || 660),
      height: Math.round(element.height || 340),
      fillColor: element.fillColor || '',
      svgContent: element.svgContent || '',
    });
    setShowAIDiagramModal(true);
  }, []);

  // AI enhancement for current slide - uses orchestrator for intent classification
  // Supports background override: handleAiEnhance(instruction, targetSlide, true) for auto layout fix
  const handleAiEnhance = useCallback(async (overrideInstruction, overrideSlide, isBackground) => {
    const instruction = overrideInstruction || chatInput.trim();
    // Sync: ensure we target the actually visible slide from scroll position
    let targetSlide = overrideSlide || currentSlide;
    if (!overrideSlide) {
      const visibleSlideId = getVisibleSlideId();
      if (visibleSlideId && visibleSlideId !== currentSlideId) {
        const visibleSlide = slides.find(s => s.id === visibleSlideId);
        if (visibleSlide) {
          targetSlide = visibleSlide;
          setCurrentSlideId(visibleSlideId);
        }
      }
    }
    if (!instruction || (!isBackground && isAiProcessing) || !targetSlide) return;

    if (!isBackground) setIsAiProcessing(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      // HANDLE "ALL SLIDES" MODE (Smart Orchestrate-All - Single API call)
      if (editScope === 'all' && !overrideSlide) {
        const instruction = chatInput;
        // Add user message to chat history
        setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
        setChatInput(''); // Clear input

        setIsAutoUpdating(true);
        setIsAiProcessing(true);

        // Only use vault if folders are explicitly selected
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
          // Filter out hidden slides for AI processing
          const aiSlides = slides.filter(s => !s.hidden);
          const aiIndexToFullIndex = aiSlides.map(s => slides.indexOf(s));

          // Build lightweight summaries for relevance classification
          const slidesSummary = buildSlidesSummary(aiSlides);
          const currentIndex = aiSlides.findIndex(s => s.id === currentSlideId);

          // Add AI entry message
          setAiChatMessages(prev => [...prev.slice(-29), {
            id: chatMsgUid(),
            text: `Analyzing ${aiSlides.length} slides and planning edits...`,
            timestamp: new Date(),
            actionType: 'edit'
          }]);

          // SSE streaming to orchestrate-all-stream
          const orchestrateAllResponse = await fetch(`${apiConfig.API_URL}/presentation/orchestrate-all-stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              instruction: instruction,
              slides_summary: slidesSummary,
              full_slides: aiSlides.map(s => {
                const { processedSlide } = extractImagesFromSlide(s);
                return { ...processedSlide, id: s.id };
              }),
              current_slide_index: currentIndex >= 0 ? currentIndex : 0,
              folder_ids: finalFolderIds,
              style: presentationStyle,
              presentation_goal: extractGoalString(presentationGoal),
              presentation_type: presentationGoal?.documentType || 'general',
              icon_set: presentationStyle?.iconSet || 'default',
              is_update_all: false,
              deck_profile: presentationGoal?.deckProfile || 'corporate',
              deck_plan: presentationGoal?.deckPlan || null,
            }),
          });

          if (!orchestrateAllResponse.ok) {
            const errorData = await orchestrateAllResponse.json().catch(() => ({}));
            if (orchestrateAllResponse.status === 402) {
              authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.');
              setIsAutoUpdating(false); setIsAiProcessing(false); return;
            }
            if (handleCreditError(errorData)) { setIsAutoUpdating(false); setIsAiProcessing(false); return; }
            throw new Error(errorData.message || 'Failed to process all slides');
          }

          // --- SSE Stream processing ---
          const allReader = orchestrateAllResponse.body.getReader();
          const allDecoder = new TextDecoder();
          let allBuffer = '';
          let successCount = 0;
          let totalMatched = 0;
          const pendingImageTasks = []; // Parallel image generation across slides

          while (true) {
            const { done, value } = await allReader.read();
            if (done) break;
            allBuffer += allDecoder.decode(value, { stream: true });
            const bufLines = allBuffer.split('\n');
            allBuffer = bufLines.pop() || '';
            for (const line of bufLines) {
              const trimmed = line.trim();
              if (!trimmed || !trimmed.startsWith('data: ')) continue;
              try {
                const event = JSON.parse(trimmed.slice(6));

                if (event.type === 'classification') {
                  totalMatched = event.relevant_count || 0;
                  setAutoUpdateProgress({ current: 0, total: totalMatched });
                } else if (event.type === 'progress') {
                  setAutoUpdateProgress(prev => ({ ...prev, current: event.page_index + 1 }));
                  setAiChatMessages(prev => [...prev.slice(-29), {
                    id: chatMsgUid(), text: `Editing slide ${event.page_index + 1}...`,
                    timestamp: new Date(), actionType: 'edit'
                  }]);
                } else if (event.type === 'page_result' && event.slide_data) {
                  // page_result events are always updates (create_new is handled via 'result' event)
                  try {
                    const fullIndex = aiIndexToFullIndex[event.page_index];
                    const originalSlide = slides[fullIndex];
                    if (!originalSlide) continue;
                    const { imageMap: editImageMap } = extractImagesFromSlide(originalSlide);
                    const restoredSlideData = restoreImagesToSlide(event.slide_data, editImageMap);
                    const processedSlideOutput = await processSlideAsync(restoredSlideData);

                    // Apply text/layout changes immediately
                    const slideUpdate = { elements: processedSlideOutput.elements };
                    if (processedSlideOutput.backgroundColor) slideUpdate.backgroundColor = processedSlideOutput.backgroundColor;
                    if (processedSlideOutput.title) slideUpdate.title = processedSlideOutput.title;
                    if (processedSlideOutput.notes) slideUpdate.notes = processedSlideOutput.notes;
                    // Sync outline from AI response (keeps outline fresh after edits)
                    slideUpdate.outline = processedSlideOutput.outline || restoredSlideData.outline || originalSlide.outline || originalSlide.sectionTopic || '';
                    // Bulk edit changed this slide's layout — flag for re-critique.
                    slideUpdate.critique_recommended = true;
                    critiquedSlidesRef.current.delete(originalSlide.id);
                    updateSlide(originalSlide.id, slideUpdate);
                    successCount++;

                    // Fire image generation in parallel (don't block SSE loop)
                    const imagePlaceholders = (processedSlideOutput.elements || []).filter(el => el.type === 'image_placeholder');
                    if (imagePlaceholders.length > 0) {
                      const slideId = originalSlide.id;
                      const imageTask = (async () => {
                        try {
                          await generateImagesParallel(imagePlaceholders, {
                            generationQuality, style: presentationStyle?.name || 'professional',
                            userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
                          });
                          const finalElements = (processedSlideOutput.elements || []).map(el => {
                            if (el.type === 'image' && !el.src && !el.isUserMedia) {
                              return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                            }
                            return el;
                          });
                          updateSlide(slideId, { elements: finalElements });
                        } catch (imgErr) { console.error(`❌ [ORCHESTRATE_ALL] Image gen failed for slide ${event.page_index}:`, imgErr); }
                      })();
                      pendingImageTasks.push(imageTask);
                    }
                  } catch (editErr) { console.error(`❌ [ORCHESTRATE_ALL] Error applying slide ${event.page_index}:`, editErr); }
                } else if (event.type === 'result' && event.data) {
                  // Handle create_new from stream
                  const d = event.data;
                  if (d.intent === 'create_new' && d.edits?.[0]?.slide_data) {
                    const newSlideId = `slide_${Date.now()}_ai_new`;
                    // Compute insertion position: after current slide, not at end
                    // Defensive: validate after_slide_index bounds
                    let rawIdx = (typeof d.edits[0].after_slide_index === 'number' && d.edits[0].after_slide_index >= 0)
                      ? d.edits[0].after_slide_index
                      : (currentIndex >= 0 ? currentIndex : slides.length - 1);
                    const insertAfterIdx = Math.min(Math.max(rawIdx, 0), slides.length - 1);
                    const insertOrder = insertAfterIdx + 2; // +1 for 0-index, +1 for "after"
                    console.log(`📄 [ORCHESTRATE_ALL] create_new: insertAfter=${insertAfterIdx}, order=${insertOrder}`);
                    const newSlideData = {
                      id: newSlideId, order: insertOrder,
                      title: d.edits[0].slide_data.title || 'New Slide',
                      layout: d.edits[0].slide_data.layout || 'content',
                      elements: d.edits[0].slide_data.elements || [],
                      backgroundColor: d.edits[0].slide_data.backgroundColor || '#ffffff',
                      notes: d.edits[0].slide_data.notes || '', hasUnsavedChanges: true,
                    };
                    const processedNew = await processSlideAsync(newSlideData);

                    // Generate images for any image_placeholder elements
                    const imgPlaceholders = (processedNew.elements || []).filter(el => el.type === 'image_placeholder');
                    await generateImagesParallel(imgPlaceholders, {
                      generationQuality, style: presentationStyle?.name || 'professional',
                      userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
                    });

                    // Safety net: catch any remaining type='image' elements without src (skip user-media)
                    const finalNewElements = (processedNew.elements || []).map(el => {
                      if (el.type === 'image' && !el.src && !el.isUserMedia) {
                        console.warn(`⚠️ [ORCHESTRATE_ALL_NEW] Image element ${el.id} still has no src — converting to shape`);
                        return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                      }
                      return el;
                    });

                    pendingLayoutFixRef.current.add(newSlideId);
                    setSlides(prev => {
                      const bumped = prev.map(s => s.order >= insertOrder ? { ...s, order: s.order + 1 } : s);
                      // Newly authored slide — flag it for a vision critique.
                      return [...bumped, { ...newSlideData, elements: finalNewElements, critique_recommended: true }].sort((a, b) => a.order - b.order);
                    });
                    successCount++;
                  }
                } else if (event.type === 'complete') {
                  setAiChatMessages(prev => [...prev.slice(-29), {
                    id: chatMsgUid(),
                    text: totalMatched === 0 ? 'No slides matched your instruction. Try being more specific.'
                      : `Updated ${successCount} of ${totalMatched} relevant slides (out of ${aiSlides.length} total).`,
                    timestamp: new Date(), actionType: 'edit'
                  }]);
                } else if (event.type === 'error') {
                  if (event.status_code === 402) { authService.notifyCreditRequired(event.message); }
                  else { console.error('❌ [ORCHESTRATE_ALL] Stream error:', event.message); }
                }
              } catch (parseErr) { console.warn('⚠️ SSE parse:', parseErr); }
            }
          }
          // Process remaining buffer
          if (allBuffer.trim()?.startsWith('data: ')) {
            try {
              const event = JSON.parse(allBuffer.trim().slice(6));
              if (event.type === 'complete' && successCount === 0) {
                setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: 'No slides were relevant to your instruction.', timestamp: new Date(), actionType: 'info' }]);
              }
            } catch { }
          }

          // Wait for all parallel image generation to complete
          if (pendingImageTasks.length > 0) {
            console.log(`🖼️ [ORCHESTRATE_ALL] Waiting for ${pendingImageTasks.length} parallel image tasks...`);
            await Promise.all(pendingImageTasks);
            console.log(`✅ [ORCHESTRATE_ALL] All image tasks completed`);
          }

        } catch (error) {
          console.error('Orchestrate All Slides failed:', error);
          if (!isInsufficientCreditsError({ message: error.message })) {
            Alert.alert('Error', 'Failed to update all slides.');
          }
        } finally {
          setIsAutoUpdating(false);
          setIsAiProcessing(false);
          setAutoUpdateProgress({ current: 0, total: 0 });
        }
        return; // Exit function
      }

      // --- IMAGE INTERCEPT: If an image element is selected, use image generation for editing/generation ---
      if (selectedElement && selectedElement.type === 'image') {
        console.log('🖼️ [AI_CHAT_IMAGE] Image element selected, routing via image generation');

        try {
          const elementImageType = selectedElement.imageType || 'photo';
          const imgWidth = Math.round(selectedElement.width || 1024);
          const imgHeight = Math.round(selectedElement.height || 1024);

          // --- Detect intent: new image vs edit existing ---
          const promptLower = instruction.toLowerCase();
          const newImagePatterns = /\b(create|generate|make|new|replace\s+with|replace\s+this|swap|change\s+to|switch\s+to|turn\s+into|convert\s+to|transform\s+into|completely\s+new|brand\s+new|different\s+image|new\s+image|replace\s+image|fresh|from\s+scratch)\b/;
          const isNewImageIntent = newImagePatterns.test(promptLower);
          // Edit-like intents: adjust, tweak, brighten, darken, crop, resize, add text, remove bg, etc.
          const editImagePatterns = /\b(edit|adjust|tweak|brighten|darken|lighten|sharpen|blur|crop|resize|add|remove|enhance|improve|fix|increase|decrease|more|less|filter|saturat|contrast|warm|cool|tone|tint|overlay|rotate|flip|mirror)\b/;
          const isEditIntent = editImagePatterns.test(promptLower);

          // If both match, prefer edit (more specific); if neither, default to new image
          const shouldGenerateNew = isNewImageIntent && !isEditIntent;

          let imageResult;

          if (shouldGenerateNew) {
            // ---- GENERATE COMPLETELY NEW IMAGE (no seed) ----
            console.log('🖼️ [AI_CHAT_IMAGE] Intent: NEW IMAGE — generating via image generation (' + generationQuality + ')');
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
            console.log('🖼️ [AI_CHAT_IMAGE] Intent: EDIT — modifying existing image via image generation');

            // Get the image source - prefer original URL (high-res) over canvas export (low-res)
            // Canvas export renders at display size (e.g. 400x300) losing original resolution
            let imageSource = null;
            if (selectedElement.src) {
              imageSource = selectedElement.src;
              console.log('🖼️ [AI_CHAT_IMAGE] Using original image source (high quality)');
            }
            if (!imageSource && canvasRef.current?.getImageAsBase64) {
              try {
                imageSource = await canvasRef.current.getImageAsBase64(selectedElement.id);
                console.log('🖼️ [AI_CHAT_IMAGE] Fallback: using canvas export');
              } catch (canvasErr) {
                console.log('🖼️ [AI_CHAT_IMAGE] Canvas export failed (tainted canvas)');
              }
            }
            if (!imageSource) {
              throw new Error('Could not get image data. Cannot edit.');
            }

            console.log('🖼️ [AI_CHAT_IMAGE] Editing via image generation');
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
          updateElement(currentSlide.id, selectedElement.id, {
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

          const response = await fetch(`${apiConfig.API_URL}/presentation/generate-chart-data`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              chart_type: selectedChartEl.chartConfig?.type || 'bar',
              query: instruction,
              user_id: userDeviceId,
              folder_ids: finalFolderIds,
              // Pass context: slide title + CURRENT chart data
              page_context: {
                slide_title: currentSlide.title,
                target_chart_config: selectedChartEl.chartConfig
              },
              source_context: 'presentation_chart_edit',
            }),
          });

          const data = await response.json();

          if (response.status === 402 || handleCreditError(data)) {
            setIsAiProcessing(false);
            return;
          }

          if (data.success && data.chart_config) {
            console.log('✅ [AI_CHAT_CHART] Chart updated successfully');
            updateElement(currentSlide.id, selectedChartEl.id, {
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
      const { processedSlide, imageMap } = extractImagesFromSlide(targetSlide, selectedElementIds);
      const hasImages = Object.keys(imageMap).length > 0;

      let finalInstruction = instruction;
      if (hasImages) {
        finalInstruction += `\n\n[SYSTEM NOTE]: The slide JSON contains existing media with placeholder values.
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

      const goalString = extractGoalString(presentationGoal);
      console.log('🎯 [ORCHESTRATOR] Extracted goal string:', goalString);

      // Add user message to chat history
      if (!isBackground) {
        setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: instruction, timestamp: new Date(), actionType: 'user' }]);
      }

      const orchestrateResponse = await fetch(`${apiConfig.API_URL}/presentation/orchestrate-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          instruction: isBackground ? instruction : chatInput,
          slide_content: processedSlide,
          folder_ids: finalFolderIds,
          slide_id: targetSlide.id,
          style: presentationStyle,
          template_id: (presentationGoal?.deckProfile === 'general') ? null : (currentSlide.template || null),
          edit_mode: editMode,
          selected_elements: selectedElements.length > 0 ? selectedElements : null,
          presentation_goal: goalString,
          presentation_type: presentationGoal?.documentType || 'informative',
          icon_set: presentationStyle?.iconSet || 'lucide',
          generation_quality: generationQuality,
          user_edit_scope: editScope,
          slides_summary: buildSlidesSummary(slides.filter(s => !s.hidden)),
          deck_profile: presentationGoal?.deckProfile || 'corporate',
          deck_plan: presentationGoal?.deckPlan || null,
          ...(isBackground ? { fast_path: 'layout_fix' } : {}),
        }),
      });

      if (!orchestrateResponse.ok) {
        const errorData = await orchestrateResponse.json().catch(() => ({}));
        console.log('❌ [ORCHESTRATOR] Error response:', orchestrateResponse.status, JSON.stringify(errorData));
        if (isBackground) { console.warn('⚠️ [AUTO-LAYOUT-FIX] API error:', orchestrateResponse.status); return; }
        if (orchestrateResponse.status === 402) {
          authService.notifyCreditRequired(errorData.detail?.message || errorData.message || 'Insufficient credits.');
          setIsAiProcessing(false); return;
        }
        if (handleCreditError(errorData)) { setIsAiProcessing(false); return; }
        if (orchestrateResponse.status === 422) { throw new Error('Request validation failed. Please try again.'); }
        throw new Error(errorData.message || 'AI processing failed');
      }

      // --- SSE Stream processing for single-slide orchestrate ---
      const reader = orchestrateResponse.body.getReader();
      const decoder = new TextDecoder();
      let streamBuffer = '';

      const applyOrchResult = async (orchestrateData) => {
        const { intent, success, enhanced_slide: es, enhanced_element, enhanced_elements,
          chart_config, action_type, ai_message, new_slide, scope_escalated, scope_message } = orchestrateData;

        if (!success && handleCreditError(orchestrateData)) return;

        if (!isBackground && scope_escalated && scope_message) {
          setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: `🔄 ${scope_message}`, timestamp: new Date(), actionType: 'info' }]);
        }
        if (!isBackground && ai_message) {
          setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: ai_message, timestamp: new Date(), actionType: action_type || 'edit' }]);
        }

        // CREATE NEW SLIDE
        if (action_type === 'create_new' && new_slide) {
          const newSlideId = `slide_${Date.now()}_ai`;
          const currentIndex = slides.findIndex(s => s.id === currentSlideId);
          const newSlideOrder = currentIndex >= 0 ? currentIndex + 2 : slides.length + 1;
          const newSlideData = {
            id: newSlideId, order: newSlideOrder,
            title: new_slide.title || 'New Slide', layout: new_slide.layout || 'content',
            elements: new_slide.elements || [], backgroundColor: new_slide.backgroundColor || '#ffffff',
            notes: new_slide.notes || '', hasUnsavedChanges: true,
          };

          // Process slide through post-processor (normalize elements)
          const processedNew = await processSlideAsync(newSlideData);

          // Generate images for any image_placeholder elements
          const imagePlaceholders = (processedNew.elements || []).filter(el => el.type === 'image_placeholder');
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: presentationStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
          });

          // Safety net: catch any remaining type='image' elements without src (skip user-media)
          const safeElements = (processedNew.elements || []).map(el => {
            if (el.type === 'image' && !el.src && !el.isUserMedia) {
              console.warn(`⚠️ [CREATE_NEW] Image element ${el.id} still has no src — converting to shape`);
              return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
            }
            return el;
          });

          // Newly authored slide — flag it so the post-render callback runs a
          // vision critique on it, same as a slide from initial deck generation.
          const finalSlideData = { ...newSlideData, elements: safeElements, critique_recommended: true };
          const updatedSlides = slides.map(s => s.order >= newSlideOrder ? { ...s, order: s.order + 1 } : s);
          const allSlides = [...updatedSlides, finalSlideData].sort((a, b) => a.order - b.order);
          setSlides(allSlides);
          setCurrentSlideId(newSlideId);
          pendingLayoutFixRef.current.add(newSlideId);
          return;
        }

        // CHART
        if (chart_config) {
          if (canvasRef.current?.addChart) { canvasRef.current.addChart(chart_config); }
          return;
        }

        // ENHANCED SLIDE
        if (es) {
          let rawSlideData = es.slide || es;
          if (rawSlideData.type && !rawSlideData.elements) {
            const existingElements = targetSlide?.elements || [];
            const mi = existingElements.findIndex(el => el.id === rawSlideData.id);
            rawSlideData = mi >= 0
              ? { elements: existingElements.map((el, i) => i === mi ? { ...el, ...rawSlideData } : el) }
              : { elements: [...existingElements, rawSlideData] };
          }

          let restoredSlideData = restoreImagesToSlide(rawSlideData, imageMap);

          const processedSlideOutput = await processSlideAsync(restoredSlideData);

          const imagePlaceholders = (processedSlideOutput.elements || []).filter(el => el.type === 'image_placeholder');
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: presentationStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
          });

          // Safety net: catch any remaining type='image' elements without src (skip user-media)
          const finalElements = (processedSlideOutput.elements || []).map(el => {
            if (el.type === 'image' && !el.src && !el.isUserMedia) {
              console.warn(`⚠️ [ENHANCE] Image element ${el.id} still has no src after generation — converting to shape`);
              return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
            }
            return el;
          });

          const slideUpdate = { elements: finalElements };
          if (processedSlideOutput.backgroundColor) slideUpdate.backgroundColor = processedSlideOutput.backgroundColor;
          if (processedSlideOutput.title) slideUpdate.title = processedSlideOutput.title;
          if (processedSlideOutput.notes || processedSlideOutput.speaker_notes) slideUpdate.notes = processedSlideOutput.notes || processedSlideOutput.speaker_notes;
          if (processedSlideOutput.template || rawSlideData.template) slideUpdate.template = processedSlideOutput.template || rawSlideData.template;
          // Preserve outline: use backend value if returned, otherwise keep existing
          slideUpdate.outline = rawSlideData.outline || targetSlide.outline || targetSlide.sectionTopic || '';

          // An AI edit changed the slide's layout — flag it for a fresh vision
          // critique and clear the per-slide dedup guard so the post-render
          // callback re-critiques it (the guard is otherwise session-persistent,
          // which would skip critique on a second edit of the same slide).
          slideUpdate.critique_recommended = true;
          critiquedSlidesRef.current.delete(targetSlide.id);

          updateSlide(targetSlide.id, slideUpdate);
          if (isBackground) console.log(`✅ [AUTO-LAYOUT-FIX] Slide ${targetSlide.id} fixed`);
          return;
        }

        // SINGLE ELEMENT
        if (enhanced_element) {
          if (selectedElementId && currentSlide?.id) {
            // If enhanced_element is an image_placeholder, generate the actual image first
            if (enhanced_element.type === 'image_placeholder') {
              console.log('🖼️ [ENHANCED_ELEMENT] Image placeholder detected, generating image...');
              try {
                const placeholderImageType = enhanced_element.imageType || 'photo';
                let imageResult;
                imageResult = await ImageGenService.generateImage(
                  enhanced_element.imageDescription || 'Professional presentation image',
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
            const processed = await processSlideAsync({ elements: [enhanced_element] });
            const final_el = processed.elements?.[0] || enhanced_element;
            updateElement(currentSlide.id, final_el.id, final_el);
            // Element edit can introduce overlap — flag the slide for re-critique.
            updateSlide(currentSlide.id, { critique_recommended: true });
            critiquedSlidesRef.current.delete(currentSlide.id);
          }
          return;
        }

        // MULTI ELEMENTS
        if (enhanced_elements && Array.isArray(enhanced_elements)) {
          if (currentSlide?.id && enhanced_elements.length > 0) {
            const processed = await processSlideAsync({ elements: enhanced_elements });
            const processedEls = processed.elements || enhanced_elements;
            updateMultipleElements(currentSlide.id, processedEls.map(el => ({ elementId: el.id, updates: el })));
            // Multi-element edit can introduce overlap — flag the slide for re-critique.
            updateSlide(currentSlide.id, { critique_recommended: true });
            critiquedSlidesRef.current.delete(currentSlide.id);
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

      if (!isBackground) {
        setChatInput('');
      }
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

  }, [chatInput, isAiProcessing, currentSlide, currentSlideId, slides, setSlides, setCurrentSlideId, apiConfig, presentationStyle, userDeviceId, selectedFolders, updateSlide, editMode, selectedElement, selectedElementId, updateElement, updateMultipleElements, selectedElements, presentationGoal, getVisibleSlideId]);

  handleAiEnhanceRef.current = handleAiEnhance;

  const handleAgentEditRef = useRef(null);
  // Lets the user STOP an in-flight agent edit. Aborting the fetch breaks the
  // SSE read loop (the loop's reader.read() rejects) — already-applied op
  // batches stay on the deck; no further rounds are read.
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
      // Swap the trailing live "thinking" line for the Stopped note.
      if (prev.length > 0 && prev[prev.length - 1].actionType === 'thinking') {
        return [...prev.slice(0, -1), stopped];
      }
      return [...prev.slice(-29), stopped];
    });
  }, []);

  // ═══════════════════════════════════════════════════════════════════════
  // AGENTIC WHOLE-DECK EDITOR — "Claude on PowerPoint"
  // The ENTIRE deck + chat message go to the backend in one shot; the LLM
  // returns a list of operations (edit/add/delete/duplicate/reorder slide,
  // update style/header-footer/slide-numbers) which we apply here. No scope
  // selection — intent + target are auto-detected from the message.
  // ═══════════════════════════════════════════════════════════════════════

  // Apply a list of agent operations against the current deck. Handles image
  // generation for any image_placeholder elements the model emitted.
  // Applies a batch of agent operations and returns the new deck array. The
  // agent loop streams MULTIPLE batches per turn, so the caller threads the
  // returned array back in as `baseSlides` to avoid stale-closure loss.
  const applyAgentOperations = useCallback(async (operations, imageMapBySlide, baseSlides) => {
    const base = baseSlides || slides;
    if (!operations || operations.length === 0) return base;

    let working = base.map(s => ({ ...s }));

    const genImagesFor = async (elements) => {
      const placeholders = (elements || []).filter(el => el.type === 'image_placeholder');
      if (placeholders.length > 0) {
        await generateImagesParallel(placeholders, {
          generationQuality, style: presentationStyle?.name || 'professional',
          userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
        });
      }
      // Safety net: any leftover srcless image element becomes a neutral shape.
      return (elements || []).map(el => {
        if (el.type === 'image' && !el.src && !el.isUserMedia) {
          return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
        }
        return el;
      });
    };

    // Restore images (markers → src), normalize, then generate any new images.
    // The image map MUST be scoped to the target slide — restoreImagesToSlide
    // has a deck-agnostic safety net that would otherwise re-inject other
    // slides' user media into this one.
    // fallbackBg: the slide's REAL background (slide bg → deck style bg — the
    // same chain the canvas renders with). update_elements ops never carry
    // backgroundColor and edit_slide ops usually omit it, so without this the
    // post-processor resolves the background to '#FFFFFF' and its contrast
    // passes flip perfectly-readable white text on dark slides to
    // #1F2937/#111827 — invisible on the actually-dark slide.
    const buildSlideFromOp = async (op, slideImageMap, fallbackBg) => {
      const restored = restoreImagesToSlide(
        { elements: op.elements || [], backgroundColor: op.backgroundColor || fallbackBg }, slideImageMap || {},
      );
      const processed = await processSlideAsync(restored);
      const finalElements = await genImagesFor(processed.elements);
      return { elements: finalElements, backgroundColor: op.backgroundColor };
    };

    const newId = (tag) => `slide_${Date.now()}_${Math.random().toString(36).slice(2, 7)}_${tag}`;

    for (const op of operations) {
      try {
        if (op.op === 'edit_slide') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          const built = await buildSlideFromOp(
            op,
            { ...(imageMapBySlide.__deckMedia || {}), ...(imageMapBySlide[op.slide_id] || {}) },
            working[idx].backgroundColor || presentationStyle?.slideBackground,
          );
          const update = { ...working[idx], elements: built.elements, critique_recommended: true, hasUnsavedChanges: true };
          if (op.title) update.title = op.title;
          if (op.outline) update.outline = op.outline;
          if (built.backgroundColor) update.backgroundColor = built.backgroundColor;
          working[idx] = update;
          critiquedSlidesRef.current?.delete?.(op.slide_id);
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
            ? (await buildSlideFromOp(
                { elements: merged },
                { ...(imageMapBySlide.__deckMedia || {}), ...(imageMapBySlide[op.slide_id] || {}) },
                working[idx].backgroundColor || presentationStyle?.slideBackground,
              )).elements
            : merged;
          const update = { ...working[idx], elements: finalElements, critique_recommended: true, hasUnsavedChanges: true };
          if (op.title) update.title = op.title;
          working[idx] = update;
          critiquedSlidesRef.current?.delete?.(op.slide_id);
        } else if (op.op === 'remove_elements') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          const rm = new Set(op.element_ids || []);
          working[idx] = {
            ...working[idx],
            elements: (working[idx].elements || []).filter(e => !rm.has(e.id)),
            critique_recommended: true, hasUnsavedChanges: true,
          };
          critiquedSlidesRef.current?.delete?.(op.slide_id);
        } else if (op.op === 'add_slide') {
          const built = await buildSlideFromOp(op, imageMapBySlide.__deckMedia || {}); // new slide — deck media fallback resolves moved markers
          const slide = {
            id: op.id || newId('new'), title: op.title || 'New Slide', layout: op.layout || 'content',
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
            const ci = working.findIndex(s => s.id === currentSlideId);
            insertAt = ci >= 0 ? ci + 1 : working.length;
          }
          working.splice(insertAt, 0, slide);
          pendingLayoutFixRef.current?.add?.(slide.id);
        } else if (op.op === 'delete_slide') {
          if (working.length <= 1) continue; // never leave an empty deck
          working = working.filter(s => s.id !== op.slide_id);
        } else if (op.op === 'duplicate_slide') {
          const idx = working.findIndex(s => s.id === op.slide_id);
          if (idx < 0) continue;
          // DEEP-COPY the elements: a spread would share the element OBJECTS with
          // the source slide, and the post-processor mutates elements in place —
          // a later edit to either slide would then corrupt the other (same class
          // of bug as the backend duplicate_slide deepcopy fix).
          const dup = {
            ...working[idx],
            id: op.new_id || newId('dup'),
            elements: JSON.parse(JSON.stringify(working[idx].elements || [])),
            hasUnsavedChanges: true,
          };
          // The dup shares the source's image markers — alias its map so a later
          // edit op targeting the dup can still resolve {{UserMedia_*}}/_orig_ keys.
          if (imageMapBySlide && imageMapBySlide[op.slide_id]) {
            imageMapBySlide[dup.id] = imageMapBySlide[op.slide_id];
          }
          working.splice(idx + 1, 0, dup);
        } else if (op.op === 'reorder_slides') {
          const byId = {};
          working.forEach(s => { byId[s.id] = s; });
          const ordered = (op.order || []).map(id => byId[id]).filter(Boolean);
          working.forEach(s => { if (!(op.order || []).includes(s.id)) ordered.push(s); });
          if (ordered.length === working.length) working = ordered;
        } else if (op.op === 'update_style') {
          if (op.style && typeof op.style === 'object') setPresentationStyle(prev => ({ ...prev, ...op.style }));
        } else if (op.op === 'update_header_footer') {
          if (op.header_footer && typeof op.header_footer === 'object') setHeaderFooter(prev => ({ ...prev, ...op.header_footer }));
        } else if (op.op === 'update_slide_numbers') {
          if (op.slide_numbers && typeof op.slide_numbers === 'object') setSlideNumbers(prev => ({ ...prev, ...op.slide_numbers }));
        }
      } catch (opErr) {
        console.error('❌ [AGENT-EDIT] operation failed:', op?.op, opErr);
      }
    }

    // Re-sequence order so navigation/thumbnails stay consistent.
    working = working.map((s, i) => ({ ...s, order: i + 1 }));
    setSlides(working);
    return working;
  }, [slides, currentSlideId, generationQuality, presentationStyle, userDeviceId, handleCreditError, setSlides]);

  // Chat entry point. Media-element edits (image pixels, chart data, video) that
  // the LLM cannot synthesize stay on the legacy element handler; everything
  // else goes agentic over the whole deck.
  const handleAgentEdit = useCallback(async (overrideInstruction) => {
    const typedInstruction = (typeof overrideInstruction === 'string' ? overrideInstruction : chatInput).trim();
    // Allow a paste-only send (screenshot, no text) — fall back to a default
    // ask so the agent still acts on the attached image.
    const imagesForSend = aiPastedImages;
    const instruction = typedInstruction || (imagesForSend.length > 0 ? 'Use the attached screenshot(s) as reference for this edit.' : '');
    if ((!instruction) || isAiProcessing || isAiLocked) return;

    // Route pixel/chart/video work to the element-aware legacy handler.
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

      // Build the whole-deck payload — extract images to markers per slide and
      // keep each slide's image map SEPARATE (keyed by slide id) so restore stays
      // slide-scoped (see buildSlideFromOp). __deckMedia holds ONLY the direct
      // UserMedia_* marker→src entries (no _orig_ backups, so the restore
      // safety-net can't re-inject other slides' media) as a deck-wide fallback
      // for markers the agent moves onto a different or new slide.
      const imageMapBySlide = {};
      const deckMediaMap = {};
      const payloadSlides = slides.map(s => {
        const { processedSlide, imageMap } = extractImagesFromSlide(s);
        imageMapBySlide[s.id] = imageMap;
        Object.keys(imageMap).forEach(k => { if (k.startsWith('UserMedia_')) deckMediaMap[k] = imageMap[k]; });
        // Strip base64 thumbnails — backend drops them before prompting anyway,
        // no reason to ship them over the wire.
        const { slideThumbnail, thumbnail, ...rest } = processedSlide;
        return { ...rest, id: s.id };
      });
      imageMapBySlide.__deckMedia = deckMediaMap;

      const extractGoalString = (g) => !g ? null : (typeof g === 'string' ? g : (g.purpose ? extractGoalString(g.purpose) : null));
      const finalFolderIds = useUploadedData && selectedFolders.length > 0 ? selectedFolders.map(f => f.id || f) : [];
      // Auto-detect the slide the user is ACTUALLY looking at (scroll position),
      // so "this slide" in chat resolves correctly even before a click.
      const visibleId = getVisibleSlideId?.() || currentSlideId;
      if (visibleId && visibleId !== currentSlideId) setCurrentSlideId(visibleId);
      const currentIndex = Math.max(0, slides.findIndex(s => s.id === visibleId));
      // Skip transient 'thinking' lines — send real conversation turns only, so
      // a prior review's suggestions survive into the next turn ("yes, do it").
      const recentHistory = aiChatMessages
        .filter(m => m.actionType !== 'thinking')
        .slice(-6)
        .map(m => ({ role: m.actionType === 'user' ? 'user' : 'assistant', text: m.text }));

      // Transient 'thinking' line — replaced in place by the agent's live
      // reasoning (see the 'status' handler) and excluded from chat history.
      setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: `Looking at your ${slides.length} slides…`, timestamp: new Date(), actionType: 'thinking' }]);

      const abortController = new AbortController();
      agentAbortRef.current = abortController;
      const response = await fetch(`${apiConfig.API_URL}/presentation/agent-edit-stream`, {
        method: 'POST',
        signal: abortController.signal,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          instruction,
          slides: payloadSlides,
          current_slide_index: currentIndex,
          style: presentationStyle,
          header_footer: headerFooter,
          slide_numbers: slideNumbers,
          presentation_goal: extractGoalString(presentationGoal),
          presentation_type: presentationGoal?.documentType || 'informative',
          chat_history: recentHistory,
          folder_ids: finalFolderIds,
          // Screenshots pasted into the chat — OCR'd server-side and prepended
          // to the instruction context. Separate from slide media (image_placeholder).
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
      let liveDeck = slides.map(s => ({ ...s }));

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
          // Raw server payload dump — when an apply corrupts a slide, this is
          // the ground truth for whether the ops even touched the elements
          // that changed (frontend pipeline bug) or carried bad values
          // (backend emit bug). Keep: ops are small, corruption is rare.
          console.log('📥 [AGENT-EDIT] raw operations:', JSON.stringify(event.operations));
          if (event.chat_message) {
            setAiChatMessages(prev => [...prev.slice(-29), { id: chatMsgUid(), text: event.chat_message, timestamp: new Date(), actionType: 'edit' }]);
          }
          liveDeck = await applyAgentOperations(event.operations || [], imageMapBySlide, liveDeck);
        } else if (event.type === 'ask_user') {
          // Clarifying question — show it with clickable quick-reply chips.
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
  }, [chatInput, aiPastedImages, isAiProcessing, isAiLocked, slides, currentSlideId, setCurrentSlideId, getVisibleSlideId, apiConfig, presentationStyle, headerFooter, slideNumbers, presentationGoal, userDeviceId, selectedFolders, useUploadedData, aiChatMessages, applyAgentOperations, handleCreditError, selectedElement, selectedElements, selectedElementIds]);

  handleAgentEditRef.current = handleAgentEdit;

  // Capture screenshots pasted into the AI chat (web). Gated on the chat input
  // being focused so it never hijacks pastes elsewhere on the page.
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
  //     const layoutFixInstruction = `Fix layout and overlapping issues on this slide.
  //
  // CANVAS: 960×540 pixels (16:9). ABSOLUTE BOUNDS: Every element must satisfy x ≥ 20, y ≥ 20, x+width ≤ 920, y+height ≤ 520. NO EXCEPTIONS — nothing may extend below y+height=520 or past x+width=920.
  //
  // PRIORITY (highest first):
  // 1. BOUNDS — every element fully inside the safe area. This overrides everything else.
  // 2. NO OVERLAPS — at least 8px gap between ALL element bounding boxes. This includes images, cards, text, shapes, icons — EVERY element type. Two elements overlap if their rectangles (x,y,width,height) intersect. Check EVERY pair.
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
  // Keep the same design, colors, and style. Return the full slide JSON.`;
  //     for (const id of ids) {
  //       const slide = slides.find(s => s.id === id);
  //       if (slide) {
  //         handleAiEnhanceRef.current?.(layoutFixInstruction, slide, true);
  //       }
  //     }
  //   }
  // }, [slides]);


  // Create new presentation
  const handleCreateNew = useCallback(() => {
    if (onClearPresentation) {
      onClearPresentation();
    }
    setSlides([{
      id: `slide_${Date.now()}`,
      order: 1,
      title: 'Title Slide',
      layout: 'title',
      elements: [],
      backgroundColor: '#ffffff',
      hasUnsavedChanges: false,
    }]);
    setCurrentPresentationId(null);
    setPresentationTitle('Untitled Presentation');
    setPresentationGoal(null);
    setPresentationStyle(PRESET_STYLES[0]);
    setHeaderFooter(DEFAULT_HEADER_FOOTER);
    setSlideNumbers(DEFAULT_SLIDE_NUMBERS);
    setShowGoalSetting(true);

    // Clear cached thumbnails and tracking for new presentation
    setSlideThumbnails({});
    initialThumbnailGeneratedRef.current.clear();
    critiquedSlidesRef.current.clear();
    inFlightCritiquesRef.current.clear();
  }, [setSlides, onClearPresentation]);

  // Generate thumbnail from first slide
  const generateThumbnail = useCallback(async () => {
    try {
      if (canvasRef.current && canvasRef.current.toDataURL) {
        // Use the canvas toDataURL method to capture current slide
        const dataUrl = await canvasRef.current.toDataURL({ format: 'jpeg', quality: 0.6 });
        // console.log('📸 [SAVE] Generated presentation thumbnail');
        return dataUrl;
      }
    } catch (err) {
      console.warn('📸 [SAVE] Failed to generate thumbnail:', err);
    }
    return null;
  }, []);

  // Vision-critique pass for a single slide. Snapshots the rendered fabric
  // canvas, POSTs to /presentation/critique-slide, and swaps the slide's
  // elements with the patched list when the server returns ≥1 applied patch.
  // Idempotent — guarded by critiquedSlidesRef so the same slide isn't
  // critiqued twice (canvas-render-complete can fire multiple times during
  // image loads).
  const runVisualCritique = useCallback(async (slideId) => {
    try {
      // Server said critique is disabled (CRITIC_VISION_ENABLED=false) — stop
      // POSTing full slide payloads it will just no-op. Latched per session.
      if (critiqueDisabledRef.current) return;
      const canvasRefHandle = canvasRefsMap.current.get(slideId);
      const canvasInstance = canvasRefHandle?.current;
      if (!canvasInstance?.snapshotForCritique) {
        // Canvas ref not ready or older build without the method — skip silently
        return;
      }
      const screenshot = canvasInstance.snapshotForCritique();
      if (!screenshot) return;

      const slide = slides.find(s => s.id === slideId);
      if (!slide || !Array.isArray(slide.elements) || slide.elements.length === 0) return;

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) return;

      console.log(`🖼️ [CRITIQUE] Sending slide ${slideId} for vision review (${slide.elements.length} elements)`);

      const response = await fetch(`${apiConfig.API_URL}/presentation/critique-slide`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          elements: slide.elements,
          screenshot,
          slide_info: { title: slide.title || '', content_hint: slide.outline || '' },
          canvas: { width: SLIDE_WIDTH, height: SLIDE_HEIGHT },
        }),
      });

      if (!response.ok) {
        console.warn(`🖼️ [CRITIQUE] Server returned ${response.status} for slide ${slideId}`);
        critiquedSlidesRef.current.add(slideId); // don't retry — server is unhappy
        return;
      }

      const result = await response.json();
      if (typeof result?.note === 'string' && result.note.includes('critique disabled')) {
        console.log('🖼️ [CRITIQUE] Disabled on server — skipping all further critique calls this session');
        critiqueDisabledRef.current = true;
        return;
      }
      const applied = result?.patches_applied || 0;
      const issues = result?.issues || [];
      console.log(`🖼️ [CRITIQUE] Slide ${slideId}: ${issues.length} issues, ${applied} patches applied`);

      if (applied > 0 && Array.isArray(result.elements)) {
        // Swap the patched elements into the slide. We replace the whole list
        // because the critique can add/delete/modify; partial merging would
        // miss deletions and re-introduce overlap.
        setSlides(prev => prev.map(s => (s.id === slideId ? { ...s, elements: result.elements } : s)));
        // Force a thumbnail re-render after the patch lands. We clear the
        // initial-thumbnail flag so the debounced regeneration effect picks
        // up the new elements on the next render cycle.
        initialThumbnailGeneratedRef.current.delete(slideId);
      }

      critiquedSlidesRef.current.add(slideId);
    } catch (err) {
      console.warn(`🖼️ [CRITIQUE] Failed for slide ${slideId}:`, err);
      // Mark as critiqued anyway so we don't retry on every render
      critiquedSlidesRef.current.add(slideId);
    }
  }, [slides, setSlides, apiConfig]);

  // Deck-complete parallel critique flush.
  //
  // Per-slide critique is also fired from handleCanvasRenderComplete as each
  // canvas finishes rendering, but during a fresh deck generation that
  // callback can fire before the slide's images have settled or before the
  // canvas is even mounted (offscreen slides). When the deck flips from
  // generating → complete, fire critique for every slide that hasn't been
  // critiqued yet IN PARALLEL via Promise.all — they run truly concurrently
  // server-side and don't block each other on the client.
  const prevIsGeneratingRef = useRef(false);
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const wasGenerating = prevIsGeneratingRef.current;
    prevIsGeneratingRef.current = isGeneratingSlides;
    if (!wasGenerating || isGeneratingSlides) return; // only fire on true→false edge

    const slidesToCritique = slides.filter(
      (s) =>
        s &&
        s.critique_recommended === true &&
        !critiquedSlidesRef.current.has(s.id) &&
        !inFlightCritiquesRef.current.has(s.id)
    );
    if (slidesToCritique.length === 0) return;

    console.log(`🖼️ [CRITIQUE] Deck complete — flushing critique for ${slidesToCritique.length} slide(s) in parallel`);
    slidesToCritique.forEach((s) => inFlightCritiquesRef.current.add(s.id));
    Promise.all(
      slidesToCritique.map(async (s) => {
        try {
          await waitForCanvasImages(s, 5000);
          await new Promise((r) => setTimeout(r, 150));
          // Vision critique DISABLED (CRITIC_VISION_ENABLED=false in prod, and
          // the per-slide POSTs are pure waste). Uncomment to re-enable.
          // await runVisualCritique(s.id);
        } finally {
          inFlightCritiquesRef.current.delete(s.id);
        }
      })
    );
  }, [isGeneratingSlides, slides, runVisualCritique, waitForCanvasImages]);

  // Callback when canvas finishes rendering - generate thumbnail after images load
  const handleCanvasRenderComplete = useCallback((slideId) => {
    if (!slideId || Platform.OS !== 'web') return;

    const slide = slides.find(s => s.id === slideId);

    // Vision-critique pass — MUST run before the isGeneratingSlides gate
    // below. During initial deck generation that flag stays true until the
    // last slide completes, so gating critique on it suppresses critique
    // for every slide in the deck (it fires per-slide canvas-render, and
    // by the time the flag flips false those callbacks won't re-fire).
    // Each critique is independent and fire-and-forget, so it's safe to
    // run while other slides are still generating server-side.
    if (
      slide &&
      slide.critique_recommended === true &&
      !critiquedSlidesRef.current.has(slideId) &&
      !inFlightCritiquesRef.current.has(slideId)
    ) {
      inFlightCritiquesRef.current.add(slideId);
      // Defer: wait for image loads + a paint tick so the snapshot
      // captures the fully-rendered slide (otherwise the vision model
      // sees blank image placeholders).
      (async () => {
        try {
          await waitForCanvasImages(slide, 5000);
          await new Promise(r => setTimeout(r, 150));
          // Vision critique DISABLED (CRITIC_VISION_ENABLED=false in prod, and
          // the per-slide POSTs are pure waste). Uncomment to re-enable.
          // await runVisualCritique(slideId);
        } finally {
          inFlightCritiquesRef.current.delete(slideId);
        }
      })();
    }

    // Skip thumbnail generation while AI is actively generating/editing slides
    if (isGeneratingSlidesRef.current || isAutoUpdatingRef.current || isAiProcessingRef.current) return;

    // Skip if we already successfully generated thumbnail for this slide
    if (initialThumbnailGeneratedRef.current.has(slideId)) return;

    const capture = async () => {
      if (slide) await waitForCanvasImages(slide, 5000);
      // Extra delay for final paint
      await new Promise(r => setTimeout(r, 150));
      generateSlideThumbnail(slideId, true);
    };
    capture();
  }, [generateSlideThumbnail, slides, waitForCanvasImages, runVisualCritique]);

  // Debounced effect to regenerate thumbnail when content changes (after initial generation)
  useEffect(() => {
    if (!currentSlideId || Platform.OS !== 'web') return;

    // Skip thumbnail regeneration while AI is actively generating/editing slides
    if (isGeneratingSlides || isAutoUpdating || isAiProcessing) return;

    // Skip if no thumbnail exists yet (canvas render complete callback handles it)
    if (!initialThumbnailGeneratedRef.current.has(currentSlideId)) return;

    // Clear any pending thumbnail generation
    if (thumbnailGenerationRef.current) {
      clearTimeout(thumbnailGenerationRef.current);
    }

    // Debounce thumbnail regeneration for content changes
    thumbnailGenerationRef.current = setTimeout(() => {
      generateSlideThumbnail(currentSlideId, false);
    }, 500);

    return () => {
      if (thumbnailGenerationRef.current) {
        clearTimeout(thumbnailGenerationRef.current);
      }
    };
  }, [currentSlideId, currentSlide, generateSlideThumbnail, isGeneratingSlides, isAutoUpdating, isAiProcessing]);

  // Background thumbnail queue: after initial slide renders, generate thumbnails for remaining slides
  useEffect(() => {
    if (Platform.OS !== 'web' || !currentSlideId || slides.length <= 1) return;

    // Don't start thumbnail queue while AI is actively generating/editing slides
    if (isGeneratingSlides || isAutoUpdating || isAiProcessing) return;

    // Don't restart if queue is already running
    if (thumbnailQueueStartedRef.current) return;

    // Wait until first slide has been rendered and captured
    if (!initialThumbnailGeneratedRef.current.has(currentSlideId)) return;

    // Find slides that still have no thumbnail
    const missingSlides = slides.filter(
      s => !initialThumbnailGeneratedRef.current.has(s.id)
    );

    if (missingSlides.length === 0) return;

    // Mark queue as started to prevent re-triggering
    thumbnailQueueStartedRef.current = true;

    // Abort any previous queue
    if (backgroundThumbnailQueueRef.current) {
      backgroundThumbnailQueueRef.current.aborted = true;
    }

    const queueState = { aborted: false };
    backgroundThumbnailQueueRef.current = queueState;

    // console.log('📸 [THUMBNAIL-QUEUE] Starting background generation for', missingSlides.length, 'slides');

    const runQueue = async () => {
      setIsGeneratingThumbnails(true);
      try {
        for (const slide of missingSlides) {
          if (queueState.aborted) {
            // console.log('📸 [THUMBNAIL-QUEUE] Aborted');
            return;
          }

          // In multi-canvas mode, all slides are already rendered — just wait for images and capture
          await waitForCanvasImages(slide, 5000);
          if (queueState.aborted) return;

          // Small extra delay for final paint
          await new Promise(resolve => setTimeout(resolve, 150));
          if (queueState.aborted) return;

          // Capture thumbnail directly from the slide's canvas ref
          await generateSlideThumbnail(slide.id, true);
        }
      } finally {
        setIsGeneratingThumbnails(false);
        thumbnailQueueStartedRef.current = false;
      }
    };

    // Small delay before starting queue to let the UI settle
    setTimeout(runQueue, 500);
    // Queue runs uninterrupted — abort only on new document load via backgroundThumbnailQueueRef
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slides.length, slideThumbnails, currentSlideId, isGeneratingSlides, isAutoUpdating, isAiProcessing]);

  // Save presentation
  const handleSave = useCallback(async () => {
    // GUARD: Read-only users cannot save
    if (isReadOnly) {
      Alert.alert('View Only', 'You have read-only access to this presentation.');
      return;
    }

    setIsSavingManual(true);
    try {
      // Generate thumbnail from current (first) slide
      let thumbnail = null;
      if (slides.length > 0) {
        // Temporarily switch to first slide for thumbnail if not already there
        const wasFirstSlide = currentSlideId === slides[0]?.id;
        if (!wasFirstSlide) {
          setCurrentSlideId(slides[0]?.id);
          // Small delay to allow canvas to render first slide
          await new Promise(resolve => setTimeout(resolve, 300));
        }
        thumbnail = await generateThumbnail();
        if (!wasFirstSlide) {
          // Switch back to original slide
          setCurrentSlideId(currentSlideId);
        }
      }

      // CRITICAL: Hydrate icons with SVG paths before saving
      // The backend needs svgPath to upload to S3, but local state might only have iconName
      const hydratedSlides = await Promise.all(slides.map(async (slide) => {
        if (!slide.elements) return slide;

        const hydratedElements = await Promise.all(slide.elements.map(async (element) => {
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

        return { ...slide, elements: hydratedElements };
      }));

      // Attach per-slide thumbnails for persistence (restored on next load)
      const slidesWithThumbnails = hydratedSlides.map(slide => ({
        ...slide,
        slideThumbnail: slideThumbnails[slide.id] || slide.slideThumbnail || null,
      }));

      // Save to server with thumbnail
      const saveResult = await savePresentationToServer({
        presentationMetadata: {
          id: currentPresentationId,
          title: presentationTitle,
          style: { ...presentationStyle, headerFooter, slideNumbers },
        },
        slides: slidesWithThumbnails,
        presentationGoal,
        thumbnail, // Include thumbnail for presentation list
        folderIds: selectedFolders.map(f => f.id || f),
      }, userDeviceId, apiConfig, currentPresentationId);

      const savedId = saveResult?.id || saveResult;

      // Update ID if this was a new presentation
      if (savedId) {
        setCurrentPresentationId(savedId);
      }

      // Update local slides with server-persisted URLs (S3 presigned) to avoid re-uploading on next save
      if (saveResult?.slides) {
        setSlides(prevSlides => {
          return prevSlides.map(localSlide => {
            const serverSlide = saveResult.slides.find(
              (ss, idx) => ss.id === localSlide.id || idx === prevSlides.indexOf(localSlide)
            );
            if (!serverSlide) return localSlide;

            // Update backgroundImage if server has it
            const updatedSlide = { ...localSlide };
            if (serverSlide.backgroundImage) {
              updatedSlide.backgroundImage = serverSlide.backgroundImage;
            }

            // Merge element URLs from server response
            if (serverSlide.elements && localSlide.elements) {
              updatedSlide.elements = localSlide.elements.map(localEl => {
                const serverEl = serverSlide.elements.find(se => se.id === localEl.id);
                if (!serverEl) return localEl;

                const merged = { ...localEl };
                // Update image src
                if (serverEl.src && localEl.type === 'image') {
                  merged.src = serverEl.src;
                }
                // Update icon svgSrc
                if (serverEl.svgSrc && localEl.type === 'icon') {
                  merged.svgSrc = serverEl.svgSrc;
                }
                // Update video src
                if (serverEl.src && localEl.type === 'video') {
                  merged.src = serverEl.src;
                }
                return merged;
              });
            }
            return updatedSlide;
          });
        });
      }

      // Also save locally as backup
      await savePresentation({
        id: savedId || currentPresentationId,
        slides: hydratedSlides,
        title: presentationTitle,
        goal: presentationGoal,
        style: { ...presentationStyle, headerFooter, slideNumbers },
      });

      isDirtyRef.current = false; // saved — clear the unsaved-changes flag
      Alert.alert('Saved', 'Presentation saved successfully.');
    } catch (error) {
      console.error('Failed to save presentation:', error);
      Alert.alert('Error', 'Failed to save presentation.');
    } finally {
      setIsSavingManual(false);
    }
  }, [savePresentationToServer, savePresentation, currentPresentationId, slides, presentationTitle, presentationGoal, presentationStyle, userDeviceId, apiConfig, generateThumbnail, currentSlideId, setCurrentSlideId, isReadOnly]);

  // PowerPoint-parity keyboard (web): Ctrl+S performs a real app save (the canvas
  // layer already suppresses the browser save dialog but saves nothing), and
  // PgUp/PgDn navigate between slides like PPT. Inputs keep PgUp/PgDn for scrolling.
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
        const visibleId = getVisibleSlideId?.() || currentSlideId;
        const idx = Math.max(0, slides.findIndex(s => s.id === visibleId));
        const next = e.key === 'PageDown' ? Math.min(slides.length - 1, idx + 1) : Math.max(0, idx - 1);
        if (next !== idx && slides[next]) {
          setCurrentSlideId(slides[next].id);
          scrollToSlide(slides[next].id, true);
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handleSave, isSavingManual, isReadOnly, slides, currentSlideId, getVisibleSlideId, scrollToSlide, setCurrentSlideId]);

  // Unsaved-changes tracking: any content change after the initial load marks the
  // deck dirty; a successful save clears it (see handleSave). While a load is in
  // flight the tracker is DISARMED so hydration doesn't count as an edit.
  useEffect(() => {
    if (isLoadingPresentation) {
      dirtyTrackingArmedRef.current = false;
      isDirtyRef.current = false;
      return;
    }
    if (!dirtyTrackingArmedRef.current) {
      dirtyTrackingArmedRef.current = true; // first clean render after mount/load
      return;
    }
    isDirtyRef.current = true;
  }, [slides, presentationStyle, presentationTitle, headerFooter, slideNumbers, isLoadingPresentation]);

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
      // Generate thumbnail from first slide
      let thumbnail = null;
      if (slides.length > 0) {
        const wasFirstSlide = currentSlideId === slides[0]?.id;
        if (!wasFirstSlide) {
          setCurrentSlideId(slides[0]?.id);
          await new Promise(resolve => setTimeout(resolve, 300));
        }
        thumbnail = await generateThumbnail();
        if (!wasFirstSlide) {
          setCurrentSlideId(currentSlideId);
        }
      }

      // Hydrate icons with SVG paths before saving
      const hydratedSlides = await Promise.all(slides.map(async (slide) => {
        if (!slide.elements) return slide;
        const hydratedElements = await Promise.all(slide.elements.map(async (element) => {
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
        return { ...slide, elements: hydratedElements };
      }));

      const slidesWithThumbnails = hydratedSlides.map(slide => ({
        ...slide,
        slideThumbnail: slideThumbnails[slide.id] || slide.slideThumbnail || null,
      }));

      const copyTitle = presentationTitle.endsWith(' (Copy)') ? presentationTitle : `${presentationTitle} (Copy)`;

      // Save with id: null to force creation of a new document
      const saveResult = await savePresentationToServer({
        presentationMetadata: {
          id: null,
          title: copyTitle,
          style: { ...presentationStyle, headerFooter, slideNumbers },
        },
        slides: slidesWithThumbnails,
        presentationGoal,
        thumbnail,
      }, userDeviceId, apiConfig, null);

      const savedId = saveResult?.id || saveResult;

      if (savedId) {
        // Switch UI to the new copy
        setCurrentPresentationId(savedId);
        setPresentationTitle(copyTitle);
        if (Platform.OS === 'web') navigateToPresentation(savedId);
      }

      // Update local slides with server-persisted URLs
      if (saveResult?.slides) {
        setSlides(prevSlides => {
          return prevSlides.map(localSlide => {
            const serverSlide = saveResult.slides.find(
              (ss, idx) => ss.id === localSlide.id || idx === prevSlides.indexOf(localSlide)
            );
            if (!serverSlide) return localSlide;
            const updatedSlide = { ...localSlide };
            if (serverSlide.backgroundImage) updatedSlide.backgroundImage = serverSlide.backgroundImage;
            if (serverSlide.elements && localSlide.elements) {
              updatedSlide.elements = localSlide.elements.map(localEl => {
                const serverEl = serverSlide.elements.find(se => se.id === localEl.id);
                if (!serverEl) return localEl;
                const merged = { ...localEl };
                if (serverEl.src && localEl.type === 'image') merged.src = serverEl.src;
                if (serverEl.svgSrc && localEl.type === 'icon') merged.svgSrc = serverEl.svgSrc;
                if (serverEl.src && localEl.type === 'video') merged.src = serverEl.src;
                return merged;
              });
            }
            return updatedSlide;
          });
        });
      }

      Alert.alert('Saved', 'A copy has been created. You are now editing the new copy.');
    } catch (error) {
      console.error('Failed to save presentation copy:', error);
      Alert.alert('Error', 'Failed to save copy.');
    } finally {
      setIsSavingManual(false);
    }
  }, [savePresentationToServer, currentPresentationId, slides, presentationTitle, presentationGoal, presentationStyle, userDeviceId, apiConfig, generateThumbnail, currentSlideId, setCurrentSlideId, slideThumbnails]);

  // Build outline data from current slides for the Update All modal
  const currentOutlineData = useMemo(() => {
    return slides.map((slide, index) => {
      let outline = slide.outline || slide.sectionTopic || '';
      // Fallback: extract text from elements for old presentations without outline
      if (!outline && slide.elements) {
        const textParts = slide.elements
          .filter(el => el.type === 'text' && (el.content || el.text))
          .map(el => (el.content || el.text || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim())
          .filter(Boolean);
        outline = textParts.join(' | ').slice(0, 200);
      }
      return {
        slideIndex: index,
        title: slide.title || `Slide ${index + 1}`,
        outline,
      };
    });
  }, [slides]);

  // Refresh outline using AI - regenerates outline suggestions based on goal + vault
  const handleRefreshOutline = useCallback(async (editedGoal, currentOutline) => {
    setIsRefreshingOutline(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) return null;

      const finalFolderIds = useUploadedData && selectedFolders.length > 0
        ? selectedFolders.map(f => f.id || f)
        : [];

      const response = await fetch(`${apiConfig.API_URL}/presentation/generate-outline-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          goal: editedGoal || presentationGoal?.purpose || '',
          presentation_type: presentationGoal?.documentType || 'general',
          target_audience: presentationGoal?.targetAudience || '',
          slide_count: currentOutline?.length || slides.length,
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
      const streamedSlides = [];
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
              } else if (data.type === 'slide') {
                streamedSlides.push({
                  slideIndex: data.slide?.original_id != null ? data.slide.original_id - 1 : data.index,
                  title: data.slide?.title || `Slide ${data.index + 1}`,
                  outline: data.slide?.outline || data.slide?.content_hint || '',
                });
              }
            } catch (e) {
              // skip parse errors
            }
          }
        }
      }

      if (streamedSlides.length > 0) {
        return { topic: suggestedTopic || editedGoal, outline: streamedSlides };
      }
      return null;
    } catch (error) {
      console.error('Failed to refresh outline:', error);
      return null;
    } finally {
      setIsRefreshingOutline(false);
    }
  }, [apiConfig, useUploadedData, selectedFolders, presentationGoal, slides.length]);

  // Auto Update - Refresh all slides with latest vault data
  // Auto Update - Step 1: Show Instruction Modal
  const handleAutoUpdate = useCallback(() => {
    if (isAutoUpdating) return;

    if (isDocumentLocked) {
      Alert.alert('Document Locked', `Locked by ${documentLockedBy?.name || 'another user'}.`);
      return;
    }

    if (slides.length === 0) {
      Alert.alert('Empty', 'No slides to update.');
      return;
    }

    setShowUpdateInstructionModal(true);
  }, [isAutoUpdating, isDocumentLocked, documentLockedBy, slides.length]);

  // Auto Update - Step 2: Execute Update with Instruction (Smart orchestrate-all path)
  const handleConfirmUpdate = useCallback(async ({ instruction, updatedGoal, updatedOutline, outlineChanged }) => {
    if (isAutoUpdating || slides.length === 0) return;

    // Acquire lock (only required in collaboration mode)
    if (collaboration?.ydoc && !requestDocumentLock()) {
      Alert.alert('Lock Failed', 'Could not acquire document lock.');
      setShowUpdateInstructionModal(false);
      return;
    }

    // Update goal if changed — always persist regardless of vault selection
    if (updatedGoal) {
      const newGoal = typeof presentationGoal === 'object'
        ? { ...presentationGoal, purpose: updatedGoal }
        : { purpose: updatedGoal };
      setPresentationGoal(newGoal);
    }

    // Update slide outlines if changed — always persist regardless of vault selection
    // Use positional mapping: i-th outline item → i-th slide (outline may have been
    // refreshed/reordered/added/deleted in the modal, so slideIndex can be stale)
    if (updatedOutline && Array.isArray(updatedOutline)) {
      updatedOutline.forEach((item, idx) => {
        const slide = slides[idx];
        if (slide) {
          updateSlide(slide.id, {
            title: item.title || slide.title,
            outline: item.outline || slide.outline,
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
    setAutoUpdateProgress({ current: 0, total: slides.length });

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

      // Filter out hidden slides for AI processing
      const aiSlides = slides.filter(s => !s.hidden);
      const aiIndexToFullIndex = aiSlides.map(s => slides.indexOf(s));

      // Build summaries with updated outline data (positional: i-th outline → i-th visible slide)
      const slidesSummary = buildSlidesSummary(aiSlides).map((summary, idx) => {
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
      const goalString = updatedGoal || extractGoalString(presentationGoal) || '';
      const baseInstruction = "Update all slides with the latest data, statistics, and information from my data store. You have full freedom to restructure content as needed. IMPORTANT: Refresh imageDescription of image_placeholder elements to match the updated content.";

      // Include the full target outline in the instruction so AI knows desired structure
      let outlineContext = '';
      if (updatedOutline && updatedOutline.length > 0) {
        const outlineList = updatedOutline.map((item, i) => `${i + 1}. ${item.title}${item.outline ? ': ' + item.outline : ''}`).join('\n');
        outlineContext = `\n\nTARGET OUTLINE (${updatedOutline.length} slides):\n${outlineList}\nRedistribute and update content to match this outline structure.`;
      }

      const fullInstruction = (instruction && instruction !== "Update with the latest data from my data store."
        ? `${baseInstruction}\n\nAdditional: ${instruction}`
        : baseInstruction) + outlineContext;

      // Extract images from visible slides before sending to API
      const imageMaps = {};
      const processedFullSlides = aiSlides.map((slide, idx) => {
        const { processedSlide, imageMap } = extractImagesFromSlide(slide);
        imageMaps[idx] = imageMap;
        return { ...processedSlide, id: slide.id };
      });

      const currentIndex = aiSlides.findIndex(s => s.id === currentSlideId);

      // Use smart orchestrate-all-stream endpoint
      const response = await fetch(`${apiConfig.API_URL}/presentation/orchestrate-all-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          instruction: fullInstruction,
          slides_summary: slidesSummary,
          full_slides: processedFullSlides,
          current_slide_index: currentIndex >= 0 ? currentIndex : 0,
          folder_ids: finalFolderIds,
          style: presentationStyle,
          presentation_goal: goalString,
          presentation_type: presentationGoal?.documentType || 'general',
          icon_set: presentationStyle?.iconSet || 'default',
          is_update_all: true,
          outline_changed: !!outlineChanged,
          deck_profile: presentationGoal?.deckProfile || 'corporate',
          deck_plan: presentationGoal?.deckPlan || null,
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
      const pendingImageTasks = []; // Parallel image generation across slides

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
                const originalSlide = slides[fullIndex];
                if (!originalSlide) continue;

                // Restore images using the image map for this slide
                const editImageMap = imageMaps[event.page_index] || {};
                const restoredSlideData = restoreImagesToSlide(event.slide_data, editImageMap);
                const processedSlideOutput = await processSlideAsync(restoredSlideData);

                // Apply text/layout changes immediately
                const slideUpdate = { elements: processedSlideOutput.elements };
                if (processedSlideOutput.backgroundColor) slideUpdate.backgroundColor = processedSlideOutput.backgroundColor;
                if (processedSlideOutput.title) slideUpdate.title = processedSlideOutput.title;
                if (processedSlideOutput.notes) slideUpdate.notes = processedSlideOutput.notes;
                // Store re-matched template if backend returned one (e.g. after outline regeneration)
                if (processedSlideOutput.template) {
                  slideUpdate.template = processedSlideOutput.template;
                  slideUpdate.layout = processedSlideOutput.template;
                }
                // Sync outline from AI response (keeps outline fresh after edits)
                slideUpdate.outline = processedSlideOutput.outline || restoredSlideData.outline || originalSlide.outline || originalSlide.sectionTopic || '';
                updateSlide(originalSlide.id, slideUpdate);
                successCount++;

                // Fire image generation in parallel (don't block SSE loop)
                const imagePlaceholders = (processedSlideOutput.elements || []).filter(el => el.type === 'image_placeholder');
                if (imagePlaceholders.length > 0) {
                  const slideId = originalSlide.id;
                  const imageTask = (async () => {
                    try {
                      await generateImagesParallel(imagePlaceholders, {
                        generationQuality, style: presentationStyle?.name || 'professional',
                        userId: userDeviceId, defaultDescription: 'Professional presentation image', handleCreditError,
                      });
                      const finalElements = (processedSlideOutput.elements || []).map(el => {
                        if (el.type === 'image' && !el.src && !el.isUserMedia) {
                          return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
                        }
                        return el;
                      });
                      updateSlide(slideId, { elements: finalElements });
                    } catch (imgErr) { console.error(`❌ [UPDATE_ALL] Image gen failed for slide ${event.page_index}:`, imgErr); }
                  })();
                  pendingImageTasks.push(imageTask);
                }
              } catch (editErr) {
                console.error(`Error applying slide ${event.page_index}:`, editErr);
              }
            } else if (event.type === 'complete') {
              const failCount = (totalMatched || aiSlides.length) - successCount;
              if (failCount === 0) {
                Alert.alert('Update Complete', `Successfully updated all ${successCount} slides with latest data store content.`);
              } else {
                Alert.alert('Update Complete', `Updated ${successCount} slides. ${failCount} slides failed to update.`);
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

      // Wait for all parallel image generation to complete
      if (pendingImageTasks.length > 0) {
        console.log(`🖼️ [UPDATE_ALL] Waiting for ${pendingImageTasks.length} parallel image tasks...`);
        await Promise.all(pendingImageTasks);
        console.log(`✅ [UPDATE_ALL] All image tasks completed`);
      }
    } catch (error) {
      console.error('Auto update error:', error);
      Alert.alert('Error', 'Failed to complete auto update. Please try again.');
    } finally {
      setIsAutoUpdating(false);
      setAutoUpdateProgress({ current: 0, total: 0 });
      releaseDocumentLock();
    }
  }, [isAutoUpdating, slides, useUploadedData, selectedFolders, apiConfig, userDeviceId, presentationStyle, presentationGoal, updateSlide, currentSlideId, generationQuality, extractImagesFromSlide, restoreImagesToSlide, releaseDocumentLock]);

  // Mini slide preview for thumbnail view
  const renderMiniSlidePreview = (slide, previewWidth = 120) => {
    const previewHeight = (previewWidth * 9) / 16; // 16:9 aspect ratio
    const thumbnail = slideThumbnails[slide?.id];
    const miniScale = previewWidth / SLIDE_WIDTH;

    // Helper to render layout blocks as fallback
    const renderLayoutBlocks = () => (
      <>
        {slide?.elements?.slice(0, 8).map((element, idx) => {
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
          backgroundColor: slide?.backgroundColor || '#ffffff',
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

        {/* Slide number overlay */}
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
            {slide?.order || 1}
          </Text>
        </View>
      </View>
    );
  };

  // Render slide thumbnail in sidebar
  const renderSlideItem = (slide, index) => {
    const isActive = currentSlideId === slide.id;
    const isEditing = editingSlideId === slide.id;

    // Thumbnail View Mode
    if (slidePanelViewMode === 'thumbnail') {
      return (
        <View
          key={slide.id}
          style={[styles.slideItemContainer, slide.hidden && { opacity: 0.45 }]}
          onLayout={(e) => {
            const layout = e.nativeEvent.layout;
            sidebarLayoutsRef.current[slide.id] = { y: layout.y, height: layout.height };
          }}
        >
          <TouchableOpacity
            style={[
              styles.slideThumbnailItem,
              isActive && styles.slideThumbnailItemActive,
              {
                borderColor: isActive ? safeTheme.primary : safeTheme.borderColor || '#e0e0e0',
                backgroundColor: isActive ? safeTheme.primary + '10' : 'transparent',
              },
            ]}
            onPress={() => {
              if (actionBtnGuard.current) { actionBtnGuard.current = false; return; }
              skipSidebarScroll.current = true;
              handleSelectSlide(slide.id);
              if (selectedElementIds.length > 0) {
                setSelectedElementIds([]);
              }
            }}
            activeOpacity={0.7}
          >
            {/* Mini Slide Preview */}
            {renderMiniSlidePreview(slide, sidebarWidth - 32)}

            {/* Title below thumbnail */}
            <View style={{ marginTop: 6, paddingHorizontal: 2 }}>
              {isEditing ? (
                <TextInput
                  style={[styles.slideTitleInput, { color: safeTheme.text, fontSize: 10 }]}
                  value={editingSlideTitleText}
                  onChangeText={setEditingSlideTitleText}
                  onBlur={saveSlideTitle}
                  onSubmitEditing={saveSlideTitle}
                  autoFocus
                />
              ) : (
                <Text style={[styles.slideItemTitle, { color: safeTheme.text, fontSize: 10, textAlign: 'left', flexWrap: 'wrap' }]}>
                  {slide.title}
                </Text>
              )}
            </View>

            {/* Hover/Active Actions */}
            <View style={[styles.slideThumbnailActions, { opacity: isActive ? 1 : 0.7 }]}>
              <TouchableOpacity
                onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderSlides(index, index - 1); }}
                disabled={index === 0}
                style={{ opacity: index === 0 ? 0.3 : 1, padding: 2 }}
              >
                <Ionicons name="chevron-up" size={10} color={safeTheme.text} />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderSlides(index, index + 1); }}
                disabled={index === slides.length - 1}
                style={{ opacity: index === slides.length - 1 ? 0.3 : 1, padding: 2 }}
              >
                <Ionicons name="chevron-down" size={10} color={safeTheme.text} />
              </TouchableOpacity>
              {!isReadOnly && (
                <Tooltip text={slide.hidden ? "Show Slide" : "Hide Slide"} theme={safeTheme}>
                  <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); toggleSlideHidden(slide.id); }} style={{ padding: 2 }}>
                    <Ionicons name={slide.hidden ? "eye-off-outline" : "eye-outline"} size={10} color={safeTheme.textSecondary || '#888'} />
                  </TouchableOpacity>
                </Tooltip>
              )}
              <Tooltip text="Copy Slide to Clipboard" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); copySlide(slide); }} style={{ padding: 2 }}>
                  <MaterialIcons name="content-paste" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Duplicate Slide" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDuplicateSlide(slide.id); }} style={{ padding: 2 }}>
                  <MaterialIcons name="content-copy" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Edit Slide" theme={safeTheme}>
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); setEditOutlineSlide(slide); }} style={{ padding: 2 }}>
                  <MaterialIcons name="edit" size={10} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              </Tooltip>
              {slides.length > 1 && (
                <Tooltip text="Delete Slide" theme={safeTheme}>
                  <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDeleteSlide(slide.id); }} style={{ padding: 2 }}>
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
        key={slide.id}
        style={[styles.slideItemContainer, slide.hidden && { opacity: 0.45 }]}
        onLayout={(e) => {
          const layout = e.nativeEvent.layout;
          sidebarLayoutsRef.current[slide.id] = { y: layout.y, height: layout.height };
        }}
      >
        <TouchableOpacity
          style={[
            styles.slideItem,
            isActive && styles.slideItemActive,
            {
              borderColor: isActive ? '#BFDBFE' : 'transparent',
              backgroundColor: isActive ? '#EFF6FF' : 'transparent',
            },
          ]}
          onPress={() => {
            if (actionBtnGuard.current) { actionBtnGuard.current = false; return; }
            skipSidebarScroll.current = true;
            handleSelectSlide(slide.id);
            if (selectedElementIds.length > 0) {
              setSelectedElementIds([]);
            }
          }}
          activeOpacity={0.7}
        >
          {/* Info & Actions Column */}
          <View style={{ flex: 1, flexDirection: 'column', gap: 4 }}>
            {/* Slide info */}
            <View style={[styles.slideInfo, { flex: 0 }]}>
              {isEditing ? (
                <TextInput
                  style={[styles.slideTitleInput, { color: safeTheme.text }]}
                  value={editingSlideTitleText}
                  onChangeText={setEditingSlideTitleText}
                  onBlur={saveSlideTitle}
                  onSubmitEditing={saveSlideTitle}
                  autoFocus
                />
              ) : (
                <Text style={[styles.slideItemTitle, { color: safeTheme.text, textAlign: 'left', flexWrap: 'wrap' }]}>
                  {slide.title}
                </Text>
              )}
            </View>

            {/* Actions */}
            <View style={styles.slideActions}>
              <View style={{ flexDirection: 'column', gap: 2, marginRight: 4 }}>
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderSlides(index, index - 1); }}
                  disabled={index === 0}
                  style={{ opacity: index === 0 ? 0.3 : 1, padding: 2 }}
                >
                  <Ionicons name="chevron-up" size={12} color={safeTheme.text} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); reorderSlides(index, index + 1); }}
                  disabled={index === slides.length - 1}
                  style={{ opacity: index === slides.length - 1 ? 0.3 : 1, padding: 2 }}
                >
                  <Ionicons name="chevron-down" size={12} color={safeTheme.text} />
                </TouchableOpacity>
              </View>

              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); copySlide(slide); }} style={styles.slideActionBtn} title="Copy Slide to Clipboard">
                <MaterialIcons name="content-paste" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDuplicateSlide(slide.id); }} style={styles.slideActionBtn} title="Duplicate Slide">
                <MaterialIcons name="content-copy" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              {!isReadOnly && (
                <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); toggleSlideHidden(slide.id); }} style={styles.slideActionBtn} title={slide.hidden ? "Show Slide" : "Hide Slide"}>
                  <Ionicons name={slide.hidden ? "eye-off-outline" : "eye-outline"} size={14} color={safeTheme.textSecondary || '#888'} />
                </TouchableOpacity>
              )}
              <TouchableOpacity onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); setEditOutlineSlide(slide); }} style={styles.slideActionBtn}>
                <MaterialIcons name="edit" size={14} color={safeTheme.textSecondary || '#888'} />
              </TouchableOpacity>
              {slides.length > 1 && (
                <TouchableOpacity
                  onPress={() => { actionBtnGuard.current = true; setTimeout(() => { actionBtnGuard.current = false; }, 50); handleDeleteSlide(slide.id); }}
                  style={[styles.slideActionBtn, styles.deleteBtn]}
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

      console.log('🎨 [PRESENTATION] Generating AI style...');

      const response = await fetch(`${apiConfig.API_URL}/presentation/generate-style`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: stylePrompt,
          user_id: userDeviceId,
        }),
      });

      const data = await response.json();

      if (response.status === 402 || handleCreditError(data)) {
        return;
      }

      if (data.success && data.style) {
        console.log('🎨 [PRESENTATION] AI style generated:', data.style.name);
        console.log('🎨 [PRESENTATION] AI style data:', JSON.stringify(data.style, null, 2));

        // Map AI response to internal style structure
        // AI returns: { name, fontFamily, textPrimary, textSecondary, accentColor, slideBackground, preview: { titleColor, bodyColor } }
        // Internal expects: { id, name, preview: { primary, secondary, accent }, slideBackground, textStyles: { title, subtitle, body } }

        const aiStyle = data.style;
        const newStyle = {
          id: `ai_style_${Date.now()}`,
          name: aiStyle.name || 'Custom AI Style',
          description: `AI generated style: ${stylePrompt}`,
          slideBackground: aiStyle.slideBackground || '#ffffff',
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
        setPresentationStyle(newStyle);
        applyStyleToAllSlides(newStyle);

        // Persist to storage
        try {
          await AsyncStorage.setItem('@custom_presentation_styles', JSON.stringify(updatedStyles));
          console.log('✅ [PRESENTATION] Custom styles saved to storage');
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
  }, [apiConfig, userDeviceId, applyStyleToAllSlides]);


  const handleAddSlideClick = (index) => {
    setInsertSlideIndex(index);
    setShowLayoutPicker(true);
  };

  const handleLayoutSelected = async (templateId, outline = '', mode = 'manual', specialInstructions = '') => {
    setShowLayoutPicker(false);

    // CASE 1: Change Existing Slide Layout
    if (targetSlideIdForLayoutChange) {
      try {
        const newSlideData = createSlideFromTemplate(templateId, presentationStyle);
        if (newSlideData) {
          updateSlide(targetSlideIdForLayoutChange, {
            layout: templateId,
            elements: newSlideData.elements,
            backgroundColor: newSlideData.background || '#ffffff',
            // If outline is provided during layout change (unlikely but possible), save it
            ...(outline ? { outline } : {})
          });
        }
      } catch (error) {
        console.error("Failed to change layout:", error);
      }
      setTargetSlideIdForLayoutChange(null);
      return;
    }

    // CASE 2: Add New Slide
    const index = insertSlideIndex !== null ? insertSlideIndex : slides.length;
    const newSlideId = `slide_${Date.now()}`;

    try {
      // Generate slide data from template
      const newSlideData = createSlideFromTemplate(templateId, presentationStyle);
      const elements = newSlideData ? newSlideData.elements : [];
      const bgColor = newSlideData ? newSlideData.background : '#ffffff';

      // Create the new slide object with custom ID
      const newSlide = {
        id: newSlideId,
        order: index + 1,
        title: 'New Slide',
        layout: templateId,
        elements: elements,
        backgroundColor: bgColor,
        hasUnsavedChanges: true,
        outline: outline, // Save the outline in metadata
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      // Use the hook's addSlide function which handles Yjs sync properly
      // Pass customSlideData to use our specific slide object instead of auto-generated one
      slideChangeFromInteraction.current = true;
      addSlide(index, templateId, elements, newSlide);

      setInsertSlideIndex(null);

      // Scroll to the new slide after it renders (fallback for when useEffect scroll misses)
      setTimeout(() => {
        scrollToSlide(newSlideId, true);
      }, 400);

      // AI GENERATION MODE
      if (mode === 'ai') {
        // Trigger async generation
        generateSlideFromOutline(newSlide, outline, specialInstructions);
      }

    } catch (error) {
      console.error("Failed to create slide from template:", error);
      slideChangeFromInteraction.current = true;
      addSlide(index); // Fallback
    }
  };

  // Helper handling AI Generation for a new slide
  const generateSlideFromOutline = async (slide, outline, specialInstructions = '') => {
    if (!outline) {
      console.warn('⚠️ [AI] Cannot generate slide without outline');
      return;
    }

    setIsGeneratingSlides(true);
    // Simplify progress to 0-1 for single slide
    setGenerationProgress({ current: 0, total: 1 });

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Error', 'Not authenticated for AI generation');
        return;
      }

      console.log(`🤖 [AI] Generating NEW slide from outline: "${outline}"`);

      // Get context from previous slides (up to 2 slides before)
      const currentIndex = slides.findIndex(s => s.id === slide.id);
      const prevSlidesContext = currentIndex > 0
        ? slides.slice(Math.max(0, currentIndex - 2), currentIndex).map(s => ({
          title: s.title || 'Untitled',
          content_summary: s.outline || s.title || ''
        }))
        : [];

      // Use the generate-slide API for NEW slides (not orchestrate)
      const response = await fetch(`${apiConfig.API_URL}/presentation/generate-slide`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          slide_info: {
            title: outline,
            content_hint: specialInstructions || outline,
          },
          slide_index: currentIndex,
          total_slides: slides.length,
          presentation_goal: presentationGoal?.purpose || (typeof presentationGoal === 'string' ? presentationGoal : ''),
          presentation_type: presentationGoal?.documentType || 'general',
          style: presentationStyle,
          template_id: (presentationGoal?.deckProfile === 'general') ? null : slide.layout,
          folder_ids: useUploadedData && selectedFolders?.length > 0 ? selectedFolders.map(f => f.id || f) : [],
          user_id: userDeviceId,
          previous_slides: prevSlidesContext,
          images_remaining: 10, // Default allowance for images
          icon_set: presentationStyle?.iconSet || 'default',
          special_instructions: specialInstructions || null,
          deck_profile: presentationGoal?.deckProfile || 'corporate',
          deck_plan: presentationGoal?.deckPlan || null,
        }),
      });

      const data = await response.json();

      if (response.status === 402 || handleCreditError(data)) {
        return;
      }

      if (data.success && data.slide) {
        console.log(`✅ [AI] New slide generated successfully`);

        // Process the slide (handle icons, etc.)
        let processedSlideOutput = await processSlideAsync(data.slide);

        // --- GENERATE IMAGES FOR PLACEHOLDERS ---
        // Check for image_placeholder elements and generate actual images
        const imagePlaceholders = (processedSlideOutput.elements || []).filter(el => el.type === 'image_placeholder');
        if (imagePlaceholders.length > 0) {
          console.log(`🖼️ [NEW_SLIDE] Found ${imagePlaceholders.length} image placeholder(s), generating...`);
          await generateImagesParallel(imagePlaceholders, {
            generationQuality, style: presentationStyle?.name || 'professional',
            userId: userDeviceId, defaultDescription: outline || 'Professional presentation image', handleCreditError,
          });
        }
        // --- END IMAGE GENERATION ---

        // Safety net: catch any remaining type='image' elements without src (skip user-media)
        const safeElements = (processedSlideOutput.elements || []).map(el => {
          if (el.type === 'image' && !el.src && !el.isUserMedia) {
            console.warn(`⚠️ [NEW_SLIDE] Image element ${el.id} still has no src — converting to shape`);
            return { ...el, type: 'shape', fill: '#e2e8f0', shapeType: 'rectangle', rx: 8 };
          }
          return el;
        });

        // Update the slide
        const slideUpdate = {
          elements: safeElements,
          // Update title if AI generated one
          ...(processedSlideOutput.title ? { title: processedSlideOutput.title } : {}),
          // Update notes
          ...(processedSlideOutput.notes ? { notes: processedSlideOutput.notes } : {}),
          // Store the actual matched template from backend (resolves ai_auto to real template)
          ...(processedSlideOutput.template ? { template: processedSlideOutput.template, layout: processedSlideOutput.template } : {}),
        };

        updateSlide(slide.id, slideUpdate);
        console.log(`✅ [AI] Slide generated successfully`);
        pendingLayoutFixRef.current.add(slide.id);
      } else {
        console.error(`❌ [AI] Generation failed:`, data.message);
        Alert.alert('Generation Failed', 'AI could not generate content. You have the blank layout.');
      }

    } catch (error) {
      console.error('AI Generation Error:', error);
      Alert.alert('Error', 'Failed to generate slide content.');
    } finally {
      setIsGeneratingSlides(false);
      setGenerationProgress({ current: 0, total: 0 });
      // Auto-play on mobile after generation completes
      if (mobileViewOnly && slides.length > 0) {
        setTimeout(() => startPresentation(), 500);
      }
    }
  };

  const openLayoutPickerForSlide = (slideId) => {
    setTargetSlideIdForLayoutChange(slideId);
    setShowLayoutPicker(true);
  };





  if (!visible) return null;

  // Handle Enter-to-send on web, Shift+Enter for newline
  const handleKeyPress = (e) => {
    if (Platform.OS === 'web') {
      const key = e?.nativeEvent?.key;
      if (key === 'Enter') {
        const shift = e?.shiftKey || e?.nativeEvent?.shiftKey;
        if (!shift && chatInput.trim() && !isAiProcessing && !isAiLocked && currentSlide) {
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
      animationType="slide"
      onRequestClose={() => setShowCloseConfirmModal(true)}
      presentationStyle="fullScreen"
      supportedOrientations={['portrait', 'landscape']}
    >
      <View style={[styles.container, { backgroundColor: safeTheme.background }]}>
        {/* Header Removed - moved to PresentationCanvas - Title now in Sidebar */}

        {/* Save Name Modal */}
        <Modal visible={showSaveModal} transparent animationType="fade" onRequestClose={() => setShowSaveModal(false)}>
          <View style={styles.topMiddleModalOverlay}>
            <View style={[styles.saveModal, { backgroundColor: safeTheme.background }]}>
              <Text style={[styles.saveModalTitle, { color: safeTheme.text }]}>Save Presentation</Text>
              <Text style={[styles.saveModalLabel, { color: safeTheme.textSecondary }]}>Name</Text>
              <TextInput
                style={[styles.saveModalInput, { color: safeTheme.text, borderColor: safeTheme.border }]}
                value={presentationTitle}
                onChangeText={setPresentationTitle}
                autoFocus
              />
              <View style={styles.saveModalButtons}>
                <TouchableOpacity
                  style={[styles.saveModalBtn, styles.cancelBtn, { borderColor: safeTheme.border }]}
                  onPress={() => setShowSaveModal(false)}
                >
                  <Text style={[styles.saveModalBtnText, { color: safeTheme.text }]}>Cancel</Text>
                </TouchableOpacity>
                {currentPresentationId && (
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
              <Text style={{ marginTop: 14, fontSize: 15, fontWeight: '600', color: safeTheme.text || '#1F2937' }}>Saving presentation…</Text>
            </View>
          </View>
        )}

        {/* Thumbnail Generation Overlay */}
        {isGeneratingThumbnails && (
          <View style={{ position: Platform.OS === 'web' ? 'fixed' : 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.25)', zIndex: 99998, justifyContent: 'center', alignItems: 'center' }}>
            <View style={{ backgroundColor: safeTheme.background || '#fff', borderRadius: 16, padding: 28, alignItems: 'center', shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 12, elevation: 8 }}>
              <ActivityIndicator size="large" color={safeTheme.primary || '#6366F1'} />
              <Text style={{ marginTop: 14, fontSize: 15, fontWeight: '600', color: safeTheme.text || '#1F2937' }}>Generating slide previews…</Text>
            </View>
          </View>
        )}

        {/* Main content area - Full height now */}
        <View style={mobileViewOnly ? styles.mainContentMobile : styles.mainContent}>

          {/* Mobile View Only - Top bar with minimal controls */}
          {mobileViewOnly && (
            <View style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingHorizontal: 12,
              paddingVertical: 8,
              backgroundColor: safeTheme.surface || '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.border || '#E5E7EB',
              zIndex: 10,
            }}>
              <TouchableOpacity onPress={() => setShowCloseConfirmModal(true)} style={{ padding: 6 }}>
                <Ionicons name="close" size={22} color={safeTheme.text} />
              </TouchableOpacity>
              {/* Insert Slide */}
              {slides.length > 0 && (
                <TouchableOpacity
                  onPress={() => handleAddSlideClick(currentSlideIndex + 1)}
                  style={{ padding: 6, marginLeft: 2 }}
                >
                  <Ionicons name="add-circle-outline" size={22} color={safeTheme.primary || '#6366F1'} />
                </TouchableOpacity>
              )}
              {/* Arrange Slides */}
              {slides.length > 1 && (
                <TouchableOpacity
                  onPress={() => setShowArrangeModal(true)}
                  style={{ padding: 6 }}
                >
                  <Ionicons name="swap-horizontal-outline" size={20} color={safeTheme.text} />
                </TouchableOpacity>
              )}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexGrow: 1, flexShrink: 1, justifyContent: 'flex-end' }}>
                {currentPresentationId && isItemOwner && (
                  <ShareButton
                    contentType="presentation"
                    sourceId={currentPresentationId}
                    title={presentationTitle}
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
                {currentPresentationId && (
                  <TouchableOpacity onPress={() => setShowAnalyticsModal(true)} style={{ padding: 6 }}>
                    <Ionicons name="bar-chart-outline" size={20} color={safeTheme.text} />
                  </TouchableOpacity>
                )}
                {slides.length > 0 && (
                  <TouchableOpacity onPress={() => setShowSaveModal(true)} style={{ padding: 6 }}>
                    <Ionicons name="save-outline" size={22} color={safeTheme.primary || '#6366F1'} />
                  </TouchableOpacity>
                )}
                {slides.length > 0 && (
                  <TouchableOpacity onPress={() => startPresentation()} style={{ padding: 6 }}>
                    <Ionicons name="play-circle-outline" size={22} color={safeTheme.primary || '#6366F1'} />
                  </TouchableOpacity>
                )}
                {slides.length > 0 && (
                  <TouchableOpacity onPress={() => setShowExportModal(true)} style={{ padding: 6 }}>
                    <Ionicons name="download-outline" size={22} color={safeTheme.text} />
                  </TouchableOpacity>
                )}
              </View>
            </View>
          )}

          {/* Mobile Generation Overlay - Shows spinner when sidebar is hidden */}
          {mobileViewOnly && isGeneratingSlides && (
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
                  Generating Slides...
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

          {/* Mobile View Only - Slide navigation strip */}
          {mobileViewOnly && slides.length > 1 && (
            <View style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              paddingVertical: 6,
              backgroundColor: safeTheme.surface || '#ffffff',
              borderBottomWidth: 1,
              borderBottomColor: safeTheme.border || '#E5E7EB',
              gap: 16,
            }}>
              <TouchableOpacity
                disabled={currentSlideIndex <= 0}
                onPress={goToPrevSlide}
                style={{ padding: 6, opacity: currentSlideIndex <= 0 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-back" size={20} color={safeTheme.text} />
              </TouchableOpacity>
              <Text style={{ color: safeTheme.text, fontSize: 13, fontWeight: '500' }}>
                Slide {currentSlideIndex + 1} / {slides.length}
              </Text>
              <TouchableOpacity
                disabled={currentSlideIndex >= slides.length - 1}
                onPress={goToNextSlide}
                style={{ padding: 6, opacity: currentSlideIndex >= slides.length - 1 ? 0.3 : 1 }}
              >
                <Ionicons name="chevron-forward" size={20} color={safeTheme.text} />
              </TouchableOpacity>
            </View>
          )}

          {/* Mobile Segmented Control - Toggle between Tools and AI Chat */}
          {mobileViewOnly && slides.length > 0 && (
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
          {mobileViewOnly && mobileEditMode === 'chat' && slides.length > 0 && (
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
              {editMode !== 'slide' && selectedElements.length > 0 && (
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

              {/* Agentic editor hint — the AI sees the whole deck and decides what to change */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name="sparkles" size={12} color="#7C3AED" />
                <Text style={{ fontSize: 11, color: safeTheme.placeholderText || '#6B7280', flex: 1 }} numberOfLines={1}>
                  AI edits the whole deck — add/remove/reorder slides, restyle, header & footer, slide numbers. Just ask.
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
                    borderColor: safeTheme.border || '#D1D5DB',
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 13,
                    maxHeight: 80,
                  }}
                  placeholder={isAiLocked ? "AI is locked..." : (editMode === 'slide' ? 'Ask anything — edit, add, reorder, review slides…' : `Edit ${getElementTypeLabel(selectedElements).toLowerCase()}...`)}
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

          {/* Sidebar - Slide list */}
          {!mobileViewOnly && (
            <View style={[styles.sidebar, { width: sidebarWidth, backgroundColor: '#ffffff', borderRightColor: safeTheme.border }]}>

              {/* Title Area Above Slide Nav */}
              <View style={{ marginBottom: 16, paddingHorizontal: 4 }}>
                {/* View Only Banner for read-only users */}
                {isReadOnly && (
                  <View style={{
                    backgroundColor: '#FEF3C7',
                    paddingVertical: 6,
                    paddingHorizontal: 10,
                    borderRadius: 4,
                    marginBottom: 8,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    borderWidth: 1,
                    borderColor: '#F59E0B',
                  }}>
                    <Ionicons name="eye-outline" size={14} color="#D97706" />
                    <Text style={{ fontSize: 11, color: '#D97706', fontWeight: '600' }}>
                      View Only
                    </Text>
                  </View>
                )}
                {/* Collaboration Lock - only show when collaboration is enabled */}
                {canCollaborate && (
                  <CollaborationLockIndicator
                    documentLock={documentLock}
                    ownClientId={collaboration.ydoc?.clientID}
                    type="presentation"
                    style={{ marginBottom: 8 }}
                  />
                )}
                <Text style={[styles.sidebarTitle, { color: safeTheme.text, fontSize: 16 }]} numberOfLines={1}>
                  {presentationTitle}
                </Text>
                {vaultDisplayName && (
                  <Text style={{ fontSize: 11, color: safeTheme.text, opacity: 0.6, fontStyle: 'italic', marginBottom: 2 }}>
                    Data Store: {vaultDisplayName}
                  </Text>
                )}
                {lastSaved && (
                  <Text style={{ fontSize: 10, color: safeTheme.textSecondary }}>
                    {isSaving ? 'Saving...' : `Saved ${new Date(lastSaved).toLocaleTimeString()}`}
                  </Text>
                )}

                {currentPresentationId && isItemOwner && (
                  <View style={{ marginTop: 8 }}>
                    <ShareButton
                      contentType="presentation"
                      sourceId={currentPresentationId}
                      title={presentationTitle}
                      theme={safeTheme}
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
                  handles whole-deck updates ("update all slides with the latest
                  data"). Flow (handleAutoUpdate + UpdateInstructionModal) kept
                  for potential re-enable. */}
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
                disabled={isAutoUpdating || isGeneratingSlides}
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
                      Update ALL
                    </Text>
                  </>
                )}
              </TouchableOpacity>
              )}

              {/* Generation Progress Indicator */}
              {isGeneratingSlides && generationProgress.total > 0 && (
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
                {/* 1. Slide Navigation */}
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <TouchableOpacity
                    disabled={currentSlideIndex <= 0}
                    onPress={goToPrevSlide}
                    style={{ opacity: currentSlideIndex <= 0 ? 0.3 : 1, padding: 4 }}
                  >
                    <Ionicons name="chevron-back" size={18} color={safeTheme.text} />
                  </TouchableOpacity>
                  <Text style={[styles.sidebarTitle, { color: safeTheme.text, fontSize: 13, marginBottom: 0 }]}>
                    Slide {currentSlideIndex + 1}/{slides.length}
                  </Text>
                  <TouchableOpacity
                    disabled={currentSlideIndex >= slides.length - 1}
                    onPress={goToNextSlide}
                    style={{ opacity: currentSlideIndex >= slides.length - 1 ? 0.3 : 1, padding: 4 }}
                  >
                    <Ionicons name="chevron-forward" size={18} color={safeTheme.text} />
                  </TouchableOpacity>
                </View>

                {/* 2. View Toggle Button */}
                <Tooltip text={slidePanelViewMode === 'thumbnail' ? 'Switch to List View' : 'Switch to Thumbnail View'} theme={safeTheme}>
                  <TouchableOpacity
                    style={{
                      padding: 6,
                      backgroundColor: safeTheme.background,
                      borderRadius: 6,
                      borderWidth: 1,
                      borderColor: safeTheme.border || '#e0e0e0',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                    onPress={toggleSlidePanelView}
                  >
                    <Ionicons
                      name={slidePanelViewMode === 'thumbnail' ? 'list-outline' : 'grid-outline'}
                      size={16}
                      color={safeTheme.text}
                    />
                  </TouchableOpacity>
                </Tooltip>

                {/* 3. Add Slide Button */}
                <TouchableOpacity
                  style={[styles.addSlideBtn, {
                    backgroundColor: safeTheme.primary,
                    height: 32,
                    width: '100%',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }]}
                  onPress={() => handleAddSlideClick(currentSlideIndex + 1)}
                >
                  <Ionicons name="add" size={20} color="#fff" />
                </TouchableOpacity>
              </View>

              <ScrollView ref={sidebarScrollRef} style={styles.slideList} showsVerticalScrollIndicator={false}>
                {slides.map((slide, index) => renderSlideItem(slide, index))}
              </ScrollView>
            </View>
          )}

          {/* Resizer Splitter (Left) */}
          {!mobileViewOnly && (
            <View
              style={styles.resizer}
              {...panResponder.panHandlers}
            >
              <View style={{ width: 1, height: '100%', backgroundColor: safeTheme.border, marginLeft: 2 }} />
            </View>
          )}

          {/* Canvas area with shared toolbar + vertical scroll */}
          <View
            style={[styles.canvasContainer, mobileViewOnly && { flex: 1 }]}
            onLayout={(e) => {
              const { width, height } = e.nativeEvent.layout;
              if (width !== containerSize.width || height !== containerSize.height) {
                setContainerSize({ width, height });
              }
            }}
          >
            {/* Shared Toolbar */}
            <PresentationSharedToolbar
              theme={safeTheme}
              activeCanvasRef={activeCanvasRef}
              selectionInfo={selectionInfo}
              onOpenStylePicker={() => setShowStylePicker(true)}
              onOpenChartHelp={() => setShowChartStudio(true)}
              onOpenDiagram={handleOpenDiagram}
              onGenerateImage={handleGenerateImage}
              formatPainterActive={formatPainterActive}
              presentationTitle={presentationTitle}
              presentationId={currentPresentationId}
              isOwner={isItemOwner}
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
              onShowQualityModal={presentationGoal ? () => setShowQualityModal(true) : undefined}
              qualityLabel={qualityLabel}
              qualityColor={qualityColor}
              slideBackgroundColor={currentSlide?.backgroundColor || '#ffffff'}
              hasBackgroundImage={!!(currentSlide?.elements?.some(el => el.imageType === 'background'))}
              backgroundImageOpacity={currentSlide?.elements?.find(el => el.imageType === 'background')?.opacity ?? 0.3}
              onUpdateSlideBackground={(color) => {
                if (currentSlide?.id) {
                  updateSlideBackground(currentSlide.id, { backgroundColor: color });
                }
              }}
              onChangeBackgroundOpacity={(opacity) => {
                if (currentSlide?.id) {
                  updateSlideBackground(currentSlide.id, { backgroundOpacity: opacity });
                }
              }}
              onRemoveBackgroundImage={() => {
                if (currentSlide?.id) {
                  updateSlideBackground(currentSlide.id, { removeBackgroundImage: true });
                }
              }}
            />

            {/* Vertically scrollable area containing all slides */}
            <div className="presentation-scroll-area" style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
              <ScrollView
                ref={contentScrollRef}
                onScroll={handleContentScrollDebounced}
                scrollEventThrottle={16}
                style={{ flex: 1 }}
                contentContainerStyle={{ paddingVertical: 24, alignItems: 'center' }}
                showsVerticalScrollIndicator={true}
              >
                {slides.map((slide, index) => {
                  const slideRef = getOrCreateCanvasRef(slide.id);
                  const isActiveSlide = slide.id === currentSlideId;
                  return (
                    <View
                      key={slide.id}
                      nativeID={`slide-view-${slide.id}`}
                      onLayout={(e) => {
                        const layout = e.nativeEvent.layout;
                        slideLayoutsRef.current[slide.id] = { y: layout.y, height: layout.height };
                      }}
                      style={{
                        marginBottom: 24,
                        alignItems: 'center',
                        borderLeftWidth: 4,
                        borderLeftColor: isActiveSlide ? safeTheme.primary : 'transparent',
                        borderRadius: 8,
                        backgroundColor: isActiveSlide ? (safeTheme.primary + '08') : 'transparent',
                        paddingLeft: 8,
                        paddingRight: 4,
                        paddingVertical: 8,
                      }}
                    >
                      <Text style={{
                        fontSize: 11,
                        color: isActiveSlide ? safeTheme.primary : (safeTheme.textSecondary || '#888'),
                        marginBottom: 6,
                        fontWeight: isActiveSlide ? '600' : '400',
                      }}>
                        Slide {index + 1} of {slides.length}
                      </Text>

                      {/* Content-sized wrapper: PresentationCanvas renders taller than the
                          slide drawing (it includes its own info bar), so forcing the canvas
                          height here squeezes it and creates an inner scrollbar. The overlay
                          is anchored top-left with explicit canvas dims instead. */}
                      <View style={{ position: 'relative' }}>
                      <PresentationCanvas
                        ref={slideRef}
                        slide={slide}
                        isActiveSlide={isActiveSlide}
                        externalEditSessionId={agentTurnIdRef.current}
                        scale={canvasScale}
                        presentationStyle={presentationStyle}
                        iconSet={presentationStyle?.iconSet}
                        awareness={collaboration?.awareness}
                        theme={safeTheme}
                        isEditable={true}
                        hideToolbar={true}
                        selectedElementId={isActiveSlide ? selectedElementId : null}
                        onSelectElement={handleSelectElement}
                        onUpdateElement={(slideId, elementId, updates) => handleElementUpdate(slide.id, elementId, updates)}
                        onUpdateSlideBackground={(color) => {
                          updateSlideBackground(slide.id, { backgroundColor: color });
                        }}
                        onAddElement={(slideId, type, data) => handleAddElement(slide.id, type, data)}
                        onDeleteElement={(slideId, elementId) => handleDeleteElement(slide.id, elementId)}
                        onDeleteMultipleElements={(slideId, elementIds) => handleDeleteMultipleElements(slide.id, elementIds)}
                        onGenerateImage={handleGenerateImage}
                        onOpenStylePicker={() => setShowStylePicker(true)}
                        onOpenChartHelp={() => setShowChartStudio(true)}
                        onOpenDiagram={handleOpenDiagram}
                        onEditChart={handleEditChart}
                        onEditDiagram={handleRegenerateDiagram}
                        onCanvasFocus={() => {
                          // Discard selection on other canvases
                          canvasRefsMap.current.forEach((ref, id) => {
                            if (id !== slide.id && ref.current?.discardSelection) {
                              ref.current.discardSelection();
                            }
                          });
                          activeCanvasRef.current = slideRef.current;
                          canvasRef.current = slideRef.current;
                          if (slide.id !== currentSlideId) {
                            slideChangeFromInteraction.current = true;
                            setCurrentSlideId(slide.id);
                          }
                        }}
                        onElementSelectionChange={(info) => {
                          setSelectionInfo(info);
                          if (info.hasSelection) {
                            canvasRefsMap.current.forEach((ref, id) => {
                              if (id !== slide.id && ref.current?.discardSelection) {
                                ref.current.discardSelection();
                              }
                            });
                          }
                          activeCanvasRef.current = slideRef.current;
                          canvasRef.current = slideRef.current;
                          if (slide.id !== currentSlideId) {
                            slideChangeFromInteraction.current = true;
                            setCurrentSlideId(slide.id);
                          }
                        }}

                        presentationTitle={presentationTitle}
                        presentationId={currentPresentationId}
                        onSave={() => setShowSaveModal(true)}
                        onExport={() => setShowExportModal(true)}
                        onPresent={() => startPresentation()}
                        onClose={() => setShowCloseConfirmModal(true)}
                        isGenerating={isGeneratingSlides}
                        generationProgress={generationProgress}
                        onRenderComplete={handleCanvasRenderComplete}

                        onCopyElements={copyElements}
                        onPasteElements={(clipboardText) => {
                          const pastedData = parsePastedElements(clipboardText);
                          if (!pastedData || !pastedData.data) return;

                          if (pastedData.type === 'slide') {
                            // Paste as a new slide after the current one
                            const insertIdx = currentSlideIndex + 1;
                            addSlide(insertIdx, null, null, {
                              ...pastedData.data,
                              order: insertIdx + 1,
                            });
                            return;
                          }

                          // Elements paste onto the current slide
                          if (slide?.id) {
                            const targetSlide = slides.find(s => s.id === slide.id);
                            if (targetSlide) {
                              const existingElements = targetSlide.elements || [];
                              const maxZ = existingElements.length > 0
                                ? Math.max(...existingElements.map(e => parseInt(e.zIndex) || 0)) + 1
                                : 1;
                              const newElements = pastedData.data.map((el, idx) => ({
                                ...el,
                                x: Math.min(el.x || 0, SLIDE_WIDTH - 20),
                                y: Math.min(el.y || 0, SLIDE_HEIGHT - 20),
                                zIndex: maxZ + idx,
                              }));
                              updateSlide(slide.id, { elements: [...existingElements, ...newElements] });
                            }
                          }
                        }}
                        formatPainterActive={formatPainterActive}
                        formatPainterData={formatPainterData}
                        onFormatPainterApply={(targetElement) => {
                          if (formatPainterData && targetElement && canApplyFormat(formatPainterData, targetElement)) {
                            const applicableFormat = getApplicableFormat(formatPainterData, targetElement.type);
                            if (applicableFormat && slide?.id) {
                              handleElementUpdate(slide.id, targetElement.id, applicableFormat);
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
                        onShowAnalytics={() => setShowAnalyticsModal(true)}
                        onShowCollaboration={() => setShowCollaborationPanel(true)}
                        collaborationStatus={collaboration?.status}
                        collaborators={collaboration?.collaborators}
                        userType={userType}
                        onUpgrade={onOpenCredits}
                        generationQuality={generationQuality}
                        qualityLabel={qualityLabel}
                        qualityColor={qualityColor}
                        onShowQualityModal={presentationGoal ? () => setShowQualityModal(true) : undefined}
                      />
                      <DeckChromeOverlay
                        width={SLIDE_WIDTH * canvasScale}
                        height={SLIDE_HEIGHT * canvasScale}
                        headerFooter={headerFooter}
                        slideNumbers={slideNumbers}
                        index={index}
                        total={slides.length}
                        noun="Slide"
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
              <View style={{ width: 1, height: '100%', backgroundColor: safeTheme.border, marginLeft: 2 }} />
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
                  borderLeftColor: '#E2E8F0',
                  borderRightWidth: 0,
                  paddingBottom: 0,
                  shadowColor: '#000',
                  shadowOffset: { width: -4, height: 0 },
                  shadowOpacity: 0.05,
                  shadowRadius: 12,
                  elevation: 5,
                  zIndex: 50,
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
                  <ScrollView style={{ flex: 1, marginBottom: 10, marginTop: 16 }}>
                    <Text style={{ fontSize: 13, color: safeTheme.textSecondary, lineHeight: 22, fontWeight: '400', paddingHorizontal: 4 }}>
                      I can see your whole deck — edit, add, delete or reorder slides, restyle, review. Try:
                    </Text>
                    <View style={{ marginTop: 16, gap: 10, paddingHorizontal: 4 }}>
                      {[
                        '🔍 Review all slides and suggest improvements',
                        '✨ Make this slide more professional',
                        '➕ Add a summary slide at the end',
                        '🔢 Add slide numbers and a footer',
                      ].map((example) => (
                        <TouchableOpacity
                          key={example}
                          onPress={() => !isAiProcessing && !isAiLocked && handleAgentEdit(example.replace(/^\S+\s/, ''))}
                          style={{
                            backgroundColor: '#F8FAFC',
                            padding: 12,
                            borderRadius: 12,
                            borderWidth: 1,
                            borderColor: '#E2E8F0',
                            shadowColor: '#000',
                            shadowOffset: { width: 0, height: 1 },
                            shadowOpacity: 0.02,
                            shadowRadius: 2,
                          }}
                        >
                          <Text style={{ fontSize: 12, color: safeTheme.text }}>{example}</Text>
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
                    {editMode !== 'slide' && selectedElements.length > 0 && (
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
                                backgroundColor: '#FFFFFF',
                                paddingHorizontal: 8,
                                paddingVertical: 6,
                                borderRadius: 6,
                                marginRight: 6,
                                borderWidth: 1,
                                borderColor: '#DDD6FE',
                                maxWidth: 140,
                              }}
                            >
                              <Ionicons
                                name={
                                  el.type === 'text' ? 'text' :
                                    el.type === 'image' ? 'image' :
                                      el.type === 'shape' ? 'shapes' :
                                        el.type === 'icon' ? 'apps' :
                                          el.type === 'card' ? 'card' :
                                            el.type === 'chart' ? 'bar-chart' :
                                              'cube-outline'
                                }
                                size={14}
                                color="#8B5CF6"
                                style={{ marginRight: 6 }}
                              />
                              <Text
                                style={{
                                  fontSize: 10,
                                  color: '#6D28D9',
                                  fontWeight: '500',
                                  flex: 1,
                                }}
                                numberOfLines={1}
                                ellipsizeMode="tail"
                              >
                                {el.type === 'text' && el.text ?
                                  (el.text.length > 15 ? el.text.substring(0, 15) + '...' : el.text) :
                                  el.type.charAt(0).toUpperCase() + el.type.slice(1)
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
                              backgroundColor: msg.actionType === 'user' ? '#F9FAFB' : (msg.actionType === 'create_new' ? '#F0FDF4' : '#EFF6FF'),
                              borderRadius: 12,
                              padding: 10,
                              marginBottom: 6,
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
                            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 3 }}>
                              <Ionicons
                                name={msg.actionType === 'user' ? 'person-circle-outline' : (msg.actionType === 'create_new' ? 'add-circle' : 'sparkles')}
                                size={13}
                                color={msg.actionType === 'user' ? '#6B7280' : (msg.actionType === 'create_new' ? '#16A34A' : '#2563EB')}
                              />
                              <Text style={{ fontSize: 10, fontWeight: '600', color: msg.actionType === 'user' ? '#6B7280' : (msg.actionType === 'create_new' ? '#15803D' : '#1D4ED8'), marginLeft: 5 }}>
                                {msg.actionType === 'user' ? 'You' : (msg.actionType === 'create_new' ? 'New Slide Created' : 'AI')}
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
                      {/* Top Row: Attachment + Scope Selector */}
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Tooltip text="Attach File" theme={safeTheme}>
                          <TouchableOpacity
                            style={{
                              padding: 10,
                              backgroundColor: safeTheme.background,
                              borderRadius: 8,
                              borderWidth: 1,
                              borderColor: safeTheme.border,
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
                            <Ionicons name="attach" size={18} color={safeTheme.textSecondary || '#666'} />
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
                                style={{ width: 44, height: 44, borderRadius: 8, borderWidth: 1, borderColor: '#E2E8F0' }}
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
                            backgroundColor: isAiLocked ? '#F3F4F6' : '#F8FAFC',
                            color: isAiLocked ? '#9CA3AF' : safeTheme.text,
                            borderColor: '#E2E8F0',
                            flex: 1,
                            marginBottom: 0, // Remove bottom margin as container handles it
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
                          placeholder={isAiLocked ? "AI is currently locked..." : (editMode === 'slide' ? 'Ask anything — edit, add, reorder, review slides…' : `Edit ${getElementTypeLabel(selectedElements).toLowerCase()}...`)}
                          placeholderTextColor="#94A3B8"
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
                        style={[styles.aiChatBtn, {
                          backgroundColor: isAiProcessing ? '#EF4444' : '#2563EB',
                          opacity: isAiProcessing ? 1 : (((chatInput.trim() || aiPastedImages.length > 0) && !isAiLocked) ? 1 : 0.6),
                          borderRadius: 12,
                          paddingVertical: 12,
                          shadowColor: isAiProcessing ? '#EF4444' : '#2563EB',
                          shadowOffset: { width: 0, height: 2 },
                          shadowOpacity: 0.2,
                          shadowRadius: 4,
                          elevation: 2,
                        }]}
                        onPress={() => isAiProcessing ? handleStopAgent() : handleAgentEdit()}
                        disabled={isAiProcessing ? false : ((!chatInput.trim() && aiPastedImages.length === 0) || isAiLocked)}
                      >
                        {isAiProcessing ? (
                          <>
                            <Ionicons name="stop" size={16} color="#fff" />
                            <Text style={[styles.aiChatBtnText, { fontWeight: '600', fontSize: 14, marginLeft: 6 }]}>Stop</Text>
                          </>
                        ) : (
                          <>
                            <Ionicons name="sparkles" size={16} color="#fff" />
                            <Text style={[styles.aiChatBtnText, { fontWeight: '600', fontSize: 14, marginLeft: 6 }]}>Enhance</Text>
                          </>
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              ) : (
                /* Layer Panel Content */
                <LayerPanel
                  slide={currentSlide}
                  selectedElementId={selectedElementId}
                  onSelectElement={handleSelectElement}
                  onUpdateElement={handleElementUpdate}
                  onDeleteElement={handleDeleteElement}
                  theme={safeTheme}
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
            <PresentationGoalInput
              visible={showGoalSetting}
              onClose={() => {
                userDismissedGoalModalRef.current = true;
                setShowGoalSetting(false);
              }}
              onPresentationGenerated={handlePresentationGenerated}
              onGoalSet={handleGoalSet}
              existingGoal={presentationGoal}
              prefillGoal={prefillGoal}
              onUsePrefill={onUsePrefill}
              apiConfig={apiConfig}
              userDeviceId={userDeviceId}
              selectedFolders={selectedFolders}
              folders={folders}
              theme={safeTheme}
              persona={persona}
              uploadModalProps={uploadModalProps}
              enhancedProgress={enhancedProgress}
            />
          </Modal>
        )}

        {/* Slide Layout Picker */}
        <SlideLayoutPicker
          visible={showLayoutPicker}
          onClose={() => setShowLayoutPicker(false)}
          onSelectLayout={handleLayoutSelected}
          theme={safeTheme}
          mobileViewOnly={mobileViewOnly}
        />

        {/* Presentation Player */}
        <PresentationPlayer
          visible={isPlaying}
          onClose={() => setIsPlaying(false)}
          slides={visibleSlides}
          initialSlideId={currentSlideId}
          theme={safeTheme}
          presentationStyle={presentationStyle}
        />

        <ChartStudio
          visible={showChartStudio}
          onClose={() => setShowChartStudio(false)}
          onInsertChart={(chartConfig, title) => {
            // Insert chart as interactive fabric.Chart object using canvas ref
            if (currentSlide?.id && canvasRef.current) {
              canvasRef.current.addChart(chartConfig);
            }
            setShowChartStudio(false);
          }}
          sourceContext="presentation"
          pageContext={currentSlide} // NEW: Pass current slide for AI context
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
            if (currentSlide?.id) {
              handleAddElement(currentSlide.id, 'image', {
                src: imageUrl,
                x: 150,
                y: 100,
                width: 500,
                height: 500,
              });
            }
            setShowAIImageModal(false);
          }}
          currentPage={currentSlide}
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
            if (!currentSlide?.id) {
              setShowAIDiagramModal(false);
              setDiagramRegenContext(null);
              return;
            }
            if (diagramRegenContext?.elementId) {
              // Regenerate-in-place: update the existing svg_diagram element.
              updateElement(currentSlide.id, diagramRegenContext.elementId, {
                svgContent: svg,
                prompt,
                diagramKind,
                diagramTitle: title || '',
              });
            } else {
              // Insert as a new svg_diagram element on the current slide.
              handleAddElement(currentSlide.id, 'svg_diagram', {
                svgContent: svg,
                svg, // also pass under `svg` for forward-compat
                prompt,
                diagramKind,
                diagramTitle: title || '',
                x: 150,
                y: 100,
                width: 660,
                height: 340,
              });
            }
            setShowAIDiagramModal(false);
            setDiagramRegenContext(null);
          }}
          currentPage={currentSlide}
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
              {[{ key: 'premium', label: 'Premium', price: '~$0.10 / slide', icon: 'diamond', color: safeTheme.primary || '#6366F1', desc: 'Best image quality' },
                { key: 'medium', label: 'Medium', price: '~$0.05 / slide', icon: 'flash', color: '#F59E0B', desc: 'Good quality, faster' },
                { key: 'basic', label: 'Basic', price: '~$0.02 / slide', icon: 'leaf', color: '#9CA3AF', desc: 'Fast & economical' },
              ].map((opt) => (
                <TouchableOpacity
                  key={opt.key}
                  onPress={() => { setPresentationGoal(prev => ({ ...prev, generationQuality: opt.key })); setShowQualityModal(false); }}
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
                <Text style={[styles.modalTitle, { color: safeTheme.text }]}>Presentation Style</Text>
                <TouchableOpacity onPress={() => setShowStylePicker(false)}>
                  <Ionicons name="close" size={24} color={safeTheme.text} />
                </TouchableOpacity>
              </View>
              <PresentationStylePicker
                theme={safeTheme}
                selectedStyle={presentationStyle}
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
        <PresentationExport
          visible={showExportModal}
          onClose={() => setShowExportModal(false)}
          slides={visibleSlides}
          presentationTitle={presentationTitle}
          style={presentationStyle}
          theme={safeTheme}
          userType={userType}
          onOpenCredits={onOpenCredits}
        />

        {/* Delete Confirmation Modal */}
        <Modal visible={showDeleteModal} transparent animationType="fade" onRequestClose={cancelDeleteSlide}>
          <View style={styles.modalOverlay}>
            <View style={[styles.deleteModal, { backgroundColor: safeTheme.background }]}>
              <Text style={[styles.deleteModalTitle, { color: safeTheme.text }]}>Delete Slide?</Text>
              <Text style={[styles.deleteModalText, { color: safeTheme.textSecondary || '#666' }]}>
                This action cannot be undone.
              </Text>
              <View style={styles.deleteModalButtons}>
                <TouchableOpacity
                  style={[styles.deleteModalBtn, styles.cancelBtn, { borderColor: safeTheme.border }]}
                  onPress={cancelDeleteSlide}
                >
                  <Text style={[styles.deleteModalBtnText, { color: safeTheme.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.deleteModalBtn, styles.confirmDeleteBtn]}
                  onPress={confirmDeleteSlide}
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

        {/* Presentation Analytics Modal */}
        <PresentationAnalyticsModal
          visible={showAnalyticsModal}
          onClose={() => setShowAnalyticsModal(false)}
          presentationId={currentPresentationId}
          presentationTitle={presentationTitle}
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

        {/* Arrange Slides Modal */}
        <Modal visible={showArrangeModal} transparent animationType="fade" onRequestClose={() => setShowArrangeModal(false)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingTop: 16, paddingBottom: 24 }}>
              {/* Handle bar */}
              <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: '#D1D5DB', alignSelf: 'center', marginBottom: 12 }} />
              {/* Header */}
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, marginBottom: 14 }}>
                <Text style={{ fontSize: 17, fontWeight: '700', color: '#111827' }}>Arrange Slides</Text>
                <TouchableOpacity onPress={() => setShowArrangeModal(false)} style={{ padding: 4 }}>
                  <Ionicons name="close" size={22} color="#6B7280" />
                </TouchableOpacity>
              </View>
              {/* Scrollable slide cards */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 10 }}>
                {slides.map((slide, index) => (
                  <View key={slide.id} style={{ alignItems: 'center', width: 110 }}>
                    {/* Card */}
                    <TouchableOpacity
                      onPress={() => { handleSelectSlide(slide.id); setShowArrangeModal(false); }}
                      style={{
                        width: 100, height: 70, borderRadius: 10, borderWidth: 2,
                        borderColor: slide.id === currentSlideId ? '#4F46E5' : '#E5E7EB',
                        backgroundColor: slide.id === currentSlideId ? '#EEF2FF' : '#F9FAFB',
                        justifyContent: 'center', alignItems: 'center', marginBottom: 6,
                      }}
                    >
                      <Text style={{ fontSize: 20, fontWeight: '700', color: slide.id === currentSlideId ? '#4F46E5' : '#6B7280' }}>{index + 1}</Text>
                    </TouchableOpacity>
                    {/* Title */}
                    <Text numberOfLines={1} style={{ fontSize: 10, color: '#374151', textAlign: 'center', marginBottom: 6, paddingHorizontal: 2 }}>
                      {slide.title || `Slide ${index + 1}`}
                    </Text>
                    {/* Reorder arrows */}
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <TouchableOpacity
                        disabled={index === 0}
                        onPress={() => { reorderSlides(index, index - 1); }}
                        style={{ padding: 4, opacity: index === 0 ? 0.25 : 1 }}
                      >
                        <Ionicons name="arrow-back" size={16} color="#4F46E5" />
                      </TouchableOpacity>
                      <TouchableOpacity
                        disabled={index === slides.length - 1}
                        onPress={() => { reorderSlides(index, index + 1); }}
                        style={{ padding: 4, opacity: index === slides.length - 1 ? 0.25 : 1 }}
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
          reportId={currentPresentationId}
          currentUser={collaboration?.ydoc?.clientID}
          theme={safeTheme}
          apiConfig={API_CONFIG}
          collaborators={collaboration?.collaborators}
        />

        {/* Edit Single Slide Topic & Outline Modal */}
        <EditSlideOutlineModal
          visible={!!editOutlineSlide}
          onClose={() => setEditOutlineSlide(null)}
          onSave={handleSaveSlideOutline}
          theme={safeTheme}
          itemLabel="Slide"
          initialTitle={editOutlineSlide?.title || ''}
          initialOutline={editOutlineSlide?.outline || editOutlineSlide?.sectionTopic || ''}
        />

        {/* Update Instruction Modal */}
        <UpdateInstructionModal
          visible={showUpdateInstructionModal}
          onClose={() => setShowUpdateInstructionModal(false)}
          onConfirm={handleConfirmUpdate}
          isUpdating={isAutoUpdating}
          theme={safeTheme}
          title="Update All Slides"
          itemLabel="Slide"
          currentGoal={presentationGoal}
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
  addSlideBtn: {
    padding: 6,
    borderRadius: 6,
  },
  slideList: {
    flex: 1,
  },
  slideItemContainer: {
    marginBottom: 8,
  },
  slideItem: {
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent', // Default transparent
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 4,
  },
  slideItemActive: {
    borderLeftColor: '#2563EB', // Active Highlight
  },
  // Thumbnail view styles
  slideThumbnailItem: {
    borderRadius: 8,
    borderWidth: 2,
    padding: 8,
    marginBottom: 4,
    alignItems: 'center',
  },
  slideThumbnailItemActive: {
    borderWidth: 2,
  },
  slideThumbnailActions: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  // Legacy thumbnail (small icon in list view)
  slideThumbnail: {
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
  slideNumberOverlay: {
    fontSize: 12,
    fontWeight: '600',
    color: '#666',
  },
  slideInfo: {
    flex: 1,
    minWidth: 0, // Allow flex items to shrink below content size
  },
  slideItemTitle: {
    fontSize: 12,
    fontWeight: '500',
  },
  slideTitleInput: {
    fontSize: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2196F3',
    paddingVertical: 2,
  },
  slideActions: {
    flexDirection: 'row',
    gap: 2,
  },
  slideActionBtn: {
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
    padding: 0,
  },
  slideNavigation: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
    gap: 20,
  },
  navBtn: {
    padding: 8,
  },
  slideCounter: {
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
    borderRadius: 12,
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

export default PresentationComposer;
