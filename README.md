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

# 🏆 南溪合约交易Agent · Bitget AI Hackathon S1

> 赛道一 · 交易 Agent — 自主感知 → LLM推理 → 规则决策 → 合约执行 → 风控闭环

[🎯 在线 Demo](https://bitget-contract-trader-jvffadtjuubrzdceuvdxmh.streamlit.app) | [📊 展示页](https://shejishi603-stack.github.io/bitget-contract-trader/) | [🧠 决策证据](logs/agent_evidence.md) | [🎬 Demo视频](https://x.com/nan8938/status/2064270211151470900)

---

## 📋 项目说明

「南溪合约交易Agent」是一个基于 **Bitget Agent Hub** 构建的 BTC 永续合约 AI 交易 Agent，参加 Bitget AI Base Camp Hackathon S1 赛道一（交易 Agent）。

**解决的问题：** 加密市场 7×24 小时运行，散户难以持续盯盘。本系统通过日线趋势通道 + 4h MACD 结构 + OI/Vol 成交量三位一体的策略引擎，实现全自动「感知→决策→执行→风控」闭环。

**🎬 Demo 视频（2分38秒）：** [X/Twitter 公开视频](https://x.com/nan8938/status/2064270211151470900) — 完整展示从数据感知→策略信号→下单执行的自主交易闭环。

**核心创新：** 规则引擎与 LLM（Qwen3.6-Plus）交叉验证——规则负责确定性信号识别，LLM 负责多源数据综合分析，两者一致时置信度提升，冲突时标记风险。

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────┐
│                    感知层 (Perception)                    │
│  Bitget REST API ──┐                                     │
│  Bitget K线 API  ──┼──▶ 数据采集 ──▶ 数据融合 ──▶ 指标计算│
│  Bitget 合约 OI ──┤                                     │
│  Skill Hub MCP  ──┘                                     │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    推理层 (Reasoning)                     │
│  ┌──────────────┐    ┌──────────────┐                    │
│  │ 规则引擎      │    │ Qwen LLM     │                    │
│  │ EMA32趋势通道 │    │ 多源数据分析  │                    │
│  │ MACD底/顶结构 │    │ JSON决策输出  │                    │
│  │ OI/Vol确认   │    │ 推理链记录    │                    │
│  └──────┬───────┘    └──────┬───────┘                    │
│         └────────┬─────────┘                              │
│                  ▼                                       │
│           交叉验证 → 置信度评估                            │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    决策层 (Decision)                      │
│  状态机引擎: NO_POSITION → LONG_BASE → LONG_FULL         │
│             → LONG_REDUCED → LONG_TRIAL → FLAT           │
│  仓位管理: 30%底仓 → 50%满仓 → 30%减仓                   │
│  止损止盈: 趋势翻空全平 / 100%收益锁30% / 钝化消失止损    │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    执行层 (Execution)                     │
│  Bitget 合约API下单 ──▶ 5x杠杆 ──▶ 隔离保证金             │
│  支持: 实盘 / 模拟盘 (X-SIMULATED-Trading: 1)            │
└─────────────────────────────────────────────────────────┘
```

---

### 策略设计思考

**为什么用 EMA32？** EMA32 在回测中优于 EMA20（过于敏感，频繁假信号）和 EMA50（过于迟钝，错过最佳入场点）。32 根日线恰好覆盖 1 个月交易周期，能有效过滤震荡市噪音。

**为什么用 4h 级别？** 1h 太短容易被洗盘，日线太大会错过最佳入场窗口。4h 是趋势与结构的最佳平衡点——既能捕捉日内波段，又不会被短期噪音干扰。

**规则 + LLM 交叉验证的独特性：**
- 纯量化：只有规则，无法处理新闻/情绪/OI 等非结构化信息
- 纯 LLM：幻觉风险大，缺乏交易纪律
- **南溪方案：规则保证纪律 + LLM 提供弹性**——两者一致时高置信度执行，冲突时降仓或观望。这是只有 AI Agent 才能做的事。

**完成度说明：**
- ✅ 已跑通：策略信号、Bitget 合约下单、风控止损、Streamlit 仪表盘、3年回测
- 🔄 进行中：LLM 推理与执行层完全打通（当前 LLM 辅助验证，规则引擎主导执行）
- 📋 规划中：多币种支持、链上数据接入、自然语言策略编译器

---

## 🧠 策略逻辑

| 状态 | 触发条件 | 仓位 | 止损 |
|------|---------|:---:|------|
| `LONG_BASE` 底仓 | 日线EMA32翻多 | 30% | 趋势翻空全平 |
| `LONG_FULL` 满仓 | 日线站稳多头线 或 4h底结构 | 50% | 趋势翻空/顶结构 |
| `LONG_REDUCED` 减仓 | 顶结构 或 100%止盈 | 30% | 趋势翻空全平 |
| `LONG_TRIAL` 试仓 | 趋势空头 + 底结构防守 | 10-15% | 钝化消失止损 |
| `FLAT` 空仓 | 趋势翻空 或 止损触发 | 0% | — |

**策略出处：** 南溪交易系统（趋势通道定方向 + MACD结构找时机）

---

## 🚀 快速开始

### 环境要求
- Python 3.9+
- Windows / WSL / Linux / macOS 均可

### 1. 安装依赖
```bash
pip install streamlit plotly pandas numpy
```

### 2. 运行仪表盘
```bash
# 进入项目目录
cd bitget-contract-trader

# 启动 Streamlit 仪表盘
streamlit run dashboard.py
```

浏览器自动打开 `http://localhost:8501`，即可看到实时数据 + 策略信号 + 回测报告。

### 3. 模拟盘测试（无需 API Key）
```bash
cd bitget-contract-trader
python src/auto_trader.py --demo
```

模拟盘固定使用 1000 USDT 本金，下单仅记录日志不真实执行。

### 4. 连接 Bitget API（可选）
```bash
# 侧边栏填入 API Key 后点击"连接"
# 或在终端运行：
python src/auto_trader.py --key YOUR_KEY --secret YOUR_SECRET --passphrase YOUR_PASS
```

API Key 需在 Bitget 官网创建，勾选「读取」和「交易」权限。

---

## ⚙️ 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `QWEN_API_KEY` | 通义千问 API Key（用于 LLM 决策增强） | 否 |

**千问 API 配置（Hackathon 专属）：**
- Base URL: `https://hackathon.bitgetops.com/v1`
- Model: `qwen3.6-plus`

---

## 📁 项目结构

```
bitget-contract-trader/
├── dashboard.py                 # Streamlit 仪表盘（主入口）
├── requirements.txt             # Python 依赖
├── README.md                    # 本文件
├── generate_paper_trading.py    # 模拟盘记录生成器
├── src/
│   ├── data_provider.py         # 数据层：Bitget API + MCP 双通道
│   ├── indicators.py            # 指标层：EMA32 / MACD / OI
│   ├── strategy.py              # 策略层：状态机引擎
│   ├── agentic_trader.py        # AI决策层：感知→推理→决策→日志
│   ├── auto_trader.py           # 执行层：Bitget 合约API下单
│   ├── bitget_account.py        # 账户层：余额/持仓查询
│   ├── backtest.py              # 回测引擎：手续费/夏普/回撤
│   ├── ai_enhancer.py           # Skill Hub 验证 + 情绪过滤
│   └── qwen_enhancer.py         # Qwen LLM 调用层
├── logs/
│   ├── agent_decisions.jsonl    # LLM 决策日志
│   ├── agent_thinking.jsonl     # LLM 推理链记录
│   ├── trade_log.jsonl          # 交易执行日志
│   └── agent_evidence.md        # 比赛证据材料
├── data/
│   ├── backtest_2022.json       # 2022-2025 回测结果
│   ├── backtest_2023.json       # 2023-2025 回测结果
│   ├── backtest_2024.json       # 2024-2025 回测结果
│   └── paper_trading_runs.jsonl # 模拟盘实跑记录
└── playbook_package/            # Bitget Playbook 策略包
    ├── manifest.yaml
    └── src/main.py
```

---

## 📊 回测结果

| 区间 | 收益率 | 交易次数 | 胜率 | 说明 |
|------|--------|---------|------|------|
| 2022-2025 | **+335.4%** | 30笔 | 36.7% | 包含完整牛熊周期 |
| 2023-2025 | **+409.8%** | 26笔 | 42.3% | 从熊市底部开始 |
| 2024-2025 | +183.7% | 20笔 | 35.0% | 近期数据 |

回测代码见 `src/backtest.py` 和 `src/historical_backtest.py`，含手续费（0.04%）和 5x 杠杆计算，评委可直接复现。

---

## 🛠️ Bitget AI 模块集成

| 模块 | 用途 | 状态 |
|------|------|------|
| Bitget REST API | 实时行情 + K线数据 | ✅ 已集成 |
| Bitget 合约API | 合约下单 + 持仓查询 | ✅ 已集成 |
| Bitget Skill Hub (MCP) | RSI / MACD / 布林带技术分析 | ✅ 已集成 |
| Qwen3.6-Plus | 深度推理 + 自然语言决策 | ✅ 已集成 |
| Bitget Playbook | 策略部署执行 | ✅ 已集成 |

---

## 📝 对 AI Trading 的看法

传统量化交易依赖预设规则，但市场是动态的。南溪合约交易 Agent 的核心理念是：**规则引擎保证纪律，LLM 提供弹性**。

- 规则引擎（EMA32 + MACD 结构）负责识别确定性信号，确保不犯低级错误
- LLM（Qwen3.6-Plus）负责综合分析多源数据（行情 + 技术指标 + OI），在规则信号不明确时提供辅助判断
- 两者一致 → 高置信度执行；两者冲突 → 降低仓位或观望

这不是"AI 取代人做交易"，而是"AI 帮人做到人做不到的事"：7×24 小时不间断感知市场、毫秒级执行纪律、完整记录每笔决策的推理过程。

---

## 🏆 Bitget AI Base Camp Hackathon S1

- **赛道：** 赛道一 · 交易 Agent
- **提交：** [GitHub 仓库](https://github.com/shejishi603-stack/bitget-contract-trader) | [Streamlit Demo](https://bitget-contract-trader-jvffadtjuubrzdceuvdxmh.streamlit.app)
- **策略出处：** 南溪交易系统
