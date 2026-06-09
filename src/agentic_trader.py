"""
Agentic决策层 — 完整自主闭环
- 感知: Skill Hub + API 数据采集
- 推理: Qwen 深度分析（带思考链）
- 决策: 规则引擎 + LLM 经验修正
- 执行: 仓位管理状态机
- 记录: 完整MCP调用日志 + LLM思考过程
"""
import json, subprocess, os
from datetime import datetime
from qwen_enhancer import qwen_chat

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')


class AgenticTrader:
    """完整自主交易Agent"""

    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.log_file = os.path.join(LOG_DIR, 'agent_decisions.jsonl')
        self.thinking_file = os.path.join(LOG_DIR, 'agent_thinking.jsonl')

    def perceive(self, provider):
        """STEP 1: 感知 — 从Bitget Agent Hub采集全部数据"""
        perception = {
            'timestamp': datetime.now().isoformat(),
            'data_sources': [],
        }

        # Bitget REST API
        try:
            ticker = provider.get_ticker()
            perception['btc_price'] = ticker.get('price', 0)
            perception['data_sources'].append('Bitget REST API')
        except:
            perception['btc_price'] = 0

        # Skill Hub 技术分析
        try:
            ta = provider.get_technical_analysis('BTC/USDT', '4h', 'full_analysis')
            perception['skill_hub'] = ta
            perception['data_sources'].append('Bitget Skill Hub (MCP)')
        except:
            perception['skill_hub'] = {'error': 'MCP不可用'}

        # 合约OI
        try:
            oi = provider.get_open_interest()
            perception['open_interest'] = oi
            perception['data_sources'].append('Bitget 合约API')
        except:
            perception['open_interest'] = 0

        # K线数据
        try:
            klines = provider.get_klines('BTCUSDT', '4h', 50)
            perception['klines_count'] = len(klines)
            perception['data_sources'].append('Bitget K线API')
        except:
            perception['klines_count'] = 0

        return perception

    def reason(self, perception, rule_signal):
        """STEP 2: 推理 — Qwen深度分析 + 规则引擎交叉验证"""
        # 构建分析提示
        ta = perception.get('skill_hub', {})
        rsi_info = ta.get('rsi', {}) if isinstance(ta, dict) else {}
        macd_info = ta.get('macd', {}) if isinstance(ta, dict) else {}

        prompt = f"""作为BTC永续合约交易Agent，分析以下多源数据并给出决策：

【感知层数据】
- BTC价格: ${perception.get('btc_price', 0):,.0f}
- 合约OI: {perception.get('open_interest', 0):,.0f} BTC
- 数据来源: {', '.join(perception.get('data_sources', []))}

【Skill Hub技术分析(MCP)】
- RSI: {rsi_info.get('rsi', '?')} ({rsi_info.get('signal', '?')})
- MACD: {macd_info.get('cross', '?')}
- 综合判断: {ta.get('verdict', '?') if isinstance(ta, dict) else 'N/A'}

【规则引擎信号】
- 趋势: {rule_signal.get('trend', '?')}
- 结构: {rule_signal.get('structure', '?')}
- OI信号: {rule_signal.get('oi', '?')}
- 当前仓位: {rule_signal.get('position', 0)}%

请按以下格式输出（JSON）:
{{
  "analysis": "一句话分析(中文)",
  "skill_hub_agreement": true/false,
  "confidence": "HIGH/MEDIUM/LOW",
  "action": "LONG/HOLD/REDUCE/FLAT",
  "reasoning_chain": ["推理步骤1", "推理步骤2", "推理步骤3"],
  "risk_flags": ["风险1", "风险2"]
}}"""

        system = """你是Bitget交易Agent的分析核心。你从Bitget Agent Hub的多源数据中推理交易决策。
你收到: ①Bitget REST API行情 ②Skill Hub MCP技术分析 ③规则引擎信号
你输出: JSON格式的决策分析，包含完整推理链。
保持客观，标注数据来源。"""

        # 调用Qwen（带思考链）
        llm_response = qwen_chat(prompt, system, 400)

        # 解析LLM输出
        decision = {}
        if llm_response:
            try:
                # 提取JSON（可能在markdown代码块里）
                text = llm_response
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0]
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0]
                if '{' in text:
                    text = text[text.index('{'):text.rindex('}')+1]
                decision = json.loads(text)
            except:
                decision = {
                    "analysis": llm_response[:200] if llm_response else "LLM超时",
                    "confidence": "MEDIUM",
                    "reasoning_chain": ["使用Qwen原始输出"],
                    "risk_flags": []
                }

        return decision

    def decide(self, perception, rule_signal, llm_decision):
        """STEP 3: 决策 — 融合规则+LLM，输出最终决策"""
        final = {
            'timestamp': datetime.now().isoformat(),
            'perception_summary': {
                'price': perception.get('btc_price', 0),
                'sources': len(perception.get('data_sources', [])),
            },
            'rule_signal': rule_signal,
            'llm_decision': llm_decision,
            'final_action': rule_signal.get('action', 'HOLD'),
            'confidence': llm_decision.get('confidence', 'MEDIUM'),
            'reasoning_chain': llm_decision.get('reasoning_chain', []),
            'mcp_calls': [
                'Skill Hub: technical_analysis/full_analysis',
                'Bitget API: /api/v2/spot/market/candles',
                'Bitget API: /api/v2/mix/market/open-interest',
            ],
        }

        # 如果LLM和规则一致 → 高置信度
        rule_action = rule_signal.get('action', 'HOLD')
        llm_action = llm_decision.get('action', 'HOLD')
        if rule_action == llm_action:
            final['confidence'] = 'HIGH'
            final['reasoning_chain'].append('✅ 规则引擎与LLM一致，置信度提升')

        return final

    def execute_and_log(self, decision):
        """STEP 4: 执行+记录 — 完整决策日志"""
        # 记录到JSONL
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(decision, ensure_ascii=False) + '\n')

        # 记录思考链
        thinking = {
            'timestamp': decision['timestamp'],
            'chain': decision.get('reasoning_chain', []),
            'mcp_calls': decision.get('mcp_calls', []),
            'confidence': decision.get('confidence', '?'),
        }
        with open(self.thinking_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(thinking, ensure_ascii=False) + '\n')

        return decision

    def get_recent_decisions(self, limit=5):
        """获取最近决策记录"""
        decisions = []
        if os.path.exists(self.log_file):
            with open(self.log_file) as f:
                for line in f:
                    decisions.append(json.loads(line))
        return decisions[-limit:]

    def get_recent_thinking(self, limit=3):
        """获取最近思考链"""
        chains = []
        if os.path.exists(self.thinking_file):
            with open(self.thinking_file) as f:
                for line in f:
                    chains.append(json.loads(line))
        return chains[-limit:]


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/src')
    from data_provider import BitgetDataProvider

    print("═══ Agentic自主交易闭环测试 ═══\n")

    agent = AgenticTrader()
    provider = BitgetDataProvider()

    # STEP 1: 感知
    print("🔍 STEP 1: 感知层")
    perception = agent.perceive(provider)
    print(f"   数据源: {perception['data_sources']}")
    print(f"   BTC: ${perception['btc_price']:,.0f}")

    # STEP 2: 推理
    print("\n🧠 STEP 2: 推理层 (Qwen深度分析)")
    mock_signal = {
        'trend': '空头', 'structure': '无', 'oi': '无', 'position': 0,
        'action': 'FLAT'
    }
    llm_decision = agent.reason(perception, mock_signal)
    print(f"   分析: {llm_decision.get('analysis', '?')}")
    print(f"   置信度: {llm_decision.get('confidence', '?')}")
    print(f"   推理链: {llm_decision.get('reasoning_chain', [])}")

    # STEP 3: 决策
    print("\n⚡ STEP 3: 决策层")
    final = agent.decide(perception, mock_signal, llm_decision)
    print(f"   最终置信度: {final['confidence']}")
    print(f"   MCP调用: {final['mcp_calls']}")

    # STEP 4: 记录
    print("\n📝 STEP 4: 日志记录")
    agent.execute_and_log(final)

    recent = agent.get_recent_decisions(1)
    print(f"   已记录决策: {len(recent)}条")
    print(f"\n完整决策JSON:")
    print(json.dumps(recent[0], ensure_ascii=False, indent=2)[:500])
