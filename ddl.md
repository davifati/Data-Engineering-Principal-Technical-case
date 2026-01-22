# DDL — Final Analytical Table

## Table Definition

```sql
CREATE TABLE gold.fact_gmv_snapshot (
    -- Primary Key (composite)
    purchase_id         BIGINT NOT NULL,
    snapshot_date       DATE NOT NULL,

    -- Partition Column
    transaction_date    DATE NOT NULL,

    -- Business Time Dimensions
    order_date          DATE,
    release_date        DATE,           -- NULL = payment not captured

    -- Business Dimensions
    subsidiary          VARCHAR,
    buyer_id            BIGINT,
    producer_id         BIGINT,
    product_id          BIGINT,
    purchase_status     VARCHAR,        -- APROVADA, CANCELADA, INICIADA, REEMBOLSADA

    -- Metrics
    purchase_value      DECIMAL(18,2),
    item_quantity       INTEGER,

    -- Derived Flag
    is_valid_for_gmv    BOOLEAN NOT NULL,

    -- Audit
    last_updated_at     TIMESTAMP,

    -- Constraints
    PRIMARY KEY (purchase_id, snapshot_date)
)
PARTITIONED BY (transaction_date);
```

---

## Grain

**`(purchase_id, snapshot_date)`**

Each row represents the state of one purchase as observed on one specific date.

This means:
- The same `purchase_id` appears multiple times in the table (once per snapshot)
- Each snapshot is a complete picture of all purchases as known at that point in time
- Queries can retrieve the state of any purchase at any historical date

**Example:**

| purchase_id | snapshot_date | release_date | is_valid_for_gmv |
|-------------|---------------|--------------|------------------|
| 72 | 2023-01-17 | NULL | false |
| 72 | 2023-01-18 | NULL | false |
| 72 | 2023-01-24 | 2023-01-20 | true |
| 72 | 2023-01-25 | 2023-01-20 | true |

Purchase 72 was not valid for GMV until January 24, when the late-arriving `release_date` was captured.

---

## Partitioning Strategy

**Partition column:** `transaction_date`

This is the date the event was ingested into the data lake (CDC ingestion time), not the business event date.

### Why `transaction_date`?

The case requirement explicitly states: *"Is partitioned by transaction_date."*

### Query Performance Implications

| Query Type | Partition Behavior |
|------------|-------------------|
| GMV of January (`transaction_date BETWEEN '2023-01-01' AND '2023-01-31'`) | Partition pruning — scans only 31 partitions |
| Current state (`snapshot_date = MAX(...)`) | Full scan with filter — acceptable at this scale |
| As-of query for a period | Partition pruning on `transaction_date` + filter on `snapshot_date` |

### Trade-off Acknowledged

Partitioning by `snapshot_date` would optimize current-state queries, but would violate the case requirement. At Teachable's volume (~100k purchases/month), the filter-based approach is acceptable.

For larger scale, composite partitioning `(transaction_date, snapshot_date)` would be considered.

---

## Immutability Strategy

The table is **append-only**. No `UPDATE` or `DELETE` operations are ever performed.

### How It Works

```
Day 1: Pipeline runs → INSERT snapshot for 2023-01-20
Day 2: Pipeline runs → INSERT snapshot for 2023-01-21
Day 3: Pipeline runs → INSERT snapshot for 2023-01-22
...
```

Each pipeline execution appends a new snapshot. Previous snapshots remain untouched.

### dbt Implementation

```yaml
config:
  materialized: incremental
  unique_key: ['purchase_id', 'snapshot_date']
  incremental_strategy: append
```

The `NOT EXISTS` clause ensures idempotency—running the pipeline twice on the same day doesn't create duplicates:

```sql
SELECT * FROM snapshot
{% if is_incremental() %}
WHERE NOT EXISTS (
    SELECT 1 FROM {{ this }} existing
    WHERE existing.purchase_id = snapshot.purchase_id
      AND existing.snapshot_date = CURRENT_DATE
)
{% endif %}
```

### Why This Matters

Immutability is **structural**, not **conventional**.

In alternative approaches (like SCD Type 2), immutability depends on discipline—developers must remember to INSERT instead of UPDATE. A bug can corrupt history.

With daily snapshots, each snapshot is a separate set of rows. There's nothing to update. The design makes mutation impossible.

---

## Current vs Historical Data

### Current State

The current state is the most recent snapshot:

```sql
-- Using the convenience view
SELECT * FROM gold.v_gmv_current;

-- Or explicitly
SELECT * FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot);
```

### Historical State (As-Of Query)

Any past state can be retrieved by filtering on `snapshot_date`:

```sql
-- State as known on March 31, 2023
SELECT * FROM gold.fact_gmv_snapshot
WHERE snapshot_date = '2023-03-31';
```

### Comparing States

```sql
-- What changed between two dates?
SELECT
    COALESCE(a.purchase_id, b.purchase_id) AS purchase_id,
    a.purchase_value AS value_jan,
    b.purchase_value AS value_mar,
    a.is_valid_for_gmv AS gmv_jan,
    b.is_valid_for_gmv AS gmv_mar
FROM gold.fact_gmv_snapshot a
FULL OUTER JOIN gold.fact_gmv_snapshot b
    ON a.purchase_id = b.purchase_id
WHERE a.snapshot_date = '2023-01-31'
  AND b.snapshot_date = '2023-03-31'
  AND (a.purchase_value != b.purchase_value
       OR a.is_valid_for_gmv != b.is_valid_for_gmv
       OR a.purchase_id IS NULL
       OR b.purchase_id IS NULL);
```

### Historical Lineage of a Single Purchase

```sql
-- How did purchase 72 evolve over time?
SELECT
    snapshot_date,
    purchase_status,
    release_date,
    purchase_value,
    is_valid_for_gmv
FROM gold.fact_gmv_snapshot
WHERE purchase_id = 72
ORDER BY snapshot_date;
```

---

## Late Events Handling

Late-arriving events are incorporated **without mutating past snapshots**.

### The Problem

CDC events arrive asynchronously. A purchase might be ingested on January 17, but its payment confirmation (`release_date`) might not arrive until January 24.

### The Solution

1. **Raw layer** receives all events, including late arrivals
2. **Silver layer** deduplicates by taking the latest version per `purchase_id` (ordered by `transaction_datetime`)
3. **Gold layer** captures whatever state exists at snapshot time

### Example: Purchase 72

**Raw events received:**

| transaction_datetime | purchase_id | release_date | purchase_status |
|---------------------|-------------|--------------|-----------------|
| 2023-01-17 12:26:00 | 72 | NULL | INICIADA |
| 2023-01-24 12:26:00 | 72 | 2023-01-20 | APROVADA |

**Silver (after dedup):**

On January 17-23, the latest version has `release_date = NULL`.
On January 24+, the latest version has `release_date = 2023-01-20`.

**Gold snapshots:**

| snapshot_date | purchase_id | release_date | is_valid_for_gmv |
|---------------|-------------|--------------|------------------|
| 2023-01-17 | 72 | NULL | false |
| 2023-01-18 | 72 | NULL | false |
| ... | ... | ... | ... |
| 2023-01-23 | 72 | NULL | false |
| 2023-01-24 | 72 | 2023-01-20 | true |
| 2023-01-25 | 72 | 2023-01-20 | true |

### Key Points

1. **Snapshots from January 17-23 are not modified.** They correctly reflect what we knew at that time.

2. **The late arrival appears in the January 24 snapshot.** This is when we learned about the payment.

3. **GMV queries are time-aware.**
   - GMV as of January 23: Purchase 72 is **not** included (we didn't know it was paid)
   - GMV as of January 24: Purchase 72 **is** included (we now know it was paid)

4. **Auditability is preserved.** We can always answer: *"What did we report on date X?"*

### No Special Logic Required

The beauty of the snapshot approach is that late arrivals are handled automatically. Each day, we take a picture of current state. If something changed since yesterday, the new snapshot reflects it. Previous snapshots remain unchanged.

There's no need for:
- Backfill logic
- Version tracking
- Merge operations
- Correction flags

The architecture handles late arrivals by design, not by code.

---

## Summary

| Aspect | Implementation |
|--------|----------------|
| **Grain** | `(purchase_id, snapshot_date)` |
| **Partition** | `transaction_date` |
| **Immutability** | Append-only; no UPDATE/DELETE |
| **Current data** | `snapshot_date = MAX(...)` or `v_gmv_current` view |
| **Historical data** | `snapshot_date = 'YYYY-MM-DD'` |
| **Late events** | Automatically captured in next snapshot; past snapshots unchanged |
