# Gold Layer - Queries de Consumo

Catálogo de queries para a tabela `gold.fact_gmv_snapshot`.

---

## 1. Queries de GMV (Consumidor Final)

### 1.1 GMV Total Atual

```sql
-- GMV total mais recente por subsidiary
SELECT
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(*) as total_transactions
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY subsidiary
ORDER BY gmv DESC;
```

### 1.2 GMV por Período (Mês/Trimestre/Ano)

```sql
-- GMV de Janeiro 2024
SELECT
    subsidiary,
    SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
  AND snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

```sql
-- GMV do Q1 2024
SELECT
    subsidiary,
    SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE transaction_date BETWEEN '2024-01-01' AND '2024-03-31'
  AND snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

### 1.3 GMV Diário (Time Series)

```sql
-- GMV diário dos últimos 30 dias (para gráficos/dashboards)
SELECT
    transaction_date,
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(*) as transactions
FROM gold.fact_gmv_snapshot
WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
  AND snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY transaction_date, subsidiary
ORDER BY transaction_date, subsidiary;
```

### 1.4 GMV por Producer (Top Sellers)

```sql
-- Top 10 producers por GMV no mês atual
SELECT
    producer_id,
    subsidiary,
    SUM(purchase_value) as gmv,
    COUNT(*) as sales_count
FROM gold.fact_gmv_snapshot
WHERE transaction_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY producer_id, subsidiary
ORDER BY gmv DESC
LIMIT 10;
```

---

## 2. As-Of Queries (Visão Histórica)

### 2.1 GMV de Janeiro Visto em 31/Mar

```sql
-- Como era o GMV de Janeiro quando olhamos em 31 de Março?
SELECT
    subsidiary,
    SUM(purchase_value) as gmv_em_marco
FROM gold.fact_gmv_snapshot
WHERE transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
  AND snapshot_date = '2024-03-31'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

### 2.2 Comparação: GMV em Dois Momentos Diferentes

```sql
-- GMV de Janeiro: como era em 31/Jan vs como é hoje
WITH jan_em_jan AS (
    SELECT
        subsidiary,
        SUM(purchase_value) as gmv
    FROM gold.fact_gmv_snapshot
    WHERE transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
      AND snapshot_date = '2024-01-31'
      AND is_valid_for_gmv = true
    GROUP BY subsidiary
),
jan_hoje AS (
    SELECT
        subsidiary,
        SUM(purchase_value) as gmv
    FROM gold.fact_gmv_snapshot
    WHERE transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
      AND snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
      AND is_valid_for_gmv = true
    GROUP BY subsidiary
)
SELECT
    COALESCE(j.subsidiary, h.subsidiary) as subsidiary,
    j.gmv as gmv_visto_em_jan,
    h.gmv as gmv_visto_hoje,
    h.gmv - j.gmv as diferenca,
    ROUND(((h.gmv - j.gmv) / j.gmv) * 100, 2) as variacao_pct
FROM jan_em_jan j
FULL OUTER JOIN jan_hoje h ON j.subsidiary = h.subsidiary
ORDER BY diferenca DESC;
```

### 2.3 Evolução do GMV ao Longo do Tempo

```sql
-- Como o GMV de Janeiro evoluiu ao longo dos meses (late arrivals)?
SELECT
    snapshot_date,
    SUM(purchase_value) as gmv_janeiro
FROM gold.fact_gmv_snapshot
WHERE transaction_date BETWEEN '2024-01-01' AND '2024-01-31'
  AND is_valid_for_gmv = true
  AND snapshot_date IN ('2024-01-31', '2024-02-29', '2024-03-31', '2024-04-30')
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

---

## 3. Queries de Reconciliação e Auditoria

### 3.1 Diff Entre Dois Dias (O Que Mudou?)

```sql
-- Purchases que mudaram de valor entre ontem e hoje
SELECT
    COALESCE(ontem.purchase_id, hoje.purchase_id) as purchase_id,
    ontem.purchase_value as valor_ontem,
    hoje.purchase_value as valor_hoje,
    hoje.purchase_value - ontem.purchase_value as diferenca,
    ontem.purchase_status as status_ontem,
    hoje.purchase_status as status_hoje,
    ontem.release_date as release_ontem,
    hoje.release_date as release_hoje
FROM gold.fact_gmv_snapshot ontem
FULL OUTER JOIN gold.fact_gmv_snapshot hoje
    ON ontem.purchase_id = hoje.purchase_id
WHERE ontem.snapshot_date = CURRENT_DATE - 1
  AND hoje.snapshot_date = CURRENT_DATE
  AND (
    ontem.purchase_value != hoje.purchase_value
    OR ontem.purchase_status != hoje.purchase_status
    OR ontem.release_date IS DISTINCT FROM hoje.release_date
    OR ontem.purchase_id IS NULL  -- novo
    OR hoje.purchase_id IS NULL   -- removido (raro)
  )
ORDER BY ABS(COALESCE(hoje.purchase_value, 0) - COALESCE(ontem.purchase_value, 0)) DESC;
```

### 3.2 Novas Purchases no Snapshot de Hoje

```sql
-- Purchases que apareceram pela primeira vez hoje
SELECT
    hoje.purchase_id,
    hoje.transaction_date,
    hoje.purchase_value,
    hoje.subsidiary,
    hoje.is_valid_for_gmv
FROM gold.fact_gmv_snapshot hoje
LEFT JOIN gold.fact_gmv_snapshot ontem
    ON hoje.purchase_id = ontem.purchase_id
    AND ontem.snapshot_date = CURRENT_DATE - 1
WHERE hoje.snapshot_date = CURRENT_DATE
  AND ontem.purchase_id IS NULL
ORDER BY hoje.purchase_value DESC;
```

### 3.3 Purchases que Viraram GMV Válido (Late Arrivals)

```sql
-- Purchases que não eram válidas ontem mas são hoje
-- (provavelmente late arrival do release_date)
SELECT
    hoje.purchase_id,
    hoje.transaction_date,
    hoje.release_date,
    hoje.purchase_value,
    hoje.subsidiary
FROM gold.fact_gmv_snapshot hoje
JOIN gold.fact_gmv_snapshot ontem
    ON hoje.purchase_id = ontem.purchase_id
WHERE hoje.snapshot_date = CURRENT_DATE
  AND ontem.snapshot_date = CURRENT_DATE - 1
  AND hoje.is_valid_for_gmv = true
  AND ontem.is_valid_for_gmv = false
ORDER BY hoje.purchase_value DESC;
```

### 3.4 Histórico Completo de Uma Purchase

```sql
-- Evolução de uma purchase específica ao longo do tempo
SELECT
    snapshot_date,
    purchase_status,
    release_date,
    purchase_value,
    is_valid_for_gmv
FROM gold.fact_gmv_snapshot
WHERE purchase_id = 12345  -- substituir pelo ID desejado
ORDER BY snapshot_date;
```

### 3.5 Variação Diária do GMV

```sql
-- GMV total por snapshot_date (para ver estabilidade/variação)
SELECT
    snapshot_date,
    SUM(purchase_value) as gmv_total,
    SUM(purchase_value) - LAG(SUM(purchase_value)) OVER (ORDER BY snapshot_date) as variacao,
    COUNT(*) as total_purchases_validas
FROM gold.fact_gmv_snapshot
WHERE is_valid_for_gmv = true
  AND snapshot_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

---

## 4. Queries Operacionais (Data Engineering)

### 4.1 Verificar Snapshots Existentes

```sql
-- Lista de snapshots disponíveis
SELECT
    snapshot_date,
    COUNT(*) as total_rows,
    COUNT(DISTINCT purchase_id) as unique_purchases,
    SUM(CASE WHEN is_valid_for_gmv THEN 1 ELSE 0 END) as gmv_valid_count,
    SUM(CASE WHEN is_valid_for_gmv THEN purchase_value ELSE 0 END) as gmv_total
FROM gold.fact_gmv_snapshot
GROUP BY snapshot_date
ORDER BY snapshot_date DESC
LIMIT 30;
```

### 4.2 Verificar Integridade do Snapshot

```sql
-- Validar que não há duplicatas no grain (purchase_id, snapshot_date)
SELECT
    purchase_id,
    snapshot_date,
    COUNT(*) as duplicates
FROM gold.fact_gmv_snapshot
GROUP BY purchase_id, snapshot_date
HAVING COUNT(*) > 1;
```

### 4.3 Verificar Cobertura de Datas

```sql
-- Verificar gaps nos snapshots (dias sem execução)
WITH date_range AS (
    SELECT generate_series(
        (SELECT MIN(snapshot_date) FROM gold.fact_gmv_snapshot),
        (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot),
        '1 day'::interval
    )::date as expected_date
),
actual_dates AS (
    SELECT DISTINCT snapshot_date FROM gold.fact_gmv_snapshot
)
SELECT expected_date as missing_snapshot_date
FROM date_range
LEFT JOIN actual_dates ON expected_date = snapshot_date
WHERE snapshot_date IS NULL
ORDER BY expected_date;
```

---

## 5. Backfill Queries

### 5.1 Gerar Snapshot Manual para Data Específica

```sql
-- Backfill: gerar snapshot para uma data específica
-- USAR COM CUIDADO - apenas se houve falha no pipeline
INSERT INTO gold.fact_gmv_snapshot
SELECT
    purchase_id,
    '2024-01-15'::date as snapshot_date,  -- data do backfill
    transaction_date,
    order_date,
    release_date,
    subsidiary,
    buyer_id,
    producer_id,
    product_id,
    purchase_status,
    purchase_value,
    item_quantity,
    (release_date IS NOT NULL AND purchase_status = 'APROVADA') as is_valid_for_gmv,
    last_updated_at
FROM silver.int_purchase_enriched
WHERE NOT EXISTS (
    SELECT 1 FROM gold.fact_gmv_snapshot existing
    WHERE existing.purchase_id = int_purchase_enriched.purchase_id
      AND existing.snapshot_date = '2024-01-15'
);
```

### 5.2 Backfill de Range de Datas

```sql
-- Backfill para múltiplas datas (usar com geração de datas)
-- NOTA: Isso gera o estado ATUAL para datas passadas
-- Só faz sentido se a raw/silver tem dados históricos corretos

WITH dates_to_backfill AS (
    SELECT generate_series(
        '2024-01-01'::date,
        '2024-01-10'::date,
        '1 day'::interval
    )::date as backfill_date
)
INSERT INTO gold.fact_gmv_snapshot
SELECT
    p.purchase_id,
    d.backfill_date as snapshot_date,
    p.transaction_date,
    p.order_date,
    p.release_date,
    p.subsidiary,
    p.buyer_id,
    p.producer_id,
    p.product_id,
    p.purchase_status,
    p.purchase_value,
    p.item_quantity,
    (p.release_date IS NOT NULL AND p.purchase_status = 'APROVADA') as is_valid_for_gmv,
    p.last_updated_at
FROM silver.int_purchase_enriched p
CROSS JOIN dates_to_backfill d
WHERE NOT EXISTS (
    SELECT 1 FROM gold.fact_gmv_snapshot existing
    WHERE existing.purchase_id = p.purchase_id
      AND existing.snapshot_date = d.backfill_date
);
```

### 5.3 Verificar Resultado do Backfill

```sql
-- Verificar se backfill foi bem sucedido
SELECT
    snapshot_date,
    COUNT(*) as rows_inserted,
    SUM(CASE WHEN is_valid_for_gmv THEN purchase_value ELSE 0 END) as gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date BETWEEN '2024-01-01' AND '2024-01-10'
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

---

## 6. Queries para Dashboards (BI)

### 6.1 KPIs Executivos

```sql
-- Dashboard executivo: métricas principais
WITH current_snapshot AS (
    SELECT MAX(snapshot_date) as max_date FROM gold.fact_gmv_snapshot
)
SELECT
    -- GMV Total
    SUM(CASE WHEN is_valid_for_gmv THEN purchase_value ELSE 0 END) as gmv_total,

    -- GMV por Período
    SUM(CASE WHEN is_valid_for_gmv
             AND transaction_date >= DATE_TRUNC('month', CURRENT_DATE)
        THEN purchase_value ELSE 0 END) as gmv_mtd,

    SUM(CASE WHEN is_valid_for_gmv
             AND transaction_date >= DATE_TRUNC('year', CURRENT_DATE)
        THEN purchase_value ELSE 0 END) as gmv_ytd,

    -- Contagens
    COUNT(DISTINCT CASE WHEN is_valid_for_gmv THEN purchase_id END) as valid_transactions,
    COUNT(DISTINCT CASE WHEN is_valid_for_gmv THEN producer_id END) as active_producers,
    COUNT(DISTINCT CASE WHEN is_valid_for_gmv THEN buyer_id END) as active_buyers,

    -- Ticket Médio
    AVG(CASE WHEN is_valid_for_gmv THEN purchase_value END) as avg_ticket

FROM gold.fact_gmv_snapshot, current_snapshot
WHERE snapshot_date = current_snapshot.max_date;
```

### 6.2 GMV por Subsidiary (Gráfico de Pizza/Barras)

```sql
-- Distribuição de GMV por subsidiary
SELECT
    subsidiary,
    SUM(purchase_value) as gmv,
    ROUND(SUM(purchase_value) * 100.0 / SUM(SUM(purchase_value)) OVER (), 2) as pct_total
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
GROUP BY subsidiary
ORDER BY gmv DESC;
```

### 6.3 Trend Mensal

```sql
-- GMV mensal (últimos 12 meses)
SELECT
    DATE_TRUNC('month', transaction_date) as month,
    subsidiary,
    SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
  AND transaction_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY DATE_TRUNC('month', transaction_date), subsidiary
ORDER BY month, subsidiary;
```

---

## 7. Queries de Data Quality

### 7.1 Purchases Sem Subsidiary

```sql
-- Verificar dados faltantes
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN subsidiary IS NULL THEN 1 END) as sem_subsidiary,
    COUNT(CASE WHEN purchase_value IS NULL THEN 1 END) as sem_valor,
    COUNT(CASE WHEN transaction_date IS NULL THEN 1 END) as sem_data
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot);
```

### 7.2 Valores Suspeitos

```sql
-- Purchases com valores extremos (possíveis erros)
SELECT
    purchase_id,
    purchase_value,
    subsidiary,
    transaction_date
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
  AND is_valid_for_gmv = true
  AND (
    purchase_value > 100000  -- valor muito alto
    OR purchase_value <= 0   -- valor zero ou negativo
  )
ORDER BY purchase_value DESC;
```

### 7.3 Consistência do is_valid_for_gmv

```sql
-- Verificar se a flag está correta
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN is_valid_for_gmv = true
               AND (release_date IS NULL OR purchase_status != 'APROVADA')
          THEN 1 END) as flag_incorreta_true,
    COUNT(CASE WHEN is_valid_for_gmv = false
               AND release_date IS NOT NULL
               AND purchase_status = 'APROVADA'
          THEN 1 END) as flag_incorreta_false
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot);
```

---

## Resumo: Queries Mais Usadas

| Caso de Uso | Query | Seção |
|-------------|-------|-------|
| GMV atual por subsidiary | 1.1 | Consumidor Final |
| GMV de um mês específico | 1.2 | Consumidor Final |
| Comparar GMV em dois momentos | 2.2 | As-Of |
| O que mudou entre ontem e hoje | 3.1 | Reconciliação |
| Late arrivals (viraram GMV válido) | 3.3 | Reconciliação |
| Histórico de uma purchase | 3.4 | Auditoria |
| Verificar snapshots existentes | 4.1 | Operacional |
| Backfill de data específica | 5.1 | Backfill |
| KPIs executivos | 6.1 | Dashboard |
