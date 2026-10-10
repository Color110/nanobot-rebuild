---
name: file-summary
description: >
  当用户需要读取本地文本文件并生成摘要、要点或内容概述时使用。
  如果用户只是要求读取文件但不做总结，不使用此 Skill。
version: 1.0.0
tags:
  - file
  - summary
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
3. 提取文件中的主要信息，包括：
   - 主题
   - 关键结论
   - 重要事实
   - 结构要点
4. 如果文件内容较长，应优先输出简洁摘要，再补充详细要点。
5. 最后由 LLM 组织自然语言总结。

## Error handling

如果文件不存在，不要猜测文件内容，应向用户说明读取失败。

如果文件内容为空或无法解析，应明确说明无法生成摘要，不要伪造内容。