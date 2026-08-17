// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import PresentationCanvas from './PresentationCanvas';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Aspect ratio 16:9
const SLIDE_WIDTH = 960;
const SLIDE_HEIGHT = 540;

const PresentationPlayer = ({
    visible,
    onClose,
    slides,
    initialSlideId,
    theme,
    presentationStyle
}) => {
    const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
    // Calculate initial scale synchronously to prevent first-render sizing issue
    const [scale, setScale] = useState(() => {
        const { width, height } = Dimensions.get('window');
        const scaleX = width / SLIDE_WIDTH;
        const scaleY = height / SLIDE_HEIGHT;
        return Math.min(scaleX, scaleY);
    });
    const [showControls, setShowControls] = useState(true);
    const controlsTimeoutRef = useRef(null);
    const containerRef = useRef(null);

    // Enter browser fullscreen on web for true immersive presentation
    useEffect(() => {
        if (Platform.OS !== 'web') return;

        let originalBodyBg = document.body.style.backgroundColor;
        let originalHtmlBg = document.documentElement.style.backgroundColor;
        let rootElement = document.getElementById('root');
        let originalRootBg = rootElement ? rootElement.style.backgroundColor : '';

        if (visible) {
            // Force black background on root elements to prevent white borders
            document.body.style.setProperty('background-color', 'black', 'important');
            document.documentElement.style.setProperty('background-color', 'black', 'important');
            if (rootElement) {
                rootElement.style.setProperty('background-color', 'black', 'important');
            }

            // Only request fullscreen if not already in fullscreen (it's requested from the click handler)
            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                try {
                    const el = document.documentElement;
                    if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
                    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
                    else if (el.msRequestFullscreen) el.msRequestFullscreen();
                } catch (e) {
                    console.warn('[PresentationPlayer] Fullscreen request failed:', e);
                }
            }
        } else {
            // Restore backgrounds if exiting visible state
            document.body.style.backgroundColor = originalBodyBg;
            document.documentElement.style.backgroundColor = originalHtmlBg;
            if (rootElement) {
                rootElement.style.backgroundColor = originalRootBg;
            }

            try {
                if (document.fullscreenElement) document.exitFullscreen();
                else if (document.webkitFullscreenElement) document.webkitExitFullscreen();
            } catch (e) { /* ignore */ }
        }

        return () => {
            // Always restore on unmount or visibility change cleanup
            if (visible) {
                try {
                    document.body.style.backgroundColor = originalBodyBg;
                    document.documentElement.style.backgroundColor = originalHtmlBg;
                    if (rootElement) {
                        rootElement.style.backgroundColor = originalRootBg;
                    }
                } catch (e) { }
            }
        };
    }, [visible]);

    // Initialize start slide - ALWAYS start from first slide
    useEffect(() => {
        if (visible) {
            setCurrentSlideIndex(0); // Always start from first slide
            calculateScale();

            // Auto-hide controls after 3 seconds
            resetControlsTimer();
        }
    }, [visible, slides]);

    // Handle window resize for responsiveness
    useEffect(() => {
        const handleResize = () => {
            calculateScale();
        };

        const subscription = Dimensions.addEventListener('change', handleResize);

        // Also listen for fullscreen change to recalculate scale
        let fullscreenHandler;
        if (Platform.OS === 'web') {
            fullscreenHandler = () => {
                // Small delay to let the browser update dimensions
                setTimeout(() => calculateScale(), 100);
            };
            document.addEventListener('fullscreenchange', fullscreenHandler);
            document.addEventListener('webkitfullscreenchange', fullscreenHandler);
        }

        return () => {
            subscription?.remove();
            if (fullscreenHandler) {
                document.removeEventListener('fullscreenchange', fullscreenHandler);
                document.removeEventListener('webkitfullscreenchange', fullscreenHandler);
            }
        };
    }, []);

    // Keyboard navigation
    useEffect(() => {
        if (!visible || Platform.OS !== 'web') return;

        const handleKeyDown = (e) => {
            // Show controls on any keypress
            resetControlsTimer();

            if (e.key === 'ArrowRight' || e.key === 'Space' || e.key === 'Enter') {
                goToNextSlide();
            } else if (e.key === 'ArrowLeft') {
                goToPrevSlide();
            } else if (e.key === 'Escape') {
                // Exit browser fullscreen then close player
                try {
                    if (document.fullscreenElement) document.exitFullscreen();
                    else if (document.webkitFullscreenElement) document.webkitExitFullscreen();
                } catch (err) { /* ignore */ }
                onClose();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [visible, currentSlideIndex, slides.length]); // Dependencies needed for index closure

    const calculateScale = () => {
        const { width, height } = Dimensions.get('window');
        // Calculate scale to fit 16:9 slide in window (with some padding)
        const scaleX = width / SLIDE_WIDTH;
        const scaleY = height / SLIDE_HEIGHT;
        // Use the smaller scale to ensure it fits completely
        // No padding for truly full screen immersion
        setScale(Math.min(scaleX, scaleY));
    };

    const goToNextSlide = () => {
        setCurrentSlideIndex(prev => {
            if (prev < slides.length - 1) return prev + 1;
            return prev;
        });
    };

    const goToPrevSlide = () => {
        setCurrentSlideIndex(prev => {
            if (prev > 0) return prev - 1;
            return prev;
        });
    };

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

    // Close handler: exit browser fullscreen then call parent onClose
    const handleClose = useCallback(() => {
        if (Platform.OS === 'web') {
            try {
                if (document.fullscreenElement) document.exitFullscreen();
                else if (document.webkitFullscreenElement) document.webkitExitFullscreen();
            } catch (e) { /* ignore */ }
        }
        onClose();
    }, [onClose]);

    if (!visible) return null;

    const currentSlide = slides[currentSlideIndex];

    return (
        <Modal visible={visible} animationType="fade" onRequestClose={handleClose}>
            <View
                style={[
                    styles.container,
                    { backgroundColor: '#000' },
                    Platform.OS === 'web' && { height: '100vh', width: '100vw' }
                ]}
                onStartShouldSetResponder={() => true}
                onResponderMove={handleMouseMove}
                // Web-specific handler
                {...(Platform.OS === 'web' ? { onMouseMove: handleMouseMove } : {})}
            >
                <StatusBar hidden />

                {/* Slide Content - fills entire screen */}
                <View style={styles.slideContainer}>
                    <PresentationCanvas
                        key={currentSlide?.id} // Force complete remount on slide change
                        slide={currentSlide}
                        presentationStyle={presentationStyle}
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

                        {/* Top-right close button */}
                        <View style={styles.topBar}>
                            <View />
                            <TouchableOpacity
                                style={styles.closeButton}
                                onPress={handleClose}
                            >
                                <Ionicons name="close" size={20} color="#fff" />
                            </TouchableOpacity>
                        </View>

                        {/* Bottom Navigation Bar */}
                        <View style={styles.bottomBar}>
                            <View style={styles.bottomBarInner}>
                                <TouchableOpacity
                                    style={[styles.bottomNavButton, currentSlideIndex === 0 && styles.navButtonDisabled]}
                                    onPress={() => { resetControlsTimer(); goToPrevSlide(); }}
                                    disabled={currentSlideIndex === 0}
                                >
                                    <Ionicons name="chevron-back" size={18} color="#fff" />
                                </TouchableOpacity>

                                <Text style={styles.slideCounter}>
                                    {currentSlideIndex + 1} / {slides.length}
                                </Text>

                                <TouchableOpacity
                                    style={[styles.bottomNavButton, currentSlideIndex === slides.length - 1 && styles.navButtonDisabled]}
                                    onPress={() => { resetControlsTimer(); goToNextSlide(); }}
                                    disabled={currentSlideIndex === slides.length - 1}
                                >
                                    <Ionicons name="chevron-forward" size={18} color="#fff" />
                                </TouchableOpacity>
                            </View>
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
    slideContainer: {
        flex: 1,
        width: '100%',
        alignItems: 'center',
        justifyContent: 'center',
    },
    controlsOverlay: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'space-between',
    },
    topBar: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingTop: 12,
        paddingHorizontal: 16,
    },
    closeButton: {
        padding: 6,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        borderRadius: 16,
    },
    slideCounter: {
        color: '#fff',
        fontSize: 13,
        fontWeight: '600',
        marginHorizontal: 14,
    },
    bottomBar: {
        alignItems: 'center',
        paddingBottom: 18,
    },
    bottomBarInner: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        borderRadius: 24,
        paddingHorizontal: 6,
        paddingVertical: 4,
    },
    bottomNavButton: {
        padding: 8,
        borderRadius: 16,
    },
    navButtonDisabled: {
        opacity: 0.2,
    },
});

export default PresentationPlayer;
