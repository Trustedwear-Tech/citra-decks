// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// BackgroundControlDropdown.js - Slide background controls: color picker + background image opacity + remove
import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import ColorPickerDropdown from './ColorPickerDropdown';

const BackgroundControlDropdown = ({
  theme = {},
  slideBackgroundColor = '#ffffff',
  onUpdateSlideBackground,
  backgroundImageOpacity,
  hasBackgroundImage = false,
  onChangeBackgroundOpacity,
  onRemoveBackgroundImage,
  compact = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const opacityPercent = Math.round((backgroundImageOpacity ?? 0.3) * 100);

  return (
    <View ref={dropdownRef} style={{ position: 'relative', zIndex: 1200 }}>
      {/* Trigger: color swatch + dropdown arrow */}
      <TouchableOpacity
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          padding: 4,
          borderRadius: 4,
          gap: 3,
        }}
        onPress={() => setIsOpen(!isOpen)}
      >
        <Text style={{ fontSize: 11, color: theme.textSecondary || '#666', fontWeight: '500' }}>Bg</Text>
        <View style={{
          width: 16, height: 16,
          borderRadius: 3,
          backgroundColor: slideBackgroundColor,
          borderWidth: 1,
          borderColor: '#d1d5db',
        }} />
        {hasBackgroundImage && (
          <View style={{
            width: 6, height: 6,
            borderRadius: 3,
            backgroundColor: '#3B82F6',
            position: 'absolute',
            top: 2, right: 2,
          }} />
        )}
        <Ionicons name="chevron-down" size={10} color={theme.textSecondary || '#666'} />
      </TouchableOpacity>

      {/* Dropdown Panel */}
      {isOpen && Platform.OS === 'web' && (
        <View style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          marginTop: 4,
          backgroundColor: '#fff',
          borderRadius: 8,
          borderWidth: 1,
          borderColor: '#e5e7eb',
          padding: 12,
          minWidth: 220,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.15,
          shadowRadius: 12,
          elevation: 8,
          zIndex: 9999,
        }}>
          {/* Section: Background Color */}
          <Text style={{ fontSize: 11, fontWeight: '600', color: '#374151', marginBottom: 6 }}>Background Color</Text>
          <View style={{ zIndex: 1300 }}>
            <ColorPickerDropdown
              label=""
              value={slideBackgroundColor}
              onChange={(c) => {
                onUpdateSlideBackground?.(c);
              }}
              themeColors={['#ffffff', '#f5f5f5', '#1a1a2e', '#0f172a', '#1e293b', '#334155']}
              theme={{ ...theme, surface: '#ffffff' }}
              compact={true}
            />
          </View>

          {/* Section: Background Image (only when one exists) */}
          {hasBackgroundImage && (
            <View style={{ marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#f0f0f0' }}>
              <Text style={{ fontSize: 11, fontWeight: '600', color: '#374151', marginBottom: 8 }}>Background Image</Text>

              {/* Opacity Slider */}
              <View style={{ marginBottom: 8 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <Text style={{ fontSize: 11, color: '#6b7280' }}>Opacity</Text>
                  <Text style={{ fontSize: 11, color: '#374151', fontWeight: '500' }}>{opacityPercent}%</Text>
                </View>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={opacityPercent}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10) / 100;
                    onChangeBackgroundOpacity?.(val);
                  }}
                  style={{
                    width: '100%',
                    height: 4,
                    accentColor: theme.primary || '#3B82F6',
                    cursor: 'pointer',
                  }}
                />
              </View>

              {/* Remove Background Image */}
              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                  paddingVertical: 6,
                  paddingHorizontal: 8,
                  borderRadius: 6,
                  backgroundColor: '#fef2f2',
                }}
                onPress={() => {
                  onRemoveBackgroundImage?.();
                  setIsOpen(false);
                }}
              >
                <Ionicons name="trash-outline" size={14} color="#dc2626" />
                <Text style={{ fontSize: 12, color: '#dc2626', fontWeight: '500' }}>Remove Background Image</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </View>
  );
};

export default BackgroundControlDropdown;
