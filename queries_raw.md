# Queries - Camada Raw

## Tabelas

```sql
SELECT * FROM raw.purchase LIMIT 10;
```

```sql
SELECT * FROM raw.product_item LIMIT 10;
```

```sql
SELECT * FROM raw.order_transaction_cost_hist LIMIT 10;
```

```sql
SELECT * FROM raw.purchase_extra_info LIMIT 10;
```

## Contagens

```sql
SELECT 'purchase' as tabela, COUNT(*) as rows FROM raw.purchase
UNION ALL SELECT 'product_item', COUNT(*) FROM raw.product_item
UNION ALL SELECT 'order_transaction_cost_hist', COUNT(*) FROM raw.order_transaction_cost_hist
UNION ALL SELECT 'purchase_extra_info', COUNT(*) FROM raw.purchase_extra_info;
```

## CDC - Múltiplas versões

* o mesmo purchase_id aparecendo múltiplas vezes com dados diferentes ao longo
  do tempo.

  O que demonstra:
  1. Evolução de estado - purchase 69 foi de INICIADA → CANCELADA
  2. Late arrival - o segundo evento chegou dias depois
  3. Veamos precisar de dedup na silver !!!!!!!

```sql
SELECT *
FROM raw.purchase
WHERE purchase_id IN (
    SELECT purchase_id FROM raw.purchase GROUP BY purchase_id HAVING COUNT(*) > 1
)
ORDER BY purchase_id, transaction_datetime
LIMIT 20;
```

```sql
SELECT *
FROM raw.purchase_extra_info
WHERE purchase_id IN (
    SELECT purchase_id FROM raw.purchase_extra_info GROUP BY purchase_id HAVING COUNT(*) > 1
)
ORDER BY purchase_id, transaction_datetime
LIMIT 20;
```

## Distribuições

```sql
SELECT purchase_status, COUNT(*) as total
FROM raw.purchase
GROUP BY purchase_status;
```

```sql
SELECT subsidiary, COUNT(*) as total
FROM raw.purchase_extra_info
GROUP BY subsidiary;
```

## Relacionamentos

```sql
SELECT *
FROM raw.purchase p
JOIN raw.product_item pi ON p.prod_item_id = pi.prod_item_id
LIMIT 10;
```

```sql
SELECT *
FROM raw.purchase p
JOIN raw.purchase_extra_info pei ON p.purchase_id = pei.purchase_id
JOIN raw.order_transaction_cost_hist otc ON p.purchase_id = otc.purchase_id
LIMIT 10;
```
