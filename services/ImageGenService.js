// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import config from '../config/config';
import authService from './authService';

// Default model for all image operations — configured via IMAGE_GEN_MODEL on the backend
const IMAGE_GEN_MODELS = {
    DEFAULT: null, // Use backend default
    EDIT: null,    // Use backend default
};

const ImageGenService = {
    /**
     * Generate an image using the image generation API
     * @param {string} prompt - Image generation prompt
     * @param {Object} options - Options (width, height, style, model, imageType)
     * @returns {Promise<Object>} - Response with image URL
     */
    generateImage: async (prompt, options = {}) => {
        try {
            const {
                width = 1024,
                height = 1024,
                model = null, // Will be determined by imageType if not provided
                imageType = 'photo', // 'photo' | 'infographic' | 'photo_with_text'
                generationQuality = 'premium', // 'basic' | 'medium' | 'premium'
            } = options;

            // Model selection - backend uses IMAGE_GEN_MODEL env var as default
            let selectedModel = model || IMAGE_GEN_MODELS.DEFAULT;
            console.log(`ðŸ–¼ï¸ [IMAGE_GEN] Model: ${selectedModel} (imageType: ${imageType}, quality: ${generationQuality}, modelOverride: ${!!model})`);

            console.log('ðŸ–¼ï¸ [IMAGE_GEN] Using image generation backend, model:', selectedModel);

            // Use authenticatedFetch (not Json) to handle 429 rate limit explicitly
            const response = await authService.authenticatedFetch(`${config.CITRA_SERVICE_URL}/image-gen/generate`, {
                method: 'POST',
                body: JSON.stringify({
                    prompt,
                    width,
                    height,
                    model: selectedModel
                })
            });

            if (response.status === 429) {
                const retryAfter = response.headers?.get('Retry-After');
                throw new Error(`429 Rate limit exceeded${retryAfter ? ` (retry after ${retryAfter}s)` : ''}`);
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Image generation failed:', error);
            throw error;
        }
    },

    /**
     * Edit an existing image using the image generation API (image-to-image via seedImage)
     * @param {string} prompt - Edit instruction prompt
     * @param {Object} options - Options (sourceImage, width, height, imageType, strength)
     * @returns {Promise<Object>} - Response with edited image URL
     */
    editImage: async (prompt, options = {}) => {
        try {
            const {
                sourceImage,
                width = 1024,
                height = 1024,
                model = null,
                imageType = 'photo',
                generationQuality = 'premium',
                strength = 0.7,
            } = options;

            if (!sourceImage) {
                throw new Error('sourceImage is required for image editing');
            }

            // Model selection - backend uses IMAGE_GEN_MODEL env var as default
            let selectedModel = model || IMAGE_GEN_MODELS.EDIT;
            let includeStrength = true;
            console.log(`ðŸ–¼ï¸ [IMAGE_EDIT] Model: ${selectedModel} (imageType: ${imageType}, modelOverride: ${!!model}, strength: ${includeStrength ? strength : 'N/A'})`);

            console.log('ðŸ–¼ï¸ [IMAGE_EDIT] Editing image via backend, model:', selectedModel, 'strength:', includeStrength ? strength : 'N/A (omitted)');

            // Build request body â€” only include strength for models that support it
            const requestBody = {
                prompt,
                source_image: sourceImage,
                width,
                height,
                model: selectedModel,
                image_type: imageType,
            };
            if (includeStrength) {
                requestBody.strength = strength;
            }

            const response = await authService.authenticatedFetch(`${config.CITRA_SERVICE_URL}/image-gen/edit`, {
                method: 'POST',
                body: JSON.stringify(requestBody)
            });

            if (response.status === 429) {
                const retryAfter = response.headers?.get('Retry-After');
                throw new Error(`429 Rate limit exceeded${retryAfter ? ` (retry after ${retryAfter}s)` : ''}`);
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Image edit failed:', error);
            throw error;
        }
    }
};

export default ImageGenService;
