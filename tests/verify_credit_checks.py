# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import middleware
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from middleware.credit_check_middleware import check_user_credits, InsufficientCreditsError

class TestCreditChecks(unittest.TestCase):

    @patch('middleware.credit_check_middleware.get_usage_service')
    def test_negative_balance(self, mock_get_service):
        # Mock usage service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        # Setup mock behavior: return failure for negative balance
        mock_service.check_credits.return_value = {
            'success': False,
            'sufficient': False,
            'balance': -10.0,
            'required': 0,
            'message': 'Insufficient credits'
        }

        # Test
        print("\nTesting Negative Balance...")
        result = check_user_credits('user123', 0)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['balance'], -10.0)
        print("✅ Negative balance check passed (blocked as expected)")

    @patch('middleware.credit_check_middleware.get_usage_service')
    def test_positive_balance_zero_cost(self, mock_get_service):
        # Mock usage service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        # Setup mock behavior: return success for positive balance
        mock_service.check_credits.return_value = {
            'success': True,
            'sufficient': True,
            'balance': 50.0,
            'required': 0,
            'message': 'Sufficient credits'
        }

        # Test
        print("\nTesting Positive Balance (Zero Cost)...")
        result = check_user_credits('user123', 0)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['balance'], 50.0)
        print("✅ Positive balance check passed (allowed as expected)")

if __name__ == '__main__':
    unittest.main()
