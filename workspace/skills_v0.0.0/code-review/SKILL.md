---
name: code-review
description: >
  当用户需要对代码片段、文件内容或变更内容进行代码审查时使用。
  如果用户只是要求修复报错、调试问题或直接改写代码，不使用此 Skill。
version: 1.0.0
tags:
  - code
  - review
  - quality
always: false
enabled: true
---

# Code Review

这个 Skill 用于“对代码进行审查并给出改进建议”的场景。

## Procedure

当用户要求审查代码时：

1. 先使用 `read_text_file` 读取用户指定的代码文件或代码片段。
2. 不要根据文件名或上下文猜测代码内容，必须以真实 Tool Result 为准。
3. 按以下维度检查代码：
   - 正确性
   - 可读性
   - 性能
   - 安全性
   - 错误处理
   - 命名与结构
4. 对每个问题给出具体位置、原因和改进建议。
5. 最后由 LLM 组织成结构化的审查报告。

## Error handling

如果文件不存在，不要猜测代码内容，应向用户说明读取失败。

如果代码内容不完整或无法判断上下文，应明确说明审查结论可能受限，不要伪造代码行为。