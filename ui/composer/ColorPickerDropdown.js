// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// ColorPickerDropdown.js - MS Word-style color picker with theme colors and standard colors
import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

// Standard colors (like MS Word)
const STANDARD_COLORS = [
    '#C00000', // Dark Red
    '#FF0000', // Red
    '#FFC000', // Orange
    '#FFFF00', // Yellow
    '#92D050', // Light Green
    '#00B050', // Green
    '#00B0F0', // Light Blue
    '#0070C0', // Blue
    '#7030A0', // Purple
    '#000000', // Black
];

// Generate tints and shades of a color
const generateTintsAndShades = (hexColor) => {
    const hex = hexColor.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);

    const tints = [];

    // Generate 5 variations: 2 tints (lighter), original, 2 shades (darker)
    const factors = [0.4, 0.6, 0.8, 1.0, 0.7]; // Mix with white for tints, darken for shades

    // Tints (lighter)
    for (let i = 0; i < 2; i++) {
        const factor = factors[i];
        const tr = Math.round(r + (255 - r) * (1 - factor));
        const tg = Math.round(g + (255 - g) * (1 - factor));
        const tb = Math.round(b + (255 - b) * (1 - factor));
        tints.push(`#${tr.toString(16).padStart(2, '0')}${tg.toString(16).padStart(2, '0')}${tb.toString(16).padStart(2, '0')}`);
    }

    // Original
    tints.push(hexColor);

    // Shades (darker)
    for (let i = 0; i < 2; i++) {
        const factor = 0.7 - (i * 0.25);
        const sr = Math.round(r * factor);
        const sg = Math.round(g * factor);
        const sb = Math.round(b * factor);
        tints.push(`#${sr.toString(16).padStart(2, '0')}${sg.toString(16).padStart(2, '0')}${sb.toString(16).padStart(2, '0')}`);
    }

    return tints;
};

// Default theme colors if none provided
const DEFAULT_THEME_COLORS = [
    '#4472C4', // Blue
    '#ED7D31', // Orange
    '#A5A5A5', // Gray
    '#FFC000', // Gold
    '#5B9BD5', // Light Blue
    '#70AD47', // Green
];

const ColorPickerDropdown = ({
    value = '#000000',
    onChange,
    label = 'Color',
    themeColors = DEFAULT_THEME_COLORS,
    theme = {},
    opacity = 1,
    onOpacityChange,
    showOpacity = false,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);
    const colorInputRef = useRef(null);

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

    const handleColorSelect = (color) => {
        onChange(color);
        setIsOpen(false);
    };

    const handleMoreColors = () => {
        if (colorInputRef.current) {
            colorInputRef.current.click();
        }
    };

    const handleCustomColorChange = (e) => {
        onChange(e.target.value);
        setIsOpen(false);
    };

    // Generate theme color grid with tints/shades
    const themeColorGrid = themeColors.map(color => generateTintsAndShades(color));

    return (
        <View ref={dropdownRef} style={styles.container}>
            {/* Trigger Button */}
            <TouchableOpacity
                style={styles.triggerButton}
                onPress={() => setIsOpen(!isOpen)}
            >
                <Text style={[styles.label, { color: theme.textSecondary || '#666' }]}>{label}</Text>
                <View style={styles.colorPreview}>
                    <View style={[styles.colorSwatch, { backgroundColor: value }]} />
                    <Ionicons
                        name="chevron-down"
                        size={12}
                        color={theme.text || '#333'}
                        style={{ marginLeft: 4 }}
                    />
                </View>
            </TouchableOpacity>

            {/* Dropdown Panel */}
            {isOpen && (
                <View style={[styles.dropdown, { backgroundColor: theme.surface || '#fff', borderColor: theme.border || '#e0e0e0' }]}>

                    {/* Theme Colors Section */}
                    <Text style={[styles.sectionTitle, { color: theme.text || '#333' }]}>Theme Colors</Text>
                    <View style={styles.colorGrid}>
                        {themeColorGrid.map((column, colIndex) => (
                            <View key={colIndex} style={styles.colorColumn}>
                                {column.map((color, rowIndex) => (
                                    <TouchableOpacity
                                        key={`${colIndex}-${rowIndex}`}
                                        style={[
                                            styles.colorCell,
                                            { backgroundColor: color },
                                            value === color && styles.colorCellSelected,
                                        ]}
                                        onPress={() => handleColorSelect(color)}
                                    />
                                ))}
                            </View>
                        ))}
                    </View>

                    {/* Standard Colors Section */}
                    <Text style={[styles.sectionTitle, { color: theme.text || '#333', marginTop: 12 }]}>Standard Colors</Text>
                    <View style={styles.standardColorsRow}>
                        {STANDARD_COLORS.map((color, index) => (
                            <TouchableOpacity
                                key={index}
                                style={[
                                    styles.colorCell,
                                    { backgroundColor: color },
                                    value === color && styles.colorCellSelected,
                                ]}
                                onPress={() => handleColorSelect(color)}
                            />
                        ))}
                    </View>

                    {/* More Colors Button */}
                    {Platform.OS === 'web' && (
                        <>
                            <TouchableOpacity
                                style={styles.moreColorsButton}
                                onPress={handleMoreColors}
                            >
                                <Ionicons name="color-palette-outline" size={16} color={theme.primary || '#4472C4'} />
                                <Text style={[styles.moreColorsText, { color: theme.primary || '#4472C4' }]}>More Colors...</Text>
                            </TouchableOpacity>

                            {/* Hidden native color picker */}
                            <input
                                ref={colorInputRef}
                                type="color"
                                value={value}
                                onChange={handleCustomColorChange}
                                style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}
                            />
                        </>
                    )}

                    {/* Opacity Slider */}
                    {showOpacity && Platform.OS === 'web' && (
                        <View style={styles.opacitySection}>
                            <View style={styles.opacityRow}>
                                <Text style={[styles.sectionTitle, { color: theme.text || '#333', marginBottom: 0 }]}>Opacity</Text>
                                <Text style={[styles.opacityValue, { color: theme.text || '#333' }]}>{Math.round((opacity ?? 1) * 100)}%</Text>
                            </View>
                            <View style={styles.opacitySliderRow}>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={Math.round((opacity ?? 1) * 100)}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value, 10) / 100;
                                        onOpacityChange?.(val);
                                    }}
                                    style={{
                                        width: '100%',
                                        height: 4,
                                        accentColor: theme.primary || '#4472C4',
                                        cursor: 'pointer',
                                    }}
                                />
                            </View>
                        </View>
                    )}
                </View>
            )}
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        position: 'relative',
        zIndex: 1000,
    },
    triggerButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
    },
    label: {
        fontSize: 11,
    },
    colorPreview: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    colorSwatch: {
        width: 24,
        height: 24,
        borderRadius: 4,
        borderWidth: 1,
        borderColor: '#ccc',
    },
    dropdown: {
        position: 'absolute',
        top: '100%',
        left: 0,
        marginTop: 4,
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        minWidth: 200,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 12,
        elevation: 8,
        zIndex: 1001,
    },
    sectionTitle: {
        fontSize: 11,
        fontWeight: '600',
        marginBottom: 8,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    colorGrid: {
        flexDirection: 'row',
        gap: 2,
    },
    colorColumn: {
        flexDirection: 'column',
        gap: 2,
    },
    standardColorsRow: {
        flexDirection: 'row',
        gap: 2,
        flexWrap: 'wrap',
    },
    colorCell: {
        width: 22,
        height: 22,
        borderRadius: 2,
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.1)',
    },
    colorCellSelected: {
        borderWidth: 2,
        borderColor: '#000',
    },
    moreColorsButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginTop: 12,
        paddingTop: 12,
        borderTopWidth: 1,
        borderTopColor: '#e0e0e0',
    },
    moreColorsText: {
        fontSize: 13,
        fontWeight: '500',
    },
    opacitySection: {
        marginTop: 12,
        paddingTop: 12,
        borderTopWidth: 1,
        borderTopColor: '#e0e0e0',
    },
    opacityRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
    },
    opacityValue: {
        fontSize: 12,
        fontWeight: '600',
    },
    opacitySliderRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
});

export default ColorPickerDropdown;
