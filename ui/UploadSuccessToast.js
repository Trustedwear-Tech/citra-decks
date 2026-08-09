// ========================= Upload Success Toast =========================
// Purpose: Show users where their documents were uploaded with clear feedback
// Features: Folder information, animated toast, auto-dismiss
// -----------------------------------------------------------------------

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Animated,
  Platform,
  StyleSheet,
  Easing,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const UploadSuccessToast = ({ 
  visible, 
  onClose, 
  documentTitle, 
  folderName, 
  isDefaultFolder,
  theme 
}) => {
  const translateY = useRef(new Animated.Value(-100)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      // Show animation
      Animated.parallel([
        Animated.spring(translateY, {
          toValue: 0,
          tension: 150,
          friction: 8,
          useNativeDriver: Platform.OS !== 'web',
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 300,
          easing: Easing.out(Easing.quad),
          useNativeDriver: Platform.OS !== 'web',
        })
      ]).start();

      // Auto-dismiss after 4 seconds
      const timer = setTimeout(() => {
        hideToast();
      }, 4000);

      return () => clearTimeout(timer);
    } else {
      // Reset values when not visible
      translateY.setValue(-100);
      opacity.setValue(0);
    }
  }, [visible, translateY, opacity]);

  const hideToast = () => {
    Animated.parallel([
      Animated.timing(translateY, {
        toValue: -100,
        duration: 250,
        easing: Easing.in(Easing.quad),
        useNativeDriver: Platform.OS !== 'web',
      }),
      Animated.timing(opacity, {
        toValue: 0,
        duration: 250,
        useNativeDriver: Platform.OS !== 'web',
      })
    ]).start(() => {
      onClose();
    });
  };

  if (!visible) return null;

  // Check if this is an error/warning message (starts with ❌ or ⚠️)
  const isErrorMessage = documentTitle.startsWith('❌') || documentTitle.startsWith('⚠️');
  
  const toastMessage = isErrorMessage 
    ? null // Don't show folder info for error messages
    : isDefaultFolder
      ? `Document uploaded to Default folder (no folder selected)`
      : `Document uploaded to "${folderName}" folder`;

  const iconName = isErrorMessage 
    ? (documentTitle.startsWith('❌') ? "close-circle" : "warning")
    : (isDefaultFolder ? "folder-outline" : "folder");
  
  const iconColor = isErrorMessage 
    ? (documentTitle.startsWith('❌') ? "#FF6B6B" : theme.warning || '#f59e0b')
    : (isDefaultFolder ? theme.textSecondary : theme.primary);

  return (
    <Animated.View
      style={[
        styles.toastContainer,
        {
          backgroundColor: theme.isDarkMode ? '#FFFFFF' : '#F5F5F5',
          borderColor: isErrorMessage 
            ? (documentTitle.startsWith('❌') ? "#FF6B6B" : theme.warning || '#f59e0b')
            : (isDefaultFolder ? theme.warning || '#f59e0b' : theme.primary),
          transform: [{ translateY }],
          opacity,
          ...Platform.select({
            web: {
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
            },
            default: {
              shadowColor: '#000',
              shadowOffset: { width: 0, height: 4 },
              shadowOpacity: 0.15,
              shadowRadius: 8,
              elevation: 8,
            }
          }),
        }
      ]}
    >
      <View style={styles.toastContent}>
        <View style={styles.iconContainer}>
          <Ionicons name={iconName} size={20} color={iconColor} />
        </View>
        
        <View style={styles.messageContainer}>
          <Text style={[styles.documentTitle, { color: theme.isDarkMode ? '#000000' : '#000000' }]} numberOfLines={1}>
            {documentTitle}
          </Text>
          {toastMessage && (
            <Text style={[styles.toastMessage, { color: theme.isDarkMode ? '#333333' : '#666666' }]} numberOfLines={1}>
              {toastMessage}
            </Text>
          )}
          {isDefaultFolder && !isErrorMessage && (
            <Text style={[styles.helpText, { color: theme.isDarkMode ? '#333333' : '#666666' }]}>
              Create folders to organize documents better
            </Text>
          )}
        </View>

        <TouchableOpacity 
          style={styles.closeButton} 
          onPress={hideToast}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="close" size={16} color={theme.isDarkMode ? '#666666' : '#999999'} />
        </TouchableOpacity>
      </View>

      {isDefaultFolder && !isErrorMessage && (
        <View style={[styles.warningStripe, { backgroundColor: theme.warning || '#f59e0b' }]} />
      )}
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  toastContainer: {
    position: 'fixed',
    bottom: Platform.OS === 'web' ? '140px' : '160px', // Position above chat input
    left: Platform.OS === 'web' ? '280px' : '20px', // Position between sidebar (260px) and chat area
    right: Platform.OS === 'web' ? '20px' : '20px',
    maxWidth: Platform.OS === 'web' ? '400px' : 'auto', // Limit width on web
    borderRadius: 12,
    borderWidth: 1,
    zIndex: 10000, // Very high z-index to appear above modals and other elements
    overflow: 'hidden',
  },
  toastContent: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  iconContainer: {
    marginRight: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  messageContainer: {
    flex: 1,
  },
  documentTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 2,
  },
  toastMessage: {
    fontSize: 12,
    lineHeight: 16,
  },
  helpText: {
    fontSize: 10,
    fontStyle: 'italic',
    marginTop: 2,
    lineHeight: 12,
  },
  closeButton: {
    padding: 4,
    marginLeft: 8,
  },
  warningStripe: {
    height: 3,
    width: '100%',
  },
});

export default UploadSuccessToast;
