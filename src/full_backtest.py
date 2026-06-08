"""
完整回测脚本 — BTC合约 2023年至今
"""
import pandas as pd
import numpy as np
import json, urllib.request, sys
from datetime import datetime

sys.path.insert(0, '/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/src')
from indicators import trend_channel, macd_structure, oi_signal
from strategy import merge_daily_4h, generate_signals
from backtest import BacktestEngine, run_backtest

PROXY = "http://172.30.112.1:7897"
proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
opener = urllib.request.build_opener(proxy_handler)

def fetch_paginated(symbol, granularity, limit, from_date_str):
    """分页拉取 - 修正版：大步跳+去重"""
    all_data = []
    from_ms = int(pd.Timestamp(from_date_str).timestamp() * 1000)
    now_ms = int(pd.Timestamp.now().timestamp() * 1000)
    
    # 先拉第一页(最新)，然后逐步向前跳
    end_ms = None
    total_pages = 0
    seen = set()
    
    while total_pages < 30:
        url = f"https://api.bitget.com/api/v2/spot/market/candles?symbol={symbol}&granularity={granularity}&limit={limit}"
        if end_ms:
            url += f"&endTime={end_ms}"
        
        for attempt in range(3):
            try:
                resp = opener.open(url, timeout=20)
                data = json.loads(resp.read())
                break
            except:
                if attempt == 2:
                    raise
                import time
                time.sleep(2)
        
        if 'data' not in data or not data['data']:
            break
        
        batch = data['data']
        
        # 去重新数据加入
        new_count = 0
        for candle in batch:
            if candle[0] not in seen:
                seen.add(candle[0])
                all_data.append(candle)
                new_count += 1
        
        oldest_in_batch = int(batch[-1][0])
        
        # 如果已到目标日期，停止
        if oldest_in_batch <= from_ms:
            break
        
        # 大步向前跳（不同周期用不同步长）
        if granularity == '4h':
            end_ms = oldest_in_batch - 30 * 86400000  # 4h: ~33天/页
        else:
            end_ms = oldest_in_batch - 200 * 86400000  # 日线: 200天/页
        total_pages += 1
        
        if total_pages % 3 == 0:
            first_ts = pd.to_datetime(oldest_in_batch, unit='ms')
            print(f"  [{total_pages}] 拉到 {first_ts} ({len(all_data)}根有效)")

    return all_data


def process_candles(raw_data):
    """原始数据 → DataFrame"""
    df = pd.DataFrame(raw_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'quoteVol', 'amount'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df[col] = df[col].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(np.int64), unit='ms')
    df = df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    return df


# ═══════════════════════════════════
print("正在拉取数据...")
print("=" * 50)

# 拉日线 (2023-01-01起)
print("\n📊 日线...")
raw_daily = fetch_paginated('BTCUSDT', '1day', 200, '2023-01-01')
df_daily = process_candles(raw_daily)
df_daily = trend_channel(df_daily)
print(f"  日线: {len(df_daily)}根, {df_daily['timestamp'].iloc[0]} ~ {df_daily['timestamp'].iloc[-1]}")

# 拉4h线
print("\n📊 4h线...")
raw_4h = fetch_paginated('BTCUSDT', '4h', 200, '2023-01-01')
df_4h = process_candles(raw_4h)
df_4h = macd_structure(df_4h)
df_4h = oi_signal(df_4h)  # OI/Vol 加分
print(f"  4h: {len(df_4h)}根, {df_4h['timestamp'].iloc[0]} ~ {df_4h['timestamp'].iloc[-1]}")

# 合并 + 信号
print("\n📊 计算信号...")
df = merge_daily_4h(df_daily, df_4h)
signals, positions = generate_signals(df)

# 回测
print("📊 回测中...\n")
result = run_backtest(df, signals, initial=10000, leverage=5)

# ═══════════════════════════════════
# 输出报告
# ═══════════════════════════════════
print(f"\n{'='*60}")
print(f"  BTC合约回测报告 — 只做多 · 5倍杠杆")
print(f"  周期: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
print(f"{'='*60}")

# 分段统计
total_days = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).days
print(f"\n  覆盖 {total_days} 天, {len(result['trades'])} 笔交易\n")

print(f"  {'─'*50}")
print(f"  {'指标':<20} {'数值':>15}")
print(f"  {'─'*50}")
for k, v in result['stats'].items():
    print(f"  {k:<20} {v:>15}")
print(f"  {'─'*50}")

# 交易明细
print(f"\n  {'─'*60}")
print(f"  交易明细")
print(f"  {'─'*60}")
total_pnl = 0
for i, t in enumerate(result['trades']):
    entry = str(t['entry'])[:10]
    ext = str(t['exit'])[:10]
    pnl = t['pnl_pct']
    total_pnl += pnl
    emoji = '🟢' if pnl > 0 else '🔴'
    size = f"{t['size']*100:.0f}%"
    print(f"  {i+1:>2}. {entry} → {ext} | {size:>3s} | {emoji} {pnl:>+6.1f}% | {t['reason'][:25]}")

print(f"  {'─'*60}")
print(f"  累计: {total_pnl:+.1f}%")

# 资金曲线摘要
print(f"\n  {'─'*60}")
print(f"  资金曲线(每月)")
print(f"  {'─'*60}")
eq = result['equity_curve']
# 取每月最后一个点
monthly = {}
for i in range(len(signals)):
    ts = signals.iloc[i]['timestamp']
    key = f"{ts.year}-{ts.month:02d}"
    monthly[key] = eq[i]

prev = 10000
for month, val in sorted(monthly.items()):
    chg = (val - prev) / prev * 100
    bar_len = max(1, int((val - 10000) / 200))
    bar = '█' * min(abs(bar_len), 40)
    sign = '+' if bar_len >= 0 else '-'
    print(f"  {month} ${val:>8.0f} {sign}{chg:>+6.1f}% {bar}")
    prev = val
