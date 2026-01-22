{{
    config(
        materialized='incremental',
        unique_key=['purchase_id', 'snapshot_date'],
        incremental_strategy='append'
    )
}}

with source as (
    select * from {{ ref('int_purchase_enriched') }}
),

snapshot as (
    select
        -- Chave primária composta
        purchase_id,
        current_date as snapshot_date,

        -- Partição 
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

        -- Flag para cálculo de GMV
        -- GMV = apenas transações com pagamento capturado (release_date preenchido)
        -- e não canceladas (status APROVADA)
        (release_date is not null and purchase_status = 'APROVADA') as is_valid_for_gmv,

        -- Auditoria
        last_updated_at

    from source
)

select * from snapshot
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} existing
    where existing.purchase_id = snapshot.purchase_id
      and existing.snapshot_date = current_date
)
{% endif %}
