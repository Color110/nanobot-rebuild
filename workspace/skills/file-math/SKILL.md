---
name: file-math
description: 当必须先读取文件中的数字、公式或计算规则，再执行数学或统计计算并得到数值结果时使用。若目标是总结文件内容使用 file-summary；若目标是清洗、转换或合并数据使用 data-transform；若用户直接给出简单表达式而无需读取文件，不使用此
  Skill。
version: 1.1.0
tags:
- file
- math
- calculation
- formula
- numeric
- statistics
- compute
- arithmetic
always: false
enabled: true
---

# File Math

这个 Skill 用于“从本地文本文件读取数学任务并执行”的场景。

## Procedure

当用户要求根据某个 workspace 文本文件完成计算时：

1. 先使用 `read_text_file` 读取用户指定的文件。
2. 不要根据文件名猜测内容，必须以真实 Tool Result 为准。
3. 对 `calculator` 支持的精确数值运算优先使用 `calculator`，不要让语言模型自行心算可由工具完成的运算。
4. 如果任务涉及统计量、矩阵、求根、迭代等超出当前计算工具能力的运算，不要伪造结果；应明确说明当前工具能力不足，或在运行时已有合适计算工具时再调用对应工具。
5. 计算工具返回结果后，再由 LLM 组织最终自然语言回答。

## Error handling

如果文件不存在，不要猜测文件内容，应向用户说明读取失败。

如果 Calculator 返回 Tool Error，应根据真实错误解释失败原因，不要伪造结果。