#!/usr/bin/env python3
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Milvus Migration Test Runner
============================

Quick test runner for verifying Milvus migration components.

Usage:
    python tests/run_milvus_tests.py                    # Run all tests
    python tests/run_milvus_tests.py --citations        # Citation tests only
    python tests/run_milvus_tests.py --metadata         # Legal metadata tests only
    python tests/run_milvus_tests.py --personal         # Personal filtering tests
    python tests/run_milvus_tests.py --enterprise       # Enterprise filtering tests
    python tests/run_milvus_tests.py --integration      # Integration tests only
    python tests/run_milvus_tests.py --quick            # Quick smoke tests
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_pytest(test_selector: str = "", verbose: bool = True) -> int:
    """Run pytest with specified test selector"""
    
    cmd = ["pytest"]
    
    # Add test file
    test_file = Path(__file__).parent / "test_milvus_migration.py"
    
    if test_selector:
        cmd.append(f"{test_file}::{test_selector}")
    else:
        cmd.append(str(test_file))
    
    # Add options
    if verbose:
        cmd.append("-v")
    cmd.append("--tb=short")  # Short traceback format
    cmd.append("--color=yes")  # Colored output
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 80)
    
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run Milvus migration tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/run_milvus_tests.py                    # All tests
  python tests/run_milvus_tests.py --citations        # Citation tests
  python tests/run_milvus_tests.py --integration      # Integration tests
  python tests/run_milvus_tests.py --quick            # Quick smoke tests
        """
    )
    
    # Test category arguments
    parser.add_argument("--citations", action="store_true",
                       help="Run citation system tests only")
    parser.add_argument("--metadata", action="store_true",
                       help="Run legal metadata tests only")
    parser.add_argument("--personal", action="store_true",
                       help="Run personal filtering tests only")
    parser.add_argument("--enterprise", action="store_true",
                       help="Run enterprise filtering tests only")
    parser.add_argument("--hybrid", action="store_true",
                       help="Run hybrid search tests only")
    parser.add_argument("--namespace", action="store_true",
                       help="Run namespace isolation tests only")
    parser.add_argument("--integration", action="store_true",
                       help="Run integration tests only")
    parser.add_argument("--performance", action="store_true",
                       help="Run performance tests only")
    parser.add_argument("--quick", action="store_true",
                       help="Run quick smoke tests (1 test per category)")
    parser.add_argument("--quiet", action="store_true",
                       help="Less verbose output")
    
    args = parser.parse_args()
    
    # Determine test selector
    test_selector = ""
    
    if args.citations:
        test_selector = "TestCitationSystem"
        print("\n🔍 Running Citation System Tests\n")
    elif args.metadata:
        test_selector = "TestLegalMetadata"
        print("\n📋 Running Legal Metadata Tests\n")
    elif args.personal:
        test_selector = "TestPersonalQueryFiltering"
        print("\n👤 Running Personal Filtering Tests\n")
    elif args.enterprise:
        test_selector = "TestEnterpriseQueryFiltering"
        print("\n🏢 Running Enterprise Filtering Tests\n")
    elif args.hybrid:
        test_selector = "TestHybridSearch"
        print("\n🔀 Running Hybrid Search Tests\n")
    elif args.namespace:
        test_selector = "TestNamespaceIsolation"
        print("\n🔒 Running Namespace Isolation Tests\n")
    elif args.integration:
        test_selector = "TestIntegration"
        print("\n🔗 Running Integration Tests\n")
    elif args.performance:
        test_selector = "TestPerformance"
        print("\n⚡ Running Performance Tests\n")
    elif args.quick:
        # Quick smoke test - one test per category
        test_selector = "TestCitationSystem::test_document_id_in_milvus_chunk or " \
                       "TestLegalMetadata::test_legal_metadata_extraction or " \
                       "TestPersonalQueryFiltering::test_user_id_namespace_isolation or " \
                       "TestEnterpriseQueryFiltering::test_enterprise_namespace_creation or " \
                       "TestHybridSearch::test_dense_vector_dimension or " \
                       "TestNamespaceIsolation::test_personal_namespace_format or " \
                       "TestIntegration::test_complete_citation_flow"
        print("\n⚡ Running Quick Smoke Tests (7 tests)\n")
    else:
        print("\n🚀 Running All Milvus Migration Tests\n")
    
    # Run tests
    return_code = run_pytest(test_selector, verbose=not args.quiet)
    
    # Summary
    print("\n" + "=" * 80)
    if return_code == 0:
        print("✅ All tests PASSED")
    else:
        print("❌ Some tests FAILED")
    print("=" * 80)
    
    return return_code


if __name__ == "__main__":
    sys.exit(main())
