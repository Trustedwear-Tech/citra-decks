// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useEffect, useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Text, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const InlineVideoOverlay = ({
    videoData, // { src, videoType, videoId, layout: { x, y, width, height, angle } }
    onClose,
    isEditable = true
}) => {
    if (!videoData) return null;

    const { layout } = videoData;

    // Extract ID helpers
    const getYoutubeId = (url) => {
        const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    };
    const getVimeoId = (url) => {
        const regExp = /vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/(?:[^\/]*)\/videos\/|album\/(?:\d+)\/video\/|video\/|)(\d+)(?:$|\/|\?)/;
        const match = url.match(regExp);
        return match ? match[1] : null;
    };

    const getLoomId = (url) => {
        const regExp = /loom\.com\/(?:share|embed)\/([a-zA-Z0-9]+)/;
        const match = url.match(regExp);
        return match ? match[1] : null;
    };

    const getSpotifyInfo = (url) => {
        const match = url.match(/spotify\.com\/(track|album|playlist|episode)\/([a-zA-Z0-9]+)/);
        return match ? { type: match[1], id: match[2] } : null;
    };

    const renderPlayer = () => {
        // Debug logging to trace embed data
        console.log('🎬 [OVERLAY] renderPlayer called with:', {
            embedType: videoData.embedType,
            videoType: videoData.videoType,
            src: videoData.src,
            html: videoData.html ? videoData.html.substring(0, 100) + '...' : null
        });

        if (videoData.videoType === 'youtube') {
            const videoId = videoData.videoId || getYoutubeId(videoData.src);
            return (
                <iframe
                    width="100%"
                    height="100%"
                    src={`https://www.youtube.com/embed/${videoId}?autoplay=1&mute=0&loop=1&playlist=${videoId}&controls=1`}
                    title="YouTube video player"
                    frameBorder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowFullScreen
                    style={{ pointerEvents: 'auto' }}
                />
            );
        } else if (videoData.videoType === 'vimeo') {
            const videoId = videoData.videoId || getVimeoId(videoData.src);
            return (
                <iframe
                    src={`https://player.vimeo.com/video/${videoId}?autoplay=1&loop=1&autopause=0`}
                    width="100%"
                    height="100%"
                    frameBorder="0"
                    allow="autoplay; fullscreen; picture-in-picture"
                    allowFullScreen
                    style={{ pointerEvents: 'auto' }}
                />
            );
        } else if (videoData.videoType === 'loom') {
            const videoId = videoData.videoId || getLoomId(videoData.src);
            return (
                <iframe
                    src={`https://www.loom.com/embed/${videoId}?autoplay=1`}
                    width="100%"
                    height="100%"
                    frameBorder="0"
                    allow="autoplay; fullscreen; picture-in-picture"
                    allowFullScreen
                    style={{ pointerEvents: 'auto' }}
                />
            );
        } else if (videoData.videoType === 'spotify') {
            const info = getSpotifyInfo(videoData.src);
            const spotifyType = info?.type || 'track';
            const spotifyId = info?.id || videoData.videoId;
            return (
                <iframe
                    src={`https://open.spotify.com/embed/${spotifyType}/${spotifyId}?theme=0`}
                    width="100%"
                    height="100%"
                    frameBorder="0"
                    allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                    allowFullScreen
                    style={{ pointerEvents: 'auto', borderRadius: 12 }}
                />
            );
        } else if (videoData.embedType) {
            // Handle embeds (Figma, Miro, Google Docs, etc.)
            // For Miro: construct fresh embed URL to ensure share_link_id is preserved and autoplay is set
            const isMiro = videoData.embedType === 'miro' || videoData.embedType === 'miro.com';
            if (isMiro) {
                let miroEmbedUrl = videoData.src;
                const miroMatch = videoData.src?.match(/miro\.com\/(?:app\/)?(?:board|embed|live-embed)\/([^\/\?#]+)/);
                if (miroMatch && !videoData.src?.includes('/live-embed/')) {
                    let miroShareParam = '';
                    try {
                        const parsed = new URL(videoData.src);
                        const shareId = parsed.searchParams.get('share_link_id');
                        if (shareId) miroShareParam = `&share_link_id=${shareId}`;
                    } catch (e) { /* ignore */ }
                    miroEmbedUrl = `https://miro.com/app/live-embed/${miroMatch[1]}/?embedMode=view_only_without_ui&autoplay=yep${miroShareParam}`;
                }
                return (
                    <iframe
                        src={miroEmbedUrl}
                        width="100%"
                        height="100%"
                        frameBorder="0"
                        allow="autoplay; fullscreen; clipboard-read; clipboard-write"
                        allowFullScreen
                        style={{ pointerEvents: 'auto', border: 'none' }}
                    />
                );
            }
            // Use provided HTML or construct iframe from src
            if (videoData.html) {
                // Inject autoplay and fullscreen into existing HTML
                return (
                    <div
                        style={{ width: '100%', height: '100%', pointerEvents: 'auto' }}
                        dangerouslySetInnerHTML={{ __html: videoData.html.replace('<iframe', '<iframe style="width:100%;height:100%;border:none;"') }}
                    />
                );
            }
            // Fallback: construct iframe from src
            return (
                <iframe
                    src={videoData.src}
                    width="100%"
                    height="100%"
                    frameBorder="0"
                    allow="autoplay; fullscreen"
                    allowFullScreen
                    style={{ pointerEvents: 'auto' }}
                />
            );
        } else {
            // Local Video or recorded video (base64 data URL)
            return (
                <video
                    src={videoData.src}
                    controls
                    autoPlay
                    loop
                    style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'auto' }}
                />
            );
        }
    };

    return (
        <View
            style={[
                styles.container,
                {
                    left: layout.x,
                    top: layout.y,
                    width: layout.width,
                    height: layout.height,
                    transform: [{ rotate: `${layout.angle}deg` }]
                }
            ]}
        >
            {/* Close Button (Top-Right of video) */}
            {isEditable && (
                <TouchableOpacity
                    style={styles.closeBtn}
                    onPress={onClose}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                    <Ionicons name="close-circle" size={24} color="#fff" />
                </TouchableOpacity>
            )}

            {/* Player Content */}
            <View style={styles.content}>
                {Platform.OS === 'web' ? renderPlayer() : <Text style={{ color: '#fff' }}>Native playback not supported in overlay</Text>}
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        position: 'absolute',
        backgroundColor: '#f5f5f5',
        overflow: 'visible', // Allow close button to be visible if slightly outside
        zIndex: 9999, // Ensure it's on top of canvas
        elevation: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 5,
        borderRadius: 8,
    },
    content: {
        width: '100%',
        height: '100%',
    },
    closeBtn: {
        position: 'absolute',
        top: -12,
        right: -12,
        backgroundColor: '#000',
        borderRadius: 12,
        zIndex: 10000,
        elevation: 11,
    }
});

export default InlineVideoOverlay;
