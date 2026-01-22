#!/usr/bin/env python3
import duckdb

DB_PATH = "warehouse/teachable.duckdb"

def main():
    con = duckdb.connect(DB_PATH)

    print("=" * 60)
    print("SCHEMAS")
    print("=" * 60)
    schemas = con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
    for s in schemas:
        print(f"  {s[0]}")

    print("\n" + "=" * 60)
    print("ROW COUNTS")
    print("=" * 60)
    tables = ["purchase", "product_item", "order_transaction_cost_hist", "purchase_extra_info"]
    for table in tables:
        count = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
        print(f"  raw.{table}: {count} rows")

    print("\n" + "=" * 60)
    print("CDC EXAMPLE (purchases with multiple versions)")
    print("=" * 60)
    result = con.execute("""
        SELECT purchase_id, transaction_datetime, release_date, purchase_status
        FROM raw.purchase
        WHERE purchase_id IN (
            SELECT purchase_id
            FROM raw.purchase
            GROUP BY purchase_id
            HAVING COUNT(*) > 1
        )
        ORDER BY purchase_id, transaction_datetime
        LIMIT 20
    """).fetchall()

    if result:
        print(f"  {'purchase_id':<12} {'transaction_datetime':<22} {'release_date':<14} {'status'}")
        print("  " + "-" * 70)
        for row in result:
            release = str(row[2]) if row[2] else "NULL"
            print(f"  {row[0]:<12} {str(row[1]):<22} {release:<14} {row[3]}")
    else:
        print("  No purchases with multiple CDC versions found")

    print("\n" + "=" * 60)
    print("STATUS DISTRIBUTION")
    print("=" * 60)
    result = con.execute("""
        SELECT purchase_status, COUNT(*) as cnt
        FROM raw.purchase
        GROUP BY purchase_status
        ORDER BY cnt DESC
    """).fetchall()
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    print("\n" + "=" * 60)
    print("SUBSIDIARY DISTRIBUTION")
    print("=" * 60)
    result = con.execute("""
        SELECT subsidiary, COUNT(*) as cnt
        FROM raw.purchase_extra_info
        GROUP BY subsidiary
        ORDER BY cnt DESC
    """).fetchall()
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    con.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
