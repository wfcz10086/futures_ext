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
    daily_klines = get_kline_data(client, symbol, "1d", 200)
    four_hour_klines = get_kline_data(client, symbol, "4h", 200)
    one_hour_klines = get_kline_data(client, symbol, "1h", 200)
    fifteen_min_klines = get_kline_data(client, symbol, "15m", 200)
    five_min_klines = get_kline_data(client, symbol, "5m", 200)
    one_min_klines = get_kline_data(client, symbol, "1m", 200)
    weekly_klines = get_kline_data(client, symbol, "1w", 1)
    monthly_klines = get_kline_data(client, symbol, "1M", 1)

    daily_closes = np.array([float(k[4]) for k in daily_klines])
    four_hour_closes = np.array([float(k[4]) for k in four_hour_klines])
    one_hour_closes = np.array([float(k[4]) for k in one_hour_klines])
    fifteen_min_closes = np.array([float(k[4]) for k in fifteen_min_klines])
    five_min_closes = np.array([float(k[4]) for k in five_min_klines])
    one_min_closes = np.array([float(k[4]) for k in one_min_klines])

    current_price = float(daily_closes[-1])
    weekly_open = float(weekly_klines[0][1])
    monthly_open = float(monthly_klines[0][1])

    daily_ema22 = talib.EMA(daily_closes, timeperiod=22)
    daily_ema200 = talib.EMA(daily_closes, timeperiod=200)
    four_hour_ema22 = talib.EMA(four_hour_closes, timeperiod=22)
    one_hour_ema22 = talib.EMA(one_hour_closes, timeperiod=22)
    fifteen_min_ema22 = talib.EMA(fifteen_min_closes, timeperiod=22)
    five_min_ema22 = talib.EMA(five_min_closes, timeperiod=22)
    one_min_ema22 = talib.EMA(one_min_closes, timeperiod=22)

    above_ema22_daily = sum(daily_closes > daily_ema22) / len(daily_closes)
    above_ema200_daily = sum(daily_closes > daily_ema200) / len(daily_closes)
    above_ema22_4h = sum(four_hour_closes > four_hour_ema22) / len(four_hour_closes)
    above_ema22_1h = sum(one_hour_closes > one_hour_ema22) / len(one_hour_closes)

    weekly_position = (current_price - weekly_open) / weekly_open
    monthly_position = (current_price - monthly_open) / monthly_open

    above_ema22 = {
        "15min": fifteen_min_closes[-1] > fifteen_min_ema22[-1],
        "5min": five_min_closes[-1] > five_min_ema22[-1],
        "1min": one_min_closes[-1] > one_min_ema22[-1]
    }

    one_min_volatility = np.std(np.diff(one_min_closes) / one_min_closes[:-1])
    five_min_volatility = np.std(np.diff(five_min_closes) / five_min_closes[:-1])

    fifteen_min_macd, fifteen_min_signal, _ = talib.MACD(fifteen_min_closes)
    fifteen_min_crossovers = sum((fifteen_min_macd[i-1] <= fifteen_min_signal[i-1] and 
                                  fifteen_min_macd[i] > fifteen_min_signal[i]) or
                                 (fifteen_min_macd[i-1] >= fifteen_min_signal[i-1] and 
                                  fifteen_min_macd[i] < fifteen_min_signal[i])
                                 for i in range(1, len(fifteen_min_macd)))

    current_price_above_ema22 = {
        "1d": current_price > daily_ema22[-1],
        "4h": current_price > four_hour_ema22[-1],
        "1h": current_price > one_hour_ema22[-1],
        "15min": current_price > fifteen_min_ema22[-1],
        "5min": current_price > five_min_ema22[-1],
        "1min": current_price > one_min_ema22[-1]
    }

    return {
        "symbol": symbol,
        "above_ema22_daily": float(above_ema22_daily),
        "above_ema200_daily": float(above_ema200_daily),
        "above_ema22_4h": float(above_ema22_4h),
        "above_ema22_1h": float(above_ema22_1h),
        "weekly_position": float(weekly_position),
        "monthly_position": float(monthly_position),
        "above_ema22": {k: bool(v) for k, v in above_ema22.items()},
        "one_min_volatility": float(one_min_volatility),
        "five_min_volatility": float(five_min_volatility),
        "fifteen_min_crossovers": int(fifteen_min_crossovers),
        "current_price_above_ema22": {k: bool(v) for k, v in current_price_above_ema22.items()}
    }

def get_kline_data(client, symbol, interval, limit):
    return client.get_klines(symbol=symbol, interval=interval, limit=limit)

def get_ai_suggestion(statistics):
    prompt = f"""
作为一位资深的加密货币交易分析师和策略师，请用中文回复，请根据以下{statistics['symbol']}交易对的详细技术指标和统计数据，提供一个全面而专业的交易分析和建议：

1. 多周期均线分析：
   - 日线EMA22上方比例：{statistics['above_ema22_daily']}
   - 日线EMA200上方比例：{statistics['above_ema200_daily']}
   - 4小时EMA22上方比例：{statistics['above_ema22_4h']}
   - 1小时EMA22上方比例：{statistics['above_ema22_1h']}

2. 大周期位置判断：
   - 相对周线开盘价位置：{statistics['weekly_position']}
   - 相对月线开盘价位置：{statistics['monthly_position']}

3. 短周期EMA22穿越情况：
   {statistics['above_ema22']}

4. 短周期市场波动性：
   - 1分钟K线波动性：{statistics['one_min_volatility']}
   - 5分钟K线波动性：{statistics['five_min_volatility']}

5. 中期趋势指标：
   15分钟MACD和EMA交叉情况：{statistics['fifteen_min_crossovers']}

6. 多周期EMA22价格关系：
   {statistics['current_price_above_ema22']}

基于以上数据，请提供以下深入分析和建议：

1. 多周期趋势分析
2. 市场结构评估
3. 动量和波动性分析
4. 交易机会识别
5. 风险管理建议
6. 具体的交易策略建议
7. 技术指标组合分析
8. 市场情绪和潜在催化剂

请确保您的所有回复内容都是中文，这个非常重要，分析全面、深入且具有可操作性，一定要使用用中文来回复，同时考虑到不同投资风格和风险承受能力的交易者。您的建议应该既专业又易于理解，并强调风险管理的重要性。
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

# 将此Blueprint添加到您的Flask应用中
# app.register_blueprint(get_statistics_with_ai_bp)
