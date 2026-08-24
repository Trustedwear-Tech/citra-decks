// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import React, { useState } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    TextInput,
    Image,
    ActivityIndicator,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { fetchEmbedMetadata } from './utils/embedMetadataService';

/**
 * Modal to embed apps and webpages (Figma, Google Drive, Miro, Airtable, PowerBI, etc.)
 */
const EmbedSourceModal = ({
    visible,
    onClose,
    onSelectEmbed, // (data) => void
    theme
}) => {
    const [mode, setMode] = useState('menu'); // 'menu' | 'url'
    const [selectedType, setSelectedType] = useState(null); // 'figma' | 'google' | 'miro' | etc.
    const [url, setUrl] = useState('');
    const [error, setError] = useState('');
    const [isValidating, setIsValidating] = useState(false);
    const [preview, setPreview] = useState(null);

    const resetState = () => {
        setMode('menu');
        setSelectedType(null);
        setUrl('');
        setError('');
        setIsValidating(false);
        setPreview(null);
    };

    const handleClose = () => {
        resetState();
        onClose();
    };

    const handleSelectType = (type) => {
        setSelectedType(type);
        setMode('url');
    };

    const handleUrlSubmit = async () => {
        if (!url.trim()) return;
        setError('');
        setIsValidating(true);

        console.log('🚀 [EMBED_MODAL] Starting embed submission');
        console.log('📝 [EMBED_MODAL] Raw input:', url.substring(0, 200));

        try {
            // Extract URL from iframe HTML if pasted
            let urlToProcess = url.trim();
            if (urlToProcess.startsWith('<iframe')) {
                console.log('🎬 [EMBED_MODAL] Detected iframe HTML');
                const srcMatch = urlToProcess.match(/<iframe[^>]+src=["']([^"']+)["']/i);
                if (srcMatch) {
                    urlToProcess = srcMatch[1];
                    console.log('✅ [EMBED_MODAL] Extracted URL from iframe:', urlToProcess);
                } else {
                    console.error('❌ [EMBED_MODAL] Failed to extract src from iframe HTML');
                    throw new Error('Could not extract URL from iframe code. Please paste just the URL.');
                }
            } else {
                console.log('🔗 [EMBED_MODAL] Processing as direct URL');
            }
            
            console.log('🔍 [EMBED_MODAL] Fetching metadata for:', urlToProcess);
            const metadata = await fetchEmbedMetadata(urlToProcess);
            console.log('📦 [EMBED_MODAL] Received metadata:', metadata);

            if (!metadata) {
                console.error('❌ [EMBED_MODAL] No metadata returned');
                throw new Error('Could not fetch embed metadata.');
            }

            const embedData = {
                src: urlToProcess,
                embedType: metadata.videoType || selectedType,
                provider: metadata.provider,
                thumbnail: metadata.thumbnail_url,
                title: metadata.title,
                html: metadata.html,
                width: metadata.width || 640,
                height: metadata.height || 480
            };
            console.log('✅ [EMBED_MODAL] Calling onSelectEmbed with:', embedData);
            onSelectEmbed(embedData);
            handleClose();
        } catch (err) {
            console.error('❌ [EMBED_MODAL] Error:', err);
            console.error('❌ [EMBED_MODAL] Error stack:', err.stack);
            setError(err.message || 'Failed to validate URL');
        } finally {
            setIsValidating(false);
        }
    };

    const EMBED_TYPES = [
        { id: 'webpage', label: 'Webpage or App', icon: 'globe-outline', color: '#3B82F6' },
        { id: 'figma', label: 'Figma', icon: 'brush-outline', color: '#F24E1E' },
        { id: 'google', label: 'Google Drive', icon: 'logo-google', color: '#4285F4' },
        { id: 'miro', label: 'Miro Board', icon: 'grid-outline', color: '#FFD02F' },
        { id: 'airtable', label: 'Airtable', icon: 'server-outline', color: '#18BFFF' },
        { id: 'powerbi', label: 'PowerBI', icon: 'bar-chart-outline', color: '#F2C811' },
    ];

    const getPlaceholder = () => {
        switch (selectedType) {
            case 'figma': return 'https://www.figma.com/file/...';
            case 'google': return 'https://docs.google.com/...';
            case 'miro': return 'https://miro.com/app/board/...';
            case 'airtable': return 'https://airtable.com/...';
            case 'powerbi': return 'https://app.powerbi.com/...';
            default: return 'https://...';
        }
    };

    const OptionButton = ({ icon, label, color, onPress, iconPack = 'ionicons' }) => (
        <TouchableOpacity
            style={[styles.optionBtn, { borderColor: theme.border }]}
            onPress={onPress}
        >
            <View style={[styles.iconContainer, { backgroundColor: color + '20' }]}>
                {iconPack === 'ionicons' ? (
                    <Ionicons name={icon} size={24} color={color} />
                ) : (
                    <MaterialCommunityIcons name={icon} size={24} color={color} />
                )}
            </View>
            <Text style={[styles.optionLabel, { color: theme.text }]}>{label}</Text>
            <Ionicons name="chevron-forward" size={16} color={theme.textSecondary} style={{ marginLeft: 'auto' }} />
        </TouchableOpacity>
    );

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={handleClose}
        >
            <View style={styles.overlay}>
                <TouchableOpacity style={styles.backdrop} onPress={handleClose} />

                <View style={[styles.modal, { backgroundColor: theme.surface }]}>
                    <View style={[styles.header, { borderBottomColor: theme.border }]}>
                        <TouchableOpacity onPress={mode === 'menu' ? handleClose : () => setMode('menu')}>
                            <Ionicons name={mode === 'menu' ? "close" : "arrow-back"} size={20} color={theme.text} />
                        </TouchableOpacity>
                        <Text style={[styles.title, { color: theme.text }]}>
                            {mode === 'menu' ? 'Embed Apps & Webpages' : `Embed ${selectedType?.charAt(0).toUpperCase() + selectedType?.slice(1)}`}
                        </Text>
                        <View style={{ width: 20 }} />
                    </View>

                    <View style={styles.content}>
                        {mode === 'menu' ? (
                            <View style={styles.menuContainer}>
                                {EMBED_TYPES.map((type) => (
                                    <OptionButton
                                        key={type.id}
                                        icon={type.icon}
                                        label={type.label}
                                        color={type.color}
                                        onPress={() => handleSelectType(type.id)}
                                    />
                                ))}
                            </View>
                        ) : (
                            <View style={styles.inputContainer}>
                                <Text style={[styles.inputLabel, { color: theme.text }]}>
                                    Paste URL or iframe code
                                </Text>
                                <Text style={[styles.inputHint, { color: theme.textSecondary }]}>
                                    You can paste either the URL or the full &lt;iframe&gt; embed code
                                </Text>
                                <TextInput
                                    style={[styles.input, {
                                        backgroundColor: theme.background,
                                        color: theme.text,
                                        borderColor: error ? '#EF4444' : theme.border
                                    }]}
                                    placeholder={getPlaceholder()}
                                    placeholderTextColor={theme.textSecondary}
                                    value={url}
                                    onChangeText={setUrl}
                                    autoFocus
                                    autoCapitalize="none"
                                />
                                {error ? (
                                    <Text style={styles.errorText}>{error}</Text>
                                ) : null}

                                <TouchableOpacity
                                    style={[styles.submitBtn, { backgroundColor: theme.primary, opacity: !url.trim() || isValidating ? 0.6 : 1 }]}
                                    onPress={handleUrlSubmit}
                                    disabled={!url.trim() || isValidating}
                                >
                                    {isValidating ? (
                                        <ActivityIndicator size="small" color="#fff" />
                                    ) : (
                                        <Text style={styles.submitBtnText}>Add Embed</Text>
                                    )}
                                </TouchableOpacity>
                            </View>
                        )}
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
        padding: 20,
    },
    backdrop: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
    },
    modal: {
        width: '100%',
        maxWidth: 400,
        borderRadius: 12,
        overflow: 'hidden',
        elevation: 5,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.2,
        shadowRadius: 10,
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 16,
        borderBottomWidth: 1,
    },
    title: {
        fontSize: 16,
        fontWeight: '600',
    },
    content: {
        padding: 16,
    },
    menuContainer: {
        gap: 8,
    },
    optionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        gap: 12,
    },
    iconContainer: {
        width: 40,
        height: 40,
        borderRadius: 8,
        justifyContent: 'center',
        alignItems: 'center',
    },
    optionLabel: {
        fontSize: 14,
        fontWeight: '500',
    },
    inputContainer: {
        gap: 12,
    },
    inputLabel: {
        fontSize: 14,
        fontWeight: '500',
    },
    inputHint: {
        fontSize: 12,
        fontStyle: 'italic',
        marginBottom: 4,
    },
    input: {
        height: 48,
        borderWidth: 1,
        borderRadius: 8,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    errorText: {
        color: '#EF4444',
        fontSize: 12,
    },
    submitBtn: {
        height: 44,
        borderRadius: 8,
        justifyContent: 'center',
        alignItems: 'center',
    },
    submitBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
});

export default EmbedSourceModal;
