"""
千问LLM增强层 — 通过curl调用（绕过urllib TUN兼容问题）
"""
import json, subprocess, os


QWEN_URL = "https://hackathon.bitgetops.com/v1/chat/completions"
QWEN_KEY = os.environ.get("QWEN_API_KEY", "")  # 环境变量读取
QWEN_MODEL = "qwen3.6-plus"


def qwen_chat(prompt, system=None, max_tokens=300):
    """调用千问API（curl方式，Clash TUN兼容）"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = json.dumps({
        "model": QWEN_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    })

    # 用curl（直连，TUN模式自动路由）
    curl_cmd = [
        "curl", "-s", "--noproxy", "*", "--max-time", "40",
        "-X", "POST", QWEN_URL,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {QWEN_KEY}",
        "-d", body,
    ]

    try:
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=25)
        data = json.loads(result.stdout)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None


def llm_experience_check(row):
    """LLM经验修正层"""
    state_desc = f"""
当前BTC市场状态:
- 价格: {row.get('close',0):.0f} USDT
- 日线趋势: {('多头' if row.get('daily_trend',0)==1 else '空头' if row.get('daily_trend',0)==-1 else '震荡')}
- 4h结构: {('底结构' if row.get('structure',0)==1 else '顶结构' if row.get('structure',0)==-1 else '无')}
- OI信号: {('吸筹' if row.get('oi_bonus',0)==1 else '出货' if row.get('oi_bonus',0)==-1 else '无')}
- 当前仓位: {row.get('position',0)*100:.0f}%

简短判断(2-3句): 当前是否适合做多？仓位应激进还是防守？有什么风险？
"""
    system = "你是趋势通道交易分析师。回答控制在3句话以内，说人话。"
    return qwen_chat(state_desc, system, 150)


def llm_strategy_adjust(user_input, current_params):
    """自然语言策略调整"""
    prompt = f"""
用户指令: "{user_input}"
当前参数: {json.dumps(current_params, ensure_ascii=False)}

分析意图，返回JSON: {{"intent":"...","no_change":false,"adjustments":{{...}}}}
如果与策略调整无关，返回: {{"no_change":true}}
"""
    system = "只返回JSON，不要解释。"
    result = qwen_chat(prompt, system, 200)

    if not result:
        return {"no_change": True, "reason": "LLM不可用"}

    try:
        if "{" in result:
            result = result[result.index("{"):result.rindex("}")+1]
        return json.loads(result)
    except:
        return {"no_change": True, "raw": result[:100]}


if __name__ == '__main__':
    print("千问LLM增强层测试\n")

    # 经验判断
    mock = {'close': 63000, 'daily_trend': -1, 'structure': 0,
            'oi_bonus': 0, 'position': 0}
    r = llm_experience_check(mock)
    print(f"经验判断: {r}")

    # 策略调整
    a = llm_strategy_adjust("把试仓降到5%", {"trial_position": 0.10})
    print(f"\n策略调整: {json.dumps(a, ensure_ascii=False)}")
