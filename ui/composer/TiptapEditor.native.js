// TiptapEditor.js - Native fallback (or future WebView implementation)
import React, { forwardRef, useImperativeHandle } from 'react';
import { View, Text, StyleSheet } from 'react-native';

const TiptapEditor = forwardRef((props, ref) => {
  console.log('📱 [TIPTAP] Native (Fallback) Component Rendering');
  // Expose empty methods to prevent crashes if ref is called
  useImperativeHandle(ref, () => ({
    getEditor: () => null,
    getHTML: () => '',
    getText: () => '',
    setContent: () => { },
    insertContent: () => { },
    replaceSelection: () => { },
    getSelection: () => ({ from: 0, to: 0, empty: true, selectedText: '' }),
    focus: () => { },
    isReady: () => false
  }));

  return (
    <View style={styles.container}>
      <Text style={styles.text}>Rich Text Editor is only available on Web.</Text>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    padding: 20,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
    height: 200
  },
  text: {
    color: '#666'
  }
});

export default TiptapEditor;
