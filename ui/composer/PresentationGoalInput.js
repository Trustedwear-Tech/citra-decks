// PresentationGoalInput.js - Goal input and slide outline generation for presentations
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  Platform,
  useWindowDimensions,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import PresentationStylePicker, { PRESET_STYLES } from './PresentationStylePicker';
import { processSlideAsync } from './utils/slidePostProcessor';
import { SLIDE_TEMPLATES } from './utils/slideTemplates';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import ImageGenService from '../../services/ImageGenService';
import globalImageCache from '../../utils/globalImageCache';
import authService from '../../services/authService';
import UnifiedUploadModal from '../UnifiedUploadModal'; // Unified upload modal
import UploadProgressPopup from '../UploadProgressPopup'; // Upload progress popup for visibility inside modal

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
      console.log('ðŸ’° [CREDITS] Detected credit error in string data:', data.substring(0, 100));
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
    console.log('ðŸ’° [CREDITS] Detected insufficient_credits error type');
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
      console.log('ðŸ’° [CREDITS] Detected credit error in message:', messageStr.substring(0, 100));
      return true;
    }
  }

  // Also check if data.error contains credit-related keywords (for dict-like error responses)
  if (typeof errorType === 'string' && errorType.toLowerCase().includes('insufficient')) {
    console.log('ðŸ’° [CREDITS] Detected credit error in error field:', errorType);
    return true;
  }

  return false;
};

/**
 * Credit error handler â€” stubbed under license model (no credit enforcement)
 */
const handleCreditError = (data) => {
  return false; // License model: unlimited credits, no credit errors
};

/**
 * PresentationGoalInput - Goal setting and slide outline generation
 * 
 * Flow:
 * 1. User writes presentation goal/topic
 * 2. AI generates slide outline (titles + content hints)
 * 3. User can EDIT, ADD, DELETE, REORDER slides
 * 4. User selects or generates style theme
 * 5. Generate presentation slides one at a time
 */
const PresentationGoalInput = ({
  onPresentationGenerated,
  onGoalSet,
  existingGoal = null,
  prefillGoal = null,   // {goal, slide_count, prefetched_corpus} from a chat open_builder handoff
  onUsePrefill = null,  // called once the prefill has been consumed
  visible = false,
  onClose,
  apiConfig,
  userDeviceId,
  selectedFolders = [],
  folders = [],
  theme,
  persona = null,
  onOpenUploadModal, // DEPRECATED: Not used, we use internal state now
  uploadModalProps, // NEW: Props for internal ChatUniversalUploadModal
  enhancedProgress, // Upload progress for showing popup inside modal
}) => {
  // Goal validation constants
  const MAX_GOAL_WORDS = 500;

  const { width: windowWidth } = useWindowDimensions();
  const isMobile = windowWidth < 768;

  // Helper function to count words
  const countWords = (text) => {
    if (!text) return 0;
    return text.trim().split(/\s+/).filter(word => word.length > 0).length;
  };

  // Goal state
  const [goal, setGoal] = useState('');
  const [goalWordCount, setGoalWordCount] = useState(0);
  const [targetAudience, setTargetAudience] = useState('');
  const [presentationType, setPresentationType] = useState('informative');
  // Deck profile — TWO options only as of 2026-05-19:
  //   - 'corporate' (default): merged executive + visuals catalog,
  //     storyboard-locked deck-coherent background image on every slide.
  //   - 'general': full photo-rich library, free-form LLM layout, per-slide
  //     vision critique runs automatically. Filters which
  // templates the matcher draws from.
  // NOTE: Corporate path produces less compelling output than General right now,
  // so the UI selector is hidden and we default everyone to 'general'. The
  // corporate template/style code paths remain intact for future re-enablement.
  const [deckProfile, setDeckProfile] = useState('general');
  // Deck-level storyboard captured from outline-stream SSE. Sent verbatim
  // to every /presentation/generate-slide call so all slides share one
  // palette / typography / background_style and the server can lock the
  // design language. null until the storyboard SSE event arrives.
  const [deckPlan, setDeckPlan] = useState(null);
  const [slideCount, setSlideCount] = useState(10);
  const [customSlideCount, setCustomSlideCount] = useState('');
  const [currentStep, setCurrentStep] = useState(1);
  const [isGeneratingOutline, setIsGeneratingOutline] = useState(false);
  const [slideOutline, setSlideOutline] = useState([]);

  // Internal modal state
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);
  const [editingSlideId, setEditingSlideId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [editingContent, setEditingContent] = useState('');

  // Style selection
  const [selectedStyle, setSelectedStyle] = useState(PRESET_STYLES[0]);
  const [selectedStyleId, setSelectedStyleId] = useState('corporate'); // For TemplateSelector
  // Per-slide template mapping for the Corporate path: { 0: 'title_hero', 1: 'three_cards', ... }
  // Unused when deckProfile === 'general' (server bypasses templates entirely).
  const [slideTemplateMap, setSlideTemplateMap] = useState({});
  const [useAutoTemplateMapping, setUseAutoTemplateMapping] = useState(true); // Auto-map by default
  const [customStyles, setCustomStyles] = useState([]);
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [iconSet, setIconSet] = useState('lucide'); // New: Icon Set preference
  const [showAdvancedSetup, setShowAdvancedSetup] = useState(false); // Collapsed by default for streamlined flow
  const [specialInstructions, setSpecialInstructions] = useState(''); // User guidance for AI generation
  const [generationQuality, setGenerationQuality] = useState('medium'); // 'premium', 'medium' or 'basic'
  const [useInternetSearch, setUseInternetSearch] = useState(false); // Pull latest data from internet for each slide

  // Loading states
  const [isGeneratingStyle, setIsGeneratingStyle] = useState(false);
  const [isGeneratingPresentation, setIsGeneratingPresentation] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0 });
  const [errorMessage, setErrorMessage] = useState('');

  // Cancellation state for presentation generation
  const [isPresentationCancelled, setIsPresentationCancelled] = useState(false);
  const presentationCancelRef = React.useRef(false);
  // Research corpus from a chat `open_builder` handoff — forwarded to the
  // outline endpoint as `prefetched_corpus` so the deck is grounded on it.
  const prefillCorpusRef = React.useRef([]);

  // Presentation types
  const presentationTypes = [
    { value: 'informative', label: 'Informative', icon: 'information-circle-outline', description: 'Share knowledge and facts' },
    { value: 'persuasive', label: 'Persuasive', icon: 'megaphone-outline', description: 'Convince and influence' },
    { value: 'instructional', label: 'Instructional', icon: 'school-outline', description: 'Teach and guide' },
    { value: 'pitch', label: 'Pitch Deck', icon: 'rocket-outline', description: 'Sell an idea or product' },
    { value: 'proposal', label: 'Proposal', icon: 'document-text-outline', description: 'Formal request or business plan' },
    { value: 'report', label: 'Report', icon: 'bar-chart-outline', description: 'Present findings' },
  ];

  // Helper: Promise with timeout â€” rejects if promise doesn't settle within ms
  const withTimeout = (promise, ms, label = '') => {
    let timer;
    return Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`Timeout after ${ms / 1000}s${label ? ': ' + label : ''}`)), ms);
      }),
    ]).finally(() => clearTimeout(timer));
  };

  // Helper: Exponential Backoff Retry (with rate limit awareness)
  const retryWithBackoff = async (fn, retries = 3, delay = 1000) => {
    try {
      return await fn();
    } catch (error) {
      // Never retry credit/billing errors - immediately propagate
      const errMsg = error.message || '';
      if (errMsg.includes('CREDITS_REQUIRED') ||
        errMsg.includes('insufficient_credits') ||
        errMsg.includes('Negative balance') ||
        errMsg.includes('purchase credits')) {
        console.log('ðŸ’° [CREDITS] Not retrying credit error');
        throw error;
      }

      if (retries === 0) throw error;

      // Detect 429 rate limit errors - wait much longer before retrying
      const is429 = errMsg.includes('429') || errMsg.includes('rate limit') || errMsg.includes('Rate limit');
      const retryDelay = is429 ? Math.max(delay, 15000) : delay; // Wait at least 15s on rate limit

      console.log(`âš ï¸ Request failed${is429 ? ' (RATE LIMITED)' : ''}, retrying in ${retryDelay / 1000}s... (${retries} attempts left). Error: ${errMsg}`);
      await new Promise(resolve => setTimeout(resolve, retryDelay));
      // On 429, don't use exponential backoff (already long), just retry at same interval
      return retryWithBackoff(fn, retries - 1, is429 ? retryDelay : delay * 2);
    }
  };

  // Load existing goal
  useEffect(() => {
    if (existingGoal) {
      setGoal(existingGoal.goal || existingGoal.purpose || '');
      setTargetAudience(existingGoal.targetAudience || '');
      if (existingGoal.slideOutline) {
        setSlideOutline(existingGoal.slideOutline);
      }
      if (existingGoal.style) {
        setSelectedStyle(existingGoal.style);
      }
      if (existingGoal.deckProfile === 'corporate' || existingGoal.deckProfile === 'general') {
        setDeckProfile(existingGoal.deckProfile);
      }
    }
  }, [existingGoal]);

  // Chat → composer handoff: a quick/main-chat turn handed off via
  // `open_builder` with the goal + the research it gathered. Pre-fill the
  // goal, stash the corpus for the outline request, and auto-start outline
  // generation so the user lands straight in the streaming build.
  useEffect(() => {
    // Fires once per handoff: onUsePrefill() nulls prefillGoal in the
    // parent, so the only re-fire is with null (caught by the guard).
    // A later handoff sets a fresh object and correctly fires again.
    if (!prefillGoal?.goal) return;
    setGoal(prefillGoal.goal);
    setGoalWordCount(countWords(prefillGoal.goal));
    const sc = parseInt(prefillGoal.slide_count, 10);
    if (sc >= 3 && sc <= 20) setSlideCount(sc);
    prefillCorpusRef.current = Array.isArray(prefillGoal.prefetched_corpus)
      ? prefillGoal.prefetched_corpus
      : [];
    onUsePrefill?.();
    // Pass the values straight into generateOutline — setGoal/setSlideCount
    // above are async, so the call must not rely on committed state.
    generateOutline({
      goalOverride: prefillGoal.goal,
      slideCountOverride: (sc >= 3 && sc <= 20) ? sc : 10,
      corpusOverride: prefillCorpusRef.current,
      folderIdsOverride: Array.isArray(prefillGoal.folder_ids) ? prefillGoal.folder_ids : [],
    });
  }, [prefillGoal]);

  // Auto-map templates when slide outline changes (if auto mode enabled)
  useEffect(() => {
    if (useAutoTemplateMapping && slideOutline.length > 0) {
      const mapping = autoMapTemplatesToSlides(slideOutline);
      setSlideTemplateMap(mapping);
    }
  }, [slideOutline, useAutoTemplateMapping]);

  const autoMapTemplatesToSlides = (slides) => {
    const mapping = {};

    slides.forEach((slide, idx) => {
      // DEFAULT TO AI DECIDE FOR EVERYTHING
      // This allows the backend to be the single source of truth for layout decisions
      // unless the user manually overrides specific slides.
      mapping[idx] = 'ai_auto';
    });

    return mapping;
  };

  /**
   * Get template for a specific slide index
   */
  const getTemplateForSlide = (slideIndex) => {
    return slideTemplateMap[slideIndex] || 'three_cards';
  };

  /**
   * Update template for a specific slide
   */
  const setTemplateForSlide = (slideIndex, templateId) => {
    setSlideTemplateMap(prev => ({
      ...prev,
      [slideIndex]: templateId
    }));
    // When user manually changes, disable auto-mapping
    if (useAutoTemplateMapping) {
      setUseAutoTemplateMapping(false);
    }
  };

  // Placeholder example - generic for all users
  const getPlaceholderExample = () => {
    return "Create a presentation on digital transformation strategies for small businesses, covering technology adoption, change management, and ROI measurement.";
  };

  const { useUploadedData, setUseUploadedData } = useWorkspace();

  // Guard: check the data-source toggle is on before allowing features that need it.
  // selectedFolders is always exactly one auto-created folder now, never empty —
  // the only real gate left is the useUploadedData toggle itself.
  const requireVault = useCallback((featureMessage) => {
    if (!useUploadedData || !selectedFolders || selectedFolders.length === 0) {
      Alert.alert('Data Source Required', featureMessage);
      return false;
    }
    return true;
  }, [useUploadedData, selectedFolders]);

  // Streaming state for outline generation
  const [streamingProgress, setStreamingProgress] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  // Handle goal text change with word count validation
  const handleGoalChange = (text) => {
    const words = countWords(text);
    setGoal(text);
    setGoalWordCount(words);
  };

  // Generate slide outline using AI with streaming.
  // `opts` lets the chat → composer prefill path pass values directly,
  // bypassing the state-commit race (setGoal is async; a deferred call
  // would otherwise close over the pre-prefill empty goal).
  const generateOutline = async (opts = {}) => {
    const effectiveGoal = (opts.goalOverride ?? goal);
    const effectiveCorpus = Array.isArray(opts.corpusOverride)
      ? opts.corpusOverride
      : prefillCorpusRef.current;
    if (!effectiveGoal || !effectiveGoal.trim()) {
      Alert.alert('Missing Goal', 'Please describe what presentation you want to create.');
      return;
    }

    // Validate goal word count
    if (goalWordCount > MAX_GOAL_WORDS) {
      Alert.alert('Goal Too Long', `Please reduce your goal to ${MAX_GOAL_WORDS} words. Current: ${goalWordCount} words.`);
      return;
    }

    // Apply Vault Logic for Presentation:
    // - Only use vault if folders are explicitly selected
    // - No default to 'general' for presentation (unlike chat)
    // - opts.folderIdsOverride wins for the chat-handoff path: it pins the
    //   build to the internal chat report vault where the research landed.
    const finalFolderIds = (Array.isArray(opts.folderIdsOverride) && opts.folderIdsOverride.length)
      ? opts.folderIdsOverride
      : (useUploadedData && selectedFolders.length > 0
          ? selectedFolders.map(f => f.id || f)
          : []);

    setIsGeneratingOutline(true);
    setIsStreaming(true);
    setErrorMessage('');
    setStreamingProgress('Starting...');
    setSlideOutline([]); // Clear existing slides
    setDeckPlan(null); // Reset deck plan so a re-run doesn't carry the previous one
    setCurrentStep(2); // Switch to step 2 immediately to show streaming

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        setCurrentStep(1);
        return;
      }

      console.log('ðŸŽ¯ [PRESENTATION] Generating slide outline with streaming...', { useUploadedData, finalFolderIds });

      // Validate slide count (opts.slideCountOverride wins for the prefill
      // path — see generateOutline opts).
      const slideCountNum = parseInt(opts.slideCountOverride ?? slideCount) || 10;
      if (slideCountNum < 3 || slideCountNum > 20) {
        console.log('ðŸŽ¯ [PRESENTATION] Validation failed: slide count', slideCountNum);
        setErrorMessage('Number of slides must be between 3 and 20.');
        setCurrentStep(1);
        return;
      }

      console.log('ðŸŽ¯ [PRESENTATION] Making streaming request with slide_count:', slideCountNum);

      const response = await fetch(`${apiConfig.API_URL}/presentation/generate-outline-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          goal: effectiveGoal,
          presentation_type: presentationType,
          target_audience: targetAudience,
          slide_count: slideCountNum,
          folder_ids: finalFolderIds,
          use_internet_search: useInternetSearch,
          deck_profile: deckProfile,
          prefetched_corpus: effectiveCorpus,
        }),
      });

      if (response.status === 401) {
        setCurrentStep(1);
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (handleCreditError(errorData)) {
          setCurrentStep(1);
          throw new Error(errorData.message || 'Insufficient credits');
        }
        setCurrentStep(1);
        throw new Error(errorData.detail || 'Failed to generate outline');
      }

      // Read the streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const streamedSlides = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'progress') {
                setStreamingProgress(data.message);
                console.log('ðŸŽ¯ [PRESENTATION] Progress:', data.message);
              } else if (data.type === 'internet_research') {
                console.log('ðŸŒ [PRESENTATION] Internet research embedded:', data.document_id, 'folder:', data.folder_id, 'words:', data.word_count);
              } else if (data.type === 'slide') {
                // Add slide with unique ID
                const slideWithId = {
                  ...data.slide,
                  id: `slide_${Date.now()}_${data.index}`,
                  order: data.index + 1,
                };
                streamedSlides.push(slideWithId);
                setSlideOutline([...streamedSlides]);
                console.log('ðŸŽ¯ [PRESENTATION] Received slide:', data.index + 1, slideWithId.title);
              } else if (data.type === 'storyboard') {
                // Capture the deck-level plan emitted after the slide stream.
                // Without this, every /generate-slide call falls back to a
                // baseline storyboard and slides lose deck cohesion.
                setDeckPlan(data.storyboard || null);
                setStreamingProgress('Outline ready');
                console.log('ðŸŽ¯ [PRESENTATION] Deck storyboard captured');
              } else if (data.type === 'done') {
                console.log('ðŸŽ¯ [PRESENTATION] Streaming complete. Total slides:', data.total);
                setStreamingProgress('');
              } else if (data.type === 'error') {
                console.error('ðŸŽ¯ [PRESENTATION] Stream error:', data.message);
                // Check if this is a credit error (402 insufficient_credits from streaming)
                if (handleCreditError(data.message || data)) {
                  setCurrentStep(1);
                  return; // Stop processing stream
                }
                setErrorMessage(data.message);
                if (streamedSlides.length === 0) {
                  setCurrentStep(1);
                }
              }
            } catch (parseError) {
              console.warn('ðŸŽ¯ [PRESENTATION] Failed to parse SSE data:', line);
            }
          }
        }
      }

      if (streamedSlides.length === 0) {
        throw new Error('No slides were generated');
      }

      console.log('ðŸŽ¯ [PRESENTATION] Created', streamedSlides.length, 'slide outlines via streaming');

    } catch (error) {
      console.error('Error generating outline:', error);
      setErrorMessage(error.message || 'Failed to generate slide outline. Please try again.');
      if (slideOutline.length === 0) {
        setCurrentStep(1);
      }
    } finally {
      setIsGeneratingOutline(false);
      setIsStreaming(false);
      setStreamingProgress('');
    }
  };

  // Generate AI style
  const generateAIStyle = async (stylePrompt) => {
    setIsGeneratingStyle(true);
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log('ðŸŽ¨ [PRESENTATION] Generating AI style...');

      const response = await fetch(`${apiConfig.API_URL}/presentation/generate-style`, {
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
        console.log('ðŸŽ¨ [PRESENTATION] AI style generated:', data.style.name);

        const newStyle = {
          ...data.style,
          id: `ai_style_${Date.now()}`,
          isCustom: true,
        };

        setCustomStyles(prev => [...prev, newStyle]);
        setSelectedStyle(newStyle);
      } else {
        throw new Error(data.message || 'Failed to generate style');
      }
    } catch (error) {
      console.error('Error generating style:', error);
      Alert.alert('Error', 'Failed to generate style. Please try again.');
    } finally {
      setIsGeneratingStyle(false);
    }
  };

  // Add new slide to outline
  const addNewSlide = () => {
    const newSlide = {
      id: `slide_${Date.now()}`,
      title: 'New Slide',
      content_hint: 'Describe what this slide should cover...',
      layout: 'title_content',
      order: slideOutline.length + 1,
      image_prompt: '',
    };
    setSlideOutline([...slideOutline, newSlide]);
    setEditingSlideId(newSlide.id);
    setEditingTitle(newSlide.title);
    setEditingContent(newSlide.content_hint);
  };

  // Start editing a slide
  const startEditing = (slide) => {
    setEditingSlideId(slide.id);
    setEditingTitle(slide.title);
    setEditingContent(slide.content_hint);
  };

  // Save editing
  const saveEditing = () => {
    if (!editingSlideId) return;

    setSlideOutline(slideOutline.map(slide =>
      slide.id === editingSlideId
        ? { ...slide, title: editingTitle, content_hint: editingContent }
        : slide
    ));
    setEditingSlideId(null);
    setEditingTitle('');
    setEditingContent('');
  };

  // Delete slide
  const deleteSlide = (id) => {
    if (slideOutline.length <= 1) {
      Alert.alert('Cannot Delete', 'You need at least one slide.');
      return;
    }
    setSlideOutline(slideOutline.filter(slide => slide.id !== id));
  };

  // Move slide up
  const moveSlideUp = (index) => {
    if (index <= 0) return;
    const newOutline = [...slideOutline];
    [newOutline[index - 1], newOutline[index]] = [newOutline[index], newOutline[index - 1]];
    setSlideOutline(newOutline.map((s, i) => ({ ...s, order: i + 1 })));
  };

  // Move slide down
  const moveSlideDown = (index) => {
    if (index >= slideOutline.length - 1) return;
    const newOutline = [...slideOutline];
    [newOutline[index], newOutline[index + 1]] = [newOutline[index + 1], newOutline[index]];
    setSlideOutline(newOutline.map((s, i) => ({ ...s, order: i + 1 })));
  };

  // Generate full presentation - PARALLEL EXECUTION with RETRIES
  const generatePresentation = async () => {
    if (slideOutline.length === 0) {
      Alert.alert('No Slides', 'Please add at least one slide.');
      return;
    }

    setIsGeneratingPresentation(true);
    setGenerationProgress({ current: 0, total: slideOutline.length });
    setIsPresentationCancelled(false);
    presentationCancelRef.current = false;

    // Store ALL slides in a sparse array to maintain order
    // Initialize with nulls or empty objects if needed
    // But we'll just insert by index
    const allSlides = new Array(slideOutline.length).fill(null);
    let completedCount = 0;

    // Use a reference to track credit errors to stop other tasks implies we need a shared state
    // But Promises run eagerly. If one fails with credit error, we should try to mark a global flag.
    let creditErrorOccurred = false;

    // Concurrency limiter for image generation to avoid rate limits (429)
    // Only allow N concurrent image API calls at once
    const MAX_CONCURRENT_IMAGES = 3;
    const imageQueue = [];
    let activeImageCount = 0;

    const enqueueImageGeneration = (task) => {
      return new Promise((resolve, reject) => {
        const runTask = async () => {
          activeImageCount++;
          try {
            const result = await task();
            resolve(result);
          } catch (err) {
            reject(err);
          } finally {
            activeImageCount--;
            // Process next queued task
            if (imageQueue.length > 0) {
              const next = imageQueue.shift();
              next();
            }
          }
        };

        if (activeImageCount < MAX_CONCURRENT_IMAGES) {
          runTask();
        } else {
          imageQueue.push(runTask);
        }
      });
    };

    console.log(`ðŸ–¼ï¸ [PRESENTATION] Max Concurrent Images: ${MAX_CONCURRENT_IMAGES}`);

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log('ðŸŽ¬ [PRESENTATION] Starting PARALLEL slide generation...');

      // Notify UI immediately to switch view
      if (onPresentationGenerated) {
        onPresentationGenerated({
          goal: goal,
          targetAudience: targetAudience,
          presentationType: presentationType,
          style: selectedStyle,
          templateMap: slideTemplateMap,
          slideOutline: slideOutline,
          slides: [], // Empty initially
          generatedAt: new Date().toISOString(),
          isGenerating: true,
        });
      }

      if (onGoalSet) {
        onGoalSet({
          purpose: goal,
          targetAudience: targetAudience,
          presentationType: presentationType,
          style: selectedStyle,
          templateMap: slideTemplateMap,
          slideOutline: slideOutline,
          generationQuality: generationQuality,
          folderIds: selectedFolders.map(f => f.id || f),
          deckProfile: deckProfile,
          // Storyboard captured during outline streaming — the Composer
          // forwards it on every edit/orchestrate call so per-slide edits
          // stay coherent with the deck's design language.
          deckPlan: deckPlan,
        });
      }

      onClose?.();

      // Define the worker function for a single slide
      const generateSingleSlide = async (idx) => {
        if (creditErrorOccurred) return;

        const slideInfo = slideOutline[idx];
        console.log(`ðŸŽ¬ [PARALLEL] Starting slide ${idx + 1}: ${slideInfo.title}`);

        try {
          // Use Retry Logic for the fetch
          const data = await retryWithBackoff(async () => {
            if (creditErrorOccurred) throw new Error('CREDITS_REQUIRED_SKIP');

            // Construct valid previous_slides context from OUTLINE
            // (Since we run in parallel, we can't wait for real previous content)
            const prevSlidesContext = idx > 0
              ? slideOutline.slice(Math.max(0, idx - 2), idx).map(s => ({ title: s.title, content_summary: s.content_hint }))
              : [];

            let finalSpecialInstructions = specialInstructions || '';
            if (generationQuality === 'basic') {
              const saveCostInstruction = "  do not generate description of infographic image and image with text , if image is required then only generate photo image desciption and type as photo and return type of image desciption as photo, this is done to save cost per slide generation ";
              finalSpecialInstructions = finalSpecialInstructions ? `${finalSpecialInstructions}\n\n${saveCostInstruction}` : saveCostInstruction;
            }
            console.log("UI LOG - Special Instructions Sent:", finalSpecialInstructions, "| Generation Quality:", generationQuality);

            const response = await fetch(`${apiConfig.API_URL}/presentation/generate-slide`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
              },
              body: JSON.stringify({
                slide_info: slideInfo,
                slide_index: idx,
                total_slides: slideOutline.length,
                presentation_goal: goal,
                presentation_type: presentationType,
                style: selectedStyle,
                // template_id is sent ONLY for corporate; general bypasses
                // the template path entirely and uses the legacy free-form
                // generator on the server.
                template_id: deckProfile === 'corporate' ? getTemplateForSlide(idx) : null,
                folder_ids: selectedFolders.map(f => f.id || f),
                previous_slides: prevSlidesContext,
                icon_set: iconSet,
                special_instructions: finalSpecialInstructions || null,
                generation_quality: generationQuality, // Pass down to track generation type server-side
                use_internet_search: useInternetSearch,
                deck_profile: deckProfile,
                deck_plan: deckPlan,
              }),
            });

            if (response.status === 401) throw new Error('Unauthorized');

            // Check for 402 insufficient credits BEFORE parsing body
            if (response.status === 402) {
              const errResult = await response.json().catch(() => ({}));
              const errorData = errResult.detail || errResult;
              handleCreditError(errorData);
              creditErrorOccurred = true;
              throw new Error('CREDITS_REQUIRED');
            }

            const result = await response.json();

            if (!response.ok || !result.success) {
              // Check credit error (fallback for 500-wrapped credit errors)
              const errorData = result.detail || result;
              if (handleCreditError(errorData)) {
                creditErrorOccurred = true;
                throw new Error('CREDITS_REQUIRED'); // Will be caught by retry but we check flag
              }
              throw new Error(result.message || result.detail || 'Generation failed');
            }

            return result;
          }, 3, 1000); // 3 retries, start with 1s delay

          if (data.success && data.slide) {
            console.log(`âœ… [PARALLEL] Slide ${idx + 1} raw generation complete`);

            let processedSlide = await processSlideAsync(data.slide);

            // Handle Images in Parallel (with retries too!)
            const imagePlaceholders = processedSlide.elements?.filter(el => el.type === 'image_placeholder') || [];

            if (imagePlaceholders.length > 0) {
              const imagePromises = imagePlaceholders.map(async (placeholder) => {
                const placeholderImageType = placeholder.imageType || 'photo';
                if (creditErrorOccurred) return;

                const slideTitle = slideInfo.title || 'Presentation';
                const imagePrompt = placeholder.imageDescription && placeholder.imageDescription !== 'Professional image'
                  ? placeholder.imageDescription
                  : `Professional presentation image for a slide titled "${slideTitle}". Context: ${processedSlide.elements.find(e => e.type === 'text')?.content || slideTitle}`;

                try {
                  // Determine model: medium uses LLM, otherwise let ImageGenService auto-select by imageType

                  // Retry image generation (throttled via concurrency limiter)
                  // Wrapped in 100s timeout â€” backend tries primary model 2Ã—30s + NANO_BANAO fallback 30s = max ~90s
                  const imageResult = await withTimeout(
                    enqueueImageGeneration(() =>
                      retryWithBackoff(async () => {
                        if (creditErrorOccurred) throw new Error('CREDITS_REQUIRED_SKIP');
                        // Background images use default model
                        if (placeholderImageType === 'background') {
                          return await ImageGenService.generateImage(imagePrompt, {
                            width: placeholder.width || 960,
                            height: placeholder.height || 540,
                            userId: userDeviceId,
                            imageType: 'background',
                          });
                        }
                        return await ImageGenService.generateImage(imagePrompt, {
                          style: selectedStyle?.name || 'professional',
                          width: placeholder.width || 1024,
                          height: placeholder.height || 768,
                          userId: userDeviceId,
                          imageType: placeholderImageType,
                          generationQuality: placeholder.generationQuality || generationQuality || 'premium',
                        });
                      }, 2, 2000) // Fewer retries (2), longer initial delay (2s)
                    ),
                    100000, // 100 second timeout per image (backend: 2Ã—30s primary + 30s fallback)
                    `Image for slide ${idx + 1}`
                  );

                  if (imageResult.success && (imageResult.image_data || imageResult.image_url)) {
                    placeholder.type = 'image';
                    placeholder.src = imageResult.image_data || imageResult.image_url;
                    // Pre-cache the generated image blob so it's ready for presentation mode
                    // without needing to navigate to each slide in the editor first
                    if (placeholder.src && placeholder.src.startsWith('http')) {
                      globalImageCache.fetchAndCache(placeholder.src).catch(() => { });
                    }
                  } else {
                    // Check credit error
                    if (handleCreditError(imageResult)) {
                      creditErrorOccurred = true;
                    }
                    // Fallback
                    placeholder.type = 'shape';
                    placeholder.fill = '#E2E8F0'; // specific fallback color
                    placeholder.shapeType = 'rectangle';
                  }
                } catch (imgIndErr) {
                  console.error(`âŒ Image gen error (Slide ${idx}):`, imgIndErr);
                  if (imgIndErr?.message === 'CREDITS_REQUIRED') creditErrorOccurred = true;

                  placeholder.type = 'shape';
                  placeholder.fill = '#E2E8F0';
                  placeholder.shapeType = 'rectangle';
                }
              });

              // Wait for all images on THIS slide to finish (or fail) so the slide we push is "complete"
              await Promise.all(imagePromises);
            }

            // Finalize slide object
            // critique_recommended is now true for every slide (both profiles)
            // — PresentationComposer always runs the vision-critique pass
            // after the canvas renders so subtle defects are caught uniformly.
            const finalSlide = {
              ...processedSlide,
              id: slideInfo.id,
              order: idx + 1,
              outline: slideInfo.content_hint || slideInfo.title || '',
              critique_recommended: data.critique_recommended === true,
            };

            // Store in results
            allSlides[idx] = finalSlide;

            // Check if server flagged credit exhaustion (e.g. layout fix ran out of credits)
            // The slide was still generated successfully, but no more credits remain
            if (data.credits_warning) {
              console.log('ðŸ’° [CREDITS] Server returned credits_warning with slide:', JSON.stringify(data.credits_warning));
              handleCreditError(data.credits_warning);
              creditErrorOccurred = true;
            }

          } else {
            throw new Error('No slide data returned');
          }

        } catch (err) {
          console.error(`âŒ [PARALLEL] Slide ${idx + 1} Failed after retries:`, err);
          if (err.message === 'CREDITS_REQUIRED') {
            creditErrorOccurred = true;
            return; // Stop processing
          }

          // Create Error Placeholder Slide so we don't have a hole
          const failedSlide = {
            id: slideInfo.id,
            order: idx + 1,
            title: slideInfo.title,
            layout: slideInfo.layout || 'title_content',
            elements: [
              {
                id: `el_fail_title_${idx}`,
                type: 'text',
                textType: 'title',
                content: slideInfo.title,
                x: 50, y: 40, width: 860, height: 60,
              },
              {
                id: `el_fail_body_${idx}`,
                type: 'text',
                textType: 'body',
                content: 'Content generation failed. Please edit manually.',
                x: 50, y: 120, width: 860, height: 380,
                color: "#FF0000"
              },
            ],
            backgroundColor: selectedStyle?.slideBackground || '#ffffff',
          };
          allSlides[idx] = failedSlide;
        }

        // Check for cancellation
        if (presentationCancelRef.current) {
          console.log('ðŸ›‘ [PRESENTATION] Slide generation cancelled by user');
          return;
        }

        // Update Progress & UI
        completedCount++;
        setGenerationProgress({ current: completedCount, total: slideOutline.length });

        // Notify Parent Immediately with what we have (filtering out nulls/pending)
        // This causes slides to "pop in" out of order in memory, but correct order in list
        if (onPresentationGenerated && !creditErrorOccurred) {
          const availableSlides = allSlides.filter(s => s !== null);
          onPresentationGenerated({
            goal: goal,
            targetAudience: targetAudience,
            presentationType: presentationType,
            style: selectedStyle,
            templateMap: slideTemplateMap,
            slideOutline: slideOutline,
            // Send ALL currently finished slides
            slides: availableSlides,
            generatedAt: new Date().toISOString(),
            isGenerating: completedCount < slideOutline.length,
          });
        }
      };

      // LAUNCH IN BATCHES (max 5 concurrent slides to avoid overwhelming the API)
      const MAX_CONCURRENT_SLIDES = 5;
      const slideIndices = slideOutline.map((_, idx) => idx);

      // Process in batches
      for (let i = 0; i < slideIndices.length; i += MAX_CONCURRENT_SLIDES) {
        if (creditErrorOccurred || presentationCancelRef.current) break;
        const batch = slideIndices.slice(i, i + MAX_CONCURRENT_SLIDES);
        await Promise.all(batch.map(idx => generateSingleSlide(idx)));
      }

      console.log('ðŸŽ¬ [PRESENTATION] All Parallel Tasks Finished');

      // Check if cancelled
      if (presentationCancelRef.current) {
        const completedSlides = allSlides.filter(Boolean);
        console.log(`ðŸ›‘ [PRESENTATION] Cancelled with ${completedSlides.length} slides completed`);
        Alert.alert('Cancelled', `Generated ${completedSlides.length} of ${slideOutline.length} slides before cancellation.`);

        // Still send partial results if any
        if (completedSlides.length > 0 && onPresentationGenerated) {
          onPresentationGenerated({
            goal: goal,
            targetAudience: targetAudience,
            presentationType: presentationType,
            style: selectedStyle,
            templateMap: slideTemplateMap,
            slideOutline: slideOutline,
            slides: completedSlides,
            iconSet: iconSet,
            generatedAt: new Date().toISOString(),
            isGenerating: false,
            wasCancelled: true,
          });
        }
        return;
      }

      // Final Completion Call
      if (onPresentationGenerated) {
        onPresentationGenerated({
          goal: goal,
          targetAudience: targetAudience,
          presentationType: presentationType,
          style: selectedStyle,
          templateMap: slideTemplateMap,
          slideOutline: slideOutline,
          slides: allSlides.filter(Boolean), // Ensure no holes
          iconSet: iconSet,
          generatedAt: new Date().toISOString(),
          isGenerating: false,
        });
      }

    } catch (error) {
      console.error('Error generating presentation:', error);
      if (error?.message !== 'CREDITS_REQUIRED') {
        Alert.alert('Error', 'Failed to generate presentation. Please try again.');
      }
    } finally {
      setIsGeneratingPresentation(false);
      setGenerationProgress({ current: 0, total: 0 });
    }
  };

  // Step indicator
  const StepIndicator = () => (
    <View style={[styles.stepIndicator, isMobile && { paddingVertical: 12, paddingHorizontal: 8 }]}>
      {[1, 2, 3, 4].map((step) => (
        <View key={step} style={styles.stepItem}>
          <View
            style={[
              styles.stepCircle,
              isMobile && { width: 26, height: 26, borderRadius: 13 },
              {
                backgroundColor: currentStep >= step ? theme.primary : theme.border,
              },
            ]}
          >
            {currentStep > step ? (
              <Ionicons name="checkmark" size={isMobile ? 12 : 14} color="#fff" />
            ) : (
              <Text style={[styles.stepNumber, isMobile && { fontSize: 12 }, { color: currentStep >= step ? '#fff' : theme.textSecondary }]}>
                {step}
              </Text>
            )}
          </View>
          <Text style={[styles.stepLabel, isMobile && { fontSize: 11, marginLeft: 4 }, { color: currentStep >= step ? theme.text : theme.textSecondary }]}>
            {step === 1 ? 'Goal' : step === 2 ? 'Outline' : step === 3 ? 'Template' : 'Generate'}
          </Text>
          {step < 4 && (
            <View style={[styles.stepLine, isMobile && { width: 20, marginHorizontal: 4 }, { backgroundColor: currentStep > step ? theme.primary : theme.border }]} />
          )}
        </View>
      ))}
    </View>
  );

  // Render Step 1: Goal Input
  const renderGoalStep = () => (
    <ScrollView
      style={styles.stepScroll}
      contentContainerStyle={styles.stepScrollContent}
      showsVerticalScrollIndicator={false}
      pointerEvents="auto"
      scrollEnabled={true}
    >
      <View style={[styles.stepInnerWrapper, isMobile && { padding: 14, maxWidth: '100%' }]}>
        <Text style={[styles.sectionTitle, isMobile && { fontSize: 18 }, { color: theme.text }]}>
          <Ionicons name="bulb-outline" size={isMobile ? 16 : 20} color={theme.primary} /> Presentation Goal
        </Text>
        <Text style={[styles.sectionDescription, { color: theme.textSecondary }]}>
          Describe what you want your presentation to achieve. Be specific about the topic, key points, and desired outcome.
        </Text>

        {/* Grounding folder — one auto-created folder per presentation, no
            picker. Toggle controls whether generation draws on its uploaded
            documents at all. */}
        <TouchableOpacity
          onPress={() => setUseUploadedData(!useUploadedData)}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 16,
            padding: 12,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: theme.borderColor || theme.textSecondary,
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
            <Ionicons name="folder-outline" size={18} color={theme.primary} />
            <Text style={{ color: theme.text, marginLeft: 8, flexShrink: 1 }} numberOfLines={1}>
              {selectedFolders?.[0]?.name || 'Data Source'}
            </Text>
          </View>
          <Ionicons
            name={useUploadedData ? 'toggle' : 'toggle-outline'}
            size={28}
            color={useUploadedData ? theme.primary : theme.textSecondary}
          />
        </TouchableOpacity>

        {Platform.OS === 'web' ? (
          <textarea
            style={{
              width: '100%',
              minHeight: 120,
              padding: 14,
              fontSize: 15,
              fontFamily: 'inherit',
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: theme.border,
              borderRadius: 10,
              backgroundColor: theme.surface,
              color: theme.text,
              marginBottom: 20,
              resize: 'vertical',
              outline: 'none',
              boxSizing: 'border-box',
              pointerEvents: 'auto',
            }}
            placeholder={getPlaceholderExample()}
            value={goal}
            onChange={(e) => handleGoalChange(e.target.value)}
            maxLength={3500}
            autoFocus={false}
          />
        ) : (
          <TextInput
            style={[
              styles.goalInput,
              {
                backgroundColor: theme.surface,
                color: theme.text,
                borderColor: theme.border,
              },
            ]}
            placeholder={getPlaceholderExample()}
            placeholderTextColor={theme.textSecondary}
            value={goal}
            onChangeText={handleGoalChange}
            multiline
            numberOfLines={5}
            textAlignVertical="top"
            maxLength={3500}
          />
        )}

        {/* Word Count Indicator */}
        <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: -16, marginBottom: 8 }}>
          <Text style={{
            fontSize: 12,
            color: goalWordCount > MAX_GOAL_WORDS ? '#EF4444' : theme.textSecondary,
            fontWeight: goalWordCount > MAX_GOAL_WORDS ? '600' : '400',
          }}>
            {goalWordCount} / {MAX_GOAL_WORDS} words
            {goalWordCount > MAX_GOAL_WORDS && ' (Please reduce to continue)'}
          </Text>
        </View>

        {/* Vault Attachment Button - Below Goal Input */}
        <TouchableOpacity
          onPress={() => {
            console.log('ðŸ”µ [PresentationGoalInput] Vault button clicked');
            if (!requireVault('You have turned off data store. To upload files, please select or create a data store first. Your uploaded files will be stored in the data store for AI to use as context during generation.')) return;
            setShowInternalUploadModal(true);
          }}
          style={[styles.vaultButton, {
            backgroundColor: '#FDF2F8', // Light pink background
            borderColor: '#EC4899', // Pink border
            marginBottom: 24,
            paddingVertical: 12,
            paddingHorizontal: 16,
          }]}
        >
          <Ionicons name="cloud-upload-outline" size={22} color="#EC4899" style={{ marginRight: 8 }} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: '600', color: '#EC4899', marginBottom: 2 }}>
              Upload Project Files to Data Store
            </Text>
            <Text style={{ fontSize: 11, color: '#DB2777', lineHeight: 14 }}>
              AI will remember your files as context for better presentations
            </Text>
          </View>
        </TouchableOpacity>

        {/* Deck Style picker (Corporate vs General) intentionally hidden —
            we default everyone to 'general' since it produces noticeably
            better output. Restore this block if/when the corporate path is
            tuned to parity. The corporate code paths (templates, advanced
            setup) remain wired and will reactivate automatically if
            deckProfile is flipped back to 'corporate' in state. */}

        {/* Target Audience */}
        <Text style={[styles.fieldLabel, { color: theme.text }]}>Target Audience (Optional)</Text>
        {Platform.OS === 'web' ? (
          <input
            type="text"
            style={{
              width: '100%',
              padding: 12,
              fontSize: 15,
              fontFamily: 'inherit',
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: theme.border,
              borderRadius: 8,
              backgroundColor: theme.surface,
              color: theme.text,
              marginBottom: 16,
              outline: 'none',
              boxSizing: 'border-box',
              pointerEvents: 'auto',
            }}
            placeholder="E.g., Senior executives, Technical team, Investors..."
            value={targetAudience}
            onChange={(e) => setTargetAudience(e.target.value)}
          />
        ) : (
          <TextInput
            style={[
              styles.textInput,
              {
                backgroundColor: theme.surface,
                color: theme.text,
                borderColor: theme.border,
              },
            ]}
            placeholder="E.g., Senior executives, Technical team, Investors..."
            placeholderTextColor={theme.textSecondary}
            value={targetAudience}
            onChangeText={setTargetAudience}
          />
        )}

        {/* Number of Slides */}
        <Text style={[styles.fieldLabel, { color: theme.text }]}>Number of Slides</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 8, marginBottom: 20 }}>
          {['5', '10', '15', '20'].map((count) => (
            <TouchableOpacity
              key={count}
              style={[
                styles.slideCountOption,
                {
                  backgroundColor: slideCount === count ? theme.primary : theme.surface,
                  borderColor: slideCount === count ? theme.primary : theme.border,
                  marginBottom: 0,
                },
              ]}
              onPress={() => setSlideCount(count)}
            >
              <Text
                style={[
                  styles.slideCountText,
                  { color: slideCount === count ? '#fff' : theme.text },
                ]}
              >
                {count}
              </Text>
            </TouchableOpacity>
          ))}

          {/* Custom Input */}
          <View style={{
            flexDirection: 'row',
            alignItems: 'center',
            backgroundColor: theme.surface,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: theme.border,
            paddingHorizontal: 10,
            height: 40,
            marginLeft: 4
          }}>
            <Text style={{ color: theme.textSecondary, marginRight: 6, fontSize: 13, fontWeight: '500' }}>Custom</Text>
            {Platform.OS === 'web' ? (
              <input
                type="number"
                min="3"
                max="50"
                style={{
                  width: 40,
                  border: 'none',
                  background: 'transparent',
                  color: theme.text,
                  fontSize: 14,
                  fontFamily: 'inherit',
                  outline: 'none',
                  textAlign: 'center',
                  fontWeight: 'bold'
                }}
                value={['5', '10', '15', '20'].includes(slideCount) ? '' : slideCount}
                placeholder="#"
                onChange={(e) => {
                  const val = e.target.value;
                  setSlideCount(val);
                }}
              />
            ) : (
              <TextInput
                style={{
                  width: 40,
                  color: theme.text,
                  fontSize: 14,
                  textAlign: 'center',
                  fontWeight: 'bold',
                  padding: 0
                }}
                value={['5', '10', '15', '20'].includes(slideCount) ? '' : slideCount}
                placeholder="#"
                placeholderTextColor={theme.textSecondary}
                keyboardType="numeric"
                onChangeText={setSlideCount}
              />
            )}
          </View>
        </View>

        {/* Internet Search Toggle */}
        <TouchableOpacity
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            backgroundColor: useInternetSearch ? theme.primary + '15' : theme.surface,
            borderWidth: 1,
            borderColor: useInternetSearch ? theme.primary + '60' : theme.border,
            borderRadius: 12,
            padding: 14,
            marginBottom: 10,
          }}
          onPress={() => {
            if (!useInternetSearch && !requireVault('You have turned off data store. To use internet search, please select or create a data store first. Data pulled from the internet will be stored in your data store for AI to use during generation.')) return;
            setUseInternetSearch(!useInternetSearch);
          }}
          activeOpacity={0.7}
        >
          <Ionicons
            name={useInternetSearch ? "globe" : "globe-outline"}
            size={20}
            color={useInternetSearch ? theme.primary : theme.textSecondary}
          />
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Text style={{ fontSize: 14, fontWeight: '600', color: theme.text }}>
              Pull Latest from Internet
            </Text>
            <Text style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2 }}>
              Fetch web data and embed in data store before generating outline
            </Text>
          </View>
          <View style={{
            width: 22,
            height: 22,
            borderRadius: 6,
            borderWidth: 2,
            borderColor: useInternetSearch ? theme.primary : theme.textSecondary + '60',
            backgroundColor: useInternetSearch ? theme.primary : 'transparent',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            {useInternetSearch && <Ionicons name="checkmark" size={14} color="#fff" />}
          </View>
        </TouchableOpacity>

        {/* Error Message */}
        {errorMessage ? (
          <View style={[styles.errorCard, { backgroundColor: '#fee2e2', borderColor: '#fca5a5' }]}>
            <Ionicons name="alert-circle" size={20} color="#dc2626" />
            <Text style={[styles.errorText, { color: '#dc2626' }]}>{errorMessage}</Text>
            <TouchableOpacity
              onPress={() => setErrorMessage('')}
              style={styles.errorClose}
            >
              <Ionicons name="close" size={16} color="#dc2626" />
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Generate Outline Button */}
        {Platform.OS === 'web' ? (
          <div
            onClick={() => {
              if (goal.trim() && !isGeneratingOutline) {
                console.log('ðŸŽ¯ Generate button pressed, goal:', goal.trim()?.substring(0, 50));
                generateOutline();
              }
            }}
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              paddingTop: 14,
              paddingBottom: 14,
              borderRadius: 10,
              gap: 8,
              backgroundColor: goal.trim() ? (theme.primary || '#2196F3') : (theme.border || '#ccc'),
              cursor: goal.trim() && !isGeneratingOutline ? 'pointer' : 'not-allowed',
              opacity: goal.trim() && !isGeneratingOutline ? 1 : 0.6,
              transition: 'all 0.2s ease',
            }}
          >
            {isGeneratingOutline ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="sparkles" size={20} color="#fff" />
                <Text style={styles.primaryButtonText}>Generate Slide Outline</Text>
              </>
            )}
          </div>
        ) : (
          <TouchableOpacity
            style={[
              styles.primaryButton,
              {
                backgroundColor: goal.trim() ? theme.primary : theme.border,
              },
            ]}
            onPress={() => {
              console.log('ðŸŽ¯ Generate button pressed, goal:', goal.trim()?.substring(0, 50));
              generateOutline();
            }}
            disabled={!goal.trim() || isGeneratingOutline}
            activeOpacity={0.7}
          >
            {isGeneratingOutline ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="sparkles" size={20} color="#fff" />
                <Text style={styles.primaryButtonText}>Generate Slide Outline</Text>
              </>
            )}
          </TouchableOpacity>
        )}
      </View>
    </ScrollView >
  );

  // Render Step 2: Outline Editor
  const renderOutlineStep = () => (
    <ScrollView style={styles.stepScroll} contentContainerStyle={styles.stepScrollContent} showsVerticalScrollIndicator={false}>
      <View style={[styles.stepInnerWrapper, isMobile && { padding: 14, maxWidth: '100%' }]}>
        <View style={styles.outlineHeader}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            <Ionicons name="list-outline" size={20} color={theme.primary} /> Slide Outline
          </Text>
          {!isStreaming && (
            <TouchableOpacity
              style={[styles.addButton, { backgroundColor: theme.primary }]}
              onPress={addNewSlide}
            >
              <Ionicons name="add" size={18} color="#fff" />
              <Text style={styles.addButtonText}>Add Slide</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Streaming Progress Indicator */}
        {isStreaming && (
          <View style={{
            flexDirection: 'row',
            alignItems: 'center',
            padding: 16,
            backgroundColor: theme.primary + '15',
            borderRadius: 10,
            marginBottom: 16,
            gap: 12,
          }}>
            <ActivityIndicator size="small" color={theme.primary} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: theme.primary, fontWeight: '600', fontSize: 14 }}>
                {streamingProgress || 'Generating slides...'}
              </Text>
              <Text style={{ color: theme.textSecondary, fontSize: 12, marginTop: 2 }}>
                {slideOutline.length > 0 ? `${slideOutline.length} slide${slideOutline.length > 1 ? 's' : ''} generated` : 'Slides will appear below as they are created'}
              </Text>
            </View>
          </View>
        )}

        <Text style={[styles.sectionDescription, { color: theme.textSecondary }]}>
          {isStreaming
            ? 'Your slides are being generated. They will appear below one by one.'
            : 'Review and edit the slide outline. You can reorder, add, or delete slides.'}
        </Text>

        {slideOutline.map((slide, index) => (
          <View
            key={slide.id}
            style={[
              styles.slideCard,
              {
                backgroundColor: theme.surface,
                borderColor: editingSlideId === slide.id ? theme.primary : theme.border,
              },
            ]}
          >
            <View style={styles.slideCardHeader}>
              <View style={[styles.slideNumber, { backgroundColor: theme.primary }]}>
                <Text style={styles.slideNumberText}>{index + 1}</Text>
              </View>

              {editingSlideId === slide.id ? (
                <TextInput
                  style={[styles.slideTitleInput, { color: theme.text, borderColor: theme.border }]}
                  value={editingTitle}
                  onChangeText={setEditingTitle}
                  placeholder="Slide title"
                  placeholderTextColor={theme.textSecondary}
                  autoFocus
                />
              ) : (
                <Text style={[styles.slideTitle, { color: theme.text }]}>{slide.title}</Text>
              )}

              <View style={styles.slideActions}>
                <TouchableOpacity onPress={() => moveSlideUp(index)} disabled={index === 0}>
                  <Ionicons name="chevron-up" size={20} color={index === 0 ? theme.border : theme.textSecondary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => moveSlideDown(index)} disabled={index === slideOutline.length - 1}>
                  <Ionicons name="chevron-down" size={20} color={index === slideOutline.length - 1 ? theme.border : theme.textSecondary} />
                </TouchableOpacity>
                {editingSlideId === slide.id ? (
                  <TouchableOpacity onPress={saveEditing}>
                    <Ionicons name="checkmark" size={20} color={theme.primary} />
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity onPress={() => startEditing(slide)}>
                    <Ionicons name="pencil" size={18} color={theme.textSecondary} />
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => deleteSlide(slide.id)}>
                  <Ionicons name="trash-outline" size={18} color="#EF4444" />
                </TouchableOpacity>
              </View>
            </View>

            {editingSlideId === slide.id ? (
              <TextInput
                style={[
                  styles.slideContentInput,
                  { color: theme.text, backgroundColor: theme.background, borderColor: theme.border },
                ]}
                value={editingContent}
                onChangeText={setEditingContent}
                placeholder="What should this slide cover?"
                placeholderTextColor={theme.textSecondary}
                multiline
                numberOfLines={3}
              />
            ) : (
              <Text style={[styles.slideContent, { color: theme.textSecondary }]}>
                {slide.content_hint}
              </Text>
            )}
          </View>
        ))}

        {/* Navigation buttons */}
        <View style={styles.navigationButtons}>
          <TouchableOpacity
            style={[styles.secondaryButton, { borderColor: theme.border }]}
            onPress={() => setCurrentStep(1)}
          >
            <Ionicons name="arrow-back" size={18} color={theme.text} />
            <Text style={[styles.secondaryButtonText, { color: theme.text }]}>Back</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.primaryButton,
              { backgroundColor: theme.primary },
              (isStreaming || slideOutline.length === 0) && { opacity: 0.6 },
            ]}
            onPress={() => setCurrentStep(3)}
            disabled={isStreaming || slideOutline.length === 0}
          >
            {isStreaming ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Text style={styles.primaryButtonText}>Choose Template</Text>
                <Ionicons name="arrow-forward" size={18} color="#fff" />
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView >
  );

  // Render Step 3: Template & Style Selection (Combined)
  const renderStyleStep = () => {
    // Handle style selection - sync with PRESET_STYLES
    const handleStyleSelect = (styleId) => {
      setSelectedStyleId(styleId);
      const matchedStyle = PRESET_STYLES.find(s => s.id === styleId);
      if (matchedStyle) {
        setSelectedStyle(matchedStyle);
      }
    };

    // Get current style for previews - use selectedStyle from PRESET_STYLES
    const currentStyle = selectedStyle || PRESET_STYLES[0];
    const accentColor = currentStyle.accentColor || currentStyle.preview?.accent || '#3B82F6';
    const cardBg = currentStyle.cardBackground || '#f0f4f8';
    const textColor = currentStyle.textPrimary || currentStyle.preview?.primary || '#1f2937';
    const bgColor = currentStyle.slideBackground || '#ffffff';

    // Template thumbnail component with visual preview
    const TemplateThumbnail = ({ templateId, isSelected, onSelect, size = 'normal' }) => {
      const template = SLIDE_TEMPLATES[templateId];
      if (!template) return null;

      const thumbWidth = size === 'small' ? 100 : 140;
      const thumbHeight = size === 'small' ? 56 : 79;

      // Render mini preview based on template type
      const renderMiniPreview = () => {
        const miniStyles = {
          slide: { flex: 1, padding: 4 },
          title: { height: 4, borderRadius: 2, marginBottom: 4 },
          line: { height: 2, borderRadius: 1, marginTop: 2 },
          row: { flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center', marginTop: 6, paddingHorizontal: 4 },
          card: { borderRadius: 3, padding: 3, alignItems: 'center' },
          icon: { width: 8, height: 8, borderRadius: 4 },
          bullet: { width: 3, height: 3, borderRadius: 1.5, marginRight: 4 },
          imageBox: { borderRadius: 3, borderWidth: 1, borderStyle: 'dashed' },
          stepCircle: { width: 12, height: 12, borderRadius: 6, justifyContent: 'center', alignItems: 'center' },
          connector: { width: 8, height: 2, borderRadius: 1 },
        };

        switch (templateId) {
          case 'title_hero':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginTop: 16 }]} />
                <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '40%', alignSelf: 'center' }]} />
              </View>
            );
          case 'title_image':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '70%', alignSelf: 'center' }]} />
                <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '50%', height: 28, alignSelf: 'center', marginTop: 6 }]} />
              </View>
            );
          case 'bullets':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ height: 2, width: 20, backgroundColor: accentColor, marginLeft: 6, marginTop: 3 }} />
                {[1, 2, 3].map(i => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginLeft: 8, marginTop: 4 }}>
                    <View style={[miniStyles.bullet, { backgroundColor: accentColor }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: 50, marginTop: 0 }]} />
                  </View>
                ))}
              </View>
            );
          case 'two_columns':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center' }]} />
                <View style={miniStyles.row}>
                  {[1, 2].map(i => (
                    <View key={i} style={[miniStyles.card, { backgroundColor: cardBg, width: '42%', height: 32 }]}>
                      <View style={[miniStyles.icon, { backgroundColor: accentColor }]} />
                      <View style={[miniStyles.line, { backgroundColor: textColor, width: '70%' }]} />
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'three_cards':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center' }]} />
                <View style={miniStyles.row}>
                  {[1, 2, 3].map(i => (
                    <View key={i} style={[miniStyles.card, { backgroundColor: cardBg, width: '28%', height: 30 }]}>
                      <View style={[miniStyles.icon, { backgroundColor: accentColor }]} />
                      <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'process_steps':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 6, marginTop: 6 }}>
                  {[0, 1, 2, 3].map((i) => (
                    <React.Fragment key={i}>
                      <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: accentColor, opacity: 0.85 }} />
                      {i < 3 && <View style={{ flex: 1, height: 1.5, backgroundColor: accentColor, opacity: 0.4, marginHorizontal: 2 }} />}
                    </React.Fragment>
                  ))}
                </View>
                <View style={{ position: 'absolute', bottom: 6, left: 8, right: 8, flexDirection: 'row', justifyContent: 'space-around' }}>
                  {[1, 2, 3, 4].map(i => (
                    <View key={i} style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: 14 }]} />
                  ))}
                </View>
              </View>
            );
          case 'org_hierarchy':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  <View style={{ width: 16, height: 8, borderRadius: 1, backgroundColor: accentColor }} />
                  <View style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                  <View style={{ width: '70%', height: 1, backgroundColor: accentColor, opacity: 0.6 }} />
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '70%', marginTop: -1 }}>
                    <View style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                    <View style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                    <View style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                  </View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '78%', marginTop: 0 }}>
                    {[0, 1, 2].map(i => (
                      <View key={i} style={{ width: 12, height: 7, borderRadius: 1, borderWidth: 1, borderColor: accentColor }} />
                    ))}
                  </View>
                </View>
              </View>
            );
          case 'infographic_diagram':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '55%', marginLeft: 6 }]} />
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                  <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: accentColor, opacity: 0.7 }} />
                  <View style={{ width: 14, height: 14, borderRadius: 2, backgroundColor: accentColor, opacity: 0.5 }} />
                  <View style={{ width: 0, height: 0, borderLeftWidth: 7, borderRightWidth: 7, borderBottomWidth: 12, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: accentColor, opacity: 0.6 }} />
                  <View style={{ width: 4, height: 14, backgroundColor: accentColor, opacity: 0.4 }} />
                  <View style={{ width: 14, height: 14, borderWidth: 1.5, borderColor: accentColor, borderRadius: 2 }} />
                </View>
              </View>
            );
          case 'image_left':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%', marginLeft: 6 }]} />
                <View style={miniStyles.row}>
                  <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 32 }]} />
                  <View style={{ width: '42%' }}>
                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '100%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '80%' }]} />
                  </View>
                </View>
              </View>
            );
          case 'image_right':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%', marginLeft: 6 }]} />
                <View style={miniStyles.row}>
                  <View style={{ width: '42%' }}>
                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '100%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '80%' }]} />
                  </View>
                  <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 32 }]} />
                </View>
              </View>
            );
          case 'quote':
            return (
              <View style={miniStyles.slide}>
                <Text style={{ position: 'absolute', top: -2, left: 6, fontSize: 24, color: accentColor, opacity: 0.3, fontWeight: 'bold' }}>"</Text>
                <View style={{ alignItems: 'center', marginTop: 16 }}>
                  <View style={[miniStyles.line, { backgroundColor: textColor, width: '60%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, width: '40%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: accentColor, width: '25%', marginTop: 6 }]} />
                </View>
              </View>
            );
          case 'ai_auto':
            return (
              <View style={miniStyles.slide}>
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: accentColor + '10' }}>
                  <Ionicons name="sparkles" size={14} color={accentColor} />
                  <View style={{ flexDirection: 'row', gap: 2, marginTop: 4 }}>
                    <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: accentColor }} />
                    <View style={{ width: 12, height: 4, borderRadius: 2, backgroundColor: accentColor, opacity: 0.5 }} />
                  </View>
                </View>
              </View>
            );
          case 'data_dashboard':
            return (
              <View style={miniStyles.slide}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '40%', marginBottom: 6, alignSelf: 'center' }]} />
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, justifyContent: 'center' }}>
                  {/* Top Left Chart */}
                  <View style={{ width: '45%', height: 24, backgroundColor: cardBg, borderRadius: 2, alignItems: 'flex-end', justifyContent: 'flex-end', padding: 2 }}>
                    <View style={{ flexDirection: 'row', gap: 1, alignItems: 'flex-end' }}>
                      <View style={{ width: 3, height: 8, backgroundColor: accentColor }} />
                      <View style={{ width: 3, height: 12, backgroundColor: accentColor }} />
                      <View style={{ width: 3, height: 16, backgroundColor: accentColor }} />
                    </View>
                  </View>
                  {/* Top Right Chart */}
                  <View style={{ width: '45%', height: 24, backgroundColor: cardBg, borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                    <View style={{ width: 16, height: 16, borderRadius: 8, borderWidth: 2, borderColor: accentColor }} />
                  </View>
                  {/* Bottom Stats */}
                  <View style={{ width: '45%', height: 20, backgroundColor: cardBg, borderRadius: 2, padding: 3 }}>
                    <View style={{ width: '60%', height: 3, backgroundColor: textColor }} />
                    <View style={{ width: '40%', height: 6, backgroundColor: accentColor, marginTop: 2 }} />
                  </View>
                  <View style={{ width: '45%', height: 20, backgroundColor: cardBg, borderRadius: 2, padding: 3 }}>
                    <View style={{ width: '60%', height: 3, backgroundColor: textColor }} />
                    <View style={{ width: '40%', height: 6, backgroundColor: accentColor, marginTop: 2 }} />
                  </View>
                </View>
              </View>
            );
          case 'modern_geometric':
            return (
              <View style={miniStyles.slide}>
                {/* Decorative background shapes */}
                <View style={{ position: 'absolute', top: 0, left: 0, width: 6, height: '100%', backgroundColor: accentColor }} />
                <View style={{ position: 'absolute', top: -10, right: -10, width: 40, height: 40, backgroundColor: accentColor, opacity: 0.2, transform: [{ rotate: '45deg' }] }} />
                <View style={{ position: 'absolute', bottom: -10, right: 30, width: 30, height: 30, borderRadius: 15, backgroundColor: accentColor, opacity: 0.1 }} />

                <View style={{ flexDirection: 'row', height: '100%', paddingLeft: 10 }}>
                  <View style={{ flex: 1, paddingTop: 10 }}>
                    <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '90%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '70%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                  </View>
                  <View style={{ width: '40%', height: '80%', marginTop: 10, marginRight: 6, backgroundColor: cardBg, borderStyle: 'dashed', borderWidth: 1, borderColor: accentColor }} />
                </View>
              </View>
            );
          default:
            return <View style={miniStyles.slide}><View style={[miniStyles.title, { backgroundColor: textColor }]} /></View>;
        }
      };

      return (
        <TouchableOpacity
          style={[
            styles.templateThumbnail,
            {
              width: thumbWidth,
              borderColor: isSelected ? accentColor : theme.border,
              borderWidth: isSelected ? 2 : 1,
            }
          ]}
          onPress={onSelect}
          activeOpacity={0.7}
        >
          <View style={[styles.thumbnailSlide, { backgroundColor: bgColor, height: thumbHeight }]}>
            {renderMiniPreview()}
          </View>
          <Text style={[styles.thumbnailLabel, { color: isSelected ? accentColor : theme.text }]} numberOfLines={1}>
            {template.name}
          </Text>
          {isSelected && (
            <View style={[styles.thumbnailCheckmark, { backgroundColor: accentColor }]}>
              <Ionicons name="checkmark" size={10} color="#fff" />
            </View>
          )}
        </TouchableOpacity>
      );
    };

    // Available templates
    const allTemplates = [
      { id: 'ai_auto', category: 'Smart' },
      { id: 'title_hero', category: 'Title' },
      { id: 'title_image', category: 'Title' },
      { id: 'title_split', category: 'Title' },
      { id: 'section_break', category: 'Title' },
      { id: 'closing', category: 'Title' },
      { id: 'bullets', category: 'Content' },
      { id: 'bullets_with_image', category: 'Content' },
      { id: 'two_columns', category: 'Content' },
      { id: 'three_cards', category: 'Content' },
      { id: 'four_cards', category: 'Content' },
      { id: 'timeline', category: 'Content' },
      { id: 'comparison', category: 'Content' },
      { id: 'quote', category: 'Content' },
      // Diagram templates (full-canvas SVG)
      { id: 'process_steps', category: 'Diagrams' },
      { id: 'org_hierarchy', category: 'Diagrams' },
      { id: 'infographic_diagram', category: 'Diagrams' },
      { id: 'image_left', category: 'Media' },
      { id: 'image_right', category: 'Media' },
      { id: 'full_bleed_image', category: 'Media' },
      { id: 'data_dashboard', category: 'Data' },
      { id: 'chart_focus', category: 'Data' },
      { id: 'stats_highlight', category: 'Data' },
      { id: 'big_number', category: 'Data' },
      { id: 'modern_geometric', category: 'Advanced' },
    ];

    return (
      <ScrollView style={styles.stepScroll} contentContainerStyle={styles.stepScrollContent} showsVerticalScrollIndicator={false}>
        <View style={[styles.stepInnerWrapper, isMobile && { padding: 14, maxWidth: '100%' }]}>
          {/* Header with AI-first messaging */}
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            <Ionicons name="sparkles" size={20} color={theme.primary} /> Ready to Generate
          </Text>
          <Text style={[styles.sectionDescription, { color: theme.textSecondary, marginBottom: 8 }]}>
            AI will automatically choose the best layouts and style for your slides.
          </Text>

          {/* The Corporate / General choice is the single routing axis —
              it lives in the deck-profile picker at the top of the modal,
              not as a separate toggle. Corporate runs the template path;
              General routes to the legacy free-form generator. */}

          {/* Primary Action - Review & Generate Button (TOP) */}

          {/* Generation Quality (premium/medium/basic) selector removed.
              Executive templates use no photographic imagery, so the
              image-generation cost knob this exposed has no effect on
              exec output. State stays defaulted to 'medium' for
              backward-compat with the request payload. */}

          {/* Special Instructions for AI */}
          <View style={[styles.specialInstructionsContainer, { backgroundColor: theme.surface, borderColor: theme.border, marginBottom: 20 }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
              <Ionicons name="bulb-outline" size={18} color={theme.primary} />
              <Text style={{ fontSize: 14, fontWeight: '600', color: theme.text, marginLeft: 8 }}>
                Special Instructions (Optional)
              </Text>
            </View>
            <Text style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 10 }}>
              Guide the AI: content style, data to include, formatting preferences, etc.
            </Text>
            <TextInput
              style={[styles.specialInstructionsInput, {
                backgroundColor: theme.background,
                color: theme.text,
                borderColor: theme.border
              }]}
              placeholder="e.g., 'Text-heavy, minimal images' or 'Use these stats: Revenue $5M, Growth 25%' or 'Focus on executive summary'"
              placeholderTextColor={theme.textSecondary}
              value={specialInstructions}
              onChangeText={setSpecialInstructions}
              multiline={true}
              maxLength={2000}
              textAlignVertical="top"
            />
          </View>

          <View style={[styles.generatePreviewCard, { backgroundColor: theme.surface, borderColor: theme.primary + '40', marginBottom: 20 }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: theme.primary + '20', alignItems: 'center', justifyContent: 'center', marginRight: 12 }}>
                <Ionicons name="flash" size={20} color={theme.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: theme.text }}>
                  {slideOutline.length} slides ready
                </Text>
                <Text style={{ fontSize: 13, color: theme.textSecondary }}>
                  {Object.keys(slideTemplateMap).length > 0 || !useAutoTemplateMapping
                    ? `Style: ${selectedStyle?.name || 'Custom'} â€¢ Custom layouts`
                    : `Style: ${selectedStyle?.name || 'Let AI Decide'} â€¢ AI layouts`
                  }
                </Text>
              </View>
            </View>

            <TouchableOpacity
              style={[styles.primaryButton, { backgroundColor: theme.primary, paddingVertical: 16 }]}
              onPress={() => generatePresentation()}
              disabled={isGeneratingPresentation}
            >
              {isGeneratingPresentation ? (
                <>
                  <ActivityIndicator size="small" color="#fff" />
                  <Text style={[styles.primaryButtonText, { marginLeft: 8 }]}>
                    Generating {generationProgress.current}/{generationProgress.total}...
                  </Text>
                </>
              ) : (
                <>
                  <Ionicons name="rocket" size={20} color="#fff" />
                  <Text style={styles.primaryButtonText}>Generate Presentation</Text>
                </>
              )}
            </TouchableOpacity>
          </View>

          {/* Navigation - Back button */}
          <View style={{ flexDirection: 'row', marginBottom: 16 }}>
            <TouchableOpacity
              style={[styles.secondaryButton, { borderColor: theme.border, alignSelf: 'flex-start' }]}
              onPress={() => setCurrentStep(2)}
            >
              <Ionicons name="arrow-back" size={18} color={theme.text} />
              <Text style={[styles.secondaryButtonText, { color: theme.text }]}>Back to Outline</Text>
            </TouchableOpacity>
          </View>



          {/* Collapsible Advanced Setup — per-slide template layouts apply to Corporate only.
              General profile lets the LLM design each slide from scratch (no templates). */}
          {deckProfile === 'corporate' && (<>
          <TouchableOpacity
            style={[styles.advancedSetupToggle, {
              backgroundColor: showAdvancedSetup ? theme.primary + '10' : theme.surface,
              borderColor: showAdvancedSetup ? theme.primary : theme.border
            }]}
            onPress={() => setShowAdvancedSetup(!showAdvancedSetup)}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
              <Ionicons
                name="settings-outline"
                size={20}
                color={showAdvancedSetup ? theme.primary : theme.textSecondary}
              />
              <View style={{ marginLeft: 12, flex: 1 }}>
                <Text style={{ fontSize: 15, fontWeight: '600', color: theme.text }}>
                  Advanced Setup
                </Text>
                <Text style={{ fontSize: 12, color: theme.textSecondary }}>
                  Customize style, icon set, and per-slide layouts
                </Text>
              </View>
            </View>
            <Ionicons
              name={showAdvancedSetup ? "chevron-up" : "chevron-down"}
              size={20}
              color={theme.textSecondary}
            />
          </TouchableOpacity>

          {/* Advanced Setup Content (Collapsible) */}
          {showAdvancedSetup && (
            <View style={[styles.advancedSetupContent, { borderColor: theme.border }]}>

              {/* Style Selection - PresentationStylePicker */}
              <View style={[styles.styleSection, { marginTop: 8, marginBottom: 20 }]}>
                <PresentationStylePicker
                  theme={theme}
                  selectedStyle={selectedStyle}
                  onSelectStyle={(style) => {
                    setSelectedStyle(style);
                    setSelectedStyleId(style?.id || 'corporate');
                  }}
                  onGenerateAIStyle={generateAIStyle}
                  customStyles={customStyles}
                  isGeneratingStyle={isGeneratingStyle}
                  apiConfig={apiConfig}
                />
              </View>

              {/* Icon Set Selection */}
              <View style={{ marginBottom: 20 }}>
                <Text style={[styles.subsectionTitle, { color: theme.text, marginBottom: 12 }]}>
                  <Ionicons name="shapes-outline" size={16} color={theme.textSecondary} /> Icon Set
                </Text>
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  {['lucide', 'ion'].map(set => (
                    <TouchableOpacity
                      key={set}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        paddingVertical: 8,
                        paddingHorizontal: 16,
                        borderRadius: 20,
                        borderWidth: 1,
                        borderColor: iconSet === set ? theme.primary : theme.border,
                        backgroundColor: iconSet === set ? theme.primary + '10' : 'transparent'
                      }}
                      onPress={() => setIconSet(set)}
                    >
                      <Ionicons
                        name={set === 'lucide' ? 'cube-outline' : 'logo-ionic'}
                        size={16}
                        color={iconSet === set ? theme.primary : theme.textSecondary}
                        style={{ marginRight: 8 }}
                      />
                      <Text style={{ color: iconSet === set ? theme.primary : theme.text, fontWeight: iconSet === set ? '600' : '400' }}>
                        {set === 'lucide' ? 'Lucide (Modern)' : 'Ionicons (Classic)'}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              {/* Template Gallery - Visual Preview (corporate only) */}
              {deckProfile === 'corporate' && (
              <View style={[styles.templateGallerySection, { marginBottom: 20 }]}>
                <Text style={[styles.subsectionTitle, { color: theme.text, marginBottom: 12 }]}>
                  <Ionicons name="albums-outline" size={16} color={theme.textSecondary} /> Available Templates
                </Text>
                <View style={styles.templateGalleryGrid}>
                  {allTemplates.map((t) => (
                    <TemplateThumbnail
                      key={t.id}
                      templateId={t.id}
                      isSelected={Object.values(slideTemplateMap).includes(t.id)}
                      onSelect={() => {
                        // Just show preview - don't auto-assign
                      }}
                    />
                  ))}
                </View>
              </View>
              )}

              {/* Auto/Manual Toggle + per-slide mapping (corporate only) */}
              {deckProfile === 'corporate' && (<>
              <View style={[styles.autoToggleRow, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.autoToggleLabel, { color: theme.text }]}>
                    <Ionicons name="sparkles" size={16} color={theme.primary} /> Let AI create its own template
                  </Text>
                  <Text style={[styles.autoToggleHint, { color: theme.textSecondary }]}>
                    AI will analyze content and create the best layout for each slide
                  </Text>
                </View>
                <TouchableOpacity
                  style={[
                    styles.toggleButton,
                    { backgroundColor: useAutoTemplateMapping ? theme.primary : theme.border }
                  ]}
                  onPress={() => {
                    const newValue = !useAutoTemplateMapping;
                    setUseAutoTemplateMapping(newValue);
                    if (newValue && slideOutline.length > 0) {
                      // Re-apply auto mapping
                      const mapping = autoMapTemplatesToSlides(slideOutline);
                      setSlideTemplateMap(mapping);
                    }
                  }}
                >
                  <View style={[
                    styles.toggleKnob,
                    {
                      backgroundColor: '#fff',
                      transform: [{ translateX: useAutoTemplateMapping ? 18 : 2 }]
                    }
                  ]} />
                </TouchableOpacity>
              </View>

              {/* Per-Slide Template Mapping */}
              <View style={[styles.slideTemplateMappingSection, { marginTop: 16 }]}>
                <Text style={[styles.subsectionTitle, { color: theme.text, marginBottom: 12 }]}>
                  <Ionicons name="list-outline" size={16} color={theme.textSecondary} /> Assign to Slides
                </Text>

                {slideOutline.map((slide, idx) => {
                  const currentTemplate = getTemplateForSlide(idx);

                  return (
                    <View
                      key={slide.id || idx}
                      style={[styles.slideTemplateRowNew, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    >
                      {/* Slide Info Row */}
                      <View style={styles.slideInfoRow}>
                        <View style={[styles.slideNumberBadge, { backgroundColor: accentColor }]}>
                          <Text style={styles.slideNumberText}>{idx + 1}</Text>
                        </View>
                        <View style={styles.slideInfoText}>
                          <Text style={[styles.slideTitle, { color: theme.text }]} numberOfLines={1}>
                            {slide.title}
                          </Text>
                          <Text style={[styles.slideContentHint, { color: theme.textSecondary }]} numberOfLines={1}>
                            {slide.content_hint || slide.contentHint || 'No description'}
                          </Text>
                        </View>
                      </View>

                      {/* Template Selection Row with Thumbnails */}
                      <ScrollView
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        style={styles.templateScrollRow}
                        contentContainerStyle={{ paddingVertical: 8 }}
                      >
                        {allTemplates.map((t) => (
                          <TemplateThumbnail
                            key={t.id}
                            templateId={t.id}
                            isSelected={currentTemplate === t.id}
                            onSelect={() => setTemplateForSlide(idx, t.id)}
                          />
                        ))}
                      </ScrollView>
                    </View>
                  );
                })}
              </View>
              </>)}
            </View>
          )}
          </>)}
        </View>
      </ScrollView>
    );
  };

  // Render Step 4: Review & Generate
  const renderGenerateStep = () => (
    <ScrollView style={styles.stepScroll} contentContainerStyle={styles.stepScrollContent} showsVerticalScrollIndicator={false}>
      <View style={[styles.stepInnerWrapper, isMobile && { padding: 14, maxWidth: '100%' }]}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>
          <Ionicons name="rocket-outline" size={20} color={theme.primary} /> Review & Generate
        </Text>
        <Text style={[styles.sectionDescription, { color: theme.textSecondary }]}>
          Review your presentation settings and generate the slides.
        </Text>

        {/* Summary */}
        <View style={[styles.summaryCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <View style={styles.summaryRow}>
            <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Goal:</Text>
            <Text style={[styles.summaryValue, { color: theme.text }]} numberOfLines={2}>{goal}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Type:</Text>
            <Text style={[styles.summaryValue, { color: theme.text }]}>
              {presentationTypes.find(t => t.value === presentationType)?.label}
            </Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Slides:</Text>
            <Text style={[styles.summaryValue, { color: theme.text }]}>{slideOutline.length}</Text>
          </View>
          {/* Template summary row is corporate-only — in general mode the
              server doesn't use the template map at all, so showing
              "N unique layouts" misleads the user. */}
          {deckProfile === 'corporate' && (
            <View style={styles.summaryRow}>
              <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Templates:</Text>
              <Text style={[styles.summaryValue, { color: theme.primary }]}>
                {Object.values(slideTemplateMap).filter((v, i, a) => a.indexOf(v) === i).length} unique layouts
              </Text>
            </View>
          )}
          <View style={styles.summaryRow}>
            <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Style:</Text>
            <View style={styles.stylePreview}>
              <View style={[styles.colorDotSmall, { backgroundColor: selectedStyle?.preview?.primary }]} />
              <View style={[styles.colorDotSmall, { backgroundColor: selectedStyle?.preview?.secondary }]} />
              <Text style={[styles.summaryValue, { color: theme.text }]}>{selectedStyle?.name}</Text>
            </View>
          </View>
          {selectedFolders.length > 0 && (
            <View style={styles.summaryRow}>
              <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Using data store:</Text>
              <Text style={[styles.summaryValue, { color: theme.primary }]}>
                {selectedFolders.length} folder(s) selected
              </Text>
            </View>
          )}
        </View>

        {/* Progress indicator during generation */}
        {isGeneratingPresentation && (
          <View style={[styles.progressCard, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
            <ActivityIndicator size="large" color={theme.primary} />
            <Text style={[styles.progressText, { color: theme.text }]}>
              Generating slide {generationProgress.current} of {generationProgress.total}...
            </Text>
            <View style={[styles.progressBar, { backgroundColor: theme.border }]}>
              <View
                style={[
                  styles.progressFill,
                  {
                    backgroundColor: theme.primary,
                    width: `${(generationProgress.current / generationProgress.total) * 100}%`,
                  },
                ]}
              />
            </View>
            {/* Cancel Button */}
            <TouchableOpacity
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                paddingVertical: 10,
                paddingHorizontal: 16,
                marginTop: 12,
                borderRadius: 8,
                backgroundColor: '#ffebee',
                borderWidth: 1,
                borderColor: '#ffcdd2',
                gap: 6,
              }}
              onPress={() => {
                presentationCancelRef.current = true;
                setIsPresentationCancelled(true);
              }}
            >
              <Ionicons name="close-circle" size={18} color="#f44336" />
              <Text style={{ color: '#f44336', fontSize: 14, fontWeight: '500' }}>
                Cancel Generation
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Navigation buttons */}
        <View style={styles.navigationButtons}>
          <TouchableOpacity
            style={[styles.secondaryButton, { borderColor: theme.border }]}
            onPress={() => setCurrentStep(3)}
            disabled={isGeneratingPresentation}
          >
            <Ionicons name="arrow-back" size={18} color={theme.text} />
            <Text style={[styles.secondaryButtonText, { color: theme.text }]}>Back</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.primaryButton,
              {
                backgroundColor: isGeneratingPresentation ? theme.border : theme.primary,
                flex: 1,
              },
            ]}
            onPress={generatePresentation}
            disabled={isGeneratingPresentation}
          >
            {isGeneratingPresentation ? (
              <Text style={styles.primaryButtonText}>Generating...</Text>
            ) : (
              <>
                <Ionicons name="sparkles" size={20} color="#fff" />
                <Text style={styles.primaryButtonText}>Generate Presentation</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView >
  );

  if (!visible) return null;

  return (
    <View style={styles.modalOverlay}>
      <View style={[styles.container, { backgroundColor: theme.background }, isMobile && styles.containerMobile]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: theme.border }, isMobile && { paddingHorizontal: 12, paddingVertical: 10 }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={theme.text} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: theme.text }]}>Create Presentation</Text>
          <View style={{ width: 40 }} />
        </View>

        {/* Step indicator */}
        <StepIndicator />

        {/* Step content */}
        {currentStep === 1 && renderGoalStep()}
        {currentStep === 2 && renderOutlineStep()}
        {currentStep === 3 && renderStyleStep()}
        {currentStep === 4 && renderGenerateStep()}

        {/* Internal Upload Modal - Rendered inside this modal's context */}
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
        />
      </View>
    </View>
  );
};

const styles = {
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  container: {
    width: '90%',
    maxWidth: 1000,
    height: '90%',
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 10,
  },
  containerMobile: {
    width: '100%',
    maxWidth: '100%',
    height: '100%',
    borderRadius: 0,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  closeButton: {
    padding: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.05)',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  vaultButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  vaultButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  stepIndicator: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 24,
    paddingHorizontal: 16,
  },
  stepItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  stepCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  stepNumber: {
    fontSize: 14,
    fontWeight: '700',
  },
  stepLabel: {
    fontSize: 13,
    marginLeft: 8,
    fontWeight: '600',
  },
  stepLine: {
    width: 48,
    height: 3,
    marginHorizontal: 10,
    borderRadius: 1.5,
  },
  stepScroll: {
    flex: 1,
    width: '100%',
  },
  stepScrollContent: {
    flexGrow: 1,
    alignItems: 'center',
  },
  stepInnerWrapper: {
    width: '100%',
    maxWidth: 900,
    padding: 24,
  },
  sectionTitle: {
    fontSize: 22,
    fontWeight: '700',
    marginBottom: 8,
    letterSpacing: 0.3,
  },
  sectionDescription: {
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 24,
    opacity: 0.8,
  },
  goalInput: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 20,
    fontSize: 16,
    minHeight: 160,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  fieldLabel: {
    fontSize: 15,
    fontWeight: '600',
    marginBottom: 10,
    marginLeft: 4,
  },
  textInput: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    fontSize: 15,
    marginBottom: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 4,
    elevation: 1,
  },
  typeSelector: {
    marginBottom: 24,
    paddingBottom: 4, // for shadow
  },
  typeOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 16,
    borderWidth: 1,
    marginRight: 12,
    gap: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  typeLabel: {
    fontSize: 14,
    fontWeight: '600',
  },
  slideCountSelector: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 32,
  },
  slideCountOption: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  slideCountText: {
    fontSize: 16,
    fontWeight: '600',
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 14,
    gap: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 6,
  },
  primaryButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    paddingHorizontal: 24,
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
  },
  secondaryButtonText: {
    fontSize: 15,
    fontWeight: '600',
  },
  outlineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    marginTop: 8,
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 12,
    gap: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 3,
  },
  addButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  slideCard: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
  },
  slideCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginBottom: 12,
  },
  slideNumber: {
    width: 32,
    height: 32,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  slideNumberText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  slideTitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  slideTitleInput: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    borderBottomWidth: 2,
    paddingVertical: 4,
    letterSpacing: 0.2,
  },
  slideActions: {
    flexDirection: 'row',
    gap: 8,
    backgroundColor: 'rgba(0,0,0,0.03)',
    borderRadius: 20,
    padding: 4,
  },
  slideContent: {
    fontSize: 14,
    lineHeight: 22,
    opacity: 0.9,
    paddingLeft: 46, // Indent to align with title
  },
  slideContentInput: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    fontSize: 14,
    minHeight: 80,
    marginLeft: 46, // Indent
  },
  navigationButtons: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 32,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
  },
  summaryCard: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 24,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  summaryRow: {
    flexDirection: 'row',
    marginBottom: 16,
    alignItems: 'center',
  },
  summaryLabel: {
    width: 100,
    fontSize: 14,
    fontWeight: '600',
    opacity: 0.7,
  },
  summaryValue: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
  },
  stylePreview: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(0,0,0,0.05)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  colorDotSmall: {
    width: 16,
    height: 16,
    borderRadius: 8,
  },
  progressCard: {
    borderWidth: 2,
    borderRadius: 16,
    padding: 32,
    alignItems: 'center',
    marginBottom: 24,
  },
  progressText: {
    fontSize: 16,
    fontWeight: '600',
    marginTop: 20,
    marginBottom: 16,
  },
  progressBar: {
    width: '100%',
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
    backgroundColor: 'rgba(0,0,0,0.05)',
  },
  progressFill: {
    height: '100%',
    borderRadius: 4,
  },
  advancedToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    paddingHorizontal: 18,
    borderWidth: 1,
    borderRadius: 12,
    borderStyle: 'dashed',
    marginTop: 12,
    backgroundColor: 'rgba(0,0,0,0.02)',
  },
  advancedToggleText: {
    fontSize: 14,
    fontWeight: '600',
  },
  // Per-slide template mapping styles
  subsectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  styleSection: {
    marginBottom: 16,
  },
  styleChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 24,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  styleColorDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
  },
  styleChipText: {
    fontSize: 14,
    fontWeight: '600',
  },
  autoToggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 8,
    elevation: 2,
  },
  autoToggleLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  autoToggleHint: {
    fontSize: 13,
    marginTop: 4,
    opacity: 0.7,
  },
  toggleButton: {
    width: 52,
    height: 30,
    borderRadius: 15,
    justifyContent: 'center',
    paddingHorizontal: 2,
  },
  toggleKnob: {
    width: 26,
    height: 26,
    borderRadius: 13,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },
  slideTemplateMappingSection: {
    marginBottom: 24,
  },
  slideTemplateRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 10,
    gap: 16,
  },
  slideTemplateRowNew: {
    padding: 16,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  slideInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 8,
  },
  slideInfoText: {
    flex: 1,
  },
  slideInfoColumn: {
    flex: 1,
    minWidth: 0,
  },
  slideNumberBadge: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  slideNumberText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },
  slideTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  slideContentHint: {
    fontSize: 13,
    marginTop: 2,
    opacity: 0.7,
  },
  templateScrollRow: {
    marginTop: 8,
    marginHorizontal: -8,
  },
  templateSelectorColumn: {
    flexShrink: 0,
  },
  // Template Gallery Styles
  templateGallerySection: {
    marginBottom: 24,
  },
  templateGalleryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    justifyContent: 'flex-start',
  },
  templateThumbnail: {
    borderRadius: 12,
    overflow: 'hidden',
    marginRight: 10,
    marginBottom: 6,
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  thumbnailSlide: {
    borderRadius: 8,
    overflow: 'hidden',
  },
  thumbnailLabel: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
    paddingVertical: 6,
    paddingHorizontal: 4,
  },
  thumbnailCheckmark: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },
  miniTemplateChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
  },
  miniTemplateChipText: {
    fontSize: 12,
    fontWeight: '600',
  },
  miniTemplateOption: {
    padding: 10,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    minWidth: 70,
  },
  miniTemplateLabel: {
    fontSize: 11,
    fontWeight: '600',
    textAlign: 'center',
  },
  errorCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
    gap: 12,
  },
  errorText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
  },
  errorClose: {
    padding: 4,
  },
  // Special Instructions styles
  specialInstructionsContainer: {
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  specialInstructionsInput: {
    minHeight: 80,
    maxHeight: 150,
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    fontSize: 14,
    textAlignVertical: 'top',
  },
  // Advanced Setup collapsible styles
  advancedSetupToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  advancedSetupContent: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderStyle: 'dashed',
  },
  generatePreviewCard: {
    padding: 20,
    borderRadius: 16,
    borderWidth: 2,
  },
};

export default PresentationGoalInput;
