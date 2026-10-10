---
name: bug-fix
description: 当已经出现功能性错误、异常、错误结果、崩溃、失效行为或可复现故障，用户希望定位根因并修复时使用。若只是审查潜在问题而不修复，使用 code-review；若核心诉求是延迟、吞吐、CPU、内存、GC、OOM 等性能或资源指标，使用
  performance-optimize；若只是解读日志而不修代码，使用 log-analysis。
version: 1.1.0
tags:
- code
- bug
- debug
- fix
- exception
- crash
- wrong-result
- root-cause
- repair
always: false
enabled: true
---

# Bug Fix

这个 Skill 用于“根据错误信息或异常现象定位并修复代码问题”的场景。

## Procedure

当用户报告代码问题时：

1. 先使用 `read_text_file` 读取相关代码文件或错误日志文件。
2. 不要根据文件名猜测代码内容或错误原因，必须以真实 Tool Result 为准。
3. 分析错误信息、堆栈、代码上下文和运行现象，定位可能原因。
4. 给出最小化修复方案，并说明修复理由。
5. 如果问题可能引发副作用，应提示需要补充测试或进一步验证。

## Error handling

如果文件不存在，不要猜测代码或日志内容，应向用户说明读取失败。

如果错误信息不足，无法确定根因，应明确说明需要更多上下文，不要编造修复方案。