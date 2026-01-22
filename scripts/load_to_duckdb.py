#!/usr/bin/env python3

import argparse
from pathlib import Path

import duckdb


TABLE_DEFINITIONS = {
    "purchase": """
        CREATE TABLE IF NOT EXISTS raw.purchase (
            purchase_id BIGINT,
            buyer_id BIGINT,
            prod_item_id BIGINT,
            order_date DATE,
            release_date DATE,
            producer_id BIGINT,
            purchase_partition BIGINT,
            prod_item_partition BIGINT,
            purchase_total_value DOUBLE,
            purchase_status VARCHAR,
            transaction_datetime TIMESTAMP,
            transaction_date DATE
        )
    """,
    "order_transaction_cost_hist": """
        CREATE TABLE IF NOT EXISTS raw.order_transaction_cost_hist (
            purchase_id BIGINT,
            purchase_partition BIGINT,
            order_transaction_cost_vat_value DOUBLE,
            order_transaction_cost_installment_value DOUBLE,
            order_transaction_cost_date DATE,
            transaction_datetime TIMESTAMP,
            transaction_date DATE
        )
    """,
    "product_item": """
        CREATE TABLE IF NOT EXISTS raw.product_item (
            prod_item_id BIGINT,
            prod_item_partition BIGINT,
            product_id BIGINT,
            item_quantity INTEGER,
            purchase_value DOUBLE,
            transaction_datetime TIMESTAMP,
            transaction_date DATE
        )
    """,
    "purchase_extra_info": """
        CREATE TABLE IF NOT EXISTS raw.purchase_extra_info (
            purchase_id BIGINT,
            purchase_partition BIGINT,
            subsidiary VARCHAR,
            transaction_datetime TIMESTAMP,
            transaction_date DATE
        )
    """,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Load CDC CSVs into DuckDB")
    parser.add_argument("--db", type=str, default="warehouse/teachable.duckdb")
    parser.add_argument("--data-dir", type=str, default="data/raw")
    return parser.parse_args()


def reset_database(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
        print(f"Removed existing database: {db_path}")


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")


def create_table(con: duckdb.DuckDBPyConnection, table_name: str, ddl: str) -> None:
    print(f"  Creating raw.{table_name}...")
    con.execute(ddl)


def load_csv(con: duckdb.DuckDBPyConnection, table_name: str, csv_path: Path) -> int:
    con.execute(f"""
        INSERT INTO raw.{table_name}
        SELECT * FROM read_csv_auto('{csv_path}', header=true)
    """)
    result = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()
    return result[0]


def print_summary(con: duckdb.DuckDBPyConnection) -> None:
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for table_name in TABLE_DEFINITIONS.keys():
        result = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()
        print(f"  raw.{table_name}: {result[0]} rows")


def main():
    args = parse_args()
    db_path = Path(args.db)
    data_dir = Path(args.data_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    reset_database(db_path)

    print(f"Creating DuckDB database: {db_path}")
    con = duckdb.connect(str(db_path))

    create_schema(con)

    for table_name, ddl in TABLE_DEFINITIONS.items():
        csv_path = data_dir / f"{table_name}.csv"

        if not csv_path.exists():
            print(f"  WARNING: {csv_path} not found, skipping {table_name}")
            continue

        create_table(con, table_name, ddl)
        row_count = load_csv(con, table_name, csv_path)
        print(f"  >> Loaded {row_count} rows")

    print_summary(con)
    con.close()
    print(f"\nDone! Database: {db_path.absolute()}")


if __name__ == "__main__":
    main()
