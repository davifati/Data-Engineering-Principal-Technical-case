insert into "teachable"."gold"."fact_gmv_snapshot" ("purchase_id", "snapshot_date", "transaction_date", "order_date", "release_date", "subsidiary", "buyer_id", "producer_id", "product_id", "purchase_status", "purchase_value", "item_quantity", "is_valid_for_gmv", "last_updated_at")
    (
        select "purchase_id", "snapshot_date", "transaction_date", "order_date", "release_date", "subsidiary", "buyer_id", "producer_id", "product_id", "purchase_status", "purchase_value", "item_quantity", "is_valid_for_gmv", "last_updated_at"
        from "fact_gmv_snapshot__dbt_tmp20260121185012027108"
    )


  