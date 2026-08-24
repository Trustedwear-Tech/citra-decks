// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    Dimensions,
    Platform,
    SafeAreaView,
    StatusBar
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import PrintableCanvas from './PrintableCanvas';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Minimum interval between page changes (ms) to prevent rapid navigation crashes
const NAV_DEBOUNCE_MS = 150;

// A4 aspect ratio
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

const PrintablePlayer = ({
    visible,
    onClose,
    PAGES,
    initialPAGEId,
    theme,
    printableStyle
}) => {
    const [currentPAGEIndex, setCurrentPAGEIndex] = useState(0);
    // Calculate initial scale synchronously to prevent first-render sizing issue
    const [scale, setScale] = useState(() => {
        const { width, height } = Dimensions.get('window');
        const scaleX = width / PAGE_WIDTH;
        const scaleY = height / PAGE_HEIGHT;
        return Math.min(scaleX, scaleY);
    });
    const [showControls, setShowControls] = useState(true);
    const [isMobileScreen, setIsMobileScreen] = useState(Dimensions.get('window').width < 768);
    const controlsTimeoutRef = useRef(null);
    const lastNavTimeRef = useRef(0); // Debounce rapid navigation
    const navCooldownRef = useRef(false);

    // Initialize start PAGE - ALWAYS start from first PAGE
    useEffect(() => {
        if (visible) {
            setCurrentPAGEIndex(0); // Always start from first PAGE
            calculateScale();

            // Auto-hide controls after 3 seconds
            resetControlsTimer();
        }
    }, [visible, PAGES]);

    // Handle window resize for responsiveness
    useEffect(() => {
        const handleResize = () => {
            const { width } = Dimensions.get('window');
            setIsMobileScreen(width < 768);
            calculateScale();
        };

        const subscription = Dimensions.addEventListener('change', handleResize);
        return () => {
            subscription?.remove();
        };
    }, []);

    // Keyboard navigation
    useEffect(() => {
        if (!visible || Platform.OS !== 'web') return;

        const handleKeyDown = (e) => {
            // Show controls on any keypress
            resetControlsTimer();

            if (e.key === 'ArrowRight' || e.key === 'Space' || e.key === 'Enter') {
                goToNextPAGE();
            } else if (e.key === 'ArrowLeft') {
                goToPrevPAGE();
            } else if (e.key === 'Escape') {
                handleClose();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [visible, currentPAGEIndex, PAGES.length]); // Dependencies needed for index closure

    const calculateScale = () => {
        const { width, height } = Dimensions.get('window');
        // Calculate scale to fit 16:9 PAGE in window (with some padding)
        const scaleX = width / PAGE_WIDTH;
        const scaleY = height / PAGE_HEIGHT;
        // Use the smaller scale to ensure it fits completely
        // No padding for truly full screen immersion
        setScale(Math.min(scaleX, scaleY));
    };

    const goToNextPAGE = useCallback(() => {
        const now = Date.now();
        if (now - lastNavTimeRef.current < NAV_DEBOUNCE_MS) return; // Debounce rapid navigation
        lastNavTimeRef.current = now;
        setCurrentPAGEIndex(prev => {
            if (prev < PAGES.length - 1) return prev + 1;
            return prev;
        });
    }, [PAGES.length]);

    const goToPrevPAGE = useCallback(() => {
        const now = Date.now();
        if (now - lastNavTimeRef.current < NAV_DEBOUNCE_MS) return; // Debounce rapid navigation
        lastNavTimeRef.current = now;
        setCurrentPAGEIndex(prev => {
            if (prev > 0) return prev - 1;
            return prev;
        });
    }, []);

    const resetControlsTimer = () => {
        setShowControls(true);
        if (controlsTimeoutRef.current) {
            clearTimeout(controlsTimeoutRef.current);
        }
        controlsTimeoutRef.current = setTimeout(() => {
            setShowControls(false);
        }, 3000);
    };

    const handleMouseMove = () => {
        if (Platform.OS === 'web') {
            resetControlsTimer();
        }
    };

    // Enter browser fullscreen when player opens
    useEffect(() => {
        if (!visible || Platform.OS !== 'web') return;
        try {
            const el = document.documentElement;
            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
                else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
            }
        } catch (e) { /* ignore */ }
        return () => {
            try {
                if (document.fullscreenElement) document.exitFullscreen();
                else if (document.webkitFullscreenElement) document.webkitExitFullscreen();
            } catch (e) { /* ignore */ }
        };
    }, [visible]);

    // Recalculate scale when fullscreen changes
    useEffect(() => {
        if (Platform.OS !== 'web') return;
        const onFSChange = () => calculateScale();
        document.addEventListener('fullscreenchange', onFSChange);
        return () => document.removeEventListener('fullscreenchange', onFSChange);
    }, []);

    const handleClose = useCallback(() => {
        try {
            if (Platform.OS === 'web' && document.fullscreenElement) {
                document.exitFullscreen();
            }
        } catch (e) { /* ignore */ }
        onClose();
    }, [onClose]);

    if (!visible) return null;

    const currentPAGE = PAGES[currentPAGEIndex];

    return (
        <Modal visible={visible} animationType="fade" onRequestClose={handleClose}>
            <View
                style={[styles.container, { backgroundColor: '#000' }]}
                onStartShouldSetResponder={() => true}
                onResponderMove={handleMouseMove}
                // Web-specific handler
                {...(Platform.OS === 'web' ? { onMouseMove: handleMouseMove } : {})}
            >
                <StatusBar hidden />

                {/* PAGE Content - No key={} prop to avoid full Fabric.js canvas
                    destroy/recreate on every page change. The canvas handles
                    PAGE prop changes via its internal useEffect diffing logic. */}
                <View style={styles.PAGEContainer}>
                    <PrintableCanvas
                        PAGE={currentPAGE}
                        printableStyle={printableStyle}
                        theme={theme}
                        isEditable={false} // READ ONLY MODE
                        scale={scale}
                        onSelectElement={() => { }} // No-op
                        onAddElement={() => { }}
                        onUpdateElement={() => { }}
                        onDeleteElement={() => { }}
                    />
                </View>

                {/* Overlay Controls */}
                {showControls && (
                    <SafeAreaView style={styles.controlsOverlay} pointerEvents="box-none">

                        {/* Top Bar */}
                        <View style={styles.topBar}>
                            <Text style={styles.PAGECounter}>
                                {currentPAGEIndex + 1} / {PAGES.length}
                            </Text>

                            <TouchableOpacity
                                style={styles.closeButton}
                                onPress={handleClose}
                            >
                                <Ionicons name="close" size={24} color="#fff" />
                            </TouchableOpacity>
                        </View>

                        {/* Navigation Arrows */}
                        <View style={isMobileScreen ? styles.navigationRowMobile : styles.navigationRow} pointerEvents="box-none">
                            <TouchableOpacity
                                style={[
                                    isMobileScreen ? styles.navButtonMobile : styles.navButton,
                                    currentPAGEIndex === 0 && styles.navButtonDisabled
                                ]}
                                onPress={() => { resetControlsTimer(); goToPrevPAGE(); }}
                                disabled={currentPAGEIndex === 0}
                            >
                                <Ionicons name="chevron-back" size={isMobileScreen ? 28 : 40} color="#fff" />
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[
                                    isMobileScreen ? styles.navButtonMobile : styles.navButton,
                                    currentPAGEIndex === PAGES.length - 1 && styles.navButtonDisabled
                                ]}
                                onPress={() => { resetControlsTimer(); goToNextPAGE(); }}
                                disabled={currentPAGEIndex === PAGES.length - 1}
                            >
                                <Ionicons name="chevron-forward" size={isMobileScreen ? 28 : 40} color="#fff" />
                            </TouchableOpacity>
                        </View>

                    </SafeAreaView>
                )}
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: 'black',
        justifyContent: 'center',
        alignItems: 'center',
    },
    PAGEContainer: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
    },
    controlsOverlay: {
        padding: 10,
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'space-between',
    },
    topBar: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
    },
    closeButton: {
        padding: 8,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        borderRadius: 20,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.3)',
    },
    PAGECounter: {
        color: 'rgba(255, 255, 255, 0.9)',
        fontSize: 14,
        fontWeight: '600',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.3)',
    },
    navigationRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        flex: 1, // fill vertical space to center vertically relative to screen if needed, or just let them float
        // Actually we want them centered vertically
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: 'box-none', // Let clicks pass through to canvas if not on buttons
    },
    navigationRowMobile: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 80,
        gap: 16,
        pointerEvents: 'box-none',
    },
    navButton: {
        padding: 20,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        borderRadius: 40,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.3)',
    },
    navButtonMobile: {
        padding: 12,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        borderRadius: 30,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.3)',
        marginHorizontal: 8,
    },
    navButtonDisabled: {
        opacity: 0.1,
    },
});

export default PrintablePlayer;
