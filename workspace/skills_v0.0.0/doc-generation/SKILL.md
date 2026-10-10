---
name: doc-generation
description: >
  当用户要求为代码、模块、API 或项目生成文档（README、API 文档、注释文档）时使用。
  如果用户只是要求总结文件内容或做知识问答，不使用此 Skill。
version: 1.0.0
tags:
  - code
  - documentation
  - readme
always: false
enabled: true
---

# Doc Generation

这个 Skill 用于“为代码或项目自动生成结构化文档”的场景。

## Procedure

当用户提出文档生成需求时：

1. 使用 `read_text_file` 读取目标代码文件或项目结构，提取模块、类、函数和参数信息。
2. 确认文档类型（README、API 参考、CHANGELOG、内联注释）和目标读者（开发者/最终用户）。
3. 按照对应文档规范组织内容：
   - README：项目简介、安装步骤、使用示例、配置说明
   - API 文档：端点、参数、返回值、示例请求
   - 代码注释：函数用途、参数说明、返回值、异常情况
4. 生成文档内容，保持语言简洁、结构清晰。
5. 使用 `write_text_file` 将文档写入用户指定路径。

## Error handling

如果代码文件不存在或无法解析，不要编造 API 描述，应向用户说明读取失败。

如果项目结构过于庞大，应先与用户确认文档范围，避免生成过于冗长的内容。
