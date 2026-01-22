


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