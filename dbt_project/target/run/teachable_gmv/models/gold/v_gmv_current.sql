
  
  create view "teachable"."gold"."v_gmv_current__dbt_tmp" as (
    

/*
    View: v_gmv_current

    Simplifica o acesso ao estado atual do GMV, eliminando a necessidade
    de subquery para encontrar o snapshot mais recente.

    Caso de uso: 80% das queries de consumo querem o "estado atual".
    Esta view encapsula esse padrão, reduzindo erro de usuário e
    simplificando queries para analistas.

    Antes (fact_gmv_snapshot):
    ```sql
    SELECT subsidiary, SUM(purchase_value) as gmv
    FROM gold.fact_gmv_snapshot
    WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
      AND is_valid_for_gmv = true
    GROUP BY subsidiary;
    ```

    Depois (v_gmv_current):
    ```sql
    SELECT subsidiary, SUM(purchase_value) as gmv
    FROM gold.v_gmv_current
    WHERE is_valid_for_gmv = true
    GROUP BY subsidiary;
    ```

    Nota: Para queries as-of (estado em data específica), use fact_gmv_snapshot diretamente.
*/

with latest_snapshot as (
    select max(snapshot_date) as max_snapshot_date
    from "teachable"."gold"."fact_gmv_snapshot"
)

select
    f.purchase_id,
    f.snapshot_date,
    f.transaction_date,
    f.order_date,
    f.release_date,
    f.subsidiary,
    f.buyer_id,
    f.producer_id,
    f.product_id,
    f.purchase_status,
    f.purchase_value,
    f.item_quantity,
    f.is_valid_for_gmv,
    f.last_updated_at
from "teachable"."gold"."fact_gmv_snapshot" f
cross join latest_snapshot ls
where f.snapshot_date = ls.max_snapshot_date
  );
