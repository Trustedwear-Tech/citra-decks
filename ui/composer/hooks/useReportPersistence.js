// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// useReportPersistence.js - Hook for saving and loading reports
import { useState, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEYS = {
  REPORTS: '@citra_ai_reports',
  CURRENT_REPORT: '@citra_ai_current_report',
  AUTO_SAVE: '@citra_ai_auto_save'
};

export const useReportPersistence = () => {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [error, setError] = useState(null);

  const autoSaveTimeoutRef = useRef(null);
  
  // Teams removed — every artifact lives in the personal workspace.
  const activeTeamId = null;

  // Save report to local storage
  const saveReport = useCallback(async (reportData, reportId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const report = {
        id: reportId || reportData.metadata?.id || `report_${Date.now()}`,
        ...reportData,
        savedAt: new Date().toISOString()
      };

      // Save individual report
      await AsyncStorage.setItem(
        `${STORAGE_KEYS.REPORTS}_${report.id}`,
        JSON.stringify(report)
      );

      // Update reports index
      const existingReportsJson = await AsyncStorage.getItem(STORAGE_KEYS.REPORTS);
      const existingReports = existingReportsJson ? JSON.parse(existingReportsJson) : [];

      const reportIndex = existingReports.findIndex(r => r.id === report.id);
      const reportSummary = {
        id: report.id,
        title: report.metadata?.title || 'Untitled Report',
        created_at: report.metadata?.created_at,
        updated_at: report.metadata?.updated_at,
        savedAt: report.savedAt,
        totalPages: report.pages?.length || 0,
        totalWordCount: report.pages?.reduce((sum, page) => sum + (page.wordCount || 0), 0) || 0
      };

      if (reportIndex >= 0) {
        existingReports[reportIndex] = reportSummary;
      } else {
        existingReports.push(reportSummary);
      }

      await AsyncStorage.setItem(STORAGE_KEYS.REPORTS, JSON.stringify(existingReports));

      // Save as current report
      await AsyncStorage.setItem(STORAGE_KEYS.CURRENT_REPORT, report.id);

      setLastSaved(new Date().toISOString());
      console.log('✅ Report saved successfully:', report.id);

      return report.id;
    } catch (err) {
      console.error('❌ Failed to save report:', err);
      setError('Failed to save report');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, []);

  // Load report from local storage
  const loadReport = useCallback(async (reportId) => {
    try {
      setIsLoading(true);
      setError(null);

      const reportJson = await AsyncStorage.getItem(`${STORAGE_KEYS.REPORTS}_${reportId}`);

      if (!reportJson) {
        throw new Error('Report not found');
      }

      const report = JSON.parse(reportJson);
      console.log('✅ Report loaded successfully:', reportId);

      return report;
    } catch (err) {
      console.error('❌ Failed to load report:', err);
      setError('Failed to load report');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-save with debouncing - DISABLED by user request
  const autoSave = useCallback(async (reportData, reportId = null) => {
    // Autosave disabled to prevent quota issues and per user preference
    // console.log('🚫 [PERSISTENCE] Autosave disabled');
    return;
  }, []);

  // Load auto-saved data
  const loadAutoSave = useCallback(async (reportId = 'current') => {
    try {
      const autoSaveJson = await AsyncStorage.getItem(`${STORAGE_KEYS.AUTO_SAVE}_${reportId}`);

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
  const clearAutoSave = useCallback(async (reportId = 'current') => {
    try {
      await AsyncStorage.removeItem(`${STORAGE_KEYS.AUTO_SAVE}_${reportId}`);
      console.log('🗑️ Auto-save data cleared');
    } catch (err) {
      console.error('❌ Failed to clear auto-save:', err);
    }
  }, []);

  // Get all saved reports
  const getAllReports = useCallback(async () => {
    try {
      setIsLoading(true);
      const reportsJson = await AsyncStorage.getItem(STORAGE_KEYS.REPORTS);
      const reports = reportsJson ? JSON.parse(reportsJson) : [];

      // Sort by updated date (most recent first)
      return reports.sort((a, b) =>
        new Date(b.updated_at || b.savedAt) - new Date(a.updated_at || a.savedAt)
      );
    } catch (err) {
      console.error('❌ Failed to get reports:', err);
      setError('Failed to load reports');
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Delete report
  const deleteReport = useCallback(async (reportId) => {
    try {
      // Remove individual report
      await AsyncStorage.removeItem(`${STORAGE_KEYS.REPORTS}_${reportId}`);

      // Remove from index
      const reportsJson = await AsyncStorage.getItem(STORAGE_KEYS.REPORTS);
      const reports = reportsJson ? JSON.parse(reportsJson) : [];
      const updatedReports = reports.filter(r => r.id !== reportId);
      await AsyncStorage.setItem(STORAGE_KEYS.REPORTS, JSON.stringify(updatedReports));

      // Clear auto-save if it exists
      await clearAutoSave(reportId);

      console.log('🗑️ Report deleted:', reportId);
    } catch (err) {
      console.error('❌ Failed to delete report:', err);
      setError('Failed to delete report');
      throw err;
    }
  }, [clearAutoSave]);

  // Duplicate report
  const duplicateReport = useCallback(async (reportId) => {
    try {
      const originalReport = await loadReport(reportId);
      const duplicatedReport = {
        ...originalReport,
        id: `report_${Date.now()}`,
        metadata: {
          ...originalReport.metadata,
          id: `report_${Date.now()}`,
          title: `${originalReport.metadata?.title || 'Untitled Report'} (Copy)`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        pages: originalReport.pages?.map(page => ({
          ...page,
          id: `page_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newReportId = await saveReport(duplicatedReport);
      console.log('📄 Report duplicated:', newReportId);

      return newReportId;
    } catch (err) {
      console.error('❌ Failed to duplicate report:', err);
      setError('Failed to duplicate report');
      throw err;
    }
  }, [loadReport, saveReport]);

  // Export report data
  const exportReportData = useCallback(async (reportId) => {
    try {
      const report = await loadReport(reportId);
      const exportData = {
        ...report,
        exportedAt: new Date().toISOString(),
        version: '1.0'
      };

      return JSON.stringify(exportData, null, 2);
    } catch (err) {
      console.error('❌ Failed to export report:', err);
      setError('Failed to export report');
      throw err;
    }
  }, [loadReport]);

  // Import report data
  const importReportData = useCallback(async (reportDataJson) => {
    try {
      const reportData = JSON.parse(reportDataJson);

      // Generate new IDs to avoid conflicts
      const importedReport = {
        ...reportData,
        id: `report_${Date.now()}`,
        metadata: {
          ...reportData.metadata,
          id: `report_${Date.now()}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        pages: reportData.pages?.map(page => ({
          ...page,
          id: `page_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: false
        })) || []
      };

      const newReportId = await saveReport(importedReport);
      console.log('📥 Report imported:', newReportId);

      return newReportId;
    } catch (err) {
      console.error('❌ Failed to import report:', err);
      setError('Failed to import report');
      throw err;
    }
  }, [saveReport]);

  // ===== SERVER-SIDE PERSISTENCE (MongoDB) =====

  // Save report to server
  const saveReportToServer = useCallback(async (reportData, apiConfig, reportId = null) => {
    try {
      setIsSaving(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      const url = reportId
        ? `${apiConfig.API_URL}/composer/reports/${reportId}`
        : `${apiConfig.API_URL}/composer/reports`;

      const method = reportId ? 'PUT' : 'POST';

      const payload = {
        team_id: activeTeamId || null,  // Include team_id for workspace association
        title: reportData.reportMetadata?.title || 'Untitled Report',
        goal: reportData.reportGoal?.purpose || null,
        pages: reportData.pages || [],
        metadata: {
          ...(reportData.reportMetadata || {}),
          folder_ids: reportData.folderIds || null,
          // Singular folder_id is what the server persists (see
          // usePresentationPersistence for the full note); sending only the
          // plural silently detached the artifact from its data store.
          folder_id: (reportData.folderIds && reportData.folderIds[0]) || null,
        },
        thumbnail: reportData.thumbnail || null  // First page thumbnail for report list
      };

      console.log('[SAVE_REPORT] Saving report:', { url, method, pageCount: payload.pages.length });
      console.log('[SAVE_REPORT] Pages data:', payload.pages.map(p => ({ id: p.id, title: p.title, contentLength: p.content?.length })));

      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const data = await response.json();
        setLastSaved(new Date().toISOString());
        console.log('✅ Report saved to server:', data.report_id);
        return data.report_id;
      } else {
        throw new Error('Server save failed');
      }
    } catch (err) {
      console.error('❌ Failed to save to server:', err);
      setError('Failed to save report');
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, [activeTeamId]);

  // Load report from server
  const loadReportFromServer = useCallback(async (reportId, apiConfig) => {
    try {
      setIsLoading(true);
      setError(null);

      const token = await AsyncStorage.getItem('@auth_token');
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${apiConfig.API_URL}/composer/reports/${reportId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('✅ Report loaded from server:', reportId);
        return data.report;
      } else {
        throw new Error('Server load failed');
      }
    } catch (err) {
      console.error('❌ Failed to load from server:', err);
      setError('Failed to load report');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    // State
    isSaving,
    isLoading,
    lastSaved,
    error,

    // Core operations (local)
    saveReport,
    loadReport,
    autoSave,

    // Auto-save utilities
    loadAutoSave,
    clearAutoSave,

    // Report management (local)
    getAllReports,
    deleteReport,
    duplicateReport,

    // Import/Export
    exportReportData,
    importReportData,

    // Server-side persistence (MongoDB)
    saveReportToServer,
    loadReportFromServer,

    // Cleanup
    clearError: () => setError(null)
  };
};
