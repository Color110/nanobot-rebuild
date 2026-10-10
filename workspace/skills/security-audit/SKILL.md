---
name: security-audit
description: 当核心诉求是发现、验证或修复安全风险、漏洞或合规问题时使用，包括注入、XSS、CSRF、SSRF、路径遍历、认证授权、密钥泄露、数据保护、依赖漏洞、威胁建模等。普通代码质量审查使用 code-review；仅依据运行日志重建事件或定位运行故障使用
  log-analysis。
version: 1.1.0
tags:
- security
- audit
- vulnerability
- owasp
- injection
- auth
- authorization
- secret
- path-traversal
- threat-model
always: false
enabled: true
---

# Security Audit

这个 Skill 用于“对代码进行安全漏洞审计和合规检查”的场景。

## Procedure

当用户提出安全审计需求时：

1. 使用 `read_text_file` 读取需要审计的代码文件，了解技术栈和框架。
2. 按照安全审计清单逐项检查：
   - **注入类**：SQL 注入、XSS、命令注入、路径遍历
   - **认证授权**：硬编码凭证、权限校验缺失、Session 管理
   - **数据保护**：敏感信息明文存储、日志泄露、加密方式不当
   - **依赖安全**：已知漏洞的第三方库版本
   - **配置安全**：调试模式开启、CORS 配置、默认密码
3. 对发现的每个问题标注严重等级（Critical / High / Medium / Low）。
4. 给出修复建议；当用户明确要求安全修复时，可提供参考修复代码，但仍应保持安全问题的分级和证据说明。
5. 生成审计报告摘要，按严重等级排序。

## Error handling

如果代码文件不存在或无法读取，不要编造漏洞报告，应向用户说明读取失败。

如果无法确定某个代码片段是否存在漏洞（取决于运行时配置），应标注为"需进一步确认"，不要给出确定性结论。