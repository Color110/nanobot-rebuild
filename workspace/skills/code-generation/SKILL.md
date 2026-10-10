---
name: code-generation
description: 当用户从功能需求或业务逻辑出发，希望创建新的函数、类、模块、脚本、组件、服务或系统实现时使用。若核心产物是 SQL、测试、文档或外部 API 对接，使用对应专项 Skill；若是在已有代码上修 Bug、重构、做专项性能或安全处理，不使用此
  Skill。
version: 1.1.0
tags:
- code
- generate
- create
- implement
- new-code
- function
- module
- service
- script
- component
- scaffold
- build
always: false
enabled: true
---

# Code Generation

这个 Skill 用于“根据自然语言需求描述生成完整可运行代码”的场景。

## Procedure

当用户提出代码生成需求时：

1. 先确认用户的目标语言、框架和运行环境；如果这些信息会实质影响实现且用户未指定，应向用户追问，不要假设存在一个名为 `ask_user` 的 Tool。
2. 如果用户要求生成到已有项目中，使用 `read_text_file` 读取相关目录结构和已有文件，了解项目规范。
3. 根据需求拆解为模块、函数或类的设计，先给出结构概要，再生成完整代码。
4. 生成的代码应包含必要的注释、类型标注和输入校验。
5. 如果生成的代码依赖外部库，应明确列出依赖项和安装方式。
6. 使用 `write_text_file` 将代码写入用户指定路径，或直接在回复中输出。

## Error handling

如果用户需求描述模糊（如"帮我写个程序"），不要猜测具体功能，应向用户追问输入输出格式、核心逻辑和约束条件。

如果目标路径不存在或无写入权限，应向用户说明并建议替代路径。