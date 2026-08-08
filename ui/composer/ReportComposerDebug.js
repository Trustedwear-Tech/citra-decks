// ReportComposerDebug.js - Minimal test version
import React from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const ReportComposerDebug = ({ 
  visible, 
  onClose, 
  theme
}) => {
  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={onClose}
    >
      <View style={{ flex: 1, backgroundColor: theme.background }}>
        <View style={{ flexDirection: 'row', padding: 20, alignItems: 'center' }}>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={theme.text} />
          </TouchableOpacity>
          <Text style={{ marginLeft: 20, fontSize: 18, color: theme.text }}>
            Debug Report Composer
          </Text>
        </View>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <Text style={{ color: theme.text, fontSize: 16 }}>
            Minimal test version loaded successfully!
          </Text>
        </View>
      </View>
    </Modal>
  );
};

export default ReportComposerDebug;
