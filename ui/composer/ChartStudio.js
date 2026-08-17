// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * ChartStudio - Interactive chart generation screen with AI chat and Chart.js preview
 * Used by both PresentationComposer and ReportComposer
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    TextInput,
    ScrollView,
    ActivityIndicator,
    Platform,
    Modal,
    useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderChartToImage } from '../../utils/chartRenderer';
import { CHART_PALETTES, CHART_TYPES, CHART_CATEGORIES, applyPaletteToConfig, changeChartType } from '../../utils/chartPalettes';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import authService from '../../services/authService';

const ChartStudio = ({
    visible,
    onClose,
    onInsertChart,
    sourceContext = 'presentation', // 'presentation' or 'report'
    pageContext = null, // NEW: Current slide/page content for AI context
    userDeviceId,
    selectedFolders = [],
    apiConfig,
    theme,
}) => {
    const { useUploadedData } = useWorkspace();
    const { width: screenWidth } = useWindowDimensions();
    const isMobile = screenWidth < 768;
    // Chat state
    const [chatInput, setChatInput] = useState('');
    const [chatHistory, setChatHistory] = useState([]);
    const [isGenerating, setIsGenerating] = useState(false);

    // Chart state
    const [chartConfig, setChartConfig] = useState(null);
    const [selectedChartType, setSelectedChartType] = useState('bar');
    const [selectedPalette, setSelectedPalette] = useState('corporate');
    const [chartError, setChartError] = useState(null);

    // Refs
    const canvasRef = useRef(null);
    const chartInstanceRef = useRef(null);
    const chatScrollRef = useRef(null);

    const safeTheme = theme || {
        background: '#ffffff',
        surface: '#f5f5f5',
        text: '#333333',
        textSecondary: '#666666',
        primary: '#2196F3',
        border: '#e0e0e0',
    };

    // Render chart when config, type, or palette changes
    useEffect(() => {
        if (!chartConfig || Platform.OS !== 'web') return;

        const renderChart = async () => {
            try {
                // Apply current type and palette
                let config = changeChartType(chartConfig, selectedChartType);
                config = applyPaletteToConfig(config, selectedPalette);

                // Get or create canvas
                const canvas = canvasRef.current;
                if (!canvas) return;

                // Destroy existing chart
                if (chartInstanceRef.current) {
                    chartInstanceRef.current.destroy();
                }

                // Dynamically import Chart.js
                const { Chart, registerables } = await import('chart.js');
                Chart.register(...registerables);

                // Create new chart
                chartInstanceRef.current = new Chart(canvas, {
                    ...config,
                    options: {
                        ...config.options,
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            ...config.options?.plugins,
                            legend: {
                                display: true,
                                position: 'bottom',
                            },
                        },
                    },
                });

                setChartError(null);
            } catch (err) {
                console.error('Chart render error:', err);
                setChartError('Failed to render chart');
            }
        };

        renderChart();

        return () => {
            if (chartInstanceRef.current) {
                chartInstanceRef.current.destroy();
                chartInstanceRef.current = null;
            }
        };
    }, [chartConfig, selectedChartType, selectedPalette]);

    // Generate chart from AI prompt
    const handleGenerateChart = useCallback(async () => {
        if (!chatInput.trim() || isGenerating) return;

        const userMessage = chatInput.trim();
        setChatInput('');
        setChatHistory(prev => [...prev, { role: 'user', content: userMessage }]);
        setIsGenerating(true);
        setChartError(null);

        try {
            const baseUrl = apiConfig?.API_URL || 'http://localhost:8085';
            const response = await authService.authenticatedFetch(`${baseUrl}/presentation/generate-chart-data`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    chart_type: selectedChartType,
                    query: userMessage,
                    user_id: userDeviceId,
                    // Only use vault if folders are explicitly selected (no default to 'general')
                    folder_ids: useUploadedData && selectedFolders.length > 0
                        ? selectedFolders.map(f => f.id || f)
                        : [],
                    page_context: pageContext, // NEW: Pass slide/page context
                    source_context: sourceContext, // NEW: Pass source type
                }),
            });

            const data = await response.json();

            if (data.success && data.chart_config) {
                setChartConfig(data.chart_config);
                setChatHistory(prev => [...prev, {
                    role: 'assistant',
                    content: `Chart generated! ${data.title || 'Here\'s your visualization.'}`
                }]);
            } else {
                setChatHistory(prev => [...prev, {
                    role: 'error',
                    content: data.message || 'Failed to generate chart. Try rephrasing your request.'
                }]);
            }
        } catch (err) {
            console.error('Chart generation error:', err);
            setChatHistory(prev => [...prev, {
                role: 'error',
                content: 'Network error. Please try again.'
            }]);
        } finally {
            setIsGenerating(false);
        }
    }, [chatInput, isGenerating, selectedChartType, userDeviceId, selectedFolders, apiConfig, useUploadedData]);

    // Insert chart - now passes chartConfig for interactive charts
    const handleInsertChart = useCallback(async () => {
        if (!chartConfig) return;

        try {
            setIsGenerating(true);

            // Apply current settings (type and palette)
            let config = changeChartType(chartConfig, selectedChartType);
            config = applyPaletteToConfig(config, selectedPalette);

            // Pass chartConfig to parent for interactive chart insertion
            // The parent (PresentationComposer) will call canvas.addChart(config)
            // which now uses fabric.Chart for interactive charts
            onInsertChart(config, config.options?.plugins?.title?.text || 'Chart');
            onClose();
        } catch (err) {
            console.error('Insert chart error:', err);
            setChartError('Failed to prepare chart configuration.');
        } finally {
            setIsGenerating(false);
        }
    }, [chartConfig, selectedChartType, selectedPalette, onInsertChart, onClose]);

    // Reset state when modal closes
    useEffect(() => {
        if (!visible) {
            setChatHistory([]);
            setChartConfig(null);
            setChartError(null);
            setChatInput('');
        }
    }, [visible]);

    if (!visible) return null;

    const content = (
        <View style={[styles.container, { backgroundColor: safeTheme.background }, isMobile && { width: '100%', height: '100%', maxWidth: undefined, maxHeight: undefined, borderRadius: 0 }]}>
            {/* Header */}
            <View style={[styles.header, { borderBottomColor: safeTheme.border }, isMobile && { padding: 10 }]}>
                <View style={styles.headerLeft}>
                    <Ionicons name="bar-chart" size={isMobile ? 20 : 24} color={safeTheme.primary} />
                    <Text style={[styles.headerTitle, { color: safeTheme.text }, isMobile && { fontSize: 16 }]}>Chart Studio</Text>
                </View>
                <View style={styles.headerRight}>
                    <TouchableOpacity
                        style={[
                            styles.headerInsertBtn,
                            {
                                backgroundColor: chartConfig ? safeTheme.primary : safeTheme.border,
                                opacity: chartConfig ? 1 : 0.6,
                            }
                        ]}
                        onPress={handleInsertChart}
                        disabled={!chartConfig || isGenerating}
                    >
                        <Ionicons name="add-circle" size={18} color="#fff" />
                        <Text style={styles.headerInsertBtnText}>
                            Insert Chart
                        </Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                        <Ionicons name="close" size={24} color={safeTheme.text} />
                    </TouchableOpacity>
                </View>
            </View>

            {/* Main content */}
            <View style={[styles.mainContent, isMobile && { flexDirection: 'column' }]}>
                {/* Left: AI Chat Panel */}
                <View style={[styles.chatPanel, { borderRightColor: safeTheme.border }, isMobile && { width: '100%', borderRightWidth: 0, borderBottomWidth: 1, borderBottomColor: safeTheme.border, maxHeight: 250, padding: 10 }]}>
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>AI Chat</Text>

                    <ScrollView
                        ref={chatScrollRef}
                        style={styles.chatHistory}
                        contentContainerStyle={styles.chatHistoryContent}
                        onContentSizeChange={() => chatScrollRef.current?.scrollToEnd()}
                    >
                        {chatHistory.length === 0 && (
                            <View style={styles.chatPlaceholder}>
                                <Ionicons name="chatbubble-ellipses-outline" size={32} color={safeTheme.textSecondary} />
                                <Text style={[styles.chatPlaceholderText, { color: safeTheme.textSecondary }]}>
                                    Describe the chart you want to create
                                </Text>
                                <Text style={[styles.chatHint, { color: safeTheme.textSecondary }]}>
                                    Example: "Show quarterly sales breakdown" or "Compare expenses by category"
                                </Text>
                            </View>
                        )}
                        {chatHistory.map((msg, idx) => (
                            <View
                                key={idx}
                                style={[
                                    styles.chatMessage,
                                    msg.role === 'user' && styles.chatMessageUser,
                                    msg.role === 'error' && styles.chatMessageError,
                                    { backgroundColor: msg.role === 'user' ? safeTheme.primary + '20' : safeTheme.surface }
                                ]}
                            >
                                <Text style={[
                                    styles.chatMessageText,
                                    { color: msg.role === 'error' ? '#EF4444' : safeTheme.text }
                                ]}>
                                    {msg.content}
                                </Text>
                            </View>
                        ))}
                        {isGenerating && (
                            <View style={[styles.chatMessage, { backgroundColor: safeTheme.surface }]}>
                                <ActivityIndicator size="small" color={safeTheme.primary} />
                                <Text style={[styles.chatMessageText, { color: safeTheme.textSecondary, marginLeft: 8 }]}>
                                    Generating chart...
                                </Text>
                            </View>
                        )}
                    </ScrollView>

                    <View style={[styles.chatInputContainer, { borderTopColor: safeTheme.border }]}>
                        <TextInput
                            style={[styles.chatInput, {
                                backgroundColor: safeTheme.surface,
                                color: safeTheme.text,
                                borderColor: safeTheme.border,
                            }, isMobile && { minHeight: 60, maxHeight: 100 }]}
                            placeholder="Describe your chart or paste data..."
                            placeholderTextColor={safeTheme.textSecondary}
                            value={chatInput}
                            onChangeText={setChatInput}
                            multiline={true}
                            maxLength={20000}
                            textAlignVertical="top"
                            scrollEnabled={true}
                        />
                        <TouchableOpacity
                            style={[styles.sendBtn, { backgroundColor: safeTheme.primary }]}
                            onPress={handleGenerateChart}
                            disabled={isGenerating || !chatInput.trim()}
                        >
                            <Ionicons name="send" size={18} color="#fff" />
                        </TouchableOpacity>
                    </View>
                </View>

                {/* Center: Chart Preview */}
                <View style={[styles.chartPanel, isMobile && { padding: 10, minHeight: 200 }]}>
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Preview</Text>

                    <View style={[styles.chartContainer, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                        {!chartConfig ? (
                            <View style={styles.chartPlaceholder}>
                                <Ionicons name="analytics-outline" size={64} color={safeTheme.textSecondary} />
                                <Text style={[styles.chartPlaceholderText, { color: safeTheme.textSecondary }]}>
                                    Your chart will appear here
                                </Text>
                            </View>
                        ) : Platform.OS === 'web' ? (
                            <canvas ref={canvasRef} style={{ maxWidth: '100%', maxHeight: '100%' }} />
                        ) : (
                            <Text style={{ color: safeTheme.textSecondary }}>Chart preview is web-only</Text>
                        )}
                        {chartError && (
                            <Text style={styles.chartError}>{chartError}</Text>
                        )}
                    </View>
                </View>

                {/* Right: Options Panel */}
                <ScrollView style={[styles.optionsPanel, { borderLeftColor: safeTheme.border }, isMobile && { width: '100%', borderLeftWidth: 0, borderTopWidth: 1, borderTopColor: safeTheme.border, padding: 10, maxHeight: 280, flex: undefined }]}>
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Options</Text>

                    {/* Chart Type — categorized */}
                    <Text style={[styles.optionLabel, { color: safeTheme.textSecondary }]}>Chart Type</Text>
                    {CHART_CATEGORIES.map(category => (
                        <View key={category} style={{ marginBottom: 8 }}>
                            <Text style={{ fontSize: 10, fontWeight: '600', color: safeTheme.textSecondary, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                {category}
                            </Text>
                            <ScrollView horizontal={isMobile} showsHorizontalScrollIndicator={false}>
                                <View style={[styles.chartTypeGrid, isMobile && { flexWrap: 'nowrap' }]}>
                                    {CHART_TYPES.filter(t => t.category === category).map(type => (
                                        <TouchableOpacity
                                            key={type.id}
                                            style={[
                                                styles.chartTypeBtn,
                                                {
                                                    backgroundColor: selectedChartType === type.id ? safeTheme.primary + '20' : safeTheme.surface,
                                                    borderColor: selectedChartType === type.id ? safeTheme.primary : safeTheme.border,
                                                },
                                                isMobile && { width: 70, padding: 6 }
                                            ]}
                                            onPress={() => setSelectedChartType(type.id)}
                                        >
                                            <Ionicons
                                                name={type.icon}
                                                size={18}
                                                color={selectedChartType === type.id ? safeTheme.primary : safeTheme.textSecondary}
                                            />
                                            <Text style={[
                                                styles.chartTypeName,
                                                { color: selectedChartType === type.id ? safeTheme.primary : safeTheme.text }
                                            ]} numberOfLines={1}>
                                                {type.name}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            </ScrollView>
                        </View>
                    ))}

                    {/* Color Palette */}
                    <Text style={[styles.optionLabel, { color: safeTheme.textSecondary, marginTop: isMobile ? 8 : 12 }]}>Color Palette</Text>
                    <ScrollView horizontal={isMobile} showsHorizontalScrollIndicator={false} style={!isMobile ? styles.paletteList : { marginBottom: 8 }} showsVerticalScrollIndicator={false}>
                        {isMobile ? (
                            <View style={{ flexDirection: 'row', gap: 8 }}>
                                {Object.entries(CHART_PALETTES).map(([key, palette]) => (
                                    <TouchableOpacity
                                        key={key}
                                        style={[
                                            styles.paletteBtn,
                                            {
                                                backgroundColor: selectedPalette === key ? safeTheme.primary + '10' : 'transparent',
                                                borderColor: selectedPalette === key ? safeTheme.primary : safeTheme.border,
                                                marginBottom: 0,
                                            }
                                        ]}
                                        onPress={() => setSelectedPalette(key)}
                                    >
                                        <View style={styles.paletteColors}>
                                            {palette.colors.slice(0, 5).map((color, idx) => (
                                                <View key={idx} style={[styles.paletteColor, { backgroundColor: color }]} />
                                            ))}
                                        </View>
                                        <Text style={[styles.paletteName, { color: safeTheme.text }]}>{palette.name}</Text>
                                        {selectedPalette === key && (
                                            <Ionicons name="checkmark-circle" size={18} color={safeTheme.primary} />
                                        )}
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : (
                            Object.entries(CHART_PALETTES).map(([key, palette]) => (
                                <TouchableOpacity
                                    key={key}
                                    style={[
                                        styles.paletteBtn,
                                        {
                                            backgroundColor: selectedPalette === key ? safeTheme.primary + '10' : 'transparent',
                                            borderColor: selectedPalette === key ? safeTheme.primary : safeTheme.border,
                                        }
                                    ]}
                                    onPress={() => setSelectedPalette(key)}
                                >
                                    <View style={styles.paletteColors}>
                                        {palette.colors.slice(0, 5).map((color, idx) => (
                                            <View key={idx} style={[styles.paletteColor, { backgroundColor: color }]} />
                                        ))}
                                    </View>
                                    <Text style={[styles.paletteName, { color: safeTheme.text }]}>{palette.name}</Text>
                                    {selectedPalette === key && (
                                        <Ionicons name="checkmark-circle" size={18} color={safeTheme.primary} />
                                    )}
                                </TouchableOpacity>
                            ))
                        )}
                    </ScrollView>


                </ScrollView>
            </View>
        </View>
    );

    // On web, render as fixed overlay
    if (Platform.OS === 'web') {
        return (
            <View style={styles.overlay}>
                {content}
            </View>
        );
    }

    // On native, use Modal
    return (
        <Modal visible={visible} animationType="slide" transparent>
            <View style={styles.overlay}>
                {content}
            </View>
        </Modal>
    );
};

const styles = {
    overlay: {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 100000,
    },
    container: {
        width: '95%',
        maxWidth: 1200,
        height: '90%',
        maxHeight: 700,
        borderRadius: 16,
        overflow: 'hidden',
        flexDirection: 'column',
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
    },
    headerLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    headerTitle: {
        fontSize: 20,
        fontWeight: '600',
    },
    closeBtn: {
        padding: 4,
        marginLeft: 8,
    },
    headerRight: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    headerInsertBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 20,
        gap: 6,
    },
    headerInsertBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
    mainContent: {
        flex: 1,
        flexDirection: 'row',
    },
    // Chat Panel
    chatPanel: {
        width: '28%',
        padding: 16,
        borderRightWidth: 1,
        flexDirection: 'column',
    },
    panelTitle: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 12,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    chatHistory: {
        flex: 1,
    },
    chatHistoryContent: {
        paddingBottom: 8,
    },
    chatPlaceholder: {
        alignItems: 'center',
        paddingVertical: 40,
    },
    chatPlaceholderText: {
        fontSize: 14,
        marginTop: 12,
        textAlign: 'center',
    },
    chatHint: {
        fontSize: 12,
        marginTop: 8,
        textAlign: 'center',
        fontStyle: 'italic',
    },
    chatMessage: {
        padding: 10,
        borderRadius: 8,
        marginBottom: 8,
        flexDirection: 'row',
        alignItems: 'center',
    },
    chatMessageUser: {
        alignSelf: 'flex-end',
        maxWidth: '90%',
    },
    chatMessageError: {
        borderLeftWidth: 3,
        borderLeftColor: '#EF4444',
    },
    chatMessageText: {
        fontSize: 13,
        lineHeight: 18,
    },
    chatInputContainer: {
        flexDirection: 'row',
        gap: 8,
        paddingTop: 12,
        borderTopWidth: 1,
        alignItems: 'flex-end',
    },
    chatInput: {
        flex: 1,
        padding: 10,
        borderRadius: 8,
        borderWidth: 1,
        fontSize: 14,
        minHeight: 120, // Allow ~6 rows
        maxHeight: 200,
        textAlignVertical: 'top',
    },
    sendBtn: {
        padding: 10,
        borderRadius: 8,
        justifyContent: 'center',
        alignItems: 'center',
    },
    // Chart Panel
    chartPanel: {
        flex: 1,
        padding: 16,
    },
    chartContainer: {
        flex: 1,
        borderRadius: 12,
        borderWidth: 1,
        padding: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    chartPlaceholder: {
        alignItems: 'center',
    },
    chartPlaceholderText: {
        fontSize: 14,
        marginTop: 16,
    },
    chartError: {
        color: '#EF4444',
        marginTop: 12,
        fontSize: 13,
    },
    // Options Panel
    optionsPanel: {
        width: '22%',
        padding: 16,
        borderLeftWidth: 1,
        flexDirection: 'column',
    },
    optionLabel: {
        fontSize: 12,
        fontWeight: '500',
        marginBottom: 8,
        textTransform: 'uppercase',
    },
    chartTypeGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    chartTypeBtn: {
        width: '30%',
        padding: 8,
        borderRadius: 8,
        borderWidth: 1,
        alignItems: 'center',
        gap: 2,
    },
    chartTypeName: {
        fontSize: 10,
        fontWeight: '500',
    },
    paletteList: {
        flex: 1,
        marginBottom: 12,
    },
    paletteBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 10,
        borderRadius: 8,
        borderWidth: 1,
        marginBottom: 8,
        gap: 10,
    },
    paletteColors: {
        flexDirection: 'row',
        gap: 3,
    },
    paletteColor: {
        width: 16,
        height: 16,
        borderRadius: 4,
    },
    paletteName: {
        flex: 1,
        fontSize: 13,
        fontWeight: '500',
    },
    insertBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
        borderRadius: 10,
        gap: 8,
    },
    insertBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
};

export default ChartStudio;
