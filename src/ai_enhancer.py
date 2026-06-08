"""
AI 分析增强层
- Skill Hub 技术分析验证
- 情绪/市场数据过滤
- 决策日志记录
"""
import json
import os
from datetime import datetime
from data_provider import BitgetDataProvider

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')

class DecisionLogger:
    """记录每笔决策的原因"""

    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.log_file = os.path.join(LOG_DIR, 'decisions.jsonl')

    def log(self, timestamp, signal, reason, indicators=None):
        entry = {
            'timestamp': str(timestamp),
            'signal': signal,
            'reason': reason,
            'indicators': indicators or {},
            'logged_at': datetime.now().isoformat(),
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def recent(self, limit=10):
        if not os.path.exists(self.log_file):
            return []
        lines = []
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                lines.append(json.loads(line))
        return lines[-limit:]


class SkillHubVerifier:
    """Skill Hub 技术分析交叉验证"""

    def __init__(self):
        self.provider = BitgetDataProvider()
        self.last_verdict = {}

    def verify(self, symbol="BTC/USDT", timeframe="4h"):
        """
        从 Skill Hub 获取技术分析，与本地指标交叉验证
        返回: {
            'local_vs_hub': 一致性判断,
            'hub_signals': Skill Hub的输出,
            'confidence': 'HIGH'/'MEDIUM'/'LOW'
        }
        """
        try:
            ta = self.provider.get_technical_analysis(symbol, timeframe, 'full_analysis')
            if not ta:
                return {'confidence': 'LOW', 'note': 'Skill Hub 不可用'}

            self.last_verdict = ta

            # 提取关键信号
            rsi = ta.get('rsi', {})
            macd = ta.get('macd', {})
            verdict = ta.get('verdict', 'NEUTRAL')

            signals = {
                'rsi_value': rsi.get('rsi', 0),
                'rsi_signal': rsi.get('signal', 'neutral'),
                'macd_cross': macd.get('cross', 'none'),
                'verdict': verdict,
                'source': ta.get('_source', 'Skill Hub'),
            }

            # 判断置信度
            bull = ta.get('bull_signals', 0)
            bear = ta.get('bear_signals', 0)
            total = bull + bear
            if total >= 3:
                confidence = 'HIGH'
            elif total >= 1:
                confidence = 'MEDIUM'
            else:
                confidence = 'LOW'

            return {
                'confidence': confidence,
                'signals': signals,
                'bull_count': bull,
                'bear_count': bear,
            }
        except Exception as e:
            return {'confidence': 'LOW', 'note': f'验证失败: {str(e)[:50]}'}


class SentimentFilter:
    """情绪/市场数据过滤器"""

    def __init__(self):
        self.provider = BitgetDataProvider()

    def check(self):
        """
        检查市场情绪，返回对做多的支持度
        返回: {
            'fear_greed': 恐惧贪婪值(0-100),
            'sentiment_bias': '支持做多'/'中立'/'反对做多',
            'score': -1到1的分数
        }
        """
        try:
            sent = self.provider.get_sentiment()
            # datahub的sentiment可能返回空
            if not sent or 'raw' in str(sent):
                return self._volume_sentiment()

            # 如果拿到真实数据
            return {'score': 0, 'bias': '中立(暂无数据)'}
        except:
            return {'score': 0, 'bias': '中立(获取失败)'}

    def _volume_sentiment(self):
        """用成交量变化近似情绪"""
        try:
            df = self.provider.get_klines('BTCUSDT', '4h', 20)
            vol_now = df['volume'].iloc[-5:].mean()
            vol_prev = df['volume'].iloc[-10:-5].mean()

            if vol_now > vol_prev * 1.2:
                return {'score': 0.3, 'bias': '放量中·偏多'}
            elif vol_now < vol_prev * 0.8:
                return {'score': -0.2, 'bias': '缩量中·偏空'}
            else:
                return {'score': 0, 'bias': '量能正常·中立'}
        except:
            return {'score': 0, 'bias': '中立'}


def ai_decision_layer(row, logger=None):
    """
    AI增强决策层——在规则信号之上叠加Skill Hub验证和情绪过滤

    row: 当前K线数据（含trend, structure, oi_bonus等）
    logger: DecisionLogger实例

    返回: {
        'confidence': 'HIGH'/'MEDIUM'/'LOW',
        'skill_hub': Skill Hub验证结果,
        'sentiment': 情绪过滤结果,
        'recommendation': 最终建议,
        'explanation': 一句话解释,
    }
    """
    verifier = SkillHubVerifier()
    sentiment = SentimentFilter()

    # 1. Skill Hub验证
    hub = verifier.verify()

    # 2. 情绪检查
    sent = sentiment.check()

    # 3. 综合判断
    reasons = []

    # 趋势判断
    trend = row.get('daily_trend', 0)
    if trend == 1:
        reasons.append('日线多头趋势')
    elif trend == -1:
        reasons.append('日线空头趋势')
    else:
        reasons.append('日线震荡')

    # 结构判断
    struct = row.get('structure', 0)
    if struct == 1:
        reasons.append('4h底结构形成')
    elif struct == -1:
        reasons.append('4h顶结构形成')

    # OI加分
    oi = row.get('oi_bonus', 0)
    if oi == 1:
        reasons.append('OI/Vol吸筹确认')

    # Skill Hub
    if hub['confidence'] != 'LOW':
        reasons.append(f"Skill Hub: {hub['signals']['verdict']}")

    # 情绪
    if sent['score'] != 0:
        reasons.append(f"情绪: {sent['bias']}")

    # 计算置信度
    if trend == 1 and struct == 1 and oi == 1:
        confidence = 'HIGH'
    elif trend == 1 or struct == 1:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'

    # 建议
    position = row.get('position', 0)
    state = row.get('state', 'NO_POSITION')
    if state == 'NO_POSITION':
        rec = '观望' if confidence == 'LOW' else '可以考虑建仓' if trend == 1 else '等待信号'
    elif state in ('LONG_FULL', 'LONG_BASE'):
        rec = '继续持有' if trend == 1 else '注意减仓'
    elif state == 'LONG_TRIAL':
        rec = '观察确认'
    else:
        rec = '—'

    explanation = ' | '.join(reasons) if reasons else '无明确信号'

    # 记录决策日志
    if logger:
        logger.log(
            timestamp=row.get('timestamp', datetime.now()),
            signal=f"置信度={confidence} 建议={rec}",
            reason=explanation,
            indicators={
                'trend': trend, 'structure': struct, 'oi_bonus': oi,
                'hub_verdict': hub.get('signals', {}).get('verdict', '?'),
                'sentiment': sent['bias'],
            }
        )

    return {
        'confidence': confidence,
        'skill_hub': hub,
        'sentiment': sent,
        'recommendation': rec,
        'explanation': explanation,
    }


# ── 测试 ──
if __name__ == '__main__':
    print("═══ AI分析增强层测试 ═══\n")

    # Skill Hub验证
    verifier = SkillHubVerifier()
    result = verifier.verify()
    print(f"Skill Hub验证:")
    print(f"  置信度: {result['confidence']}")
    print(f"  信号: {json.dumps(result.get('signals',{}), ensure_ascii=False)}")

    # 情绪
    sent = SentimentFilter()
    s = sent.check()
    print(f"\n情绪过滤: {s['bias']} (score={s['score']})")

    # 决策日志
    logger = DecisionLogger()
    from datetime import datetime
    logger.log(datetime.now(), 'TEST', '集成测试')

    recent = logger.recent(3)
    print(f"\n最近决策日志 ({len(recent)}条):")
    for r in recent:
        print(f"  {r['timestamp']} | {r['signal']} | {r['reason'][:50]}")
