{{
    config(
        materialized='view'
    )
}}

with source as (
    select * from {{ source('raw', 'order_transaction_cost_hist') }}
),

deduplicated as (
    select
        purchase_id,
        purchase_partition,
        order_transaction_cost_vat_value,
        order_transaction_cost_installment_value,
        order_transaction_cost_date,
        transaction_datetime,
        transaction_date
    from source
    qualify row_number() over (
        partition by purchase_id
        order by transaction_datetime desc
    ) = 1
)

select * from deduplicated
