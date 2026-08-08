/**
 * AIImageModal - AI-powered image generation modal for Report Composer
 * Uses vault context for description enhancement.
 * Image gen: Configurable backend (IMAGE_GEN_API_KEY)
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    TextInput,
    ScrollView,
    ActivityIndicator,
    Platform,
    Modal,
    Image,
    useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import ImageGenService from '../../services/ImageGenService';
import authService from '../../services/authService';
import globalImageCache from '../../utils/globalImageCache';

const AIImageModal = ({
    visible,
    onClose,
    onInsertImage,
    currentPage,
    userDeviceId,
    selectedFolders = [],
    apiConfig,
    theme,
    initialWidth = 1024,
    initialHeight = 1024,
}) => {
    const { useUploadedData } = useWorkspace();
    const { width: screenWidth } = useWindowDimensions();
    const isMobile = screenWidth < 768;

    // State
    const [imageQuery, setImageQuery] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [generatedImage, setGeneratedImage] = useState(null);
    const [imageDescription, setImageDescription] = useState('');
    const [imageType, setImageType] = useState('photo'); // 'photo' | 'infographic' | 'photo_with_text'
    const [error, setError] = useState(null);

    const [stage, setStage] = useState('input'); // 'input', 'generating', 'preview'
    const [imageProvider, setImageProvider] = useState('image-gen');

    const safeTheme = theme || {
        background: '#ffffff',
        surface: '#f5f5f5',
        text: '#333333',
        textSecondary: '#666666',
        primary: '#2196F3',
        border: '#e0e0e0',
    };

    // Get first paragraph from page content for context
    const getPageSnippet = useCallback(() => {
        if (!currentPage?.content) return '';
        // Strip HTML tags and get first 300 chars
        const text = currentPage.content.replace(/<[^>]*>/g, '');
        return text.substring(0, 300);
    }, [currentPage]);

    // Generate image description from backend (LLM + vault)
    const generateImageDescription = useCallback(async () => {
        if (!imageQuery.trim() || isGenerating) return;

        setIsGenerating(true);
        setError(null);
        setStage('generating');

        try {
            const token = await AsyncStorage.getItem('@auth_token');
            if (!token) {
                setError('Please log in again.');
                setStage('input');
                setIsGenerating(false);
                return;
            }

            const response = await fetch(`${apiConfig.API_URL}/composer/generate-image-description`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    user_query: imageQuery,
                    page_title: currentPage?.title || '',
                    page_snippet: getPageSnippet(),
                    folder_ids: useUploadedData
                        ? (selectedFolders.length > 0 ? selectedFolders.map(f => f.id || f) : [])
                        : [],
                    user_id: userDeviceId,
                }),
            });

            if (!response.ok) {
                const errText = await response.text();
                setError(`Request failed: ${response.status}`);
                setStage('input');
                setIsGenerating(false);
                return;
            }

            const data = await response.json();

            if (data.success && data.image_description) {
                setImageDescription(data.image_description);

                // Store the image type from AI response (photo | infographic | photo_with_text)
                const detectedImageType = data.image_type || 'photo';
                setImageType(detectedImageType);

                // Auto-select provider based on image type (for UI display only)
                if (detectedImageType === 'infographic' || detectedImageType === 'photo_with_text') {
                    setImageProvider('llm-image');
                } else {
                    setImageProvider('image-gen');
                }

                // Now generate the actual image, passing the detected image type
                await generateImageFromDescription(data.image_description, detectedImageType);
            } else {
                setError(data.detail || 'Failed to generate image description.');
                setStage('input');
            }
        } catch (err) {
            console.error('Image description error:', err);
            setError('Network error. Please try again.');
            setStage('input');
        } finally {
            setIsGenerating(false);
        }
    }, [imageQuery, isGenerating, currentPage, getPageSnippet, userDeviceId, selectedFolders, apiConfig, useUploadedData]);

    // Generate image via Image Generation API
    const generateImageFromDescription = useCallback(async (description, detectedImageType = null) => {
        try {
            // Use passed imageType or fall back to state
            const typeToUse = detectedImageType || imageType;

            console.log(`🖼️ [AI_IMAGE_MODAL] Generating image - Type: ${typeToUse}`);

            let response;
            response = await ImageGenService.generateImage(description, {
                width: initialWidth,
                height: initialHeight,
            });

            if (response.success) {
                // Prefer base64 image_data if available (immediate display), else use URL
                const imageUrl = response.image_data || response.image_url;
                setGeneratedImage(imageUrl);
                setStage('preview');

                // Pre-cache the image as blob URL so it's ready for instant insertion
                // into the Tiptap editor (avoids CORS/loading issues on insert)
                if (imageUrl && imageUrl.startsWith('http')) {
                    globalImageCache.fetchAndCache(imageUrl).catch(() => {
                        console.warn('[AI_IMAGE_MODAL] Pre-cache failed, will retry on insert');
                    });
                }
            } else {
                setError(response.message || `Failed to generate image with ${imageProvider}.`);
                setStage('input');
            }
        } catch (err) {
            console.error('Image generation error:', err);
            setError('Failed to generate image. Please try again.');
            setStage('input');
        }
    }, [userDeviceId, imageProvider, initialWidth, initialHeight, imageType]);

    // Insert image into report
    const handleInsertImage = useCallback(async () => {
        if (!generatedImage) return;

        // Insert as half-width image (async - pre-caches before insertion)
        await onInsertImage(generatedImage, imageDescription);
        onClose();
    }, [generatedImage, imageDescription, onInsertImage, onClose]);

    // Regenerate with same query
    const handleRegenerate = useCallback(() => {
        setGeneratedImage(null);
        setStage('generating');
        generateImageFromDescription(imageDescription, imageType);
    }, [imageDescription, imageType, generateImageFromDescription]);

    // Reset state when modal closes
    useEffect(() => {
        if (!visible) {
            setImageQuery('');
            setGeneratedImage(null);
            setImageDescription('');
            setImageType('photo');
            setError(null);
            setStage('input');
            setIsGenerating(false);
        }
    }, [visible]);

    if (!visible) return null;

    const content = (
        <View style={[styles.container, { backgroundColor: safeTheme.background }, isMobile && { width: '100%', height: '100%', maxWidth: undefined, maxHeight: undefined, borderRadius: 0 }]}>
            {/* Header */}
            <View style={[styles.header, { borderBottomColor: safeTheme.border }, isMobile && { padding: 10 }]}>
                <View style={styles.headerLeft}>
                    <Ionicons name="image" size={isMobile ? 20 : 24} color={safeTheme.primary} />
                    <Text style={[styles.headerTitle, { color: safeTheme.text }, isMobile && { fontSize: 16 }]}>AI Image</Text>
                </View>
                <View style={styles.headerRight}>
                    <TouchableOpacity
                        style={[
                            styles.headerInsertBtn,
                            {
                                backgroundColor: generatedImage ? safeTheme.primary : safeTheme.border,
                                opacity: generatedImage ? 1 : 0.6,
                            }
                        ]}
                        onPress={handleInsertImage}
                        disabled={!generatedImage || isGenerating}
                    >
                        <Ionicons name="add-circle" size={18} color="#fff" />
                        <Text style={styles.headerInsertBtnText}>
                            Insert Image
                        </Text>
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
                    style={[styles.inputPanel, { borderRightColor: safeTheme.border }, isMobile && { width: '100%', borderRightWidth: 0, borderBottomWidth: 1, borderBottomColor: safeTheme.border, maxHeight: 320 }]}
                    contentContainerStyle={{ padding: isMobile ? 12 : 20 }}
                >
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Describe Your Image</Text>

                    <View style={styles.inputSection}>
                        <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>
                            What image would you like to create?
                        </Text>
                        <TextInput
                            style={[styles.queryInput, {
                                backgroundColor: safeTheme.surface,
                                color: safeTheme.text,
                                borderColor: safeTheme.border
                            }]}
                            placeholder="e.g., A professional diagram showing our team structure..."
                            placeholderTextColor={safeTheme.textSecondary}
                            value={imageQuery}
                            onChangeText={setImageQuery}
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
                        onPress={generateImageDescription}
                        disabled={isGenerating || !imageQuery.trim()}
                    >
                        {isGenerating ? (
                            <ActivityIndicator size="small" color="#fff" />
                        ) : (
                            <>
                                <Ionicons name="sparkles" size={18} color="#fff" />
                                <Text style={styles.generateBtnText}>Generate Image</Text>
                            </>
                        )}
                    </TouchableOpacity>

                    {/* Quick suggestions */}
                    <View style={styles.suggestionsSection}>
                        <Text style={[styles.suggestionsTitle, { color: safeTheme.textSecondary }]}>Quick Ideas:</Text>
                        {[
                            'An infographic for this section',
                            'A professional diagram',
                            'A visualization of key data',
                            'An illustration matching the content'
                        ].map((suggestion, idx) => (
                            <TouchableOpacity
                                key={idx}
                                style={[styles.suggestionChip, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}
                                onPress={() => setImageQuery(suggestion)}
                            >
                                <Text style={[styles.suggestionText, { color: safeTheme.text }]}>{suggestion}</Text>
                            </TouchableOpacity>
                        ))}
                    </View>
                </ScrollView>

                {/* Right: Preview Panel */}
                <View style={[styles.previewPanel, isMobile && { padding: 12, minHeight: 250 }]}>
                    <Text style={[styles.panelTitle, { color: safeTheme.text }]}>Preview</Text>

                    <View style={[styles.previewContainer, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                        {stage === 'input' && !generatedImage && (
                            <View style={styles.previewPlaceholder}>
                                <Ionicons name="image-outline" size={64} color={safeTheme.textSecondary} />
                                <Text style={[styles.previewPlaceholderText, { color: safeTheme.textSecondary }]}>
                                    Your generated image will appear here
                                </Text>
                            </View>
                        )}

                        {stage === 'generating' && (
                            <View style={styles.previewPlaceholder}>
                                <ActivityIndicator size="large" color={safeTheme.primary} />
                                <Text style={[styles.previewPlaceholderText, { color: safeTheme.primary, marginTop: 16 }]}>
                                    Generating image...
                                </Text>
                                {imageDescription && (
                                    <Text style={[styles.descriptionPreview, { color: safeTheme.textSecondary }]}>
                                        "{imageDescription.substring(0, 100)}..."
                                    </Text>
                                )}
                            </View>
                        )}

                        {stage === 'preview' && generatedImage && (
                            <View style={styles.imagePreviewWrapper}>
                                <Image
                                    source={{ uri: generatedImage }}
                                    style={styles.generatedImage}
                                    resizeMode="contain"
                                />
                            </View>
                        )}

                        {error && (
                            <View style={styles.errorContainer}>
                                <Ionicons name="alert-circle" size={24} color="#EF4444" />
                                <Text style={styles.errorText}>{error}</Text>
                            </View>
                        )}
                    </View>

                    {/* Action buttons when image is ready */}
                    {generatedImage && (
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

                    {/* Description preview */}
                    {imageDescription && stage === 'preview' && (
                        <View style={[styles.descriptionCard, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                            <Text style={[styles.descriptionLabel, { color: safeTheme.textSecondary }]}>Generated Description:</Text>
                            <Text style={[styles.descriptionText, { color: safeTheme.text }]}>
                                {imageDescription}
                            </Text>
                        </View>
                    )}
                </View>
            </View>
        </View>
    );

    // On web, render as fixed overlay
    if (Platform.OS === 'web') {
        return (
            <View style={styles.overlay}>
                {content}
            </View>
        );
    }

    // On native, use Modal
    return (
        <Modal visible={visible} animationType="slide" transparent>
            <View style={styles.overlay}>
                {content}
            </View>
        </Modal>
    );
};

const styles = {
    overlay: {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
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
    headerLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    headerTitle: {
        fontSize: 20,
        fontWeight: '600',
    },
    closeBtn: {
        padding: 4,
        marginLeft: 8,
    },
    headerRight: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    headerInsertBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 20,
        gap: 6,
    },
    headerInsertBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
    mainContent: {
        flex: 1,
        flexDirection: 'row',
    },
    // Input Panel
    inputPanel: {
        width: '40%',
        // Padding moved to contentContainerStyle
        borderRightWidth: 1,
        flexDirection: 'column',
    },
    panelTitle: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 16,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    inputSection: {
        marginBottom: 16,
    },
    inputLabel: {
        fontSize: 13,
        marginBottom: 8,
    },
    queryInput: {
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        fontSize: 14,
        minHeight: 100,
        textAlignVertical: 'top',
    },
    contextCard: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 10,
        borderRadius: 8,
        borderWidth: 1,
        marginBottom: 16,
        gap: 8,
    },
    contextTextContainer: {
        flex: 1,
    },
    contextLabel: {
        fontSize: 11,
    },
    contextValue: {
        fontSize: 13,
        fontWeight: '500',
    },
    generateBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
        borderRadius: 10,
        gap: 8,
        marginBottom: 20,
    },
    generateBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
    suggestionsSection: {
        gap: 8,
    },
    suggestionsTitle: {
        fontSize: 12,
        marginBottom: 4,
    },
    suggestionChip: {
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 6,
        borderWidth: 1,
    },
    suggestionText: {
        fontSize: 12,
    },
    // Preview Panel
    previewPanel: {
        flex: 1,
        padding: 20,
        flexDirection: 'column',
    },
    previewContainer: {
        flex: 1,
        borderRadius: 12,
        borderWidth: 1,
        justifyContent: 'center',
        alignItems: 'center',
        overflow: 'hidden',
    },
    previewPlaceholder: {
        alignItems: 'center',
        padding: 20,
    },
    previewPlaceholderText: {
        fontSize: 14,
        marginTop: 16,
        textAlign: 'center',
    },
    descriptionPreview: {
        fontSize: 12,
        marginTop: 12,
        textAlign: 'center',
        fontStyle: 'italic',
        maxWidth: 300,
    },
    imagePreviewWrapper: {
        width: '100%',
        height: '100%',
        padding: 16,
    },
    generatedImage: {
        width: '100%',
        height: '100%',
    },
    errorContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        padding: 16,
    },
    errorText: {
        color: '#EF4444',
        fontSize: 13,
    },
    actionButtons: {
        flexDirection: 'row',
        gap: 8,
        marginTop: 12,
    },
    actionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: 8,
        borderWidth: 1,
        gap: 6,
    },
    actionBtnText: {
        fontSize: 13,
        fontWeight: '500',
    },
    descriptionCard: {
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        marginTop: 12,
    },
    descriptionLabel: {
        fontSize: 11,
        marginBottom: 4,
    },
    descriptionText: {
        fontSize: 12,
        lineHeight: 18,
    },
};

export default AIImageModal;
