---
name: code-refactor
description: >
  当用户要求改善已有代码的结构、可读性、可维护性或设计模式，但不改变外部行为时使用。
  如果用户是要修复 Bug、新增功能或生成全新代码，不使用此 Skill。
version: 1.0.0
tags:
  - code
  - refactor
  - cleanup
always: false
enabled: true
---

# Code Refactor

这个 Skill 用于“在不改变外部行为的前提下优化代码结构”的场景。

## Procedure

当用户提出重构需求时：

1. 使用 `read_text_file` 读取需要重构的代码文件，完整理解现有逻辑。
2. 识别代码中的坏味道（code smell），如重复代码、过长函数、过深嵌套、命名不规范等。
3. 制定重构计划：列出每一步改动及其理由，确保每步都不改变外部行为。
4. 执行重构，优先使用小步改动（extract method、rename、inline 等）。
5. 重构完成后，对比改动前后的行为一致性，提示用户运行已有测试进行验证。
6. 使用 `write_text_file` 写回重构后的代码。

## Error handling

如果代码文件不存在或无法读取，不要猜测代码内容，应向用户说明读取失败。

如果重构可能影响其他模块的调用方式，应明确提示潜在影响范围，而非静默修改。
