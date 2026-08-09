import React, { useState, useEffect } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  FlatList,
  TextInput,
  ActivityIndicator,
  StyleSheet,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import authService from '../services/authService';
import API_CONFIG from '../config/config';

/**
 * DocumentSelectorModal - Shows a modal to select documents from a vault or all user documents
 * @param {boolean} visible - Whether modal is visible
 * @param {function} onClose - Callback when modal closes without selection
 * @param {function} onSelect - Callback when documents are selected (receives array of document objects)
 * @param {string} folderId - The vault ID to fetch documents from (if null, fetches all user documents)
 * @param {string} currentUserEmail - Current user's email for API auth
 * @param {object} theme - Theme object for styling
 * @param {boolean} multiSelect - Whether to allow multiple document selection (default: true)
 * @param {number} maxSelection - Maximum number of documents that can be selected (default: 50)
 * @param {boolean} showLimitWarning - Whether to show processing limit warning (default: false)
 * @param {string} featureName - Name of feature for warning message (e.g., "Diagram", "Mindmap")
 */
const DocumentSelectorModal = ({
  visible,
  onClose,
  onSelect,
  folderId,
  currentUserEmail,
  theme,
  multiSelect = true,
  maxSelection = 50,
  showLimitWarning = false,
  featureName = ''
}) => {
  const [documents, setDocuments] = useState([]);
  const [filteredDocuments, setFilteredDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocuments, setSelectedDocuments] = useState([]); // Changed to array for multi-select
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch documents when modal opens
  useEffect(() => {
    if (visible) {
      if (folderId) {
        console.log('📂 DocumentSelectorModal: Opening with folderId:', folderId);
      } else {
        console.log('📂 DocumentSelectorModal: Opening without folderId - will fetch all user documents');
      }
      fetchDocuments();
    } else {
      // Reset state when modal closes
      setDocuments([]);
      setFilteredDocuments([]);
      setSearchQuery('');
      setSelectedDocuments([]); // Reset to empty array
      setError(null);
    }
  }, [visible, folderId, currentUserEmail]);

  // Filter documents based on search query
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredDocuments(documents);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = documents.filter(doc =>
        (doc.topic_or_filename || '').toLowerCase().includes(query) ||
        (doc.file_type || '').toLowerCase().includes(query)
      );
      setFilteredDocuments(filtered);
    }
  }, [searchQuery, documents]);

  const fetchDocuments = async () => {
    setIsLoading(true);
    setError(null);

    try {
      let url;
      if (folderId) {
        console.log('📄 Fetching documents for folder:', folderId);
        // Use lightweight selector endpoint (10x faster - no download URLs)
        url = `${API_CONFIG.CITRA_SERVICE_URL}/v2/documents/folder/${folderId}/selector?limit=200`;
      } else {
        console.log('📄 Fetching all documents for user:', currentUserEmail);
        // Fetch all user documents when no folder selected
        url = `${API_CONFIG.CITRA_SERVICE_URL}/api/v2/documents/chunked/list?limit=200`;
      }

      const response = await authService.authenticatedFetch(url, { method: 'GET' });

      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.status}`);
      }

      const data = await response.json();
      const docs = data.documents || [];
      console.log(`✅ Fetched ${docs.length} documents ${folderId ? 'from vault' : 'for user'}`);
      console.log('📋 Sample documents:', docs.map(d => d.topic_or_filename).slice(0, 5));

      setDocuments(docs);
      setFilteredDocuments(docs);

    } catch (err) {
      console.error('❌ Error fetching documents:', err);
      setError(err.message || 'Failed to load documents');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectDocument = () => {
    if (selectedDocuments.length > 0) {
      console.log('✅ Documents selected:', selectedDocuments.map(d => d.topic_or_filename));
      onSelect(selectedDocuments); // Pass array of selected documents
      onClose();
    }
  };

  const toggleDocumentSelection = (document) => {
    if (multiSelect) {
      const isSelected = selectedDocuments.some(doc => doc.document_id === document.document_id);

      if (isSelected) {
        // Remove from selection
        setSelectedDocuments(selectedDocuments.filter(doc => doc.document_id !== document.document_id));
      } else {
        // Add to selection if under max limit
        if (selectedDocuments.length < maxSelection) {
          setSelectedDocuments([...selectedDocuments, document]);
        } else {
          // Show alert that max selection reached
          if (Platform.OS === 'web') {
            alert(`Maximum ${maxSelection} documents can be selected`);
          }
        }
      }
    } else {
      // Single select mode
      setSelectedDocuments([document]);
    }
  };

  const getFileIcon = (fileType) => {
    const type = fileType?.toLowerCase() || '';
    if (type.includes('pdf')) return 'document-text';
    if (type.includes('image') || type.includes('png') || type.includes('jpg') || type.includes('jpeg')) return 'image';
    if (type.includes('audio') || type.includes('mp3') || type.includes('wav')) return 'musical-notes';
    if (type.includes('video') || type.includes('mp4')) return 'videocam';
    if (type.includes('text') || type.includes('txt')) return 'document-text-outline';
    return 'document';
  };

  const renderDocumentItem = ({ item }) => {
    const isSelected = selectedDocuments.some(doc => doc.document_id === item.document_id);

    return (
      <TouchableOpacity
        style={[
          styles.documentItem,
          {
            backgroundColor: theme.cardBackground,
            borderColor: isSelected ? '#10B981' : theme.border || '#E5E7EB',
          },
          isSelected && styles.documentItemSelected
        ]}
        onPress={() => toggleDocumentSelection(item)}
        activeOpacity={0.7}
      >
        <View style={styles.documentItemContent}>
          {/* Checkbox for multi-select, Radio for single-select */}
          {multiSelect ? (
            <View style={[
              styles.checkbox,
              { borderColor: isSelected ? '#10B981' : theme.text || '#6B7280' },
              isSelected && { backgroundColor: '#10B981' }
            ]}>
              {isSelected && <Ionicons name="checkmark" size={16} color="#FFFFFF" />}
            </View>
          ) : (
            <View style={[
              styles.radioButton,
              { borderColor: isSelected ? '#10B981' : theme.text || '#6B7280' }
            ]}>
              {isSelected && <View style={styles.radioButtonInner} />}
            </View>
          )}

          {/* File icon */}
          <Ionicons
            name={getFileIcon(item.file_type)}
            size={24}
            color={isSelected ? '#10B981' : theme.text || '#6B7280'}
            style={styles.fileIcon}
          />

          {/* Document info */}
          <View style={styles.documentInfo}>
            <Text
              style={[
                styles.documentName,
                { color: theme.text || '#1F2937' }
              ]}
              numberOfLines={2}
            >
              {item.topic_or_filename || item.filename || 'Untitled Document'}
            </Text>
            <Text
              style={[
                styles.documentMeta,
                { color: theme.secondaryText || '#6B7280' }
              ]}
            >
              {item.file_type} • {item.total_chunks || 0} chunks
            </Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <View style={[
          styles.modalContainer,
          { backgroundColor: theme.background || '#FFFFFF' }
        ]}>
          {/* Header */}
          <View style={styles.modalHeader}>
            <View>
              <Text style={[
                styles.modalTitle,
                { color: theme.text || '#1F2937' }
              ]}>
                Select Document{multiSelect ? 's' : ''}
              </Text>
              {multiSelect && (
                <Text style={[
                  styles.modalSubtitle,
                  { color: theme.secondaryText || '#6B7280' }
                ]}>
                  Select up to {maxSelection} documents
                </Text>
              )}
            </View>
            <TouchableOpacity
              onPress={onClose}
              style={styles.closeButton}
            >
              <Ionicons name="close" size={24} color={theme.text || '#6B7280'} />
            </TouchableOpacity>
          </View>

          {/* Search bar */}
          <View style={[
            styles.searchContainer,
            { backgroundColor: theme.inputBackground || '#F3F4F6' }
          ]}>
            <Ionicons name="search" size={20} color={theme.secondaryText || '#6B7280'} />
            <TextInput
              style={[
                styles.searchInput,
                { color: theme.text || '#1F2937' }
              ]}
              placeholder="Search documents..."
              placeholderTextColor={theme.placeholderText || '#9CA3AF'}
              value={searchQuery}
              onChangeText={setSearchQuery}
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setSearchQuery('')}>
                <Ionicons name="close-circle" size={20} color={theme.secondaryText || '#6B7280'} />
              </TouchableOpacity>
            )}
          </View>

          {/* Processing Limits Warning */}
          {showLimitWarning && (
            <View style={[
              styles.warningCard,
              {
                backgroundColor: '#FFF3E0',
                borderColor: '#FFE0B2'
              }
            ]}>
              <View style={styles.warningHeader}>
                <Ionicons name="information-circle" size={20} color="#E65100" />
                <Text style={styles.warningTitle}>Processing Limits</Text>
              </View>
              <Text style={styles.warningText}>
                • Max 100 pages per document{'\n'}
                • Max {maxSelection} {maxSelection === 1 ? 'document' : 'documents'} for {featureName}
              </Text>
            </View>
          )}

          {/* Document count */}
          {!isLoading && !error && (
            <View style={styles.countContainer}>
              <Text style={[
                styles.documentCount,
                { color: theme.secondaryText || '#6B7280' }
              ]}>
                {filteredDocuments.length} document{filteredDocuments.length !== 1 ? 's' : ''} found
              </Text>
              {multiSelect && selectedDocuments.length > 0 && (
                <Text style={[
                  styles.selectedCount,
                  { color: '#10B981' }
                ]}>
                  {selectedDocuments.length} selected
                </Text>
              )}
            </View>
          )}

          {/* Content area */}
          <View style={styles.contentArea}>
            {isLoading ? (
              <View style={styles.centerContent}>
                <ActivityIndicator size="large" color="#10B981" />
                <Text style={[
                  styles.loadingText,
                  { color: theme.secondaryText || '#6B7280' }
                ]}>
                  Loading documents...
                </Text>
              </View>
            ) : error ? (
              <View style={styles.centerContent}>
                <Ionicons name="alert-circle" size={48} color="#EF4444" />
                <Text style={[
                  styles.errorText,
                  { color: theme.text || '#1F2937' }
                ]}>
                  {error}
                </Text>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={fetchDocuments}
                >
                  <Text style={styles.retryButtonText}>Retry</Text>
                </TouchableOpacity>
              </View>
            ) : filteredDocuments.length === 0 ? (
              <View style={styles.centerContent}>
                <Ionicons name="document-text-outline" size={48} color={theme.secondaryText || '#9CA3AF'} />
                <Text style={[
                  styles.emptyText,
                  { color: theme.secondaryText || '#6B7280' }
                ]}>
                  {searchQuery ? 'No documents match your search' : 'No documents found'}
                </Text>
                <Text style={[
                  styles.emptySubtext,
                  { color: theme.secondaryText || '#9CA3AF' }
                ]}>
                  {searchQuery ? 'Try adjusting your search terms' : 'Upload documents to get started'}
                </Text>
              </View>
            ) : (
              <FlatList
                data={filteredDocuments}
                keyExtractor={(item) => item.document_id}
                renderItem={renderDocumentItem}
                contentContainerStyle={styles.listContent}
                showsVerticalScrollIndicator={true}
              />
            )}
          </View>

          {/* Action buttons */}
          <View style={[styles.actionButtons, { borderTopColor: theme.border || '#E5E7EB' }]}>
            <TouchableOpacity
              style={[
                styles.button,
                styles.cancelButton,
                { borderColor: theme.border || '#E5E7EB' }
              ]}
              onPress={onClose}
            >
              <Text style={[
                styles.cancelButtonText,
                { color: theme.text || '#6B7280' }
              ]}>
                Cancel
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.button,
                styles.selectButton,
                selectedDocuments.length === 0 && styles.selectButtonDisabled
              ]}
              onPress={handleSelectDocument}
              disabled={selectedDocuments.length === 0}
            >
              <Text style={[
                styles.selectButtonText,
                selectedDocuments.length === 0 && styles.selectButtonTextDisabled
              ]}>
                Select {selectedDocuments.length > 0 ? `(${selectedDocuments.length})` : 'Documents'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContainer: {
    width: '100%',
    maxWidth: 600,
    maxHeight: '80%',
    borderRadius: 16,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    ...Platform.select({
      web: {
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },
      default: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.25,
        shadowRadius: 25,
        elevation: 10,
      },
    }),
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
  },
  modalSubtitle: {
    fontSize: 14,
    marginTop: 4,
  },
  closeButton: {
    padding: 4,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    margin: 16,
    marginBottom: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    padding: 0,
  },
  warningCard: {
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
  },
  warningHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  warningTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#E65100',
    marginLeft: 6,
  },
  warningText: {
    fontSize: 13,
    color: '#E65100',
    lineHeight: 18,
  },
  documentCount: {
    fontSize: 13,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  countContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  selectedCount: {
    fontSize: 13,
    fontWeight: '600',
  },
  contentArea: {
    flex: 1,
    minHeight: 200,
  },
  listContent: {
    padding: 16,
    paddingTop: 8,
  },
  documentItem: {
    borderRadius: 12,
    borderWidth: 2,
    marginBottom: 12,
    overflow: 'hidden',
  },
  documentItemSelected: {
    borderWidth: 2,
    borderColor: '#10B981',
    ...Platform.select({
      web: {
        boxShadow: '0 0 0 3px rgba(16, 185, 129, 0.1)',
      },
    }),
  },
  documentItemContent: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
  },
  radioButton: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  radioButtonInner: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#10B981',
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  fileIcon: {
    marginRight: 12,
  },
  documentInfo: {
    flex: 1,
  },
  documentName: {
    fontSize: 15,
    fontWeight: '600',
    marginBottom: 4,
    lineHeight: 20,
  },
  documentMeta: {
    fontSize: 13,
    lineHeight: 18,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 15,
  },
  errorText: {
    marginTop: 12,
    fontSize: 15,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: 16,
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: '#10B981',
    borderRadius: 8,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
  emptyText: {
    marginTop: 12,
    fontSize: 15,
    textAlign: 'center',
  },
  emptySubtext: {
    marginTop: 8,
    fontSize: 13,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  actionButtons: {
    flexDirection: 'row',
    padding: 20,
    paddingTop: 16,
    gap: 16,
    borderTopWidth: 1,
  },
  button: {
    flex: 1,
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 2,
    ...Platform.select({
      web: {
        cursor: 'pointer',
        transition: 'all 0.2s',
      },
    }),
  },
  cancelButton: {
    borderWidth: 1,
    backgroundColor: 'transparent',
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
  },
  selectButton: {
    backgroundColor: '#10B981',
    shadowColor: '#10B981',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  selectButtonDisabled: {
    backgroundColor: '#F3F4F6',
    shadowOpacity: 0,
    elevation: 0,
    borderWidth: 1,
    borderColor: '#E5E7EB',
    ...Platform.select({
      web: {
        cursor: 'not-allowed',
        boxShadow: 'none',
      },
    }),
  },
  selectButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  selectButtonTextDisabled: {
    color: '#9CA3AF',
  },
});

export default DocumentSelectorModal;
