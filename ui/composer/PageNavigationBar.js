// PageNavigationBar.js - Horizontal scrollable page navigation
import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Modal,
  Platform,
  Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const PageTab = ({ 
  page, 
  index, 
  isActive, 
  onSelect, 
  onDelete, 
  onInsertBefore, 
  onInsertAfter,
  theme 
}) => {
  const [showContextMenu, setShowContextMenu] = useState(false);
  const [contextMenuPosition, setContextMenuPosition] = useState({ x: 0, y: 0 });

  const handleLongPress = (event) => {
    const { pageX, pageY } = event.nativeEvent;
    setContextMenuPosition({ x: pageX, y: pageY });
    setShowContextMenu(true);
  };

  const handleContextAction = (action) => {
    setShowContextMenu(false);
    switch (action) {
      case 'insertBefore':
        onInsertBefore();
        break;
      case 'insertAfter':
        onInsertAfter();
        break;
      case 'delete':
        onDelete();
        break;
      case 'rename':
        // TODO: Implement rename functionality
        break;
    }
  };

  return (
    <>
      <TouchableOpacity
        style={[
          styles.pageTab,
          { 
            backgroundColor: isActive ? theme.primary : theme.surface,
            borderColor: isActive ? theme.primary : theme.borderColor,
          }
        ]}
        onPress={onSelect}
        onLongPress={handleLongPress}
      >
        <View style={styles.pageTabContent}>
          <Text style={[
            styles.pageTabTitle,
            { 
              color: isActive ? theme.buttonText : theme.text,
              fontWeight: isActive ? '600' : '400'
            }
          ]}>
            {page.title || `Page ${index + 1}`}
          </Text>
          <Text style={[
            styles.pageTabNumber,
            { color: isActive ? theme.buttonText : theme.placeholderText }
          ]}>
            {index + 1}
          </Text>
        </View>
        
        {/* Page status indicators */}
        <View style={styles.pageIndicators}>
          {page.hasUnsavedChanges && (
            <View style={[styles.unsavedIndicator, { backgroundColor: '#FF9500' }]} />
          )}
          {page.wordCount > 0 && (
            <Text style={[styles.wordCount, { 
              color: isActive ? theme.buttonText : theme.placeholderText 
            }]}>
              {page.wordCount}w
            </Text>
          )}
        </View>
      </TouchableOpacity>

      {/* Context Menu */}
      {showContextMenu && Platform.OS === 'web' && (
        <Modal
          visible={showContextMenu}
          transparent
          animationType="fade"
          onRequestClose={() => setShowContextMenu(false)}
        >
          <TouchableOpacity
            style={styles.contextMenuOverlay}
            onPress={() => setShowContextMenu(false)}
          >
            <View 
              style={[
                styles.contextMenu,
                { 
                  backgroundColor: theme.surface,
                  borderColor: theme.borderColor,
                  left: Math.min(contextMenuPosition.x, window.innerWidth - 200),
                  top: Math.min(contextMenuPosition.y, window.innerHeight - 200)
                }
              ]}
            >
              <TouchableOpacity
                style={[styles.contextMenuItem, { borderBottomColor: theme.borderColor }]}
                onPress={() => handleContextAction('insertBefore')}
              >
                <Ionicons name="add-circle-outline" size={16} color={theme.text} />
                <Text style={[styles.contextMenuText, { color: theme.text }]}>
                  Insert Page Before
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.contextMenuItem, { borderBottomColor: theme.borderColor }]}
                onPress={() => handleContextAction('insertAfter')}
              >
                <Ionicons name="add-circle-outline" size={16} color={theme.text} />
                <Text style={[styles.contextMenuText, { color: theme.text }]}>
                  Insert Page After
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.contextMenuItem, { borderBottomColor: theme.borderColor }]}
                onPress={() => handleContextAction('rename')}
              >
                <Ionicons name="create-outline" size={16} color={theme.text} />
                <Text style={[styles.contextMenuText, { color: theme.text }]}>
                  Rename Page
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={styles.contextMenuItem}
                onPress={() => handleContextAction('delete')}
              >
                <Ionicons name="trash-outline" size={16} color="#FF3B30" />
                <Text style={[styles.contextMenuText, { color: '#FF3B30' }]}>
                  Delete Page
                </Text>
              </TouchableOpacity>
            </View>
          </TouchableOpacity>
        </Modal>
      )}
    </>
  );
};

const AddPageButton = ({ onPress, theme }) => (
  <TouchableOpacity
    style={[styles.addPageButton, { 
      backgroundColor: theme.surface,
      borderColor: theme.borderColor,
      borderStyle: 'dashed'
    }]}
    onPress={onPress}
  >
    <Ionicons name="add" size={24} color={theme.placeholderText} />
    <Text style={[styles.addPageText, { color: theme.placeholderText }]}>
      Add Page
    </Text>
  </TouchableOpacity>
);

const PageNavigationBar = ({
  pages,
  currentPageId,
  onSelectPage,
  onAddPage,
  onDeletePage,
  onInsertPage,
  theme
}) => {
  // Default theme fallback
  const safeTheme = theme || {
    background: '#ffffff',
    borderColor: '#e0e0e0',
    textColor: '#000000',
    primaryColor: '#007AFF',
    primary: '#007AFF',
    surface: '#f8f9fa',
    text: '#000000',
    buttonText: '#ffffff',
    placeholderText: '#666666'
  };
  
  const scrollViewRef = useRef(null);
  const currentPageIndex = pages.findIndex(p => p.id === currentPageId);

  // Auto-scroll to current page when it changes
  useEffect(() => {
    if (scrollViewRef.current && currentPageIndex >= 0) {
      const scrollX = currentPageIndex * 200; // Approximate tab width
      scrollViewRef.current.scrollTo({ x: scrollX, animated: true });
    }
  }, [currentPageIndex]);

  const handleInsertPage = (insertIndex) => {
    // Support both onInsertPage and onInsertPageIndex prop names
    if (typeof onInsertPage === 'function') {
      onInsertPage(insertIndex);
    }
  };

  return (
    <View style={[styles.container, { 
      backgroundColor: safeTheme.background,
      borderBottomColor: safeTheme.borderColor 
    }]}>
      <ScrollView
        ref={scrollViewRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        style={styles.scrollView}
      >
        {pages.map((page, index) => (
          <PageTab
            key={page.id}
            page={page}
            index={index}
            isActive={currentPageId === page.id}
            onSelect={() => onSelectPage(page.id)}
            onDelete={() => onDeletePage(page.id)}
            onInsertBefore={() => handleInsertPage(index)}
            onInsertAfter={() => handleInsertPage(index + 1)}
            theme={safeTheme}
          />
        ))}
        
        <AddPageButton onPress={onAddPage} theme={safeTheme} />
      </ScrollView>

      {/* Page counter */}
      <View style={[styles.pageCounter, { backgroundColor: safeTheme.surface }]}>
        <Text style={[styles.pageCounterText, { color: safeTheme.text }]}>
          {currentPageIndex + 1} of {pages.length}
        </Text>
      </View>
    </View>
  );
};

const styles = {
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    paddingVertical: 8,
    minHeight: 60,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 16,
    alignItems: 'center',
    gap: 8,
  },
  pageTab: {
    minWidth: 180,
    maxWidth: 240,
    height: 44,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    position: 'relative',
  },
  pageTabContent: {
    flex: 1,
  },
  pageTabTitle: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 2,
  },
  pageTabNumber: {
    fontSize: 11,
  },
  pageIndicators: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  unsavedIndicator: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  wordCount: {
    fontSize: 10,
    fontWeight: '400',
  },
  addPageButton: {
    width: 120,
    height: 44,
    borderRadius: 8,
    borderWidth: 2,
    justifyContent: 'center',
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  addPageText: {
    fontSize: 12,
    fontWeight: '500',
  },
  pageCounter: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    marginRight: 16,
  },
  pageCounterText: {
    fontSize: 12,
    fontWeight: '500',
  },
  contextMenuOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.1)',
  },
  contextMenu: {
    position: 'absolute',
    minWidth: 180,
    borderRadius: 8,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 8,
  },
  contextMenuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    gap: 8,
  },
  contextMenuText: {
    fontSize: 14,
    fontWeight: '400',
  },
};

export default PageNavigationBar;
