// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Docker runtime override (window.__CITRA_ENV__) → build-time env → fallback
const _runtimeEnv = (typeof window !== 'undefined' && window.__CITRA_ENV__) ? window.__CITRA_ENV__ : {};
const COLLAB_SERVER_URL = _runtimeEnv.COLLAB_SERVER_URL || process.env.EXPO_PUBLIC_COLLAB_SERVER_URL || 'ws://localhost:1234';
const MAX_RECONNECT_ATTEMPTS = 5;
const MAX_BACKOFF_TIME = 30000; // 30 seconds cap on exponential backoff

// Kill switch, gates every consumer of this hook (Presentation, Printable,
// Report composers). Enabled by default — the collaboration-server
// (citra-decks/collaboration-server) must also have COLLABORATION_ENABLED=true
// and share the same JWT_SECRET, or every connection attempt will fail
// (server rejects the upgrade with 503 while its own switch is off, or 401
// if the secrets don't match).
const COLLABORATION_ENABLED = true;

/**
 * useCollaboration - Real-time collaboration hook with team/workspace support
 * 
 * @param {object} options
 * @param {string} options.docId - Document ID
 * @param {object} options.user - Current user info
 * @param {boolean} options.enabled - Whether collaboration is enabled
 * @param {string|null} options.teamId - Team ID (null for personal workspace)
 * 
 * Room naming convention:
 * - Personal workspace: `personal:{userId}:{docId}`
 * - Team workspace: `team:{teamId}:{docId}`
 * 
 * This ensures documents in different workspaces have isolated collaboration rooms
 */
export const useCollaboration = ({ docId, user, enabled = false, teamId = null }) => {
    // Collaboration is disabled platform-wide (see COLLABORATION_ENABLED).
    enabled = enabled && COLLABORATION_ENABLED;
    const [status, setStatus] = useState('disconnected'); // disconnected, connecting, connected
    const [collaborators, setCollaborators] = useState([]);
    const providerRef = useRef(null);
    const ydocRef = useRef(null);
    const isConnectingRef = useRef(false);
    const lastRoomNameRef = useRef(null);
    
    // Stable user reference - only update when email changes
    const userRef = useRef(user);
    useEffect(() => {
        if (user?.email !== userRef.current?.email) {
            userRef.current = user;
        }
    }, [user?.email]);

    // Generate room name based on team context
    // This ensures team members collaborate in team-scoped rooms
    // and personal content stays isolated
    const roomName = useMemo(() => {
        if (!docId) return null;
        
        if (teamId) {
            // Team workspace: team:{teamId}:{docId}
            return `team:${teamId}:${docId}`;
        } else if (user?.email) {
            // Personal workspace: personal:{userEmailHash}:{docId}
            // Use email to scope personal documents
            const userScope = user.email.split('@')[0];
            return `personal:${userScope}:${docId}`;
        }
        // Fallback (should not happen in practice)
        return docId;
    }, [docId, teamId, user?.email]);

    // Create Y.Doc instance - only create new one when room actually changes
    const ydoc = useMemo(() => {
        // Clean up old ydoc if room changed
        if (ydocRef.current && lastRoomNameRef.current !== roomName) {
            // Don't destroy here - let cleanup handle it
        }
        if (!roomName) return null;
        
        // Reuse existing ydoc if same room
        if (ydocRef.current && lastRoomNameRef.current === roomName) {
            return ydocRef.current;
        }
        
        const newDoc = new Y.Doc();
        ydocRef.current = newDoc;
        lastRoomNameRef.current = roomName;
        return newDoc;
    }, [roomName]);

    useEffect(() => {
        // Skip if not enabled, no room, or no ydoc
        if (!enabled || !roomName || !ydocRef.current) {
            setStatus('disconnected');
            return;
        }
        
        // Prevent duplicate connections
        if (isConnectingRef.current && providerRef.current) {
            console.log(`🔌 [COLLAB] Already connected/connecting to ${roomName}, skipping`);
            return;
        }

        const currentYdoc = ydocRef.current;
        let provider = null;
        let awarenessHandler = null;
        let isCancelled = false;
        isConnectingRef.current = true;

        const connect = async () => {
            console.log(`🔌 [COLLAB] Connecting to room: ${roomName}...`);
            setStatus('connecting');

            // Get auth token for WebSocket authentication
            let authToken = '';
            try {
                authToken = await AsyncStorage.getItem('@auth_token') || '';
            } catch (e) {
                console.warn('[COLLAB] Could not get auth token:', e);
            }

            if (isCancelled) {
                isConnectingRef.current = false;
                return; // Component unmounted during async
            }

            // Initialize WebSocket Provider with token and team context
            // Room format: {roomName}?token={token}&team={teamId}
            const params = new URLSearchParams();
            params.set('token', authToken);
            if (teamId) {
                params.set('team', teamId);
            }
            
            provider = new WebsocketProvider(
                COLLAB_SERVER_URL,
                `${roomName}?${params.toString()}`,
                currentYdoc,
                { maxBackoffTime: MAX_BACKOFF_TIME }
            );

            providerRef.current = provider;
            isConnectingRef.current = false;

            // Sync status handler
            provider.on('status', event => {
                console.log(`🔌 [COLLAB] Status: ${event.status}`);
                setStatus(event.status);
            });

            // Cap reconnect attempts at MAX_RECONNECT_ATTEMPTS
            provider.on('connection-close', () => {
                if (provider.wsUnsuccessfulReconnects >= MAX_RECONNECT_ATTEMPTS) {
                    console.warn(`🔌 [COLLAB] Max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached, giving up`);
                    provider.shouldConnect = false;
                    provider.disconnect();
                    setStatus('disconnected');
                }
            });

            // Awareness (User Presence)
            const awareness = provider.awareness;
            const currentUser = userRef.current;

            if (currentUser) {
                awareness.setLocalStateField('user', {
                    name: currentUser.name || 'Anonymous',
                    color: currentUser.color || '#' + Math.floor(Math.random() * 16777215).toString(16),
                    email: currentUser.email,
                    avatar: currentUser.avatar
                });
            }

            // Listen for awareness updates
            awarenessHandler = () => {
                const states = awareness.getStates();
                const users = Array.from(states.values()).map(s => s.user).filter(Boolean);
                setCollaborators(users);
            };

            awareness.on('change', awarenessHandler);
        };

        connect();

        // Cleanup
        return () => {
            isCancelled = true;
            isConnectingRef.current = false;
            console.log(`🔌 [COLLAB] Disconnecting from ${roomName}`);
            if (provider) {
                if (awarenessHandler) {
                    provider.awareness.off('change', awarenessHandler);
                }
                provider.disconnect();
            }
            providerRef.current = null;
            // Don't destroy ydoc here - it's managed by the useMemo
        };
    }, [roomName, enabled, teamId]); // Removed user and ydoc from deps to prevent reconnection loop

    const [aiLockedBy, setAiLockedBy] = useState(null);

    // AI Lock State Management
    useEffect(() => {
        if (!enabled || !ydoc || !providerRef.current) return; // Need provider for awareness

        const locksMap = ydoc.getMap('locks');
        const awareness = providerRef.current.awareness;

        const updateLockState = () => {
            const lockInfo = locksMap.get('ai_chat');

            // "Stale Lock" Check:
            if (lockInfo) {
                const now = Date.now();
                const LOCK_TIMEOUT = 10 * 60 * 1000; // 10 Minutes

                // 1. Check user presence (Awareness)
                const activeStates = awareness.getStates();
                const isUserActive = activeStates.has(lockInfo.clientId);

                // 2. Check timeout
                const isExpired = (now - lockInfo.timestamp) > LOCK_TIMEOUT;

                if (!isUserActive || isExpired) {
                    // Stale or Expired lock detected
                    if (status === 'connected') {
                        const reason = !isUserActive ? 'disconnected client' : 'timeout';
                        console.log(`[COLLAB] Auto-releasing stale lock (${reason}):`, lockInfo.clientId);
                        locksMap.set('ai_chat', null);
                    }

                    setAiLockedBy(null);
                    return;
                }
            }

            setAiLockedBy(lockInfo || null);
        };

        // Initial state
        updateLockState();

        locksMap.observe(updateLockState);
        awareness.on('change', updateLockState); // Re-check locks when users join/leave

        return () => {
            locksMap.unobserve(updateLockState);
            awareness.off('change', updateLockState);
        };
    }, [ydoc, enabled, status]); // providerRef is stable, status triggers re-check

    // Auto-release lock on unmount
    useEffect(() => {
        return () => {
            if (ydoc && status === 'connected') {
                const locksMap = ydoc.getMap('locks');
                const currentLock = locksMap.get('ai_chat');
                if (currentLock && currentLock.clientId === ydoc.clientID) {
                    console.log('[COLLAB] Releasing AI lock on unmount');
                    locksMap.set('ai_chat', null);
                }
            }
        };
    }, [ydoc, status]);

    // Request Lock function
    const requestAiLock = () => {
        if (!ydoc) return false;
        const locksMap = ydoc.getMap('locks');
        const currentLock = locksMap.get('ai_chat');

        // If no lock exists, or we already own it
        if (!currentLock || currentLock.clientId === ydoc.clientID) {
            // Set lock with our info
            locksMap.set('ai_chat', {
                clientId: ydoc.clientID,
                user: user,
                timestamp: Date.now()
            });
            return true;
        }
        return false; // Already locked by someone else
    };

    // Release Lock function
    const releaseAiLock = () => {
        if (!ydoc) return;
        const locksMap = ydoc.getMap('locks');
        const currentLock = locksMap.get('ai_chat');

        if (currentLock && currentLock.clientId === ydoc.clientID) {
            locksMap.set('ai_chat', null);
        }
    };

    const refreshAiLock = () => {
        // Just call requestAiLock again to update timestamp if we own it
        return requestAiLock();
    };

    // ========== GRANULAR LOCK SYSTEM ==========

    const [documentLock, setDocumentLock] = useState(null);
    const [slideLocks, setSlideLocks] = useState({}); // { 0: lockInfo, 1: lockInfo, ... }
    const [pageLocks, setPageLocks] = useState({}); // For reports

    // Document Lock State Management
    useEffect(() => {
        if (!enabled || !ydoc || !providerRef.current) return;

        const locksMap = ydoc.getMap('locks');
        const awareness = providerRef.current.awareness;

        const updateGranularLocks = () => {
            // Document lock
            const docLock = locksMap.get('document');
            if (docLock) {
                const activeStates = awareness.getStates();
                const isUserActive = activeStates.has(docLock.clientId);
                const isExpired = (Date.now() - docLock.timestamp) > 10 * 60 * 1000;

                if (!isUserActive || isExpired) {
                    if (status === 'connected') {
                        console.log('[COLLAB] Auto-releasing stale document lock');
                        locksMap.set('document', null);
                    }
                    setDocumentLock(null);
                } else {
                    setDocumentLock(docLock);
                }
            } else {
                setDocumentLock(null);
            }

            // Slide locks
            const newSlideLocks = {};
            locksMap.forEach((value, key) => {
                if (key.startsWith('slide:') && value) {
                    const index = parseInt(key.replace('slide:', ''));
                    const activeStates = awareness.getStates();
                    const isUserActive = activeStates.has(value.clientId);
                    const isExpired = (Date.now() - value.timestamp) > 10 * 60 * 1000;

                    if (!isUserActive || isExpired) {
                        if (status === 'connected') {
                            console.log(`[COLLAB] Auto-releasing stale slide lock: ${index}`);
                            locksMap.set(key, null);
                        }
                    } else {
                        newSlideLocks[index] = value;
                    }
                }
            });
            setSlideLocks(newSlideLocks);

            // Page locks (for reports)
            const newPageLocks = {};
            locksMap.forEach((value, key) => {
                if (key.startsWith('page:') && value) {
                    const index = parseInt(key.replace('page:', ''));
                    const activeStates = awareness.getStates();
                    const isUserActive = activeStates.has(value.clientId);
                    const isExpired = (Date.now() - value.timestamp) > 10 * 60 * 1000;

                    if (!isUserActive || isExpired) {
                        if (status === 'connected') {
                            console.log(`[COLLAB] Auto-releasing stale page lock: ${index}`);
                            locksMap.set(key, null);
                        }
                    } else {
                        newPageLocks[index] = value;
                    }
                }
            });
            setPageLocks(newPageLocks);
        };

        updateGranularLocks();
        locksMap.observe(updateGranularLocks);
        awareness.on('change', updateGranularLocks);

        return () => {
            locksMap.unobserve(updateGranularLocks);
            awareness.off('change', updateGranularLocks);
        };
    }, [ydoc, enabled, status]);

    // Request Document Lock (for Update button - locks entire document)
    const requestDocumentLock = () => {
        if (!ydoc) return false;
        const locksMap = ydoc.getMap('locks');

        // Check if document already locked by someone else
        const existingDocLock = locksMap.get('document');
        if (existingDocLock && existingDocLock.clientId !== ydoc.clientID) {
            console.log('[COLLAB] Cannot acquire document lock - already locked');
            return false;
        }

        // Check if any slide/page locks exist by others
        let hasConflict = false;
        locksMap.forEach((value, key) => {
            if ((key.startsWith('slide:') || key.startsWith('page:')) && value) {
                if (value.clientId !== ydoc.clientID) {
                    hasConflict = true;
                }
            }
        });

        if (hasConflict) {
            console.log('[COLLAB] Cannot acquire document lock - slide/page locks exist');
            return false;
        }

        // Acquire document lock
        locksMap.set('document', {
            clientId: ydoc.clientID,
            user: user,
            timestamp: Date.now()
        });
        console.log('[COLLAB] Document lock acquired');
        return true;
    };

    // Release Document Lock
    const releaseDocumentLock = () => {
        if (!ydoc) return;
        const locksMap = ydoc.getMap('locks');
        const currentLock = locksMap.get('document');

        if (currentLock && currentLock.clientId === ydoc.clientID) {
            locksMap.set('document', null);
            console.log('[COLLAB] Document lock released');
        }
    };

    // Request Slide Lock (for AI Chat on specific slide)
    const requestSlideLock = (slideIndex) => {
        if (!ydoc) return false;
        const locksMap = ydoc.getMap('locks');

        // Check if document is locked by someone else
        const docLock = locksMap.get('document');
        if (docLock && docLock.clientId !== ydoc.clientID) {
            console.log('[COLLAB] Cannot acquire slide lock - document is locked');
            return false;
        }

        // Check if this slide is locked by someone else
        const key = `slide:${slideIndex}`;
        const existingLock = locksMap.get(key);
        if (existingLock && existingLock.clientId !== ydoc.clientID) {
            console.log(`[COLLAB] Cannot acquire slide lock - slide ${slideIndex} is locked`);
            return false;
        }

        // Acquire slide lock
        locksMap.set(key, {
            clientId: ydoc.clientID,
            user: user,
            timestamp: Date.now()
        });
        console.log(`[COLLAB] Slide ${slideIndex} lock acquired`);
        return true;
    };

    // Release Slide Lock
    const releaseSlideLock = (slideIndex) => {
        if (!ydoc) return;
        const locksMap = ydoc.getMap('locks');
        const key = `slide:${slideIndex}`;
        const currentLock = locksMap.get(key);

        if (currentLock && currentLock.clientId === ydoc.clientID) {
            locksMap.set(key, null);
            console.log(`[COLLAB] Slide ${slideIndex} lock released`);
        }
    };

    // Request Page Lock (for AI Chat on specific report page)
    const requestPageLock = (pageIndex) => {
        if (!ydoc) return false;
        const locksMap = ydoc.getMap('locks');

        // Check if document is locked by someone else
        const docLock = locksMap.get('document');
        if (docLock && docLock.clientId !== ydoc.clientID) {
            console.log('[COLLAB] Cannot acquire page lock - document is locked');
            return false;
        }

        // Check if this page is locked by someone else
        const key = `page:${pageIndex}`;
        const existingLock = locksMap.get(key);
        if (existingLock && existingLock.clientId !== ydoc.clientID) {
            console.log(`[COLLAB] Cannot acquire page lock - page ${pageIndex} is locked`);
            return false;
        }

        // Acquire page lock
        locksMap.set(key, {
            clientId: ydoc.clientID,
            user: user,
            timestamp: Date.now()
        });
        console.log(`[COLLAB] Page ${pageIndex} lock acquired`);
        return true;
    };

    // Release Page Lock
    const releasePageLock = (pageIndex) => {
        if (!ydoc) return;
        const locksMap = ydoc.getMap('locks');
        const key = `page:${pageIndex}`;
        const currentLock = locksMap.get(key);

        if (currentLock && currentLock.clientId === ydoc.clientID) {
            locksMap.set(key, null);
            console.log(`[COLLAB] Page ${pageIndex} lock released`);
        }
    };

    // Release all locks owned by this client (for cleanup)
    const releaseAllLocks = () => {
        releaseAiLock();
        releaseDocumentLock();
        if (!ydoc) return;
        const locksMap = ydoc.getMap('locks');
        locksMap.forEach((value, key) => {
            if (value && value.clientId === ydoc.clientID) {
                locksMap.set(key, null);
            }
        });
        console.log('[COLLAB] All locks released');
    };

    // Helper: Check if a slide is locked by someone else
    const isSlideLocked = (slideIndex) => {
        // Document lock blocks everything
        if (documentLock && ydoc && documentLock.clientId !== ydoc.clientID) {
            return { locked: true, by: documentLock.user, type: 'document' };
        }
        // Check specific slide lock
        const slideLock = slideLocks[slideIndex];
        if (slideLock && ydoc && slideLock.clientId !== ydoc.clientID) {
            return { locked: true, by: slideLock.user, type: 'slide' };
        }
        return { locked: false };
    };

    // Helper: Check if a page is locked by someone else
    const isPageLocked = (pageIndex) => {
        // Document lock blocks everything
        if (documentLock && ydoc && documentLock.clientId !== ydoc.clientID) {
            return { locked: true, by: documentLock.user, type: 'document' };
        }
        // Check specific page lock
        const pageLock = pageLocks[pageIndex];
        if (pageLock && ydoc && pageLock.clientId !== ydoc.clientID) {
            return { locked: true, by: pageLock.user, type: 'page' };
        }
        return { locked: false };
    };

    return {
        ydoc,
        provider: (enabled && providerRef.current) ? providerRef.current : null,
        status,
        collaborators,
        // Room info for debugging/display
        roomName,
        teamId,
        // Legacy AI lock (still works)
        aiLockedBy,
        requestAiLock,
        releaseAiLock,
        refreshAiLock,
        // Granular locks
        documentLock,
        slideLocks,
        pageLocks,
        requestDocumentLock,
        releaseDocumentLock,
        requestSlideLock,
        releaseSlideLock,
        requestPageLock,
        releasePageLock,
        releaseAllLocks,
        isSlideLocked,
        isPageLocked
    };
};

/* 
Note: We need to modify the hook to store the provider in state or ref to return it.
Refactoring slightly to keep provider in ref or state.
*/
export const useCollaborationRefined = ({ docId, user, enabled = false }) => {
    // Collaboration is disabled platform-wide (see COLLABORATION_ENABLED).
    enabled = enabled && COLLABORATION_ENABLED;
    const [provider, setProvider] = useState(null);
    const [status, setStatus] = useState('disconnected');
    const [collaborators, setCollaborators] = useState([]);

    const ydoc = useMemo(() => new Y.Doc(), [docId]);

    useEffect(() => {
        if (!enabled || !docId) return;

        const wsProvider = new WebsocketProvider(
            COLLAB_SERVER_URL,
            docId,
            ydoc
        );

        wsProvider.on('status', event => setStatus(event.status));

        if (user) {
            wsProvider.awareness.setLocalStateField('user', {
                name: user.name || 'Anonymous',
                color: user.color || '#3b82f6',
                email: user.email
            });
        }

        const handleAwareness = () => {
            const states = wsProvider.awareness.getStates();
            const users = Array.from(states.values()).map(s => s.user).filter(Boolean);
            // Deduplicate by email/id if needed, but raw list is fine for cursors
            setCollaborators(users);
        };

        wsProvider.awareness.on('change', handleAwareness);
        setProvider(wsProvider);

        return () => {
            wsProvider.disconnect();
            wsProvider.destroy();
            setProvider(null);
        };
    }, [docId, enabled, ydoc]); // Removing user from dependency to avoid reconnects on minor user object changes

    return { ydoc, provider, status, collaborators };
};

export default useCollaborationRefined;
