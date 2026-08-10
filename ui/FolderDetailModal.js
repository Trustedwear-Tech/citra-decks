/**
 * FolderDetailModal — the contents view for an artifact's dedicated folder.
 *
 * New for citra-decks, not a port: the equivalent component in Citra-UI's
 * history (FolderManagementPanel.js) is a full multi-folder browser with
 * drag-and-drop, sharing, and Teams coupling — the wrong shape for "show
 * me what's in this one folder." This is deliberately minimal: folder
 * name/description (GET /api/folders/{folder_id}), its file list
 * (GET /api/v2/files?folder_id=X), and per-file view + delete
 * (DELETE /api/v2/files/{file_id}).
 *
 * There is no folder picker anywhere in this product, so this modal is the
 * only place a user can see — and remove — what they uploaded. "View" opens
 * the extracted text stored in MongoDB (see DocumentContentModal), which is
 * what actually grounds generation; delete cascades server-side across the
 * Milvus vectors, the stored original in S3, the Mongo chunks and the
 * registry row.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, Modal, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet, Platform, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import authService from '../services/authService';
import { CONFIG } from '../config/config';
import DocumentContentModal from './DocumentContentModal';

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const FILE_TYPE_ICONS = {
  document: 'document-text-outline',
  audio: 'musical-notes-outline',
  video: 'videocam-outline',
  image: 'image-outline',
  note: 'create-outline',
};

/**
 * Confirm through whichever dialog the platform actually shows.
 * Alert.alert is a no-op on react-native-web, so a delete confirmed there
 * would silently never fire — hence the window.confirm branch.
 */
function confirmDestructive(title, message) {
  if (Platform.OS === 'web') {
    return Promise.resolve(
      typeof window !== 'undefined' && window.confirm(`${title}\n\n${message}`)
    );
  }
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: 'Delete', style: 'destructive', onPress: () => resolve(true) },
    ]);
  });
}

export default function FolderDetailModal({ visible, onClose, folderId, theme }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [folder, setFolder] = useState(null);
  const [files, setFiles] = useState([]);
  // `${fileId}:delete` — keeps one row's spinner local and stops
  // a double-tap firing the same destructive call twice.
  const [busyFile, setBusyFile] = useState(null);
  const [actionError, setActionError] = useState(null);
  // { documentId, filename } of the row whose stored text is open, or null.
  const [viewing, setViewing] = useState(null);

  const load = useCallback(async () => {
    if (!folderId) return;
    setLoading(true);
    setError(null);
    try {
      const headers = await authService.getAuthHeaders();
      const base = CONFIG.CITRA_SERVICE_URL;

      const [folderRes, filesRes] = await Promise.all([
        fetch(`${base}/api/folders/${folderId}`, { headers }),
        fetch(`${base}/api/v2/files?folder_id=${encodeURIComponent(folderId)}&limit=100`, { headers }),
      ]);

      if (!folderRes.ok) throw new Error(`Failed to load folder: HTTP ${folderRes.status}`);
      const folderData = await folderRes.json();
      setFolder(folderData);

      if (filesRes.ok) {
        const filesData = await filesRes.json();
        setFiles(filesData.files || []);
      } else {
        setFiles([]);
      }
    } catch (e) {
      console.error('❌ [FOLDER_DETAIL] Failed to load folder:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [folderId]);

  useEffect(() => {
    if (visible && folderId) {
      load();
    }
  }, [visible, folderId, load]);

  const handleDelete = useCallback(async (file) => {
    const fileId = file.id || file._id;
    if (!fileId) {
      setActionError('This file has no id — cannot delete it.');
      return;
    }

    const confirmed = await confirmDestructive(
      'Delete document',
      `Remove "${file.filename || 'this file'}" from the data store? Its embeddings ` +
      'are deleted too, so it will no longer ground generation. This cannot be undone.'
    );
    if (!confirmed) return;

    setBusyFile(`${fileId}:delete`);
    setActionError(null);
    try {
      const response = await authService.authenticatedFetch(
        `${CONFIG.CITRA_SERVICE_URL}/api/v2/files/${encodeURIComponent(fileId)}`,
        { method: 'DELETE' }
      );
      const body = await response.json().catch(() => ({}));

      // The endpoint answers 200 with success:false when a sub-step (Milvus,
      // S3 or Mongo) failed, so the status alone is not enough.
      if (!response.ok || body.success === false) {
        const detail = body?.details?.errors?.join('; ') || body?.message || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      setFiles((prev) => prev.filter((f) => (f.id || f._id) !== fileId));
    } catch (e) {
      console.error('❌ [FOLDER_DETAIL] Delete failed:', e);
      setActionError(`Delete failed: ${e.message}`);
    } finally {
      setBusyFile(null);
    }
  }, []);

  // "View" opens the extracted text held in MongoDB — the same text that was
  // chunked and embedded — rather than fetching the original file back out of
  // object storage. What the model sees is what the user is shown.
  const handleView = useCallback((file) => {
    const documentId = file.document_id || file.id || file._id;
    if (!documentId) {
      setActionError('This file has no document id — cannot open it.');
      return;
    }
    setViewing({ documentId, filename: file.filename });
  }, []);

  return (
    <Modal visible={!!visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.card, { backgroundColor: theme.surface || theme.card || '#16213e', borderColor: theme.borderColor }]}>
          <View style={styles.header}>
            <Ionicons name="folder-outline" size={22} color={theme.primary} />
            <Text style={[styles.title, { color: theme.text }]} numberOfLines={1}>
              {folder?.name || 'Folder'}
            </Text>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <Ionicons name="close" size={22} color={theme.textSecondary} />
            </TouchableOpacity>
          </View>

          {loading && (
            <View style={styles.centered}>
              <ActivityIndicator size="large" color={theme.primary} />
            </View>
          )}

          {!loading && error && (
            <View style={styles.centered}>
              <Text style={{ color: theme.error || '#ef4444' }}>{error}</Text>
            </View>
          )}

          {!loading && !error && folder && (
            <>
              {!!folder.description && (
                <Text style={[styles.description, { color: theme.textSecondary }]}>
                  {folder.description}
                </Text>
              )}

              <Text style={[styles.sectionLabel, { color: theme.textSecondary }]}>
                {files.length} file{files.length !== 1 ? 's' : ''}
              </Text>

              {!!actionError && (
                <Text style={[styles.actionError, { color: theme.error || '#ef4444' }]}>
                  {actionError}
                </Text>
              )}

              <ScrollView style={styles.fileList}>
                {files.length === 0 ? (
                  <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                    No documents in this folder yet.
                  </Text>
                ) : (
                  files.map((file) => {
                    const fileId = file.id || file._id;
                    const isDeleting = busyFile === `${fileId}:delete`;

                    return (
                      <View key={fileId || file.filename} style={[styles.fileRow, { borderColor: theme.borderColor }]}>
                        <Ionicons
                          name={FILE_TYPE_ICONS[file.file_type_category] || 'document-outline'}
                          size={18}
                          color={theme.textSecondary}
                        />
                        <Text style={[styles.fileName, { color: theme.text }]} numberOfLines={1}>
                          {file.filename || 'Untitled'}
                        </Text>
                        <Text style={[styles.fileSize, { color: theme.textSecondary }]}>
                          {formatBytes(file.file_size_bytes)}
                        </Text>

                        <TouchableOpacity
                          onPress={() => handleView(file)}
                          disabled={isDeleting}
                          style={styles.rowAction}
                          accessibilityLabel={`View stored text of ${file.filename || 'file'}`}
                        >
                          <Ionicons name="eye-outline" size={18} color={theme.textSecondary} />
                        </TouchableOpacity>

                        {isDeleting ? (
                          <ActivityIndicator size="small" color={theme.error || '#ef4444'} style={styles.rowAction} />
                        ) : (
                          <TouchableOpacity
                            onPress={() => handleDelete(file)}
                            style={styles.rowAction}
                            accessibilityLabel={`Delete ${file.filename || 'file'}`}
                          >
                            <Ionicons name="trash-outline" size={18} color={theme.error || '#ef4444'} />
                          </TouchableOpacity>
                        )}
                      </View>
                    );
                  })
                )}
              </ScrollView>
            </>
          )}
        </View>
      </View>

      <DocumentContentModal
        visible={!!viewing}
        documentId={viewing?.documentId}
        filename={viewing?.filename}
        theme={theme}
        onClose={() => setViewing(null)}
      />
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  card: {
    width: '90%',
    maxWidth: 480,
    maxHeight: '70%',
    borderRadius: 12,
    borderWidth: 1,
    padding: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    marginLeft: 8,
    flex: 1,
  },
  closeButton: {
    padding: 4,
  },
  centered: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  description: {
    fontSize: 14,
    marginBottom: 16,
    lineHeight: 20,
  },
  sectionLabel: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 8,
  },
  fileList: {
    maxHeight: 320,
  },
  emptyText: {
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 24,
  },
  fileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  fileName: {
    flex: 1,
    fontSize: 14,
    marginLeft: 10,
  },
  fileSize: {
    fontSize: 12,
    marginLeft: 8,
  },
  rowAction: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: 4,
  },
  actionError: {
    fontSize: 12,
    marginBottom: 8,
  },
});
