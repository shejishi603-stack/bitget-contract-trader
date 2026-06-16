---
title: 南溪合约交易Agent
emoji: 📈
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.58.0
app_file: dashboard.py
pinned: false
---

# 南溪合约交易Agent · Bitget Hackathon S1

## 项目说明

南溪合约交易Agent — 以「趋势通道+MACD结构」双剑架构捕捉每一次4H/日线主升浪。感知层通过 **Bitget REST API** 与 **Skill Hub MCP** 多源并行采集，每小时扫描趋势通道与结构指标，触发后按底仓状态机分配仓位权重（30%底仓→50%满仓）。决策层由 **Qwen3.6-Plus** 深度推理与规则引擎交叉验证，通过 **Bitget Playbook** 执行。风控层：触发顶部结构或跌破趋势通道即砍仓，以小亏博取大赚。

## 策略闭环

```
感知层（4源并行）  →  推理层（Qwen+规则）  →  决策层（融合执行）  →  风控层（砍仓锁利）
      ↑                                                                    ↓
      └──────────────────── 日志审计（JSONL全链路） ────────────────────────┘
```

## Bitget AI 模块

| 模块 | 用途 |
|------|------|
| Bitget REST API | 实时行情 + K线数据 |
| Skill Hub MCP | RSI / MACD / 布林带技术分析 |
| Qwen3.6-Plus | 深度推理 + 自然语言交互 |
| Bitget Playbook | 策略部署执行 |

## 仓位管理（3.0底仓思维）

| 状态 | 触发条件 | 仓位 |
|------|---------|:---:|
| LONG_BASE | 日线翻多 | 30% |
| LONG_FULL | 确认站稳/底结构 | 50% |
| LONG_REDUCED | 顶结构/100%利润锁仓 | 30% |
| LONG_TRIAL | 趋势下底结构防守试仓 | 10% |
| FLAT | 趋势翻空/钝化消失/ATR止损 | 0% |

## Demo 链接

- 🔗 Streamlit Cloud: [bitget-contract-trader.streamlit.app](https://bitget-contract-trader-jvffadtjuubrzdceuvdxmh.streamlit.app)
- 🔗 GitHub Pages: [shejishi603-stack.github.io/bitget-contract-trader](https://shejishi603-stack.github.io/bitget-contract-trader)

## 策略出处

南溪交易系统
