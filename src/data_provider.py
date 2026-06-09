"""
Bitget Agent Hub 数据提供层（双通道容错版）
通道1: Bitget REST API (需Clash代理)
通道2: datahub.noxiaohao.com MCP (国内直连)
自动切换，哪个通就用哪个
"""
import json, urllib.request, subprocess, re, os
import pandas as pd
import numpy as np

DATAHUB = "https://datahub.noxiaohao.com/mcp"


class BitgetDataProvider:
    def __init__(self):
        self._mcp_session = None
        self.source = "Bitget Agent Hub"
        self._use_proxy = True
        self.proxy_url = "http://172.30.112.1:7897"

    def _request(self, url, timeout=10):
        """双通道请求：先试代理，不行试直连"""
        # 通道1: 走Clash代理
        if self._use_proxy:
            try:
                ph = urllib.request.ProxyHandler(
                    {"http": self.proxy_url, "https": self.proxy_url}
                )
                opener = urllib.request.build_opener(ph)
                resp = opener.open(url, timeout=timeout)
                return json.loads(resp.read())
            except:
                pass

        # 通道2: datahub直连
        try:
            resp = urllib.request.urlopen(url, timeout=timeout)
            return json.loads(resp.read())
        except:
            pass

        return None

    def get_ticker(self, symbol="BTCUSDT"):
        result = self._request(
            f"https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}"
        )
        if result and 'data' in result:
            t = result['data'][0]
            return {
                'symbol': symbol, 'price': float(t['lastPr']),
                'high_24h': float(t['high24h']), 'low_24h': float(t['low24h']),
                'volume_24h': float(t['baseVolume']), 'source': self.source,
            }
        return self._fallback_ticker()

    def _fallback_ticker(self):
        """兜底方案"""
        try:
            ta = self._mcp_call("crypto_price", {"action": "price", "symbol": "BTC"})
            if ta and isinstance(ta, dict):
                return {
                    'symbol': 'BTCUSDT', 'price': ta.get('price', 0),
                    'high_24h': 0, 'low_24h': 0,
                    'volume_24h': 0, 'source': 'datahub (fallback)',
                }
        except:
            pass
        return {'symbol': 'BTCUSDT', 'price': 0, 'high_24h': 0, 'low_24h': 0,
                'volume_24h': 0, 'source': 'offline'}

    def get_klines(self, symbol="BTCUSDT", granularity="4h", limit=200):
        result = self._request(
            f"https://api.bitget.com/api/v2/spot/market/candles?"
            f"symbol={symbol}&granularity={granularity}&limit={limit}"
        )
        if result and 'data' in result:
            df = pd.DataFrame(result['data'], columns=[
                'timestamp', 'open', 'high', 'low', 'close',
                'volume', 'quoteVol', 'amount'
            ])
            for col in ['open','high','low','close','volume','amount']:
                df[col] = df[col].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(np.int64), unit='ms')
            return df.sort_values('timestamp').reset_index(drop=True)

        # 兜底：用datahub CCXT
        return self._fallback_klines(symbol, granularity, limit)

    def _fallback_klines(self, symbol, granularity, limit):
        data = self._mcp_call("crypto_derivatives", {
            "action": "klines",
            "symbol": symbol.replace("USDT", "/USDT"),
            "timeframe": granularity,
            "limit": min(limit, 50),
        })
        if data and isinstance(data, list):
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for c in ['open','high','low','close','volume']:
                if c in df.columns:
                    df[c] = df[c].astype(float)
            return df.sort_values('timestamp').reset_index(drop=True)
        return pd.DataFrame()

    def get_open_interest(self, symbol="BTCUSDT"):
        result = self._request(
            f"https://api.bitget.com/api/v2/mix/market/open-interest?"
            f"symbol={symbol}&productType=USDT-FUTURES"
        )
        if result and 'data' in result:
            oi_list = result['data'].get('openInterestList', [])
            if oi_list:
                return float(oi_list[0].get('size', 0))
        return 0

    def _mcp_call(self, method, params):
        """调用datahub MCP服务"""
        import subprocess, re

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
            f'-X POST "{DATAHUB}" -H "Content-Type: application/json" '
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
                try:
                    return json.loads(text)
                except:
                    return {"raw": text}
        return None

    def get_technical_analysis(self, symbol="BTC/USDT", timeframe="4h",
                                action="full_analysis"):
        result = self._mcp_call("technical_analysis", {
            "action": action, "symbol": symbol, "timeframe": timeframe,
        })
        if result:
            result['_source'] = 'Bitget Skill Hub'
        return result


if __name__ == '__main__':
    p = BitgetDataProvider()
    print(f"BTC: ${p.get_ticker()['price']:.1f}")
    df = p.get_klines('BTCUSDT', '4h', 3)
    print(f"K线: {len(df)}根")
    print("✅ 数据层正常")
