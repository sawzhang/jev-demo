# 04 · 四种架构模式

官方总结了四个模式。下面每个都配了本仓库里的实际代码位置和实测数据。

---

## 1. 投机性扇出 (Speculative Fan-out)

> 一次调用里问掉所有**可能**用到的问题（包括用不上的），让代码去挑。

**为什么可行** —— 实测数据：

| 问题数 | 耗时 | input tokens | 成本 |
|---:|---:|---:|---:|
| 1 | 0.53s | 305 | $0.0000128 |
| 12 | 0.53s | 449 | $0.0000189 |
| 40 | 0.52s | 817 | $0.0000343 |

40 个问题和 1 个问题**耗时相同**，成本只涨 2.7 倍（因为 state 只发一次，
只有问题文本在增加，而且 output token 不计费）。

**反模式**（串行多轮，每轮一次网络往返）：
```python
cat = ask("category?")
if cat == "bug_report":
    sev = ask("severity?")        # 第二次往返
    repro = ask("has repro?")     # 第三次往返
```

**正确姿势**（`demo/01_triage.py`）：
```python
a = client.system_one(state=ticket, questions={
    "category": Choice(...), "bug_severity": Score(...), "has_repro": Noul(...),
    "refund_requested": Noul(...), "frustration": Score(...), "deadline": Noul(...),
    "legal_threat": Noul(...), "actionable": Noul(...),
}).answers
# bug_severity 只在 category==bug_report 时有意义 —— 但问它几乎不要钱
if a["category"].choice == "bug_report" and a["bug_severity"].score >= 2.0:
    ...
```

**注意**：横切问题（`frustration` / `legal_threat` / `deadline`）不属于任何分支，
对所有工单都适用。扇出让这类「全局标记」变得几乎免费。

---

## 2. 置信度闸门路由 (Confidence-Gated Routing)

> 把 confidence 当第二根决策轴。答案说「是什么」，置信度说「敢不敢动手」。

阈值按**动作的风险**设，不按模型设。详见 [03-confidence.md](03-confidence.md)。

`demo/01_triage.py` 里的两道闸门，注意它们是**两个不同的东西**：

```python
# 闸门 1：模型不确定 -> 转人工
if cat.confidence < 0.60:
    return "human_triage"

# 闸门 2：模型很确定，但工单本身信息不足 -> 反问用户
if cat.choice == "unclear" or a["actionable"].noul < 0.5:
    return "ask_for_details"
```

把这两种混成一个 flag 是常见 bug —— 一个是「模型不知道」，
一个是「模型知道，而且知道的是：信息不够」。

---

## 3. 复合打分 (Composite Scoring)

> 把一个复杂判断拆成几个原子分，在代码里加权合成，而不是让模型直接给总分。

**反模式**：`Score("这个候选人整体怎么样？", ["差","一般","好","很好"])`
—— 权重藏在模型脑子里，你既不知道也改不了。

**正确姿势**：
```python
questions = {
    "scope":     Score(instructions="项目影响范围", criteria=[...]),
    "ownership": Score(instructions="端到端负责程度", criteria=[...]),
    "influence": Score(instructions="对他人的技术影响", criteria=[...]),
}
a = client.system_one(state=resume, questions=questions).answers

# 权重在你的代码里 —— 可读、可调、可 A/B、可解释给别人听
total = (0.5 * a["scope"].score + 0.3 * a["ownership"].score + 0.2 * a["influence"].score)
```

好处不只是可控：每个子维度都有自己的 confidence，
你能定位到**是哪一维拿不准**，而不是只知道「总分置信度低」。

---

## 4. 意图路由 (Intent Routing)

> 分类用户意图，分派给对应 handler。答案空间封闭 = 不可能路由到不存在的 handler。

`demo/04_function_calling.py` 是完整实现。三条实战经验：

1. **必须有兜底选项** (`none` / `other`)。否则「法国首都是哪」会被硬塞进某个工具。
2. **枚举参数和工具一起投机性地问出来**（`direction` / `room`），不要二次调用。
3. **配一个 `multi_step` 的 Noul**。多动作请求会让 Choice 的置信度崩掉
   （实测 0.38），提前检测出来拆分，比事后看 confidence 猜原因好。

```python
"make the living room a bit warmer and dim the lights"
  -> tool conf=0.38  (set_temperature 0.48 / set_lights 0.40)
  -> multi_step=高  -> 拆成两个请求，而不是猜一个
```

---

## 组合起来：一个典型生产链路

```
用户消息
  ↓
[Jev] 护栏扇出（越狱/PII/越界/有害）      ~0.5s, ~$0.00003   demo/02
  ↓ 通过
[Jev] 意图路由 + 枚举参数扇出              ~0.5s, ~$0.00003   demo/04
  ↓ confidence >= 阈值
  ├─ 确定性 handler（查余额、改设置）—— 根本不需要 LLM
  └─ 需要生成文本
        ↓
     [向量检索] 召回 20 段
        ↓
     [Jev] 重排 + 截断                    ~0.5s, ~$0.00005   demo/03
        ↓ 只剩 2~3 段
     [LLM] 生成回复                        ~3s,  ~$0.01
        ↓
     [Jev] 输出护栏（幻觉/引用核对/语气）    ~0.5s, ~$0.00003
```

整条链路里 Jev 那几步加起来还不到 LLM 那一步成本的 1%，
但把 LLM 的输入收窄了、把不该进 LLM 的请求挡住了、把输出核对了。
