# GMV Data Product — Design Specification

This document describes the design decisions behind the GMV analytical layer, built as a data product for Finance, BI, and Leadership. It reflects alignment with the Data team on requirements, constraints, and trade-offs.

---

## Why This Matters

GMV is the number that shows up in board decks, investor reports, and monthly closes. When Finance asks "what was our GMV last quarter?", they need an answer they can defend—not a number that changes depending on when they ask.

The challenge is that GMV is computed from CDC streams. Events arrive late. They arrive out of order. Sometimes they're replayed for correction. This is normal behavior for event-driven systems, but it creates a problem: how do you report a stable number when the underlying data keeps changing?

This design solves that problem by treating GMV as a versioned data product with explicit guarantees around correctness, stability, and auditability.

---

## Business Goal

Deliver a single, trusted source of daily GMV by subsidiary that stakeholders can use directly—without reconciliation spreadsheets, without asking engineering to validate, and without worrying that yesterday's number will change tomorrow.

### Who Uses This

| Consumer | What They Need |
|----------|----------------|
| Finance | Monthly close numbers, as-of reporting for audits, reconciliation |
| BI | Dashboards, trend analysis, subsidiary comparisons |
| Leadership | A number they can put in a board deck without checking twice |

### What Success Looks Like

- Finance uses the GMV table directly for monthly close
- Historical values remain stable after the reporting window
- Any variance can be traced to specific purchases within minutes
- No shadow spreadsheets exist for GMV calculation

### What Failure Looks Like

- Finance disputes the number or maintains parallel calculations
- Someone asks "why did last month's GMV change?" and we can't answer quickly
- BI avoids the table due to trust issues
- Queries require engineering support for basic questions

---

## The Product Contract

### Metric Definition

**GMV** = sum of `purchase_value` where payment was captured and transaction was approved.

In practice:
```
is_valid_for_gmv = (release_date IS NOT NULL AND purchase_status = 'APROVADA')
```

This flag is computed in the gold layer and exposed directly. Consumers filter on `is_valid_for_gmv = true`—no need to remember the business logic.

### Grain

Each row represents a purchase at a point in time:

- **purchase_id**: the transaction
- **snapshot_date**: when we observed this state

This means the same purchase can appear multiple times in the table—once per snapshot. That's intentional. It's what enables as-of queries and historical lineage.

### Dimensions

- **subsidiary**: primary business dimension
- **transaction_date**: when the event was ingested (partition key)
- **snapshot_date**: when the snapshot was taken (version key)

The distinction between `transaction_date` and `snapshot_date` is important. One is business time (when did this happen?), the other is system time (when did we know about it?). Keeping both explicit is what makes the model auditable.

---

## Data Reality

The source data comes from three CDC tables, plus one cost table that's available for future use:

| Table | Contains | Notes |
|-------|----------|-------|
| `purchase` | Core event: order_date, release_date, status | Main fact |
| `product_item` | Line items, monetary amounts | Provides `purchase_value` |
| `purchase_extra_info` | Dimensional attributes | Provides `subsidiary` |
| `order_transaction_cost_hist` | VAT, installment costs | Not used in GMV, available for reconciliation |

These tables are ingested asynchronously. A purchase might land in the lake today, but its `purchase_extra_info` might not arrive until tomorrow. Events can arrive late, out of order, or be replayed for correction.

The architecture assumes this is normal, not exceptional.

---

## Constraints We're Working With

Some constraints come from the business, some from the technical case requirements:

| Constraint | Source | Implication |
|------------|--------|-------------|
| D-1 freshness | Business requirement | No real-time; batch is sufficient |
| Partition by `transaction_date` | Case requirement | Optimizes period queries, not snapshot queries |
| Append-only | Auditability need | No UPDATE/DELETE on analytical tables |
| No joins for consumers | Usability need | Gold layer must be fully denormalized |

These constraints shaped the architecture. We didn't pick a design and then check if it fits—we started with the constraints and built what they require.

---

## How Consumers Use It

### Current State

Most queries want "GMV right now":

```sql
SELECT subsidiary, SUM(purchase_value) as gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary;
```

The `v_gmv_current` view handles the snapshot filtering automatically.

### As-Of Analysis

"What was GMV of January as we reported it on March 31?"

```sql
SELECT subsidiary, SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = '2024-03-31'
  AND transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

Same table, different filter. No special logic needed.

### Historical Lineage

"How did purchase 12345 evolve over time?"

```sql
SELECT snapshot_date, purchase_status, release_date, purchase_value
FROM gold.fact_gmv_snapshot
WHERE purchase_id = 12345
ORDER BY snapshot_date;
```

Every state is preserved. Nothing is overwritten.

---

## What We're Explicitly Not Doing

- **Real-time GMV**: Would require a different architecture. D-1 is sufficient for financial reporting.
- **Intra-day snapshots**: Daily granularity matches business reporting cadence.
- **Automatic Finance reconciliation**: The data is there; the process remains manual.
- **Optimizing for storage**: We're trading storage for auditability. That's intentional.

---

## Validation

The implementation was validated against all 9 requirements from the technical case:

| Requirement | Status |
|-------------|--------|
| GMV only from released transactions | ✓ |
| Handles late arrivals and reprocessing | ✓ |
| Preserves past analytical results | ✓ |
| Supports as-of queries | ✓ |
| Easy access to current/historical/lineage | ✓ |
| Simple to query (no joins) | ✓ |
| Partitioned by transaction_date | ✓ |
| Updated in D-1 batches | ✓ |
| Reprocessing doesn't rewrite history | ✓ |

Validation scripts and expected values are documented separately.

---

## Summary

This design treats GMV as a data product with explicit contracts. The architecture is append-only and versioned, which means:

- Past results never change
- Late arrivals are incorporated without rewriting history
- Any question about "what did we know when" has a clear answer

The trade-off is storage growth—every snapshot is preserved. For a financial metric where trust matters more than disk space, that's the right trade-off.
