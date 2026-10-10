---
name: knowledge-compare
description: 当核心目标是对两个或以上概念、方案、模型、技术或知识来源进行横向比较，分析差异、优缺点、取舍和适用场景时使用。若只是回答单一知识问题使用 knowledge-qa；若只是总结一个文件而不做横向比较，使用 file-summary。
version: 1.1.0
tags:
- knowledge
- compare
- comparison
- tradeoff
- difference
- pros-cons
- alternatives
- analysis
- benchmark
always: false
enabled: true
---

# Knowledge Compare

这个 Skill 用于“比较多个知识来源之间的相同点、差异点和矛盾点”的场景。

## Procedure

当用户要求比较多个知识内容时：

1. 先确认需要比较的知识来源，例如多个文件、多个段落或多个检索结果。
2. 如果知识来源是文件，使用 `read_text_file` 分别读取每个文件。
3. 不要根据文件名猜测内容，必须以真实 Tool Result 为准。
4. 从以下维度进行比较：
   - 相同点
   - 差异点
   - 矛盾点
   - 信息覆盖范围
   - 可信度或完整度差异
5. 最后由 LLM 输出结构化的比较结论。

## Error handling

如果任意文件不存在，不要猜测其内容，应向用户说明哪些文件读取失败。

如果知识内容不足以支持完整比较，应明确说明比较结论可能不完整，不要伪造差异或结论。