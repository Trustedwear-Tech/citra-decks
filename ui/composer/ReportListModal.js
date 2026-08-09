// ReportListModal.js - Full-screen modal to browse, load, and manage saved reports
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

const ReportListModal = ({
    visible,
    onClose,
    onLoadReport,
    onCreateNew,
    apiConfig,
    userDeviceId,
    theme,
    selectedVaultName
}) => {
    const [reports, setReports] = useState([]);
    const [sharedReports, setSharedReports] = useState([]);
    const [activeTab, setActiveTab] = useState('my'); // 'my' | 'shared'
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [deleteConfirmation, setDeleteConfirmation] = useState({ visible: false, title: '', onConfirm: () => { } });
    const [screenDimensions, setScreenDimensions] = useState({ width: SCREEN_WIDTH, height: SCREEN_HEIGHT });
    const isMobile = screenDimensions.width < 768;

    // Teams removed — every artifact lives in the personal workspace.
    const activeTeamId = null;

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

    // Fetch reports from server
    const fetchReports = useCallback(async () => {
        if (!userDeviceId) return;

        try {
            setIsLoading(true);
            setError(null);

            const token = await AsyncStorage.getItem('@auth_token');
            
            // Fetch ALL user reports (user-level, not workspace-specific)
            let url = `${apiConfig.API_URL}/composer/reports?all_workspaces=true`;
            // Remove team_id filter to get all user reports across all workspaces

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
                // Filter out shared items - only show owned reports in "My" tab
                const myReports = (data.reports || []).filter(r => !r.is_shared);
                setReports(myReports);
            } else {
                throw new Error('Failed to fetch reports');
            }
        } catch (err) {
            console.error('Failed to fetch reports:', err);
            setError('Failed to load reports');
        } finally {
            setIsLoading(false);
        }
    }, [apiConfig.API_URL, userDeviceId, activeTeamId]);

    // Fetch shared reports
    const fetchSharedReports = useCallback(async () => {
        try {
            setIsLoading(true);
            setError(null);
            console.log('Fetching ALL shared reports (user-level, all workspaces) for', userDeviceId);

            const token = await AsyncStorage.getItem('@auth_token');
            const response = await fetch(
                `${apiConfig.API_URL}/api/sharing/my-shared/report`,
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
                setSharedReports(mapped);
            } else {
                console.warn('Failed to fetch shared items status:', response.status);
                setSharedReports([]);
            }
        } catch (err) {
            console.error('Failed to fetch shared reports:', err);
        } finally {
            setIsLoading(false);
        }
    }, [apiConfig.API_URL, userDeviceId]);

    useEffect(() => {
        if (visible) {
            if (activeTab === 'my') {
                fetchReports();
            } else {
                fetchSharedReports();
            }
        }
    }, [visible, activeTab, fetchReports, fetchSharedReports]);

    const handleLoadReport = async (reportId) => {
        console.log('[REPORT_LIST_MODAL] Loading report ID:', reportId);
        try {
            setIsLoading(true);
            const token = await AsyncStorage.getItem('@auth_token');

            const response = await fetch(
                `${apiConfig.API_URL}/composer/reports/${reportId}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                console.log('[REPORT_LIST_MODAL] Fetched report data:', data);
                onLoadReport(data.report);
                onClose();
            } else {
                throw new Error('Failed to load report');
            }
        } catch (err) {
            console.error('Failed to load report:', err);
            Alert.alert('Error', 'Failed to load.');
        } finally {
            setIsLoading(false);
        }
    };

    // Shared delete logic
    const executeDelete = async (reportId) => {
        try {
            const token = await AsyncStorage.getItem('@auth_token');
            const response = await fetch(
                `${apiConfig.API_URL}/composer/reports/${reportId}`,
                {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                }
            );

            if (response.ok) {
                setReports(prev => prev.filter(r => r.id !== reportId));
                console.log('Report deleted successfully');
            } else {
                throw new Error('Failed to delete');
            }
        } catch (err) {
            console.error('Delete error:', err);
            if (Platform.OS === 'web') {
                window.alert('Failed to delete: ' + err.message);
            } else {
                Alert.alert('Error', 'Failed to delete.');
            }
        } finally {
            setDeleteConfirmation({ visible: false, title: '', onConfirm: () => { } });
        }
    };

    const handleDeleteReport = async (reportId, title) => {
        setDeleteConfirmation({
            visible: true,
            title: title,
            onConfirm: () => executeDelete(reportId)
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
    const gridColumns = getGridColumns(screenDimensions.width);
    const gridPadding = isMobile ? 24 : 80;
    const gridGap = isMobile ? 12 : 20;
    const cardWidth = Math.floor((screenDimensions.width * (isMobile ? 1 : 0.95) - gridPadding - (gridColumns - 1) * gridGap) / gridColumns);
    const thumbnailHeight = Math.floor(cardWidth * 9 / 16); // 16:9 aspect ratio

    // Render report card with thumbnail
    const renderReportCard = (report) => {
        const hasThumbnail = report.thumbnail && typeof report.thumbnail === 'string';

        return (
            <TouchableOpacity
                key={report.id}
                style={[
                    styles.reportCard,
                    {
                        width: cardWidth,
                        backgroundColor: safeTheme.surface,
                        borderColor: safeTheme.borderColor,
                    }
                ]}
                onPress={() => handleLoadReport(report.id)}
                activeOpacity={0.8}
            >
                {/* Thumbnail Area */}
                <View style={[styles.cardThumbnail, { height: thumbnailHeight }]}>
                    {hasThumbnail ? (
                        <LazyThumbnail
                            uri={report.thumbnail}
                            style={styles.thumbnailImage}
                            resizeMode="cover"
                            placeholder={
                                <View style={[styles.thumbnailPlaceholder, { backgroundColor: safeTheme.primary + '08' }]}>
                                    <ActivityIndicator size="small" color={safeTheme.primary} />
                                </View>
                            }
                        />
                    ) : (
                        <View style={[styles.thumbnailPlaceholder, { backgroundColor: safeTheme.primary + '15' }]}>
                            <MaterialIcons name="description" size={48} color={safeTheme.primary} />
                        </View>
                    )}

                    {/* Delete button overlay - hidden for shared reports */}
                    {!report.isShared && (
                    <TouchableOpacity
                        style={styles.cardDeleteBtn}
                        onPress={(e) => {
                            e.stopPropagation();
                            handleDeleteReport(report.id, report.title);
                        }}
                    >
                        <MaterialIcons name="delete" size={18} color="#fff" />
                    </TouchableOpacity>
                    )}

                    {/* Page count badge */}
                    {report.page_count !== undefined && (
                        <View style={styles.pageCountBadge}>
                            <Text style={styles.pageCountText}>{report.page_count} pages</Text>
                        </View>
                    )}
                </View>

                {/* Card Info */}
                <View style={styles.cardInfo}>
                    <Text style={[styles.cardTitle, { color: safeTheme.text }]} numberOfLines={2}>
                        {report.title || 'Untitled Report'}
                    </Text>
                    <Text style={styles.cardMeta}>
                        {formatDate(report.updated_at || report.created_at)}
                    </Text>
                    {report.goal && (
                        <Text style={styles.cardGoal} numberOfLines={1}>
                            {report.goal}
                        </Text>
                    )}
                    {report.workspace_name && report.isShared && (
                        <View style={styles.workspaceBadge}>
                            <Ionicons name="briefcase-outline" size={11} color="#6B7280" />
                            <Text style={styles.workspaceBadgeText}>{report.workspace_name}</Text>
                        </View>
                    )}
                </View>
            </TouchableOpacity>
        );
    };

    // Create New Report Card
    const renderCreateNewCard = () => (
        <TouchableOpacity
            style={[
                styles.reportCard,
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
                    Create New Document
                </Text>
                <Text style={styles.cardMeta}>
                    Start from scratch
                </Text>
            </View>
        </TouchableOpacity>
    );

    // Key generator to force re-render when columns change
    const [listKey, setListKey] = useState('grid-1');

    useEffect(() => {
        setListKey(`grid-${gridColumns}`);
    }, [gridColumns]);

    // FlatList Render Item
    const renderItem = ({ item }) => {
        if (item.isCreateNew) {
            return renderCreateNewCard();
        }
        return renderReportCard(item);
    };

    // Prepare data with Create New as first item
    const listData = [
        { id: 'create_new', isCreateNew: true },
        ...reports
    ];

    const content = (
        <View style={[styles.fullScreenContainer, { backgroundColor: safeTheme.background }]}>
            {/* Header */}
            <View style={[styles.fullScreenHeader, { borderBottomColor: safeTheme.borderColor, ...(isMobile && { paddingHorizontal: 16, paddingVertical: 12 }) }]}>
                <View style={styles.headerContent}>
                    <View style={styles.headerLeft}>
                        {!isMobile && <MaterialIcons name="description" size={32} color={safeTheme.primary} />}
                        <View style={{ marginLeft: isMobile ? 0 : 16 }}>
                            <View style={{ flexDirection: 'row', gap: isMobile ? 12 : 20 }}>
                                <TouchableOpacity onPress={() => setActiveTab('my')}>
                                    <Text style={[
                                        styles.fullScreenTitle,
                                        { color: activeTab === 'my' ? safeTheme.text : safeTheme.text + '60', ...(isMobile && { fontSize: 18 }) }
                                    ]}>
                                        My Documents
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
                            {selectedVaultName && (
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

            {/* Content with FlatList */}
            {isLoading ? (
                <View style={styles.fullScreenCentered}>
                    <ActivityIndicator size="large" color={safeTheme.primary} />
                    <Text style={[styles.loadingText, { color: safeTheme.text }]}>Loading documents...</Text>
                </View>
            ) : error ? (
                <View style={styles.fullScreenCentered}>
                    <MaterialIcons name="error-outline" size={64} color="#f44336" />
                    <Text style={styles.errorText}>{error}</Text>
                    <TouchableOpacity onPress={fetchReports} style={styles.retryBtn}>
                        <Text style={{ color: safeTheme.primary }}>Retry</Text>
                    </TouchableOpacity>
                </View>
            ) : ((activeTab === 'my' && reports.length === 0) || (activeTab === 'shared' && sharedReports.length === 0)) ? (
                // Only show empty state if NO reports
                <View style={{ justifyContent: 'center', alignItems: 'center', flex: 1 }}>
                    {activeTab === 'my' && renderCreateNewCard()}
                    <View style={[styles.emptyStateInline, { width: isMobile ? '100%' : Math.min(cardWidth * 2 + 20, screenDimensions.width - 80), maxWidth: '100%', paddingHorizontal: isMobile ? 16 : 40 }]}>
                        <Text style={[styles.emptyText, { color: safeTheme.text, textAlign: 'center' }]}>
                            {activeTab === 'my' ? 'No saved documents yet' : 'No documents shared with you'}
                        </Text>
                        <Text style={[styles.emptySubtext, { textAlign: 'center' }]}>
                            {activeTab === 'my' ? 'Click "Create New Document" to get started' : 'Documents shared by others will appear here'}
                        </Text>
                    </View>
                </View>
            ) : (
                <FlatList
                    key={listKey} // Force re-mount on column change
                    data={activeTab === 'my'
                        ? [{ id: 'create_new', isCreateNew: true }, ...reports]
                        : sharedReports}
                    renderItem={renderItem}
                    keyExtractor={(item) => item.id}
                    numColumns={gridColumns}
                    contentContainerStyle={isMobile ? { padding: 12, paddingTop: 12 } : styles.gridContainer}
                    columnWrapperStyle={gridColumns > 1 ? { gap: gridGap } : undefined}
                    showsVerticalScrollIndicator={true}
                    // Virtualization Props
                    initialNumToRender={10}
                    maxToRenderPerBatch={10}
                    windowSize={5}
                    removeClippedSubviews={Platform.OS !== 'web'} // Improve performance on native
                />
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
                                Delete Report?
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
        <Modal visible={visible} animationType="slide" transparent={true}>
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
                                    Delete Report?
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
    // Full-screen styles
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

    // Report Card styles
    reportCard: {
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
    pageCountBadge: {
        position: 'absolute',
        bottom: 8,
        left: 8,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4,
    },
    pageCountText: {
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

export default ReportListModal;
