// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// printableListModal.js - Full-screen modal to browse, load, and manage saved printables
// Enhanced with Canva-like card grid layout and thumbnail previews
import React, { useState, useEffect, useCallback } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    ScrollView,
    ActivityIndicator,
    Alert,
    Platform,
    Image,
    Dimensions,
    FlatList
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import LazyThumbnail from '../ui/LazyThumbnail';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Calculate responsive grid columns based on screen width
const getGridColumns = (width) => {
    if (width >= 1400) return 5;
    if (width >= 1100) return 4;
    if (width >= 800) return 3;
    if (width >= 500) return 2;
    return 1;
};

const printableListModal = ({
    visible,
    onClose,
    onLoadprintable,
    onCreateNew,
    apiConfig,
    userDeviceId,
    theme,
    selectedVaultName
}) => {
    const [printables, setprintables] = useState([]);
    const [sharedprintables, setSharedprintables] = useState([]);
    const [activeTab, setActiveTab] = useState('my'); // 'my' | 'shared'
    const [isLoading, setIsLoading] = useState(false);
    const [isFetchingMore, setIsFetchingMore] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [offset, setOffset] = useState(0);
    const LIMIT = 20;

    // Teams removed — every artifact lives in the personal workspace.
    const activeTeamId = null;

    const [error, setError] = useState(null);
    const [imageLoadErrors, setImageLoadErrors] = useState({});
    const [deleteConfirmation, setDeleteConfirmation] = useState({ visible: false, title: '', onConfirm: () => { } });
    const [screenDimensions, setScreenDimensions] = useState({ width: SCREEN_WIDTH, height: SCREEN_HEIGHT });
    const isMobile = screenDimensions.width < 768;

    const handleImageError = (id) => {
        setImageLoadErrors(prev => ({ ...prev, [id]: true }));
    };

    // Update dimensions on resize (for web)
    useEffect(() => {
        if (Platform.OS === 'web') {
            const handleResize = () => {
                setScreenDimensions({
                    width: window.innerWidth,
                    height: window.innerHeight
                });
            };
            window.addEventListener('resize', handleResize);
            handleResize();
            return () => window.removeEventListener('resize', handleResize);
        }
    }, []);

    const safeTheme = theme || {
        background: '#ffffff',
        text: '#333333',
        primary: '#2196F3',
        surface: '#f5f5f5',
        borderColor: '#e0e0e0'
    };

    // Fetch printables from server
    const fetchprintables = useCallback(async (isLoadMore = false) => {
        // No device-id gate. The shell passes userDeviceId: null, so this used
        // to return before fetching -- the list rendered empty and anything you
        // saved was unreachable from the UI even though the server had it. The
        // request is authorised by the bearer token and scoped to the caller
        // server-side; X-Device-ID is not read anywhere in the backend.
        if (isLoadMore && (!hasMore || isFetchingMore)) return;

        try {
            if (isLoadMore) {
                setIsFetchingMore(true);
            } else {
                setIsLoading(true);
            }
            setError(null);

            const token = await AsyncStorage.getItem('@auth_token');
            const currentOffset = isLoadMore ? offset : 0;

            // Fetch ALL user printables (user-level, not workspace-specific)
            let url = `${apiConfig.API_URL}/printable/list?skip=${currentOffset}&limit=${LIMIT}&all_workspaces=true`;
            // Remove team_id filter to get all user printables across all workspaces

            const response = await fetch(
                url,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                const newItems = data.printables || [];
                const myItems = newItems.filter(item => !item.isShared);

                if (isLoadMore) {
                    setprintables(prev => [...prev, ...myItems]);
                } else {
                    setprintables(myItems);
                }

                // Update pagination state based on MY items count
                setOffset(currentOffset + myItems.length);
                setHasMore(myItems.length === LIMIT);
            } else {
                // Stop further auto-load attempts on failure to avoid infinite retries
                setHasMore(false);
                throw new Error('Failed to fetch printables');
            }
        } catch (err) {
            console.error('Failed to fetch printables:', err);
            if (!isLoadMore) setError('Failed to load printables');
            // Prevent repeated edge-triggered retries when backend is failing
            setHasMore(false);
        } finally {
            setIsLoading(false);
            setIsFetchingMore(false);
        }
    }, [apiConfig.API_URL, userDeviceId, hasMore, isFetchingMore, offset, activeTeamId]);

    // Fetch shared printables
    const fetchSharedprintables = useCallback(async () => {
        try {
            setIsLoading(true);
            setError(null);
            console.log('Fetching ALL shared printables (user-level, all workspaces) for', userDeviceId);

            // Fetch all shared printables via centralized sharing endpoint
            const token = await AsyncStorage.getItem('@auth_token');
            const response = await fetch(
                `${apiConfig.API_URL}/api/sharing/my-shared/printable`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                        'X-Device-ID': userDeviceId
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                // Map from centralized sharing response
                const mapped = (data.resources || []).map(item => ({
                    id: item.resource_id,
                    title: item.title || item.resource_id,
                    updated_at: item.shared_at,
                    thumbnail: null,
                    goal: `Shared by ${item.shared_by || item.owner_id}`,
                    owner_id: item.owner_id,
                    isShared: true,
                    permission: item.permission
                }));
                setSharedprintables(mapped);
            } else {
                console.warn('Failed to fetch shared items status:', response.status);
                // Don't error out hard, just show empty
                setSharedprintables([]);
            }
        } catch (err) {
            console.error('Failed to fetch shared printables:', err);
            // Don't show critical error for shared section
        } finally {
            setIsLoading(false);
        }
    }, [apiConfig.API_URL, userDeviceId]);

    useEffect(() => {
        if (visible) {
            if (activeTab === 'my') {
                // Reset pagination on tab switch or open
                setOffset(0);
                setHasMore(true);
                fetchprintables(false);
            } else {
                fetchSharedprintables();
            }
        }
    }, [visible, activeTab]);

    const handleLoadMore = () => {
        // Do not retry if a previous fetch failed (error or hasMore false)
        if (activeTab === 'my' && !isLoading && !isFetchingMore && hasMore && !error) {
            fetchprintables(true);
        }
    };

    const handleLoadprintable = async (printableId) => {
        console.log('[printable_LIST_MODAL] Loading printable ID:', printableId);
        try {
            setIsLoading(true);
            const token = await AsyncStorage.getItem('@auth_token');

            const response = await fetch(
                `${apiConfig.API_URL}/printable/load/${printableId}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                console.log('[printable_LIST_MODAL] Fetched printable data:', data);

                // Call onLoadprintable with the printable data
                onLoadprintable(data.printable || data);
                onClose();
            } else {
                throw new Error('Failed to load printable');
            }
        } catch (err) {
            console.error('Failed to load printable:', err);
            Alert.alert('Error', 'Failed to load.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleDeleteprintable = async (printableId, title) => {
        const confirmDelete = async () => {
            try {
                const token = await AsyncStorage.getItem('@auth_token');
                const response = await fetch(
                    `${apiConfig.API_URL}/printable/${printableId}`,
                    {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    }
                );

                if (response.ok) {
                    setprintables(prev => prev.filter(p => p.id !== printableId));
                    console.log('✅ printable deleted successfully');
                } else {
                    const errData = await response.json().catch(() => ({}));
                    console.error('❌ Delete failed:', response.status, errData);
                    throw new Error(errData.detail || 'Failed to delete');
                }
            } catch (err) {
                console.error('❌ Delete error:', err);
                if (Platform.OS === 'web') {
                    window.alert('Failed to delete: ' + err.message);
                } else {
                    Alert.alert('Error', 'Failed to delete.');
                }
            } finally {
                setDeleteConfirmation({ visible: false, title: '', onConfirm: () => { } });
            }
        };

        // Use custom modal
        setDeleteConfirmation({
            visible: true,
            title: title,
            onConfirm: confirmDelete
        });
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return 'Unknown date';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    // Calculate grid layout
    // On web, the modal is constrained to 95% width or max 1400px
    const getContainerWidth = (screenWidth) => {
        if (Platform.OS === 'web') {
            return isMobile ? screenWidth : Math.min(screenWidth * 0.95, 1400);
        }
        return screenWidth;
    };

    const containerWidth = getContainerWidth(screenDimensions.width);
    const gridColumns = getGridColumns(containerWidth);
    const gridPadding = isMobile ? 24 : 80;
    const gridGap = isMobile ? 12 : 20;
    const cardWidth = Math.floor((containerWidth - gridPadding - (gridColumns - 1) * gridGap) / gridColumns);
    const thumbnailHeight = Math.floor(cardWidth * 9 / 16); // 16:9 aspect ratio

    // Render printable card with thumbnail
    const renderprintableCard = (printable) => {
        const hasThumbnail = printable.thumbnail && typeof printable.thumbnail === 'string';

        return (
            <TouchableOpacity
                key={printable.id}
                style={[
                    styles.printableCard,
                    {
                        width: cardWidth,
                        backgroundColor: safeTheme.surface,
                        borderColor: safeTheme.borderColor,
                    }
                ]}
                onPress={() => handleLoadprintable(printable.id)}
                activeOpacity={0.8}
            >
                {/* Thumbnail Area */}
                <View style={[styles.cardThumbnail, { height: thumbnailHeight }]}>
                    {hasThumbnail && !imageLoadErrors[printable.id] ? (
                        <LazyThumbnail
                            uri={printable.thumbnail}
                            style={styles.thumbnailImage}
                            resizeMode="cover"
                            onError={() => handleImageError(printable.id)}
                            placeholder={
                                <View style={[styles.thumbnailPlaceholder, { backgroundColor: safeTheme.primary + '08' }]}>
                                    <ActivityIndicator size="small" color={safeTheme.primary} />
                                </View>
                            }
                        />
                    ) : (
                        <View style={[styles.thumbnailPlaceholder, { backgroundColor: safeTheme.primary + '15' }]}>
                            <Ionicons name="easel" size={48} color={safeTheme.primary} />
                        </View>
                    )}

                    {/* Delete button overlay - hidden for shared printables */}
                    {!printable.isShared && (
                    <TouchableOpacity
                        style={styles.cardDeleteBtn}
                        onPress={(e) => {
                            e.stopPropagation();
                            handleDeleteprintable(printable.id, printable.title);
                        }}
                    >
                        <MaterialIcons name="delete" size={18} color="#fff" />
                    </TouchableOpacity>
                    )}

                    {/* PAGE count badge */}
                    {printable.PAGE_count && (
                        <View style={styles.PAGECountBadge}>
                            <Text style={styles.PAGECountText}>{printable.PAGE_count} PAGES</Text>
                        </View>
                    )}
                </View>

                {/* Card Info */}
                <View style={styles.cardInfo}>
                    <Text style={[styles.cardTitle, { color: safeTheme.text }]} numberOfLines={2}>
                        {printable.title || 'Untitled'}
                    </Text>
                    <Text style={styles.cardMeta}>
                        {formatDate(printable.updated_at || printable.created_at)}
                    </Text>
                    {printable.goal && (
                        <Text style={styles.cardGoal} numberOfLines={1}>
                            {(() => {
                                if (!printable.goal) return '';
                                if (typeof printable.goal === 'string') return printable.goal;
                                if (typeof printable.goal === 'object') {
                                    const p = printable.goal;
                                    if (p.purpose && typeof p.purpose === 'string') return p.purpose;
                                    if (p.printableType && typeof p.printableType === 'string') return p.printableType;
                                    return 'printable';
                                }
                                return 'printable';
                            })()}
                        </Text>
                    )}
                    {printable.workspace_name && printable.isShared && (
                        <View style={styles.workspaceBadge}>
                            <Ionicons name="briefcase-outline" size={11} color="#6B7280" />
                            <Text style={styles.workspaceBadgeText}>{printable.workspace_name}</Text>
                        </View>
                    )}
                </View>
            </TouchableOpacity>
        );
    };

    // Create New printable Card
    const renderCreateNewCard = () => (
        <TouchableOpacity
            style={[
                styles.printableCard,
                styles.createNewCard,
                {
                    width: cardWidth,
                    borderColor: safeTheme.primary,
                }
            ]}
            onPress={onCreateNew}
            activeOpacity={0.8}
        >
            <View style={[styles.cardThumbnail, styles.createNewThumbnail, { height: thumbnailHeight, backgroundColor: safeTheme.primary + '10' }]}>
                <View style={[styles.createNewIcon, { backgroundColor: safeTheme.primary }]}>
                    <Ionicons name="add" size={36} color="#fff" />
                </View>
            </View>
            <View style={styles.cardInfo}>
                <Text style={[styles.cardTitle, { color: safeTheme.primary, fontWeight: '600' }]}>
                    Create New Visual Report
                </Text>
                <Text style={styles.cardMeta}>
                    Start from scratch
                </Text>
            </View>
        </TouchableOpacity>
    );

    const content = (
        <View style={[styles.fullScreenContainer, { backgroundColor: safeTheme.background }]}>
            {/* Header */}
            <View style={[styles.fullScreenHeader, { borderBottomColor: safeTheme.borderColor, ...(isMobile && { paddingHorizontal: 16, paddingVertical: 12 }) }]}>
                <View style={styles.headerContent}>
                    <View style={styles.headerLeft}>
                        {!isMobile && <Ionicons name="easel-outline" size={32} color={safeTheme.primary} />}
                        <View style={{ marginLeft: isMobile ? 0 : 16 }}>
                            <View style={{ flexDirection: 'row', gap: isMobile ? 12 : 20 }}>
                                <TouchableOpacity onPress={() => setActiveTab('my')}>
                                    <Text style={[
                                        styles.fullScreenTitle,
                                        { color: activeTab === 'my' ? safeTheme.text : safeTheme.text + '60', ...(isMobile && { fontSize: 18 }) }
                                    ]}>
                                        My Visual Reports
                                    </Text>
                                    {activeTab === 'my' && <View style={{ height: 3, backgroundColor: safeTheme.primary, marginTop: 4 }} />}
                                </TouchableOpacity>
                                {/* "Shared with Me" tab — HIDDEN for now (sharing is an
                                    advanced, not-fully-tested feature kept for future).
                                    activeTab stays 'my'. Flip `false` to re-enable. */}
                                {false && (
                                <TouchableOpacity onPress={() => setActiveTab('shared')}>
                                    <Text style={[
                                        styles.fullScreenTitle,
                                        { color: activeTab === 'shared' ? safeTheme.text : safeTheme.text + '60', ...(isMobile && { fontSize: 18 }) }
                                    ]}>
                                        Shared with Me
                                    </Text>
                                    {activeTab === 'shared' && <View style={{ height: 3, backgroundColor: safeTheme.primary, marginTop: 4 }} />}
                                </TouchableOpacity>
                                )}
                            </View>
                            {selectedVaultName && activeTab === 'my' && (
                                <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 4 }}>
                                    <Ionicons name="folder-open-outline" size={14} color={safeTheme.text + '80'} style={{ marginRight: 6 }} />
                                    <Text style={{ fontSize: 13, color: safeTheme.text + '80' }}>
                                        Vault: {selectedVaultName}
                                    </Text>
                                </View>
                            )}
                        </View>
                    </View>
                    <TouchableOpacity onPress={onClose} style={styles.fullScreenCloseBtn}>
                        <Ionicons name="close" size={28} color={safeTheme.text} />
                    </TouchableOpacity>
                </View>
            </View>

            {/* Content using FlatList for lazy loading */}
            {isLoading ? (
                <View style={styles.fullScreenCentered}>
                    <ActivityIndicator size="large" color={safeTheme.primary} />
                    <Text style={[styles.loadingText, { color: safeTheme.text }]}>Loading visual reports...</Text>
                </View>
            ) : error ? (
                <View style={styles.fullScreenCentered}>
                    <MaterialIcons name="error-outline" size={64} color="#f44336" />
                    <Text style={styles.errorText}>{error}</Text>
                    <TouchableOpacity onPress={fetchprintables} style={styles.retryBtn}>
                        <Text style={{ color: safeTheme.primary }}>Retry</Text>
                    </TouchableOpacity>
                </View>
            ) : (
                <View style={{ flex: 1, paddingHorizontal: isMobile ? 12 : 40 }}>
                    <FlatList
                        data={activeTab === 'my'
                            ? [{ id: 'create_new' }, ...printables]
                            : sharedprintables}
                        renderItem={({ item }) => {
                            if (item.id === 'create_new') {
                                return renderCreateNewCard();
                            }
                            return renderprintableCard(item);
                        }}
                        keyExtractor={(item) => item.id}
                        numColumns={gridColumns}
                        key={`grid-${gridColumns}`} // Force re-render when columns change
                        contentContainerStyle={{ paddingTop: isMobile ? 12 : 30, paddingBottom: isMobile ? 20 : 40 }}
                        columnWrapperStyle={gridColumns > 1 ? { gap: gridGap, marginBottom: isMobile ? 12 : 20 } : undefined}
                        showsVerticalScrollIndicator={true}
                        onEndReached={handleLoadMore}
                        onEndReachedThreshold={0.5}
                        ListFooterComponent={
                            isFetchingMore ? (
                                <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                                    <ActivityIndicator size="small" color={safeTheme.primary} />
                                </View>
                            ) : null
                        }
                        ListEmptyComponent={
                            <View style={[styles.emptyStateInline, { width: isMobile ? '100%' : Math.min(cardWidth * 2 + 20, screenDimensions.width - 80), maxWidth: '100%' }]}>
                                <Text style={[styles.emptyText, { color: safeTheme.text, textAlign: 'center' }]}>
                                    {activeTab === 'my' ? 'No saved visual reports yet' : 'No visual reports shared with you'}
                                </Text>
                                <Text style={[styles.emptySubtext, { textAlign: 'center' }]}>
                                    {activeTab === 'my' ? 'Click "Create New Visual Report" to get started' : 'Visual reports shared by others will appear here'}
                                </Text>
                            </View>
                        }
                    />
                </View>
            )}
        </View>
    );

    // On web, render as a fixed full-screen modal overlay
    if (Platform.OS === 'web') {
        if (!visible) return null;

        return (
            <View
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    backgroundColor: 'rgba(0,0,0,0.6)',
                    justifyContent: 'center',
                    alignItems: 'center',
                    zIndex: 50000,
                }}
                pointerEvents="auto"
            >
                {/* Full-screen modal container with slight margin */}
                <View style={{
                    width: isMobile ? '100%' : '95%',
                    height: isMobile ? '100%' : '95%',
                    maxWidth: isMobile ? '100%' : 1400,
                    backgroundColor: safeTheme.background,
                    borderRadius: isMobile ? 0 : 16,
                    overflow: 'hidden',
                    shadowColor: '#000',
                    shadowOffset: { width: 0, height: 8 },
                    shadowOpacity: 0.3,
                    shadowRadius: 24,
                }}>
                    {content}
                </View>

                {/* Custom Delete Confirmation Modal */}
                {deleteConfirmation.visible && (
                    <View
                        style={{
                            position: 'fixed',
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            backgroundColor: 'rgba(0,0,0,0.7)',
                            justifyContent: 'center',
                            alignItems: 'center',
                            zIndex: 60000,
                        }}
                        pointerEvents="auto"
                    >
                        <View style={{
                            width: '90%',
                            maxWidth: 400,
                            backgroundColor: '#2C2C2E',
                            borderRadius: 12,
                            padding: 24,
                            shadowColor: '#000',
                            shadowOffset: { width: 0, height: 8 },
                            shadowOpacity: 0.3,
                            shadowRadius: 16,
                        }}>
                            <Text style={{ fontSize: 16, fontWeight: '600', color: '#FFFFFF', marginBottom: 8 }}>
                                Delete printable?
                            </Text>
                            <Text style={{ fontSize: 14, color: '#D1D1D6', marginBottom: 24 }}>
                                Are you sure you want to delete "{deleteConfirmation.title}"? This action cannot be undone.
                            </Text>
                            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 12 }}>
                                <TouchableOpacity
                                    onPress={() => setDeleteConfirmation({ visible: false, title: '', onConfirm: () => { } })}
                                    style={{
                                        paddingVertical: 10,
                                        paddingHorizontal: 20,
                                        borderRadius: 8,
                                        backgroundColor: '#3A3A3C',
                                    }}
                                >
                                    <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    onPress={() => {
                                        deleteConfirmation.onConfirm();
                                    }}
                                    style={{
                                        paddingVertical: 10,
                                        paddingHorizontal: 20,
                                        borderRadius: 8,
                                        backgroundColor: '#007AFF',
                                    }}
                                >
                                    <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>Delete</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    </View>
                )}
            </View>
        );
    }

    // Mobile: Full-screen modal
    return (
        <Modal visible={visible} animationType="PAGE" transparent={true}>
            <View style={{
                flex: 1,
                backgroundColor: 'rgba(0,0,0,0.6)',
                justifyContent: 'center',
                alignItems: 'center',
            }}>
                <View style={{
                    width: '95%',
                    height: '95%',
                    backgroundColor: safeTheme.background,
                    borderRadius: 16,
                    overflow: 'hidden',
                }}>
                    {content}
                </View>

                {/* Custom Delete Confirmation Modal - Mobile */}
                {deleteConfirmation.visible && (
                    <Modal visible={deleteConfirmation.visible} transparent animationType="fade">
                        <View style={{
                            flex: 1,
                            backgroundColor: 'rgba(0,0,0,0.7)',
                            justifyContent: 'center',
                            alignItems: 'center',
                            padding: 20
                        }}>
                            <View style={{
                                width: '100%',
                                maxWidth: 400,
                                backgroundColor: '#2C2C2E',
                                borderRadius: 12,
                                padding: 24,
                                shadowColor: '#000',
                                shadowOffset: { width: 0, height: 8 },
                                shadowOpacity: 0.3,
                                shadowRadius: 16,
                                elevation: 10,
                            }}>
                                <Text style={{ fontSize: 16, fontWeight: '600', color: '#FFFFFF', marginBottom: 8 }}>
                                    Delete printable?
                                </Text>
                                <Text style={{ fontSize: 14, color: '#D1D1D6', marginBottom: 24 }}>
                                    Are you sure you want to delete "{deleteConfirmation.title}"? This action cannot be undone.
                                </Text>
                                <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 12 }}>
                                    <TouchableOpacity
                                        onPress={() => setDeleteConfirmation({ visible: false, title: '', onConfirm: () => { } })}
                                        style={{
                                            paddingVertical: 10,
                                            paddingHorizontal: 20,
                                            borderRadius: 8,
                                            backgroundColor: '#3A3A3C',
                                        }}
                                    >
                                        <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        onPress={() => {
                                            deleteConfirmation.onConfirm();
                                        }}
                                        style={{
                                            paddingVertical: 10,
                                            paddingHorizontal: 20,
                                            borderRadius: 8,
                                            backgroundColor: '#007AFF',
                                        }}
                                    >
                                        <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600' }}>Delete</Text>
                                    </TouchableOpacity>
                                </View>
                            </View>
                        </View>
                    </Modal>
                )}
            </View>
        </Modal>
    );
};

const styles = {
    // Legacy styles for mobile modal
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'center',
        alignItems: 'center'
    },
    container: {
        width: '90%',
        maxWidth: 550,
        maxHeight: '95%',
        borderRadius: 16,
        overflow: 'hidden',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.25,
        shadowRadius: 16,
        elevation: 8,
    },

    // Full-screen styles (new Canva-like design)
    fullScreenContainer: {
        flex: 1,
        width: '100%',
        height: '100%',
    },
    fullScreenHeader: {
        paddingHorizontal: 40,
        paddingVertical: 20,
        borderBottomWidth: 1,
    },
    headerContent: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    headerLeft: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    fullScreenTitle: {
        fontSize: 28,
        fontWeight: '700',
    },
    fullScreenCloseBtn: {
        padding: 8,
        borderRadius: 8,
    },
    fullScreenContent: {
        flex: 1,
    },
    gridContainer: {
        padding: 40,
        paddingTop: 30,
    },
    cardGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 20,
    },
    fullScreenCentered: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 100,
        minHeight: 400,
    },

    // printable Card styles
    printableCard: {
        borderRadius: 12,
        borderWidth: 1,
        overflow: 'hidden',
        marginBottom: 0,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.08,
        shadowRadius: 8,
        elevation: 3,
    },
    createNewCard: {
        borderWidth: 2,
        borderStyle: 'dashed',
    },
    cardThumbnail: {
        width: '100%',
        position: 'relative',
        overflow: 'hidden',
    },
    thumbnailImage: {
        width: '100%',
        height: '100%',
    },
    thumbnailPlaceholder: {
        width: '100%',
        height: '100%',
        alignItems: 'center',
        justifyContent: 'center',
    },
    createNewThumbnail: {
        alignItems: 'center',
        justifyContent: 'center',
    },
    createNewIcon: {
        width: 64,
        height: 64,
        borderRadius: 32,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cardDeleteBtn: {
        position: 'absolute',
        top: 8,
        right: 8,
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(244, 67, 54, 0.9)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    PAGECountBadge: {
        position: 'absolute',
        bottom: 8,
        left: 8,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4,
    },
    PAGECountText: {
        color: '#fff',
        fontSize: 11,
        fontWeight: '500',
    },
    cardInfo: {
        padding: 12,
    },
    cardTitle: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 4,
    },
    cardMeta: {
        fontSize: 11,
        color: '#888',
    },
    cardGoal: {
        fontSize: 11,
        color: '#666',
        marginTop: 4,
        fontStyle: 'italic',
    },
    workspaceBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#F3F4F6',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4,
        marginTop: 6,
        alignSelf: 'flex-start',
        gap: 4,
    },
    workspaceBadgeText: {
        fontSize: 10,
        color: '#6B7280',
        fontWeight: '500',
    },
    emptyStateInline: {
        padding: 40,
        paddingVertical: 60,
        alignItems: 'center',
        justifyContent: 'center',
    },

    // Common styles
    loadingText: {
        marginTop: 16,
        fontSize: 15
    },
    errorText: {
        color: '#f44336',
        marginTop: 12,
        fontSize: 15,
    },
    retryBtn: {
        marginTop: 16,
        padding: 10
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '500',
        marginTop: 20,
        textAlign: 'center',
    },
    emptySubtext: {
        color: '#999',
        marginTop: 8,
        fontSize: 14,
        textAlign: 'center',
        paddingHorizontal: 20,
    },
};

export default printableListModal;
