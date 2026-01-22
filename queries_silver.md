# Queries - Camada Silver

## Pré-requisito

Antes de testar, execute o dbt para criar as views:

```bash
cd dbt_project && dbt run --profiles-dir .
```

---

## 1. Validação de Deduplicação

### 1.1 Conferir que cada staging tem grain correto

```sql
-- stg_purchase: deve ter 1 row por purchase_id
SELECT
    'stg_purchase' as model,
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_ids,
    CASE WHEN COUNT(*) = COUNT(DISTINCT purchase_id) THEN 'OK' ELSE 'FAIL' END as grain_check
FROM silver.stg_purchase;
```

```sql
-- stg_product_item: deve ter 1 row por prod_item_id
SELECT
    'stg_product_item' as model,
    COUNT(*) as total_rows,
    COUNT(DISTINCT prod_item_id) as unique_ids,
    CASE WHEN COUNT(*) = COUNT(DISTINCT prod_item_id) THEN 'OK' ELSE 'FAIL' END as grain_check
FROM silver.stg_product_item;
```

```sql
-- stg_purchase_extra_info: deve ter 1 row por purchase_id
SELECT
    'stg_purchase_extra_info' as model,
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_ids,
    CASE WHEN COUNT(*) = COUNT(DISTINCT purchase_id) THEN 'OK' ELSE 'FAIL' END as grain_check
FROM silver.stg_purchase_extra_info;
```

```sql
-- stg_order_transaction_cost_hist: deve ter 1 row por purchase_id
SELECT
    'stg_order_transaction_cost_hist' as model,
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_ids,
    CASE WHEN COUNT(*) = COUNT(DISTINCT purchase_id) THEN 'OK' ELSE 'FAIL' END as grain_check
FROM silver.stg_order_transaction_cost_hist;
```

### 1.2 Validação consolidada (todas as stagings)

```sql
SELECT 'stg_purchase' as model, COUNT(*) as rows, COUNT(DISTINCT purchase_id) as unique_keys FROM silver.stg_purchase
UNION ALL
SELECT 'stg_product_item', COUNT(*), COUNT(DISTINCT prod_item_id) FROM silver.stg_product_item
UNION ALL
SELECT 'stg_purchase_extra_info', COUNT(*), COUNT(DISTINCT purchase_id) FROM silver.stg_purchase_extra_info
UNION ALL
SELECT 'stg_order_transaction_cost_hist', COUNT(*), COUNT(DISTINCT purchase_id) FROM silver.stg_order_transaction_cost_hist;
```

---

## 2. Comparação Raw vs Silver (Efeito do Dedup)

### 2.1 Quantos registros foram "colapsados" pelo dedup?

```sql
SELECT
    'purchase' as tabela,
    (SELECT COUNT(*) FROM raw.purchase) as raw_rows,
    (SELECT COUNT(*) FROM silver.stg_purchase) as silver_rows,
    (SELECT COUNT(*) FROM raw.purchase) - (SELECT COUNT(*) FROM silver.stg_purchase) as dedup_removed
UNION ALL
SELECT
    'product_item',
    (SELECT COUNT(*) FROM raw.product_item),
    (SELECT COUNT(*) FROM silver.stg_product_item),
    (SELECT COUNT(*) FROM raw.product_item) - (SELECT COUNT(*) FROM silver.stg_product_item)
UNION ALL
SELECT
    'purchase_extra_info',
    (SELECT COUNT(*) FROM raw.purchase_extra_info),
    (SELECT COUNT(*) FROM silver.stg_purchase_extra_info),
    (SELECT COUNT(*) FROM raw.purchase_extra_info) - (SELECT COUNT(*) FROM silver.stg_purchase_extra_info)
UNION ALL
SELECT
    'order_transaction_cost_hist',
    (SELECT COUNT(*) FROM raw.order_transaction_cost_hist),
    (SELECT COUNT(*) FROM silver.stg_order_transaction_cost_hist),
    (SELECT COUNT(*) FROM raw.order_transaction_cost_hist) - (SELECT COUNT(*) FROM silver.stg_order_transaction_cost_hist);
```

### 2.2 Exemplo: CDC colapsado para última versão

```sql
-- Raw: múltiplas versões do mesmo purchase_id
SELECT purchase_id, purchase_status, release_date, transaction_datetime
FROM raw.purchase
WHERE purchase_id IN (
    SELECT purchase_id FROM raw.purchase GROUP BY purchase_id HAVING COUNT(*) > 1
)
ORDER BY purchase_id, transaction_datetime
LIMIT 10;
```

```sql
-- Silver: apenas última versão
SELECT purchase_id, purchase_status, release_date, transaction_datetime
FROM silver.stg_purchase
WHERE purchase_id IN (
    SELECT purchase_id FROM raw.purchase GROUP BY purchase_id HAVING COUNT(*) > 1
)
ORDER BY purchase_id
LIMIT 10;
```

---

## 3. Visualização das Stagings

### 3.1 stg_purchase

```sql
SELECT * FROM silver.stg_purchase LIMIT 10;
```

### 3.2 stg_product_item

```sql
SELECT * FROM silver.stg_product_item LIMIT 10;
```

### 3.3 stg_purchase_extra_info

```sql
SELECT * FROM silver.stg_purchase_extra_info LIMIT 10;
```

### 3.4 stg_order_transaction_cost_hist

```sql
SELECT * FROM silver.stg_order_transaction_cost_hist LIMIT 10;
```

---

## 4. Intermediate: int_purchase_enriched

### 4.1 Visualizar dados consolidados

```sql
SELECT * FROM silver.int_purchase_enriched LIMIT 10;
```

### 4.2 Validar grain (1 row por purchase_id)

```sql
SELECT
    'int_purchase_enriched' as model,
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_ids,
    CASE WHEN COUNT(*) = COUNT(DISTINCT purchase_id) THEN 'OK' ELSE 'FAIL' END as grain_check
FROM silver.int_purchase_enriched;
```

### 4.3 Validar joins (sem órfãos)

```sql
-- Purchases sem product_item (purchase_value NULL)
SELECT COUNT(*) as purchases_sem_product_item
FROM silver.int_purchase_enriched
WHERE purchase_value IS NULL;
```

```sql
-- Purchases sem subsidiary (subsidiary NULL)
SELECT COUNT(*) as purchases_sem_subsidiary
FROM silver.int_purchase_enriched
WHERE subsidiary IS NULL;
```

---

## 5. Distribuições na Silver

### 5.1 Status das purchases (após dedup)

```sql
SELECT purchase_status, COUNT(*) as total
FROM silver.stg_purchase
GROUP BY purchase_status
ORDER BY total DESC;
```

### 5.2 Subsidiaries (após dedup)

```sql
SELECT subsidiary, COUNT(*) as total
FROM silver.stg_purchase_extra_info
GROUP BY subsidiary
ORDER BY total DESC;
```

### 5.3 Purchases válidas para GMV (release_date NOT NULL e APROVADA)

```sql
SELECT
    COUNT(*) as total_purchases,
    SUM(CASE WHEN release_date IS NOT NULL AND purchase_status = 'APROVADA' THEN 1 ELSE 0 END) as valid_for_gmv,
    SUM(CASE WHEN release_date IS NULL THEN 1 ELSE 0 END) as sem_release_date,
    SUM(CASE WHEN purchase_status != 'APROVADA' THEN 1 ELSE 0 END) as status_nao_aprovada
FROM silver.stg_purchase;
```

---

## 6. Preview do GMV (usando int_purchase_enriched)

### 6.1 GMV por subsidiary (preview da gold)

```sql
SELECT
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(DISTINCT purchase_id) as transactions
FROM silver.int_purchase_enriched
WHERE release_date IS NOT NULL
  AND purchase_status = 'APROVADA'
GROUP BY subsidiary
ORDER BY gmv DESC;
```

### 6.2 GMV por transaction_date e subsidiary

```sql
SELECT
    transaction_date,
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(DISTINCT purchase_id) as transactions
FROM silver.int_purchase_enriched
WHERE release_date IS NOT NULL
  AND purchase_status = 'APROVADA'
GROUP BY transaction_date, subsidiary
ORDER BY transaction_date, subsidiary;
```

---

## 7. Checklist de Validação

Execute estas queries e confirme:

| Check | Query | Esperado |
|-------|-------|----------|
| stg_purchase grain | 1.1 | `grain_check = OK` |
| stg_product_item grain | 1.1 | `grain_check = OK` |
| stg_purchase_extra_info grain | 1.1 | `grain_check = OK` |
| stg_order_transaction_cost_hist grain | 1.1 | `grain_check = OK` |
| int_purchase_enriched grain | 4.2 | `grain_check = OK` |
| Joins sem órfãos | 4.3 | `0` em ambas queries |
| Dedup funcionou | 2.1 | `dedup_removed > 0` para tabelas com CDC |
