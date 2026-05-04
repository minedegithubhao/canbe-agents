# 京东帮助中心 FAQ 导出规则

更新时间：2026-04-30

## 1. 页面范围

入口页：

```text
https://help.jd.com/user/issue.html
```

允许访问的页面类型：

```text
分类页：https://help.jd.com/user/issue/list-*.html
详情页：https://help.jd.com/user/issue/*-*.html
```

`list-*.html` 包含如下形式：

```text
list-81.html
list-81-100.html
list-944.html
list-944-945.html
```

分类页 URL 正则：

```regex
^https://help\.jd\.com/user/issue/list-\d+(?:-\d+)?\.html$
```

详情页 URL 正则：

```regex
^https://help\.jd\.com/user/issue/\d+-\d+\.html$
```

## 2. 分类页处理

分类页只负责发现链接，不作为 FAQ 的最终分类来源。

分类页分三种情况：

```text
有 FAQ：
  只解析主内容区 #all-ques-tab .help_list 中的详情页链接。

无 FAQ 但有子分类：
  继续访问子分类页，不生成 FAQ。

无 FAQ 且无子分类：
  记入 empty_categories 报告，不生成 FAQ。
```

详情页链接必须限定在主内容区：

```css
#all-ques-tab .help_list a[href]
```

不要从全页面泛匹配详情页链接，避免混入页脚、推荐问题和广告区域链接。

## 3. 详情页分类

每个 FAQ 的分类信息必须严格来自详情页自己的面包屑和详情页脚本分类节点，不使用分类页推断结果。

详情页面包屑通常如下：

```html
<div class="breadcrumb">
  <span id="sLevel1"></span>
  >
  <a href="//help.jd.com/user/issue/list-53.html">
    <span id="sLevel2"></span>
  </a>
  > <a href="//help.jd.com/user/issue/list-53-57.html">拆分订单</a>
</div>
```

`sLevel1` 和 `sLevel2` 在原始 HTML 中常为空，需要根据详情页脚本补全：

```js
var catItem = $(".list-item[data-id=53]");
$('#sLevel2').html(catItem.attr('data-name'));
$('#sLevel1').html(catItem.attr('data-parent-name'));
```

再在详情页左侧分类树中查找同一节点：

```html
<li class="list-item"
    data-id="53"
    data-name="订单拆分"
    data-parent-name="订单百事通">
```

最终分类规则：

```text
category_l1 = catItem.data-parent-name
category_l2 = catItem.data-name
category_l3 = 面包屑第三段文本
```

如果详情页面包屑没有第三段：

```text
category_l3 = 全部
```

## 4. 分类示例

详情页：

```text
https://help.jd.com/user/issue/945-4232.html
```

分类结果：

```json
{
  "category_l1": "购物指南",
  "category_l2": "用户协议",
  "category_l3": "注册协议"
}
```

详情页：

```text
https://help.jd.com/user/issue/57-127.html
```

分类结果：

```json
{
  "category_l1": "订单百事通",
  "category_l2": "订单拆分",
  "category_l3": "拆分订单"
}
```

空分类页：

```text
https://help.jd.com/user/issue/list-52.html
```

该页面 FAQ 主内容区为空，但存在子分类：

```text
https://help.jd.com/user/issue/list-52-65.html
```

处理结果：

```text
不生成 FAQ。
继续访问子分类页。
可写入 empty_categories 报告。
```

## 5. 正文解析

详情页正文只解析：

```css
#pdfContainer .contxt
```

字段规则：

```text
question = .help-tit1 文本
answer_html = 去掉标题后的正文 HTML
answer_text = HTML 转文本后的正文
```

不要纳入：

```text
顶部导航
左侧分类树
下载 PDF 按钮
投票区域
猜你感兴趣的问题
页脚
广告脚本
```

## 6. 编码

京东帮助中心页面当前返回：

```text
text/html;charset=GBK
```

处理规则：

```text
页面读取：GBK 解码
文件导出：UTF-8
```

## 7. 推荐输出

FAQ 主数据：

```json
{
  "id": "jd_help_57_127",
  "url": "https://help.jd.com/user/issue/57-127.html",
  "question": "我的订单，为什么会被拆分？",
  "answer": "...",
  "category_l1": "订单百事通",
  "category_l2": "订单拆分",
  "category_l3": "拆分订单",
  "page_date": "2018-11-14",
  "exported_at": "2026-04-30T..."
}
```

空分类报告：

```json
{
  "list_url": "https://help.jd.com/user/issue/list-52.html",
  "category_l1": "订单百事通",
  "category_l2": "订单锁定/解锁",
  "category_l3": "全部",
  "faq_count": 0,
  "child_list_count": 1,
  "type": "category_only"
}
```

核心原则：

```text
分类页负责发现链接。
详情页负责确定分类。
空分类只继续访问子分类或记录到报告，不生成 FAQ。
最终每条 FAQ 的 category_l1/category_l2/category_l3 必须来自该详情页的面包屑和脚本分类节点。
```
