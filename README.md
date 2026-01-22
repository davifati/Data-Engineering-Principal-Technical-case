# Teachable GMV Technical Case

Data Engineering Principal I - Technical Assessment

## Overview

This project implements an immutable, historically consistent analytical data model for calculating daily GMV (Gross Merchandising Value) by subsidiary.

## Tech Stack

- **Python 3.10+** - Runtime environment
- **DuckDB** - Local analytical database
- **dbt (dbt-duckdb)** - Data transformation framework
- **pandas/numpy** - Data generation utilities

## Project Structure

```
.
├── README.md
├── requirements.txt
├── dbt_project/
│   ├── dbt_project.yml
│   ├── profiles.yml.example
│   └── models/
│       └── sources.yml
├── scripts/
│   ├── generate_mock_cdc.py
│   └── load_to_duckdb.py
├── data/
│   └── raw/                    # Generated CSV files
├── warehouse/
│   └── teachable.duckdb        # DuckDB database file
└── claude/
    └── decidir_estrategia_solucao.md
```

## Quick Start

### 1. Create Python Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate Mock CDC Data

```bash
python scripts/generate_mock_cdc.py --out data/raw --seed 42
```

Expected output:
```
Generating mock CDC data with seed=42
Generating purchase data...
  -> 52 rows written to purchase.csv
Generating order_transaction_cost_hist data...
  -> 51 rows written to order_transaction_cost_hist.csv
Generating product_item data...
  -> 52 rows written to product_item.csv
Generating purchase_extra_info data...
  -> 51 rows written to purchase_extra_info.csv
```

### 4. Load Data into DuckDB

```bash
python scripts/load_to_duckdb.py --db warehouse/teachable.duckdb --data-dir data/raw
```

Expected output:
```
Creating DuckDB database: warehouse/teachable.duckdb
Creating 'raw' schema...

Creating tables and loading data...

  Creating table raw.purchase...
  Loading data from data/raw/purchase.csv...
  -> Loaded 52 rows into raw.purchase

  Creating table raw.order_transaction_cost_hist...
  Loading data from data/raw/order_transaction_cost_hist.csv...
  -> Loaded 51 rows into raw.order_transaction_cost_hist

  Creating table raw.product_item...
  Loading data from data/raw/product_item.csv...
  -> Loaded 52 rows into raw.product_item

  Creating table raw.purchase_extra_info...
  Loading data from data/raw/purchase_extra_info.csv...
  -> Loaded 51 rows into raw.purchase_extra_info

==================================================
SUMMARY - Row counts per table:
==================================================
  raw.purchase: 52 rows
  raw.order_transaction_cost_hist: 51 rows
  raw.product_item: 52 rows
  raw.purchase_extra_info: 51 rows
```

### 5. Configure dbt Profile

Copy the example profile to your dbt profiles directory:

```bash
# Option A: Copy to default dbt location
mkdir -p ~/.dbt
cp dbt_project/profiles.yml.example ~/.dbt/profiles.yml

# Option B: Use local profiles directory
cp dbt_project/profiles.yml.example dbt_project/profiles.yml
```

If using Option B (local profiles), run dbt with:
```bash
cd dbt_project && dbt debug --profiles-dir .
```

### 6. Verify dbt Setup

```bash
cd dbt_project && dbt debug
```

Expected output:
```
  Connection:
    database: ../warehouse/teachable.duckdb
    schema: main
    Connection test: OK connection ok
  All checks passed!
```

## Verify Raw Data in DuckDB

You can use the DuckDB CLI to verify the data:

```bash
# Start DuckDB CLI
duckdb warehouse/teachable.duckdb

# Check row counts
SELECT COUNT(*) FROM raw.purchase;
SELECT COUNT(*) FROM raw.order_transaction_cost_hist;
SELECT COUNT(*) FROM raw.product_item;
SELECT COUNT(*) FROM raw.purchase_extra_info;

# Sample purchase data
SELECT * FROM raw.purchase LIMIT 5;

# Check subsidiaries distribution
SELECT subsidiary, COUNT(*)
FROM raw.purchase_extra_info
GROUP BY subsidiary;

# Check purchase status distribution
SELECT purchase_status, COUNT(*)
FROM raw.purchase
GROUP BY purchase_status;

# Exit DuckDB
.exit
```

## Raw CDC Tables Schema

### purchase
| Column | Type | Description |
|--------|------|-------------|
| purchase_id | BIGINT | Unique purchase identifier |
| buyer_id | BIGINT | Buyer/customer identifier |
| prod_item_id | BIGINT | FK to product_item |
| order_date | DATE | Order placement date |
| release_date | DATE | Payment capture date (NULL if unpaid) |
| producer_id | BIGINT | Course producer identifier |
| purchase_partition | BIGINT | Partition key |
| prod_item_partition | BIGINT | Product item partition key |
| purchase_total_value | DOUBLE | Total purchase value |
| purchase_status | VARCHAR | INICIADA, APROVADA, CANCELADA, REEMBOLSADA |
| transaction_datetime | TIMESTAMP | Ingestion timestamp |
| transaction_date | DATE | Ingestion date |

### order_transaction_cost_hist
| Column | Type | Description |
|--------|------|-------------|
| purchase_id | BIGINT | FK to purchase |
| purchase_partition | BIGINT | Partition key |
| order_transaction_cost_vat_value | DOUBLE | VAT/tax value |
| order_transaction_cost_installment_value | DOUBLE | Installment fee |
| order_transaction_cost_date | DATE | Cost record date |
| transaction_datetime | TIMESTAMP | Ingestion timestamp |
| transaction_date | DATE | Ingestion date |

### product_item
| Column | Type | Description |
|--------|------|-------------|
| prod_item_id | BIGINT | Unique product item identifier |
| prod_item_partition | BIGINT | Partition key |
| product_id | BIGINT | Product/course identifier |
| item_quantity | INTEGER | Quantity purchased |
| purchase_value | DOUBLE | Line item value |
| transaction_datetime | TIMESTAMP | Ingestion timestamp |
| transaction_date | DATE | Ingestion date |

### purchase_extra_info
| Column | Type | Description |
|--------|------|-------------|
| purchase_id | BIGINT | FK to purchase |
| purchase_partition | BIGINT | Partition key |
| subsidiary | VARCHAR | nacional, internacional, latam |
| transaction_datetime | TIMESTAMP | Ingestion timestamp |
| transaction_date | DATE | Ingestion date |

## Table Relationships

```
purchase_extra_info.purchase_id ──────┐
                                      │
order_transaction_cost_hist.purchase_id ──► purchase.purchase_id
                                      │
purchase.prod_item_id ────────────────┴──► product_item.prod_item_id
```

## Mock Data Characteristics

The generated mock data includes:
- **50 base purchases** with various statuses
- **3 subsidiaries**: nacional (50%), internacional (35%), latam (15%)
- **4 statuses**: INICIADA (15%), APROVADA (60%), CANCELADA (15%), REEMBOLSADA (10%)
- **Late arrivals**: Events arriving 1-15 days after order date
- **Duplicate rows**: ~3-5% duplicates to simulate replay scenarios
- **Out-of-order events**: Some records with earlier timestamps ingested later

## Next Steps

After completing this setup, the analytical models (silver/gold layers) will be implemented to:
1. Deduplicate CDC events
2. Join the 3 source tables
3. Build the immutable fact table with GMV calculations
4. Support as-of queries for historical consistency
