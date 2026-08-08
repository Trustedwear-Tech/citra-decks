// Test ReportComposer Dependencies - Minimal Test Component
import React from 'react';
import { View, Text } from 'react-native';

// Test individual imports one by one
console.log('Testing ReportComposer dependencies...');

// Test 1: Basic React Native components (should work)
const TestBasicComponents = () => {
  return (
    <View>
      <Text>Basic components work</Text>
    </View>
  );
};

// Test 2: Icon import
try {
  const { MaterialIcons } = require('@expo/vector-icons');
  console.log('✅ MaterialIcons import successful');
} catch (error) {
  console.log('❌ MaterialIcons import failed:', error.message);
}

// Test 3: Hooks import
try {
  const { useReportPages } = require('../../hooks/useReportPages');
  console.log('✅ useReportPages import successful');
} catch (error) {
  console.log('❌ useReportPages import failed:', error.message);
}

try {
  const { useReportPersistence } = require('../../hooks/useReportPersistence');
  console.log('✅ useReportPersistence import successful');
} catch (error) {
  console.log('❌ useReportPersistence import failed:', error.message);
}

// Test 4: Other composer components
try {
  const ReportGoalSetting = require('./ReportGoalSetting').default;
  console.log('✅ ReportGoalSetting import successful');
} catch (error) {
  console.log('❌ ReportGoalSetting import failed:', error.message);
}

try {
  const ContextNavigator = require('./ContextNavigator').default;
  console.log('✅ ContextNavigator import successful');
} catch (error) {
  console.log('❌ ContextNavigator import failed:', error.message);
}

try {
  const SelectionContextMenu = require('./SelectionContextMenu').default;
  console.log('✅ SelectionContextMenu import successful');
} catch (error) {
  console.log('❌ SelectionContextMenu import failed:', error.message);
}

export default TestBasicComponents;
