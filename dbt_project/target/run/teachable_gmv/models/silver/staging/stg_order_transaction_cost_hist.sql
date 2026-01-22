
  
  create view "teachable"."silver"."stg_order_transaction_cost_hist__dbt_tmp" as (
    

/*
    Staging: Order Transaction Cost History

    Deduplicação CDC: mantém apenas a última versão de cada purchase_id
    baseado em transaction_datetime.

    Fonte: raw.order_transaction_cost_hist (eventos CDC)
    Grain: 1 row per purchase_id

    Nota: Esta tabela contém custos (VAT, installment) que não são usados
    no cálculo de GMV, mas estão disponíveis para evolução futura
    (ex: reconciliação com Finance).
*/

with source as (
    select * from "teachable"."raw"."order_transaction_cost_hist"
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
  );
