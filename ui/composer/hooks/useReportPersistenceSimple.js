// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// Simple useReportPersistence hook for debugging
import { useState, useCallback } from 'react';

export const useReportPersistence = () => {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [error, setError] = useState(null);

  const saveReport = useCallback(async (reportData, reportId = null) => {
    setIsSaving(true);
    try {
      // Simulate save
      await new Promise(resolve => setTimeout(resolve, 500));
      setLastSaved(new Date().toISOString());
      console.log('Report saved:', reportData);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, []);

  const loadReport = useCallback(async (reportId) => {
    setIsLoading(true);
    try {
      // Simulate load
      await new Promise(resolve => setTimeout(resolve, 500));
      return null; // No saved report for now
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const autoSave = useCallback(async (reportData) => {
    // Simple auto-save implementation
    console.log('Auto-saving:', reportData);
  }, []);

  return {
    saveReport,
    loadReport,
    autoSave,
    isSaving,
    isLoading,
    lastSaved,
    error
  };
};
