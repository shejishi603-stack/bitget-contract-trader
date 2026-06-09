# 🧠 南溪交易Agent · 完整决策证据

> 所有决策均有完整思考链，可在实时仪表盘中查看。
> 脱敏确认: ✅ 无API Key暴露 ✅ 无资金细节

## 📸 关键证据

| 证据类型 | 状态 |
|---------|:--:|
| Prompt示例（4源感知） | ✅ |
| MCP调用记录（3接口） | ✅ |
| Qwen思考链 | ✅ |
| 决策日志JSONL | ✅ |
| 自然语言交互 | ✅ |

---

# 🧠 Agentic 决策证据 — 南溪合约交易Agent

## 一、自主闭环架构

```
感知层 → 推理层 → 决策层 → 执行层
  ↑                          ↓
  └──── 日志记录（可审计） ────┘
```

## 二、感知层 — 多源数据采集（4源并行）

每次决策前，Agent自动从以下数据源采集最新数据：

| 数据源 | 接口 | 类型 |
|--------|------|------|
| Bitget REST API | `/api/v2/spot/market/tickers` | 实时行情 |
| Bitget K线API | `/api/v2/spot/market/candles` | 日线+4h K线 |
| Bitget 合约API | `/api/v2/mix/market/open-interest` | OI持仓量 |
| Bitget Skill Hub(MCP) | `datahub.noxiaohao.com/mcp` | RSI/MACD/布林带 |

## 三、推理层 — Qwen LLM深度分析

### Prompt示例
```
作为BTC永续合约交易Agent，分析以下多源数据并给出决策：

【感知层数据】
- BTC价格: $63,386
- 合约OI: 31,633 BTC
- 数据来源: Bitget REST API, Bitget Skill Hub (MCP), Bitget 合约API, Bitget K线API

【Skill Hub技术分析(MCP)】
- RSI: 48.64 (neutral)
- MACD: death_cross
- 综合判断: NEUTRAL

【规则引擎信号】
- 趋势: 空头
- 结构: 无
- 当前仓位: 0%

请输出JSON决策...
```

### Qwen响应示例
```json
{
  "action": "FLAT",
  "confidence": "MEDIUM",
  "reason": "MACD死亡交叉与空头趋势一致，RSI中性无超卖信号，应保持空仓等待底部结构形成。",
  "risk_flags": ["趋势未反转", "无底部结构", "MACD空头加速"]
}
```

## 四、决策层 — 规则+LLM融合

```
规则引擎: FLAT（空头趋势，无结构）
Qwen分析: FLAT（MACD死亡交叉，保持空仓）
        ↓
融合决策: FLAT | 置信度: HIGH（规则与LLM一致）
```

## 五、MCP调用记录

每次Agent决策包含以下MCP调用：
```
✓ Skill Hub: technical_analysis/full_analysis
✓ Bitget API: /api/v2/spot/market/candles (日线200根)
✓ Bitget API: /api/v2/spot/market/candles (4h 200根)
✓ Bitget API: /api/v2/mix/market/open-interest
```

## 六、完整决策日志样例

```json
{
  "timestamp": "2026-06-09T12:50:24",
  "perception_summary": {
    "price": 63423.87,
    "sources": 4
  },
  "rule_signal": {
    "trend": "空头",
    "structure": "无",
    "oi": "无",
    "position": 0,
    "action": "FLAT"
  },
  "llm_decision": {
    "action": "FLAT",
    "confidence": "MEDIUM",
    "reasoning_chain": [
      "感知: Bitget API + Skill Hub获取4源数据",
      "分析: RSI 48.64中性，MACD death_cross",
      "推理: 空头趋势+无底部结构 → 不做多",
      "决策: FLAT，等待底部结构或趋势翻多"
    ]
  },
  "final_action": "FLAT",
  "confidence": "HIGH",
  "mcp_calls": [
    "Skill Hub: technical_analysis/full_analysis",
    "Bitget API: /api/v2/spot/market/candles",
    "Bitget API: /api/v2/mix/market/open-interest"
  ]
}
```

## 七、关键特性总结

| Agentic特性 | 实现方式 |
|------------|---------|
| 自主感知 | 4源并行采集（REST API + MCP + 合约API） |
| LLM推理 | Qwen深度分析 + JSON决策输出 |
| 交叉验证 | Skill Hub × 规则引擎 × LLM 三方校验 |
| 思考链 | 每一步决策记录完整推理过程 |
| MCP集成 | Skill Hub MCP Server 直接调用 |
| 可审计 | 全部决策JSONL日志化存储 |
| 自然语言交互 | 支持"按南溪3.0风格操作"等指令 |

---

## 八、查看方式

所有决策均有完整思考链，可在仪表盘中实时查看：

```
本地仪表盘: http://172.30.112.210:8502
  → 🧠 AI增强决策 面板 → 置信度 + 推理链

日志文件: logs/agent_decisions.jsonl
  → 每次决策的完整JSON（含MCP调用记录）
```
