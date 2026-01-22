



with source as (
    select * from "teachable"."raw"."product_item"
),

deduplicated as (
    select
        prod_item_id,
        prod_item_partition,
        product_id,
        item_quantity,
        purchase_value,
        transaction_datetime,
        transaction_date
    from source
    qualify row_number() over (
        partition by prod_item_id
        order by transaction_datetime desc
    ) = 1
)

select * from deduplicated