import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, Alert, ActivityIndicator, StyleSheet, Dimensions, FlatList } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MaterialIcons as Icon, Ionicons } from '@expo/vector-icons';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import UnifiedUploadModal from '../UnifiedUploadModal'; // Unified upload modal
import VaultRequiredModal from '../VaultRequiredModal';
import UploadProgressPopup from '../UploadProgressPopup'; // Upload progress popup for visibility inside modal
import VaultSelectorChip from '../ui/VaultSelectorChip';
import ReportStylePicker, { REPORT_STYLES, getStyleCSS } from './ReportStylePicker';
import authService from '../../services/authService';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const BATCH_SIZE = 5; // Process 5 sections in parallel

/**
 * AI Report Generator - Goal Setting Modal
 * 
 * Flow:
 * 1. User writes comprehensive goal
 * 2. AI breaks goal into to-do items (report sections)
 * 3. User can EDIT, ADD, DELETE, REORDER sections
 * 4. Generate report from vault documents
 */
// Goal validation constants
const MAX_GOAL_WORDS = 500;

// Helper function to count words
const countWords = (text) => {
  if (!text) return 0;
  return text.trim().split(/\s+/).filter(word => word.length > 0).length;
};

const ReportGoalSetting = ({
  onReportGenerated,
  onGoalSet,
  onGenerationStart, // NEW: Called when generation starts with placeholder pages
  onPageBatchGenerated, // NEW: Called after each batch with completed pages
  onPageError, // NEW: Called when a page fails to generate
  existingGoal = null,
  visible = false,
  onClose,
  apiConfig,
  userDeviceId,
  selectedFolders = [],
  folders = [],
  onSelectFolder,
  onCreateVault,
  persona = null,
  uploadModalProps, // NEW: Props for internal ChatUniversalUploadModal
  vaultModalProps, // NEW: Props for internal VaultRequiredModal
}) => {
  const { useUploadedData, setUseUploadedData } = useWorkspace();

  // Guard: check vault is enabled before allowing features that need it
  const requireVault = useCallback((featureMessage) => {
    if (!useUploadedData || !selectedFolders || selectedFolders.length === 0) {
      setVaultNeededMessage(featureMessage);
      setShowVaultNeededModal(true);
      return false;
    }
    return true;
  }, [useUploadedData, selectedFolders]);
  
  // Wizard step state (1 = Basic Info, 2 = Outline & Layouts)
  const [currentStep, setCurrentStep] = useState(1);
  
  // Goal state
  const [goal, setGoal] = useState('');
  const [goalWordCount, setGoalWordCount] = useState(0);
  const [targetAudience, setTargetAudience] = useState('');
  const [documentType, setDocumentType] = useState('report');
  const [sectionCount, setSectionCount] = useState(10); // User-specified section/page count

  // To-do items (report sections) - EDITABLE
  const [todos, setTodos] = useState([]);
  const [editingTodoId, setEditingTodoId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [editingDescription, setEditingDescription] = useState('');

  // Loading states
  const [isBreakingGoal, setIsBreakingGoal] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [specialInstructions, setSpecialInstructions] = useState(''); // User guidance for AI generation
  const [useInternetSearch, setUseInternetSearch] = useState(false);

  // Streaming states
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingProgress, setStreamingProgress] = useState('');

  // Style states
  const [selectedStyle, setSelectedStyle] = useState('ai_auto');
  const [showStylePicker, setShowStylePicker] = useState(false);

  // Batch generation states
  const [generatedPages, setGeneratedPages] = useState([]);
  const [batchProgress, setBatchProgress] = useState({ currentBatch: 0, totalBatches: 0, completedSections: 0, totalSections: 0 });
  const [isCancelled, setIsCancelled] = useState(false);
  const cancelRef = useRef(false);

  // Internal modal state
  const [showInternalUploadModal, setShowInternalUploadModal] = useState(false);
  const [showVaultNeededModal, setShowVaultNeededModal] = useState(false);
  const [vaultNeededMessage, setVaultNeededMessage] = useState('');
  
  // Scroll ref for section list
  const sectionListRef = useRef(null);

  // Normalize profession - always returns 'general' (General Professional only)
  const normalizeProfession = (persona) => {
    return 'general';
  };

  const profession = normalizeProfession(persona);

  // Profession-specific examples
  const getPlaceholderExample = () => {
    return "Create a detailed enterprise document analyzing the topic comprehensively with well-researched content, clear structure, and actionable insights — grounded in your knowledge base.";
  };

  // Document type label - generic for all users
  const getDocumentTypeLabel = () => {
    return 'Case Study';
  };

  const documentTypes = [
    { value: 'report', label: 'Report', icon: 'assessment' },
    { value: 'case_review', label: getDocumentTypeLabel(), icon: 'gavel' },
    { value: 'research', label: 'Research', icon: 'search' },
    { value: 'proposal', label: 'Proposal', icon: 'lightbulb' },
    { value: 'enterprise_doc', label: 'Enterprise Doc', icon: 'business-center' },
    { value: 'summary', label: 'Summary', icon: 'summarize' }
  ];

  useEffect(() => {
    if (visible) {
      if (existingGoal) {
        setGoal(existingGoal.goal || existingGoal.purpose || '');
        setTargetAudience(existingGoal.targetAudience || '');
        if (existingGoal.todos) {
          setTodos(existingGoal.todos);
          setCurrentStep(2); // Go to step 2 if we have existing todos
        }
      } else {
        // Reset state for new report
        setGoal('');
        setTargetAudience('');
        setTodos([]);
        setDocumentType('report');
        setCurrentStep(1); // Start at step 1
      }
    }
  }, [existingGoal, visible]);

  // Handle goal text change with word count validation
  const handleGoalChange = (text) => {
    const words = countWords(text);
    setGoal(text);
    setGoalWordCount(words);
  };

  // Break goal into to-do items using AI with streaming
  const breakGoalIntoTodos = async () => {
    if (!goal.trim()) {
      Alert.alert('Missing Goal', 'Please describe what report you want to create.');
      return;
    }

    // Validate goal word count
    if (goalWordCount > MAX_GOAL_WORDS) {
      Alert.alert('Goal Too Long', `Please reduce your goal to ${MAX_GOAL_WORDS} words. Current: ${goalWordCount} words.`);
      return;
    }

    setIsBreakingGoal(true);
    setIsStreaming(true);
    setStreamingProgress('Starting...');
    setTodos([]); // Clear existing todos
    setGeneratedPages([]); // Clear any previously generated pages
    
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log('🤖 [GOAL] Breaking goal into', sectionCount, 'sections with streaming...');

      const response = await authService.authenticatedFetch(`${apiConfig.API_URL}/composer/break-goal-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          goal: goal,
          document_type: documentType,
          report_type: documentType,
          target_audience: targetAudience,
          section_count: sectionCount, // Pass user-specified section count
          folder_ids: useUploadedData && selectedFolders.length > 0
            ? selectedFolders.map(f => f.id || f)
            : [],
          use_internet_search: useInternetSearch,
          use_personal_data: useUploadedData,
        })
      });

      if (response.status === 401) {
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to analyze goal');
      }

      // Read the streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const streamedTodos = [];

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
                console.log('🤖 [GOAL] Progress:', data.message);
              } else if (data.type === 'internet_research') {
                console.log('🌐 [GOAL] Internet research embedded:', data.document_id, 'folder:', data.folder_id, 'words:', data.word_count);
              } else if (data.type === 'section') {
                // Add section with unique ID
                const todoWithId = {
                  ...data.section,
                  id: `todo_${Date.now()}_${data.index}`,
                };
                streamedTodos.push(todoWithId);
                setTodos([...streamedTodos]);
                console.log('🤖 [GOAL] Received section:', data.index + 1, todoWithId.title);
              } else if (data.type === 'done') {
                console.log('🤖 [GOAL] Streaming complete. Total sections:', data.total);
                setStreamingProgress('');
              } else if (data.type === 'error') {
                console.error('🤖 [GOAL] Stream error:', data.message);
                Alert.alert('Error', data.message);
              }
            } catch (parseError) {
              console.warn('🤖 [GOAL] Failed to parse SSE data:', line);
            }
          }
        }
      }

      if (streamedTodos.length === 0) {
        throw new Error('No sections were generated');
      }

      console.log('🤖 [GOAL] Created', streamedTodos.length, 'to-do items via streaming');
      
      // Transition to Step 2 after successful outline generation
      setCurrentStep(2);

    } catch (error) {
      console.error('Error breaking goal:', error);
      Alert.alert('Error', 'Failed to analyze goal. Please try again.');
    } finally {
      setIsBreakingGoal(false);
      setIsStreaming(false);
      setStreamingProgress('');
    }
  };

  // Add new section
  const addNewSection = () => {
    const newTodo = {
      id: `todo_${Date.now()}`,
      title: 'New Section',
      description: 'Describe what this section should cover...',
      search_query: '',  // Will be set from description when saved
      order: todos.length + 1,
      search_queries: []
    };
    setTodos([...todos, newTodo]);
    setEditingTodoId(newTodo.id);
    setEditingTitle(newTodo.title);
    setEditingDescription(newTodo.description);
  };

  // Start editing a todo
  const startEditing = (todo) => {
    setEditingTodoId(todo.id);
    setEditingTitle(todo.title);
    setEditingDescription(todo.description);
  };

  // Save editing
  const saveEditing = () => {
    if (!editingTodoId) return;

    console.log('[GOAL_SETTING] Saving section edit:', { id: editingTodoId, title: editingTitle, description: editingDescription });

    setTodos(todos.map(todo =>
      todo.id === editingTodoId
        ? {
          ...todo,
          title: editingTitle,
          description: editingDescription,
          // Update search_query to match the description for better AI context
          search_query: editingDescription || editingTitle
        }
        : todo
    ));
    setEditingTodoId(null);
    setEditingTitle('');
    setEditingDescription('');
  };

  // Delete todo
  const deleteTodo = (id) => {
    setTodos(todos.filter(todo => todo.id !== id));
  };

  // Move todo up
  const moveTodoUp = (index) => {
    if (index <= 0) return;
    const newTodos = [...todos];
    [newTodos[index - 1], newTodos[index]] = [newTodos[index], newTodos[index - 1]];
    setTodos(newTodos);
  };

  // Move todo down
  const moveTodoDown = (index) => {
    if (index >= todos.length - 1) return;
    const newTodos = [...todos];
    [newTodos[index], newTodos[index + 1]] = [newTodos[index + 1], newTodos[index]];
    setTodos(newTodos);
  };

  // Helper: Chunk array into batches
  const chunkArray = (array, size) => {
    const chunks = [];
    for (let i = 0; i < array.length; i += size) {
      chunks.push(array.slice(i, i + size));
    }
    return chunks;
  };

  // Generate single section via API with retry logic
  const generateSingleSection = async (section, sectionIndex, totalSections, retryCount = 0) => {
    const MAX_RETRIES = 2;
    
    // Get style configuration (only if user selected a specific style, not ai_auto)
    const styleConfig = selectedStyle && selectedStyle !== 'ai_auto' 
      ? REPORT_STYLES[selectedStyle] 
      : null;
    
    try {
      const response = await authService.authenticatedFetch(`${apiConfig.API_URL}/composer/generate-section`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          section: {
            ...section,
            search_query: section.search_query || section.description || section.title
          },
          goal: goal,
          report_type: documentType,
          folder_ids: useUploadedData && selectedFolders.length > 0
            ? selectedFolders.map(f => f.id || f)
            : [],
          special_instructions: specialInstructions || null,
          section_index: sectionIndex,
          total_sections: totalSections,
          use_internet_search: useInternetSearch,
          use_personal_data: useUploadedData,
          // Pass user-selected style (only if explicitly selected)
          style: styleConfig ? {
            id: selectedStyle,
            colors: styleConfig.colors,
            fonts: styleConfig.fonts
          } : null
        })
      });

      if (!response.ok) {
        // Retry on 500 errors
        if (response.status >= 500 && retryCount < MAX_RETRIES) {
          console.log(`⚠️ [REPORT] Retrying section ${sectionIndex + 1} (attempt ${retryCount + 2}/${MAX_RETRIES + 1})...`);
          await new Promise(resolve => setTimeout(resolve, 1000 * (retryCount + 1))); // Exponential backoff
          return generateSingleSection(section, sectionIndex, totalSections, retryCount + 1);
        }
        throw new Error(`Failed to generate section: ${section.title}`);
      }

      const data = await response.json();
      return data.page;
    } catch (error) {
      // Retry on network errors
      if (retryCount < MAX_RETRIES) {
        console.log(`⚠️ [REPORT] Retrying section ${sectionIndex + 1} after error (attempt ${retryCount + 2}/${MAX_RETRIES + 1})...`);
        await new Promise(resolve => setTimeout(resolve, 1000 * (retryCount + 1)));
        return generateSingleSection(section, sectionIndex, totalSections, retryCount + 1);
      }
      throw error;
    }
  };

  // Generate full report from vault with UI-controlled batching
  const generateReportFromVault = async () => {
    if (todos.length === 0) {
      Alert.alert('No Sections', 'Please add at least one section.');
      return;
    }

    setIsGeneratingReport(true);
    setGeneratedPages([]);
    setIsCancelled(false);
    cancelRef.current = false;

    const totalSections = todos.length;
    const batches = chunkArray(todos, BATCH_SIZE);
    const totalBatches = batches.length;

    setBatchProgress({
      currentBatch: 0,
      totalBatches,
      completedSections: 0,
      totalSections
    });

    // 🆕 PROGRESSIVE RENDERING: Create placeholder pages immediately
    if (onGenerationStart) {
      const placeholderPages = todos.map((todo, index) => ({
        id: `page_placeholder_${index}`,
        order: index + 1,
        title: todo.title,
        description: todo.description,
        content: '',
        isGenerating: true,
        hasError: false,
        errorMessage: null,
        sectionId: todo.id, // Link to original section
      }));
      onGenerationStart({
        placeholderPages,
        totalSections,
        reportStyle: selectedStyle,
        goal,
        targetAudience,
        documentType,
      });
    }

    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) {
        Alert.alert('Authentication Error', 'Please log in again.');
        return;
      }

      console.log(`🤖 [REPORT] Generating ${totalSections} sections in ${totalBatches} batches of ${BATCH_SIZE}...`);

      const allPages = [];
      const allCitations = [];

      // Process batches sequentially, sections within batch in parallel
      for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
        if (cancelRef.current) {
          console.log('🛑 [REPORT] Generation cancelled by user');
          break;
        }

        const batch = batches[batchIndex];
        const batchStartIndex = batchIndex * BATCH_SIZE;

        setBatchProgress(prev => ({
          ...prev,
          currentBatch: batchIndex + 1
        }));

        console.log(`🔄 [REPORT] Processing batch ${batchIndex + 1}/${totalBatches} (${batch.length} sections)...`);

        // Generate all sections in this batch in parallel
        const batchPromises = batch.map((section, idx) => {
          const sectionIndex = batchStartIndex + idx;
          return generateSingleSection(section, sectionIndex, totalSections)
            .then(page => ({
              ...page,
              sectionId: section.id,
              sectionIndex,
              isGenerating: false,
              hasError: false,
            }))
            .catch(err => {
              console.error(`❌ Failed to generate section ${sectionIndex + 1}:`, err);
              // 🆕 PROGRESSIVE RENDERING: Report error for this specific page
              if (onPageError) {
                onPageError({
                  sectionId: section.id,
                  sectionIndex,
                  title: section.title,
                  error: err.message || 'Failed to generate section',
                });
              }
              return {
                sectionId: section.id,
                sectionIndex,
                order: sectionIndex + 1,
                title: section.title,
                content: '',
                isGenerating: false,
                hasError: true,
                errorMessage: err.message || 'Failed to generate section',
              };
            });
        });

        const batchResults = await Promise.all(batchPromises);

        // Separate successful and failed pages
        const successfulPages = batchResults.filter(page => !page.hasError);
        const failedPages = batchResults.filter(page => page.hasError);
        allPages.push(...batchResults); // Include all for tracking

        // Collect citations from successful pages
        successfulPages.forEach(page => {
          if (page.citations) {
            allCitations.push(...page.citations);
          }
        });

        // Update local UI with this batch's results
        setGeneratedPages(prev => [...prev, ...batchResults]);

        // 🆕 PROGRESSIVE RENDERING: Notify parent of completed batch immediately
        if (onPageBatchGenerated) {
          onPageBatchGenerated({
            pages: batchResults,
            batchIndex,
            totalBatches,
            completedSections: allPages.length,
            totalSections,
          });
        }

        setBatchProgress(prev => ({
          ...prev,
          completedSections: allPages.length
        }));

        console.log(`✅ [REPORT] Batch ${batchIndex + 1} complete. Total: ${allPages.length}/${totalSections} sections`);
      }

      if (cancelRef.current) {
        Alert.alert('Cancelled', `Generated ${allPages.length} of ${totalSections} sections before cancellation.`);
      } else if (allPages.length > 0) {
        console.log('🤖 [REPORT] Generated', allPages.length, 'pages via batch processing');

        // Sort pages by order
        allPages.sort((a, b) => (a.order || 0) - (b.order || 0));

        if (onReportGenerated) {
          onReportGenerated({
            goal: goal,
            targetAudience: targetAudience,
            documentType: documentType,
            todos: todos,
            pages: allPages,
            citations: allCitations,
            generatedAt: new Date().toISOString(),
            reportStyle: selectedStyle,
            folderIds: useUploadedData && selectedFolders.length > 0 ? selectedFolders.map(f => f.id || f) : [],
          });
        }

        if (onGoalSet) {
          onGoalSet({
            purpose: goal,
            targetAudience: targetAudience,
            documentType: documentType,
            report_type: documentType,
            todos: todos,
            folderIds: useUploadedData && selectedFolders.length > 0 ? selectedFolders.map(f => f.id || f) : [],
          });
        }

        onClose();
        Alert.alert('Success', `Generated ${allPages.length} page report from your data store!`);
      } else {
        throw new Error('Failed to generate any sections');
      }
    } catch (error) {
      console.error('Error generating report:', error);
      Alert.alert('Error', 'Failed to generate report. Please try again.');
    } finally {
      setIsGeneratingReport(false);
      setBatchProgress({ currentBatch: 0, totalBatches: 0, completedSections: 0, totalSections: 0 });
    }
  };

  // Cancel generation
  const cancelGeneration = () => {
    cancelRef.current = true;
    setIsCancelled(true);
  };

  // Render to-do item (editable)
  const renderTodoItem = (todo, index) => {
    const isEditing = editingTodoId === todo.id;

    return (
      <View key={todo.id} style={styles.todoItem}>
        {/* Order Controls */}
        <View style={styles.todoOrderControls}>
          <TouchableOpacity
            onPress={() => moveTodoUp(index)}
            style={[styles.orderButton, index === 0 && styles.orderButtonDisabled]}
            disabled={index === 0}
          >
            <Icon name="keyboard-arrow-up" size={18} color={index === 0 ? '#ccc' : '#666'} />
          </TouchableOpacity>
          <View style={styles.todoNumber}>
            <Text style={styles.todoNumberText}>{index + 1}</Text>
          </View>
          <TouchableOpacity
            onPress={() => moveTodoDown(index)}
            style={[styles.orderButton, index === todos.length - 1 && styles.orderButtonDisabled]}
            disabled={index === todos.length - 1}
          >
            <Icon name="keyboard-arrow-down" size={18} color={index === todos.length - 1 ? '#ccc' : '#666'} />
          </TouchableOpacity>
        </View>

        {/* Content */}
        <View style={styles.todoContent}>
          {isEditing ? (
            <>
              <TextInput
                style={styles.todoTitleInput}
                value={editingTitle}
                onChangeText={setEditingTitle}
                placeholder="Section title"
                autoFocus
              />
              <TextInput
                style={styles.todoDescInput}
                value={editingDescription}
                onChangeText={setEditingDescription}
                placeholder="What should this section cover?"
                multiline
              />
            </>
          ) : (
            <TouchableOpacity onPress={() => startEditing(todo)} style={styles.todoTextArea}>
              <Text style={styles.todoTitle}>{todo.title}</Text>
              <Text style={styles.todoDescription}>{todo.description}</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Actions */}
        <View style={styles.todoActions}>
          {isEditing ? (
            <TouchableOpacity style={styles.saveButton} onPress={saveEditing}>
              <Icon name="check" size={18} color="#4CAF50" />
            </TouchableOpacity>
          ) : (
            <>
              <TouchableOpacity style={styles.actionButton} onPress={() => startEditing(todo)}>
                <Icon name="edit" size={16} color="#2196F3" />
              </TouchableOpacity>
              <TouchableOpacity style={styles.actionButton} onPress={() => deleteTodo(todo.id)}>
                <Icon name="delete" size={16} color="#f44336" />
              </TouchableOpacity>
            </>
          )}
        </View>
      </View>
    );
  };

  if (!visible) return null;

  // Step indicator component
  const renderStepIndicator = () => (
    <View style={styles.stepIndicator}>
      {[1, 2].map((step, idx) => (
        <React.Fragment key={step}>
          <TouchableOpacity
            style={[
              styles.stepDot,
              currentStep >= step && styles.stepDotActive,
              currentStep === step && styles.stepDotCurrent
            ]}
            onPress={() => {
              // Only allow going back, not forward without completing
              if (step < currentStep) setCurrentStep(step);
            }}
          >
            {currentStep > step ? (
              <Ionicons name="checkmark" size={14} color="#fff" />
            ) : (
              <Text style={[styles.stepDotText, currentStep >= step && styles.stepDotTextActive]}>
                {step}
              </Text>
            )}
          </TouchableOpacity>
          {idx < 1 && (
            <View style={[styles.stepLine, currentStep > step && styles.stepLineActive]} />
          )}
        </React.Fragment>
      ))}
    </View>
  );

  // Render Step 1: Basic Info
  const renderStep1 = () => (
    <ScrollView style={styles.stepContent} showsVerticalScrollIndicator={false}>
      <View style={styles.stepHeader}>
        <Text style={styles.stepTitle}>What document do you want to create?</Text>
        <Text style={styles.stepSubtitle}>Describe your goal and AI will draft an outline grounded in your knowledge base</Text>
      </View>

      {/* Vault Selector - Prominent vault selection */}
      <View style={{ marginBottom: 16 }}>
        <VaultSelectorChip
          selectedFolders={selectedFolders}
          folders={folders}
          onSelectFolder={onSelectFolder}
          onCreateVault={onCreateVault}
          theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
          label="Data Source"
          insideModal
          vaultEnabled={useUploadedData}
          onToggleVault={setUseUploadedData}
        />
      </View>

      {/* Goal Input */}
      <TextInput
        style={styles.goalInput}
        placeholder={`Describe the document you want to create...\n\nExample: ${getPlaceholderExample()}`}
        placeholderTextColor="#999"
        value={goal}
        onChangeText={handleGoalChange}
        multiline
        numberOfLines={4}
        maxLength={3500}
      />

      {/* Word Count Indicator */}
      <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: -8, marginBottom: 12 }}>
        <Text style={{
          fontSize: 12,
          color: goalWordCount > MAX_GOAL_WORDS ? '#EF4444' : '#999',
          fontWeight: goalWordCount > MAX_GOAL_WORDS ? '600' : '400',
        }}>
          {goalWordCount} / {MAX_GOAL_WORDS} words
          {goalWordCount > MAX_GOAL_WORDS && ' (Please reduce to continue)'}
        </Text>
      </View>

      {/* Document Type */}
      <View style={styles.typeRow}>
        {documentTypes.map(type => (
          <TouchableOpacity
            key={type.value}
            style={[
              styles.typeButton,
              documentType === type.value && styles.typeButtonActive
            ]}
            onPress={() => setDocumentType(type.value)}
          >
            <Icon
              name={type.icon}
              size={16}
              color={documentType === type.value ? '#fff' : '#666'}
            />
            <Text style={[
              styles.typeButtonText,
              documentType === type.value && styles.typeButtonTextActive
            ]}>
              {type.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Target Audience */}
      <TextInput
        style={styles.audienceInput}
        placeholder="Target audience (optional)"
        placeholderTextColor="#999"
        value={targetAudience}
        onChangeText={setTargetAudience}
      />

      {/* Vault Attachment Button */}
      <TouchableOpacity
        onPress={() => {
          console.log('🔵 [ReportGoalSetting] Vault button clicked');
          if (!requireVault('You have turned off data store. To upload files, please select or create a data store first. Your uploaded files will be stored in the data store for AI to use as context during generation.')) return;
          setShowInternalUploadModal(true);
        }}
        style={styles.vaultButton}
      >
        <Ionicons name="cloud-upload-outline" size={22} color="#EC4899" style={{ marginRight: 8 }} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: '#EC4899', marginBottom: 2 }}>
            Upload Project Files to Data Store
          </Text>
          <Text style={{ fontSize: 11, color: '#DB2777', lineHeight: 14 }}>
            AI will remember your files as context for better reports
          </Text>
        </View>
      </TouchableOpacity>

      {/* Section/Page Count Selector */}
      <View style={styles.sectionCountContainer}>
        <View style={styles.sectionCountHeader}>
          <Icon name="format-list-numbered" size={18} color="#2196F3" />
          <Text style={styles.sectionCountLabel}>Number of Pages/Sections</Text>
        </View>
        <Text style={styles.sectionCountHint}>
          How many sections should your report have? (3-100)
        </Text>
        <View style={styles.sectionCountRow}>
          {[5, 10, 20, 50].map(count => (
            <TouchableOpacity
              key={count}
              style={[
                styles.sectionCountQuickButton,
                sectionCount === count && styles.sectionCountQuickButtonActive
              ]}
              onPress={() => setSectionCount(count)}
            >
              <Text style={[
                styles.sectionCountQuickText,
                sectionCount === count && styles.sectionCountQuickTextActive
              ]}>
                {count}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={styles.sectionCountInputWrapper}>
            <TextInput
              style={styles.sectionCountInput}
              value={![5, 10, 20, 50].includes(sectionCount) ? String(sectionCount) : ''}
              onChangeText={(text) => {
                const num = parseInt(text) || 0;
                if (num >= 3 && num <= 100) {
                  setSectionCount(num);
                } else if (text === '') {
                  setSectionCount(10);
                }
              }}
              placeholder="Custom"
              placeholderTextColor="#999"
              keyboardType="numeric"
              maxLength={3}
            />
          </View>
        </View>
      </View>

      {/* Internet Search Toggle */}
      <TouchableOpacity
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          backgroundColor: useInternetSearch ? '#2196F315' : '#fafafa',
          borderWidth: 1,
          borderColor: useInternetSearch ? '#2196F360' : '#ddd',
          borderRadius: 12,
          padding: 14,
          marginBottom: 10,
          marginHorizontal: 4,
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
          color={useInternetSearch ? '#2196F3' : '#888'}
        />
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: '#333' }}>
            Pull Latest from Internet
          </Text>
          <Text style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
            Fetch web data and embed in data store before generating outline
          </Text>
        </View>
        <View style={{
          width: 22,
          height: 22,
          borderRadius: 6,
          borderWidth: 2,
          borderColor: useInternetSearch ? '#2196F3' : '#88888860',
          backgroundColor: useInternetSearch ? '#2196F3' : 'transparent',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          {useInternetSearch && <Ionicons name="checkmark" size={14} color="#fff" />}
        </View>
      </TouchableOpacity>

      {/* Generate Outline Button */}
      <TouchableOpacity
        style={[styles.primaryButton, isBreakingGoal && styles.buttonDisabled]}
        onPress={breakGoalIntoTodos}
        disabled={isBreakingGoal || !goal.trim()}
      >
        {isBreakingGoal ? (
          <>
            <ActivityIndicator size="small" color="#fff" />
            <Text style={styles.primaryButtonText}>Generating {sectionCount} sections...</Text>
          </>
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color="#fff" />
            <Text style={styles.primaryButtonText}>Generate Report Outline</Text>
            <Ionicons name="arrow-forward" size={18} color="#fff" />
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  // Render Step 2: Outline & Layouts
  const renderStep2 = () => (
    <ScrollView style={styles.stepContent} showsVerticalScrollIndicator={false}>
      <View style={styles.stepHeader}>
        <Text style={styles.stepTitle}>
          <Ionicons name="sparkles" size={20} color="#2196F3" /> Report Outline
        </Text>
        <Text style={styles.stepSubtitle}>
          Review and edit sections. AI will generate each page from your data store.
        </Text>
      </View>

      {/* Style Selection - Simple inline */}
      <View style={styles.styleSelectionRow}>
        <Text style={styles.styleSelectionLabel}>Document Style:</Text>
        <TouchableOpacity
          style={styles.styleSelectButton}
          onPress={() => setShowStylePicker(true)}
        >
          <View style={[styles.stylePreviewDot, { backgroundColor: REPORT_STYLES[selectedStyle]?.colors?.primary || '#8B5CF6' }]} />
          <Text style={styles.styleSelectValue}>
            {REPORT_STYLES[selectedStyle]?.name || 'AI Smart Style'}
          </Text>
          <Icon name="chevron-right" size={20} color="#666" />
        </TouchableOpacity>
      </View>

      {/* Streaming Progress Indicator */}
      {isStreaming && (
        <View style={styles.streamingProgress}>
          <ActivityIndicator size="small" color="#2196F3" />
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Text style={{ color: '#2196F3', fontWeight: '600', fontSize: 14 }}>
              {streamingProgress || `Generating ${sectionCount} sections...`}
            </Text>
            <Text style={{ color: '#666', fontSize: 12, marginTop: 2 }}>
              {todos.length > 0 ? `${todos.length}/${sectionCount} sections generated` : 'Sections will appear below as they are created'}
            </Text>
          </View>
        </View>
      )}

      {/* Section List Header */}
      {todos.length > 0 && (
        <View style={styles.sectionListHeader}>
          <Text style={styles.sectionListTitle}>
            <Icon name="format-list-numbered" size={18} color="#2196F3" /> Report Sections ({todos.length} pages)
          </Text>
        </View>
      )}

      {/* Section List */}
      <View style={styles.sectionListContainer}>
        {todos.map((todo, index) => {
          const isEditing = editingTodoId === todo.id;

          return (
            <View key={todo.id} style={styles.sectionItem}>
              {/* Section Header Row */}
              <View style={styles.sectionHeaderRow}>
                {/* Order Controls */}
                <View style={styles.sectionOrderControls}>
                  <TouchableOpacity
                    onPress={() => moveTodoUp(index)}
                    style={[styles.orderButton, index === 0 && styles.orderButtonDisabled]}
                    disabled={index === 0}
                  >
                    <Icon name="keyboard-arrow-up" size={18} color={index === 0 ? '#ccc' : '#666'} />
                  </TouchableOpacity>
                  <View style={styles.sectionNumber}>
                    <Text style={styles.sectionNumberText}>{index + 1}</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => moveTodoDown(index)}
                    style={[styles.orderButton, index === todos.length - 1 && styles.orderButtonDisabled]}
                    disabled={index === todos.length - 1}
                  >
                    <Icon name="keyboard-arrow-down" size={18} color={index === todos.length - 1 ? '#ccc' : '#666'} />
                  </TouchableOpacity>
                </View>

                {/* Section Content */}
                <View style={styles.sectionContent}>
                  {isEditing ? (
                    <>
                      <TextInput
                        style={styles.sectionTitleInput}
                        value={editingTitle}
                        onChangeText={setEditingTitle}
                        placeholder="Section title"
                        autoFocus
                      />
                      <TextInput
                        style={styles.sectionDescInput}
                        value={editingDescription}
                        onChangeText={setEditingDescription}
                        placeholder="What should this section cover?"
                        multiline
                      />
                    </>
                  ) : (
                    <TouchableOpacity onPress={() => startEditing(todo)} style={styles.sectionTextArea}>
                      <Text style={styles.sectionTitle}>{todo.title}</Text>
                      <Text style={styles.sectionDescription} numberOfLines={2}>{todo.description}</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {/* Actions */}
                <View style={styles.sectionActions}>
                  {isEditing ? (
                    <TouchableOpacity style={styles.saveButton} onPress={saveEditing}>
                      <Icon name="check" size={18} color="#4CAF50" />
                    </TouchableOpacity>
                  ) : (
                    <>
                      <TouchableOpacity style={styles.actionButton} onPress={() => startEditing(todo)}>
                        <Icon name="edit" size={16} color="#2196F3" />
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.actionButton} onPress={() => deleteTodo(todo.id)}>
                        <Icon name="delete" size={16} color="#f44336" />
                      </TouchableOpacity>
                    </>
                  )}
                </View>
              </View>
            </View>
          );
        })}
      </View>

      {/* Add Section Button */}
      {!isStreaming && (
        <TouchableOpacity style={styles.addSectionButton} onPress={addNewSection}>
          <Icon name="add" size={20} color="#2196F3" />
          <Text style={styles.addSectionText}>Add Section</Text>
        </TouchableOpacity>
      )}

      {/* Vault Selection Info */}
      {selectedFolders.length > 0 ? (
        <View style={styles.foldersInfo}>
          <Icon name="folder" size={16} color="#2196F3" />
          <Text style={styles.foldersInfoText}>
            Using {selectedFolders.length} folder(s) as source
          </Text>
        </View>
      ) : (
        <View style={styles.noFoldersWarning}>
          <Icon name="info" size={16} color="#666" />
          <Text style={styles.noFoldersText}>
            No vault selected - AI will generate without vault data
          </Text>
        </View>
      )}

      {/* Special Instructions */}
      <View style={styles.specialInstructionsContainer}>
        <View style={styles.specialInstructionsHeader}>
          <Icon name="lightbulb" size={16} color="#2196F3" />
          <Text style={styles.specialInstructionsLabel}>Special Instructions (Optional)</Text>
        </View>
        <Text style={styles.specialInstructionsHint}>
          Guide the AI: writing style, data to include, formatting, etc.
        </Text>
        <TextInput
          style={styles.specialInstructionsInput}
          placeholder="e.g., 'Formal tone, include statistics' or 'Focus on executive summary' or 'Use these numbers: Revenue $5M'"
          placeholderTextColor="#999"
          value={specialInstructions}
          onChangeText={setSpecialInstructions}
          multiline
          maxLength={2000}
        />
      </View>

      {/* Batch Progress UI */}
      {isGeneratingReport && batchProgress.totalSections > 0 && (
        <View style={styles.batchProgressContainer}>
          <View style={styles.progressBarOuter}>
            <View 
              style={[
                styles.progressBarInner, 
                { width: `${(batchProgress.completedSections / batchProgress.totalSections) * 100}%` }
              ]} 
            />
          </View>
          <View style={styles.progressTextRow}>
            <Text style={styles.progressMainText}>
              {batchProgress.completedSections} / {batchProgress.totalSections} pages generated
            </Text>
            <Text style={styles.progressBatchText}>
              Batch {batchProgress.currentBatch} of {batchProgress.totalBatches}
            </Text>
          </View>
          <Text style={styles.progressHint}>
            Processing {BATCH_SIZE} sections in parallel per batch
          </Text>
          
          {generatedPages.length > 0 && (
            <View style={styles.generatedPagesPreview}>
              <Text style={styles.generatedPagesTitle}>✓ Completed Sections:</Text>
              <ScrollView style={styles.generatedPagesList} nestedScrollEnabled>
                {generatedPages.map((page, idx) => (
                  <View key={page.id || idx} style={styles.generatedPageItem}>
                    <Icon name="check-circle" size={14} color="#4CAF50" />
                    <Text style={styles.generatedPageText} numberOfLines={1}>
                      {idx + 1}. {page.title}
                    </Text>
                  </View>
                ))}
              </ScrollView>
            </View>
          )}

          <TouchableOpacity style={styles.cancelButton} onPress={cancelGeneration}>
            <Icon name="cancel" size={16} color="#f44336" />
            <Text style={styles.cancelButtonText}>Cancel Generation</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Navigation Buttons */}
      <View style={styles.navigationButtons}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => setCurrentStep(1)}
        >
          <Ionicons name="arrow-back" size={18} color="#666" />
          <Text style={styles.backButtonText}>Back</Text>
        </TouchableOpacity>

        {!isGeneratingReport && (
          <TouchableOpacity
            style={[styles.generateButton, (todos.length === 0 || isStreaming) && styles.buttonDisabled]}
            onPress={generateReportFromVault}
            disabled={todos.length === 0 || isStreaming}
          >
            <Icon name="auto-stories" size={20} color="#fff" />
            <Text style={styles.generateButtonText}>
              Generate {todos.length} Page Report
            </Text>
          </TouchableOpacity>
        )}
      </View>
    </ScrollView>
  );

  return (
    <View style={styles.modalOverlay}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Icon name="auto-awesome" size={24} color="#2196F3" />
            <Text style={styles.title}>Document Creator</Text>
          </View>
          {renderStepIndicator()}
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Icon name="close" size={24} color="#666" />
          </TouchableOpacity>
        </View>

        {/* Step Content */}
        {currentStep === 1 ? renderStep1() : renderStep2()}

        {/* Internal Upload Modal */}
        <UnifiedUploadModal
          {...(uploadModalProps || {})}
          isVisible={showInternalUploadModal}
          onClose={() => setShowInternalUploadModal(false)}
          theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
        />

        {/* Style Picker Modal */}
        <ReportStylePicker
          visible={showStylePicker}
          onClose={() => setShowStylePicker(false)}
          onSelectStyle={(styleId) => {
            setSelectedStyle(styleId);
            setShowStylePicker(false);
          }}
          currentStyle={selectedStyle}
          theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
        />

        {/* Internal Vault Modal */}
        {vaultModalProps && (
          <VaultRequiredModal
            {...vaultModalProps}
            theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
          />
        )}

        {/* Vault Needed Modal - shown when user tries internet/upload with vault off */}
        <VaultRequiredModal
          visible={showVaultNeededModal}
          onClose={() => setShowVaultNeededModal(false)}
          onSelectVault={(vault) => { onSelectFolder(vault.unique_id || vault.id); setShowVaultNeededModal(false); }}
          onCreateVault={() => { setShowVaultNeededModal(false); onCreateVault?.(); }}
          folders={folders}
          theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
          message={vaultNeededMessage}
        />

        {/* Upload Progress Popup - Rendered inside modal so it's visible above overlay */}
        <UploadProgressPopup
          visible={uploadModalProps?.enhancedProgress && uploadModalProps.enhancedProgress.size > 0}
          enhancedProgress={uploadModalProps?.enhancedProgress}
          theme={{ primary: '#2196F3', background: '#fff', text: '#333', surface: '#fafafa', border: '#ddd', textSecondary: '#888' }}
          onClose={() => {}}
        />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  modalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000
  },
  container: {
    width: '98%',
    maxWidth: 1000, // Larger max width for better previews
    height: '98%',
    maxHeight: SCREEN_HEIGHT * 0.98,
    backgroundColor: '#fff',
    borderRadius: 16,
    overflow: 'hidden'
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
    backgroundColor: '#fafafa'
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333'
  },
  closeButton: {
    padding: 4
  },
  
  // Step Indicator
  stepIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    maxWidth: 200,
  },
  stepDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#e0e0e0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepDotActive: {
    backgroundColor: '#2196F3',
  },
  stepDotCurrent: {
    borderWidth: 3,
    borderColor: '#1565C0',
  },
  stepDotText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
  },
  stepDotTextActive: {
    color: '#fff',
  },
  stepLine: {
    width: 40,
    height: 3,
    backgroundColor: '#e0e0e0',
    marginHorizontal: 8,
  },
  stepLineActive: {
    backgroundColor: '#2196F3',
  },

  // Step Content
  stepContent: {
    flex: 1,
    padding: 24,
  },
  stepHeader: {
    marginBottom: 20,
  },
  stepTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#333',
    marginBottom: 8,
  },
  stepSubtitle: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
  },

  // Goal Input (Step 1)
  goalInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 12,
    padding: 16,
    fontSize: 15,
    minHeight: 140,
    textAlignVertical: 'top',
    color: '#333',
    backgroundColor: '#fafafa',
    marginBottom: 16,
  },
  typeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  typeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: '#f5f5f5',
    gap: 6
  },
  typeButtonActive: {
    backgroundColor: '#2196F3'
  },
  typeButtonText: {
    fontSize: 13,
    color: '#666'
  },
  typeButtonTextActive: {
    color: '#fff'
  },
  audienceInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    marginBottom: 16,
    color: '#333'
  },
  vaultButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FDF2F8',
    borderColor: '#EC4899',
    borderWidth: 2,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  
  // Section Count
  sectionCountContainer: {
    marginBottom: 20,
    padding: 16,
    backgroundColor: '#f0f7ff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#bbdefb'
  },
  sectionCountHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6
  },
  sectionCountLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1976D2'
  },
  sectionCountHint: {
    fontSize: 12,
    color: '#666',
    marginBottom: 12
  },
  sectionCountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap'
  },
  sectionCountQuickButton: {
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ddd',
    minWidth: 56,
    alignItems: 'center'
  },
  sectionCountQuickButtonActive: {
    backgroundColor: '#2196F3',
    borderColor: '#2196F3'
  },
  sectionCountQuickText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#666'
  },
  sectionCountQuickTextActive: {
    color: '#fff'
  },
  sectionCountInputWrapper: {
    flex: 1,
    minWidth: 90
  },
  sectionCountInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#333',
    backgroundColor: '#fff',
    textAlign: 'center'
  },

  // Primary Button
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2196F3',
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 8,
    gap: 10,
  },
  primaryButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600'
  },
  buttonDisabled: {
    opacity: 0.6
  },

  // Streaming Progress
  streamingProgress: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#e3f2fd',
    borderRadius: 12,
    marginBottom: 16,
  },

  // Section List (Step 2)
  sectionListHeader: {
    marginTop: 16,
    marginBottom: 12,
  },
  sectionListTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  sectionListHint: {
    fontSize: 12,
    color: '#888',
  },
  sectionListContainer: {
    gap: 12,
    marginBottom: 16,
  },
  sectionItem: {
    backgroundColor: '#f8f9fa',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e9ecef',
    overflow: 'hidden',
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    padding: 14,
    gap: 12,
  },
  sectionOrderControls: {
    alignItems: 'center',
    gap: 4,
  },
  orderButton: {
    padding: 2
  },
  orderButtonDisabled: {
    opacity: 0.3
  },
  sectionNumber: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#2196F3',
    justifyContent: 'center',
    alignItems: 'center'
  },
  sectionNumberText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 13
  },
  sectionContent: {
    flex: 1,
  },
  sectionTextArea: {
    flex: 1
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4
  },
  sectionDescription: {
    fontSize: 13,
    color: '#666',
    lineHeight: 18
  },
  sectionTitleInput: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    borderBottomWidth: 2,
    borderBottomColor: '#2196F3',
    paddingVertical: 6,
    marginBottom: 10
  },
  sectionDescInput: {
    fontSize: 13,
    color: '#666',
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 10,
    minHeight: 70,
    textAlignVertical: 'top',
    backgroundColor: '#fff',
  },
  sectionActions: {
    flexDirection: 'row',
    gap: 8
  },
  actionButton: {
    padding: 8,
    borderRadius: 8,
    backgroundColor: '#fff',
  },
  saveButton: {
    padding: 8,
    backgroundColor: '#E8F5E9',
    borderRadius: 8
  },

  // Add Section Button
  addSectionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: '#2196F3',
    borderRadius: 12,
    paddingVertical: 14,
    marginBottom: 20,
    gap: 8
  },
  addSectionText: {
    color: '#2196F3',
    fontSize: 14,
    fontWeight: '600'
  },

  // Advanced Setup
  advancedSetupToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#f8f9fa',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e9ecef',
    marginBottom: 16,
  },
  advancedSetupToggleActive: {
    backgroundColor: '#e3f2fd',
    borderColor: '#2196F3',
  },
  advancedSetupContent: {
    backgroundColor: '#fafafa',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e9ecef',
    padding: 20,
    marginBottom: 16,
  },
  advancedSection: {
    marginBottom: 20,
  },
  advancedSectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 12,
  },

  // Style Selection Row (simple inline version)
  styleSelectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#e9ecef',
  },
  styleSelectionLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#666',
    marginRight: 12,
  },

  // Style Select Button
  styleSelectButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e9ecef',
    gap: 12,
  },
  stylePreviewDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  styleSelectTextArea: {
    flex: 1,
  },
  styleSelectLabel: {
    fontSize: 11,
    color: '#888',
    textTransform: 'uppercase',
    marginBottom: 2,
  },
  styleSelectValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
  },

  // Vault Info
  foldersInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E3F2FD',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    marginBottom: 16,
    gap: 10
  },
  foldersInfoText: {
    color: '#1976D2',
    fontSize: 14
  },
  noFoldersWarning: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF3E0',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    marginBottom: 16,
    gap: 10
  },
  noFoldersText: {
    color: '#F57C00',
    fontSize: 14
  },

  // Special Instructions
  specialInstructionsContainer: {
    marginBottom: 20,
    padding: 16,
    backgroundColor: '#f8f9fa',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e9ecef'
  },
  specialInstructionsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6
  },
  specialInstructionsLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333'
  },
  specialInstructionsHint: {
    fontSize: 12,
    color: '#888',
    marginBottom: 10
  },
  specialInstructionsInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    padding: 12,
    fontSize: 14,
    minHeight: 80,
    maxHeight: 120,
    textAlignVertical: 'top',
    color: '#333',
    backgroundColor: '#fff'
  },

  // Batch Progress
  batchProgressContainer: {
    backgroundColor: '#e8f5e9',
    borderRadius: 12,
    padding: 18,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#c8e6c9'
  },
  progressBarOuter: {
    height: 14,
    backgroundColor: '#c8e6c9',
    borderRadius: 7,
    overflow: 'hidden',
    marginBottom: 12
  },
  progressBarInner: {
    height: '100%',
    backgroundColor: '#4CAF50',
    borderRadius: 7
  },
  progressTextRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6
  },
  progressMainText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#2E7D32'
  },
  progressBatchText: {
    fontSize: 12,
    color: '#666'
  },
  progressHint: {
    fontSize: 12,
    color: '#888',
    marginBottom: 14
  },
  generatedPagesPreview: {
    marginTop: 10,
    maxHeight: 160
  },
  generatedPagesTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#4CAF50',
    marginBottom: 8
  },
  generatedPagesList: {
    maxHeight: 130
  },
  generatedPageItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 4
  },
  generatedPageText: {
    fontSize: 13,
    color: '#333',
    flex: 1
  },
  cancelButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#c8e6c9',
    gap: 8
  },
  cancelButtonText: {
    color: '#f44336',
    fontSize: 14,
    fontWeight: '500'
  },

  // Navigation Buttons
  navigationButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#eee',
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ddd',
    gap: 8,
  },
  backButtonText: {
    fontSize: 14,
    color: '#666',
    fontWeight: '500',
  },
  generateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#4CAF50',
    paddingVertical: 14,
    paddingHorizontal: 24,
    borderRadius: 12,
    gap: 10
  },
  generateButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600'
  },
});

export default ReportGoalSetting;
