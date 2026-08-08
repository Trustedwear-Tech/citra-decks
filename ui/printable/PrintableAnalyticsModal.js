import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    Modal,
    TouchableOpacity,
    ScrollView,
    StyleSheet,
    ActivityIndicator,
    Switch,
    Platform,
    useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

/**
 * PrintableAnalyticsModal
 * 
 * Displays analytics for a shared printable including:
 * - Total views and unique viewers
 * - Average time spent and completion rate
 * - Page-by-page engagement heatmap
 * - Recent viewer activity
 */
const PrintableAnalyticsModal = ({
    visible,
    onClose,
    printableId,
    printableTitle,
    theme,
    apiBaseUrl,
    getAuthHeaders,
}) => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [analyticsEnabled, setAnalyticsEnabled] = useState(true);
    const [toggling, setToggling] = useState(false);
    const { width: windowWidth } = useWindowDimensions();
    const isMobile = windowWidth < 600;

    useEffect(() => {
        if (visible && printableId) {
            fetchAnalytics();
        }
    }, [visible, printableId]);

    const fetchAnalytics = async () => {
        setLoading(true);
        setError(null);

        try {
            const headers = getAuthHeaders ? await getAuthHeaders() : {};
            const response = await fetch(
                `${apiBaseUrl}/api/analytics/printable/${printableId}?days=30`,
                { headers }
            );

            if (!response.ok) {
                throw new Error('Failed to fetch analytics');
            }

            const data = await response.json();
            setAnalytics(data);
        } catch (err) {
            console.error('Analytics fetch error:', err);
            setError('Could not load analytics. Make sure it has been shared.');
        } finally {
            setLoading(false);
        }
    };

    const toggleAnalytics = async (enabled) => {
        setToggling(true);
        try {
            const headers = getAuthHeaders ? await getAuthHeaders() : {};
            const response = await fetch(
                `${apiBaseUrl}/api/analytics/printable/${printableId}/toggle?enabled=${enabled}`,
                { method: 'POST', headers }
            );

            if (response.ok) {
                setAnalyticsEnabled(enabled);
            }
        } catch (err) {
            console.error('Toggle analytics error:', err);
        } finally {
            setToggling(false);
        }
    };

    const formatDuration = (ms) => {
        if (!ms || ms === 0) return '0s';
        const seconds = Math.floor(ms / 1000);
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;

        if (minutes > 0) {
            return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
        return `${seconds}s`;
    };

    const formatTimeAgo = (dateStr) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now - date;
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffHours / 24);

        if (diffHours < 1) return 'Just now';
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        return date.toLocaleDateString();
    };

    const styles = createStyles(theme, windowWidth, isMobile);

    // Find max duration for heatmap scaling
    const maxDuration = analytics?.page_stats?.length > 0
        ? Math.max(...analytics.page_stats.map(s => s.avg_duration_ms))
        : 1;

    return (
        <Modal
            visible={visible}
            animationType="slide"
            transparent={true}
            onRequestClose={onClose}
        >
            <View style={styles.overlay}>
                <View style={styles.container}>
                    {/* Header */}
                    <View style={styles.header}>
                        <View style={styles.headerLeft}>
                            <Ionicons name="stats-chart" size={isMobile ? 20 : 24} color={theme.primary} />
                            <Text style={styles.headerTitle} numberOfLines={1}>Analytics</Text>
                        </View>
                        <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                            <Ionicons name="close" size={24} color={theme.text} />
                        </TouchableOpacity>
                    </View>

                    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
                        {loading ? (
                            <View style={styles.loadingContainer}>
                                <ActivityIndicator size="large" color={theme.primary} />
                                <Text style={styles.loadingText}>Loading analytics...</Text>
                            </View>
                        ) : error ? (
                            <View style={styles.errorContainer}>
                                <Ionicons name="warning-outline" size={48} color="#f59e0b" />
                                <Text style={styles.errorText}>{error}</Text>
                                <TouchableOpacity style={styles.retryButton} onPress={fetchAnalytics}>
                                    <Text style={styles.retryText}>Retry</Text>
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <>
                                {/* Analytics Toggle */}
                                <View style={styles.toggleRow}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.toggleLabel}>Enable Analytics Tracking</Text>
                                        <Text style={styles.toggleHint}>Track views when shared</Text>
                                    </View>
                                    <Switch
                                        value={analyticsEnabled}
                                        onValueChange={toggleAnalytics}
                                        disabled={toggling}
                                        trackColor={{ false: '#767577', true: theme.primary + '80' }}
                                        thumbColor={analyticsEnabled ? theme.primary : '#f4f3f4'}
                                    />
                                </View>

                                {/* Overview Stats */}
                                <View style={styles.statsGrid}>
                                    <View style={styles.statCard}>
                                        <Text style={styles.statValue}>{analytics?.total_views || 0}</Text>
                                        <Text style={styles.statLabel}>Total Views</Text>
                                    </View>
                                    <View style={styles.statCard}>
                                        <Text style={styles.statValue}>{analytics?.unique_viewers || 0}</Text>
                                        <Text style={styles.statLabel}>Unique Viewers</Text>
                                    </View>
                                    <View style={styles.statCard}>
                                        <Text style={styles.statValue}>
                                            {formatDuration(analytics?.avg_duration_ms || 0)}
                                        </Text>
                                        <Text style={styles.statLabel}>Avg. Time</Text>
                                    </View>
                                    <View style={styles.statCard}>
                                        <Text style={styles.statValue}>
                                            {Math.round(analytics?.completion_rate || 0)}%
                                        </Text>
                                        <Text style={styles.statLabel}>Completion</Text>
                                    </View>
                                </View>

                                {/* Page Engagement Heatmap */}
                                <View style={styles.section}>
                                    <Text style={styles.sectionTitle}>
                                        <Ionicons name="bar-chart-outline" size={isMobile ? 15 : 18} color={theme.text} /> Page Engagement
                                    </Text>

                                    {analytics?.page_stats?.map((page, index) => {
                                        const barWidth = maxDuration > 0
                                            ? (page.avg_duration_ms / maxDuration) * 100
                                            : 0;
                                        const isDropOff = page.drop_off_count > 0;

                                        return (
                                            <View key={index} style={styles.pageRow}>
                                                <Text style={styles.pageLabel}>Page {index + 1}</Text>
                                                <View style={styles.barContainer}>
                                                    <View
                                                        style={[
                                                            styles.bar,
                                                            {
                                                                width: `${Math.max(barWidth, 5)}%`,
                                                                backgroundColor: isDropOff ? '#f59e0b' : theme.primary
                                                            }
                                                        ]}
                                                    />
                                                </View>
                                                <Text style={styles.pageDuration}>
                                                    {formatDuration(page.avg_duration_ms)}
                                                </Text>
                                                {isDropOff && (
                                                    <View style={styles.dropOffBadge}>
                                                        <Text style={styles.dropOffText}>⚠️ {page.drop_off_count}</Text>
                                                    </View>
                                                )}
                                            </View>
                                        );
                                    })}

                                    {(!analytics?.page_stats || analytics.page_stats.length === 0) && (
                                        <Text style={styles.noDataText}>No page data available yet</Text>
                                    )}
                                </View>

                                {/* Recent Viewers */}
                                <View style={styles.section}>
                                    <Text style={styles.sectionTitle}>
                                        <Ionicons name="people-outline" size={isMobile ? 15 : 18} color={theme.text} /> Recent Viewers
                                    </Text>

                                    {analytics?.recent_viewers?.map((viewer, index) => (
                                        <View key={index} style={styles.viewerRow}>
                                            <View style={styles.viewerIcon}>
                                                <Ionicons
                                                    name={viewer.device_type === 'mobile' ? 'phone-portrait' : 'desktop'}
                                                    size={isMobile ? 16 : 20}
                                                    color={theme.primary}
                                                />
                                            </View>
                                            <View style={styles.viewerInfo}>
                                                <Text style={styles.viewerDevice} numberOfLines={1}>
                                                    {viewer.device_type === 'mobile' ? 'Mobile' : 'Desktop'}
                                                    {viewer.location && ` • ${viewer.location}`}
                                                </Text>
                                                <Text style={styles.viewerMeta} numberOfLines={1}>
                                                    {formatTimeAgo(viewer.viewed_at)} • {formatDuration(viewer.duration_ms)} • {viewer.pages_viewed || viewer.slides_viewed} pages
                                                </Text>
                                            </View>
                                        </View>
                                    ))}

                                    {(!analytics?.recent_viewers || analytics.recent_viewers.length === 0) && (
                                        <Text style={styles.noDataText}>No viewers yet. Share to start tracking.</Text>
                                    )}
                                </View>
                            </>
                        )}
                    </ScrollView>
                </View>
            </View>
        </Modal>
    );
};

const createStyles = (theme, windowWidth, isMobile) => StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: isMobile ? 'flex-end' : 'center',
        alignItems: 'center',
    },
    container: {
        width: isMobile ? '100%' : Math.min(windowWidth - 40, 600),
        maxHeight: isMobile ? '92%' : '85%',
        backgroundColor: theme.surface,
        borderTopLeftRadius: 16,
        borderTopRightRadius: 16,
        borderBottomLeftRadius: isMobile ? 0 : 16,
        borderBottomRightRadius: isMobile ? 0 : 16,
        overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' } : {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: -4 },
            shadowOpacity: 0.25,
            shadowRadius: 16,
            elevation: 10,
        }),
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: isMobile ? 16 : 20,
        paddingVertical: isMobile ? 14 : 16,
        borderBottomWidth: 1,
        borderBottomColor: theme.border,
    },
    headerLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: isMobile ? 8 : 10,
        flex: 1,
    },
    headerTitle: {
        fontSize: isMobile ? 16 : 18,
        fontWeight: '600',
        color: theme.text,
        flex: 1,
    },
    closeButton: {
        padding: 8,
    },
    content: {
        flex: 1,
        padding: isMobile ? 14 : 20,
    },
    loadingContainer: {
        alignItems: 'center',
        paddingVertical: 60,
    },
    loadingText: {
        marginTop: 16,
        color: theme.secondaryText,
    },
    errorContainer: {
        alignItems: 'center',
        paddingVertical: 40,
    },
    errorText: {
        marginTop: 12,
        color: theme.secondaryText,
        textAlign: 'center',
    },
    retryButton: {
        marginTop: 16,
        paddingHorizontal: 20,
        paddingVertical: 10,
        backgroundColor: theme.primary,
        borderRadius: 8,
    },
    retryText: {
        color: '#fff',
        fontWeight: '600',
    },
    toggleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: theme.background,
        padding: isMobile ? 12 : 16,
        borderRadius: 12,
        marginBottom: isMobile ? 16 : 20,
    },
    toggleLabel: {
        fontSize: isMobile ? 13 : 14,
        fontWeight: '600',
        color: theme.text,
    },
    toggleHint: {
        fontSize: isMobile ? 11 : 12,
        color: theme.secondaryText,
        marginTop: 2,
    },
    statsGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: isMobile ? 8 : 12,
        marginBottom: isMobile ? 16 : 24,
    },
    statCard: {
        flexBasis: isMobile ? '47%' : undefined,
        flex: isMobile ? undefined : 1,
        minWidth: isMobile ? undefined : 100,
        backgroundColor: theme.background,
        padding: isMobile ? 12 : 16,
        borderRadius: 12,
        alignItems: 'center',
    },
    statValue: {
        fontSize: isMobile ? 22 : 28,
        fontWeight: '700',
        color: theme.primary,
    },
    statLabel: {
        fontSize: isMobile ? 11 : 12,
        color: theme.secondaryText,
        marginTop: 4,
    },
    section: {
        marginBottom: isMobile ? 16 : 24,
    },
    sectionTitle: {
        fontSize: isMobile ? 14 : 16,
        fontWeight: '600',
        color: theme.text,
        marginBottom: isMobile ? 12 : 16,
    },
    pageRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: isMobile ? 8 : 10,
        gap: isMobile ? 6 : 8,
    },
    pageLabel: {
        width: isMobile ? 48 : 60,
        fontSize: isMobile ? 11 : 13,
        color: theme.secondaryText,
    },
    barContainer: {
        flex: 1,
        height: isMobile ? 16 : 20,
        backgroundColor: theme.background,
        borderRadius: 4,
        overflow: 'hidden',
    },
    bar: {
        height: '100%',
        borderRadius: 4,
    },
    pageDuration: {
        width: isMobile ? 40 : 50,
        fontSize: isMobile ? 11 : 12,
        color: theme.text,
        textAlign: 'right',
    },
    dropOffBadge: {
        paddingHorizontal: 6,
        paddingVertical: 2,
        backgroundColor: '#fef3c7',
        borderRadius: 4,
    },
    dropOffText: {
        fontSize: isMobile ? 10 : 11,
        color: '#92400e',
    },
    viewerRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: isMobile ? 10 : 12,
        borderBottomWidth: 1,
        borderBottomColor: theme.border,
    },
    viewerIcon: {
        width: isMobile ? 32 : 40,
        height: isMobile ? 32 : 40,
        borderRadius: isMobile ? 16 : 20,
        backgroundColor: theme.primary + '15',
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: isMobile ? 10 : 12,
    },
    viewerInfo: {
        flex: 1,
    },
    viewerDevice: {
        fontSize: isMobile ? 13 : 14,
        fontWeight: '500',
        color: theme.text,
    },
    viewerMeta: {
        fontSize: isMobile ? 11 : 12,
        color: theme.secondaryText,
        marginTop: 2,
    },
    noDataText: {
        color: theme.secondaryText,
        fontStyle: 'italic',
        textAlign: 'center',
        paddingVertical: 20,
    },
});

export default PrintableAnalyticsModal;
