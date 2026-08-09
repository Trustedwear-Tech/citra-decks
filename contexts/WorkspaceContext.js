/**
 * WorkspaceContext — citra-decks
 *
 * Not a port of Citra-UI's WorkspaceContext.js: that version manages a
 * multi-folder picker (selectedFolderIds, toggleFolderSelection, an
 * action-chat-service scope push, an AsyncStorage-backed folder list) built
 * for a UX citra-decks doesn't have. Every composer file here (confirmed by
 * grep across ui/composer and ui/printable) destructures exactly one thing
 * from useWorkspace(): the useUploadedData / setUseUploadedData toggle —
 * "should this generation ground itself in the artifact's folder, or run
 * AI-only?" The folder itself is a prop the shell supplies (one per
 * artifact, auto-created — see Phase B5), not something picked here.
 */
import React, { createContext, useContext, useState } from 'react';

const WorkspaceContext = createContext();

const useWorkspace = () => {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
};

const WorkspaceProvider = ({ children, useUploadedData, setUseUploadedData }) => {
  // Allow an uncontrolled fallback if the shell doesn't pass these down —
  // keeps this provider usable standalone (e.g. in tests) without forcing
  // every mount site to wire state through.
  const [internalUseUploadedData, setInternalUseUploadedData] = useState(true);

  const contextValue = {
    useUploadedData: useUploadedData !== undefined ? useUploadedData : internalUseUploadedData,
    setUseUploadedData: setUseUploadedData || setInternalUseUploadedData,
  };

  return (
    <WorkspaceContext.Provider value={contextValue}>
      {children}
    </WorkspaceContext.Provider>
  );
};

export { useWorkspace, WorkspaceProvider };
export default WorkspaceContext;
