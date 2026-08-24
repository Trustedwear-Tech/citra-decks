// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * AIDiagramModal - AI-powered SVG diagram generator for the composer.
 *
 * Replaces the legacy "Insert Diagram" flow with a unified AI dialog that
 * lets the user pick a diagram kind (Flowchart / Infographic / Org Chart),
 * type a prompt, preview the generated <svg> markup, and insert it as an
 * `svg_diagram` element on the slide / page.
 *
 * Backend: POST {API_URL}/composer/generate-svg-diagram
 *   body: { user_query, diagram_kind, page_title, page_snippet, width, height, user_id }
 *   reply: { success, svg, diagram_kind, title, prompt_used }
 *
 * onInsertDiagram(svg, prompt, diagramKind, title) — invoked when user clicks Insert.
 */

import React, { useState, useEffect, useCallback } from 'react';
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

const DIAGRAM_KINDS = [
    { id: 'flowchart',   label: 'Flowchart',   icon: 'git-network-outline' },
    { id: 'infographic', label: 'Infographic', icon: 'stats-chart-outline' },
    { id: 'org_chart',   label: 'Org Chart',   icon: 'people-outline' },
];

const AIDiagramModal = ({
    visible,
    onClose,
    onInsertDiagram,
    currentPage,
    userDeviceId,
    apiConfig,
    theme,
    initialPrompt = '',
    initialKind = 'flowchart',
    width = 920,
    height = 440,
    paletteHint = '',
    currentSvg = '',  // when regenerating, the existing SVG markup is sent to the LLM
                      // as edit context so it can preserve / modify it instead of
                      // generating from scratch.
}) => {
    const { width: screenWidth } = useWindowDimensions();
    const isMobile = screenWidth < 768;

    const [prompt, setPrompt] = useState(initialPrompt);
    const [diagramKind, setDiagramKind] = useState(initialKind || 'flowchart');
    const [isGenerating, setIsGenerating] = useState(false);
    const [generatedSvg, setGeneratedSvg] = useState(null);
    const [generatedTitle, setGeneratedTitle] = useState('');
    const [error, setError] = useState(null);
    const [stage, setStage] = useState('input'); // 'input' | 'generating' | 'preview'

    const safeTheme = theme || {
        background: '#ffffff',
        surface: '#f5f5f5',
        text: '#333333',
        textSecondary: '#666666',
        primary: '#2196F3',
        border: '#e0e0e0',
    };

    const getPageSnippet = useCallback(() => {
        if (!currentPage?.content) return '';
        const text = String(currentPage.content).replace(/<[^>]*>/g, '');
        return text.substring(0, 300);
    }, [currentPage]);

    const generateDiagram = useCallback(async () => {
        if (!prompt.trim() || isGenerating) return;

        setIsGenerating(true);
        setError(null);
        setGeneratedSvg(null);
        setStage('generating');

        try {
            const token = await AsyncStorage.getItem('@auth_token');
            if (!token) {
                setError('Please log in again.');
                setStage('input');
                setIsGenerating(false);
                return;
            }

            const response = await fetch(
                `${apiConfig.API_URL}/composer/generate-svg-diagram`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        user_query: prompt,
                        diagram_kind: diagramKind,
                        page_title: currentPage?.title || '',
                        page_snippet: getPageSnippet(),
                        width,
                        height,
                        palette_hint: paletteHint || '',
                        // When editing an existing diagram, pass its SVG so the LLM
                        // can revise rather than start from scratch.
                        current_svg: currentSvg || '',
                        user_id: userDeviceId,
                    }),
                }
            );

            if (!response.ok) {
                const errText = await response.text().catch(() => '');
                setError(`Request failed (${response.status}). ${errText.slice(0, 160)}`);
                setStage('input');
                setIsGenerating(false);
                return;
            }

            const data = await response.json();
            if (data.success && data.svg) {
                setGeneratedSvg(data.svg);
                setGeneratedTitle(data.title || '');
                setStage('preview');
            } else {
                setError(data.detail || data.message || 'Failed to generate diagram.');
                setStage('input');
            }
        } catch (err) {
            console.error('SVG diagram generation error:', err);
            setError('Network error. Please try again.');
            setStage('input');
        } finally {
            setIsGenerating(false);
        }
    }, [prompt, diagramKind, isGenerating, currentPage, getPageSnippet,
        userDeviceId, apiConfig, width, height, paletteHint]);

    const handleInsert = useCallback(() => {
        if (!generatedSvg) return;
        onInsertDiagram?.(generatedSvg, prompt, diagramKind, generatedTitle);
        onClose?.();
    }, [generatedSvg, prompt, diagramKind, generatedTitle, onInsertDiagram, onClose]);

    const handleRegenerate = useCallback(() => {
        generateDiagram();
    }, [generateDiagram]);

    // Reset on close; rehydrate from initialPrompt/initialKind on open.
    useEffect(() => {
        if (!visible) {
            setError(null);
            setIsGenerating(false);
        } else {
            setPrompt(initialPrompt || '');
            setDiagramKind(initialKind || 'flowchart');
            setGeneratedSvg(null);
            setGeneratedTitle('');
            setError(null);
            setStage('input');
        }
    }, [visible, initialPrompt, initialKind]);

    if (!visible) return null;

    const renderSvgPreview = () => {
        if (!generatedSvg) return null;
        if (Platform.OS === 'web') {
            return (
                <div
                    style={{ width: '100%', height: '100%', display: 'flex',
                             alignItems: 'center', justifyContent: 'center', padding: 16 }}
                    // eslint-disable-next-line react/no-danger
                    dangerouslySetInnerHTML={{ __html: generatedSvg }}
                />
            );
        }
        // Native: lazy-require react-native-svg's SvgXml so this file stays
        // safe to import even if the package is missing in some build profiles.
        try {
            // eslint-disable-next-line global-require
            const { SvgXml } = require('react-native-svg');
            return (
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 16 }}>
                    <SvgXml xml={generatedSvg} width="100%" height="100%" />
                </View>
            );
        } catch (e) {
            return (
                <View style={styles.errorContainer}>
                    <Text style={styles.errorText}>SVG preview unavailable on this platform.</Text>
                </View>
            );
        }
    };

    const content = (
        <View style={[
            styles.container,
            { backgroundColor: safeTheme.background },
            isMobile && { width: '100%', height: '100%', maxWidth: undefined, maxHeight: undefined, borderRadius: 0 },
        ]}>
            {/* Header */}
            <View style={[styles.header, { borderBottomColor: safeTheme.border }, isMobile && { padding: 10 }]}>
                <View style={styles.headerLeft}>
                    <Ionicons name="git-network" size={isMobile ? 20 : 24} color={safeTheme.primary} />
                    <Text style={[styles.headerTitle, { color: safeTheme.text }, isMobile && { fontSize: 16 }]}>
                        AI Diagram
                    </Text>
                </View>
                <View style={styles.headerRight}>
                    <TouchableOpacity
                        style={[
                            styles.headerInsertBtn,
                            {
                                backgroundColor: generatedSvg ? safeTheme.primary : safeTheme.border,
                                opacity: generatedSvg ? 1 : 0.6,
                            },
                        ]}
                        onPress={handleInsert}
                        disabled={!generatedSvg || isGenerating}
                    >
                        <Ionicons name="add-circle" size={18} color="#fff" />
                        <Text style={styles.headerInsertBtnText}>Insert Diagram</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                        <Ionicons name="close" size={24} color={safeTheme.text} />
                    </TouchableOpacity>
                </View>
            </View>

            {/* Main content */}
            <View style={[styles.mainContent, isMobile && { flexDirection: 'column' }]}>
                {/* Left: Input Panel */}
                <ScrollView
                    style={[
                        styles.inputPanel,
                        { borderRightColor: safeTheme.border },
                        isMobile && {
                            width: '100%',
                            borderRightWidth: 0,
                            borderBottomWidth: 1,
                            borderBottomColor: safeTheme.border,
                            maxHeight: 360,
                        },
                    ]}
                    contentContainerStyle={{ padding: isMobile ? 12 : 20 }}
                >
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Describe Your Diagram</Text>

                    {/* Kind selector */}
                    <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>Diagram type</Text>
                    <View style={styles.kindRow}>
                        {DIAGRAM_KINDS.map(k => {
                            const active = diagramKind === k.id;
                            return (
                                <TouchableOpacity
                                    key={k.id}
                                    onPress={() => setDiagramKind(k.id)}
                                    style={[
                                        styles.kindPill,
                                        {
                                            backgroundColor: active ? safeTheme.primary : safeTheme.surface,
                                            borderColor: active ? safeTheme.primary : safeTheme.border,
                                        },
                                    ]}
                                >
                                    <Ionicons
                                        name={k.icon}
                                        size={16}
                                        color={active ? '#fff' : safeTheme.text}
                                    />
                                    <Text style={[
                                        styles.kindPillText,
                                        { color: active ? '#fff' : safeTheme.text },
                                    ]}>{k.label}</Text>
                                </TouchableOpacity>
                            );
                        })}
                    </View>

                    {/* Prompt */}
                    <View style={styles.inputSection}>
                        <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>
                            What should the diagram show?
                        </Text>
                        <TextInput
                            style={[styles.queryInput, {
                                backgroundColor: safeTheme.surface,
                                color: safeTheme.text,
                                borderColor: safeTheme.border,
                            }]}
                            placeholder="e.g., Steps for AI deployment lifecycle"
                            placeholderTextColor={safeTheme.textSecondary}
                            value={prompt}
                            onChangeText={setPrompt}
                            multiline
                            numberOfLines={4}
                        />
                    </View>

                    {/* Page context info */}
                    {currentPage && (
                        <View style={[styles.contextCard, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                            <Ionicons name="document-text-outline" size={16} color={safeTheme.textSecondary} />
                            <View style={styles.contextTextContainer}>
                                <Text style={[styles.contextLabel, { color: safeTheme.textSecondary }]}>Page Context:</Text>
                                <Text style={[styles.contextValue, { color: safeTheme.text }]} numberOfLines={1}>
                                    {currentPage.title || 'Untitled Page'}
                                </Text>
                            </View>
                        </View>
                    )}

                    <TouchableOpacity
                        style={[styles.generateBtn, { backgroundColor: safeTheme.primary }]}
                        onPress={generateDiagram}
                        disabled={isGenerating || !prompt.trim()}
                    >
                        {isGenerating ? (
                            <ActivityIndicator size="small" color="#fff" />
                        ) : (
                            <>
                                <Ionicons name="sparkles" size={18} color="#fff" />
                                <Text style={styles.generateBtnText}>
                                    {generatedSvg ? 'Regenerate' : 'Generate Diagram'}
                                </Text>
                            </>
                        )}
                    </TouchableOpacity>

                    {/* Quick suggestions */}
                    <View style={styles.suggestionsSection}>
                        <Text style={[styles.suggestionsTitle, { color: safeTheme.textSecondary }]}>Quick Ideas:</Text>
                        {[
                            'Process flow for onboarding new users',
                            'Stat cards comparing Q1 vs Q2 revenue',
                            'Reporting hierarchy of the engineering team',
                            'Lifecycle stages of a software release',
                        ].map((s, idx) => (
                            <TouchableOpacity
                                key={idx}
                                style={[styles.suggestionChip, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}
                                onPress={() => setPrompt(s)}
                            >
                                <Text style={[styles.suggestionText, { color: safeTheme.text }]}>{s}</Text>
                            </TouchableOpacity>
                        ))}
                    </View>
                </ScrollView>

                {/* Right: Preview Panel */}
                <View style={[styles.previewPanel, isMobile && { padding: 12, minHeight: 280 }]}>
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Preview</Text>

                    <View style={[styles.previewContainer, { backgroundColor: '#fff', borderColor: safeTheme.border }]}>
                        {stage === 'input' && !generatedSvg && (
                            <View style={styles.previewPlaceholder}>
                                <Ionicons name="git-network-outline" size={64} color={safeTheme.textSecondary} />
                                <Text style={[styles.previewPlaceholderText, { color: safeTheme.textSecondary }]}>
                                    Your generated diagram will appear here
                                </Text>
                            </View>
                        )}

                        {stage === 'generating' && (
                            <View style={styles.previewPlaceholder}>
                                <ActivityIndicator size="large" color={safeTheme.primary} />
                                <Text style={[styles.previewPlaceholderText, { color: safeTheme.primary, marginTop: 16 }]}>
                                    Generating diagram...
                                </Text>
                            </View>
                        )}

                        {stage === 'preview' && generatedSvg && renderSvgPreview()}

                        {error && (
                            <View style={styles.errorContainer}>
                                <Ionicons name="alert-circle" size={24} color="#EF4444" />
                                <Text style={styles.errorText}>{error}</Text>
                            </View>
                        )}
                    </View>

                    {generatedSvg && (
                        <View style={styles.actionButtons}>
                            <TouchableOpacity
                                style={[styles.actionBtn, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}
                                onPress={handleRegenerate}
                                disabled={isGenerating}
                            >
                                <Ionicons name="refresh" size={18} color={safeTheme.text} />
                                <Text style={[styles.actionBtnText, { color: safeTheme.text }]}>Regenerate</Text>
                            </TouchableOpacity>
                        </View>
                    )}

                    {generatedTitle && stage === 'preview' && (
                        <View style={[styles.descriptionCard, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                            <Text style={[styles.descriptionLabel, { color: safeTheme.textSecondary }]}>Title:</Text>
                            <Text style={[styles.descriptionText, { color: safeTheme.text }]}>{generatedTitle}</Text>
                        </View>
                    )}
                </View>
            </View>
        </View>
    );

    if (Platform.OS === 'web') {
        return <View style={styles.overlay}>{content}</View>;
    }
    return (
        <Modal visible={visible} animationType="slide" transparent>
            <View style={styles.overlay}>{content}</View>
        </Modal>
    );
};

const styles = {
    overlay: {
        position: 'fixed',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 100000,
    },
    container: {
        width: '95%',
        maxWidth: 1200,
        height: '90%',
        maxHeight: 900,
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
    headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
    headerRight: { flexDirection: 'row', alignItems: 'center' },
    headerTitle: { fontSize: 20, fontWeight: '600' },
    closeBtn: { padding: 4, marginLeft: 8 },
    headerInsertBtn: {
        flexDirection: 'row', alignItems: 'center',
        paddingVertical: 8, paddingHorizontal: 16,
        borderRadius: 20, gap: 6,
    },
    headerInsertBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
    mainContent: { flex: 1, flexDirection: 'row' },
    inputPanel: { width: '40%', borderRightWidth: 1, flexDirection: 'column' },
    panelTitle: {
        fontSize: 14, fontWeight: '600', marginBottom: 16,
        textTransform: 'uppercase', letterSpacing: 0.5,
    },
    inputLabel: { fontSize: 13, marginBottom: 8 },
    kindRow: {
        flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16,
    },
    kindPill: {
        flexDirection: 'row', alignItems: 'center',
        paddingHorizontal: 12, paddingVertical: 8,
        borderRadius: 20, borderWidth: 1, gap: 6,
    },
    kindPillText: { fontSize: 13, fontWeight: '500' },
    inputSection: { marginBottom: 16 },
    queryInput: {
        padding: 12, borderRadius: 8, borderWidth: 1,
        fontSize: 14, minHeight: 100, textAlignVertical: 'top',
    },
    contextCard: {
        flexDirection: 'row', alignItems: 'center',
        padding: 10, borderRadius: 8, borderWidth: 1,
        marginBottom: 16, gap: 8,
    },
    contextTextContainer: { flex: 1 },
    contextLabel: { fontSize: 11 },
    contextValue: { fontSize: 13, fontWeight: '500' },
    generateBtn: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
        padding: 14, borderRadius: 10, gap: 8, marginBottom: 20,
    },
    generateBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
    suggestionsSection: { gap: 8 },
    suggestionsTitle: { fontSize: 12, marginBottom: 4 },
    suggestionChip: {
        paddingHorizontal: 12, paddingVertical: 8,
        borderRadius: 6, borderWidth: 1,
    },
    suggestionText: { fontSize: 12 },
    previewPanel: { flex: 1, padding: 20, flexDirection: 'column' },
    previewContainer: {
        flex: 1, borderRadius: 12, borderWidth: 1,
        justifyContent: 'center', alignItems: 'center', overflow: 'hidden',
    },
    previewPlaceholder: { alignItems: 'center', padding: 20 },
    previewPlaceholderText: { fontSize: 14, marginTop: 16, textAlign: 'center' },
    actionButtons: { flexDirection: 'row', gap: 8, marginTop: 12 },
    actionBtn: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
        paddingVertical: 10, paddingHorizontal: 16,
        borderRadius: 8, borderWidth: 1, gap: 6,
    },
    actionBtnText: { fontSize: 13, fontWeight: '500' },
    descriptionCard: {
        marginTop: 12, padding: 12, borderRadius: 8, borderWidth: 1,
    },
    descriptionLabel: { fontSize: 11, marginBottom: 4 },
    descriptionText: { fontSize: 13 },
    errorContainer: {
        flexDirection: 'row', alignItems: 'center', padding: 16, gap: 8,
    },
    errorText: { color: '#EF4444', fontSize: 13, flex: 1 },
};

export default AIDiagramModal;
