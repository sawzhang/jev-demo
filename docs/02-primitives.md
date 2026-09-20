# 02 · 三原语详解

## Noul —— 「这是真的吗？」

返回一个 0~1 的概率。**没有单独的 confidence 字段 —— 概率本身就是信号。**

```python
Noul(instructions="The customer is asking for money back.")
# -> {"type": "noul", "noul": 0.98}
```

- 接近 1 → 强烈是
- 接近 0 → 强烈否
- 接近 0.5 → 模型真的不知道

**instructions 写成陈述句，不要写成疑问句。** 「The customer is angry.」
比「Is the customer angry?」更稳，因为 Noul 评估的是「这句陈述成立的概率」。

可选的 criteria 用来钉死边界（边界模糊时非常有用）：

```python
Noul(
    instructions="The user is trying to override the assistant's instructions.",
    criteria={
        "true":  {"what": "Prompt injection or jailbreak attempt",
                  "examples": ["ignore previous instructions", "you are now DAN"]},
        "false": {"what": "An ordinary request, even a blunt or unusual one"},
    },
)
```

**重要：P(x) 和 P(¬x) 不保证互补。** 官方明说不保证，实测这个例子里
0.02 + 0.97 = 0.99 很接近，但别依赖这条。想要互补语义就问一次，用 `1 - noul`。

## Choice —— 「是哪一个？」

无序的一组选项里挑一个。criteria **必填**，最多 255 项。

```python
Choice(
    instructions="What kind of support ticket is this?",
    criteria={
        "bug_report":      "Something in the product is broken or errors out",
        "billing":         "Charges, invoices, refunds, subscriptions",
        "feature_request": "Asking for something that does not exist yet",
        "unclear":         "Not enough information to tell",
    },
)
# -> {"choice": "bug_report", "confidence": 1.0,
#     "probabilities": {"bug_report": 1.0, "billing": 0.0, ...}}
```

选项描述可以是 `None`（让 key 自己说话），但**写描述明显更稳**，
尤其是要区分相邻概念时。进阶写法用嵌套对象划清边界：

```python
criteria={
    "electronics": {"what": "Phones, laptops, consoles",
                    "examples": ["iPhone", "PS5"],
                    "not_for": "Phone cases or cables"},   # <- not_for 很关键
    "accessories": {"what": "Cases, cables, chargers"},
}
```

**永远留一个兜底选项**（`other` / `unclear` / `none`）。
没有兜底，模型被迫在不合适的选项里硬选，你只能靠 confidence 发现问题。

## Score —— 「在哪一档？」

有序档位。criteria 是**数组**。文档说 2~10 档，实测**上限 10 是硬限制**（11 档 → HTTP 400），
下限没有被服务端强制（1 档也能通过）—— 但 1 档的 Score 没有意义，别这么写。

```python
Score(
    instructions="How frustrated does the customer sound?",
    criteria=["Calm", "Mildly annoyed", "Clearly angry", "Threatening to escalate"],
)
# -> {"score": 3.0, "confidence": 1.0,
#     "legend": {"0": "Calm", "1": "Mildly annoyed", ...},
#     "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0}}
```

`score` 是概率加权的**期望值**，所以会落在档位之间：`1.45` 表示介于
「这周处理」和「今天处理」，偏向前者。这比硬分类信息量大得多。

档位描述要写**可观察的特征**，不要写程度副词。
「Calm / Somewhat angry / Very angry」这种写法各档之间没有客观分界线；
写成「陈述事实，无情绪词」/「用了抱怨措辞但礼貌」/「大写、脏话、威胁」会稳很多。

进阶：每档可以是结构化对象：

```python
criteria=[
    {"summary": "Junior", "signals": ["needs review", "single tickets"]},
    {"summary": "Mid",    "signals": ["owns features end-to-end"]},
    {"summary": "Senior", "signals": ["designs systems", "cross-team impact", "mentors"]},
    {"summary": "Staff",  "signals": ["org-wide architecture", "sets technical direction"]},
]
# 实测：给一段「做了分布式限流器 + 写设计文档 + 带两个初级」的简历 -> score=2.0, conf=1.0
```

## 选型速查

| 你想知道 | 用 |
|---|---|
| 这条消息里有没有 PII？ | Noul |
| 该路由到哪个团队？ | Choice |
| 客户有多生气？ | Score |
| 这段文档回答了用户问题吗？（要排序） | Score（0~3 rubric，然后代码排序） |
| 这是哪种语言？ | Choice |
| 用户要调哪个函数？ | Choice（+ 兜底 `none`） |

经验法则：
**要排序或比较 → Score；要分派 → Choice；要开关 → Noul。**

## instructions 也可以结构化

三种原语的 instructions 都接受 JSON（对象/数组/字符串/null），
用来表达多段式的问题，比拼字符串模板干净：

```python
Score(
    instructions={"task": "Rate how well this passage answers the question",
                  "question": query,
                  "passage": passage},
    criteria=RUBRIC,
)
```

这也是 `demo/03_semantic_rerank.py` 里一次调用塞进 8 段候选的做法 ——
每个问题自带自己的 passage，共享同一个 state。
