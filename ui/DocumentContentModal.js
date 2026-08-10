/**
 * DocumentContentModal — read an uploaded document's text back out of MongoDB.
 *
 * The point of the data store is the extracted text: that is what gets chunked,
 * embedded into Milvus, and retrieved to ground generation. So "view" here means
 * "show me what the model will actually see", not "download the original file" —
 * no object storage is involved on this path.
 *
 * Loosely follows Citra-UI's ChunkedDocumentViewer (pre-oss-split), but not a
 * port: that one renders a FlatList of chunk cards, each with its own nested
 * 300px-tall ScrollView, which behaves badly on web; it hardcodes iOS colours;
 * and its jump-to-chunk is built on Alert.prompt, which is iOS-only and silently
 * does nothing on the web target this repo ships. Two of its bugs are fixed here
 * rather than inherited: it sent `chunks_per_page` where the API expects
 * `per_page` (so paging silently used the server default), and it read
 * `metadata.filename`/`metadata.topic`, which the API does not return — the
 * field is `topic_or_filename`.
 *
 *   GET /api/v2/documents/chunked/metadata/{document_id}
 *   GET /api/v2/documents/chunked/{document_id}/chunks?page=N&per_page=M
 */
import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, Modal, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import authService from '../services/authService';
import { CONFIG } from '../config/config';

const CHUNKS_PER_PAGE = 20;

/**
 * Chunk text carries structural markers the chunker injects for the embedding
 * model (=== PARAGRAPH ===, === TABLE === and friends). They are noise to a
 * human reader, so strip them and collapse the blank lines they leave behind.
 */
function cleanChunkText(text) {
  if (!text) return '';
  return text
    .replace(/^===\s*[A-Z_ ]+\s*===\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export default function DocumentContentModal({ visible, onClose, documentId, filename, theme }) {
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [pagination, setPagination] = useState(null);

  const fetchChunks = useCallback(async (page) => {
    const base = CONFIG.CITRA_SERVICE_URL;
    const response = await authService.authenticatedFetch(
      `${base}/api/v2/documents/chunked/${encodeURIComponent(documentId)}/chunks?page=${page}&per_page=${CHUNKS_PER_PAGE}`
    );
    if (!response.ok) throw new Error(`Failed to load content: HTTP ${response.status}`);
    return response.json();
  }, [documentId]);

  const load = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    setChunks([]);
    setPagination(null);
    try {
      const base = CONFIG.CITRA_SERVICE_URL;
      const metaResponse = await authService.authenticatedFetch(
        `${base}/api/v2/documents/chunked/metadata/${encodeURIComponent(documentId)}`
      );
      if (!metaResponse.ok) {
        throw new Error(
          metaResponse.status === 404
            ? 'No extracted text stored for this document.'
            : `Failed to load document: HTTP ${metaResponse.status}`
        );
      }
      const meta = await metaResponse.json();
      setMetadata(meta);

      // Surface the states where there is legitimately nothing to show yet,
      // instead of rendering an empty body and letting the user guess.
      if (meta.processing_status === 'processing') {
        throw new Error('This document is still being processed — try again shortly.');
      }
      if (meta.processing_status === 'failed') {
        throw new Error('Processing failed for this document, so no text was stored.');
      }

      const first = await fetchChunks(1);
      setChunks(first.chunks || []);
      setPagination(first.pagination || null);
    } catch (e) {
      console.error('❌ [DOC_CONTENT] Failed to load document content:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [documentId, fetchChunks]);

  useEffect(() => {
    if (visible && documentId) load();
  }, [visible, documentId, load]);

  const loadMore = useCallback(async () => {
    if (!pagination?.has_next || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await fetchChunks(pagination.next_page);
      setChunks((prev) => [...prev, ...(next.chunks || [])]);
      setPagination(next.pagination || null);
    } catch (e) {
      console.error('❌ [DOC_CONTENT] Failed to load more:', e);
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }, [pagination, loadingMore, fetchChunks]);

  const title = filename || metadata?.topic_or_filename || 'Document';

  return (
    <Modal visible={!!visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.card, { backgroundColor: theme.surface || theme.card || '#16213e', borderColor: theme.borderColor }]}>
          <View style={styles.header}>
            <Ionicons name="document-text-outline" size={20} color={theme.primary} />
            <Text style={[styles.title, { color: theme.text }]} numberOfLines={1}>{title}</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <Ionicons name="close" size={22} color={theme.textSecondary} />
            </TouchableOpacity>
          </View>

          {!!metadata && !error && (
            <Text style={[styles.subline, { color: theme.textSecondary }]}>
              {metadata.total_chunks} chunk{metadata.total_chunks !== 1 ? 's' : ''}
              {metadata.total_pages ? ` · ${metadata.total_pages} page${metadata.total_pages !== 1 ? 's' : ''}` : ''}
              {' · stored text used for grounding'}
            </Text>
          )}

          {loading && (
            <View style={styles.centered}>
              <ActivityIndicator size="large" color={theme.primary} />
            </View>
          )}

          {!loading && error && (
            <View style={styles.centered}>
              <Text style={{ color: theme.error || '#ef4444', textAlign: 'center' }}>{error}</Text>
              <TouchableOpacity onPress={load} style={[styles.retryBtn, { borderColor: theme.borderColor }]}>
                <Text style={{ color: theme.primary }}>Retry</Text>
              </TouchableOpacity>
            </View>
          )}

          {!loading && !error && (
            <ScrollView style={styles.body}>
              {chunks.length === 0 ? (
                <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                  No extracted text stored for this document.
                </Text>
              ) : (
                <>
                  {chunks.map((chunk, index) => {
                    const text = cleanChunkText(chunk.content);
                    return (
                      <View key={`${chunk.chunk_index}-${index}`} style={styles.chunk}>
                        <Text style={[styles.chunkLabel, { color: theme.textSecondary }]}>
                          Chunk {(chunk.chunk_index ?? index) + 1}
                          {chunk.start_page ? ` · pages ${chunk.start_page}–${chunk.end_page ?? chunk.start_page}` : ''}
                        </Text>
                        <Text style={[styles.chunkText, { color: theme.text }]} selectable>
                          {text || '(no text in this chunk)'}
                        </Text>
                      </View>
                    );
                  })}

                  {pagination?.has_next && (
                    <TouchableOpacity
                      onPress={loadMore}
                      disabled={loadingMore}
                      style={[styles.moreBtn, { borderColor: theme.borderColor }]}
                    >
                      {loadingMore
                        ? <ActivityIndicator size="small" color={theme.primary} />
                        : <Text style={{ color: theme.primary }}>
                            Load more ({chunks.length} of {pagination.total_chunks})
                          </Text>}
                    </TouchableOpacity>
                  )}
                </>
              )}
            </ScrollView>
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
    maxWidth: 640,
    maxHeight: '80%',
    borderRadius: 12,
    borderWidth: 1,
    padding: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  title: {
    fontSize: 17,
    fontWeight: '700',
    marginLeft: 8,
    flex: 1,
  },
  closeButton: { padding: 4 },
  subline: {
    fontSize: 12,
    marginBottom: 12,
  },
  centered: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  retryBtn: {
    marginTop: 12,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
  },
  body: {
    maxHeight: 420,
  },
  emptyText: {
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 24,
  },
  chunk: {
    marginBottom: 18,
  },
  chunkLabel: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  chunkText: {
    fontSize: 14,
    lineHeight: 21,
  },
  moreBtn: {
    alignSelf: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    marginBottom: 12,
  },
});
