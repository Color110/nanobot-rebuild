# Skill Retrieval 失败用例审计与优化报告

## 1. 当前基线

- Recall@1: 63.07%
- Recall@3: 86.08%
- Recall@5: 92.90%
- MRR: 0.7528
- 难度分层：easy R@3=91.34%，medium R@3=84.82%，hard R@3=81.42%。

当前输出中共有 49 个 Recall@3 Failure。人工审计结果：
- LABEL_ERROR：6 个
- TAXONOMY_BOUNDARY：16 个
- RETRIEVAL_MISS：27 个

其中 6 个当前 Failure 其实是错误标注；完整 352 条测试集中又发现 3 个未出现在 Failure 列表里的标签冲突，因此共修正 9 条 Ground Truth。

## 2. Ground Truth 修正

| id | 原标注 | 新标注 | 原因 |
|---|---|---|---|
| code_review_005 | code-review | security-audit | SQL 注入是明确安全漏洞专项，security-audit 应优先于通用 code-review。 |
| code_review_008 | code-review | performance-optimize | 核心目标是性能分析/优化，是否直接改代码不改变其专项属性。 |
| code_review_015 | code-review | performance-optimize | 时间复杂度与更优方案属于 performance-optimize 的核心范围。 |
| code_review_018 | code-review | security-audit | 输入校验、权限控制、数据脱敏属于安全专项审计。 |
| code_review_019 | code-review | performance-optimize | 空间复杂度与 OOM 风险属于性能/资源专项。 |
| bug_fix_014 | bug-fix | performance-optimize | 与 performance-optimize 中的内存持续增长/泄漏样本语义近乎重复；按“性能/资源指标优先专项 Skill”统一到 performance-optimize。 |
| bug_fix_021 | bug-fix | performance-optimize | OOM + heap dump + 泄漏路径是典型内存/资源性能诊断，统一到 performance-optimize。 |
| file_summary_012 | file-summary | log-analysis | 目标是从运行日志梳理关键事件和时间线，log-analysis 的职责更精确。 |
| file_summary_018 | file-summary | knowledge-compare | 多个方案的优劣分析属于横向比较/取舍，knowledge-compare 优先于“来源是文件”这一信号。 |

## 3. 49 个 Recall@3 Failure 审计

| id | 原 expected | Top1 | 分类 | 新 expected | 处理建议 |
|---|---|---|---|---|---|
| code_review_002 | code-review | bug-fix | TAXONOMY_BOUNDARY | code-review | 保留 code-review。用户只要求检查且明确不修改；与 bug-fix 的边界应由“是否存在已知故障/是否要求修复”区分。 |
| knowledge_qa_002 | knowledge-qa | code-review | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。已有资料 + 单一机制问答 + 明确不比较，标注清晰；应增强 knowledge-qa 的问答/解释路由词。 |
| code_review_003 | code-review | code-refactor | TAXONOMY_BOUNDARY | code-review | 保留 code-review。询问命名和结构是否合理但未要求修改；code-refactor 应要求明确重构/改写动作。 |
| code_review_005 | code-review | sql-query | LABEL_ERROR | security-audit | 改为 security-audit。SQL 注入属于明确的安全漏洞专项，且数据集中已有 security-audit 的同类样本。 |
| code_review_007 | code-review | bug-fix | RETRIEVAL_MISS | code-review | 保留 code-review。是在审查异常处理设计是否完善，没有已经发生的异常或修复诉求。 |
| code_review_008 | code-review | performance-optimize | LABEL_ERROR | performance-optimize | 改为 performance-optimize。核心意图是专项性能分析/优化，即使用户要求先给建议不直接改。 |
| code_review_009 | code-review | bug-fix | TAXONOMY_BOUNDARY | code-review | 保留 code-review。是在评价依赖关系是否合理，没有要求解耦或重构；需强化 review/refactor 的动作边界。 |
| code_review_011 | code-review | bug-fix | RETRIEVAL_MISS | code-review | 保留 code-review。检查错误处理覆盖边界，不是已发生故障的修复。 |
| code_review_012 | code-review | bug-fix | TAXONOMY_BOUNDARY | code-review | 保留 code-review。检查 SRP 是否符合属于评审；若用户要求拆分类才进入 code-refactor。 |
| code_review_013 | code-review | performance-optimize | TAXONOMY_BOUNDARY | code-review | 保留 code-review。这里是潜在资源生命周期风险审查，并无已观测性能退化或内存指标；与 performance-optimize 属边界样本。 |
| code_review_015 | code-review | performance-optimize | LABEL_ERROR | performance-optimize | 改为 performance-optimize。时间复杂度和更优方案属于专项性能/算法效率问题。 |
| code_review_016 | code-review | bug-fix | TAXONOMY_BOUNDARY | code-review | 保留 code-review。用户要求审查耦合问题而不是直接拆分系统；与 code-refactor 是合理 Hard Negative。 |
| code_review_017 | code-review | performance-optimize | TAXONOMY_BOUNDARY | code-review | 保留 code-review。核心是并发正确性/线程安全审查，没有已知故障或性能指标诉求。 |
| code_review_018 | code-review | bug-fix | LABEL_ERROR | security-audit | 改为 security-audit。输入校验、权限控制、数据脱敏明确属于安全专项审计。 |
| code_review_019 | code-review | performance-optimize | LABEL_ERROR | performance-optimize | 改为 performance-optimize。空间复杂度和大规模数据下 OOM 风险属于资源/性能专项。 |
| code_review_020 | code-review | data-transform | TAXONOMY_BOUNDARY | code-review | 保留 code-review。询问分布式事务实现是否可能不一致，是潜在正确性审查；若已有数据不一致现象并要求修复才是 bug-fix。 |
| file_summary_008 | file-summary | log-analysis | RETRIEVAL_MISS | file-summary | 保留 file-summary。目标是从会议纪要抽取决议/待办，不是运行日志分析。 |
| file_summary_009 | file-summary | performance-optimize | RETRIEVAL_MISS | file-summary | 保留 file-summary。目标是总结现有技术文档中的设计决策，不是生成新文档。 |
| file_summary_011 | file-summary | api-integration | RETRIEVAL_MISS | file-summary | 保留 file-summary。目标是从现有需求文档提取功能点，不是实现功能或生成文档。 |
| file_summary_018 | file-summary | performance-optimize | LABEL_ERROR | knowledge-compare | 改为 knowledge-compare。多方案 + 优劣属于横向比较/取舍，来源是文件不应覆盖任务主意图。 |
| file_summary_019 | file-summary | data-transform | RETRIEVAL_MISS | file-summary | 保留 file-summary。提炼报告中已经存在的数据结论/趋势，不是做数据转换。 |
| file_summary_021 | file-summary | doc-generation | TAXONOMY_BOUNDARY | file-summary | 保留 file-summary。是从现有代码文档抽取接口用途，不是生成新的 API 文档；需强化 extract-existing 与 generate-docs 边界。 |
| knowledge_qa_003 | knowledge-qa | log-analysis | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。询问 AgentRunner 启动流程属于单一知识/机制问答。 |
| knowledge_qa_008 | knowledge-qa | api-integration | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。询问接口有哪些方法是事实型知识问答，不是 API 对接。 |
| knowledge_qa_011 | knowledge-qa | performance-optimize | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。根据已有资料解释归一化原因，属于单一概念解释。 |
| knowledge_qa_012 | knowledge-qa | sql-query | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。询问文档中的 upsert 语义，SQL 只是语义词干干扰。 |
| knowledge_qa_015 | knowledge-qa | log-analysis | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。根据文档解释 MRR 指标，属于知识问答。 |
| knowledge_qa_018 | knowledge-qa | sql-query | RETRIEVAL_MISS | knowledge-qa | 保留 knowledge-qa。询问文档对一致性的定义，不是在设计 SQL/数据库。 |
| cg-e01 | code-generation | file-math | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要求用 Python 写新函数；file 只是函数处理对象。 |
| cg-m01 | code-generation | sql-query | TAXONOMY_BOUNDARY | code-generation | 保留 code-generation。核心产物是服务层新方法；动态过滤/分页容易被 sql-query 干扰，但未要求 SQL。 |
| cg-m02 | code-generation | performance-optimize | RETRIEVAL_MISS | code-generation | 保留 code-generation。是从零实现键值存储；缓存/并发安全只是需求属性，不是性能优化或修 Bug。 |
| cg-m04 | code-generation | api-integration | TAXONOMY_BOUNDARY | code-generation | 保留 code-generation。核心是实现新的聊天室后端；WebSocket 是技术手段，不是外部 API 对接。 |
| cg-h01 | code-generation | performance-optimize | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要实现新的分布式爬虫调度器。 |
| cg-h02 | code-generation | log-analysis | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要实现新的 Raft KV 引擎，日志复制中的“日志”不是运行日志分析。 |
| tg-m03 | test-generation | performance-optimize | RETRIEVAL_MISS | test-generation | 保留 test-generation。明确要求压力测试和竞态测试，测试意图强，应强化 test-generation 的压力/并发测试标签。 |
| dg-h03 | doc-generation | code-generation | RETRIEVAL_MISS | doc-generation | 保留 doc-generation。输出目标是新员工培训文档；源码/变更历史只是输入材料。 |
| ai-e02 | api-integration | code-generation | RETRIEVAL_MISS | api-integration | 保留 api-integration。明确“对接短信发送接口”，封装方法只是集成实现的一部分。 |
| cg-e06 | code-generation | code-refactor | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要求写新的批量重命名脚本。 |
| cg-e08 | code-generation | performance-optimize | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要求用 Rust 写新的命令行解析器。 |
| cg-e09 | code-generation | performance-optimize | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要求写新的装饰器；记录执行时间不是性能优化目标。 |
| cg-m06 | code-generation | api-integration | TAXONOMY_BOUNDARY | code-generation | 保留 code-generation。核心产物是新的 API 中间件；权限/限流是需求属性，不是外部 API 对接。 |
| cg-h04 | code-generation | performance-optimize | TAXONOMY_BOUNDARY | code-generation | 保留 code-generation。核心是从零实现 LSM-Tree；“高性能”是实现约束，不是在优化已有系统。 |
| cg-h06 | code-generation | performance-optimize | RETRIEVAL_MISS | code-generation | 保留 code-generation。明确要求实现新的 Kubernetes 调度器。 |
| cr-h04 | code-refactor | api-integration | TAXONOMY_BOUNDARY | code-refactor | 保留 code-refactor。关键词是“抽离”“保持接口兼容”，核心是已有系统结构改造，不是 API 对接或安全审计。 |
| tg-h04 | test-generation | data-transform | RETRIEVAL_MISS | test-generation | 保留 test-generation。明确要求验证一致性哈希节点变更场景，属于测试设计/生成。 |
| tg-h06 | test-generation | data-transform | RETRIEVAL_MISS | test-generation | 保留 test-generation。明确要求生成属性测试验证 CRDT 性质。 |
| dg-m06 | doc-generation | sql-query | TAXONOMY_BOUNDARY | doc-generation | 保留 doc-generation。输出目标是数据字典/ER 图文档；DDL 只是输入材料，不是 SQL 查询任务。 |
| sa-e08 | security-audit | log-analysis | TAXONOMY_BOUNDARY | security-audit | 保留 security-audit。核心目标是检查密钥泄露风险；“日志”只是泄露载体，不是在分析运行日志。 |
| sa-e09 | security-audit | code-refactor | RETRIEVAL_MISS | security-audit | 保留 security-audit。路径遍历是明确的安全漏洞类型。 |

## 4. Skill 优化结论

### api-integration
强化“外部/远程 API 对接、client/adapter/gateway/auth/callback”信号，并排除只是使用 HTTP/WebSocket 的普通新业务代码。

### bug-fix
原边界与 performance-optimize、log-analysis 重叠。已改成“已经发生的功能性故障 + 希望定位并修复”为触发条件，并把资源/性能指标问题让给 performance-optimize。

### code-generation
原 tags 太弱，复杂“实现一个系统/模块”容易被其他领域词吸走。增加 create / implement / new-code / module / service / script 等生成意图信号，并显式排除 SQL/API/test/doc 专项。

### code-refactor
强化“修改已有代码 + 保持外部行为/接口”边界，与 code-review 的“只分析不改”分离。

### code-review
最大问题是范围过宽，原 description 与 instructions 同时覆盖性能、安全、结构等专项领域。已改成“通用、只审不改”为核心，并显式让 bug-fix / performance / security / refactor / generation 等专项 Skill 优先。

### data-transform
以“输出是转换后的数据/数据流程”为核心，和日志分析、SQL、file-math 分离。

### doc-generation
以“输出是新文档”定义边界，和 file-summary 的“只总结/提取现有文件”分离，同时减少 DDL/API 等输入材料造成的误路由。

### file-math
强化“先读文件再计算”的路由边界；同时补上高级计算超出 calculator 能力时不能伪造结果的执行保护。

### file-summary
强化 summary + extract-existing-content，覆盖会议纪要、条款、接口提取；明确跨方案比较交给 knowledge-compare、日志诊断交给 log-analysis。

### knowledge-compare
强化两个及以上概念/方案/来源的 comparison / tradeoff / pros-cons 信号，与 knowledge-qa 和 file-summary 分离。

### knowledge-qa
增加“是什么/为什么/如何工作/文档如何定义”类问答信号，解决 AgentRunner/EmbeddingProvider/MRR 等知识问题被代码类 Skill 吸走的问题。

### log-analysis
明确必须以日志/堆栈/告警/trace 为证据，目标是时间线/链路/根因；和 bug-fix、security-audit、data-transform 分离。

### performance-optimize
强化 latency / throughput / CPU / memory / GC / OOM / complexity 等路由词，并明确资源类问题优先本 Skill、SQL 专项调优交给 sql-query。

### security-audit
强化漏洞类型和安全专项优先级，允许安全修复建议；明确普通代码评审与日志事件分析不属于本 Skill。

### sql-query
强化 SQL/DDL/schema/execution-plan/query-tuning/dialect-migration，规定 SQL 专项性能仍归本 Skill。

### test-generation
增加压力、属性、Fuzz、混沌测试等路由信号，减少并发/性能词把测试任务吸到 performance-optimize。

## 5. 原始测试分布

原始数据集共有 352 条，16 个 Skill 每个恰好 22 条，因此“按 Skill 总量”是均衡的；但 easy/medium/hard 并不均衡。

| Skill | easy | medium | hard | total |
|---|---:|---:|---:|---:|
| api-integration | 9 | 7 | 6 | 22 |
| bug-fix | 6 | 7 | 9 | 22 |
| code-generation | 9 | 7 | 6 | 22 |
| code-refactor | 9 | 7 | 6 | 22 |
| code-review | 7 | 7 | 8 | 22 |
| data-transform | 9 | 7 | 6 | 22 |
| doc-generation | 9 | 7 | 6 | 22 |
| file-math | 6 | 7 | 9 | 22 |
| file-summary | 6 | 7 | 9 | 22 |
| knowledge-compare | 6 | 7 | 9 | 22 |
| knowledge-qa | 6 | 7 | 9 | 22 |
| log-analysis | 9 | 7 | 6 | 22 |
| performance-optimize | 9 | 7 | 6 | 22 |
| security-audit | 9 | 7 | 6 | 22 |
| sql-query | 9 | 7 | 6 | 22 |
| test-generation | 9 | 7 | 6 | 22 |

## 6. 标签修正后的分布

Ground Truth 修正后，Skill 数量不再均衡；这是正常现象，因为正确标签优先于人为凑数。

| Skill | easy | medium | hard | total |
|---|---:|---:|---:|---:|
| api-integration | 9 | 7 | 6 | 22 |
| bug-fix | 6 | 6 | 8 | 20 |
| code-generation | 9 | 7 | 6 | 22 |
| code-refactor | 9 | 7 | 6 | 22 |
| code-review | 6 | 6 | 5 | 17 |
| data-transform | 9 | 7 | 6 | 22 |
| doc-generation | 9 | 7 | 6 | 22 |
| file-math | 6 | 7 | 9 | 22 |
| file-summary | 6 | 6 | 8 | 20 |
| knowledge-compare | 6 | 7 | 10 | 23 |
| knowledge-qa | 6 | 7 | 9 | 22 |
| log-analysis | 9 | 8 | 6 | 23 |
| performance-optimize | 9 | 9 | 9 | 27 |
| security-audit | 10 | 7 | 7 | 24 |
| sql-query | 9 | 7 | 6 | 22 |
| test-generation | 9 | 7 | 6 | 22 |

## 7. Balanced v2 数据集

为避免标签修正后类别分布偏斜，又避免只按总量平衡而忽略难度，我另外生成了 `retrieval_cases_balanced_v2.jsonl`：
- 16 个 Skill；
- 每个 Skill 24 条；
- 每个 Skill 恰好 easy 8 / medium 8 / hard 8；
- 总计 384 条；
- 对重复、边界冲突或能力不匹配的 17 条样本从 balanced 版本中移除；
- 新增 49 条针对缺口和 Hard Negative 的测试。

### Balanced v2 分布

| Skill | easy | medium | hard | total |
|---|---:|---:|---:|---:|
| api-integration | 8 | 8 | 8 | 24 |
| bug-fix | 8 | 8 | 8 | 24 |
| code-generation | 8 | 8 | 8 | 24 |
| code-refactor | 8 | 8 | 8 | 24 |
| code-review | 8 | 8 | 8 | 24 |
| data-transform | 8 | 8 | 8 | 24 |
| doc-generation | 8 | 8 | 8 | 24 |
| file-math | 8 | 8 | 8 | 24 |
| file-summary | 8 | 8 | 8 | 24 |
| knowledge-compare | 8 | 8 | 8 | 24 |
| knowledge-qa | 8 | 8 | 8 | 24 |
| log-analysis | 8 | 8 | 8 | 24 |
| performance-optimize | 8 | 8 | 8 | 24 |
| security-audit | 8 | 8 | 8 | 24 |
| sql-query | 8 | 8 | 8 | 24 |
| test-generation | 8 | 8 | 8 | 24 |

## 8. 从 Balanced v2 中移除的 17 条

这些样本并非都“错误”，主要是为了去重、消除冲突或把每个 Skill×difficulty 控制到同一数量。

`ai-e05`, `cg-e07`, `cr-e07`, `dt-e09`, `dg-e04`, `la-e09`, `po-e03`, `bug_fix_014`, `bug_fix_021`, `code_review_005`, `sa-e03`, `sq-e04`, `tg-e06`, `file_math_019`, `knowledge_qa_016`, `knowledge_compare_017`, `knowledge_compare_020`

## 9. 建议的下一次实验顺序

1. 用 `skills_optimized_v1.1.zip` 替换旧 Skill metadata。
2. 先用 `retrieval_cases_corrected_v2.jsonl` 跑一次，观察“只改标签 + Skill metadata”后的自然结果。
3. 再用 `retrieval_cases_balanced_v2.jsonl` 做主 Eval，避免类别/难度分布偏斜。
4. 记录 per-skill Recall@1/3/5 和 MRR，重点观察 code-review、code-generation、knowledge-qa、file-summary。
5. 只有在 Ground Truth 和 Taxonomy 稳定后，再比较 Vector / BM25 / Hybrid-RRF。

注意：当前结果文件只打印了 Recall@3 Failure 的 Top5，并没有保存全部 352 条的完整候选列表。因此不能仅靠这份失败日志可靠地重算“修正标签后的新 Recall@1/MRR”；必须重新跑一次 Eval。