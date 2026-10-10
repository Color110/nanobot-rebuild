---
name: data-transform
description: 当核心目标是对数据进行清洗、格式转换、字段映射、合并、聚合、脱敏、ETL 或构建数据处理管道时使用，输出重点是转换后的数据或数据流程。若只是文件数值计算使用 file-math；SQL 查询或数据库 Schema 使用
  sql-query；日志故障诊断使用 log-analysis。
version: 1.1.0
tags:
- data
- transform
- etl
- clean
- convert
- mapping
- merge
- aggregate
- pipeline
- schema
- format
always: false
enabled: true
---

# Data Transform

这个 Skill 用于“对数据进行清洗、格式转换和 ETL 处理”的场景。

## Procedure

当用户提出数据处理需求时：

1. 使用 `read_text_file` 读取源数据文件（CSV、JSON、XML 等），确认数据格式、字段和样本。
2. 与用户确认目标格式、转换规则和输出要求。
3. 制定转换方案：字段映射、类型转换、缺失值处理、去重规则、聚合逻辑。
4. 编写转换脚本（Python / pandas / jq 等），包含输入校验和异常处理。
5. 执行转换并验证输出数据的完整性和正确性。
6. 使用 `write_text_file` 将结果写入用户指定路径。

## Error handling

如果源数据文件不存在或格式无法识别，不要猜测数据结构，应向用户说明。

如果数据量过大无法一次性处理，应建议分片处理策略，而非强行加载导致内存溢出。
