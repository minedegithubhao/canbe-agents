# 京东帮助中心知识库召回增强方案 v1

更新时间：2026-04-30

## 1. 目标

提升用户非标准提问的召回率。

非标准提问包括：

```text
简称：企微、E卡、白条
口语：付钱、邮费谁出、买贵了
同义：付款/支付/结算，退货/售后/退换货
省略：企业微信能网银吗？
错位表达：买贵补差价、退款多久到账
```

v1 重点做三件事：

```text
同义词词典
查询规范化与改写
index_text / embedding_text 增强
```

`similar_questions` 作为预留字段，第一版可先设计字段和流程，不批量生成。

## 2. 当前基础

当前清洗产物：

```text
exports/jd_help_faq.cleaned.jsonl
exports/jd_help_faq.chunks.jsonl
```

每条 FAQ / chunk 已有：

```text
question
answer_clean
embedding_text
index_text
category_l1/category_l2/category_l3
doc_type
status
search_enabled
quality_flags
parent_id
duplicate_group_id
```

这些字段已经支持：

```text
分类上下文召回
关键词召回
向量召回
业务去重
历史规则过滤
doc_type 加权
```

## 3. 同义词词典

建议新增配置文件：

```text
configs/jd_help_synonyms.yaml
```

结构：

```yaml
支付:
  canonical: 支付
  aliases:
    - 付款
    - 付钱
    - 结算
    - 收银台

退换货:
  canonical: 退换货
  aliases:
    - 退货
    - 换货
    - 售后
    - 返修

企业微信:
  canonical: 企业微信
  aliases:
    - 企微
    - 企业微信端

京东企业购:
  canonical: 京东企业购
  aliases:
    - 企业购
    - 企业采购
    - 企业会员

京东白条:
  canonical: 京东白条
  aliases:
    - 白条
    - 打白条

发票:
  canonical: 发票
  aliases:
    - 开票
    - 票据
    - 数电票
    - 电子发票

价格保护:
  canonical: 价格保护
  aliases:
    - 价保
    - 补差价
    - 买贵了

运费:
  canonical: 运费
  aliases:
    - 邮费
    - 配送费
    - 续重费
    - 逆向运费

京东E卡:
  canonical: 京东E卡
  aliases:
    - E卡
    - 京东卡
```

使用位置：

```text
入库阶段：把 canonical_terms / synonym_terms 写入 index_text。
查询阶段：把用户问题中的 alias 扩展为 canonical。
```

示例：

```text
用户问题：企微能不能走网银？
扩展结果：企业微信 企业微信端 企微 网银 支付 付款 结算
```

## 4. 查询规范化

Query Normalize 负责把用户问题变成稳定输入。

规则：

```text
统一全角/半角空格
去掉多余标点
保留数字、金额、日期、百分比
英文大小写统一
常见简称展开
```

示例：

```json
{
  "raw_query": "企微能不能走网银？",
  "normalized_query": "企微能不能走网银"
}
```

## 5. 查询改写

Query Rewrite 负责生成 1-3 个更适合检索的问题。

输入：

```text
raw_query
normalized_query
synonym_terms
```

输出：

```json
{
  "normalized_query": "企微能不能走网银",
  "expanded_query": "企业微信 企业微信端 企微 网银 支付 付款 结算",
  "rewrite_queries": [
    "企业微信是否支持网银支付？",
    "京东企业购企业微信端支持哪些支付方式？"
  ]
}
```

限制：

```text
最多 3 个 rewrite query。
每个 query 不超过 60 字。
不生成带答案倾向的 query。
不生成答案中未出现的业务承诺。
不改写金额、日期、规则条件。
```

## 6. 字段增强

在 `cleaned.jsonl` 和 `chunks.jsonl` 中建议增加或保留：

```json
{
  "canonical_terms": ["企业微信", "京东企业购", "支付"],
  "synonym_terms": ["企微", "企业购", "付款", "结算"],
  "similar_questions": [],
  "embedding_text": "...",
  "index_text": "..."
}
```

v1 要求：

```text
embedding_text：保持语义干净，适合 dense embedding。
index_text：加入 canonical_terms、synonym_terms、source_url，适合 BM25 / sparse。
similar_questions：字段预留，默认空数组。
```

示例：

```json
{
  "question": "企业微信支付方式有哪些",
  "canonical_terms": ["企业微信", "京东企业购", "支付"],
  "synonym_terms": ["企微", "企业购", "付款", "结算"],
  "embedding_text": "企业会员帮助中心 > 平台介绍 > 平台介绍\n章节：常见问题\n问题：企业微信支付方式有哪些\n答案：目前应用一期只支持微信支付，后续可支持网银支付",
  "index_text": "企业会员帮助中心 平台介绍 常见问题 企业微信 企微 京东企业购 企业购 支付 付款 结算 微信支付 网银支付 source_url:https://help.jd.com/user/issue/973-4253.html"
}
```

## 7. 检索流程 v1

推荐第一版检索流程：

```text
用户问题
  ↓
Query Normalize
  ↓
Synonym Expand
  ↓
Query Rewrite
  ↓
Dense 检索：normalized_query + rewrite_queries
  +
BM25 检索：expanded_query + rewrite_queries
  ↓
chunk_id 去重
  ↓
RRF 融合
  ↓
Reranker 重排
  ↓
业务去重
  ↓
最终 top5 业务候选
```

v1 可以先不启用 sparse vector，但字段和接口预留。

## 8. 默认过滤

普通问题默认过滤：

```json
{
  "search_enabled": true,
  "status": "active"
}
```

历史规则只有在用户明确提到以下词时放开：

```text
历史
旧版
已失效
失效
某年某月版本
```

协议类内容只有在用户明确提到以下词时提升权重：

```text
协议
隐私政策
条款
授权
服务协议
```

## 9. 融合策略

候选召回：

```text
dense topK = 30
BM25 topK = 30
```

融合：

```text
RRF 融合
chunk_id 去重
reranker top20
业务去重 top5
```

RRF 公式：

\[
score(d)=\sum_i \frac{1}{k + rank_i(d)}
\]

建议：

```text
k = 60
```

## 10. 业务去重

最终 top5 不是 5 个 chunk，而是 5 个业务候选。

业务去重 key 优先级：

```text
duplicate_group_id
parent_id
url
normalized question
```

规则：

```text
同一个 parent_id 的多个 chunk 合并为一个候选。
同一个 duplicate_group_id 只保留最高分候选。
同一个 URL 的多个相近 chunk 合并展示。
compound_qa 父文档不参与普通 top5。
embedded_qa 和 embedded_section 可以作为独立候选。
```

## 11. doc_type 加权

初始权重：

```json
{
  "operation_guide": 1.15,
  "fee_standard": 1.15,
  "faq": 1.0,
  "policy_rule": 1.0,
  "service_intro": 0.9,
  "agreement": 0.65,
  "historical_rule": 0.0,
  "compound_qa": 0.0
}
```

查询意图调整：

```text
问“怎么/如何/流程”：提升 operation_guide。
问“收费/运费/服务费/补偿”：提升 fee_standard。
问“协议/隐私/条款”：提升 agreement。
问“历史/旧版/失效”：允许 historical_rule。
```

## 12. similar_questions 预留

v1 不默认批量生成 `similar_questions`，只预留字段。

后续 v2 可离线生成：

```json
{
  "similar_questions": [
    "企业微信端支持哪些付款方式？",
    "企业购企业微信可以用网银支付吗？",
    "企业微信下单能用微信支付吗？"
  ]
}
```

生成限制：

```text
每条 FAQ 2-5 条。
只基于 question + answer_clean + category 生成。
不能引入答案中没有的信息。
historical_rule 不生成。
compound_qa 父文档不生成。
agreement 默认不生成，或只生成标题同义问法。
```

## 13. 排序分、置信度与候选问题点击

业界推荐做法：

```text
多路召回分数不可直接比较：dense、sparse、BM25/keyword 的原始分数尺度不同。
融合排序使用 RRF：RRF 基于排名位置融合，不依赖各召回器原始分数可比。
重排分用于相关性判断：reranker_score 更适合判断候选是否足够接近用户问题。
业务加权只影响排序：doc_type、意图权重用于调整候选顺序，不作为命中置信度。
```

本项目落地规则：

```text
ranking_score = rerank_score * doc_type_weight
用途：只用于排序、业务去重后保留最高排序候选。

confidence = calibrated_rerank_score
用途：只用于判断是否命中、是否 fallback。

禁止使用 ranking_score / final_score 计算 confidence。
原因：ranking_score 可能因为 doc_type_weight 超过 1，若再用固定公式归一化，会把高相关候选误压低。
```

命中判断：

```text
1. 前端传 candidateId：
   按 id 直接读取 FAQ。
   FAQ 必须满足 enabled=true、searchEnabled=true、status=active、sourceUrl 合法。
   通过校验后直接命中，confidence=1.0。

2. 用户 query 与 Top1 FAQ 标准问题完全一致：
   normalize(query) == normalize(faq.question) 时强命中。
   confidence = max(rerank_score, 0.95)。

3. 普通问题：
   confidence = clamp(rerank_score, 0, 1)。
   confidence < 0.65 时 fallback。

4. doc_type_weight：
   只写入 ranking_score。
   operation_guide、fee_standard 等加权不改变 confidence。
```

候选问题返回：

```json
{
  "suggestedQuestions": ["如何查看自己申请的价格保护记录？"],
  "suggestedQuestionCandidates": [
    {
      "id": "jd_help_292_553",
      "question": "如何查看自己申请的价格保护记录？",
      "score": 0.96,
      "rankingScore": 1.20,
      "docType": "operation_guide",
      "sourceUrl": "https://help.jd.com/user/issue/292-553.html"
    }
  ]
}
```

前端点击候选问题时：

```text
优先传 candidateId。
不要只把候选问题文本再次作为普通 query 提交。
原因：candidateId 是标准问题的稳定标识，可以避免再次检索时受召回波动、阈值和文本改写影响。
```

## 14. 百炼模型配置

当前运行时只保留百炼 / DashScope API，不再内置本地 BGE 模型分支。

```text
embedding：百炼 text-embedding-v4。
rerank：百炼 qwen3-rerank。
sparse：本地 hash lexical 表示。
```

推荐在 `.env` 中配置：

```env
BAILIAN_API_KEY=
# 已使用 DashScope 命名时，也可配置 DASHSCOPE_API_KEY。
DASHSCOPE_API_KEY=
BAILIAN_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BAILIAN_EMBEDDING_MODEL=text-embedding-v4
BAILIAN_EMBEDDING_DIMENSION=1024
BAILIAN_EMBEDDING_BATCH_SIZE=10
BAILIAN_EMBEDDING_TIMEOUT_SECONDS=60

BAILIAN_RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-api/v1
BAILIAN_RERANK_MODEL=qwen3-rerank
BAILIAN_RERANK_TIMEOUT_SECONDS=60
```

实现约束：

```text
API key 只放在 .env 或环境变量，不写入代码和文档示例。
BAILIAN_EMBEDDING_DIMENSION 必须和 Milvus dense_vector 维度一致。
BAILIAN_EMBEDDING_BATCH_SIZE 第一版按 text-embedding-v4 单次 10 条设置。
如果后续调整 embedding 维度，需要重建向量集合并重新入库。
百炼 embedding 只提供 dense vector 时，sparse_vector 第一版继续使用本地 hash lexical 表示。
重排服务不可用时，检索链路可降级为本地 overlap reranker，但不依赖本地模型。
如需使用 gte-rerank-v2，可只调整 BAILIAN_RERANK_MODEL。
```

## 15. 验收指标

准备 50-100 条非标准问法测试集。

示例：

```text
企微能不能用网银？
企业微信能用什么付款？
退货邮费谁出？
E卡能开发票吗？
白条退款多久到账？
买贵了能补差价吗？
企业金采怎么改手机号？
数电票 XML 打不开怎么办？
```

指标：

```text
Recall@5
MRR@10
source_url 命中正确率
历史规则误召回率
无答案兜底率
```

## 16. v1 落地顺序

```text
1. 新增 configs/jd_help_synonyms.yaml。
2. 清洗产物增加 canonical_terms / synonym_terms / similar_questions。
3. 入库时增强 index_text。
4. 查询层实现 normalize + synonym expand。
5. 查询层实现最多 3 条 rewrite query。
6. Dense + BM25 多路召回。
7. RRF 融合 + reranker。
8. parent_id / duplicate_group_id 业务去重。
9. 用非标准问法测试集验收。
```

当前代码落地入口：

```text
清洗产物导入：POST /admin/ingest/import
重建索引任务：POST /admin/ingest/build-index
任务查询：GET /admin/ingest/tasks/{task_id}
```

构建索引时：

```text
Milvus dense_vector 使用 chunk.embeddingText。
Milvus sparse_vector 使用 chunk.indexText 的本地 lexical 表示。
Elasticsearch 使用 chunk.indexText / rerankText / question 做关键词召回。
```

检索时：

```text
查询先经过 normalize、synonym expand、rewrite。
Dense 使用 normalized_query + rewrite_queries。
BM25 使用 expanded_query + rewrite_queries。
候选经过 RRF、字段过滤、reranker、doc_type 加权、业务去重后返回 topK。
```

## 17. 暂不做事项

```text
v1 不强制启用 sparse vector。
v1 不批量生成 similar_questions。
v1 不启用 ColBERT / multi-vector。
v1 不让历史规则默认参与普通检索。
```
