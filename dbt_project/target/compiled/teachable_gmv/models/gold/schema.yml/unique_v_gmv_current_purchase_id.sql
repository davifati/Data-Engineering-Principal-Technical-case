
    
    

select
    purchase_id as unique_field,
    count(*) as n_records

from "teachable"."gold"."v_gmv_current"
where purchase_id is not null
group by purchase_id
having count(*) > 1


