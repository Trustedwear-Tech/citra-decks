/**
 * useDocumentUpload — citra-decks
 *
 * Supplies the `actions` that UnifiedUploadModal calls when the user picks a
 * file. Without this the modal renders its tiles but every tap is a no-op
 * ("[UnifiedUploadModal] Action is not a function, ignoring"), which is what
 * shipped before this hook existed.
 *
 * Not a port of Citra-UI's upload path — that was ~900 lines spread across
 * App.js plus a 934-line EnhancedUploadManager, carrying a background upload
 * queue, team/enterprise entity routing, Google Drive, and native pickers.
 * citra-decks uploads into exactly one auto-created folder per artifact and
 * ships as an Expo *web* export, so this is the web file-input path only,
 * posting straight to the same backend endpoint (POST /v2/documents).
 *
 * Progress is coarse on purpose: fetch() gives no upload-progress events, so
 * an entry is 'uploading' until the response lands, then 'complete'. The
 * backend does the real work (extract → chunk → embed → Milvus) inside that
 * one request.
 */
import { useState, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import CONFIG from '../config/config';
import authService from '../services/authService';

const DOC_ACCEPT = [
  '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv',
  '.pptx', '.txt', '.md', '.html', '.htm', '.json',
].join(',');

const IMAGE_ACCEPT = 'image/*';
const AUDIO_ACCEPT = 'audio/*';

// Web caps the picker at 10 files per selection, same as the original.
const MAX_FILES_PER_PICK = 10;

/**
 * Open a browser file picker and resolve the chosen File objects.
 * Resolves [] when the user cancels (no reliable cancel event, so the
 * promise settles on the next window focus if nothing was chosen).
 */
function pickFilesWeb({ accept, multiple = true }) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve([]);
      return;
    }

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.multiple = multiple;
    input.style.position = 'fixed';
    input.style.left = '-9999px';
    document.body.appendChild(input);

    let settled = false;
    const finish = (files) => {
      if (settled) return;
      settled = true;
      window.removeEventListener('focus', onFocus);
      if (input.parentNode) input.parentNode.removeChild(input);
      resolve(files);
    };

    // Cancelling the OS dialog fires no event — the window regaining focus
    // with an empty input is the only signal we get.
    const onFocus = () => {
      setTimeout(() => {
        if (!input.files || input.files.length === 0) finish([]);
      }, 400);
    };

    input.onchange = () => {
      const files = Array.from(input.files || []).slice(0, MAX_FILES_PER_PICK);
      finish(files);
    };

    window.addEventListener('focus', onFocus);
    input.click();
  });
}

export default function useDocumentUpload({ folderId, folderName } = {}) {
  // Map<documentId, {stage, progress, filename}> — UnifiedUploadModal reads
  // .size off this to badge the Documents tile.
  const [uploadProgress, setUploadProgress] = useState(new Map());
  const [uploadSuccess, setUploadSuccess] = useState({ visible: false });
  const [uploadStatus, setUploadStatus] = useState(null);
  const folderIdRef = useRef(folderId);
  folderIdRef.current = folderId;

  const patchProgress = useCallback((documentId, patch) => {
    setUploadProgress((prev) => {
      const next = new Map(prev);
      if (patch === null) {
        next.delete(documentId);
      } else {
        next.set(documentId, { ...(next.get(documentId) || {}), ...patch });
      }
      return next;
    });
  }, []);

  /**
   * POST one file to the ingestion endpoint. Throws on failure — callers
   * surface the message rather than swallowing it.
   */
  const uploadOne = useCallback(async (file, { useOCR = false, filename } = {}) => {
    const targetFolderId = folderIdRef.current;
    if (!targetFolderId) {
      throw new Error('No data-store folder for this artifact — cannot upload.');
    }

    const documentId = uuidv4();
    const name = filename || file.name || 'upload';

    patchProgress(documentId, { stage: 'uploading', progress: 10, filename: name });

    const form = new FormData();
    form.append('file', file, name);
    form.append('document_id', documentId);
    form.append('filename', name);
    form.append('folder_id', targetFolderId);
    if (useOCR) form.append('use_ocr', 'true');

    let response;
    try {
      response = await authService.authenticatedFetch(
        `${CONFIG.CITRA_SERVICE_URL}/v2/documents`,
        { method: 'POST', body: form }
      );
    } catch (error) {
      patchProgress(documentId, { stage: 'error', progress: 0, filename: name });
      throw new Error(`Upload failed for ${name}: ${error.message}`);
    }

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        detail = body?.detail || body?.message || detail;
      } catch (_parseError) {
        // Body wasn't JSON — the status code is all we have.
      }
      patchProgress(documentId, { stage: 'error', progress: 0, filename: name });
      throw new Error(`Upload failed for ${name}: ${detail}`);
    }

    const result = await response.json();
    patchProgress(documentId, { stage: 'complete', progress: 100, filename: name });

    // Clear the finished entry so the tile badge reflects only in-flight work.
    setTimeout(() => patchProgress(documentId, null), 4000);

    setUploadSuccess({
      visible: true,
      documentTitle: name,
      folderName: folderName || 'this artifact',
      isDefaultFolder: false,
    });

    return result;
  }, [patchProgress, folderName]);

  /** Pick N files and upload them sequentially, reporting the first failure. */
  const pickAndUpload = useCallback(async ({ accept, useOCR = false }) => {
    const files = await pickFilesWeb({ accept });
    if (!files.length) return;

    setUploadStatus({ isUploading: true, count: files.length });
    const failures = [];
    for (const file of files) {
      try {
        await uploadOne(file, { useOCR });
      } catch (error) {
        console.error('❌ [UPLOAD]', error.message);
        failures.push(error.message);
      }
    }
    setUploadStatus({ isUploading: false, count: 0 });

    if (failures.length) {
      throw new Error(failures.join('\n'));
    }
  }, [uploadOne]);

  const pickDocument = useCallback(
    () => pickAndUpload({ accept: DOC_ACCEPT, useOCR: false }),
    [pickAndUpload]
  );

  const pickDocumentOCR = useCallback(
    () => pickAndUpload({ accept: '.pdf,image/*', useOCR: true }),
    [pickAndUpload]
  );

  const pickImage = useCallback(
    () => pickAndUpload({ accept: IMAGE_ACCEPT, useOCR: false }),
    [pickAndUpload]
  );

  const pickAudioFile = useCallback(
    () => pickAndUpload({ accept: AUDIO_ACCEPT, useOCR: false }),
    [pickAndUpload]
  );

  /** Paste-text tile: embed raw text as a .txt document in the same folder. */
  const pasteText = useCallback(async (topic, content) => {
    const safeTopic = (topic || 'Pasted text').trim();
    const blob = new Blob([content], { type: 'text/plain' });
    const file = new File([blob], `${safeTopic}.txt`, { type: 'text/plain' });
    return uploadOne(file, { filename: `${safeTopic}.txt` });
  }, [uploadOne]);

  /** Internet tile, step 1: fetch page/query text without embedding it. */
  const internetIngestFetch = useCallback(async (queryOrUrl) => {
    const response = await authService.authenticatedFetch(
      `${CONFIG.CITRA_SERVICE_URL}/internet-ingest`,
      {
        method: 'POST',
        body: JSON.stringify({ query: queryOrUrl }),
      }
    );
    if (!response.ok) {
      throw new Error(`Internet fetch failed: HTTP ${response.status}`);
    }
    return response.json();
  }, []);

  /** Internet tile, step 2: embed the reviewed text. */
  const internetIngestEmbed = useCallback(
    (topic, text) => pasteText(topic, text),
    [pasteText]
  );

  return {
    uploadProgress,
    uploadSuccess,
    uploadStatus,
    setUploadSuccess,
    setUploadStatus,
    actions: {
      pickDocument,
      pickDocumentOCR,
      pickImage,
      pickAudioFile,
    },
    pasteText,
    internetIngestFetch,
    internetIngestEmbed,
  };
}
