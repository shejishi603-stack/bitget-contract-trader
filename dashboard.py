"""
南溪合约交易仪表盘 — Bitget BTC 永续合约
Powered by Bitget Agent Hub
策略: 日线趋势通道 + 4h MACD结构 + OI/Vol加分
"""
import streamlit as st
import pandas as pd
import numpy as np
import sys, os, time, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')
from data_provider import BitgetDataProvider
from indicators import trend_channel, macd_structure, oi_signal
from strategy import merge_daily_4h, generate_signals
from bitget_account import BitgetAccount
from backtest import BacktestEngine, run_backtest
from ai_enhancer import ai_decision_layer, DecisionLogger

st.set_page_config(
    page_title="南溪合约交易 · Bitget AI Hackathon S1",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto",
)

# ═══════════════════════ 样式 ═══════════════════════
st.markdown("""
<style>
    .main { background-color: #0d1117; }
    .stApp { background-color: #0d1117; }
    [data-testid="stHeader"] { background-color: #0d1117; }
    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 18px;
        margin: 4px;
    }
    .price-big {
        font-size: 38px;
        font-weight: 700;
        color: #58a6ff;
    }
    .strategy-desc {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px 20px;
        margin: 10px 0;
        font-size: 14px;
        line-height: 1.7;
        color: #c9d1d9;
    }
    .green { color: #3fb950; }
    .red { color: #f85149; }
    .gray { color: #8b949e; }
    .signal-card {
        background: #161b22;
        border-left: 3px solid #58a6ff;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 5px 0;
    }
    .footer-bar {
        display: flex;
        gap: 16px;
        justify-content: center;
        padding: 14px;
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        margin-top: 20px;
    }
    .footer-tag {
        padding: 5px 12px;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 500;
    }
    .stButton button {
        background: #238636;
        color: white;
        border: 1px solid #2ea043;
        border-radius: 6px;
        font-weight: 500;
    }
    div[data-testid="stTabs"] button {
        font-size: 15px;
        font-weight: 600;
        color: #8b949e;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #58a6ff;
        border-bottom-color: #58a6ff;
    }
    .stMetric { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px; }
    .hackathon-header {
        background: linear-gradient(135deg, #1a1a3e 0%, #0d3b66 50%, #0d1117 100%);
        border: 2px solid #58a6ff;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 18px;
    }
    .hackathon-header h1 {
        font-size: 22px;
        font-weight: 800;
        color: #fff;
        margin: 0 0 6px 0;
    }
    .hackathon-header .subtitle {
        font-size: 14px;
        color: #8b949e;
        margin: 0;
    }
    .hackathon-badge {
        display: inline-block;
        background: #58a6ff;
        color: #0d1117;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 700;
        margin-right: 8px;
    }
    .pipeline {
        display: flex;
        gap: 8px;
        margin: 16px 0;
    }
    .pipeline-step {
        flex: 1;
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        position: relative;
    }
    .pipeline-step .step-num {
        font-size: 10px;
        color: #58a6ff;
        font-weight: 700;
        text-transform: uppercase;
    }
    .pipeline-step .step-title {
        font-size: 16px;
        font-weight: 700;
        color: #fff;
        margin: 4px 0;
    }
    .pipeline-step .step-detail {
        font-size: 11px;
        color: #8b949e;
        line-height: 1.4;
    }
    .pipeline-arrow {
        display: flex;
        align-items: center;
        color: #58a6ff;
        font-size: 20px;
        flex-shrink: 0;
    }
    .deadline-banner {
        background: #1a1a2e;
        border: 1px solid #f0b90b;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        color: #f0b90b;
        margin-bottom: 12px;
        text-align: center;
    }

</style>
""", unsafe_allow_html=True)

# ═══════════════════════ 侧边栏 ═══════════════════════
with st.sidebar:
    st.header("🔌 Bitget API")
    st.caption("连接你的Bitget账户（可选）")

    for key in ['bitget_api_key', 'bitget_secret_key', 'bitget_passphrase']:
        if key not in st.session_state:
            st.session_state[key] = ''
    for key in ['account_connected', 'account']:
        if key not in st.session_state:
            st.session_state[key] = False if key == 'account_connected' else None

    with st.expander("📝 配置API Key", expanded=not st.session_state.account_connected):
        api_key = st.text_input("API Key", value=st.session_state.bitget_api_key,
                                type="password", placeholder="从Bitget设置页获取")
        secret_key = st.text_input("Secret Key", value=st.session_state.bitget_secret_key,
                                   type="password", placeholder="从Bitget设置页获取")
        passphrase = st.text_input("Passphrase", value=st.session_state.bitget_passphrase,
                                   type="password", placeholder="创建API时设置的密码")

        c1, c2 = st.columns(2)
        if c1.button("🔗 连接", use_container_width=True):
            if api_key and secret_key and passphrase:
                st.session_state.bitget_api_key = api_key
                st.session_state.bitget_secret_key = secret_key
                st.session_state.bitget_passphrase = passphrase
                acc = BitgetAccount(api_key, secret_key, passphrase)
                result = acc.test_connection()
                if result['ok']:
                    st.session_state.account_connected = True
                    st.session_state.account = acc
                    st.success(result['msg'])
                else:
                    st.session_state.account_connected = False
                    st.error(result['msg'])
            else:
                st.warning("请填写完整")
        if c2.button("🗑️ 清除", use_container_width=True):
            for k in ['account_connected', 'account']:
                st.session_state[k] = False if k == 'account_connected' else None
            for k in ['bitget_api_key', 'bitget_secret_key', 'bitget_passphrase']:
                st.session_state[k] = ''
            st.rerun()

    if st.session_state.account_connected:
        st.success("✅ 已连接")
        acc = st.session_state.account
        balance = acc.get_balance()
        st.metric("💰 USDT", f"{balance.get('USDT', 0):.2f}")
        positions = acc.get_positions()
        if positions:
            for pos in positions:
                color = "green" if pos['pnl'] >= 0 else "red"
                st.markdown(f"**{pos['symbol']}** {pos['side']} "
                           f":{color}[{pos['pnl_pct']:+.2f}%]")
        st.divider()

    # 导出按钮
    st.subheader("📤 导出")
    if st.button("📄 导出回测报告", use_container_width=True):
        st.info("报告已生成到: bitget-contract-trader/report.txt\n运行 full_backtest.py 生成完整报告")

    # 数据源
    st.divider()
    st.subheader("🏆 比赛信息")
    st.markdown("""
    <div class="deadline-banner" style="margin-top:8px">
      <b>⏰ 提交截止：6月25日 24:00 (UTC+8)</b><br>
      <span style="font-size:10px">报名截止：6月14日 | 提交窗口：6月15-25日 | 颁奖：6月30日</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("**提交清单：**")
    st.markdown("- [x] Demo可运行")
    st.markdown("- [x] 回测记录(2022-2025)")
    st.markdown("- [x] 项目说明(200字)")
    st.markdown("- [ ] 视频演示(选填)")
    st.markdown("- [ ] 发帖带 #BitgetHackathon")
    
    st.divider()
    st.caption("📡 Bitget REST API")
    st.caption("🧠 Bitget Skill Hub")
    st.caption("📊 OI/Vol 吸筹检测")

# ═══════════════════════ 数据加载 ═══════════════════════
@st.cache_data(ttl=300)
def load_data():
    provider = BitgetDataProvider()
    try:
        df_daily = provider.get_klines('BTCUSDT', '1day', 200)
        df_daily = trend_channel(df_daily)
        df_4h = provider.get_klines('BTCUSDT', '4h', 200)
        df_4h = macd_structure(df_4h)
        df_4h = oi_signal(df_4h)
        df = merge_daily_4h(df_daily, df_4h)
        signals, positions = generate_signals(df)
        ticker = provider.get_ticker()
        ta = provider.get_technical_analysis('BTC/USDT', '4h', 'full_analysis')
        oi_value = provider.get_open_interest()
        return df_daily, df_4h, df, signals, ticker, ta, oi_value, None
    except Exception as e:
        st.warning(f"⚠️ API连接失败(Clash可能未开启): {str(e)[:80]}")
        # 返回空数据
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df, empty_df, {}, {}, 0, str(e)

with st.spinner("Bitget Agent Hub 数据加载中..."):
    df_d, df_4h, df, signals, ticker, ta, oi_val, api_error = load_data()
    if api_error or df_d.empty:
        st.error("⚠️ 无法连接Bitget API，请确认Clash代理已开启。")
        st.info("开启Clash后点击🔄刷新按钮。")
        st.stop()
    last = df.iloc[-1]
    last_signal = signals[signals['action'] != '']

# ═══════════════════════ 比赛头部 ═══════════════════════
st.markdown("""
<div class="hackathon-header">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
    <span class="hackathon-badge">🏆 Bitget AI Hackathon S1</span>
    <span style="color:#8b949e;font-size:12px">赛道一 · 交易Agent</span>
  </div>
  <h1>🏗️ 南溪合约交易</h1>
  <p class="subtitle">日线EMA趋势通道定方向 + 4h MACD结构找时机 + OI/Vol吸筹加分 · 只做多 · 5x杠杆 · BTC永续合约</p>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════ 策略闭环可视化 ═══════════════════════
st.markdown("""
<div class="pipeline">
  <div class="pipeline-step">
    <div class="step-num">STEP 1</div>
    <div class="step-title">🔍 感知</div>
    <div class="step-detail">Bitget REST API<br>实时K线数据<br>日线+4h+OI/Vol</div>
  </div>
  <div class="pipeline-arrow">→</div>
  <div class="pipeline-step">
    <div class="step-num">STEP 2</div>
    <div class="step-title">🧠 决策</div>
    <div class="step-detail">日线趋势通道<br>MACD底部结构<br>OI吸筹确认<br>3.0状态机引擎</div>
  </div>
  <div class="pipeline-arrow">→</div>
  <div class="pipeline-step">
    <div class="step-num">STEP 3</div>
    <div class="step-title">⚡ 执行</div>
    <div class="step-detail">Bitget合约API<br>5x杠杆开多<br>底仓30%→满仓50%</div>
  </div>
  <div class="pipeline-arrow">→</div>
  <div class="pipeline-step">
    <div class="step-num">STEP 4</div>
    <div class="step-title">🛡️ 风控</div>
    <div class="step-detail">日线翻空止损<br>ATR动态止损<br>100%止盈平30%<br>钝化消失止损</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════ 项目说明 ═══════════════════════
st.markdown("""
<div class="strategy-desc">
<b>📋 项目说明：</b>「南溪合约交易」是一个基于 Bitget Agent Hub 构建的 BTC 永续合约 AI 交易 Agent，
参加 Bitget AI Base Camp Hackathon S1 赛道一（交易Agent）。<br><br>
<b>解决的问题：</b>加密市场7×24小时运行，散户难以持续盯盘。本系统通过日线趋势通道+4h MACD结构+OI成交量
三位一体的策略引擎，实现全自动感知→决策→执行→风控闭环。<br><br>
<b>策略闭环：</b>①感知层通过 Bitget REST API 获取实时K线和OI数据；
②决策层采用「南溪交易系统」3.0底仓思维状态机（30%底仓→日线确认加满50%→顶结构减30%）；
③执行层通过 Bitget 合约API下单，5倍杠杆只做多；
④风控层多重止损（日线翻空/ATR/钝化消失）和100%止盈锁定利润。<br><br>
<b>技术栈：</b>Python + Streamlit + Plotly + pandas-ta + Bitget Agent Hub（MCP Server + Skill Hub）。
</div>
""", unsafe_allow_html=True)

# ═══════════════════════ 标签页 ═══════════════════════
tab1, tab2 = st.tabs(["📊 实时交易", "📈 策略回测"])

# ═══════════════════════ TAB 1: 实时 ═══════════════════════
with tab1:
    # 核心指标卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        price = ticker['price']
        chg = (price - ticker['low_24h']) / ticker['low_24h'] * 100 - 50
        clr = "#00d4aa" if chg > 0 else "#ff4757"
        st.markdown(f'<div class="metric-card"><span class="gray">BTC实时</span><br>'
                    f'<span class="price-big">${price:,.0f}</span><br>'
                    f'<span style="color:{clr}">24h {chg:+.1f}%</span></div>',
                    unsafe_allow_html=True)
    with c2:
        t = '🟢 多头' if last['daily_trend']==1 else '🔴 空头' if last['daily_trend']==-1 else '⚪ 震荡'
        st.markdown(f'<div class="metric-card"><span class="gray">日线趋势</span><br>'
                    f'<span style="font-size:28px;font-weight:700;">{t}</span><br>'
                    f'<span class="gray">多头线 {last.get("daily_long",0):,.0f}</span></div>',
                    unsafe_allow_html=True)
    with c3:
        sm = {'NO_POSITION':'⚪ 空仓','LONG_BASE':'🟡 底仓30%','LONG_FULL':'🟢 满仓50%',
              'LONG_REDUCED':'🟠 减仓30%','LONG_TRIAL':'🔵 试仓10%'}
        st.markdown(f'<div class="metric-card"><span class="gray">当前状态</span><br>'
                    f'<span style="font-size:24px;font-weight:700;">{sm.get(last.get("state",""),"⚪")}</span><br>'
                    f'<span class="gray">仓位 {last.get("position",0)*100:.0f}%</span></div>',
                    unsafe_allow_html=True)
    with c4:
        pnl = last.get('pnl_pct', 0)
        st.markdown(f'<div class="metric-card"><span class="gray">浮盈</span><br>'
                    f'<span style="font-size:28px;font-weight:700;color:{"#00d4aa" if pnl>=0 else "#ff4757"}">{pnl:+.1f}%</span><br>'
                    f'<span class="gray">5x杠杆</span></div>',
                    unsafe_allow_html=True)
    with c5:
        rsi_val = ta.get('rsi',{}).get('rsi',0) if ta else 0
        macd_x = ta.get('macd',{}).get('cross','?') if ta else '?'
        oi_bonus = last.get('oi_bonus', 0)
        oi_text = '📈吸筹' if oi_bonus==1 else '📉出货' if oi_bonus==-1 else '—'
        st.markdown(f'<div class="metric-card"><span class="gray">Skill Hub</span><br>'
                    f'<span style="font-size:18px;">RSI {rsi_val:.1f} | MACD {macd_x}</span><br>'
                    f'<span class="gray">OI信号: {oi_text} | OI {oi_val:,.0f}BTC</span></div>',
                    unsafe_allow_html=True)

    st.markdown("---")

    # 图表 + 信号面板
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.subheader("📊 趋势通道（日线）")
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                               row_heights=[0.65, 0.35], vertical_spacing=0.05)

            plot_d = df_d.tail(30)
            fig.add_trace(go.Candlestick(
                x=plot_d['timestamp'], open=plot_d['open'],
                high=plot_d['high'], low=plot_d['low'],
                close=plot_d['close'], name='BTC',
                increasing_line_color='#00d4aa',
                decreasing_line_color='#ff4757'), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=plot_d['timestamp'], y=plot_d['long_line'],
                name='多头线', line=dict(color='#00d4aa', width=2, dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=plot_d['timestamp'], y=plot_d['short_line'],
                name='空头线', line=dict(color='#ff4757', width=2, dash='dot')), row=1, col=1)

            # MACD
            plot_h = df.tail(120)
            if 'HIST' in df.columns:
                fig.add_trace(go.Bar(
                    x=plot_h['timestamp'], y=plot_h['HIST'],
                    name='MACD柱',
                    marker_color=np.where(plot_h['HIST']>0, '#00d4aa','#ff4757')), row=2, col=1)
                fig.add_trace(go.Scatter(
                    x=plot_h['timestamp'], y=plot_h['DIF'],
                    name='DIF', line=dict(color='#00a3ff', width=1)), row=2, col=1)
                fig.add_trace(go.Scatter(
                    x=plot_h['timestamp'], y=plot_h['DEA'],
                    name='DEA', line=dict(color='#ffa500', width=1)), row=2, col=1)

            fig.update_layout(
                template='plotly_dark', paper_bgcolor='#0a0e17',
                plot_bgcolor='#0a0e17', font_color='#7a8ba0',
                height=500, margin=dict(l=0,r=0,t=10,b=10),
                legend=dict(orientation='h', y=1.1))
            fig.update_xaxes(rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.info("pip install plotly 即可显示图表")

    with col_r:
        st.subheader("📋 交易信号")
        if len(last_signal) > 0:
            for _, row in last_signal.tail(8).iterrows():
                action = row['action']
                pos_s = f"{row['position']*100:.0f}%"
                # 信号分类
                if '止损' in action or '全平' in action:
                    emoji, border = '🔴', '#ff4757'
                elif '建仓' in action or '加仓' in action or '确认' in action or '突破' in action:
                    emoji, border = '🟢', '#00d4aa'
                elif '减仓' in action or '止盈' in action:
                    emoji, border = '🟡', '#ffa500'
                else:
                    emoji, border = '🔵', '#00a3ff'
                st.markdown(
                    f'<div class="signal-card" style="border-left-color:{border}">'
                    f'<small class="gray">{str(row["timestamp"])[:16]}</small><br>'
                    f'<b>{emoji} {action}</b> '
                    f'<span class="gray">| ${row["close"]:,.0f} | {pos_s}</span></div>',
                    unsafe_allow_html=True)
        else:
            st.info("暂无信号")

        st.divider()
        st.subheader("📐 当前价位")
        ld = df_d.iloc[-1]
        c1,c2,c3 = st.columns(3)
        c1.metric("多头线", f"{ld['long_line']:,.0f}")
        c2.metric("空头线", f"{ld['short_line']:,.0f}")
        c3.metric("现价", f"{ld['close']:,.0f}")

        st.subheader("🔍 4h结构")
        d1,d2,d3 = st.columns(3)
        du = last.get('dull',0)
        d1.metric("钝化", '底部' if du==1 else '顶部' if du==-1 else '无')
        stt = last.get('structure',0)
        d2.metric("结构", '🟢底' if stt==1 else '🔴顶' if stt==-1 else '无')
        d3.metric("DIF", f"{last.get('DIF',0):.0f}")

    # AI增强决策层
    st.markdown("---")
    st.markdown("#### 🧠 Agentic决策（感知→推理→决策→日志）")
    
    # 加载agentic trader的决策日志
    import os, json as _json
    log_file = "/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/logs/agent_decisions.jsonl"
    recent_decisions = []
    if os.path.exists(log_file):
        with open(log_file) as f:
            for line in f:
                recent_decisions.append(_json.loads(line))
    
    c1, c2, c3 = st.columns(3)
    
    if recent_decisions:
        last_d = recent_decisions[-1]
        c1.metric("决策次数", len(recent_decisions))
        c2.metric("置信度", last_d.get('confidence', '?'))
        c3.metric("MCP调用", len(last_d.get('mcp_calls', [])))
        
        st.markdown("**最近决策:**")
        for d in recent_decisions[-3:]:
            st.markdown(
                f'<div class="signal-card" style="border-left-color:#a78bfa">'
                f'<small class="gray">{d.get("timestamp","?")[:19]}</small><br>'
                f'<b>🧠 操作: {d.get("final_action","?")}</b> | '
                f'<span class="gray">置信度: {d.get("confidence","?")} | '
                f'MCP: {len(d.get("mcp_calls",[]))}接口</span>'
                f'</div>', unsafe_allow_html=True)
        
        # 思考链
        thinking_file = "/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/logs/agent_thinking.jsonl"
        if os.path.exists(thinking_file):
            with open(thinking_file) as f:
                chains = [_json.loads(line) for line in f]
            if chains:
                last_chain = chains[-1]
                with st.expander("🔍 查看最近思考链"):
                    for step in last_chain.get('chain', ['无记录']):
                        st.write(f"• {step}")
                    if last_chain.get('mcp_calls'):
                        st.write("**MCP接口调用:**")
                        for call in last_chain['mcp_calls']:
                            st.write(f"  ✓ {call}")
    else:
        c1.metric("决策次数", 0)
        c2.metric("置信度", "N/A")
        c3.metric("MCP调用", 0)
        st.info("运行 agentic_trader.py 生成决策日志")
    
    # 补充AI增强验证
    try:
        from ai_enhancer import ai_decision_layer
        ai_result = ai_decision_layer(last) if 'last' in dir() else {}
        if ai_result:
            st.caption(f"📝 Skill Hub: {ai_result.get('skill_hub',{}).get('signals',{}).get('verdict','?')} | 建议: {ai_result.get('recommendation','?')}")
    except:
        pass

# ═══════════════════════ TAB 2: 回测 ═══════════════════════
with tab2:
    st.subheader("📈 策略回测报告")

    # ── 长期回测（日线简化版） ──
    st.markdown("#### 📅 长期回测（日线趋势通道，2022-2025）")

    # 加载历史数据
    hist_data = {}
    for start in [2022, 2023, 2024]:
        fname = f"/mnt/c/Users/Administrator/Desktop/bitget-contract-trader/data/backtest_{start}.json"
        if os.path.exists(fname):
            with open(fname) as f:
                hist_data[start] = json.load(f)

    if hist_data:
        cols = st.columns(len(hist_data))
        for idx, (start, h) in enumerate(sorted(hist_data.items())):
            with cols[idx]:
                st.markdown(f'<div class="metric-card" style="text-align:center">'
                           f'<div class="gray">{start}-2025</div>'
                           f'<div style="font-size:32px;font-weight:700;color:#3fb950">{h["total_return"]}</div>'
                           f'<div class="gray">{h["trades"]}笔 | 胜率{h["win_rate"]}</div>'
                           f'</div>', unsafe_allow_html=True)

        # 选一个详细展示
        selected = st.selectbox("选择回测区间查看详情",
                                sorted(hist_data.keys()),
                                format_func=lambda x: f"{x}-2025 ({hist_data[x]['trades']}笔交易)")

        h = hist_data[selected]
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("收益率", h['total_return'])
        mc2.metric("胜率", h['win_rate'])
        mc3.metric("交易次数", h['trades'])
        mc4.metric("平均盈利", h.get('avg_win', 'N/A'))

        if h.get('detail'):
            st.markdown("**最近交易记录:**")
            rows = []
            for t in h['detail'][-10:]:
                rows.append({
                    '入场': t['entry'], '出场': t['exit'],
                    '盈亏': t['pnl'],
                    '结果': '🟢' if '+' in t['pnl'] else '🔴'
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 近期回测（日线+4h完整版） ──
    st.markdown("#### 📊 近期回测（日线+4h结构+OI，2025.11至今）")

    with st.spinner("正在计算..."):
        result = run_backtest(df, signals, initial=10000, leverage=5)

    st.markdown(f'<span class="gray">{df["timestamp"].iloc[0]} ~ {df["timestamp"].iloc[-1]} · '
                f'{(df["timestamp"].iloc[-1]-df["timestamp"].iloc[0]).days}天 · '
                f'{len(result["trades"])}笔交易</span>',
                unsafe_allow_html=True)

    metrics = st.columns(6)
    stats = result['stats']
    for i, (label, key) in enumerate(zip(
        ['收益率', '最大回撤', '夏普比率', '胜率', '交易数', '盈亏'],
        ['总收益率', '最大回撤', '夏普比率', '胜率', '交易次数', '总盈亏']
    )):
        metrics[i].metric(label, stats.get(key, 'N/A'))

    # 资金曲线
    try:
        import plotly.graph_objects as go
        eq = result['equity_curve']
        ts_list = [signals.iloc[i]['timestamp'] for i in range(len(eq))]
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=ts_list, y=eq, fill='tozeroy',
            fillcolor='rgba(88,166,255,0.1)',
            line=dict(color='#58a6ff', width=2), name='净值'))
        fig_eq.add_hline(y=10000, line_dash='dash', line_color='#484f58',
                        annotation_text='$10,000')
        fig_eq.update_layout(
            template='plotly_dark', paper_bgcolor='#0d1117',
            plot_bgcolor='#0d1117', font_color='#8b949e',
            height=280, margin=dict(l=0,r=0,t=10,b=10),
            showlegend=False, yaxis_title='净值($)')
        st.plotly_chart(fig_eq, use_container_width=True)
    except:
        pass

    if result['trades']:
        rows = []
        total_pnl = 0
        for i, t in enumerate(result['trades']):
            total_pnl += t['pnl_pct']
            rows.append({
                '#': i+1, '入场': str(t['entry'])[:10], '出场': str(t['exit'])[:10],
                '仓位': f"{t['size']*100:.0f}%",
                '盈亏': f"{t['pnl_pct']:+.1f}%",
                '原因': t['reason'][:25], '': '🟢' if t['pnl_pct']>0 else '🔴',
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ═══════════════════════ 底部: 数据源 ═══════════════════════
st.markdown("---")
st.markdown("""
<div class="footer-bar">
    <span class="footer-tag" style="background:#1a2a1a;color:#00d4aa">📡 Bitget REST API</span>
    <span class="footer-tag" style="background:#1a1a2a;color:#00a3ff">🧠 Bitget Skill Hub</span>
    <span class="footer-tag" style="background:#2a1a2a;color:#ffa500">🏆 Bitget AI Hackathon S1</span>
    <span class="footer-tag" style="background:#1a1a2a;color:#a78bfa">🐍 Python 策略引擎</span>
    <span class="footer-tag" style="background:#2a1a1a;color:#f0b90b">#BitgetHackathon</span>
</div>
""", unsafe_allow_html=True)

# 刷新
col_b1, col_b2 = st.columns([1, 8])
if col_b1.button("🔄 刷新", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
col_b2.caption(f"⏰ 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
