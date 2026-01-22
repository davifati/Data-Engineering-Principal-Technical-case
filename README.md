# GMV Analytical Layer — Technical Case

Pipeline de dados para GMV diário por subsidiary, com snapshots imutáveis e histórico completo.

---

## Quick Start

```bash
# 1. Setup
cd dbt_project
pip install dbt-duckdb

# 2. Run pipeline
dbt run

# 3. Validate
dbt test
```

---

## O Problema

CDC events chegam atrasados, fora de ordem, e podem ser reprocessados. Como garantir que o GMV reportado ontem não mude amanhã?

**Solução**: Daily snapshots. Cada dia = foto completa. Snapshots anteriores nunca mudam.

---

## Estrutura

```
├── dbt_project/
│   └── models/
│       ├── silver/          # Dedup + Enrich
│       │   ├── staging/     # stg_purchase, stg_product_item, stg_purchase_extra_info
│       │   └── intermediate/# int_purchase_enriched
│       └── gold/            # Consumo
│           ├── fact_gmv_snapshot.sql  # Tabela principal
│           └── v_gmv_current.sql      # View latest snapshot
│
├── scripts/
│   ├── calculate_expected_gmv.py      # Calcula GMV esperado
│   └── validate_requirements.py       # Valida 9 requisitos
│
├── warehouse/
│   └── teachable.duckdb               # Database local
│
└── docs/
    ├── arch.md              # Arquitetura e trade-offs
    ├── ddl.md               # DDL + grain + particionamento
    ├── product.md           # Visão de produto
    └── advanced.md          # Real-time, semantic layer, corrections
```

---

## Queries Essenciais

**GMV atual por subsidiary:**
```sql
SELECT subsidiary, SUM(purchase_value) as gmv
FROM gold.v_gmv_current
WHERE is_valid_for_gmv = true
GROUP BY subsidiary;
```

**GMV de Janeiro (como reportado em 31/Mar):**
```sql
SELECT subsidiary, SUM(purchase_value) as gmv
FROM gold.fact_gmv_snapshot
WHERE snapshot_date = '2023-03-31'
  AND transaction_date BETWEEN '2023-01-01' AND '2023-01-31'
  AND is_valid_for_gmv = true
GROUP BY subsidiary;
```

**Histórico de uma compra:**
```sql
SELECT snapshot_date, purchase_status, release_date, is_valid_for_gmv
FROM gold.fact_gmv_snapshot
WHERE purchase_id = 72
ORDER BY snapshot_date;
```

---

## Números Validados

| Subsidiary | GMV |
|------------|-----|
| Nacional | 10,168.25 |
| Internacional | 13,393.65 |
| **Total** | **23,561.90** |

---

## Requisitos Atendidos

| # | Requisito | Status |
|---|-----------|--------|
| 1 | GMV apenas de transações liberadas | ✓ |
| 2 | Lida com late arrivals | ✓ |
| 3 | Preserva resultados históricos | ✓ |
| 4 | Suporta as-of queries | ✓ |
| 5 | Acesso fácil a current/historical/lineage | ✓ |
| 6 | Simples de consultar (sem joins) | ✓ |
| 7 | Particionado por transaction_date | ✓ |
| 8 | Atualizado em batch D-1 | ✓ |
| 9 | Reprocessamento não reescreve histórico | ✓ |

---

## Decisão Arquitetural

| Opção | Descrição | Decisão |
|-------|-----------|---------|
| A. Bitemporal (SCD2) | valid_from/valid_to + processed_at | ❌ Queries complexas |
| B. Daily Snapshot | Foto completa por dia | ✅ **Escolhido** |
| C. Hybrid (delta) | Só grava mudanças | ❌ Imutabilidade convencional |

**Por que B?** Queries simples (`WHERE snapshot_date = 'YYYY-MM-DD'`), imutabilidade estrutural, late arrivals automáticos.

---

## Documentação

- [`arch.md`](arch.md) — Arquitetura, layers, trade-offs
- [`ddl.md`](ddl.md) — DDL, grain, particionamento, imutabilidade
- [`product.md`](product.md) — Visão de produto, contratos, consumidores
- [`advanced.md`](advanced.md) — Real-time, semantic layer, corrections
- [`architecture_diagram.md`](architecture_diagram.md) — Diagrama visual

---

## Autor

Davi Fati — Principal Data Engineer Technical Case
