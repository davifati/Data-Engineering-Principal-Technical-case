
    
    

select
    purchase_id || '-' || snapshot_date as unique_field,
    count(*) as n_records

from "teachable"."gold"."fact_gmv_snapshot"
where purchase_id || '-' || snapshot_date is not null
group by purchase_id || '-' || snapshot_date
having count(*) > 1


