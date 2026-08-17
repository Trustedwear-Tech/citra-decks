// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState, useCallback } from 'react';
import { View, ActivityIndicator, Text, Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import ErrorBoundary from './ErrorBoundary';
import UserProvider, { useUser } from './components/UserProvider';
import { WorkspaceProvider } from './contexts/WorkspaceContext';
import authService from './services/authService';
import LandingScreen from './screens/LandingScreen';
import EmailAuthScreen from './components/auth/EmailAuthScreen';
import PresentationComposer from './ui/composer/PresentationComposer';
import PresentationListModal from './ui/composer/PresentationListModal';
import ReportComposer from './ui/composer/ReportComposer';
import ReportListModal from './ui/composer/ReportListModal';
import PrintableComposer from './ui/printable/PrintableComposer';
import PrintableListModal from './ui/printable/PrintableListModal';
import useDocumentUpload from './hooks/useDocumentUpload';
import { CONFIG } from './config/config';

const CITRA_SERVICE_URL = CONFIG.CITRA_SERVICE_URL;

const THEME = {
  primary: '#6366f1',
  background: '#0a0b14',
  surface: '#16213e',
  card: '#16213e',
  text: '#e0e0e0',
  textSecondary: '#a0a0a0',
  borderColor: '#2a2a3e',
  inputBackground: '#0f3460',
  inputBorder: '#1a5276',
  error: '#ef4444',
  success: '#22c55e',
  isDark: true,
};

const ROUTE = {
  LOADING: 'loading',
  LANDING: 'landing',
  LOGIN: 'login',
  LIST: 'list',
  COMPOSER: 'composer',
};

const TYPE_CONFIG = {
  presentation: {
    ListModal: PresentationListModal,
    Composer: PresentationComposer,
    loadPropName: 'onLoadPresentation',
    initialPropName: 'initialPresentation',
    folderApiName: 'presentation',
  },
  report: {
    ListModal: ReportListModal,
    Composer: ReportComposer,
    loadPropName: 'onLoadReport',
    initialPropName: 'initialReport',
    folderApiName: 'report',
  },
  printable: {
    ListModal: PrintableListModal,
    Composer: PrintableComposer,
    loadPropName: 'onLoadprintable',
    initialPropName: 'initialPrintable',
    folderApiName: 'printable',
  },
};

function LoadingScreen() {
  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: THEME.background }}>
      <ActivityIndicator size={Platform.OS === 'web' ? 60 : 'large'} color={THEME.primary} />
      <Text style={{ color: THEME.text, marginTop: 24, fontSize: 16 }}>Loading...</Text>
    </View>
  );
}

async function createArtifactFolder(name) {
  const headers = await authService.getAuthHeaders();
  const response = await fetch(`${CITRA_SERVICE_URL}/api/folders/create`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(`Failed to create folder: HTTP ${response.status}`);
  }
  return response.json();
}

const AppContent = () => {
  const { isInitialized, isLoading, isAuthenticated, handleAuthentication } = useUser();
  const [route, setRoute] = useState(ROUTE.LANDING);
  const [selectedType, setSelectedType] = useState(null);
  const [activeFolder, setActiveFolder] = useState(null);
  const [activeArtifact, setActiveArtifact] = useState(null);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [folderCreateError, setFolderCreateError] = useState(null);

  // Supplies UnifiedUploadModal's `actions`. Scoped to the open artifact's
  // folder — there is no folder picker in this product, so every upload from
  // a composer lands in that artifact's own data store.
  const upload = useDocumentUpload({
    folderId: activeFolder?.id || activeArtifact?.folder_id || null,
    folderName: activeFolder?.name,
  });

  const handleSelectType = useCallback((type) => {
    setSelectedType(type);
    setRoute(isAuthenticated ? ROUTE.LIST : ROUTE.LOGIN);
  }, [isAuthenticated]);

  const handleAuthSuccess = useCallback(async (authData) => {
    await handleAuthentication(authData);
    setRoute(ROUTE.LIST);
  }, [handleAuthentication]);

  const handleCreateNew = useCallback(async () => {
    if (isCreatingFolder) return;
    setIsCreatingFolder(true);
    setFolderCreateError(null);
    try {
      const label = TYPE_CONFIG[selectedType]?.folderApiName || selectedType;
      const folder = await createArtifactFolder(
        `Untitled ${label} — ${new Date().toLocaleDateString()}`
      );
      setActiveFolder(folder);
      setActiveArtifact(null);
      setRoute(ROUTE.COMPOSER);
    } catch (error) {
      console.error('❌ [SHELL] Failed to create folder for new artifact:', error);
      setFolderCreateError(error.message);
    } finally {
      setIsCreatingFolder(false);
    }
  }, [selectedType, isCreatingFolder]);

  const handleOpenExisting = useCallback((artifact) => {
    setActiveArtifact(artifact);
    setActiveFolder(artifact?.folder_id ? { id: artifact.folder_id } : null);
    setRoute(ROUTE.COMPOSER);
  }, []);

  const handleCloseComposer = useCallback(() => {
    setActiveArtifact(null);
    setActiveFolder(null);
    setRoute(ROUTE.LIST);
  }, []);

  const handleCloseList = useCallback(() => {
    setSelectedType(null);
    setRoute(ROUTE.LANDING);
  }, []);

  if (!isInitialized || isLoading) {
    return <LoadingScreen />;
  }

  if (route === ROUTE.LANDING) {
    return <LandingScreen onSelectType={handleSelectType} theme={THEME} />;
  }

  if (route === ROUTE.LOGIN) {
    return (
      <View style={{ flex: 1, backgroundColor: THEME.background }}>
        <EmailAuthScreen onAuthSuccess={handleAuthSuccess} theme="dark" />
      </View>
    );
  }

  const config = TYPE_CONFIG[selectedType];
  if (!config) {
    // Shouldn't happen — fall back to landing rather than a blank screen.
    return <LandingScreen onSelectType={handleSelectType} theme={THEME} />;
  }

  const selectedFolders = activeFolder ? [{ id: activeFolder.id, name: activeFolder.name || 'Untitled' }] : [];

  if (route === ROUTE.LIST) {
    const { ListModal, loadPropName } = config;
    const listProps = {
      visible: true,
      onClose: handleCloseList,
      onCreateNew: handleCreateNew,
      apiConfig: { API_URL: CITRA_SERVICE_URL, CITRA_SERVICE_URL },
      userDeviceId: null,
      theme: THEME,
      [loadPropName]: handleOpenExisting,
    };
    return (
      <View style={{ flex: 1, backgroundColor: THEME.background }}>
        <ListModal {...listProps} />
        {isCreatingFolder && (
          <View style={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)',
          }}>
            <ActivityIndicator size="large" color={THEME.primary} />
          </View>
        )}
        {folderCreateError && (
          <View style={{ position: 'absolute', bottom: 24, left: 24, right: 24, padding: 12, borderRadius: 8, backgroundColor: THEME.error }}>
            <Text style={{ color: '#fff' }}>{folderCreateError}</Text>
          </View>
        )}
      </View>
    );
  }

  if (route === ROUTE.COMPOSER) {
    const { Composer, initialPropName } = config;
    const composerProps = {
      visible: true,
      onClose: handleCloseComposer,
      theme: THEME,
      userDeviceId: null,
      apiConfig: { API_URL: CITRA_SERVICE_URL, CITRA_SERVICE_URL },
      selectedFolders,
      folders: selectedFolders,
      [initialPropName]: activeArtifact,
      // Without this the upload modal renders but every tile is inert.
      uploadModalProps: {
        actions: upload.actions,
        onPasteTextSubmit: upload.pasteText,
        onInternetIngestFetch: upload.internetIngestFetch,
        onInternetIngestEmbed: upload.internetIngestEmbed,
        onUploadStatusChange: upload.setUploadStatus,
        enhancedProgress: upload.uploadProgress,
        selectedFolderIds: selectedFolders.map((f) => f.id),
        folders: selectedFolders,
        uploadSuccessToast: upload.uploadSuccess,
        onCloseUploadSuccessToast: () =>
          upload.setUploadSuccess((prev) => ({ ...prev, visible: false })),
      },
    };
    return (
      // No useUploadedData/setUseUploadedData props — WorkspaceProvider
      // falls back to its own internal state (defaults true), which is
      // what makes the goal-input toggle actually interactive.
      <WorkspaceProvider>
        <Composer {...composerProps} />
      </WorkspaceProvider>
    );
  }

  return <LoadingScreen />;
};

export default function App() {
  return (
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <UserProvider>
            <AppContent />
          </UserProvider>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}
