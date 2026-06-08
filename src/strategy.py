"""
合同交易策略引擎
只做多 · 5倍杠杆 · 日线定方向 · 4h找结构
基于 炒币的猫 交易系统 + OI/Vol 加分
"""
import pandas as pd
import numpy as np
from indicators import trend_channel, macd_structure, oi_signal


def merge_daily_4h(daily_df, h4_df):
    """
    日线和4h数据合并，4h每根K线打上当日趋势
    daily_df: 日线数据（含trend, long_line, short_line）
    h4_df:    4h数据（含structure, DIF, DEA, HIST, dull）
    返回: h4_df 附加 daily_trend, daily_long_line, daily_short_line
    """
    h4 = h4_df.copy()
    h4['date'] = h4['timestamp'].dt.date

    daily = daily_df[['timestamp', 'trend', 'long_line', 'short_line']].copy()
    daily['date'] = daily['timestamp'].dt.date
    daily = daily.rename(columns={
        'trend': 'daily_trend',
        'long_line': 'daily_long',
        'short_line': 'daily_short'
    })

    merged = h4.merge(
        daily[['date', 'daily_trend', 'daily_long', 'daily_short']],
        on='date', how='left'
    )
    merged['daily_trend'] = merged['daily_trend'].fillna(0)
    return merged


def distance_to_trend(row):
    """
    价格离多头线的距离百分比
    返回: (距离%, 远近判断)
    """
    if row['daily_long'] and row['daily_long'] > 0:
        dist_pct = (row['daily_long'] - row['close']) / row['daily_long'] * 100
        near = abs(dist_pct) < 3  # 3%以内算近
        return dist_pct, near
    return 999, False


def generate_signals(df):
    """
    交易系统 2.0核心 + 3.0改进
    只做多  5倍杠杆  日线定方向  4h找结构
    3.0改进: 底仓思维(30%) + 突破加仓 + 防守优先(试仓10%)

    状态机: NO_POSITION/LONG_BASE/LONG_FULL/LONG_REDUCED/LONG_TRIAL/FLAT
    """
    df = df.copy()
    N = len(df)

    # 信号列
    df['signal'] = ''
    df['position'] = 0.0   # 目标仓位比例
    df['action'] = ''
    df['entry_price'] = np.nan
    df['pnl_pct'] = 0.0

    # 状态追踪
    # NO_POSITION / LONG_BASE / LONG_FULL / LONG_REDUCED / LONG_TRIAL
    state = 'NO_POSITION'
    entry_price = 0
    entry_bar = -1            # 开仓那根K线的索引
    trend_opened = False      # 趋势信号是否已在这笔订单触发过
    struct_opened = False     # 结构信号是否已在这笔订单触发过
    take_profit_triggered = False  # 100%止盈是否已触发过
    daily_confirm_count = 0   # 日线站稳计数（底仓确认用）
    peak_pnl = 0              # 最高浮盈百分比
    recent_high = 0           # 近期前高（突破加仓用，看过去20根4h K线）
    positions = []            # 记录每笔订单

    # 日线收盘确认: 记录上一根日线的趋势（新日线出来后才确认）
    prev_daily_trend = 0
    daily_confirmed = 0       # 已确认的日线趋势

    for i in range(1, N):
        now = df.iloc[i]
        prev = df.iloc[i-1]
        close = now['close']
        daily_trend = now.get('daily_trend', 0)
        structure = now.get('structure', 0)

        # --- 日线收盘确认 ---
        # 日线K线每24h一根，4h数据每6根对应一根日线
        # 当日线数据变化时确认
        if daily_trend != prev_daily_trend and not np.isnan(daily_trend):
            daily_confirmed = daily_trend
            prev_daily_trend = daily_trend

        # --- 计算距离趋势远近 ---
        dist, is_near = distance_to_trend(now)

        # --- 计算当前浮盈 ---
        current_pnl = 0
        if state != 'NO_POSITION' and entry_price > 0:
            current_pnl = (close - entry_price) / entry_price * 100 * 5  # 5倍杠杆
            if current_pnl > peak_pnl:
                peak_pnl = current_pnl

        # =================================================================
        # 状态机逻辑
        # =================================================================

        # ── 状态: 空仓 ──
        if state == 'NO_POSITION':
            # 条件1: 趋势翻多 → 3.0底仓思维，先建30%底仓
            if daily_confirmed == 1 and not trend_opened:
                state = 'LONG_BASE'
                entry_price = close
                entry_bar = i
                trend_opened = True
                struct_opened = False
                take_profit_triggered = False
                daily_confirm_count = 0
                peak_pnl = 0
                # 记录开仓时的近期前高
                lookback = min(20, i)
                recent_high = df['high'].iloc[i-lookback:i].max()
                df.at[df.index[i], 'signal'] = 'LONG_BASE'
                df.at[df.index[i], 'position'] = 0.30
                df.at[df.index[i], 'action'] = '日线翻多·底仓建仓(30%) 等确认'
                df.at[df.index[i], 'entry_price'] = close

            # 条件2: 趋势下 + 底结构 → 3.0防守优先，只试仓10%
            elif daily_confirmed == -1 and structure == 1 and not struct_opened:
                state = 'LONG_TRIAL'
                entry_price = close
                entry_bar = i
                trend_opened = False
                struct_opened = True
                take_profit_triggered = False
                peak_pnl = 0

                # OI加分: 缩量下跌=吸筹确认 → +5%
                oi_b = now.get('oi_bonus', 0)
                if oi_b == 1:
                    size = 0.15
                    desc = '底结构+OI确认·试仓(15%)'
                elif oi_b == -1:
                    size = 0.10
                    desc = '底结构·OI减分·试仓(10%)'
                else:
                    size = 0.10
                    desc = '底结构·试仓(10%)'

                df.at[df.index[i], 'signal'] = 'LONG_TRIAL'
                df.at[df.index[i], 'position'] = size
                df.at[df.index[i], 'action'] = desc
                df.at[df.index[i], 'entry_price'] = close

        # ── 状态: 底仓(30%) → 等待确认加仓 ──
        elif state == 'LONG_BASE':
            # 止损: 日线趋势翻空 → 全平
            if daily_confirmed == -1:
                state = 'FLAT'
                pnl = current_pnl
                df.at[df.index[i], 'signal'] = 'CLOSE_ALL'
                df.at[df.index[i], 'position'] = 0
                df.at[df.index[i], 'action'] = f'趋势翻空·底仓止损(PnL:{pnl:.1f}%)'
                trend_opened = False
                positions.append({'entry': entry_bar, 'exit': i, 'pnl': pnl})
                entry_price = 0

            # 确认方式1: 连续2根日线站上多头线
            elif close > now.get('daily_long', 0):
                daily_confirm_count += 1
                if daily_confirm_count >= 12:  # 12根4h ≈ 2根日线
                    state = 'LONG_FULL'
                    df.at[df.index[i], 'signal'] = 'ADD_TO_FULL'
                    df.at[df.index[i], 'position'] = 0.50
                    df.at[df.index[i], 'action'] = '日线站稳确认·加仓至满仓(50%)'

            # 确认方式2: 4h底结构出现 → 加仓（OI加分可到55%）
            elif structure == 1 and not struct_opened and daily_confirm_count < 12:
                state = 'LONG_FULL'
                struct_opened = True
                oi_b = now.get('oi_bonus', 0)
                if oi_b == 1:
                    target = 0.55
                    desc = '4h底结构+OI确认·加仓至55%'
                else:
                    target = 0.50
                    desc = '4h底结构确认·加仓至50%'
                df.at[df.index[i], 'signal'] = 'ADD_TO_FULL'
                df.at[df.index[i], 'position'] = target
                df.at[df.index[i], 'action'] = desc

            # 突破加仓: 价格突破近期前高(开仓时记下的recent_high)
            elif close > recent_high:
                state = 'LONG_FULL'
                df.at[df.index[i], 'signal'] = 'BREAKOUT_ADD'
                df.at[df.index[i], 'position'] = 0.50
                df.at[df.index[i], 'action'] = f'突破前高{recent_high:.0f}·加仓至50%'

            # 顶结构减仓（底仓也可能遇到）
            elif structure == -1 and not struct_opened:
                state = 'LONG_REDUCED'
                struct_opened = True
                df.at[df.index[i], 'signal'] = 'REDUCE'
                df.at[df.index[i], 'position'] = 0.30
                df.at[df.index[i], 'action'] = '顶结构·底仓减至30%'

            else:
                df.at[df.index[i], 'position'] = 0.30
        elif state == 'LONG_FULL':
            # 止损1: 日线趋势翻空 → 全平
            if daily_confirmed == -1:
                state = 'FLAT'
                pnl = current_pnl
                df.at[df.index[i], 'signal'] = 'CLOSE_ALL'
                df.at[df.index[i], 'position'] = 0
                df.at[df.index[i], 'action'] = f'趋势翻空·全平(PnL:{pnl:.1f}%)'
                trend_opened = False
                struct_opened = False
                positions.append({'entry': entry_bar, 'exit': i, 'pnl': pnl})

            # 止盈: 收益率100% → 平30%锁定利润
            elif current_pnl >= 100 and not take_profit_triggered:
                state = 'LONG_REDUCED'
                take_profit_triggered = True
                df.at[df.index[i], 'signal'] = 'TAKE_PROFIT'
                df.at[df.index[i], 'position'] = 0.30
                df.at[df.index[i], 'action'] = f'止盈100%·平30%锁定利润(剩余30%)'

            # 顶结构减仓
            elif structure == -1 and not struct_opened:
                state = 'LONG_REDUCED'
                struct_opened = True
                df.at[df.index[i], 'signal'] = 'REDUCE'
                df.at[df.index[i], 'position'] = 0.30
                df.at[df.index[i], 'action'] = '顶结构·减仓至30%'
                df.at[df.index[i], 'entry_price'] = close

            # 记录持仓
            else:
                df.at[df.index[i], 'position'] = 0.50

        # ── 状态: 减仓后(30%) ──
        elif state == 'LONG_REDUCED':
            # 止损: 趋势翻空 → 全平
            if daily_confirmed == -1:
                state = 'FLAT'
                pnl = current_pnl
                df.at[df.index[i], 'signal'] = 'CLOSE_ALL'
                df.at[df.index[i], 'position'] = 0
                df.at[df.index[i], 'action'] = f'趋势翻空·全平(PnL:{pnl:.1f}%)'
                trend_opened = False
                struct_opened = False
                positions.append({'entry': entry_bar, 'exit': i, 'pnl': pnl})
                entry_price = 0

            # ATR止损（跌破1.5×ATR）
            elif current_pnl < -30:
                state = 'FLAT'
                df.at[df.index[i], 'signal'] = 'STOP_LOSS'
                df.at[df.index[i], 'position'] = 0
                df.at[df.index[i], 'action'] = f'ATR止损(PnL:{current_pnl:.1f}%)'
                trend_opened = False
                struct_opened = False
                positions.append({'entry': entry_bar, 'exit': i, 'pnl': current_pnl})
                entry_price = 0

            # 趋势翻多(重新满仓) — 但趋势信号已触发过不重复
            # 只有结构信号可以再次触发
            elif structure == 1 and struct_opened:
                # 结构信号已用过，不重复
                pass

            else:
                df.at[df.index[i], 'position'] = 0.30

        # ── 状态: 试仓(15-20%) ──
        elif state == 'LONG_TRIAL':
            # 止损: 趋势翻空(本来就在趋势下)不一定是止损
            # 钝化消失才止损
            dull_now = now.get('dull', 0)
            dull_prev = prev.get('dull', 0)

            # 钝化消失: 底钝化(1)消失了
            if dull_prev == 1 and dull_now == 0:
                state = 'FLAT'
                pnl = current_pnl
                df.at[df.index[i], 'signal'] = 'STOP_LOSS'
                df.at[df.index[i], 'position'] = 0
                df.at[df.index[i], 'action'] = f'钝化消失·止损(PnL:{pnl:.1f}%)'
                struct_opened = False
                positions.append({'entry': entry_bar, 'exit': i, 'pnl': pnl})
                entry_price = 0

            # 趋势翻多 → 加仓到满仓(50%)
            elif daily_confirmed == 1 and not trend_opened:
                state = 'LONG_FULL'
                trend_opened = True
                df.at[df.index[i], 'signal'] = 'ADD_TO_FULL'
                df.at[df.index[i], 'position'] = 0.50
                df.at[df.index[i], 'action'] = '趋势翻多·加仓至满仓(50%)'

            # 止盈: 试仓100%收益也触发
            elif current_pnl >= 100 and not take_profit_triggered:
                state = 'LONG_REDUCED'
                take_profit_triggered = True
                df.at[df.index[i], 'signal'] = 'TAKE_PROFIT'
                df.at[df.index[i], 'position'] = 0.30
                df.at[df.index[i], 'action'] = f'试仓止盈100%·平30%锁定利润'

            else:
                df.at[df.index[i], 'position'] = df.at[df.index[i-1], 'position']

        # ── 状态: 已平仓 ──
        elif state == 'FLAT':
            # 平仓后等一根K线再判断
            state = 'NO_POSITION'
            trend_opened = False
            struct_opened = False
            take_profit_triggered = False
            entry_price = 0

        # 记录浮盈
        df.at[df.index[i], 'pnl_pct'] = current_pnl
        df.at[df.index[i], 'state'] = state

    return df, positions


def backtest_summary(positions, df):
    """回测统计"""
    if not positions:
        return "无交易记录"

    pnls = [p['pnl'] for p in positions]
    wins = sum(1 for p in pnls if p > 0)
    total = len(pnls)

    return {
        '总交易数': total,
        '盈利次数': wins,
        '亏损次数': total - wins,
        '胜率': f"{wins/total*100:.1f}%" if total > 0 else "N/A",
        '平均盈亏': f"{np.mean(pnls):.1f}%",
        '最大盈利': f"{max(pnls):.1f}%",
        '最大亏损': f"{min(pnls):.1f}%",
        '累计盈亏': f"{sum(pnls):.1f}%",
    }


# ── 测试入口 ──
if __name__ == '__main__':
    import sys
    import json
    import urllib.request

    PROXY = "http://172.30.112.1:7897"
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)

    def fetch_candles(symbol, granularity, limit, end_ms=None):
        """拉K线，支持分页"""
        url = f"https://api.bitget.com/api/v2/spot/market/candles?symbol={symbol}&granularity={granularity}&limit={limit}"
        if end_ms:
            url += f"&endTime={end_ms}"
        resp = opener.open(url, timeout=15)
        return json.loads(resp.read())['data']

    def fetch_all(symbol, granularity, limit, days_back):
        """分页拉取指定天数的全部K线"""
        all_data = []
        now_ms = int(pd.Timestamp.now().timestamp() * 1000)
        end_ms = now_ms
        fetched = 0
        max_requests = 20  # 安全上限

        while fetched < max_requests:
            batch = fetch_candles(symbol, granularity, limit, end_ms)
            if not batch:
                break
            all_data.extend(batch)
            oldest = int(batch[-1][0])
            target = now_ms - days_back * 24 * 3600 * 1000
            if oldest <= target or len(batch) < limit:
                break
            end_ms = oldest - 1
            fetched += 1
            print(f"  已拉 {len(all_data)} 根{ granularity }K线...")

        return all_data

    # 拉日线 (365天)
    print("正在拉取日线数据...")
    raw_d = fetch_all('BTCUSDT', '1day', 200, days_back=365)
    df_d = pd.DataFrame(raw_d, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'quoteVol', 'amount'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df_d[col] = df_d[col].astype(float)
    df_d['timestamp'] = pd.to_datetime(df_d['timestamp'].astype(np.int64), unit='ms')
    df_d = df_d.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    df_d = trend_channel(df_d)
    print(f"  日线共 {len(df_d)} 根, {df_d['timestamp'].iloc[0]} ~ {df_d['timestamp'].iloc[-1]}")

    # 拉4h线 (365天)
    print("正在拉取4h数据...")
    raw_4h = fetch_all('BTCUSDT', '4h', 1000, days_back=365)
    df_4h = pd.DataFrame(raw_4h, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'quoteVol', 'amount'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df_4h[col] = df_4h[col].astype(float)
    df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'].astype(np.int64), unit='ms')
    df_4h = df_4h.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    df_4h = macd_structure(df_4h)
    print(f"  4h共 {len(df_4h)} 根, {df_4h['timestamp'].iloc[0]} ~ {df_4h['timestamp'].iloc[-1]}")

    # 合并
    df = merge_daily_4h(df_d, df_4h)

    # 生成信号
    df, positions = generate_signals(df)

    # 输出
    print(f"\n{'='*60}")
    print(f"  合约策略回测 — 只做多 · 5倍杠杆 · 日线+4h")
    print(f"{'='*60}")

    # 最后状态
    last = df.iloc[-1]
    print(f"最新: {str(last['timestamp'])[:16]}")
    print(f"价格: {last['close']:.1f}")
    print(f"日线趋势: {'多头' if last['daily_trend']==1 else '空头' if last['daily_trend']==-1 else '震荡'}")
    print(f"日线多头线: {last['daily_long']:.1f}")
    print(f"状态: {last['state']}")
    print(f"仓位: {last['position']*100:.0f}%")
    print(f"浮盈: {last['pnl_pct']:.1f}%")

    # 信号记录
    signals = df[df['action'] != ''][['timestamp', 'close', 'action', 'position']].tail(20)
    if len(signals) > 0:
        print(f"\n近期信号:")
        for _, row in signals.iterrows():
            pos = f"{row['position']*100:.0f}%"
            print(f"  {str(row['timestamp'])[:16]} | {row['close']:>9.1f} | {pos:>4s} | {row['action']}")

    # 回测统计
    print(f"\n{'='*60}")
    print(f"  回测统计")
    print(f"{'='*60}")
    stats = backtest_summary(positions, df)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if len(positions) > 0:
        print(f"\n交易明细:")
        for i, p in enumerate(positions):
            e_bar = df.iloc[p['entry']]['timestamp']
            x_bar = df.iloc[p['exit']]['timestamp']
            print(f"  {i+1}. {str(e_bar)[:10]} → {str(x_bar)[:10]} | PnL: {p['pnl']:.1f}%")
