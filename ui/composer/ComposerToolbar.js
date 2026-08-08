// ComposerToolbar.js - Shared toolbar for continuous scroll mode
// Renders a single fixed toolbar above the ScrollView, controlling the active editor
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import {
  ToolbarButton,
  ToolbarDivider,
  TableSizePicker,
  LinkInputPopover,
  ColorPickerPopover,
  FontFamilyPopover,
  TextAlignPopover,
} from './TiptapEditor.web';

/**
 * ComposerToolbar - a single shared toolbar that operates on the currently active TipTap editor.
 * Props:
 *  - editorRef: ref whose .current points to the active TiptapEditor imperative handle
 *  - theme: app theme object
 *  - disabled: if true, disable all buttons
 *  - currentPageId: triggers re-render when active page changes
 */
const ComposerToolbar = ({ editorRef, theme = {}, disabled = false, currentPageId, isMobile = false }) => {
  // Force re-render when editor state changes (selection, formatting)
  const [, forceUpdate] = useState(0);
  const updateTimerRef = useRef(null);

  // Popover state (managed locally, not in individual editors)
  const [showTablePicker, setShowTablePicker] = useState(false);
  const [tablePickerAnchor, setTablePickerAnchor] = useState(null);
  const [showLinkPopover, setShowLinkPopover] = useState(false);
  const [linkPopoverAnchor, setLinkPopoverAnchor] = useState(null);
  const [currentLinkUrl, setCurrentLinkUrl] = useState('');
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [colorPickerAnchor, setColorPickerAnchor] = useState(null);
  const [showFontPicker, setShowFontPicker] = useState(false);
  const [fontPickerAnchor, setFontPickerAnchor] = useState(null);
  const [showAlignPicker, setShowAlignPicker] = useState(false);
  const [alignPickerAnchor, setAlignPickerAnchor] = useState(null);

  // Get the underlying TipTap editor instance
  const getEditor = useCallback(() => {
    return editorRef?.current?.getEditor?.();
  }, [editorRef]);

  // Listen to editor transactions to update toolbar active states
  useEffect(() => {
    const editor = getEditor();
    if (!editor) return;

    const handleTransaction = () => {
      // Debounce toolbar state updates to avoid excessive re-renders
      if (updateTimerRef.current) clearTimeout(updateTimerRef.current);
      updateTimerRef.current = setTimeout(() => forceUpdate(n => n + 1), 50);
    };

    editor.on('transaction', handleTransaction);
    editor.on('selectionUpdate', handleTransaction);

    // Initial state sync
    forceUpdate(n => n + 1);

    return () => {
      editor.off('transaction', handleTransaction);
      editor.off('selectionUpdate', handleTransaction);
      if (updateTimerRef.current) clearTimeout(updateTimerRef.current);
    };
  }, [getEditor, currentPageId]);

  const editor = getEditor();

  // Toolbar actions
  const toggleBold = useCallback(() => editor?.chain().focus().toggleBold().run(), [editor]);
  const toggleItalic = useCallback(() => editor?.chain().focus().toggleItalic().run(), [editor]);
  const toggleUnderline = useCallback(() => editor?.chain().focus().toggleUnderline().run(), [editor]);
  const toggleStrike = useCallback(() => editor?.chain().focus().toggleStrike().run(), [editor]);
  const toggleBulletList = useCallback(() => editor?.chain().focus().toggleBulletList().run(), [editor]);
  const toggleOrderedList = useCallback(() => editor?.chain().focus().toggleOrderedList().run(), [editor]);
  const toggleBlockquote = useCallback(() => editor?.chain().focus().toggleBlockquote().run(), [editor]);
  const undo = useCallback(() => editor?.chain().focus().undo().run(), [editor]);
  const redo = useCallback(() => editor?.chain().focus().redo().run(), [editor]);
  const clearFormatting = useCallback(() => editor?.chain().focus().unsetAllMarks().clearNodes().run(), [editor]);

  const setHeading = useCallback((level) => {
    editor?.chain().focus().toggleHeading({ level }).run();
  }, [editor]);

  const insertTable = useCallback((rows = 3, cols = 3) => {
    editor?.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run();
    setShowTablePicker(false);
  }, [editor]);

  const handleTableButtonClick = useCallback((event) => {
    const rect = event?.currentTarget?.getBoundingClientRect?.();
    if (rect) {
      setTablePickerAnchor({ top: rect.bottom + 5, left: rect.left - 50 });
    } else {
      setTablePickerAnchor({ top: 150, left: 300 });
    }
    setShowTablePicker(true);
  }, []);

  const addTableRowAfter = useCallback(() => editor?.chain().focus().addRowAfter().run(), [editor]);
  const addTableColumnAfter = useCallback(() => editor?.chain().focus().addColumnAfter().run(), [editor]);
  const deleteTable = useCallback(() => editor?.chain().focus().deleteTable().run(), [editor]);
  const deleteRow = useCallback(() => editor?.chain().focus().deleteRow().run(), [editor]);
  const deleteColumn = useCallback(() => editor?.chain().focus().deleteColumn().run(), [editor]);

  // Link
  const handleLinkButtonClick = useCallback((event) => {
    const currentUrl = editor?.getAttributes('link')?.href || '';
    setCurrentLinkUrl(currentUrl);
    const rect = event?.currentTarget?.getBoundingClientRect?.();
    if (rect) {
      setLinkPopoverAnchor({ top: rect.bottom + 5, left: rect.left - 100 });
    } else {
      setLinkPopoverAnchor({ top: 150, left: 300 });
    }
    setShowLinkPopover(true);
  }, [editor]);

  const applyLink = useCallback((url) => {
    if (url) editor?.chain().focus().setLink({ href: url }).run();
    setShowLinkPopover(false);
  }, [editor]);

  const removeLink = useCallback(() => {
    editor?.chain().focus().unsetLink().run();
  }, [editor]);

  // Image — trigger the hidden file input inside the active TiptapEditor
  const addImage = useCallback(() => {
    editorRef?.current?.addImage?.();
  }, [editorRef]);

  // Video / Embed — open modals via editor ref
  const openVideoModal = useCallback(() => {
    editorRef?.current?.openVideoModal?.();
  }, [editorRef]);

  const openEmbedModal = useCallback(() => {
    editorRef?.current?.openEmbedModal?.();
  }, [editorRef]);

  // Color picker
  const handleColorButtonClick = useCallback((event) => {
    const rect = event?.currentTarget?.getBoundingClientRect?.();
    if (rect) {
      setColorPickerAnchor({ top: rect.bottom + 5, left: rect.left - 80 });
    } else {
      setColorPickerAnchor({ top: 150, left: 300 });
    }
    setShowColorPicker(true);
  }, []);

  const setTextColor = useCallback((color) => editor?.chain().focus().setColor(color).run(), [editor]);
  const clearTextColor = useCallback(() => editor?.chain().focus().unsetColor().run(), [editor]);
  const setHighlightColor = useCallback((color) => editor?.chain().focus().setHighlight({ color }).run(), [editor]);
  const clearHighlight = useCallback(() => editor?.chain().focus().unsetHighlight().run(), [editor]);

  // Font family
  const handleFontButtonClick = useCallback((event) => {
    const rect = event?.currentTarget?.getBoundingClientRect?.();
    if (rect) {
      setFontPickerAnchor({ top: rect.bottom + 5, left: rect.left - 60 });
    } else {
      setFontPickerAnchor({ top: 150, left: 300 });
    }
    setShowFontPicker(true);
  }, []);

  const setFontFamily = useCallback((family) => {
    if (family) {
      editor?.chain().focus().setFontFamily(family).run();
    } else {
      editor?.chain().focus().unsetFontFamily().run();
    }
  }, [editor]);

  // Text alignment
  const handleAlignButtonClick = useCallback((event) => {
    const rect = event?.currentTarget?.getBoundingClientRect?.();
    if (rect) {
      setAlignPickerAnchor({ top: rect.bottom + 5, left: rect.left - 60 });
    } else {
      setAlignPickerAnchor({ top: 150, left: 300 });
    }
    setShowAlignPicker(true);
  }, []);

  const setTextAlign = useCallback((alignment) => {
    editor?.chain().focus().setTextAlign(alignment).run();
  }, [editor]);

  // Current styling state
  const currentTextColor = editor?.getAttributes('textStyle')?.color || null;
  const currentHighlight = editor?.getAttributes('highlight')?.color || null;
  const currentFontFamily = editor?.getAttributes('textStyle')?.fontFamily || null;
  const currentAlignment = editor?.isActive({ textAlign: 'center' }) ? 'center' :
    editor?.isActive({ textAlign: 'right' }) ? 'right' :
      editor?.isActive({ textAlign: 'justify' }) ? 'justify' : 'left';

  const isInTable = editor?.isActive('table') || false;
  const isDisabled = disabled || !editor;

  const toolbarContent = (
    <>
      {/* Undo/Redo */}
      <ToolbarButton icon="undo" onPress={undo} title="Undo" disabled={isDisabled || !editor?.can().undo()} />
      <ToolbarButton icon="redo" onPress={redo} title="Redo" disabled={isDisabled || !editor?.can().redo()} />

        <ToolbarDivider />

        {/* Headings */}
        <ToolbarButton icon="title" onPress={() => setHeading(2)} isActive={editor?.isActive('heading', { level: 2 })} title="Heading 2" disabled={isDisabled} />
        <ToolbarButton icon="format-size" onPress={() => setHeading(3)} isActive={editor?.isActive('heading', { level: 3 })} title="Heading 3" disabled={isDisabled} />

        <ToolbarDivider />

        {/* Text formatting */}
        <ToolbarButton icon="format-bold" onPress={toggleBold} isActive={editor?.isActive('bold')} title="Bold" disabled={isDisabled} />
        <ToolbarButton icon="format-italic" onPress={toggleItalic} isActive={editor?.isActive('italic')} title="Italic" disabled={isDisabled} />
        <ToolbarButton icon="format-underlined" onPress={toggleUnderline} isActive={editor?.isActive('underline')} title="Underline" disabled={isDisabled} />
        <ToolbarButton icon="strikethrough-s" onPress={toggleStrike} isActive={editor?.isActive('strike')} title="Strikethrough" disabled={isDisabled} />

        <ToolbarDivider />

        {/* Text & Highlight Color */}
        <TouchableOpacity
          onPress={handleColorButtonClick}
          disabled={isDisabled}
          style={[
            styles.toolbarButton,
            (currentTextColor || currentHighlight) && styles.toolbarButtonActive,
            isDisabled && styles.toolbarButtonDisabled
          ]}
          title="Text & Highlight Color"
        >
          <View style={{ alignItems: 'center' }}>
            <MaterialIcons name="format-color-text" size={18} color={currentTextColor || '#555'} />
            <View style={{
              height: 3, width: 16,
              backgroundColor: currentHighlight || currentTextColor || '#555',
              borderRadius: 1, marginTop: 1,
            }} />
          </View>
        </TouchableOpacity>

        {/* Font Family */}
        <ToolbarButton icon="font-download" onPress={handleFontButtonClick} isActive={!!currentFontFamily} title="Font Family" disabled={isDisabled} />

        {/* Text Alignment */}
        <ToolbarButton
          icon={currentAlignment === 'center' ? 'format-align-center' :
            currentAlignment === 'right' ? 'format-align-right' :
              currentAlignment === 'justify' ? 'format-align-justify' : 'format-align-left'}
          onPress={handleAlignButtonClick}
          isActive={currentAlignment !== 'left'}
          title="Text Alignment"
          disabled={isDisabled}
        />

        <ToolbarDivider />

        {/* Lists */}
        <ToolbarButton icon="format-list-bulleted" onPress={toggleBulletList} isActive={editor?.isActive('bulletList')} title="Bullet List" disabled={isDisabled} />
        <ToolbarButton icon="format-list-numbered" onPress={toggleOrderedList} isActive={editor?.isActive('orderedList')} title="Numbered List" disabled={isDisabled} />
        <ToolbarButton icon="format-quote" onPress={toggleBlockquote} isActive={editor?.isActive('blockquote')} title="Quote" disabled={isDisabled} />

        <ToolbarDivider />

        {/* Table */}
        <ToolbarButton icon="table-chart" onPress={handleTableButtonClick} title="Insert Table" disabled={isDisabled} />
        {isInTable && (
          <>
            <ToolbarButton icon="add-box" onPress={addTableRowAfter} title="Add Row Below" />
            <ToolbarButton icon="library-add" onPress={addTableColumnAfter} title="Add Column Right" />
            <ToolbarButton icon="remove-circle-outline" onPress={deleteRow} title="Delete Row" />
            <ToolbarButton icon="cancel" onPress={deleteColumn} title="Delete Column" />
            <ToolbarButton icon="delete-forever" onPress={deleteTable} title="Delete Table" />
          </>
        )}

        <ToolbarDivider />

        {/* Media */}
        <ToolbarButton icon="image" onPress={addImage} title="Insert Image" disabled={isDisabled} />
        {/* Insert Video + Insert Embed — HIDDEN for now (kept for future). Flip `false`. */}
        {false && <ToolbarButton icon="movie" onPress={openVideoModal} title="Insert Video" disabled={isDisabled} />}
        {false && <ToolbarButton icon="code" onPress={openEmbedModal} title="Insert Embed" disabled={isDisabled} />}

        <ToolbarDivider />

        {/* Link */}
        <ToolbarButton icon="link" onPress={handleLinkButtonClick} isActive={editor?.isActive('link')} title="Add Link" disabled={isDisabled} />
        {editor?.isActive('link') && (
          <ToolbarButton icon="link-off" onPress={removeLink} title="Remove Link" />
        )}

        <ToolbarDivider />

      {/* Clear formatting */}
      <ToolbarButton icon="format-clear" onPress={clearFormatting} title="Clear Formatting" disabled={isDisabled} />
    </>
  );

  return (
    <View style={styles.wrapper}>
      {isMobile ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.mobileScrollWrapper}
          contentContainerStyle={[styles.toolbar, { flexWrap: 'nowrap' }]}
        >
          {toolbarContent}
        </ScrollView>
      ) : (
        <View style={styles.toolbar} className="composer-toolbar-sticky">
          {toolbarContent}
        </View>
      )}

      {/* Popovers */}
      <TableSizePicker
        visible={showTablePicker}
        onSelect={(rows, cols) => insertTable(rows, cols)}
        onClose={() => setShowTablePicker(false)}
        anchorPosition={tablePickerAnchor}
      />
      <LinkInputPopover
        visible={showLinkPopover}
        onApply={applyLink}
        onClose={() => setShowLinkPopover(false)}
        anchorPosition={linkPopoverAnchor}
        initialUrl={currentLinkUrl}
      />
      <ColorPickerPopover
        visible={showColorPicker}
        onClose={() => setShowColorPicker(false)}
        anchorPosition={colorPickerAnchor}
        onSelectColor={setTextColor}
        onSelectHighlight={setHighlightColor}
        onClearColor={clearTextColor}
        onClearHighlight={clearHighlight}
        currentColor={currentTextColor}
        currentHighlight={currentHighlight}
      />
      <FontFamilyPopover
        visible={showFontPicker}
        onClose={() => setShowFontPicker(false)}
        anchorPosition={fontPickerAnchor}
        onSelectFont={setFontFamily}
        currentFont={currentFontFamily}
      />
      <TextAlignPopover
        visible={showAlignPicker}
        onClose={() => setShowAlignPicker(false)}
        anchorPosition={alignPickerAnchor}
        onSelectAlign={setTextAlign}
        currentAlign={currentAlignment}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    zIndex: 100,
    position: 'relative',
  },
  toolbar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    paddingVertical: 4,
    paddingHorizontal: 8,
    backgroundColor: '#f8f9fa',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
    gap: 2,
    flexShrink: 0,
  },
  toolbarButton: {
    padding: 8,
    borderRadius: 4,
    backgroundColor: 'transparent',
  },
  toolbarButtonActive: {
    backgroundColor: '#e3f2fd',
  },
  toolbarButtonDisabled: {
    opacity: 0.4,
  },
  mobileScrollWrapper: {
    maxHeight: 44,
  },
});

export default React.memo(ComposerToolbar);
