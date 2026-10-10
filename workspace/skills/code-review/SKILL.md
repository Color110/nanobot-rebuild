---
name: code-review
description: 当用户要求审查已有代码、PR 或实现方案，主要目标是发现或评价正确性、可读性、错误处理、并发安全、资源生命周期、接口/架构设计或测试覆盖等问题，且以分析和建议为主而不是直接修改时使用。若目标明确是修复已知故障、专项性能优化、安全漏洞审计、重构、生成新代码/测试/文档，优先使用对应专项
  Skill。
version: 1.1.0
tags:
- code
- review
- analysis
- quality
- correctness
- readability
- design
- maintainability
- inspect
- pr-review
always: false
enabled: true
---

# Code Review

这个 Skill 用于“对代码进行审查并给出改进建议”的场景。

## Procedure

当用户要求审查代码时：

1. 先使用 `read_text_file` 读取用户指定的代码文件或代码片段。
2. 不要根据文件名或上下文猜测代码内容，必须以真实 Tool Result 为准。
3. 按任务目标选择相关维度检查代码：
   - 正确性与边界条件
   - 可读性与可维护性
   - 错误处理与资源生命周期
   - 并发安全与状态一致性
   - 接口、依赖和结构设计
   - 已有测试覆盖与可测试性
   对于用户明确提出的安全专项或性能专项问题，应由对应的 `security-audit` / `performance-optimize` Skill 优先处理，而不是让通用 Review 吞掉所有专项任务。
4. 对每个问题给出具体位置、原因和改进建议。
5. 最后由 LLM 组织成结构化的审查报告。

## Error handling

如果文件不存在，不要猜测代码内容，应向用户说明读取失败。

如果代码内容不完整或无法判断上下文，应明确说明审查结论可能受限，不要伪造代码行为。