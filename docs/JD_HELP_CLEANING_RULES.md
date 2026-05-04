# 京东帮助中心 FAQ 清洗规则

更新时间：2026-04-30

数据源文件：

```text
exports/jd_help_faq.md
```

本文件用于说明 `jd_help_faq.md` 后续进入知识库前的清洗规则。每条规则都给出来自当前导出文件的适用案例，便于逐条核对。

## 1. 先结构化为 FAQ 对象

规则：

```text
H1 -> category_l1
H2 -> category_l2
H3 -> category_l3
H4 -> question
url 行 -> url
H4 到下一个 H4/H3/H2/H1 之间的正文 -> answer_raw
```

清洗后建议字段：

```json
{
  "id": "jd_help_57_127",
  "url": "https://help.jd.com/user/issue/57-127.html",
  "category_l1": "订单百事通",
  "category_l2": "订单拆分",
  "category_l3": "拆分订单",
  "question": "我的订单，为什么会被拆分？",
  "answer_raw": "...",
  "answer_clean": "...",
  "page_date": "2018-11-14"
}
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:17344
分类路径：订单百事通 > 订单拆分 > 拆分订单
问题：我的订单，为什么会被拆分？
URL：https://help.jd.com/user/issue/57-127.html
```

原因：

```text
当前 Markdown 已经有稳定层级。先对象化，后续才能做检索、去重、分块、质量校验和入库。
```

清洗后效果：

```json
{
  "id": "jd_help_57_127",
  "url": "https://help.jd.com/user/issue/57-127.html",
  "category_l1": "订单百事通",
  "category_l2": "订单拆分",
  "category_l3": "拆分订单",
  "category_path": "订单百事通 > 订单拆分 > 拆分订单",
  "question": "我的订单，为什么会被拆分？",
  "answer_raw": "订单拆分有以下几种情况：\n\n1.您所购买的商品库房分布不同；\n\n2.您所购买的商品发货方不同（第三方卖家或京东发货）；\n\n3.您选择了有货先发；\n\n如有疑问，您可以联系客服为您解答。\n\n2018-11-14",
  "answer_clean": "订单拆分有以下几种情况：\n\n1. 您所购买的商品库房分布不同；\n2. 您所购买的商品发货方不同（第三方卖家或京东发货）；\n3. 您选择了有货先发。",
  "removed_boilerplate": ["如有疑问，您可以联系客服为您解答。"],
  "embedding_text": "订单百事通 > 订单拆分 > 拆分订单\n问题：我的订单，为什么会被拆分？\n答案：订单拆分有以下几种情况：\n\n1. 您所购买的商品库房分布不同；\n2. 您所购买的商品发货方不同（第三方卖家或京东发货）；\n3. 您选择了有货先发。",
  "index_text": "订单百事通 订单拆分 拆分订单 我的订单，为什么会被拆分？ 订单拆分 库房分布不同 发货方不同 第三方卖家 京东发货 有货先发 source_url:https://help.jd.com/user/issue/57-127.html",
  "page_date": "2018-11-14"
}
```

## 2. 分类字段必须保留

规则：

```text
保留 category_l1/category_l2/category_l3/category_path。
不要只保留 question 和 answer。
```

向量化或关键词索引时，可以拼接分类上下文：

```text
订单百事通 > 订单拆分 > 拆分订单
问题：我的订单，为什么会被拆分？
答案：...
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:17344
问题：我的订单，为什么会被拆分？
```

原因：

```text
很多问题标题本身很短，脱离分类后容易误召回。例如“运费是多少”“如何退款”在不同业务域下含义不同。
```

清洗后效果：

```json
{
  "category_l1": "订单百事通",
  "category_l2": "订单拆分",
  "category_l3": "拆分订单",
  "category_path": "订单百事通 > 订单拆分 > 拆分订单",
  "embedding_text": "订单百事通 > 订单拆分 > 拆分订单\n问题：我的订单，为什么会被拆分？\n答案：订单拆分有以下几种情况：\n\n1. 您所购买的商品库房分布不同；\n2. 您所购买的商品发货方不同（第三方卖家或京东发货）；\n3. 您选择了有货先发。",
  "index_text": "订单百事通 订单拆分 拆分订单 我的订单，为什么会被拆分？ 订单拆分 库房分布不同 发货方不同 第三方卖家 京东发货 有货先发 source_url:https://help.jd.com/user/issue/57-127.html",
  "removed_boilerplate": ["如有疑问，您可以联系客服为您解答。"]
}
```

字段区别：

```text
embedding_text：语义干净、自然语言化，给向量模型生成 dense embedding。
index_text：关键词更全，可加入 URL、标签、同义词、业务别名，给 Elasticsearch/BM25/关键词检索使用。
两个字段都必须保留。
```

## 3. 正文轻清洗，不做语义改写

规则：

```text
合并多余空行。
去掉空 span、空段落、残留样式。
保留编号、金额、日期、重量、地区、限制条件。
保留正文内来源链接。
不改写规则含义。
不删除免责、适用范围和例外条件。
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:639
问题：消费者购买京东自营商品运费收取标准
URL：https://help.jd.com/user/issue/109-188.html
```

该案例包含金额、重量、地区、续重规则等结构化规则信息。

原因：

```text
运费、售后、支付、协议类内容属于规则文本。清洗只能改善格式，不能改变边界。
```

清洗后效果：

```text
清洗前：
订单实付金额

含饮用水类商品及工业品

（饮料冲调-饮用水）

清洗后：
订单实付金额
含饮用水类商品及工业品（饮料冲调-饮用水）
不含饮用水类商品
限重
超出部分
续重费
```

同时保留：

```json
{
  "answer_raw": "第一节 运费总则\n\n一、自营商品基础运费6元...",
  "answer_clean": "第一节 运费总则\n\n一、自营商品基础运费6元，订单商品实付金额满59元，免基础运费...",
  "quality_flags": ["table_candidate"]
}
```

## 4. 表格型文本标记为 table_candidate

规则：

```text
正文中连续出现字段名、金额、重量、地区、规则列名时，标记 quality_flags 包含 table_candidate。
第一版可以保留为文本。
后续如需要展示或精确问答，再转为 Markdown 表格或结构化表格。
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:639
问题：消费者购买京东自营商品运费收取标准
字段特征：订单实付金额、限重、续重费、部分城市、其他地区
```

原因：

```text
原页面表格在 Markdown 中会变成多行碎片。直接改写容易出错，先标记再专项处理更稳。
```

清洗后效果：

```json
{
  "doc_type": "fee_standard",
  "quality_flags": ["table_candidate"],
  "table_parse_status": "pending",
  "answer_clean": "第一节 运费总则\n\n一、自营商品基础运费6元，订单商品实付金额满59元，免基础运费..."
}
```

说明：

```text
第一版不强制转表格，避免把复杂列关系转错。
如果后续需要精确计算运费，再单独生成 structured_tables。
```

## 5. 图片指代文本处理

规则：

```text
删除纯图片指代行：如下图、如图、见下图、图示如下、如下图所示。
句子有操作信息时，只删除图片指代短语，保留操作步骤。
如果答案明显依赖图片才能理解，标记 image_missing。
```

建议正则：

```regex
[（(]?(如下图|如图|见下图|点击下图|图示如下|如下图所示|详见下图)[）)]?[：:]?
```

适用案例 A：

```text
核对位置：exports/jd_help_faq.md:1189
问题：如何申请退货/换货？
原文含义：APP 端路径后带“如下图”
```

清洗方向：

```text
保留：打开京东APP客户端，点击 我的 > 退换/售后 > 申请售后。
删除：如下图
```

适用案例 B：

```text
核对位置：exports/jd_help_faq.md:4325
问题上下文：闪电退款标识说明
原文含义：是否支持以商品详情页标识为准，并提示“详见下图”
```

清洗方向：

```json
{
  "quality_flags": ["missing_image_context"]
}
```

原因：

```text
当前导出文件没有保留图片。“如下图”留在 answer_clean 中会让用户看到断裂答案。
```

清洗后效果 A：

```text
清洗前：
打开京东APP客户端，点击 我的>退换/售后>申请售后 （如下图），填写退换货信息后，即可提交。

清洗后：
打开京东APP客户端，点击 我的 > 退换/售后 > 申请售后，填写退换货信息后，即可提交。
```

清洗后效果 B：

```json
{
  "has_image_reference": true,
  "image_missing": true,
  "quality_flags": ["missing_image_context"]
}
```

## 6. 文档类型 doc_type 标记

规则：

```text
根据标题和正文给每条 FAQ 标记 doc_type。
```

建议取值：

```text
faq
operation_guide
service_intro
fee_standard
policy_rule
agreement
historical_rule
```

适用案例：

| doc_type | 核对位置 | 问题 |
|---|---:|---|
| operation_guide | exports/jd_help_faq.md:1179 | 如何申请退货/换货？ |
| service_intro | exports/jd_help_faq.md:224 | 京东配送服务说明（京邦达配送） |
| fee_standard | exports/jd_help_faq.md:639 | 消费者购买京东自营商品运费收取标准 |
| agreement | exports/jd_help_faq.md:20346 | 《京东用户服务协议》（2026年1月20日生效版本） |
| historical_rule | exports/jd_help_faq.md:20026 | （已失效）《京东用户服务协议》2023年5月5日-2024年5月17日 |

原因：

```text
操作步骤、服务介绍、收费规则、协议文本、历史规则的使用风险不同。RAG 回答时需要区别处理。
```

清洗后效果：

```json
[
  {
    "question": "如何申请退货/换货？",
    "doc_type": "operation_guide"
  },
  {
    "question": "消费者购买京东自营商品运费收取标准",
    "doc_type": "fee_standard"
  },
  {
    "question": "《京东用户服务协议》（2026年1月20日生效版本）",
    "doc_type": "agreement"
  },
  {
    "question": "（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日",
    "doc_type": "historical_rule"
  }
]
```

## 7. 历史规则隔离

规则：

标题或分类中出现以下词时，标记为历史内容：

```text
已失效
失效
历史规则
有效期截止
旧版本
适用版本
```

建议字段：

```json
{
  "status": "expired",
  "search_enabled": false,
  "doc_type": "historical_rule"
}
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:20026
问题：（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日
URL：https://help.jd.com/user/issue/945-4098.html
```

原因：

```text
历史规则默认不能参与普通用户问题回答，否则可能把旧规则说成当前规则。
```

清洗后效果：

```json
{
  "question": "（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日",
  "doc_type": "historical_rule",
  "status": "expired",
  "search_enabled": false,
  "quality_flags": ["historical_content"]
}
```

检索效果：

```text
普通问答默认不召回。
用户明确询问“历史版本”“旧协议”“2023年版本”时才允许召回。
```

## 8. 日期字段拆分

规则：

不要只设置一个 `date`。日期至少拆成：

```text
page_date：正文末尾独立日期
effective_date：标题或正文中的生效日期
expired_date：标题或正文中的失效日期
exported_at：本次导出时间
```

适用案例 A：page_date

```text
核对位置：exports/jd_help_faq.md:17348
问题：我的订单，为什么会被拆分？
正文末尾日期：2018-11-14
```

适用案例 B：effective_date

```text
核对位置：exports/jd_help_faq.md:20346
问题：《京东用户服务协议》（2026年1月20日生效版本）
正文含：版本生效日期
```

适用案例 C：effective_date + expired_date

```text
核对位置：exports/jd_help_faq.md:20026
问题：（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日
```

建议结果：

```json
{
  "effective_date": "2023-05-05",
  "expired_date": "2024-05-17",
  "status": "expired"
}
```

原因：

```text
页面日期、规则生效日期、规则失效日期和数据导出日期是不同概念，混成一个 date 会导致版本判断错误。
```

清洗后效果 A：

```json
{
  "question": "我的订单，为什么会被拆分？",
  "page_date": "2018-11-14",
  "effective_date": null,
  "expired_date": null,
  "exported_at": "2026-04-30T..."
}
```

清洗后效果 B：

```json
{
  "question": "《京东用户服务协议》（2026年1月20日生效版本）",
  "page_date": null,
  "effective_date": "2026-01-20",
  "expired_date": null,
  "exported_at": "2026-04-30T..."
}
```

清洗后效果 C：

```json
{
  "question": "（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日",
  "effective_date": "2023-05-05",
  "expired_date": "2024-05-17",
  "status": "expired"
}
```

## 9. 长文档二次分块

规则：

```text
answer_clean <= 1200 字符：一条 FAQ 一个 chunk。
1200 < answer_clean <= 3000 字符：按段落、小标题轻分块。
answer_clean > 3000 字符：按章节、条款、编号强制分块。
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:23366
问题：（已失效）《京东隐私政策》2021年8月30日-2021年10月6日
正文长度：超长协议/政策文本
```

建议结构：

```json
{
  "parent_id": "jd_help_952_4090",
  "chunk_id": "jd_help_952_4090_003",
  "chunk_title": "第三章 ...",
  "chunk_text": "...",
  "source_url": "..."
}
```

原因：

```text
长协议直接作为一个向量块会稀释主题，也容易超过模型上下文。分块后检索更准确。
```

清洗后效果：

```json
{
  "id": "jd_help_xxx",
  "question": "（已失效）《京东隐私政策》2021年8月30日-2021年10月6日",
  "doc_type": "historical_rule",
  "quality_flags": ["long_policy_text", "historical_content"],
  "chunk_count": 12
}
```

子块示例：

```json
{
  "parent_id": "jd_help_xxx",
  "chunk_id": "jd_help_xxx_003",
  "chunk_title": "三、我们如何使用您的个人信息",
  "chunk_text": "...",
  "source_url": "https://help.jd.com/..."
}
```

## 10. 重复标题保守处理

规则：

```text
URL 不同的重复标题不直接删除。
正文 hash 完全相同：可标记 duplicate_of。
标题相同但正文不同：保留，并加入 related_items。
```

适用案例：

```text
核对位置 A：exports/jd_help_faq.md:25508
核对位置 B：exports/jd_help_faq.md:25570
重复标题：京东PLUS会员先享后付服务协议（现称“PLUS会员保你不赔服务“）(已失效）
```

原因：

```text
帮助中心可能保留同名但不同版本、不同适用范围的规则。只按标题去重会误删。
```

清洗后效果：

```json
[
  {
    "id": "jd_help_965_4549",
    "question": "京东PLUS会员先享后付服务协议（现称“PLUS会员保你不赔服务“）(已失效）",
    "duplicate_group_id": "dup_plus_pay_later_agreement",
    "duplicate_of": null
  },
  {
    "id": "jd_help_965_4550",
    "question": "京东PLUS会员先享后付服务协议（现称“PLUS会员保你不赔服务“）(已失效）",
    "duplicate_group_id": "dup_plus_pay_later_agreement",
    "duplicate_of": "jd_help_965_4549"
  }
]
```

说明：

```text
只有正文 hash 完全一致时才设置 duplicate_of。
如果正文不同，只设置 duplicate_group_id，不删除。
```

## 11. 短答案保留，但加完整上下文

规则：

```text
短答案不要因为字数少直接删除。
用于索引时必须拼接分类、问题和 URL。
```

适用案例：

```text
核对位置：exports/jd_help_faq.md:14
问题：自提订单是否收费（自提订单运费）？
```

原因：

```text
短答案可能是有效规则回答。删除会损失常见问题；但索引时如果没有分类上下文，召回容易混淆。
```

清洗后效果：

```json
{
  "question": "自提订单是否收费（自提订单运费）？",
  "quality_flags": ["short_answer"],
  "answer_clean": "京东自提订单运费规则与送货上门订单运费规则一致，详情请见京东订单运费收取标准。",
  "embedding_text": "配送方式 > 京东配送服务说明 > 上门自提\n问题：自提订单是否收费（自提订单运费）？\n答案：京东自提订单运费规则与送货上门订单运费规则一致，详情请见京东订单运费收取标准。",
  "index_text": "配送方式 京东配送服务说明 上门自提 自提订单是否收费 自提订单运费 京东订单运费收取标准"
}
```

## 12. 质量标记 quality_flags

规则：

清洗时不要只产出“成功/失败”，还要打质量标记：

```text
missing_image_context：正文依赖图片
table_candidate：疑似表格
long_policy_text：超长协议/政策
historical_content：历史内容
date_ambiguous：日期语义不明确
short_answer：短答案
```

适用案例：

| quality_flag | 核对位置 | 原因 |
|---|---:|---|
| missing_image_context | exports/jd_help_faq.md:1189 | 正文含“如下图” |
| table_candidate | exports/jd_help_faq.md:639 | 运费规则表格化 |
| long_policy_text | exports/jd_help_faq.md:23366 | 隐私政策长文本 |
| historical_content | exports/jd_help_faq.md:20026 | 标题含“已失效” |
| short_answer | exports/jd_help_faq.md:14 | 答案较短但有效 |

原因：

```text
质量标记能让后续入库、检索、人工复核和回答兜底有依据，而不是把所有内容当成同等质量。
```

清洗后效果：

```json
{
  "question": "如何申请退货/换货？",
  "quality_flags": ["missing_image_context"],
  "review_required": true
}
```

```json
{
  "question": "消费者购买京东自营商品运费收取标准",
  "quality_flags": ["table_candidate"],
  "review_required": false
}
```

```json
{
  "question": "（已失效）《京东用户服务协议》2023年5月5日-2024年5月17日",
  "quality_flags": ["historical_content", "long_policy_text"],
  "search_enabled": false
}
```

## 13. 客服兜底模板句剔除

规则：

```text
纯兜底客服句从 answer_clean 和 embedding_text 中剔除。
answer_raw 永远保留原文。
被剔除句子写入 removed_boilerplate。
带有条件、对象、流程差异、联系方式、审核规则的客服句不剔除。
```

建议模板：

```regex
如有疑问[，,]?(您)?可以联系.*客服.*[。.]?
如需帮助[，,]?(请)?联系.*客服.*[。.]?
详情可咨询.*客服.*[。.]?
具体.*可联系.*客服.*[。.]?
```

适用案例 A：应剔除

```text
核对位置：exports/jd_help_faq.md:17360
问题：我的订单，为什么会被拆分？
原文：如有疑问，您可以联系客服为您解答。
```

清洗后效果：

```json
{
  "question": "我的订单，为什么会被拆分？",
  "answer_raw": "订单拆分有以下几种情况：... 如有疑问，您可以联系客服为您解答。\n\n2018-11-14",
  "answer_clean": "订单拆分有以下几种情况：\n\n1. 您所购买的商品库房分布不同；\n2. 您所购买的商品发货方不同（第三方卖家或京东发货）；\n3. 您选择了有货先发。",
  "removed_boilerplate": ["如有疑问，您可以联系客服为您解答。"],
  "embedding_text": "订单百事通 > 订单拆分 > 拆分订单\n问题：我的订单，为什么会被拆分？\n答案：订单拆分有以下几种情况：\n\n1. 您所购买的商品库房分布不同；\n2. 您所购买的商品发货方不同（第三方卖家或京东发货）；\n3. 您选择了有货先发。",
  "index_text": "订单百事通 订单拆分 拆分订单 我的订单，为什么会被拆分？ 订单拆分 库房分布不同 发货方不同 第三方卖家 京东发货 有货先发 source_url:https://help.jd.com/user/issue/57-127.html"
}
```

适用案例 B：应保留

```text
核对位置：exports/jd_help_faq.md:633
原文：若您长时间未收货，京东自营商品建议您联系京东在线客服帮您查询原因，第三方卖家商品请直接联系商家客服处理。
```

清洗后效果：

```json
{
  "removed_boilerplate": [],
  "answer_clean": "若您长时间未收货，京东自营商品建议您联系京东在线客服帮您查询原因，第三方卖家商品请直接联系商家客服处理。",
  "embedding_text": "配送方式 > 配送服务查询 > 全部\n问题：物流为何没有在指定时间到达？\n答案：若您长时间未收货，京东自营商品建议您联系京东在线客服帮您查询原因，第三方卖家商品请直接联系商家客服处理。",
  "index_text": "配送方式 配送服务查询 物流为何没有在指定时间到达 长时间未收货 京东自营 京东在线客服 第三方卖家 商家客服"
}
```

原因：

```text
纯兜底句信息密度低，且在大量 FAQ 中重复出现，会稀释嵌入向量的主题，让不同问题变得更相似。
但包含自营/第三方差异、联系方式、处理路径或业务条件的客服句有实际业务信息，不能删除。
```

## 14. 推荐产物

规则：

清洗后建议生成四类文件：

```text
exports/jd_help_faq.cleaned.jsonl
exports/jd_help_faq.chunks.jsonl
exports/jd_help_faq.cleaned.md
exports/jd_help_faq_quality_report.json
```

原因：

```text
jsonl 适合入库和索引，chunks 适合 RAG，cleaned.md 适合人工核对，quality_report 适合验收和回归检查。
```

清洗后效果：

```text
exports/jd_help_faq.cleaned.jsonl
  一行一个 FAQ 主对象，必须包含 answer_raw、answer_clean、embedding_text、index_text。

exports/jd_help_faq.chunks.jsonl
  一行一个检索块，长文档会拆成多个块；每个 chunk 也必须包含 embedding_text 和 index_text。

exports/jd_help_faq.cleaned.md
  人工可读版，去掉无效图片指代、纯兜底客服句和明显噪声。

exports/jd_help_faq_quality_report.json
  统计短答案、图片缺失、表格候选、历史规则、重复标题、剔除的客服兜底句等。
```

质量报告示例：

```json
{
  "faq_count": 853,
  "removed_boilerplate_count": 1,
  "removed_boilerplate_examples": [
    {
      "url": "https://help.jd.com/user/issue/57-127.html",
      "text": "如有疑问，您可以联系客服为您解答。"
    }
  ]
}
```

## 15. 总体原则

```text
结构先于改写。
保留原文，另存清洗文本。
规则文本只做格式清洗，不做含义改写。
历史内容默认隔离。
图片缺失要标记。
纯兜底客服句不进入 embedding_text。
长文档必须分块。
所有清洗结果都要能回到原 URL 和原 Markdown 行号核对。
```
