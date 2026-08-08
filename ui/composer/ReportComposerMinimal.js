// Minimal ReportComposer for testing - Step by step import testing
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useReportPages } from '../../hooks/useReportPages';
import { useReportPersistence } from '../../hooks/useReportPersistence';
import ReportGoalSetting from './ReportGoalSetting';
import ContextNavigator from './ContextNavigator';
import SelectionContextMenu from './SelectionContextMenu';
import PageNavigationBar from './PageNavigationBar';  // TESTING: Add PageNavigationBar

// Basic ReportComposer that only imports React Native components
const ReportComposerMinimal = ({ 
  visible, 
  onClose, 
  theme,
  userDeviceId,
  apiConfig,
  persona,
  initialReport = null
}) => {
  // Test the hooks
  const {
    pages,
    currentPageId,
    addPage,
    reportMetadata
  } = useReportPages(initialReport);

  const {
    saveReport,
    isSaving
  } = useReportPersistence();

  const [showGoalSetting, setShowGoalSetting] = useState(false);
  const [showContextNavigator, setShowContextNavigator] = useState(false);
  const [selectionMenu, setSelectionMenu] = useState(null);

  // Mock context manager for testing
  const mockContextManager = {
    reportGoal: { purpose: 'Test Goal', documentType: 'business_report' },
    documentStructure: { totalPages: pages?.length || 1, currentPage: 1 }
  };

  return (
    <Modal visible={visible} animationType="slide">
      <View style={{ flex: 1, backgroundColor: '#fff', padding: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 20 }}>
          <MaterialIcons name="edit" size={24} color="#007AFF" />
          <Text style={{ marginLeft: 10, fontSize: 18 }}>Report Composer - Testing All Components</Text>
        </View>
        <Text style={{ marginBottom: 10 }}>Pages: {pages?.length || 0}</Text>
        <Text style={{ marginBottom: 10 }}>Title: {reportMetadata?.title || 'Untitled'}</Text>
        <Text style={{ marginBottom: 10 }}>Saving: {isSaving ? 'Yes' : 'No'}</Text>
        
        <TouchableOpacity 
          onPress={() => setShowGoalSetting(true)}
          style={{ padding: 10, backgroundColor: '#28a745', borderRadius: 5, marginTop: 10 }}
        >
          <Text style={{ color: '#fff', textAlign: 'center' }}>Test Goal Setting</Text>
        </TouchableOpacity>

        <TouchableOpacity 
          onPress={() => setShowContextNavigator(!showContextNavigator)}
          style={{ padding: 10, backgroundColor: '#ffc107', borderRadius: 5, marginTop: 10 }}
        >
          <Text style={{ color: '#000', textAlign: 'center' }}>Toggle Context Navigator</Text>
        </TouchableOpacity>

        <TouchableOpacity 
          onPress={() => setSelectionMenu({ text: 'Sample selected text', position: { x: 100, y: 200 } })}
          style={{ padding: 10, backgroundColor: '#17a2b8', borderRadius: 5, marginTop: 10 }}
        >
          <Text style={{ color: '#fff', textAlign: 'center' }}>Test Selection Menu</Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          onPress={onClose}
          style={{ padding: 10, backgroundColor: '#007AFF', borderRadius: 5, marginTop: 20 }}
        >
          <Text style={{ color: '#fff', textAlign: 'center' }}>Close</Text>
        </TouchableOpacity>

        {/* Test PageNavigationBar */}
        <View style={{ marginTop: 20, padding: 10, backgroundColor: '#f8f9fa', borderRadius: 5 }}>
          <Text style={{ marginBottom: 10, fontWeight: 'bold' }}>Testing PageNavigationBar:</Text>
          <PageNavigationBar
            pages={pages}
            currentPageId={currentPageId}
            onPageSelect={(pageId) => console.log('Page selected:', pageId)}
            onAddPage={() => addPage()}
            onDeletePage={(pageId) => console.log('Delete page:', pageId)}
            onReorderPages={(newOrder) => console.log('Reorder pages:', newOrder)}
            theme={theme}
          />
        </View>

        {/* Context Navigator */}
        {showContextNavigator && (
          <View style={{ marginTop: 20, padding: 10, backgroundColor: '#f8f9fa', borderRadius: 5 }}>
            <ContextNavigator
              contextManager={mockContextManager}
              currentPage={1}
              totalPages={pages?.length || 1}
              onPageChange={(page) => console.log('Page changed to:', page)}
              documentProgress={{ completed: 0.3, goalAlignment: 0.7 }}
            />
          </View>
        )}
      </View>

      {/* Goal Setting Modal */}
      <ReportGoalSetting
        visible={showGoalSetting}
        onClose={() => setShowGoalSetting(false)}
        onGoalSet={(goalData) => {
          console.log('Goal set:', goalData);
          setShowGoalSetting(false);
        }}
        apiConfig={apiConfig}
        userDeviceId={userDeviceId}
      />

      {/* Selection Context Menu */}
      <SelectionContextMenu
        visible={!!selectionMenu}
        selectedText={selectionMenu?.text || ''}
        position={selectionMenu?.position}
        onAction={(action, text) => {
          console.log('Context action:', action, text);
          setSelectionMenu(null);
        }}
        onClose={() => setSelectionMenu(null)}
        contextManager={mockContextManager}
      />
    </Modal>
  );
};

export default ReportComposerMinimal;
