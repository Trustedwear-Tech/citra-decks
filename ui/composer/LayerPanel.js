// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// LayerPanel.js - Visual layer management panel for presentation elements
import React, { useMemo, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';

/**
 * LayerPanel - Displays slide elements in z-index order with controls
 * 
 * Features:
 * - Shows all elements sorted by z-index (highest at top)
 * - Click to select element on canvas
 * - Up/Down buttons to reorder layers
 * - Delete button for each element
 * - Visual indicator for element type
 */

// Get icon for element type
const getElementIcon = (element) => {
  switch (element.type) {
    case 'text':
      return { name: 'text', library: 'Ionicons' };
    case 'image':
      return { name: 'image', library: 'Ionicons' };
    case 'shape':
      return { name: 'shapes', library: 'Ionicons' };
    case 'icon':
      return { name: 'star', library: 'Ionicons' };
    case 'chart':
      return { name: 'bar-chart', library: 'Ionicons' };
    case 'diagram':
      return { name: 'git-network', library: 'Ionicons' };
    case 'image_placeholder':
      return { name: 'image-outline', library: 'Ionicons' };
    case 'card':
      return { name: 'card', library: 'Ionicons' };
    case 'numbered_step':
      return { name: 'list-number', library: 'MaterialIcons' };
    default:
      return { name: 'cube', library: 'Ionicons' };
  }
};

// Get display name for element
const getElementDisplayName = (element) => {
  switch (element.type) {
    case 'text':
      // Truncate text content for display
      const textContent = element.content || element.text || '';
      const truncated = textContent.substring(0, 25);
      return truncated.length < textContent.length ? `${truncated}...` : truncated || 'Text';
    case 'image':
      return element.alt || 'Image';
    case 'shape':
      return element.shapeType ? `${element.shapeType.charAt(0).toUpperCase()}${element.shapeType.slice(1)}` : 'Shape';
    case 'icon':
      return element.iconName || 'Icon';
    case 'chart':
      return element.chartType || 'Chart';
    case 'diagram':
      return 'Diagram';
    case 'image_placeholder':
      return 'Image Placeholder';
    case 'card':
      return 'Card';
    case 'numbered_step':
      return `Step ${element.stepNumber || ''}`;
    default:
      return element.type || 'Element';
  }
};

const LayerPanel = ({
  slide,
  selectedElementId,
  onSelectElement,
  onUpdateElement,
  onDeleteElement,
  onReorderElement,
  theme,
}) => {
  // Sort elements by z-index (highest first for display, as top layer = top of list)
  const sortedElements = useMemo(() => {
    if (!slide?.elements || slide.elements.length === 0) return [];
    
    return [...slide.elements].sort((a, b) => {
      const zIndexA = parseInt(a.zIndex) || 0;
      const zIndexB = parseInt(b.zIndex) || 0;
      return zIndexB - zIndexA; // Descending order (highest z-index at top)
    });
  }, [slide?.elements]);

  // Handle moving element up (increase z-index)
  const handleMoveUp = useCallback((element) => {
    if (!slide?.id || !element?.id) return;
    
    // Find element with next higher z-index
    const currentZ = parseInt(element.zIndex) || 0;
    const elementsAbove = sortedElements.filter(el => (parseInt(el.zIndex) || 0) > currentZ);
    
    if (elementsAbove.length === 0) return; // Already at top
    
    // Get the element just above (last in sorted descending array of elements above)
    const elementAbove = elementsAbove[elementsAbove.length - 1];
    const newZ = (parseInt(elementAbove.zIndex) || 0) + 1;
    
    onUpdateElement(slide.id, element.id, { zIndex: newZ });
  }, [slide?.id, sortedElements, onUpdateElement]);

  // Handle moving element down (decrease z-index)
  const handleMoveDown = useCallback((element) => {
    if (!slide?.id || !element?.id) return;
    
    // Find element with next lower z-index
    const currentZ = parseInt(element.zIndex) || 0;
    const elementsBelow = sortedElements.filter(el => (parseInt(el.zIndex) || 0) < currentZ);
    
    if (elementsBelow.length === 0) return; // Already at bottom
    
    // Get the element just below (first in sorted descending array of elements below)
    const elementBelow = elementsBelow[0];
    const newZ = Math.max(0, (parseInt(elementBelow.zIndex) || 0) - 1);
    
    onUpdateElement(slide.id, element.id, { zIndex: newZ });
  }, [slide?.id, sortedElements, onUpdateElement]);

  // Handle bring to front
  const handleBringToFront = useCallback((element) => {
    if (!slide?.id || !element?.id) return;
    
    const maxZ = Math.max(...sortedElements.map(el => parseInt(el.zIndex) || 0));
    onUpdateElement(slide.id, element.id, { zIndex: maxZ + 1 });
  }, [slide?.id, sortedElements, onUpdateElement]);

  // Handle send to back
  const handleSendToBack = useCallback((element) => {
    if (!slide?.id || !element?.id) return;
    
    const minZ = Math.min(...sortedElements.map(el => parseInt(el.zIndex) || 0));
    onUpdateElement(slide.id, element.id, { zIndex: Math.max(0, minZ - 1) });
  }, [slide?.id, sortedElements, onUpdateElement]);

  // Handle delete
  const handleDelete = useCallback((element) => {
    if (!slide?.id || !element?.id) return;
    onDeleteElement(slide.id, element.id);
  }, [slide?.id, onDeleteElement]);

  // Handle select
  const handleSelect = useCallback((element) => {
    onSelectElement(element.id);
  }, [onSelectElement]);

  if (!slide?.elements || slide.elements.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="layers-outline" size={48} color={theme?.textSecondary || '#888'} />
        <Text style={[styles.emptyText, { color: theme?.textSecondary || '#888' }]}>
          No elements on this slide
        </Text>
        <Text style={[styles.emptyHint, { color: theme?.textSecondary || '#888' }]}>
          Add text, images, or shapes to get started
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={[styles.headerText, { color: theme?.textSecondary || '#666' }]}>
          {sortedElements.length} element{sortedElements.length !== 1 ? 's' : ''}
        </Text>
        <Text style={[styles.headerHint, { color: theme?.textSecondary || '#888' }]}>
          Top = Front
        </Text>
      </View>
      
      <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
        {sortedElements.map((element, index) => {
          const isSelected = element.id === selectedElementId;
          const isFirst = index === 0;
          const isLast = index === sortedElements.length - 1;
          const iconInfo = getElementIcon(element);
          const displayName = getElementDisplayName(element);
          
          return (
            <TouchableOpacity
              key={element.id}
              style={[
                styles.layerItem,
                { 
                  backgroundColor: isSelected 
                    ? (theme?.primary || '#3B82F6') + '20' 
                    : theme?.background || '#f5f5f5',
                  borderColor: isSelected 
                    ? theme?.primary || '#3B82F6' 
                    : theme?.border || '#e0e0e0',
                }
              ]}
              onPress={() => handleSelect(element)}
              activeOpacity={0.7}
            >
              {/* Element Type Icon */}
              <View style={[
                styles.iconContainer,
                { backgroundColor: theme?.surface || '#fff' }
              ]}>
                {iconInfo.library === 'MaterialIcons' ? (
                  <MaterialIcons 
                    name={iconInfo.name} 
                    size={16} 
                    color={isSelected ? theme?.primary || '#3B82F6' : theme?.text || '#333'} 
                  />
                ) : (
                  <Ionicons 
                    name={iconInfo.name} 
                    size={16} 
                    color={isSelected ? theme?.primary || '#3B82F6' : theme?.text || '#333'} 
                  />
                )}
              </View>
              
              {/* Element Name */}
              <View style={styles.nameContainer}>
                <Text 
                  style={[
                    styles.elementName, 
                    { color: isSelected ? theme?.primary || '#3B82F6' : theme?.text || '#333' }
                  ]}
                  numberOfLines={1}
                  ellipsizeMode="tail"
                >
                  {displayName}
                </Text>
                <Text style={[styles.zIndexLabel, { color: theme?.textSecondary || '#888' }]}>
                  z: {element.zIndex || 0}
                </Text>
              </View>
              
              {/* Action Buttons */}
              <View style={styles.actions}>
                {/* Move Up */}
                <TouchableOpacity
                  style={[styles.actionBtn, isFirst && styles.actionBtnDisabled]}
                  onPress={() => handleMoveUp(element)}
                  disabled={isFirst}
                  hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                >
                  <Ionicons 
                    name="chevron-up" 
                    size={16} 
                    color={isFirst ? (theme?.textSecondary || '#ccc') : (theme?.text || '#333')} 
                  />
                </TouchableOpacity>
                
                {/* Move Down */}
                <TouchableOpacity
                  style={[styles.actionBtn, isLast && styles.actionBtnDisabled]}
                  onPress={() => handleMoveDown(element)}
                  disabled={isLast}
                  hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                >
                  <Ionicons 
                    name="chevron-down" 
                    size={16} 
                    color={isLast ? (theme?.textSecondary || '#ccc') : (theme?.text || '#333')} 
                  />
                </TouchableOpacity>
                
                {/* Delete */}
                <TouchableOpacity
                  style={styles.actionBtn}
                  onPress={() => handleDelete(element)}
                  hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                >
                  <Ionicons 
                    name="trash-outline" 
                    size={14} 
                    color="#ef4444" 
                  />
                </TouchableOpacity>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      
      {/* Quick Actions Footer */}
      {selectedElementId && (
        <View style={[styles.footer, { borderTopColor: theme?.border || '#e0e0e0' }]}>
          <TouchableOpacity
            style={[styles.footerBtn, { backgroundColor: theme?.background || '#f5f5f5' }]}
            onPress={() => {
              const element = sortedElements.find(el => el.id === selectedElementId);
              if (element) handleBringToFront(element);
            }}
          >
            <Ionicons name="arrow-up" size={14} color={theme?.text || '#333'} />
            <Text style={[styles.footerBtnText, { color: theme?.text || '#333' }]}>Front</Text>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={[styles.footerBtn, { backgroundColor: theme?.background || '#f5f5f5' }]}
            onPress={() => {
              const element = sortedElements.find(el => el.id === selectedElementId);
              if (element) handleSendToBack(element);
            }}
          >
            <Ionicons name="arrow-down" size={14} color={theme?.text || '#333'} />
            <Text style={[styles.footerBtnText, { color: theme?.text || '#333' }]}>Back</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 8,
    marginBottom: 8,
  },
  headerText: {
    fontSize: 12,
    fontWeight: '500',
  },
  headerHint: {
    fontSize: 10,
    fontStyle: 'italic',
  },
  list: {
    flex: 1,
  },
  layerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    marginBottom: 6,
    borderRadius: 8,
    borderWidth: 1,
    gap: 8,
  },
  iconContainer: {
    width: 28,
    height: 28,
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
  },
  nameContainer: {
    flex: 1,
    minWidth: 0,
  },
  elementName: {
    fontSize: 12,
    fontWeight: '500',
  },
  zIndexLabel: {
    fontSize: 10,
    marginTop: 2,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  actionBtn: {
    padding: 4,
    borderRadius: 4,
  },
  actionBtnDisabled: {
    opacity: 0.4,
  },
  footer: {
    flexDirection: 'row',
    gap: 8,
    paddingTop: 12,
    marginTop: 8,
    borderTopWidth: 1,
  },
  footerBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    gap: 4,
  },
  footerBtnText: {
    fontSize: 12,
    fontWeight: '500',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  emptyText: {
    fontSize: 14,
    fontWeight: '500',
    marginTop: 12,
  },
  emptyHint: {
    fontSize: 12,
    marginTop: 4,
    textAlign: 'center',
  },
});

export default LayerPanel;
