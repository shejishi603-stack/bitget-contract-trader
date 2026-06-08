"""
历史回测 2022-2025（日线趋势通道 + 简化仓位）
Bitget 4h数据只到2025.11，所以2022-2024用日线独立回测
"""
import pandas as pd
import numpy as np
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from indicators import trend_channel
from backtest import BacktestEngine

PROXY = "http://172.30.112.1:7897"
import urllib.request
ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
opener = urllib.request.build_opener(ph)

def fetch_all_daily():
    """拉2022年起的全部日线"""
    all_data = []
    seen = set()
    end_ms = None
    from_ms = int(pd.Timestamp('2022-01-01').timestamp() * 1000)

    for _ in range(20):
        url = f"https://api.bitget.com/api/v2/spot/market/candles?symbol=BTCUSDT&granularity=1day&limit=200"
        if end_ms:
            url += f"&endTime={end_ms}"
        data = json.loads(opener.open(url, timeout=20).read())
        if 'data' not in data or not data['data']:
            break
        batch = data['data']
        for c in batch:
            if c[0] not in seen:
                seen.add(c[0])
                all_data.append(c)
        oldest = int(batch[-1][0])
        if oldest <= from_ms:
            break
        end_ms = oldest - 200 * 86400000

    df = pd.DataFrame(all_data, columns=[
        'timestamp','open','high','low','close','volume','quoteVol','amount'
    ])
    for col in ['open','high','low','close','volume','amount']:
        df[col] = df[col].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(np.int64), unit='ms')
    return df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)


def run_daily_backtest(df, start_year=2022):
    """日线级别简化回测：趋势翻多=开仓，趋势翻空=平仓"""
    df = trend_channel(df)
    df = df[df['timestamp'] >= f'{start_year}-01-01']

    engine = BacktestEngine(initial_capital=10000, leverage=5)
    equity = []
    state = 'FLAT'
    entry_price = 0
    trades = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        price = row['close']
        trend = row['trend']

        if state == 'FLAT' and trend == 1:
            # 翻多开仓
            engine.open_long(price, 0.50, row['timestamp'])
            state = 'LONG'
            entry_price = price
        elif state == 'LONG' and trend == -1:
            # 翻空平仓
            pnl = engine.close_long(price, 1.0, row['timestamp'], '趋势翻空')
            trades.append({
                'entry': entry_price,
                'exit': price,
                'entry_date': '...',
                'exit_date': str(row['timestamp'])[:10],
                'pnl': (price - entry_price) / entry_price * 500,  # 5x * 50%仓位
            })
            state = 'FLAT'
            entry_price = 0

        eq = engine.get_equity(price)
        equity.append(eq)

    # 统计
    if trades:
        pnls = [t['pnl'] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        return {
            'period': f"{start_year}-2025",
            'start': str(df['timestamp'].iloc[0])[:10],
            'end': str(df['timestamp'].iloc[-1])[:10],
            'days': len(df),
            'trades': len(trades),
            'wins': wins,
            'losses': len(trades) - wins,
            'win_rate': f"{wins/len(trades)*100:.1f}%" if trades else "N/A",
            'total_return': f"{(equity[-1]/10000-1)*100:.1f}%",
            'max_dd': '见资金曲线',
            'avg_win': f"{np.mean([t['pnl'] for t in trades if t['pnl']>0]):.1f}%" if wins > 0 else "N/A",
            'avg_loss': f"{np.mean([t['pnl'] for t in trades if t['pnl']<=0]):.1f}%" if len(trades)-wins > 0 else "N/A",
            'equity': equity[::max(1, len(equity)//100)],
            'timestamps': [str(df['timestamp'].iloc[i])[:10] for i in range(0, len(equity), max(1, len(equity)//100))][:100],
            'detail': [{
                'entry': str(df.iloc[max(0, i-1)]['timestamp'])[:10] if state else '...',
                'exit': t['exit_date'],
                'pnl': f"{t['pnl']:+.1f}%"
            } for t in trades[-10:]],
            'yearly': {}
        }
    return None


if __name__ == '__main__':
    print("拉取日线数据 2022-2025...")
    df = fetch_all_daily()
    print(f"共 {len(df)} 根日线, {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")

    # 跑3个时间段
    for start in [2022, 2023, 2024]:
        result = run_daily_backtest(df.copy(), start)
        if result:
            fname = f"/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/data/backtest_{start}.json"
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            with open(fname, 'w') as f:
                json.dump(result, f, ensure_ascii=False)
            print(f"\n{start}-2025 回测:")
            print(f"  交易: {result['trades']}笔")
            print(f"  胜率: {result['win_rate']}")
            print(f"  收益: {result['total_return']}")
            print(f"  保存至: {fname}")
