---
name: file-math
description: 读取 workspace 文本文件中的数学任务，并通过 read_text_file 和 calculator 可靠完成计算。
always: false
---

# File Math

这个 Skill 用于“从本地文本文件读取数学任务并执行”的场景。

## Procedure

当用户要求根据某个 workspace 文本文件完成计算时：

1. 先使用 `read_text_file` 读取用户指定的文件。
2. 不要根据文件名猜测内容，必须以真实 Tool Result 为准。
3. 如果文件内容包含需要精确执行的加、减、乘、除运算，使用 `calculator`。
4. 不要让语言模型自行心算可以由 `calculator` 完成的运算。
5. Calculator 返回结果后，再由 LLM 组织最终自然语言回答。

## Error handling

如果文件不存在，不要猜测文件内容，应向用户说明读取失败。

如果 Calculator 返回 Tool Error，应根据真实错误解释失败原因，不要伪造结果。