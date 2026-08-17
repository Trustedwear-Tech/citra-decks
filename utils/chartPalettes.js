// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * Chart color palettes and utilities for ChartStudio
 */

// Predefined color palettes for charts
export const CHART_PALETTES = {
    corporate: {
        name: 'Corporate Blue',
        colors: ['#2563EB', '#3B82F6', '#60A5FA', '#1D4ED8', '#1E3A8A', '#93C5FD'],
        background: 'rgba(37, 99, 235, 0.1)',
    },
    corporateNavy: {
        name: 'Navy Professional',
        colors: ['#0F172A', '#1E293B', '#334155', '#475569', '#64748B', '#94A3B8'],
        background: 'rgba(15, 23, 42, 0.1)',
    },
    corporateClassic: {
        name: 'Classic Business',
        colors: ['#1e40af', '#047857', '#b91c1c', '#d97706', '#6d28d9', '#4b5563'],
        background: 'rgba(30, 64, 175, 0.1)',
    },
    darkFuturistic: {
        name: 'Dark Mode',
        colors: ['#60A5FA', '#34D399', '#F472B6', '#A78BFA', '#FBBF24', '#9CA3AF'], // Brighter colors against dark bg
        background: 'rgba(31, 41, 55, 0.8)', // Dark background for the chart area itself if transparent
    },
    vibrant: {
        name: 'Vibrant',
        colors: ['#EF4444', '#F97316', '#FACC15', '#22C55E', '#3B82F6', '#8B5CF6'],
        background: 'rgba(239, 68, 68, 0.1)',
    },
    pastel: {
        name: 'Pastel & Readable',
        colors: ['#FDA4AF', '#FDBA74', '#FDE047', '#86EFAC', '#93C5FD', '#C4B5FD'],
        background: 'rgba(254, 205, 211, 0.1)',
    },
    brightPastel: {
        name: 'Bright Pastel (New)',
        colors: ['#FF9F9F', '#FCD34D', '#4FD1C5', '#60A5FA', '#A78BFA', '#FB923C'],
        background: 'rgba(255, 159, 159, 0.1)',
    },
    monochrome: {
        name: 'Monochrome',
        colors: ['#1F2937', '#374151', '#4B5563', '#6B7280', '#9CA3AF', '#D1D5DB'],
        background: 'rgba(31, 41, 55, 0.1)',
    },
    earthTones: {
        name: 'Earth Tones',
        colors: ['#78350F', '#A16207', '#65A30D', '#047857', '#0E7490', '#4338CA'],
        background: 'rgba(120, 53, 15, 0.1)',
    },
    sunset: {
        name: 'Sunset',
        colors: ['#DC2626', '#EA580C', '#F59E0B', '#FBBF24', '#FCD34D', '#FDE68A'],
        background: 'rgba(220, 38, 38, 0.1)',
    },
    ocean: {
        name: 'Ocean',
        colors: ['#0C4A6E', '#0369A1', '#0EA5E9', '#38BDF8', '#7DD3FC', '#BAE6FD'],
        background: 'rgba(12, 74, 110, 0.1)',
    },
};

// Chart type configurations — organized by category
// baseType: the Chart.js native type used for rendering
// defaultOptions: additional Chart.js options applied when this variant is selected
export const CHART_TYPES = [
    // Basic
    { id: 'bar', baseType: 'bar', name: 'Bar', icon: 'bar-chart', category: 'Basic' },
    { id: 'line', baseType: 'line', name: 'Line', icon: 'trending-up', category: 'Basic' },
    { id: 'pie', baseType: 'pie', name: 'Pie', icon: 'pie-chart', category: 'Basic' },
    { id: 'doughnut', baseType: 'doughnut', name: 'Doughnut', icon: 'radio-button-off', category: 'Basic' },
    // Advanced
    { id: 'horizontalBar', baseType: 'bar', name: 'Horizontal Bar', icon: 'swap-horizontal', category: 'Advanced', defaultOptions: { indexAxis: 'y' } },
    { id: 'stackedBar', baseType: 'bar', name: 'Stacked Bar', icon: 'layers', category: 'Advanced', defaultOptions: { scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } },
    { id: 'area', baseType: 'line', name: 'Area', icon: 'analytics', category: 'Advanced', datasetDefaults: { fill: true } },
    { id: 'stepLine', baseType: 'line', name: 'Step Line', icon: 'git-commit', category: 'Advanced', datasetDefaults: { stepped: true } },
    { id: 'scatter', baseType: 'scatter', name: 'Scatter', icon: 'ellipse', category: 'Advanced' },
    { id: 'bubble', baseType: 'bubble', name: 'Bubble', icon: 'ellipsis-horizontal-circle', category: 'Advanced' },
    // Specialized
    { id: 'radar', baseType: 'radar', name: 'Radar', icon: 'radio', category: 'Specialized' },
    { id: 'polarArea', baseType: 'polarArea', name: 'Polar Area', icon: 'aperture', category: 'Specialized' },
    { id: 'mixed', baseType: 'bar', name: 'Mixed / Combo', icon: 'git-merge', category: 'Specialized' },
];

// Categories for UI grouping
export const CHART_CATEGORIES = ['Basic', 'Advanced', 'Specialized'];

/**
 * Apply a color palette to a Chart.js configuration
 * @param {Object} chartConfig - Original Chart.js config
 * @param {string} paletteKey - Key from CHART_PALETTES
 * @returns {Object} - Modified Chart.js config with new colors
 */
export const applyPaletteToConfig = (chartConfig, paletteKey) => {
    const palette = CHART_PALETTES[paletteKey] || CHART_PALETTES.corporate;
    const newConfig = JSON.parse(JSON.stringify(chartConfig)); // Deep clone

    if (newConfig.data && newConfig.data.datasets) {
        newConfig.data.datasets = newConfig.data.datasets.map((dataset, index) => {
            const isPieOrDoughnut = ['pie', 'doughnut', 'polarArea'].includes(newConfig.type);
            const isScatterOrBubble = ['scatter', 'bubble'].includes(newConfig.type);

            // Common enhancements for all charts
            const baseDataset = {
                ...dataset,
                borderWidth: 0, // Clean look
                hoverOffset: 6,
            };

            if (isPieOrDoughnut) {
                return {
                    ...baseDataset,
                    backgroundColor: palette.colors,
                    borderColor: '#ffffff', // split segments with white
                    borderWidth: 2,
                };
            } else if (isScatterOrBubble) {
                const color = palette.colors[index % palette.colors.length];
                return {
                    ...baseDataset,
                    backgroundColor: color + '99', // 60% opacity for bubbles/scatter
                    borderColor: color,
                    borderWidth: 2,
                    pointBackgroundColor: color + '99',
                    pointBorderColor: color,
                    pointRadius: newConfig.type === 'bubble' ? undefined : 5,
                    pointHoverRadius: newConfig.type === 'bubble' ? undefined : 7,
                };
            } else {
                const color = palette.colors[index % palette.colors.length];
                const isLine = newConfig.type === 'line';
                const isFilled = dataset.fill === true || dataset.fill === 'origin';

                return {
                    ...baseDataset,
                    backgroundColor: (isLine && !isFilled) ? palette.background : isFilled ? (color + '33') : color,
                    borderColor: color,
                    borderWidth: isLine ? 3 : 0,
                    borderRadius: isLine ? 0 : 6, // Rounded corners for bars
                    pointBackgroundColor: '#ffffff',
                    pointBorderColor: color,
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    tension: 0.4, // Smooth lines
                };
            }
        });
    }

    // Enhance Options
    newConfig.options = newConfig.options || {};
    newConfig.options.plugins = newConfig.options.plugins || {};

    // Modern Legend
    newConfig.options.plugins.legend = {
        ...newConfig.options.plugins.legend,
        labels: {
            usePointStyle: true, // Use dots instead of boxes
            boxWidth: 8,
            padding: 20,
            font: {
                family: 'System',
                size: 12
            }
        }
    };

    // Clean Grid Lines for cartesian charts
    if (newConfig.options.scales) {
        ['x', 'y'].forEach(axis => {
            if (newConfig.options.scales[axis]) {
                newConfig.options.scales[axis].grid = {
                    display: axis === 'y', // Only show horizontal grid lines
                    drawBorder: false,
                    color: 'rgba(0,0,0,0.05)', // Very subtle
                    ...(newConfig.options.scales[axis].grid || {})
                };
            }
        });
    }

    return newConfig;
};

/**
 * Resolve a chart type ID (including variants) to its Chart.js base type and options
 */
export const resolveChartType = (typeId) => {
    const typeEntry = CHART_TYPES.find(t => t.id === typeId);
    if (!typeEntry) return { baseType: typeId, defaultOptions: {}, datasetDefaults: {} };
    return {
        baseType: typeEntry.baseType,
        defaultOptions: typeEntry.defaultOptions || {},
        datasetDefaults: typeEntry.datasetDefaults || {},
    };
};

/**
 * Convert label-based data to {x,y} point format for scatter/bubble
 */
const convertToPointData = (labels, values, isBubble) => {
    return values.map((v, i) => {
        const point = { x: i, y: typeof v === 'number' ? v : parseFloat(v) || 0 };
        if (isBubble) point.r = 8; // default bubble radius
        return point;
    });
};

/**
 * Convert {x,y} point data back to label-based format
 */
const convertFromPointData = (pointData, labelCount) => {
    const labels = [];
    const values = [];
    (pointData || []).forEach((p, i) => {
        labels.push(p.x != null ? String(p.x) : `Point ${i + 1}`);
        values.push(p.y != null ? p.y : 0);
    });
    // Pad if needed
    while (labels.length < labelCount) {
        labels.push(`Point ${labels.length + 1}`);
        values.push(0);
    }
    return { labels, values };
};

/**
 * Change chart type in a Chart.js configuration — handles variants and data conversion
 * @param {Object} chartConfig - Original Chart.js config
 * @param {string} newTypeId - New chart type ID (from CHART_TYPES)
 * @returns {Object} - Modified Chart.js config with new type
 */
export const changeChartType = (chartConfig, newTypeId) => {
    const newConfig = JSON.parse(JSON.stringify(chartConfig)); // Deep clone
    const { baseType, defaultOptions, datasetDefaults } = resolveChartType(newTypeId);
    const oldType = newConfig.type;
    const wasScatterOrBubble = ['scatter', 'bubble'].includes(oldType);
    const isScatterOrBubble = ['scatter', 'bubble'].includes(baseType);

    newConfig.type = baseType;
    newConfig._variantId = newTypeId; // Store variant for UI state

    // --- Data format conversion ---
    if (!wasScatterOrBubble && isScatterOrBubble) {
        // Converting FROM label-based TO point-based
        if (newConfig.data?.datasets) {
            newConfig.data.datasets = newConfig.data.datasets.map(ds => ({
                ...ds,
                data: convertToPointData(newConfig.data.labels || [], ds.data || [], baseType === 'bubble'),
            }));
        }
        // Scatter/bubble don't use labels array for rendering, but keep it for back-conversion
        newConfig.data._savedLabels = newConfig.data.labels;
        delete newConfig.data.labels;
    } else if (wasScatterOrBubble && !isScatterOrBubble) {
        // Converting FROM point-based TO label-based
        if (newConfig.data?.datasets?.length > 0) {
            const firstDs = newConfig.data.datasets[0];
            const { labels, values } = convertFromPointData(firstDs.data, (firstDs.data || []).length);
            newConfig.data.labels = newConfig.data._savedLabels || labels;
            newConfig.data.datasets = newConfig.data.datasets.map(ds => {
                const { values: dsValues } = convertFromPointData(ds.data, labels.length);
                return { ...ds, data: dsValues };
            });
        }
        delete newConfig.data._savedLabels;
    }

    // --- Options adjustments ---
    newConfig.options = newConfig.options || {};

    // Remove variant-specific options first (clean slate for variant)
    delete newConfig.options.indexAxis;

    if (['pie', 'doughnut', 'polarArea'].includes(baseType)) {
        delete newConfig.options.scales;
    } else if (isScatterOrBubble) {
        // Scatter/bubble need proper scales
        newConfig.options.scales = {
            x: { title: { display: true, text: 'X' }, ...(newConfig.options.scales?.x || {}) },
            y: { beginAtZero: true, title: { display: true, text: 'Y' }, ...(newConfig.options.scales?.y || {}) },
        };
    } else if (!newConfig.options.scales) {
        newConfig.options.scales = {
            y: { beginAtZero: true },
        };
    }

    // Apply variant default options (deep merge)
    if (defaultOptions) {
        Object.keys(defaultOptions).forEach(key => {
            if (key === 'scales' && typeof defaultOptions[key] === 'object') {
                newConfig.options.scales = newConfig.options.scales || {};
                Object.keys(defaultOptions[key]).forEach(axis => {
                    newConfig.options.scales[axis] = { ...(newConfig.options.scales[axis] || {}), ...defaultOptions[key][axis] };
                });
            } else {
                newConfig.options[key] = defaultOptions[key];
            }
        });
    }

    // Apply dataset defaults (fill, stepped, etc.)
    if (datasetDefaults && newConfig.data?.datasets) {
        newConfig.data.datasets = newConfig.data.datasets.map(ds => ({
            ...ds,
            ...datasetDefaults,
        }));
    }

    // For mixed charts, ensure each dataset has an explicit type
    if (newTypeId === 'mixed' && newConfig.data?.datasets) {
        newConfig.data.datasets = newConfig.data.datasets.map((ds, i) => ({
            ...ds,
            type: ds.type || (i % 2 === 0 ? 'bar' : 'line'),
        }));
    }

    // Clean up dataset fields that don't apply to new type
    if (newConfig.data?.datasets) {
        newConfig.data.datasets = newConfig.data.datasets.map(ds => {
            const cleaned = { ...ds };
            if (newTypeId !== 'area' && newTypeId !== 'mixed') delete cleaned.fill;
            if (newTypeId !== 'stepLine') delete cleaned.stepped;
            if (newTypeId !== 'mixed') delete cleaned.type;
            return cleaned;
        });
    }

    return newConfig;
};

export default {
    CHART_PALETTES,
    CHART_TYPES,
    CHART_CATEGORIES,
    applyPaletteToConfig,
    changeChartType,
    resolveChartType,
};
