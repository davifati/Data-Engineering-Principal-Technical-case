
  
  create view "teachable"."silver"."stg_purchase__dbt_tmp" as (
    

/*
    Staging: Purchase

    Deduplicação CDC: mantém apenas a última versão de cada purchase_id
    baseado em transaction_datetime.

    Fonte: raw.purchase (eventos CDC)
    Grain: 1 row per purchase_id
*/

with source as (
    select * from "teachable"."raw"."purchase"
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
  );
