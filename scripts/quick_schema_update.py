#!/usr/bin/env python3
"""
Quick Schema Update Helper
===========================

This script provides a guided process to update your Milvus schema
to include the missing folder_id and entity_id fields.

⚠️  WARNING: This will DELETE ALL DATA in the collection!

Usage:
    python scripts/quick_schema_update.py              # Update dev environment
    python scripts/quick_schema_update.py --env prod   # Update prod environment
    python scripts/quick_schema_update.py --force      # Skip confirmation
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_step(step_num, text):
    """Print a step header"""
    print(f"\n{'='*70}")
    print(f"  Step {step_num}: {text}")
    print(f"{'='*70}\n")

def run_command(cmd, description):
    """Run a command and return the exit code"""
    print(f"🔄 {description}...")
    print(f"   Command: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(
        description='Quick Milvus schema update helper',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--env',
        choices=['dev', 'test', 'prod'],
        default='dev',
        help='Target environment (default: dev)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts'
    )
    
    args = parser.parse_args()
    
    print_header("Milvus Schema Update - Add folder_id & entity_id")
    
    print(f"🎯 Target Environment: {args.env.upper()}\n")
    
    # Check if we're in the right directory
    if not os.path.exists('scripts/setup_milvus_schema.py'):
        print("❌ Error: Must run from Citra-Service directory")
        print(f"   Current: {os.getcwd()}")
        return 1
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found")
        return 1
    
    # Step 1: Validate current schema
    print_step(1, "Validating Current Schema")
    
    result = run_command(
        ['python', 'scripts/setup_milvus_schema.py', '--validate'],
        'Checking current schema'
    )
    
    if result == 0:
        print("\n✅ Schema is already up to date!")
        print("   Both folder_id and entity_id fields exist.\n")
        return 0
    
    print("\n⚠️  Schema validation failed - update required\n")
    
    # Step 2: Show current collection info
    print_step(2, "Current Collection Status")
    
    run_command(
        ['python', 'scripts/setup_milvus_schema.py', '--check'],
        'Getting collection information'
    )
    
    # Warning
    print("\n" + "=" * 70)
    print("  ⚠️  WARNING: THIS WILL DELETE ALL DATA!")
    print("=" * 70 + "\n")
    
    print("The schema update requires recreating the collection.")
    print("All documents will be PERMANENTLY DELETED.\n")
    print("You will need to re-upload all documents after this operation.\n")
    
    # Confirmation
    if not args.force:
        print("❓ Do you want to proceed?")
        response = input("   Type 'DELETE' to confirm: ")
        
        if response != 'DELETE':
            print("\n❌ Aborted - confirmation not provided\n")
            return 0
    
    # Step 3: Force recreate
    print_step(3, "Recreating Collection with New Schema")
    
    result = run_command(
        ['python', 'scripts/setup_milvus_schema.py', '--force'],
        'Force recreating collection'
    )
    
    if result == 0:
        print_header("✅ Schema Update Complete!")
        
        print("New fields added:")
        print("  • folder_id (VARCHAR 100) - Indexed ✅")
        print("  • entity_id (VARCHAR 100) - Indexed ✅\n")
        
        print("📝 Next Steps:")
        print("  1. Re-upload all your documents to the collection")
        print("  2. Test folder filtering functionality")
        print("  3. Test enterprise entity filtering\n")
        
        print("📚 For more details, see: MILVUS_SCHEMA_UPDATE.md\n")
        
        return 0
    else:
        print("\n❌ Schema update failed!")
        print("\nCheck the error messages above for details.\n")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)
