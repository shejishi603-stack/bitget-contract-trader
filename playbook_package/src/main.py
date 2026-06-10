from getagent import data, runtime
import pandas as pd
import numpy as np

EMA = 32
SYM = "BTCUSDT"

def compute_indicators(df):
    df = df.copy()
    df['long_line'] = df['high'].ewm(span=EMA, adjust=False).mean()
    df['short_line'] = df['low'].ewm(span=EMA, adjust=False).mean()
    e_fast = df['close'].ewm(span=12, adjust=False).mean()
    e_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = e_fast - e_slow
    return df

def run():
    bars = data.crypto.futures.kline(symbol=SYM, interval="4h", exchange="bitget")
    if bars is None or len(bars) == 0:
        runtime.emit_signal(action="hold", symbol=SYM, confidence=0)
        return
    df = compute_indicators(bars)
    close = float(df['close'].iloc[-1])
    long_l = float(df['long_line'].iloc[-1])
    short_l = float(df['short_line'].iloc[-1])
    if close > long_l:
        action, trend = "long", "bull"
    elif close < short_l:
        action, trend = "flat", "bear"
    else:
        action, trend = "hold", "neutral"
    runtime.emit_signal(action=action, symbol=SYM, confidence=0.7 if action=="long" else 0.5,
        metrics={"price":close,"long_line":long_l,"short_line":short_l,"trend":trend})
