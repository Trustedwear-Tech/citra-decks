// EnhancedNoteModal.js - Improved note creation experience
import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Modal,
  Alert,
  Switch,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Dimensions
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const { width: screenWidth } = Dimensions.get('window');

const EnhancedNoteModal = ({ 
  isVisible, 
  onClose, 
  initialNoteText = '', 
  onSave, 
  theme 
}) => {
  const [tempTitle, setTempTitle] = useState('');
  const [tempNoteText, setTempNoteText] = useState(initialNoteText);
  const [isSaving, setIsSaving] = useState(false);
  const [wordCount, setWordCount] = useState(0);
  const [characterCount, setCharacterCount] = useState(0);
  
  const titleInputRef = useRef(null);
  const noteInputRef = useRef(null);

  // Note templates for quick start - REMOVED TO SIMPLIFY

  useEffect(() => {
    setTempNoteText(initialNoteText);
    updateCounts(initialNoteText);
  }, [initialNoteText]);

  useEffect(() => {
    if (isVisible) {
      // Reset form when modal opens
      setTempTitle('');
      setTempNoteText(initialNoteText || '');
      updateCounts(initialNoteText || '');
    }
  }, [isVisible, initialNoteText]);

  const updateCounts = (text) => {
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    const characters = text.length;
    setWordCount(words);
    setCharacterCount(characters);
  };

  const handleTextChange = (text) => {
    setTempNoteText(text);
    updateCounts(text);
  };

  const handleSave = async () => {
    if (!tempTitle.trim() && !tempNoteText.trim()) {
      Alert.alert('Error', 'Please enter a title or note content before saving.');
      return;
    }

    setIsSaving(true);
    try {
      const noteData = {
        title: tempTitle.trim() || 'Untitled Note',
        text: tempNoteText,
        wordCount: wordCount,
        characterCount: characterCount,
        timestamp: new Date().toISOString()
      };
      
      await onSave(noteData.title, noteData.text, noteData);
      onClose();
      
      // Reset form after successful save
      setTempTitle('');
      setTempNoteText('');
    } catch (error) {
      console.error('Failed to save note:', error);
      Alert.alert('Error', 'Failed to save note. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  // Removed all complex functions like applyTemplate, addTag, removeTag, getPriorityColor, formatPreviewText

  return (
    <Modal
      animationType="slide"
      transparent={true}
      visible={isVisible}
      onRequestClose={onClose}
      presentationStyle="pageSheet"
    >
      <KeyboardAvoidingView 
        style={styles.container} 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
          <View style={[styles.modalContent, { 
            backgroundColor: theme.background,
            width: Platform.OS === 'web' ? Math.min(screenWidth * 0.9, 800) : '95%'
          }]}>
            
            {/* Header */}
            <View style={[styles.header, { borderBottomColor: theme.borderColor }]}>
              <View style={styles.headerLeft}>
                <Text style={[styles.modalTitle, { color: theme.text }]}>
                  Create Note
                </Text>
                <View style={styles.statsContainer}>
                  <Text style={[styles.statsText, { color: theme.placeholderText }]}>
                    {wordCount} words • {characterCount} characters
                  </Text>
                </View>
              </View>
              
              <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                <Ionicons name="close" size={24} color={theme.text} />
              </TouchableOpacity>
            </View>

            {/* Content */}
            <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
              {/* Title Input */}
              <View style={styles.inputSection}>
                <Text style={[styles.inputLabel, { color: theme.text }]}>Title</Text>
                <TextInput
                  ref={titleInputRef}
                  style={[
                    styles.titleInput,
                    { 
                      color: theme.text, 
                      backgroundColor: theme.inputBackground,
                      borderColor: theme.borderColor
                    }
                  ]}
                  placeholder="Enter note title..."
                  placeholderTextColor={theme.placeholderText}
                  value={tempTitle}
                  onChangeText={setTempTitle}
                  returnKeyType="next"
                  onSubmitEditing={() => noteInputRef.current?.focus()}
                />
              </View>

              {/* Note Content - Made Much Larger */}
              <View style={styles.inputSection}>
                <Text style={[styles.inputLabel, { color: theme.text }]}>Content</Text>
                <TextInput
                  ref={noteInputRef}
                  style={[
                    styles.noteTextInput,
                    { 
                      color: theme.text, 
                      backgroundColor: theme.inputBackground,
                      borderColor: theme.borderColor,
                      height: Platform.OS === 'web' ? 400 : 300, // Much larger text area
                      minHeight: 300
                    }
                  ]}
                  multiline
                  placeholder="Start typing your note here..."
                  placeholderTextColor={theme.placeholderText}
                  value={tempNoteText}
                  onChangeText={handleTextChange}
                  textAlignVertical="top"
                />
              </View>
            </ScrollView>

            {/* Footer */}
            <View style={[styles.footer, { borderTopColor: theme.borderColor }]}>
              <TouchableOpacity 
                onPress={onClose} 
                style={[styles.footerButton, { borderColor: theme.borderColor }]}
              >
                <Text style={[styles.footerButtonText, { color: theme.text }]}>
                  Cancel
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                onPress={handleSave}
                style={[styles.footerButton, styles.saveButton, { backgroundColor: theme.primary }]}
                disabled={isSaving}
              >
                {isSaving ? (
                  <ActivityIndicator size="small" color={theme.buttonText} />
                ) : (
                  <Text style={[styles.footerButtonText, { color: theme.buttonText }]}>
                    Save Note
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
};

const styles = {
  container: {
    flex: 1,
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    borderRadius: 16,
    maxHeight: '90%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 8,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flex: 1,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 4,
  },
  closeButton: {
    padding: 4,
  },
  content: {
    flex: 1,
    padding: 20,
  },
  inputSection: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 8,
  },
  titleInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    fontWeight: '500',
  },
  noteTextInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    lineHeight: 24,
    textAlignVertical: 'top',
    flex: 1,
  },
  footer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderTopWidth: 1,
    gap: 12,
  },
  footerButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
  },
  saveButton: {
    borderWidth: 0,
  },
  footerButtonText: {
    fontSize: 16,
    fontWeight: '600',
  },
};

export default EnhancedNoteModal;
