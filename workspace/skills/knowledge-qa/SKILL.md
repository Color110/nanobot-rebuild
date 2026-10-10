---
name: knowledge-qa
description: 当用户希望基于知识库、已有资料、文档或检索证据回答一个单一的事实、概念、机制、接口或定义问题时使用，典型意图包括“是什么”“为什么”“怎么工作”“文档如何定义”。若核心目标是比较两个或以上方案/概念/来源，使用 knowledge-compare；若只是摘要指定文件，使用
  file-summary。
version: 1.1.0
tags:
- knowledge
- qa
- question-answering
- explain
- factual
- concept
- documentation
- knowledge-base
- retrieval
- definition
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