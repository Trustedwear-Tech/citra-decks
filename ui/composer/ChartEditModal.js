// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// ChartEditModal.js - Enhanced modal for editing chart data, style, and options inline
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    TextInput,
    ScrollView,
    StyleSheet,
    Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CHART_TYPES, CHART_CATEGORIES, CHART_PALETTES, applyPaletteToConfig, changeChartType } from '../../utils/chartPalettes';

/**
 * ChartEditModal - Enhanced modal for editing chart data directly on the canvas
 * Opens when user double-clicks on a chart element in presentation/printable/report
 * Features: all chart types, tabbed UI (Data / Style / Options), live preview, palette picker
 */
const ChartEditModal = ({
    visible,
    onClose,
    chartConfig,
    onSave,
    theme,
}) => {
    const [chartType, setChartType] = useState('bar');
    const [labels, setLabels] = useState([]);
    const [datasets, setDatasets] = useState([]);
    const [chartTitle, setChartTitle] = useState('');
    const [activeTab, setActiveTab] = useState('data'); // 'data' | 'style' | 'options'

    // Style state
    const [selectedPalette, setSelectedPalette] = useState(null); // null = keep current colors
    const [labelColor, setLabelColor] = useState('#6B7280'); // axis tick + legend label color
    const [legendPosition, setLegendPosition] = useState('bottom');
    const [showLegend, setShowLegend] = useState(true);
    const [showGrid, setShowGrid] = useState(true);
    const [beginAtZero, setBeginAtZero] = useState(true);
    const [borderRadius, setBorderRadius] = useState(6);

    // Live preview
    const previewCanvasRef = useRef(null);
    const previewChartRef = useRef(null);
    // Initialize state from chartConfig
    useEffect(() => {
        if (chartConfig && visible) {
            // Determine the variant ID if stored, otherwise infer from base type + options
            let typeId = chartConfig._variantId || chartConfig.type || 'bar';
            // Infer variant from options if _variantId not set
            if (!chartConfig._variantId) {
                if (chartConfig.type === 'bar' && chartConfig.options?.indexAxis === 'y') typeId = 'horizontalBar';
                else if (chartConfig.type === 'bar' && chartConfig.options?.scales?.x?.stacked) typeId = 'stackedBar';
                else if (chartConfig.type === 'line' && chartConfig.data?.datasets?.[0]?.fill) typeId = 'area';
                else if (chartConfig.type === 'line' && chartConfig.data?.datasets?.[0]?.stepped) typeId = 'stepLine';
            }
            setChartType(typeId);
            setLabels(chartConfig.data?.labels || []);
            setDatasets(chartConfig.data?.datasets || []);
            setChartTitle(chartConfig.options?.plugins?.title?.text || '');
            setActiveTab('data');
            setSelectedPalette(null);
            // Resolve initial label color from existing config
            const existingLabelColor =
                chartConfig.options?.plugins?.legend?.labels?.color ||
                chartConfig.options?.scales?.x?.ticks?.color ||
                chartConfig.options?.scales?.y?.ticks?.color ||
                '#6B7280';
            setLabelColor(existingLabelColor);
            // Options state
            setLegendPosition(chartConfig.options?.plugins?.legend?.position || 'bottom');
            setShowLegend(chartConfig.options?.plugins?.legend?.display !== false);
            setShowGrid(chartConfig.options?.scales?.y?.grid?.display !== false);
            setBeginAtZero(chartConfig.options?.scales?.y?.beginAtZero !== false);
            setBorderRadius(chartConfig.data?.datasets?.[0]?.borderRadius || 6);
        }
    }, [chartConfig, visible]);

    // Handle label change
    const handleLabelChange = useCallback((index, value) => {
        setLabels(prev => {
            const newLabels = [...prev];
            newLabels[index] = value;
            return newLabels;
        });
    }, []);

    // Handle data value change
    const handleDataChange = useCallback((datasetIndex, dataIndex, value) => {
        setDatasets(prev => {
            const newDatasets = [...prev];
            if (newDatasets[datasetIndex]) {
                const newData = [...(newDatasets[datasetIndex].data || [])];
                newData[dataIndex] = parseFloat(value) || 0;
                newDatasets[datasetIndex] = { ...newDatasets[datasetIndex], data: newData };
            }
            return newDatasets;
        });
    }, []);

    // Handle dataset label change
    const handleDatasetLabelChange = useCallback((datasetIndex, value) => {
        setDatasets(prev => {
            const newDatasets = [...prev];
            if (newDatasets[datasetIndex]) {
                newDatasets[datasetIndex] = { ...newDatasets[datasetIndex], label: value };
            }
            return newDatasets;
        });
    }, []);

    // Add new label/data point
    const handleAddDataPoint = useCallback(() => {
        setLabels(prev => [...prev, `Item ${prev.length + 1}`]);
        setDatasets(prev => prev.map(ds => ({
            ...ds,
            data: [...(ds.data || []), 0]
        })));
    }, []);

    // Remove data point
    const handleRemoveDataPoint = useCallback((index) => {
        setLabels(prev => prev.filter((_, i) => i !== index));
        setDatasets(prev => prev.map(ds => ({
            ...ds,
            data: (ds.data || []).filter((_, i) => i !== index)
        })));
    }, []);

    // Add new dataset
    const handleAddDataset = useCallback(() => {
        const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'];
        const newColor = colors[datasets.length % colors.length];
        setDatasets(prev => [...prev, {
            label: `Dataset ${prev.length + 1}`,
            data: labels.map(() => 0),
            backgroundColor: newColor,
            borderColor: newColor,
        }]);
    }, [datasets.length, labels]);

    // Remove dataset
    const handleRemoveDataset = useCallback((index) => {
        setDatasets(prev => prev.filter((_, i) => i !== index));
    }, []);

    // Scatter/Bubble point handlers
    const handlePointChange = useCallback((dsIndex, pointIndex, field, value) => {
        setDatasets(prev => {
            const newDatasets = [...prev];
            if (newDatasets[dsIndex]) {
                const newData = [...(newDatasets[dsIndex].data || [])];
                newData[pointIndex] = { ...newData[pointIndex], [field]: parseFloat(value) || 0 };
                newDatasets[dsIndex] = { ...newDatasets[dsIndex], data: newData };
            }
            return newDatasets;
        });
    }, []);

    const handleAddPoint = useCallback((dsIndex) => {
        setDatasets(prev => {
            const newDatasets = [...prev];
            if (newDatasets[dsIndex]) {
                const newData = [...(newDatasets[dsIndex].data || [])];
                const newPoint = { x: newData.length, y: 0 };
                if (chartType === 'bubble') newPoint.r = 8;
                newData.push(newPoint);
                newDatasets[dsIndex] = { ...newDatasets[dsIndex], data: newData };
            }
            return newDatasets;
        });
    }, [chartType]);

    const handleRemovePoint = useCallback((dsIndex, pointIndex) => {
        setDatasets(prev => {
            const newDatasets = [...prev];
            if (newDatasets[dsIndex]) {
                const newData = (newDatasets[dsIndex].data || []).filter((_, i) => i !== pointIndex);
                newDatasets[dsIndex] = { ...newDatasets[dsIndex], data: newData };
            }
            return newDatasets;
        });
    }, []);

    // Handle chart type change — uses variant-aware changeChartType with data conversion
    const handleChartTypeChange = useCallback((newTypeId) => {
        // Build current config to convert
        const currentConfig = {
            type: chartConfig?.type || 'bar',
            _variantId: chartType,
            data: { labels, datasets },
            options: chartConfig?.options || {},
        };
        const converted = changeChartType(currentConfig, newTypeId);
        setChartType(newTypeId);
        setLabels(converted.data?.labels || []);
        setDatasets(converted.data?.datasets || []);
    }, [chartType, labels, datasets, chartConfig]);

    // Build the config from current state — used for save and live preview
    const buildConfig = useCallback(() => {
        // Start from a changeChartType conversion to get base type + variant options
        const baseConfig = changeChartType(
            { type: 'bar', data: { labels, datasets }, options: chartConfig?.options || {} },
            chartType
        );

        // Apply style/options overrides
        baseConfig.options = baseConfig.options || {};
        baseConfig.options.plugins = baseConfig.options.plugins || {};
        baseConfig.options.plugins.title = {
            ...baseConfig.options.plugins.title,
            display: !!chartTitle,
            text: chartTitle,
            color: labelColor,
        };
        baseConfig.options.plugins.legend = {
            ...baseConfig.options.plugins.legend,
            display: showLegend,
            position: legendPosition,
            labels: {
                ...(baseConfig.options.plugins.legend?.labels || {}),
                color: labelColor,
            },
        };

        // Axis options for non-radial types
        const isRadial = ['pie', 'doughnut', 'polarArea'].includes(baseConfig.type);
        if (!isRadial && baseConfig.options.scales) {
            if (baseConfig.options.scales.y) {
                baseConfig.options.scales.y.beginAtZero = beginAtZero;
                baseConfig.options.scales.y.grid = { ...(baseConfig.options.scales.y.grid || {}), display: showGrid };
                baseConfig.options.scales.y.ticks = { ...(baseConfig.options.scales.y.ticks || {}), color: labelColor };
            }
            if (baseConfig.options.scales.x) {
                baseConfig.options.scales.x.grid = { ...(baseConfig.options.scales.x.grid || {}), display: false };
                baseConfig.options.scales.x.ticks = { ...(baseConfig.options.scales.x.ticks || {}), color: labelColor };
            }
            // Stacked / horizontal variants may have additional axes
            Object.keys(baseConfig.options.scales).forEach(axisKey => {
                if (axisKey !== 'x' && axisKey !== 'y' && axisKey !== 'r') {
                    baseConfig.options.scales[axisKey].ticks = {
                        ...(baseConfig.options.scales[axisKey].ticks || {}),
                        color: labelColor,
                    };
                }
            });
        }
        // Radial (radar / polarArea) scales
        if (['radar', 'polarArea'].includes(baseConfig.type) && baseConfig.options.scales?.r) {
            baseConfig.options.scales.r.ticks = {
                ...(baseConfig.options.scales.r.ticks || {}),
                color: labelColor,
                backdropColor: 'transparent',
            };
            baseConfig.options.scales.r.pointLabels = {
                ...(baseConfig.options.scales.r.pointLabels || {}),
                color: labelColor,
            };
        }

        // Apply border radius to bar datasets
        if (['bar'].includes(baseConfig.type)) {
            baseConfig.data.datasets = baseConfig.data.datasets.map(ds => ({
                ...ds,
                borderRadius: borderRadius,
            }));
        }

        // Apply palette if selected
        if (selectedPalette) {
            return applyPaletteToConfig(baseConfig, selectedPalette);
        }

        return baseConfig;
    }, [chartConfig, chartType, labels, datasets, chartTitle, labelColor, showLegend, legendPosition, showGrid, beginAtZero, borderRadius, selectedPalette]);

    // Live preview rendering
    useEffect(() => {
        if (!visible || Platform.OS !== 'web' || !previewCanvasRef.current) return;
        if (labels.length === 0 && datasets.length === 0) return;

        const renderPreview = async () => {
            try {
                if (previewChartRef.current) {
                    previewChartRef.current.destroy();
                    previewChartRef.current = null;
                }
                const config = buildConfig();
                const { Chart, registerables } = await import('chart.js');
                Chart.register(...registerables);
                previewChartRef.current = new Chart(previewCanvasRef.current, {
                    ...config,
                    options: {
                        ...config.options,
                        responsive: true,
                        maintainAspectRatio: true,
                        animation: false,
                    },
                });
            } catch (err) {
                console.warn('Preview render error:', err);
            }
        };

        const timeout = setTimeout(renderPreview, 150); // debounce
        return () => {
            clearTimeout(timeout);
            if (previewChartRef.current) {
                previewChartRef.current.destroy();
                previewChartRef.current = null;
            }
        };
    }, [visible, buildConfig]);

    // Save changes
    const handleSave = useCallback(() => {
        const newConfig = buildConfig();
        onSave(newConfig);
        onClose();
    }, [buildConfig, onSave, onClose]);

    // Check if current type uses point data (scatter/bubble)
    const isPointData = ['scatter', 'bubble'].includes(
        (CHART_TYPES.find(t => t.id === chartType) || {}).baseType
    );

    const tabs = [
        { id: 'data', label: 'Data', icon: 'grid-outline' },
        { id: 'style', label: 'Style', icon: 'color-palette-outline' },
        { id: 'options', label: 'Options', icon: 'settings-outline' },
    ];

    const legendPositions = ['top', 'bottom', 'left', 'right'];

    const isDark = theme?.colorScheme === 'dark';
    const bgColor = isDark ? '#1a1a2e' : '#ffffff';
    const textColor = isDark ? '#ffffff' : '#1a1a2e';
    const borderColor = isDark ? '#333355' : '#e0e0e0';
    const inputBg = isDark ? '#252545' : '#f5f5f5';
    const primaryColor = theme?.primary || '#6366f1';

    if (!visible) return null;

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={onClose}
        >
            <View
                style={[styles.overlay, { zIndex: 10000 }]}
                onStartShouldSetResponder={() => true}
                onMoveShouldSetResponder={() => true}
                onResponderTerminationRequest={() => false}
            >
                <View
                    style={[styles.modal, { backgroundColor: bgColor }]}
                    onStartShouldSetResponder={() => true}
                >
                    {/* Header */}
                    <View style={[styles.header, { borderBottomColor: borderColor }]}>
                        <Text style={[styles.title, { color: textColor }]}>Edit Chart</Text>
                        <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                            <Ionicons name="close" size={24} color={textColor} />
                        </TouchableOpacity>
                    </View>

                    {/* Chart Type Selector — categorized */}
                    <View style={{ paddingHorizontal: 16, paddingTop: 12 }}>
                        <Text style={[styles.sectionTitle, { color: textColor, marginTop: 0 }]}>Chart Type</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
                            <View style={{ flexDirection: 'row', gap: 6 }}>
                                {CHART_TYPES.map((type) => (
                                    <TouchableOpacity
                                        key={type.id}
                                        style={[
                                            styles.typeChip,
                                            { borderColor: borderColor },
                                            chartType === type.id && { backgroundColor: primaryColor, borderColor: primaryColor },
                                        ]}
                                        onPress={() => handleChartTypeChange(type.id)}
                                    >
                                        <Ionicons
                                            name={type.icon}
                                            size={14}
                                            color={chartType === type.id ? '#ffffff' : textColor}
                                        />
                                        <Text style={[
                                            styles.typeChipLabel,
                                            { color: chartType === type.id ? '#ffffff' : textColor }
                                        ]} numberOfLines={1}>
                                            {type.name}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </ScrollView>
                    </View>

                    {/* Tabs */}
                    <View style={[styles.tabBar, { borderBottomColor: borderColor }]}>
                        {tabs.map(tab => (
                            <TouchableOpacity
                                key={tab.id}
                                style={[styles.tab, activeTab === tab.id && [styles.tabActive, { borderBottomColor: primaryColor }]]}
                                onPress={() => setActiveTab(tab.id)}
                            >
                                <Ionicons name={tab.icon} size={16} color={activeTab === tab.id ? primaryColor : textColor} />
                                <Text style={[styles.tabText, { color: activeTab === tab.id ? primaryColor : textColor }]}>
                                    {tab.label}
                                </Text>
                            </TouchableOpacity>
                        ))}
                    </View>

                    {/* Live Preview */}
                    {Platform.OS === 'web' && (
                        <View style={{ paddingHorizontal: 16, paddingTop: 8, alignItems: 'center' }}>
                            <View style={{ width: '100%', maxHeight: 160, backgroundColor: inputBg, borderRadius: 8, padding: 8, alignItems: 'center', justifyContent: 'center' }}>
                                <canvas ref={previewCanvasRef} style={{ maxWidth: '100%', maxHeight: 144 }} />
                            </View>
                        </View>
                    )}

                    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
                        {/* === DATA TAB === */}
                        {activeTab === 'data' && (
                            <>
                                {/* Chart Title */}
                                <Text style={[styles.sectionTitle, { color: textColor }]}>Title</Text>
                                <TextInput
                                    style={[styles.input, { backgroundColor: inputBg, color: textColor, borderColor }]}
                                    value={chartTitle}
                                    onChangeText={setChartTitle}
                                    placeholder="Chart Title"
                                    placeholderTextColor={isDark ? '#666' : '#999'}
                                />

                                {!isPointData ? (
                                    <>
                                        {/* Labels */}
                                        <View style={styles.sectionHeader}>
                                            <Text style={[styles.sectionTitle, { color: textColor }]}>Labels</Text>
                                            <TouchableOpacity style={styles.addButton} onPress={handleAddDataPoint}>
                                                <Ionicons name="add" size={16} color="#ffffff" />
                                                <Text style={styles.addButtonText}>Add</Text>
                                            </TouchableOpacity>
                                        </View>
                                        {labels.map((label, index) => (
                                            <View key={index} style={styles.labelRow}>
                                                <TextInput
                                                    style={[styles.labelInput, { backgroundColor: inputBg, color: textColor, borderColor }]}
                                                    value={label}
                                                    onChangeText={(value) => handleLabelChange(index, value)}
                                                    placeholder={`Label ${index + 1}`}
                                                    placeholderTextColor={isDark ? '#666' : '#999'}
                                                />
                                                <TouchableOpacity
                                                    style={styles.removeButton}
                                                    onPress={() => handleRemoveDataPoint(index)}
                                                >
                                                    <Ionicons name="trash-outline" size={18} color="#ff6b6b" />
                                                </TouchableOpacity>
                                            </View>
                                        ))}

                                        {/* Datasets */}
                                        <View style={styles.sectionHeader}>
                                            <Text style={[styles.sectionTitle, { color: textColor }]}>Datasets</Text>
                                            <TouchableOpacity style={styles.addButton} onPress={handleAddDataset}>
                                                <Ionicons name="add" size={16} color="#ffffff" />
                                                <Text style={styles.addButtonText}>Add Dataset</Text>
                                            </TouchableOpacity>
                                        </View>
                                        {datasets.map((dataset, dsIndex) => (
                                            <View key={dsIndex} style={[styles.datasetCard, { backgroundColor: inputBg, borderColor }]}>
                                                <View style={styles.datasetHeader}>
                                                    <TextInput
                                                        style={[styles.datasetNameInput, { color: textColor }]}
                                                        value={dataset.label || ''}
                                                        onChangeText={(value) => handleDatasetLabelChange(dsIndex, value)}
                                                        placeholder="Dataset Name"
                                                        placeholderTextColor={isDark ? '#666' : '#999'}
                                                    />
                                                    <TouchableOpacity
                                                        style={styles.removeButton}
                                                        onPress={() => handleRemoveDataset(dsIndex)}
                                                    >
                                                        <Ionicons name="trash-outline" size={18} color="#ff6b6b" />
                                                    </TouchableOpacity>
                                                </View>
                                                <View style={styles.dataValues}>
                                                    {(dataset.data || []).map((value, dataIndex) => (
                                                        <View key={dataIndex} style={styles.dataValueRow}>
                                                            <Text style={[styles.dataLabel, { color: textColor }]}>
                                                                {labels[dataIndex] || `#${dataIndex + 1}`}:
                                                            </Text>
                                                            <TextInput
                                                                style={[styles.dataInput, { backgroundColor: bgColor, color: textColor, borderColor }]}
                                                                value={String(value)}
                                                                onChangeText={(v) => handleDataChange(dsIndex, dataIndex, v)}
                                                                keyboardType="numeric"
                                                                placeholder="0"
                                                                placeholderTextColor={isDark ? '#666' : '#999'}
                                                            />
                                                        </View>
                                                    ))}
                                                </View>
                                            </View>
                                        ))}
                                    </>
                                ) : (
                                    /* Scatter / Bubble point data editor */
                                    <>
                                        <View style={styles.sectionHeader}>
                                            <Text style={[styles.sectionTitle, { color: textColor }]}>Datasets</Text>
                                            <TouchableOpacity style={styles.addButton} onPress={handleAddDataset}>
                                                <Ionicons name="add" size={16} color="#ffffff" />
                                                <Text style={styles.addButtonText}>Add Dataset</Text>
                                            </TouchableOpacity>
                                        </View>
                                        {datasets.map((dataset, dsIndex) => (
                                            <View key={dsIndex} style={[styles.datasetCard, { backgroundColor: inputBg, borderColor }]}>
                                                <View style={styles.datasetHeader}>
                                                    <TextInput
                                                        style={[styles.datasetNameInput, { color: textColor }]}
                                                        value={dataset.label || ''}
                                                        onChangeText={(value) => handleDatasetLabelChange(dsIndex, value)}
                                                        placeholder="Dataset Name"
                                                        placeholderTextColor={isDark ? '#666' : '#999'}
                                                    />
                                                    <TouchableOpacity style={styles.removeButton} onPress={() => handleRemoveDataset(dsIndex)}>
                                                        <Ionicons name="trash-outline" size={18} color="#ff6b6b" />
                                                    </TouchableOpacity>
                                                </View>
                                                <View style={{ flexDirection: 'row', gap: 4, marginBottom: 4 }}>
                                                    <Text style={[styles.dataLabel, { color: textColor, flex: 1, fontWeight: '600' }]}>X</Text>
                                                    <Text style={[styles.dataLabel, { color: textColor, flex: 1, fontWeight: '600' }]}>Y</Text>
                                                    {chartType === 'bubble' && (
                                                        <Text style={[styles.dataLabel, { color: textColor, flex: 1, fontWeight: '600' }]}>R</Text>
                                                    )}
                                                    <View style={{ width: 34 }} />
                                                </View>
                                                {(dataset.data || []).map((point, pIndex) => (
                                                    <View key={pIndex} style={{ flexDirection: 'row', gap: 4, marginBottom: 4 }}>
                                                        <TextInput
                                                            style={[styles.dataInput, { flex: 1, backgroundColor: bgColor, color: textColor, borderColor }]}
                                                            value={String(point?.x ?? '')}
                                                            onChangeText={(v) => handlePointChange(dsIndex, pIndex, 'x', v)}
                                                            keyboardType="numeric"
                                                            placeholder="X"
                                                            placeholderTextColor={isDark ? '#666' : '#999'}
                                                        />
                                                        <TextInput
                                                            style={[styles.dataInput, { flex: 1, backgroundColor: bgColor, color: textColor, borderColor }]}
                                                            value={String(point?.y ?? '')}
                                                            onChangeText={(v) => handlePointChange(dsIndex, pIndex, 'y', v)}
                                                            keyboardType="numeric"
                                                            placeholder="Y"
                                                            placeholderTextColor={isDark ? '#666' : '#999'}
                                                        />
                                                        {chartType === 'bubble' && (
                                                            <TextInput
                                                                style={[styles.dataInput, { flex: 1, backgroundColor: bgColor, color: textColor, borderColor }]}
                                                                value={String(point?.r ?? 8)}
                                                                onChangeText={(v) => handlePointChange(dsIndex, pIndex, 'r', v)}
                                                                keyboardType="numeric"
                                                                placeholder="R"
                                                                placeholderTextColor={isDark ? '#666' : '#999'}
                                                            />
                                                        )}
                                                        <TouchableOpacity style={styles.removeButton} onPress={() => handleRemovePoint(dsIndex, pIndex)}>
                                                            <Ionicons name="close-circle-outline" size={18} color="#ff6b6b" />
                                                        </TouchableOpacity>
                                                    </View>
                                                ))}
                                                <TouchableOpacity
                                                    style={[styles.addButton, { alignSelf: 'flex-start', marginTop: 4 }]}
                                                    onPress={() => handleAddPoint(dsIndex)}
                                                >
                                                    <Ionicons name="add" size={14} color="#ffffff" />
                                                    <Text style={styles.addButtonText}>Add Point</Text>
                                                </TouchableOpacity>
                                            </View>
                                        ))}
                                    </>
                                )}
                            </>
                        )}

                        {/* === STYLE TAB === */}
                        {activeTab === 'style' && (
                            <>
                                <Text style={[styles.sectionTitle, { color: textColor }]}>Color Palette</Text>
                                <Text style={{ fontSize: 12, color: isDark ? '#888' : '#999', marginBottom: 8 }}>
                                    Select a palette to override current colors
                                </Text>
                                {Object.entries(CHART_PALETTES).map(([key, palette]) => (
                                    <TouchableOpacity
                                        key={key}
                                        style={[
                                            styles.paletteRow,
                                            { borderColor: selectedPalette === key ? primaryColor : borderColor },
                                            selectedPalette === key && { backgroundColor: primaryColor + '20' },
                                        ]}
                                        onPress={() => setSelectedPalette(selectedPalette === key ? null : key)}
                                    >
                                        <View style={{ flexDirection: 'row', gap: 3 }}>
                                            {palette.colors.slice(0, 6).map((c, i) => (
                                                <View key={i} style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: c }} />
                                            ))}
                                        </View>
                                        <Text style={[styles.paletteName, { color: textColor }]}>{palette.name}</Text>
                                        {selectedPalette === key && (
                                            <Ionicons name="checkmark-circle" size={18} color={primaryColor} />
                                        )}
                                    </TouchableOpacity>
                                ))}

                                {/* Border Radius (for bar charts) */}
                                {['bar', 'horizontalBar', 'stackedBar'].includes(chartType) && (
                                    <>
                                        <Text style={[styles.sectionTitle, { color: textColor }]}>Bar Corner Radius</Text>
                                        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                                            {[0, 4, 6, 10, 16].map(r => (
                                                <TouchableOpacity
                                                    key={r}
                                                    style={[
                                                        styles.optionChip,
                                                        { borderColor: borderRadius === r ? primaryColor : borderColor },
                                                        borderRadius === r && { backgroundColor: primaryColor + '20' },
                                                    ]}
                                                    onPress={() => setBorderRadius(r)}
                                                >
                                                    <Text style={{ color: borderRadius === r ? primaryColor : textColor, fontSize: 13 }}>{r}px</Text>
                                                </TouchableOpacity>
                                            ))}
                                        </View>
                                    </>
                                )}

                                {/* Label Color */}
                                <Text style={[styles.sectionTitle, { color: textColor }]}>Label Color</Text>
                                <Text style={{ fontSize: 12, color: isDark ? '#888' : '#999', marginBottom: 8 }}>
                                    Applies to axis tick labels, legend text, and chart title
                                </Text>
                                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                                    {['#1F2937', '#374151', '#6B7280', '#9CA3AF', '#D1D5DB', '#FFFFFF', '#000000', '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'].map(c => (
                                        <TouchableOpacity
                                            key={c}
                                            onPress={() => setLabelColor(c)}
                                            style={{
                                                width: 28,
                                                height: 28,
                                                borderRadius: 14,
                                                backgroundColor: c,
                                                borderWidth: labelColor === c ? 3 : 1,
                                                borderColor: labelColor === c ? primaryColor : borderColor,
                                            }}
                                        />
                                    ))}
                                    {/* Native color picker for custom color */}
                                    {Platform.OS === 'web' && (
                                        <View style={{ width: 28, height: 28, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor }}>
                                            <input
                                                type="color"
                                                value={labelColor}
                                                onChange={(e) => setLabelColor(e.target.value)}
                                                title="Custom color"
                                                style={{
                                                    width: '200%',
                                                    height: '200%',
                                                    border: 'none',
                                                    padding: 0,
                                                    cursor: 'pointer',
                                                    transform: 'translate(-25%, -25%)',
                                                    opacity: labelColor && !['#1F2937','#374151','#6B7280','#9CA3AF','#D1D5DB','#FFFFFF','#000000','#3B82F6','#10B981','#F59E0B','#EF4444','#8B5CF6'].includes(labelColor) ? 1 : 0.4,
                                                }}
                                            />
                                        </View>
                                    )}
                                </View>
                                {/* Current color preview */}
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                                    <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: labelColor, borderWidth: 1, borderColor }} />
                                    <Text style={{ fontSize: 12, color: isDark ? '#aaa' : '#666' }}>{labelColor}</Text>
                                </View>
                            </>
                        )}

                        {/* === OPTIONS TAB === */}
                        {activeTab === 'options' && (
                            <>
                                {/* Legend */}
                                <Text style={[styles.sectionTitle, { color: textColor }]}>Legend</Text>
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                                    <TouchableOpacity
                                        style={[styles.toggleBtn, showLegend && styles.toggleBtnActive]}
                                        onPress={() => setShowLegend(!showLegend)}
                                    >
                                        <Ionicons name={showLegend ? 'checkbox' : 'square-outline'} size={20} color={showLegend ? primaryColor : textColor} />
                                        <Text style={{ color: textColor, fontSize: 13 }}>Show Legend</Text>
                                    </TouchableOpacity>
                                </View>
                                {showLegend && (
                                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                                        {legendPositions.map(pos => (
                                            <TouchableOpacity
                                                key={pos}
                                                style={[
                                                    styles.optionChip,
                                                    { borderColor: legendPosition === pos ? primaryColor : borderColor },
                                                    legendPosition === pos && { backgroundColor: primaryColor + '20' },
                                                ]}
                                                onPress={() => setLegendPosition(pos)}
                                            >
                                                <Text style={{ color: legendPosition === pos ? primaryColor : textColor, fontSize: 13, textTransform: 'capitalize' }}>{pos}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                )}

                                {/* Axis Options — only for non-radial types */}
                                {!['pie', 'doughnut', 'polarArea', 'radar'].includes(
                                    (CHART_TYPES.find(t => t.id === chartType) || {}).baseType
                                ) && (
                                    <>
                                        <Text style={[styles.sectionTitle, { color: textColor }]}>Axes</Text>
                                        <View style={{ gap: 8, marginBottom: 8 }}>
                                            <TouchableOpacity
                                                style={[styles.toggleBtn, beginAtZero && styles.toggleBtnActive]}
                                                onPress={() => setBeginAtZero(!beginAtZero)}
                                            >
                                                <Ionicons name={beginAtZero ? 'checkbox' : 'square-outline'} size={20} color={beginAtZero ? primaryColor : textColor} />
                                                <Text style={{ color: textColor, fontSize: 13 }}>Y-Axis Begin at Zero</Text>
                                            </TouchableOpacity>
                                            <TouchableOpacity
                                                style={[styles.toggleBtn, showGrid && styles.toggleBtnActive]}
                                                onPress={() => setShowGrid(!showGrid)}
                                            >
                                                <Ionicons name={showGrid ? 'checkbox' : 'square-outline'} size={20} color={showGrid ? primaryColor : textColor} />
                                                <Text style={{ color: textColor, fontSize: 13 }}>Show Grid Lines</Text>
                                            </TouchableOpacity>
                                        </View>
                                    </>
                                )}
                            </>
                        )}
                    </ScrollView>

                    {/* Footer */}
                    <View style={[styles.footer, { borderTopColor: borderColor }]}>
                        <TouchableOpacity
                            style={[styles.cancelButton, { borderColor }]}
                            onPress={onClose}
                        >
                            <Text style={[styles.cancelButtonText, { color: textColor }]}>Cancel</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.saveButton}
                            onPress={handleSave}
                        >
                            <Text style={styles.saveButtonText}>Save Changes</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    modal: {
        width: '90%',
        maxWidth: 500,
        maxHeight: '85%',
        borderRadius: 16,
        overflow: 'hidden',
        ...(Platform.OS === 'web' && {
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.3)',
        }),
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
    closeButton: {
        padding: 4,
    },
    content: {
        padding: 16,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 8,
        marginTop: 16,
    },
    sectionHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: 16,
        marginBottom: 8,
    },
    typeChipScroll: {
        marginBottom: 12,
    },
    typeChip: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 20,
        borderWidth: 1,
        marginRight: 8,
        gap: 6,
    },
    typeChipActive: {
        backgroundColor: '#6366f1',
        borderColor: '#6366f1',
    },
    typeChipLabel: {
        fontSize: 12,
        fontWeight: '500',
    },
    tabBar: {
        flexDirection: 'row',
        borderBottomWidth: 1,
        marginBottom: 12,
    },
    tab: {
        flex: 1,
        paddingVertical: 10,
        alignItems: 'center',
    },
    tabActive: {
        borderBottomWidth: 2,
        borderBottomColor: '#6366f1',
    },
    tabText: {
        fontSize: 13,
        fontWeight: '500',
    },
    previewCanvas: {
        width: '100%',
        height: 180,
        marginBottom: 12,
        borderRadius: 8,
    },
    paletteRow: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 10,
        borderRadius: 8,
        borderWidth: 1,
        marginBottom: 8,
        gap: 8,
    },
    paletteName: {
        fontSize: 13,
        fontWeight: '500',
        flex: 1,
    },
    paletteColors: {
        flexDirection: 'row',
        gap: 4,
    },
    paletteSwatch: {
        width: 16,
        height: 16,
        borderRadius: 3,
    },
    optionRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 10,
    },
    optionLabel: {
        fontSize: 14,
    },
    optionChip: {
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 6,
        borderWidth: 1,
        marginLeft: 8,
    },
    toggleBtn: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 8,
        borderWidth: 1,
    },
    toggleBtnActive: {
        backgroundColor: '#6366f1',
        borderColor: '#6366f1',
    },
    pointRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginBottom: 6,
    },
    pointInput: {
        flex: 1,
        height: 36,
        borderRadius: 6,
        borderWidth: 1,
        paddingHorizontal: 8,
        fontSize: 13,
        textAlign: 'center',
    },
    pointLabel: {
        fontSize: 11,
        fontWeight: '500',
        width: 14,
        textAlign: 'center',
    },
    input: {
        height: 44,
        borderRadius: 8,
        borderWidth: 1,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    labelRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
    },
    labelInput: {
        flex: 1,
        height: 40,
        borderRadius: 8,
        borderWidth: 1,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    addButton: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#6366f1',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 6,
        gap: 4,
    },
    addButtonText: {
        color: '#ffffff',
        fontSize: 12,
        fontWeight: '500',
    },
    removeButton: {
        padding: 8,
    },
    datasetCard: {
        borderRadius: 8,
        borderWidth: 1,
        padding: 12,
        marginBottom: 12,
    },
    datasetHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 12,
    },
    datasetNameInput: {
        flex: 1,
        fontSize: 14,
        fontWeight: '500',
    },
    dataValues: {
        gap: 8,
    },
    dataValueRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    dataLabel: {
        fontSize: 13,
        width: 80,
    },
    dataInput: {
        flex: 1,
        height: 36,
        borderRadius: 6,
        borderWidth: 1,
        paddingHorizontal: 10,
        fontSize: 14,
        textAlign: 'right',
    },
    footer: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        gap: 12,
        padding: 16,
        borderTopWidth: 1,
    },
    cancelButton: {
        paddingHorizontal: 20,
        paddingVertical: 10,
        borderRadius: 8,
        borderWidth: 1,
    },
    cancelButtonText: {
        fontSize: 14,
        fontWeight: '500',
    },
    saveButton: {
        backgroundColor: '#6366f1',
        paddingHorizontal: 20,
        paddingVertical: 10,
        borderRadius: 8,
    },
    saveButtonText: {
        color: '#ffffff',
        fontSize: 14,
        fontWeight: '600',
    },
});

export default ChartEditModal;
