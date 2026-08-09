// AIAssistantPanel.js - AI-powered assistance for report writing
import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  TextInput,
  ActivityIndicator,
  Alert,
  Platform
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import authService from '../../services/authService';

const AIAssistantPanel = ({
  currentPage,
  pages,
  reportMetadata,
  onContentSuggestion,
  onPageSuggestion,
  theme,
  apiConfig, // API configuration from Citra-Service
  userDeviceId, // User device ID for API calls
  getCurrentPageContent, // Function to get the latest content from editor
  persona, // User persona for legal search
  // Data source toggles from header (controlled by parent)
  useUploadedData,
  selectedFolders = [], // Selected vault folders for data retrieval
  // NEW: Context-aware features
  contextManager = null, // Document context manager
  documentProgress = null, // Current document progress
  onContextAction = null, // Handler for context-aware actions
  reportGoal = null // Report goal information
}) => {
  const [activeTab, setActiveTab] = useState('expand'); // 'expand', 'review', 'suggest'
  const [aiInput, setAiInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [assistantHistory, setAssistantHistory] = useState([]);
  const [suggestions, setSuggestions] = useState([]);

  const scrollViewRef = useRef(null);

  // Build context-aware prompts
  const buildContextPrompt = useCallback((userInput, type) => {
    const currentPageContent = currentPage?.content || '';
    const pageTitle = currentPage?.title || 'Untitled Page';
    const reportGoal = reportMetadata.overall_goal || 'General report';
    const currentPageIndex = pages.findIndex(p => p.id === currentPage?.id) + 1;
    const totalPages = pages.length;

    // Get summary of previous pages
    const previousPages = pages.slice(0, currentPageIndex - 1);
    const previousSummary = previousPages.map(p =>
      `Page ${p.order}: ${p.title} (${p.wordCount} words)`
    ).join('\n');

    const baseContext = `
Report Goal: ${reportGoal}
Current Page: ${currentPageIndex} of ${totalPages}
Page Title: ${pageTitle}
Previous Pages Summary:
${previousSummary}

Current Page Content:
${currentPageContent}
`;

    switch (type) {
      case 'expand':
        return `${baseContext}

User Request: ${userInput}

Please expand the content based on the user's request. Maintain coherence with the overall report goal and previous pages. Write in a professional tone and provide well-structured content.`;

      case 'review':
        return `${baseContext}

Please review the current page content and provide suggestions for:
1. Grammar and style improvements
2. Clarity and readability
3. Coherence with the overall report structure
4. Content gaps or areas that need expansion

User's specific request: ${userInput}`;

      case 'suggest':
        return `${baseContext}

Based on the report goal and current progress, suggest:
1. What topics should be covered in the next pages
2. How to improve the current page
3. Content ideas that would strengthen the overall report

User's question: ${userInput}`;

      default:
        return `${baseContext}\n\nUser: ${userInput}`;
    }
  }, [currentPage, pages, reportMetadata]);

  // Build context-aware prompts with specific content
  const buildContextPromptWithContent = useCallback((userInput, type, specificContent) => {
    const pageTitle = currentPage?.title || 'Untitled Page';
    const reportGoal = reportMetadata.overall_goal || 'General report';
    const currentPageIndex = pages.findIndex(p => p.id === currentPage?.id) + 1;
    const totalPages = pages.length;

    // Get summary of previous pages
    const previousPages = pages.slice(0, currentPageIndex - 1);
    const previousSummary = previousPages.map(p =>
      `Page ${p.order}: ${p.title} (${p.wordCount} words)`
    ).join('\n');

    const baseContext = `
Report Goal: ${reportGoal}
Current Page: ${currentPageIndex} of ${totalPages}
Page Title: ${pageTitle}
Previous Pages Summary:
${previousSummary}

Current Page Content:
${specificContent}
`;

    switch (type) {
      case 'expand':
        return `${baseContext}

User Request: ${userInput}

Please expand the content based on the user's request. Maintain coherence with the overall report goal and previous pages. Write in a professional tone and provide well-structured content.`;

      case 'review':
        return `${baseContext}

Please review the current page content and provide suggestions for:
1. Grammar and style improvements
2. Clarity and readability
3. Coherence with the overall report structure
4. Content gaps or areas that need expansion

User's specific request: ${userInput}`;

      case 'suggest':
        return `${baseContext}

Based on the report goal and current progress, suggest:
1. What topics should be covered in the next pages
2. How to improve the current page
3. Content ideas that would strengthen the overall report

User's question: ${userInput}`;

      default:
        return `${baseContext}\n\nUser: ${userInput}`;
    }
  }, [currentPage, pages, reportMetadata]);

  // Mock AI responses for development
  const getMockAIResponse = useCallback((prompt, type) => {
    const responses = {
      expand: `Based on your request "${prompt}", here's expanded content:

This section builds upon the previous content by providing detailed analysis and insights. The key points to consider include:

• **Primary consideration**: This aspect is crucial for understanding the overall context
• **Secondary factors**: These elements support the main argument
• **Implementation details**: Practical steps for moving forward

The relationship between these elements demonstrates the complexity of the topic and requires careful consideration of multiple perspectives.`,

      review: `Here's my review of the current page:

**Strengths:**
• Clear structure and logical flow
• Good use of supporting examples
• Professional tone throughout

**Suggestions for improvement:**
• Consider adding more specific examples in paragraph 2
• The transition between sections could be smoother
• Some sentences could be more concise

**Grammar and style notes:**
• All grammar appears correct
• Consider varying sentence length for better readability`,

      suggest: `Based on your report progress, here are some suggestions:

**For the next page:**
• Detailed analysis of implementation strategies
• Case studies or examples
• Potential challenges and solutions

**For the current page:**
• Add a concluding paragraph that transitions to the next section
• Include more data or evidence to support your points

**Overall report structure:**
• Consider adding a methodology section
• Plan for a comprehensive conclusion that ties all pages together`
    };

    return responses[type] || 'I can help you with expanding content, reviewing your writing, or suggesting improvements. What would you like to work on?';
  }, []);

  // AI Service call - using dedicated composer endpoint
  const callAIService = useCallback(async (prompt, type = 'expand', apiConfig, userDeviceId, currentPageContent) => {
    try {
      setIsProcessing(true);

      // Composer always uses citra-ai-lite internally (no UI selection needed)
      const aiModel = 'citra-ai-lite';

      // Prepare composer-specific request payload
      const folderIds = useUploadedData && selectedFolders?.length > 0
        ? selectedFolders.map(f => f.id || f)
        : [];
      const composerPayload = {
        user_id: userDeviceId,
        query: prompt,
        ai_model: aiModel,
        context_type: type, // expand, review, suggest
        current_content: currentPageContent || '',
        report_metadata: {
          overall_goal: reportMetadata.overall_goal || 'General report',
          title: reportMetadata.title || 'Untitled Report',
          current_page_title: currentPage?.title || 'Untitled Page',
          page_info: (() => {
            const currentPageIndex = pages.findIndex(p => p.id === currentPage?.id) + 1;
            const totalPages = pages.length;
            return `Page ${currentPageIndex} of ${totalPages}`;
          })()
        },
        // User preference flags
        use_personal_data: useUploadedData,
        include_supplementary: useUploadedData && folderIds.length > 0,
        folder_ids: folderIds,
        persona_data: persona || null
      };

      console.log('🎨 [COMPOSER_AI] Calling dedicated composer endpoint:', {
        type,
        currentContentLength: currentPageContent?.length || 0,
        deviceId: userDeviceId,
        endpoint: apiConfig.COMPOSER_QUERY_URL,
        aiModel,
        dataFlags: {
          personalData: useUploadedData
        }
      });

      // Call dedicated composer endpoint
      const response = await authService.authenticatedFetch(`${apiConfig.COMPOSER_QUERY_URL}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(composerPayload)
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('🎨 [COMPOSER_AI] API request failed:', response.status, errorText);
        throw new Error(`Composer service request failed: ${response.status} - ${errorText}`);
      }

      const result = await response.json();
      console.log('🎨 [COMPOSER_AI] Received response from composer service:', {
        responseLength: result.response?.length || 0,
        processingTime: result.processing_time
      });

      // Extract the AI response
      const aiResponse = result.response || 'No response received';
      return aiResponse;
    } catch (error) {
      console.error('🎨 [COMPOSER_AI] Service error:', error);
      // Fallback to mock response for development
      console.log('🎨 [COMPOSER_AI] Using fallback mock response');
      return getMockAIResponse(prompt, type);
    } finally {
      setIsProcessing(false);
    }
  }, [currentPage, pages, reportMetadata, useUploadedData, selectedFolders, getMockAIResponse]);

  // Handle AI assistance
  const handleAIAssist = useCallback(async () => {
    if (!aiInput.trim()) {
      Alert.alert('Input Required', 'Please enter your request or question.');
      return;
    }

    // Validate required props
    if (!apiConfig || !userDeviceId) {
      console.error('🤖 [AI_ASSISTANT] Missing required props: apiConfig or userDeviceId');
      Alert.alert('Configuration Error', 'AI Assistant is not properly configured. Please check your setup.');
      return;
    }

    const assistantMessage = {
      id: Date.now(),
      type: activeTab,
      input: aiInput,
      timestamp: new Date().toISOString()
    };

    try {
      console.log('🤖 [AI_ASSISTANT] Processing request:', {
        type: activeTab,
        inputLength: aiInput.length,
        currentPageTitle: currentPage?.title || 'No page selected'
      });

      // Get the latest content from editor if function is available
      const latestContent = getCurrentPageContent ? getCurrentPageContent() : (currentPage?.content || '');

      console.log('🤖 [AI_ASSISTANT] Using content:', {
        hasGetCurrentPageContent: !!getCurrentPageContent,
        contentLength: latestContent.length,
        isLatestContent: latestContent !== (currentPage?.content || '')
      });

      const response = await callAIService(aiInput, activeTab, apiConfig, userDeviceId, latestContent);

      const updatedMessage = {
        ...assistantMessage,
        response,
        status: 'completed'
      };

      setAssistantHistory(prev => [...prev, updatedMessage]);

      // Auto-scroll to bottom
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 100);

      // Clear input
      setAiInput('');

      // If it's an expand request, offer to apply the content
      if (activeTab === 'expand' && response && response.trim()) {
        Alert.alert(
          'Apply Changes?',
          'Would you like to apply this expanded content to your page?',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Apply',
              onPress: () => {
                if (onContentSuggestion) {
                  const currentContent = currentPage?.content || '';
                  const newContent = currentContent + '\n\n' + response;
                  onContentSuggestion(newContent);
                }
              }
            }
          ]
        );
      }

    } catch (error) {
      console.error('🤖 [AI_ASSISTANT] Error processing request:', error);
      const errorMessage = {
        ...assistantMessage,
        response: 'Sorry, I encountered an error. Please try again.',
        status: 'error'
      };

      setAssistantHistory(prev => [...prev, errorMessage]);
    }
  }, [aiInput, activeTab, callAIService, currentPage, onContentSuggestion, apiConfig, userDeviceId]);

  // Quick action buttons - Enhanced with context awareness
  const quickActions = {
    expand: [
      'Expand this section to support the document goal',
      'Add examples that strengthen the main argument',
      'Provide detailed analysis aligned with the purpose',
      'Create supporting content for key topics'
    ],
    review: [
      'Check alignment with document goal',
      'Review flow and coherence',
      'Improve professional tone',
      'Optimize for target audience'
    ],
    suggest: [
      'What should come next to achieve the goal?',
      'How can I better address key topics?',
      'Suggest content that advances the purpose',
      'Help me strengthen this section'
    ]
  };

  // Enhanced contextual quick actions based on document progress
  const getContextualActions = useCallback(() => {
    if (!documentProgress || !reportGoal) {
      return quickActions[activeTab];
    }

    const completion = documentProgress.overall_completion || 0;
    const missingElements = documentProgress.missing_elements || [];
    const nextPriorities = documentProgress.next_priorities || [];

    let contextualActions = [...quickActions[activeTab]];

    // Add contextual suggestions based on progress
    if (activeTab === 'suggest') {
      if (completion < 30) {
        contextualActions.unshift('Help me develop the main arguments');
      } else if (completion < 70) {
        contextualActions.unshift('Suggest content to reach the next milestone');
      } else {
        contextualActions.unshift('Help me strengthen the conclusion');
      }

      if (missingElements.length > 0) {
        contextualActions.push(`Address missing element: ${missingElements[0]}`);
      }

      if (nextPriorities.length > 0) {
        contextualActions.push(`Focus on: ${nextPriorities[0]}`);
      }
    }

    return contextualActions.slice(0, 6); // Limit to 6 actions
  }, [activeTab, documentProgress, reportGoal, quickActions]);

  const tabs = [
    { id: 'expand', label: 'Expand', icon: 'expand-outline' },
    { id: 'review', label: 'Review', icon: 'checkmark-circle-outline' },
    { id: 'suggest', label: 'Suggest', icon: 'bulb-outline' }
  ];
  // Handle Enter-to-send on web, Shift+Enter for newline
  const handleKeyPress = (e) => {
    if (Platform.OS === 'web') {
      const key = e?.nativeEvent?.key;
      if (key === 'Enter') {
        const shift = e?.shiftKey || e?.nativeEvent?.shiftKey;
        if (!shift && aiInput.trim() && !isProcessing) {
          e.preventDefault();
          e.stopPropagation();
          handleAIAssist();
        }
      }
    }
  };
  return (
    <View style={[styles.container, { backgroundColor: theme.surface }]}>
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: theme.borderColor }]}>
        <View style={styles.headerLeft}>
          <Ionicons name="sparkles" size={20} color={theme.primary} />
          <Text style={[styles.headerTitle, { color: theme.text }]}>
            AI Assistant
          </Text>
        </View>
      </View>

      {/* Tabs */}
      <View style={[styles.tabsContainer, { backgroundColor: theme.background }]}>
        {tabs.map(tab => (
          <TouchableOpacity
            key={tab.id}
            style={[
              styles.tab,
              activeTab === tab.id && { backgroundColor: theme.primary }
            ]}
            onPress={() => setActiveTab(tab.id)}
          >
            <Ionicons
              name={tab.icon}
              size={16}
              color={activeTab === tab.id ? theme.buttonText : theme.text}
            />
            <Text style={[
              styles.tabText,
              { color: activeTab === tab.id ? theme.buttonText : theme.text }
            ]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>



      {/* Content */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.content}
        contentContainerStyle={styles.contentContainer}
      >
        {/* Goal Progress Indicator */}
        {reportGoal && documentProgress && (
          <View style={[styles.goalProgressCard, {
            backgroundColor: theme.inputBackground,
            borderColor: theme.borderColor
          }]}>
            <View style={styles.goalProgressHeader}>
              <Text style={[styles.goalProgressTitle, { color: theme.text }]}>
                🎯 Goal Progress
              </Text>
              <Text style={[styles.goalProgressPercent, { color: theme.primary }]}>
                {Math.round(documentProgress.overall_completion || 0)}%
              </Text>
            </View>

            <View style={[styles.goalProgressBar, { backgroundColor: theme.borderColor }]}>
              <View
                style={[
                  styles.goalProgressFill,
                  {
                    width: `${documentProgress.overall_completion || 0}%`,
                    backgroundColor: theme.primary
                  }
                ]}
              />
            </View>

            <Text style={[styles.goalProgressText, { color: theme.placeholderText }]}>
              {reportGoal.purpose?.substring(0, 60)}...
            </Text>

            {documentProgress.next_priorities && documentProgress.next_priorities.length > 0 && (
              <Text style={[styles.nextPriorityText, { color: theme.text }]}>
                🎯 Next: {documentProgress.next_priorities[0]}
              </Text>
            )}
          </View>
        )}

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            Context-Aware Actions
          </Text>
          {getContextualActions().map((action, index) => (
            <TouchableOpacity
              key={index}
              style={[styles.quickActionButton, {
                backgroundColor: theme.inputBackground,
                borderColor: theme.borderColor
              }]}
              onPress={() => setAiInput(action)}
            >
              <Text style={[styles.quickActionText, { color: theme.text }]}>
                {action}
              </Text>
              <Ionicons name="arrow-forward" size={14} color={theme.placeholderText} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Assistant History */}
        {assistantHistory.length > 0 && (
          <View style={styles.historySection}>
            <Text style={[styles.sectionTitle, { color: theme.text }]}>
              Recent Assistance
            </Text>
            {assistantHistory.slice(-3).map((item) => (
              <View
                key={item.id}
                style={[styles.historyItem, {
                  backgroundColor: theme.inputBackground,
                  borderColor: theme.borderColor
                }]}
              >
                <View style={styles.historyHeader}>
                  <Text style={[styles.historyType, { color: theme.primary }]}>
                    {item.type.toUpperCase()}
                  </Text>
                  <Text style={[styles.historyTime, { color: theme.placeholderText }]}>
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </Text>
                </View>
                <Text style={[styles.historyInput, { color: theme.text }]}>
                  {item.input}
                </Text>
                {item.response && (
                  <Text style={[styles.historyResponse, { color: theme.placeholderText }]}>
                    {item.response.substring(0, 150)}...
                  </Text>
                )}
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Input Area */}
      <View style={[styles.inputContainer, {
        backgroundColor: theme.background,
        borderTopColor: theme.borderColor
      }]}>
        <TextInput
          style={[styles.textInput, {
            backgroundColor: theme.inputBackground,
            color: theme.text,
            borderColor: theme.borderColor
          }]}
          value={aiInput}
          onChangeText={setAiInput}
          placeholder={`Ask AI to ${activeTab} your content...`}
          placeholderTextColor={theme.placeholderText}
          multiline
          maxLength={500}
          onKeyPress={handleKeyPress}
        />
        <TouchableOpacity
          style={[styles.sendButton, {
            backgroundColor: aiInput.trim() ? theme.primary : theme.borderColor
          }]}
          onPress={handleAIAssist}
          disabled={!aiInput.trim() || isProcessing}
        >
          {isProcessing ? (
            <ActivityIndicator size="small" color={theme.buttonText} />
          ) : (
            <Ionicons
              name="send"
              size={20}
              color={aiInput.trim() ? theme.buttonText : theme.placeholderText}
            />
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = {
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  tabsContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 4,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    gap: 4,
  },
  tabText: {
    fontSize: 12,
    fontWeight: '500',
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    padding: 16,
    gap: 20,
  },
  quickActions: {
    gap: 8,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  quickActionButton: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  quickActionText: {
    fontSize: 13,
    flex: 1,
  },
  historySection: {
    gap: 8,
  },
  historyItem: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  historyType: {
    fontSize: 10,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  historyTime: {
    fontSize: 10,
  },
  historyInput: {
    fontSize: 12,
    fontWeight: '500',
  },
  historyResponse: {
    fontSize: 11,
    lineHeight: 16,
  },
  inputContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
    gap: 8,
    alignItems: 'flex-end',
  },
  textInput: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    maxHeight: 80,
    fontSize: 14,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  // New styles for context-aware features
  goalProgressCard: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 16,
  },
  goalProgressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  goalProgressTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  goalProgressPercent: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  goalProgressBar: {
    height: 4,
    borderRadius: 2,
    marginBottom: 8,
    overflow: 'hidden',
  },
  goalProgressFill: {
    height: '100%',
    borderRadius: 2,
  },
  goalProgressText: {
    fontSize: 12,
    lineHeight: 16,
    marginBottom: 4,
  },
  nextPriorityText: {
    fontSize: 11,
    fontWeight: '500',
    fontStyle: 'italic',
  },
};

export default AIAssistantPanel;
