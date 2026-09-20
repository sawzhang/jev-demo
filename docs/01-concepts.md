# 01 · 核心概念

## System One 是什么

命名来自 Kahneman 的双系统理论：

- **System 2** —— 慢、费力、可解释的推理。LLM 干的活：写代码、写文章、多步推导。
- **System 1** —— 快、直觉、无需解释的判断。「这条工单是不是投诉？」「这段话的语气多冲？」

绝大多数软件里真正需要的是 System 1：一个**能喂给 `if` 的判断**。
但今天大家都在用 System 2 的模型干 System 1 的活 —— 让 GPT 输出一段 JSON，
再解析、校验、处理幻觉、处理格式漂移、重试。

Jev 把这一层砍掉了。

| | System One (Jev) | LLM |
|---|---|---|
| 输出 | 类型化、受约束 | 自由文本 |
| 答案空间 | **你定义**，模型只能从中选 | 开放 |
| 概率标定 | 针对真实结果优化过 | 未针对准确度标定 |
| 能做 | 分类、打分、判真假 | 生成、解释、写代码 |
| 不能做 | 写任何一个字的自由文本 | 保证结构合法 |
| 延迟 | 实测 0.5s 量级，与问题数几乎无关 | 随输出长度线性增长 |
| 计价 | $42 / 十亿 input token，**output 免费** | input + output 都计费 |

「答案空间由你定义」这一条是结构性的，不是概率性的：
Choice 只能返回你给的某个 key，**不可能**返回一个你没写过的字符串。
这和「我用 prompt 求 LLM 只返回这几个词」有本质区别。

## 一次请求的三件套

```
state      —— 要评估的材料（事实、证据、上下文）
questions  —— 要做的判断（每个带类型和答案空间）
model      —— "jev-latest"
```

一次请求 = **一份 state × N 个问题**。N 个问题并行评估，互相独立：
删掉其中一个，其他答案不变。

### state 怎么写

支持三种形态：

```python
state = "My card was charged twice."                              # 字符串
state = {"message": "...", "order_id": "A-104", "tier": "pro"}    # 对象（推荐）
state = ["Hi", "My customer number is TS1337.", "Charged twice."] # 数组（对话）
```

**对象最好用**，因为字段名本身携带语义，模型能靠字段名定位。

两条原则：

1. **相关信息放一起。** 要判断「该不该退款」，就把工单、订单、退款政策
   放进同一个 state 对象，而不是拆成三次调用。
2. **事实归 state，判断归 questions。** state 里放材料，不要放结论。
   ```python
   # 差：把判断塞进 state
   state = {"ticket": "...", "looks_angry": True}
   # 好
   state = {"ticket": "...", "policy": "..."}
   questions = {"angry": Noul(instructions="The customer sounds angry.")}
   ```

官方的比喻很准：**state 是你在请一组专家做判断之前，摆在他们面前的所有材料。**

### 反引号路径引用

instructions 里可以用反引号点号语法指向 state 的某个字段，模型会定位过去：

```python
state = {"customer": {"tier": "enterprise"},
         "ticket": {"messages": [{"text": "The API returns 500 on every POST."}]}}

Noul(instructions="The text in `ticket.messages[0].text` describes a server-side outage.")
# -> 0.79
```

state 大、字段多的时候这个很有用 —— 直接点名，别让模型自己猜你指哪段。

## 输入限制

- **只吃文本**：字符串 / JSON 对象 / 文本数组。不支持图片、音频、视频。
- **64k context**，其中 state + 最长的那个问题 ≤ 32k。
- 英语最准；中文等 CJK 支持但准确率略低（实测中文分类/打分表现良好，见 [05](05-limitations.md)）。

## 心智模型：Jev 不替代 LLM，它替代 `if`

最常见的误解是把 Jev 当便宜版 GPT。不是。

正确的用法是：**Jev 负责把模糊的现实世界变成确定的布尔值和数字，
然后你的普通 Python 代码拿着这些数字做决策。** 决策逻辑始终在你手里、
可读、可测、可 diff、可回归。模型只提供它擅长的那一部分：判断。

```python
a = client.system_one(state=ticket, questions=QUESTIONS).answers

# 下面全是普通代码，没有 prompt，没有解析，没有重试
if a["category"].confidence < 0.6:
    return human_triage()
if a["category"].choice == "bug_report" and a["severity"].score >= 2.0:
    return escalate()
```
