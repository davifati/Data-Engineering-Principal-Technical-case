"""
Script para calcular o GMV esperado manualmente a partir dos dados raw.
Simula a lógica da silver/gold para validação.
"""

import pandas as pd
from pathlib import Path

# Paths
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"

def load_raw_data():
    """Carrega os CSVs raw"""
    purchase = pd.read_csv(DATA_DIR / "purchase.csv")
    product_item = pd.read_csv(DATA_DIR / "product_item.csv")
    purchase_extra_info = pd.read_csv(DATA_DIR / "purchase_extra_info.csv")

    # Converter timestamps
    purchase['transaction_datetime'] = pd.to_datetime(purchase['transaction_datetime'])
    product_item['transaction_datetime'] = pd.to_datetime(product_item['transaction_datetime'])
    purchase_extra_info['transaction_datetime'] = pd.to_datetime(purchase_extra_info['transaction_datetime'])

    return purchase, product_item, purchase_extra_info

def dedup_by_latest(df, key_col, time_col='transaction_datetime'):
    """Deduplica pegando a última versão por chave"""
    return df.sort_values(time_col).drop_duplicates(subset=[key_col], keep='last')

def main():
    print("=" * 80)
    print("CÁLCULO MANUAL DO GMV ESPERADO")
    print("=" * 80)

    # 1. Carregar dados
    purchase_raw, product_item_raw, extra_info_raw = load_raw_data()

    print(f"\n### RAW DATA ###")
    print(f"purchase.csv: {len(purchase_raw)} linhas")
    print(f"product_item.csv: {len(product_item_raw)} linhas")
    print(f"purchase_extra_info.csv: {len(extra_info_raw)} linhas")

    # 2. Dedup - última versão de cada entidade
    purchase = dedup_by_latest(purchase_raw, 'purchase_id')
    product_item = dedup_by_latest(product_item_raw, 'prod_item_id')
    extra_info = dedup_by_latest(extra_info_raw, 'purchase_id')

    print(f"\n### APÓS DEDUP (última versão) ###")
    print(f"purchase: {len(purchase)} purchases únicas")
    print(f"product_item: {len(product_item)} items únicos")
    print(f"purchase_extra_info: {len(extra_info)} registros únicos")

    # 3. Join: purchase + product_item + extra_info
    # purchase.prod_item_id -> product_item.prod_item_id
    # purchase.purchase_id -> extra_info.purchase_id

    enriched = purchase.merge(
        product_item[['prod_item_id', 'purchase_value', 'product_id', 'item_quantity']],
        on='prod_item_id',
        how='left'
    ).merge(
        extra_info[['purchase_id', 'subsidiary']],
        on='purchase_id',
        how='left'
    )

    print(f"\n### APÓS JOIN (int_purchase_enriched) ###")
    print(f"Registros: {len(enriched)}")

    # 4. Calcular is_valid_for_gmv
    enriched['is_valid_for_gmv'] = (
        enriched['release_date'].notna() &
        (enriched['purchase_status'] == 'APROVADA')
    )

    # 5. Mostrar todas as purchases com detalhes
    print("\n" + "=" * 80)
    print("DETALHAMENTO POR PURCHASE")
    print("=" * 80)

    cols = ['purchase_id', 'prod_item_id', 'purchase_status', 'release_date',
            'subsidiary', 'purchase_value', 'is_valid_for_gmv']

    enriched_sorted = enriched[cols].sort_values('purchase_id')

    print("\n| purchase_id | prod_item_id | status | release_date | subsidiary | value | is_gmv |")
    print("|-------------|--------------|--------|--------------|------------|-------|--------|")

    for _, row in enriched_sorted.iterrows():
        release = str(row['release_date'])[:10] if pd.notna(row['release_date']) else 'NULL'
        value = f"{row['purchase_value']:.2f}" if pd.notna(row['purchase_value']) else 'NULL'
        gmv = 'YES' if row['is_valid_for_gmv'] else 'NO'
        print(f"| {row['purchase_id']:>11} | {row['prod_item_id']:>12} | {row['purchase_status']:<6} | {release:<12} | {row['subsidiary']:<10} | {value:>10} | {gmv:<6} |")

    # 6. Calcular GMV
    print("\n" + "=" * 80)
    print("GMV ESPERADO")
    print("=" * 80)

    gmv_valid = enriched[enriched['is_valid_for_gmv'] == True]

    print(f"\n### CONTAGENS ###")
    print(f"Total purchases: {len(enriched)}")
    print(f"Válidas para GMV: {len(gmv_valid)}")
    print(f"Inválidas: {len(enriched) - len(gmv_valid)}")

    print(f"\n### POR STATUS ###")
    status_counts = enriched['purchase_status'].value_counts()
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    print(f"\n### GMV POR SUBSIDIARY ###")
    gmv_by_sub = gmv_valid.groupby('subsidiary').agg({
        'purchase_value': ['sum', 'count']
    }).round(2)
    gmv_by_sub.columns = ['gmv', 'count']
    print(gmv_by_sub.to_string())

    print(f"\n### GMV TOTAL ###")
    gmv_total = gmv_valid['purchase_value'].sum()
    print(f"GMV Total: {gmv_total:.2f}")

    # 7. Lista de purchases válidas para GMV
    print("\n" + "=" * 80)
    print("PURCHASES VÁLIDAS PARA GMV (para conferência)")
    print("=" * 80)
    print("\n| purchase_id | subsidiary | purchase_value |")
    print("|-------------|------------|----------------|")

    for _, row in gmv_valid.sort_values('purchase_id').iterrows():
        print(f"| {row['purchase_id']:>11} | {row['subsidiary']:<10} | {row['purchase_value']:>14.2f} |")

    print(f"\n{'':>11} | {'TOTAL':<10} | {gmv_total:>14.2f} |")

    # 8. Gerar SQL de validação
    print("\n" + "=" * 80)
    print("SQL DE VALIDAÇÃO (copie e execute no DuckDB)")
    print("=" * 80)

    print("""
-- 1. Validar contagem total de purchases
SELECT
    CASE WHEN COUNT(*) = """ + str(len(enriched)) + """ THEN 'OK' ELSE 'ERRO' END as validation,
    'Total purchases' as metric,
    COUNT(*) as actual,
    """ + str(len(enriched)) + """ as expected
FROM gold.v_gmv_current;

-- 2. Validar contagem de GMV válido
SELECT
    CASE WHEN COUNT(*) = """ + str(len(gmv_valid)) + """ THEN 'OK' ELSE 'ERRO' END as validation,
    'GMV valid count' as metric,
    COUNT(*) as actual,
    """ + str(len(gmv_valid)) + """ as expected
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true;

-- 3. Validar GMV total (com tolerância de 0.01 para arredondamento)
SELECT
    CASE WHEN ABS(SUM(purchase_value) - """ + f"{gmv_total:.2f}" + """) < 0.01 THEN 'OK' ELSE 'ERRO' END as validation,
    'GMV total' as metric,
    ROUND(SUM(purchase_value), 2) as actual,
    """ + f"{gmv_total:.2f}" + """ as expected
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true;
""")

    # GMV por subsidiary
    for sub in gmv_by_sub.index:
        sub_gmv = gmv_by_sub.loc[sub, 'gmv']
        sub_count = int(gmv_by_sub.loc[sub, 'count'])
        print(f"""
-- 4. Validar GMV {sub}
SELECT
    CASE WHEN ABS(SUM(purchase_value) - {sub_gmv:.2f}) < 0.01 THEN 'OK' ELSE 'ERRO' END as validation,
    'GMV {sub}' as metric,
    ROUND(SUM(purchase_value), 2) as actual,
    {sub_gmv:.2f} as expected,
    COUNT(*) as count_actual,
    {sub_count} as count_expected
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true AND subsidiary = '{sub}';
""")

    # 9. Query consolidada de validação
    print("""
-- QUERY CONSOLIDADA DE VALIDAÇÃO
-- Deve retornar todas as linhas com 'OK'
WITH expected AS (
    SELECT 'Total purchases' as metric, """ + str(len(enriched)) + """ as expected
    UNION ALL SELECT 'GMV valid count', """ + str(len(gmv_valid)) + """
    UNION ALL SELECT 'GMV total', """ + f"{gmv_total:.2f}" + """
""")
    for sub in gmv_by_sub.index:
        sub_gmv = gmv_by_sub.loc[sub, 'gmv']
        print(f"    UNION ALL SELECT 'GMV {sub}', {sub_gmv:.2f}")

    print("""),
actual AS (
    SELECT 'Total purchases' as metric, COUNT(*)::numeric as actual FROM gold.v_gmv_current
    UNION ALL SELECT 'GMV valid count', COUNT(*) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
    UNION ALL SELECT 'GMV total', ROUND(SUM(purchase_value), 2) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
""")
    for sub in gmv_by_sub.index:
        print(f"    UNION ALL SELECT 'GMV {sub}', ROUND(SUM(purchase_value), 2) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true AND subsidiary = '{sub}'")

    print(""")
SELECT
    e.metric,
    a.actual,
    e.expected,
    CASE WHEN ABS(a.actual - e.expected) < 0.01 THEN 'OK' ELSE 'ERRO' END as validation
FROM expected e
JOIN actual a ON e.metric = a.metric
ORDER BY e.metric;
""")

    return enriched, gmv_valid, gmv_total, gmv_by_sub

if __name__ == "__main__":
    main()
