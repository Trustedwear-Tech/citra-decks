// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import React, { useState, useRef, useEffect } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    ActivityIndicator,
    Platform,
    Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

/**
 * Modal to record video using camera and microphone
 * Returns a Data URL (base64) of the recorded video
 */
const VideoRecorderModal = ({
    visible,
    onClose,
    onSave, // (videoDataUrl) => void
    theme
}) => {
    const [isRecording, setIsRecording] = useState(false);
    const [stream, setStream] = useState(null);
    const [videoBlob, setVideoBlob] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [timer, setTimer] = useState(0);
    const [isProcessing, setIsProcessing] = useState(false);
    const [cameraError, setCameraError] = useState(null);

    const mediaRecorderRef = useRef(null);
    const videoPreviewRef = useRef(null);
    const timerIntervalRef = useRef(null);
    const chunksRef = useRef([]);

    // Initialize camera stream when modal opens
    useEffect(() => {
        if (visible) {
            startCamera();
        } else {
            stopCamera();
            resetState();
        }
        return () => {
            stopCamera();
        };
    }, [visible]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            stopCamera();
            if (previewUrl) {
                URL.revokeObjectURL(previewUrl);
            }
        };
    }, []);

    const startCamera = async () => {
        if (Platform.OS !== 'web') {
            setCameraError('Video recording is currently only supported on Web.');
            return;
        }

        setError(null);

        // Try preferred constraints first
        try {
            const constraints = {
                audio: true,
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: "user"
                }
            };

            const mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
            setStream(mediaStream);

            if (videoPreviewRef.current) {
                videoPreviewRef.current.srcObject = mediaStream;
            }
        } catch (err) {
            console.log('Preferred camera constraints failed, trying fallback...', err);

            // Fallback: minimal constraints
            try {
                const fallbackConstraints = {
                    audio: true,
                    video: true
                };

                const mediaStream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
                setStream(mediaStream);

                if (videoPreviewRef.current) {
                    videoPreviewRef.current.srcObject = mediaStream;
                }
            } catch (finalErr) {
                console.error('Error accessing camera (fallback failed):', finalErr);
                setCameraError('Could not access camera or microphone. Please ensure you have granted permissions.');
            }
        }
    };

    // Helper to set error (shim for replace)
    const setError = (msg) => setCameraError(msg);

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            setStream(null);
        }
        if (videoPreviewRef.current) {
            videoPreviewRef.current.srcObject = null;
        }
    };

    const resetState = () => {
        setIsRecording(false);
        chunksRef.current = [];
        setVideoBlob(null);
        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
        }
        setPreviewUrl(null);
        setTimer(0);
        setIsProcessing(false);
        if (timerIntervalRef.current) {
            clearInterval(timerIntervalRef.current);
        }
    };

    const startRecording = () => {
        if (!stream) return;

        chunksRef.current = [];
        const options = { mimeType: 'video/webm;codecs=vp8,opus' };

        try {
            const mediaRecorder = new MediaRecorder(stream, options);
            mediaRecorderRef.current = mediaRecorder;

            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    chunksRef.current.push(event.data);
                }
            };

            mediaRecorder.start();
            setIsRecording(true);

            // Start Timer
            setTimer(0);
            timerIntervalRef.current = setInterval(() => {
                setTimer(prev => prev + 1);
            }, 1000);

        } catch (e) {
            console.error('Exception while creating MediaRecorder:', e);
            Alert.alert('Error', 'Could not start recording: ' + e.message);
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);

            if (timerIntervalRef.current) {
                clearInterval(timerIntervalRef.current);
            }

            // Wait for the stop event or just process chunks
            mediaRecorderRef.current.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: 'video/webm' });
                setVideoBlob(blob);
                const url = URL.createObjectURL(blob);
                setPreviewUrl(url);

                console.log('Recording stopped, blob size:', blob.size);
            };
        }
    };

    const handleRetake = () => {
        setVideoBlob(null);
        setPreviewUrl(null);
        chunksRef.current = [];
        setTimer(0);
        // Ensure stream is still active
        if (!stream) {
            startCamera();
        } else if (videoPreviewRef.current) {
            videoPreviewRef.current.srcObject = stream;
        }
    };

    const handleSave = () => {
        if (!videoBlob && chunksRef.current.length === 0) return;

        setIsProcessing(true);

        // Final blob creation check
        const blob = videoBlob || new Blob(chunksRef.current, { type: 'video/webm' });

        // Convert to Data URL
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = () => {
            const base64data = reader.result;
            console.log('Video converted to Data URL. Length:', base64data.length);
            onSave(base64data);
            setIsProcessing(false);
            onClose();
        };
        reader.onerror = (error) => {
            console.error('Error converting blob to base64:', error);
            Alert.alert('Error', 'Failed to process video.');
            setIsProcessing(false);
        };
    };

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <Modal
            visible={visible}
            transparent
            animationType="slide"
            onRequestClose={onClose}
        >
            <View style={styles.overlay}>
                <View style={[styles.modal, { backgroundColor: theme.surface }]}>
                    <View style={[styles.header, { borderBottomColor: theme.border }]}>
                        <Text style={[styles.title, { color: theme.text }]}>Record Video</Text>
                        <TouchableOpacity onPress={onClose} disabled={isRecording}>
                            <Ionicons name="close" size={24} color={theme.text} />
                        </TouchableOpacity>
                    </View>

                    <View style={styles.content}>
                        <View style={styles.videoContainer}>
                            {cameraError ? (
                                <View style={styles.errorContainer}>
                                    <Ionicons name="warning-outline" size={48} color="#FF6B6B" />
                                    <Text style={[styles.errorText, { color: theme.text }]}>{cameraError}</Text>
                                    <TouchableOpacity
                                        style={[styles.retryBtn, { borderColor: theme.border }]}
                                        onPress={startCamera}
                                    >
                                        <Text style={{ color: theme.text }}>Retry</Text>
                                    </TouchableOpacity>
                                </View>
                            ) : previewUrl ? (
                                // Web Video Element for playback
                                Platform.OS === 'web' ? (
                                    <video
                                        src={previewUrl}
                                        controls
                                        style={{ width: '100%', height: '100%', borderRadius: 8, objectFit: 'cover' }}
                                    />
                                ) : (
                                    <Text style={{ color: theme.text }}>Preview not supported on native</Text>
                                )
                            ) : (
                                // Web Video Element for camera preview
                                Platform.OS === 'web' ? (
                                    <video
                                        ref={videoPreviewRef}
                                        autoPlay
                                        muted
                                        playsInline
                                        style={{
                                            width: '100%',
                                            height: '100%',
                                            borderRadius: 8,
                                            objectFit: 'cover',
                                            transform: 'scaleX(-1)' // Mirror effect
                                        }}
                                    />
                                ) : (
                                    <Text style={{ color: theme.text }}>Camera view</Text>
                                )
                            )}

                            {/* Recording Timer Overlay */}
                            {isRecording && (
                                <View style={styles.timerOverlay}>
                                    <View style={styles.recordingDot} />
                                    <Text style={styles.timerText}>{formatTime(timer)}</Text>
                                </View>
                            )}
                        </View>

                        <View style={styles.controls}>
                            {previewUrl ? (
                                <View style={styles.reviewControls}>
                                    <TouchableOpacity
                                        style={[styles.btn, styles.secondaryBtn, { borderColor: theme.border }]}
                                        onPress={handleRetake}
                                    >
                                        <Text style={[styles.btnText, { color: theme.text }]}>Retake</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        style={[styles.btn, styles.primaryBtn, { backgroundColor: theme.primary }]}
                                        onPress={handleSave}
                                        disabled={isProcessing}
                                    >
                                        {isProcessing ? (
                                            <ActivityIndicator color="#fff" size="small" />
                                        ) : (
                                            <Text style={[styles.btnText, { color: '#fff' }]}>Use Video</Text>
                                        )}
                                    </TouchableOpacity>
                                </View>
                            ) : (
                                <TouchableOpacity
                                    style={[styles.recordBtn, isRecording ? styles.recording : null]}
                                    onPress={isRecording ? stopRecording : startRecording}
                                >
                                    <View style={[styles.recordIcon, isRecording ? styles.recordingIcon : null]} />
                                </TouchableOpacity>
                            )}
                        </View>
                    </View>

                    <Text style={[styles.note, { color: theme.textSecondary }]}>
                        {isRecording ? 'Recording... click button to stop.' : previewUrl ? 'Review your video.' : 'Make sure you are well lit.'}
                    </Text>
                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.7)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
    },
    modal: {
        width: '100%',
        maxWidth: 600,
        borderRadius: 12,
        overflow: 'hidden',
        maxHeight: '90%'
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
    },
    title: {
        fontSize: 18,
        fontWeight: '600',
    },
    content: {
        padding: 20,
        alignItems: 'center',
    },
    videoContainer: {
        width: '100%',
        aspectRatio: 16 / 9,
        backgroundColor: '#000',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
        marginBottom: 20,
    },
    timerOverlay: {
        position: 'absolute',
        top: 10,
        right: 10,
        backgroundColor: 'rgba(0,0,0,0.5)',
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 4,
        flexDirection: 'row',
        alignItems: 'center',
    },
    recordingDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor: '#ff4444',
        marginRight: 6,
    },
    timerText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '600',
        fontFamily: Platform.OS === 'web' ? 'monospace' : undefined,
    },
    controls: {
        width: '100%',
        alignItems: 'center',
        justifyContent: 'center',
    },
    recordBtn: {
        width: 64,
        height: 64,
        borderRadius: 32,
        borderWidth: 4,
        borderColor: '#fff',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'transparent', // Outer ring
    },
    recording: {
        borderColor: '#ff4444',
    },
    recordIcon: {
        width: 50,
        height: 50,
        borderRadius: 25,
        backgroundColor: '#ff4444',
    },
    recordingIcon: {
        width: 24,
        height: 24,
        borderRadius: 4, // Square when recording
    },
    reviewControls: {
        flexDirection: 'row',
        gap: 12,
        width: '100%',
        justifyContent: 'center',
    },
    btn: {
        paddingHorizontal: 24,
        paddingVertical: 12,
        borderRadius: 8,
        minWidth: 100,
        alignItems: 'center',
        justifyContent: 'center',
    },
    primaryBtn: {
        // bg color from props
    },
    secondaryBtn: {
        backgroundColor: 'transparent',
        borderWidth: 1,
    },
    btnText: {
        fontSize: 14,
        fontWeight: '600',
    },
    note: {
        textAlign: 'center',
        paddingBottom: 16,
        fontSize: 12,
    },
    errorContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20
    },
    errorText: {
        marginTop: 10,
        textAlign: 'center',
        marginBottom: 20
    },
    retryBtn: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 20,
        borderWidth: 1,
    }
});

export default VideoRecorderModal;
