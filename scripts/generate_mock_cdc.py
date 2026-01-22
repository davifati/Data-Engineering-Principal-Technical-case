#!/usr/bin/env python3
"""
Generate deterministic mock CDC data following the technical case diagram.

Schema from diagram:
- purchase: purchase_id, buyer_id, prod_item_id, order_date, release_date, producer_id,
            purchase_partition, prod_item_partition, purchase_total_value, purchase_status,
            transaction_datetime, transaction_date
- product_item: prod_item_id, prod_item_partition, product_id, item_quantity, purchase_value,
                transaction_datetime, transaction_date
- order_transaction_cost_hist: purchase_id, purchase_partition, order_transaction_cost_vat_value,
                               order_transaction_cost_installment_value, order_transaction_cost_date,
                               transaction_datetime, transaction_date
- purchase_extra_info: purchase_id, purchase_partition, subsidiary, transaction_datetime, transaction_date

CDC characteristics (from case examples):
- Events can arrive late (out-of-order ingestion)
- Same purchase_id can appear multiple times (CDC updates)
- release_date evolves: NULL -> date, or date -> later date (never backwards)
- subsidiary can change over time
- Status follows lifecycle: INICIADA -> APROVADA/CANCELADA, APROVADA -> REEMBOLSADA
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Generate mock CDC data")
    parser.add_argument("--out", type=str, default="data/raw")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def generate_purchase_data(rng: np.random.Generator) -> pd.DataFrame:
    """
    Generate purchase CDC events following the diagram schema.

    Status lifecycle:
    - INICIADA: order placed, no payment yet (release_date = NULL)
    - APROVADA: payment confirmed (release_date = date)
    - CANCELADA: order cancelled (release_date = NULL)
    - REEMBOLSADA: refunded after approval (release_date = date, was paid before refund)
    """
    base_purchases = []

    for i in range(30):
        purchase_id = 50 + i
        buyer_id = rng.integers(10000, 500000)
        prod_item_id = 5 + i
        producer_id = rng.integers(800000, 999999)

        order_day = int(rng.integers(1, 45))
        order_date = datetime(2023, 1, 15) + timedelta(days=order_day)

        # Initial status distribution
        initial_status = rng.choice(
            ["INICIADA", "APROVADA", "CANCELADA"],
            p=[0.25, 0.60, 0.15]
        )

        # release_date based on status
        if initial_status == "APROVADA":
            release_date = order_date + timedelta(days=int(rng.integers(1, 5)))
        else:
            release_date = None

        purchase_partition = (purchase_id % 10) * 100
        prod_item_partition = (prod_item_id % 10) * 100
        purchase_total_value = round(rng.uniform(25.0, 2500.0), 2)

        base_purchases.append({
            "purchase_id": purchase_id,
            "buyer_id": buyer_id,
            "prod_item_id": prod_item_id,
            "order_date": order_date.date(),
            "release_date": release_date.date() if release_date else None,
            "producer_id": producer_id,
            "purchase_partition": purchase_partition,
            "prod_item_partition": prod_item_partition,
            "purchase_total_value": purchase_total_value,
            "purchase_status": initial_status,
        })

    # Generate CDC events
    events = []

    for purchase in base_purchases:
        # First event: initial ingestion
        days_to_ingest = int(rng.integers(0, 3))
        first_ingest = datetime.combine(
            purchase["order_date"], datetime.min.time()
        ) + timedelta(days=days_to_ingest, hours=int(rng.integers(0, 24)), minutes=int(rng.integers(0, 60)))

        events.append({
            **purchase,
            "transaction_datetime": first_ingest,
            "transaction_date": first_ingest.date(),
        })

        # ~30% get a second CDC event (status/release_date evolution)
        if rng.random() < 0.30:
            days_later = int(rng.integers(5, 25))
            second_ingest = first_ingest + timedelta(days=days_later)

            updated = purchase.copy()

            if purchase["purchase_status"] == "INICIADA":
                # INICIADA can become APROVADA or CANCELADA
                if rng.random() < 0.7:
                    updated["purchase_status"] = "APROVADA"
                    updated["release_date"] = (
                        datetime.combine(purchase["order_date"], datetime.min.time())
                        + timedelta(days=int(rng.integers(2, 10)))
                    ).date()
                else:
                    updated["purchase_status"] = "CANCELADA"

            elif purchase["purchase_status"] == "APROVADA":
                # APROVADA can become REEMBOLSADA or have release_date adjusted (later)
                if rng.random() < 0.3:
                    updated["purchase_status"] = "REEMBOLSADA"
                else:
                    # release_date adjusted to later date
                    current_release = datetime.combine(purchase["release_date"], datetime.min.time())
                    updated["release_date"] = (
                        current_release + timedelta(days=int(rng.integers(1, 10)))
                    ).date()

            events.append({
                **updated,
                "transaction_datetime": second_ingest,
                "transaction_date": second_ingest.date(),
            })

        # ~10% get a third event (replay or further update)
        if rng.random() < 0.10:
            days_later = int(rng.integers(30, 60))
            third_ingest = first_ingest + timedelta(days=days_later)

            # Replay of current state
            current_state = events[-1].copy()
            current_state["transaction_datetime"] = third_ingest
            current_state["transaction_date"] = third_ingest.date()
            events.append(current_state)

    # Add exact duplicates (~5%) to simulate replay
    n_duplicates = max(1, int(len(events) * 0.05))
    duplicate_indices = rng.choice(len(events), n_duplicates, replace=False)
    for idx in duplicate_indices:
        events.append(events[idx].copy())

    df = pd.DataFrame(events)
    df = df.sample(frac=1, random_state=int(rng.integers(0, 10000))).reset_index(drop=True)

    return df


def generate_product_item_data(rng: np.random.Generator, purchase_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate product_item CDC events.

    Schema: prod_item_id, prod_item_partition, product_id, item_quantity, purchase_value,
            transaction_datetime, transaction_date

    Relationship: purchase.prod_item_id -> product_item.prod_item_id
    """
    unique_items = purchase_df[["prod_item_id", "prod_item_partition", "purchase_total_value"]].drop_duplicates(subset=["prod_item_id"])

    events = []

    for _, row in unique_items.iterrows():
        prod_item_id = row["prod_item_id"]
        prod_item_partition = row["prod_item_partition"]

        product_id = int(rng.integers(100000, 999999))
        item_quantity = int(rng.integers(1, 120))
        purchase_value = row["purchase_total_value"]

        related = purchase_df[purchase_df["prod_item_id"] == prod_item_id]
        base_date = related["transaction_date"].min()

        # Arrives around same time as purchase
        offset_hours = int(rng.integers(-24, 48))
        transaction_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(
            hours=offset_hours + int(rng.integers(0, 24)),
            minutes=int(rng.integers(0, 60))
        )

        events.append({
            "prod_item_id": prod_item_id,
            "prod_item_partition": prod_item_partition,
            "product_id": product_id,
            "item_quantity": item_quantity,
            "purchase_value": purchase_value,
            "transaction_datetime": transaction_dt,
            "transaction_date": transaction_dt.date(),
        })

        # ~15% get value correction (always higher or equal)
        if rng.random() < 0.15:
            days_later = int(rng.integers(5, 20))
            second_dt = transaction_dt + timedelta(days=days_later)
            adjusted_value = round(purchase_value * rng.uniform(1.0, 1.10), 2)

            events.append({
                "prod_item_id": prod_item_id,
                "prod_item_partition": prod_item_partition,
                "product_id": product_id,
                "item_quantity": item_quantity,
                "purchase_value": adjusted_value,
                "transaction_datetime": second_dt,
                "transaction_date": second_dt.date(),
            })

    # Add duplicates
    n_duplicates = max(1, int(len(events) * 0.03))
    duplicate_indices = rng.choice(len(events), n_duplicates, replace=False)
    for idx in duplicate_indices:
        events.append(events[idx].copy())

    df = pd.DataFrame(events)
    df = df.sample(frac=1, random_state=int(rng.integers(0, 10000))).reset_index(drop=True)

    return df


def generate_order_transaction_cost_hist(rng: np.random.Generator, purchase_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate order_transaction_cost_hist CDC events.

    Schema: purchase_id, purchase_partition, order_transaction_cost_vat_value,
            order_transaction_cost_installment_value, order_transaction_cost_date,
            transaction_datetime, transaction_date
    """
    unique_purchases = purchase_df[["purchase_id", "purchase_partition", "purchase_total_value", "order_date"]].drop_duplicates(subset=["purchase_id"])

    events = []

    for _, row in unique_purchases.iterrows():
        purchase_id = row["purchase_id"]
        purchase_partition = row["purchase_partition"]
        total_value = row["purchase_total_value"]
        order_date = row["order_date"]

        vat_value = round(total_value * rng.uniform(0.08, 0.18), 2)
        installment_value = round(total_value * rng.uniform(0.02, 0.08), 2)
        cost_date = order_date

        related = purchase_df[purchase_df["purchase_id"] == purchase_id]
        base_date = related["transaction_date"].min()

        offset_days = int(rng.integers(0, 5))
        transaction_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(
            days=offset_days,
            hours=int(rng.integers(0, 24)),
            minutes=int(rng.integers(0, 60))
        )

        events.append({
            "purchase_id": purchase_id,
            "purchase_partition": purchase_partition,
            "order_transaction_cost_vat_value": vat_value,
            "order_transaction_cost_installment_value": installment_value,
            "order_transaction_cost_date": cost_date,
            "transaction_datetime": transaction_dt,
            "transaction_date": transaction_dt.date(),
        })

    # Add duplicates
    n_duplicates = max(1, int(len(events) * 0.03))
    duplicate_indices = rng.choice(len(events), n_duplicates, replace=False)
    for idx in duplicate_indices:
        events.append(events[idx].copy())

    df = pd.DataFrame(events)
    df = df.sample(frac=1, random_state=int(rng.integers(0, 10000))).reset_index(drop=True)

    return df


def generate_purchase_extra_info(rng: np.random.Generator, purchase_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate purchase_extra_info CDC events.

    Schema: purchase_id, purchase_partition, subsidiary, transaction_datetime, transaction_date

    Subsidiary can change over time (as shown in case example: purchase 69 changed from nacional to internacional)
    """
    subsidiaries = ["nacional", "internacional"]

    unique_purchases = purchase_df[["purchase_id", "purchase_partition"]].drop_duplicates(subset=["purchase_id"])

    events = []

    for _, row in unique_purchases.iterrows():
        purchase_id = row["purchase_id"]
        purchase_partition = row["purchase_partition"]

        subsidiary = rng.choice(subsidiaries, p=[0.55, 0.45])

        related = purchase_df[purchase_df["purchase_id"] == purchase_id]
        base_date = related["transaction_date"].min()

        # Extra info often arrives later
        offset_days = int(rng.integers(0, 8))
        transaction_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(
            days=offset_days,
            hours=int(rng.integers(0, 24)),
            minutes=int(rng.integers(0, 60))
        )

        events.append({
            "purchase_id": purchase_id,
            "purchase_partition": purchase_partition,
            "subsidiary": subsidiary,
            "transaction_datetime": transaction_dt,
            "transaction_date": transaction_dt.date(),
        })

        # ~12% get subsidiary change (like case example)
        if rng.random() < 0.12:
            days_later = int(rng.integers(10, 40))
            second_dt = transaction_dt + timedelta(days=days_later)
            new_subsidiary = "internacional" if subsidiary == "nacional" else "nacional"

            events.append({
                "purchase_id": purchase_id,
                "purchase_partition": purchase_partition,
                "subsidiary": new_subsidiary,
                "transaction_datetime": second_dt,
                "transaction_date": second_dt.date(),
            })

    # Add duplicates
    n_duplicates = max(1, int(len(events) * 0.03))
    duplicate_indices = rng.choice(len(events), n_duplicates, replace=False)
    for idx in duplicate_indices:
        events.append(events[idx].copy())

    df = pd.DataFrame(events)
    df = df.sample(frac=1, random_state=int(rng.integers(0, 10000))).reset_index(drop=True)

    return df


def main():
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    print(f"Generating mock CDC data with seed={args.seed}")

    print("Generating purchase events...")
    purchase_df = generate_purchase_data(rng)
    purchase_df.to_csv(out_dir / "purchase.csv", index=False)
    print(f"  >> {len(purchase_df)} rows -> purchase.csv")

    print("Generating product_item events...")
    product_item_df = generate_product_item_data(rng, purchase_df)
    product_item_df.to_csv(out_dir / "product_item.csv", index=False)
    print(f"  >> {len(product_item_df)} rows -> product_item.csv")

    print("Generating order_transaction_cost_hist events...")
    cost_df = generate_order_transaction_cost_hist(rng, purchase_df)
    cost_df.to_csv(out_dir / "order_transaction_cost_hist.csv", index=False)
    print(f"  >> {len(cost_df)} rows -> order_transaction_cost_hist.csv")

    print("Generating purchase_extra_info events...")
    extra_df = generate_purchase_extra_info(rng, purchase_df)
    extra_df.to_csv(out_dir / "purchase_extra_info.csv", index=False)
    print(f"  >> {len(extra_df)} rows -> purchase_extra_info.csv")

    print(f"\nAll files written to {out_dir.absolute()}")

    # Summary
    print("\n" + "=" * 50)
    print("DATA SUMMARY")
    print("=" * 50)
    print(f"Unique purchases: {purchase_df['purchase_id'].nunique()}")
    print(f"Purchase CDC events: {len(purchase_df)}")

    print(f"\nStatus distribution:")
    for status, count in purchase_df.groupby("purchase_status").size().items():
        print(f"  {status}: {count}")

    print(f"\nPurchases with release_date: {purchase_df['release_date'].notna().sum()}")
    print(f"Purchases with NULL release_date: {purchase_df['release_date'].isna().sum()}")

    print(f"\nSubsidiary distribution:")
    for sub, count in extra_df.groupby("subsidiary").size().items():
        print(f"  {sub}: {count}")

    # Show CDC examples
    print("\n" + "=" * 50)
    print("CDC EVOLUTION EXAMPLES")
    print("=" * 50)
    multi_version = purchase_df.groupby("purchase_id").filter(lambda x: len(x) > 1)
    if not multi_version.empty:
        for pid in multi_version["purchase_id"].unique()[:3]:
            print(f"\npurchase_id {pid}:")
            rows = purchase_df[purchase_df["purchase_id"] == pid].sort_values("transaction_datetime")
            for _, r in rows.iterrows():
                release = r["release_date"] if pd.notna(r["release_date"]) else "NULL"
                print(f"  {r['transaction_datetime']} | status={r['purchase_status']} | release_date={release}")


if __name__ == "__main__":
    main()
