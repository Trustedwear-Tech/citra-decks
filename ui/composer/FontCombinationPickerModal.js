// FontCombinationPickerModal.js - Canva-like Font Combination Picker for Presentation Canvas
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    ScrollView,
    TextInput,
    StyleSheet,
    Platform,
    ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
    FONT_COMBINATIONS,
    FONT_CATEGORIES,
    CATEGORY_INFO,
    loadFonts,
    getFontsByCategory,
} from './FontCombinationsData';

// ===================== COMPONENT =====================
const FontCombinationPickerModal = ({ visible, onClose, onSelectCombination, theme }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState(null); // null = show all
    const [fontsLoaded, setFontsLoaded] = useState(false);
    const [loadingFonts, setLoadingFonts] = useState(false);

    // Memoized colors
    const colors = useMemo(() => ({
        background: theme?.background || '#ffffff',
        surface: theme?.surface || '#f5f5f5',
        text: theme?.text || '#333333',
        textSecondary: theme?.textSecondary || '#888888',
        primary: theme?.primary || '#2563EB',
        border: theme?.border || '#e0e0e0',
    }), [theme]);

    // Load fonts when modal opens
    useEffect(() => {
        if (visible && !fontsLoaded && Platform.OS === 'web') {
            setLoadingFonts(true);
            loadFonts()
                .then(() => {
                    setFontsLoaded(true);
                    setLoadingFonts(false);
                })
                .catch((err) => {
                    console.error('Failed to load fonts:', err);
                    setLoadingFonts(false);
                });
        }
    }, [visible, fontsLoaded]);

    // Filter combinations based on search and category
    const filteredCombinations = useMemo(() => {
        let combos = FONT_COMBINATIONS;

        if (selectedCategory) {
            combos = combos.filter(c => c.category === selectedCategory);
        }

        if (searchQuery.trim()) {
            const query = searchQuery.toLowerCase();
            combos = combos.filter(c =>
                c.name.toLowerCase().includes(query) ||
                c.headingFont.family.toLowerCase().includes(query) ||
                c.bodyFont.family.toLowerCase().includes(query) ||
                c.category.toLowerCase().includes(query)
            );
        }

        return combos;
    }, [searchQuery, selectedCategory]);

    // Group combinations by category for display
    const groupedCombinations = useMemo(() => {
        if (selectedCategory) {
            return { [selectedCategory]: filteredCombinations };
        }

        const grouped = {};
        filteredCombinations.forEach(combo => {
            if (!grouped[combo.category]) {
                grouped[combo.category] = [];
            }
            grouped[combo.category].push(combo);
        });
        return grouped;
    }, [filteredCombinations, selectedCategory]);

    const handleSelectCombination = useCallback((combination) => {
        if (onSelectCombination) {
            onSelectCombination(combination);
        }
        onClose();
    }, [onSelectCombination, onClose]);

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

    const renderFontPreview = (combination) => {
        const { headingFont, bodyFont, preview } = combination;

        return (
            <View style={styles.previewContainer}>
                {/* Heading preview */}
                <Text
                    style={[
                        styles.previewHeading,
                        {
                            fontFamily: Platform.OS === 'web' ? headingFont.family : 'System',
                            fontWeight: headingFont.weight,
                            color: colors.text,
                        }
                    ]}
                    numberOfLines={1}
                >
                    {preview.heading}
                </Text>

                {/* Subheading preview */}
                {preview.subheading && (
                    <Text
                        style={[
                            styles.previewSubheading,
                            {
                                fontFamily: Platform.OS === 'web' ? bodyFont.family : 'System',
                                fontWeight: bodyFont.weight,
                                color: colors.textSecondary,
                            }
                        ]}
                        numberOfLines={1}
                    >
                        {preview.subheading}
                    </Text>
                )}

                {/* Body preview if available */}
                {preview.body && (
                    <Text
                        style={[
                            styles.previewBody,
                            {
                                fontFamily: Platform.OS === 'web' ? bodyFont.family : 'System',
                                fontWeight: bodyFont.weight,
                                color: colors.textSecondary,
                            }
                        ]}
                        numberOfLines={1}
                    >
                        {preview.body}
                    </Text>
                )}
            </View>
        );
    };

    const renderCombinationCard = (combination) => (
        <TouchableOpacity
            key={combination.id}
            style={[styles.combinationCard, { backgroundColor: colors.surface, borderColor: colors.border }]}
            onPress={() => handleSelectCombination(combination)}
            activeOpacity={0.7}
        >
            {renderFontPreview(combination)}

            <View style={styles.fontInfo}>
                <Text style={[styles.fontName, { color: colors.text }]} numberOfLines={1}>
                    {combination.name}
                </Text>
                <Text style={[styles.fontDetails, { color: colors.textSecondary }]} numberOfLines={1}>
                    {combination.headingFont.family} + {combination.bodyFont.family}
                </Text>
            </View>
        </TouchableOpacity>
    );

    const renderCombinationGrid = (combinations) => (
        <View style={styles.combinationGrid}>
            {combinations.map(combo => renderCombinationCard(combo))}
        </View>
    );

    const renderContent = () => (
        <ScrollView
            style={styles.scrollView}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={true}
        >
            {loadingFonts && (
                <View style={styles.loadingContainer}>
                    <ActivityIndicator size="small" color={colors.primary} />
                    <Text style={[styles.loadingText, { color: colors.textSecondary }]}>
                        Loading fonts...
                    </Text>
                </View>
            )}

            {Object.entries(groupedCombinations).map(([category, combinations]) => (
                <View key={category} style={styles.categorySection}>
                    {!selectedCategory && (
                        <View style={styles.categorySectionHeader}>
                            <Ionicons
                                name={CATEGORY_INFO[category]?.icon || 'text-outline'}
                                size={18}
                                color={colors.text}
                            />
                            <Text style={[styles.categorySectionTitle, { color: colors.text }]}>
                                {CATEGORY_INFO[category]?.name || category}
                            </Text>
                            <Text style={[styles.categoryCount, { color: colors.textSecondary }]}>
                                {combinations.length}
                            </Text>
                        </View>
                    )}
                    {renderCombinationGrid(combinations)}
                </View>
            ))}

            {filteredCombinations.length === 0 && (
                <View style={styles.emptyState}>
                    <Ionicons name="search-outline" size={48} color={colors.textSecondary} />
                    <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                        No font combinations found for "{searchQuery}"
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
                            <Ionicons name="text" size={24} color={colors.primary} />
                            <Text style={[styles.title, { color: colors.text }]}>Font Combinations</Text>
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
                            placeholder="Search fonts..."
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

                    {/* Info Banner */}
                    <View style={[styles.infoBanner, { backgroundColor: colors.primary + '10', borderColor: colors.primary + '30' }]}>
                        <Ionicons name="information-circle-outline" size={16} color={colors.primary} />
                        <Text style={[styles.infoText, { color: colors.primary }]}>
                            Select a text element first, then click a font combination to apply
                        </Text>
                    </View>

                    {/* Category Tabs */}
                    {renderCategoryTabs()}

                    {/* Combinations Grid */}
                    {renderContent()}
                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.2)',
        justifyContent: 'flex-start',
        alignItems: 'flex-end',
        paddingTop: 70,
        paddingBottom: 20,
        paddingRight: 20,
    },
    modalContainer: {
        width: 350,
        maxWidth: '100%',
        height: '100%',
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
    infoBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        marginHorizontal: 16,
        marginBottom: 8,
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 8,
        borderWidth: 1,
        gap: 8,
    },
    infoText: {
        fontSize: 12,
        fontWeight: '500',
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
    scrollView: {
        flex: 1,
    },
    scrollContent: {
        paddingHorizontal: 16,
        paddingVertical: 12,
        paddingBottom: 24,
    },
    loadingContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 16,
        gap: 8,
    },
    loadingText: {
        fontSize: 14,
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
    combinationGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
    },
    combinationCard: {
        width: Platform.OS === 'web' ? 200 : '48%',
        minHeight: 140,
        borderRadius: 12,
        borderWidth: 1,
        padding: 16,
        justifyContent: 'space-between',
        ...Platform.select({
            web: {
                cursor: 'pointer',
                transition: 'all 0.2s ease',
            },
        }),
    },
    previewContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingVertical: 8,
    },
    previewHeading: {
        fontSize: 22,
        textAlign: 'center',
        marginBottom: 4,
    },
    previewSubheading: {
        fontSize: 14,
        textAlign: 'center',
        marginBottom: 2,
    },
    previewBody: {
        fontSize: 11,
        textAlign: 'center',
    },
    fontInfo: {
        borderTopWidth: 1,
        borderTopColor: '#e5e5e5',
        paddingTop: 10,
        marginTop: 8,
    },
    fontName: {
        fontSize: 12,
        fontWeight: '600',
        marginBottom: 2,
    },
    fontDetails: {
        fontSize: 10,
    },
    emptyState: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 40,
    },
    emptyText: {
        marginTop: 12,
        fontSize: 14,
    },
});

export default FontCombinationPickerModal;
