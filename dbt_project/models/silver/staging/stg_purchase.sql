{{
    config(
        materialized='view'
    )
}}

with source as (
    select * from {{ source('raw', 'purchase') }}
),

deduplicated as (
    select
        purchase_id,
        buyer_id,
        prod_item_id,
        order_date,
        release_date,
        producer_id,
        purchase_partition,
        prod_item_partition,
        purchase_total_value,
        purchase_status,
        transaction_datetime,
        transaction_date
    from source
    qualify row_number() over (
        partition by purchase_id
        order by transaction_datetime desc
    ) = 1
)

select * from deduplicated
