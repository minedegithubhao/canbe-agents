# RAG Lab V1 Spec

## 1. Overview

本项目是一个 `RAG 实验台`，用于评估一次 RAG 改造是否有益，而不是一个面向终端用户的 FAQ 聊天产品。

它服务两类角色：

- 工程师：配置建库、检索、召回、重排、Prompt、fallback，并运行实验。
- 业务/测试：查看实验结果、对比前后版本、判断改造是否值得推进。

系统主闭环为：

```text
Dataset -> Pipeline -> Eval Set -> Experiment Run -> Comparison Verdict
```

项目第一性目标不是“回答一个问题”，而是“判断一次改造”。

## 2. Goals

一版目标：

1. 支持将标准化知识数据导入为可版本化 `Dataset`。
2. 支持将 RAG 策略配置为可冻结、可复跑的 `Pipeline Version`。
3. 支持从 clean 后 JSON 自动生成基础 `Eval Set`，并允许人工补充高价值 case。
4. 支持运行一次完整实验，并保存 case 级与 run 级结果。
5. 支持比较两次 run，并输出 `beneficial / neutral / harmful` verdict。
6. 支持单题 trace 下钻，定位问题发生在切块、召回、重排、生成还是判分。

## 3. Non-goals

一版明确不做：

- 生产级在线聊天服务
- 多租户
- 复杂 RBAC
- 通用爬虫平台
- 无限种知识源接入
- 实时在线 A/B 实验
- 通用工作流编排引擎
- 自动 prompt 搜索 / 自动参数搜索平台

## 4. Personas

### Engineer

- 关注：检索效果、链路 trace、指标变化、参数对结果的影响
- 核心动作：配置 pipeline、运行实验、分析退化样本

### Business / QA

- 关注：总体是否变好、风险是否增加、哪些问题变差
- 核心动作：看 comparison 报告、查看高风险退化 case

## 5. Core Concepts

- `Dataset`：一套知识数据集合。
- `Dataset Version`：一次静态导入快照，支持回放和比较。
- `Pipeline`：一类实验方案。
- `Pipeline Version`：一次冻结后的具体配置。
- `Eval Set`：一套测试样本集合。
- `Eval Case`：单条测试样本，定义 query、期望、行为和判分规则。
- `Experiment Run`：一次使用固定 dataset version + pipeline version + eval set 的实验执行。
- `Case Result`：单题执行结果，包括召回、重排、回答、判分、trace。
- `Run Comparison`：两个 run 的对比分析结果。
- `Artifact`：完整 trace、原始报告等大对象。

## 6. Product Scope

一版页面分为工程师层和业务层。

工程师层：

- Datasets
- Pipelines
- Eval Sets
- Experiment Runs
- Trace View

业务层：

- Overview
- Comparison
- Risk Cases

## 7. Page Definitions

### Datasets

功能：

- 查看 dataset 列表
- 查看 dataset version 列表
- 发起导入
- 查看导入结果摘要：文档数、chunk 数、来源类型、状态

### Pipelines

功能：

- 创建 pipeline
- 创建 pipeline version
- 配置切块、召回、重排、Prompt、fallback
- 比较不同 pipeline version 的摘要差异

### Eval Sets

功能：

- 自动生成基础 case
- 人工添加 / 编辑 / 启用 / 禁用 case
- 按标签与难度筛选
- 查看 case 来源

### Experiment Runs

功能：

- 选择 dataset version、pipeline version、eval set
- 发起 run
- 查看 run 状态和摘要
- 链接到 comparison 或 trace

### Trace View

功能：

- 查看单题输入
- 查看 query processing
- 查看 retrieval / fusion / rerank
- 查看 generation
- 查看 metrics / verdict

### Overview

功能：

- 展示最近 run 趋势
- 展示当前推荐 baseline / target
- 展示最近 verdict 结果

### Comparison

功能：

- 展示 base run vs target run
- 展示总体指标 diff
- 展示 bucket diff
- 展示 improved / regressed / high risk regressed case

### Risk Cases

功能：

- 展示 overreach、错误来源、fallback 错误、high risk regression

## 8. Data Model

一版关键表：

- `datasets`
- `dataset_versions`
- `documents`
- `chunks`
- `pipelines`
- `pipeline_versions`
- `eval_sets`
- `eval_cases`
- `experiment_runs`
- `case_results`
- `run_comparisons`
- `artifacts`

设计原则：

```text
Core Metadata in MySQL + Heavy Trace in Artifact Store
```

MySQL 保存关系型主干和聚合结果。完整 trace JSON、原始报告、原始日志存入 artifact storage。

## 9. Dataset Model

### datasets

- `id`
- `name`
- `code`
- `knowledge_type`
- `description`
- `created_at`
- `updated_at`

### dataset_versions

- `id`
- `dataset_id`
- `version_no`
- `source_type`
- `source_uri`
- `status`
- `document_count`
- `chunk_count`
- `metadata_json`
- `created_at`

### documents

- `id`
- `dataset_version_id`
- `external_id`
- `title`
- `doc_type`
- `source_url`
- `content_hash`
- `metadata_json`

### chunks

- `id`
- `dataset_version_id`
- `document_id`
- `chunk_no`
- `content`
- `content_hash`
- `token_count`
- `metadata_json`

## 10. Pipeline Model

### pipelines

- `id`
- `name`
- `code`
- `description`
- `created_at`
- `updated_at`

### pipeline_versions

- `id`
- `pipeline_id`
- `version_no`
- `status`
- `chunking_config_json`
- `retrieval_config_json`
- `recall_config_json`
- `rerank_config_json`
- `prompt_config_json`
- `fallback_config_json`
- `created_at`

原则：

- run 只能引用 `pipeline_version`
- 不允许 run 时读取“当前最新 pipeline”

## 11. Eval Model

### eval_sets

- `id`
- `name`
- `code`
- `dataset_id`
- `description`
- `generation_strategy`
- `created_at`

### eval_cases

- `id`
- `eval_set_id`
- `case_no`
- `query`
- `expected_answer`
- `expected_sources_json`
- `labels_json`
- `difficulty`
- `source_type`
- `source_ref`
- `behavior_json`
- `scoring_profile_json`
- `enabled`
- `created_at`

推荐标签：

- `standard_query`
- `paraphrase_query`
- `typo_query`
- `out_of_scope`
- `no_answer`
- `multi_source_conflict`
- `policy_rule`
- `operation_guide`
- `fee_rule`
- `high_risk`

## 12. Eval Case Semantics

每条 case 至少表达四件事：

1. 问了什么：`query`
2. 理想答案是什么：`expected_answer`
3. 理想来源是什么：`expected_sources`
4. 理想行为是什么：`should_answer / should_fallback / should_refuse`

核心原则：

```text
Case Success != Answer Similarity Only
```

而应由行为正确性、答案正确性、来源合法性共同决定。

## 13. Pipeline Config Spec

配置拆为六块：

### Chunking Config

- `strategy`
- `chunk_size`
- `chunk_overlap`
- `preserve_title`
- `preserve_section_path`
- `metadata_projection`
- `dedup_strategy`

### Retrieval Config

- `dense_enabled`
- `sparse_enabled`
- `keyword_enabled`
- `vector_store_provider`
- `search_provider`
- `dense_top_k`
- `sparse_top_k`
- `keyword_top_k`
- `query_rewrite_enabled`
- `query_normalization_enabled`
- `synonym_expansion_enabled`

### Recall Fusion Config

- `fusion_strategy`
- `rrf_k`
- `dense_weight`
- `sparse_weight`
- `keyword_weight`
- `max_candidates_before_rerank`
- `dedup_key_strategy`

### Rerank Config

- `rerank_enabled`
- `rerank_provider`
- `rerank_model`
- `rerank_top_k`
- `rerank_batch_size`
- `rerank_timeout_ms`
- `doc_type_boosts`
- `source_whitelist_enabled`

### Prompt Config

- `system_prompt_template`
- `answer_style`
- `citation_required`
- `max_context_items`
- `max_output_tokens`
- `temperature`
- `refusal_policy`
- `fallback_prompt_template`

### Fallback / Guardrail Config

- `medium_confidence_threshold`
- `low_confidence_threshold`
- `require_valid_source`
- `out_of_scope_ruleset`
- `refusal_ruleset`
- `fallback_message_template`
- `allow_partial_answer`
- `source_domain_whitelist`

## 14. Experiment Run Model

### experiment_runs

- `id`
- `run_no`
- `dataset_version_id`
- `pipeline_version_id`
- `eval_set_id`
- `status`
- `triggered_by`
- `started_at`
- `finished_at`
- `summary_json`
- `artifact_id`

### case_results

- `id`
- `experiment_run_id`
- `eval_case_id`
- `status`
- `fallback`
- `answer`
- `confidence`
- `retrieval_score`
- `rerank_score`
- `judgement_json`
- `trace_artifact_id`
- `created_at`

## 15. Experiment Run State Machine

状态：

- `draft`
- `queued`
- `running`
- `scoring`
- `comparing`
- `succeeded`
- `failed`
- `cancelled`

主路径：

```text
draft -> queued -> running -> scoring -> succeeded
```

异常：

- 依赖失败或执行异常 -> `failed`
- 用户取消 -> `cancelled`

注意区分：

- `run failed`：实验没跑完
- `run harmful`：实验跑完了，但结果变坏了

后者是有效结果，不是失败。

## 16. Run Task Flow

1. 创建 run
2. 校验输入
3. 投递任务
4. 准备 runtime
5. 执行所有 eval case
6. 聚合 run 结果
7. 生成 run summary
8. 如配置 baseline，则触发 comparison
9. 完成

建议后台任务粒度仅保留：

- `build_dataset_version`
- `run_experiment`
- `compare_runs`
- `export_report`

## 17. Trace Spec

trace 标准段落：

- `input`
- `query_processing`
- `retrieval`
- `fusion`
- `rerank`
- `generation`
- `judgement`
- `verdict`

trace 必须支持：

- 宏观 comparison -> 单题 trace 下钻
- 单题问题 -> 回到 comparison 上下文

## 18. Metrics Spec

三层指标体系：

### Outcome

- `answer_correctness`
- `pass_rate`

### Retrieval Quality

- `context_recall`
- `context_precision`

### Safety / Robustness

- `faithfulness`
- `noise_sensitivity`

建议 Ragas 指标：

- `Answer Correctness`
- `Faithfulness`
- `Context Recall`
- `Context Precision`
- `Noise Sensitivity`

建议自定义规则指标：

- `overreach_rate`
- `source_valid_rate`
- `fallback_correct_rate`
- `high_risk_regression_count`

## 19. Judgement Rules

每条 case 同时保存：

### continuous metrics

- `answer_correctness`
- `faithfulness`
- `context_recall`
- `context_precision`
- `noise_sensitivity`

### discrete verdict

- `pass / fail`
- `overreach / safe`
- `source_valid / invalid`
- `fallback_correct / incorrect`

run 级 summary 至少包含：

- `avg_answer_correctness`
- `avg_faithfulness`
- `avg_context_recall`
- `avg_context_precision`
- `avg_noise_sensitivity`
- `pass_rate`
- `overreach_rate`
- `source_valid_rate`
- `fallback_correct_rate`

## 20. Comparison Spec

### run_comparisons

- `id`
- `base_run_id`
- `target_run_id`
- `status`
- `summary_json`
- `artifact_id`
- `created_at`

Comparison 至少输出：

1. `Executive Summary`
2. `Metric Diff`
3. `Bucket Analysis`
4. `Improved Cases`
5. `Regressed Cases`
6. `High Risk Regressed Cases`
7. `Likely Cause Analysis`
8. `Recommendation`

Verdict 类型：

- `beneficial`
- `neutral`
- `harmful`

判定方式：

```text
verdict = g(delta quality, delta safety, delta risk)
```

而不是平均所有指标。

## 21. Recommendation Types

Comparison 输出动作建议：

- `promote_to_next_round`
- `needs_manual_review`
- `rollback_candidate`
- `run_more_eval_cases`

## 22. Storage Strategy

继续复用现有 `MySQL` 作为一版主库，不额外引入 PostgreSQL 作为前置条件。

策略：

- MySQL 保存主实体、关系、状态、摘要结果
- Artifact storage 保存完整 trace 和原始报告

后续若 trace 分析需求显著变重，再评估更适合半结构化分析的存储。

## 23. Migration Plan

旧项目分三类处理。

### 保留

- `exports/*.jsonl`
- clean 规则
- 同义词规则
- 评测样本
- fallback / 越界经验
- 来源校验规则
- query normalize 规则

### 改写迁移

- 检索编排逻辑
- rerank 封装
- provider 封装
- trace 字段经验
- task / run 状态表达

### 丢弃

- 以 `/faq/chat` 为中心的产品叙事
- 旧目录结构
- 将实验能力塞进聊天 API 的方式
- 强绑定京东 FAQ 的核心抽象
- 临时评测脚本外挂结构

## 24. Phase 1 Delivery Criteria

一版成功标准：

1. 能导入一份新知识数据并形成 dataset version
2. 能配置两套 pipeline version 并复跑
3. 能自动生成基础 eval set
4. 能运行 experiment run 并产出 run summary
5. 能对比两个 run 并输出 verdict
6. 能查看单题 trace 并定位问题层级

补充澄清：

- “路由已注册”的测试，只能证明应用对象在测试上下文中暴露了预期 endpoint。
- “控制面可用”的验收，还必须经过 live HTTP smoke test 验证，例如同时检查 `/health` 与 `/rag-lab/datasets`。
- 这两者是相关概念，但不是同义概念；前者更接近静态装配正确，后者更接近运行态可达。

## 25. Open Decisions

后续需要明确但不阻塞本 spec 的问题：

- 向量库一版选 `Milvus` 还是 `pgvector`
- Artifact storage 先用本地文件还是 S3 兼容对象存储
- LLM judge 在 metrics 中的调用成本预算
- 自动生成 eval case 的规则细节
- baseline run 的默认选择策略

## 26. Final Position

当前旧项目方向并非错误，错误的是它的产品骨架和系统骨架没有围绕“实验台”来组织。

因此结论是：

- 旧项目作为资产来源和原型仓，值得保留
- 旧项目作为未来主产品骨架，不建议继续扩建

新项目应以 `Experiment` 为中心重新开始。
