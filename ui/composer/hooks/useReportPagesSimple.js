// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// Simple useReportPages hook for debugging
import { useState } from 'react';

export const useReportPages = (initialReport = null) => {
  const [pages, setPages] = useState([{
    id: 'page-1',
    order: 1,
    title: 'Introduction',
    content: '',
    wordCount: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    hasUnsavedChanges: false
  }]);

  const [currentPageId, setCurrentPageId] = useState('page-1');
  const [reportMetadata, setReportMetadata] = useState({
    id: 'report-1',
    title: 'Untitled Report',
    description: '',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  });

  const addPage = () => {
    const newId = `page-${Date.now()}`;
    const newPage = {
      id: newId,
      order: pages.length + 1,
      title: `Page ${pages.length + 1}`,
      content: '',
      wordCount: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: false
    };
    setPages(prev => [...prev, newPage]);
    return newId;
  };

  const deletePage = (pageId) => {
    setPages(prev => prev.filter(p => p.id !== pageId));
  };

  const insertPage = (insertIndex) => {
    const newId = `page-${Date.now()}`;
    const newPage = {
      id: newId,
      order: insertIndex + 1,
      title: `Page ${insertIndex + 1}`,
      content: '',
      wordCount: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: false
    };
    const newPages = [...pages];
    newPages.splice(insertIndex, 0, newPage);
    setPages(newPages);
    return newId;
  };

  const reorderPages = (fromIndex, toIndex) => {
    const newPages = [...pages];
    const [movedPage] = newPages.splice(fromIndex, 1);
    newPages.splice(toIndex, 0, movedPage);
    setPages(newPages);
  };

  const updatePageContent = (pageId, content) => {
    setPages(prev => prev.map(p => 
      p.id === pageId 
        ? { ...p, content, updated_at: new Date().toISOString(), hasUnsavedChanges: true }
        : p
    ));
  };

  const updatePageTitle = (pageId, title) => {
    setPages(prev => prev.map(p => 
      p.id === pageId 
        ? { ...p, title, updated_at: new Date().toISOString(), hasUnsavedChanges: true }
        : p
    ));
  };

  const updateReportMetadata = (metadata) => {
    setReportMetadata(prev => ({ ...prev, ...metadata }));
  };

  return {
    pages,
    currentPageId,
    setCurrentPageId,
    addPage,
    deletePage,
    insertPage,
    reorderPages,
    updatePageContent,
    updatePageTitle,
    reportMetadata,
    updateReportMetadata
  };
};
