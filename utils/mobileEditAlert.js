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
