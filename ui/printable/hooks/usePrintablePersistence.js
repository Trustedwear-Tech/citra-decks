// useprintablePersistence.js - Hook for saving and loading printables
import { useState, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEYS = {
  printableS: '@citra_ai_printables',
  CURRENT_printable: '@citra_ai_current_printable',
  AUTO_SAVE: '@citra_ai_printable_auto_save',
  STYLE_PRESETS: '@citra_ai_printable_styles'
};

export const usePrintablePersistence = () => {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [error, setError] = useState(null);

  const autoSaveTimeoutRef = useRef(null);
  
  // Teams removed — every artifact lives in the personal workspace.
  const activeTeamId = null;

  // Save printable to local storage
  const saveprintable = useCallback(async (printableData, printableId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const printable = {
        id: printableId || printableData.metadata?.id || `printable_${Date.now()}`,
        ...printableData,
        savedAt: new Date().toISOString()
      };

      // Save individual printable - DISABLED to prevent QuotaExceededError
      // User explicitly requested to rely on server storage
      /* 
      await AsyncStorage.setItem(
        `${STORAGE_KEYS.printableS}_${printable.id}`,
        JSON.stringify(printable)
      );
      */

      /* 
      // DISABLED: User requested to rely strictly on server. 
      // The printableListModal fetches from server, so local index is not needed.

      // Update printables index (Keep this for "Recent Files" list)
      const existingprintablesJson = await AsyncStorage.getItem(STORAGE_KEYS.printableS);
      const existingprintables = existingprintablesJson ? JSON.parse(existingprintablesJson) : [];

      const printableIndex = existingprintables.findIndex(p => p.id === printable.id);
      const printableSummary = {
        id: printable.id,
        title: printable.metadata?.title || 'Untitled printable',
        created_at: printable.metadata?.created_at,
        updated_at: printable.metadata?.updated_at,
        savedAt: printable.savedAt,
        totalPAGES: printable.PAGES?.length || 0,
        style: printable.metadata?.style?.name || null,
        // thumbnail: printable.PAGES?.[0]?.thumbnail || null // Disable thumbnail to save space if needed
      };

      if (printableIndex >= 0) {
        existingprintables[printableIndex] = printableSummary;
      } else {
        existingprintables.push(printableSummary);
      }

      await AsyncStorage.setItem(STORAGE_KEYS.printableS, JSON.stringify(existingprintables));
      */

      // Save as current printable
      await AsyncStorage.setItem(STORAGE_KEYS.CURRENT_printable, printable.id);

      setLastSaved(new Date().toISOString());
      console.log('✅ printable saved successfully:', printable.id);

      return printable.id;
    } catch (err) {
      console.error('❌ Failed to save printable:', err);
      setError('Failed to save printable');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, []);

  // Load printable from local storage
  const loadprintable = useCallback(async (printableId) => {
    try {
      setIsLoading(true);
      setError(null);

      const printableJson = await AsyncStorage.getItem(`${STORAGE_KEYS.printableS}_${printableId}`);

      if (!printableJson) {
        throw new Error('printable not found');
      }

      const printable = JSON.parse(printableJson);
      console.log('✅ printable loaded successfully:', printableId);

      return printable;
    } catch (err) {
      console.error('❌ Failed to load printable:', err);
      setError('Failed to load printable');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-save with debouncing - DISABLED by user request
  const autoSave = useCallback(async (printableData, printableId = null) => {
    // Autosave disabled to prevent quota issues and per user preference
    // console.log('🚫 [printable_PERSISTENCE] Autosave disabled');
    return;
  }, []);

  // Load auto-saved data
  const loadAutoSave = useCallback(async (printableId = 'current') => {
    try {
      const autoSaveJson = await AsyncStorage.getItem(`${STORAGE_KEYS.AUTO_SAVE}_${printableId}`);

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
  const clearAutoSave = useCallback(async (printableId = 'current') => {
    try {
      await AsyncStorage.removeItem(`${STORAGE_KEYS.AUTO_SAVE}_${printableId}`);
      console.log('🗑️ Auto-save data cleared');
    } catch (err) {
      console.error('❌ Failed to clear auto-save:', err);
    }
  }, []);

  // Get all saved printables
  const getAllprintables = useCallback(async () => {
    try {
      setIsLoading(true);
      const printablesJson = await AsyncStorage.getItem(STORAGE_KEYS.printableS);
      const printables = printablesJson ? JSON.parse(printablesJson) : [];

      // Sort by updated date (most recent first)
      return printables.sort((a, b) =>
        new Date(b.updated_at || b.savedAt) - new Date(a.updated_at || a.savedAt)
      );
    } catch (err) {
      console.error('❌ Failed to get printables:', err);
      setError('Failed to load printables');
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Delete printable
  const deleteprintable = useCallback(async (printableId) => {
    try {
      // Remove individual printable
      await AsyncStorage.removeItem(`${STORAGE_KEYS.printableS}_${printableId}`);

      // Remove from index
      const printablesJson = await AsyncStorage.getItem(STORAGE_KEYS.printableS);
      const printables = printablesJson ? JSON.parse(printablesJson) : [];
      const updatedprintables = printables.filter(p => p.id !== printableId);
      await AsyncStorage.setItem(STORAGE_KEYS.printableS, JSON.stringify(updatedprintables));

      // Clear auto-save if it exists
      await clearAutoSave(printableId);

      console.log('🗑️ printable deleted:', printableId);
    } catch (err) {
      console.error('❌ Failed to delete printable:', err);
      setError('Failed to delete printable');
      throw err;
    }
  }, [clearAutoSave]);

  // Duplicate printable
  const duplicateprintable = useCallback(async (printableId) => {
    try {
      const originalprintable = await loadprintable(printableId);
      const duplicatedprintable = {
        ...originalprintable,
        id: `printable_${Date.now()}`,
        metadata: {
          ...originalprintable.metadata,
          id: `printable_${Date.now()}`,
          title: `${originalprintable.metadata?.title || 'Untitled printable'} (Copy)`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        PAGES: originalprintable.PAGES?.map(PAGE => ({
          ...PAGE,
          id: `PAGE_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          elements: PAGE.elements?.map(el => ({
            ...el,
            id: `element_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          })) || [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newprintableId = await saveprintable(duplicatedprintable);
      console.log('📄 printable duplicated:', newprintableId);

      return newprintableId;
    } catch (err) {
      console.error('❌ Failed to duplicate printable:', err);
      setError('Failed to duplicate printable');
      throw err;
    }
  }, [loadprintable, saveprintable]);

  // Export printable data
  const exportprintableData = useCallback(async (printableId) => {
    try {
      const printable = await loadprintable(printableId);
      const exportData = {
        ...printable,
        exportedAt: new Date().toISOString(),
        version: '1.0'
      };

      return JSON.stringify(exportData, null, 2);
    } catch (err) {
      console.error('❌ Failed to export printable:', err);
      setError('Failed to export printable');
      throw err;
    }
  }, [loadprintable]);

  // Import printable data
  const importprintableData = useCallback(async (printableDataJson) => {
    try {
      const printableData = JSON.parse(printableDataJson);

      // Generate new IDs to avoid conflicts
      const importedprintable = {
        ...printableData,
        id: `printable_${Date.now()}`,
        metadata: {
          ...printableData.metadata,
          id: `printable_${Date.now()}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        PAGES: printableData.PAGES?.map(PAGE => ({
          ...PAGE,
          id: `PAGE_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          elements: PAGE.elements?.map(el => ({
            ...el,
            id: `element_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          })) || [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newprintableId = await saveprintable(importedprintable);
      console.log('📥 printable imported:', newprintableId);

      return newprintableId;
    } catch (err) {
      console.error('❌ Failed to import printable:', err);
      setError('Failed to import printable');
      throw err;
    }
  }, [saveprintable]);

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

  // Save printable to server
  const saveprintableToServer = useCallback(async (printableData, apiConfig, printableId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /printable/save endpoint (POST) for both create and update
      const url = `${apiConfig.API_URL}/printable/save`;

      const payload = {
        id: printableId || null,  // If null, backend creates new; if set, backend updates
        team_id: activeTeamId || null,  // Include team_id for workspace association
        title: printableData.printableMetadata?.title || 'Untitled printable',
        goal: printableData.printableGoal || null,
        PAGES: printableData.PAGES || [],
        style: printableData.printableMetadata?.style || null,
        thumbnail: printableData.thumbnail || null, // First PAGE thumbnail for printable list
        folder_ids: printableData.folderIds || null,
      };

      // Aggressive Logging: Payload Analysis
      const PAGECount = payload.PAGES.length;
      const elementCounts = payload.PAGES.map(s => s.elements?.length || 0);
      const totalElements = elementCounts.reduce((a, b) => a + b, 0);
      const imageElements = payload.PAGES.flatMap(s => s.elements || []).filter(e => e.type === 'image');
      const iconElements = payload.PAGES.flatMap(s => s.elements || []).filter(e => e.type === 'icon');

      console.log('💾 [SAVE_printable] Initiating Save...', {
        url,
        printableId,
        title: payload.title,
        PAGECount,
        totalElements,
        imageCount: imageElements.length,
        iconCount: iconElements.length,
        PAGEElementCounts: elementCounts
      });

      // Sanity Check
      if (PAGECount === 0) {
        console.warn('⚠️ [SAVE_printable] Saving printable with 0 PAGES! Is this intended?');
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
        console.log('✅ [SAVE_printable] Server confirmed save:', data.id);
        return { id: data.id, pages: data.pages || null };
      } else {
        const errorText = await response.text();
        console.error('❌ [SAVE_printable] Server rejected save:', {
          status: response.status,
          statusText: response.statusText,
          errorBody: errorText
        });
        throw new Error(`Server save failed: ${response.status} ${errorText}`);
      }
    } catch (err) {
      console.error('❌ [SAVE_printable] Network/Client Error:', err);
      setError('Failed to save printable');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, [activeTeamId]);

  // Load printable from server
  const loadprintableFromServer = useCallback(async (printableId, apiConfig) => {
    try {
      setIsLoading(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /printable/load/{id}?user_id=xxx
      const response = await fetch(`${apiConfig.API_URL}/printable/load/${printableId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('✅ printable loaded from server:', printableId);
        return data.printable;
      } else {
        throw new Error('Server load failed');
      }
    } catch (err) {
      console.error('❌ Failed to load from server:', err);
      setError('Failed to load printable');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Get all printables from server
  const getAllprintablesFromServer = useCallback(async (apiConfig) => {
    try {
      setIsLoading(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      // Backend uses /printable/list?user_id=xxx
      const response = await fetch(`${apiConfig.API_URL}/printable/list`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('✅ printables loaded from server:', data.printables?.length);
        return data.printables || [];
      } else {
        throw new Error('Server load failed');
      }
    } catch (err) {
      console.error('❌ Failed to load printables from server:', err);
      setError('Failed to load printables');
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Delete printable from server
  const deleteprintableFromServer = useCallback(async (printableId, apiConfig) => {
    try {
      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${apiConfig.API_URL}/printable/${printableId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        console.log('🗑️ printable deleted from server:', printableId);
        return true;
      } else {
        throw new Error('Server delete failed');
      }
    } catch (err) {
      console.error('❌ Failed to delete from server:', err);
      setError('Failed to delete printable');
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
    savePrintable: saveprintable,
    loadPrintable: loadprintable,
    autoSave,

    // Auto-save utilities
    loadAutoSave,
    clearAutoSave,

    // Printable management (local)
    getAllPrintables: getAllprintables,
    deletePrintable: deleteprintable,
    duplicatePrintable: duplicateprintable,

    // Import/Export
    exportPrintableData: exportprintableData,
    importPrintableData: importprintableData,

    // Style presets
    saveStylePreset,
    getCustomStylePresets,
    deleteStylePreset,

    // Server-side persistence (MongoDB)
    savePrintableToServer: saveprintableToServer,
    loadPrintableFromServer: loadprintableFromServer,
    getAllPrintablesFromServer: getAllprintablesFromServer,
    deletePrintableFromServer: deleteprintableFromServer,

    // Cleanup
    clearError: () => setError(null)
  };
};

export default usePrintablePersistence;
