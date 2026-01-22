# Architecture & Data Modeling

This document describes the architectural decisions, data flow, and trade-offs behind the GMV analytical layer.

---

## Design Principles

These principles guided every decision in this design:

**1. Immutability over mutation**

Once data is written, it doesn't change. Corrections are additive—we append new state, we don't overwrite history. This is non-negotiable for financial data.

**2. Simplicity for consumers, complexity hidden in pipelines**

Analysts query a single denormalized table. All joins, deduplication, and versioning logic live in the transformation layer, not in consumption queries.

**3. Explicit time modeling**

Two time dimensions exist and must be kept separate:
- `transaction_date`: when the event was ingested (business/system boundary)
- `snapshot_date`: when we captured this state (versioning)

Conflating these breaks auditability.

**4. Constraints drive architecture**

We didn't pick a design and check if it fits. We started with the constraints—D-1 batch, partition by `transaction_date`, append-only, no joins for consumers—and built what they require.

**5. Pragmatism over elegance**

A simpler solution that meets requirements is better than an elegant solution that adds operational risk. Knowing when not to over-engineer is a sign of maturity.

---

## Architecture Decision: Why Daily Snapshots

Three approaches were evaluated:

| Approach | Description | Verdict |
|----------|-------------|---------|
| **A. Bitemporal (SCD Type 2)** | Each record has `valid_from`/`valid_to` + `processed_at` | Rejected |
| **B. Daily Snapshot** | Each pipeline run produces a complete snapshot | **Selected** |
| **C. Hybrid (delta-only)** | Append only when data changes, with `is_current` flag | Rejected |

### Why not Bitemporal (Option A)?

As-of queries require window functions:

```sql
-- Bitemporal as-of query
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY purchase_id
        ORDER BY processed_at DESC
    ) as rn
    FROM fact_gmv
    WHERE processed_at <= '2023-03-31'
) WHERE rn = 1
```

This violates requirement #6: *"Simple to query by non-expert SQL users."*

A BI analyst will get this wrong. In daily snapshots, the same query is:

```sql
-- Snapshot as-of query
SELECT * FROM fact_gmv_snapshot
WHERE snapshot_date = '2023-03-31'
```

No window function. No subquery. Just a filter.

### Why not Hybrid (Option C)?

Option C is technically interesting—it stores only deltas, reducing storage by ~19x. But:

1. **Storage cost is irrelevant at Teachable scale.** We're talking $30/month vs $2/month. This doesn't justify added complexity.

2. **Immutability becomes a convention, not a guarantee.** Option C requires `UPDATE is_current = false` when new versions arrive. A bug can corrupt historical state. In snapshots, each snapshot is a separate partition—structurally immutable.

3. **Pipeline complexity triples.** Option B is ~50 lines of SQL. Option C is ~150 lines with hash comparison, version management, and careful UPDATE/INSERT orchestration.

4. **Debug is harder.** In Option B, state is materialized—you can see exactly what existed on any date. In Option C, state must be reconstructed via window functions.

### The Decision

**Option B (Daily Snapshots)** is the right choice for this case.

It meets all 9 requirements with the simplest implementation, lowest operational risk, and best analytical usability. If requirements change—real-time needs, billion-row scale—we revisit. Until then, simplicity wins.

---

## From Raw to Gold

```
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│    RAW      │     │       SILVER        │     │        GOLD         │
│   (CDC)     │────▶│  (Dedup + Enrich)   │────▶│    (Snapshot)       │
└─────────────┘     └─────────────────────┘     └─────────────────────┘

 purchase            stg_purchase              fact_gmv_snapshot
 product_item        stg_product_item          v_gmv_current (view)
 purchase_extra_info stg_purchase_extra_info
                     int_purchase_enriched
```

### Raw Layer

CDC tables as ingested. No transformation. Multiple versions of the same entity may exist (late arrivals, corrections, replays).

| Table | Content | Key |
|-------|---------|-----|
| `purchase` | Core transaction event | `purchase_id` |
| `product_item` | Line items, monetary amounts | `prod_item_id` |
| `purchase_extra_info` | Dimensional attributes | `purchase_id` |
| `order_transaction_cost_hist` | Costs (VAT, installments) | `purchase_id` |

### Silver Layer

**Purpose:** Deduplicate CDC events and prepare data for consumption.

**Approach:** One staging model per source table, plus one intermediate model for enrichment.

```
silver/
├── staging/
│   ├── stg_purchase.sql
│   ├── stg_product_item.sql
│   ├── stg_purchase_extra_info.sql
│   └── stg_order_transaction_cost_hist.sql
└── intermediate/
    └── int_purchase_enriched.sql
```

#### Staging Models

Each staging model deduplicates to the latest version per primary key:

```sql
SELECT *
FROM raw.purchase
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY purchase_id
    ORDER BY transaction_datetime DESC
) = 1
```

This handles late arrivals automatically—the most recent event wins.

**Materialization:** `view`

Views are sufficient because:
- Volume is moderate
- Data freshness is guaranteed (always reads current raw state)
- No need to persist intermediate state

In production at higher volume, these could become incremental models.

#### Intermediate Model

`int_purchase_enriched` joins the three staging models into a single denormalized dataset:

```sql
SELECT
    p.purchase_id,
    p.order_date,
    p.release_date,
    p.purchase_status,
    pi.purchase_value,
    pei.subsidiary,
    ...
FROM stg_purchase p
LEFT JOIN stg_product_item pi ON p.prod_item_id = pi.prod_item_id
LEFT JOIN stg_purchase_extra_info pei ON p.purchase_id = pei.purchase_id
```

**Why LEFT JOIN?**

CDC tables arrive asynchronously. A purchase may exist before its `purchase_extra_info` arrives. LEFT JOIN ensures we don't lose purchases due to timing—they'll have `NULL` subsidiary until the dimension arrives, then the next snapshot picks it up.

**Materialization:** `view`

The intermediate model is consumed only by the gold layer. No need to persist.

### Gold Layer

**Purpose:** Produce the analytical fact table that consumers query directly.

**Model:** `fact_gmv_snapshot`

```sql
SELECT
    purchase_id,
    CURRENT_DATE AS snapshot_date,
    transaction_date,
    order_date,
    release_date,
    subsidiary,
    purchase_value,
    purchase_status,
    (release_date IS NOT NULL AND purchase_status = 'APROVADA') AS is_valid_for_gmv,
    ...
FROM silver.int_purchase_enriched
```

**Materialization:** `incremental` with `append` strategy

```yaml
config:
  materialized: incremental
  unique_key: ['purchase_id', 'snapshot_date']
  incremental_strategy: append
```

This ensures:
- Each run appends a new snapshot
- Running twice on the same day doesn't create duplicates (idempotent)
- Historical snapshots are never modified

#### Grain

`(purchase_id, snapshot_date)`

Each row represents the state of one purchase as known on one date. The same purchase appears multiple times—once per snapshot. This is intentional; it enables as-of queries.

#### Partitioning

Partitioned by `transaction_date` as required by the case.

**Trade-off acknowledged:** Partition by `transaction_date` optimizes period queries (GMV of January) but not snapshot queries (state on March 31). For snapshot queries, we filter within partitions rather than prune.

At Teachable scale, this is acceptable. At larger scale, composite partitioning `(transaction_date, snapshot_date)` would be considered.

#### Key Columns

| Column | Purpose |
|--------|---------|
| `purchase_id` | Grain identifier |
| `snapshot_date` | Version identifier (when this state was captured) |
| `transaction_date` | Partition key, business time proxy |
| `is_valid_for_gmv` | Pre-computed inclusion flag |
| `release_date` | Payment capture date (NULL = not paid) |
| `purchase_status` | APROVADA, CANCELADA, INICIADA, etc. |
| `subsidiary` | Primary business dimension |
| `purchase_value` | Monetary amount |

#### The `is_valid_for_gmv` Flag

```sql
is_valid_for_gmv = (release_date IS NOT NULL AND purchase_status = 'APROVADA')
```

This encapsulates the GMV business rule. Consumers filter on `is_valid_for_gmv = true` without needing to know the underlying logic.

**Why not just filter on `release_date IS NOT NULL`?**

The case specifies *"not canceled."* A refunded transaction might have a `release_date` but shouldn't count as GMV. The flag makes the rule explicit and auditable.

### Convenience View: `v_gmv_current`

Most queries want current state. Instead of repeating `snapshot_date = (SELECT MAX...)`, we provide a view:

```sql
SELECT *
FROM fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_gmv_snapshot)
```

**Consumer query becomes:**

```sql
SELECT subsidiary, SUM(purchase_value) AS gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary;
```

No subquery. No snapshot logic. Just business questions.

---

## Trade-off Summary

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| Daily snapshots over bitemporal | Higher storage, simpler queries | Query simplicity > storage cost at this scale |
| Append-only over merge | No in-place corrections | Immutability is structural, not conventional |
| Views in silver | Recomputed on each query | Volume doesn't justify materialization overhead |
| Table in gold | Persisted, versioned | Snapshots must be immutable and queryable |
| Partition by `transaction_date` | Suboptimal for snapshot queries | Meets case requirement; acceptable at this volume |
| `is_valid_for_gmv` flag | Redundant with underlying columns | Encapsulates business rule; prevents consumer errors |
| LEFT JOIN in intermediate | May include incomplete purchases | Better to have NULL than lose data; next snapshot corrects |

---

## What This Architecture Guarantees

1. **Past results never change.** Each snapshot is append-only. No UPDATE, no DELETE.

2. **Late arrivals are handled automatically.** Dedup takes latest version; next snapshot reflects corrections.

3. **Any historical question has a stable answer.** `WHERE snapshot_date = '2023-03-31'` always returns the same result.

4. **Consumers don't need to understand CDC complexity.** They query a single table with a simple filter.

5. **The pipeline is idempotent.** Running it twice on the same day produces the same result.

---

## What This Architecture Does Not Do

- **Real-time GMV.** This is D-1 batch. Real-time would require a different architecture.
- **Intra-day snapshots.** Daily granularity matches business reporting cadence.
- **Automatic reconciliation.** The data supports reconciliation; the process is manual.
- **Storage optimization.** We trade storage for simplicity. That's intentional.
