---
name: log-analysis
description: 当用户提供或指向运行日志、异常堆栈、告警、事件记录或监控追踪数据，主要目标是解读日志、恢复时间线、关联调用链、识别异常模式或定位运行根因时使用。若最终目标是修改代码修复故障，使用 bug-fix；若是代码安全审计，使用
  security-audit；若只是把日志转换成结构化数据，使用 data-transform。
version: 1.1.0
tags:
- log
- analysis
- stacktrace
- monitoring
- incident
- timeline
- root-cause
- trace
- error-log
- observability
always: false
enabled: true
---

# Log Analysis

这个 Skill 用于“解读运行日志并定位异常原因”的场景。

## Procedure

当用户提供日志并要求分析时：

1. 使用 `read_text_file` 读取日志文件，完整获取日志内容。
2. 识别日志格式（时间戳、级别、模块名、消息体），确认日志来源系统。
3. 按以下维度分析：
   - 时间线：异常事件的发生顺序和频率
   - 错误级别：ERROR / FATAL 条目的具体内容
   - 关联上下文：异常前后的 WARN / INFO 日志
   - 模式识别：是否有重复出现的错误模式
4. 给出异常原因分析和可能的根因，标注置信度。
5. 给出下一步排查建议或修复方向。
6. 如果日志涉及多个服务，梳理调用链路和故障传播路径。

## Error handling

如果日志文件不存在或为空，不要编造分析结论，应向用户说明读取失败。

如果日志内容不足以确定根因（如只有一条错误且无上下文），应明确说明需要更多日志或监控数据，不要过度推测。