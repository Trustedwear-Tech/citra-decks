// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * AIEditScopeSelector - Radio button selector for AI edit scope
 * ==============================================================
 * Replaces the ambiguous toggle button with clear labeled radio options.
 * Used in PresentationComposer, PrintableComposer, and ReportComposer.
 * 
 * 3 options:
 *   - 'element'  : Edit only the selected element(s) — shown only when something is selected
 *   - 'page'     : Edit the current page/slide
 *   - 'all'      : AI finds & edits relevant pages
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons, Ionicons } from '@expo/vector-icons';

const AIEditScopeSelector = ({
  scope = 'page',           // 'element' | 'page' | 'all'
  onScopeChange,            // (newScope: string) => void
  hasSelection = false,     // Whether element(s) are selected (Pres/Printable) or text is selected (Report)
  selectedElementLabel = '',// e.g. "Text Box", "2 Elements", "selected text"
  disabled = false,
  pageLabel = 'Slide',      // 'Slide' for presentations, 'Page' for printable/report
  theme = null,             // Optional theme object
}) => {
  const isDark = theme?.isDark || false;

  const options = [
    {
      value: 'element',
      label: selectedElementLabel || 'Selection',
      icon: 'crop-square',
      iconLib: 'material',
      visible: hasSelection,
      activeColor: '#16A34A',
      activeBg: isDark ? '#14532D' : '#DCFCE7',
      activeBorder: isDark ? '#22C55E' : '#86EFAC',
    },
    {
      value: 'page',
      label: `This ${pageLabel}`,
      icon: 'description',
      iconLib: 'material',
      visible: true,
      activeColor: '#2563EB',
      activeBg: isDark ? '#1E3A5F' : '#DBEAFE',
      activeBorder: isDark ? '#3B82F6' : '#93C5FD',
    },
    {
      value: 'all',
      label: `All ${pageLabel}s`,
      icon: 'library-books',
      iconLib: 'material',
      visible: true,
      activeColor: '#7C3AED',
      activeBg: isDark ? '#3B1F6E' : '#EDE7F6',
      activeBorder: isDark ? '#A78BFA' : '#B39DDB',
    },
  ];

  const visibleOptions = options.filter(o => o.visible);

  return (
    <View style={scopeStyles.container}>
      <View style={scopeStyles.optionsRow}>
        {visibleOptions.map((option) => {
          const isSelected = scope === option.value;
          const inactiveColor = isDark ? '#9CA3AF' : '#6B7280';
          const inactiveBg = isDark ? '#1F2937' : '#F9FAFB';
          const inactiveBorder = isDark ? '#374151' : '#E5E7EB';

          return (
            <TouchableOpacity
              key={option.value}
              style={[
                scopeStyles.option,
                {
                  backgroundColor: isSelected ? option.activeBg : inactiveBg,
                  borderColor: isSelected ? option.activeBorder : inactiveBorder,
                  opacity: disabled ? 0.5 : 1,
                },
              ]}
              onPress={() => !disabled && onScopeChange(option.value)}
              activeOpacity={0.7}
              disabled={disabled}
            >
              {/* Radio Circle */}
              <View style={[
                scopeStyles.radio,
                {
                  borderColor: isSelected ? option.activeColor : (isDark ? '#6B7280' : '#D1D5DB'),
                },
              ]}>
                {isSelected && (
                  <View style={[scopeStyles.radioInner, { backgroundColor: option.activeColor }]} />
                )}
              </View>

              {/* Icon */}
              <MaterialIcons
                name={option.icon}
                size={14}
                color={isSelected ? option.activeColor : inactiveColor}
              />

              {/* Label */}
              <Text
                style={[
                  scopeStyles.label,
                  { color: isSelected ? option.activeColor : inactiveColor },
                ]}
                numberOfLines={1}
              >
                {option.label}
              </Text>

              {/* Sparkle for "All" mode */}
              {option.value === 'all' && isSelected && (
                <Ionicons name="sparkles" size={10} color={option.activeColor} />
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Smart mode hint for All Pages */}
      {scope === 'all' && (
        <View style={[scopeStyles.hint, { 
          backgroundColor: isDark ? '#2D1B69' : '#FAF5FF',
          borderColor: isDark ? '#6D28D9' : '#E9D5FF',
        }]}>
          <Ionicons name="sparkles" size={11} color="#7C3AED" />
          <Text style={scopeStyles.hintText}>
            AI will find and edit only relevant {pageLabel.toLowerCase()}s
          </Text>
        </View>
      )}
    </View>
  );
};

const scopeStyles = StyleSheet.create({
  container: {
    gap: 6,
    marginBottom: 8,
  },
  optionsRow: {
    flexDirection: 'column',
    gap: 6,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 7,
    borderRadius: 8,
    borderWidth: 1.5,
    cursor: 'pointer',
  },
  radio: {
    width: 14,
    height: 14,
    borderRadius: 7,
    borderWidth: 2,
    justifyContent: 'center',
    alignItems: 'center',
  },
  radioInner: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
  label: {
    fontSize: 11,
    fontWeight: '600',
    flex: 1,
  },
  hint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 6,
    borderWidth: 1,
  },
  hintText: {
    fontSize: 10,
    color: '#7C3AED',
    flex: 1,
  },
});

export default AIEditScopeSelector;
