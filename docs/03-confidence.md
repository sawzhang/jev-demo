# 03 · 置信度

## 它是什么

`confidence` 是从概率分布算出来的**一个标量（0~1），衡量分布有多「尖」**。
Choice 和 Score 都有；Noul 没有（Noul 的概率本身就是信号）。

- 概率集中在一个选项 → confidence 接近 1.0
- 概率摊平在多个选项 → confidence 接近 0.0
- 完全均匀分布 → confidence = 0.0

三选项时近似公式：`(3 × 最大概率 − 1) / 2`

验算一下 `demo/04_function_calling.py` 的实测输出：
概率 `{set_temperature: 0.48, set_lights: 0.40, ...}`，最大 0.48 →
`(3 × 0.48 − 1) / 2 = 0.22`。实际返回 0.38（选项多于 3 个，公式只是近似），
但方向一致：**分布越平，置信度越低。**

## 为什么它是 Jev 最值钱的字段

`choice` 告诉你**是什么**；`confidence` 告诉你**敢不敢自动执行**。

这是两根独立的轴。LLM 给不了你第二根轴 —— 它对着一个完全模糊的输入
也会用同样自信的语气给你一个答案。

```python
action = response.answers["intent"]

if action.confidence < 0.6:
    route_to_human(account_id)                    # 任何动作，置信度不够就不自动做

elif action.choice == "check_balance":
    show_balance(account_id)                      # 低风险，0.6 够了

elif action.choice == "approve_transfer":
    if action.confidence > 0.85:
        approve_transfer(account_id)              # 高风险 + 高置信度 -> 自动
    else:
        ask_user_to_confirm("确认要批准这笔转账吗？")  # 高风险 + 中置信度 -> 先确认
```

**阈值跟着风险走，不跟着模型走。** 同一个系统里，只读操作可以 0.6 放行，
不可逆操作要 0.85 甚至要人确认。**风险容忍度编码在你的代码里，不在模型里。**

## 官方建议的三档

| 区间 | 含义 | 建议动作 |
|---|---|---|
| 0.0 – 0.5 | 模型是真不确定 | 转人工 / 反问澄清 |
| 0.5 – 0.9 | 答案合理但不笃定 | 视风险决定：放行 or 先确认 |
| 0.9 – 1.0 | 清晰明确 | 自动执行 |

从保守阈值起步，用自己的数据验证，再慢慢放松 —— 这个顺序别反过来。

## 低置信度的三种成因（要分开处理）

实测下来，confidence 掉下去通常是这三种情况之一，处理方式完全不同：

**1. 输入本身就模糊** —— 「It arrived.」问情感倾向。
→ 反问用户，或者走中性默认值。

**2. 多意图 / 多动作** —— 「make the living room warmer **and** dim the lights」
→ 实测 conf=0.38，概率劈成 `set_temperature 0.48 / set_lights 0.40`。
这不是模型不行，是**你的答案空间假设了单意图**。正确做法是先加一个
`multi_step` 的 Noul 问题，检测到就拆分请求，而不是硬选一个。

**3. 你的选项设计有重叠** —— 两个 Choice 选项描述得几乎一样。
→ 这是你的 bug，不是模型的。用 `not_for` 把边界写清楚。

**别把这三种一律当成「转人工」。** 第 2、3 种是可以在代码/提示设计里解决的。

## 一个反直觉的点：confidence 高 ≠ 答案对

confidence 衡量的是**分布的尖锐度**，不是正确率。
模型可以非常自信地答错 —— 尤其是在它「literal reading」的时候：

```
"lock up, I'm going to bed"  ->  lock_doors(room=bedroom)  conf=0.99
```

`room=bedroom` 是错的（要锁的是门，不是卧室），但置信度 0.99。
模型把「I'm going to bed」里的 bedroom 老实地抽了出来 —— 它回答了你**字面写的**
问题（「哪个房间被提到了」），而不是你**想问的**（「动作发生在哪个房间」）。

**所以 confidence 是防「模糊」的，不是防「问错问题」的。**
后者只能靠把 instructions 写准 + 用真实数据回归测试。

## Score 的 confidence 有个特殊解读

Score 的 confidence 低，往往不代表「不知道」，而代表「**就在两档之间**」：

```
urgency: score=1.45  confidence=0.48
probabilities: {0: 0.04, 1: 0.50, 2: 0.43, 3: 0.03}
```

概率集中在相邻的 1 和 2 —— 模型很清楚这事「比这周急、比今天松」。
这是有效信息，不是噪声。**对 Score，与其看 confidence，不如直接看
概率质量是否集中在相邻档位。**

```python
probs = answer.probabilities
top2 = sorted(probs.items(), key=lambda kv: -kv[1])[:2]
adjacent = abs(int(top2[0][0]) - int(top2[1][0])) == 1
if adjacent and top2[0][1] + top2[1][1] > 0.85:
    ...  # 模型很确定，只是落在两档之间 —— 用 score 的小数部分就好
```
