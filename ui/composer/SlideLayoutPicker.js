import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Modal, Platform, TextInput, Dimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SLIDE_TEMPLATES, TEMPLATE_CATEGORIES, getTemplatesByCategory } from './utils/slideTemplates';

const SlideLayoutPicker = ({ visible, onClose, onSelectLayout, theme, mobileViewOnly }) => {
    const [selectedCategory, setSelectedCategory] = useState('title');
    const [selectedLayoutId, setSelectedLayoutId] = useState(null);
    const [outlineText, setOutlineText] = useState('');
    const [specialInstructions, setSpecialInstructions] = useState('');

    // Reset state on open
    React.useEffect(() => {
        if (visible) {
            setSelectedLayoutId('ai_auto'); // Default to AI Decide
            setOutlineText('');
            setSpecialInstructions('');
        }
    }, [visible]);

    // Detailed visual preview based on template type (Ported from PresentationGoalInput)
    const renderThumbnail = (template) => {
        const isSelected = selectedLayoutId === template.id;

        // Define colors based on theme if not currently selecting a style
        // In this picker, we don't have a "selectedStyle" object with colors like in GoalInput
        // so we use the theme prop or defaults.
        const accentColor = theme.primary || '#3B82F6';
        const cardBg = '#f0f4f8';
        const textColor = theme.text || '#1f2937';
        // const bgColor = theme.surface || '#ffffff';

        // AI Auto-Decide Card
        if (template.id === 'ai_auto') {
            return (
                <View style={[
                    styles.thumbnail,
                    { borderColor: isSelected ? theme.primary : theme.border, borderWidth: isSelected ? 3 : 1 }
                ]}>
                    <View style={[styles.thumbContent, { backgroundColor: isSelected ? theme.primary + '10' : '#f9fafb', alignItems: 'center', justifyContent: 'center' }]}>
                        <Ionicons name="sparkles" size={24} color={theme.primary} />
                        <Text style={{ fontSize: 10, color: theme.primary, marginTop: 4, fontWeight: '600' }}>AI DECIDE</Text>
                    </View>
                    <Text style={[styles.templateName, { color: theme.primary, fontWeight: '700' }]}>{template.name}</Text>
                    {isSelected && (
                        <View style={[styles.checkBadge, { backgroundColor: theme.primary }]}>
                            <Ionicons name="checkmark" size={12} color="#fff" />
                        </View>
                    )}
                </View>
            );
        }

        const miniStyles = {
            slide: { flex: 1, padding: 6, justifyContent: 'center' }, // slightly more padding
            title: { height: 4, borderRadius: 2, marginBottom: 4 },
            line: { height: 2, borderRadius: 1, marginTop: 2 },
            row: { flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center', marginTop: 6, paddingHorizontal: 2 },
            card: { borderRadius: 3, padding: 3, alignItems: 'center' },
            icon: { width: 8, height: 8, borderRadius: 4, marginBottom: 2 },
            bullet: { width: 3, height: 3, borderRadius: 1.5, marginRight: 4 },
            imageBox: { borderRadius: 3, borderWidth: 1, borderStyle: 'dashed' },
            stepCircle: { width: 12, height: 12, borderRadius: 6, justifyContent: 'center', alignItems: 'center' },
            connector: { width: 8, height: 2, borderRadius: 1 },
        };

        const renderMiniPreviewContent = () => {
            switch (template.id) {
                case 'title_hero':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center', height: 6 }]} />
                            <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.5, width: '40%', alignSelf: 'center', marginTop: 4 }]} />
                        </View>
                    );
                case 'title_image':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '70%', alignSelf: 'center' }]} />
                            <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '50%', height: 36, alignSelf: 'center', marginTop: 8 }]} />
                        </View>
                    );
                case 'bullets':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                            <View style={{ height: 2, width: 20, backgroundColor: accentColor, marginLeft: 6, marginTop: 3 }} />
                            {[1, 2, 3].map(i => (
                                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginLeft: 8, marginTop: 5 }}>
                                    <View style={[miniStyles.bullet, { backgroundColor: accentColor }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: 60, marginTop: 0 }]} />
                                </View>
                            ))}
                        </View>
                    );
                case 'two_columns':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginBottom: 6 }]} />
                            <View style={miniStyles.row}>
                                {[1, 2].map(i => (
                                    <View key={i} style={[miniStyles.card, { backgroundColor: cardBg, width: '45%', height: 40 }]}>
                                        <View style={[miniStyles.icon, { backgroundColor: accentColor }]} />
                                        <View style={[miniStyles.line, { backgroundColor: textColor, width: '70%' }]} />
                                        <View style={[miniStyles.line, { backgroundColor: textColor, width: '50%', opacity: 0.5 }]} />
                                    </View>
                                ))}
                            </View>
                        </View>
                    );
                case 'three_cards':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center', marginBottom: 6 }]} />
                            <View style={miniStyles.row}>
                                {[1, 2, 3].map(i => (
                                    <View key={i} style={[miniStyles.card, { backgroundColor: cardBg, width: '30%', height: 40 }]}>
                                        <View style={[miniStyles.icon, { backgroundColor: accentColor }]} />
                                        <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                                    </View>
                                ))}
                            </View>
                        </View>
                    );
                case 'process_steps':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 6, marginTop: 6 }}>
                                {[0, 1, 2, 3].map(i => (
                                    <React.Fragment key={i}>
                                        <View style={{ width: 11, height: 11, borderRadius: 2, backgroundColor: accentColor, opacity: 0.85 }} />
                                        {i < 3 && <View style={{ flex: 1, height: 1.5, backgroundColor: accentColor, opacity: 0.4, marginHorizontal: 2 }} />}
                                    </React.Fragment>
                                ))}
                            </View>
                        </View>
                    );
                case 'org_hierarchy':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '50%', marginLeft: 6 }]} />
                            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                                <View style={{ width: 16, height: 8, borderRadius: 1, backgroundColor: accentColor }} />
                                <View style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                                <View style={{ width: '70%', height: 1, backgroundColor: accentColor, opacity: 0.6 }} />
                                <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '70%' }}>
                                    {[0, 1, 2].map(i => (
                                        <View key={i} style={{ width: 1, height: 6, backgroundColor: accentColor, opacity: 0.6 }} />
                                    ))}
                                </View>
                                <View style={{ flexDirection: 'row', justifyContent: 'space-between', width: '78%' }}>
                                    {[0, 1, 2].map(i => (
                                        <View key={i} style={{ width: 12, height: 7, borderRadius: 1, borderWidth: 1, borderColor: accentColor }} />
                                    ))}
                                </View>
                            </View>
                        </View>
                    );
                case 'infographic_diagram':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '55%', marginLeft: 6 }]} />
                            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                                <View style={{ width: 13, height: 13, borderRadius: 6.5, backgroundColor: accentColor, opacity: 0.7 }} />
                                <View style={{ width: 13, height: 13, borderRadius: 2, backgroundColor: accentColor, opacity: 0.5 }} />
                                <View style={{ width: 0, height: 0, borderLeftWidth: 6.5, borderRightWidth: 6.5, borderBottomWidth: 11, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: accentColor, opacity: 0.6 }} />
                                <View style={{ width: 13, height: 13, borderWidth: 1.5, borderColor: accentColor, borderRadius: 2 }} />
                            </View>
                        </View>
                    );
                case 'image_left':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%', marginLeft: 6, marginBottom: 6 }]} />
                            <View style={[miniStyles.row, { paddingHorizontal: 6 }]}>
                                <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 40 }]} />
                                <View style={{ width: '52%', paddingLeft: 6 }}>
                                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '100%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '80%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '90%' }]} />
                                </View>
                            </View>
                        </View>
                    );
                case 'image_right':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '80%', marginLeft: 6, marginBottom: 6 }]} />
                            <View style={[miniStyles.row, { paddingHorizontal: 6 }]}>
                                <View style={{ width: '52%', paddingRight: 6 }}>
                                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '100%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '80%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, opacity: 0.6, width: '90%' }]} />
                                </View>
                                <View style={[miniStyles.imageBox, { backgroundColor: cardBg, borderColor: accentColor, width: '42%', height: 40 }]} />
                            </View>
                        </View>
                    );
                case 'quote':
                    return (
                        <View style={miniStyles.slide}>
                            <Text style={{ position: 'absolute', top: 4, left: 10, fontSize: 30, color: accentColor, opacity: 0.3, fontWeight: 'bold' }}>"</Text>
                            <View style={{ alignItems: 'center', marginTop: 10 }}>
                                <View style={[miniStyles.line, { backgroundColor: textColor, width: '70%', height: 3 }]} />
                                <View style={[miniStyles.line, { backgroundColor: textColor, width: '50%', height: 3, marginTop: 4 }]} />
                                <View style={[miniStyles.line, { backgroundColor: accentColor, width: '30%', marginTop: 8 }]} />
                            </View>
                        </View>
                    );
                case 'data_dashboard':
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '40%', marginBottom: 8, alignSelf: 'center' }]} />
                            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'center' }}>
                                {/* Top Left Chart */}
                                <View style={{ width: '40%', height: 24, backgroundColor: cardBg, borderRadius: 2, alignItems: 'flex-end', justifyContent: 'flex-end', padding: 2 }}>
                                    <View style={{ flexDirection: 'row', gap: 1, alignItems: 'flex-end' }}>
                                        <View style={{ width: 3, height: 8, backgroundColor: accentColor }} />
                                        <View style={{ width: 3, height: 12, backgroundColor: accentColor }} />
                                        <View style={{ width: 3, height: 18, backgroundColor: accentColor }} />
                                    </View>
                                </View>
                                {/* Top Right Chart */}
                                <View style={{ width: '40%', height: 24, backgroundColor: cardBg, borderRadius: 2, alignItems: 'center', justifyContent: 'center' }}>
                                    <View style={{ width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: accentColor }} />
                                </View>
                                {/* Bottom Stats */}
                                <View style={{ width: '40%', height: 16, backgroundColor: cardBg, borderRadius: 2, padding: 3 }}>
                                    <View style={{ width: '60%', height: 2, backgroundColor: textColor }} />
                                    <View style={{ width: '40%', height: 4, backgroundColor: accentColor, marginTop: 2 }} />
                                </View>
                                <View style={{ width: '40%', height: 16, backgroundColor: cardBg, borderRadius: 2, padding: 3 }}>
                                    <View style={{ width: '60%', height: 2, backgroundColor: textColor }} />
                                    <View style={{ width: '40%', height: 4, backgroundColor: accentColor, marginTop: 2 }} />
                                </View>
                            </View>
                        </View>
                    );
                case 'modern_geometric':
                    return (
                        <View style={miniStyles.slide}>
                            {/* Decorative background shapes */}
                            <View style={{ position: 'absolute', top: 0, left: 0, width: 8, height: '100%', backgroundColor: accentColor }} />
                            <View style={{ position: 'absolute', top: -15, right: -15, width: 50, height: 50, backgroundColor: accentColor, opacity: 0.2, transform: [{ rotate: '45deg' }] }} />

                            <View style={{ flexDirection: 'row', height: '100%', paddingLeft: 14 }}>
                                <View style={{ flex: 1, paddingTop: 10 }}>
                                    <View style={[miniStyles.title, { backgroundColor: textColor, width: '90%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '80%' }]} />
                                    <View style={[miniStyles.line, { backgroundColor: textColor, width: '60%' }]} />
                                </View>
                                <View style={{ width: '40%', height: '70%', marginTop: 10, marginRight: 6, backgroundColor: cardBg, borderStyle: 'dashed', borderWidth: 1, borderColor: accentColor }} />
                            </View>
                        </View>
                    );
                default:
                    return (
                        <View style={miniStyles.slide}>
                            <View style={[miniStyles.title, { backgroundColor: textColor, width: '60%', alignSelf: 'center' }]} />
                        </View>
                    );
            }
        };

        // Standard card wrapper
        return (
            <View style={[
                styles.thumbnail,
                { borderColor: isSelected ? theme.primary : theme.border, borderWidth: isSelected ? 3 : 1 }
            ]}>
                <View style={[styles.thumbContent, { backgroundColor: '#f9fafb' }]}>
                    {renderMiniPreviewContent()}
                </View>
                <Text style={[styles.templateName, { color: theme.text }]}>{template.name}</Text>
                {isSelected && (
                    <View style={[styles.checkBadge, { backgroundColor: theme.primary }]}>
                        <Ionicons name="checkmark" size={12} color="#fff" />
                    </View>
                )}
            </View>
        );
    };

    const handleConfirm = (mode) => {
        if (!selectedLayoutId) return;
        onSelectLayout(selectedLayoutId, outlineText, mode, specialInstructions);
    };

    // Mobile simplified view — two options with outline & instructions inputs
    if (mobileViewOnly) {
        return (
            <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
                <TouchableOpacity style={mobileStyles.overlay} activeOpacity={1} onPress={onClose}>
                    <TouchableOpacity activeOpacity={1} style={[mobileStyles.sheet, { backgroundColor: theme.surface || '#fff' }]}>
                        {/* Handle bar */}
                        <View style={mobileStyles.handleBar}>
                            <View style={[mobileStyles.handle, { backgroundColor: theme.border || '#d1d5db' }]} />
                        </View>

                        {/* Title */}
                        <Text style={[mobileStyles.title, { color: theme.text }]}>Add New Slide</Text>

                        {/* Outline input - Required */}
                        <View style={mobileStyles.inputGroup}>
                            <Text style={[mobileStyles.inputLabel, { color: theme.textSecondary }]}>
                                Slide Outline / Topic <Text style={{ color: '#ef4444' }}>*</Text>
                            </Text>
                            <TextInput
                                style={[mobileStyles.input, { color: theme.text, borderColor: outlineText.trim() ? theme.border : '#ef444440', backgroundColor: theme.background || '#f9fafb' }]}
                                placeholder="e.g. Q4 Revenue Growth, Project Timeline..."
                                placeholderTextColor={(theme.textSecondary || '#6b7280') + '80'}
                                value={outlineText}
                                onChangeText={setOutlineText}
                            />
                        </View>

                        {/* Special instructions input */}
                        <View style={mobileStyles.inputGroup}>
                            <Text style={[mobileStyles.inputLabel, { color: theme.textSecondary }]}>Special Instructions</Text>
                            <TextInput
                                style={[mobileStyles.input, mobileStyles.multilineInput, { color: theme.text, borderColor: theme.border, backgroundColor: theme.background || '#f9fafb' }]}
                                placeholder="e.g. Use dark theme, focus on sales data..."
                                placeholderTextColor={(theme.textSecondary || '#6b7280') + '80'}
                                value={specialInstructions}
                                onChangeText={setSpecialInstructions}
                                multiline
                            />
                        </View>

                        {/* Two option buttons */}
                        <View style={mobileStyles.optionsRow}>
                            {/* Blank option */}
                            <TouchableOpacity
                                style={[mobileStyles.optionCard, { borderColor: theme.border, backgroundColor: theme.background || '#f9fafb', opacity: outlineText.trim() ? 1 : 0.45 }]}
                                onPress={() => {
                                    if (!outlineText.trim()) return;
                                    handleConfirm('manual');
                                    onClose();
                                }}
                                activeOpacity={0.7}
                            >
                                <Ionicons name="document-outline" size={22} color={theme.textSecondary || '#6b7280'} />
                                <Text style={[mobileStyles.optionTitle, { color: theme.text }]}>Blank</Text>
                            </TouchableOpacity>

                            {/* Let AI Decide option */}
                            <TouchableOpacity
                                style={[mobileStyles.optionCard, { borderColor: theme.primary + '40', backgroundColor: theme.primary + '08', opacity: outlineText.trim() ? 1 : 0.45 }]}
                                onPress={() => {
                                    if (!outlineText.trim()) return;
                                    handleConfirm('ai');
                                    onClose();
                                }}
                                activeOpacity={0.7}
                            >
                                <Ionicons name="sparkles" size={22} color={theme.primary} />
                                <Text style={[mobileStyles.optionTitle, { color: theme.primary }]}>Let AI Decide</Text>
                            </TouchableOpacity>
                        </View>
                    </TouchableOpacity>
                </TouchableOpacity>
            </Modal>
        );
    }

    return (
        <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
            <View style={styles.overlay}>
                <View style={[styles.modalContainer, { backgroundColor: theme.surface || '#fff' }]}>

                    {/* Header */}
                    <View style={[styles.header, { borderBottomColor: theme.border }]}>
                        <Text style={[styles.title, { color: theme.text }]}>New Slide</Text>
                        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                            <Ionicons name="close" size={24} color={theme.text} />
                        </TouchableOpacity>
                    </View>

                    {/* Body */}
                    <View style={styles.body}>
                        {/* Sidebar Categories */}
                        <View style={[styles.sidebar, { borderRightColor: theme.border }]}>
                            {TEMPLATE_CATEGORIES.map(cat => {
                                // Map generic icons to Ionicons
                                const getIconName = (id) => {
                                    switch (id) {
                                        case 'title': return 'layers-outline';
                                        case 'content': return 'document-text-outline';
                                        case 'media': return 'image-outline';
                                        case 'data': return 'bar-chart-outline';
                                        case 'advanced': return 'star-outline';
                                        default: return 'grid-outline';
                                    }
                                };
                                return (
                                    <TouchableOpacity
                                        key={cat.id}
                                        style={[
                                            styles.catBtn,
                                            selectedCategory === cat.id && { backgroundColor: theme.primary + '20' }
                                        ]}
                                        onPress={() => setSelectedCategory(cat.id)}
                                    >
                                        <Ionicons
                                            name={getIconName(cat.id)}
                                            size={18}
                                            color={selectedCategory === cat.id ? theme.primary : theme.textSecondary}
                                        />
                                        <Text style={[
                                            styles.catText,
                                            { color: selectedCategory === cat.id ? theme.primary : theme.textSecondary, fontWeight: selectedCategory === cat.id ? '600' : '500' }
                                        ]}>
                                            {cat.name}
                                        </Text>
                                    </TouchableOpacity>
                                );
                            })}
                        </View>

                        {/* Grid */}
                        <ScrollView style={styles.gridArea} contentContainerStyle={styles.gridContent}>
                            <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>
                                {TEMPLATE_CATEGORIES.find(c => c.id === selectedCategory)?.name}
                            </Text>

                            <View style={styles.grid}>
                                {/* AI Decision Card */}
                                <TouchableOpacity
                                    key="ai_auto"
                                    style={styles.gridItem}
                                    onPress={() => setSelectedLayoutId('ai_auto')}
                                >
                                    {renderThumbnail({ id: 'ai_auto', name: 'Let AI Decide', category: 'special' })}
                                </TouchableOpacity>

                                {getTemplatesByCategory(selectedCategory).map(template => (
                                    <TouchableOpacity
                                        key={template.id}
                                        style={styles.gridItem}
                                        onPress={() => setSelectedLayoutId(template.id)}
                                    >
                                        {renderThumbnail(template)}
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </ScrollView>
                    </View>

                    {/* Footer - Configuration & Actions */}
                    <View style={[styles.footer, { borderTopColor: theme.border }]}>
                        <View style={styles.footerInputContainer}>
                            <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>
                                Slide Outline / Topic <Text style={{ color: '#ef4444' }}>*</Text>
                            </Text>
                            <TextInput
                                style={[styles.outlineInput, { color: theme.text, borderColor: outlineText.trim() ? theme.border : '#ef444440', backgroundColor: theme.background }]}
                                placeholder="e.g. Q4 Revenue Growth, Project Timeline, Team Structure..."
                                placeholderTextColor={theme.textSecondary + '80'}
                                value={outlineText}
                                onChangeText={setOutlineText}
                            />
                        </View>

                        <View style={styles.footerInputContainer}>
                            <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>
                                Special Instructions (Optional)
                            </Text>
                            <TextInput
                                style={[styles.outlineInput, { color: theme.text, borderColor: theme.border, backgroundColor: theme.background, height: 80, textAlignVertical: 'top', paddingTop: 8 }]}
                                placeholder="e.g. Use a dark theme, focus on sales data, include a chart..."
                                placeholderTextColor={theme.textSecondary + '80'}
                                value={specialInstructions}
                                onChangeText={setSpecialInstructions}
                                multiline
                            />
                        </View>

                        <View style={styles.footerButtons}>
                            <TouchableOpacity
                                style={[styles.actionBtn, styles.manualBtn, { borderColor: theme.border, opacity: (selectedLayoutId && outlineText.trim()) ? 1 : 0.5 }]}
                                onPress={() => handleConfirm('manual')}
                                disabled={!selectedLayoutId || !outlineText.trim()}
                            >
                                <Ionicons name="create-outline" size={18} color={theme.text} />
                                <Text style={[styles.btnText, { color: theme.text }]}>Create Blank</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionBtn, styles.aiBtn, { backgroundColor: theme.primary, opacity: (selectedLayoutId && outlineText.trim()) ? 1 : 0.5 }]}
                                onPress={() => handleConfirm('ai')}
                                disabled={!selectedLayoutId || !outlineText.trim()}
                            >
                                <Ionicons name="sparkles" size={18} color="#fff" />
                                <Text style={[styles.btnText, { color: '#fff' }]}>Generate with AI</Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    modalContainer: {
        width: 800,
        height: 700, // Increased height for footer
        borderRadius: 12,
        overflow: 'hidden',
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.2,
        shadowRadius: 8,
        elevation: 10,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
    },
    title: {
        fontSize: 18,
        fontWeight: '600',
    },
    closeBtn: {
        padding: 4,
    },
    body: {
        flex: 1,
        flexDirection: 'row',
    },
    sidebar: {
        width: 200,
        borderRightWidth: 1,
        padding: 12,
        backgroundColor: '#fafafa', // Light grey sidebar
    },
    catBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 12,
        borderRadius: 8,
        marginBottom: 4,
        gap: 10,
    },
    catText: {
        fontSize: 14,
    },
    gridArea: {
        flex: 1,
        padding: 20,
    },
    gridContent: {
        paddingBottom: 40,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 16,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    grid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 20,
    },
    gridItem: {
        width: 160,
    },
    thumbnail: {
        width: '100%',
        aspectRatio: 16 / 9,
        borderWidth: 1,
        borderRadius: 8,
        overflow: 'hidden',
        marginBottom: 8,
        backgroundColor: '#fff',
    },
    thumbContent: {
        flex: 1,
    },
    templateName: {
        fontSize: 13,
        fontWeight: '500',
        textAlign: 'center',
    },
    checkBadge: {
        position: 'absolute',
        top: 4,
        right: 4,
        width: 20,
        height: 20,
        borderRadius: 10,
        alignItems: 'center',
        justifyContent: 'center',
    },
    // Footer Styles
    footer: {
        padding: 16,
        borderTopWidth: 1,
        backgroundColor: '#f9fafb',
        gap: 16,
    },
    footerInputContainer: {
        gap: 8,
    },
    inputLabel: {
        fontSize: 12,
        fontWeight: '600',
        textTransform: 'uppercase',
    },
    outlineInput: {
        height: 48,
        borderWidth: 1,
        borderRadius: 8,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    footerButtons: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        gap: 12,
    },
    actionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 8,
        gap: 8,
        minWidth: 140,
    },
    manualBtn: {
        borderWidth: 1,
        backgroundColor: 'transparent',
    },
    aiBtn: {
        // backgroundColor set inline
    },
    btnText: {
        fontSize: 14,
        fontWeight: '600',
    }
});

const mobileStyles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.4)',
        justifyContent: 'flex-end',
    },
    sheet: {
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        paddingHorizontal: 20,
        paddingBottom: 32,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: -2 },
        shadowOpacity: 0.15,
        shadowRadius: 8,
        elevation: 10,
    },
    handleBar: {
        alignItems: 'center',
        paddingTop: 12,
        paddingBottom: 8,
    },
    handle: {
        width: 40,
        height: 4,
        borderRadius: 2,
    },
    title: {
        fontSize: 18,
        fontWeight: '700',
        textAlign: 'center',
        marginBottom: 16,
    },
    inputGroup: {
        marginBottom: 12,
    },
    inputLabel: {
        fontSize: 12,
        fontWeight: '600',
        textTransform: 'uppercase',
        letterSpacing: 0.3,
        marginBottom: 6,
    },
    input: {
        height: 44,
        borderWidth: 1,
        borderRadius: 10,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    multilineInput: {
        height: 72,
        textAlignVertical: 'top',
        paddingTop: 10,
    },
    optionsRow: {
        flexDirection: 'row',
        gap: 12,
        marginTop: 8,
    },
    optionCard: {
        flex: 1,
        flexDirection: 'row',
        borderWidth: 1.5,
        borderRadius: 12,
        paddingVertical: 14,
        paddingHorizontal: 16,
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
    },
    optionTitle: {
        fontSize: 15,
        fontWeight: '700',
    },
});

export default SlideLayoutPicker;
