# Validação Numérica do GMV - Reconciliação Raw → Gold

## Valores Esperados (calculados manualmente do raw)

### Resumo

| Métrica | Valor Esperado |
|---------|----------------|
| Total purchases | 30 |
| Válidas para GMV | 18 |
| GMV Total | **23.561,90** |
| GMV Internacional | 13.393,65 (10 transações) |
| GMV Nacional | 10.168,25 (8 transações) |

### Por Status

| Status | Count |
|--------|-------|
| APROVADA | 18 |
| INICIADA | 7 |
| CANCELADA | 5 |

---

## Detalhamento: 18 Purchases Válidas para GMV

| purchase_id | subsidiary | purchase_value |
|-------------|------------|----------------|
| 52 | internacional | 942,73 |
| 53 | internacional | 1.122,45 |
| 55 | internacional | 2.427,48 |
| 56 | internacional | 1.180,13 |
| 58 | nacional | 941,89 |
| 60 | nacional | 2.085,88 |
| 61 | nacional | 2.016,79 |
| 62 | internacional | 370,89 |
| 64 | internacional | 1.160,82 |
| 66 | internacional | 1.728,94 |
| 67 | nacional | 103,67 |
| 70 | nacional | 1.997,68 |
| 71 | nacional | 438,26 |
| 72 | nacional | 1.812,84 |
| 73 | internacional | 401,97 |
| 74 | nacional | 771,24 |
| 77 | internacional | 1.799,30 |
| 78 | internacional | 2.258,94 |
| **TOTAL** | | **23.561,90** |

---

## Queries de Validação

Execute cada query e compare com o valor esperado.

### 1. Total de Purchases

```sql
SELECT COUNT(*) as total_purchases
FROM gold.v_gmv_current;
```
**Esperado:** 30

---

### 2. Contagem por Status

```sql
SELECT purchase_status, COUNT(*) as count
FROM gold.v_gmv_current
GROUP BY purchase_status
ORDER BY count DESC;
```

**Esperado:**
| purchase_status | count |
|-----------------|-------|
| APROVADA | 18 |
| INICIADA | 7 |
| CANCELADA | 5 |

---

### 3. Contagem de GMV Válido

```sql
SELECT
    COUNT(*) FILTER (WHERE is_valid_for_gmv = true) as gmv_valido,
    COUNT(*) FILTER (WHERE is_valid_for_gmv = false) as gmv_invalido
FROM gold.v_gmv_current;
```
**Esperado:** gmv_valido = 18, gmv_invalido = 12

---

### 4. GMV Total

```sql
SELECT ROUND(SUM(purchase_value), 2) as gmv_total
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true;
```
**Esperado:** 23561.90

---

### 5. GMV por Subsidiary

```sql
SELECT
    subsidiary,
    COUNT(*) as transactions,
    ROUND(SUM(purchase_value), 2) as gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary
ORDER BY gmv DESC;
```

**Esperado:**
| subsidiary | transactions | gmv |
|------------|--------------|-----|
| internacional | 10 | 13393.65 |
| nacional | 8 | 10168.25 |

---

### 6. Validação Linha a Linha (Purchases GMV Válidas)

```sql
SELECT
    purchase_id,
    subsidiary,
    ROUND(purchase_value, 2) as purchase_value,
    is_valid_for_gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
ORDER BY purchase_id;
```

**Esperado:** 18 linhas com os valores da tabela de detalhamento acima.

---

### 7. Validação Consolidada (QUERY FINAL)

```sql
-- Rode esta query. Todas as linhas devem mostrar 'OK'
WITH expected AS (
    SELECT 'Total purchases' as metric, 30.0 as expected
    UNION ALL SELECT 'GMV valid count', 18.0
    UNION ALL SELECT 'GMV total', 23561.90
    UNION ALL SELECT 'GMV internacional', 13393.65
    UNION ALL SELECT 'GMV nacional', 10168.25
),
actual AS (
    SELECT 'Total purchases' as metric, COUNT(*)::numeric as actual FROM gold.v_gmv_current
    UNION ALL SELECT 'GMV valid count', COUNT(*) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
    UNION ALL SELECT 'GMV total', ROUND(SUM(purchase_value), 2) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
    UNION ALL SELECT 'GMV internacional', ROUND(SUM(purchase_value), 2) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true AND subsidiary = 'internacional'
    UNION ALL SELECT 'GMV nacional', ROUND(SUM(purchase_value), 2) FROM gold.v_gmv_current WHERE is_valid_for_gmv = true AND subsidiary = 'nacional'
)
SELECT
    e.metric,
    a.actual,
    e.expected,
    CASE WHEN ABS(a.actual - e.expected) < 0.01 THEN '✓ OK' ELSE '✗ ERRO' END as validation
FROM expected e
JOIN actual a ON e.metric = a.metric
ORDER BY e.metric;
```

**Esperado:**
| metric | actual | expected | validation |
|--------|--------|----------|------------|
| GMV internacional | 13393.65 | 13393.65 | ✓ OK |
| GMV nacional | 10168.25 | 10168.25 | ✓ OK |
| GMV total | 23561.90 | 23561.90 | ✓ OK |
| GMV valid count | 18 | 18 | ✓ OK |
| Total purchases | 30 | 30 | ✓ OK |

---

## Validações Específicas por Cenário

### Cenário A: Late Arrival (Purchase 72)

A purchase 72 começou como INICIADA (sem release_date) e depois virou APROVADA.

```sql
SELECT
    purchase_id,
    purchase_status,
    release_date,
    is_valid_for_gmv,
    purchase_value
FROM gold.v_gmv_current
WHERE purchase_id = 72;
```

**Esperado:**
- purchase_status = 'APROVADA'
- release_date = '2023-01-20'
- is_valid_for_gmv = true
- purchase_value = 1812.84

---

### Cenário B: Late Arrival Tardio (Purchase 78)

A purchase 78 só virou APROVADA em Março (late arrival tardio).

```sql
SELECT
    purchase_id,
    purchase_status,
    release_date,
    is_valid_for_gmv,
    purchase_value
FROM gold.v_gmv_current
WHERE purchase_id = 78;
```

**Esperado:**
- purchase_status = 'APROVADA'
- release_date = '2023-02-24'
- is_valid_for_gmv = true
- purchase_value = 2258.94

---

### Cenário C: Cancelamento (Purchase 69)

A purchase 69 foi INICIADA e depois CANCELADA, nunca teve release_date.

```sql
SELECT
    purchase_id,
    purchase_status,
    release_date,
    is_valid_for_gmv
FROM gold.v_gmv_current
WHERE purchase_id = 69;
```

**Esperado:**
- purchase_status = 'CANCELADA'
- release_date = NULL
- is_valid_for_gmv = false

---

### Cenário D: Múltiplas Versões CDC (Purchase 64)

A purchase 64 tem 4 versões no raw. O dedup deve pegar a última.

```sql
-- Versões no raw (para referência)
SELECT purchase_id, transaction_datetime, release_date, purchase_status
FROM raw.purchase
WHERE purchase_id = 64
ORDER BY transaction_datetime;

-- Resultado na gold (deve ser 1 linha)
SELECT
    purchase_id,
    transaction_date,
    release_date,
    is_valid_for_gmv,
    purchase_value
FROM gold.v_gmv_current
WHERE purchase_id = 64;
```

**Esperado na gold:**
- 1 linha apenas
- transaction_date = '2023-03-12' (última ingestão)
- release_date = '2023-02-10'
- is_valid_for_gmv = true
- purchase_value = 1160.82

---

## Checklist de Validação

Execute cada query e marque:

- [ ] Query 1: Total purchases = 30
- [ ] Query 2: Status counts corretos (18/7/5)
- [ ] Query 3: GMV válido = 18, inválido = 12
- [ ] Query 4: GMV total = 23561.90
- [ ] Query 5: GMV por subsidiary correto
- [ ] Query 6: 18 linhas com valores corretos
- [ ] Query 7: Todas as linhas com 'OK'
- [ ] Cenário A: Purchase 72 correta
- [ ] Cenário B: Purchase 78 correta
- [ ] Cenário C: Purchase 69 correta
- [ ] Cenário D: Purchase 64 correta (1 linha, última versão)

---

## Como Executar

```bash
# 1. Garantir que dbt está atualizado
cd dbt_project && dbt run

# 2. Abrir DuckDB
duckdb ../warehouse/teachable.duckdb

# 3. Executar as queries acima uma a uma
```

Se todos os valores baterem, a gold está **confiável para o consumidor**.
