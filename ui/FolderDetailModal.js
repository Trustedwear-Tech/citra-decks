/**
 * FolderDetailModal — read-only view of an artifact's dedicated folder.
 *
 * New for citra-decks, not a port: the equivalent component in Citra-UI's
 * history (FolderManagementPanel.js) is a full multi-folder browser with
 * drag-and-drop, sharing, and Teams coupling — the wrong shape for "show
 * me what's in this one folder." This is deliberately minimal: folder
 * name/description (GET /api/folders/{folder_id}) plus its file list
 * (GET /api/v2/files?folder_id=X), both already-existing, already-working
 * endpoints with no prior UI consumer.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, Modal, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import authService from '../services/authService';
import { CONFIG } from '../config/config';

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

export default function FolderDetailModal({ visible, onClose, folderId, theme }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [folder, setFolder] = useState(null);
  const [files, setFiles] = useState([]);

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

              <ScrollView style={styles.fileList}>
                {files.length === 0 ? (
                  <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                    No documents in this folder yet.
                  </Text>
                ) : (
                  files.map((file) => (
                    <View key={file.id || file._id || file.filename} style={[styles.fileRow, { borderColor: theme.borderColor }]}>
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
                    </View>
                  ))
                )}
              </ScrollView>
            </>
          )}
        </View>
      </View>
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
});
