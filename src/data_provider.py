"""
Bitget Agent Hub 数据提供层
- 行情数据: Bitget REST API
- OI持仓量: Bitget合约API
- 技术分析: datahub.noxiaohao.com MCP
"""
import json, urllib.request, subprocess, re, os
import pandas as pd
import numpy as np

PROXY = "http://172.30.112.1:7897"
DATAHUB = "https://datahub.noxiaohao.com/mcp"
PROXY = os.environ.get("BITGET_PROXY", "")  # 国内需代理，公网部署留空

class BitgetDataProvider:
    def __init__(self):
        if PROXY:
            self.proxy_handler = urllib.request.ProxyHandler(
                {"http": PROXY, "https": PROXY}
            )
            self.opener = urllib.request.build_opener(self.proxy_handler)
        else:
            self.proxy_handler = None
            self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._mcp_session = None
        self.source = "Bitget Agent Hub"

    def _api(self, path):
        url = f"https://api.bitget.com{path}"
        resp = self.opener.open(url, timeout=15)
        return json.loads(resp.read())

    # ── 行情 ──
    def get_ticker(self, symbol="BTCUSDT"):
        data = self._api(f"/api/v2/spot/market/tickers?symbol={symbol}")
        t = data['data'][0]
        return {
            'symbol': symbol, 'price': float(t['lastPr']),
            'high_24h': float(t['high24h']), 'low_24h': float(t['low24h']),
            'volume_24h': float(t['baseVolume']), 'source': self.source,
        }

    # ── K线 ──
    def get_klines(self, symbol="BTCUSDT", granularity="4h", limit=200):
        data = self._api(
            f"/api/v2/spot/market/candles?symbol={symbol}"
            f"&granularity={granularity}&limit={limit}"
        )
        df = pd.DataFrame(data['data'], columns=[
            'timestamp', 'open', 'high', 'low', 'close',
            'volume', 'quoteVol', 'amount'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            df[col] = df[col].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(np.int64), unit='ms')
        return df.sort_values('timestamp').reset_index(drop=True)

    # ── OI持仓量 ──
    def get_open_interest(self, symbol="BTCUSDT"):
        data = self._api(
            f"/api/v2/mix/market/open-interest?"
            f"symbol={symbol}&productType=USDT-FUTURES"
        )
        oi_list = data.get('data', {}).get('openInterestList', [])
        if oi_list:
            return float(oi_list[0].get('size', 0))
        return 0

    # ── 持仓 ──
    def get_position_info(self):
        return {
            'symbol': 'BTCUSDT', 'side': 'LONG', 'size_pct': 0,
            'entry_price': 0, 'pnl_pct': 0,
            'mode': 'DEMO (Bitget Agent Hub)', 'source': self.source,
        }

    # ── MCP技术分析 ──
    def _mcp_call(self, method, params):
        if not self._mcp_session:
            cmd = (
                f'curl -s --noproxy "*" -D- --max-time 10 '
                f'-X POST "{DATAHUB}" -H "Content-Type: application/json" '
                f'-H "Accept: application/json, text/event-stream" '
                f'-d \'{{"jsonrpc":"2.0","id":1,"method":"initialize",'
                f'"params":{{"protocolVersion":"2024-11-05","capabilities":{{}},'
                f'"clientInfo":{{"name":"trader","version":"1.0"}}}}}}\''
            )
            out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            sid = re.search(r'mcp-session-id:\s*(\S+)', out.stdout, re.IGNORECASE)
            if sid:
                self._mcp_session = sid.group(1)

        if not self._mcp_session:
            return None

        body = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": method, "arguments": params}
        })
        cmd2 = (
            f'curl -s --noproxy "*" --max-time 20 '
            f'-X POST "{DATAHUB}" '
            f'-H "Content-Type: application/json" '
            f'-H "Accept: application/json, text/event-stream" '
            f'-H "Mcp-Session-Id: {self._mcp_session}" '
            f"-d '{body}'"
        )
        out2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=25)
        for line in out2.stdout.split("\n"):
            if line.startswith("data: "):
                result = json.loads(line[6:])
                content = result.get("result", {}).get("content", [{}])
                text = content[0].get("text", "{}")
                try: return json.loads(text)
                except: return {"raw": text}
        return None

    def get_technical_analysis(self, symbol="BTC/USDT", timeframe="4h",
                                action="full_analysis"):
        result = self._mcp_call("technical_analysis", {
            "action": action, "symbol": symbol, "timeframe": timeframe,
        })
        if result:
            result['_source'] = 'Bitget Skill Hub'
        return result


# ── 测试 ──
if __name__ == '__main__':
    p = BitgetDataProvider()
    print(f"BTC: ${p.get_ticker()['price']:.1f}")
    oi = p.get_open_interest()
    print(f"OI持仓量: {oi:.1f} BTC")
    df = p.get_klines('BTCUSDT', '4h', 3)
    vol = df['volume'].iloc[-1]
    print(f"最近4h成交量: {vol:.1f} BTC")
    print(f"OI/Vol: {oi/vol:.2f}" if vol > 0 else "OI/Vol: N/A")
    print("✅ 数据层正常")
