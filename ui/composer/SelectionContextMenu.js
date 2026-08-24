// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, Animated, Dimensions } from 'react-native';
import { MaterialIcons as Icon } from '@expo/vector-icons';

const SelectionContextMenu = ({ 
  selectedText, 
  position, 
  onAction,
  contextManager,
  visible = false,
  onClose
}) => {
  const [fadeAnim] = useState(new Animated.Value(0));
  const [slideAnim] = useState(new Animated.Value(-10));
  const screenWidth = Dimensions.get('window').width;
  const screenHeight = Dimensions.get('window').height;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: 200,
          useNativeDriver: true,
        })
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 0,
          duration: 150,
          useNativeDriver: true,
        }),
        Animated.timing(slideAnim, {
          toValue: -10,
          duration: 150,
          useNativeDriver: true,
        })
      ]).start();
    }
  }, [visible]);

  const actions = [
    {
      icon: 'expand-more',
      label: 'Expand',
      description: 'Add more detail',
      aiPrompt: 'contextual-expand',
      color: '#4CAF50',
      shortcut: 'E'
    },
    {
      icon: 'rate-review',
      label: 'Review',
      description: 'Check accuracy & flow',
      aiPrompt: 'contextual-review',
      color: '#FF9800',
      shortcut: 'R'
    },
    {
      icon: 'lightbulb',
      label: 'Suggest',
      description: 'Get AI suggestions',
      aiPrompt: 'contextual-suggest',
      color: '#2196F3',
      shortcut: 'S'
    },
    {
      icon: 'link',
      label: 'Connect',
      description: 'Link to report goal',
      aiPrompt: 'contextual-connect',
      color: '#9C27B0',
      shortcut: 'C'
    }
  ];

  // Calculate menu position to keep it on screen
  const menuWidth = 280;
  const menuHeight = actions.length * 60 + 20;
  
  let adjustedX = position?.x || 0;
  let adjustedY = (position?.y || 0) - menuHeight - 10;
  
  // Keep menu within screen bounds
  if (adjustedX + menuWidth > screenWidth) {
    adjustedX = screenWidth - menuWidth - 20;
  }
  if (adjustedX < 20) {
    adjustedX = 20;
  }
  if (adjustedY < 50) {
    adjustedY = (position?.y || 0) + 40;
  }
  if (adjustedY + menuHeight > screenHeight - 50) {
    adjustedY = screenHeight - menuHeight - 50;
  }

  const handleAction = async (action) => {
    try {
      await onAction(action, selectedText);
      onClose();
    } catch (error) {
      console.error('Error executing context action:', error);
      onClose();
    }
  };

  const getSelectionPreview = () => {
    if (!selectedText) return '';
    const preview = selectedText.length > 50 
      ? selectedText.substring(0, 50) + '...' 
      : selectedText;
    return `"${preview}"`;
  };

  const styles = {
    overlay: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'transparent',
      zIndex: 1000
    },
    container: {
      position: 'absolute',
      top: adjustedY,
      left: adjustedX,
      width: menuWidth,
      backgroundColor: 'white',
      borderRadius: 12,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.3,
      shadowRadius: 8,
      elevation: 10,
      borderWidth: 1,
      borderColor: '#e0e0e0',
      zIndex: 1001
    },
    header: {
      backgroundColor: '#f8f9fa',
      paddingHorizontal: 15,
      paddingVertical: 10,
      borderTopLeftRadius: 12,
      borderTopRightRadius: 12,
      borderBottomWidth: 1,
      borderBottomColor: '#e0e0e0'
    },
    headerText: {
      fontSize: 12,
      color: '#666',
      fontWeight: '500'
    },
    selectedTextPreview: {
      fontSize: 13,
      color: '#333',
      fontStyle: 'italic',
      marginTop: 2
    },
    menuItem: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 15,
      paddingVertical: 12,
      borderBottomWidth: 1,
      borderBottomColor: '#f0f0f0'
    },
    lastMenuItem: {
      borderBottomWidth: 0,
      borderBottomLeftRadius: 12,
      borderBottomRightRadius: 12
    },
    iconContainer: {
      width: 40,
      height: 40,
      borderRadius: 20,
      justifyContent: 'center',
      alignItems: 'center',
      marginRight: 12
    },
    menuContent: {
      flex: 1
    },
    menuLabel: {
      fontSize: 16,
      fontWeight: '600',
      color: '#333',
      marginBottom: 2
    },
    menuDescription: {
      fontSize: 13,
      color: '#666'
    },
    shortcut: {
      backgroundColor: '#f0f0f0',
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 4,
      marginLeft: 8
    },
    shortcutText: {
      fontSize: 11,
      color: '#666',
      fontWeight: '600'
    },
    goalContext: {
      backgroundColor: '#e3f2fd',
      margin: 12,
      padding: 10,
      borderRadius: 8,
      borderLeftWidth: 3,
      borderLeftColor: '#2196F3'
    },
    goalContextTitle: {
      fontSize: 12,
      fontWeight: '600',
      color: '#1976d2',
      marginBottom: 4
    },
    goalContextText: {
      fontSize: 11,
      color: '#424242',
      lineHeight: 16
    }
  };

  if (!visible) return null;

  return (
    <View style={styles.overlay}>
      <TouchableOpacity style={{ flex: 1 }} onPress={onClose} activeOpacity={1}>
        <Animated.View 
          style={[
            styles.container,
            {
              opacity: fadeAnim,
              transform: [{ translateY: slideAnim }]
            }
          ]}
        >
          {/* Header with selection preview */}
          <View style={styles.header}>
            <Text style={styles.headerText}>🎯 Context-Aware Actions</Text>
            <Text style={styles.selectedTextPreview}>
              {getSelectionPreview()}
            </Text>
          </View>

          {/* Goal context indicator */}
          {contextManager?.reportGoal?.purpose && (
            <View style={styles.goalContext}>
              <Text style={styles.goalContextTitle}>Document Goal:</Text>
              <Text style={styles.goalContextText}>
                {contextManager.reportGoal.purpose.length > 60 
                  ? contextManager.reportGoal.purpose.substring(0, 60) + '...'
                  : contextManager.reportGoal.purpose
                }
              </Text>
            </View>
          )}

          {/* Action items */}
          {actions.map((action, index) => (
            <TouchableOpacity
              key={action.label}
              style={[
                styles.menuItem,
                index === actions.length - 1 && styles.lastMenuItem
              ]}
              onPress={() => handleAction(action)}
              activeOpacity={0.7}
            >
              <View style={[styles.iconContainer, { backgroundColor: action.color + '20' }]}>
                <Icon name={action.icon} size={20} color={action.color} />
              </View>
              
              <View style={styles.menuContent}>
                <Text style={styles.menuLabel}>{action.label}</Text>
                <Text style={styles.menuDescription}>{action.description}</Text>
              </View>
              
              <View style={styles.shortcut}>
                <Text style={styles.shortcutText}>{action.shortcut}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </Animated.View>
      </TouchableOpacity>
    </View>
  );
};

export default SelectionContextMenu;
