from binance.client import Client
from flask import Blueprint, jsonify, request, session, render_template
from auth import login_required
from models import BinanceKey, User

get_klines_bp = Blueprint('get_klines', __name__)

@get_klines_bp.route('/get_klines', methods=['GET'])
@login_required
def get_klines_page():
    user = User.query.get(session['user_id'])
    binance_keys = user.binance_keys
    return render_template('get_klines.html', binance_keys=binance_keys)

@get_klines_bp.route('/get_klines', methods=['POST'])
@login_required
def get_klines():
    key_id = request.form['binance_key']
    symbol = request.form['symbol']
    interval = request.form['interval']
    limit = int(request.form['limit'])
    
    binance_key = BinanceKey.query.get(key_id)
    
    if binance_key and binance_key.user_id == session['user_id']:
        client = Client(binance_key.api_key, binance_key.secret_key)
        
        try:
            if interval == '1h':
                interval = Client.KLINE_INTERVAL_1HOUR
            elif interval == '2h':
                interval = Client.KLINE_INTERVAL_2HOUR
            elif interval == '4h':
                interval = Client.KLINE_INTERVAL_4HOUR
            elif interval == '6h':
                interval = Client.KLINE_INTERVAL_6HOUR
            elif interval == '8h':
                interval = Client.KLINE_INTERVAL_8HOUR
            elif interval == '12h':
                interval = Client.KLINE_INTERVAL_12HOUR
            else:
                interval = Client.KLINE_INTERVAL_1DAY
            
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            
            processed_klines = []
            for kline in klines:
                processed_klines.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_asset_volume': float(kline[7]),
                    'number_of_trades': kline[8],
                    'taker_buy_base_asset_volume': float(kline[9]),
                    'taker_buy_quote_asset_volume': float(kline[10])
                })
            
            return jsonify(success=True, klines=processed_klines)
        except Exception as e:
            return jsonify(success=False, error=f"Error: {str(e)}"), 500
    else:
        return jsonify(success=False, error="Invalid Binance key."), 400
