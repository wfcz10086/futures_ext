# get_statistics_all.py
from flask import Blueprint, jsonify, render_template, session, current_app
from binance.client import Client
from auth import login_required
from models import User
from extensions import cache, db
import numpy as np
import talib
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

get_statistics_all_bp = Blueprint('get_statistics_all', __name__)

CRYPTO_LIST = [
    'BTCUSDT','CRVUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT', 'SOLUSDT', 'DOTUSDT', 'DOGEUSDT',
    'AVAXUSDT', 'LTCUSDT', 'LINKUSDT', 'UNIUSDT', 'MATICUSDT', 'XLMUSDT', 'VETUSDT', 'ICPUSDT',
    'FILUSDT', 'TRXUSDT', 'THETAUSDT', 'XMRUSDT', 'ATOMUSDT', 'AAVEUSDT', 'ALGOUSDT', 'FTMUSDT',
    'EGLDUSDT', 'NEARUSDT', 'XTZUSDT', 'FLOWUSDT', 'KSMUSDT', 'HBARUSDT'
]

INTERVALS = {
    'daily': Client.KLINE_INTERVAL_1DAY,
    'four_hour': Client.KLINE_INTERVAL_4HOUR,
    'hourly': Client.KLINE_INTERVAL_1HOUR
}

@get_statistics_all_bp.route('/crypto_market_overview', methods=['GET'])
@login_required
def crypto_market_overview():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user or not user.binance_keys:
        return jsonify(success=False, error="用户未登录或未设置Binance API密钥"), 401
    
    try:
        market_data = get_cached_market_data(user_id)
        return render_template('crypto_market_overview.html', market_data=market_data)
    except Exception as e:
        current_app.logger.error(f"Error in crypto_market_overview: {str(e)}")
        return jsonify(success=False, error="获取市场数据时发生错误"), 500

@cache.memoize(timeout=300)
def get_cached_market_data(user_id):
    user = User.query.get(user_id)
    if not user or not user.binance_keys:
        raise ValueError("Invalid user or missing Binance keys")
    
    client = Client(user.binance_keys[0].api_key, user.binance_keys[0].secret_key)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        market_data = list(executor.map(lambda symbol: analyze_crypto(client, symbol), CRYPTO_LIST))
    
    return market_data

@lru_cache(maxsize=None)
def get_kline_data(client, symbol, interval, limit):
    try:
        return client.get_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception as e:
        current_app.logger.error(f"Error fetching kline data for {symbol}: {str(e)}")
        return []

def analyze_crypto(client, symbol):
    kline_data = {key: get_kline_data(client, symbol, interval, 200) for key, interval in INTERVALS.items()}
    if not all(kline_data.values()):
        return {'symbol': symbol, 'error': '无法获取数据'}
    
    hourly_data = kline_data['hourly']
    
    return {
        'symbol': symbol,
        'price_changes': calculate_price_changes(hourly_data),
        'ema_status': check_ema_status(hourly_data),
        'ema_above_count': count_ema_above(kline_data)
    }

def calculate_price_changes(hourly_data):
    return {f'{interval}h': round((float(hourly_data[-1][4]) - float(hourly_data[-interval][1])) / float(hourly_data[-interval][1]) * 100, 2)
            for interval in [2, 4, 6, 12, 24]}

def check_ema_status(hourly_data):
    closes = np.array([float(k[4]) for k in hourly_data])
    ema22 = talib.EMA(closes, timeperiod=22)
    return {f'{interval}h': 'Above EMA22' if float(hourly_data[-1][4]) > ema22[-interval] else 'Below EMA22'
            for interval in [2, 4, 6, 12, 24]}

def count_ema_above(kline_data):
    return {timeframe: sum(np.array([float(k[4]) for k in kline_data[timeframe]]) > 
                           talib.EMA(np.array([float(k[4]) for k in kline_data[timeframe]]), timeperiod=22))
            for timeframe in ['hourly', 'four_hour', 'daily']}

@get_statistics_all_bp.errorhandler(Exception)
def handle_error(e):
    current_app.logger.error(f"Unhandled exception: {str(e)}")
    return jsonify(success=False, error="服务器内部错误"), 500
