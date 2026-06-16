"""
趋势通道 + 结构检测 + OI信号
基于 南溪交易系统
"""
import pandas as pd
import numpy as np


def trend_channel(df):
    """趋势通道 EMA(high,32) / EMA(low,32)"""
    df = df.copy()
    df['long_line'] = df['high'].ewm(span=32, adjust=False).mean()
    df['short_line'] = df['low'].ewm(span=32, adjust=False).mean()
    def _trend(row):
        if row['close'] > row['long_line']: return 1
        elif row['close'] < row['short_line']: return -1
        return 0
    df['trend'] = df.apply(_trend, axis=1)
    return df


def macd_structure(df, fast=12, slow=26, signal=9):
    """MACD钝化+结构检测"""
    df = df.copy()
    ema_f = df['close'].ewm(span=fast, adjust=False).mean()
    ema_s = df['close'].ewm(span=slow, adjust=False).mean()
    df['DIF'] = ema_f - ema_s
    df['DEA'] = df['DIF'].ewm(span=signal, adjust=False).mean()
    df['HIST'] = 2 * (df['DIF'] - df['DEA'])
    df['dull'] = 0
    df['structure'] = 0
    
    N = len(df)
    if N < 60: return df
    
    window = 40
    for i in range(window, N):
        win = df.iloc[i-window:i+1]
        now = df.iloc[i]
        prev = df.iloc[i-1]
        
        p_low = win['close'].iloc[-20:].min()
        d_low = win['DIF'].iloc[-20:].min()
        if now['close'] <= p_low and now['DIF'] > d_low:
            df.at[df.index[i], 'dull'] = 1
        
        p_high = win['close'].iloc[-20:].max()
        d_high = win['DIF'].iloc[-20:].max()
        if now['close'] >= p_high and now['DIF'] < d_high:
            df.at[df.index[i], 'dull'] = -1
        
        if prev.get('dull', 0) == 1 and now['DIF'] > prev['DIF']:
            df.at[df.index[i], 'structure'] = 1
        if prev.get('dull', 0) == -1 and now['DIF'] < prev['DIF']:
            df.at[df.index[i], 'structure'] = -1
    
    return df


def oi_signal(df):
    """OI/Vol 信号"""
    df = df.copy()
    df['oi_bonus'] = 0
    if 'volume' not in df.columns or len(df) < 20: return df
    
    vol_ma5 = df['volume'].rolling(5).mean()
    price_ma5 = df['close'].rolling(5).mean()
    
    for i in range(5, len(df)):
        v_now = df['volume'].iloc[i]
        v_prev = vol_ma5.iloc[i-5] if i >= 10 else v_now
        p_now = df['close'].iloc[i]
        p_prev = price_ma5.iloc[i-5] if i >= 10 else p_now
        
        if v_now < v_prev * 0.85 and p_now < p_prev:
            df.at[df.index[i], 'oi_bonus'] = 1
        elif v_now > v_prev * 1.15 and p_now > p_prev:
            df.at[df.index[i], 'oi_bonus'] = -1
    
    return df
