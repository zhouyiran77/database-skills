# 数据库主键冲突检测配置

## 数据库实例

| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode |
|---|---|---|---|---|---:|---|---|---|---|
| v2_huashi | source | 华师 | postgresql | pg-v2-huashi.example.internal | 5432 | teaching_v2 | migration_reader | DB_V2_HUASHI_PASSWORD | require |
| v2_wut | source | 武汉理工 | postgresql | pg-v2-wut.example.internal | 5432 | teaching_v2 | migration_reader | DB_V2_WUT_PASSWORD | require |
| v2_gdei | source | 广东二师 | postgresql | pg-v2-gdei.example.internal | 5432 | teaching_v2 | migration_reader | DB_V2_GDEI_PASSWORD | require |
| v3_main | target | 3.0合并库 | postgresql | pg-v3.example.internal | 5432 | teaching_v3 | migration_reader | DB_V3_MAIN_PASSWORD | require |

## 表比对范围

| scope_id | enabled | source_instances | source_table | target_instance | target_table | primary_key |
|---|---|---|---|---|---|---|
| activity_nodes | true | * | public.activity_nodes | v3_main | teaching.activity_node | id |
| course | true | * | public.course | v3_main | teaching.courses | id |
