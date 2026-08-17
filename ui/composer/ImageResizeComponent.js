// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { View, StyleSheet, Platform } from 'react-native';
import globalImageCache from '../../utils/globalImageCache';

const ImageResizeComponent = (props) => {
    const { node, updateAttributes, selected, editor } = props;
    const [width, setWidth] = useState(node.attrs.width || '100%');
    const [isResizing, setIsResizing] = useState(false);
    const [imageSrc, setImageSrc] = useState(node.attrs.src); // Display source (Blob or Original)
    const [isHovered, setIsHovered] = useState(false);
    const [imageStatus, setImageStatus] = useState('loading'); // 'loading' | 'loaded' | 'error'
    const [retryCount, setRetryCount] = useState(0);
    const resizeRef = useRef(null);
    const MAX_RETRIES = 2;

    // Detect if this is a chart image
    const chartConfigRaw = node.attrs['data-chart-config'];
    const isChart = !!chartConfigRaw;

    const handleChartEdit = useCallback(() => {
        if (!chartConfigRaw || !editor) return;
        try {
            const chartConfig = JSON.parse(decodeURIComponent(chartConfigRaw));
            const onChartEdit = editor.storage?.image?.onChartEdit;
            if (onChartEdit) {
                // Find the position of this node in the document
                const pos = props.getPos?.();
                onChartEdit(chartConfig, pos);
            }
        } catch (e) {
            console.warn('Failed to parse chart config:', e);
        }
    }, [chartConfigRaw, editor, props]);

    // Sync with node attributes
    useEffect(() => {
        setWidth(node.attrs.width || '100%');
    }, [node.attrs.width]);

    // Blob Caching Logic - uses global shared cache
    useEffect(() => {
        const originalSrc = node.attrs.src;
        if (!originalSrc) {
            setImageStatus('error');
            return;
        }

        // If already a data URI or blob, use as is
        if (originalSrc.startsWith('data:') || originalSrc.startsWith('blob:')) {
            setImageSrc(originalSrc);
            return;
        }

        // Check global shared cache first (synchronous)
        const cached = globalImageCache.get(originalSrc);
        if (cached) {
            setImageSrc(cached);
            return;
        }

        // Fetch via global cache (deduplicates in-flight requests)
        let isMounted = true;
        setImageStatus('loading');

        globalImageCache.fetchAndCache(originalSrc)
            .then(blobUrl => {
                if (isMounted) setImageSrc(blobUrl || originalSrc);
            })
            .catch(err => {
                console.warn('Failed to cache image in Report, falling back:', err);
                if (isMounted) setImageSrc(originalSrc);
            });

        return () => {
            isMounted = false;
        };
    }, [node.attrs.src, retryCount]);

    // Handle image load error - retry via globalImageCache (re-triggers the 3-tier fallback)
    const handleImageError = useCallback(() => {
        console.warn(`⚠️ [ImageResize] Image failed to load (attempt ${retryCount + 1}):`, imageSrc?.substring(0, 80));
        
        if (retryCount < MAX_RETRIES) {
            const originalSrc = node.attrs.src;
            if (originalSrc && !originalSrc.startsWith('data:') && !originalSrc.startsWith('blob:')) {
                setRetryCount(prev => prev + 1);
                // Clear the cached entry so fetchAndCache retries with full fallback chain
                // (direct fetch → Image element → backend proxy)
                globalImageCache.evict(originalSrc);
                // The retryCount change triggers the useEffect which calls fetchAndCache again
            } else {
                setImageStatus('error');
            }
        } else {
            setImageStatus('error');
        }
    }, [retryCount, imageSrc, node.attrs.src]);

    const handleImageLoad = useCallback(() => {
        setImageStatus('loaded');
    }, []);

    const handleMouseDown = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();

        setIsResizing(true);

        const startX = e.clientX;
        const startWidth = resizeRef.current ? resizeRef.current.offsetWidth : 0;

        const onMouseMove = (moveEvent) => {
            if (startWidth) {
                const currentX = moveEvent.clientX;
                const diffX = currentX - startX;
                const newWidth = Math.max(100, startWidth + diffX); // Min width 100px
                setWidth(`${newWidth}px`);
            }
        };

        const onMouseUp = (upEvent) => {
            setIsResizing(false);

            // Calculate final width to save
            if (startWidth) {
                const currentX = upEvent.clientX;
                const diffX = currentX - startX;
                const newWidth = Math.max(100, startWidth + diffX);
                updateAttributes({ width: `${newWidth}px` });
            }

            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }, [updateAttributes]);

    return (
        <NodeViewWrapper as="div" style={styles.wrapper}>
            <div
                ref={resizeRef}
                className={`image-resizer ${selected ? 'ProseMirror-selectednode' : ''}`}
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
                onDoubleClick={isChart ? handleChartEdit : undefined}
                style={{
                    width: width,
                    position: 'relative',
                    display: 'inline-block',
                    transition: isResizing ? 'none' : 'width 0.2s',
                    minHeight: imageStatus === 'loaded' ? undefined : 60,
                    backgroundColor: imageStatus === 'loaded' ? undefined : '#f5f5f5',
                    borderRadius: 4,
                    cursor: isChart ? 'pointer' : undefined,
                }}
            >
                {imageStatus === 'error' ? (
                    // Error fallback placeholder
                    <div style={{
                        width: '100%',
                        minHeight: 120,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexDirection: 'column',
                        backgroundColor: '#f8f9fa',
                        border: '1px dashed #dee2e6',
                        borderRadius: 4,
                        padding: 16,
                        gap: 8,
                    }}>
                        <span style={{ fontSize: 28, opacity: 0.5 }}>🖼️</span>
                        <span style={{ fontSize: 12, color: '#868e96', textAlign: 'center' }}>
                            Image could not be loaded
                        </span>
                        <button
                            onClick={() => {
                                setRetryCount(0);
                                setImageStatus('loading');
                                setImageSrc(node.attrs.src);
                            }}
                            style={{
                                fontSize: 11,
                                padding: '4px 12px',
                                border: '1px solid #dee2e6',
                                borderRadius: 4,
                                backgroundColor: '#fff',
                                cursor: 'pointer',
                                color: '#495057',
                            }}
                        >
                            Retry
                        </button>
                    </div>
                ) : (
                    <img
                        src={imageSrc}
                        alt={node.attrs.alt}
                        crossOrigin={imageSrc && !imageSrc.startsWith('blob:') ? 'anonymous' : undefined}
                        onLoad={handleImageLoad}
                        onError={handleImageError}
                        style={{
                            width: '100%',
                            display: imageStatus === 'loaded' ? 'block' : 'none',
                            borderRadius: 4
                        }}
                    />
                )}

                {/* Loading indicator while image is being fetched */}
                {imageStatus === 'loading' && (
                    <div style={{
                        width: '100%',
                        minHeight: 120,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#f8f9fa',
                        borderRadius: 4,
                    }}>
                        <span style={{ fontSize: 13, color: '#868e96' }}>Loading image...</span>
                    </div>
                )}

                {/* Chart Edit Overlay */}
                {isChart && isHovered && imageStatus === 'loaded' && (
                    <button
                        onClick={(e) => { e.stopPropagation(); handleChartEdit(); }}
                        style={{
                            position: 'absolute',
                            top: 8,
                            right: 8,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            padding: '6px 12px',
                            backgroundColor: 'rgba(99, 102, 241, 0.9)',
                            color: '#fff',
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 12,
                            fontWeight: 500,
                            zIndex: 10,
                            backdropFilter: 'blur(4px)',
                        }}
                    >
                        ✏️ Edit Chart
                    </button>
                )}

                {/* Resize Handle - Bottom Right */}
                {(selected || isResizing) && imageStatus === 'loaded' && (
                    <div
                        onMouseDown={handleMouseDown}
                        style={{
                            position: 'absolute',
                            bottom: 0,
                            right: 0,
                            width: 12,
                            height: 12,
                            backgroundColor: '#2196F3',
                            border: '1px solid white',
                            cursor: 'nwse-resize',
                            zIndex: 10
                        }}
                    />
                )}
            </div>
        </NodeViewWrapper>
    );
};

// Styles aren't fully applicable since we use some raw HTML/CSS for the resizer logic
// But we keep the wrapper consistent
const styles = StyleSheet.create({
    wrapper: {
        marginVertical: 10,
        width: '100%', // Allow container to be full width, inner div controls actual image width
        alignItems: 'flex-start', // Default left align
        display: 'block', // Ensure block display for proper width handling
    }
});

export default ImageResizeComponent;