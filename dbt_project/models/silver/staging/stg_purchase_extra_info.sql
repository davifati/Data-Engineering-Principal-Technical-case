{{
    config(
        materialized='view'
    )
}}



with source as (
    select * from {{ source('raw', 'purchase_extra_info') }}
),

deduplicated as (
    select
        purchase_id,
        purchase_partition,
        subsidiary,
        transaction_datetime,
        transaction_date
    from source
    qualify row_number() over (
        partition by purchase_id
        order by transaction_datetime desc
    ) = 1
)

select * from deduplicated
