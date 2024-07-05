from flask import Blueprint, jsonify, render_template, request, session
from flask_paginate import Pagination, get_page_parameter
from binance.client import Client
from auth import login_required
from models import BinanceKey, User, FuturesSymbol
from extensions import db
import numpy as np
import talib
import json
get_statistics_bp = Blueprint('get_statistics', __name__)


@get_statistics_bp.route('/indicator_description', methods=['GET'])
@login_required
def indicator_description():
    return render_template('indicator_description.html')



@get_statistics_bp.route('/get_statistics_page', methods=['GET'])
@login_required
def get_statistics_page():
    # 获取当前用户
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify(success=False, error="用户不存在"), 404

    binance_keys = user.binance_keys

    # 分页
    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = 10

    # 获取与当前用户相关的期货交易对
    futures_symbols = FuturesSymbol.query.filter_by(user_id=user_id).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 创建分页对象
    pagination = Pagination(
        page=page, 
        total=futures_symbols.total, 
        per_page=per_page, 
        css_framework='bootstrap4'
    )

    return render_template('get_statistics.html', 
                           binance_keys=binance_keys, 
                           futures_symbols=futures_symbols.items, 
                           pagination=pagination)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

def convert_to_serializable(obj):
    if isinstance(obj, (np.generic, np.ndarray)):
        return obj.item() if isinstance(obj, np.generic) else obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    return obj

@get_statistics_bp.route('/analyze_symbol', methods=['POST'])
@login_required
def analyze_symbol():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401

    user = User.query.get(user_id)
    if not user or not user.binance_keys:
        return jsonify(success=False, error="没有有效的 Binance 密钥"), 400

    binance_key = user.binance_keys[0]  # 假设用户至少有一个密钥
    symbol = request.form.get('symbol')
    
    if not symbol:
        return jsonify(success=False, error="未提供交易对"), 400
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        statistics = calculate_symbol_statistics(client, symbol)
        
        # 转换统计数据为可序列化格式
        serializable_statistics = convert_to_serializable(statistics)
        
        # 使用自定义编码器进行 JSON 序列化
        return json.dumps({
            'success': True,
            'statistics': serializable_statistics
        }, cls=NumpyEncoder)
    except Exception as e:
        print(f"Error in analyze_symbol: {str(e)}")  # 用于调试
        return jsonify(success=False, error=f"分析交易对时发生错误: {str(e)}"), 500


def get_kline_data(client, symbol):
    intervals = {
        'daily': Client.KLINE_INTERVAL_1DAY,
        'four_hour': Client.KLINE_INTERVAL_4HOUR,
        'hourly': Client.KLINE_INTERVAL_1HOUR,
        'fifteen_min': Client.KLINE_INTERVAL_15MINUTE,
        'one_min': Client.KLINE_INTERVAL_1MINUTE,
        'five_min': Client.KLINE_INTERVAL_5MINUTE,
        'weekly': Client.KLINE_INTERVAL_1WEEK,
        'monthly': Client.KLINE_INTERVAL_1MONTH
    }

    limits = {
        'daily': 200,
        'four_hour': 100,
        'hourly': 100,
        'fifteen_min': 300,
        'one_min': 200,
        'five_min': 200,
        'weekly': 1,
        'monthly': 1
    }

    kline_data = {}

    for key, interval in intervals.items():
        kline_data[key] = client.get_klines(symbol=symbol, interval=interval, limit=limits[key])

    return kline_data

import numpy as np
import talib
from binance.client import Client

def calculate_symbol_statistics(client, symbol):
    kline_data = get_kline_data(client, symbol)

    # 1-4. 计算高于 EMA 的蜡烛比例
    daily_closes = np.array([float(k[4]) for k in kline_data['daily'][-100:]])
    daily_ema22 = talib.EMA(daily_closes, timeperiod=22)
    daily_ema200 = talib.EMA(daily_closes, timeperiod=200)
    above_ema22_daily = float(np.sum(daily_closes > daily_ema22) / len(daily_closes))
    above_ema200_daily = float(np.sum(daily_closes > daily_ema200) / len(daily_closes))

    four_hour_closes = np.array([float(k[4]) for k in kline_data['four_hour']])
    four_hour_ema22 = talib.EMA(four_hour_closes, timeperiod=22)
    above_ema22_4h = float(np.sum(four_hour_closes > four_hour_ema22) / len(four_hour_closes))

    hourly_closes = np.array([float(k[4]) for k in kline_data['hourly']])
    hourly_ema22 = talib.EMA(hourly_closes, timeperiod=22)
    above_ema22_1h = float(np.sum(hourly_closes > hourly_ema22) / len(hourly_closes))

    # 5-7. 最新日线收盘价相对于周线、月线的位置
    latest_daily_close = float(kline_data['daily'][-1][4])
    weekly_open = float(kline_data['weekly'][0][1])
    monthly_open = float(kline_data['monthly'][0][1])

    weekly_position = float(latest_daily_close / weekly_open)
    monthly_position = float(latest_daily_close / monthly_open)

    # 8. 检查最新的 15m, 30m, 1h, 2h, 4h 蜡烛是否高于各自的 EMA22
    above_ema22 = {}
    for interval in ['15MINUTE', '30MINUTE', '1HOUR', '2HOUR', '4HOUR']:
        klines = client.get_klines(symbol=symbol, interval=getattr(Client, f'KLINE_INTERVAL_{interval}'), limit=22)
        closes = np.array([float(k[4]) for k in klines])
        ema22 = talib.EMA(closes, timeperiod=22)
        above_ema22[interval.lower().replace('minute', 'm').replace('hour', 'h')] = bool(closes[-1] > ema22[-1])

    # 10-11. K线波动性
    one_min_closes = np.array([float(k[4]) for k in kline_data['one_min']])
    one_min_changes = np.diff(one_min_closes) / one_min_closes[:-1]
    one_min_volatile_count = int(np.sum(np.abs(one_min_changes) > 0.001))
    one_min_volatility = (one_min_volatile_count, float(one_min_volatile_count / len(one_min_changes)), 
                          "正向" if np.sum(one_min_changes > 0.001) > np.sum(one_min_changes < -0.001) else "负向")

    five_min_closes = np.array([float(k[4]) for k in kline_data['five_min']])
    five_min_changes = np.diff(five_min_closes) / five_min_closes[:-1]
    five_min_volatile_count = int(np.sum(np.abs(five_min_changes) > 0.0015))
    five_min_volatility = (five_min_volatile_count, float(five_min_volatile_count / len(five_min_changes)), 
                           "正向" if np.sum(five_min_changes > 0.0015) > np.sum(five_min_changes < -0.0015) else "负向")

    # 12. 15分钟 MACD 和 EMA 交叉
    fifteen_min_closes = np.array([float(k[4]) for k in kline_data['fifteen_min']])
    macd, signal, _ = talib.MACD(fifteen_min_closes)
    ema18 = talib.EMA(fifteen_min_closes, timeperiod=18)
    ema36 = talib.EMA(fifteen_min_closes, timeperiod=36)
    
    macd_golden_cross = int(np.sum(macd > signal))
    macd_death_cross = int(np.sum(macd < signal))
    ema_golden_cross = int(np.sum(ema18 > ema36))
    ema_death_cross = int(np.sum(ema18 < ema36))
    
    fifteen_min_crossovers = (macd_golden_cross, macd_death_cross, ema_golden_cross, ema_death_cross)

    # 13. 检查当前价格是否高于各时间周期的 EMA22
    current_price_above_ema22 = {}
    for interval in ['3MINUTE', '5MINUTE', '15MINUTE', '30MINUTE', '1HOUR', '2HOUR', '4HOUR', '6HOUR', '8HOUR', '12HOUR', '1DAY']:
        klines = client.get_klines(symbol=symbol, interval=getattr(Client, f'KLINE_INTERVAL_{interval}'), limit=22)
        closes = np.array([float(k[4]) for k in klines])
        ema22 = talib.EMA(closes, timeperiod=22)
        current_price_above_ema22[interval.lower().replace('minute', 'm').replace('hour', 'h').replace('day', 'd')] = bool(closes[-1] > ema22[-1])

    # 返回结果
    return {
        'symbol': symbol,
        'above_ema22_daily': round(above_ema22_daily, 3),
        'above_ema200_daily': round(above_ema200_daily, 3),
        'above_ema22_4h': round(above_ema22_4h, 3),
        'above_ema22_1h': round(above_ema22_1h, 3),
        'weekly_position': round(weekly_position, 3),
        'monthly_position': round(monthly_position, 3),
        'above_ema22': above_ema22,
        'one_min_volatility': one_min_volatility,
        'five_min_volatility': five_min_volatility,
        'fifteen_min_crossovers': fifteen_min_crossovers,
        'current_price_above_ema22': current_price_above_ema22
    }
