// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// URL Router Utilities for Web
// Handles URL-based navigation without changing the UI/UX

import { Platform } from 'react-native';

// Route definitions
export const ROUTES = {
  HOME: '/home',
  PRESENTATION: '/presentation',
  PRINTABLE: '/printable',
  REPORT: '/report',
  DIAGRAM: '/diagram',
  PAGES: '/pages',
  CHAT: '/chat',
  READER: '/reader',
  INVITE: '/invite',
  CREDITS: '/credits',
  PROJECT: '/project',
  VERIFY_EMAIL: '/verify-email',
  RESET_PASSWORD: '/reset-password',
};

/**
 * Parse current URL and return route info
 * @returns {{ route: string, id: string|null, params: object }}
 */
export const parseCurrentUrl = () => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return { route: ROUTES.HOME, id: null, params: {} };
  }

  const path = window.location.pathname;
  const searchParams = new URLSearchParams(window.location.search);
  const params = Object.fromEntries(searchParams.entries());

  // Parse route patterns
  // /presentation/abc123 -> { route: '/presentation', id: 'abc123' }
  // /home -> { route: '/home', id: null }
  // /chat -> { route: '/chat', id: null }

  if (path === '/' || path === '' || path === '/home') {
    return { route: ROUTES.HOME, id: null, params };
  }

  // Check for exact route matches (no ID)
  const exactRoutes = [
    { path: '/chat', route: ROUTES.CHAT },
    { path: '/diagram', route: ROUTES.DIAGRAM },
    { path: '/reader', route: ROUTES.READER },
    { path: '/invite', route: ROUTES.INVITE },
    { path: '/credits', route: ROUTES.CREDITS },
    { path: '/project', route: ROUTES.PROJECT },
    { path: '/verify-email', route: ROUTES.VERIFY_EMAIL },
    { path: '/reset-password', route: ROUTES.RESET_PASSWORD },
  ];

  for (const { path: routePath, route } of exactRoutes) {
    if (path === routePath) {
      return { route, id: null, params };
    }
  }

  // Check for item routes with ID (id can be a tab name like 'internet' or 'personal')
  const itemRoutes = [
    { prefix: '/presentation/', route: ROUTES.PRESENTATION },
    { prefix: '/printable/', route: ROUTES.PRINTABLE },
    { prefix: '/report/', route: ROUTES.REPORT },
    { prefix: '/diagram/', route: ROUTES.DIAGRAM },
    { prefix: '/pages/', route: ROUTES.PAGES },
    { prefix: '/chat/', route: ROUTES.CHAT },
    { prefix: '/reader/', route: ROUTES.READER },
    { prefix: '/invite/', route: ROUTES.INVITE },
    { prefix: '/project/', route: ROUTES.PROJECT },
  ];

  for (const { prefix, route } of itemRoutes) {
    if (path.startsWith(prefix)) {
      const id = path.slice(prefix.length) || null;
      return { route, id, params };
    }
  }

  // Default to home for unknown routes
  return { route: ROUTES.HOME, id: null, params };
};

/**
 * Navigate to a route (updates URL without page reload)
 * @param {string} route - Route path
 * @param {string|null} id - Optional item ID
 * @param {object} params - Optional query parameters
 */
export const navigateTo = (route, id = null, params = {}) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }

  let path = route;
  if (id) {
    path = `${route}/${id}`;
  }

  // Add query params if any
  const queryString = new URLSearchParams(params).toString();
  if (queryString) {
    path = `${path}?${queryString}`;
  }

  // Skip navigation if we're already on the same URL (prevents duplicate history entries)
  if (window.location.pathname === path) {
    console.log('🔗 [URL_ROUTER] Already on', path, '- skipping navigation');
    return;
  }

  // Use history.pushState to change URL without reload
  window.history.pushState({ route, id, params }, '', path);

  // Dispatch custom event for components to listen to
  window.dispatchEvent(new CustomEvent('urlchange', { 
    detail: { route, id, params } 
  }));
};

/**
 * Replace current URL without adding to history (for updates like save)
 * @param {string} route - Route path
 * @param {string|null} id - Optional item ID
 * @param {object} params - Optional query parameters
 */
export const replaceUrl = (route, id = null, params = {}) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }

  let path = route;
  if (id) {
    path = `${route}/${id}`;
  }

  // Add query params if any
  const queryString = new URLSearchParams(params).toString();
  if (queryString) {
    path = `${path}?${queryString}`;
  }

  // Use replaceState to update URL without adding history entry
  window.history.replaceState({ route, id, params }, '', path);
  console.log('🔗 [URL_ROUTER] Replaced URL to', path);
};

/**
 * Navigate to home
 */
export const navigateToHome = () => {
  navigateTo(ROUTES.HOME);
};

/**
 * Navigate to presentation editor
 * @param {string} presentationId - Presentation ID
 */
export const navigateToPresentation = (presentationId) => {
  navigateTo(ROUTES.PRESENTATION, presentationId);
};

/**
 * Navigate to printable editor
 * @param {string} printableId - Printable ID
 */
export const navigateToPrintable = (printableId) => {
  navigateTo(ROUTES.PRINTABLE, printableId);
};

/**
 * Navigate to report editor
 * @param {string} reportId - Report ID
 */
export const navigateToReport = (reportId) => {
  navigateTo(ROUTES.REPORT, reportId);
};

/**
 * Navigate to diagram editor
 * @param {string} diagramId - Diagram ID (optional - if not provided, shows mode selector)
 */
export const navigateToDiagram = (diagramId = null) => {
  navigateTo(ROUTES.DIAGRAM, diagramId);
};

/**
 * Replace URL to diagram (doesn't add history entry - for save operations)
 * @param {string} diagramId - Diagram ID
 */
export const replaceUrlToDiagram = (diagramId) => {
  replaceUrl(ROUTES.DIAGRAM, diagramId);
};

/**
 * Navigate to pages editor
 * @param {string} pageId - Page ID
 */
export const navigateToPages = (pageId) => {
  navigateTo(ROUTES.PAGES, pageId);
};

/**
 * Navigate to reader panel (documents)
 */
export const navigateToReader = () => {
  navigateTo(ROUTES.READER);
};

/**
 * Navigate to chat interface
 */
export const navigateToChat = () => {
  navigateTo(ROUTES.CHAT);
};

/**
 * Navigate to project list
 */
export const navigateToProjectList = () => {
  navigateTo(ROUTES.PROJECT);
};

/**
 * Navigate to project management
 * @param {string} projectId - Project ID
 * @param {string|null} tab - Optional tab name (kanban, timeline, etc.)
 * @param {string|null} taskId - Optional task ID to focus
 */
export const navigateToProject = (projectId, tab = null, taskId = null) => {
  if (taskId) {
    navigateTo(ROUTES.PROJECT, `${projectId}/task/${taskId}`);
  } else if (tab) {
    navigateTo(ROUTES.PROJECT, `${projectId}/${tab}`);
  } else {
    navigateTo(ROUTES.PROJECT, projectId);
  }
};

/**
 * Replace URL to project (no history entry - for tab switches etc.)
 * @param {string} projectId - Project ID
 * @param {string|null} tab - Optional tab name
 */
export const replaceUrlToProject = (projectId, tab = null) => {
  if (tab) {
    replaceUrl(ROUTES.PROJECT, `${projectId}/${tab}`);
  } else {
    replaceUrl(ROUTES.PROJECT, projectId);
  }
};

/**
 * Parse project URL into project ID, optional tab, and optional task ID
 * URL patterns:
 *   /project              -> { projectId: null, tab: null, taskId: null }  (list view)
 *   /project/new          -> { projectId: 'new', tab: null, taskId: null } (create)
 *   /project/{id}         -> { projectId: id, tab: null, taskId: null }    (dashboard)
 *   /project/{id}/kanban  -> { projectId: id, tab: 'kanban', taskId: null }
 *   /project/{id}/task/{tid} -> { projectId: id, tab: null, taskId: tid }
 * @param {string} id - The ID portion from URL parsing
 * @returns {{ projectId: string|null, tab: string|null, taskId: string|null }}
 */
export const parseProjectUrl = (id) => {
  if (!id) return { projectId: null, tab: null, taskId: null };
  
  // Check for /task/ pattern first
  const taskMatch = id.match(/^([^/]+)\/task\/(.+)$/);
  if (taskMatch) {
    return { projectId: taskMatch[1], tab: null, taskId: taskMatch[2] };
  }
  
  // Check for /{id}/{tab} pattern
  const tabMatch = id.match(/^([^/]+)\/([^/]+)$/);
  if (tabMatch) {
    const knownTabs = ['tasks', 'kanban', 'resources', 'dashboard', 'timeline', 'critical-path', 'notifications', 'workload', 'budget', 'closure', 'help'];
    if (knownTabs.includes(tabMatch[2])) {
      return { projectId: tabMatch[1], tab: tabMatch[2], taskId: null };
    }
  }
  
  // Simple /{id} pattern
  return { projectId: id, tab: null, taskId: null };
};

/**
 * Go back in browser history
 */
export const goBack = () => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }
  window.history.back();
};

/**
 * Hook to listen for URL changes (popstate events)
 * @param {function} callback - Called with route info when URL changes
 * @returns {function} Cleanup function
 */
export const onUrlChange = (callback) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return () => {};
  }

  const handlePopState = () => {
    const routeInfo = parseCurrentUrl();
    callback(routeInfo);
  };

  const handleUrlChange = (event) => {
    callback(event.detail);
  };

  // Listen for browser back/forward
  window.addEventListener('popstate', handlePopState);
  // Listen for programmatic navigation
  window.addEventListener('urlchange', handleUrlChange);

  return () => {
    window.removeEventListener('popstate', handlePopState);
    window.removeEventListener('urlchange', handleUrlChange);
  };
};

/**
 * Update document title based on route
 * @param {string} route - Current route
 * @param {string|null} itemName - Optional item name
 */
export const updateDocumentTitle = (route, itemName = null) => {
  if (Platform.OS !== 'web' || typeof document === 'undefined') {
    return;
  }

  const titles = {
    [ROUTES.HOME]: 'Citra AI - Create Intelligent Content',
    [ROUTES.PRESENTATION]: itemName ? `${itemName} - Presentation | Citra AI` : 'Presentation Editor | Citra AI',
    [ROUTES.PRINTABLE]: itemName ? `${itemName} - Document | Citra AI` : 'Document Editor | Citra AI',
    [ROUTES.REPORT]: itemName ? `${itemName} - Report | Citra AI` : 'Report Editor | Citra AI',
    [ROUTES.DIAGRAM]: itemName ? `${itemName} - Diagram | Citra AI` : 'Diagram Editor | Citra AI',
    [ROUTES.PAGES]: itemName ? `${itemName} - Page | Citra AI` : 'Page Editor | Citra AI',
    [ROUTES.CHAT]: 'Chat | Citra AI',
    [ROUTES.READER]: 'Reader & Review | Citra AI',
  };

  document.title = titles[route] || 'Citra AI';
};

/**
 * Initialize URL routing on app start
 * Redirects root (/) to /home
 */
export const initializeRouting = () => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return { route: ROUTES.HOME, id: null, params: {} };
  }

  const path = window.location.pathname;
  
  // If at root, redirect to /home
  if (path === '/' || path === '') {
    window.history.replaceState({}, '', '/home');
  }

  return parseCurrentUrl();
};
