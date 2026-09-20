# Jev 实测报告

- 模型：`jev-1.13.0`（`jev-latest` 解析结果）
- 日期：2026-09-20
- 环境：macOS 26.6 / Python 3.12 / `typesafe-sdk` 0.7.0 / 经 SOCKS 代理
- 复现：`.venv/bin/python demo/05_benchmark.py`
- 原始输出：[`run_all_2026-09-20.txt`](run_all_2026-09-20.txt)

---

## 1. 扇出扩展性（最重要的一条）

同一份 state，只改问题数量：

| 问题数 | 耗时 | input tokens | output tokens | 成本 |
|---:|---:|---:|---:|---:|
| 1 | 0.53s | 305 | 21 | $0.0000128 |
| 4 | 0.46s | 346 | 72 | $0.0000145 |
| 12 | 0.40s | 449 | 210 | $0.0000189 |
| 40 | 0.52s | 817 | 714 | $0.0000343 |

（首次调用含 TLS 握手约 1.9s，后续稳定在 0.4~0.6s。上表取预热后数值。）

**40 倍问题量 → 延迟不变，成本 2.7 倍。** 因为 state 只发一次，
增量只有问题文本；而 output token 不计费。

**这条决定了 Jev 的正确用法**：不要「先分类再追问」，
要把整棵决策树的所有问题一次问完，让代码去挑。

---

## 2. 官方「已知弱点」逐条压测

官方 [model-jaggedness/jev-1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
列了 9 类失败模式但无量化数据。实测：

| 场景 | 期望 | 实测 | 判定 |
|---|---|---|---|
| 计数 17 项 | 17→高，16/18→低 | 0.99 / 0.01 / 0.01 | PASS |
| **日期窗口（模型自己算天数）** | **≈0.0（实际 42 天 > 30 天）** | **0.26 / 0.29 / 0.32**（3 次） | **FAIL** |
| 同题，代码先算好 `days=42` | ≈1.0 | 0.99 | PASS |
| 双重否定 | ≈1.0 | 0.92 ~ 0.93 | PASS |
| 噪声淹没信号（夹在 240 句废话中） | 分类与干净输入一致 | auth(1.0) == auth(1.0) | PASS |
| state 内提示注入 | ≈0.0 | 0.01 | PASS |
| P(x) + P(¬x) | 不保证 = 1 | 0.02 + 0.97 = 0.99 | PASS |
| 中文（非主力语言） | 能判对 | anger=2.93~2.95, 类别=物流(1.0) | PASS |
| 数值接近（0.1452 vs 0.15，差 3.2%） | ≈1.0 | 0.86 | 勉强 |
| 十六进制颜色接近（#3A7BD5 vs #3A7BD9） | ≈1.0 | 0.90 | 勉强 |
| 十六进制颜色语义（#3A7BD5 是蓝色吗） | ≈1.0 | 0.98 | PASS |

### 结论

**1.13 比文档描述健壮得多，但日期/时间计算是真的不行，且稳定复现。**

日期那条的危险之处不是「答错」，而是**答成 0.26 这种模棱两可的值** ——
任何阈值都救不了你。规避：

```python
# 0.26（错且模糊）
Noul("The return request is within the policy window.")

# 0.99（对且干净）—— 代码先算好天数放进 state
state = {..., "days_elapsed": 42, "policy_days": 30}
Noul("`days_elapsed` exceeds `policy_days`.")

# 最佳 —— 这题根本不该问模型
days_elapsed > policy_days
```

抗噪声和抗注入的实测表现好于文档预期，但官方原话是「不**默认**把数据当敌意输入」，
**不是保证**。仍需自己的纵深防御。

---

## 3. 限额与错误（实测确认）

| 项 | 文档 | 实测 |
|---|---|---|
| Choice 选项上限 | 255 | 255 通过（255 选 1 仍 conf=1.0）；256 → HTTP 400 |
| Score 档位上限 | 10 | 11 → HTTP 400 `Too many score levels` |
| Score 档位下限 | 2 | **未强制** —— 1 档也通过 |
| 无效 API key | 401 | `TypeSafeAuthenticationError` (401) |
| 空 questions | — | `TypeSafeError`（SDK 侧拦截，未发出请求） |

值得一提：**255 个选项里选出目标项，置信度仍然 1.0。**
大规模分类（商品类目、技能目录、意图集）是可行的。

---

## 4. jev-latest vs jev-preview

同一个刻意模糊的样本
（"The meeting could have gone better, but we did land the contract."）：

| 模型 | 结果 | probabilities |
|---|---|---|
| `jev-latest` | mixed, conf=0.92 | mixed 0.95 / positive 0.05 / negative 0.0 |
| `jev-preview` | mixed, conf=0.91 | mixed 0.94 / positive 0.06 / negative 0.0 |

当前两个别名都解析到 `jev-1.13.0`，输出差异在噪声范围内。

---

## 5. 从 demo 里跑出来的两个「字面理解」实例

这类问题不会出现在压测表里，但在真实开发里最高频：

**A. `demo/04_function_calling.py`**
```
"lock up, I'm going to bed"  ->  lock_doors(room=bedroom)  conf=0.99
```
问题写的是 "Which room is mentioned?" —— bedroom 确实被提到了。
想问的是「动作发生在哪个房间」。**模型没错，问题写错了。**
注意置信度 0.99 —— confidence 防不了「问错问题」。

**B. `demo/01_triage.py`**
```
"Would be great if you supported dark mode one day. No rush at all."
  ->  actionable = 0.15  ->  被路由到 ask_for_details
```
问题写的是 "enough information to start working on this ticket"。
对一个功能建议，确实没法马上开工 —— 字面上完全正确。

**教训：instructions 要写「精确的判定条件」，不是「意图」。
这类坑只有拿真实样本回归测试才会暴露。**

---

## 6. Choice 低置信度如实反映多意图

```
"make the living room a bit warmer and dim the lights"
  -> conf=0.38, probabilities: set_temperature 0.48 / set_lights 0.40
```

双动作请求，模型没硬选，把概率劈成两半。
生成式 function calling 通常会自信地只调一个工具。

**实践建议**：配一个 `multi_step` 的 Noul 一起扇出，
主动检测多动作并拆分请求，而不是事后从 confidence 反推原因。
