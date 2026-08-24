// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * TemplateSelector - Visual template picker for presentations
 * 
 * Shows template thumbnails with live style preview.
 * Replaces the initial style picker during presentation generation.
 */

import React, { useState, useMemo } from 'react';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    Dimensions,
    Platform,
} from 'react-native';
import { Feather } from '@expo/vector-icons';
import { SLIDE_TEMPLATES, TEMPLATE_CATEGORIES, getTemplatesByCategory } from './utils/slideTemplates';
import { PRESET_STYLES } from './PresentationStylePicker';

const { width: screenWidth } = Dimensions.get('window');
const isWeb = Platform.OS === 'web';
const THUMBNAIL_WIDTH = isWeb ? 160 : 140;
const THUMBNAIL_HEIGHT = 90; // 16:9 ratio

// ==================== Template Thumbnail ====================

const TemplateThumbnail = ({ template, style, isSelected, onSelect }) => {
    const accentColor = style?.accentColor || style?.preview?.accent || '#3B82F6';
    const cardBg = style?.cardBackground || '#f0f4f8';
    const textColor = style?.textPrimary || style?.textStyles?.title?.color || '#1f2937';
    const bgColor = style?.slideBackground || '#ffffff';

    // Generate mini-preview based on template type
    const renderMiniPreview = () => {
        switch (template.id) {
            case 'title_hero':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginTop: 28 }]} />
                        <View style={[styles.miniSubtitle, { backgroundColor: textColor, opacity: 0.5, width: '40%', alignSelf: 'center', marginTop: 6 }]} />
                        <View style={[styles.miniCircle, { backgroundColor: accentColor, opacity: 0.3, left: 8, bottom: 8 }]} />
                    </View>
                );
            
            case 'title_image':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '70%', alignSelf: 'center', marginTop: 6 }]} />
                        <View style={[styles.miniImageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '50%', height: 45, alignSelf: 'center', marginTop: 8 }]} />
                    </View>
                );
            
            case 'bullets':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '50%', marginLeft: 8, marginTop: 8 }]} />
                        <View style={[styles.miniDivider, { backgroundColor: accentColor, marginLeft: 8, marginTop: 4 }]} />
                        {[1, 2, 3].map(i => (
                            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginLeft: 12, marginTop: 6 }}>
                                <View style={[styles.miniBullet, { backgroundColor: accentColor }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, opacity: 0.6, width: 60 }]} />
                            </View>
                        ))}
                    </View>
                );
            
            case 'two_columns':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginTop: 6 }]} />
                        <View style={styles.miniRow}>
                            <View style={[styles.miniCard, { backgroundColor: cardBg, width: '42%', height: 48 }]}>
                                <View style={[styles.miniIcon, { backgroundColor: accentColor }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, width: '70%' }]} />
                            </View>
                            <View style={[styles.miniCard, { backgroundColor: cardBg, width: '42%', height: 48 }]}>
                                <View style={[styles.miniIcon, { backgroundColor: accentColor }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, width: '70%' }]} />
                            </View>
                        </View>
                    </View>
                );
            
            case 'three_cards':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginTop: 6 }]} />
                        <View style={styles.miniRow}>
                            {[1, 2, 3].map(i => (
                                <View key={i} style={[styles.miniCard, { backgroundColor: cardBg, width: '28%', height: 46 }]}>
                                    <View style={[styles.miniIcon, { backgroundColor: accentColor }]} />
                                    <View style={[styles.miniLine, { backgroundColor: textColor, width: '80%', marginTop: 4 }]} />
                                </View>
                            ))}
                        </View>
                    </View>
                );
            
            case 'image_left':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '80%', marginLeft: 8, marginTop: 6 }]} />
                        <View style={styles.miniRow}>
                            <View style={[styles.miniImageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 50 }]} />
                            <View style={{ width: '42%', paddingLeft: 6 }}>
                                <View style={[styles.miniLine, { backgroundColor: textColor, width: '100%', marginTop: 4 }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, opacity: 0.6, width: '100%', marginTop: 3 }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, opacity: 0.6, width: '80%', marginTop: 3 }]} />
                            </View>
                        </View>
                    </View>
                );
            
            case 'image_right':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '80%', marginLeft: 8, marginTop: 6 }]} />
                        <View style={styles.miniRow}>
                            <View style={{ width: '42%', paddingRight: 6, paddingLeft: 8 }}>
                                <View style={[styles.miniLine, { backgroundColor: textColor, width: '100%', marginTop: 4 }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, opacity: 0.6, width: '100%', marginTop: 3 }]} />
                                <View style={[styles.miniLine, { backgroundColor: textColor, opacity: 0.6, width: '80%', marginTop: 3 }]} />
                            </View>
                            <View style={[styles.miniImageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 50 }]} />
                        </View>
                    </View>
                );
            
            case 'process_steps':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '50%', marginLeft: 8, marginTop: 6 }]} />
                        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 8 }}>
                            {[0, 1, 2, 3].map(i => (
                                <React.Fragment key={i}>
                                    <View style={{ width: 12, height: 12, borderRadius: 2, backgroundColor: accentColor, opacity: 0.85 }} />
                                    {i < 3 && <View style={{ flex: 1, height: 1.5, backgroundColor: accentColor, opacity: 0.4, marginHorizontal: 2 }} />}
                                </React.Fragment>
                            ))}
                        </View>
                    </View>
                );
            case 'org_hierarchy':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '50%', marginLeft: 8, marginTop: 6 }]} />
                        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                            <View style={{ width: 18, height: 9, borderRadius: 1, backgroundColor: accentColor }} />
                            <View style={{ width: 1, height: 8, backgroundColor: accentColor, opacity: 0.6 }} />
                            <View style={{ width: '70%', height: 1, backgroundColor: accentColor, opacity: 0.6 }} />
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '70%' }}>
                                {[0, 1, 2].map(i => (
                                    <View key={i} style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                                ))}
                            </View>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '78%' }}>
                                {[0, 1, 2].map(i => (
                                    <View key={i} style={{ width: 14, height: 8, borderRadius: 1, borderWidth: 1, borderColor: accentColor }} />
                                ))}
                            </View>
                        </View>
                    </View>
                );
            case 'infographic_diagram':
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor, width: '55%', marginLeft: 8, marginTop: 6 }]} />
                        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                            <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: accentColor, opacity: 0.7 }} />
                            <View style={{ width: 14, height: 14, borderRadius: 2, backgroundColor: accentColor, opacity: 0.5 }} />
                            <View style={{ width: 0, height: 0, borderLeftWidth: 7, borderRightWidth: 7, borderBottomWidth: 12, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: accentColor, opacity: 0.6 }} />
                            <View style={{ width: 14, height: 14, borderWidth: 1.5, borderColor: accentColor, borderRadius: 2 }} />
                        </View>
                    </View>
                );
            
            case 'quote':
                return (
                    <View style={styles.miniSlide}>
                        <Text style={[styles.miniQuoteMark, { color: accentColor, opacity: 0.3 }]}>"</Text>
                        <View style={{ alignItems: 'center', marginTop: 20 }}>
                            <View style={[styles.miniLine, { backgroundColor: textColor, width: '70%' }]} />
                            <View style={[styles.miniLine, { backgroundColor: textColor, width: '50%', marginTop: 4 }]} />
                            <View style={[styles.miniLine, { backgroundColor: accentColor, width: '30%', marginTop: 8, height: 3 }]} />
                        </View>
                    </View>
                );
            
            default:
                return (
                    <View style={styles.miniSlide}>
                        <View style={[styles.miniTitle, { backgroundColor: textColor }]} />
                    </View>
                );
        }
    };

    return (
        <TouchableOpacity
            style={[
                styles.thumbnailContainer,
                isSelected && { borderColor: accentColor, borderWidth: 3 },
            ]}
            onPress={() => onSelect(template.id)}
            activeOpacity={0.7}
        >
            <View style={[styles.thumbnailSlide, { backgroundColor: bgColor }]}>
                {renderMiniPreview()}
            </View>
            <Text
                style={[styles.thumbnailLabel, isSelected && { color: accentColor, fontWeight: '600' }]}
                numberOfLines={1}
            >
                {template.name}
            </Text>
            {isSelected && (
                <View style={[styles.selectedBadge, { backgroundColor: accentColor }]}>
                    <Feather name="check" size={12} color="#fff" />
                </View>
            )}
        </TouchableOpacity>
    );
};

// ==================== Style Pill ====================

const StylePill = ({ style, isSelected, onSelect }) => {
    const accentColor = style.accentColor || '#3B82F6';
    const bgColor = style.slideBackground || '#ffffff';

    return (
        <TouchableOpacity
            style={[
                styles.stylePill,
                { borderColor: isSelected ? accentColor : '#e5e7eb' },
                isSelected && { borderWidth: 2 },
            ]}
            onPress={onSelect}
            activeOpacity={0.7}
        >
            <View style={styles.stylePillColors}>
                <View style={[styles.colorDot, { backgroundColor: bgColor, borderWidth: 1, borderColor: '#e5e7eb' }]} />
                <View style={[styles.colorDot, { backgroundColor: accentColor }]} />
            </View>
            <Text style={[styles.stylePillLabel, isSelected && { fontWeight: '600', color: accentColor }]}>
                {style.name}
            </Text>
        </TouchableOpacity>
    );
};

// ==================== Main Component ====================

export const TemplateSelector = ({
    selectedTemplate,
    onSelectTemplate,
    selectedStyle,
    onSelectStyle,
    style: containerStyle,
}) => {
    const [activeCategory, setActiveCategory] = useState('content');
    
    const styles_list = useMemo(() => PRESET_STYLES, []);
    const currentStyle = PRESET_STYLES.find(s => s.id === selectedStyle) || PRESET_STYLES[0];
    const templatesInCategory = useMemo(
        () => getTemplatesByCategory(activeCategory),
        [activeCategory]
    );

    return (
        <View style={[styles.container, containerStyle]}>
            {/* Style Selection */}
            <View style={styles.section}>
                <Text style={styles.sectionTitle}>Choose Style</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.styleScroll}>
                    {styles_list.map(st => (
                        <StylePill
                            key={st.id}
                            style={st}
                            isSelected={selectedStyle === st.id}
                            onSelect={() => onSelectStyle(st.id)}
                        />
                    ))}
                </ScrollView>
            </View>

            {/* Category Tabs */}
            <View style={styles.section}>
                <Text style={styles.sectionTitle}>Choose Template</Text>
                <View style={styles.categoryTabs}>
                    {TEMPLATE_CATEGORIES.map(cat => (
                        <TouchableOpacity
                            key={cat.id}
                            style={[
                                styles.categoryTab,
                                activeCategory === cat.id && { 
                                    backgroundColor: currentStyle.accentColor || '#3B82F6',
                                },
                            ]}
                            onPress={() => setActiveCategory(cat.id)}
                        >
                            <Feather
                                name={cat.icon}
                                size={14}
                                color={activeCategory === cat.id ? '#fff' : '#6b7280'}
                            />
                            <Text
                                style={[
                                    styles.categoryTabText,
                                    activeCategory === cat.id && { color: '#fff' },
                                ]}
                            >
                                {cat.name}
                            </Text>
                        </TouchableOpacity>
                    ))}
                </View>
            </View>

            {/* Template Grid */}
            <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                style={styles.templateScroll}
                contentContainerStyle={styles.templateScrollContent}
            >
                {templatesInCategory.map(template => (
                    <TemplateThumbnail
                        key={template.id}
                        template={template}
                        style={currentStyle}
                        isSelected={selectedTemplate === template.id}
                        onSelect={onSelectTemplate}
                    />
                ))}
            </ScrollView>

            {/* Preview hint */}
            {selectedTemplate && (
                <View style={styles.previewHint}>
                    <Feather name="info" size={14} color="#6b7280" />
                    <Text style={styles.previewHintText}>
                        {SLIDE_TEMPLATES[selectedTemplate]?.description || 'Selected template'}
                    </Text>
                </View>
            )}
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        borderWidth: 1,
        borderColor: '#e5e7eb',
    },
    section: {
        marginBottom: 16,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '600',
        color: '#374151',
        marginBottom: 10,
    },
    
    // Style Pills
    styleScroll: {
        flexDirection: 'row',
    },
    stylePill: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: '#e5e7eb',
        marginRight: 8,
        backgroundColor: '#fff',
    },
    stylePillColors: {
        flexDirection: 'row',
        marginRight: 6,
    },
    colorDot: {
        width: 14,
        height: 14,
        borderRadius: 7,
        marginRight: 2,
    },
    stylePillLabel: {
        fontSize: 13,
        color: '#4b5563',
    },

    // Category Tabs
    categoryTabs: {
        flexDirection: 'row',
        gap: 8,
    },
    categoryTab: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: 20,
        backgroundColor: '#f3f4f6',
        gap: 6,
    },
    categoryTabText: {
        fontSize: 13,
        color: '#6b7280',
        fontWeight: '500',
    },

    // Template Thumbnails
    templateScroll: {
        marginTop: 8,
    },
    templateScrollContent: {
        paddingBottom: 8,
        gap: 12,
    },
    thumbnailContainer: {
        marginRight: 12,
        borderRadius: 10,
        borderWidth: 2,
        borderColor: '#e5e7eb',
        overflow: 'hidden',
        backgroundColor: '#fff',
        position: 'relative',
    },
    thumbnailSlide: {
        width: THUMBNAIL_WIDTH,
        height: THUMBNAIL_HEIGHT,
        overflow: 'hidden',
    },
    thumbnailLabel: {
        fontSize: 12,
        color: '#6b7280',
        textAlign: 'center',
        paddingVertical: 6,
        paddingHorizontal: 4,
        backgroundColor: '#f9fafb',
    },
    selectedBadge: {
        position: 'absolute',
        top: 4,
        right: 4,
        width: 20,
        height: 20,
        borderRadius: 10,
        justifyContent: 'center',
        alignItems: 'center',
    },

    // Mini Preview Elements
    miniSlide: {
        flex: 1,
        padding: 4,
    },
    miniTitle: {
        height: 5,
        borderRadius: 2,
        width: '60%',
        marginLeft: 8,
        marginTop: 8,
    },
    miniSubtitle: {
        height: 3,
        borderRadius: 1.5,
        marginTop: 4,
    },
    miniDivider: {
        height: 2,
        width: '90%',
        borderRadius: 1,
    },
    miniRow: {
        flexDirection: 'row',
        justifyContent: 'space-around',
        alignItems: 'center',
        marginTop: 10,
        paddingHorizontal: 8,
    },
    miniCard: {
        borderRadius: 4,
        padding: 4,
        alignItems: 'center',
        justifyContent: 'center',
    },
    miniIcon: {
        width: 10,
        height: 10,
        borderRadius: 5,
    },
    miniLine: {
        height: 3,
        borderRadius: 1.5,
    },
    miniBullet: {
        width: 4,
        height: 4,
        borderRadius: 2,
        marginRight: 6,
    },
    miniCircle: {
        position: 'absolute',
        width: 20,
        height: 20,
        borderRadius: 10,
    },
    miniImageBox: {
        borderRadius: 4,
        borderWidth: 1,
        borderStyle: 'dashed',
        justifyContent: 'center',
        alignItems: 'center',
    },
    miniStepCircle: {
        width: 14,
        height: 14,
        borderRadius: 7,
        justifyContent: 'center',
        alignItems: 'center',
    },
    miniStepNumber: {
        color: '#fff',
        fontSize: 8,
        fontWeight: 'bold',
    },
    miniConnector: {
        width: 12,
        height: 2,
        borderRadius: 1,
    },
    miniQuoteMark: {
        position: 'absolute',
        top: 0,
        left: 8,
        fontSize: 36,
        fontWeight: 'bold',
        lineHeight: 36,
    },

    // Preview Hint
    previewHint: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginTop: 8,
        paddingTop: 12,
        borderTopWidth: 1,
        borderTopColor: '#f3f4f6',
    },
    previewHintText: {
        fontSize: 13,
        color: '#6b7280',
        flex: 1,
    },
});

export default TemplateSelector;
