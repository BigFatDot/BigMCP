#!/usr/bin/env python3
"""
Key Rotation CLI - Manage encryption keys and migrate credentials.

Usage:
    python -m app.cli.rotate_keys status                # Check encryption status
    python -m app.cli.rotate_keys migrate --dry-run     # Preview migration
    python -m app.cli.rotate_keys migrate               # Execute migration
    python -m app.cli.rotate_keys generate              # Generate new key

Environment Variables Required:
    DATABASE_URL: PostgreSQL connection string
    ENCRYPTION_KEY: Current encryption key
    ENCRYPTION_KEY_V{N}: Versioned keys for rotation

Examples:
    # Step 1: Generate a new key
    python -m app.cli.rotate_keys generate
    # Output: New key: abc123xyz...

    # Step 2: Add to environment
    # ENCRYPTION_KEY_V2=abc123xyz...
    # ENCRYPTION_KEY=abc123xyz...

    # Step 3: Check status
    python -m app.cli.rotate_keys status

    # Step 4: Preview migration
    python -m app.cli.rotate_keys migrate --dry-run

    # Step 5: Execute migration
    python -m app.cli.rotate_keys migrate

    # Step 6: Verify
    python -m app.cli.rotate_keys status
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cryptography.fernet import Fernet


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_table(headers: list, rows: list) -> None:
    """Print a simple ASCII table."""
    if not rows:
        print("  (no data)")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Print header
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(f"  {header_line}")
    print(f"  {'-' * len(header_line)}")

    # Print rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        print(f"  {row_line}")


async def cmd_status(args: argparse.Namespace) -> int:
    """Show current encryption status."""
    from app.db.session import AsyncSessionLocal
    from app.services.key_rotation_service import KeyRotationService

    print_header("Encryption Status")

    async with AsyncSessionLocal() as db:
        service = KeyRotationService(db)
        status = await service.get_encryption_status()

    print(f"  Current Key Version: v{status.current_version}")
    print(f"  Available Versions:  {', '.join(f'v{v}' for v in status.available_versions)}")
    print(f"  Development Mode:    {'YES (WARNING!)' if status.is_dev_mode else 'No'}")
    print()

    if status.is_dev_mode:
        print("  ⚠️  WARNING: Running with auto-generated development key!")
        print("     Credentials will be LOST on restart.")
        print("     Set ENCRYPTION_KEY environment variable for production.")
        print()

    print(f"  Total Credentials:      {status.total_credentials}")
    print(f"  Needing Rotation:       {status.credentials_needing_rotation}")
    print()

    # User credentials by version
    print("  User Credentials by Version:")
    if status.user_credentials_by_version:
        rows = [[f"v{v}", count, "✓ current" if v == status.current_version else "← needs rotation"]
                for v, count in sorted(status.user_credentials_by_version.items())]
        print_table(["Version", "Count", "Status"], rows)
    else:
        print("    (no user credentials)")
    print()

    # Organization credentials by version
    print("  Organization Credentials by Version:")
    if status.org_credentials_by_version:
        rows = [[f"v{v}", count, "✓ current" if v == status.current_version else "← needs rotation"]
                for v, count in sorted(status.org_credentials_by_version.items())]
        print_table(["Version", "Count", "Status"], rows)
    else:
        print("    (no organization credentials)")
    print()

    # Recommendations
    if status.credentials_needing_rotation > 0:
        print("  📋 RECOMMENDATION: Run key rotation to migrate credentials")
        print("     python -m app.cli.rotate_keys migrate --dry-run")
        print()
    else:
        print("  ✅ All credentials are on the current key version.")
        print()

    return 0


async def cmd_migrate(args: argparse.Namespace) -> int:
    """Migrate credentials to the current key version."""
    from app.db.session import AsyncSessionLocal
    from app.services.key_rotation_service import KeyRotationService

    dry_run = args.dry_run
    batch_size = args.batch_size

    if dry_run:
        print_header("Key Rotation - DRY RUN")
        print("  This is a simulation. No changes will be made.\n")
    else:
        print_header("Key Rotation - LIVE MIGRATION")
        print("  ⚠️  This will modify credential data in the database.\n")

        if not args.yes:
            response = input("  Continue? [y/N]: ")
            if response.lower() != 'y':
                print("  Aborted.")
                return 1

    async with AsyncSessionLocal() as db:
        service = KeyRotationService(db)

        print(f"  Starting migration (batch size: {batch_size})...")
        print(f"  Target version: v{service.secrets.current_version}")
        print()

        report = await service.rotate_all_credentials(
            batch_size=batch_size,
            dry_run=dry_run
        )

    # Print report
    print()
    print(f"  {'[DRY RUN] ' if dry_run else ''}Migration Report:")
    print(f"  {'─' * 40}")
    print(f"  Started:    {report.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Completed:  {report.completed_at.strftime('%Y-%m-%d %H:%M:%S') if report.completed_at else 'N/A'}")
    print(f"  To Version: v{report.to_version}")
    print()

    # User credentials
    uc = report.user_credentials
    print(f"  User Credentials:")
    print(f"    Total:           {uc.total}")
    print(f"    Migrated:        {uc.migrated}")
    print(f"    Already Current: {uc.already_current}")
    print(f"    Failed:          {uc.failed}")
    print()

    # Organization credentials
    oc = report.org_credentials
    print(f"  Organization Credentials:")
    print(f"    Total:           {oc.total}")
    print(f"    Migrated:        {oc.migrated}")
    print(f"    Already Current: {oc.already_current}")
    print(f"    Failed:          {oc.failed}")
    print()

    # Errors
    all_errors = uc.errors + oc.errors
    if all_errors:
        print(f"  Errors ({len(all_errors)}):")
        for error in all_errors[:10]:
            print(f"    - {error}")
        if len(all_errors) > 10:
            print(f"    ... and {len(all_errors) - 10} more")
        print()

    # Summary
    if report.success:
        if dry_run:
            print(f"  ✅ DRY RUN SUCCESSFUL - {uc.migrated + oc.migrated} credentials would be migrated")
            print()
            print("  To execute the migration, run:")
            print("    python -m app.cli.rotate_keys migrate")
        else:
            print(f"  ✅ MIGRATION SUCCESSFUL - {uc.migrated + oc.migrated} credentials migrated")
        print()
        return 0
    else:
        print(f"  ❌ MIGRATION FAILED: {report.error}")
        print()
        return 1


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a new encryption key."""
    print_header("Generate New Encryption Key")

    new_key = Fernet.generate_key().decode()

    print(f"  New Key: {new_key}")
    print()
    print("  To use this key for rotation:")
    print()
    print("  1. Add to your environment (e.g., .env file):")
    print(f"     ENCRYPTION_KEY_V2={new_key}")
    print(f"     ENCRYPTION_KEY={new_key}")
    print()
    print("  2. Keep the old key for decryption during migration:")
    print("     ENCRYPTION_KEY_V1=<your-current-key>")
    print()
    print("  3. Restart the application")
    print()
    print("  4. Run migration:")
    print("     python -m app.cli.rotate_keys migrate")
    print()
    print("  5. After successful migration, you can remove V1 key")
    print()

    if args.json:
        print(json.dumps({"key": new_key}))

    return 0


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="rotate_keys",
        description="Manage encryption keys and credential rotation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show current encryption status and credential distribution"
    )

    # migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate credentials to the current key version"
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without making changes"
    )
    migrate_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of credentials to process per batch (default: 100)"
    )
    migrate_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )

    # generate command
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a new Fernet encryption key"
    )
    generate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output key as JSON"
    )

    args = parser.parse_args()

    # Route to command handler
    if args.command == "status":
        return asyncio.run(cmd_status(args))
    elif args.command == "migrate":
        return asyncio.run(cmd_migrate(args))
    elif args.command == "generate":
        return cmd_generate(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
