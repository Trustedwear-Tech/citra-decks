// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    Dimensions,
    Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { WebView } from 'react-native-webview';

const { width, height } = Dimensions.get('window');

const VideoPlayerModal = ({
    visible,
    onClose,
    videoData, // { src, videoType, videoId, thumbnail }
    theme
}) => {
    if (!videoData) return null;

    const renderPlayer = () => {
        if (videoData.videoType === 'youtube') {
            // Use YouTube Embed
            const videoId = videoData.videoId || getYoutubeId(videoData.src);
            return (
                <iframe
                    width="100%"
                    height="100%"
                    src={`https://www.youtube.com/embed/${videoId}?autoplay=1`}
                    title="YouTube video player"
                    frameBorder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowFullScreen
                />
            );
        } else if (videoData.videoType === 'vimeo') {
            const videoId = videoData.videoId || getVimeoId(videoData.src);
            return (
                <iframe
                    src={`https://player.vimeo.com/video/${videoId}?autoplay=1`}
                    width="100%"
                    height="100%"
                    frameBorder="0"
                    allow="autoplay; fullscreen; picture-in-picture"
                    allowFullScreen
                />
            );
        } else {
            // Local Video
            return (
                <video
                    src={videoData.src}
                    controls
                    autoPlay
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
            );
        }
    };

    return (
        <Modal
            visible={visible}
            transparent={true}
            animationType="fade"
            onRequestClose={onClose}
        >
            <View style={styles.container}>
                <TouchableOpacity style={styles.backdrop} onPress={onClose} />

                <View style={styles.playerContainer}>
                    {/* Header */}
                    <View style={styles.header}>
                        <Text style={styles.title}>Video Preview</Text>
                        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                            <Ionicons name="close" size={24} color="#fff" />
                        </TouchableOpacity>
                    </View>

                    {/* Video Content */}
                    <View style={styles.videoWrapper}>
                        {Platform.OS === 'web' ? renderPlayer() : (
                            <Text style={{ color: '#fff' }}>Native video playback not implemented in this preview</Text>
                        )}
                    </View>
                </View>
            </View>
        </Modal>
    );
};

// Helper for extracting ID if missing (fallback)
const getYoutubeId = (url) => {
    if (!url) return '';
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
};
const getVimeoId = (url) => {
    if (!url) return '';
    const regExp = /vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/(?:[^\/]*)\/videos\/|album\/(?:\d+)\/video\/|video\/|)(\d+)(?:$|\/|\?)/;
    const match = url.match(regExp);
    return match ? match[1] : null;
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.85)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 9999
    },
    backdrop: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0
    },
    playerContainer: {
        width: '90%',
        maxWidth: 1000,
        aspectRatio: 16 / 9,
        backgroundColor: '#000',
        borderRadius: 8,
        overflow: 'hidden',
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.5,
        shadowRadius: 20,
        elevation: 20,
    },
    header: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: 60,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        zIndex: 10,
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.7), transparent)' // Web only, but okay
    },
    title: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
        textShadowColor: 'rgba(0,0,0,0.5)',
        textShadowOffset: { width: 1, height: 1 },
        textShadowRadius: 2
    },
    closeBtn: {
        padding: 8,
        backgroundColor: 'rgba(0,0,0,0.5)',
        borderRadius: 20
    },
    videoWrapper: {
        flex: 1,
        backgroundColor: '#000'
    }
});

export default VideoPlayerModal;
