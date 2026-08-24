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
    Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { fetchEmbedMetadata } from './utils/embedMetadataService';
import VideoRecorderModal from './VideoRecorderModal';

/**
 * Modal to select video source (Local, YouTube, Vimeo)
 */
const VideoSourceModal = ({
    visible,
    onClose,
    onSelectVideo, // (data) => void. data: { src, videoType, thumbnail? }
    theme
}) => {
    const [mode, setMode] = useState('menu'); // 'menu' | 'youtube' | 'vimeo' | 'loom' | 'spotify'
    const [url, setUrl] = useState('');
    const [error, setError] = useState('');
    const [isValidating, setIsValidating] = useState(false);
    const [showRecorder, setShowRecorder] = useState(false);

    const resetState = () => {
        setMode('menu');
        setUrl('');
        setError('');
        setIsValidating(false);
        setShowRecorder(false);
    };

    const handleClose = () => {
        resetState();
        onClose();
    };

    // Extract YouTube ID
    const getYoutubeId = (url) => {
        const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    };

    // Extract Vimeo ID
    const getVimeoId = (url) => {
        const regExp = /vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/(?:[^\/]*)\/videos\/|album\/(?:\d+)\/video\/|video\/|)(\d+)(?:$|\/|\?)/;
        const match = url.match(regExp);
        return match ? match[1] : null;
    };

    const handleUrlSubmit = async () => {
        if (!url.trim()) return;
        setError('');
        setIsValidating(true);

        try {
            // Use the centralized embed metadata service (NoEmbed -> Iframely cascade)
            const metadata = await fetchEmbedMetadata(url);

            if (!metadata || metadata.type === 'link') {
                throw new Error('Could not fetch video metadata. Please check the URL.');
            }

            onSelectVideo({
                src: url,
                videoType: metadata.videoType,
                videoId: metadata.videoId,
                thumbnail: metadata.thumbnail_url,
                title: metadata.title,
                aspectRatio: metadata.width && metadata.height ? metadata.width / metadata.height : 1.77
            });
            handleClose();
        } catch (err) {
            console.error('Video validation error:', err);
            setError(err.message || 'Failed to validate URL');
        } finally {
            setIsValidating(false);
        }
    };

    const handleLocalUpload = () => {
        // Notify parent to trigger local file picker
        // Close modal first, then let parent open file picker after a short delay
        // This prevents the modal overlay from blocking the file input click
        resetState();
        onClose();
        // Parent will handle opening the file picker via onSelectVideo callback
        setTimeout(() => {
            onSelectVideo({ videoType: 'local' });
        }, 100);
    };

    const OptionButton = ({ icon, label, color, onPress }) => (
        <TouchableOpacity
            style={[styles.optionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
            onPress={onPress}
        >
            <View style={[styles.iconContainer, { backgroundColor: color + '20' }]}>
                <Ionicons name={icon} size={24} color={color} />
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
                            {mode === 'menu' ? 'Insert Media' : `Add ${mode.charAt(0).toUpperCase() + mode.slice(1)} URL`}
                        </Text>
                        <View style={{ width: 20 }} />
                    </View>

                    <View style={styles.content}>
                        {mode === 'menu' ? (
                            <View style={styles.menuContainer}>
                                <OptionButton
                                    icon="folder-open"
                                    label="Upload from Computer"
                                    color="#3B82F6"
                                    onPress={handleLocalUpload}
                                />
                                {Platform.OS === 'web' && (
                                    <OptionButton
                                        icon="radio-button-on"
                                        label="Record Video"
                                        color="#DC2626"
                                        onPress={() => setShowRecorder(true)}
                                    />
                                )}
                                <OptionButton
                                    icon="logo-youtube"
                                    label="YouTube URL"
                                    color="#EF4444"
                                    onPress={() => setMode('youtube')}
                                />
                                <OptionButton
                                    icon="logo-vimeo"
                                    label="Vimeo URL"
                                    color="#1AB7EA"
                                    onPress={() => setMode('vimeo')}
                                />
                                <OptionButton
                                    icon="videocam"
                                    label="Loom URL"
                                    color="#625DF5"
                                    onPress={() => setMode('loom')}
                                />
                                <OptionButton
                                    icon="musical-notes"
                                    label="Spotify URL"
                                    color="#1DB954"
                                    onPress={() => setMode('spotify')}
                                />
                            </View>
                        ) : (
                            <View style={styles.inputContainer}>
                                <Text style={[styles.inputLabel, { color: theme.text }]}>
                                    Paste video URL
                                </Text>
                                <TextInput
                                    style={[styles.input, {
                                        backgroundColor: theme.background,
                                        color: theme.text,
                                        borderColor: error ? '#EF4444' : theme.border
                                    }]}
                                    placeholder={`https://www.${mode}.com/...`}
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
                                        <Text style={styles.submitBtnText}>Add Video</Text>
                                    )}
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                </View>
            </View>

            {/* Video Recorder Modal */}
            <VideoRecorderModal
                visible={showRecorder}
                onClose={() => setShowRecorder(false)}
                onSave={(videoDataUrl) => {
                    // Return recorded video with 'recorded' type
                    onSelectVideo({
                        src: videoDataUrl,
                        videoType: 'recorded',
                        title: `Recording ${new Date().toLocaleString()}`
                    });
                    handleClose();
                }}
                theme={theme}
            />
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
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 3.84,
        elevation: 5,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
    },
    title: {
        fontSize: 16,
        fontWeight: '600',
    },
    content: {
        padding: 20,
    },
    menuContainer: {
        gap: 12,
    },
    optionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
    },
    iconContainer: {
        width: 40,
        height: 40,
        borderRadius: 20,
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: 12,
    },
    optionLabel: {
        fontSize: 16,
        fontWeight: '500',
    },
    inputContainer: {
        gap: 12,
    },
    inputLabel: {
        fontSize: 14,
        fontWeight: '500',
    },
    input: {
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        fontSize: 16,
    },
    errorText: {
        color: '#EF4444',
        fontSize: 12,
    },
    submitBtn: {
        padding: 14,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 8,
    },
    submitBtnText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
    },
});

export default VideoSourceModal;
