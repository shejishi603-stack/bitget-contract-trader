"""
全自动交易执行器
- 读取策略信号 → Bitget 合约下单
- 每4小时自动检查一次
- 支持模拟盘/实盘切换
"""
import json, urllib.request, time
import hmac, base64, hashlib
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_provider import BitgetDataProvider
from indicators import trend_channel, macd_structure, oi_signal
from strategy import merge_daily_4h, generate_signals


class BitgetTrader:
    def __init__(self, api_key, secret_key, passphrase, demo=True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.demo = demo
        self.base = "https://api.bitget.com"
        self.proxy = "http://172.30.112.1:7897"
        self.symbol = "BTCUSDT"
        self.leverage = 5
        self.log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'trade_log.jsonl')

    def _sign(self, timestamp, method, path, body=""):
        message = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method, path, body=""):
        ts = str(int(time.time()))
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _request(self, method, path, body=None):
        body_str = json.dumps(body) if body else ""
        url = self.base + path
        req = urllib.request.Request(url, data=body_str.encode() if body_str else None, 
                                     headers=self._headers(method, path, body_str), method=method)
        ph = urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
        return json.loads(urllib.request.build_opener(ph).open(req, timeout=15).read())

    def get_position(self):
        """查当前持仓"""
        result = self._request("GET", f"/api/v2/mix/position/single-position?symbol={self.symbol}&productType=USDT-FUTURES")
        if result.get("code") == "00000":
            data = result.get("data", [])
            if data:
                size = float(data[0].get("total", 0))
                return {
                    "size": size,
                    "side": "LONG" if data[0].get("holdSide") == "long" else "SHORT",
                    "entry_price": float(data[0].get("averageOpenPrice", 0)),
                    "pnl": float(data[0].get("unrealizedPL", 0)),
                }
        return {"size": 0, "side": None, "entry_price": 0, "pnl": 0}

    def get_balance(self):
        """查 USDT 余额"""
        if self.demo:
            return 1000.0  # 模拟盘固定余额
        result = self._request("GET", "/api/v2/account/all-account-balance")
        if result.get("code") == "00000":
            for acc in result.get("data", []):
                for coin in acc.get("coinList", []):
                    if coin.get("coin") == "USDT":
                        return float(coin.get("available", 0))
        return 0

    def place_order(self, side, size_pct):
        """下单：根据仓位百分比计算合约数量"""
        balance = self.get_balance()
        if balance <= 0:
            self._log("WARN", f"余额不足: {balance} USDT")
            return None

        # 计算合约数量（保证金 = 仓位%，杠杆由交易所处理）
        margin = balance * size_pct
        ticker = self._request("GET", f"/api/v2/mix/market/tickers?productType=USDT-FUTURES&symbol={self.symbol}")
        price = float(ticker.get("data", [{}])[0].get("lastPr", 0))
        if price <= 0:
            return None

        size = margin / price
        size = round(size, 3)  # BTC精度3位

        body = {
            "symbol": self.symbol,
            "productType": "USDT-FUTURES",
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "side": side,
            "orderType": "market",
            "size": str(size),
            "leverage": str(self.leverage),
        }

        if self.demo:
            self._log("DEMO", f"{side} {size}BTC @ {price} ({size_pct*100}%仓位)")
            return {"demo": True, "side": side, "size": size, "price": price}

        result = self._request("POST", "/api/v2/mix/order/place-order", body)
        self._log("ORDER", f"{side} {size}BTC | {json.dumps(result, ensure_ascii=False)[:200]}")
        return result

    def close_all(self):
        """全平"""
        pos = self.get_position()
        if pos["size"] <= 0:
            return None

        body = {
            "symbol": self.symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT",
            "side": "close_" + ("long" if pos["side"] == "LONG" else "short"),
            "orderType": "market",
            "size": str(pos["size"]),
        }

        if self.demo:
            self._log("DEMO", f"全平 {pos['size']}BTC (PnL: {pos['pnl']:.2f})")
            return {"demo": True, "action": "close_all", "pnl": pos["pnl"]}

        result = self._request("POST", "/api/v2/mix/order/close-positions", body)
        self._log("CLOSE", f"全平 | {json.dumps(result, ensure_ascii=False)[:200]}")
        return result

    def _log(self, level, msg):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        entry = {"time": datetime.now().isoformat(), "level": level, "msg": msg}
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[{level}] {msg}")

    def execute(self):
        """主循环：读取信号 → 执行交易"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 自动交易检查")
        print(f"{'='*50}")

        # 1. 读策略信号
        provider = BitgetDataProvider()
        daily = provider.get_klines("BTCUSDT", "1day", 200)
        h4 = provider.get_klines("BTCUSDT", "4h", 200)
        daily = trend_channel(daily)
        h4 = macd_structure(h4)
        h4 = oi_signal(h4)
        df = merge_daily_4h(daily, h4)
        signals, _ = generate_signals(df)
        last = df.iloc[-1]
        state = last.get("state", "NO_POSITION")
        target_pos = last.get("position", 0)

        # 2. 查当前持仓
        pos = self.get_position()
        current_size = pos["size"]

        print(f"  策略信号: {state} → 目标仓位 {target_pos*100:.0f}%")
        print(f"  当前持仓: {current_size:.3f}BTC ({pos['pnl']:.2f}USDT)")

        # 3. 执行
        if state in ("LONG_BASE", "LONG_FULL", "LONG_TRIAL", "LONG_REDUCED"):
            if current_size <= 0:
                self.place_order("buy", target_pos)
                self._log("TRADE", f"开仓 {target_pos*100:.0f}%")
            elif abs(target_pos * 100 - current_size / self.get_balance() * 100) > 10:
                self._log("INFO", f"仓位差异较大，需调整")
        elif state == "NO_POSITION" or state == "FLAT":
            if current_size > 0:
                self.close_all()
                self._log("TRADE", "平仓")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="")
    parser.add_argument("--secret", default="")
    parser.add_argument("--passphrase", default="")
    parser.add_argument("--demo", action="store_true", default=True)
    args = parser.parse_args()

    trader = BitgetTrader(args.key, args.secret, args.passphrase, args.demo)
    trader.execute()
    print(f"\n{'='*50}")
    print("完成。日志: logs/trade_log.jsonl")
