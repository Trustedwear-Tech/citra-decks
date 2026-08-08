"""
Migration Script: Migrate Legacy Sharing to Centralized Authorization

This script migrates existing sharing data from legacy collections 
(vault_shares, shared_with_me) to the centralized resource_permissions collection.

Usage:
    python scripts/migrate_sharing_to_centralized.py [--dry-run]

Options:
    --dry-run    Show what would be migrated without making changes
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vault_env_loader import load_environment_variables
load_environment_variables()

from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_migration(dry_run: bool = False):
    """Run the migration process."""
    
    logger.info("=" * 60)
    logger.info("🔄 Sharing Data Migration to Centralized Authorization")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    try:
        # Connect to MongoDB
        client = get_async_mongo_client()
        db = client[MONGODB_DATABASE]
        
        logger.info(f"📊 Connected to database: {MONGODB_DATABASE}")
        
        # Get collection counts
        vault_shares_count = await db["vault_shares"].count_documents({"status": "active"})
        shared_with_me_count = await db["shared_with_me"].count_documents({})
        existing_permissions_count = await db["resource_permissions"].count_documents({})
        
        logger.info(f"📂 Active vault shares: {vault_shares_count}")
        logger.info(f"📋 Shared with me entries: {shared_with_me_count}")
        logger.info(f"🔐 Existing resource permissions: {existing_permissions_count}")
        
        if dry_run:
            logger.info("\n📊 Migration Preview:")
            logger.info(f"   Would migrate up to {vault_shares_count} vault shares")
            logger.info(f"   Would migrate up to {shared_with_me_count} shared_with_me entries")
            return {
                "dry_run": True,
                "vault_shares_to_migrate": vault_shares_count,
                "shared_with_me_to_migrate": shared_with_me_count
            }
        
        # Run migration
        from services.sharing_migration_service import SharingMigrationService
        
        migration_service = SharingMigrationService(db)
        results = await migration_service.migrate_all()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"📂 Vault shares migrated: {results['vault_shares']['migrated']}")
        logger.info(f"   Skipped: {results['vault_shares']['skipped']}")
        logger.info(f"   Errors: {len(results['vault_shares']['errors'])}")
        logger.info(f"📋 Shared with me migrated: {results['shared_with_me']['migrated']}")
        logger.info(f"   Skipped: {results['shared_with_me']['skipped']}")
        logger.info(f"   Errors: {len(results['shared_with_me']['errors'])}")
        logger.info(f"🔐 Total migrated: {results['total_migrated']}")
        
        # Show any errors
        all_errors = results['vault_shares']['errors'] + results['shared_with_me']['errors']
        if all_errors:
            logger.warning("\n⚠️ ERRORS:")
            for error in all_errors[:10]:  # Show first 10
                logger.warning(f"   {error}")
            if len(all_errors) > 10:
                logger.warning(f"   ... and {len(all_errors) - 10} more errors")
        
        # Final count
        final_permissions_count = await db["resource_permissions"].count_documents({})
        logger.info(f"\n📊 Final resource permissions count: {final_permissions_count}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        raise


async def verify_migration():
    """Verify migration integrity."""
    
    logger.info("\n" + "=" * 60)
    logger.info("🔍 VERIFICATION")
    logger.info("=" * 60)
    
    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    
    # Sample check: Verify some vault shares are now in resource_permissions
    vault_shares = await db["vault_shares"].find({"status": "active"}).limit(5).to_list(length=5)
    
    verified = 0
    for share in vault_shares:
        vault_id = share.get("vault_id")
        perm = await db["resource_permissions"].find_one({
            "resource_id": vault_id,
            "resource_type": "vault"
        })
        
        if perm:
            verified += 1
            logger.info(f"   ✅ Vault {vault_id} found in resource_permissions")
        else:
            logger.warning(f"   ⚠️ Vault {vault_id} NOT found in resource_permissions")
    
    logger.info(f"\n📊 Verification: {verified}/{len(vault_shares)} sampled vault shares verified")


def main():
    parser = argparse.ArgumentParser(description="Migrate legacy sharing to centralized authorization")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without changes")
    parser.add_argument("--verify", action="store_true", help="Verify migration after completion")
    args = parser.parse_args()
    
    try:
        results = asyncio.run(run_migration(dry_run=args.dry_run))
        
        if args.verify and not args.dry_run:
            asyncio.run(verify_migration())
        
        logger.info("\n✅ Script completed successfully")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
