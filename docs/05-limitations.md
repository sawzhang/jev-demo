# 05 · 弱点与规避

官方在 [model-jaggedness/jev-1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
列了 9 类失败模式，但没给量化数据。下面是**文档说法 + 我的实测结果 + 规避写法**。

复现：`.venv/bin/python demo/05_benchmark.py`

---

## 实测汇总（jev-1.13.0, 2026-09-20）

| # | 场景 | 期望 | 实测 | |
|---|---|---|---|---|
| 1 | 计数 17 项 | 17→高, 16/18→低 | 0.99 / 0.01 / 0.01 | PASS |
| 2 | **日期窗口（模型自己算天数）** | **≈0.0（42 天 > 30 天）** | **0.26** | **FAIL** |
| 3 | 同题，代码先算好 `days=42` | ≈1.0 | 0.99 | PASS |
| 4 | 双重否定 | ≈1.0 | 0.93 | PASS |
| 5 | 噪声淹没信号（夹在 120 句废话中） | 分类不变 | auth(1.0)，与干净输入一致 | PASS |
| 6 | state 内提示注入 | ≈0.0 | 0.01 | PASS |
| 7 | P(x) + P(¬x) | 不保证 = 1 | 0.99 | PASS |
| 8 | 中文 | 能判对 | anger=2.93, 类别=物流 | PASS |
| 9 | 数值接近判断 (0.1452 vs 0.15 差 5% 内) | ≈1.0 | 0.86 | 勉强 |

**结论：1.13 比文档写的健壮得多，但日期/时间是真的不行。**

---

## 1. 字面理解 (Literal Reading) —— 最容易踩的坑

> 「它回答你**写**的问题，不是你**想问**的问题。」

这条没法用实测表格体现，但它是实际开发里最高频的问题。本仓库里就踩到两次：

**踩坑 A** —— `demo/04_function_calling.py`
```
"lock up, I'm going to bed"  ->  lock_doors(room=bedroom)  conf=0.99
```
我问的是「Which room is mentioned?」，bedroom 确实被提到了。
我想问的是「动作发生在哪个房间」。模型没错，我的问题写错了。

**踩坑 B** —— `demo/01_triage.py`
```
"Would be great if you supported dark mode one day. No rush at all."
  -> actionable = 0.15  -> 被路由到 ask_for_details
```
我问的是「There is enough information here to start working on this ticket」。
对一个功能建议来说，确实「没法马上开工」。但我想表达的是「这条工单值不值得记录」。

**规避**：
- instructions 写**精确的判定条件**，不写意图。
  `"The room where the requested action takes place is named."` 而不是 `"Which room is mentioned?"`
- 边界情况直接写进 criteria 的 `not_for` / `examples`。
- **拿真实数据回归测试**。字面理解的坑只有在真实样本上才会暴露。

---

## 2. 日期与时间 —— 唯一稳定复现的失败

> 「它把日期当文本读，不当有序量。」

```python
state = {"order_date": "Mar 11, 2024", "return_request": "2024/04/22",
         "policy": "Returns accepted within 30 days of order."}
Noul("The return request is within the policy window.")
# -> 0.26   真实间隔 42 天，正确答案应该 ≈0.0。0.26 既不是"是"也不是明确的"否"。
```

**规避（按推荐度排序）**：

```python
# 最好：根本不问模型
days = (request_date - order_date).days
eligible = days <= 30

# 次好：代码算好，模型只做判断
state = {..., "days_elapsed": 42, "policy_days": 30}
Noul("`days_elapsed` exceeds `policy_days`.")          # -> 0.99  干净

# 可以：让模型做分桶（不做算术），代码再比较
Choice("Roughly how many days passed?",
       {"lt15": "fewer than 15 days", "15to30": "15-30 days",
        "31to60": "31-60 days", "gt60": "more than 60 days"})
# -> 31to60, conf=0.97   分桶是判断，模型行；算差值是算术，模型不行
```

**通用规则：算术在代码里做，判断才交给模型。**

---

## 3. 数学与数字

计数在实测里表现不错（17 项判对，0.99），但官方明确说不可靠 ——
**别依赖**，列表长了、嵌套了、要跨字段数了就会崩。

数值接近判断实测 0.86（5% 以内，真值是「接近」），能用但不干净。
十六进制颜色、RGB 三元组这类**数字化表示**是明确的弱项。

**规避**：
```python
# 差：让模型判断颜色接近
Noul("`hex` and `other_hex` are visually almost the same color.")   # -> 0.9 勉强

# 好：代码算色差，模型做语义判断
Noul("`hex` is a shade of blue.")                                   # -> 0.98 稳
```
语义判断（「这是不是蓝色」）行，数值运算（「这两个数差多少」）不行。

---

## 4. 间接推理 (Indirection)

双重否定实测 0.93，比预期好。但「属性的属性」「多跳引用」仍然是弱项。

**规避**：用反引号直接点名字段，别让模型自己找链路。
```python
# 差
Noul("The person who submitted the most recent ticket is an enterprise customer.")
# 好
Noul("`customer.tier` is `enterprise`.")
```

---

## 5. 大 state 里的无关细节

实测：把信号句夹在 240 句无关废话中间，分类结果和置信度**完全没变**（auth, 1.0）。
比文档说的健壮。

但这只说明单一强信号抗干扰。**先检索、再判断**仍然是对的架构 ——
不光为了准确率，也为了 32k 的 state 上限和成本。

---

## 6. 对抗性内容

> 「不默认把数据当敌意输入。」

实测提示注入返回 0.01（完全没上当）。`demo/02_guardrails.py` 里
5 条对抗样本全部正确拦截。

**但不要当成安全保证。** 官方的说法是「不默认」，不是「不会」。
生产环境的正确姿势：
- 把用户内容放在 state 的**具名字段**里（`{"user_message": ...}`），
  而不是拼进 instructions。
- 用 criteria 的 `examples` 钉死判定标准。
- Jev 护栏是**纵深防御的一层**，不是唯一一层。

---

## 7. 指令与 criteria 互相矛盾

instructions 说 A，criteria 描述暗示 B，模型会懵。
**规避**：两边用同一套措辞。写完通读一遍，确认没有隐含的第二套标准。

---

## 8. 常识性结构不变量不保证

`P(noul) ≠ 1 − P(not noul)`（实测 0.99 很接近，但不保证）。
不同问题之间也不保证任何数学关系 —— 它们是**独立评估**的。

**规避**：
- 需要互补语义就问一次，用 `1 - noul`。
- 别把一个问题的阈值经验搬到另一个问题上。
- 别假设 `Score` 的分数和某个 `Noul` 的概率有关系。

---

## 9. 不能生成

Jev 不能写文本。用「强行链式 Choice 逐字生成」这种黑魔法又慢又不可靠。

**规避**：答案空间有限就用 Choice；要自由文本就用生成模型。
两者组合（Jev 定路由和枚举参数，LLM 填自由文本）是最实用的分工。

---

## 限额与错误速查

| 项 | 值 |
|---|---|
| Score 档位 | 上限 10（11 档 → HTTP 400）。下限文档说 2，实测未强制 |
| Choice 选项 | ≤ 255（256 → HTTP 400）。实测 255 选项里选对目标项，conf=1.0 |
| Context | 64k 总量；state + 最长问题 ≤ 32k |
| 速率 | 250k tokens/s，1200 req/min（beta 期动态调整） |

| HTTP | 含义 | SDK 异常 |
|---|---|---|
| 400 | 参数超限（如档位过多） | `TypeSafeBadRequestError` |
| 401 | key 无效/缺失 | `TypeSafeAuthenticationError` |
| 422 | 请求校验失败 | `TypeSafeUnprocessableEntityError` |
| 429 | 限流 | `TypeSafeRateLimitError` |
| 529 | 服务过载 | — |

429/529 用指数退避重试；SDK 的 `RetryPolicy` 自动处理。
错误里带 `request_id`，报 issue 时贴上。
