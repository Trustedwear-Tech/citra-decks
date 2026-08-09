/**
 * UnifiedUploadModal.js
 * ======================
 * Single consolidated upload modal for all upload scenarios:
 * - HomeScreen (Preload)
 * - ChatScreen 
 * - Enterprise entity uploads
 * 
 * Features:
 * - Local device uploads (documents, images, audio, camera)
 * - Cloud app imports (Google Drive, OneDrive, SharePoint, Dropbox, Box, Slack, Confluence, Notion) — cloud sync disabled
 * - URL fetch imports
 * - Progress tracking sidebar
 * - Entity search for enterprise mode
 * 
 * This replaces: PreloadUploadModal.js, ChatUniversalUploadModal.js
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  ScrollView,
  Alert,
  Platform,
  ActivityIndicator,
  StyleSheet,
  TextInput,
  Dimensions,
  useWindowDimensions
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import ChatUploadBubble from './ChatUploadBubble';
import UploadSuccessToast from './UploadSuccessToast';
import DuplicateUploadToast from './DuplicateUploadToast';
import { fetchUploadLimits, formatLimitsForDisplay } from '../services/UploadLimitsService';

const UnifiedUploadModal = ({
  isVisible,
  onClose,
  theme,
  actions = {},
  onUploadStatusChange,
  enhancedProgress,
  selectedFolderIds = [],
  folders = [],
  // Modal title and mode
  modalTitle = "Upload Files",
  // Enterprise functionality
  showEntitySearch = false,
  selectedEntity = null,
  onEntitySelect = () => { },
  onEntitySearch = async () => [],
  isEnterpriseMode = false,
  // Toast props
  uploadSuccessToast = { visible: false },
  onCloseUploadSuccessToast = () => { },
  duplicateUploadToast = { visible: false },
  onCloseDuplicateUploadToast = () => { },
  // ModernAlert props
  showModernAlert = () => { },
  setModernAlertConfig = () => { },
  // Hide certain options
  hideAudioUpload = false,
  hideCameraUpload = false,
  // Auto-open cloud browser on mount
  autoOpenCloudBrowser = false,
  // Create Vault functionality
  onCreateVault = null,
  // Vault-scoped SaaS connections
  vaultId = null,
  vaultName = null,
  // User type for paid feature gating
  userType = 'free',
  // Inline view callbacks
  onPasteTextSubmit = null,
  onInternetIngestFetch = null,
  onInternetIngestEmbed = null,
}) => {
  const [uploadStatus, setUploadStatus] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(false);

  // Entity search state
  const [entitySearchText, setEntitySearchText] = useState('');
  const [entitySuggestions, setEntitySuggestions] = useState([]);
  const [isEntitySearching, setIsEntitySearching] = useState(false);
  const [showEntitySuggestions, setShowEntitySuggestions] = useState(false);

  // Document details state (only for entity uploads)
  const [documentDetails, setDocumentDetails] = useState('');
  const [documentDetailsError, setDocumentDetailsError] = useState(false);

  // Inline view state (paste text / internet ingest rendered inside this modal)
  const [activeInlineView, setActiveInlineView] = useState(null); // null | 'pasteText' | 'internetIngest'
  // Paste Text inline state
  const [ptTopic, setPtTopic] = useState('');
  const [ptContent, setPtContent] = useState('');
  const [ptLoading, setPtLoading] = useState(false);
  // Internet Ingest inline state
  const [iiQuery, setIiQuery] = useState('');
  const [iiPhase, setIiPhase] = useState('query'); // 'query' | 'review'
  const [iiResultText, setIiResultText] = useState('');
  const [iiTopic, setIiTopic] = useState('');
  const [iiFetching, setIiFetching] = useState(false);
  const [iiEmbedding, setIiEmbedding] = useState(false);

  // File limits info expanded state
  const [showFileLimits, setShowFileLimits] = useState(false);

  // Paid feature modal state
  const [showPaidFeatureModal, setShowPaidFeatureModal] = useState(false);
  const [paidFeatureTitle, setPaidFeatureTitle] = useState('');

  // Upload limits from API (fetched on mount)
  const [uploadLimits, setUploadLimits] = useState(null);
  const [limitsLoading, setLimitsLoading] = useState(false);

  // Screen dimensions to detect mobile web
  const { width } = useWindowDimensions();
  const isMobileWeb = Platform.OS === 'web' && width < 768;

  // Derive vault context from selected folders if not explicitly provided
  const effectiveVaultId = vaultId || (selectedFolderIds.length === 1 ? selectedFolderIds[0] : null);
  const effectiveVaultName = vaultName || folders.find(f => f.id === effectiveVaultId)?.name;

  // Check if multiple folders are selected (only for personal uploads, not enterprise)
  const hasMultipleFoldersSelected = !isEnterpriseMode && selectedFolderIds.length > 1;
  const multipleFolderWarning = hasMultipleFoldersSelected ?
    `Multiple drives selected (${selectedFolderIds.length}). Please choose a single drive before uploading.` :
    null;

  // Reset state when modal is closed or opened
  useEffect(() => {
    if (!isVisible) {
      setIsUploading(false);
      setUploadStatus(null);
      setUploadProgress(0);
      setActionInProgress(false);
      // Reset inline views
      setActiveInlineView(null);
      setPtTopic(''); setPtContent(''); setPtLoading(false);
      setIiQuery(''); setIiPhase('query'); setIiResultText(''); setIiTopic('');
      setIiFetching(false); setIiEmbedding(false);
    } else {
      setIsUploading(false);
      setUploadStatus(null);
      setUploadProgress(0);
      setActionInProgress(false);
      setActiveInlineView(null);
    }
  }, [isVisible]);

  // Fetch upload limits when modal becomes visible
  useEffect(() => {
    if (isVisible && !uploadLimits && !limitsLoading) {
      setLimitsLoading(true);
      fetchUploadLimits()
        .then(limits => {
          setUploadLimits(limits);
          setLimitsLoading(false);
        })
        .catch(error => {
          console.warn('[UnifiedUploadModal] Failed to fetch limits:', error);
          setLimitsLoading(false);
        });
    }
  }, [isVisible, uploadLimits, limitsLoading]);

  // Function to reset all upload states
  const resetUploadState = useCallback(() => {
    console.log('Resetting upload state');
    setIsUploading(false);
    setUploadStatus(null);
    setUploadProgress(0);
    setActionInProgress(false);
    if (onUploadStatusChange) {
      onUploadStatusChange({
        isUploading: false,
        status: null,
        progress: 0
      });
    }
  }, [onUploadStatusChange]);

  // Protected action handler with minimal debounce
  const handleProtectedAction = useCallback(async (action) => {
    // Guard: Ensure action is a function
    if (typeof action !== 'function') {
      console.warn('[UnifiedUploadModal] Action is not a function, ignoring');
      return;
    }

    // Check for multiple folder selection before any upload action (skip for enterprise mode)
    if (!isEnterpriseMode && hasMultipleFoldersSelected) {
      console.log('Multiple folders selected, blocking upload action');
      return;
    }

    // Validate entity selection for entity uploads
    if (showEntitySearch && (!selectedEntity || !selectedEntity.entity_id)) {
      setModernAlertConfig({
        title: 'Entity Selection Required',
        message: 'Please search and select an entity (client/matter) before uploading documents.',
        type: 'error',
        buttons: [{ text: 'OK', onPress: () => showModernAlert(false) }]
      });
      showModernAlert(true);
      return;
    }

    // Validate document details for entity uploads
    if (showEntitySearch && (!documentDetails || !documentDetails.trim())) {
      setDocumentDetailsError(true);
      setModernAlertConfig({
        title: 'Document Details Required',
        message: 'Please enter the document details before uploading to an entity.',
        type: 'error',
        buttons: [{ text: 'OK', onPress: () => showModernAlert(false) }]
      });
      showModernAlert(true);
      return;
    }

    // Minimal debounce - only prevent rapid duplicate clicks (200ms)
    if (actionInProgress) {
      console.log('Action already in progress, ignoring rapid duplicate call');
      return;
    }

    setActionInProgress(true);

    try {
      // Pass document details to the action if it's an entity upload
      let result;
      if (showEntitySearch && documentDetails && documentDetails.trim()) {
        result = await action(documentDetails.trim());
      } else {
        result = await action();
      }
      // Close the modal after successfully triggering the upload action
      // Don't close if the action was canceled (e.g., user dismissed file picker)
      if (!result || !result.canceled) {
        onClose();
      }
    } catch (error) {
      console.error('Protected action error:', error);
    } finally {
      setTimeout(() => {
        setActionInProgress(false);
      }, 200);
    }
  }, [actionInProgress, hasMultipleFoldersSelected, isEnterpriseMode, showEntitySearch, selectedEntity, documentDetails, setModernAlertConfig, showModernAlert, onClose]);

  // Entity search functionality
  const handleEntitySearch = useCallback(async (searchText) => {
    if (!searchText.trim()) {
      setEntitySuggestions([]);
      setShowEntitySuggestions(false);
      return;
    }

    setIsEntitySearching(true);
    try {
      const results = await onEntitySearch(searchText);
      setEntitySuggestions(results);
      setShowEntitySuggestions(results.length > 0);
    } catch (error) {
      console.error('Entity search error:', error);
      setEntitySuggestions([]);
      setShowEntitySuggestions(false);
    } finally {
      setIsEntitySearching(false);
    }
  }, [onEntitySearch]);

  const handleEntitySearchTextChange = useCallback((text) => {
    setEntitySearchText(text);

    const timeout = setTimeout(() => {
      handleEntitySearch(text);
    }, 300);

    return () => clearTimeout(timeout);
  }, [handleEntitySearch]);

  const handleEntitySelect = useCallback((entity) => {
    onEntitySelect(entity);
    setEntitySearchText(entity.entity_name);
    setShowEntitySuggestions(false);
  }, [onEntitySelect]);

  const handleCloseWithConfirmation = useCallback(() => {
    const isActivelyUploading = isUploading &&
      uploadStatus &&
      uploadProgress > 0 &&
      !uploadStatus.includes('completed') &&
      !uploadStatus.includes('successfully') &&
      !uploadStatus.includes('Error') &&
      !uploadStatus.includes('failed') &&
      !uploadStatus.includes('canceled');

    if (isActivelyUploading) {
      if (Platform.OS === 'web') {
        if (confirm('Upload in progress. Are you sure you want to close?')) {
          resetUploadState();
          onClose();
        }
      } else {
        Alert.alert(
          'Upload in Progress',
          'Are you sure you want to close? The upload will be canceled.',
          [
            { text: 'Continue Upload', style: 'cancel' },
            {
              text: 'Close',
              style: 'destructive',
              onPress: () => {
                resetUploadState();
                onClose();
              }
            }
          ]
        );
      }
    } else {
      onClose();
    }
  }, [isUploading, uploadStatus, uploadProgress, resetUploadState, onClose]);

  // Define categorized data sources for web
  const DATA_SOURCE_CATEGORIES = [
    {
      id: 'upload',
      title: 'Upload to Vault',
      icon: 'cloud-upload',
      color: '#3b82f6',
      options: [
        {
          id: 'documents',
          title: 'Documents',
          icon: 'document-text',
          description: 'PDF, Excel, CSV, Word, TXT, HTML, JSON',
          action: actions.pickDocument,
        },
        {
          id: 'images',
          title: 'Images',
          icon: 'image',
          description: 'JPG, PNG, GIF, etc.',
          action: actions.pickImage,
        },
        {
          id: 'documents_ocr',
          title: 'OCR Scan',
          icon: 'scan',
          description: 'Scanned docs (Max 10 pages)',
          action: actions.pickDocumentOCR,
        },
        {
          id: 'audio',
          title: 'Audio',
          icon: 'musical-notes',
          description: 'MP3, WAV, M4A, etc.',
          action: actions.pickAudioFile,
          hidden: hideAudioUpload || isEnterpriseMode,
        },
        {
          id: 'pasteText',
          title: 'Paste Text',
          icon: 'clipboard',
          description: 'Paste or type text to embed in vault',
          action: () => setActiveInlineView('pasteText'),
          isInlineView: true,
        },
      ],
    },
    {
      id: 'internet',
      title: 'Internet',
      icon: 'globe',
      color: '#06b6d4',
      options: [
        {
          id: 'urlFetch',
          title: 'Import from URL',
          icon: 'link',
          description: 'Fetch content from web pages',
          action: actions.openURLFetchModal,
        },
        {
          id: 'internetIngest',
          title: 'Ingest from Internet',
          icon: 'search',
          description: 'AI fetches data from the web based on your query',
          action: () => setActiveInlineView('internetIngest'),
          isInlineView: true,
        },
      ],
    },
  ];

  // Legacy upload options for mobile
  const uploadOptions = [
    {
      id: 'documents',
      title: 'Upload Documents',
      icon: 'document-text',
      description: 'Upload PDF, Excel, CSV, Word, TXT, HTML, JSON files',
      action: actions.pickDocument,
      category: 'device',
    },
    {
      id: 'images',
      title: 'Upload Images',
      icon: 'image',
      description: 'Upload image files (JPG, PNG, GIF, etc.)',
      action: actions.pickImage,
      category: 'device',
    },
    {
      id: 'documents_ocr',
      title: 'OCR Document Upload',
      icon: 'scan',
      description: 'Upload scanned documents for OCR text extraction (Max 10 pages)',
      action: actions.pickDocumentOCR,
      category: 'device',
    },
    {
      id: 'audio',
      title: 'Upload Audio Files',
      icon: 'musical-notes',
      description: 'Upload audio files (MP3, WAV, M4A, etc.)',
      action: actions.pickAudioFile,
      hidden: hideAudioUpload || isEnterpriseMode,
      category: 'device',
    },
    {
      id: 'camera',
      title: 'Take Photo',
      icon: 'camera',
      description: 'Take a photo to add to your Vault',
      action: actions.takePhoto,
      hidden: hideCameraUpload || Platform.OS === 'web',
      category: 'device',
    },
    {
      id: 'pasteText',
      title: 'Paste Text',
      icon: 'clipboard',
      description: 'Paste or type text to embed in vault',
      action: () => setActiveInlineView('pasteText'),
      isInlineView: true,
      category: 'other',
    },
    {
      id: 'urlFetch',
      title: 'Import from URL',
      icon: 'link',
      description: 'Fetch and import content from a web page URL',
      action: actions.openURLFetchModal,
      category: 'other',
    },
    {
      id: 'internetIngest',
      title: 'Ingest from Internet',
      icon: 'search',
      description: 'AI fetches data from the web based on your query',
      action: () => setActiveInlineView('internetIngest'),
      isInlineView: true,
      category: 'other',
    },
  ];

  // Render category section with header and grid of options (Web only)
  const renderCategory = (category) => {
    if (category.hidden) return null;
    const visibleOptions = category.options.filter(opt => !opt.hidden);
    if (visibleOptions.length === 0) return null;

    return (
      <View key={category.id} style={styles.categorySection}>
        {/* Category Header */}
        <View style={[styles.categoryHeader, { borderLeftColor: category.color }]}>
          <View style={[styles.categoryIconContainer, { backgroundColor: category.color + '15' }]}>
            <Ionicons name={category.icon} size={18} color={category.color} />
          </View>
          <Text style={[styles.categoryTitle, { color: theme.text }]}>{category.title}</Text>
        </View>

        {/* Options Grid */}
        <View style={styles.categoryOptionsGrid}>
          {visibleOptions.map((option) => renderCategoryOptionCard(option, category.color))}
        </View>
      </View>
    );
  };

  // Render individual option card within a category (Web only)
  const renderCategoryOptionCard = (option, categoryColor) => {
    const isCloudOption = option.isCloudImport;
    const isDataConnection = option.isDataConnection;
    const needsVaultSelection = option.requiresVault && !effectiveVaultId;
    const isPaidGated = option.paidOnly && userType !== 'paid';

    return (
      <TouchableOpacity
        key={option.id}
        style={[
          styles.categoryOptionCard,
          {
            backgroundColor: theme.inputBackground,
            borderColor: isDataConnection ? '#f59e0b' : theme.borderColor,
            borderWidth: isDataConnection ? 2 : 1,
            opacity: (hasMultipleFoldersSelected && !isDataConnection) || needsVaultSelection ? 0.6 : 1
          }
        ]}
        onPress={() => {
          if (isPaidGated) {
            setPaidFeatureTitle(option.title);
            setShowPaidFeatureModal(true);
            return;
          }
          if (option.isDataConnection) {
            option.action?.();
          } else if (option.isInlineView) {
            option.action?.();
          } else {
            handleProtectedAction(option.action);
          }
        }}
        disabled={actionInProgress || (hasMultipleFoldersSelected && !isDataConnection)}
        activeOpacity={0.7}
      >
        <View style={[
          styles.categoryOptionIcon,
          { backgroundColor: categoryColor + '15' }
        ]}>
          <Ionicons
            name={option.icon}
            size={24}
            color={categoryColor}
          />
        </View>
        <Text style={[styles.categoryOptionTitle, { color: theme.text }]} numberOfLines={1}>
          {option.title}
        </Text>
        <Text style={[styles.categoryOptionDesc, { color: theme.placeholderText }]} numberOfLines={2}>
          {option.description}
        </Text>
        {/* Data connection badge - shows vault requirement hint */}
        {isDataConnection && !isPaidGated && (
          <View style={[styles.dataBadge, { backgroundColor: needsVaultSelection ? '#94a3b820' : '#f59e0b20' }]}>
            <Text style={[styles.dataBadgeText, { color: needsVaultSelection ? '#94a3b8' : '#f59e0b' }]}>
              {needsVaultSelection ? 'Select Vault' : 'Live Data'}
            </Text>
          </View>
        )}
        {/* Paid users only badge */}
        {isPaidGated && (
          <View style={[styles.dataBadge, { backgroundColor: '#FEF3C7' }]}>
            <Text style={[styles.dataBadgeText, { color: '#D97706' }]}>
              Paid users only
            </Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  // Render option card
  const renderOptionCard = (option) => {
    if (option.hidden) return null;

    return (
      <TouchableOpacity
        key={option.id}
        style={[
          styles.optionCard,
          {
            backgroundColor: theme.inputBackground,
            borderColor: theme.borderColor,
            borderWidth: 1,
            opacity: hasMultipleFoldersSelected ? 0.5 : 1
          }
        ]}
        onPress={() => {
          if (option.isInlineView) {
            option.action?.();
          } else {
            handleProtectedAction(option.action);
          }
        }}
        disabled={actionInProgress || hasMultipleFoldersSelected}
        activeOpacity={0.7}
      >
        <View style={styles.optionIconContainer}>
          <Ionicons
            name={option.icon}
            size={32}
            color={
              actionInProgress || hasMultipleFoldersSelected
                ? theme.placeholderText
                : theme.sendButton
            }
          />
        </View>
        <View style={styles.optionTextContainer}>
          <View style={styles.optionTitleRow}>
            <Text style={[
              styles.optionTitle,
              {
                color: actionInProgress || hasMultipleFoldersSelected
                  ? theme.placeholderText
                  : theme.text
              }
            ]}>
              {option.title}
            </Text>
            {option.id === 'documents' && enhancedProgress && enhancedProgress.size > 0 && (
              <View style={styles.queueIndicator}>
                <Text style={styles.queueIndicatorText}>
                  {enhancedProgress.size}
                </Text>
              </View>
            )}
          </View>
          <Text style={[styles.optionDescription, { color: theme.placeholderText }]}>
            {option.description}
          </Text>
        </View>
      </TouchableOpacity>
    );
  };

  // ─── Inline View Handlers ───
  const handleBackToCategories = useCallback(() => {
    setActiveInlineView(null);
    setPtTopic(''); setPtContent(''); setPtLoading(false);
    setIiQuery(''); setIiPhase('query'); setIiResultText(''); setIiTopic('');
    setIiFetching(false); setIiEmbedding(false);
  }, []);

  const handlePtSubmit = useCallback(async () => {
    if (!ptContent.trim() || !onPasteTextSubmit) return;
    setPtLoading(true);
    try {
      // Auto-generate title from first words of content if not provided
      const topic = ptTopic.trim() || ptContent.trim().split(/\s+/).slice(0, 6).join(' ');
      await onPasteTextSubmit(topic, ptContent.trim());
      // Success — reset and go back
      handleBackToCategories();
    } catch (e) {
      // Error alert handled by parent callback
      setPtLoading(false);
    }
  }, [ptTopic, ptContent, onPasteTextSubmit, handleBackToCategories]);

  const handleIiFetch = useCallback(async () => {
    if (!iiQuery.trim() || !onInternetIngestFetch) return;
    setIiFetching(true);
    try {
      const result = await onInternetIngestFetch(iiQuery.trim());
      if (result && result.text) {
        setIiResultText(result.text);
        setIiTopic(iiQuery.trim().length > 60 ? iiQuery.trim().substring(0, 60) + '...' : iiQuery.trim());
        setIiPhase('review');
      }
      setIiFetching(false);
    } catch (e) {
      setIiFetching(false);
    }
  }, [iiQuery, onInternetIngestFetch]);

  const handleIiEmbed = useCallback(async () => {
    if (!iiTopic.trim() || !iiResultText.trim() || !onInternetIngestEmbed) return;
    setIiEmbedding(true);
    try {
      await onInternetIngestEmbed(iiTopic.trim(), iiResultText.trim());
      // Success — reset and go back
      handleBackToCategories();
    } catch (e) {
      setIiEmbedding(false);
    }
  }, [iiTopic, iiResultText, onInternetIngestEmbed, handleBackToCategories]);

  const handleIiReFetch = useCallback(() => {
    setIiResultText('');
    setIiTopic('');
    setIiPhase('query');
  }, []);

  // ─── Inline View Renderers ───
  const ptWordCount = ptContent.trim() ? ptContent.trim().split(/\s+/).length : 0;
  const iiWordCount = iiResultText.trim() ? iiResultText.trim().split(/\s+/).length : 0;

  const renderPasteTextView = () => (
    <View>
      {/* Back button */}
      <TouchableOpacity onPress={handleBackToCategories} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
        <Ionicons name="arrow-back" size={20} color={theme.sendButton} />
        <Text style={{ color: theme.sendButton, marginLeft: 6, fontWeight: '600', fontSize: 14 }}>Back to upload options</Text>
      </TouchableOpacity>

      {/* Title */}
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
        <Ionicons name="clipboard" size={22} color={theme.sendButton} style={{ marginRight: 8 }} />
        <Text style={{ color: theme.text, fontSize: 18, fontWeight: '700' }}>Paste Text to Vault</Text>
      </View>
      <Text style={{ color: theme.placeholderText, marginBottom: 16, fontSize: 13, lineHeight: 18 }}>
        Paste or type text content to embed as a document in your vault. Useful for notes, research data, or any text content for AI-powered search and generation.
      </Text>

      {/* Document Title */}
      <Text style={{ color: theme.text, fontWeight: '600', marginBottom: 6 }}>Document Title <Text style={{ color: theme.placeholderText, fontWeight: '400', fontSize: 12 }}>(optional)</Text></Text>
      <TextInput
        style={{
          backgroundColor: theme.inputBackground,
          color: theme.text,
          borderColor: theme.borderColor,
          borderWidth: 1,
          borderRadius: 8,
          padding: 12,
          marginBottom: 16,
          height: 44,
          fontSize: 14,
        }}
        placeholder="e.g., Market Research Notes, Product Specs..."
        placeholderTextColor={theme.placeholderText}
        value={ptTopic}
        onChangeText={setPtTopic}
        maxLength={200}
        editable={!ptLoading}
      />

      {/* Text Content */}
      <Text style={{ color: theme.text, fontWeight: '600', marginBottom: 6 }}>Text Content *</Text>
      <TextInput
        style={{
          backgroundColor: theme.inputBackground,
          color: theme.text,
          borderColor: theme.borderColor,
          borderWidth: 1,
          borderRadius: 8,
          padding: 12,
          marginBottom: 8,
          minHeight: 180,
          maxHeight: 280,
          fontSize: 14,
          textAlignVertical: 'top',
        }}
        placeholder="Paste or type your text content here..."
        placeholderTextColor={theme.placeholderText}
        value={ptContent}
        onChangeText={setPtContent}
        multiline={true}
        editable={!ptLoading}
      />
      <Text style={{ color: theme.placeholderText, fontSize: 12, marginBottom: 16, textAlign: 'right' }}>{ptWordCount} words</Text>

      {/* Info */}
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: theme.inputBackground, padding: 10, borderRadius: 8 }}>
        <Ionicons name="information-circle" size={18} color={theme.sendButton} style={{ marginRight: 8 }} />
        <Text style={{ color: theme.placeholderText, flex: 1, fontSize: 12, lineHeight: 16 }}>
          Text will be processed, chunked, and embedded for AI-powered search and content generation.
        </Text>
      </View>

      {/* Submit Button */}
      <TouchableOpacity
        style={{
          backgroundColor: (!ptContent.trim() || ptLoading) ? theme.borderColor : theme.sendButton,
          justifyContent: 'center',
          alignItems: 'center',
          paddingVertical: 14,
          borderRadius: 8,
        }}
        onPress={handlePtSubmit}
        disabled={!ptContent.trim() || ptLoading}
      >
        {ptLoading ? (
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 8 }} />
            <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 16 }}>Embedding in Vault...</Text>
          </View>
        ) : (
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Ionicons name="cloud-upload" size={20} color="#FFFFFF" style={{ marginRight: 8 }} />
            <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 16 }}>Embed in Vault</Text>
          </View>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderInternetIngestView = () => (
    <View>
      {/* Back button */}
      <TouchableOpacity onPress={iiPhase === 'review' && !iiEmbedding ? handleIiReFetch : handleBackToCategories} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
        <Ionicons name="arrow-back" size={20} color="#06b6d4" />
        <Text style={{ color: '#06b6d4', marginLeft: 6, fontWeight: '600', fontSize: 14 }}>
          {iiPhase === 'review' ? 'Back to query' : 'Back to upload options'}
        </Text>
      </TouchableOpacity>

      {/* Title */}
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
        <Ionicons name="globe" size={22} color="#06b6d4" style={{ marginRight: 8 }} />
        <Text style={{ color: theme.text, fontSize: 18, fontWeight: '700' }}>
          {iiPhase === 'query' ? 'Ingest from Internet' : 'Review & Edit Content'}
        </Text>
      </View>

      {iiPhase === 'query' ? (
        <>
          <Text style={{ color: theme.placeholderText, marginBottom: 16, fontSize: 13, lineHeight: 18 }}>
            Describe what data you want to fetch from the internet. AI will search the web and compile comprehensive content for your vault.
          </Text>

          <Text style={{ color: theme.text, fontWeight: '600', marginBottom: 6 }}>What do you want to research? *</Text>
          <TextInput
            style={{
              backgroundColor: theme.inputBackground,
              color: theme.text,
              borderColor: theme.borderColor,
              borderWidth: 1,
              borderRadius: 8,
              padding: 12,
              marginBottom: 16,
              minHeight: 80,
              fontSize: 14,
              textAlignVertical: 'top',
            }}
            placeholder="e.g., Latest statistics on renewable energy adoption in India 2025..."
            placeholderTextColor={theme.placeholderText}
            value={iiQuery}
            onChangeText={setIiQuery}
            multiline={true}
            editable={!iiFetching}
          />

          {/* Info */}
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: theme.inputBackground, padding: 10, borderRadius: 8 }}>
            <Ionicons name="information-circle" size={18} color="#06b6d4" style={{ marginRight: 8 }} />
            <Text style={{ color: theme.placeholderText, flex: 1, fontSize: 12, lineHeight: 16 }}>
              AI will search the internet for current data and return structured content. You can review and edit before embedding in your vault.
            </Text>
          </View>

          {/* Fetch Button */}
          <TouchableOpacity
            style={{
              backgroundColor: (!iiQuery.trim() || iiFetching) ? theme.borderColor : '#06b6d4',
              justifyContent: 'center',
              alignItems: 'center',
              paddingVertical: 14,
              borderRadius: 8,
            }}
            onPress={handleIiFetch}
            disabled={!iiQuery.trim() || iiFetching}
          >
            {iiFetching ? (
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 8 }} />
                <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 16 }}>Searching the Internet...</Text>
              </View>
            ) : (
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Ionicons name="search" size={20} color="#FFFFFF" style={{ marginRight: 8 }} />
                <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 16 }}>Fetch from Internet</Text>
              </View>
            )}
          </TouchableOpacity>
        </>
      ) : (
        <>
          <Text style={{ color: theme.placeholderText, marginBottom: 12, fontSize: 13, lineHeight: 18 }}>
            Review the fetched content below. You can edit both the title and content before embedding in your vault.
          </Text>

          {/* Document Title */}
          <Text style={{ color: theme.text, fontWeight: '600', marginBottom: 6 }}>Document Title</Text>
          <TextInput
            style={{
              backgroundColor: theme.inputBackground,
              color: theme.text,
              borderColor: theme.borderColor,
              borderWidth: 1,
              borderRadius: 8,
              padding: 12,
              marginBottom: 16,
              height: 44,
              fontSize: 14,
            }}
            placeholder="Document title"
            placeholderTextColor={theme.placeholderText}
            value={iiTopic}
            onChangeText={setIiTopic}
            maxLength={200}
            editable={!iiEmbedding}
          />

          {/* Content Editor */}
          <Text style={{ color: theme.text, fontWeight: '600', marginBottom: 6 }}>Content (editable)</Text>
          <TextInput
            style={{
              backgroundColor: theme.inputBackground,
              color: theme.text,
              borderColor: theme.borderColor,
              borderWidth: 1,
              borderRadius: 8,
              padding: 12,
              marginBottom: 8,
              minHeight: 200,
              maxHeight: 320,
              fontSize: 13,
              textAlignVertical: 'top',
              lineHeight: 20,
            }}
            value={iiResultText}
            onChangeText={setIiResultText}
            multiline={true}
            editable={!iiEmbedding}
          />
          <Text style={{ color: theme.placeholderText, fontSize: 12, marginBottom: 16, textAlign: 'right' }}>{iiWordCount} words</Text>

          {/* Action Buttons */}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <TouchableOpacity
              style={{
                flex: 1,
                backgroundColor: theme.inputBackground,
                borderColor: '#06b6d4',
                borderWidth: 1.5,
                justifyContent: 'center',
                alignItems: 'center',
                paddingVertical: 12,
                borderRadius: 8,
              }}
              onPress={handleIiReFetch}
              disabled={iiEmbedding}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Ionicons name="refresh" size={18} color="#06b6d4" style={{ marginRight: 6 }} />
                <Text style={{ color: '#06b6d4', fontWeight: '600', fontSize: 14 }}>Re-fetch</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity
              style={{
                flex: 2,
                backgroundColor: (!iiTopic.trim() || !iiResultText.trim() || iiEmbedding) ? theme.borderColor : theme.sendButton,
                justifyContent: 'center',
                alignItems: 'center',
                paddingVertical: 12,
                borderRadius: 8,
              }}
              onPress={handleIiEmbed}
              disabled={!iiTopic.trim() || !iiResultText.trim() || iiEmbedding}
            >
              {iiEmbedding ? (
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 8 }} />
                  <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 14 }}>Embedding in Vault...</Text>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Ionicons name="cloud-upload" size={18} color="#FFFFFF" style={{ marginRight: 6 }} />
                  <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 14 }}>Embed in Vault</Text>
                </View>
              )}
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );

  // ChartStudio pattern: early return if not visible
  if (!isVisible) return null;

  const content = (
    <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
      <View style={[styles.modalContainer, { backgroundColor: theme.background }]}>
        {/* Header */}
        <View style={[styles.modalHeader, { borderBottomColor: theme.borderColor }]}>
          <View style={styles.headerContent}>
            <Text style={[styles.modalTitle, { color: theme.text }]}>
              {activeInlineView === 'pasteText' ? 'Paste Text to Vault' :
               activeInlineView === 'internetIngest' ? 'Ingest from Internet' :
               modalTitle}
            </Text>
            {!activeInlineView && (
            <View style={styles.headerTip}>
              <Text style={styles.headerTipText}>
                Use meaningful file names during upload for better search capability.
              </Text>
            </View>
            )}

            {/* File Limits Info - Collapsible (hide when inline view is active) */}
            {!activeInlineView && (
            <>
            <TouchableOpacity
              style={styles.fileLimitsToggle}
              onPress={() => setShowFileLimits(!showFileLimits)}
              activeOpacity={0.7}
            >
              <View style={styles.fileLimitsToggleContent}>
                <Ionicons name="information-circle-outline" size={16} color="#6b7280" />
                <Text style={styles.fileLimitsToggleText}>File Size & Type Limits</Text>
                {limitsLoading && <ActivityIndicator size="small" color="#6b7280" style={{ marginLeft: 8 }} />}
              </View>
              <Ionicons
                name={showFileLimits ? "chevron-up" : "chevron-down"}
                size={16}
                color="#6b7280"
              />
            </TouchableOpacity>

            {showFileLimits && uploadLimits && (
              <View style={styles.fileLimitsContainer}>
                <View style={styles.fileLimitsGrid}>
                  {formatLimitsForDisplay(uploadLimits).map((item, index) => (
                    <View key={index} style={styles.fileLimitItem}>
                      <Ionicons name={item.icon} size={14} color={item.color} />
                      <Text style={styles.fileLimitText}>{item.text}</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
            </>
            )}

            {!activeInlineView && multipleFolderWarning && (
              <View style={[styles.warningContainer, { backgroundColor: '#FFF3CD', borderColor: '#FFEAA7' }]}>
                <Ionicons name="warning" size={16} color="#856404" />
                <Text style={[styles.warningText, { color: '#856404' }]}>
                  {multipleFolderWarning}
                </Text>
              </View>
            )}

            {/* Entity Search (Enterprise Mode) */}
            {showEntitySearch && (
              <View style={[styles.entitySearchContainer, { borderColor: theme.borderColor, backgroundColor: theme.background }]}>
                <Text style={[styles.entitySearchLabel, { color: theme.text }]}>
                  Select Entity <Text style={styles.required}>*</Text>
                </Text>
                <View style={styles.entitySearchInputContainer}>
                  <Ionicons name="search" size={20} color={theme.placeholderText} style={styles.searchIcon} />
                  <TextInput
                    style={[styles.entitySearchInput, { color: theme.text, borderColor: theme.borderColor }]}
                    placeholder="Search for entity (case name, dept name, etc.)"
                    placeholderTextColor={theme.placeholderText}
                    value={entitySearchText}
                    onChangeText={handleEntitySearchTextChange}
                    autoCorrect={false}
                    autoCapitalize="words"
                  />
                  {isEntitySearching && (
                    <ActivityIndicator size="small" color={theme.sendButton} style={styles.searchSpinner} />
                  )}
                </View>
                {selectedEntity && (
                  <View style={[styles.selectedEntityContainer, { backgroundColor: theme.sendButton + '20', borderColor: theme.sendButton }]}>
                    <Text style={[styles.selectedEntityText, { color: theme.text }]}>
                      Selected: {selectedEntity.entity_name} ({selectedEntity.entity_type})
                    </Text>
                    <TouchableOpacity onPress={() => { onEntitySelect(null); setEntitySearchText(''); }}>
                      <Ionicons name="close-circle" size={20} color={theme.sendButton} />
                    </TouchableOpacity>
                  </View>
                )}
                {showEntitySuggestions && entitySuggestions.length > 0 && (
                  <ScrollView
                    style={[styles.entitySuggestionsContainer, { backgroundColor: theme.background, borderColor: theme.borderColor }]}
                    contentContainerStyle={styles.entitySuggestionsContent}
                    nestedScrollEnabled={true}
                    showsVerticalScrollIndicator={true}
                  >
                    {entitySuggestions.map((entity) => (
                      <TouchableOpacity
                        key={entity.entity_id}
                        style={[styles.entitySuggestionItem, { borderBottomColor: theme.borderColor }]}
                        onPress={() => handleEntitySelect(entity)}
                      >
                        <Text style={[styles.entitySuggestionName, { color: theme.text }]}>
                          {entity.entity_name}
                        </Text>
                        <Text style={[styles.entitySuggestionType, { color: theme.placeholderText }]}>
                          {entity.entity_type}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                )}
                {!selectedEntity && (
                  <Text style={[styles.entityHintText, { color: theme.placeholderText }]}>
                    You must select an entity before uploading documents
                  </Text>
                )}
              </View>
            )}

            {/* Document Details Input - Only for Entity Uploads */}
            {showEntitySearch && (
              <View style={[styles.documentDetailsContainer, { borderColor: theme.borderColor, backgroundColor: theme.background }]}>
                <Text style={[styles.documentDetailsLabel, { color: theme.text }]}>
                  Document Details <Text style={styles.required}>*</Text>
                </Text>
                <TextInput
                  style={[
                    styles.documentDetailsInput,
                    {
                      color: theme.text,
                      borderColor: documentDetailsError ? '#ff4444' : theme.borderColor,
                      backgroundColor: theme.inputBackground || theme.background
                    }
                  ]}
                  placeholder="e.g., Report of xyz, case of a person, etc."
                  placeholderTextColor={theme.placeholderText}
                  value={documentDetails}
                  onChangeText={(text) => {
                    setDocumentDetails(text);
                    if (text.trim()) {
                      setDocumentDetailsError(false);
                    }
                  }}
                  autoCorrect={false}
                  autoCapitalize="words"
                  multiline={false}
                />
                {documentDetailsError && (
                  <Text style={styles.errorText}>
                    Document details are required for entity uploads
                  </Text>
                )}
                <Text style={[styles.documentDetailsHint, { color: theme.placeholderText }]}>
                  Specify the type of document (e.g., client case file, police FIR, land Record)
                </Text>
              </View>
            )}
          </View>
          <TouchableOpacity style={styles.closeButton} onPress={handleCloseWithConfirmation}>
            <Ionicons name="close" size={28} color={theme.text} />
          </TouchableOpacity>
        </View>

        {/* Modal Content - Full Width */}
        <View style={styles.modalBody}>
          {activeInlineView ? (
            <ScrollView
              style={styles.modalContent}
              showsVerticalScrollIndicator={true}
              contentContainerStyle={{ padding: 20 }}
              keyboardShouldPersistTaps="handled"
            >
              {activeInlineView === 'pasteText' ? renderPasteTextView() : renderInternetIngestView()}
            </ScrollView>
          ) : (
          <ScrollView
            style={styles.modalContent}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={styles.modalContentContainer}
          >
            {/* Categorized Data Sources for Web - Horizontal Layout */}
            {Platform.OS === 'web' && !isMobileWeb ? (
              <View style={styles.allCategoriesRow}>
                {DATA_SOURCE_CATEGORIES.map(renderCategory)}
              </View>
            ) : (
              <View style={styles.optionsContainer}>
                {uploadOptions.map(renderOptionCard)}
              </View>
            )}
          </ScrollView>
          )}
        </View>

        {/* Footer */}
        <View style={[styles.modalFooter, { borderTopColor: theme.borderColor }]}>
          <TouchableOpacity
            style={[styles.cancelButton, { borderColor: theme.borderColor }]}
            onPress={handleCloseWithConfirmation}
          >
            <Text style={[styles.cancelButtonText, { color: theme.text }]}>
              Close
            </Text>
          </TouchableOpacity>
        </View>

        {/* Toast Messages */}
        {uploadSuccessToast.visible && (
          <UploadSuccessToast
            visible={uploadSuccessToast.visible}
            onClose={onCloseUploadSuccessToast}
            documentTitle={uploadSuccessToast.documentTitle}
            folderName={uploadSuccessToast.folderName}
            isDefaultFolder={uploadSuccessToast.isDefaultFolder}
            theme={theme}
          />
        )}

        {duplicateUploadToast.visible && (
          <DuplicateUploadToast
            visible={duplicateUploadToast.visible}
            onClose={onCloseDuplicateUploadToast}
            topicName={duplicateUploadToast.topic_or_filename}
            theme={theme}
          />
        )}
      </View>
    </View>
  );

  // Paid Feature Gate - rendered separately for proper z-index layering
  const paidFeatureOverlay = showPaidFeatureModal ? (
    <View style={[
      styles.paidModalOverlay,
      Platform.OS === 'web' && {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 200000,
      }
    ]}>
      <View style={styles.paidModalContainer}>
        <View style={styles.paidModalIconCircle}>
          <Ionicons name="lock-closed" size={32} color="#F59E0B" />
        </View>
        <Text style={styles.paidModalTitle}>Paid Feature</Text>
        <Text style={styles.paidModalMessage}>
          {paidFeatureTitle} is only available for paid users. Purchase credits to unlock this feature.
        </Text>
        <View style={styles.paidModalButtonRow}>
          <TouchableOpacity
            style={styles.paidModalCancelBtn}
            onPress={() => setShowPaidFeatureModal(false)}
          >
            <Text style={styles.paidModalCancelText}>Cancel</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.paidModalBuyBtn}
            onPress={() => {
              setShowPaidFeatureModal(false);
              onClose?.();
            }}
          >
            <Ionicons name="card-outline" size={18} color="#fff" style={{ marginRight: 6 }} />
            <Text style={styles.paidModalBuyText}>Buy Credits</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  ) : null;

  // Platform-specific rendering
  if (Platform.OS === 'web') {
    return (
      <>
        <View style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 100000,
        }}>
          {content}
        </View>
        {paidFeatureOverlay}
      </>
    );
  }

  return (
    <>
      <Modal
        animationType="slide"
        transparent={true}
        visible={isVisible}
        onRequestClose={handleCloseWithConfirmation}
        statusBarTranslucent={true}
      >
        {content}
      </Modal>
      {paidFeatureOverlay}
    </>
  );
};

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContainer: {
    width: '95%',
    maxWidth: 1100,
    height: Platform.OS === 'web' && Dimensions.get('window').width >= 768 ? 'auto' : '90%',
    maxHeight: Platform.OS === 'web' && Dimensions.get('window').width >= 768 ? 520 : 800,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 8,
    display: 'flex',
    flexDirection: 'column',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    padding: 20,
    borderBottomWidth: 1,
    zIndex: 10, // Ensure header is above body for dropdowns
    position: 'relative',
  },
  headerContent: {
    flex: 1,
    marginRight: 10,
    zIndex: 1, // Keep header content above body but below dropdowns
  },
  modalTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  headerTip: {
    marginTop: 4,
    marginBottom: 6,
    backgroundColor: 'rgba(34, 197, 94, 0.1)',
    borderLeftWidth: 3,
    borderLeftColor: '#22c55e',
    paddingVertical: 7,
    paddingHorizontal: 9,
    borderRadius: 8,
  },
  headerTipText: {
    color: '#22c55e',
    fontSize: 13,
    fontWeight: '500',
  },
  // File Limits Styles
  fileLimitsToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: 'rgba(107, 114, 128, 0.08)',
    borderRadius: 8,
    minHeight: 44,
    zIndex: 1, // Below entity search dropdown but above body
  },
  fileLimitsToggleContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  fileLimitsToggleText: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '500',
  },
  fileLimitsContainer: {
    marginTop: 6,
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: 'rgba(107, 114, 128, 0.05)',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(107, 114, 128, 0.15)',
  },
  fileLimitsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
  },
  fileLimitItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    width: '48%',
    paddingVertical: 3,
  },
  fileLimitText: {
    color: '#6b7280',
    fontSize: 11,
  },
  description: {
    fontSize: 14,
    marginBottom: 24,
    lineHeight: 20,
  },
  warningContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
  },
  warningText: {
    fontSize: 13,
    marginLeft: 8,
    flex: 1,
  },
  // Entity Search Styles
  entitySearchContainer: {
    marginTop: 16,
    marginBottom: 8,
    width: '100%',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    position: 'relative',
    overflow: 'visible',
    zIndex: 1000,
  },
  entitySearchLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  required: {
    color: '#ff4444',
  },
  entitySearchInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  searchIcon: {
    position: 'absolute',
    left: 10,
    zIndex: 1,
  },
  entitySearchInput: {
    flex: 1,
    height: 44,
    borderWidth: 1,
    borderRadius: 8,
    paddingLeft: 36,
    paddingRight: 40,
    paddingVertical: 10,
    fontSize: 16,
  },
  searchSpinner: {
    position: 'absolute',
    right: 12,
  },
  selectedEntityContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 8,
    borderRadius: 6,
    borderWidth: 1,
    marginTop: 4,
  },
  selectedEntityText: {
    fontSize: 13,
    fontWeight: '500',
    flex: 1,
    marginRight: 8,
  },
  entitySuggestionsContainer: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    maxHeight: 200,
    borderWidth: 1,
    borderTopWidth: 0,
    borderBottomLeftRadius: 8,
    borderBottomRightRadius: 8,
    zIndex: 2000,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 10,
  },
  entitySuggestionsContent: {
    paddingVertical: 4,
  },
  entitySuggestionItem: {
    padding: 12,
    borderBottomWidth: 1,
  },
  entitySuggestionName: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 4,
  },
  entitySuggestionType: {
    fontSize: 12,
  },
  entityHintText: {
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 4,
    marginLeft: 4,
  },
  // Document details styles
  documentDetailsContainer: {
    marginTop: 12,
    width: '100%',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
  },
  documentDetailsLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  documentDetailsInput: {
    width: '100%',
    height: 40,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
  },
  errorText: {
    color: '#ff4444',
    fontSize: 12,
    marginTop: 4,
    marginLeft: 2,
  },
  documentDetailsHint: {
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 6,
    marginLeft: 2,
  },
  closeButton: {
    padding: 12,
    marginRight: -8,
    marginTop: -8,
  },
  // Body Layout
  modalBody: {
    flex: 1,
    overflow: 'hidden',
    zIndex: 0, // Ensure body is below header overlays but still clickable
    position: 'relative', // Establish stacking context
  },
  modalContent: {
    flex: 1,
    padding: 20,
    paddingTop: 16,
  },
  modalContentContainer: {
    paddingBottom: 20,
  },
  // Options
  optionsContainer: {
    gap: 12,
    paddingBottom: 20,
  },
  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  optionIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(128, 128, 128, 0.08)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  optionTextContainer: {
    flex: 1,
  },
  optionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
    flexWrap: 'wrap',
    gap: 8,
  },
  optionTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  queueIndicator: {
    backgroundColor: '#3b82f6',
    borderRadius: 10,
    paddingHorizontal: 6,
    paddingVertical: 1,
    minWidth: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  queueIndicatorText: {
    color: 'white',
    fontSize: 11,
    fontWeight: '700',
  },
  cloudBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  cloudBadgeText: {
    fontSize: 11,
    fontWeight: '600',
  },
  optionDescription: {
    fontSize: 13,
    lineHeight: 18,
  },
  cloudProviderIcons: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 6,
  },
  miniProviderIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    justifyContent: 'center',
    alignItems: 'center',
  },
  moreProvidersText: {
    fontSize: 11,
    fontWeight: '500',
  },
  // Footer
  modalFooter: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    padding: 16,
    borderTopWidth: 1,
  },
  cancelButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    marginLeft: 12,
  },
  cancelButtonText: {
    fontSize: 14,
    fontWeight: '500',
  },
  // Create Vault Form
  createVaultForm: {
    marginBottom: 20,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
  },
  createVaultTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  createVaultInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 12,
  },
  colorPickerContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 12,
  },
  colorOption: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  createVaultButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  createVaultButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  // Category Styles (Web)
  categoriesContainer: {
    paddingBottom: 20,
  },
  allCategoriesRow: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: 20,
    justifyContent: 'flex-start',
    alignItems: 'flex-start',
  },
  categorySection: {
    flex: 1,
    minWidth: 160,
    maxWidth: 220,
  },
  categoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
    paddingLeft: 10,
    borderLeftWidth: 3,
  },
  categoryIconContainer: {
    width: 28,
    height: 28,
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  categoryTitle: {
    fontSize: 13,
    fontWeight: '600',
  },
  categoryOptionsGrid: {
    flexDirection: 'column',
    gap: 8,
  },
  categoryOptionCard: {
    width: '100%',
    padding: 12,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'flex-start',
    minHeight: 100,
    ...Platform.select({
      web: {
        cursor: 'pointer',
        transition: 'transform 0.15s, box-shadow 0.15s',
      },
    }),
  },
  categoryOptionIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  categoryOptionTitle: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
    marginBottom: 3,
  },
  categoryOptionDesc: {
    fontSize: 10,
    textAlign: 'center',
    lineHeight: 13,
  },
  miniProviderRow: {
    flexDirection: 'row',
    marginTop: 6,
    gap: 3,
  },
  tinyProviderIcon: {
    width: 16,
    height: 16,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  dataBadge: {
    marginTop: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
  },
  dataBadgeText: {
    fontSize: 9,
    fontWeight: '600',
  },
  // Paid feature modal styles
  paidModalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    zIndex: 999999,
  },
  paidModalContainer: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 28,
    maxWidth: 400,
    width: '90%',
    alignItems: 'center',
    ...(Platform.OS === 'web' ? { boxShadow: '0 20px 60px rgba(0,0,0,0.3)' } : { elevation: 10 }),
  },
  paidModalIconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FEF3C7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  paidModalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1F2937',
    marginBottom: 8,
  },
  paidModalMessage: {
    fontSize: 15,
    color: '#6B7280',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  paidModalButtonRow: {
    flexDirection: 'row',
    gap: 12,
    width: '100%',
  },
  paidModalCancelBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    backgroundColor: '#F3F4F6',
    alignItems: 'center',
  },
  paidModalCancelText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#6B7280',
  },
  paidModalBuyBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    backgroundColor: '#F59E0B',
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  paidModalBuyText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});

export default UnifiedUploadModal;
