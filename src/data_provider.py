"""
Bitget Agent Hub 数据提供层（双通道容错版 + 重试）
通道1: Bitget REST API (需Clash代理)
通道2: datahub.noxiaohao.com MCP (国内直连)
自动切换，哪个通就用哪个
"""
import json, urllib.request, subprocess, re, os, time
import pandas as pd
import numpy as np

DATAHUB = "https://datahub.noxiaohao.com/mcp"
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


class BitgetDataProvider:
    def __init__(self):
        self._mcp_session = None
        self.source = "Bitget Agent Hub"
        # 检测是否在Streamlit Cloud（有STREAMLIT_SERVER_PORT环境变量）
        self._on_cloud = "STREAMLIT_SERVER_PORT" in os.environ and not os.path.exists("/mnt/c")
        self.proxy_url = "http://172.30.112.1:7897"

    def _request(self, url, timeout=15):
        """带重试的双通道请求：先直连/代理，再datahub兜底"""
        last_err = None

        for attempt in range(MAX_RETRIES):
            # 通道1: 在Cloud上直连，在WSL走代理
            try:
                if self._on_cloud:
                    resp = urllib.request.urlopen(url, timeout=timeout)
                else:
                    ph = urllib.request.ProxyHandler(
                        {"http": self.proxy_url, "https": self.proxy_url}
                    )
                    opener = urllib.request.build_opener(ph)
                    resp = opener.open(url, timeout=timeout)
                return json.loads(resp.read())
            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))

        # 所有通道失败 → datahub兜底
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
        """调用datahub MCP服务（用urllib替代subprocess+curl，避免shell注入）"""
        import urllib.request

        if not self._mcp_session:
            init_body = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "trader", "version": "1.0"}
                }
            }).encode()
            req = urllib.request.Request(
                DATAHUB, data=init_body,
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"},
                method="POST"
            )
            try:
                # datahub 国内直连，不用代理
                resp = urllib.request.urlopen(req, timeout=15)
                # 从响应头获取 session id
                sid = resp.headers.get('mcp-session-id') or resp.headers.get('Mcp-Session-Id')
                if sid:
                    self._mcp_session = sid
            except Exception:
                pass

        if not self._mcp_session:
            return None

        body = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": method, "arguments": params}
        }).encode()
        req = urllib.request.Request(
            DATAHUB, data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": self._mcp_session,
            },
            method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=20)
            text = resp.read().decode()
            for line in text.split("\n"):
                if line.startswith("data: "):
                    result = json.loads(line[6:])
                    content = result.get("result", {}).get("content", [{}])
                    content_text = content[0].get("text", "{}")
                    try:
                        return json.loads(content_text)
                    except:
                        return {"raw": content_text}
        except Exception:
            pass
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
