// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * FabricYjsBinder - Binds a Fabric.js canvas to Yjs Awareness
 * Handles remote cursors and selection highlighting (object locking)
 */
export class FabricYjsBinder {
    constructor(canvas, awareness, localUser) {
        this.canvas = canvas;
        this.awareness = awareness;
        this.localUser = localUser;

        // Map of clientID -> { cursor: FabricObject, label: FabricObject, selection: FabricObject }
        this.remoteCursors = new Map();

        // Map of clientID -> { elementIds: [], selectionGroup: FabricObject, objects: [], originalStates: Map }
        this.remoteSelections = new Map();

        // Bind methods
        this.handleMouseMove = this.handleMouseMove.bind(this);
        this.handleSelection = this.handleSelection.bind(this);
        this.handleAwarenessUpdate = this.handleAwarenessUpdate.bind(this);

        this.isBound = false;
    }

    bind() {
        if (this.isBound) return;

        if (!this.canvas || !this.awareness) {
            console.warn('[FabricYjsBinder] Missing canvas or awareness');
            return;
        }

        console.log('[FabricYjsBinder] Binding to canvas');

        // Local events -> Awareness
        this.canvas.on('mouse:move', this.handleMouseMove);
        this.canvas.on('selection:created', this.handleSelection);
        this.canvas.on('selection:updated', this.handleSelection);
        this.canvas.on('selection:cleared', this.handleSelection);

        // Awareness -> Remote Render
        this.awareness.on('change', this.handleAwarenessUpdate);

        this.isBound = true;

        // Activity tracking for local selection
        this.lastLocalActivity = Date.now();
        this.inactivityInterval = setInterval(() => {
            this.checkInactivity();
        }, 60 * 1000); // Check every minute
    }

    unbind() {
        if (!this.isBound) return;

        clearInterval(this.inactivityInterval);

        this.canvas.off('mouse:move', this.handleMouseMove);
        this.canvas.off('selection:created', this.handleSelection);
        this.canvas.off('selection:updated', this.handleSelection);
        this.canvas.off('selection:cleared', this.handleSelection);
        this.canvas.off('object:moving', this.handleActivity);
        this.canvas.off('object:scaling', this.handleActivity);
        this.canvas.off('object:rotating', this.handleActivity);
        this.canvas.off('object:modified', this.handleActivity);

        this.awareness.off('change', this.handleAwarenessUpdate);

        // Clear remote cursors from canvas
        this.remoteCursors.forEach(cursorObj => {
            this.removeCursor(cursorObj);
        });
        this.remoteCursors.clear();

        // Clear selections
        this.remoteSelections.forEach((val, clientId) => {
            this.clearRemoteSelection(clientId);
        });

        this.isBound = false;
    }

    handleActivity = () => {
        this.lastLocalActivity = Date.now();
    }

    checkInactivity() {
        if (!this.canvas) return;
        const activeObject = this.canvas.getActiveObject();

        // If we have a selection and it's been idle > 10 mins
        if (activeObject && (Date.now() - this.lastLocalActivity > 10 * 60 * 1000)) {
            console.log('[FabricYjsBinder] Auto-releasing selection due to inactivity');
            this.canvas.discardActiveObject();
            this.canvas.requestRenderAll();
            // This will trigger 'selection:cleared' -> updates awareness
            this.handleSelection();
        }
    }

    handleMouseMove(e) {
        if (!e.pointer) return;

        const { x, y } = e.pointer;

        this.awareness.setLocalStateField('cursor', {
            x,
            y,
            slideId: this.currentSlideId // We need to track which slide we are on
        });
    }

    handleSelection(e) {
        const selected = this.canvas.getActiveObjects();
        const selectedIds = selected.map(obj => obj.elementId).filter(Boolean);

        this.awareness.setLocalStateField('selection', {
            elementIds: selectedIds,
            slideId: this.currentSlideId
        });
    }

    // Method to update current slide context
    setCurrentSlideId(slideId) {
        this.currentSlideId = slideId;
        this.awareness.setLocalStateField('currentSlideId', slideId);

        // Clear remote states that don't match new slide
        this.handleAwarenessUpdate({ added: [], updated: [], removed: [] });
        // ^ Trigger generic cleanup
    }

    handleAwarenessUpdate({ added, updated, removed }) {
        const states = this.awareness.getStates();

        // Handle added/updated
        states.forEach((state, clientId) => {
            if (clientId === this.awareness.doc.clientID) return; // Ignore self

            // Check if user is on same slide
            if (state.currentSlideId !== this.currentSlideId) {
                // Remove if they moved away
                this.clearRemoteState(clientId);
                return;
            }

            if (state.cursor) {
                this.updateRemoteCursor(clientId, state);
            }

            if (state.selection) {
                this.updateRemoteSelection(clientId, state);
            } else {
                this.clearRemoteSelection(clientId);
            }
        });

        // Handle removed
        removed.forEach(clientId => {
            this.clearRemoteState(clientId);
        });
    }

    clearRemoteState(clientId) {
        if (this.remoteCursors.has(clientId)) {
            this.removeCursor(this.remoteCursors.get(clientId));
            this.remoteCursors.delete(clientId);
        }
        // This effectively releases any object locks held by this client
        // because updateRemoteSelection is awareness-driven.
        this.clearRemoteSelection(clientId);
    }

    updateRemoteCursor(clientId, state) {
        const { cursor, user } = state;
        if (!cursor) return;

        const color = user?.color || '#FF0000';
        const name = user?.name || 'User ' + clientId;

        // Check if cursor object exists
        let cursorObj = this.remoteCursors.get(clientId);

        if (!cursorObj) {
            // Create new cursor
            cursorObj = this.createCursorObject(color, name);
            this.remoteCursors.set(clientId, cursorObj);
            this.canvas.add(cursorObj.group);
        }

        // Update position
        cursorObj.group.set({
            left: cursor.x,
            top: cursor.y
        });

        cursorObj.group.setCoords();
        this.canvas.requestRenderAll();
    }

    updateRemoteSelection(clientId, state) {
        const { selection, user } = state;
        const elementIds = selection?.elementIds || [];

        const current = this.remoteSelections.get(clientId);
        // Optimization: avoid re-locking if same
        if (current && JSON.stringify(current.elementIds) === JSON.stringify(elementIds)) {
            return;
        }

        this.clearRemoteSelection(clientId);

        if (elementIds.length === 0) return;

        const color = user?.color || '#FF0000';
        const name = user?.name || 'User ' + clientId;

        const objectsToLock = [];
        const canvasObjects = this.canvas.getObjects();

        elementIds.forEach(id => {
            const obj = canvasObjects.find(o => o.elementId === id);
            if (obj) objectsToLock.push(obj);
        });

        if (objectsToLock.length === 0) return;

        // Store original states and lock
        const originalStates = new Map();
        objectsToLock.forEach(obj => {
            originalStates.set(obj, {
                lockMovementX: obj.lockMovementX,
                lockMovementY: obj.lockMovementY,
                lockRotation: obj.lockRotation,
                lockScalingX: obj.lockScalingX,
                lockScalingY: obj.lockScalingY,
                selectable: obj.selectable,
                evented: obj.evented
            });

            obj.set({
                lockMovementX: true,
                lockMovementY: true,
                lockRotation: true,
                lockScalingX: true,
                lockScalingY: true,
                selectable: false,
                evented: false
            });
        });

        // Visual Bounding Box (Locked Indicator)
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        objectsToLock.forEach(obj => {
            const br = obj.getBoundingRect();
            minX = Math.min(minX, br.left);
            minY = Math.min(minY, br.top);
            maxX = Math.max(maxX, br.left + br.width);
            maxY = Math.max(maxY, br.top + br.height);
        });

        const pad = 4;
        minX -= pad; minY -= pad; maxX += pad; maxY += pad;

        const box = new window.fabric.Rect({
            left: minX,
            top: minY,
            width: maxX - minX,
            height: maxY - minY,
            fill: 'transparent',
            stroke: color,
            strokeWidth: 2,
            selectable: false,
            evented: false,
            excludeFromExport: true
        });

        const label = new window.fabric.Text(`${name} (Editing)`, {
            left: minX,
            top: minY - 20,
            fontSize: 12,
            fontFamily: 'Inter',
            fill: 'white',
            backgroundColor: color,
            padding: 4,
            rx: 4,
            ry: 4,
            selectable: false,
            evented: false,
            excludeFromExport: true
        });

        const selectionGroup = new window.fabric.Group([box, label], {
            selectable: false,
            evented: false,
            excludeFromExport: true
        });

        this.canvas.add(selectionGroup);
        this.canvas.requestRenderAll();

        this.remoteSelections.set(clientId, {
            elementIds,
            selectionGroup,
            objects: objectsToLock,
            originalStates
        });
    }

    clearRemoteSelection(clientId) {
        const current = this.remoteSelections.get(clientId);
        if (!current) return;

        // Restore
        current.objects.forEach(obj => {
            const original = current.originalStates.get(obj);
            if (original) {
                obj.set(original);
            }
        });

        this.canvas.remove(current.selectionGroup);
        this.canvas.requestRenderAll();

        this.remoteSelections.delete(clientId);
    }

    createCursorObject(color, name) {
        const fabric = window.fabric;
        if (!fabric) return null;

        const cursorPath = 'M 0 0 L 12 12 L 0 16 Z';

        const pointer = new fabric.Path(cursorPath, {
            fill: color,
            stroke: 'white',
            strokeWidth: 1,
            originX: 'left',
            originY: 'top'
        });

        const text = new fabric.Text(name, {
            fontFamily: 'Inter',
            fontSize: 12,
            fill: 'white',
            backgroundColor: color,
            left: 10,
            top: 10,
            originX: 'left',
            originY: 'top',
            rx: 4,
            ry: 4,
            padding: 4
        });

        const group = new fabric.Group([pointer, text], {
            selectable: false,
            evented: false,
            excludeFromExport: true,
            hoverCursor: 'default'
        });

        return { group };
    }

    removeCursor(cursorObj) {
        if (cursorObj && cursorObj.group) {
            this.canvas.remove(cursorObj.group);
            this.canvas.requestRenderAll();
        }
    }
}
