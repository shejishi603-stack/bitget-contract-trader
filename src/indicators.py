"""
趋势通道 + 结构检测
基于 炒币的猫 交易系统：
  - 趋势通道：EMA(high,32) / EMA(low,32) 定方向
  - 结构：MACD钝化+结构形成 定买卖点
"""
import pandas as pd
import numpy as np


def trend_channel(df):
    """
    趋势通道指标
    输入: DataFrame 包含 high, low, close 列
    输出: 添加以下列
      - long_line:  多头线 EMA(high, 32)
      - short_line: 空头线 EMA(low, 32)
      - trend: 1=多头(价格>多头线), -1=空头(价格<多头线), 0=方向不明
    """
    df = df.copy()
    df['long_line'] = df['high'].ewm(span=32, adjust=False).mean()
    df['short_line'] = df['low'].ewm(span=32, adjust=False).mean()

    def _trend(row):
        if row['close'] > row['long_line']:
            return 1      # 多头趋势
        elif row['close'] < row['short_line']:
            return -1     # 空头趋势
        else:
            return 0      # 通道内震荡

    df['trend'] = df.apply(_trend, axis=1)
    return df


def macd_structure(df, fast=12, slow=26, signal=9):
    """
    MACD结构检测（钝化 → 结构形成）
    输入: DataFrame 包含 close 列
    输出: 添加以下列
      - DIF: MACD差离值
      - DEA: 信号线
      - HIST: 柱状线
      - dull: 是否钝化 (1=底钝化, -1=顶钝化, 0=无)
      - structure: 结构形成信号 (1=底结构=买点, -1=顶结构=卖点, 0=无)
      - dull_break: 钝化消失/纠错信号

    钝化判定（简化版）：
      底钝化：价格新低 但 DIF不新低，且至少2根反向角线
      顶钝化：价格新高 但 DIF不新高，且至少2根反向角线
    结构形成：钝化状态下 DIF拐头
    钝化消失：DIF值低于（或高于）钝化前锋值
    """
    df = df.copy()

    # MACD计算
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['DIF'] = ema_fast - ema_slow
    df['DEA'] = df['DIF'].ewm(span=signal, adjust=False).mean()
    df['HIST'] = 2 * (df['DIF'] - df['DEA'])

    # 初始化信号列
    df['dull'] = 0
    df['structure'] = 0
    df['dull_break'] = 0

    N = len(df)
    if N < 60:
        return df

    lookback = 40  # 回看区间

    for i in range(lookback, N):
        window = df.iloc[i-lookback:i+1]
        now = df.iloc[i]
        prev = df.iloc[i-1]

        # --- 底钝化 ---
        price_low_20 = window['close'].iloc[-20:].min()
        price_low_now = now['close']
        dif_low_20 = window['DIF'].iloc[-20:].min()
        dif_now = now['DIF']

        if price_low_now <= price_low_20 and dif_now > dif_low_20:
            df.at[df.index[i], 'dull'] = 1  # 底钝化

        # --- 顶钝化 ---
        price_high_20 = window['close'].iloc[-20:].max()
        price_high_now = now['close']
        dif_high_20 = window['DIF'].iloc[-20:].max()

        if price_high_now >= price_high_20 and dif_now < dif_high_20:
            df.at[df.index[i], 'dull'] = -1  # 顶钝化

        # --- 结构形成（钝化后DIF拐头） ---
        # 底结构：前一根DIF在下降，当前DIF开始上升
        if prev.get('dull', 0) == 1 and now['DIF'] > prev['DIF']:
            df.at[df.index[i], 'structure'] = 1

        # 顶结构：前一根DIF在上升，当前DIF开始下降
        if prev.get('dull', 0) == -1 and now['DIF'] < prev['DIF']:
            df.at[df.index[i], 'structure'] = -1

    return df


def combined_signal(df):
    """
    综合信号：趋势 + 结构
    根据 炒币的猫 规则：
      - 趋势上(1) = 原则上满仓做多
      - 趋势下(-1) = 原则上满仓做空
      - 趋势上 + 顶结构 = 减仓/止盈信号
      - 趋势下 + 底结构 = 建仓/试仓信号

    输出信号值：
      2 = 趋势上 + 底结构（满仓多+加仓）
      1 = 趋势上（满仓做多）
      0 = 通道内（观望/轻仓）
     -1 = 趋势下（满仓做空）
     -2 = 趋势下 + 顶结构（满仓空+加仓）
    """
    df = df.copy()

    def _signal(row):
        t = row.get('trend', 0)
        s = row.get('structure', 0)

        if t == 1 and s == 1:
            return 2   # 多头趋势+底结构 = 最强的做多信号
        elif t == 1 and s == -1:
            return 0.5  # 多头趋势+顶结构 = 减仓观望
        elif t == 1:
            return 1   # 纯多头趋势
        elif t == -1 and s == -1:
            return -2  # 空头趋势+顶结构 = 最强的做空信号
        elif t == -1 and s == 1:
            return -0.5  # 空头趋势+底结构 = 减仓观望
        elif t == -1:
            return -1  # 纯空头趋势
        else:
            return 0   # 通道内震荡

    dull_now = now.get('dull', 0)
    dull_prev = prev.get('dull', 0)


def oi_signal(df):
    """
    OI/Vol 比率信号
    OI/Vol上升 + 价格下降 = 吸筹信号(1)
    OI/Vol下降 + 价格上升 = 出货信号(-1)
    权重: 10%，仅作为趋势/结构的加分项
    """
    df = df.copy()
    df['oi_vol_ratio'] = 0.0
    df['oi_bonus'] = 0  # 0=无信号, 1=加分, -1=减分

    # 需要至少20根K线计算变化率
    if 'volume' not in df.columns or len(df) < 20:
        return df

    # 用volume近似计算OI/Vol（无历史OI数据时用volume变化替代）
    # Bitget API只能拿当前OI，历史OI不可用
    # 方案：用volume趋势替代OI/Vol趋势
    # volume↓ = OI/Vol↑（成交量萎缩，持仓不变=比率上升）
    # 较上一根，volume下降+价格下降 → 加分

    vol_ma5 = df['volume'].rolling(5).mean()
    price_ma5 = df['close'].rolling(5).mean()

    for i in range(5, len(df)):
        vol_now = df['volume'].iloc[i]
        vol_prev = vol_ma5.iloc[i-5] if i >= 10 else vol_now
        price_now = df['close'].iloc[i]
        price_prev = price_ma5.iloc[i-5] if i >= 10 else price_now

        # OI/Vol上升(成交量缩量) + 价格下降 → 吸筹 加分
        if vol_now < vol_prev * 0.85 and price_now < price_prev:
            df.at[df.index[i], 'oi_bonus'] = 1

        # OI/Vol下降(成交量放量) + 价格上升 → 出货 减分
        elif vol_now > vol_prev * 1.15 and price_now > price_prev:
            df.at[df.index[i], 'oi_bonus'] = -1

    return df


# ── 测试入口 ──
if __name__ == '__main__':
    import sys
    import json
    import urllib.request

    PROXY = "http://172.30.112.1:7897"
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)

    # 拉BTC 4h K线
    url = "https://api.bitget.com/api/v2/spot/market/candles?symbol=BTCUSDT&granularity=4h&limit=200"
    resp = opener.open(url, timeout=15)
    raw = json.loads(resp.read())

    df = pd.DataFrame(raw['data'], columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'quoteVol', 'amount'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df[col] = df[col].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(np.int64), unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)

    # 计算所有指标
    df = trend_channel(df)
    df = macd_structure(df)
    df = combined_signal(df)

    # 输出最新状态
    last = df.iloc[-1]
    print(f"\n{'='*50}")
    print(f"BTC 4h 趋势通道分析")
    print(f"{'='*50}")
    print(f"时间: {last['timestamp']}")
    print(f"价格: {last['close']:.2f}")
    print(f"多头线(EMA high 32): {last['long_line']:.2f}")
    print(f"空头线(EMA low 32):  {last['short_line']:.2f}")
    print(f"趋势: {'多头' if last['trend']==1 else '空头' if last['trend']==-1 else '震荡'}")

    signal_map = {2:'强多',1:'做多',0.5:'减仓多',0:'观望',-0.5:'减仓空',-1:'做空',-2:'强空'}
    print(f"综合信号: {signal_map.get(last['signal'], last['signal'])}")

    # 显示最近信号变化
    print(f"\n最近10根K线信号:")
    recent = df[['timestamp','close','trend','DIF','structure','signal']].tail(10)
    for _, row in recent.iterrows():
        t = '多' if row['trend']==1 else '空' if row['trend']==-1 else '震'
        s = '底↑' if row['structure']==1 else '顶↓' if row['structure']==-1 else '-'
        sig = signal_map.get(row['signal'], row['signal'])
        diff = f"({row['DIF']:+.1f})"
        print(f"  {str(row['timestamp'])[:16]} | {row['close']:>9.1f} | {t} {diff} | 结构{s} | {sig}")

    # 统计近期结构信号
    structs = df[df['structure'] != 0]
    if len(structs) > 0:
        print(f"\n近期结构信号 ({len(structs)}个):")
        for _, row in structs.tail(5).iterrows():
            kind = '底结构(买点)' if row['structure'] == 1 else '顶结构(卖点)'
            print(f"  {str(row['timestamp'])[:16]} | {row['close']:.1f} | {kind}")
