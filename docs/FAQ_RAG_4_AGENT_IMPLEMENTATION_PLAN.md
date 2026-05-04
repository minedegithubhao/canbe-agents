# FAQ RAG 智能助手 4-Agent 协作与实现方案

> 归档说明：本文是早期实施计划，包含本地 BGE 模型等历史设计。当前运行时实现已精简为百炼 embedding / rerank + DeepSeek + MongoDB / Elasticsearch / Milvus / Redis，实际代码和接口以 `docs/JD_HELP_RETRIEVAL_ENHANCEMENT_V1.md`、`docs/API_USAGE.md` 和 `app/` 当前实现为准。

更新时间：2026-04-28

## 0. 当前已确认开发约束

本节由 PM Agent 维护，记录用户已经明确确认的实现约束。

```text
后端技术栈：Python FastAPI。
前端范围：不开发真正前端，已有前端系统；本项目只提供 API 接口。
数据导入：由本项目自行从 https://help.jd.com/user/issue.html 及其 FAQ 子页面温和导入公开数据。
导入范围：第一版只允许进入 https://help.jd.com/user/issue.html 以及 https://help.jd.com/user/issue/*.html 公开 FAQ issue 页面。
导入原则：拒绝暴力导入；并发 1；请求间隔 2-5 秒随机；不做登录绕过；不做站点扫描；不访问非 FAQ issue 路径。
本地模型目录：models。
Embedding / sparse 模型：优先使用 models/bge-m3。
Reranker 模型：优先使用 models/bge-reranker-base。
Reranker 策略：第一版启用 reranker。
大模型：DeepSeek。
DeepSeek 调用方式：通过 .env 配置，用户后续补充。
检索策略：稠密向量 + 稀疏向量 + 关键词检索。
存储环境：MongoDB + Milvus + Elasticsearch + Redis。
中间件连接方式：通过 .env 配置，用户后续补充。
WSL Docker 中间件命名：必须使用项目专属库表、索引、collection 和 key 前缀 canbe_faq_rag，避免影响其他人的数据。
```

角色边界同步调整：

```text
Agent C 不负责开发真实前端页面。
Agent C 负责 API 返回结构校验、前端联调契约、测试集、评测指标和演示用例。
```

## 1. 项目定位

本项目是教学项目，目标是基于京东帮助中心公开 FAQ 构建一个 RAG 智能问答助手。

v1 数据源固定为以下公开 FAQ issue 范围：

https://help.jd.com/user/issue.html
https://help.jd.com/user/issue/*.html

项目只做公开 FAQ 问答，不接入京东内部 API，不查询订单、物流、账号、支付、退款进度、客服工单等个人化或内部业务数据。

核心原则：

```text
流程可以答，状态不能查。
规则可以说，结果不能承诺。
公开资料可以用，内部数据不能编。
知识库没有依据时，必须兜底。
```

## 2. 4-Agent 分工

```text
PM Agent：产品经理 / 项目统筹
├── Agent A：知识库负责人
├── Agent B：RAG + 后端负责人
└── Agent C：API 联调 + 测试评测负责人
```

| Agent | 角色 | 主责 |
|---|---|---|
| PM Agent | 产品经理 / 项目统筹 | 记录已确认方案、拆任务、协调冲突、验收成果 |
| Agent A | 知识库负责人 | 数据采集、清洗、FAQ 结构化、分类、标签、兜底边界 |
| Agent B | RAG + 后端负责人 | 存储设计、检索策略、RAG 流程、API、日志反馈 |
| Agent C | API 联调 + 测试评测负责人 | API 返回结构校验、前端联调契约、来源链接校验、测试集、评测指标 |

PM Agent 必须持续维护本文档，凡是讨论中已经敲定的规则，都应记录到本文档或后续拆分文档中。

## 3. 数据源与导入规则

v1 数据源是京东帮助中心公开 FAQ issue 页面：

https://help.jd.com/user/issue.html
https://help.jd.com/user/issue/*.html

采集目标不是整站文本，而是明确的 FAQ 问答对。

第一版导入边界必须严格保持为“限定路径、低频、内容判定”：

```text
仅允许请求：https://help.jd.com/user/issue.html
仅允许递归进入：https://help.jd.com/user/issue/*.html
允许示例：https://help.jd.com/user/issue/list-959-960.html
允许示例：https://help.jd.com/user/issue/110-4188.html
不做站点扫描、目录枚举或批量探测。
不绕过登录、验证码、访问限制或反爬机制。
不访问 help.jd.com 下除 FAQ issue 路径以外的其他页面。
并发固定为 1。
请求间隔为 2-5 秒随机。
```

允许进入 v1 知识库的数据必须同时满足：

```text
1. 有明确问题。
2. 有明确答案。
3. 有真实可跳转 sourceUrl。
4. 内容来自 help.jd.com 公开 FAQ issue 页面。
5. 答案脱离原页面后仍能被用户理解。
```

不进入 v1 的数据：

```text
纯分类导航
帮助中心首页说明
搜索框提示
页头页脚
客服入口
广告位
无答案的问题列表
没有明确问题标题的长篇政策文档
需要登录或内部接口才能获取的内容
```

长篇政策文档默认不进入 v1，除非可以拆出明确的 question-answer pair。

## 4. 数据清洗策略

Agent A 负责数据清洗，清洗流程如下：

```text
抓取原始页面
  ↓
保存 rawHtml / rawText / sourceUrl / fetchedAt / contentHash
  ↓
结构化提取 question / answer / category / sourceUrl
  ↓
去除导航、脚本、样式、页头页脚、客服入口、重复分类
  ↓
中文文本 UTF-8 规范化
  ↓
识别明确问答对
  ↓
去重与相似问法合并
  ↓
补充分类、标签、风险等级、回答边界
  ↓
质量校验
  ↓
进入 FAQ 主库和向量索引流程
```

质量校验规则：

```text
question 不能为空。
answer 不能为空。
sourceUrl 必须真实可跳转。
sourceUrl 必须来自 help.jd.com。
answer 不能只剩导航文本。
正文不能包含大量脚本、样式或乱码。
重复内容需要合并或剔除。
```

## 5. FAQ 数据结构

每条 FAQ 建议结构：

```json
{
  "id": "jd_faq_001",
  "question": "忘记密码怎么办？",
  "similarQuestions": ["密码丢了怎么找回？", "登录密码忘了怎么办？"],
  "answer": "可以在登录页点击“忘记密码”，按页面提示完成身份验证后重置密码。",
  "category": "account",
  "categoryName": "账户与登录",
  "tags": ["登录", "密码", "找回密码"],
  "source": "京东帮助中心公开 FAQ",
  "sourceUrl": "https://help.jd.com/user/issue.html",
  "sourceTitle": "京东帮助中心",
  "enabled": true,
  "priority": 10,
  "riskLevel": "low",
  "answerBoundary": "只说明公开流程，不查询个人状态",
  "updatedAt": "2026-04-28",
  "fetchedAt": "2026-04-28",
  "contentHash": "sha256_hash",
  "suggestedQuestions": ["收不到验证码怎么办？"]
}
```

真实采集时，如果存在具体 FAQ 详情页，应优先使用具体详情页 URL，而不是统一使用入口页 URL。

## 6. 存储设计

根据团队已经准备好的环境，存储方案调整为：

```text
MongoDB：保存原始页面、清洗后的 FAQ 主数据、切块数据、版本信息。
Milvus：保存 dense/sparse 向量索引，负责语义检索和向量混合检索。
Elasticsearch：保存 FAQ 搜索索引，负责 BM25、关键词检索、字段过滤和高亮。
Redis：保存会话、热点问题缓存、接口结果短缓存、分布式锁和异步任务状态。
```

不再优先采用 PostgreSQL + pgvector。原因是你们已有 ES、Milvus、Redis、MongoDB，直接按现有环境设计能减少基础设施切换成本，也更适合展示专业 RAG 的混合检索链路。

### 6.1 MongoDB：主数据与原始数据

MongoDB 作为 FAQ 知识库的主存储，不负责向量相似度检索。

集合设计：

| Collection | 用途 |
|---|---|
| `crawl_pages` | 保存原始页面快照、URL、抓取时间、内容指纹 |
| `faq_items` | 保存清洗后的 FAQ 主数据 |
| `faq_chunks` | 保存 FAQ 切块，短 FAQ 可一条 FAQ 一个 chunk |
| `index_versions` | 保存索引版本、构建时间、数据范围 |
| `chat_logs` | 保存用户问题、命中 FAQ、分数、答案、fallback 状态 |
| `feedback_logs` | 保存用户反馈，如 useful / useless / unresolved |

在 WSL Docker 共享中间件环境中，所有集合必须落在项目专属数据库中：

```text
MONGODB_DATABASE=canbe_faq_rag
```

不得复用、清理或重建非本项目数据库。

`crawl_pages` 建议字段：

```text
_id
sourceUrl
rawHtml
rawText
httpStatus
fetchedAt
contentHash
parseStatus
```

`faq_items` 建议字段：

```text
_id
question
similarQuestions
answer
category
categoryName
tags
source
sourceUrl
sourceTitle
enabled
priority
riskLevel
answerBoundary
updatedAt
fetchedAt
contentHash
```

`faq_chunks` 建议字段：

```text
_id
faqId
chunkText
chunkIndex
sourceUrl
enabled
contentHash
```

短 FAQ 默认一条 FAQ 一个 chunk；长答案按小标题、步骤或自然段切块，但不能切断条件和结论。

### 6.2 Milvus：向量索引

Milvus 负责保存向量和执行向量召回。

Collection 建议：

```text
canbe_faq_rag_vector_index
- id
- faqId
- chunkId
- denseVector
- sparseVector 可选
- category
- tags
- riskLevel
- enabled
- sourceUrl
- indexVersion
```

项目专属 collection 名称：

```text
MILVUS_COLLECTION=canbe_faq_rag_vector_index
```

不得删除或覆盖非本项目 collection。

向量化文本建议：

```text
问题：{question}
相似问法：{similarQuestions}
分类：{categoryName}
标签：{tags}
答案：{answer}
边界：{answerBoundary}
```

`sourceUrl` 不参与语义匹配，只用于答案溯源和过滤校验。

Milvus 的设计目标：

```text
1. v1 支持 dense embedding 检索。
2. v1.1 支持 sparse vector 或 dense + sparse hybrid search。
3. 检索结果只返回 faqId、chunkId、score、indexVersion 等轻量字段。
4. FAQ 完整内容回 MongoDB 查询，避免向量库承担主数据职责。
```

### 6.3 Elasticsearch：关键词、BM25 与过滤

Elasticsearch 负责 FAQ 的 lexical 检索，包括 BM25、关键词匹配、短词匹配、分类过滤和标签过滤。

Index 建议：

```text
canbe_faq_rag_search_index
- faqId
- chunkId
- question
- similarQuestions
- answer
- category
- categoryName
- tags
- sourceUrl
- enabled
- priority
- riskLevel
- answerBoundary
- indexVersion
```

项目专属 index 名称：

```text
ELASTICSEARCH_INDEX=canbe_faq_rag_search_index
```

不得删除或覆盖非本项目 index。

ES 的重点不是保存原始网页，而是提供检索能力：

```text
1. question、similarQuestions 使用较高权重。
2. tags、categoryName 用于过滤与加权。
3. answer 用于补充检索，不应压过问题标题。
4. enabled=false 的 FAQ 不参与检索。
```

### 6.4 Redis：缓存、会话和任务状态

Redis 不作为知识库主存储，只做加速和状态管理。

建议用途：

```text
canbe_faq_rag:faq:hotQuestions：热门问题缓存。
canbe_faq_rag:faq:categories：分类缓存。
canbe_faq_rag:chat:session:{sessionId}：短期会话状态。
canbe_faq_rag:chat:answer:{queryHash}：低时效问答结果缓存，可设置较短 TTL。
canbe_faq_rag:index:rebuild:lock：重建索引分布式锁。
canbe_faq_rag:index:task:{taskId}：索引任务进度。
canbe_faq_rag:rate_limit:{clientId}：简单限流。
```

Redis 中的数据允许丢失或重建，不能作为 FAQ 唯一数据源。

项目专属 key 前缀：

```text
REDIS_PREFIX=canbe_faq_rag
```

不得扫描、删除或覆盖非本项目前缀 key。

### 6.5 数据同步关系

写入和索引流程：

```text
京东帮助中心页面
  ↓
导入公开 FAQ HTML
  ↓
MongoDB.crawl_pages 保存原始快照
  ↓
清洗出明确问答对
  ↓
MongoDB.faq_items / faq_chunks 保存主数据
  ↓
构建 ES 索引
  ↓
构建 Milvus 向量索引
  ↓
Redis 刷新分类和热门问题缓存
```

索引构建必须按后台任务执行：

```text
POST /admin/ingest/build-index 只负责创建任务并立即返回 taskId。
GET /admin/ingest/tasks/{taskId} 查询任务状态、阶段、进度、统计和错误。
任务状态写入 Redis：canbe_faq_rag:index:task:{taskId}。
本地 embedding 模型加载和向量化必须分批执行，避免阻塞 FastAPI 健康检查和问答接口。
```

检索读取流程：

```text
用户 query
  ↓
ES 召回 BM25 / 关键词候选
  +
Milvus 召回 dense / sparse 向量候选
  ↓
融合排序
  ↓
根据 faqId / chunkId 回 MongoDB 获取完整 FAQ 内容
  ↓
构造 Prompt
  ↓
返回 answer + sources + confidence + fallback
```

## 7. 检索策略

Agent B 的检索策略不采用单纯 dense Top-K，而采用分阶段增强路线。

### 7.1 基础版

```text
dense 向量检索
  ↓
相似度阈值判断
  ↓
高置信回答 / 低置信 fallback
```

适合先跑通 RAG 闭环。

在当前已确认的模型目录下，dense embedding 优先使用 `models/bge-m3` 生成。

### 7.2 增强版

```text
dense 向量检索 + BM25 / 全文检索
  ↓
候选合并
  ↓
字段加权重排序
  ↓
阈值与边界判断
```

适合处理短词、专有词和口语表达。

在当前已确认的检索目标中，v1 不停留在 dense only，而是直接按增强检索设计：

```text
Milvus dense 向量召回
+
Milvus sparse 向量召回
+
Elasticsearch BM25 / keyword 召回
```

### 7.3 专业版

```text
dense 向量检索
  +
sparse 向量检索
  +
BM25 / lexical 检索
  ↓
RRF 融合
  ↓
重排序
  ↓
Top1/Top2 差距判断
  ↓
风险边界过滤
  ↓
生成答案或 fallback
```

稀疏向量需要纳入设计。它能在关键词和语义向量之间补充词项扩展能力，尤其适合 FAQ 中的短问题和业务词。

Rerank 阶段使用 `models/bge-reranker-base`，第一版启用 reranker。检索链路应先通过 Milvus 和 Elasticsearch 得到候选，再交给 reranker 对候选 FAQ 重新排序。

### 7.4 长答案防语义稀释

长 answer 不能直接完整进入向量索引或 reranker pair，否则容易让关键语义被背景说明、条件说明、注意事项稀释。

采用父子切块策略：

```text
parent FAQ：保存完整 question、answer、sourceUrl、category、tags、answerBoundary。
child chunk：按小标题、步骤、条件、自然段切分，用于检索和 rerank。
```

实现原则：

```text
1. MongoDB 保存完整 parent FAQ。
2. Milvus / Elasticsearch 索引 child chunk。
3. reranker 使用 chunk-level passage。
4. 生成答案时根据 parentFaqId 回 MongoDB 取必要上下文。
5. 同一个 parent FAQ 的多个 chunk 命中时，最终按 faqId 聚合。
```

`indexText` 用于召回，可以相对丰富：

```text
问题 + 相似问法 + 分类 + 标签 + 答案摘要 + chunk
```

`rerankText` 用于重排，必须短而聚焦：

```text
问题 + 相似问法 + 命中的答案片段 + 回答边界
```

reranker pair 组成：

```text
左侧：用户原始 query
右侧：chunk-level rerankText
```

示例：

```text
query:
优惠券咋用不了？

passage:
问题：优惠券为什么不能用？
相似问法：券不可用怎么办？优惠券用不了是什么原因？
答案片段：可能与使用门槛、有效期、适用范围有关，请以优惠券页面显示规则为准。
边界：只说明公开规则，不查询个人优惠券状态。
```

不进入 rerank passage 的内容：

```text
sourceUrl
rawHtml
导航文本
页脚版权
客服入口
广告文本
完整长篇政策全文
```

`sourceUrl` 只用于答案溯源和前端展示，不用于语义打分。

### 7.5 去重策略

去重分四层：

| 层级 | 依据 | 处理方式 |
|---|---|---|
| URL 去重 | canonicalUrl 相同 | 视为同一来源页面 |
| 内容指纹去重 | normalizedQuestion + normalizedAnswer 的 hash 相同 | 删除完全重复 |
| 近似文本去重 | question/answer 高相似 | 合并或进入复核 |
| chunk 去重 | chunkText 归一化后重复 | 同 FAQ 内删除，跨 FAQ 进入复核 |

完全重复内容可直接去重；近似重复不能直接删除，必须结合业务语义判断。

### 7.6 业务去重

业务去重必须考虑，不能只按文本相似度合并。

业务合并需要判断：

```text
业务对象是否一致：密码、验证码、优惠券、发票、售后等。
用户意图是否一致：流程说明、规则说明、状态查询、异常排查。
回答边界是否一致：只答流程、不查状态、不能承诺结果。
操作入口是否一致。
风险等级是否一致。
```

可以合并的例子：

```text
忘记密码怎么办？
登录密码忘了怎么找回？
密码丢了如何处理？
```

它们应合并为一个 canonical FAQ，其他问法进入 `similarQuestions`。

不能合并的例子：

```text
如何申请售后？
我的售后进度到哪了？
```

两者都包含“售后”，但前者是流程说明，后者是状态查询，回答边界不同，不能合并。

业务去重决策：

| 情况 | 处理 |
|---|---|
| 问法不同，答案边界一致 | 合并为 similarQuestions |
| 问法类似，但一个问流程一个问状态 | 不合并，状态类走 fallback |
| 答案几乎相同，但分类不同 | 进入复核 |
| 同一页面重复出现相同 FAQ | URL/hash 去重 |
| 不同 sourceUrl 内容相同 | 合并 canonical FAQ，保留 alternateSources |
| 同一 FAQ 多个 chunk 命中 | 按 faqId 聚合，只保留最高分 chunk |

### 7.7 Rerank 后 FAQ 级聚合

reranker 输出的是 chunk 级结果，但最终进入 Prompt 的应是 FAQ 级证据。

流程：

```text
chunk candidates
  ↓
rerank
  ↓
group by faqId
  ↓
每个 faqId 保留最高分 chunk
  ↓
按 faqScore 排序
  ↓
取 Top 3 FAQ 进入 Prompt
```

这样避免一个长 answer 的多个 chunk 占满 TopK，也避免同一业务问题重复进入 Prompt。

## 8. RRF 使用策略

RRF 不是 v1 最低闭环必需项，但如果系统采用多路召回，则建议使用。

判断规则：

```text
如果只有 dense 单路检索，不需要 RRF。
如果使用 dense + BM25，建议使用 RRF。
如果使用 dense + sparse，建议使用 RRF。
如果使用 dense + sparse + BM25，应该使用 RRF 或等价融合策略。
```

原因：

```text
1. dense、sparse、BM25 的原始分数尺度不同，直接相加不稳。
2. RRF 基于排名融合，不依赖不同检索器的分数可比性。
3. FAQ 场景问题短、业务词密集，多路都靠前的结果更可信。
```

RRF 公式：

```text
RRF(d) = sum(1 / (k + rank_i(d)))
```

其中 `d` 是候选 FAQ，`rank_i(d)` 是该 FAQ 在第 i 路召回中的排名，`k` 是平滑常数，常用 60。

## 9. 阈值与边界策略

推荐初始阈值：

| 分数 | 行为 |
|---|---|
| `>= 0.78` | 高置信度，正常回答 |
| `0.65 - 0.78` | 中置信度，提示“可能相关”，谨慎回答 |
| `< 0.65` | fallback，不生成自由答案 |

还需要判断 Top1 和 Top2 差距：

```text
Top1 明显高于 Top2：可以回答。
Top1 与 Top2 很接近：可能混淆，谨慎回答或展示可能相关问题。
整体分数都低：fallback。
```

边界判断优先级高于相似度。即使检索分数高，只要用户问题是订单状态、物流状态、退款进度、支付记录、账号隐私等个人化查询，也必须 fallback。

## 10. API 契约

本项目后端使用 Python FastAPI 实现，只提供 API，不开发真实前端页面。

核心接口：

```text
POST /faq/chat
GET  /faq/categories
GET  /faq/hot-questions
POST /faq/feedback
POST /admin/faq
PUT  /admin/faq/{id}
POST /admin/faq/reindex
```

`POST /faq/chat` 请求：

```json
{
  "query": "密码丢了咋办？",
  "sessionId": "session_001",
  "topK": 5
}
```

`POST /faq/chat` 响应：

```json
{
  "answer": "可以在登录页点击“忘记密码”，根据页面提示完成身份验证后重置密码。",
  "confidence": 0.88,
  "sources": [
    {
      "id": "jd_faq_001",
      "title": "忘记密码怎么办？",
      "category": "账户与登录",
      "source": "京东帮助中心公开 FAQ",
      "sourceUrl": "https://help.jd.com/user/issue.html",
      "score": 0.88
    }
  ],
  "suggestedQuestions": ["收不到验证码怎么办？"],
  "fallback": false,
  "traceId": "trace_20260428_001"
}
```

fallback 响应：

```json
{
  "answer": "暂未找到与该问题高度相关的 FAQ。你可以换一种问法，或查看帮助中心分类。",
  "confidence": 0.42,
  "sources": [],
  "suggestedQuestions": [],
  "fallback": true,
  "traceId": "trace_20260428_002"
}
```

## 11. 防幻觉策略

统一策略：

```text
1. 数据源锚定：只使用京东帮助中心公开 FAQ。
2. 来源可追溯：每条 FAQ 必须有真实可跳转 sourceUrl。
3. 检索优先：先检索，再生成。
4. 阈值兜底：低相似度不回答，直接 fallback。
5. Prompt 约束：模型只能基于检索内容回答。
6. 边界过滤：个人状态、内部数据、承诺性结果必须兜底。
7. 测试验证：用无关、越权、攻击型问题专门测幻觉。
```

Prompt 约束：

```text
你是一个 FAQ RAG 智能助手。
你只能根据给定的 FAQ 内容回答用户问题。
如果 FAQ 内容中没有答案，必须回答“暂未找到相关答案”，不能编造。
不能回答订单、物流、账号、支付、退款状态等个人化查询问题。
不能承诺具体业务结果。
回答要简洁、准确，并尽量使用 FAQ 中的原始事实。
```

## 12. API 联调与展示契约

真实前端已经存在，本项目不开发前端页面。Agent C 负责定义和验证 API 联调契约，确保已有前端可以展示：

```text
答案正文
来源标题
真实可点击 sourceUrl
推荐问题
置信度或可信状态
反馈按钮
```

fallback 状态不能被 API 包装成正常答案。

API 必须支持前端区分这些状态：

```text
初始状态
输入中
加载中
正常命中
低置信度
无结果
接口错误
反馈成功
反馈失败
```

## 13. 测试与验收

测试问题必须覆盖：

```text
标准问法
相似问法
口语问法
错别字问法
模糊问题
无关问题
禁止范围问题
Prompt Injection
```

验收指标：

| 指标 | 目标 |
|---|---|
| FAQ 数量 | 不少于 50 条 |
| 分类数量 | 不少于 5 类，建议 7 类 |
| 标准问法命中率 | >= 80% |
| 相似问法命中率 | >= 70% |
| 无关问题兜底率 | >= 90% |
| 来源完整率 | >= 95% |
| 来源链接可跳转率 | 100% |
| 反馈成功率 | >= 95% |
| Prompt Injection 越权回答 | 0 次 |

## 14. 已确认决策

| 决策 | 结论 |
|---|---|
| v1 数据源 | `https://help.jd.com/user/issue.html` 及 `https://help.jd.com/user/issue/*.html` |
| 数据目标 | 只导入明确问题 + 明确答案 |
| sourceUrl | 必须真实可跳转 |
| 存储方案 | MongoDB + Milvus + Elasticsearch + Redis |
| 后端技术栈 | Python FastAPI |
| 前端实现 | 不做真实前端，只提供 API 和联调契约 |
| 数据导入方式 | 项目自行温和导入公开 FAQ 数据，拒绝暴力访问 |
| 导入范围 | 入口页及其 FAQ issue 子页面，例如 `list-959-960.html`、`110-4188.html` |
| 导入频率 | 并发 1，请求间隔 2-5 秒随机 |
| 访问边界 | 不做登录绕过、不做扫描、不访问非 FAQ issue 路径 |
| WSL Docker 命名 | 使用项目专属 `canbe_faq_rag` 库表/索引/collection/key 前缀 |
| 本地模型目录 | `models/bge-m3`、`models/bge-reranker-base` |
| 生成模型 | DeepSeek |
| DeepSeek 配置 | 写入 `.env`，用户后续补充 |
| 中间件配置 | 写入 `.env`，用户后续补充 |
| MongoDB 职责 | 原始页面、FAQ 主数据、切块、日志、反馈、索引版本 |
| Milvus 职责 | dense/sparse 向量索引和向量召回 |
| Elasticsearch 职责 | BM25、关键词、分类标签过滤、lexical 召回 |
| Redis 职责 | 会话、缓存、限流、索引任务状态 |
| 索引构建方式 | 后台任务，接口立即返回 taskId，Redis 记录进度 |
| 检索方案 | Milvus dense/sparse + Elasticsearch BM25/keyword |
| 是否考虑 sparse | 是 |
| 是否启用 reranker | 第一版启用 `models/bge-reranker-base` |
| 是否使用 RRF | 多路召回时建议使用，单路 dense 不需要 |
| 防幻觉底线 | 没有依据就 fallback，不允许自由编造 |
