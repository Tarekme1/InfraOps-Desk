"""Create and restore verified SQLite backups for the local demo.

This is an operator tool, not a scheduled backup service. Stop the application
before restore and keep backup files in access-controlled storage.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def integrity_check(path):
    connection = sqlite3.connect(str(path))
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if result != "ok" or foreign_keys:
            raise ValueError("Database integrity or foreign-key check failed")
        return result
    finally:
        connection.close()


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Backup destination must differ from the source database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite backup: {destination}")
    integrity_check(source)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(destination))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity_check(destination)
    return destination


def restore(source, destination):
    """Atomically install a verified backup; caller must stop the service."""
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"Backup does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Restore source and destination must differ")
    integrity_check(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".restore-", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        src = sqlite3.connect(str(source))
        dst = sqlite3.connect(str(temporary))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        integrity_check(temporary)
        if destination.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safety_copy = destination.with_name(f"{destination.name}.pre-restore-{stamp}.bak")
            if safety_copy.exists():
                raise FileExistsError(f"Refusing to overwrite safety copy: {safety_copy}")
            backup(destination, safety_copy)
        os.replace(temporary, destination)
        integrity_check(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("backup", help="create a verified, non-overwriting backup")
    make.add_argument("database")
    make.add_argument("destination", nargs="?")
    put = commands.add_parser("restore", help="restore a verified backup; stop MIHWAR first")
    put.add_argument("backup")
    put.add_argument("database")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            destination = args.destination or f"{args.database}.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.bak"
            print(backup(args.database, destination))
        else:
            print(restore(args.backup, args.database))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
