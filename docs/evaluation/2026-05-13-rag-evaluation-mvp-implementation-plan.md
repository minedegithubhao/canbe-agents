# RAG 检索评估 MVP 实现计划

## 1. 目标

基于已确认的 chunk 级检索评估设计和前端原型，实现一个可闭环的 RAG 检索评估 MVP。

该 MVP 要支持：

- 通过页面一键生成评估集。
- 支持 `single_chunk`、`multi_chunk`、`single_chunk + multi_chunk` 三种评测类型。
- 支持手动调整 `question_style`、`difficulty`、`category` 分布。
- 运行评估前实时校验 `source_hash`。
- 按 chunk 级标准答案计算检索指标。
- 在前端查看评估集、评估历史、评估详情和 Case 诊断详情。

第一版不做：

- 不接入 RAGAS。
- 不做 Faithfulness。
- 不做 Answer Accuracy。
- 不引入 LLM Judge。
- 不做复杂 RAG 配置页。
- 不做 FAQ 级主指标。

## 2. 当前状态判断

当前 `D:\IdeaProjects\canbe_agents\app\evaluation` 已有评估模块，但主要还是旧口径：

- schema 仍包含 FAQ 级字段，例如 `expected_retrieved_faq_ids`、`reference_answer`、`must_refuse`。
- service 仍通过 `chat_service.chat()` 做回答级评估。
- summary 仍是 `passRate`、`answerableHitRate`、`fallbackRate` 等回答质量指标。
- repository 目前把 run results 嵌入 `eval_runs.results`，不适合大量案例。
- 部分中文字符串存在 mojibake，需要在本次改造中避免继续引入乱码。

因此本次不是新增一套并行模块，而是把现有 `app\evaluation` 迁移为 chunk 检索评估 MVP。

## 3. 数据结构

### 3.1 eval_sets

集合名：`eval_sets`

```json
{
  "_id": "eval_20260513_001",
  "eval_set_id": "eval_20260513_001",
  "name": "jd_help_eval_v1",
  "description": "基于 clean FAQ chunk 生成的检索评估集",
  "source_path": "exports/jd_help_faq.cleaned.jsonl",
  "source_hash": "sha256...",
  "config": {
    "total_count": 100,
    "eval_type_distribution": {
      "single_chunk": 0.7,
      "multi_chunk": 0.3
    },
    "question_style_distribution": {
      "original": 0.3,
      "colloquial": 0.4,
      "synonym": 0.2,
      "abbreviated": 0.1
    },
    "difficulty_distribution": {
      "easy": 0.3,
      "medium": 0.5,
      "hard": 0.2
    },
    "category_distribution": {
      "订单相关": 0.35,
      "退款售后": 0.25,
      "物流配送": 0.2,
      "账户支付": 0.1,
      "发票相关": 0.1
    }
  },
  "summary": {
    "total": 100
  },
  "created_at": "2026-05-13T10:30:00+08:00",
  "created_by": "admin"
}
```

设计理由：

- `source_hash` 只用于运行前实时校验数据源是否变化。
- 不持久化 `stale_status`，避免和 `source_hash` 形成重复状态。
- `config` 保存生成时的抽样策略，保证评估集可复核。

### 3.2 eval_cases

集合名：`eval_cases`

```json
{
  "_id": "eval_20260513_001:faq_eval_000001",
  "case_id": "faq_eval_000001",
  "eval_set_id": "eval_20260513_001",
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
  "created_at": "2026-05-13T10:30:00+08:00"
}
```

设计理由：

- `expected_retrieved_chunk_ids` 是计算 Hit@K、Context Recall@K、MRR@K、Precision@ConfiguredK、Precision@EffectiveK 的标准答案。
- `reference_contexts` 用于前端 Case 诊断详情展示，不用于第一版 LLM Judge。
- `parent_faq_id` 只做业务追溯，不作为主评估口径。

### 3.3 eval_runs

集合名：`eval_runs`

```json
{
  "_id": "run_20260513_001",
  "run_id": "run_20260513_001",
  "eval_set_id": "eval_20260513_001",
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
  "created_at": "2026-05-13T11:00:00+08:00"
}
```

设计理由：

- 只保存 run 级配置和整体 summary。
- 不再把大量 case result 嵌入 `eval_runs`。

### 3.4 eval_run_results

集合名：`eval_run_results`

```json
{
  "_id": "run_20260513_001:faq_eval_000001",
  "run_id": "run_20260513_001",
  "eval_set_id": "eval_20260513_001",
  "case_id": "faq_eval_000001",
  "question": "下单后还能改规格吗？",
  "eval_type": "single_chunk",
  "question_style": "colloquial",
  "difficulty": "medium",
  "category": "订单相关",
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
    "expected_chunk_ids": ["chunk_订单相关_2_001"],
    "retrieved_chunk_ids": ["chunk_物流配送_9_001", "chunk_订单相关_2_001"],
    "matched_chunk_ids": ["chunk_订单相关_2_001"],
    "retrieved_contexts": [
      {
        "chunk_id": "chunk_物流配送_9_001",
        "parent_faq_id": "FAQ_物流配送_9",
        "score": 0.81,
        "matched": false,
        "content": "商品出库后物流信息通常在 24 小时内更新..."
      },
      {
        "chunk_id": "chunk_订单相关_2_001",
        "parent_faq_id": "FAQ_订单相关_2",
        "score": 0.77,
        "matched": true,
        "content": "订单未支付可取消重拍..."
      }
    ],
    "failure_reasons": []
  },
  "created_at": "2026-05-13T11:00:00+08:00"
}
```

设计理由：

- result 拆表后可以支持大量案例。
- `retrieved_contexts` 支持前端 Case 诊断抽屉。
- `failure_reasons` 用于快速筛选未命中、低召回、低排序、`effective_k = 0`、噪声过多。

## 4. 指标计算

记号：

- `E_i`：第 i 个 case 的期望 chunk 集合。
- `R_i`：第 i 个 case 经过阈值过滤后、实际送入评估的有序 chunk 列表。
- `CK`：配置的 `configured_k`。
- `EK_i = |R_i|`：第 i 个 case 的 `effective_k`。
- `N`：参与评估的 case 数。

单 case 指标：

- `hit_at_k = 1`，当 `R_i ∩ E_i` 非空；否则为 `0`。
- `context_recall_at_k = |R_i ∩ E_i| / |E_i|`。
- `mrr_at_k = 1 / rank(first matched chunk)`；无命中时为 `0`。
- `precision_at_configured_k = |R_i ∩ E_i| / CK`。
- `precision_at_effective_k = |R_i ∩ E_i| / EK_i`；当 `EK_i = 0` 时为 `0`。

整体指标：

- `Hit@K = sum(hit_at_k) / N`
- `Context Recall@K = sum(context_recall_at_k) / N`
- `MRR@K = sum(mrr_at_k) / N`
- `Precision@ConfiguredK = sum(precision_at_configured_k) / N`
- `Precision@EffectiveK = sum(precision_at_effective_k) / N`
- `avg_effective_k = sum(EK_i) / N`
- `zero_context_rate = count(EK_i = 0) / N`

## 5. 后端 API 契约

FastAPI 后端保留现有 `evaluation_api.router`，对外通过 blog server 或前端代理映射到 `/api/v1/rag-evaluation`。

### 5.1 生成评估集

`POST /admin/eval-sets/generate`

Request:

```json
{
  "name": "jd_help_eval_v1",
  "total_count": 100,
  "source_path": "exports/jd_help_faq.cleaned.jsonl",
  "eval_type_distribution": {
    "single_chunk": 0.7,
    "multi_chunk": 0.3
  },
  "question_style_distribution": {
    "original": 0.3,
    "colloquial": 0.4,
    "synonym": 0.2,
    "abbreviated": 0.1
  },
  "difficulty_distribution": {
    "easy": 0.3,
    "medium": 0.5,
    "hard": 0.2
  },
  "category_distribution": {
    "订单相关": 0.35,
    "退款售后": 0.25,
    "物流配送": 0.2,
    "账户支付": 0.1,
    "发票相关": 0.1
  }
}
```

Response:

```json
{
  "ok": true,
  "eval_set_id": "eval_20260513_001",
  "summary": {
    "total": 100
  }
}
```

### 5.2 评估集列表

`GET /admin/eval-sets?limit=50&skip=0`

Response:

```json
{
  "items": [
    {
      "eval_set_id": "eval_20260513_001",
      "name": "jd_help_eval_v1",
      "source_path": "exports/jd_help_faq.cleaned.jsonl",
      "source_hash": "sha256...",
      "summary": {
        "total": 100
      },
      "created_at": "2026-05-13T10:30:00+08:00"
    }
  ]
}
```

### 5.3 开始评估

`POST /admin/eval-sets/{eval_set_id}/runs/start`

Request:

```json
{
  "configured_k": 5,
  "retrieval_top_n": 20,
  "similarity_threshold": 0.72,
  "rerank_enabled": true
}
```

Response:

```json
{
  "ok": true,
  "run_id": "run_20260513_001",
  "eval_set_id": "eval_20260513_001",
  "summary": {
    "total": 100,
    "hit_at_k": 0.86,
    "context_recall_at_k": 0.79,
    "mrr_at_k": 0.68,
    "precision_at_configured_k": 0.31,
    "precision_at_effective_k": 0.52,
    "avg_effective_k": 3.2,
    "zero_context_rate": 0.08
  }
}
```

如果 `source_hash` 不一致：

```json
{
  "ok": false,
  "code": "EVAL_SOURCE_CHANGED",
  "message": "评估集数据源已变化，请重新生成评估集后再运行评估。"
}
```

### 5.4 评估记录

`GET /admin/eval-sets/{eval_set_id}/runs?limit=20&skip=0`

Response:

```json
{
  "items": [
    {
      "run_id": "run_20260513_001",
      "eval_set_id": "eval_20260513_001",
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
      "created_at": "2026-05-13T11:00:00+08:00"
    }
  ]
}
```

### 5.5 评估详情

`GET /admin/eval-runs/{run_id}`

Response:

```json
{
  "run_id": "run_20260513_001",
  "eval_set_id": "eval_20260513_001",
  "rag_config": {},
  "summary": {},
  "created_at": "2026-05-13T11:00:00+08:00"
}
```

### 5.6 Case 结果列表

`GET /admin/eval-runs/{run_id}/results?page=1&page_size=50&filter=miss`

Response:

```json
{
  "items": [
    {
      "case_id": "faq_eval_000001",
      "question": "下单后还能改规格吗？",
      "eval_type": "single_chunk",
      "difficulty": "medium",
      "category": "订单相关",
      "metrics": {},
      "diagnostics": {}
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 50
}
```

### 5.7 删除评估集

`DELETE /admin/eval-sets/{eval_set_id}`

第一版建议级联删除：

- `eval_sets`
- `eval_cases`
- `eval_runs`
- `eval_run_results`

原因：MVP 阶段没有归档需求，保留孤儿 run 反而增加理解成本。

## 6. 后端实现任务

### Task 1：重构 schema

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\evaluation\schemas.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_generator.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_service.py`

内容：

- 删除旧的 FAQ/回答评估主字段。
- 新增 `EvalSetGenerateRequest`：
  - `name`
  - `total_count`
  - `source_path`
  - `eval_type_distribution`
  - `question_style_distribution`
  - `difficulty_distribution`
  - `category_distribution`
- 新增 `EvalCase`：
  - `case_id`
  - `eval_set_id`
  - `question`
  - `eval_type`
  - `question_style`
  - `difficulty`
  - `category`
  - `expected_retrieved_chunk_ids`
  - `reference_contexts`
- 新增 `EvalRunConfig`、`EvalRunSummary`、`EvalRunResult`。

验收：

- Pydantic 校验能拒绝未知 `eval_type`。
- 分布合计不是 1.0 时返回明确错误。
- 不再出现 `single_faq_equivalent`、`fallback_or_refusal` 作为默认 eval_type。

### Task 2：重构 generator

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\evaluation\generator.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_generator.py`

内容：

- 加载 `exports/jd_help_faq.cleaned.jsonl` 作为来源。
- 生成 `single_chunk` 案例时，选择一个目标 chunk。
- 生成 `multi_chunk` 案例时，选择同类别或同业务主题下多个目标 chunk。
- `question_style` 根据配置生成：
  - `original`
  - `colloquial`
  - `synonym`
  - `abbreviated`
- `difficulty` 根据配置落到 case 字段。
- `category` 根据传入分布抽样；默认分布来自 clean 数据真实分布。

注意：

- 目前 clean 文件可能是 FAQ 级数据，而检索是 chunk 级数据。实现时需要通过 `jd_help_faq.chunks.jsonl` 或 Mongo chunk 数据补齐 `chunk_id` 和 chunk content。
- 标准答案必须是 `expected_retrieved_chunk_ids`，不能退回 FAQ ID。

验收：

- `single_chunk` case 的 `expected_retrieved_chunk_ids` 长度为 1。
- `multi_chunk` case 的 `expected_retrieved_chunk_ids` 长度大于 1。
- 生成数量和分布比例校验通过。
- 生成的中文内容不出现 mojibake。

### Task 3：新增指标计算模块

文件：

- 新建：`D:\IdeaProjects\canbe_agents\app\evaluation\metrics.py`
- 新建或修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_metrics.py`

内容：

- 实现单 case 指标：
  - `hit_at_k`
  - `context_recall_at_k`
  - `mrr_at_k`
  - `precision_at_configured_k`
  - `precision_at_effective_k`
- 实现整体 summary：
  - `hit_at_k`
  - `context_recall_at_k`
  - `mrr_at_k`
  - `precision_at_configured_k`
  - `precision_at_effective_k`
  - `avg_effective_k`
  - `zero_context_rate`
- 实现 failure reason：
  - `miss`
  - `low_recall`
  - `low_rank`
  - `zero_effective_k`
  - `too_many_noise_chunks`

验收：

- 多答案 chunk 的 MRR 使用第一个命中 chunk 的排名。
- `effective_k = 0` 时 `precision_at_effective_k = 0`。
- configured_k 和 effective_k 的 precision 分母不能混用。

### Task 4：调整 Retriever 评估边界

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\services\retrieval_service.py`
- 修改或新增：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_service.py`

内容：

- 不通过 `chat_service.chat()` 做评估。
- EvaluationService 直接调用 retriever，拿到排序后的 chunk 候选。
- 根据 `similarity_threshold` 过滤候选。
- 保留过滤后的有序列表作为 `R_i`。
- 结果中需要包含：
  - `chunk_id`
  - `faq_id`
  - `score`
  - `content`
  - `source_url`

建议实现方式：

- 优先新增 EvaluationService 内部的 `_retrieve_for_eval()` 适配函数。
- 尽量不大改 Retriever 主流程。
- 如果需要传入 `retrieval_top_n`，可以调用 `retriever.retrieve(query, top_k=retrieval_top_n)`，再在评估层做阈值过滤和截断。

验收：

- 评估运行不调用 LLM。
- 评估运行不生成 answer。
- 评估结果能拿到有序 chunk ids 和 score。

### Task 5：重构 repository

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\evaluation\repository.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_repository.py`

内容：

- `save_generated_eval_set()` 保存 `eval_sets` 和 `eval_cases`。
- `save_eval_run()` 只保存 run summary。
- 新增 `save_eval_run_results()` 批量保存 result。
- `list_eval_run_results()` 从 `eval_run_results` 集合分页读取。
- 新增 `delete_eval_set()` 级联删除。
- 更新 indexes：
  - `eval_sets: created_at`
  - `eval_cases: eval_set_id + case_id unique`
  - `eval_cases: eval_set_id + eval_type`
  - `eval_cases: eval_set_id + difficulty`
  - `eval_cases: eval_set_id + question_style`
  - `eval_cases: eval_set_id + category`
  - `eval_runs: eval_set_id + created_at`
  - `eval_run_results: run_id + case_id unique`
  - `eval_run_results: run_id + metrics.hit_at_k`
  - `eval_run_results: run_id + metrics.context_recall_at_k`
  - `eval_run_results: run_id + diagnostics.effective_k`

验收：

- `eval_run_results` 不再嵌入 `eval_runs`。
- 大量 results 分页读取可用。
- `_id` 和业务 ID 字段保持一致策略。

### Task 6：重构 service

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\evaluation\service.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_service.py`

内容：

- `generate()` 保存新结构评估集。
- `start_eval_run()`：
  - 读取 eval_set。
  - 实时计算 `source_path` 当前 hash。
  - hash 不一致则拒绝运行。
  - 读取所有 cases。
  - 调用 retriever 获取候选 chunk。
  - 计算单 case metrics。
  - 保存 `eval_runs`。
  - 批量保存 `eval_run_results`。
  - 返回 summary。
- `list_eval_runs()` 返回 run summary。
- `list_eval_run_results()` 支持分页和筛选。
- `delete_eval_set()` 级联删除。

验收：

- source_hash 变化时不运行。
- 每个 result 都有 metrics 和 diagnostics。
- summary 与 case 级指标平均值一致。

### Task 7：调整 API

文件：

- 修改：`D:\IdeaProjects\canbe_agents\app\evaluation\api.py`
- 修改：`D:\IdeaProjects\canbe_agents\tests\evaluation\test_api.py`

内容：

- 增加 `StartEvalRunRequest`。
- 增加删除接口。
- 调整 run detail 路由，避免 `/admin/eval-sets/runs/{run_id}` 这类路径歧义。
- 建议最终路由：
  - `POST /admin/eval-sets/generate`
  - `GET /admin/eval-sets`
  - `GET /admin/eval-sets/{eval_set_id}`
  - `DELETE /admin/eval-sets/{eval_set_id}`
  - `POST /admin/eval-sets/{eval_set_id}/runs/start`
  - `GET /admin/eval-sets/{eval_set_id}/runs`
  - `GET /admin/eval-runs/{run_id}`
  - `GET /admin/eval-runs/{run_id}/results`

验收：

- API 返回字段和前端类型一致。
- 错误响应能区分 source changed 和普通异常。

## 7. 前端实现任务

### Task 8：重构前端类型和 API

文件：

- 修改：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\types.ts`
- 修改：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\api.ts`

内容：

- 删除旧的 `passRate`、`answerableHitRate` 等字段。
- 新增 eval set、generate payload、run summary、run result、case diagnostics 类型。
- API 对齐后端新契约。

验收：

- TypeScript 不再引用旧评估字段。
- 页面能用新 summary 字段渲染。

### Task 9：实现评估集 Table 主页面

文件：

- 修改：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\rag-evaluation-page.tsx`

内容：

- 主页面展示评估集 Table。
- 顶部保留：
  - `一键生成评估集`
  - `刷新`
- Table 操作栏：
  - `开始评估`
  - `评估记录`
  - `删除`

验收：

- 首页不再显示旧卡片式生成/运行布局。
- 空数据时有清晰空状态。

### Task 10：实现一键生成评估集三步向导

文件建议：

- 新建：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\generate-eval-set-dialog.tsx`
- 修改：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\rag-evaluation-page.tsx`

内容：

- 步骤 1：基础信息。
- 步骤 2：抽样策略。
- 步骤 3：生成预览与确认。
- `category` 类别选项 MVP 阶段写死在前端。
- `category` 默认比例来自当前 RAG 数据真实分布。如果后端第一版还没有统计接口，则前端先使用写死默认比例，并在文案中标明“默认来自当前 RAG 分类统计”。

验收：

- 分布合计不是 100% 时，不能进入下一步。
- `single_chunk + multi_chunk` 才展示 eval_type 比例输入。
- 生成预览能展示预计数量和示例结构。

### Task 11：实现评估记录弹层

文件建议：

- 新建：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\eval-run-history-dialog.tsx`

内容：

- 展示某个 eval_set 的 run 列表。
- 列包括：
  - Run ID
  - 时间
  - Hit@K
  - Context Recall@K
  - MRR@K
  - P@CK
  - P@EK
  - 操作：详情

验收：

- 点击评估记录只展示当前 eval_set 的历史 run。
- 点击详情进入评估详情弹层。

### Task 12：实现评估详情弹层和 Case 诊断抽屉

文件建议：

- 新建：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\eval-run-detail-dialog.tsx`
- 新建：`D:\IdeaProjects\blog\canbe_blog_web\src\modules\rag-evaluation\components\case-diagnostics-drawer.tsx`

内容：

- 评估详情弹层采用已确认原型：
  - 整体指标
  - 诊断筛选
  - Case 明细
- Case 诊断抽屉展示：
  - 问题
  - 基础信息
  - 本 Case 指标
  - 期望召回 chunks
  - 实际召回 chunks
  - 诊断结论

验收：

- 能从整体指标下钻到具体失败 case。
- 能看清 expected chunk 和 retrieved chunk 的差异。
- 支持筛选未命中、低召回、低排序、`effective_k = 0`。

## 8. 验证计划

### 后端测试命令

在 `D:\IdeaProjects\canbe_agents` 执行：

```powershell
venv\Scripts\python.exe -m pytest tests\evaluation -q
```

如果当前使用 `.venv`：

```powershell
.venv\Scripts\python.exe -m pytest tests\evaluation -q
```

### 前端测试命令

在 `D:\IdeaProjects\blog\canbe_blog_web` 执行：

```powershell
npm run lint
npm run build
```

### 联调验证

1. 启动 `canbe_agents` dev 环境。
2. 启动 `canbe_blog_server` dev 环境。
3. 启动 `canbe_blog_web` dev 环境。
4. 访问 `http://127.0.0.1:8802/dashboard/rag-evaluation`。
5. 生成 20 条评估集。
6. 运行评估。
7. 查看评估记录。
8. 打开评估详情。
9. 打开失败 case 的诊断抽屉。

验收标准：

- 生成评估集成功。
- source_hash 未变化时可以运行。
- source_hash 变化时拒绝运行。
- summary 指标和 result 明细一致。
- 前端能从评估集列表一路下钻到 case 诊断。
- 页面无中文乱码。

## 9. 推荐执行顺序

推荐顺序：

1. Task 1 schema
2. Task 3 metrics
3. Task 2 generator
4. Task 5 repository
5. Task 6 service
6. Task 7 API
7. Task 8 前端类型和 API
8. Task 9 主页面 Table
9. Task 10 生成向导
10. Task 11 评估记录弹层
11. Task 12 评估详情和 Case 诊断
12. 联调验证

推荐理由：

- 指标模块越早独立，越容易保证评估结果可信。
- 后端契约稳定后再做前端，能减少 mock 数据返工。
- 前端先 Table，再弹窗，再详情，符合用户实际操作路径。

## 10. 风险点

### 风险 1：clean 数据和 chunk 数据映射不完整

风险：

- 如果 `cleaned.jsonl` 只有 FAQ ID，没有 chunk ID，就无法直接生成 chunk 级标准答案。

处理：

- 生成器必须读取 `jd_help_faq.chunks.jsonl` 或 Mongo chunks，建立 FAQ 到 chunk 的映射。
- 不能用 FAQ ID 冒充 chunk ID。

### 风险 2：Retriever 当前会按业务去重

风险：

- `group_by_business()` 可能导致同一 FAQ 下多个 chunk 被压缩为一个结果，影响 `multi_chunk` 评估。

处理：

- MVP 先接受当前检索链路的真实行为。
- 如果 `multi_chunk` 大量低召回，需要单独评审是否为去重策略导致。
- 不在第一版评估里绕过主检索链路，否则评估结果不能反映线上真实表现。

### 风险 3：阈值字段来源不稳定

风险：

- 当前 Retriever 返回的 `Candidate.final_score` 可能来自 rerank、RRF 或 ranking_score，不一定是标准相似度。

处理：

- 第一版明确 `similarity_threshold` 实际作用于 `Candidate.final_score`。
- 前端文案暂时写成“得分阈值”，不要写成严格的 embedding 相似度。

### 风险 4：中文 mojibake

风险：

- 当前部分 Python 文件和测试已有中文乱码，继续复制会扩大问题。

处理：

- 新增或修改的中文内容统一 UTF-8。
- 测试数据尽量使用正常中文，避免复制旧 mojibake 字符串。

## 11. 是否可以开始编码

建议在你确认本计划后开始编码。

我的建议是先实现后端 Task 1 到 Task 7，后端测试通过后再进入前端 Task 8 到 Task 12。
