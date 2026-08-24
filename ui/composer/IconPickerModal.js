// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    View,
    Text,
    Modal,
    TextInput,
    TouchableOpacity,
    FlatList,
    ActivityIndicator,
    StyleSheet,
    Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SvgXml } from 'react-native-svg';
import { searchIcons, mapIconToPathAsync, getIconSVG } from './utils/iconMapper';

// Default "Local" Icons (Common usage)
const DEFAULT_ICONS = [
    'home', 'user', 'settings', 'search', 'menu',
    'check', 'x', 'arrow-right', 'arrow-left', 'chevron-down',
    'star', 'heart', 'share', 'download', 'upload',
    'trash', 'edit', 'plus', 'minus', 'alert-circle',
    'info', 'calendar', 'clock', 'image', 'file',
    'folder', 'mail', 'phone', 'map-pin', 'globe',
    'lock', 'unlock', 'eye', 'eye-off', 'camera',
    'video', 'mic', 'volume-2', 'battery', 'wifi'
];

const IconPreview = React.memo(({ iconName, color, size = 24 }) => {
    const [svgXml, setSvgXml] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;

        const loadIcon = async () => {
            try {
                setLoading(true);
                // Ensure we have the icon cached/fetched
                await mapIconToPathAsync(iconName);

                if (!mounted) return;

                // Get the SVG string
                const svgString = getIconSVG(iconName, { fill: color, size });
                setSvgXml(svgString);
            } catch (err) {
                console.warn(`Failed to load preview for ${iconName}`, err);
            } finally {
                if (mounted) setLoading(false);
            }
        };

        loadIcon();
        return () => { mounted = false; };
    }, [iconName, color, size]);

    if (loading) {
        return <ActivityIndicator size="small" color={color} />;
    }

    if (!svgXml) {
        return <Ionicons name="help-circle-outline" size={size} color={color} />;
    }

    return <SvgXml xml={svgXml} width={size} height={size} />;
});

export default function IconPickerModal({
    visible,
    onClose,
    onSelectIcon,
    theme,
}) {
    const [searchQuery, setSearchQuery] = useState('');
    const [icons, setIcons] = useState(DEFAULT_ICONS);
    const [isLoading, setIsLoading] = useState(false);
    const debounceTimerRef = useRef(null);

    // Reset state when modal opens/closes
    useEffect(() => {
        if (visible) {
            // Reset to default state when modal opens
            setSearchQuery('');
            setIcons(DEFAULT_ICONS);
            setIsLoading(false);
            // Clear any pending debounce timer
            if (debounceTimerRef.current) {
                clearTimeout(debounceTimerRef.current);
                debounceTimerRef.current = null;
            }
        }
    }, [visible]);

    // Handle Search
    useEffect(() => {
        if (searchQuery.length < 2) {
            setIcons(DEFAULT_ICONS);
            return;
        }

        setIsLoading(true);

        // Debounce
        if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);

        debounceTimerRef.current = setTimeout(async () => {
            try {
                const results = await searchIcons(searchQuery);
                setIcons(results.length > 0 ? results : []);
            } catch (error) {
                console.error('Icon search failed:', error);
            } finally {
                setIsLoading(false);
            }
        }, 500);

        return () => {
            if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
        };
    }, [searchQuery]);

    const renderItem = useCallback(({ item }) => {
        // Item is just a string (icon name)
        const iconName = item;

        return (
            <TouchableOpacity
                style={[styles.iconItem, { borderColor: theme.border }]}
                onPress={() => onSelectIcon(iconName)}
            >
                <IconPreview iconName={iconName} color={theme.text} size={28} />
                <Text style={[styles.iconName, { color: theme.textSecondary }]} numberOfLines={1}>
                    {iconName.split(':').pop()}
                </Text>
            </TouchableOpacity>
        );
    }, [theme, onSelectIcon]);

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={onClose}
        >
            <View style={styles.modalOverlay}>
                <View style={[styles.modalContent, { backgroundColor: theme.surface }]}>

                    {/* Header */}
                    <View style={[styles.header, { borderBottomColor: theme.border }]}>
                        <Text style={[styles.title, { color: theme.text }]}>Select Icon</Text>
                        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                            <Ionicons name="close" size={24} color={theme.text} />
                        </TouchableOpacity>
                    </View>

                    {/* Search */}
                    <View style={[styles.searchContainer, { backgroundColor: theme.background, borderColor: theme.border }]}>
                        <Ionicons name="search" size={20} color={theme.textSecondary} />
                        <TextInput
                            style={[styles.searchInput, { color: theme.text }]}
                            placeholder="Search icons (e.g. 'chart', 'user')..."
                            placeholderTextColor={theme.textSecondary}
                            value={searchQuery}
                            onChangeText={setSearchQuery}
                            autoFocus
                        />
                        {searchQuery.length > 0 && (
                            <TouchableOpacity onPress={() => setSearchQuery('')}>
                                <Ionicons name="close-circle" size={18} color={theme.textSecondary} />
                            </TouchableOpacity>
                        )}
                    </View>

                    {/* Grid */}
                    {isLoading ? (
                        <View style={styles.loadingContainer}>
                            <ActivityIndicator size="large" color={theme.primary} />
                            <Text style={{ marginTop: 12, color: theme.textSecondary }}>Searching icons...</Text>
                        </View>
                    ) : (
                        <FlatList
                            data={icons}
                            keyExtractor={(item) => item}
                            renderItem={renderItem}
                            numColumns={5}
                            contentContainerStyle={styles.listContent}
                            columnWrapperStyle={{ gap: 8 }}
                            showsVerticalScrollIndicator={false}
                            ListEmptyComponent={
                                <View style={styles.emptyContainer}>
                                    <Ionicons name="alert-circle-outline" size={32} color={theme.textSecondary} />
                                    <Text style={[styles.emptyText, { color: theme.textSecondary }]}>No icons found</Text>
                                </View>
                            }
                        />
                    )}

                    {/* Footer / Attribution */}
                    <View style={[styles.footer, { borderTopColor: theme.border }]}>
                        <Text style={[styles.footerText, { color: theme.textSecondary }]}>
                            Powered by Iconify • Includes Lucide, Material & more
                        </Text>
                    </View>

                </View>
            </View>
        </Modal>
    );
}

const styles = StyleSheet.create({
    modalOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    modalContent: {
        width: Platform.OS === 'web' ? 500 : '90%',
        height: '70%',
        maxWidth: '90%',
        maxHeight: 600,
        borderRadius: 12,
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.25,
        shadowRadius: 16,
        elevation: 10,
        display: 'flex',
        flexDirection: 'column',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
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
    searchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        margin: 16,
        paddingHorizontal: 12,
        height: 44,
        borderRadius: 8,
        borderWidth: 1,
        gap: 8,
    },
    searchInput: {
        flex: 1,
        fontSize: 16,
        height: '100%',
        outlineStyle: 'none',
    },
    listContent: {
        padding: 16,
        gap: 8,
    },
    iconItem: {
        flex: 1,
        aspectRatio: 1,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 1,
        borderRadius: 8,
        padding: 4,
        minWidth: 70, // Ensure decent size on web
    },
    iconName: {
        fontSize: 10,
        marginTop: 4,
        maxWidth: '100%',
        textAlign: 'center',
    },
    loadingContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    emptyContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 40,
        opacity: 0.7,
    },
    emptyText: {
        marginTop: 8,
        fontSize: 14,
    },
    footer: {
        padding: 12,
        borderTopWidth: 1,
        alignItems: 'center',
    },
    footerText: {
        fontSize: 11,
    },
});
