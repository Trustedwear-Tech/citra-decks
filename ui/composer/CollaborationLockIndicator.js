// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * CollaborationLockIndicator Component
 * 
 * Displays a banner indicating who has locked the document or current slide/page.
 * Shown at the top of the composer when collaboration is active.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';

const CollaborationLockIndicator = ({
    documentLock,
    currentSlideLock,
    currentPageLock,
    ownClientId,
    type = 'presentation' // 'presentation' or 'report'
}) => {
    // Determine which lock to show (document takes priority)
    let lockInfo = null;
    let lockType = null;
    let lockScope = null;

    if (documentLock && documentLock.clientId !== ownClientId) {
        lockInfo = documentLock;
        lockType = 'document';
        lockScope = 'Entire document';
    } else if (type === 'presentation' && currentSlideLock && currentSlideLock.clientId !== ownClientId) {
        lockInfo = currentSlideLock;
        lockType = 'slide';
        lockScope = 'This slide';
    } else if (type === 'report' && currentPageLock && currentPageLock.clientId !== ownClientId) {
        lockInfo = currentPageLock;
        lockType = 'page';
        lockScope = 'This page';
    }

    if (!lockInfo) {
        return null;
    }

    const userName = lockInfo.user?.name || lockInfo.user?.email || 'Another user';
    const userColor = lockInfo.user?.color || '#ef4444';

    return (
        <View style={[styles.container, { borderLeftColor: userColor }]}>
            <MaterialIcons name="lock" size={18} color={userColor} />
            <View style={styles.textContainer}>
                <Text style={styles.lockText}>
                    <Text style={[styles.userName, { color: userColor }]}>{userName}</Text>
                    {lockType === 'document'
                        ? ' is updating all slides'
                        : lockType === 'slide'
                            ? ' is editing this slide'
                            : ' is editing this page'}
                </Text>
                <Text style={styles.scopeText}>{lockScope} • View only</Text>
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderLeftWidth: 4,
        gap: 12,
    },
    textContainer: {
        flex: 1,
    },
    lockText: {
        color: '#fff',
        fontSize: 14,
    },
    userName: {
        fontWeight: '600',
    },
    scopeText: {
        color: 'rgba(255, 255, 255, 0.6)',
        fontSize: 12,
        marginTop: 2,
    },
});

export default CollaborationLockIndicator;
