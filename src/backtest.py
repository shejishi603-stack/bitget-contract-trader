"""
专业回测引擎
支持: 多仓位加权均价 · 手续费 · 资金曲线 · 最大回撤 · 夏普比率
"""
import pandas as pd
import numpy as np
from datetime import datetime


class BacktestEngine:
    def __init__(self, initial_capital=10000, leverage=5, fee_rate=0.0004):
        self.initial = initial_capital
        self.leverage = leverage
        self.fee_rate = fee_rate
        self.reset()

    def reset(self):
        self.cash = self.initial
        self.position = 0.0   # 合约张数（等值美元）
        self.avg_price = 0.0  # 加权均价
        self.equity = []      # 资金曲线
        self.trades = []      # 交易记录
        self.bar_idx = 0

    def _size_to_contracts(self, size_pct, price):
        """仓位百分比 → 合约价值（用杠杆）"""
        capital = self.initial  # 始终用初始本金算仓位
        return capital * size_pct * self.leverage / price

    def open_long(self, price, size_pct, timestamp=None):
        """开多仓"""
        fee = self.initial * size_pct * self.leverage * self.fee_rate
        contracts = self._size_to_contracts(size_pct, price)

        # 加权均价
        if self.position > 0:
            total_value = self.position * self.avg_price + contracts * price
            self.position += contracts
            self.avg_price = total_value / self.position
        else:
            self.position = contracts
            self.avg_price = price

        self.cash -= fee
        self.trades.append({
            'type': 'OPEN', 'price': price, 'size_pct': size_pct,
            'fee': fee, 'timestamp': timestamp,
            'position': self.position, 'avg_price': self.avg_price
        })

    def close_long(self, price, close_pct=None, timestamp=None, reason=''):
        """平多仓（部分或全部）"""
        if self.position <= 0:
            return 0

        if close_pct is None:
            close_pct = 1.0

        close_contracts = self.position * close_pct
        fee = close_contracts * price * self.fee_rate
        pnl = close_contracts * (price - self.avg_price)

        self.position -= close_contracts
        self.cash -= fee
        self.cash += pnl

        pnl_pct = (pnl / (self.initial * self.leverage * 0.5)) * 100 if self.initial > 0 else 0

        self.trades.append({
            'type': 'CLOSE', 'price': price, 'close_pct': close_pct,
            'pnl': pnl, 'pnl_pct': pnl_pct, 'fee': fee,
            'reason': reason, 'timestamp': timestamp,
            'position': self.position, 'avg_price': self.avg_price
        })

        if self.position < 0.0001:
            self.position = 0
            self.avg_price = 0

        return pnl

    def get_equity(self, price):
        """当前净值（现金 + 持仓浮盈）"""
        if self.position > 0:
            unrealized = self.position * (price - self.avg_price)
            return self.cash + unrealized
        return self.cash

    def get_position_pct(self, price):
        """当前仓位占总资金的百分比"""
        if self.position <= 0:
            return 0
        return (self.position * price / self.leverage) / self.initial * 100

    def get_leverage_exposure(self):
        """杠杆暴露倍数"""
        return (self.position * self.avg_price) / (self.initial * self.leverage)

    def stats(self, equity_curve):
        """统计指标"""
        if not equity_curve or len(equity_curve) < 2:
            return {}

        eq = pd.Series(equity_curve)
        returns = eq.pct_change().dropna()

        # 夏普比率（年化，假设4h = 2190根/年）
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(2190)
        else:
            sharpe = 0

        # 最大回撤
        peak = eq.cummax()
        drawdown = (eq - peak) / peak * 100
        max_dd = drawdown.min()

        # 基本指标
        total_return = (eq.iloc[-1] - self.initial) / self.initial * 100

        # 交易统计
        closes = [t for t in self.trades if t['type'] == 'CLOSE']
        wins = sum(1 for t in closes if t.get('pnl', 0) > 0)

        return {
            '总收益率': f"{total_return:.1f}%",
            '最大回撤': f"{max_dd:.1f}%",
            '夏普比率': f"{sharpe:.2f}",
            '交易次数': len(closes),
            '盈利次数': wins,
            '亏损次数': len(closes) - wins,
            '胜率': f"{wins/len(closes)*100:.1f}%" if closes else "N/A",
            '总盈亏': f"${sum(t.get('pnl',0) for t in closes):.0f}",
        }

    def summary(self, equity_curve):
        """完整回测报告"""
        stats = self.stats(equity_curve)

        # 交易明细
        trade_details = []
        open_trade = None
        for t in self.trades:
            if t['type'] == 'OPEN':
                open_trade = t
            elif t['type'] == 'CLOSE' and open_trade:
                trade_details.append({
                    'entry': open_trade['timestamp'],
                    'entry_price': open_trade['price'],
                    'exit': t['timestamp'],
                    'exit_price': t['price'],
                    'pnl_pct': t.get('pnl_pct', 0),
                    'reason': t.get('reason', ''),
                    'size': open_trade['size_pct']
                })
                open_trade = None

        return {
            'stats': stats,
            'trades': trade_details,
            'equity_curve': equity_curve,
            'final_equity': equity_curve[-1] if equity_curve else self.initial
        }


def run_backtest(df, signals_df, initial=10000, leverage=5):
    """
    用信号数据跑回测
    df: 原始K线（含close）
    signals_df: generate_signals输出的信号（含action, position）
    """
    engine = BacktestEngine(initial, leverage)
    equity_curve = []

    for i in range(len(signals_df)):
        row = signals_df.iloc[i]
        price = row['close']
        action = row.get('action', '')
        target_pos = row.get('position', 0)
        current_pos = engine.get_position_pct(price)

        # 开仓
        if '建仓' in action or '试仓' in action:
            size = target_pos  # 0.3 or 0.1
            engine.open_long(price, size, row.get('timestamp'))

        # 加仓
        elif '加仓' in action:
            size = target_pos - current_pos / 100
            if size > 0:
                engine.open_long(price, size, row.get('timestamp'))

        # 减仓
        elif '减仓' in action or '止盈' in action:
            close_frac = (current_pos / 100 - target_pos) / (current_pos / 100)
            if close_frac > 0:
                engine.close_long(price, close_frac, row.get('timestamp'), action)

        # 全平
        elif '全平' in action or '止损' in action:
            engine.close_long(price, 1.0, row.get('timestamp'), action)

        # 记录资金曲线
        eq = engine.get_equity(price)
        equity_curve.append(eq)

    return engine.summary(equity_curve)


if __name__ == '__main__':
    # 用strategy.py的信号跑完整回测
    import sys, json, urllib.request
    sys.path.insert(0, '/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/src')
    from indicators import trend_channel, macd_structure
    from strategy import merge_daily_4h, generate_signals

    PROXY = "http://172.30.112.1:7897"
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)

    def fetch_candles(symbol, granularity, limit, end_ms=None):
        url = f"https://api.bitget.com/api/v2/spot/market/candles?symbol={symbol}&granularity={granularity}&limit={limit}"
        if end_ms:
            url += f"&endTime={end_ms}"
        resp = opener.open(url, timeout=15)
        return json.loads(resp.read())['data']

    # 拉日线
    raw_d = fetch_candles('BTCUSDT', '1day', 200)
    df_d = pd.DataFrame(raw_d, columns=['timestamp','open','high','low','close','volume','quoteVol','amount'])
    for col in ['open','high','low','close','volume','amount']:
        df_d[col] = df_d[col].astype(float)
    df_d['timestamp'] = pd.to_datetime(df_d['timestamp'].astype(np.int64), unit='ms')
    df_d = df_d.sort_values('timestamp').reset_index(drop=True)
    df_d = trend_channel(df_d)

    # 拉4h
    raw_4h = fetch_candles('BTCUSDT', '4h', 500)
    df_4h = pd.DataFrame(raw_4h, columns=['timestamp','open','high','low','close','volume','quoteVol','amount'])
    for col in ['open','high','low','close','volume','amount']:
        df_4h[col] = df_4h[col].astype(float)
    df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'].astype(np.int64), unit='ms')
    df_4h = df_4h.sort_values('timestamp').reset_index(drop=True)
    df_4h = macd_structure(df_4h)

    # 合并+信号
    df = merge_daily_4h(df_d, df_4h)
    signals, positions = generate_signals(df)

    # 回测
    result = run_backtest(df, signals, initial=10000, leverage=5)

    # 输出
    print(f"\n{'='*60}")
    print(f"  【回测报告】BTC合约 · 只做多 · 5倍杠杆")
    print(f"{'='*60}")
    print(f"周期: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
    print(f"初始资金: ${result['final_equity']-sum(t['pnl_pct']/100*10000 for t in result['trades']):.0f}")
    print(f"最终净值: ${result['final_equity']:.0f}")

    print(f"\n── 核心指标 ──")
    for k, v in result['stats'].items():
        print(f"  {k}: {v}")

    print(f"\n── 交易明细 ──")
    for i, t in enumerate(result['trades']):
        entry = str(t['entry'])[:10]
        exit = str(t['exit'])[:10]
        pnl = t['pnl_pct']
        emoji = '🟢' if pnl > 0 else '🔴'
        print(f"  {i+1}. {entry}→{exit} | {t['size']*100:.0f}%仓位 | {emoji} {pnl:+.1f}% | {t['reason'][:20]}")

    print(f"\n── 资金曲线(最近) ──")
    curve = result['equity_curve']
    step = max(1, len(curve) // 20)
    for i in range(0, len(curve), step):
        bar = int(curve[i] / 100)
        ts = str(signals.iloc[i]['timestamp'])[:10]
        print(f"  {ts} ${curve[i]:>8.0f} {'█' * min(bar, 60)}")
