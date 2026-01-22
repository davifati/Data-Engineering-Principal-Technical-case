#!/bin/bash
set -e

echo "=============================================="
echo "Teachable GMV Technical Case - Setup"
echo "=============================================="

# Get script directory (works even if called from another directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "[1/5] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo ""
echo "[2/5] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "[3/5] Generating mock CDC data..."
python scripts/generate_mock_cdc.py --out data/raw --seed 42

echo ""
echo "[4/5] Loading data into DuckDB..."
python scripts/load_to_duckdb.py --db warehouse/teachable.duckdb --data-dir data/raw

echo ""
echo "[5/5] Testing dbt connection..."
cd dbt_project && dbt debug --profiles-dir .
cd ..

echo ""
echo "[6/6] Verifying data..."
python scripts/query_duckdb.py

echo ""
echo "=============================================="
echo "Setup complete!"
echo "=============================================="
echo ""
echo "To activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run dbt:"
echo "  cd dbt_project && dbt run --profiles-dir ."
