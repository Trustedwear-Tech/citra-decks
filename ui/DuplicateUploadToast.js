// ========================= Duplicate Upload Toast =========================
// Purpose: Notify users when they try to upload the same document multiple times
// Features: Warning toast, auto-dismiss, clear messaging
// -------------------------------------------------------------------------

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

const DuplicateUploadToast = ({ 
  visible, 
  onClose, 
  topicName,
  existingItem,
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

      // Auto-dismiss after 5 seconds
      const timer = setTimeout(() => {
        hideToast();
      }, 5000);

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

  const getStatusText = () => {
    if (!existingItem) return 'in queue';
    
    switch (existingItem.status) {
      case 'processing':
        return 'currently uploading';
      case 'queued':
        return 'in queue';
      case 'completed':
        return 'already uploaded';
      default:
        return 'in progress';
    }
  };

  const statusText = getStatusText();
  const toastMessage = `Document "${topicName}" is ${statusText}`;

  return (
    <Animated.View
      style={[
        styles.toastContainer,
        {
          backgroundColor: theme.surface,
          borderColor: theme.warning || '#f59e0b',
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
          <Ionicons 
            name="warning" 
            size={20} 
            color={theme.warning || '#f59e0b'} 
          />
        </View>
        
        <View style={styles.messageContainer}>
          <Text style={[styles.documentTitle, { color: theme.text }]} numberOfLines={1}>
            Duplicate Upload Detected
          </Text>
          <Text style={[styles.toastMessage, { color: theme.textSecondary }]} numberOfLines={2}>
            {toastMessage}
          </Text>
          <Text style={[styles.helpText, { color: theme.textSecondary }]}>
            Only the first upload will be processed
          </Text>
        </View>

        <TouchableOpacity 
          style={styles.closeButton} 
          onPress={hideToast}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="close" size={16} color={theme.textSecondary} />
        </TouchableOpacity>
      </View>

      <View style={[styles.warningStripe, { backgroundColor: theme.warning || '#f59e0b' }]} />
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  toastContainer: {
    position: 'absolute',
    top: Platform.OS === 'web' ? 20 : 60,
    left: 20,
    right: 20,
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

export default DuplicateUploadToast;
