// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// PageEditor.js - Rich markdown page editor with live preview
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { WebHTMLRenderer } from '../message/MessageComponents';

const EditorToolbar = ({ onInsert, theme, editorRef }) => {
  const toolbarItems = [
    { 
      icon: 'text', 
      label: 'H1', 
      action: () => onInsert('# ', ''), 
      type: 'header' 
    },
    { 
      icon: 'text-outline', 
      label: 'H2', 
      action: () => onInsert('## ', ''), 
      type: 'header' 
    },
    { 
      icon: 'text-outline', 
      label: 'Bold', 
      action: () => onInsert('**', '**'), 
      type: 'format' 
    },
    { 
      icon: 'create-outline', 
      label: 'Italic', 
      action: () => onInsert('*', '*'), 
      type: 'format' 
    },
    { 
      icon: 'code-slash', 
      label: 'Code', 
      action: () => onInsert('`', '`'), 
      type: 'format' 
    },
    { 
      icon: 'link', 
      label: 'Link', 
      action: () => onInsert('[Link Text](', ')'), 
      type: 'insert' 
    },
    { 
      icon: 'list', 
      label: 'List', 
      action: () => onInsert('\n- ', ''), 
      type: 'insert' 
    },
    { 
      icon: 'list-outline', 
      label: 'Numbered', 
      action: () => onInsert('\n1. ', ''), 
      type: 'insert' 
    },
    { 
      icon: 'chatbox-outline', 
      label: 'Quote', 
      action: () => onInsert('\n> ', ''), 
      type: 'insert' 
    },
    { 
      icon: 'remove', 
      label: 'Divider', 
      action: () => onInsert('\n---\n', ''), 
      type: 'insert' 
    },
  ];

  return (
    <View style={[styles.toolbar, { 
      backgroundColor: theme.surface,
      borderBottomColor: theme.borderColor 
    }]}>
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.toolbarContent}
      >
        {toolbarItems.map((item, index) => (
          <TouchableOpacity
            key={index}
            style={[styles.toolbarButton, { backgroundColor: theme.inputBackground }]}
            onPress={item.action}
            title={item.label}
          >
            <Ionicons name={item.icon} size={16} color={theme.text} />
            <Text style={[styles.toolbarButtonText, { color: theme.text }]}>
              {item.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
};

const MarkdownEditor = ({ 
  content, 
  onContentChange, 
  theme, 
  placeholder = "Start writing your content..." 
}) => {
  const textAreaRef = useRef(null);
  const [cursorPosition, setCursorPosition] = useState({ start: 0, end: 0 });

  const handleInsert = useCallback((before, after = '') => {
    if (Platform.OS === 'web' && textAreaRef.current) {
      const textarea = textAreaRef.current;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const selectedText = content.substring(start, end);
      
      const newContent = 
        content.substring(0, start) + 
        before + selectedText + after + 
        content.substring(end);
      
      onContentChange(newContent);
      
      // Set cursor position after insertion
      setTimeout(() => {
        const newPosition = start + before.length + selectedText.length;
        textarea.setSelectionRange(newPosition, newPosition);
        textarea.focus();
      }, 0);
    }
  }, [content, onContentChange]);

  const handleSelectionChange = useCallback((event) => {
    if (Platform.OS === 'web') {
      const { selectionStart, selectionEnd } = event.target;
      setCursorPosition({ start: selectionStart, end: selectionEnd });
    }
  }, []);

  // For web, use textarea for better editing experience
  if (Platform.OS === 'web') {
    return (
      <View style={styles.editorContainer}>
        <EditorToolbar 
          onInsert={handleInsert} 
          theme={theme} 
          editorRef={textAreaRef}
        />
        <textarea
          ref={textAreaRef}
          value={content}
          onChange={(e) => onContentChange(e.target.value)}
          onSelect={handleSelectionChange}
          placeholder={placeholder}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            outline: 'none',
            resize: 'none',
            padding: '16px',
            fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
            fontSize: '14px',
            lineHeight: '1.6',
            backgroundColor: theme.inputBackground,
            color: theme.text,
            caretColor: theme.primary,
          }}
        />
      </View>
    );
  }

  // Fallback for non-web platforms (should not be used based on requirements)
  return (
    <View style={styles.editorContainer}>
      <EditorToolbar onInsert={handleInsert} theme={theme} />
      <TextInput
        ref={textAreaRef}
        value={content}
        onChangeText={onContentChange}
        placeholder={placeholder}
        placeholderTextColor={theme.placeholderText}
        multiline
        textAlignVertical="top"
        style={[styles.textInput, {
          backgroundColor: theme.inputBackground,
          color: theme.text,
          borderColor: theme.borderColor,
        }]}
      />
    </View>
  );
};

const PreviewPanel = ({ content, theme }) => {
  return (
    <ScrollView style={[styles.previewContainer, { backgroundColor: theme.background }]}>
      <View style={styles.previewContent}>
        <WebHTMLRenderer
          content={content}
          theme={theme}
          style={{
            padding: 16,
            minHeight: '100%',
          }}
        />
      </View>
    </ScrollView>
  );
};

const PageTitleEditor = ({ title, onTitleChange, theme }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editingTitle, setEditingTitle] = useState(title || '');

  const handleSaveTitle = () => {
    onTitleChange(editingTitle.trim() || 'Untitled Page');
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setEditingTitle(title || '');
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <View style={[styles.titleEditor, { backgroundColor: theme.inputBackground }]}>
        <TextInput
          value={editingTitle}
          onChangeText={setEditingTitle}
          placeholder="Enter page title..."
          placeholderTextColor={theme.placeholderText}
          style={[styles.titleInput, { color: theme.text }]}
          autoFocus
          onBlur={handleSaveTitle}
          onSubmitEditing={handleSaveTitle}
        />
        <TouchableOpacity onPress={handleSaveTitle} style={styles.titleSaveButton}>
          <Ionicons name="checkmark" size={20} color={theme.primary} />
        </TouchableOpacity>
        <TouchableOpacity onPress={handleCancelEdit} style={styles.titleCancelButton}>
          <Ionicons name="close" size={20} color={theme.placeholderText} />
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <TouchableOpacity
      style={[styles.titleDisplay, { backgroundColor: theme.surface }]}
      onPress={() => setIsEditing(true)}
    >
      <Text style={[styles.titleText, { color: theme.text }]}>
        {title || 'Untitled Page'}
      </Text>
      <Ionicons name="create-outline" size={16} color={theme.placeholderText} />
    </TouchableOpacity>
  );
};

const PageEditor = React.forwardRef(({ 
  page, 
  pages,
  onContentUpdate, 
  onTitleUpdate,
  onContentChange, // alias supported by ReportComposer
  onTitleChange,   // alias supported by ReportComposer
  theme, 
  mode = 'split',
  reportMetadata,
  onUpdateMetadata 
}, ref) => {
  const [content, setContent] = useState(page?.content || '');
  const [wordCount, setWordCount] = useState(0);

  // Expose methods to parent component
  React.useImperativeHandle(ref, () => ({
    getCurrentContent: () => content,
    getWordCount: () => wordCount
  }), [content, wordCount]);

  // Update content when page changes
  useEffect(() => {
    setContent(page?.content || '');
  }, [page?.id, page?.content]);

  // Calculate word count
  useEffect(() => {
    const words = content.trim().split(/\s+/).filter(word => word.length > 0);
    setWordCount(words.length);
  }, [content]);

  // Resolve handlers (support both prop name variants)
  const emitContentUpdate = useCallback((id, value) => {
    if (typeof onContentChange === 'function') {
      onContentChange(value);
    } else if (typeof onContentUpdate === 'function') {
      onContentUpdate(id, value);
    }
  }, [onContentChange, onContentUpdate]);

  const emitTitleUpdate = useCallback((id, value) => {
    if (typeof onTitleChange === 'function') {
      onTitleChange(value);
    } else if (typeof onTitleUpdate === 'function') {
      onTitleUpdate(id, value);
    }
  }, [onTitleChange, onTitleUpdate]);

  // Debounced content update
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (content !== page?.content) {
        emitContentUpdate(page?.id, content);
      }
    }, 500);

    return () => clearTimeout(timeoutId);
  }, [content, page?.id, page?.content, emitContentUpdate]);

  const handleContentChange = useCallback((newContent) => {
    setContent(newContent);
  }, []);

  const handleTitleChange = useCallback((newTitle) => {
    emitTitleUpdate(page?.id, newTitle);
  }, [page?.id, emitTitleUpdate]);

  // Expose methods to parent component
  React.useImperativeHandle(ref, () => ({
    getCurrentContent: () => content,
    getWordCount: () => wordCount
  }), [content, wordCount]);

  if (!page) {
    return (
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        <View style={styles.emptyState}>
          <Ionicons name="document-text-outline" size={48} color={theme.placeholderText} />
          <Text style={[styles.emptyStateText, { color: theme.placeholderText }]}>
            No page selected
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      {/* Page Header */}
      <View style={[styles.pageHeader, { 
        backgroundColor: theme.surface,
        borderBottomColor: theme.borderColor 
      }]}>
        <PageTitleEditor
          title={page.title}
          onTitleChange={handleTitleChange}
          theme={theme}
        />
        
        <View style={styles.pageStats}>
          <Text style={[styles.pageStatsText, { color: theme.placeholderText }]}>
            {wordCount} words
          </Text>
          <Text style={[styles.pageStatsText, { color: theme.placeholderText }]}>
            Page {pages.findIndex(p => p.id === page.id) + 1} of {pages.length}
          </Text>
        </View>
      </View>

      {/* Editor Content */}
      <View style={styles.editorWrapper}>
        {mode === 'split' && (
          <View style={styles.splitMode}>
            <View style={styles.editorHalf}>
              <View style={[styles.panelHeader, { backgroundColor: theme.surface }]}>
                <Text style={[styles.panelTitle, { color: theme.text }]}>Editor</Text>
              </View>
              <MarkdownEditor
                content={content}
                onContentChange={handleContentChange}
                theme={theme}
                placeholder="Start writing your page content..."
              />
            </View>
            <View style={[styles.divider, { backgroundColor: theme.borderColor }]} />
            <View style={styles.previewHalf}>
              <View style={[styles.panelHeader, { backgroundColor: theme.surface }]}>
                <Text style={[styles.panelTitle, { color: theme.text }]}>Preview</Text>
              </View>
              <PreviewPanel content={content} theme={theme} />
            </View>
          </View>
        )}

        {mode === 'edit' && (
          <MarkdownEditor
            content={content}
            onContentChange={handleContentChange}
            theme={theme}
            placeholder="Start writing your page content..."
          />
        )}

        {mode === 'preview' && (
          <PreviewPanel content={content} theme={theme} />
        )}
      </View>
    </View>
  );
});

const styles = {
  container: {
    flex: 1,
  },
  pageHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  titleDisplay: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 8,
  },
  titleText: {
    fontSize: 16,
    fontWeight: '600',
  },
  titleEditor: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
    gap: 8,
  },
  titleInput: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
    paddingVertical: 4,
  },
  titleSaveButton: {
    padding: 4,
  },
  titleCancelButton: {
    padding: 4,
  },
  pageStats: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  pageStatsText: {
    fontSize: 12,
    fontWeight: '500',
  },
  editorWrapper: {
    flex: 1,
  },
  splitMode: {
    flex: 1,
    flexDirection: 'row',
  },
  editorHalf: {
    flex: 1,
  },
  previewHalf: {
    flex: 1,
  },
  divider: {
    width: 1,
  },
  panelHeader: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.1)',
  },
  panelTitle: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  editorContainer: {
    flex: 1,
  },
  toolbar: {
    borderBottomWidth: 1,
    paddingVertical: 8,
  },
  toolbarContent: {
    paddingHorizontal: 16,
    gap: 8,
  },
  toolbarButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  toolbarButtonText: {
    fontSize: 11,
    fontWeight: '500',
  },
  textInput: {
    flex: 1,
    padding: 16,
    fontSize: 14,
    lineHeight: 20,
    fontFamily: Platform.OS === 'web' ? 'Monaco, Menlo, "Ubuntu Mono", monospace' : 'monospace',
  },
  previewContainer: {
    flex: 1,
  },
  previewContent: {
    flex: 1,
    padding: 16,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  emptyStateText: {
    fontSize: 16,
    fontWeight: '500',
  },
};

export default PageEditor;
