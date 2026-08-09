// printableGoalInput.js - Goal input and PAGE outline generation for printables
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
import PrintableStylePicker, { PRESET_STYLES } from './PrintableStylePicker';
import { processPageAsync as processPAGEAsync } from './utils/pagePostProcessor';
import { PAGE_TEMPLATES } from './printableTemplates';
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
 * Credit error handler — stubbed under license model (no credit enforcement)
 */
const handleCreditError = (data) => {
  return false; // License model: unlimited credits, no credit errors
};

/**
 * printableGoalInput - Goal setting and PAGE outline generation
 * 
 * Flow:
 * 1. User writes printable goal/topic
 * 2. AI generates PAGE outline (titles + content hints)
 * 3. User can EDIT, ADD, DELETE, REORDER PAGES
 * 4. User selects or generates style theme
 * 5. Generate printable PAGES one at a time
 */
const PrintableGoalInput = ({
  onPrintableGenerated,
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
  const [printableType, setPrintableType] = useState('report');
  // Profile — TWO options only as of 2026-05-19:
  //   - 'corporate' (default): unified executive A4 catalog + storyboard-locked
  //     deck-coherent background image on every page.
  //   - 'general': free-form library, AI designs each page, per-page vision
  //     critique runs automatically.
  // NOTE: Corporate path produces less compelling output than General right
  // now, so the UI selector is hidden and we default everyone to 'general'.
  // The corporate template/style code paths remain intact for future
  // re-enablement.
  const [deckProfile, setDeckProfile] = useState('general');
  // Document-level storyboard captured from outline-stream SSE. Sent verbatim
  // to every /printable/generate-page call so all pages share one palette /
  // typography / background_style. null until the storyboard SSE event arrives.
  const [deckPlan, setDeckPlan] = useState(null);
  const [PAGECount, setPAGECount] = useState(10);
  const [customPAGECount, setCustomPAGECount] = useState('');
  const [currentStep, setCurrentStep] = useState(1);
  const [isGeneratingOutline, setIsGeneratingOutline] = useState(false);
  const [PAGEOutline, setPAGEOutline] = useState([]);

  // Internal modal state
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);
  const [editingPAGEId, setEditingPAGEId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [editingContent, setEditingContent] = useState('');

  // Style selection
  const [selectedStyle, setSelectedStyle] = useState(PRESET_STYLES[0]);
  const [selectedStyleId, setSelectedStyleId] = useState('corporate'); // For TemplateSelector
  // Per-PAGE template mapping: { 0: 'title_hero', 1: 'three_cards', ... }
  const [PAGETemplateMap, setPAGETemplateMap] = useState({});
  const [useAutoTemplateMapping, setUseAutoTemplateMapping] = useState(true); // Auto-map by default
  const [customStyles, setCustomStyles] = useState([]);
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [iconSet, setIconSet] = useState('lucide'); // New: Icon Set preference
  const [showAdvancedSetup, setShowAdvancedSetup] = useState(false); // Collapsed by default for streamlined flow
  const [specialInstructions, setSpecialInstructions] = useState(''); // User guidance for AI generation
  const [generationQuality, setGenerationQuality] = useState('medium'); // 'premium', 'medium' or 'basic'
  const [useInternetSearch, setUseInternetSearch] = useState(false); // Pull latest data from internet for each page

  // Loading states
  const [isGeneratingStyle, setIsGeneratingStyle] = useState(false);
  const [isGeneratingprintable, setIsGeneratingprintable] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0 });
  const [errorMessage, setErrorMessage] = useState('');

  // Cancellation state for printable generation
  const [isprintableCancelled, setIsprintableCancelled] = useState(false);
  const printableCancelRef = React.useRef(false);
  // Research corpus from a chat `open_builder` handoff — forwarded to the
  // outline endpoint as `prefetched_corpus` so the report is grounded on it.
  const prefillCorpusRef = React.useRef([]);

  // printable types - Visual report formats for enterprise users
  const printableTypes = [
    { value: 'report', label: 'Report', icon: 'document-text-outline', description: 'Business or technical report' },
    { value: 'proposal', label: 'Proposal', icon: 'briefcase-outline', description: 'Business proposal or plan' },
    { value: 'whitepaper', label: 'Whitepaper', icon: 'library-outline', description: 'Technical or research paper' },
    { value: 'brochure', label: 'Brochure', icon: 'albums-outline', description: 'Marketing brochure or flyer' },
    { value: 'newsletter', label: 'Newsletter', icon: 'newspaper-outline', description: 'Newsletter or bulletin' },
  ];

  // Helper: Exponential Backoff Retry
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
        console.log('💰 [CREDITS] Not retrying credit error');
        throw error;
      }

      if (retries === 0) throw error;
      // Exponential backoff: 1s, 2s, 4s...
      console.log(`⚠️ Request failed, retrying in ${delay / 1000}s... (${retries} attempts left). Error: ${errMsg}`);
      await new Promise(resolve => setTimeout(resolve, delay));
      return retryWithBackoff(fn, retries - 1, delay * 2);
    }
  };

  // Load existing goal
  useEffect(() => {
    if (existingGoal) {
      setGoal(existingGoal.goal || existingGoal.purpose || '');
      setTargetAudience(existingGoal.targetAudience || '');
      if (existingGoal.PAGEOutline) {
        setPAGEOutline(existingGoal.PAGEOutline);
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
  // goal, stash the corpus, and auto-start outline generation.
  useEffect(() => {
    // Fires once per handoff: onUsePrefill() nulls prefillGoal in the
    // parent, so the only re-fire is with null (caught by the guard).
    if (!prefillGoal?.goal) return;
    setGoal(prefillGoal.goal);
    setGoalWordCount(countWords(prefillGoal.goal));
    const pc = parseInt(prefillGoal.slide_count, 10);
    if (pc >= 1 && pc <= 20) setPAGECount(pc);
    prefillCorpusRef.current = Array.isArray(prefillGoal.prefetched_corpus)
      ? prefillGoal.prefetched_corpus
      : [];
    onUsePrefill?.();
    generateOutline({
      goalOverride: prefillGoal.goal,
      pageCountOverride: (pc >= 1 && pc <= 20) ? pc : 10,
      corpusOverride: prefillCorpusRef.current,
      folderIdsOverride: Array.isArray(prefillGoal.folder_ids) ? prefillGoal.folder_ids : [],
    });
  }, [prefillGoal]);

  // Auto-map templates when PAGE outline changes (if auto mode enabled)
  useEffect(() => {
    if (useAutoTemplateMapping && PAGEOutline.length > 0) {
      const mapping = autoMapTemplatesToPAGES(PAGEOutline);
      setPAGETemplateMap(mapping);
    }
  }, [PAGEOutline, useAutoTemplateMapping]);

  const autoMapTemplatesToPAGES = (PAGES) => {
    const mapping = {};

    PAGES.forEach((PAGE, idx) => {
      // DEFAULT TO AI DECIDE FOR EVERYTHING
      // This allows the backend to be the single source of truth for layout decisions
      // unless the user manually overrides specific PAGES.
      mapping[idx] = 'ai_auto';
    });

    return mapping;
  };

  /**
   * Get template for a specific PAGE index
   */
  const getTemplateForPAGE = (PAGEIndex) => {
    return PAGETemplateMap[PAGEIndex] || 'three_cards';
  };

  /**
   * Update template for a specific PAGE
   */
  const setTemplateForPAGE = (PAGEIndex, templateId) => {
    setPAGETemplateMap(prev => ({
      ...prev,
      [PAGEIndex]: templateId
    }));
    // When user manually changes, disable auto-mapping
    if (useAutoTemplateMapping) {
      setUseAutoTemplateMapping(false);
    }
  };

  // Placeholder examples based on profession
  const getPlaceholderExample = () => {
    const profession = persona?.profession || 'general';
    const examples = {
      legal: "Create a quarterly compliance report covering active matters, regulatory risks, and outcomes for the legal team.",
      engineering: "Create a technical report on sustainable building practices, covering green materials and LEED certification.",
      pharmaceutical: "Create a whitepaper on drug development lifecycle from discovery to market launch.",
      contract: "Create a proposal for EPC contract negotiations with risk allocation and payment milestones.",
      general: "Create a Q2 executive performance report with revenue trends, regional breakdowns, top accounts, and pipeline narrative — grounded in our data store.",
    };
    return examples[profession] || examples.general;
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

  // Generate PAGE outline using AI with streaming
  // `opts` lets the chat → composer prefill path pass values directly,
  // bypassing the state-commit race (setGoal is async).
  const generateOutline = async (opts = {}) => {
    const effectiveGoal = (opts.goalOverride ?? goal);
    const effectiveCorpus = Array.isArray(opts.corpusOverride)
      ? opts.corpusOverride
      : prefillCorpusRef.current;
    if (!effectiveGoal || !effectiveGoal.trim()) {
      Alert.alert('Missing Goal', 'Please describe the visual report you want to create.');
      return;
    }

    // Validate goal word count
    if (goalWordCount > MAX_GOAL_WORDS) {
      Alert.alert('Goal Too Long', `Please reduce your goal to ${MAX_GOAL_WORDS} words. Current: ${goalWordCount} words.`);
      return;
    }

    // Apply Vault Logic for printable:
    // - Only use vault if folders are explicitly selected
    // - No default to 'general' for printable (unlike chat)
    // opts.folderIdsOverride wins for the chat-handoff path — it pins the
    // build to the internal chat report vault where the research landed.
    const finalFolderIds = (Array.isArray(opts.folderIdsOverride) && opts.folderIdsOverride.length)
      ? opts.folderIdsOverride
      : (useUploadedData && selectedFolders.length > 0
          ? selectedFolders.map(f => f.id || f)
          : []);

    setIsGeneratingOutline(true);
    setIsStreaming(true);
    setErrorMessage('');
    setStreamingProgress('Starting...');
    setPAGEOutline([]); // Clear existing PAGES
    setDeckPlan(null); // Reset deck plan so a re-run doesn't carry the previous one
    setCurrentStep(2); // Switch to step 2 immediately to show streaming

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        setCurrentStep(1);
        return;
      }

      console.log('🎯 [printable] Generating PAGE outline with streaming...', { useUploadedData, finalFolderIds });

      // Validate PAGE count (opts.pageCountOverride wins for the prefill path)
      const PAGECountNum = parseInt(opts.pageCountOverride ?? PAGECount) || 10;
      if (PAGECountNum < 1 || PAGECountNum > 20) {
        console.log('🎯 [printable] Validation failed: PAGE count', PAGECountNum);
        setErrorMessage('Number of PAGES must be between 1 and 20.');
        setCurrentStep(1);
        return;
      }

      console.log('🎯 [printable] Making streaming request with PAGE_count:', PAGECountNum);

      const response = await fetch(`${apiConfig.API_URL}/printable/generate-outline-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          goal: effectiveGoal,
          printable_type: printableType,
          target_audience: targetAudience,
          PAGE_count: PAGECountNum,
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
      const streamedPAGES = [];

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
                console.log('🎯 [printable] Progress:', data.message);
              } else if (data.type === 'internet_research') {
                console.log('🌐 [PRINTABLE] Internet research embedded:', data.document_id, 'folder:', data.folder_id, 'words:', data.word_count);
              } else if (data.type === 'PAGE') {
                // Add PAGE with unique ID
                const PAGEWithId = {
                  ...data.PAGE,
                  id: `PAGE_${Date.now()}_${data.index}`,
                  order: data.index + 1,
                };
                streamedPAGES.push(PAGEWithId);
                setPAGEOutline([...streamedPAGES]);
                console.log('🎯 [printable] Received PAGE:', data.index + 1, PAGEWithId.title);
              } else if (data.type === 'storyboard') {
                // Capture the document-level plan emitted after the PAGE stream.
                // Without this, every /generate-page call falls back to a
                // baseline storyboard and pages lose document cohesion.
                setDeckPlan(data.storyboard || null);
                setStreamingProgress('Outline ready');
                console.log('🎯 [printable] Document storyboard captured');
              } else if (data.type === 'done') {
                console.log('🎯 [printable] Streaming complete. Total PAGES:', data.total);
                setStreamingProgress('');
              } else if (data.type === 'error') {
                console.error('🎯 [printable] Stream error:', data.message);
                // Check if this is a credit error (402 insufficient_credits from streaming)
                if (handleCreditError(data.message || data)) {
                  setCurrentStep(1);
                  return; // Stop processing stream
                }
                setErrorMessage(data.message);
                if (streamedPAGES.length === 0) {
                  setCurrentStep(1);
                }
              }
            } catch (parseError) {
              console.warn('🎯 [printable] Failed to parse SSE data:', line);
            }
          }
        }
      }

      if (streamedPAGES.length === 0) {
        throw new Error('No PAGES were generated');
      }

      console.log('🎯 [printable] Created', streamedPAGES.length, 'PAGE outlines via streaming');

    } catch (error) {
      console.error('Error generating outline:', error);
      setErrorMessage(error.message || 'Failed to generate PAGE outline. Please try again.');
      if (PAGEOutline.length === 0) {
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

  // Add new page to outline
  const addNewPAGE = () => {
    const newPAGE = {
      id: `PAGE_${Date.now()}`,
      title: 'New Page',
      content_hint: 'Describe what this page should cover...',
      layout: 'title_content',
      order: PAGEOutline.length + 1,
      image_prompt: '',
    };
    setPAGEOutline([...PAGEOutline, newPAGE]);
    setEditingPAGEId(newPAGE.id);
    setEditingTitle(newPAGE.title);
    setEditingContent(newPAGE.content_hint);
  };

  // Start editing a PAGE
  const startEditing = (PAGE) => {
    setEditingPAGEId(PAGE.id);
    setEditingTitle(PAGE.title);
    setEditingContent(PAGE.content_hint);
  };

  // Save editing
  const saveEditing = () => {
    if (!editingPAGEId) return;

    setPAGEOutline(PAGEOutline.map(PAGE =>
      PAGE.id === editingPAGEId
        ? { ...PAGE, title: editingTitle, content_hint: editingContent }
        : PAGE
    ));
    setEditingPAGEId(null);
    setEditingTitle('');
    setEditingContent('');
  };

  // Delete page
  const deletePAGE = (id) => {
    if (PAGEOutline.length <= 1) {
      Alert.alert('Cannot Delete', 'You need at least one page.');
      return;
    }
    setPAGEOutline(PAGEOutline.filter(PAGE => PAGE.id !== id));
  };

  // Move PAGE up
  const movePAGEUp = (index) => {
    if (index <= 0) return;
    const newOutline = [...PAGEOutline];
    [newOutline[index - 1], newOutline[index]] = [newOutline[index], newOutline[index - 1]];
    setPAGEOutline(newOutline.map((s, i) => ({ ...s, order: i + 1 })));
  };

  // Move PAGE down
  const movePAGEDown = (index) => {
    if (index >= PAGEOutline.length - 1) return;
    const newOutline = [...PAGEOutline];
    [newOutline[index], newOutline[index + 1]] = [newOutline[index + 1], newOutline[index]];
    setPAGEOutline(newOutline.map((s, i) => ({ ...s, order: i + 1 })));
  };

  // Generate full printable - PARALLEL EXECUTION with RETRIES
  const generateprintable = async () => {
    if (PAGEOutline.length === 0) {
      Alert.alert('No Pages', 'Please add at least one page.');
      return;
    }

    setIsGeneratingprintable(true);
    setGenerationProgress({ current: 0, total: PAGEOutline.length });
    setIsprintableCancelled(false);
    printableCancelRef.current = false;

    // Store ALL PAGES in a sparse array to maintain order
    // Initialize with nulls or empty objects if needed
    // But we'll just insert by index
    const allPAGES = new Array(PAGEOutline.length).fill(null);
    let completedCount = 0;

    // Use a reference to track credit errors to stop other tasks implies we need a shared state
    // But Promises run eagerly. If one fails with credit error, we should try to mark a global flag.
    let creditErrorOccurred = false;



    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log('🎬 [printable] Starting PARALLEL PAGE generation...');

      // Notify UI immediately to switch view
      if (onPrintableGenerated) {
        onPrintableGenerated({
          goal: goal,
          targetAudience: targetAudience,
          printableType: printableType,
          style: selectedStyle,
          templateMap: PAGETemplateMap,
          PAGEOutline: PAGEOutline,
          PAGES: [], // Empty initially
          generatedAt: new Date().toISOString(),
          isGenerating: true,
        });
      }

      if (onGoalSet) {
        onGoalSet({
          purpose: goal,
          targetAudience: targetAudience,
          printableType: printableType,
          style: selectedStyle,
          templateMap: PAGETemplateMap,
          PAGEOutline: PAGEOutline,
          generationQuality: generationQuality,
          folderIds: selectedFolders.map(f => f.id || f),
          deckProfile: deckProfile,
          // Storyboard captured during outline streaming — forwarded by the
          // Composer on every edit/orchestrate call so per-page edits stay
          // coherent with the document's design language.
          deckPlan: deckPlan,
        });
      }

      onClose?.();

      // Define the worker function for a single PAGE
      const generateSinglePAGE = async (idx) => {
        if (creditErrorOccurred) return;

        const PAGEInfo = PAGEOutline[idx];
        console.log(`🎬 [PARALLEL] Starting PAGE ${idx + 1}: ${PAGEInfo.title}`);

        try {
          // Use Retry Logic for the fetch
          const data = await retryWithBackoff(async () => {
            if (creditErrorOccurred) throw new Error('CREDITS_REQUIRED_SKIP');

            // Construct valid previous_PAGES context from OUTLINE
            // (Since we run in parallel, we can't wait for real previous content)
            const prevPAGESContext = idx > 0
              ? PAGEOutline.slice(Math.max(0, idx - 2), idx).map(s => ({ title: s.title, content_summary: s.content_hint }))
              : [];

            let finalSpecialInstructions = specialInstructions || '';
            if (generationQuality === 'basic') {
              const saveCostInstruction = "  do not generate description of infographic image and image with text , if image is required then only generate photo image desciption and type as photo and return type of image desciption as photo, this is done to save cost per slide generation";
              finalSpecialInstructions = finalSpecialInstructions ? `${finalSpecialInstructions}\n\n${saveCostInstruction}` : saveCostInstruction;
            }
            console.log("UI LOG - Special Instructions Sent:", finalSpecialInstructions, "| Generation Quality:", generationQuality);

            const response = await fetch(`${apiConfig.API_URL}/printable/generate-PAGE`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
              },
              body: JSON.stringify({
                PAGE_info: PAGEInfo,
                PAGE_index: idx,
                total_PAGES: PAGEOutline.length,
                printable_goal: goal,
                printable_type: printableType,
                style: selectedStyle,
                // template_id is sent ONLY for corporate; general bypasses
                // the template path entirely and uses the legacy free-form
                // generator on the server.
                template_id: deckProfile === 'corporate' ? getTemplateForPAGE(idx) : null,
                folder_ids: selectedFolders.map(f => f.id || f),
                previous_PAGES: prevPAGESContext,
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

          if (data.success && data.PAGE) {
            console.log(`✅ [PARALLEL] PAGE ${idx + 1} raw generation complete`);

            let processedPAGE = await processPAGEAsync(data.PAGE);

            // Handle Images in Parallel (with retries too!)
            const imagePlaceholders = processedPAGE.elements?.filter(el => el.type === 'image_placeholder') || [];

            if (imagePlaceholders.length > 0) {
              const imagePromises = imagePlaceholders.map(async (placeholder) => {
                const placeholderImageType = placeholder.imageType || 'photo';
                if (creditErrorOccurred) return;

                const PAGETitle = PAGEInfo.title || 'printable';
                const imagePrompt = placeholder.imageDescription && placeholder.imageDescription !== 'Professional image'
                  ? placeholder.imageDescription
                  : `Professional printable image for a PAGE titled "${PAGETitle}". Context: ${processedPAGE.elements.find(e => e.type === 'text')?.content || PAGETitle}`;

                try {
                  // Determine model: let ImageGenService auto-select by imageType

                  // Retry image generation
                  const imageResult = await retryWithBackoff(async () => {
                    if (creditErrorOccurred) throw new Error('CREDITS_REQUIRED_SKIP');
                    // Background images use default model
                    if (placeholderImageType === 'background') {
                      return await ImageGenService.generateImage(imagePrompt, {
                        width: placeholder.width || 794,
                        height: placeholder.height || 1123,
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
                  }, 3, 1000);

                  if (imageResult.success && (imageResult.image_data || imageResult.image_url)) {
                    placeholder.type = 'image';
                    placeholder.src = imageResult.image_data || imageResult.image_url;
                    // Pre-cache the generated image blob so it's ready for presentation mode
                    // without needing to navigate to each page in the editor first
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
                  console.error(`❌ Image gen error (PAGE ${idx}):`, imgIndErr);
                  if (imgIndErr?.message === 'CREDITS_REQUIRED') creditErrorOccurred = true;

                  placeholder.type = 'shape';
                  placeholder.fill = '#E2E8F0';
                  placeholder.shapeType = 'rectangle';
                }
              });

              // Wait for all images on THIS PAGE to finish (or fail) so the PAGE we push is "complete"
              await Promise.all(imagePromises);
            }

            // Finalize PAGE object
            // critique_recommended: server flags pages that should run through
            // the vision-critique pass after render. Mirrors the presentation
            // flow so PrintableComposer can fire one critique per page in
            // parallel post-render.
            const finalPAGE = {
              ...processedPAGE,
              id: PAGEInfo.id,
              order: idx + 1,
              outline: PAGEInfo.content_hint || PAGEInfo.title || '',
              critique_recommended: data.critique_recommended === true,
            };

            // Store in results
            allPAGES[idx] = finalPAGE;

            // Check if server flagged credit exhaustion (e.g. layout fix ran out of credits)
            // The page was still generated successfully, but no more credits remain
            if (data.credits_warning) {
              console.log('💰 [CREDITS] Server returned credits_warning with page:', JSON.stringify(data.credits_warning));
              handleCreditError(data.credits_warning);
              creditErrorOccurred = true;
            }

          } else {
            throw new Error('No PAGE data returned');
          }

        } catch (err) {
          console.error(`❌ [PARALLEL] PAGE ${idx + 1} Failed after retries:`, err);
          if (err.message === 'CREDITS_REQUIRED') {
            creditErrorOccurred = true;
            return; // Stop processing
          }

          // Create Error Placeholder PAGE so we don't have a hole
          const failedPAGE = {
            id: PAGEInfo.id,
            order: idx + 1,
            title: PAGEInfo.title,
            layout: PAGEInfo.layout || 'title_content',
            elements: [
              {
                id: `el_fail_title_${idx}`,
                type: 'text',
                textType: 'title',
                content: PAGEInfo.title,
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
            backgroundColor: selectedStyle?.PAGEBackground || '#ffffff',
          };
          allPAGES[idx] = failedPAGE;
        }

        // Check for cancellation
        if (printableCancelRef.current) {
          console.log('🛑 [printable] PAGE generation cancelled by user');
          return;
        }

        // Update Progress & UI
        completedCount++;
        setGenerationProgress({ current: completedCount, total: PAGEOutline.length });

        // Notify Parent Immediately with what we have (filtering out nulls/pending)
        // This causes PAGES to "pop in" out of order in memory, but correct order in list
        if (onPrintableGenerated && !creditErrorOccurred) {
          const availablePAGES = allPAGES.filter(s => s !== null);
          onPrintableGenerated({
            goal: goal,
            targetAudience: targetAudience,
            printableType: printableType,
            style: selectedStyle,
            templateMap: PAGETemplateMap,
            PAGEOutline: PAGEOutline,
            // Send ALL currently finished PAGES
            PAGES: availablePAGES,
            generatedAt: new Date().toISOString(),
            isGenerating: completedCount < PAGEOutline.length,
          });
        }
      };

      // LAUNCH IN BATCHES (max 5 concurrent pages to avoid overwhelming the API)
      const MAX_CONCURRENT_PAGES = 5;
      const pageIndices = PAGEOutline.map((_, idx) => idx);

      for (let i = 0; i < pageIndices.length; i += MAX_CONCURRENT_PAGES) {
        if (creditErrorOccurred || printableCancelRef.current) break;
        const batch = pageIndices.slice(i, i + MAX_CONCURRENT_PAGES);
        await Promise.all(batch.map(idx => generateSinglePAGE(idx)));
      }

      console.log('🎬 [printable] All Parallel Tasks Finished');

      // Check if cancelled
      if (printableCancelRef.current) {
        const completedPAGES = allPAGES.filter(Boolean);
        console.log(`🛑 [printable] Cancelled with ${completedPAGES.length} PAGES completed`);
        Alert.alert('Cancelled', `Generated ${completedPAGES.length} of ${PAGEOutline.length} PAGES before cancellation.`);

        // Still send partial results if any
        if (completedPAGES.length > 0 && onPrintableGenerated) {
          onPrintableGenerated({
            goal: goal,
            targetAudience: targetAudience,
            printableType: printableType,
            style: selectedStyle,
            templateMap: PAGETemplateMap,
            PAGEOutline: PAGEOutline,
            PAGES: completedPAGES,
            iconSet: iconSet,
            generatedAt: new Date().toISOString(),
            isGenerating: false,
            wasCancelled: true,
          });
        }
        return;
      }

      // Final Completion Call
      if (onPrintableGenerated) {
        onPrintableGenerated({
          goal: goal,
          targetAudience: targetAudience,
          printableType: printableType,
          style: selectedStyle,
          templateMap: PAGETemplateMap,
          PAGEOutline: PAGEOutline,
          PAGES: allPAGES.filter(Boolean), // Ensure no holes
          iconSet: iconSet,
          generatedAt: new Date().toISOString(),
          isGenerating: false,
        });
      }

    } catch (error) {
      console.error('Error generating printable:', error);
      if (error?.message !== 'CREDITS_REQUIRED') {
        Alert.alert('Error', 'Failed to generate printable. Please try again.');
      }
    } finally {
      setIsGeneratingprintable(false);
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
          <Ionicons name="bulb-outline" size={isMobile ? 16 : 20} color={theme.primary} /> Visual Report Goal
        </Text>
        <Text style={[styles.sectionDescription, { color: theme.textSecondary }]}>
          Describe the visual report you want to create. Be specific about KPIs, sections, audience, and the business question it should answer.
        </Text>

        {/* Grounding folder — one auto-created folder per printable, no
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
            console.log('🔵 [printableGoalInput] Vault button clicked');
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
              Upload Reference Files to Data Store
            </Text>
            <Text style={{ fontSize: 11, color: '#DB2777', lineHeight: 14 }}>
              AI will use your files as context for better documents
            </Text>
          </View>
        </TouchableOpacity>

        {/* Document Type selector removed.
            Every Citra report is an executive overview — the outline LLM
            no longer reads `printable_type` to switch tone; tone is
            inferred from the goal text. The `printableType` state stays
            for backward-compat with the request payload. */}

        {/* Document Style picker (Corporate vs General) intentionally hidden —
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

        {/* Number of Pages */}
        <Text style={[styles.fieldLabel, { color: theme.text }]}>Number of Pages</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 8, marginBottom: 20 }}>
          {['1', '5', '10', '15', '20'].map((count) => (
            <TouchableOpacity
              key={count}
              style={[
                styles.PAGECountOption,
                {
                  backgroundColor: PAGECount === count ? theme.primary : theme.surface,
                  borderColor: PAGECount === count ? theme.primary : theme.border,
                  marginBottom: 0,
                },
              ]}
              onPress={() => setPAGECount(count)}
            >
              <Text
                style={[
                  styles.PAGECountText,
                  { color: PAGECount === count ? '#fff' : theme.text },
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
                min="1"
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
                value={['1', '5', '10', '15', '20'].includes(PAGECount) ? '' : PAGECount}
                placeholder="#"
                onChange={(e) => {
                  const val = e.target.value;
                  setPAGECount(val);
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
                value={['1', '5', '10', '15', '20'].includes(PAGECount) ? '' : PAGECount}
                placeholder="#"
                placeholderTextColor={theme.textSecondary}
                keyboardType="numeric"
                onChangeText={setPAGECount}
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
                console.log('🎯 Generate button pressed, goal:', goal.trim()?.substring(0, 50));
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
                <Text style={styles.primaryButtonText}>Generate Page Outline</Text>
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
              console.log('🎯 Generate button pressed, goal:', goal.trim()?.substring(0, 50));
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
                <Text style={styles.primaryButtonText}>Generate Page Outline</Text>
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
            <Ionicons name="list-outline" size={20} color={theme.primary} /> Page Outline
          </Text>
          {!isStreaming && (
            <TouchableOpacity
              style={[styles.addButton, { backgroundColor: theme.primary }]}
              onPress={addNewPAGE}
            >
              <Ionicons name="add" size={18} color="#fff" />
              <Text style={styles.addButtonText}>Add Page</Text>
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
                {streamingProgress || 'Generating pages...'}
              </Text>
              <Text style={{ color: theme.textSecondary, fontSize: 12, marginTop: 2 }}>
                {PAGEOutline.length > 0 ? `${PAGEOutline.length} page${PAGEOutline.length > 1 ? 's' : ''} generated` : 'Pages will appear below as they are created'}
              </Text>
            </View>
          </View>
        )}

        <Text style={[styles.sectionDescription, { color: theme.textSecondary }]}>
          {isStreaming
            ? 'Your pages are being generated. They will appear below one by one.'
            : 'Review and edit the page outline. You can reorder, add, or delete pages.'}
        </Text>

        {PAGEOutline.map((PAGE, index) => (
          <View
            key={PAGE.id}
            style={[
              styles.PAGECard,
              {
                backgroundColor: theme.surface,
                borderColor: editingPAGEId === PAGE.id ? theme.primary : theme.border,
              },
            ]}
          >
            <View style={styles.PAGECardHeader}>
              <View style={[styles.PAGENumber, { backgroundColor: theme.primary }]}>
                <Text style={styles.PAGENumberText}>{index + 1}</Text>
              </View>

              {editingPAGEId === PAGE.id ? (
                <TextInput
                  style={[styles.PAGETitleInput, { color: theme.text, borderColor: theme.border }]}
                  value={editingTitle}
                  onChangeText={setEditingTitle}
                  placeholder="Page title"
                  placeholderTextColor={theme.textSecondary}
                  autoFocus
                />
              ) : (
                <Text style={[styles.PAGETitle, { color: theme.text }]}>{PAGE.title}</Text>
              )}

              <View style={styles.PAGEActions}>
                <TouchableOpacity onPress={() => movePAGEUp(index)} disabled={index === 0}>
                  <Ionicons name="chevron-up" size={20} color={index === 0 ? theme.border : theme.textSecondary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => movePAGEDown(index)} disabled={index === PAGEOutline.length - 1}>
                  <Ionicons name="chevron-down" size={20} color={index === PAGEOutline.length - 1 ? theme.border : theme.textSecondary} />
                </TouchableOpacity>
                {editingPAGEId === PAGE.id ? (
                  <TouchableOpacity onPress={saveEditing}>
                    <Ionicons name="checkmark" size={20} color={theme.primary} />
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity onPress={() => startEditing(PAGE)}>
                    <Ionicons name="pencil" size={18} color={theme.textSecondary} />
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => deletePAGE(PAGE.id)}>
                  <Ionicons name="trash-outline" size={18} color="#EF4444" />
                </TouchableOpacity>
              </View>
            </View>

            {editingPAGEId === PAGE.id ? (
              <TextInput
                style={[
                  styles.PAGEContentInput,
                  { color: theme.text, backgroundColor: theme.background, borderColor: theme.border },
                ]}
                value={editingContent}
                onChangeText={setEditingContent}
                placeholder="What should this page cover?"
                placeholderTextColor={theme.textSecondary}
                multiline
                numberOfLines={3}
              />
            ) : (
              <Text style={[styles.PAGEContent, { color: theme.textSecondary }]}>
                {PAGE.content_hint}
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
            style={[styles.primaryButton, { backgroundColor: theme.primary }]}
            onPress={() => setCurrentStep(3)}
          >
            <Text style={styles.primaryButtonText}>Choose Template</Text>
            <Ionicons name="arrow-forward" size={18} color="#fff" />
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
    const bgColor = currentStyle.PAGEBackground || '#ffffff';

    // Template thumbnail component with visual preview
    const TemplateThumbnail = ({ templateId, isSelected, onSelect, size = 'normal' }) => {
      const template = PAGE_TEMPLATES[templateId];
      if (!template) return null;

      // A4 aspect ratio (794:1123 ≈ 0.707) - portrait orientation for printables
      const thumbWidth = size === 'small' ? 70 : 100;
      const thumbHeight = size === 'small' ? 99 : 141;

      // Render mini preview based on template type
      const renderMiniPreview = () => {
        const miniStyles = {
          PAGE: { flex: 1, padding: 4 },
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
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginTop: 16 }]} />
                <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '40%', alignSelf: 'center' }]} />
              </View>
            );
          case 'title_image':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '70%', alignSelf: 'center' }]} />
                <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '50%', height: 28, alignSelf: 'center', marginTop: 6 }]} />
              </View>
            );
          case 'bullets':
            return (
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 4 }}>
                  {[0, 1, 2].map(i => (
                    <React.Fragment key={i}>
                      <View style={{ width: '70%', height: 8, borderRadius: 1.5, backgroundColor: cardBg, borderWidth: 1, borderColor: accentColor, opacity: 0.85 }} />
                      {i < 2 && <View style={{ width: 1.5, height: 6, backgroundColor: accentColor, opacity: 0.5 }} />}
                    </React.Fragment>
                  ))}
                </View>
              </View>
            );
          case 'org_hierarchy':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  <View style={{ width: 16, height: 7, borderRadius: 1, backgroundColor: accentColor }} />
                  <View style={{ width: 1, height: 5, backgroundColor: accentColor, opacity: 0.6 }} />
                  <View style={{ width: '65%', height: 1, backgroundColor: accentColor, opacity: 0.6 }} />
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '65%' }}>
                    {[0, 1, 2].map(i => (
                      <View key={i} style={{ width: 1, height: 5, backgroundColor: accentColor, opacity: 0.6 }} />
                    ))}
                  </View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '72%' }}>
                    {[0, 1, 2].map(i => (
                      <View key={i} style={{ width: 11, height: 6, borderRadius: 1, borderWidth: 1, borderColor: accentColor }} />
                    ))}
                  </View>
                </View>
              </View>
            );
          case 'infographic_diagram':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '55%', marginLeft: 6 }]} />
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
                  <View style={{ width: 11, height: 11, borderRadius: 6, backgroundColor: accentColor, opacity: 0.7 }} />
                  <View style={{ width: 11, height: 11, borderRadius: 1.5, backgroundColor: accentColor, opacity: 0.5 }} />
                  <View style={{ width: 0, height: 0, borderLeftWidth: 5.5, borderRightWidth: 5.5, borderBottomWidth: 10, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: accentColor, opacity: 0.6 }} />
                  <View style={{ width: 11, height: 11, borderWidth: 1.5, borderColor: accentColor, borderRadius: 1.5 }} />
                </View>
              </View>
            );
          case 'image_left':
            return (
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
              <View style={miniStyles.PAGE}>
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
          // Resume Templates
          case 'resume_header_photo':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', padding: 4 }}>
                  <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: cardBg, marginRight: 6 }} />
                  <View style={{ flex: 1 }}>
                    <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '60%' }]} />
                  </View>
                </View>
                {[1, 2, 3].map(i => (
                  <View key={i} style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, marginHorizontal: 6, width: '85%', marginTop: 4 }]} />
                ))}
              </View>
            );
          case 'resume_two_column':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', alignSelf: 'center' }]} />
                <View style={{ flexDirection: 'row', flex: 1, marginTop: 6 }}>
                  <View style={{ width: '35%', backgroundColor: cardBg, marginLeft: 4, borderRadius: 2, padding: 3 }}>
                    <View style={[miniStyles.line, { backgroundColor: accentColor, width: '60%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '80%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '70%' }]} />
                  </View>
                  <View style={{ flex: 1, marginLeft: 4, marginRight: 4 }}>
                    <View style={[miniStyles.line, { backgroundColor: accentColor, width: '50%' }]} />
                    {[1, 2, 3].map(i => (
                      <View key={i} style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '90%', marginTop: 3 }]} />
                    ))}
                  </View>
                </View>
              </View>
            );
          // Report Templates
          case 'report_title_page':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ alignItems: 'center', marginTop: 12 }}>
                  <View style={{ width: 24, height: 12, backgroundColor: cardBg, borderRadius: 2, marginBottom: 8 }} />
                  <View style={[miniStyles.title, { backgroundColor: textColor, width: '70%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '50%', marginTop: 4 }]} />
                </View>
                <View style={{ position: 'absolute', bottom: 6, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.3, width: '40%' }]} />
                </View>
              </View>
            );
          case 'report_chart_focus':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', marginLeft: 6 }]} />
                <View style={{ backgroundColor: cardBg, marginHorizontal: 6, marginTop: 6, height: 28, borderRadius: 3, alignItems: 'flex-end', justifyContent: 'flex-end', padding: 3 }}>
                  <View style={{ flexDirection: 'row', gap: 2, alignItems: 'flex-end' }}>
                    <View style={{ width: 4, height: 8, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 14, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 10, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 18, backgroundColor: accentColor }} />
                  </View>
                </View>
                <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, marginHorizontal: 6, marginTop: 4, width: '80%' }]} />
              </View>
            );
          case 'report_multi_column':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ flexDirection: 'row', marginTop: 6, paddingHorizontal: 4, gap: 3 }}>
                  {[1, 2, 3].map(i => (
                    <View key={i} style={{ flex: 1 }}>
                      {[1, 2, 3].map(j => (
                        <View key={j} style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '90%', marginTop: 2 }]} />
                      ))}
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'report_executive_summary':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', marginLeft: 6 }]} />
                <View style={{ flexDirection: 'row', marginTop: 6, paddingHorizontal: 6, gap: 4 }}>
                  <View style={{ flex: 1 }}>
                    {[1, 2, 3].map(i => (
                      <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginTop: 3 }}>
                        <View style={[miniStyles.bullet, { backgroundColor: accentColor }]} />
                        <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: 30, marginTop: 0 }]} />
                      </View>
                    ))}
                  </View>
                  <View style={{ width: '40%' }}>
                    <View style={{ flexDirection: 'row', gap: 3, justifyContent: 'center' }}>
                      <View style={{ width: 16, height: 16, backgroundColor: cardBg, borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ fontSize: 8, fontWeight: 'bold', color: accentColor }}>%</Text>
                      </View>
                      <View style={{ width: 16, height: 16, backgroundColor: cardBg, borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ fontSize: 8, fontWeight: 'bold', color: accentColor }}>#</Text>
                      </View>
                    </View>
                  </View>
                </View>
              </View>
            );
          case 'section_break':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '40%' }]} />
                  <View style={{ width: 20, height: 3, backgroundColor: accentColor, marginTop: 8, borderRadius: 1 }} />
                </View>
              </View>
            );
          case 'closing':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  <View style={[miniStyles.title, { backgroundColor: textColor, width: '55%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '35%' }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.3, width: '45%' }]} />
                  <View style={{ width: 30, height: 3, backgroundColor: accentColor, marginTop: 6, borderRadius: 1 }} />
                </View>
              </View>
            );
          case 'four_cards':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center' }]} />
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 4, marginTop: 6, paddingHorizontal: 4 }}>
                  {[1, 2, 3, 4].map(i => (
                    <View key={i} style={[miniStyles.card, { backgroundColor: cardBg, width: '42%', height: 24 }]}>
                      <View style={[miniStyles.icon, { backgroundColor: accentColor }]} />
                      <View style={[miniStyles.line, { backgroundColor: textColor, width: '70%' }]} />
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'timeline':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', alignSelf: 'center' }]} />
                <View style={{ flexDirection: 'row', marginTop: 6, paddingHorizontal: 6 }}>
                  <View style={{ width: 2, backgroundColor: accentColor, opacity: 0.4, marginRight: 4 }} />
                  <View style={{ flex: 1 }}>
                    {[1, 2, 3, 4].map(i => (
                      <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginTop: i === 1 ? 0 : 4 }}>
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: accentColor, marginRight: 4 }} />
                        <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: 40, marginTop: 0 }]} />
                      </View>
                    ))}
                  </View>
                </View>
              </View>
            );
          case 'comparison':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', alignSelf: 'center' }]} />
                <View style={{ height: 2, backgroundColor: accentColor, marginHorizontal: 6, marginTop: 4 }} />
                <View style={miniStyles.row}>
                  {[1, 2].map(i => (
                    <View key={i} style={{ width: '42%' }}>
                      <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                      <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '90%' }]} />
                      <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '70%' }]} />
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'chart_focus':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                <View style={{ backgroundColor: cardBg, marginHorizontal: 6, marginTop: 4, height: 36, borderRadius: 3, alignItems: 'flex-end', justifyContent: 'flex-end', padding: 3 }}>
                  <View style={{ flexDirection: 'row', gap: 2, alignItems: 'flex-end' }}>
                    <View style={{ width: 4, height: 10, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 18, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 14, backgroundColor: accentColor }} />
                    <View style={{ width: 4, height: 24, backgroundColor: accentColor }} />
                  </View>
                </View>
                <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, marginHorizontal: 6, marginTop: 4, width: '70%' }]} />
              </View>
            );
          case 'stats_highlight':
            return (
              <View style={miniStyles.PAGE}>
                <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', alignSelf: 'center' }]} />
                <View style={{ height: 2, backgroundColor: accentColor, marginHorizontal: 6, marginTop: 4 }} />
                <View style={[miniStyles.row, { marginTop: 8 }]}>
                  {[1, 2, 3].map(i => (
                    <View key={i} style={{ alignItems: 'center', width: '28%' }}>
                      <Text style={{ fontSize: 10, fontWeight: 'bold', color: accentColor }}>##</Text>
                      <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                    </View>
                  ))}
                </View>
              </View>
            );
          case 'big_number':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ fontSize: 18, fontWeight: 'bold', color: accentColor }}>42</Text>
                  <View style={[miniStyles.line, { backgroundColor: textColor, width: '50%', marginTop: 4 }]} />
                  <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '60%' }]} />
                  <View style={{ width: 20, height: 2, backgroundColor: accentColor, opacity: 0.3, marginTop: 6 }} />
                </View>
              </View>
            );
          case 'full_bleed_image':
            return (
              <View style={miniStyles.PAGE}>
                <View style={{ flex: 1, backgroundColor: cardBg, borderStyle: 'dashed', borderWidth: 1, borderColor: accentColor }}>
                  <View style={{ position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(0,0,0,0.4)', padding: 4 }}>
                    <View style={[miniStyles.title, { backgroundColor: '#ffffff', width: '60%' }]} />
                    <View style={[miniStyles.line, { backgroundColor: '#ffffff', opacity: 0.6, width: '40%' }]} />
                  </View>
                </View>
              </View>
            );
          case 'blank_freeflow':
            return (
              <View style={[miniStyles.PAGE, { backgroundColor: bgColor, alignItems: 'center', justifyContent: 'center' }]}>
                <Ionicons name="add" size={16} color={theme.textSecondary} style={{ opacity: 0.5 }} />
              </View>
            );
          default:
            return <View style={miniStyles.PAGE}><View style={[miniStyles.title, { backgroundColor: textColor }]} /></View>;
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
          <View style={[styles.thumbnailPAGE, { backgroundColor: bgColor, height: thumbHeight }]}>
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

    // Available templates for printable documents (resumes, reports)
    const allTemplates = [
      { id: 'ai_auto', category: 'Smart' },
      // Resume Templates
      { id: 'resume_header_photo', category: 'Resume' },
      { id: 'resume_two_column', category: 'Resume' },
      // Report Templates
      { id: 'report_title_page', category: 'Report' },
      { id: 'report_chart_focus', category: 'Report' },
      { id: 'report_multi_column', category: 'Report' },
      { id: 'report_executive_summary', category: 'Report' },
      // Title & Closing
      { id: 'title_hero', category: 'Title' },
      { id: 'title_image', category: 'Title' },
      { id: 'section_break', category: 'Title' },
      { id: 'closing', category: 'Title' },
      // Content
      { id: 'bullets', category: 'Content' },
      { id: 'two_columns', category: 'Content' },
      { id: 'three_cards', category: 'Content' },
      { id: 'four_cards', category: 'Content' },
      { id: 'process_steps', category: 'Content' },
      { id: 'org_hierarchy', category: 'Diagrams' },
      { id: 'infographic_diagram', category: 'Diagrams' },
      { id: 'timeline', category: 'Content' },
      { id: 'comparison', category: 'Content' },
      { id: 'quote', category: 'Content' },
      // Media
      { id: 'image_left', category: 'Media' },
      { id: 'image_right', category: 'Media' },
      { id: 'full_bleed_image', category: 'Media' },
      // Data
      { id: 'data_dashboard', category: 'Data' },
      { id: 'chart_focus', category: 'Data' },
      { id: 'stats_highlight', category: 'Data' },
      { id: 'big_number', category: 'Data' },
      // Advanced
      { id: 'modern_geometric', category: 'Advanced' },
      { id: 'blank_freeflow', category: 'Blank' },
    ];

    return (
      <ScrollView style={styles.stepScroll} contentContainerStyle={styles.stepScrollContent} showsVerticalScrollIndicator={false}>
        <View style={[styles.stepInnerWrapper, isMobile && { padding: 14, maxWidth: '100%' }]}>
          {/* Header with AI-first messaging */}
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            <Ionicons name="sparkles" size={20} color={theme.primary} /> Ready to Generate
          </Text>
          <Text style={[styles.sectionDescription, { color: theme.textSecondary, marginBottom: 8 }]}>
            AI will automatically choose the best layouts and style for your pages.
          </Text>

          {/* The Corporate / General choice is the single routing axis —
              it lives in the document-profile picker at the top of the modal,
              not as a separate toggle. Corporate runs the template path;
              General routes to the legacy free-form generator. */}

          {/* Primary Action - Review & Generate Button (TOP) */}

          {/* Generation Quality (premium/medium/basic) selector removed.
              Executive A4 templates use no photographic imagery, so the
              image-generation cost knob this exposed has no effect on
              executive output. State stays defaulted to 'medium' for
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
                  {PAGEOutline.length} pages ready
                </Text>
                <Text style={{ fontSize: 13, color: theme.textSecondary }}>
                  {deckProfile === 'general'
                    ? `Style: ${selectedStyle?.name || 'Custom'} • AI-designed (free-form)`
                    : (Object.keys(PAGETemplateMap).length > 0 || !useAutoTemplateMapping
                      ? `Style: ${selectedStyle?.name || 'Custom'} • Custom layouts`
                      : `Style: ${selectedStyle?.name || 'Let AI Decide'} • AI layouts`)
                  }
                </Text>
              </View>
            </View>

            <TouchableOpacity
              style={[styles.primaryButton, { backgroundColor: theme.primary, paddingVertical: 16 }]}
              onPress={() => generateprintable()}
              disabled={isGeneratingprintable}
            >
              {isGeneratingprintable ? (
                <>
                  <ActivityIndicator size="small" color="#fff" />
                  <Text style={[styles.primaryButtonText, { marginLeft: 8 }]}>
                    Generating {generationProgress.current}/{generationProgress.total}...
                  </Text>
                </>
              ) : (
                <>
                  <Ionicons name="rocket" size={20} color="#fff" />
                  <Text style={styles.primaryButtonText}>Generate Document</Text>
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



          {/* Collapsible Advanced Setup — per-page template layouts apply to Corporate only.
              General profile lets the LLM design each page from scratch (no templates). */}
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
                  Customize style, icon set, and per-page layouts
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

              {/* Style Selection - PrintableStylePicker */}
              <View style={[styles.styleSection, { marginTop: 8, marginBottom: 20 }]}>
                <PrintableStylePicker
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
                      isSelected={Object.values(PAGETemplateMap).includes(t.id)}
                      onSelect={() => {
                        // Just show preview - don't auto-assign
                      }}
                    />
                  ))}
                </View>
              </View>
              )}

              {/* Auto/Manual Toggle (corporate only) */}
              {deckProfile === 'corporate' && (<>

              <View style={[styles.autoToggleRow, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.autoToggleLabel, { color: theme.text }]}>
                    <Ionicons name="sparkles" size={16} color={theme.primary} /> Let AI create its own template
                  </Text>
                  <Text style={[styles.autoToggleHint, { color: theme.textSecondary }]}>
                    AI will analyze content and create the best layout for each page
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
                    if (newValue && PAGEOutline.length > 0) {
                      // Re-apply auto mapping
                      const mapping = autoMapTemplatesToPAGES(PAGEOutline);
                      setPAGETemplateMap(mapping);
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

              {/* Per-Page Template Mapping */}
              <View style={[styles.PAGETemplateMappingSection, { marginTop: 16 }]}>
                <Text style={[styles.subsectionTitle, { color: theme.text, marginBottom: 12 }]}>
                  <Ionicons name="list-outline" size={16} color={theme.textSecondary} /> Assign to Pages
                </Text>

                {PAGEOutline.map((PAGE, idx) => {
                  const currentTemplate = getTemplateForPAGE(idx);

                  return (
                    <View
                      key={PAGE.id || idx}
                      style={[styles.PAGETemplateRowNew, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    >
                      {/* Page Info Row */}
                      <View style={styles.PAGEInfoRow}>
                        <View style={[styles.PAGENumberBadge, { backgroundColor: accentColor }]}>
                          <Text style={styles.PAGENumberText}>{idx + 1}</Text>
                        </View>
                        <View style={styles.PAGEInfoText}>
                          <Text style={[styles.PAGETitle, { color: theme.text }]} numberOfLines={1}>
                            {PAGE.title}
                          </Text>
                          <Text style={[styles.PAGEContentHint, { color: theme.textSecondary }]} numberOfLines={1}>
                            {PAGE.content_hint || PAGE.contentHint || 'No description'}
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
                            onSelect={() => setTemplateForPAGE(idx, t.id)}
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
          Review your document settings and generate the pages.
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
              {printableTypes.find(t => t.value === printableType)?.label}
            </Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Pages:</Text>
            <Text style={[styles.summaryValue, { color: theme.text }]}>{PAGEOutline.length}</Text>
          </View>
          {/* Template summary row is corporate-only — in general mode the
              server ignores the template map, so showing "N unique layouts"
              would be misleading. */}
          {deckProfile === 'corporate' && (
            <View style={styles.summaryRow}>
              <Text style={[styles.summaryLabel, { color: theme.textSecondary }]}>Templates:</Text>
              <Text style={[styles.summaryValue, { color: theme.primary }]}>
                {Object.values(PAGETemplateMap).filter((v, i, a) => a.indexOf(v) === i).length} unique layouts
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
        {isGeneratingprintable && (
          <View style={[styles.progressCard, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
            <ActivityIndicator size="large" color={theme.primary} />
            <Text style={[styles.progressText, { color: theme.text }]}>
              Generating PAGE {generationProgress.current} of {generationProgress.total}...
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
                printableCancelRef.current = true;
                setIsprintableCancelled(true);
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
            disabled={isGeneratingprintable}
          >
            <Ionicons name="arrow-back" size={18} color={theme.text} />
            <Text style={[styles.secondaryButtonText, { color: theme.text }]}>Back</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.primaryButton,
              {
                backgroundColor: isGeneratingprintable ? theme.border : theme.primary,
                flex: 1,
              },
            ]}
            onPress={generateprintable}
            disabled={isGeneratingprintable}
          >
            {isGeneratingprintable ? (
              <Text style={styles.primaryButtonText}>Generating...</Text>
            ) : (
              <>
                <Ionicons name="sparkles" size={20} color="#fff" />
                <Text style={styles.primaryButtonText}>Generate Dashboard</Text>
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
          <Text style={[styles.headerTitle, { color: theme.text }]}>Create Visual Report</Text>
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
          visible={uploadModalProps?.enhancedProgress && uploadModalProps.enhancedProgress.size > 0}
          enhancedProgress={uploadModalProps?.enhancedProgress}
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
  PAGECountSelector: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 32,
  },
  PAGECountOption: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  PAGECountText: {
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
  PAGECard: {
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
  PAGECardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginBottom: 12,
  },
  PAGENumber: {
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
  PAGENumberText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  PAGETitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  PAGETitleInput: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    borderBottomWidth: 2,
    paddingVertical: 4,
    letterSpacing: 0.2,
  },
  PAGEActions: {
    flexDirection: 'row',
    gap: 8,
    backgroundColor: 'rgba(0,0,0,0.03)',
    borderRadius: 20,
    padding: 4,
  },
  PAGEContent: {
    fontSize: 14,
    lineHeight: 22,
    opacity: 0.9,
    paddingLeft: 46, // Indent to align with title
  },
  PAGEContentInput: {
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
  // Per-PAGE template mapping styles
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
  PAGETemplateMappingSection: {
    marginBottom: 24,
  },
  PAGETemplateRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 10,
    gap: 16,
  },
  PAGETemplateRowNew: {
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
  PAGEInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 8,
  },
  PAGEInfoText: {
    flex: 1,
  },
  PAGEInfoColumn: {
    flex: 1,
    minWidth: 0,
  },
  PAGENumberBadge: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  PAGENumberText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },
  PAGETitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  PAGEContentHint: {
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
  thumbnailPAGE: {
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

export default PrintableGoalInput;
