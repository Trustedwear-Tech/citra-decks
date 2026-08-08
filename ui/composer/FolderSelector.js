// FolderSelector.js - Folder selection for organizing reports
import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Modal,
  TextInput,
  Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const FolderSelector = ({
  visible,
  onClose,
  onFolderSelect,
  currentFolderId,
  folders = [],
  theme,
  userDeviceId,
  apiConfig
}) => {
  const [selectedFolderId, setSelectedFolderId] = useState(currentFolderId);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderDescription, setNewFolderDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    setSelectedFolderId(currentFolderId);
  }, [currentFolderId]);

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      Alert.alert('Error', 'Please enter a folder name');
      return;
    }

    try {
      setIsCreating(true);
      
      // Call folder creation API
      const response = await fetch(`${apiConfig.FOLDER_API_URL}/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: newFolderName.trim(),
          description: newFolderDescription.trim(),
          user_id: userDeviceId,
          folder_type: 'reports'
        })
      });

      if (response.ok) {
        const newFolder = await response.json();
        Alert.alert('Success', 'Folder created successfully');
        setNewFolderName('');
        setNewFolderDescription('');
        setShowCreateFolder(false);
        // Refresh folders - this would typically trigger a parent component refresh
        if (onFolderSelect) {
          onFolderSelect(newFolder.id, newFolder);
        }
      } else {
        throw new Error('Failed to create folder');
      }
    } catch (error) {
      console.error('Error creating folder:', error);
      Alert.alert('Error', 'Failed to create folder. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleConfirm = () => {
    const selectedFolder = folders.find(f => f.id === selectedFolderId);
    onFolderSelect(selectedFolderId, selectedFolder);
    onClose();
  };

  const reportFolders = folders.filter(folder => 
    folder.folder_type === 'reports' || 
    folder.name?.toLowerCase().includes('report')
  );

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: theme.borderColor }]}>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={theme.text} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: theme.text }]}>
            Select Folder
          </Text>
          <TouchableOpacity 
            onPress={() => setShowCreateFolder(true)}
            style={styles.createButton}
          >
            <Ionicons name="add" size={24} color={theme.primary} />
          </TouchableOpacity>
        </View>

        {/* Folder List */}
        <ScrollView style={styles.content}>
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: theme.text }]}>
              Report Folders
            </Text>
            
            {/* No Folder Option */}
            <TouchableOpacity
              style={[
                styles.folderItem,
                { 
                  backgroundColor: selectedFolderId === null ? theme.primary + '20' : theme.surface,
                  borderColor: selectedFolderId === null ? theme.primary : theme.borderColor
                }
              ]}
              onPress={() => setSelectedFolderId(null)}
            >
              <View style={styles.folderInfo}>
                <Ionicons 
                  name="document-outline" 
                  size={20} 
                  color={selectedFolderId === null ? theme.primary : theme.placeholderText} 
                />
                <View style={styles.folderDetails}>
                  <Text style={[
                    styles.folderName, 
                    { color: selectedFolderId === null ? theme.primary : theme.text }
                  ]}>
                    No Folder
                  </Text>
                  <Text style={[styles.folderDescription, { color: theme.placeholderText }]}>
                    Save report without organizing in a folder
                  </Text>
                </View>
              </View>
              {selectedFolderId === null && (
                <Ionicons name="checkmark-circle" size={20} color={theme.primary} />
              )}
            </TouchableOpacity>

            {/* Existing Folders */}
            {reportFolders.map((folder) => (
              <TouchableOpacity
                key={folder.id}
                style={[
                  styles.folderItem,
                  { 
                    backgroundColor: selectedFolderId === folder.id ? theme.primary + '20' : theme.surface,
                    borderColor: selectedFolderId === folder.id ? theme.primary : theme.borderColor
                  }
                ]}
                onPress={() => setSelectedFolderId(folder.id)}
              >
                <View style={styles.folderInfo}>
                  <Ionicons 
                    name="folder-outline" 
                    size={20} 
                    color={selectedFolderId === folder.id ? theme.primary : theme.placeholderText} 
                  />
                  <View style={styles.folderDetails}>
                    <Text style={[
                      styles.folderName, 
                      { color: selectedFolderId === folder.id ? theme.primary : theme.text }
                    ]}>
                      {folder.name}
                    </Text>
                    {folder.description && (
                      <Text style={[styles.folderDescription, { color: theme.placeholderText }]}>
                        {folder.description}
                      </Text>
                    )}
                    <Text style={[styles.folderMeta, { color: theme.placeholderText }]}>
                      {folder.item_count || 0} items
                    </Text>
                  </View>
                </View>
                {selectedFolderId === folder.id && (
                  <Ionicons name="checkmark-circle" size={20} color={theme.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Create Folder Modal */}
        <Modal
          visible={showCreateFolder}
          animationType="fade"
          transparent={true}
        >
          <View style={styles.overlay}>
            <View style={[styles.createModal, { backgroundColor: theme.surface }]}>
              <Text style={[styles.createTitle, { color: theme.text }]}>
                Create New Folder
              </Text>
              
              <TextInput
                style={[styles.input, { 
                  backgroundColor: theme.inputBackground,
                  color: theme.text,
                  borderColor: theme.borderColor 
                }]}
                placeholder="Folder name"
                placeholderTextColor={theme.placeholderText}
                value={newFolderName}
                onChangeText={setNewFolderName}
                maxLength={50}
              />
              
              <TextInput
                style={[styles.textArea, { 
                  backgroundColor: theme.inputBackground,
                  color: theme.text,
                  borderColor: theme.borderColor 
                }]}
                placeholder="Description (optional)"
                placeholderTextColor={theme.placeholderText}
                value={newFolderDescription}
                onChangeText={setNewFolderDescription}
                multiline
                maxLength={200}
              />
              
              <View style={styles.createActions}>
                <TouchableOpacity
                  style={[styles.button, styles.cancelButton, { borderColor: theme.borderColor }]}
                  onPress={() => {
                    setShowCreateFolder(false);
                    setNewFolderName('');
                    setNewFolderDescription('');
                  }}
                >
                  <Text style={[styles.buttonText, { color: theme.text }]}>Cancel</Text>
                </TouchableOpacity>
                
                <TouchableOpacity
                  style={[styles.button, styles.primaryButton, { backgroundColor: theme.primary }]}
                  onPress={handleCreateFolder}
                  disabled={isCreating || !newFolderName.trim()}
                >
                  <Text style={[styles.buttonText, { color: theme.buttonText }]}>
                    {isCreating ? 'Creating...' : 'Create'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Footer Actions */}
        <View style={[styles.footer, { borderTopColor: theme.borderColor }]}>
          <TouchableOpacity
            style={[styles.footerButton, { borderColor: theme.borderColor }]}
            onPress={onClose}
          >
            <Text style={[styles.footerButtonText, { color: theme.text }]}>Cancel</Text>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={[styles.footerButton, styles.primaryFooterButton, { backgroundColor: theme.primary }]}
            onPress={handleConfirm}
          >
            <Text style={[styles.footerButtonText, { color: theme.buttonText }]}>
              Confirm
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
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
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  createButton: {
    padding: 4,
  },
  content: {
    flex: 1,
    padding: 16,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  folderItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 8,
  },
  folderInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  folderDetails: {
    flex: 1,
  },
  folderName: {
    fontSize: 16,
    fontWeight: '500',
    marginBottom: 2,
  },
  folderDescription: {
    fontSize: 13,
    marginBottom: 2,
  },
  folderMeta: {
    fontSize: 12,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  createModal: {
    width: '90%',
    maxWidth: 400,
    padding: 24,
    borderRadius: 16,
    margin: 20,
  },
  createTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 20,
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    marginBottom: 16,
  },
  textArea: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    height: 80,
    textAlignVertical: 'top',
    marginBottom: 20,
  },
  createActions: {
    flexDirection: 'row',
    gap: 12,
  },
  button: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  cancelButton: {
    borderWidth: 1,
  },
  primaryButton: {
    // backgroundColor set inline
  },
  buttonText: {
    fontSize: 16,
    fontWeight: '500',
  },
  footer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderTopWidth: 1,
    gap: 12,
  },
  footerButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
  },
  primaryFooterButton: {
    borderWidth: 0,
  },
  footerButtonText: {
    fontSize: 16,
    fontWeight: '500',
  },
};

export default FolderSelector;
