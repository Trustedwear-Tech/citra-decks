// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// ShapesPickerModal.js - Canva-like Shapes Picker for Presentation Canvas
import React, { useState, useMemo, useCallback } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    ScrollView,
    TextInput,
    StyleSheet,
    Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, {
    Rect,
    Circle,
    Ellipse,
    Line,
    Polygon,
    Path,
    G,
    Defs,
    Marker
} from 'react-native-svg';

// ===================== SHAPE DEFINITIONS =====================
// Each shape has: id, name, category, render function, fabricCreate function
// The fabricCreate returns { type, shapeType, pathData?, points?, ... }

export const SHAPE_CATEGORIES = {
    LINES: 'lines',
    BASIC: 'basic',
    POLYGONS: 'polygons',
    STARS: 'stars',
    ARROWS: 'arrows',
    CALLOUTS: 'callouts',
};

export const CATEGORY_INFO = {
    [SHAPE_CATEGORIES.LINES]: { name: 'Lines', icon: 'remove-outline' },
    [SHAPE_CATEGORIES.BASIC]: { name: 'Basic Shapes', icon: 'square-outline' },
    [SHAPE_CATEGORIES.POLYGONS]: { name: 'Polygons', icon: 'pentagon-outline' },
    [SHAPE_CATEGORIES.STARS]: { name: 'Stars', icon: 'star-outline' },
    [SHAPE_CATEGORIES.ARROWS]: { name: 'Arrows', icon: 'arrow-forward-outline' },
    [SHAPE_CATEGORIES.CALLOUTS]: { name: 'Callouts', icon: 'chatbox-outline' },
};

// SVG Path generator utilities
const generateStarPath = (cx, cy, outerR, innerR, points) => {
    const angle = Math.PI / points;
    let path = '';
    for (let i = 0; i < 2 * points; i++) {
        const r = i % 2 === 0 ? outerR : innerR;
        const x = cx + r * Math.sin(i * angle);
        const y = cy - r * Math.cos(i * angle);
        path += (i === 0 ? 'M' : 'L') + x.toFixed(2) + ',' + y.toFixed(2);
    }
    return path + 'Z';
};

const generatePolygonPoints = (cx, cy, r, sides) => {
    const angle = (2 * Math.PI) / sides;
    let points = [];
    for (let i = 0; i < sides; i++) {
        const x = cx + r * Math.sin(i * angle - Math.PI / 2);
        const y = cy - r * Math.cos(i * angle - Math.PI / 2);
        points.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    }
    return points.join(' ');
};

// Shape definitions with preview SVG and Fabric.js creation data
export const SHAPES = [
    // ==================== LINES ====================
    {
        id: 'line_solid',
        name: 'Solid Line',
        category: SHAPE_CATEGORIES.LINES,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Line x1="5" y1="20" x2="35" y2="20" stroke={color} strokeWidth="2" />
            </Svg>
        ),
        fabricData: { shapeType: 'line', subType: 'solid' },
    },
    {
        id: 'line_dashed',
        name: 'Dashed Line',
        category: SHAPE_CATEGORIES.LINES,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Line x1="5" y1="20" x2="35" y2="20" stroke={color} strokeWidth="2" strokeDasharray="4,3" />
            </Svg>
        ),
        fabricData: { shapeType: 'line', subType: 'dashed', strokeDashArray: [8, 6] },
    },
    {
        id: 'line_dotted',
        name: 'Dotted Line',
        category: SHAPE_CATEGORIES.LINES,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Line x1="5" y1="20" x2="35" y2="20" stroke={color} strokeWidth="2" strokeDasharray="2,2" />
            </Svg>
        ),
        fabricData: { shapeType: 'line', subType: 'dotted', strokeDashArray: [3, 3] },
    },
    {
        id: 'line_arrow',
        name: 'Arrow Line',
        category: SHAPE_CATEGORIES.LINES,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Line x1="5" y1="20" x2="30" y2="20" stroke={color} strokeWidth="2" />
                <Polygon points="30,15 38,20 30,25" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'arrow', subType: 'single' },
    },
    {
        id: 'line_arrow_double',
        name: 'Double Arrow Line',
        category: SHAPE_CATEGORIES.LINES,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Line x1="10" y1="20" x2="30" y2="20" stroke={color} strokeWidth="2" />
                <Polygon points="10,15 2,20 10,25" fill={color} />
                <Polygon points="30,15 38,20 30,25" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'arrow', subType: 'double' },
    },

    // ==================== BASIC SHAPES ====================
    {
        id: 'rectangle',
        name: 'Rectangle',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Rect x="4" y="8" width="32" height="24" fill={color} rx="0" />
            </Svg>
        ),
        fabricData: { shapeType: 'rectangle' },
    },
    {
        id: 'rectangle_rounded',
        name: 'Rounded Rectangle',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Rect x="4" y="8" width="32" height="24" fill={color} rx="6" />
            </Svg>
        ),
        fabricData: { shapeType: 'rectangle', borderRadius: 12 },
    },
    {
        id: 'square',
        name: 'Square',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Rect x="6" y="6" width="28" height="28" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'square' },
    },
    {
        id: 'circle',
        name: 'Circle',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Circle cx="20" cy="20" r="16" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'circle' },
    },
    {
        id: 'ellipse',
        name: 'Ellipse',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Ellipse cx="20" cy="20" rx="17" ry="11" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'ellipse' },
    },
    {
        id: 'triangle',
        name: 'Triangle',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="20,4 36,36 4,36" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'triangle' },
    },
    {
        id: 'triangle_right',
        name: 'Right Triangle',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="4,4 36,36 4,36" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'triangle_right' },
    },
    {
        id: 'diamond',
        name: 'Diamond',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="20,2 38,20 20,38 2,20" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'diamond' },
    },
    {
        id: 'parallelogram',
        name: 'Parallelogram',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="10,8 38,8 30,32 2,32" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'parallelogram' },
    },
    {
        id: 'trapezoid',
        name: 'Trapezoid',
        category: SHAPE_CATEGORIES.BASIC,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="8,8 32,8 38,32 2,32" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'trapezoid' },
    },

    // ==================== POLYGONS ====================
    {
        id: 'pentagon',
        name: 'Pentagon',
        category: SHAPE_CATEGORIES.POLYGONS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points={generatePolygonPoints(20, 21, 17, 5)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'polygon', sides: 5 },
    },
    {
        id: 'hexagon',
        name: 'Hexagon',
        category: SHAPE_CATEGORIES.POLYGONS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points={generatePolygonPoints(20, 20, 17, 6)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'polygon', sides: 6 },
    },
    {
        id: 'heptagon',
        name: 'Heptagon',
        category: SHAPE_CATEGORIES.POLYGONS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points={generatePolygonPoints(20, 21, 17, 7)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'polygon', sides: 7 },
    },
    {
        id: 'octagon',
        name: 'Octagon',
        category: SHAPE_CATEGORIES.POLYGONS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points={generatePolygonPoints(20, 20, 17, 8)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'polygon', sides: 8 },
    },
    {
        id: 'decagon',
        name: 'Decagon',
        category: SHAPE_CATEGORIES.POLYGONS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points={generatePolygonPoints(20, 20, 17, 10)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'polygon', sides: 10 },
    },

    // ==================== STARS ====================
    {
        id: 'star_4',
        name: '4-Point Star',
        category: SHAPE_CATEGORIES.STARS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d={generateStarPath(20, 20, 17, 7, 4)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'star', points: 4 },
    },
    {
        id: 'star_5',
        name: '5-Point Star',
        category: SHAPE_CATEGORIES.STARS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d={generateStarPath(20, 20, 17, 8, 5)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'star', points: 5 },
    },
    {
        id: 'star_6',
        name: '6-Point Star',
        category: SHAPE_CATEGORIES.STARS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d={generateStarPath(20, 20, 17, 9, 6)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'star', points: 6 },
    },
    {
        id: 'star_8',
        name: '8-Point Star',
        category: SHAPE_CATEGORIES.STARS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d={generateStarPath(20, 20, 17, 10, 8)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'star', points: 8 },
    },
    {
        id: 'star_burst',
        name: 'Starburst',
        category: SHAPE_CATEGORIES.STARS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d={generateStarPath(20, 20, 17, 5, 12)} fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'star', points: 12 },
    },

    // ==================== ARROWS ====================
    {
        id: 'arrow_right',
        name: 'Arrow Right',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="2,14 22,14 22,6 38,20 22,34 22,26 2,26" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'block_arrow', direction: 'right' },
    },
    {
        id: 'arrow_left',
        name: 'Arrow Left',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="38,14 18,14 18,6 2,20 18,34 18,26 38,26" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'block_arrow', direction: 'left' },
    },
    {
        id: 'arrow_up',
        name: 'Arrow Up',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="14,38 14,18 6,18 20,2 34,18 26,18 26,38" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'block_arrow', direction: 'up' },
    },
    {
        id: 'arrow_down',
        name: 'Arrow Down',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="14,2 14,22 6,22 20,38 34,22 26,22 26,2" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'block_arrow', direction: 'down' },
    },
    {
        id: 'arrow_chevron_right',
        name: 'Chevron Right',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="2,4 26,4 38,20 26,36 2,36 14,20" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'chevron', direction: 'right' },
    },
    {
        id: 'arrow_pentagon',
        name: 'Pentagon Arrow',
        category: SHAPE_CATEGORIES.ARROWS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Polygon points="2,8 28,8 38,20 28,32 2,32" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'pentagon_arrow' },
    },

    // ==================== CALLOUTS ====================
    {
        id: 'callout_rect',
        name: 'Rectangle Callout',
        category: SHAPE_CATEGORIES.CALLOUTS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d="M4,4 L36,4 L36,26 L18,26 L12,34 L12,26 L4,26 Z" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'callout_rect' },
    },
    {
        id: 'callout_rounded',
        name: 'Rounded Callout',
        category: SHAPE_CATEGORIES.CALLOUTS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d="M8,4 L32,4 Q36,4 36,8 L36,22 Q36,26 32,26 L18,26 L12,34 L12,26 L8,26 Q4,26 4,22 L4,8 Q4,4 8,4 Z" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'callout_rounded' },
    },
    {
        id: 'callout_cloud',
        name: 'Cloud Callout',
        category: SHAPE_CATEGORIES.CALLOUTS,
        preview: (size, color) => (
            <Svg width={size} height={size} viewBox="0 0 40 40">
                <Path d="M12,28 Q4,28 4,20 Q4,14 10,12 Q10,6 18,6 Q26,6 28,12 Q36,12 36,20 Q36,28 28,28 L18,28 L14,34 L14,28 Z" fill={color} />
            </Svg>
        ),
        fabricData: { shapeType: 'callout_cloud' },
    },
];

// Get shapes by category
export const getShapesByCategory = (category) => {
    return SHAPES.filter(shape => shape.category === category);
};

// ===================== COMPONENT =====================
const ShapesPickerModal = ({ visible, onClose, onSelectShape, theme }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState(null); // null = show all

    // Memoized colors
    const colors = useMemo(() => ({
        background: theme?.background || '#ffffff',
        surface: theme?.surface || '#f5f5f5',
        text: theme?.text || '#333333',
        textSecondary: theme?.textSecondary || '#888888',
        primary: theme?.primary || '#2563EB',
        border: theme?.border || '#e0e0e0',
        shapePreview: theme?.isDark ? '#ffffff' : '#1a1a2e',
    }), [theme]);

    // Filter shapes based on search and category
    const filteredShapes = useMemo(() => {
        let shapes = SHAPES;

        if (selectedCategory) {
            shapes = shapes.filter(s => s.category === selectedCategory);
        }

        if (searchQuery.trim()) {
            const query = searchQuery.toLowerCase();
            shapes = shapes.filter(s =>
                s.name.toLowerCase().includes(query) ||
                s.category.toLowerCase().includes(query)
            );
        }

        return shapes;
    }, [searchQuery, selectedCategory]);

    // Group shapes by category for display
    const groupedShapes = useMemo(() => {
        if (selectedCategory) {
            return { [selectedCategory]: filteredShapes };
        }

        const grouped = {};
        filteredShapes.forEach(shape => {
            if (!grouped[shape.category]) {
                grouped[shape.category] = [];
            }
            grouped[shape.category].push(shape);
        });
        return grouped;
    }, [filteredShapes, selectedCategory]);

    const handleSelectShape = useCallback((shape) => {
        if (onSelectShape) {
            onSelectShape(shape.fabricData);
        }
        onClose();
    }, [onSelectShape, onClose]);

    const renderCategoryTabs = () => (
        <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.categoryTabsContainer}
            style={styles.categoryTabsScroll}
        >
            <TouchableOpacity
                style={[
                    styles.categoryTab,
                    !selectedCategory && styles.categoryTabActive,
                    { borderColor: !selectedCategory ? colors.primary : colors.border }
                ]}
                onPress={() => setSelectedCategory(null)}
            >
                <Ionicons name="apps-outline" size={16} color={!selectedCategory ? colors.primary : colors.textSecondary} />
                <Text style={[styles.categoryTabText, { color: !selectedCategory ? colors.primary : colors.textSecondary }]}>
                    All
                </Text>
            </TouchableOpacity>

            {Object.entries(CATEGORY_INFO).map(([key, info]) => (
                <TouchableOpacity
                    key={key}
                    style={[
                        styles.categoryTab,
                        selectedCategory === key && styles.categoryTabActive,
                        { borderColor: selectedCategory === key ? colors.primary : colors.border }
                    ]}
                    onPress={() => setSelectedCategory(key)}
                >
                    <Ionicons
                        name={info.icon}
                        size={16}
                        color={selectedCategory === key ? colors.primary : colors.textSecondary}
                    />
                    <Text style={[
                        styles.categoryTabText,
                        { color: selectedCategory === key ? colors.primary : colors.textSecondary }
                    ]}>
                        {info.name}
                    </Text>
                </TouchableOpacity>
            ))}
        </ScrollView>
    );

    const renderShapeGrid = (shapes, categoryKey) => (
        <View style={styles.shapeGrid}>
            {shapes.map(shape => (
                <TouchableOpacity
                    key={shape.id}
                    style={[styles.shapeItem, { backgroundColor: colors.surface, borderColor: colors.border }]}
                    onPress={() => handleSelectShape(shape)}
                    activeOpacity={0.7}
                >
                    <View style={styles.shapePreviewContainer}>
                        {shape.preview(48, colors.shapePreview)}
                    </View>
                    <Text style={[styles.shapeName, { color: colors.textSecondary }]} numberOfLines={1}>
                        {shape.name}
                    </Text>
                </TouchableOpacity>
            ))}
        </View>
    );

    const renderContent = () => (
        <ScrollView
            style={styles.shapesScrollView}
            contentContainerStyle={styles.shapesScrollContent}
            showsVerticalScrollIndicator={true}
        >
            {Object.entries(groupedShapes).map(([category, shapes]) => (
                <View key={category} style={styles.categorySection}>
                    {!selectedCategory && (
                        <View style={styles.categorySectionHeader}>
                            <Ionicons
                                name={CATEGORY_INFO[category]?.icon || 'shapes-outline'}
                                size={18}
                                color={colors.text}
                            />
                            <Text style={[styles.categorySectionTitle, { color: colors.text }]}>
                                {CATEGORY_INFO[category]?.name || category}
                            </Text>
                            <Text style={[styles.categoryCount, { color: colors.textSecondary }]}>
                                {shapes.length}
                            </Text>
                        </View>
                    )}
                    {renderShapeGrid(shapes, category)}
                </View>
            ))}

            {filteredShapes.length === 0 && (
                <View style={styles.emptyState}>
                    <Ionicons name="search-outline" size={48} color={colors.textSecondary} />
                    <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                        No shapes found for "{searchQuery}"
                    </Text>
                </View>
            )}
        </ScrollView>
    );

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={onClose}
        >
            <View style={styles.overlay}>
                <View style={[styles.modalContainer, { backgroundColor: colors.background }]}>
                    {/* Header */}
                    <View style={[styles.header, { borderBottomColor: colors.border }]}>
                        <View style={styles.headerLeft}>
                            <Ionicons name="shapes" size={24} color={colors.primary} />
                            <Text style={[styles.title, { color: colors.text }]}>Shapes</Text>
                        </View>
                        <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                            <Ionicons name="close" size={24} color={colors.textSecondary} />
                        </TouchableOpacity>
                    </View>

                    {/* Search */}
                    <View style={[styles.searchContainer, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                        <Ionicons name="search" size={18} color={colors.textSecondary} />
                        <TextInput
                            style={[styles.searchInput, { color: colors.text }]}
                            placeholder="Search shapes..."
                            placeholderTextColor={colors.textSecondary}
                            value={searchQuery}
                            onChangeText={setSearchQuery}
                        />
                        {searchQuery.length > 0 && (
                            <TouchableOpacity onPress={() => setSearchQuery('')}>
                                <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
                            </TouchableOpacity>
                        )}
                    </View>

                    {/* Category Tabs */}
                    {renderCategoryTabs()}

                    {/* Shapes Grid */}
                    {renderContent()}
                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
    },
    modalContainer: {
        width: '100%',
        maxWidth: 600,
        maxHeight: '85%',
        borderRadius: 16,
        overflow: 'hidden',
        ...Platform.select({
            web: {
                boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            },
            default: {
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 10 },
                shadowOpacity: 0.3,
                shadowRadius: 30,
                elevation: 20,
            },
        }),
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingVertical: 16,
        borderBottomWidth: 1,
    },
    headerLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    title: {
        fontSize: 20,
        fontWeight: '700',
    },
    closeButton: {
        padding: 4,
    },
    searchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        marginHorizontal: 16,
        marginVertical: 12,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: 10,
        borderWidth: 1,
        gap: 8,
    },
    searchInput: {
        flex: 1,
        fontSize: 15,
        paddingVertical: 0,
        ...(Platform.OS === 'web' && { outlineStyle: 'none' }),
    },
    categoryTabsScroll: {
        maxHeight: 48,
        borderBottomWidth: 1,
        borderBottomColor: '#e5e5e5',
    },
    categoryTabsContainer: {
        flexDirection: 'row',
        paddingHorizontal: 12,
        paddingVertical: 8,
        gap: 8,
    },
    categoryTab: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 20,
        borderWidth: 1,
        gap: 6,
    },
    categoryTabActive: {
        backgroundColor: 'rgba(37, 99, 235, 0.1)',
    },
    categoryTabText: {
        fontSize: 13,
        fontWeight: '500',
    },
    shapesScrollView: {
        flex: 1,
    },
    shapesScrollContent: {
        paddingHorizontal: 16,
        paddingVertical: 12,
        paddingBottom: 24,
    },
    categorySection: {
        marginBottom: 20,
    },
    categorySectionHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 12,
        gap: 8,
    },
    categorySectionTitle: {
        fontSize: 15,
        fontWeight: '600',
        flex: 1,
    },
    categoryCount: {
        fontSize: 13,
        fontWeight: '500',
    },
    shapeGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
    },
    shapeItem: {
        width: 80,
        height: 90,
        borderRadius: 10,
        borderWidth: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 8,
        ...Platform.select({
            web: {
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                ':hover': {
                    transform: 'scale(1.05)',
                },
            },
        }),
    },
    shapePreviewContainer: {
        width: 48,
        height: 48,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 4,
    },
    shapeName: {
        fontSize: 10,
        fontWeight: '500',
        textAlign: 'center',
        paddingHorizontal: 4,
    },
    emptyState: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 48,
        gap: 12,
    },
    emptyText: {
        fontSize: 14,
        textAlign: 'center',
    },
});

export default ShapesPickerModal;
