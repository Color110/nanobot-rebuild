---
name: api-integration
description: >
  当用户要求对接外部 API、设计 REST/GraphQL 接口、或编写 API 客户端时使用。
  如果用户是要求编写本地函数或处理数据库查询，不使用此 Skill。
version: 1.0.0
tags:
  - api
  - integration
  - http
always: false
enabled: true
---

# API Integration

这个 Skill 用于“对接外部 API 或设计/实现 API 接口”的场景。

## Procedure

当用户提出 API 相关需求时：

1. 确认 API 类型（REST / GraphQL / gRPC / WebSocket）和数据格式（JSON / XML / Protobuf）。
2. 如果用户提供了 API 文档，使用 `read_text_file` 读取文档文件，提取端点、认证方式和参数规范。
3. 设计请求方案：URL 构造、HTTP 方法、请求头、请求体、认证方式（API Key / OAuth / JWT）。
4. 编写客户端代码或接口实现，包含：
   - 请求构造与发送
   - 响应解析与错误码处理
   - 超时与重试策略
5. 如果涉及认证信息，提醒用户通过环境变量或密钥管理存储，不要硬编码。
6. 提供调用示例和预期响应格式。

## Error handling

如果 API 文档不存在或无法访问，不要猜测端点和参数，应向用户说明并请求提供文档。

如果 API 需要认证但用户未提供凭证，应明确提示所需凭证类型，不要编造 token。
