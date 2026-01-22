
  
  create view "teachable"."silver"."stg_product_item__dbt_tmp" as (
    

/*
    Staging: Product Item

    Deduplicação CDC: mantém apenas a última versão de cada prod_item_id
    baseado em transaction_datetime.

    Fonte: raw.product_item (eventos CDC)
    Grain: 1 row per prod_item_id

    Nota: purchase_value é o campo usado para cálculo de GMV
*/

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
  );
