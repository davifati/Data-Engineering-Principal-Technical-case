
  
  create view "teachable"."silver"."stg_purchase_extra_info__dbt_tmp" as (
    

/*
    Staging: Purchase Extra Info

    Deduplicação CDC: mantém apenas a última versão de cada purchase_id
    baseado em transaction_datetime.

    Fonte: raw.purchase_extra_info (eventos CDC)
    Grain: 1 row per purchase_id

    Nota: subsidiary é a dimensão chave para agrupamento de GMV
*/

with source as (
    select * from "teachable"."raw"."purchase_extra_info"
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
  );
