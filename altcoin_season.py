from flask import Blueprint, jsonify, render_template, request, session
from flask_paginate import Pagination, get_page_parameter
from binance.client import Client
from auth import login_required
from models import BinanceKey, User, FuturesSymbol
from extensions import db, cache
import numpy as np
import talib
import json
from datetime import datetime, timedelta

altcoin_season_bp = Blueprint('altcoin_season', __name__)

TOP_70_COINS = [
    'BTC', 'ETH', 'BNB', 'ADA', 'XRP', 'SOL', 'DOT', 'DOGE', 'AVAX', 'MATIC',
    'UNI', 'LINK', 'AAVE', 'MKR', 'COMP', 'SNX', 'YFI', 'CAKE', 'SUSHI', 'CRV',
    'LRC', 'OMG', 'SKL', 'IMX', 'SHIB', 'FLOKI', 'FTT',
    'USDC', 'BUSD', 'DAI', 'XMR', 'ZEC', 'DASH',
    'FIL', 'THETA', 'ICP', 'GRT', 'AR', 'STX',
    'AXS', 'MANA', 'SAND', 'ENJ', 'GALA', 'ILV',
    'VET', 'ATOM', 'ALGO', 'XTZ', 'NEO', 'IOTA', 'EOS', 'XLM', 'TRX', 'NEAR',
    'ONE', 'FTM', 'EGLD', 'HBAR', 'WAVES', 'KSM', 'FLOW', 'XEM', 'DCR', 'ZIL'
]

SECTORS = {
    'DeFi': ['AAVE', 'UNI', 'LINK', 'SNX', 'COMP', 'MKR', 'YFI', 'CAKE', 'SUSHI', 'CRV', 'LRC'],
    'Layer1': ['ETH', 'BNB', 'ADA', 'SOL', 'DOT', 'AVAX', 'MATIC', 'ATOM', 'NEAR', 'FTM', 'ALGO', 'ONE', 'EGLD'],
    'Gaming': ['AXS', 'MANA', 'SAND', 'ENJ', 'GALA', 'ILV', 'THETA'],
    'Privacy': ['XMR', 'ZEC', 'DASH'],
    'Exchange': ['BNB', 'FTT', 'CRO', 'HT', 'KCS'],
    'Layer2': ['MATIC', 'LRC', 'OMG', 'SKL', 'IMX'],
    'Storage': ['FIL', 'AR', 'STORJ', 'SC'],
    'Interoperability': ['DOT', 'ATOM', 'NEAR', 'QNT', 'ICX'],
    'Oracle': ['LINK', 'BAND', 'TRB', 'API3'],
    'IoT': ['IOTA', 'VET', 'IOTX', 'WTC'],
    'Meme': ['DOGE', 'SHIB', 'FLOKI', 'ELON']
}

def convert_to_serializable(obj):
    if isinstance(obj, (np.generic, np.ndarray)):
        return obj.item() if isinstance(obj, np.generic) else obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

@altcoin_season_bp.route('/altcoin_season_analysis', methods=['GET'])
@login_required
def altcoin_season_analysis():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify(success=False, error="用户不存在"), 404

    binance_key = BinanceKey.query.filter_by(user_id=user_id).first()
    if not binance_key:
        return jsonify(success=False, error="没有有效的 Binance 密钥"), 400

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

    return render_template('altcoin_season_analysis.html', 
                           binance_key=binance_key, 
                           futures_symbols=futures_symbols.items, 
                           pagination=pagination)

@altcoin_season_bp.route('/analyze_altcoin_season', methods=['POST'])
@login_required
def analyze_altcoin_season():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401

    binance_key = BinanceKey.query.filter_by(user_id=user_id).first()
    if not binance_key:
        return jsonify(success=False, error="没有有效的 Binance 密钥"), 400

    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        analysis_data = get_cached_altcoin_season_data(client)
        serializable_analysis = convert_to_serializable(analysis_data)
        return jsonify(success=True, data=serializable_analysis)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@cache.memoize(timeout=300)
def get_cached_altcoin_season_data(client):
    return get_altcoin_season_data(client)

def get_altcoin_season_data(client):
    try:
        coin_data = get_all_coin_data(client)

        altcoin_performance = analyze_altcoin_performance(coin_data)
        top_performers = get_top_performers(coin_data)
        altcoin_season_index = calculate_altcoin_season_index(coin_data)
        eth_btc_ratio = analyze_eth_btc_ratio(client)
        volume_trends = analyze_volume_trends(coin_data)
        top_sectors = analyze_sector_performance(coin_data)

        return {
            'altcoin_performance': altcoin_performance,
            'top_performers': top_performers,
            'altcoin_season_index': altcoin_season_index,
            'eth_btc_ratio': eth_btc_ratio,
            'volume_trends': volume_trends,
            'top_sectors': top_sectors,
            'coin_data': coin_data
        }
    except Exception as e:
        raise ValueError(f"获取市场数据时发生错误: {str(e)}")

def get_all_coin_data(client):
    coin_data = []
    for coin in TOP_70_COINS:
        try:
            symbol = f"{coin}USDT"
            ticker = client.get_ticker(symbol=symbol)
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1DAY, limit=180)
            
            price_changes = {
                '3d': calculate_price_change(klines, 3),
                '7d': calculate_price_change(klines, 7),
                '15d': calculate_price_change(klines, 15),
                '30d': calculate_price_change(klines, 30),
                '60d': calculate_price_change(klines, 60),
                '180d': calculate_price_change(klines, 180)
            }
            
            if any(change is None for change in price_changes.values()):
                print(f"Skipping {coin} due to insufficient price change data")
                continue
            
            coin_data.append({
                'symbol': coin,
                'price_change_24h': float(ticker['priceChangePercent']),
                'price_changes': price_changes,
                'total_volume': float(ticker['volume']),
                'current_price': float(ticker['lastPrice'])
            })
        except Exception as e:
            print(f"Error fetching data for {coin}: {str(e)}")
            continue
    
    return coin_data

def calculate_price_change(klines, days):
    if len(klines) < days:
        return None
    current_price = float(klines[-1][4])
    past_price = float(klines[-days][4])
    return ((current_price - past_price) / past_price) * 100

def analyze_altcoin_performance(coin_data):
    btc_performance = next((coin['price_changes']['30d'] for coin in coin_data if coin['symbol'] == 'BTC'), None)
    if not btc_performance:
        return 0
    altcoins_outperforming = sum(1 for coin in coin_data if coin['symbol'] != 'BTC' and coin['price_changes']['30d'] > btc_performance)
    return (altcoins_outperforming / (len(coin_data) - 1)) * 100 if len(coin_data) > 1 else 0

def get_top_performers(coin_data):
    top_performers = {}
    for period in ['3d', '7d', '15d', '30d', '60d', '180d']:
        sorted_coins = sorted(coin_data, key=lambda x: x['price_changes'][period], reverse=True)
        top_performers[period] = [{'symbol': coin['symbol'], 'performance': coin['price_changes'][period]} for coin in sorted_coins[:5]]
    return top_performers

def calculate_altcoin_season_index(coin_data):
    btc_performance = next((coin['price_changes']['180d'] for coin in coin_data if coin['symbol'] == 'BTC'), None)
    if btc_performance is None:
        return 0
    altcoins_outperforming = sum(1 for coin in coin_data if coin['symbol'] != 'BTC' and coin['price_changes']['180d'] > btc_performance)
    return (altcoins_outperforming / (len(coin_data) - 1)) * 100 if len(coin_data) > 1 else 0

def analyze_eth_btc_ratio(client):
    try:
        eth_price = float(client.get_symbol_ticker(symbol="ETHUSDT")['price'])
        btc_price = float(client.get_symbol_ticker(symbol="BTCUSDT")['price'])
        return eth_price / btc_price if btc_price > 0 else 0
    except Exception as e:
        print(f"Error calculating ETH/BTC ratio: {str(e)}")
        return 0

def analyze_volume_trends(coin_data):
    btc_volume = next((coin['total_volume'] for coin in coin_data if coin['symbol'] == 'BTC'), 0)
    altcoin_volumes = [coin['total_volume'] for coin in coin_data if coin['symbol'] != 'BTC']
    avg_altcoin_volume = sum(altcoin_volumes) / len(altcoin_volumes) if altcoin_volumes else 0
    return avg_altcoin_volume / btc_volume if btc_volume > 0 else 0

def analyze_sector_performance(coin_data):
    sector_performances = {}
    for sector, coins in SECTORS.items():
        performances = [coin['price_changes']['30d'] for coin in coin_data if coin['symbol'] in coins]
        if performances:
            sector_performances[sector] = sum(performances) / len(performances)
    
    sorted_sectors = sorted(sector_performances.items(), key=lambda x: x[1], reverse=True)
    return [{'sector': sector, 'performance': performance} for sector, performance in sorted_sectors[:3]]

@altcoin_season_bp.route('/get_coin_details', methods=['GET'])
@login_required
def get_coin_details():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify(success=False, error="未提供币种符号"), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify(success=False, error="未登录"), 401

    binance_key = BinanceKey.query.filter_by(user_id=user_id).first()
    if not binance_key:
        return jsonify(success=False, error="没有有效的 Binance 密钥"), 400

    client = Client(binance_key.api_key, binance_key.secret_key)

    try:
        coin_data = get_coin_detailed_data(client, symbol)
        return jsonify(success=True, data=coin_data)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

def get_coin_detailed_data(client, symbol):
    try:
        ticker = client.get_ticker(symbol=f"{symbol}USDT")
        klines = client.get_klines(symbol=f"{symbol}USDT", interval=Client.KLINE_INTERVAL_1DAY, limit=180)

        price_changes = {
            '3d': calculate_price_change(klines, 3),
            '7d': calculate_price_change(klines, 7),
            '15d': calculate_price_change(klines, 15),
            '30d': calculate_price_change(klines, 30),
            '60d': calculate_price_change(klines, 60),
            '180d': calculate_price_change(klines, 180)
        }

        closes = np.array([float(k[4]) for k in klines])
        rsi = talib.RSI(closes)[-1]
        macd, signal, _ = talib.MACD(closes)
        
        current_macd = macd[-1]
        current_signal = signal[-1]

        return {
            'symbol': symbol,
            'current_price': float(ticker['lastPrice']),
            'price_change_24h': float(ticker['priceChangePercent']),
            'price_changes': price_changes,
            'volume_24h': float(ticker['volume']),
            'rsi': rsi,
            'macd': current_macd,
            'macd_signal': current_signal
        }
    except Exception as e:
        raise ValueError(f"获取 {symbol} 详细数据时发生错误: {str(e)}")
