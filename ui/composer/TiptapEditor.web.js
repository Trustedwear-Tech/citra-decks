// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// TiptapEditor.web.js - Web-specific implementation with standard imports
import React, { useEffect, useCallback, forwardRef, useImperativeHandle, useState, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { getStyleCSS } from './ReportStylePicker';

// Standard top-level imports for Web
// Tiptap Extensions
import { useEditor, EditorContent, ReactNodeViewRenderer, BubbleMenu } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import Underline from '@tiptap/extension-underline';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
// Text Styling Extensions
import TextStyle from '@tiptap/extension-text-style';
import { Color } from '@tiptap/extension-color';
import Highlight from '@tiptap/extension-highlight';
import FontFamily from '@tiptap/extension-font-family';
import TextAlign from '@tiptap/extension-text-align';
// Collaboration Imports
import Collaboration from '@tiptap/extension-collaboration';
import CollaborationCursor from '@tiptap/extension-collaboration-cursor';
import { mergeAttributes, Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

// ═══════════════════════════════════════════════════════════════════
// TEXT STYLING CONSTANTS
// ═══════════════════════════════════════════════════════════════════

// Color palette for text and highlight
const COLOR_PRESETS = [
    // Row 1 - Neutrals
    { color: '#000000', name: 'Black' },
    { color: '#374151', name: 'Gray 700' },
    { color: '#6B7280', name: 'Gray 500' },
    { color: '#9CA3AF', name: 'Gray 400' },
    { color: '#D1D5DB', name: 'Gray 300' },
    { color: '#FFFFFF', name: 'White' },
    // Row 2 - Primary colors
    { color: '#EF4444', name: 'Red' },
    { color: '#F97316', name: 'Orange' },
    { color: '#EAB308', name: 'Yellow' },
    { color: '#22C55E', name: 'Green' },
    { color: '#3B82F6', name: 'Blue' },
    { color: '#8B5CF6', name: 'Purple' },
    // Row 3 - Lighter variants
    { color: '#FCA5A5', name: 'Light Red' },
    { color: '#FDBA74', name: 'Light Orange' },
    { color: '#FDE047', name: 'Light Yellow' },
    { color: '#86EFAC', name: 'Light Green' },
    { color: '#93C5FD', name: 'Light Blue' },
    { color: '#C4B5FD', name: 'Light Purple' },
];

const HIGHLIGHT_PRESETS = [
    { color: '#FEF08A', name: 'Yellow' },
    { color: '#BBF7D0', name: 'Green' },
    { color: '#BFDBFE', name: 'Blue' },
    { color: '#FBCFE8', name: 'Pink' },
    { color: '#FED7AA', name: 'Orange' },
    { color: '#E9D5FF', name: 'Purple' },
    { color: '#FECACA', name: 'Red' },
    { color: '#E5E7EB', name: 'Gray' },
];

// Google Fonts - popular web-safe options
const FONT_FAMILIES = [
    { id: 'default', name: 'Default', family: 'Georgia, serif', isSystem: true },
    { id: 'arial', name: 'Arial', family: 'Arial, Helvetica, sans-serif', isSystem: true },
    { id: 'times', name: 'Times New Roman', family: '"Times New Roman", Times, serif', isSystem: true },
    { id: 'courier', name: 'Courier New', family: '"Courier New", Courier, monospace', isSystem: true },
    // Google Fonts
    { id: 'roboto', name: 'Roboto', family: '"Roboto", sans-serif', googleFont: 'Roboto:wght@400;500;700' },
    { id: 'opensans', name: 'Open Sans', family: '"Open Sans", sans-serif', googleFont: 'Open+Sans:wght@400;600;700' },
    { id: 'lato', name: 'Lato', family: '"Lato", sans-serif', googleFont: 'Lato:wght@400;700' },
    { id: 'montserrat', name: 'Montserrat', family: '"Montserrat", sans-serif', googleFont: 'Montserrat:wght@400;500;600;700' },
    { id: 'poppins', name: 'Poppins', family: '"Poppins", sans-serif', googleFont: 'Poppins:wght@400;500;600;700' },
    { id: 'playfair', name: 'Playfair Display', family: '"Playfair Display", serif', googleFont: 'Playfair+Display:wght@400;500;600;700' },
    { id: 'merriweather', name: 'Merriweather', family: '"Merriweather", serif', googleFont: 'Merriweather:wght@400;700' },
    { id: 'inter', name: 'Inter', family: '"Inter", sans-serif', googleFont: 'Inter:wght@400;500;600;700' },
    { id: 'nunito', name: 'Nunito', family: '"Nunito", sans-serif', googleFont: 'Nunito:wght@400;600;700' },
    { id: 'raleway', name: 'Raleway', family: '"Raleway", sans-serif', googleFont: 'Raleway:wght@400;500;600;700' },
];

// Track loaded Google Fonts to avoid duplicates
const loadedFonts = new Set();

// Dynamic Google Font loader
const loadGoogleFont = (fontConfig) => {
    if (!fontConfig.googleFont || loadedFonts.has(fontConfig.id)) return;

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `https://fonts.googleapis.com/css2?family=${fontConfig.googleFont}&display=swap`;
    document.head.appendChild(link);
    loadedFonts.add(fontConfig.id);
    console.log(`[TipTap] Loaded Google Font: ${fontConfig.name}`);
};

import ImageResizeComponent from './ImageResizeComponent';
import EmbedNode from './extensions/EmbedNode';

// Media Modals
import VideoSourceModal from './VideoSourceModal';
import EmbedSourceModal from './EmbedSourceModal';

// CustomImage definition using the resize component
const CustomImage = Image.extend({
    addAttributes() {
        return {
            ...this.parent?.(),
            width: {
                default: null,
                parseHTML: element => element.getAttribute('width') || element.style?.width || null,
                renderHTML: attributes => {
                    if (!attributes.width) return {};
                    return { width: attributes.width };
                },
            },
            'data-chart-config': {
                default: null,
                parseHTML: element => element.getAttribute('data-chart-config'),
                renderHTML: attributes => {
                    if (!attributes['data-chart-config']) return {};
                    return { 'data-chart-config': attributes['data-chart-config'] };
                },
            },
            'data-user-media': {
                default: null,
                parseHTML: element => element.getAttribute('data-user-media'),
                renderHTML: attributes => {
                    if (!attributes['data-user-media']) return {};
                    return { 'data-user-media': attributes['data-user-media'] };
                },
            },
        };
    },
    addStorage() {
        return { onChartEdit: null };
    },
    addNodeView() {
        return ReactNodeViewRenderer(ImageResizeComponent);
    },
});

// Toolbar Components
const ToolbarButton = ({ icon, onPress, isActive, disabled, title }) => (
    <TouchableOpacity
        onPress={onPress}
        disabled={disabled}
        style={[
            styles.toolbarButton,
            isActive && styles.toolbarButtonActive,
            disabled && styles.toolbarButtonDisabled
        ]}
        accessibilityLabel={title}
        // Web specific tooltip
        {...{ title }}
    >
        <MaterialIcons name={icon} size={20} color={isActive ? '#1565C0' : '#555'} />
    </TouchableOpacity>
);

const ToolbarDivider = () => <View style={styles.toolbarDivider} />;
// Table Size Picker Popover Component
const TableSizePicker = ({ visible, onSelect, onClose, anchorPosition }) => {
    const [hoverSize, setHoverSize] = useState({ rows: 0, cols: 0 });
    const maxRows = 6;
    const maxCols = 6;

    if (!visible) return null;

    return (
        <>
            {/* Backdrop */}
            <TouchableOpacity
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 9999,
                    backgroundColor: 'transparent',
                }}
                onPress={onClose}
                activeOpacity={1}
            />
            {/* Popover - using fixed position with screen coordinates */}
            <View style={{
                position: 'fixed',
                top: anchorPosition?.top || 100,
                left: anchorPosition?.left || 100,
                backgroundColor: '#fff',
                borderRadius: 8,
                padding: 12,
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.3,
                shadowRadius: 12,
                elevation: 10,
                zIndex: 10000,
                borderWidth: 1,
                borderColor: '#e0e0e0',
            }}>
                <Text style={{ fontSize: 12, color: '#666', marginBottom: 8, textAlign: 'center' }}>
                    {hoverSize.rows > 0 ? `${hoverSize.rows} × ${hoverSize.cols}` : 'Select table size'}
                </Text>
                <View style={{ flexDirection: 'column', gap: 2 }}>
                    {Array.from({ length: maxRows }, (_, rowIndex) => (
                        <View key={rowIndex} style={{ flexDirection: 'row', gap: 2 }}>
                            {Array.from({ length: maxCols }, (_, colIndex) => {
                                const isHighlighted = rowIndex < hoverSize.rows && colIndex < hoverSize.cols;
                                return (
                                    <TouchableOpacity
                                        key={colIndex}
                                        onPress={() => onSelect(rowIndex + 1, colIndex + 1)}
                                        onMouseEnter={() => setHoverSize({ rows: rowIndex + 1, cols: colIndex + 1 })}
                                        style={{
                                            width: 20,
                                            height: 20,
                                            backgroundColor: isHighlighted ? '#2196F3' : '#f0f0f0',
                                            borderRadius: 2,
                                            borderWidth: 1,
                                            borderColor: isHighlighted ? '#1976D2' : '#ddd',
                                        }}
                                    />
                                );
                            })}
                        </View>
                    ))}
                </View>
                <Text style={{ fontSize: 10, color: '#999', marginTop: 8, textAlign: 'center' }}>
                    Click to insert • Max 6×6
                </Text>
            </View>
        </>
    );
};

// Link Input Popover Component
const LinkInputPopover = ({ visible, onApply, onClose, anchorPosition, initialUrl = '' }) => {
    const [url, setUrl] = useState(initialUrl);
    const inputRef = React.useRef(null);

    // Focus input when popover opens
    React.useEffect(() => {
        if (visible && inputRef.current) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
        // Reset URL when opening
        if (visible) {
            setUrl(initialUrl);
        }
    }, [visible, initialUrl]);

    if (!visible) return null;

    const handleApply = () => {
        if (url.trim()) {
            // Auto-add https:// if no protocol
            let finalUrl = url.trim();
            if (!/^https?:\/\//i.test(finalUrl)) {
                finalUrl = 'https://' + finalUrl;
            }
            onApply(finalUrl);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleApply();
        } else if (e.key === 'Escape') {
            onClose();
        }
    };

    return (
        <>
            {/* Backdrop */}
            <TouchableOpacity
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 9999,
                    backgroundColor: 'transparent',
                }}
                onPress={onClose}
                activeOpacity={1}
            />
            {/* Popover */}
            <View style={{
                position: 'fixed',
                top: anchorPosition?.top || 100,
                left: anchorPosition?.left || 100,
                backgroundColor: '#fff',
                borderRadius: 8,
                padding: 16,
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.3,
                shadowRadius: 12,
                elevation: 10,
                zIndex: 10000,
                borderWidth: 1,
                borderColor: '#e0e0e0',
                minWidth: 280,
            }}>
                <Text style={{ fontSize: 14, fontWeight: '600', color: '#333', marginBottom: 12 }}>
                    Insert Link
                </Text>
                <Text style={{ fontSize: 12, color: '#666', marginBottom: 6 }}>
                    URL
                </Text>
                <input
                    ref={inputRef}
                    type="text"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="https://example.com"
                    style={{
                        width: '100%',
                        padding: '10px 12px',
                        fontSize: 14,
                        borderRadius: 6,
                        border: '1px solid #ddd',
                        outline: 'none',
                        boxSizing: 'border-box',
                        marginBottom: 12,
                    }}
                />
                <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8 }}>
                    <TouchableOpacity
                        onPress={onClose}
                        style={{
                            paddingVertical: 8,
                            paddingHorizontal: 16,
                            borderRadius: 6,
                            backgroundColor: '#f0f0f0',
                        }}
                    >
                        <Text style={{ fontSize: 13, color: '#666' }}>Cancel</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                        onPress={handleApply}
                        style={{
                            paddingVertical: 8,
                            paddingHorizontal: 16,
                            borderRadius: 6,
                            backgroundColor: '#2196F3',
                            opacity: url.trim() ? 1 : 0.5,
                        }}
                        disabled={!url.trim()}
                    >
                        <Text style={{ fontSize: 13, color: '#fff', fontWeight: '500' }}>Apply</Text>
                    </TouchableOpacity>
                </View>
                <Text style={{ fontSize: 10, color: '#999', marginTop: 10, textAlign: 'center' }}>
                    Select text first, then add a link • Press Enter to apply
                </Text>
            </View>
        </>
    );
};

// ═══════════════════════════════════════════════════════════════════
// COLOR PICKER POPOVER
// ═══════════════════════════════════════════════════════════════════
const ColorPickerPopover = ({
    visible,
    onClose,
    anchorPosition,
    onSelectColor,
    onSelectHighlight,
    onClearColor,
    onClearHighlight,
    currentColor,
    currentHighlight,
    mode = 'text' // 'text' or 'highlight'
}) => {
    const [customColor, setCustomColor] = useState('');
    const [activeTab, setActiveTab] = useState(mode);

    if (!visible) return null;

    const colors = activeTab === 'text' ? COLOR_PRESETS : HIGHLIGHT_PRESETS;
    const currentValue = activeTab === 'text' ? currentColor : currentHighlight;

    const handleColorSelect = (color) => {
        if (activeTab === 'text') {
            onSelectColor(color);
        } else {
            onSelectHighlight(color);
        }
        onClose();
    };

    const handleClear = () => {
        if (activeTab === 'text') {
            onClearColor();
        } else {
            onClearHighlight();
        }
        onClose();
    };

    const handleCustomColorApply = () => {
        if (customColor && /^#[0-9A-Fa-f]{6}$/.test(customColor)) {
            handleColorSelect(customColor);
        }
    };

    return (
        <>
            {/* Backdrop */}
            <TouchableOpacity
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 9999,
                    backgroundColor: 'transparent',
                }}
                onPress={onClose}
                activeOpacity={1}
            />
            {/* Popover */}
            <View style={{
                position: 'fixed',
                top: anchorPosition?.top || 100,
                left: anchorPosition?.left || 100,
                backgroundColor: '#fff',
                borderRadius: 10,
                padding: 12,
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.25,
                shadowRadius: 12,
                elevation: 10,
                zIndex: 10000,
                borderWidth: 1,
                borderColor: '#e0e0e0',
                minWidth: 220,
            }}>
                {/* Tabs */}
                <View style={{ flexDirection: 'row', marginBottom: 12, gap: 4 }}>
                    <TouchableOpacity
                        onPress={() => setActiveTab('text')}
                        style={{
                            flex: 1,
                            paddingVertical: 8,
                            paddingHorizontal: 12,
                            borderRadius: 6,
                            backgroundColor: activeTab === 'text' ? '#2196F3' : '#f0f0f0',
                            alignItems: 'center',
                        }}
                    >
                        <Text style={{
                            fontSize: 12,
                            fontWeight: '600',
                            color: activeTab === 'text' ? '#fff' : '#666'
                        }}>
                            Text Color
                        </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                        onPress={() => setActiveTab('highlight')}
                        style={{
                            flex: 1,
                            paddingVertical: 8,
                            paddingHorizontal: 12,
                            borderRadius: 6,
                            backgroundColor: activeTab === 'highlight' ? '#2196F3' : '#f0f0f0',
                            alignItems: 'center',
                        }}
                    >
                        <Text style={{
                            fontSize: 12,
                            fontWeight: '600',
                            color: activeTab === 'highlight' ? '#fff' : '#666'
                        }}>
                            Highlight
                        </Text>
                    </TouchableOpacity>
                </View>

                {/* Color Grid */}
                <View style={{
                    flexDirection: 'row',
                    flexWrap: 'wrap',
                    gap: 6,
                    marginBottom: 12,
                }}>
                    {colors.map((item, index) => (
                        <TouchableOpacity
                            key={index}
                            onPress={() => handleColorSelect(item.color)}
                            style={{
                                width: 28,
                                height: 28,
                                borderRadius: 6,
                                backgroundColor: item.color,
                                borderWidth: currentValue === item.color ? 2 : 1,
                                borderColor: currentValue === item.color ? '#2196F3' :
                                    (item.color === '#FFFFFF' ? '#ddd' : 'transparent'),
                                shadowColor: item.color === '#FFFFFF' ? '#000' : 'transparent',
                                shadowOffset: { width: 0, height: 1 },
                                shadowOpacity: 0.1,
                                shadowRadius: 2,
                            }}
                            title={item.name}
                        />
                    ))}
                </View>

                {/* Custom Color Input */}
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
                    <input
                        type="text"
                        value={customColor}
                        onChange={(e) => setCustomColor(e.target.value)}
                        placeholder="#FF5733"
                        style={{
                            flex: 1,
                            padding: '8px 10px',
                            fontSize: 13,
                            borderRadius: 6,
                            border: '1px solid #ddd',
                            outline: 'none',
                            fontFamily: 'monospace',
                        }}
                    />
                    <TouchableOpacity
                        onPress={handleCustomColorApply}
                        style={{
                            paddingHorizontal: 12,
                            paddingVertical: 8,
                            borderRadius: 6,
                            backgroundColor: '#2196F3',
                            opacity: /^#[0-9A-Fa-f]{6}$/.test(customColor) ? 1 : 0.5,
                        }}
                        disabled={!/^#[0-9A-Fa-f]{6}$/.test(customColor)}
                    >
                        <Text style={{ fontSize: 12, color: '#fff', fontWeight: '500' }}>Apply</Text>
                    </TouchableOpacity>
                </View>

                {/* Clear Button */}
                <TouchableOpacity
                    onPress={handleClear}
                    style={{
                        paddingVertical: 8,
                        borderRadius: 6,
                        backgroundColor: '#f5f5f5',
                        alignItems: 'center',
                        borderWidth: 1,
                        borderColor: '#e0e0e0',
                    }}
                >
                    <Text style={{ fontSize: 12, color: '#666' }}>
                        {activeTab === 'text' ? 'Remove Text Color' : 'Remove Highlight'}
                    </Text>
                </TouchableOpacity>
            </View>
        </>
    );
};

// ═══════════════════════════════════════════════════════════════════
// FONT FAMILY POPOVER
// ═══════════════════════════════════════════════════════════════════
const FontFamilyPopover = ({ visible, onClose, anchorPosition, onSelectFont, currentFont }) => {
    if (!visible) return null;

    const handleFontSelect = (fontConfig) => {
        // Load Google Font if needed
        if (fontConfig.googleFont) {
            loadGoogleFont(fontConfig);
        }
        onSelectFont(fontConfig.family);
        onClose();
    };

    return (
        <>
            {/* Backdrop */}
            <TouchableOpacity
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 9999,
                    backgroundColor: 'transparent',
                }}
                onPress={onClose}
                activeOpacity={1}
            />
            {/* Popover */}
            <View style={{
                position: 'fixed',
                top: anchorPosition?.top || 100,
                left: anchorPosition?.left || 100,
                backgroundColor: '#fff',
                borderRadius: 10,
                padding: 8,
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.25,
                shadowRadius: 12,
                elevation: 10,
                zIndex: 10000,
                borderWidth: 1,
                borderColor: '#e0e0e0',
                maxHeight: 320,
                width: 200,
            }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: '#666', padding: 8, paddingBottom: 4 }}>
                    Font Family
                </Text>
                <ScrollView style={{ maxHeight: 280 }} showsVerticalScrollIndicator={false}>
                    {FONT_FAMILIES.map((font) => {
                        const isSelected = currentFont === font.family;
                        return (
                            <TouchableOpacity
                                key={font.id}
                                onPress={() => handleFontSelect(font)}
                                style={{
                                    paddingVertical: 10,
                                    paddingHorizontal: 12,
                                    borderRadius: 6,
                                    backgroundColor: isSelected ? '#e3f2fd' : 'transparent',
                                    marginBottom: 2,
                                }}
                            >
                                <Text style={{
                                    fontSize: 14,
                                    color: isSelected ? '#1565C0' : '#333',
                                    fontFamily: font.isSystem ? font.family : undefined,
                                    fontWeight: isSelected ? '600' : '400',
                                }}>
                                    {font.name}
                                </Text>
                                {font.googleFont && (
                                    <Text style={{ fontSize: 10, color: '#999', marginTop: 2 }}>
                                        Google Font
                                    </Text>
                                )}
                            </TouchableOpacity>
                        );
                    })}
                </ScrollView>

                {/* Clear Font */}
                <TouchableOpacity
                    onPress={() => { onSelectFont(null); onClose(); }}
                    style={{
                        paddingVertical: 8,
                        marginTop: 4,
                        borderRadius: 6,
                        backgroundColor: '#f5f5f5',
                        alignItems: 'center',
                        borderTopWidth: 1,
                        borderTopColor: '#eee',
                    }}
                >
                    <Text style={{ fontSize: 12, color: '#666' }}>Reset to Default</Text>
                </TouchableOpacity>
            </View>
        </>
    );
};

// ═══════════════════════════════════════════════════════════════════
// TEXT ALIGN POPOVER
// ═══════════════════════════════════════════════════════════════════
const TextAlignPopover = ({ visible, onClose, anchorPosition, onSelectAlign, currentAlign }) => {
    if (!visible) return null;

    const alignments = [
        { id: 'left', icon: 'format-align-left', label: 'Left' },
        { id: 'center', icon: 'format-align-center', label: 'Center' },
        { id: 'right', icon: 'format-align-right', label: 'Right' },
        { id: 'justify', icon: 'format-align-justify', label: 'Justify' },
    ];

    return (
        <>
            {/* Backdrop */}
            <TouchableOpacity
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 9999,
                    backgroundColor: 'transparent',
                }}
                onPress={onClose}
                activeOpacity={1}
            />
            {/* Popover */}
            <View style={{
                position: 'fixed',
                top: anchorPosition?.top || 100,
                left: anchorPosition?.left || 100,
                backgroundColor: '#fff',
                borderRadius: 10,
                padding: 8,
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.25,
                shadowRadius: 12,
                elevation: 10,
                zIndex: 10000,
                borderWidth: 1,
                borderColor: '#e0e0e0',
                flexDirection: 'row',
                gap: 4,
            }}>
                {alignments.map((align) => (
                    <TouchableOpacity
                        key={align.id}
                        onPress={() => { onSelectAlign(align.id); onClose(); }}
                        style={{
                            padding: 10,
                            borderRadius: 6,
                            backgroundColor: currentAlign === align.id ? '#e3f2fd' : 'transparent',
                        }}
                        title={align.label}
                    >
                        <MaterialIcons
                            name={align.icon}
                            size={20}
                            color={currentAlign === align.id ? '#1565C0' : '#555'}
                        />
                    </TouchableOpacity>
                ))}
            </View>
        </>
    );
};

const TiptapEditor = forwardRef(({
    content,
    onContentChange,
    onSelectionChange,
    placeholder,
    editable = true,
    theme = {},
    reportStyle = 'ai_auto', // NEW: Report style ID for dynamic CSS
    ydoc,       // NEW: Y.Doc instance
    provider,   // NEW: WebsocketProvider instance
    user,       // NEW: Current user info
    showToolbar = true, // Whether to render the built-in toolbar (false when shared ComposerToolbar is used)
    onChartEdit, // Callback when user wants to edit a chart image: (chartConfig, nodePos) => void
}, ref) => {
    console.log('🌐 [TIPTAP] Web Component Rendering. Collab enabled:', !!provider);

    // State for table size picker
    const [showTablePicker, setShowTablePicker] = useState(false);
    const [tablePickerAnchor, setTablePickerAnchor] = useState(null);
    const tableButtonRef = React.useRef(null);

    // State for link input popover
    const [showLinkPopover, setShowLinkPopover] = useState(false);
    const [linkPopoverAnchor, setLinkPopoverAnchor] = useState(null);
    const [currentLinkUrl, setCurrentLinkUrl] = useState('');

    // State for media modals
    const [showVideoModal, setShowVideoModal] = useState(false);
    const [showEmbedModal, setShowEmbedModal] = useState(false);

    // State for text styling popovers
    const [showColorPicker, setShowColorPicker] = useState(false);
    const [colorPickerAnchor, setColorPickerAnchor] = useState(null);
    const [showFontPicker, setShowFontPicker] = useState(false);
    const [fontPickerAnchor, setFontPickerAnchor] = useState(null);
    const [showAlignPicker, setShowAlignPicker] = useState(false);
    const [alignPickerAnchor, setAlignPickerAnchor] = useState(null);

    // Default theme for modals
    const modalTheme = {
        surface: theme.surface || '#ffffff',
        background: theme.background || '#f8f9fa',
        text: theme.text || '#1a1a1a',
        textSecondary: theme.textSecondary || '#666666',
        border: theme.border || '#e0e0e0',
        primary: theme.primary || '#3b82f6',
        ...theme
    };

    // Extension: persist selection highlight when editor loses focus
    const SelectionPersist = Extension.create({
        name: 'selectionPersist',
        addProseMirrorPlugins() {
            const pluginKey = new PluginKey('selectionPersist');
            return [
                new Plugin({
                    key: pluginKey,
                    state: {
                        init() { return { hasFocus: true }; },
                        apply(tr, prev) {
                            const focusMeta = tr.getMeta('selectionPersistFocus');
                            if (focusMeta !== undefined) return { hasFocus: focusMeta };
                            return prev;
                        },
                    },
                    props: {
                        handleDOMEvents: {
                            blur(view) {
                                view.dispatch(view.state.tr.setMeta('selectionPersistFocus', false));
                                return false;
                            },
                            focus(view) {
                                view.dispatch(view.state.tr.setMeta('selectionPersistFocus', true));
                                return false;
                            },
                        },
                        decorations(state) {
                            const pluginState = pluginKey.getState(state);
                            if (pluginState?.hasFocus) return DecorationSet.empty;
                            const { from, to } = state.selection;
                            if (from === to) return DecorationSet.empty;
                            return DecorationSet.create(state.doc, [
                                Decoration.inline(from, to, { class: 'selection-persist' }),
                            ]);
                        },
                    },
                }),
            ];
        },
    });

    // Extensions configuration
    const extensions = [
        StarterKit.configure({
            heading: { levels: [1, 2, 3, 4] },
            // Disable history if using collaboration (Yjs handles history)
            history: !provider
        }),
        SelectionPersist,
        Table.configure({
            resizable: true,
            HTMLAttributes: { class: 'tiptap-table' }
        }),
        TableRow, TableCell, TableHeader, Underline,
        Link.configure({
            openOnClick: false,
            HTMLAttributes: { class: 'tiptap-link' }
        }),
        CustomImage.configure({ inline: true, allowBase64: true }),
        EmbedNode,
        Placeholder.configure({ placeholder: placeholder || 'Start writing...' }),
        // Text Styling Extensions
        TextStyle,
        Color,
        Highlight.configure({ multicolor: true }),
        FontFamily,
        TextAlign.configure({
            types: ['heading', 'paragraph'],
            alignments: ['left', 'center', 'right', 'justify'],
        }),
    ];

    // Add Collaboration Extensions if provider exists
    if (provider && ydoc) {
        extensions.push(
            Collaboration.configure({
                document: ydoc,
            }),
            CollaborationCursor.configure({
                provider: provider,
                user: {
                    name: user?.name || 'Anonymous',
                    color: user?.color || '#f783ac'
                }
            })
        );
    }

    // Initialize editor with extensions
    const editor = useEditor({
        extensions: extensions,
        editorProps: {
            handlePaste: (view, event, slice) => {
                console.log('🔍 [TIPTAP] Paste event detected');

                // First check for text content (might be iframe HTML)
                const text = (event.clipboardData || event.originalEvent.clipboardData).getData('text/plain');
                console.log('📋 [TIPTAP] Pasted text:', text?.substring(0, 100));

                // Check if pasted content is iframe HTML
                if (text && text.trim().startsWith('<iframe')) {
                    console.log('🎬 [TIPTAP] Detected iframe HTML paste');
                    event.preventDefault();

                    // Extract src from iframe
                    const srcMatch = text.match(/<iframe[^>]+src=["']([^"']+)["']/i);
                    if (srcMatch) {
                        const embedUrl = srcMatch[1];
                        console.log('✅ [TIPTAP] Extracted embed URL:', embedUrl);

                        // Import embed metadata service dynamically
                        import('./utils/embedMetadataService').then(({ fetchEmbedMetadata }) => {
                            fetchEmbedMetadata(embedUrl).then((metadata) => {
                                console.log('📦 [TIPTAP] Got metadata:', metadata);
                                const { schema } = view.state;
                                if (schema.nodes.embed) {
                                    const embedNode = schema.nodes.embed.create({
                                        src: metadata.url || embedUrl,
                                        embedType: metadata.videoType || 'webpage',
                                        provider: metadata.provider || 'Web',
                                        title: metadata.title || 'Embedded Content',
                                        thumbnail: metadata.thumbnail_url,
                                        html: metadata.html,
                                        videoId: metadata.videoId,
                                        width: metadata.width || 640,
                                        height: metadata.height || 360,
                                    });
                                    const transaction = view.state.tr.replaceSelectionWith(embedNode);
                                    view.dispatch(transaction);
                                    console.log('✅ [TIPTAP] Embed node inserted');
                                }
                            }).catch((err) => {
                                console.error('❌ [TIPTAP] Failed to fetch metadata:', err);
                            });
                        });

                        return true;
                    } else {
                        console.warn('⚠️ [TIPTAP] Could not extract src from iframe HTML');
                    }
                }

                // Handle image paste
                const items = (event.clipboardData || event.originalEvent.clipboardData).items;
                let handled = false;
                for (const item of items) {
                    if (item.type.indexOf('image') === 0) {
                        event.preventDefault();
                        handled = true;
                        const file = item.getAsFile();
                        const reader = new FileReader();
                        reader.onload = (readerEvent) => {
                            const content = readerEvent.target.result;
                            if (content) {
                                const { schema } = view.state;
                                const node = schema.nodes.image.create({ src: content, width: '100%', 'data-user-media': 'true' });
                                const transaction = view.state.tr.replaceSelectionWith(node);
                                view.dispatch(transaction);
                            }
                        };
                        reader.readAsDataURL(file);
                        break;
                    }
                }
                return handled;
            }
        },
        content: content || '', // Note: Content is synced via Yjs if collab enabled
        editable: editable,
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            onContentChange?.(html);
        },
        onSelectionUpdate: ({ editor }) => {
            const { from, to, empty } = editor.state.selection;
            const { node } = editor.view.state.selection; // Get NodeSelection if applicable

            let selectedText = '';
            let selectedNodeAttributes = null;
            let selectedNodeType = null;

            // Check for text selection
            if (!empty) {
                selectedText = editor.state.doc.textBetween(from, to, ' ');
            }

            // Check for Node selection (Images, etc.)
            if (node) {
                selectedNodeType = node.type.name;
                // Safely clone node.attrs to a plain object to avoid
                // "Cannot convert object to primitive value" errors
                // when the attrs object is logged or serialized
                try {
                    selectedNodeAttributes = JSON.parse(JSON.stringify(node.attrs));
                } catch (e) {
                    selectedNodeAttributes = { ...node.attrs };
                }
                // If it's an image, use alt text as "selected text" for context if regular text is empty
                if (selectedNodeType === 'image' && !selectedText) {
                    selectedText = node.attrs.alt || '';
                }
            }

            onSelectionChange?.({
                from,
                to,
                empty,
                selectedText,
                selectedNodeType,
                selectedNodeAttributes,
                hasSelection: (!empty && selectedText.trim().length > 0) || !!selectedNodeAttributes
            });
        }
    });

    // Sync onChartEdit callback to CustomImage storage so ImageResizeComponent can access it
    useEffect(() => {
        if (editor && editor.extensionManager.extensions) {
            const imageExt = editor.extensionManager.extensions.find(e => e.name === 'image');
            if (imageExt) {
                editor.storage.image = editor.storage.image || {};
                editor.storage.image.onChartEdit = onChartEdit || null;
            }
        }
    }, [editor, onChartEdit]);

    // Expose editor methods via ref
    useImperativeHandle(ref, () => ({
        // Get the editor instance
        getEditor: () => editor,

        // Get current HTML content
        getHTML: () => editor?.getHTML() || '',

        // Get plain text
        getText: () => editor?.getText() || '',

        // Set entire content (for full page updates)
        setContent: (html) => {
            editor?.commands.setContent(html);
        },

        // Insert content at current cursor position
        insertContent: (html) => {
            editor?.commands.insertContent(html);
        },

        // Replace selection with new content
        replaceSelection: (html) => {
            if (editor) {
                const { from, to, empty } = editor.state.selection;
                if (!empty) {
                    editor.chain()
                        .focus()
                        .deleteRange({ from, to })
                        .insertContent(html)
                        .run();
                } else {
                    // No selection, just insert at cursor
                    editor.commands.insertContent(html);
                }
            }
        },

        // Get selection info
        getSelection: () => {
            if (!editor) return { from: 0, to: 0, empty: true, selectedText: '' };
            const { from, to, empty } = editor.state.selection;
            const selectedText = empty ? '' : editor.state.doc.textBetween(from, to, ' ');
            return { from, to, empty, selectedText };
        },

        // Focus editor
        focus: () => editor?.commands.focus(),

        // Check if editor is ready
        isReady: () => !!editor,

        // Trigger image upload
        addImage: () => {
            fileInputRef.current?.click();
        },

        // Open video source modal
        openVideoModal: () => {
            setShowVideoModal(true);
        },

        // Open embed source modal
        openEmbedModal: () => {
            setShowEmbedModal(true);
        }
    }), [editor]);

    // Update content when prop changes (for page switches)
    useEffect(() => {
        if (editor && content !== undefined) {
            const currentContent = editor.getHTML();
            // Only update if content is different (avoid loops)
            if (content !== currentContent) {
                editor.commands.setContent(content);
            }
        }
    }, [content, editor]);

    // Toolbar actions
    const toggleBold = useCallback(() => editor?.chain().focus().toggleBold().run(), [editor]);
    const toggleItalic = useCallback(() => editor?.chain().focus().toggleItalic().run(), [editor]);
    const toggleUnderline = useCallback(() => editor?.chain().focus().toggleUnderline().run(), [editor]);
    const toggleStrike = useCallback(() => editor?.chain().focus().toggleStrike().run(), [editor]);
    const toggleBulletList = useCallback(() => editor?.chain().focus().toggleBulletList().run(), [editor]);
    const toggleOrderedList = useCallback(() => editor?.chain().focus().toggleOrderedList().run(), [editor]);
    const toggleBlockquote = useCallback(() => editor?.chain().focus().toggleBlockquote().run(), [editor]);
    const undo = useCallback(() => editor?.chain().focus().undo().run(), [editor]);
    const redo = useCallback(() => editor?.chain().focus().redo().run(), [editor]);

    const setHeading = useCallback((level) => {
        editor?.chain().focus().toggleHeading({ level }).run();
    }, [editor]);

    const insertTable = useCallback((rows = 3, cols = 3) => {
        editor?.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run();
        setShowTablePicker(false);
    }, [editor]);

    const handleTableButtonClick = useCallback((event) => {
        // Get button position for popover using screen coordinates
        const rect = event?.currentTarget?.getBoundingClientRect?.();
        if (rect) {
            // Position popover below the button, using fixed positioning
            setTablePickerAnchor({
                top: rect.bottom + 5,
                left: rect.left - 50 // Center the popover roughly under the button
            });
        } else {
            // Fallback position
            setTablePickerAnchor({ top: 150, left: 300 });
        }
        setShowTablePicker(true);
    }, []);

    const addTableRowAfter = useCallback(() => editor?.chain().focus().addRowAfter().run(), [editor]);
    const addTableRowBefore = useCallback(() => editor?.chain().focus().addRowBefore().run(), [editor]);
    const addTableColumnAfter = useCallback(() => editor?.chain().focus().addColumnAfter().run(), [editor]);
    const addTableColumnBefore = useCallback(() => editor?.chain().focus().addColumnBefore().run(), [editor]);
    const deleteTable = useCallback(() => editor?.chain().focus().deleteTable().run(), [editor]);
    const deleteRow = useCallback(() => editor?.chain().focus().deleteRow().run(), [editor]);
    const deleteColumn = useCallback(() => editor?.chain().focus().deleteColumn().run(), [editor]);

    // Link popover handler
    const handleLinkButtonClick = useCallback((event) => {
        // Get current link URL if cursor is on a link
        const currentUrl = editor?.getAttributes('link')?.href || '';
        setCurrentLinkUrl(currentUrl);

        // Get button position for popover
        const rect = event?.currentTarget?.getBoundingClientRect?.();
        if (rect) {
            setLinkPopoverAnchor({
                top: rect.bottom + 5,
                left: rect.left - 100 // Center the popover under the button
            });
        } else {
            setLinkPopoverAnchor({ top: 150, left: 300 });
        }
        setShowLinkPopover(true);
    }, [editor]);

    const applyLink = useCallback((url) => {
        if (url) {
            editor?.chain().focus().setLink({ href: url }).run();
        }
        setShowLinkPopover(false);
    }, [editor]);

    const removeLink = useCallback(() => {
        editor?.chain().focus().unsetLink().run();
    }, [editor]);

    // Image upload handler
    const fileInputRef = React.useRef(null);

    const addImage = useCallback(() => {
        fileInputRef.current?.click();
    }, []);

    const handleImageUpload = useCallback((event) => {
        const file = event.target.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const result = e.target?.result;
                if (typeof result === 'string') {
                    editor?.chain().focus().setImage({ src: result, width: '100%', 'data-user-media': 'true' }).run();
                }
            };
            reader.readAsDataURL(file);
        }
        // Reset value so same file can be selected again
        event.target.value = '';
    }, [editor]);

    // Video file input ref for local uploads
    const videoInputRef = React.useRef(null);

    // Video/Media insertion handler (from VideoSourceModal)
    const handleVideoSelect = useCallback((videoData) => {
        if (!editor || !videoData) return;

        // Handle local file upload trigger
        if (videoData.videoType === 'local') {
            videoInputRef.current?.click();
            return;
        }

        // Insert embed using the custom EmbedNode
        editor.commands.insertEmbed({
            src: videoData.src,
            embedType: videoData.videoType,
            provider: videoData.videoType?.charAt(0).toUpperCase() + videoData.videoType?.slice(1) || 'Video',
            title: videoData.title || '',
            thumbnail: videoData.thumbnail || null,
            videoId: videoData.videoId || null,
            width: 640,
            height: videoData.videoType === 'spotify' ? 152 : 360,
        });

        setShowVideoModal(false);
    }, [editor]);

    // Handle local video file upload
    const handleVideoUpload = useCallback((event) => {
        const file = event.target.files?.[0];
        if (file && editor) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const result = e.target?.result;
                if (typeof result === 'string') {
                    editor.commands.insertEmbed({
                        src: result,
                        embedType: 'local-video',
                        provider: 'Local Video',
                        title: file.name || 'Uploaded Video',
                        thumbnail: null,
                        videoId: null,
                        width: 640,
                        height: 360,
                    });
                }
            };
            reader.readAsDataURL(file);
        }
        // Reset value so same file can be selected again
        event.target.value = '';
    }, [editor]);

    // Handle embed selection (Figma, Google Drive, Miro, etc.)
    const handleEmbedSelect = useCallback((embedData) => {
        if (!editor || !embedData) return;

        editor.commands.insertEmbed({
            src: embedData.src,
            embedType: embedData.embedType || 'webpage',
            provider: embedData.provider || embedData.embedType || 'Embed',
            title: embedData.title || '',
            thumbnail: embedData.thumbnail || null,
            html: embedData.html || null,
            videoId: null,
            width: embedData.width || 640,
            height: embedData.height || 480,
        });

        setShowEmbedModal(false);
    }, [editor]);

    const clearFormatting = useCallback(() => {
        editor?.chain().focus().unsetAllMarks().clearNodes().run();
    }, [editor]);

    // ═══════════════════════════════════════════════════════════════════
    // TEXT STYLING HANDLERS
    // ═══════════════════════════════════════════════════════════════════

    // Color picker handler
    const handleColorButtonClick = useCallback((event) => {
        const rect = event?.currentTarget?.getBoundingClientRect?.();
        if (rect) {
            setColorPickerAnchor({
                top: rect.bottom + 5,
                left: rect.left - 80
            });
        } else {
            setColorPickerAnchor({ top: 150, left: 300 });
        }
        setShowColorPicker(true);
    }, []);

    const setTextColor = useCallback((color) => {
        editor?.chain().focus().setColor(color).run();
    }, [editor]);

    const clearTextColor = useCallback(() => {
        editor?.chain().focus().unsetColor().run();
    }, [editor]);

    const setHighlightColor = useCallback((color) => {
        editor?.chain().focus().setHighlight({ color }).run();
    }, [editor]);

    const clearHighlight = useCallback(() => {
        editor?.chain().focus().unsetHighlight().run();
    }, [editor]);

    // Font family handler
    const handleFontButtonClick = useCallback((event) => {
        const rect = event?.currentTarget?.getBoundingClientRect?.();
        if (rect) {
            setFontPickerAnchor({
                top: rect.bottom + 5,
                left: rect.left - 60
            });
        } else {
            setFontPickerAnchor({ top: 150, left: 300 });
        }
        setShowFontPicker(true);
    }, []);

    const setFontFamily = useCallback((family) => {
        if (family) {
            editor?.chain().focus().setFontFamily(family).run();
        } else {
            editor?.chain().focus().unsetFontFamily().run();
        }
    }, [editor]);

    // Text alignment handler
    const handleAlignButtonClick = useCallback((event) => {
        const rect = event?.currentTarget?.getBoundingClientRect?.();
        if (rect) {
            setAlignPickerAnchor({
                top: rect.bottom + 5,
                left: rect.left - 60
            });
        } else {
            setAlignPickerAnchor({ top: 150, left: 300 });
        }
        setShowAlignPicker(true);
    }, []);

    const setTextAlign = useCallback((alignment) => {
        editor?.chain().focus().setTextAlign(alignment).run();
    }, [editor]);

    // Get current styling for active state indicators
    const currentTextColor = editor?.getAttributes('textStyle')?.color || null;
    const currentHighlight = editor?.getAttributes('highlight')?.color || null;
    const currentFontFamily = editor?.getAttributes('textStyle')?.fontFamily || null;
    const currentAlignment = editor?.isActive({ textAlign: 'center' }) ? 'center' :
        editor?.isActive({ textAlign: 'right' }) ? 'right' :
            editor?.isActive({ textAlign: 'justify' }) ? 'justify' : 'left';

    if (!editor) {
        return (
            <View style={styles.loading}>
                <Text>Loading editor...</Text>
            </View>
        );
    }

    const isInTable = editor.isActive('table');

    return (
        <View style={styles.container}>
            {/* Inject CSS for Tiptap */}
            <style type="text/css">{`
        /* Dynamic Report Style CSS */
        ${getStyleCSS(reportStyle)}
        
        /* Cursor visibility fix - multiple selectors to ensure it works */
        .ProseMirror {
          caret-color: #000 !important;
        }
        
        .ProseMirror::caret {
          color: #000 !important;
        }
        
        .ProseMirror[contenteditable="true"] {
          caret-color: #000 !important;
        }
        
        .ProseMirror[contenteditable="true"]::caret {
          color: #000 !important;
        }
        
        [contenteditable="true"] {
          caret-color: #000 !important;
        }
        
        [contenteditable="true"]::caret {
          color: #000 !important;
        }
        
        .tiptap-editor .ProseMirror {
          caret-color: #000 !important;
        }
        
        .tiptap-editor {
          min-height: 400px;
          padding: 12px 24px;
          outline: none;
          /* Force black I-beam cursor using SVG to override OS theme */
          cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M11 2h2v20h-2z'/%3E%3Cpath fill='black' d='M8 2h8v2H8z'/%3E%3Cpath fill='black' d='M8 20h8v2H8z'/%3E%3C/svg%3E") 12 12, text;
        }
        
        .ProseMirror {
          /* Force black I-beam cursor using SVG to override OS theme */
          cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M11 2h2v20h-2z'/%3E%3Cpath fill='black' d='M8 2h8v2H8z'/%3E%3Cpath fill='black' d='M8 20h8v2H8z'/%3E%3C/svg%3E") 12 12, text !important;
        }
        
        .tiptap-editor:focus {
          outline: none;
        }

        /* Persist selection highlight when editor loses focus */
        .selection-persist {
          background-color: rgba(59, 130, 246, 0.25);
        }
        
        /* Table styles */
        .tiptap-editor table,
        .tiptap-editor .tiptap-table {
          border-collapse: collapse;
          width: 100%;
          margin: 1em 0;
          table-layout: fixed;
          overflow: hidden;
        }
        
        .tiptap-editor td,
        .tiptap-editor th {
          border: 1px solid #ddd;
          padding: 8px 12px;
          text-align: left;
          vertical-align: top;
          position: relative;
          min-width: 100px;
        }
        
        .tiptap-editor th {
          background-color: #f8f9fa;
          font-weight: 600;
        }
        
        .tiptap-editor tr:nth-child(even) td {
          background-color: #f9f9f9;
        }
        
        /* Layout tables - tables used for page column layouts (no borders) */
        .tiptap-editor table[style*="table-layout: fixed"] > tbody > tr > td {
          border: 1px dashed #e0e0e0;
          background-color: transparent;
        }
        
        .tiptap-editor table[style*="table-layout: fixed"] > tbody > tr > td:focus-within {
          border-color: #2196F3;
          background-color: #fafafa;
        }
        
        /* ═══════════════════════════════════════════════════════════════════
         * AI AUTO MODE - Advanced Visual Styling Support
         * These styles ensure AI-generated visual elements render correctly
         * ═══════════════════════════════════════════════════════════════════ */
        
        /* Metric Cards & Call-out Boxes */
        .tiptap-editor div[style*="background"] {
          border-radius: 8px;
          margin: 16px 0;
        }
        
        /* Grid Layouts */
        .tiptap-editor div[style*="display: grid"],
        .tiptap-editor div[style*="display:grid"] {
          width: 100%;
          margin: 20px 0;
        }
        
        /* Flexbox Layouts */
        .tiptap-editor div[style*="display: flex"],
        .tiptap-editor div[style*="display:flex"] {
          width: 100%;
        }
        
        /* Styled Tables (AI-generated with inline styles) */
        .tiptap-editor table[style] {
          border-collapse: collapse;
          border-radius: 8px;
          overflow: hidden;
        }
        
        .tiptap-editor table[style] thead {
          /* Allow AI inline styles to take precedence */
        }
        
        .tiptap-editor table[style] th,
        .tiptap-editor table[style] td {
          /* Ensure padding even if AI forgets */
          padding: 12px 14px;
        }
        
        /* Progress Bars */
        .tiptap-editor div[style*="border-radius: 999px"],
        .tiptap-editor div[style*="border-radius:999px"] {
          overflow: hidden;
        }
        
        /* Large Typography for Stats */
        .tiptap-editor span[style*="font-size: 2"],
        .tiptap-editor span[style*="font-size:2"] {
          display: inline-block;
          line-height: 1.2;
        }
        
        /* Status Badges */
        .tiptap-editor span[style*="border-radius: 20px"],
        .tiptap-editor span[style*="border-radius:20px"] {
          display: inline-flex;
          align-items: center;
          white-space: nowrap;
        }
        
        /* Gradient Backgrounds */
        .tiptap-editor div[style*="linear-gradient"] {
          /* Ensure text is readable */
        }
        
        /* Images within AI content */
        .tiptap-editor img {
          max-width: 100%;
          height: auto;
          border-radius: 8px;
        }
        
        /* ═══════════════════════════════════════════════════════════════════
         * VIDEO & EMBED SUPPORT - User-inserted media
         * ═══════════════════════════════════════════════════════════════════ */
        
        /* Video containers (YouTube, Vimeo, Loom, etc.) */
        .tiptap-editor div[data-user-media="true"] {
          margin: 16px 0;
          max-width: 100%;
        }
        
        /* Responsive video wrapper */
        .tiptap-editor div[data-media-type="youtube"],
        .tiptap-editor div[data-media-type="vimeo"],
        .tiptap-editor div[data-media-type="loom"] {
          position: relative;
          padding-bottom: 56.25%; /* 16:9 aspect ratio */
          height: 0;
          overflow: hidden;
          border-radius: 12px;
        }
        
        .tiptap-editor div[data-media-type="youtube"] iframe,
        .tiptap-editor div[data-media-type="vimeo"] iframe,
        .tiptap-editor div[data-media-type="loom"] iframe {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          border: none;
          border-radius: 12px;
        }
        
        /* Spotify embeds */
        .tiptap-editor div[data-media-type="spotify"] {
          margin: 16px 0;
        }
        
        .tiptap-editor div[data-media-type="spotify"] iframe {
          width: 100%;
          border: none;
          border-radius: 12px;
        }
        
        /* Local/Recorded video */
        .tiptap-editor div[data-media-type="local-video"] video,
        .tiptap-editor div[data-media-type="recorded"] video {
          width: 100%;
          max-width: 100%;
          border-radius: 12px;
        }
        
        /* Generic embed containers */
        .tiptap-editor div[data-media-type="embed"] {
          position: relative;
          padding-bottom: 56.25%;
          height: 0;
          overflow: hidden;
          border-radius: 12px;
          margin: 16px 0;
        }
        
        .tiptap-editor div[data-media-type="embed"] iframe {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          border: none;
        }
        
        /* Figma, Miro, etc. embeds */
        .tiptap-editor div[data-media-type="figma"],
        .tiptap-editor div[data-media-type="miro"],
        .tiptap-editor div[data-media-type="google"],
        .tiptap-editor div[data-media-type="airtable"],
        .tiptap-editor div[data-media-type="powerbi"] {
          position: relative;
          padding-bottom: 56.25%;
          height: 0;
          overflow: hidden;
          border-radius: 12px;
          margin: 16px 0;
          border: 1px solid #e5e7eb;
        }
        
        .tiptap-editor div[data-media-type="figma"] iframe,
        .tiptap-editor div[data-media-type="miro"] iframe,
        .tiptap-editor div[data-media-type="google"] iframe,
        .tiptap-editor div[data-media-type="airtable"] iframe,
        .tiptap-editor div[data-media-type="powerbi"] iframe {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          border: none;
        }
        
        /* Chart placeholders (before conversion to image) */
        .tiptap-editor chart-config {
          display: none; /* Hidden - processed by React */
        }
        
        /* Preserve inline styles from AI */
        .tiptap-editor [style] {
          /* Allow all inline styles */
        }
        
        /* Shadow support */
        .tiptap-editor div[style*="box-shadow"] {
          /* Shadows render naturally */
        }
        
        /* Border-left accent cards */
        .tiptap-editor div[style*="border-left"] {
          overflow: hidden;
        }
        
        /* Ensure nested elements inherit properly */
        .tiptap-editor div[style] p,
        .tiptap-editor div[style] span,
        .tiptap-editor div[style] strong,
        .tiptap-editor div[style] em {
          margin: 0;
        }
        
        /* First paragraph in styled divs */
        .tiptap-editor div[style] > p:first-child {
          margin-top: 0;
        }
        
        .tiptap-editor div[style] > p:last-child {
          margin-bottom: 0;
        }
        
        /* Selected cell */
        .tiptap-editor .selectedCell {
          background-color: #e3f2fd !important;
        }
        
        /* Placeholder */
        .tiptap-editor p.is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: #aaa;
          pointer-events: none;
          height: 0;
        }
        
        /* Gapcursor styling - CRITICAL for cursor visibility */
        .ProseMirror-gapcursor {
          display: block;
          pointer-events: none;
          position: absolute;
        }
        
        .ProseMirror-gapcursor:after {
          content: "";
          display: block;
          position: absolute;
          top: -2px;
          width: 20px;
          border-top: 2px solid #000;
          animation: ProseMirror-cursor-blink 1.1s steps(2, start) infinite;
        }
        
        @keyframes ProseMirror-cursor-blink {
          to {
            visibility: hidden;
          }
        }
        
        /* Selection highlight */
        .tiptap-editor ::selection {
          background-color: #b3d4fc;
        }
        
        /* Image Node Wrapper styles (handled by custom component, but general flow here) */
        .image-resizer {
          display: inline-block;
          max-width: 100%;
        }
        
        /* ═══════════════════════════════════════════════════════════════════
         * TIPTAP EMBED NODE STYLES - Custom embed extension
         * ═══════════════════════════════════════════════════════════════════ */
        
        .embed-node-wrapper {
          display: block;
          max-width: 100%;
          margin: 16px 0;
        }
        
        .tiptap-embed {
          position: relative;
          border-radius: 12px;
          overflow: hidden;
          transition: border-color 0.2s ease;
        }
        
        .tiptap-embed.selected {
          border-color: #2196F3 !important;
          box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.2);
        }
        
        .tiptap-embed-wrapper {
          /* Fallback for HTML rendering */
          display: block;
          margin: 16px 0;
        }
        
        /* Sticky Toolbar */
        .tiptap-toolbar-sticky {
          position: relative;
          z-index: 100;
          background-color: #f8f9fa;
          flex-shrink: 0;
        }
        
        /* TiptapEditor main container - handles its own scroll */
        .tiptap-editor-container {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }
        
        /* Scrollable editor content area */
        .tiptap-editor-scroll-area {
          flex: 1;
          overflow-y: auto;
          overflow-x: hidden;
          min-height: 0; /* Important for flex scroll to work */
        }
      `}</style>

            {/* Toolbar - Fixed at top (hidden when shared ComposerToolbar is used) */}
            {showToolbar && <View style={styles.toolbar} className="tiptap-toolbar-sticky">
                {/* Undo/Redo */}
                <ToolbarButton icon="undo" onPress={undo} title="Undo" disabled={!editor.can().undo()} />
                <ToolbarButton icon="redo" onPress={redo} title="Redo" disabled={!editor.can().redo()} />

                <ToolbarDivider />

                {/* Headings dropdown - simplified as buttons */}
                <ToolbarButton
                    icon="title"
                    onPress={() => setHeading(2)}
                    isActive={editor.isActive('heading', { level: 2 })}
                    title="Heading 2"
                />
                <ToolbarButton
                    icon="format-size"
                    onPress={() => setHeading(3)}
                    isActive={editor.isActive('heading', { level: 3 })}
                    title="Heading 3"
                />

                <ToolbarDivider />

                {/* Text formatting */}
                <ToolbarButton icon="format-bold" onPress={toggleBold} isActive={editor.isActive('bold')} title="Bold" />
                <ToolbarButton icon="format-italic" onPress={toggleItalic} isActive={editor.isActive('italic')} title="Italic" />
                <ToolbarButton icon="format-underlined" onPress={toggleUnderline} isActive={editor.isActive('underline')} title="Underline" />
                <ToolbarButton icon="strikethrough-s" onPress={toggleStrike} isActive={editor.isActive('strike')} title="Strikethrough" />

                <ToolbarDivider />

                {/* Text & Highlight Color */}
                <TouchableOpacity
                    onPress={handleColorButtonClick}
                    style={[
                        styles.toolbarButton,
                        (currentTextColor || currentHighlight) && styles.toolbarButtonActive
                    ]}
                    title="Text & Highlight Color"
                >
                    <View style={{ alignItems: 'center' }}>
                        <MaterialIcons name="format-color-text" size={18} color={currentTextColor || '#555'} />
                        <View style={{
                            height: 3,
                            width: 16,
                            backgroundColor: currentHighlight || currentTextColor || '#555',
                            borderRadius: 1,
                            marginTop: 1,
                        }} />
                    </View>
                </TouchableOpacity>

                {/* Font Family */}
                <ToolbarButton
                    icon="font-download"
                    onPress={handleFontButtonClick}
                    isActive={!!currentFontFamily}
                    title="Font Family"
                />

                {/* Text Alignment */}
                <ToolbarButton
                    icon={currentAlignment === 'center' ? 'format-align-center' :
                        currentAlignment === 'right' ? 'format-align-right' :
                            currentAlignment === 'justify' ? 'format-align-justify' : 'format-align-left'}
                    onPress={handleAlignButtonClick}
                    isActive={currentAlignment !== 'left'}
                    title="Text Alignment"
                />

                <ToolbarDivider />

                {/* Lists */}
                <ToolbarButton icon="format-list-bulleted" onPress={toggleBulletList} isActive={editor.isActive('bulletList')} title="Bullet List" />
                <ToolbarButton icon="format-list-numbered" onPress={toggleOrderedList} isActive={editor.isActive('orderedList')} title="Numbered List" />
                <ToolbarButton icon="format-quote" onPress={toggleBlockquote} isActive={editor.isActive('blockquote')} title="Quote" />

                <ToolbarDivider />

                {/* Table */}
                <ToolbarButton icon="table-chart" onPress={handleTableButtonClick} title="Insert Table" />
                {isInTable && (
                    <>
                        <ToolbarButton icon="add-box" onPress={addTableRowAfter} title="Add Row Below" />
                        <ToolbarButton icon="library-add" onPress={addTableColumnAfter} title="Add Column Right" />
                        <ToolbarButton icon="remove-circle-outline" onPress={deleteRow} title="Delete Row" />
                        <ToolbarButton icon="cancel" onPress={deleteColumn} title="Delete Column" />
                        <ToolbarButton icon="delete-forever" onPress={deleteTable} title="Delete Table" />
                    </>
                )}

                <ToolbarDivider />

                {/* Media */}
                <ToolbarButton icon="image" onPress={addImage} title="Insert Image" />
                {/* Insert Video + Insert Embed — HIDDEN for now (kept for future). */}
                {false && <ToolbarButton icon="movie" onPress={() => setShowVideoModal(true)} title="Insert Video" />}
                {false && <ToolbarButton icon="code" onPress={() => setShowEmbedModal(true)} title="Insert Embed" />}

                <ToolbarDivider />

                {/* Link */}
                <ToolbarButton icon="link" onPress={handleLinkButtonClick} isActive={editor.isActive('link')} title="Add Link" />
                {editor.isActive('link') && (
                    <ToolbarButton icon="link-off" onPress={removeLink} title="Remove Link" />
                )}

                <ToolbarDivider />

                {/* Clear formatting */}
                <ToolbarButton icon="format-clear" onPress={clearFormatting} title="Clear Formatting" />
            </View>}

            {/* Hidden File Input */}
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleImageUpload}
                style={{ display: 'none' }}
                accept="image/*"
            />

            {/* Hidden Video File Input */}
            <input
                type="file"
                ref={videoInputRef}
                onChange={handleVideoUpload}
                style={{ display: 'none' }}
                accept="video/*"
            />

            {/* Editor Content - Scrollable area */}
            <div className="tiptap-editor-scroll-area">
                <View style={styles.editorContainer}>
                    <EditorContent editor={editor} className="tiptap-editor report-content" />
                </View>
            </div>

            {/* Inline Formatting BubbleMenu - appears on text selection */}
            {editor && (
                <BubbleMenu
                    editor={editor}
                    tippyOptions={{ duration: 150, placement: 'top', zIndex: 9999 }}
                    shouldShow={({ editor, from, to }) => {
                        // Only show when there is a text selection (not collapsed cursor)
                        return from !== to && !editor.isActive('image');
                    }}
                >
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 2,
                        backgroundColor: theme.surface || '#ffffff',
                        border: `1px solid ${theme.border || '#e0e0e0'}`,
                        borderRadius: 8,
                        padding: '4px 6px',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    }}>
                        {/* Bold */}
                        <button
                            onClick={toggleBold}
                            title="Bold"
                            style={{
                                background: editor.isActive('bold') ? (theme.primary || '#3b82f6') : 'transparent',
                                color: editor.isActive('bold') ? '#fff' : (theme.text || '#1a1a1a'),
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                fontWeight: 'bold',
                                fontSize: 14,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >B</button>

                        {/* Italic */}
                        <button
                            onClick={toggleItalic}
                            title="Italic"
                            style={{
                                background: editor.isActive('italic') ? (theme.primary || '#3b82f6') : 'transparent',
                                color: editor.isActive('italic') ? '#fff' : (theme.text || '#1a1a1a'),
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                fontStyle: 'italic',
                                fontSize: 14,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >I</button>

                        {/* Underline */}
                        <button
                            onClick={toggleUnderline}
                            title="Underline"
                            style={{
                                background: editor.isActive('underline') ? (theme.primary || '#3b82f6') : 'transparent',
                                color: editor.isActive('underline') ? '#fff' : (theme.text || '#1a1a1a'),
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                textDecoration: 'underline',
                                fontSize: 14,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >U</button>

                        {/* Strikethrough */}
                        <button
                            onClick={toggleStrike}
                            title="Strikethrough"
                            style={{
                                background: editor.isActive('strike') ? (theme.primary || '#3b82f6') : 'transparent',
                                color: editor.isActive('strike') ? '#fff' : (theme.text || '#1a1a1a'),
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                textDecoration: 'line-through',
                                fontSize: 14,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >S</button>

                        {/* Divider */}
                        <div style={{
                            width: 1,
                            height: 20,
                            backgroundColor: theme.border || '#e0e0e0',
                            margin: '0 4px',
                        }} />

                        {/* Text Color */}
                        <button
                            onClick={handleColorButtonClick}
                            title="Text Color"
                            style={{
                                background: 'transparent',
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                fontSize: 14,
                                fontWeight: 'bold',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: currentTextColor || (theme.text || '#1a1a1a'),
                                borderBottom: `3px solid ${currentTextColor || (theme.text || '#1a1a1a')}`,
                            }}
                        >A</button>

                        {/* Highlight */}
                        <button
                            onClick={(e) => {
                                if (currentHighlight) {
                                    clearHighlight();
                                } else {
                                    setHighlightColor('#FFEB3B');
                                }
                            }}
                            title="Highlight"
                            style={{
                                background: currentHighlight || 'transparent',
                                border: 'none',
                                borderRadius: 4,
                                width: 28,
                                height: 28,
                                cursor: 'pointer',
                                fontSize: 14,
                                fontWeight: 'bold',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: currentHighlight ? '#1a1a1a' : (theme.text || '#1a1a1a'),
                            }}
                        >⬛</button>
                    </div>
                </BubbleMenu>
            )}

            {/* Popovers - only render when toolbar is shown (shared toolbar manages its own popovers) */}
            {showToolbar && <>
            <TableSizePicker
                visible={showTablePicker}
                onSelect={(rows, cols) => insertTable(rows, cols)}
                onClose={() => setShowTablePicker(false)}
                anchorPosition={tablePickerAnchor}
            />

            <LinkInputPopover
                visible={showLinkPopover}
                onApply={applyLink}
                onClose={() => setShowLinkPopover(false)}
                anchorPosition={linkPopoverAnchor}
                initialUrl={currentLinkUrl}
            />

            <ColorPickerPopover
                visible={showColorPicker}
                onClose={() => setShowColorPicker(false)}
                anchorPosition={colorPickerAnchor}
                onSelectColor={setTextColor}
                onSelectHighlight={setHighlightColor}
                onClearColor={clearTextColor}
                onClearHighlight={clearHighlight}
                currentColor={currentTextColor}
                currentHighlight={currentHighlight}
            />

            <FontFamilyPopover
                visible={showFontPicker}
                onClose={() => setShowFontPicker(false)}
                anchorPosition={fontPickerAnchor}
                onSelectFont={setFontFamily}
                currentFont={currentFontFamily}
            />

            <TextAlignPopover
                visible={showAlignPicker}
                onClose={() => setShowAlignPicker(false)}
                anchorPosition={alignPickerAnchor}
                onSelectAlign={setTextAlign}
                currentAlign={currentAlignment}
            />
            </>}

            {/* Video/Embed Modals - always rendered (triggered via ref methods) */}
            <VideoSourceModal
                visible={showVideoModal}
                onClose={() => setShowVideoModal(false)}
                onSelectVideo={handleVideoSelect}
                theme={modalTheme}
            />

            <EmbedSourceModal
                visible={showEmbedModal}
                onClose={() => setShowEmbedModal(false)}
                onSelectEmbed={handleEmbedSelect}
                theme={modalTheme}
            />
        </View>
    );
});

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#fff',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
    },
    toolbar: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        alignItems: 'center',
        paddingVertical: 4,
        paddingHorizontal: 8,
        backgroundColor: '#f8f9fa',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
        gap: 2,
        flexShrink: 0
    },
    toolbarButton: {
        padding: 8,
        borderRadius: 4,
        backgroundColor: 'transparent'
    },
    toolbarButtonActive: {
        backgroundColor: '#e3f2fd'
    },
    toolbarButtonDisabled: {
        opacity: 0.4
    },
    toolbarDivider: {
        width: 1,
        height: 24,
        backgroundColor: '#ddd',
        marginHorizontal: 6
    },
    editorContainer: {
        flex: 1,
        backgroundColor: '#fff',
        overflow: 'auto'
    },
    loading: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 40
    }
});

export default TiptapEditor;

// Named exports for shared ComposerToolbar
export {
    ToolbarButton,
    ToolbarDivider,
    TableSizePicker,
    LinkInputPopover,
    ColorPickerPopover,
    FontFamilyPopover,
    TextAlignPopover,
    COLOR_PRESETS,
    HIGHLIGHT_PRESETS,
    FONT_FAMILIES,
    loadGoogleFont,
};
