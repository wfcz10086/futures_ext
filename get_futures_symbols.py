from flask import Blueprint, jsonify, request, session, render_template
from models import BinanceKey, User, FuturesSymbol
from binance.client import Client
from binance.exceptions import BinanceAPIException
from auth import login_required
from extensions import db

get_futures_symbols_bp = Blueprint('get_futures_symbols', __name__)

@get_futures_symbols_bp.route('/futures_symbols')
@login_required
def futures_symbols():
    user = User.query.get(session['user_id'])
    binance_keys = user.binance_keys
    
    page = request.args.get('page', 1, type=int)
    pagination = FuturesSymbol.query.filter_by(user_id=session['user_id']).paginate(page, per_page=10, error_out=False)
    saved_symbols = pagination.items
    
    return render_template('futures_symbols.html', binance_keys=binance_keys, saved_symbols=saved_symbols, pagination=pagination)

@get_futures_symbols_bp.route('/get_futures_symbols', methods=['POST'])
@login_required
def get_futures_symbols():
    key_id = request.form['binance_key']
    binance_key = BinanceKey.query.get(key_id)
    
    if binance_key and binance_key.user_id == session['user_id']:
        client = Client(binance_key.api_key, binance_key.secret_key)
        try:
            exchange_info = client.futures_exchange_info()
            symbols = [symbol['symbol'] for symbol in exchange_info['symbols']]
            
            # 删除用户原有的期货币种记录
            FuturesSymbol.query.filter_by(user_id=session['user_id']).delete()
            
            # 保存新的期货币种记录  
            for symbol in symbols:
                futures_symbol = FuturesSymbol(symbol=symbol, user_id=session['user_id'])
                db.session.add(futures_symbol)
            db.session.commit()
            
            return jsonify(success=True)
        except BinanceAPIException as e:
            return jsonify(success=False, error=f"Binance API Error: {e.status_code} - {e.message}"), 400
        except Exception as e:
            return jsonify(success=False, error=f"Error: {str(e)}"), 500
    else:
        return jsonify(success=False, error="Invalid Binance key."), 400

@get_futures_symbols_bp.route('/delete_futures_symbol', methods=['POST'])
@login_required
def delete_futures_symbol():
    symbol = request.form['symbol']
    futures_symbol = FuturesSymbol.query.filter_by(user_id=session['user_id'], symbol=symbol).first()
    
    if futures_symbol:
        db.session.delete(futures_symbol)
        db.session.commit()
        return jsonify(success=True)
    else:
        return jsonify(success=False, error="期货币种未找到。"), 404
