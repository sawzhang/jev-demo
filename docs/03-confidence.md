# 03 · 置信度

## 它是什么

`confidence` 是从概率分布算出来的**一个标量（0~1），衡量分布有多「尖」**。
Choice 和 Score 都有；Noul 没有（Noul 的概率本身就是信号）。

- 概率集中在一个选项 → confidence 接近 1.0
- 概率摊平在多个选项 → confidence 接近 0.0
- 完全均匀分布 → confidence = 0.0

Choice 的官方公式为 `(p_max - 1/n) / (1 - 1/n)`，其中 n 是选项数。
三选项时精确化简为 `(3 * p_max - 1) / 2`，不能用于六选项。

`demo/04_function_calling.py` 的六选项案例最大概率0.48，对应约0.376，与返回0.38一致。
Score 使用考虑等级距离的另一种公式，不应套用Choice公式。见[官方定义](https://docs.typesafe.ai/confidence)。

## 如何使用这个字段

`choice`给出选项；`confidence`给出分布统计，可帮助路由，但不是经验正确率。
阈值需要用领域标注数据校准，不能仅凭高confidence授权高风险操作。
以下数字只是示例，不是已经验证的生产阈值。

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

## 路由区间示例（需领域校准）

| 区间 | 含义 | 建议动作 |
|---|---|---|
| 0.0 – 0.5 | 模型是真不确定 | 转人工 / 反问澄清 |
| 0.5 – 0.9 | 答案合理但不笃定 | 视风险决定：放行 or 先确认 |
| 0.9 – 1.0 | 分布较集中，仍可能答错 | 结合证据、权限与领域校准决定 |

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
