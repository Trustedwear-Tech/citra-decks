// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// usePresentationPersistence.js - Hook for saving and loading presentations
import { useState, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEYS = {
  PRESENTATIONS: '@citra_ai_presentations',
  CURRENT_PRESENTATION: '@citra_ai_current_presentation',
  AUTO_SAVE: '@citra_ai_presentation_auto_save',
  STYLE_PRESETS: '@citra_ai_presentation_styles'
};

export const usePresentationPersistence = () => {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [error, setError] = useState(null);

  const autoSaveTimeoutRef = useRef(null);
  
  // Teams removed — every artifact lives in the personal workspace.
  const activeTeamId = null;

  // Save presentation to local storage
  const savePresentation = useCallback(async (presentationData, presentationId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const presentation = {
        id: presentationId || presentationData.metadata?.id || `presentation_${Date.now()}`,
        ...presentationData,
        savedAt: new Date().toISOString()
      };

      // Save individual presentation - DISABLED to prevent QuotaExceededError
      // User explicitly requested to rely on server storage
      /* 
      await AsyncStorage.setItem(
        `${STORAGE_KEYS.PRESENTATIONS}_${presentation.id}`,
        JSON.stringify(presentation)
      );
      */

      /* 
      // DISABLED: User requested to rely strictly on server. 
      // The PresentationListModal fetches from server, so local index is not needed.

      // Update presentations index (Keep this for "Recent Files" list)
      const existingPresentationsJson = await AsyncStorage.getItem(STORAGE_KEYS.PRESENTATIONS);
      const existingPresentations = existingPresentationsJson ? JSON.parse(existingPresentationsJson) : [];

      const presentationIndex = existingPresentations.findIndex(p => p.id === presentation.id);
      const presentationSummary = {
        id: presentation.id,
        title: presentation.metadata?.title || 'Untitled Presentation',
        created_at: presentation.metadata?.created_at,
        updated_at: presentation.metadata?.updated_at,
        savedAt: presentation.savedAt,
        totalSlides: presentation.slides?.length || 0,
        style: presentation.metadata?.style?.name || null,
        // thumbnail: presentation.slides?.[0]?.thumbnail || null // Disable thumbnail to save space if needed
      };

      if (presentationIndex >= 0) {
        existingPresentations[presentationIndex] = presentationSummary;
      } else {
        existingPresentations.push(presentationSummary);
      }

      await AsyncStorage.setItem(STORAGE_KEYS.PRESENTATIONS, JSON.stringify(existingPresentations));
      */

      // Save as current presentation
      await AsyncStorage.setItem(STORAGE_KEYS.CURRENT_PRESENTATION, presentation.id);

      setLastSaved(new Date().toISOString());
      console.log('✅ Presentation saved successfully:', presentation.id);

      return presentation.id;
    } catch (err) {
      console.error('❌ Failed to save presentation:', err);
      setError('Failed to save presentation');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, []);

  // Load presentation from local storage
  const loadPresentation = useCallback(async (presentationId) => {
    try {
      setIsLoading(true);
      setError(null);

      const presentationJson = await AsyncStorage.getItem(`${STORAGE_KEYS.PRESENTATIONS}_${presentationId}`);

      if (!presentationJson) {
        throw new Error('Presentation not found');
      }

      const presentation = JSON.parse(presentationJson);
      console.log('✅ Presentation loaded successfully:', presentationId);

      return presentation;
    } catch (err) {
      console.error('❌ Failed to load presentation:', err);
      setError('Failed to load presentation');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-save with debouncing - DISABLED by user request
  const autoSave = useCallback(async (presentationData, presentationId = null) => {
    // Autosave disabled to prevent quota issues and per user preference
    // console.log('🚫 [PRESENTATION_PERSISTENCE] Autosave disabled');
    return;
  }, []);

  // Load auto-saved data
  const loadAutoSave = useCallback(async (presentationId = 'current') => {
    try {
      const autoSaveJson = await AsyncStorage.getItem(`${STORAGE_KEYS.AUTO_SAVE}_${presentationId}`);

      if (!autoSaveJson) {
        return null;
      }

      const autoSaveData = JSON.parse(autoSaveJson);
      console.log('📂 Auto-save data loaded');

      return autoSaveData;
    } catch (err) {
      console.error('❌ Failed to load auto-save:', err);
      return null;
    }
  }, []);

  // Clear auto-save data
  const clearAutoSave = useCallback(async (presentationId = 'current') => {
    try {
      await AsyncStorage.removeItem(`${STORAGE_KEYS.AUTO_SAVE}_${presentationId}`);
      console.log('🗑️ Auto-save data cleared');
    } catch (err) {
      console.error('❌ Failed to clear auto-save:', err);
    }
  }, []);

  // Get all saved presentations
  const getAllPresentations = useCallback(async () => {
    try {
      setIsLoading(true);
      const presentationsJson = await AsyncStorage.getItem(STORAGE_KEYS.PRESENTATIONS);
      const presentations = presentationsJson ? JSON.parse(presentationsJson) : [];

      // Sort by updated date (most recent first)
      return presentations.sort((a, b) =>
        new Date(b.updated_at || b.savedAt) - new Date(a.updated_at || a.savedAt)
      );
    } catch (err) {
      console.error('❌ Failed to get presentations:', err);
      setError('Failed to load presentations');
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Delete presentation
  const deletePresentation = useCallback(async (presentationId) => {
    try {
      // Remove individual presentation
      await AsyncStorage.removeItem(`${STORAGE_KEYS.PRESENTATIONS}_${presentationId}`);

      // Remove from index
      const presentationsJson = await AsyncStorage.getItem(STORAGE_KEYS.PRESENTATIONS);
      const presentations = presentationsJson ? JSON.parse(presentationsJson) : [];
      const updatedPresentations = presentations.filter(p => p.id !== presentationId);
      await AsyncStorage.setItem(STORAGE_KEYS.PRESENTATIONS, JSON.stringify(updatedPresentations));

      // Clear auto-save if it exists
      await clearAutoSave(presentationId);

      console.log('🗑️ Presentation deleted:', presentationId);
    } catch (err) {
      console.error('❌ Failed to delete presentation:', err);
      setError('Failed to delete presentation');
      throw err;
    }
  }, [clearAutoSave]);

  // Duplicate presentation
  const duplicatePresentation = useCallback(async (presentationId) => {
    try {
      const originalPresentation = await loadPresentation(presentationId);
      const duplicatedPresentation = {
        ...originalPresentation,
        id: `presentation_${Date.now()}`,
        metadata: {
          ...originalPresentation.metadata,
          id: `presentation_${Date.now()}`,
          title: `${originalPresentation.metadata?.title || 'Untitled Presentation'} (Copy)`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        slides: originalPresentation.slides?.map(slide => ({
          ...slide,
          id: `slide_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          elements: slide.elements?.map(el => ({
            ...el,
            id: `element_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          })) || [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newPresentationId = await savePresentation(duplicatedPresentation);
      console.log('📄 Presentation duplicated:', newPresentationId);

      return newPresentationId;
    } catch (err) {
      console.error('❌ Failed to duplicate presentation:', err);
      setError('Failed to duplicate presentation');
      throw err;
    }
  }, [loadPresentation, savePresentation]);

  // Export presentation data
  const exportPresentationData = useCallback(async (presentationId) => {
    try {
      const presentation = await loadPresentation(presentationId);
      const exportData = {
        ...presentation,
        exportedAt: new Date().toISOString(),
        version: '1.0'
      };

      return JSON.stringify(exportData, null, 2);
    } catch (err) {
      console.error('❌ Failed to export presentation:', err);
      setError('Failed to export presentation');
      throw err;
    }
  }, [loadPresentation]);

  // Import presentation data
  const importPresentationData = useCallback(async (presentationDataJson) => {
    try {
      const presentationData = JSON.parse(presentationDataJson);

      // Generate new IDs to avoid conflicts
      const importedPresentation = {
        ...presentationData,
        id: `presentation_${Date.now()}`,
        metadata: {
          ...presentationData.metadata,
          id: `presentation_${Date.now()}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        slides: presentationData.slides?.map(slide => ({
          ...slide,
          id: `slide_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          elements: slide.elements?.map(el => ({
            ...el,
            id: `element_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          })) || [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newPresentationId = await savePresentation(importedPresentation);
      console.log('📥 Presentation imported:', newPresentationId);

      return newPresentationId;
    } catch (err) {
      console.error('❌ Failed to import presentation:', err);
      setError('Failed to import presentation');
      throw err;
    }
  }, [savePresentation]);

  // ===== STYLE PRESET MANAGEMENT =====

  // Save custom style preset
  const saveStylePreset = useCallback(async (styleData) => {
    try {
      const presetsJson = await AsyncStorage.getItem(STORAGE_KEYS.STYLE_PRESETS);
      const presets = presetsJson ? JSON.parse(presetsJson) : [];

      const newPreset = {
        id: `style_${Date.now()}`,
        ...styleData,
        isCustom: true,
        created_at: new Date().toISOString()
      };

      presets.push(newPreset);
      await AsyncStorage.setItem(STORAGE_KEYS.STYLE_PRESETS, JSON.stringify(presets));

      console.log('✅ Style preset saved:', newPreset.id);
      return newPreset.id;
    } catch (err) {
      console.error('❌ Failed to save style preset:', err);
      throw err;
    }
  }, []);

  // Get all style presets (custom)
  const getCustomStylePresets = useCallback(async () => {
    try {
      const presetsJson = await AsyncStorage.getItem(STORAGE_KEYS.STYLE_PRESETS);
      return presetsJson ? JSON.parse(presetsJson) : [];
    } catch (err) {
      console.error('❌ Failed to get style presets:', err);
      return [];
    }
  }, []);

  // Delete style preset
  const deleteStylePreset = useCallback(async (presetId) => {
    try {
      const presetsJson = await AsyncStorage.getItem(STORAGE_KEYS.STYLE_PRESETS);
      const presets = presetsJson ? JSON.parse(presetsJson) : [];
      const updatedPresets = presets.filter(p => p.id !== presetId);
      await AsyncStorage.setItem(STORAGE_KEYS.STYLE_PRESETS, JSON.stringify(updatedPresets));
      console.log('🗑️ Style preset deleted:', presetId);
    } catch (err) {
      console.error('❌ Failed to delete style preset:', err);
      throw err;
    }
  }, []);

  // ===== SERVER-SIDE PERSISTENCE (MongoDB) =====

  // Save presentation to server
  const savePresentationToServer = useCallback(async (presentationData, userId, apiConfig, presentationId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /presentation/save endpoint (POST) for both create and update
      const url = `${apiConfig.API_URL}/presentation/save`;

      const payload = {
        id: presentationId || null,  // If null, backend creates new; if set, backend updates
        user_id: userId,
        team_id: activeTeamId || null,  // Include team_id for workspace association
        title: presentationData.presentationMetadata?.title || 'Untitled Presentation',
        goal: presentationData.presentationGoal || null,
        slides: presentationData.slides || [],
        style: presentationData.presentationMetadata?.style || null,
        thumbnail: presentationData.thumbnail || null, // First slide thumbnail for presentation list
        folder_ids: presentationData.folderIds || null,
      };

      // Aggressive Logging: Payload Analysis
      const slideCount = payload.slides.length;
      const elementCounts = payload.slides.map(s => s.elements?.length || 0);
      const totalElements = elementCounts.reduce((a, b) => a + b, 0);
      const imageElements = payload.slides.flatMap(s => s.elements || []).filter(e => e.type === 'image');
      const iconElements = payload.slides.flatMap(s => s.elements || []).filter(e => e.type === 'icon');

      console.log('💾 [SAVE_PRESENTATION] Initiating Save...', {
        url,
        presentationId,
        title: payload.title,
        slideCount,
        totalElements,
        imageCount: imageElements.length,
        iconCount: iconElements.length,
        slideElementCounts: elementCounts
      });

      // Sanity Check
      if (slideCount === 0) {
        console.warn('⚠️ [SAVE_PRESENTATION] Saving presentation with 0 slides! Is this intended?');
      }

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const data = await response.json();
        setLastSaved(new Date().toISOString());
        console.log('✅ [SAVE_PRESENTATION] Server confirmed save:', data.id);
        return { id: data.id, slides: data.slides || null };
      } else {
        const errorText = await response.text();
        console.error('❌ [SAVE_PRESENTATION] Server rejected save:', {
          status: response.status,
          statusText: response.statusText,
          errorBody: errorText
        });
        throw new Error(`Server save failed: ${response.status} ${errorText}`);
      }
    } catch (err) {
      console.error('❌ [SAVE_PRESENTATION] Network/Client Error:', err);
      setError('Failed to save presentation');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, [activeTeamId]);

  // Load presentation from server
  const loadPresentationFromServer = useCallback(async (presentationId, userId, apiConfig) => {
    try {
      setIsLoading(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /presentation/load/{id}?user_id=xxx
      const response = await fetch(`${apiConfig.API_URL}/presentation/load/${presentationId}?user_id=${encodeURIComponent(userId)}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('✅ Presentation loaded from server:', presentationId);
        return data.presentation;
      } else {
        throw new Error('Server load failed');
      }
    } catch (err) {
      console.error('❌ Failed to load from server:', err);
      setError('Failed to load presentation');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Get all presentations from server
  const getAllPresentationsFromServer = useCallback(async (userId, apiConfig) => {
    try {
      setIsLoading(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /presentation/list?user_id=xxx
      const response = await fetch(`${apiConfig.API_URL}/presentation/list?user_id=${encodeURIComponent(userId)}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('✅ Presentations loaded from server:', data.presentations?.length);
        return data.presentations || [];
      } else {
        throw new Error('Server load failed');
      }
    } catch (err) {
      console.error('❌ Failed to load presentations from server:', err);
      setError('Failed to load presentations');
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Delete presentation from server
  const deletePresentationFromServer = useCallback(async (presentationId, apiConfig) => {
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${apiConfig.API_URL}/presentation/${presentationId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        console.log('🗑️ Presentation deleted from server:', presentationId);
        return true;
      } else {
        throw new Error('Server delete failed');
      }
    } catch (err) {
      console.error('❌ Failed to delete from server:', err);
      setError('Failed to delete presentation');
      throw err;
    }
  }, []);

  return {
    // State
    isSaving,
    isLoading,
    lastSaved,
    error,

    // Core operations (local)
    savePresentation,
    loadPresentation,
    autoSave,

    // Auto-save utilities
    loadAutoSave,
    clearAutoSave,

    // Presentation management (local)
    getAllPresentations,
    deletePresentation,
    duplicatePresentation,

    // Import/Export
    exportPresentationData,
    importPresentationData,

    // Style presets
    saveStylePreset,
    getCustomStylePresets,
    deleteStylePreset,

    // Server-side persistence (MongoDB)
    savePresentationToServer,
    loadPresentationFromServer,
    getAllPresentationsFromServer,
    deletePresentationFromServer,

    // Cleanup
    clearError: () => setError(null)
  };
};

export default usePresentationPersistence;
