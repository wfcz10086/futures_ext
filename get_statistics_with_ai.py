from flask import Blueprint, jsonify, render_template, request, session
from flask_paginate import Pagination, get_page_parameter
from binance.client import Client
from auth import login_required
from models import BinanceKey, User, FuturesSymbol
from extensions import db
import numpy as np
import talib
import json
import requests

get_statistics_with_ai_bp = Blueprint('get_statistics_with_ai', __name__)

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_API_KEY = "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"

@get_statistics_with_ai_bp.route('/get_statistics_with_ai_page', methods=['GET'])
@login_required
def get_statistics_with_ai_page():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify(success=False, error="用户不存在"), 404

    binance_keys = user.binance_keys

    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = 10

    futures_symbols = FuturesSymbol.query.filter_by(user_id=user_id).paginate(
        page=page, per_page=per_page, error_out=False
    )

    pagination = Pagination(
        page=page, 
        total=futures_symbols.total, 
        per_page=per_page, 
        css_framework='bootstrap4'
    )

    return render_template('get_statistics_with_ai.html', 
                           binance_keys=binance_keys, 
                           futures_symbols=futures_symbols.items, 
                           pagination=pagination)

@get_statistics_with_ai_bp.route('/analyze_symbol_with_ai', methods=['POST'])
@login_required
def analyze_symbol_with_ai():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401

    user = User.query.get(user_id)
    if not user or not user.binance_keys:
        return jsonify(success=False, error="没有有效的 Binance 密钥"), 400

    binance_key = user.binance_keys[0]
    symbol = request.form.get('symbol')

    if not symbol:
        return jsonify(success=False, error="未提供交易对"), 400

    client = Client(binance_key.api_key, binance_key.secret_key)

    try:
        statistics = calculate_symbol_statistics(client, symbol)
        ai_suggestion = get_ai_suggestion(statistics)
        
        return jsonify(success=True, statistics=statistics, ai_suggestion=ai_suggestion)
    except Exception as e:
        print(f"分析交易对时发生错误: {str(e)}")
        return jsonify(success=False, error=f"分析交易对时发生错误: {str(e)}"), 500

def calculate_symbol_statistics(client, symbol):
    intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1w", "1M"]
    klines_data = {interval: get_kline_data(client, symbol, interval, 200) for interval in intervals}
    
    closes = {interval: np.array([float(k[4]) for k in klines]) for interval, klines in klines_data.items()}
    highs = {interval: np.array([float(k[2]) for k in klines]) for interval, klines in klines_data.items()}
    lows = {interval: np.array([float(k[3]) for k in klines]) for interval, klines in klines_data.items()}
    current_price = float(closes['1m'][-1])

    ema22 = {interval: talib.EMA(closes[interval], timeperiod=22) for interval in intervals}
    ema200 = talib.EMA(closes['1d'], timeperiod=200)

    above_ema22 = {interval: float(np.sum(closes[interval] > ema22[interval]) / len(closes[interval])) for interval in intervals}
    above_ema200 = float(np.sum(closes['1d'] > ema200) / len(closes['1d']))

    weekly_open = float(klines_data['1w'][0][1])
    monthly_open = float(klines_data['1M'][0][1])

    weekly_position = float((current_price - weekly_open) / weekly_open * 100)
    monthly_position = float((current_price - monthly_open) / monthly_open * 100)

    volatility = {
        '1m': calculate_volatility(closes['1m']),
        '5m': calculate_volatility(closes['5m'])
    }

    macd, signal, _ = talib.MACD(closes['15m'])
    crossovers = calculate_crossovers(macd, signal)

    current_price_above_ema22 = {interval: bool(current_price > ema22[interval][-1]) for interval in intervals}

    td9 = {interval: calculate_td9(highs[interval], lows[interval], closes[interval]) for interval in intervals}

    return {
        "symbol": symbol,
        "current_price": current_price,
        "above_ema22": above_ema22,
        "above_ema200_daily": above_ema200,
        "weekly_position": weekly_position,
        "monthly_position": monthly_position,
        "volatility": volatility,
        "fifteen_min_crossovers": crossovers,
        "current_price_above_ema22": current_price_above_ema22,
        "td9": td9
    }

def calculate_volatility(closes):
    volatility = float(np.std(np.diff(closes) / closes[:-1]))
    direction = "正向" if closes[-1] > closes[0] else "负向"
    return {
        "value": volatility,
        "direction": direction,
        "change_count": int(np.sum(np.diff(closes) != 0))
    }

def calculate_crossovers(macd, signal):
    crossovers = int(np.sum((macd[:-1] <= signal[:-1]) & (macd[1:] > signal[1:]) |
                            (macd[:-1] >= signal[:-1]) & (macd[1:] < signal[1:])))
    return {
        "total": crossovers,
        "last_3": [crossovers for _ in range(3)]  # 这里需要实际计算最后3次的交叉
    }

def calculate_td9(highs, lows, closes):
    setup = np.zeros(len(closes))
    countdown = np.zeros(len(closes))
    setup_direction = 0
    countdown_direction = 0
    
    for i in range(4, len(closes)):
        # Setup phase
        if closes[i] > closes[i-4]:
            if setup_direction <= 0:
                setup_direction = 1
                setup[i] = 1
            else:
                setup[i] = min(setup[i-1] + 1, 9)
        elif closes[i] < closes[i-4]:
            if setup_direction >= 0:
                setup_direction = -1
                setup[i] = -1
            else:
                setup[i] = max(setup[i-1] - 1, -9)
        else:
            setup[i] = setup[i-1]
        
        # Countdown phase
        if abs(setup[i-1]) == 9:
            if setup[i-1] > 0 and lows[i] <= lows[i-2]:
                countdown[i] = countdown[i-1] + 1
                countdown_direction = 1
            elif setup[i-1] < 0 and highs[i] >= highs[i-2]:
                countdown[i] = countdown[i-1] - 1
                countdown_direction = -1
            else:
                countdown[i] = countdown[i-1]
        else:
            countdown[i] = countdown[i-1]
    
    current_setup = int(setup[-1])
    current_countdown = int(abs(countdown[-1]))
    
    return {
        "setup": current_setup,
        "countdown": current_countdown,
        "setup_direction": "买入" if current_setup > 0 else "卖出" if current_setup < 0 else "中性",
        "countdown_direction": "买入" if countdown_direction > 0 else "卖出" if countdown_direction < 0 else "中性"
    }

def get_kline_data(client, symbol, interval, limit):
    return client.get_klines(symbol=symbol, interval=interval, limit=limit)

def get_ai_suggestion(statistics):
    prompt = f"""
作为一位资深的加密货币交易分析师和策略师，请用中文回复，请根据以下{statistics['symbol']}交易对的详细技术指标和统计数据，提供一个全面而专业的交易分析和建议：

1. 交易对: {statistics['symbol']} 当前价格: {statistics['current_price']}

2. 多周期均线分析：
   - 日线EMA22上方比例：{statistics['above_ema22']['1d']:.2%}
   - 日线EMA200上方比例：{statistics['above_ema200_daily']:.2%}
   - 4小时EMA22上方比例：{statistics['above_ema22']['4h']:.2%}
   - 1小时EMA22上方比例：{statistics['above_ema22']['1h']:.2%}

3. 大周期位置判断：
   - 相对周线开盘价位置：{statistics['weekly_position']:.2f}%
   - 相对月线开盘价位置：{statistics['monthly_position']:.2f}%

4. 短周期EMA22穿越情况：
   {', '.join([f"{k}: {'是' if v else '否'}" for k, v in statistics['current_price_above_ema22'].items()])}

5. 短周期市场波动性：
   - 1分钟K线波动性：{statistics['volatility']['1m']['value']:.6f}，方向：{statistics['volatility']['1m']['direction']}，变化次数：{statistics['volatility']['1m']['change_count']}
   - 5分钟K线波动性：{statistics['volatility']['5m']['value']:.6f}，方向：{statistics['volatility']['5m']['direction']}，变化次数：{statistics['volatility']['5m']['change_count']}

6. 15分钟MACD交叉情况：
   总交叉次数：{statistics['fifteen_min_crossovers']['total']}
   最近三次交叉：{', '.join(map(str, statistics['fifteen_min_crossovers']['last_3']))}

7. TD9指标情况：
   {', '.join([f"{k}: Setup {v['setup']} ({v['setup_direction']}), Countdown {v['countdown']} ({v['countdown_direction']})" for k, v in statistics['td9'].items()])}

基于以上数据，请提供以下深入分析和建议：

1. 多周期趋势分析
2. 市场结构评估
3. 动量和波动性分析
4. 交易机会识别
5. 风险管理建议
6. 具体的交易策略建议，包括：
   - 3-10倍杠杆的建议
   - 每种杠杆的止盈止损点
   - 当前盈亏比分析
   - 当前K线状态评估
7. 技术指标组合分析，特别关注TD9指标在不同时间周期的表现

请确保您的所有回复内容都是中文，分析全面、深入且具有可操作性。同时考虑到不同投资风格和风险承受能力的交易者。您的建议应该既专业又易于理解，并强调风险管理的重要性。
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NVIDIA_API_KEY}"
    }

    data = {
        "model": "meta/llama3-70b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "top_p": 1,
        "max_tokens": 2048,
        "stream": False
    }

    response = requests.post(NVIDIA_API_URL, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        return f"获取AI建议时出错: {response.status_code} - {response.text}"
