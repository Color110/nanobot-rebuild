---
name: knowledge-qa
description: >
  当用户基于已有知识片段、文档内容或检索结果提出事实性问题时使用。
  如果用户要求比较多个知识片段之间的差异，不使用此 Skill。
version: 1.0.0
tags:
  - knowledge
  - qa
  - retrieval
always: false
enabled: true
---

# Knowledge QA

这个 Skill 用于“基于已有知识内容回答事实性问题”的场景。

## Procedure

当用户提出知识性问题时：

1. 先确认问题对应的知识来源，例如文档、检索结果或已提供的上下文。
2. 如果知识来源是文件，使用 `read_text_file` 读取文件内容。
3. 不要根据文件名或问题猜测知识内容，必须以真实 Tool Result 为准。
4. 仅基于提供的知识内容回答问题，不要引入未验证的外部信息。
5. 如果知识内容不足以回答问题，应明确说明信息不足。

## Error handling

如果文件不存在，不要猜测知识内容，应向用户说明读取失败。

如果知识内容与问题无关，应说明无法基于当前材料回答，不要编造答案。