{% macro generate_schema_name(custom_schema_name, node) -%}
    {#
        Override default dbt schema naming behavior.

        Default dbt behavior: {target_schema}_{custom_schema} -> main_silver
        Our behavior: just {custom_schema} -> silver

        If no custom schema is specified, use the target schema (main).
    #}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}