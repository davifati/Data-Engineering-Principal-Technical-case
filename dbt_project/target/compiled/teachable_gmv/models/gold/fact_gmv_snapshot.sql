

with source as (
    select * from "teachable"."silver"."int_purchase_enriched"
),

snapshot as (
    select
        -- Chave primária composta
        purchase_id,
        current_date as snapshot_date,

        -- Partição (transaction_date) - cumpre requisito #7
        transaction_date,

        -- Dimensões temporais
        order_date,
        release_date,

        -- Dimensões de negócio
        subsidiary,
        buyer_id,
        producer_id,
        product_id,
        purchase_status,

        -- Métricas
        purchase_value,
        item_quantity,

        -- Flag para cálculo de GMV - cumpre requisito #1
        -- GMV = apenas transações com pagamento capturado (release_date preenchido)
        -- e não canceladas (status APROVADA)
        (release_date is not null and purchase_status = 'APROVADA') as is_valid_for_gmv,

        -- Auditoria
        last_updated_at

    from source
)

select * from snapshot

where not exists (
    select 1
    from "teachable"."gold"."fact_gmv_snapshot" existing
    where existing.purchase_id = snapshot.purchase_id
      and existing.snapshot_date = current_date
)
