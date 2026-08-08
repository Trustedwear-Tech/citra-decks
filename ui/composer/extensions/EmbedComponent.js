/**
 * EmbedComponent.js - React component for rendering embedded content in TipTap
 * 
 * Features:
 * - Responsive iframe wrapper (16:9 aspect ratio)
 * - Provider badge overlay
 * - Delete button on hover/selection
 * - Handles different embed types (iframe, video tag)
 */

import React, { useMemo } from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons, Ionicons } from '@expo/vector-icons';

// Provider icon mapping
const PROVIDER_ICONS = {
    youtube: { icon: 'logo-youtube', library: 'Ionicons', color: '#FF0000' },
    vimeo: { icon: 'logo-vimeo', library: 'Ionicons', color: '#1AB7EA' },
    loom: { icon: 'videocam', library: 'Ionicons', color: '#625DF5' },
    spotify: { icon: 'musical-notes', library: 'Ionicons', color: '#1DB954' },
    figma: { icon: 'brush-outline', library: 'Ionicons', color: '#F24E1E' },
    google: { icon: 'logo-google', library: 'Ionicons', color: '#4285F4' },
    miro: { icon: 'grid-outline', library: 'Ionicons', color: '#FFD02F' },
    airtable: { icon: 'server-outline', library: 'Ionicons', color: '#18BFFF' },
    powerbi: { icon: 'bar-chart-outline', library: 'Ionicons', color: '#F2C811' },
    calendly: { icon: 'calendar-outline', library: 'Ionicons', color: '#006BFF' },
    typeform: { icon: 'document-text-outline', library: 'Ionicons', color: '#262627' },
    googleform: { icon: 'document-outline', library: 'Ionicons', color: '#673AB7' },
    tally: { icon: 'checkbox-outline', library: 'Ionicons', color: '#1E1E1E' },
    recorded: { icon: 'radio-button-on', library: 'Ionicons', color: '#FF4444' },
    'local-video': { icon: 'folder-open', library: 'Ionicons', color: '#666666' },
    webpage: { icon: 'globe-outline', library: 'Ionicons', color: '#666666' },
};

// Generate embed URL based on type
const getEmbedUrl = (attrs) => {
    const { embedType, videoId, src } = attrs;

    switch (embedType) {
        case 'youtube':
            return `https://www.youtube.com/embed/${videoId}`;
        case 'vimeo':
            return `https://player.vimeo.com/video/${videoId}`;
        case 'loom':
            return `https://www.loom.com/embed/${videoId}`;
        case 'spotify': {
            // Extract type and ID from Spotify URL
            const spotifyMatch = src?.match(/spotify\.com\/(track|album|playlist|episode)\/([a-zA-Z0-9]+)/);
            if (spotifyMatch) {
                return `https://open.spotify.com/embed/${spotifyMatch[1]}/${spotifyMatch[2]}`;
            }
            return src;
        }
        case 'figma':
            return `https://www.figma.com/embed?embed_host=share&url=${encodeURIComponent(src)}`;
        case 'miro':
        case 'miro.com': {
            // If it's already a live-embed URL, use it directly
            if (src?.includes('/live-embed/')) {
                return src;
            }
            // Preserve share_link_id from original URL
            let miroExtraParams = '';
            try {
                const parsedSrc = new URL(src);
                const shareId = parsedSrc.searchParams.get('share_link_id');
                if (shareId) miroExtraParams = `&share_link_id=${shareId}`;
            } catch (e) { /* ignore */ }
            // Extract board ID and convert to live-embed format
            const boardMatch = src?.match(/miro\.com\/(?:app\/)?(?:board|embed)\/([^\/\?#]+)/);
            if (boardMatch) {
                return `https://miro.com/app/live-embed/${boardMatch[1]}/?embedMode=view_only_without_ui&autoplay=yep${miroExtraParams}`;
            }
            // Fallback: simple embed conversion
            if (src?.includes('/board/')) {
                return src.replace('/board/', '/app/live-embed/') + `?embedMode=view_only_without_ui&autoplay=yep${miroExtraParams}`;
            }
            return src;
        }
        default:
            return src;
    }
};

// Check if this is a video type that uses <video> tag
const isVideoTag = (embedType) => {
    return embedType === 'recorded' || embedType === 'local-video';
};

const EmbedComponent = (props) => {
    const { node, deleteNode, selected } = props;
    const attrs = node.attrs;
    const { embedType, provider, title, src, thumbnail } = attrs;

    // Get provider icon info
    const providerInfo = PROVIDER_ICONS[embedType] || PROVIDER_ICONS.webpage;

    // Calculate embed URL
    const embedUrl = useMemo(() => getEmbedUrl(attrs), [attrs]);

    // Determine if this needs a video tag or iframe
    const useVideoTag = isVideoTag(embedType);

    // Special height for Spotify (compact player)
    const isSpotify = embedType === 'spotify';
    const aspectRatio = isSpotify ? '0' : '56.25%'; // 16:9 for videos, fixed height for Spotify
    const spotifyHeight = 152;

    return (
        <NodeViewWrapper className="embed-node-wrapper">
            <div
                className={`tiptap-embed ${selected ? 'selected' : ''}`}
                style={{
                    position: 'relative',
                    margin: '16px 0',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    border: selected ? '2px solid #2196F3' : '1px solid #e0e0e0',
                    backgroundColor: '#000',
                }}
            >
                {/* Provider Badge */}
                <div
                    style={{
                        position: 'absolute',
                        top: 8,
                        left: 8,
                        zIndex: 10,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        padding: '4px 10px',
                        borderRadius: 20,
                        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                    }}
                >
                    <Ionicons
                        name={providerInfo.icon}
                        size={14}
                        color={providerInfo.color}
                    />
                    <span style={{
                        fontSize: 11,
                        fontWeight: '600',
                        color: '#333',
                        maxWidth: 150,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                    }}>
                        {provider || embedType}
                    </span>
                </div>

                {/* Delete Button */}
                <button
                    onClick={deleteNode}
                    className="embed-delete-btn"
                    style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        zIndex: 10,
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                        opacity: selected ? 1 : 0,
                        transition: 'opacity 0.2s ease',
                    }}
                    title="Remove embed"
                >
                    <MaterialIcons name="close" size={18} color="#666" />
                </button>

                {/* Embed Content */}
                {useVideoTag ? (
                    // Video tag for local/recorded videos
                    <video
                        controls
                        src={src}
                        style={{
                            width: '100%',
                            maxHeight: 480,
                            backgroundColor: '#000',
                        }}
                        poster={thumbnail}
                    >
                        Your browser does not support the video tag.
                    </video>
                ) : isSpotify ? (
                    // Spotify uses fixed height
                    <iframe
                        src={embedUrl}
                        style={{
                            width: '100%',
                            height: spotifyHeight,
                            border: 'none',
                        }}
                        allow="encrypted-media"
                        loading="lazy"
                    />
                ) : (
                    // Standard 16:9 iframe wrapper
                    <div
                        style={{
                            position: 'relative',
                            paddingBottom: aspectRatio,
                            height: 0,
                            overflow: 'hidden',
                        }}
                    >
                        <iframe
                            src={embedUrl}
                            style={{
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                width: '100%',
                                height: '100%',
                                border: 'none',
                            }}
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                            allowFullScreen
                            loading="lazy"
                        />
                    </div>
                )}

                {/* Title overlay (shown on hover) */}
                {title && (
                    <div
                        className="embed-title-overlay"
                        style={{
                            position: 'absolute',
                            bottom: 0,
                            left: 0,
                            right: 0,
                            padding: '24px 12px 8px 12px',
                            background: 'linear-gradient(transparent, rgba(0,0,0,0.7))',
                            color: '#fff',
                            fontSize: 12,
                            fontWeight: '500',
                            opacity: 0,
                            transition: 'opacity 0.2s ease',
                            pointerEvents: 'none',
                        }}
                    >
                        {title}
                    </div>
                )}
            </div>

            {/* Hover styles injected via style tag */}
            <style>{`
                .tiptap-embed:hover .embed-delete-btn {
                    opacity: 1 !important;
                }
                .tiptap-embed:hover .embed-title-overlay {
                    opacity: 1 !important;
                }
            `}</style>
        </NodeViewWrapper>
    );
};

export default EmbedComponent;
