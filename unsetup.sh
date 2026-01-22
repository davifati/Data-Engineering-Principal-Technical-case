#!/bin/bash
set -e

echo "=============================================="
echo "Teachable GMV Technical Case - Unsetup"
echo "=============================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "Removing virtual environment..."
rm -rf .venv

echo "Removing generated data..."
rm -rf data/raw/*.csv

echo "Removing DuckDB database..."
rm -rf warehouse/*.duckdb

echo "Removing dbt artifacts..."
rm -rf dbt_project/target
rm -rf dbt_project/dbt_packages
rm -rf dbt_project/logs

echo ""
echo "=============================================="
echo "Unsetup complete! Run ./setup.sh to start fresh."
echo "=============================================="
