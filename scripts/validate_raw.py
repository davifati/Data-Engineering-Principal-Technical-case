#!/usr/bin/env python3
"""Validate raw layer data against diagram schema and relationships."""

import duckdb

DB_PATH = "warehouse/teachable.duckdb"

DIAGRAM_SCHEMA = {
    "purchase": [
        "purchase_id",
        "buyer_id",
        "prod_item_id",
        "order_date",
        "release_date",
        "producer_id",
        "purchase_partition",
        "prod_item_partition",
        "purchase_total_value",
        "purchase_status",
        "transaction_datetime",
        "transaction_date",
    ],
    "product_item": [
        "prod_item_id",
        "prod_item_partition",
        "product_id",
        "item_quantity",
        "purchase_value",
        "transaction_datetime",
        "transaction_date",
    ],
    "order_transaction_cost_hist": [
        "purchase_id",
        "purchase_partition",
        "order_transaction_cost_vat_value",
        "order_transaction_cost_installment_value",
        "order_transaction_cost_date",
        "transaction_datetime",
        "transaction_date",
    ],
    "purchase_extra_info": [
        "purchase_id",
        "purchase_partition",
        "subsidiary",
        "transaction_datetime",
        "transaction_date",
    ],
}


def main():
    con = duckdb.connect(DB_PATH)

    print("=" * 70)
    print("1. SCHEMA VALIDATION (DuckDB vs Diagram)")
    print("=" * 70)

    all_valid = True
    for table, expected_cols in DIAGRAM_SCHEMA.items():
        actual_cols = con.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw' AND table_name = '{table}'
            ORDER BY ordinal_position
        """).fetchall()
        actual_cols = [c[0] for c in actual_cols]

        missing = set(expected_cols) - set(actual_cols)
        extra = set(actual_cols) - set(expected_cols)

        status = "OK" if not missing and not extra else "FAIL"
        print(f"\n  raw.{table}: {status}")

        if missing:
            print(f"    MISSING: {missing}")
            all_valid = False
        if extra:
            print(f"    EXTRA: {extra}")
            all_valid = False
        if status == "OK":
            print(f"    Columns: {len(actual_cols)} (match)")

    print()
    print("=" * 70)
    print("2. ROW COUNTS")
    print("=" * 70)

    for table in DIAGRAM_SCHEMA.keys():
        count = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
        key = "purchase_id" if table != "product_item" else "prod_item_id"
        unique = con.execute(f"SELECT COUNT(DISTINCT {key}) FROM raw.{table}").fetchone()[0]
        cdc_ratio = round(count / unique, 2) if unique > 0 else 0
        print(f"  raw.{table}: {count} rows, {unique} unique, CDC ratio: {cdc_ratio}x")

    print()
    print("=" * 70)
    print("3. STATUS DISTRIBUTION (purchase)")
    print("=" * 70)

    result = con.execute("""
        SELECT purchase_status, COUNT(*) as cnt
        FROM raw.purchase
        GROUP BY purchase_status
        ORDER BY cnt DESC
    """).fetchall()
    for r in result:
        print(f"  {r[0]}: {r[1]}")

    print()
    print("=" * 70)
    print("4. RELEASE_DATE vs STATUS")
    print("=" * 70)

    result = con.execute("""
        SELECT
            purchase_status,
            COUNT(*) as total,
            SUM(CASE WHEN release_date IS NOT NULL THEN 1 ELSE 0 END) as with_release,
            SUM(CASE WHEN release_date IS NULL THEN 1 ELSE 0 END) as without_release
        FROM raw.purchase
        GROUP BY purchase_status
    """).fetchall()

    print(f"  {'STATUS':<15} {'TOTAL':<8} {'WITH_RELEASE':<15} {'WITHOUT_RELEASE'}")
    print(f"  {'-'*15} {'-'*8} {'-'*15} {'-'*15}")
    for r in result:
        print(f"  {r[0]:<15} {r[1]:<8} {r[2]:<15} {r[3]}")

    print()
    print("=" * 70)
    print("5. CDC EXAMPLES (purchases with multiple versions)")
    print("=" * 70)

    result = con.execute("""
        SELECT purchase_id, transaction_datetime, purchase_status, release_date
        FROM raw.purchase
        WHERE purchase_id IN (
            SELECT purchase_id FROM raw.purchase GROUP BY purchase_id HAVING COUNT(*) > 1
        )
        ORDER BY purchase_id, transaction_datetime
        LIMIT 20
    """).fetchall()

    if result:
        current_pid = None
        for r in result:
            if r[0] != current_pid:
                print(f"\n  purchase_id {r[0]}:")
                current_pid = r[0]
            release = str(r[3]) if r[3] else "NULL"
            print(f"    {r[1]} | {r[2]:<12} | release_date={release}")
    else:
        print("  (no multi-version purchases found)")

    print()
    print("=" * 70)
    print("6. SUBSIDIARY DISTRIBUTION")
    print("=" * 70)

    result = con.execute("""
        SELECT subsidiary, COUNT(*) as cnt
        FROM raw.purchase_extra_info
        GROUP BY subsidiary
    """).fetchall()
    for r in result:
        print(f"  {r[0]}: {r[1]}")

    print()
    print("=" * 70)
    print("7. RELATIONSHIP VALIDATION")
    print("=" * 70)

    # purchase -> product_item
    orphans = con.execute("""
        SELECT COUNT(DISTINCT p.purchase_id) as orphans
        FROM raw.purchase p
        LEFT JOIN raw.product_item pi ON p.prod_item_id = pi.prod_item_id
        WHERE pi.prod_item_id IS NULL
    """).fetchone()[0]
    status = "OK" if orphans == 0 else f"FAIL ({orphans} orphans)"
    print(f"  purchase.prod_item_id -> product_item.prod_item_id: {status}")

    # purchase_extra_info -> purchase
    orphans = con.execute("""
        SELECT COUNT(DISTINCT pei.purchase_id) as orphans
        FROM raw.purchase_extra_info pei
        LEFT JOIN raw.purchase p ON pei.purchase_id = p.purchase_id
        WHERE p.purchase_id IS NULL
    """).fetchone()[0]
    status = "OK" if orphans == 0 else f"FAIL ({orphans} orphans)"
    print(f"  purchase_extra_info.purchase_id -> purchase.purchase_id: {status}")

    # order_transaction_cost_hist -> purchase
    orphans = con.execute("""
        SELECT COUNT(DISTINCT otc.purchase_id) as orphans
        FROM raw.order_transaction_cost_hist otc
        LEFT JOIN raw.purchase p ON otc.purchase_id = p.purchase_id
        WHERE p.purchase_id IS NULL
    """).fetchone()[0]
    status = "OK" if orphans == 0 else f"FAIL ({orphans} orphans)"
    print(f"  order_transaction_cost_hist.purchase_id -> purchase.purchase_id: {status}")

    con.close()

    print()
    print("=" * 70)
    if all_valid:
        print("RAW LAYER VALIDATION: PASSED")
    else:
        print("RAW LAYER VALIDATION: FAILED (schema mismatch)")
    print("=" * 70)


if __name__ == "__main__":
    main()
