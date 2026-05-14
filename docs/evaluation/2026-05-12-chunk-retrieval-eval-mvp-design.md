# RAG 评估 MVP 设计：Chunk 级检索指标

日期：2026-05-12
状态：待评审草案
范围：canbe_agents RAG 评估 MVP

## 1. 目标

MVP 只评估检索质量，回答一个工程问题：

> 在当前 topK + 相似度阈值过滤策略下，系统能不能召回正确 chunk、把正确 chunk 排在靠前位置，并让最终上下文尽量干净？

这一版不评估答案生成质量，不包含 Faithfulness、Answer Accuracy、RAGAS、LLM Judge。

## 2. 核心原则

1. Chunk 是主评估单元。
   FAQ id 只作为业务追溯字段。检索指标必须比较 expected chunk ids 和 retrieved chunk ids。

2. Eval set 是固定考卷。
   Eval set 记录 `source_path` 和 `source_hash`。每次运行前，后端重新计算当前 source 文件 hash。如果 hash 不一致，则拒绝运行，提示用户重新生成评估集。

3. 运行策略属于 eval run，不属于 eval case。
   `configured_k`、`retrieval_top_n`、`similarity_threshold`、rerank 配置都是 run 级配置字段，不是 case 字段。

4. MVP 只保留确定性指标。
   第一版所有指标都基于规则计算，速度快、结果稳定、不依赖 LLM Judge。

## 3. 指标设计

### 3.1 Case 级核心指标

每条 case result 只保存这 5 个核心指标：

```json
{
  "hit_at_k": 1,
  "context_recall_at_k": 1.0,
  "mrr_at_k": 0.5,
  "precision_at_configured_k": 0.2,
  "precision_at_effective_k": 0.5
}
```

### 3.2 Case 级诊断字段

诊断字段不是直接评分项，但用于解释评分结果：

```json
{
  "configured_k": 5,
  "effective_k": 2,
  "similarity_threshold": 0.72,
  "expected_chunk_ids": ["chunk_001"],
  "retrieved_chunk_ids": ["chunk_009", "chunk_001"],
  "matched_chunk_ids": ["chunk_001"]
}
```

字段含义：

- `configured_k`：run 配置的最大 chunk 数。对同一次 run 固定。
- `effective_k`：经过相似度阈值过滤后实际保留的 chunk 数。不同 case 可以不同。
- `expected_chunk_ids`：标准应该召回的 chunk ids。
- `retrieved_chunk_ids`：阈值过滤后最终保留的 chunk ids。
- `matched_chunk_ids`：expected 和 retrieved 的交集。

### 3.3 指标计算公式

定义：

- `E_i`：第 i 条 case 的 expected chunk ids。
- `R_i`：第 i 条 case 阈值过滤后的 retrieved chunk ids。
- `CK`：configured_k。
- `EK_i`：第 i 条 case 的 effective_k，也就是 `|R_i|`。
- `N`：本次 run 的 case 总数。

#### Hit@K

Case 级：

```text
hit_i@K = 1 if R_i 与 E_i 有交集 else 0
```

Run 级：

```text
Hit@K = sum(hit_i@K) / N
```

含义：最终保留的上下文中，是否至少包含一个正确 chunk。

#### Context Recall@K

Case 级：

```text
context_recall_i@K = |R_i 与 E_i 的交集| / |E_i|
```

Run 级：

```text
Context Recall@K = sum(context_recall_i@K) / N
```

含义：标准应该召回的 chunk 找回了多少。

#### MRR@K

Case 级：

```text
mrr_i@K = 1 / 第一个命中 chunk 的排名
```

如果没有命中：

```text
mrr_i@K = 0
```

Run 级：

```text
MRR@K = sum(mrr_i@K) / N
```

含义：第一个正确 chunk 是否排得靠前。

#### Precision@ConfiguredK

Case 级：

```text
precision_i@configured_k = |R_i 与 E_i 的交集| / CK
```

Run 级：

```text
Precision@ConfiguredK = sum(precision_i@configured_k) / N
```

含义：在固定 topK 配置口径下，正确 chunk 占比是多少。适合横向比较不同检索策略。

#### Precision@EffectiveK

Case 级：

```text
precision_i@effective_k = |R_i 与 E_i 的交集| / EK_i
```

如果 `EK_i = 0`：

```text
precision_i@effective_k = 0
```

Run 级：

```text
Precision@EffectiveK = sum(precision_i@effective_k) / N
```

含义：实际送给 LLM 的上下文有多干净。

### 3.4 Run 级额外汇总字段

Run summary 还应保存：

```json
{
  "avg_effective_k": 3.2,
  "zero_context_rate": 0.08
}
```

公式：

```text
avg_effective_k = sum(EK_i) / N
zero_context_rate = count(EK_i = 0) / N
```

含义：

- `avg_effective_k`：阈值过滤后平均还剩多少上下文。
- `zero_context_rate`：阈值是否过严，导致空上下文或 fallback。

## 4. Eval Set 字段

Eval set 只保存来源身份和生成元数据。

```json
{
  "_id": "eval_20260512_001",
  "eval_set_id": "eval_20260512_001",
  "name": "jd_help_eval_v1",
  "description": "基于 clean FAQ chunk 生成的检索评估集",
  "source_path": "exports/jd_help_faq.cleaned.jsonl",
  "source_hash": "sha256...",
  "config": {},
  "summary": {
    "total": 100
  },
  "created_at": "2026-05-12T10:30:00+08:00",
  "created_by": "admin"
}
```

字段理由：

| 字段 | 理由 |
|---|---|
| `eval_set_id` | 评估集唯一 ID，用于关联 eval cases 和 eval runs。 |
| `name` | 页面展示和用户识别。 |
| `description` | 说明这个评估集为什么存在。 |
| `source_path` | MVP 阶段的来源文件路径。 |
| `source_hash` | 生成评估集时的来源文件 hash，用于运行前实时校验。 |
| `config` | 生成配置，例如总数和分布。 |
| `summary.total` | 评估集案例总数。 |
| `created_at` | 排序和审计。 |
| `created_by` | 审计字段，默认 `admin`。 |

`_id` 规则：

```text
eval_sets._id = eval_set_id
```

原因：`eval_set_id` 是系统生成的稳定业务 ID，不需要修改。直接作为 Mongo `_id` 可以利用 Mongo 默认唯一索引，避免额外创建 `eval_set_id` 唯一索引。

删除字段：

- `status`
- `stale_status`
- `stale_checked_at`
- `runnable`
- `block_reason`
- `summary.validated`
- `summary.needs_review`
- `summary.rejected`

删除原因：MVP 每次运行前实时做 `source_hash` 校验，不持久化 stale 状态。

## 5. Eval Case 字段

Eval case 以 chunk 为主。

```json
{
  "_id": "eval_20260512_001:faq_eval_000001",
  "case_id": "faq_eval_000001",
  "eval_set_id": "eval_20260512_001",
  "question": "下单后还能改规格吗？",
  "eval_type": "single_chunk",
  "question_style": "colloquial",
  "difficulty": "medium",
  "category": "订单相关",
  "expected_retrieved_chunk_ids": ["chunk_订单相关_2_001"],
  "reference_contexts": [
    {
      "chunk_id": "chunk_订单相关_2_001",
      "parent_faq_id": "FAQ_订单相关_2",
      "title": "下单后还能改规格吗？",
      "content": "订单未支付可取消重拍；已支付未发货可联系客服尝试修改；已发货无法修改。",
      "source_url": "https://help.jd.com/user/issue/xxx.html"
    }
  ],
  "created_at": "2026-05-12T10:30:00+08:00"
}
```

字段理由：

| 字段 | 理由 |
|---|---|
| `case_id` | 评估集内唯一 case id。 |
| `eval_set_id` | 关联所属评估集。 |
| `question` | 送入 RAG 的查询问题。 |
| `eval_type` | 标准证据形态。MVP 取值：`single_chunk`、`multi_chunk`。 |
| `question_style` | 问题生成方式。取值：`original`、`semantic_equivalent`、`colloquial`、`keyword_query`、`typo`、`alias`。 |
| `difficulty` | 难度标签。取值：`easy`、`medium`、`hard`。 |
| `category` | 业务分组，用于筛选和报表。 |
| `expected_retrieved_chunk_ids` | 检索指标的标准答案。 |
| `reference_contexts` | 可读的标准上下文，也为后续答案质量评估预留。 |
| `reference_contexts.chunk_id` | 标准 chunk id。 |
| `reference_contexts.parent_faq_id` | 业务追溯字段，不作为主指标口径。 |
| `reference_contexts.content` | 标准 chunk 文本，用于人工复核。 |
| `reference_contexts.source_url` | 来源追溯。 |
| `created_at` | 审计字段。 |

`_id` 规则：

```text
eval_cases._id = eval_set_id + ":" + case_id
```

原因：`case_id` 只要求在同一个 eval set 内唯一。拼接 `eval_set_id` 和 `case_id` 后，可以得到全局唯一 `_id`。

## 6. Eval Run 字段

运行配置和汇总结果保存在 run 级别。单条 case 运行结果不内嵌在 `eval_runs`，而是保存到独立的 `eval_run_results` collection。

```json
{
  "_id": "run_001",
  "run_id": "run_001",
  "eval_set_id": "eval_20260512_001",
  "rag_config": {
    "configured_k": 5,
    "retrieval_top_n": 20,
    "similarity_threshold": 0.72,
    "rerank_enabled": true
  },
  "summary": {
    "total": 100,
    "hit_at_k": 0.86,
    "context_recall_at_k": 0.79,
    "mrr_at_k": 0.68,
    "precision_at_configured_k": 0.31,
    "precision_at_effective_k": 0.52,
    "avg_effective_k": 3.2,
    "zero_context_rate": 0.08
  },
  "created_at": "2026-05-12T11:00:00+08:00"
}
```

`_id` 规则：

```text
eval_runs._id = run_id
```

原因：`run_id` 是系统生成的稳定业务 ID，直接作为 Mongo `_id` 可以利用默认唯一索引，避免额外创建 `run_id` 唯一索引。

## 7. Eval Run Result 字段

每条 case 的运行结果单独保存，避免大量 case 时 `eval_runs` 单文档过大，也便于分页和失败复核。

```json
{
  "_id": "run_001:faq_eval_000001",
  "run_id": "run_001",
  "eval_set_id": "eval_20260512_001",
  "case_id": "faq_eval_000001",
  "question": "下单后还能改规格吗？",
  "metrics": {
    "hit_at_k": 1,
    "context_recall_at_k": 1.0,
    "mrr_at_k": 0.5,
    "precision_at_configured_k": 0.2,
    "precision_at_effective_k": 0.5
  },
  "diagnostics": {
    "configured_k": 5,
    "effective_k": 2,
    "similarity_threshold": 0.72,
    "expected_chunk_ids": ["chunk_001"],
    "retrieved_chunk_ids": ["chunk_009", "chunk_001"],
    "matched_chunk_ids": ["chunk_001"]
  },
  "created_at": "2026-05-12T11:00:00+08:00"
}
```

`_id` 规则：

```text
eval_run_results._id = run_id + ":" + case_id
```

原因：同一次 run 下，一个 case 只能有一条结果。拼接 `run_id` 和 `case_id` 后，可以得到全局唯一 `_id`。

## 8. Mongo Collection 与索引

MVP 使用 4 个 Mongo collection：

```text
1. eval_sets
2. eval_cases
3. eval_runs
4. eval_run_results
```

### 8.1 eval_sets

```js
db.eval_sets.createIndex({ created_at: -1 })
```

原因：评估集列表需要按创建时间倒序展示。

不需要额外创建 `{ eval_set_id: 1 }` 唯一索引，因为：

```text
eval_sets._id = eval_set_id
```

Mongo 默认已对 `_id` 建唯一索引。

### 8.2 eval_cases

```js
db.eval_cases.createIndex(
  { eval_set_id: 1, case_id: 1 },
  { unique: true }
)
```

原因：保证同一个评估集内 `case_id` 唯一，并支持快速查询某个评估集下的某条 case。

```js
db.eval_cases.createIndex({ eval_set_id: 1, eval_type: 1 })
```

原因：按评估类型筛选或统计 case，例如 `single_chunk`、`multi_chunk`。

```js
db.eval_cases.createIndex({ eval_set_id: 1, difficulty: 1 })
```

原因：按难度筛选或统计 case，例如 `easy`、`medium`、`hard`。

```js
db.eval_cases.createIndex({ eval_set_id: 1, question_style: 1 })
```

原因：按问题生成方式筛选或统计 case，例如 `original`、`colloquial`、`typo`、`alias`。

```js
db.eval_cases.createIndex({ eval_set_id: 1, category: 1 })
```

原因：按业务类别筛选或统计 case，例如订单、售后、会员等。

### 8.3 eval_runs

```js
db.eval_runs.createIndex({ eval_set_id: 1, created_at: -1 })
```

原因：查询某个评估集的运行历史，并按创建时间倒序展示。

不需要额外创建 `{ run_id: 1 }` 唯一索引，因为：

```text
eval_runs._id = run_id
```

Mongo 默认已对 `_id` 建唯一索引。

### 8.4 eval_run_results

```js
db.eval_run_results.createIndex(
  { run_id: 1, case_id: 1 },
  { unique: true }
)
```

原因：保证同一次 run 下，一个 case 只有一条结果，并支持快速查询某次 run 的某条 case 结果。

```js
db.eval_run_results.createIndex({ run_id: 1, "metrics.hit_at_k": 1 })
```

原因：快速筛选某次 run 中未命中的 case，例如 `metrics.hit_at_k = 0`。

```js
db.eval_run_results.createIndex({ run_id: 1, "metrics.context_recall_at_k": 1 })
```

原因：快速筛选召回不完整的 case，例如 `metrics.context_recall_at_k < 1`。

```js
db.eval_run_results.createIndex({ run_id: 1, "diagnostics.effective_k": 1 })
```

原因：快速筛选阈值过滤后上下文为空或过少的 case，例如 `diagnostics.effective_k = 0`，用于判断相似度阈值是否过严。

## 9. 运行前 source hash 校验

每次开始运行前：

```text
1. 读取 eval_set.source_path。
2. 计算当前 source 文件 hash。
3. 与 eval_set.source_hash 对比。
4. 如果一致，允许运行评估。
5. 如果不一致，拒绝运行，并提示用户重新生成评估集。
```

这个机制替代持久化 stale 字段。

## 10. 实施计划

1. 用 chunk 级字段替换当前 eval case schema。
2. 从 cleaned chunk 数据生成案例，而不是从 FAQ 级记录生成主指标。
3. Eval set metadata 保持最小字段，只基于 `source_path/source_hash`。
4. 运行前执行实时 source hash 校验。
5. 检索链路需要输出阈值过滤后的有序 chunk ids。
6. 计算 5 个确定性 case 指标。
7. 保存 case 诊断字段和 run 级 summary。
8. 更新前端文案和表格，展示 chunk 级指标。
9. 增加单测：指标公式、effective_k 边界、source hash 不一致、run summary 平均值。

## 11. MVP 不做的内容

MVP 明确不做：

- Faithfulness
- Answer Accuracy
- RAGAS 集成
- LLM Judge
- FAQ 级主指标
- dataset/version 表
- stale 状态持久化
- 自增主键
