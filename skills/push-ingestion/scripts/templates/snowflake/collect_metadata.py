#!/usr/bin/env python3
"""
Collect table metadata from Snowflake — collection only.

Connects to Snowflake, discovers all accessible databases and schemas, then
queries INFORMATION_SCHEMA.TABLES for volume/freshness and
INFORMATION_SCHEMA.COLUMNS for field definitions.  The collected assets are
written to a JSON manifest file.

Can be run standalone via CLI or imported (use the ``collect()`` function).

Substitution points
-------------------
- SNOWFLAKE_ACCOUNT    (env) / --account    (CLI) : Snowflake account identifier (e.g. xy12345.us-east-1)
- SNOWFLAKE_USER       (env) / --user       (CLI) : Snowflake username
- SNOWFLAKE_PASSWORD   (env) / --password   (CLI) : Snowflake password
- SNOWFLAKE_WAREHOUSE  (env) / --warehouse  (CLI) : Snowflake virtual warehouse

Prerequisites
-------------
    pip install snowflake-connector-python

Usage
-----
    python collect_metadata.py \\
        --account  <SNOWFLAKE_ACCOUNT> \\
        --user     <SNOWFLAKE_USER> \\
        --password <SNOWFLAKE_PASSWORD> \\
        --warehouse <SNOWFLAKE_WAREHOUSE>
"""

import argparse
import json
import os
from datetime import datetime, timezone

import snowflake.connector

# ← SUBSTITUTE: set RESOURCE_TYPE to match your Monte Carlo connection type
RESOURCE_TYPE = "snowflake"

# Databases that are Snowflake system databases — skip them
_SKIP_DATABASES = {"SNOWFLAKE", "SNOWFLAKE_SAMPLE_DATA"}

# Schemas that are Snowflake system schemas — skip them
_SKIP_SCHEMAS = {"INFORMATION_SCHEMA"}


def _connect(account: str, user: str, password: str, warehouse: str):
    # ← SUBSTITUTE: add role= or authenticator= kwargs if your org requires them
    return snowflake.connector.connect(
        account=account,
        user=user,
        password=password,
        warehouse=warehouse,
    )


def _collect_assets(conn) -> list[dict]:
    """Collect table metadata from Snowflake and return as a list of dicts."""
    cursor = conn.cursor()
    assets: list[dict] = []

    # --- Discover databases ---
    cursor.execute("SHOW DATABASES")
    # SHOW DATABASES returns (created_on, name, …); column index 1 is the name
    databases = [row[1] for row in cursor.fetchall() if row[1] not in _SKIP_DATABASES]
    print(f"  Found {len(databases)} database(s): {databases}")

    for db in databases:
        # --- Discover schemas in each database ---
        try:
            cursor.execute(f'SHOW SCHEMAS IN DATABASE "{db}"')
        except Exception as exc:
            print(f"  WARNING: could not list schemas in {db}: {exc}")
            continue

        # Column index 1 is the schema name
        schemas = [row[1] for row in cursor.fetchall() if row[1] not in _SKIP_SCHEMAS]

        # --- Collect tables, volume, and freshness via INFORMATION_SCHEMA ---
        try:
            cursor.execute(
                f"""
                SELECT
                    TABLE_CATALOG,
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE,
                    ROW_COUNT,
                    BYTES,
                    LAST_ALTERED,
                    COMMENT
                FROM "{db}".INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA != 'INFORMATION_SCHEMA'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
            )
        except Exception as exc:
            print(f"  WARNING: could not query INFORMATION_SCHEMA.TABLES in {db}: {exc}")
            continue

        table_rows = cursor.fetchall()
        print(f"  {db}: {len(table_rows)} table(s)")

        # Build a set of schema names present in the table result to know which
        # INFORMATION_SCHEMA.COLUMNS queries to run
        schemas_with_tables: set[str] = {row[1] for row in table_rows}

        # Pre-fetch all columns for this database in one query per schema
        columns_by_table: dict[tuple[str, str], list[dict]] = {}
        for schema in schemas_with_tables:
            if schema not in schemas:
                continue  # respect the earlier schema skip list
            try:
                cursor.execute(
                    f"""
                    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COMMENT
                    FROM "{db}".INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME, ORDINAL_POSITION
                    """,
                    (schema,),
                )
            except Exception as exc:
                print(f"  WARNING: could not fetch columns for {db}.{schema}: {exc}")
                continue

            for col_row in cursor.fetchall():
                table_name, col_name, data_type, col_comment = col_row
                key = (schema, table_name)
                if key not in columns_by_table:
                    columns_by_table[key] = []
                columns_by_table[key].append(
                    {
                        "name": col_name,
                        "type": data_type,
                        "description": col_comment or None,
                    }
                )

        # Build asset dicts
        for row in table_rows:
            tbl_catalog, tbl_schema, tbl_name, tbl_type, row_count, byte_count, last_altered, tbl_comment = row

            volume = None
            if row_count is not None or byte_count is not None:
                volume = {
                    "row_count": int(row_count) if row_count is not None else None,
                    "byte_count": int(byte_count) if byte_count is not None else None,
                }

            freshness = None
            if last_altered is not None:
                freshness = {
                    "last_update_time": last_altered.isoformat() if hasattr(last_altered, "isoformat") else str(last_altered),
                }

            fields = columns_by_table.get((tbl_schema, tbl_name), [])

            assets.append(
                {
                    "type": tbl_type or "TABLE",
                    "database": tbl_catalog,
                    "schema": tbl_schema,
                    "name": tbl_name,
                    "description": tbl_comment or None,
                    "fields": fields,
                    "volume": volume,
                    "freshness": freshness,
                }
            )
            print(f"    + {tbl_catalog}.{tbl_schema}.{tbl_name} ({len(fields)} columns)")

    cursor.close()
    return assets


def collect(
    account: str,
    user: str,
    password: str,
    warehouse: str,
    output_file: str = "metadata_output.json",
) -> dict:
    """
    Connect to Snowflake, collect table metadata, and write a JSON manifest.

    Returns the manifest dict.
    """
    print(f"Connecting to Snowflake account: {account} ...")
    conn = _connect(account, user, password, warehouse)

    print("Collecting table metadata ...")
    assets = _collect_assets(conn)
    conn.close()
    print(f"\nCollected {len(assets)} table(s).")

    manifest = {
        "resource_type": RESOURCE_TYPE,
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        "assets": assets,
    }
    with open(output_file, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Asset manifest written to {output_file}")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Snowflake table metadata and write to a manifest file",
    )
    parser.add_argument(
        "--account",
        default=os.environ.get("SNOWFLAKE_ACCOUNT"),
        help="Snowflake account identifier, e.g. xy12345.us-east-1 (env: SNOWFLAKE_ACCOUNT)",  # ← SUBSTITUTE
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("SNOWFLAKE_USER"),
        help="Snowflake username (env: SNOWFLAKE_USER)",  # ← SUBSTITUTE
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SNOWFLAKE_PASSWORD"),
        help="Snowflake password (env: SNOWFLAKE_PASSWORD)",  # ← SUBSTITUTE
    )
    parser.add_argument(
        "--warehouse",
        default=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        help="Snowflake virtual warehouse (env: SNOWFLAKE_WAREHOUSE)",  # ← SUBSTITUTE
    )
    parser.add_argument(
        "--output-file",
        default="metadata_output.json",
        help="Path to write the output manifest (default: metadata_output.json)",
    )
    args = parser.parse_args()

    missing = [
        name
        for name, val in [
            ("--account", args.account),
            ("--user", args.user),
            ("--password", args.password),
            ("--warehouse", args.warehouse),
        ]
        if not val
    ]
    if missing:
        parser.error(f"Missing required arguments: {', '.join(missing)}")

    collect(
        account=args.account,
        user=args.user,
        password=args.password,
        warehouse=args.warehouse,
        output_file=args.output_file,
    )
    print("Done.")


if __name__ == "__main__":
    main()
