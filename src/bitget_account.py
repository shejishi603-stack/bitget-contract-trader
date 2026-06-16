"""
Bitget 账户连接模块
- API Key 签名认证
- 账户余额查询
- 持仓查询
- 模拟/实盘切换
"""
import hmac, base64, hashlib, json, time, urllib.request


class BitgetAccount:
    """Bitget API 账户连接"""

    def __init__(self, api_key="", secret_key="", passphrase="", demo=True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.demo = demo
        self.base_url = "https://api.bitget.com"
        self.proxy = "http://172.30.112.1:7897"
        self.connected = False

    def configure(self, api_key, secret_key, passphrase):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    def _sign(self, timestamp, method, path, body=""):
        """HMAC-SHA256 签名"""
        message = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method, path, body=""):
        timestamp = str(int(time.time()))
        sign = self._sign(timestamp, method, path, body)
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.demo:
            headers["X-SIMULATED-Trading"] = "1"  # 模拟盘标记
        return headers

    def _request(self, method, path, body=None):
        """发送签名请求（带重试）"""
        body_str = json.dumps(body) if body else ""
        url = self.base_url + path
        headers = self._headers(method, path, body_str)

        data = body_str.encode() if body_str else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        proxy_handler = urllib.request.ProxyHandler(
            {"http": self.proxy, "https": self.proxy}
        )
        opener = urllib.request.build_opener(proxy_handler)

        # 最多重试3次，指数退避
        last_err = None
        for attempt in range(3):
            try:
                resp = opener.open(req, timeout=15)
                return json.loads(resp.read())
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        return {"code": "99999", "msg": f"请求失败(3次重试后): {str(last_err)[:80]}"}

    def test_connection(self):
        """测试API Key是否有效"""
        if not self.api_key or not self.secret_key:
            return {"ok": False, "msg": "请填写API Key"}
        try:
            result = self._request("GET", "/api/v2/account/account-info")
            if result.get("code") == "00000":
                self.connected = True
                return {"ok": True, "msg": "✅ 连接成功",
                       "uid": result.get("data", {}).get("userId", "?")}
            return {"ok": False, "msg": f"❌ {result.get('msg', '认证失败')}"}
        except Exception as e:
            return {"ok": False, "msg": f"❌ 网络错误: {str(e)[:60]}"}

    def get_balance(self):
        """获取账户余额"""
        try:
            result = self._request("GET", "/api/v2/account/all-account-balance")
            if result.get("code") == "00000":
                data = result.get("data", [])
                if data:
                    usdt = next(
                        (d for d in data[0].get("coinList", [])
                         if d.get("coin") == "USDT"),
                        {}
                    )
                    return {
                        "USDT": float(usdt.get("available", 0)),
                        "frozen": float(usdt.get("frozen", 0)),
                    }
            return {"USDT": 0, "frozen": 0, "error": result.get("msg", "?")}
        except Exception as e:
            return {"USDT": 0, "frozen": 0, "error": str(e)[:80]}

    def get_positions(self, product_type="USDT-FUTURES"):
        """获取合约持仓"""
        try:
            result = self._request(
                "GET",
                f"/api/v2/mix/position/all-position?productType={product_type}"
            )
            if result.get("code") == "00000":
                positions = []
                for pos in result.get("data", []):
                    size = float(pos.get("total", 0))
                    if size > 0:
                        positions.append({
                            "symbol": pos.get("symbol", ""),
                            "side": "LONG" if pos.get("holdSide") == "long" else "SHORT",
                            "size": size,
                            "entry_price": float(pos.get("averageOpenPrice", 0)),
                            "current_price": float(pos.get("marketPrice", 0)),
                            "pnl": float(pos.get("unrealizedPL", 0)),
                            "pnl_pct": float(pos.get("unrealizedPLR", 0)) * 100,
                            "leverage": int(pos.get("leverage", 5)),
                        })
                return positions
            return []
        except Exception as e:
            return []

    def get_orders(self, symbol="BTCUSDT", status="filled", limit=10):
        """获取历史订单"""
        try:
            result = self._request(
                "GET",
                f"/api/v2/mix/order/orders-history?"
                f"symbol={symbol}&productType=USDT-FUTURES&limit={limit}"
            )
            if result.get("code") == "00000":
                return [
                    {
                        "order_id": o.get("orderId"),
                        "symbol": o.get("symbol"),
                        "side": o.get("side"),
                        "price": float(o.get("priceAvg", 0)),
                        "size": float(o.get("size", 0)),
                        "pnl": float(o.get("pnl", 0)),
                        "time": o.get("cTime"),
                    }
                    for o in result.get("data", {}).get("orderList", [])
                ]
            return []
        except:
            return []


# ── 测试 ──
if __name__ == '__main__':
    import os
    acc = BitgetAccount(
        os.environ.get("BITGET_API_KEY", ""),
        os.environ.get("BITGET_SECRET_KEY", ""),
        os.environ.get("BITGET_PASSPHRASE", ""),
    )
    print("测试连接...")
    result = acc.test_connection()
    print(result)

    if acc.connected:
        print("\n账户余额:")
        print(acc.get_balance())
        print("\n合约持仓:")
        print(acc.get_positions())
