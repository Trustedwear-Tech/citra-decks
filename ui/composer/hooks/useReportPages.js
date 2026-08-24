// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// useReportPages.js - Hook for managing report pages and content
import { useState, useCallback, useRef, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';

// Default header/footer configuration
const DEFAULT_HEADER_CONFIG = {
  enabled: false,
  leftContent: '',
  centerContent: '',
  rightContent: '',
  showOnFirstPage: false,
  showLogo: false,
  logoUrl: '',
};

const DEFAULT_FOOTER_CONFIG = {
  enabled: true,
  leftContent: '',
  centerContent: '',
  rightContent: 'Page {page} of {total}',
  showOnFirstPage: true,
};

// Default layout for new pages
const DEFAULT_LAYOUT = 'single_column';

// Create a page with all fields including layout
const createPage = (overrides = {}) => ({
  id: uuidv4(),
  order: 1,
  title: 'Introduction',
  content: '',
  wordCount: 0,
  layout: DEFAULT_LAYOUT,
  layoutMeta: {}, // Additional layout-specific metadata (e.g., column widths)
  hidden: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  hasUnsavedChanges: false,
  ...overrides,
});

export const useReportPages = (initialReport = null) => {
  // Initialize state from existing report or create new
  const [pages, setPages] = useState(() => {
    if (initialReport?.pages?.length > 0) {
      return initialReport.pages.map(page => ({
        ...createPage(),
        ...page,
        layout: page.layout || DEFAULT_LAYOUT,
      }));
    }
    return [createPage()];
  });

  const [currentPageId, setCurrentPageId] = useState(() => {
    return initialReport?.currentPageId || pages[0]?.id;
  });

  const [reportMetadata, setReportMetadata] = useState(() => ({
    id: initialReport?.id || uuidv4(),
    title: initialReport?.title || 'Untitled Report',
    description: initialReport?.description || '',
    created_at: initialReport?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    overall_goal: initialReport?.overall_goal || '',
    target_audience: initialReport?.target_audience || '',
    style_guide: initialReport?.style_guide || 'professional',
    word_count_target: initialReport?.word_count_target || 'flexible',
    // New layout-related metadata
    reportStyle: initialReport?.reportStyle || 'ai_auto',
    defaultLayout: initialReport?.defaultLayout || 'ai_auto',
    headerConfig: initialReport?.headerConfig || DEFAULT_HEADER_CONFIG,
    footerConfig: initialReport?.footerConfig || DEFAULT_FOOTER_CONFIG,
  }));

  // Handle initialReport changes (when loading an existing report)
  useEffect(() => {
    if (initialReport?.pages?.length > 0) {
      const loadedPages = initialReport.pages.map((page, index) => ({
        id: page.id || uuidv4(),
        order: page.order || index + 1,
        title: page.title || `Page ${index + 1}`,
        content: page.content || '',
        wordCount: (page.content || '').trim().split(/\s+/).filter(w => w.length > 0).length,
        layout: page.layout || DEFAULT_LAYOUT,
        layoutMeta: page.layoutMeta || {},
        created_at: page.created_at || new Date().toISOString(),
        updated_at: page.updated_at || new Date().toISOString(),
        hasUnsavedChanges: false,
        hidden: page.hidden || false,
      }));
      
      setPages(loadedPages);
      
      if (loadedPages.length > 0) {
        setCurrentPageId(loadedPages[0].id);
      }
      
      // Update metadata from loaded report
      setReportMetadata(prev => ({
        ...prev,
        id: initialReport.id || prev.id,
        title: initialReport.title || prev.title,
        description: initialReport.description || prev.description,
        overall_goal: initialReport.goal || initialReport.overall_goal || prev.overall_goal,
        reportStyle: initialReport.reportStyle || prev.reportStyle,
        defaultLayout: initialReport.defaultLayout || prev.defaultLayout,
        headerConfig: initialReport.headerConfig || prev.headerConfig,
        footerConfig: initialReport.footerConfig || prev.footerConfig,
        updated_at: new Date().toISOString()
      }));
    } else if (initialReport === null) {
      // Reset to default for new report
      const defaultPage = createPage({
        id: `page_${Date.now()}`,
        title: 'Page 1',
      });
      setPages([defaultPage]);
      setCurrentPageId(defaultPage.id);
      setReportMetadata({
        id: null,
        title: 'Untitled Report',
        description: '',
        overall_goal: '',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        format: 'document',
        style_guide: 'professional',
        word_count_target: 'flexible',
        reportStyle: 'ai_auto',
        defaultLayout: 'ai_auto',
        headerConfig: DEFAULT_HEADER_CONFIG,
        footerConfig: DEFAULT_FOOTER_CONFIG,
      });
    }
  }, [initialReport]);

  // Count words in text
  const countWords = useCallback((text) => {
    if (!text || typeof text !== 'string') return 0;
    return text.trim().split(/\s+/).filter(word => word.length > 0).length;
  }, []);

  // Add new page
  const addPage = useCallback((insertIndex = pages.length, pageOptions = {}) => {
    const newPage = createPage({
      id: uuidv4(),
      order: insertIndex + 1,
      title: pageOptions.title || `Page ${insertIndex + 1}`,
      content: pageOptions.content || '',
      layout: pageOptions.layout || reportMetadata.defaultLayout || DEFAULT_LAYOUT,
      layoutMeta: pageOptions.layoutMeta || {},
    });

    setPages(currentPages => {
      const updatedPages = [...currentPages];
      updatedPages.splice(insertIndex, 0, newPage);

      // Reorder all pages
      return updatedPages.map((page, index) => ({
        ...page,
        order: index + 1
      }));
    });

    // Set the new page as current
    setCurrentPageId(newPage.id);

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));

    return newPage.id;
  }, [pages.length, reportMetadata.defaultLayout]);

  // Delete page
  const deletePage = useCallback((pageId) => {
    console.log('[REPORT_COMPOSER] deletePage invoked', { pageId });

    let nextPageId = null;

    setPages(currentPages => {
      if (currentPages.length <= 1) {
        console.warn('[REPORT_COMPOSER] Cannot delete the last remaining page');
        return currentPages;
      }

      const filteredPages = currentPages.filter(p => p.id !== pageId);
      nextPageId = filteredPages[0]?.id || null;

      // Reorder remaining pages
      const reorderedPages = filteredPages.map((page, index) => ({
        ...page,
        order: index + 1
      }));

      console.log('[REPORT_COMPOSER] Pages after delete', {
        remaining: reorderedPages.map(p => ({ id: p.id, title: p.title }))
      });

      return reorderedPages;
    });

    // Update current page if the deleted page was active
    setCurrentPageId(prevId => prevId === pageId ? nextPageId : prevId);

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Insert page at specific index
  const insertPage = useCallback((insertIndex, pageOptions = {}) => {
    return addPage(insertIndex, pageOptions);
  }, [addPage]);

  // Update page layout
  const updatePageLayout = useCallback((pageId, layout, layoutMeta = {}) => {
    setPages(currentPages =>
      currentPages.map(page =>
        page.id === pageId
          ? {
            ...page,
            layout,
            layoutMeta: { ...page.layoutMeta, ...layoutMeta },
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true
          }
          : page
      )
    );

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Update letterhead/header/footer configuration
  const updateHeaderFooterConfig = useCallback(({ header, footer, letterhead }) => {
    setReportMetadata(prev => ({
      ...prev,
      headerConfig: header !== undefined ? header : prev.headerConfig,
      footerConfig: footer !== undefined ? footer : prev.footerConfig,
      letterheadConfig: letterhead !== undefined ? letterhead : prev.letterheadConfig,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Update report style
  const updateReportStyle = useCallback((styleId) => {
    setReportMetadata(prev => ({
      ...prev,
      reportStyle: styleId,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Update default layout for new pages
  const updateDefaultLayout = useCallback((layoutId) => {
    setReportMetadata(prev => ({
      ...prev,
      defaultLayout: layoutId,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Update page content
  const updatePageContent = useCallback((pageId, content) => {
    const wordCount = countWords(content);

    setPages(currentPages =>
      currentPages.map(page =>
        page.id === pageId
          ? {
            ...page,
            content,
            wordCount,
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
            isGenerating: false, // Clear generating state when content is updated
          }
          : page
      )
    );

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));
  }, [countWords]);

  // Toggle page hidden state
  const togglePageHidden = useCallback((pageId) => {
    setPages(prev => prev.map(p => p.id === pageId ? { ...p, hidden: !p.hidden } : p));
  }, []);

  // Update page title
  const updatePageTitle = useCallback((pageId, title) => {
    setPages(currentPages =>
      currentPages.map(page =>
        page.id === pageId
          ? {
            ...page,
            title: title.trim() || 'Untitled Page',
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true
          }
          : page
      )
    );

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Reorder pages
  const reorderPages = useCallback((fromIndex, toIndex) => {
    setPages(currentPages => {
      const reorderedPages = [...currentPages];
      const [movedPage] = reorderedPages.splice(fromIndex, 1);
      reorderedPages.splice(toIndex, 0, movedPage);

      // Update order numbers
      return reorderedPages.map((page, index) => ({
        ...page,
        order: index + 1,
        updated_at: new Date().toISOString()
      }));
    });

    // Update report metadata
    setReportMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Update report metadata
  const updateReportMetadata = useCallback((updates) => {
    setReportMetadata(prev => ({
      ...prev,
      ...updates,
      updated_at: new Date().toISOString()
    }));
  }, []);

  // Mark page as saved
  const markPageAsSaved = useCallback((pageId) => {
    setPages(currentPages =>
      currentPages.map(page =>
        page.id === pageId
          ? { ...page, hasUnsavedChanges: false }
          : page
      )
    );
  }, []);

  // Mark all pages as saved
  const markAllPagesSaved = useCallback(() => {
    setPages(currentPages =>
      currentPages.map(page => ({
        ...page,
        hasUnsavedChanges: false
      }))
    );
  }, []);

  // Get page by ID
  const getPageById = useCallback((pageId) => {
    return pages.find(page => page.id === pageId);
  }, [pages]);

  // Get current page
  const getCurrentPage = useCallback(() => {
    return pages.find(page => page.id === currentPageId);
  }, [pages, currentPageId]);

  // Get total word count across all pages
  const getTotalWordCount = useCallback(() => {
    return pages.reduce((total, page) => total + (page.wordCount || 0), 0);
  }, [pages]);

  // Get pages summary for AI context
  const getPagesSummary = useCallback(() => {
    return pages.map(page => ({
      id: page.id,
      title: page.title,
      wordCount: page.wordCount,
      order: page.order,
      summary: page.content ? page.content.substring(0, 200) + '...' : 'Empty page'
    }));
  }, [pages]);

  // Validate current page ID
  useEffect(() => {
    if (currentPageId && !pages.find(p => p.id === currentPageId)) {
      setCurrentPageId(pages[0]?.id || null);
    }
  }, [pages, currentPageId]);

  // Imperative reset for "Create New Report" (works even when initialReport stays null)
  const resetToNew = useCallback(() => {
    const defaultPage = createPage({
      id: `page_${Date.now()}`,
      title: 'Page 1',
    });
    setPages([defaultPage]);
    setCurrentPageId(defaultPage.id);
    setReportMetadata({
      id: null,
      title: 'Untitled Report',
      description: '',
      overall_goal: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      format: 'document',
      style_guide: 'professional',
      word_count_target: 'flexible',
      reportStyle: 'ai_auto',
      defaultLayout: 'ai_auto',
      headerConfig: DEFAULT_HEADER_CONFIG,
      footerConfig: DEFAULT_FOOTER_CONFIG,
    });
  }, []);

  return {
    // State
    pages,
    setPages, // Direct setter for report generation
    currentPageId,
    reportMetadata,

    // Page management
    addPage,
    deletePage,
    insertPage,
    reorderPages,

    // Content management
    updatePageContent,
    updatePageTitle,
    updateReportMetadata,

    // Layout management
    updatePageLayout,
    updateHeaderFooterConfig,
    updateReportStyle,
    updateDefaultLayout,

    // Navigation
    setCurrentPageId,

    // Visibility
    togglePageHidden,

    // Utilities
    getPageById,
    getCurrentPage,
    getTotalWordCount,
    getPagesSummary,
    markPageAsSaved,
    markAllPagesSaved,

    // Reset
    resetToNew,

    // Computed values
    hasUnsavedChanges: pages.some(page => page.hasUnsavedChanges),
    totalPages: pages.length,
    totalWordCount: getTotalWordCount()
  };
};
