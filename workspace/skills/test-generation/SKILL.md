---
name: test-generation
description: 当核心目标是为已有代码或系统设计、生成测试时使用，包括单元测试、集成测试、压力测试、属性测试、Fuzz 测试和混沌测试。若只是审查现有测试覆盖是否充分而不生成测试，使用 code-review；若是修复测试失败背后的代码故障，使用
  bug-fix。
version: 1.1.0
tags:
- code
- test
- generate-tests
- unit-test
- integration-test
- property-test
- fuzz
- chaos-test
- coverage
- mock
always: false
enabled: true
---

# Test Generation

这个 Skill 用于“为已有代码自动生成测试用例”的场景。

## Procedure

当用户提出测试生成需求时：

1. 使用 `read_text_file` 读取需要测试的源代码文件，理解函数签名、输入输出和边界条件。
2. 确认用户偏好的测试框架（如 pytest、Jest、JUnit 等）；如果项目中已有测试文件，使用 `read_text_file` 读取以保持风格一致。
3. 根据任务类型设计测试：普通代码覆盖正常路径、边界值、异常输入和空值；并发/分布式场景可进一步使用压力测试、属性测试、Fuzz 或混沌测试，并明确要验证的不变量。
4. 生成测试代码，包含清晰的测试描述（test name）和断言信息。
5. 如果涉及外部依赖（数据库、网络），应生成 mock 或 fixture。
6. 使用 `write_text_file` 将测试文件写入对应目录。

## Error handling

如果源代码文件不存在或无法读取，不要编造函数签名，应向用户说明。

如果被测函数依赖复杂环境且无法 mock，应明确说明限制，建议用户补充集成测试环境。
