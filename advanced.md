# Advanced Topics

This document discusses how the GMV data model would evolve beyond the current batch architecture. These aren't hypothetical exercises—they're the conversations I'd expect to have with the team as the business scales.

---

## Real-Time Evolution

The current architecture is D-1 batch. That's the right choice for financial reporting—Finance doesn't need GMV updating every second. But other use cases will eventually demand lower latency.

### When Real-Time Makes Sense

- **Fraud detection**: Can't wait 24 hours to flag suspicious patterns
- **Operational dashboards**: Support team needs current order status
- **Marketing attribution**: Campaign performance within hours, not days

### When It Doesn't

- **Monthly close**: D-1 is fine. Actually, D-1 is *better*—it's more stable.
- **Board reporting**: Nobody's refreshing the board deck in real-time
- **Audit trails**: Auditors want immutable snapshots, not live data

### Architecture Options

**Lambda Architecture**

```
         ┌─────────────┐
         │   Batch     │──────┐
         │  (current)  │      │
         └─────────────┘      ▼
                          ┌───────────┐
CDC ─────────────────────▶│  Serving  │
                          │   Layer   │
         ┌─────────────┐      ▲
         │   Speed     │──────┘
         │  (Kafka)    │
         └─────────────┘
```

Two pipelines: batch for correctness, streaming for speed. The serving layer merges both.

**Pros**: Battle-tested. Clear separation of concerns.
**Cons**: Two codebases to maintain. Reconciliation complexity between batch and speed layers.

**Kappa Architecture**

```
CDC ──▶ Kafka ──▶ Flink ──▶ Iceberg ──▶ Consumers
```

Single pipeline. Everything flows through the stream. Batch is just a stream replayed from the beginning.

**Pros**: One codebase. Simpler mental model.
**Cons**: Reprocessing large windows is expensive. Harder to debug than batch.

**Streaming Lakehouse (My Recommendation)**

```
CDC ──▶ Kafka ──▶ Flink ──▶ Iceberg (with upsert) ──▶ Consumers
                              │
                              ▼
                     Batch snapshots (unchanged)
```

Keep the current batch snapshot architecture for Finance. Add a streaming layer that writes to Iceberg tables with upsert semantics for operational use cases.

**Why this approach:**

1. **Doesn't break what works.** Finance keeps their immutable snapshots. Nothing changes for them.

2. **Iceberg handles the hard parts.** Time travel, schema evolution, partition evolution—all built in.

3. **Single source of truth.** Both batch and streaming read from the same Iceberg tables. No reconciliation needed.

4. **Gradual migration.** Start with one use case (fraud?), prove it works, expand.

### What I'd Actually Build

Phase 1: Keep batch as-is. Add Kafka Connect to mirror CDC to Kafka topics.

Phase 2: Build Flink job that maintains a "current state" Iceberg table. This serves operational queries.

Phase 3: Modify batch pipeline to read from Iceberg instead of raw CDC. Now batch and streaming share the same deduplication logic.

The batch snapshots remain untouched. They're still append-only, still partitioned by `transaction_date`, still queryable by `snapshot_date`. We're adding capability, not replacing architecture.

---

## Semantic Metric Layer

Right now, the GMV definition lives in SQL:

```sql
is_valid_for_gmv = (release_date IS NOT NULL AND purchase_status = 'APROVADA')
```

This works until it doesn't. Eventually someone writes a slightly different definition in a dashboard, another in a spreadsheet, and suddenly we're back to "which GMV is right?"

### The Problem

Metric definitions scattered across:
- dbt models
- BI tool calculated fields
- Analyst notebooks
- Finance spreadsheets

Each copy can drift. Each drift creates a reconciliation conversation.

### Solution: Centralized Metric Layer

Tools like dbt Semantic Layer, Cube, or Transform define metrics once and expose them everywhere.

```yaml
# Example: dbt Semantic Layer
metrics:
  - name: gmv
    label: "Gross Merchandise Value"
    type: sum
    sql: purchase_value
    timestamp: order_date

    filters:
      - field: is_valid_for_gmv
        operator: "="
        value: true

    dimensions:
      - subsidiary
      - transaction_date
      - snapshot_date
```

### What This Enables

**Consistent definitions**: Every tool queries the same metric definition. Looker, Tableau, Python notebooks—all get the same number.

**Governed changes**: Changing the GMV definition requires a PR, code review, and deployment. No more "I updated the formula in the dashboard."

**Self-service with guardrails**: Analysts can slice GMV by any dimension without risk of calculating it wrong.

### My Recommendation

Implement dbt Semantic Layer. It integrates with the existing dbt project and doesn't require new infrastructure. The migration path:

1. Define core metrics (GMV, transaction count, average order value) in dbt
2. Configure BI tools to query through the semantic layer
3. Deprecate direct table access for metric queries
4. Add new metrics as business needs evolve

The `is_valid_for_gmv` flag in the current model is a step toward this—it encapsulates the business rule. The semantic layer just makes it the *only* place that rule exists.

---

## Finance Reconciliation

GMV is not revenue. This distinction matters for Finance.

### The Difference

| Concept | Definition | Timing |
|---------|------------|--------|
| **GMV** | Total value of transactions | When payment is captured (`release_date`) |
| **Revenue** | What Teachable earns | When service is delivered (revenue recognition) |
| **Cash** | What hits the bank | When funds settle |

A $100 course sale might be:
- GMV: $100 (full amount, at capture)
- Revenue: $30 (Teachable's platform fee, recognized over course duration)
- Cash: $28 (after payment processor fees, when it settles)

### How to Support Finance

**1. Preserve GMV as the top-of-funnel metric**

GMV is the number that shows market activity. Keep it simple: sum of captured transactions. Don't try to make one table serve all purposes.

**2. Build a separate revenue recognition model**

```
fact_gmv_snapshot (current)
    │
    ▼
fact_revenue_recognition (new)
    - purchase_id
    - recognition_date
    - recognized_amount
    - recognition_schedule (straight-line, usage-based, etc.)
    - deferred_revenue
```

This table handles the accounting complexity—amortization schedules, deferred revenue, partial recognition. It references GMV but doesn't pollute it.

**3. Expose reconciliation dimensions**

Add to the GMV model:
- `payment_method`: Credit card, PayPal, etc.
- `processor_fee`: Stripe/PayPal take rate
- `net_to_producer`: Amount after platform fee
- `platform_fee`: Teachable's cut

Finance can then reconcile:
```
GMV
- Refunds
- Chargebacks
= Net GMV

Net GMV × Platform Fee Rate
- Processor Fees
= Platform Revenue

Platform Revenue
- Costs
= Gross Margin
```

**4. Double-entry validation**

For every transaction, two entries should balance:

```sql
-- Validation: debits = credits for each purchase
SELECT purchase_id
FROM fact_ledger_entries
GROUP BY purchase_id
HAVING SUM(CASE WHEN entry_type = 'debit' THEN amount ELSE 0 END)
    != SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE 0 END)
```

This isn't in scope for the GMV model, but it's the natural next step for Finance trust.

---

## Backdated Corrections Without Rewriting History

The current model handles late arrivals well—they appear in the next snapshot. But what about corrections that need to affect past periods?

### The Scenario

Finance closes January. In March, they discover a $10,000 transaction was miscategorized—it should be Internacional, not Nacional. They need:

1. Current reports to show the correct subsidiary
2. Historical snapshots to remain unchanged (audit trail)
3. A way to answer "what was the corrected January GMV?"

### The Problem

If we UPDATE the January snapshot, we break immutability. If we don't, the "corrected" number requires manual adjustment.

### Solution: Correction Overlays

Keep snapshots immutable. Add a corrections table:

```sql
CREATE TABLE gold.fact_gmv_corrections (
    correction_id       BIGINT PRIMARY KEY,
    purchase_id         BIGINT NOT NULL,
    effective_date      DATE NOT NULL,        -- When correction applies from
    correction_date     DATE NOT NULL,        -- When correction was made
    field_name          VARCHAR NOT NULL,     -- What changed
    old_value           VARCHAR,
    new_value           VARCHAR,
    reason              VARCHAR,
    approved_by         VARCHAR,

    UNIQUE (purchase_id, effective_date, field_name)
);
```

### How It Works

**Original snapshot (January 31):**
```
purchase_id=999, subsidiary='nacional', purchase_value=10000
```

**Correction entered (March 15):**
```sql
INSERT INTO gold.fact_gmv_corrections VALUES (
    1, 999, '2023-01-15', '2023-03-15',
    'subsidiary', 'nacional', 'internacional',
    'Miscategorized at ingestion', 'finance.user@teachable.com'
);
```

**Querying with corrections:**

```sql
-- Corrected view of January GMV
SELECT
    COALESCE(c.new_value, f.subsidiary) AS subsidiary,
    SUM(f.purchase_value) AS gmv
FROM gold.fact_gmv_snapshot f
LEFT JOIN gold.fact_gmv_corrections c
    ON f.purchase_id = c.purchase_id
    AND f.snapshot_date >= c.effective_date
    AND c.field_name = 'subsidiary'
WHERE f.snapshot_date = '2023-01-31'
  AND f.is_valid_for_gmv = true
GROUP BY 1;
```

**Querying original (audit):**

```sql
-- Original January GMV (as reported)
SELECT subsidiary, SUM(purchase_value) AS gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = '2023-01-31'
  AND is_valid_for_gmv = true
GROUP BY 1;
```

### Why This Works

1. **Snapshots stay immutable.** The original data is preserved for audit.

2. **Corrections are explicit.** Every change has a reason, date, and approver.

3. **Both views are available.** "As reported" and "as corrected" are both queryable.

4. **No partition rewrites.** We're adding rows to a small corrections table, not touching the main fact table.

### Convenience View

```sql
CREATE VIEW gold.v_gmv_corrected AS
SELECT
    f.purchase_id,
    f.snapshot_date,
    f.transaction_date,
    f.order_date,
    f.release_date,
    COALESCE(c_sub.new_value, f.subsidiary) AS subsidiary,
    f.purchase_status,
    COALESCE(CAST(c_val.new_value AS DECIMAL(18,2)), f.purchase_value) AS purchase_value,
    f.is_valid_for_gmv,
    (c_sub.correction_id IS NOT NULL OR c_val.correction_id IS NOT NULL) AS has_correction
FROM gold.fact_gmv_snapshot f
LEFT JOIN gold.fact_gmv_corrections c_sub
    ON f.purchase_id = c_sub.purchase_id
    AND c_sub.field_name = 'subsidiary'
    AND f.snapshot_date >= c_sub.effective_date
LEFT JOIN gold.fact_gmv_corrections c_val
    ON f.purchase_id = c_val.purchase_id
    AND c_val.field_name = 'purchase_value'
    AND f.snapshot_date >= c_val.effective_date;
```

Finance uses `v_gmv_corrected` for current reporting. Audit uses `fact_gmv_snapshot` directly.

---

## Summary

| Topic | Recommendation |
|-------|----------------|
| **Real-time** | Streaming Lakehouse—add Kafka + Flink for operational use cases, keep batch snapshots for Finance |
| **Metric layer** | dbt Semantic Layer—single source of truth for metric definitions |
| **Finance reconciliation** | Separate revenue recognition model, expose reconciliation dimensions |
| **Backdated corrections** | Correction overlays—immutable snapshots + explicit corrections table |

These aren't theoretical. They're the natural evolution of the current architecture as the business grows. The batch snapshot model we built is the foundation—it doesn't get replaced, it gets extended.
