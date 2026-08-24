// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// mobileEditAlert.js - Utility to show "desktop required" alert on mobile web
// Used by composers when mobileViewOnly is true and user tries to edit

import { Alert, Platform } from 'react-native';

/**
 * Show an alert informing the user that editing requires a desktop browser.
 * @param {Function} [showModernAlert] - Optional ModernAlert handler (preferred on web).
 *   Signature: showModernAlert({ title, message, type, buttons })
 */
export const showDesktopEditingAlert = (showModernAlert) => {
  const title = 'Desktop Required';
  const message =
    'Editing features are available on desktop.\n\nPlease visit Citra AI on a desktop web browser for the full editing experience.';

  if (showModernAlert && typeof showModernAlert === 'function') {
    showModernAlert({
      title,
      message,
      type: 'info',
      buttons: [{ text: 'OK' }],
    });
  } else {
    Alert.alert(title, message, [{ text: 'OK' }]);
  }
};

export default showDesktopEditingAlert;
