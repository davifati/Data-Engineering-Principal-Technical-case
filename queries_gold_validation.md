# Validação da Gold Layer - Testes Baseados nos Dados Raw

Este documento contém queries de validação para testar a gold layer (`fact_gmv_snapshot`) contra os requisitos do technical case, usando os dados mockados em `data/raw/`.

**Importante:** Execute `dbt run` antes de rodar estas queries para garantir que a gold está atualizada.

---

## 0. Setup: Verificar Estado Atual

### 0.1 Verificar que a gold foi populada

```sql
-- Deve retornar 1 linha com contagem > 0
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_purchases,
    COUNT(DISTINCT snapshot_date) as snapshots,
    MIN(snapshot_date) as first_snapshot,
    MAX(snapshot_date) as last_snapshot
FROM gold.fact_gmv_snapshot;
```

**Esperado:**
- total_rows = número de purchases únicas (após dedup)
- snapshots = 1 (se rodou uma vez)

### 0.2 Verificar grain (sem duplicatas)

```sql
-- Deve retornar 0 linhas (nenhuma duplicata)
SELECT purchase_id, snapshot_date, COUNT(*) as cnt
FROM gold.fact_gmv_snapshot
GROUP BY purchase_id, snapshot_date
HAVING COUNT(*) > 1;
```

**Esperado:** 0 linhas

---

## 1. Requisito #1: GMV só de Released Transactions

### 1.1 Verificar flag is_valid_for_gmv

```sql
-- Verificar consistência da flag
SELECT
    purchase_id,
    purchase_status,
    release_date,
    is_valid_for_gmv,
    CASE
        WHEN release_date IS NOT NULL AND purchase_status = 'APROVADA' THEN true
        ELSE false
    END as expected_flag,
    CASE
        WHEN is_valid_for_gmv = (release_date IS NOT NULL AND purchase_status = 'APROVADA')
        THEN 'OK'
        ELSE 'ERRO'
    END as validation
FROM gold.v_gmv_current
ORDER BY validation DESC, purchase_id;
```

**Esperado:** Todas as linhas com validation = 'OK'

### 1.2 Listar purchases válidas para GMV

```sql
-- Purchases que entram no GMV (APROVADA + release_date preenchido)
SELECT
    purchase_id,
    subsidiary,
    purchase_value,
    release_date,
    purchase_status
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
ORDER BY purchase_id;
```

**Esperado (purchases com APROVADA + release_date):**
- 50: NÃO (CANCELADA)
- 51: NÃO (CANCELADA)
- 52: SIM
- 53: SIM
- 54: NÃO (INICIADA)
- 55: SIM
- 56: SIM
- 57: NÃO (INICIADA)
- 58: SIM
- 59: NÃO (INICIADA)
- 60: SIM
- 61: SIM
- 62: SIM
- 63: NÃO (INICIADA)
- 64: SIM
- 65: NÃO (INICIADA)
- 66: SIM
- 67: SIM
- 68: NÃO (INICIADA)
- 69: NÃO (CANCELADA)
- 70: SIM
- 71: SIM
- 72: SIM
- 73: SIM
- 74: SIM
- 75: NÃO (CANCELADA)
- 76: NÃO (CANCELADA)
- 77: SIM
- 78: SIM
- 79: NÃO (INICIADA)

### 1.3 Validar que CANCELADA/INICIADA não entram no GMV

```sql
-- Nenhuma dessas deve ter is_valid_for_gmv = true
SELECT purchase_id, purchase_status, is_valid_for_gmv
FROM gold.v_gmv_current
WHERE purchase_status IN ('CANCELADA', 'INICIADA')
  AND is_valid_for_gmv = true;
```

**Esperado:** 0 linhas

### 1.4 Calcular GMV Total

```sql
-- GMV total (apenas transações válidas)
SELECT
    subsidiary,
    COUNT(*) as transactions,
    SUM(purchase_value) as gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary
ORDER BY gmv DESC;
```

**Esperado:** Calcular manualmente e comparar (ver seção de valores esperados abaixo)

---

## 2. Requisito #2: Late Arrivals

### 2.1 Verificar Purchase 72 (INICIADA → APROVADA)

```sql
-- Purchase 72: Late arrival - iniciou INICIADA, depois virou APROVADA
-- Raw tem 2 versões:
--   2023-01-17: INICIADA, release_date=NULL
--   2023-01-24: APROVADA, release_date=2023-01-20

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
- purchase_value = 1812.84 (valor do prod_item_id=27)

### 2.2 Verificar Purchase 78 (Late arrival de aprovação)

```sql
-- Purchase 78: Late arrival
-- Raw tem 2 versões:
--   2023-02-18: INICIADA, release_date=NULL
--   2023-03-07: APROVADA, release_date=2023-02-24

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
- purchase_value = 2258.94 (valor do prod_item_id=33)

### 2.3 Verificar Purchase 69 (INICIADA → CANCELADA)

```sql
-- Purchase 69: Nunca teve release_date
-- Raw tem 2 versões:
--   2023-01-17: INICIADA
--   2023-01-26: CANCELADA

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

## 3. Requisito #3: Imutabilidade (Preserva Passado)

### 3.1 Verificar que snapshot_date existe

```sql
-- Cada registro deve ter snapshot_date
SELECT COUNT(*) as total, COUNT(snapshot_date) as with_snapshot
FROM gold.fact_gmv_snapshot;
```

**Esperado:** total = with_snapshot (todos têm snapshot_date)

### 3.2 Verificar que dados são append-only

```sql
-- Verificar distribuição por snapshot_date
-- Se rodar dbt run múltiplas vezes no mesmo dia, deve ter 1 snapshot
-- Se rodar em dias diferentes, deve ter múltiplos snapshots
SELECT
    snapshot_date,
    COUNT(*) as rows,
    SUM(CASE WHEN is_valid_for_gmv THEN purchase_value ELSE 0 END) as gmv
FROM gold.fact_gmv_snapshot
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

**Esperado:** Cada snapshot_date tem o mesmo número de purchases

---

## 4. Requisito #4: As-Of Queries

**Nota:** Para testar as-of queries corretamente, precisaríamos de múltiplos snapshots gerados em datas diferentes. Com um único snapshot, podemos apenas verificar a estrutura.

### 4.1 Estrutura para As-Of

```sql
-- Verificar que a query as-of funciona sintaticamente
SELECT
    subsidiary,
    SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND transaction_date BETWEEN '2023-01-01' AND '2023-01-31'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

**Esperado:** Query executa sem erro, retorna GMV de Janeiro

### 4.2 GMV de Janeiro

```sql
-- GMV de transações de Janeiro (transaction_date em Janeiro)
SELECT
    subsidiary,
    COUNT(*) as transactions,
    SUM(purchase_value) as gmv
FROM gold.v_gmv_current
WHERE transaction_date BETWEEN '2023-01-01' AND '2023-01-31'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

### 4.3 GMV de Fevereiro

```sql
-- GMV de transações de Fevereiro
SELECT
    subsidiary,
    COUNT(*) as transactions,
    SUM(purchase_value) as gmv
FROM gold.v_gmv_current
WHERE transaction_date BETWEEN '2023-02-01' AND '2023-02-28'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

---

## 5. Requisito #5: Current/Historical/Lineage

### 5.1 Current Records (via view)

```sql
-- Usando a view simplificada
SELECT COUNT(*) as current_records
FROM gold.v_gmv_current;
```

### 5.2 Histórico de uma Purchase (Purchase 64 - múltiplas versões)

```sql
-- Purchase 64 tem 4 versões no raw
-- Verificar que apenas 1 aparece no snapshot (a mais recente)
SELECT
    purchase_id,
    snapshot_date,
    transaction_date,
    release_date,
    purchase_status,
    subsidiary,
    purchase_value
FROM gold.fact_gmv_snapshot
WHERE purchase_id = 64
ORDER BY snapshot_date;
```

**Esperado:**
- 1 linha por snapshot_date
- release_date = '2023-02-10' (última versão)
- transaction_date = '2023-03-12' (última ingestão)

### 5.3 Verificar Dedup correto (última versão por transaction_datetime)

```sql
-- Comparar raw vs gold para purchase 64
-- Raw tem 4 versões, gold deve ter 1 (por snapshot)

-- Versões no raw:
SELECT
    purchase_id,
    transaction_datetime,
    transaction_date,
    release_date,
    purchase_status
FROM raw.purchase
WHERE purchase_id = 64
ORDER BY transaction_datetime;
```

---

## 6. Requisito #6: Simples de Consultar (No Joins)

### 6.1 Query de GMV sem joins

```sql
-- Query completa de GMV sem nenhum JOIN
SELECT
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(*) as transactions,
    AVG(purchase_value) as avg_ticket
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary
ORDER BY gmv DESC;
```

**Esperado:** Query funciona, retorna dados agregados

### 6.2 Query detalhada sem joins

```sql
-- Detalhes de uma transação sem JOIN
SELECT
    purchase_id,
    order_date,
    release_date,
    subsidiary,
    purchase_value,
    buyer_id,
    producer_id
FROM gold.v_gmv_current
WHERE purchase_id = 55;
```

**Esperado:** Todos os campos preenchidos (desnormalizado)

---

## 7. Requisito #7: Particionado por transaction_date

### 7.1 Verificar distribuição por transaction_date

```sql
-- Distribuição de registros por transaction_date
SELECT
    transaction_date,
    COUNT(*) as records,
    SUM(CASE WHEN is_valid_for_gmv THEN purchase_value ELSE 0 END) as gmv
FROM gold.v_gmv_current
GROUP BY transaction_date
ORDER BY transaction_date;
```

**Esperado:** Registros distribuídos por data de ingestão

### 7.2 Verificar que transaction_date está preenchido

```sql
-- Nenhum registro sem transaction_date
SELECT COUNT(*) as sem_transaction_date
FROM gold.v_gmv_current
WHERE transaction_date IS NULL;
```

**Esperado:** 0

---

## 8. Requisito #8: D-1 Batches

### 8.1 Verificar snapshot_date

```sql
-- snapshot_date deve ser a data do build
SELECT DISTINCT snapshot_date
FROM gold.fact_gmv_snapshot;
```

**Esperado:** Data de hoje (quando rodou dbt run)

---

## 9. Requisito #9: Reprocessing Não Reescreve

**Nota:** Para testar completamente, seria necessário rodar o pipeline em dias diferentes e verificar que snapshots antigos permanecem inalterados.

### 9.1 Verificar append-only

```sql
-- Contar registros por snapshot
-- Se rodar múltiplas vezes no mesmo dia, deve manter o mesmo count
SELECT
    snapshot_date,
    COUNT(*) as records
FROM gold.fact_gmv_snapshot
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

---

## 10. Valores Esperados (Calculados Manualmente)

### 10.1 Mapeamento Purchase → Product Item → Value

Baseado no dedup (última versão por transaction_datetime):

| purchase_id | prod_item_id | purchase_value | status | release_date | is_gmv |
|-------------|--------------|----------------|--------|--------------|--------|
| 50 | 5 | 1750.99 | CANCELADA | NULL | NO |
| 51 | 6 | 1908.82 | CANCELADA | NULL | NO |
| 52 | 7 | 942.73 | APROVADA | 2023-02-16 | YES |
| 53 | 8 | 1122.45 | APROVADA | 2023-02-23 | YES |
| 54 | 9 | 2108.91* | INICIADA | NULL | NO |
| 55 | 10 | 2427.48 | APROVADA | 2023-02-15 | YES |
| 56 | 11 | 1180.13 | APROVADA | 2023-02-28 | YES |
| 57 | 12 | 1715.55 | INICIADA | NULL | NO |
| 58 | 13 | 941.89 | APROVADA | 2023-02-05 | YES |
| 59 | 14 | 1202.37* | INICIADA | NULL | NO |
| 60 | 15 | 2085.88 | APROVADA | 2023-01-31 | YES |
| 61 | 16 | 2016.79 | APROVADA | 2023-02-19 | YES |
| 62 | 17 | 370.89 | APROVADA | 2023-02-08 | YES |
| 63 | 18 | 1972.64 | INICIADA | NULL | NO |
| 64 | 19 | 1160.82 | APROVADA | 2023-02-10 | YES |
| 65 | 20 | 1769.32* | INICIADA | NULL | NO |
| 66 | 21 | 1728.94* | APROVADA | 2023-02-06 | YES |
| 67 | 22 | 103.67* | APROVADA | 2023-02-13 | YES |
| 68 | 23 | 1036.11* | INICIADA | NULL | NO |
| 69 | 24 | 721.43 | CANCELADA | NULL | NO |
| 70 | 25 | 1997.68* | APROVADA | 2023-01-29 | YES |
| 71 | 26 | 438.26 | APROVADA | 2023-02-16 | YES |
| 72 | 27 | 1812.84 | APROVADA | 2023-01-20 | YES |
| 73 | 28 | 401.97 | APROVADA | 2023-02-17 | YES |
| 74 | 29 | 771.24 | APROVADA | 2023-02-08 | YES |
| 75 | 30 | 321.69* | CANCELADA | NULL | NO |
| 76 | 31 | 1756.78 | CANCELADA | NULL | NO |
| 77 | 32 | 1799.30 | APROVADA | 2023-02-22 | YES |
| 78 | 33 | 2258.94 | APROVADA | 2023-02-24 | YES |
| 79 | 34 | 782.24 | INICIADA | NULL | NO |

*Valores que mudaram entre versões CDC (usando última versão)

### 10.2 GMV Esperado por Subsidiary

**Nota:** Precisa mapear subsidiary (última versão de purchase_extra_info) para cada purchase.

```sql
-- Query para calcular GMV esperado
-- Execute após validar os valores individuais acima
SELECT
    subsidiary,
    COUNT(*) as count_gmv,
    SUM(purchase_value) as gmv_total
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary;
```

### 10.3 Contagens Esperadas

| Métrica | Valor Esperado |
|---------|----------------|
| Total purchases (após dedup) | 30 |
| Purchases válidas para GMV | 18 |
| Purchases APROVADA | 18 |
| Purchases CANCELADA | 5 |
| Purchases INICIADA | 7 |

---

## 11. Testes de Data Quality

### 11.1 Purchases sem subsidiary

```sql
SELECT purchase_id, subsidiary
FROM gold.v_gmv_current
WHERE subsidiary IS NULL;
```

**Esperado:** 0 linhas (todas têm subsidiary após join)

### 11.2 Purchases sem purchase_value

```sql
SELECT purchase_id, purchase_value
FROM gold.v_gmv_current
WHERE purchase_value IS NULL;
```

**Esperado:** 0 linhas

### 11.3 Valores negativos ou zero

```sql
SELECT purchase_id, purchase_value
FROM gold.v_gmv_current
WHERE purchase_value <= 0;
```

**Esperado:** 0 linhas

---

## 12. Resumo da Validação

Execute esta query final para um resumo completo:

```sql
SELECT
    'Total purchases' as metric, COUNT(*)::text as value FROM gold.v_gmv_current
UNION ALL
SELECT 'GMV valid', COUNT(*)::text FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
UNION ALL
SELECT 'GMV invalid', COUNT(*)::text FROM gold.v_gmv_current WHERE is_valid_for_gmv = false
UNION ALL
SELECT 'APROVADA', COUNT(*)::text FROM gold.v_gmv_current WHERE purchase_status = 'APROVADA'
UNION ALL
SELECT 'CANCELADA', COUNT(*)::text FROM gold.v_gmv_current WHERE purchase_status = 'CANCELADA'
UNION ALL
SELECT 'INICIADA', COUNT(*)::text FROM gold.v_gmv_current WHERE purchase_status = 'INICIADA'
UNION ALL
SELECT 'GMV Total', ROUND(SUM(purchase_value), 2)::text FROM gold.v_gmv_current WHERE is_valid_for_gmv = true
UNION ALL
SELECT 'Subsidiaries', COUNT(DISTINCT subsidiary)::text FROM gold.v_gmv_current;
```

---

## Checklist de Validação

- [ ] 0.1 Gold populada com dados
- [ ] 0.2 Sem duplicatas no grain
- [ ] 1.1 Flag is_valid_for_gmv consistente
- [ ] 1.3 CANCELADA/INICIADA não no GMV
- [ ] 2.1 Purchase 72 late arrival correto
- [ ] 2.2 Purchase 78 late arrival correto
- [ ] 2.3 Purchase 69 cancelada correto
- [ ] 5.2 Purchase 64 dedup correto (1 linha)
- [ ] 6.1 Query GMV sem joins funciona
- [ ] 7.2 transaction_date preenchido
- [ ] 10.3 Contagens batem com esperado
- [ ] 11.* Data quality OK
