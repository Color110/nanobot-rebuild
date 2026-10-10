---
name: sql-query
description: 当任务核心是编写、解释或优化 SQL/DDL，设计关系型数据库 Schema，分析执行计划，或进行存储过程/SQL 方言迁移时使用。SQL 专项性能问题仍优先本 Skill；若主要目标是非 SQL 的数据清洗/ETL，使用
  data-transform；若是普通业务代码生成，使用 code-generation。
version: 1.1.0
tags:
- database
- sql
- query
- ddl
- schema
- execution-plan
- query-tuning
- join
- cte
- migration
always: false
enabled: true
---

# SQL Query

这个 Skill 用于“编写、优化和解释 SQL 查询及数据库设计”的场景。

## Procedure

当用户提出 SQL 相关需求时：

1. 确认用户的数据库类型（MySQL、PostgreSQL、SQLite 等），不同方言语法有差异。
2. 如果用户提供了表结构，使用 `read_text_file` 读取 DDL 或 schema 文件；如果没有，请用户提供表名和字段信息。
3. 根据需求编写 SQL 查询，包含清晰的注释说明每段逻辑。
4. 对于复杂查询，先给出逻辑分解（CTE 或子查询），再组合为完整语句。
5. 如果用户要求优化，分析可能的性能瓶颈（全表扫描、缺少索引、N+1 问题）并给出优化建议。
6. 提供查询结果的预期格式说明。

## Error handling

如果用户未提供表结构，不要猜测字段名和类型，应明确询问。

如果 SQL 语法因数据库类型不同而存在歧义，应列出差异并让用户确认。
