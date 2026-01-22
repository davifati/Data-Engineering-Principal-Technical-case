
  
  create view "teachable"."silver"."int_purchase_enriched__dbt_tmp" as (
    

/*
    Intermediate: Purchase Enriched

    Consolida as stagings em uma única visão desnormalizada,
    preparando os dados para a camada gold.

    Joins:
    - stg_purchase (base)
    - stg_product_item (via prod_item_id) -> purchase_value para GMV
    - stg_purchase_extra_info (via purchase_id) -> subsidiary para agrupamento

    Grain: 1 row per purchase_id

    Esta tabela entrega todos os campos necessários para a gold
    calcular GMV por subsidiary sem necessidade de joins adicionais.

    Requisito atendido: "Simple to query by non-expert SQL users (no joins needed)"
*/

with purchase as (
    select * from "teachable"."silver"."stg_purchase"
),

product_item as (
    select * from "teachable"."silver"."stg_product_item"
),

purchase_extra_info as (
    select * from "teachable"."silver"."stg_purchase_extra_info"
),

enriched as (
    select
        -- Identificadores
        p.purchase_id,
        p.buyer_id,
        p.producer_id,
        pi.product_id,

        -- Dimensões temporais
        p.transaction_date,
        p.order_date,
        p.release_date,

        -- Dimensões de negócio
        pei.subsidiary,
        p.purchase_status,

        -- Métricas
        pi.purchase_value,
        pi.item_quantity,

        -- Campos técnicos (para auditoria/debug)
        p.prod_item_id,
        greatest(
            p.transaction_datetime,
            coalesce(pi.transaction_datetime, p.transaction_datetime),
            coalesce(pei.transaction_datetime, p.transaction_datetime)
        ) as last_updated_at

    from purchase p
    left join product_item pi
        on p.prod_item_id = pi.prod_item_id
    left join purchase_extra_info pei
        on p.purchase_id = pei.purchase_id
)

select * from enriched
  );
