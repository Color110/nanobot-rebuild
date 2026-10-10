---
name: file-summary
description: 当用户指定一个或多个现有文件/文档，希望摘要、提炼或结构化抽取其中已经存在的信息（要点、时间节点、条款、接口等）时使用，而不是生成新的技术文档。若核心目标是跨多个方案或来源做横向比较与取舍，使用 knowledge-compare；若是运行日志诊断使用
  log-analysis；文件中的数值计算使用 file-math。
version: 1.1.0
tags:
- file
- summary
- summarize
- extract
- document
- key-points
- outline
- existing-content
- text
always: false
enabled: true
---

# File Summary

这个 Skill 用于“读取文件内容并生成摘要”的场景。

## Procedure

当用户要求总结某个文件时：

1. 先使用 `read_text_file` 读取用户指定的文件。
2. 不要根据文件名猜测文件内容，必须以真实 Tool Result 为准。
3. 根据用户目标总结或抽取文件中的已有信息，包括：
   - 主题与结构
   - 关键结论和事实
   - 时间节点、条款、行动项
   - 已有接口、字段或其他结构化要点
4. 如果文件内容较长，应优先输出简洁摘要，再补充详细要点。
5. 最后由 LLM 组织自然语言总结。

## Error handling

如果文件不存在，不要猜测文件内容，应向用户说明读取失败。

如果文件内容为空或无法解析，应明确说明无法生成摘要，不要伪造内容。