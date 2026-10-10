# OpenAI 官方页面检索与阅读总结

> 依据依赖任务 `research_openai_official` 的检索与抓取结果整理，仅陈述该任务已提供的证据。

## 一、检索到的官方页面标题与 URL

通过查询 `site:openai.com OpenAI` 检索到以下官方页面线索（标题与 URL 均为检索结果原文）：

| 标题 | URL |
|---|---|
| About | `https://openai.com/about/` |
| Introducing OpenAI  OpenAI | `https://openai.com/blog/introducing-openai/` |
| OpenAI | `https://grants.openai.com/` |

（其中 `About` 另有 http 版本 `http://openai.com/about/`，`Introducing OpenAI` 另有去尾斜杠版本 `https://openai.com/blog/introducing-openai`，均为同一页面的不同写法。）

## 二、页面抓取情况

- **抓取失败**：`https://openai.com/about/` 与 `https://openai.com/blog/introducing-openai/` 均返回 `WEB_FETCH_HTTP_403`（HTTP 403 Forbidden），**正文无法读取**；随后对 `openai.com` 同一 hostname 的重复尝试被 Runtime 阻止（`WEB_FETCH_REPEAT_BLOCKED`）。因此 `About` 页与 `Introducing OpenAI` 博客的正文内容**未能验证**，本总结不引用其正文。
- **抓取成功**：`https://grants.openai.com/`（页面标题为 **OpenAI**，内容类型 text/html）。

## 三、所读页面主要内容（`https://grants.openai.com/`）

- 该站点由 **SurveyMonkey Apply** 平台驱动，页面含登录、注册、帮助中心、支持等导航元素，并提及 "Programs / Sign Up"、引导查看活跃资助计划（active grant programs）。
- 核心声明（原文摘录）：

  > "OpenAI's mission is to ensure that artificial general intelligence (AGI) benefits all of humanity. In service of that mission, we sometimes provide grants (in the form of monetary compensation or API credits, depending on the program) to support strategic initiatives and research."

- 页脚版权标注为 **SurveyMonkey**，含 Help / Privacy / Terms 链接。

## 四、说明与边界

- 成功读取的仅有 `grants.openai.com` 一个页面，其内容依托第三方 SurveyMonkey Apply 托管平台呈现。
- `openai.com` 主域（About 页与博客页）因返回 403 而未能读取正文，故仅依据检索所得的标题与 URL 报告，未对其正文内容做任何陈述。
- 检索结果中出现的内容摘要（snippet）未经原文读取核验，不作为已证实事实引用。
