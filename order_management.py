from flask import Blueprint, render_template, request, session, jsonify
from auth import login_required
from models import BinanceKey, Order, FuturesSymbol
from extensions import db
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from decimal import Decimal
import json
from binance.exceptions import BinanceAPIException
from decimal import Decimal, ROUND_DOWN
import logging

order_management_bp = Blueprint('order_management', __name__)

def round_price(price, tick_size):
    return round(Decimal(price), Decimal(tick_size).as_tuple().exponent)

@order_management_bp.route('/order_management')
@login_required
def order_management():
    page = request.args.get('page', 1, type=int)
    symbols = FuturesSymbol.query.filter_by(user_id=session['user_id']).paginate(page=page, per_page=10)
    return render_template('order_management.html', symbols=symbols)

@order_management_bp.route('/order/<symbol>', methods=['GET', 'POST'])
@login_required
def order(symbol):
    key = BinanceKey.query.filter_by(user_id=session['user_id']).first()

    if not key:
        return "No API key found", 404

    client = Client(key.api_key, key.secret_key)
    
    try:
        # 获取交易对信息
        exchange_info = client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        
        if not symbol_info:
            return f"Symbol {symbol} not found", 404

        # 获取当前期货价格
        current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])

        # 获取不同时间段的K线数据
        klines = {}
        intervals = ['5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']
        for interval in intervals:
            klines[interval] = client.futures_klines(symbol=symbol, interval=interval, limit=2)

        # 计算价格增长幅度
        price_changes = {}
        for interval, kline in klines.items():
            open_price = float(kline[0][1])
            close_price = float(kline[-1][4])
            price_change = (close_price - open_price) / open_price * 100
            price_changes[interval] = round(price_change, 2)

        # 获取账户余额和合约信息
        account_info = client.futures_account()
        usdt_balance = float(next(asset for asset in account_info['assets'] if asset['asset'] == 'USDT')['walletBalance'])
        
        # 获取最小下单量
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
        min_qty = float(lot_size_filter['minQty'])

        max_qty_dict = {}
        long_liquidation_price_dict = {}
        short_liquidation_price_dict = {}
        total_position_dict = {}
        
        for leverage in range(1, 11):
            max_qty = (usdt_balance * leverage / current_price) // min_qty * min_qty  # 确保数量是最小下单量的整数倍
            max_qty_dict[str(leverage)] = round(max_qty, 3)
            
            # 计算做多的爆仓价格
            long_liquidation_price = current_price * (1 - 1 / leverage)
            long_liquidation_price_dict[str(leverage)] = round(long_liquidation_price, 4)
            
            # 计算做空的爆仓价格
            short_liquidation_price = current_price * (1 + 1 / leverage)
            short_liquidation_price_dict[str(leverage)] = round(short_liquidation_price, 4)
            
            total_position = usdt_balance * leverage
            total_position_dict[str(leverage)] = round(total_position, 2)

        price_per_contract = current_price * min_qty

        # 获取当前合约利率
        try:
            funding_rate = float(client.futures_funding_rate(symbol=symbol)[-1]['fundingRate'])
        except Exception as e:
            print(f"Error fetching funding rate: {str(e)}")
            funding_rate = None

        return render_template('order.html', 
                               symbol=symbol,
                               current_price=current_price,
                               price_changes=price_changes,
                               usdt_balance=usdt_balance,
                               max_qty_dict=max_qty_dict,
                               long_liquidation_price_dict=long_liquidation_price_dict,
                               short_liquidation_price_dict=short_liquidation_price_dict,
                               total_position_dict=total_position_dict,
                               price_per_contract=price_per_contract,
                               funding_rate=funding_rate)

    except BinanceAPIException as e:
        return str(e), 400
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}", 500
from flask import jsonify, request, current_app
from flask_login import login_required, current_user
from binance.exceptions import BinanceAPIException
from decimal import Decimal, ROUND_DOWN
import logging

# 假设这些是您的蓝图和 Binance 客户端设置
# from your_app import order_management_bp, client

def round_step_size(quantity: float, step_size: float) -> float:
    """将数量舍入到最接近的步长"""
    precision = len(str(step_size).split('.')[-1])
    return float(Decimal(str(quantity)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))

@order_management_bp.route('/place_order/<symbol>', methods=['POST'])
@login_required
def place_order(symbol):
    try:
        # 从请求中获取参数
        data = request.json
        order_type = data.get('order_type', 'MARKET').upper()
        direction = data.get('direction', 'long').lower()
        quantity = float(data.get('quantity', 0))
        price = float(data.get('price', 0)) if order_type == 'LIMIT' else None
        leverage = int(data.get('leverage', 1))
        take_profit = float(data.get('take_profit', 0))
        stop_loss = float(data.get('stop_loss', 0))

        # 验证参数
        if not symbol or not order_type or not direction or quantity <= 0:
            return jsonify(success=False, error="Invalid parameters provided"), 400

        if order_type == 'LIMIT' and price <= 0:
            return jsonify(success=False, error="Invalid price for limit order"), 400

        # 获取交易对的信息
        symbol_info = client.futures_exchange_info()
        symbol_info = next((s for s in symbol_info['symbols'] if s['symbol'] == symbol), None)
        if not symbol_info:
            return jsonify(success=False, error=f"Symbol {symbol} not found"), 400

        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
        price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', symbol_info['filters']))
        
        step_size = float(lot_size_filter['stepSize'])
        tick_size = float(price_filter['tickSize'])

        # 舍入数量和价格
        quantity = round_step_size(quantity, step_size)
        if order_type == 'LIMIT':
            price = round_step_size(price, tick_size)

        # 设置杠杆
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # 创建订单参数
        order_params = {
            'symbol': symbol,
            'side': 'BUY' if direction == 'long' else 'SELL',
            'type': order_type,
            'quantity': quantity,
        }

        if order_type == 'LIMIT':
            order_params['price'] = price
            order_params['timeInForce'] = 'GTC'  # Good Till Cancel

        # 下单
        order = client.futures_create_order(**order_params)

        # 设置止盈止损
        if take_profit > 0:
            tp_params = order_params.copy()
            tp_params['type'] = 'TAKE_PROFIT_MARKET'
            tp_params['stopPrice'] = round_step_size(take_profit, tick_size)
            tp_params['side'] = 'SELL' if direction == 'long' else 'BUY'
            client.futures_create_order(**tp_params)

        if stop_loss > 0:
            sl_params = order_params.copy()
            sl_params['type'] = 'STOP_MARKET'
            sl_params['stopPrice'] = round_step_size(stop_loss, tick_size)
            sl_params['side'] = 'SELL' if direction == 'long' else 'BUY'
            client.futures_create_order(**sl_params)
        # 创建订单记录
        new_order = Order(
            user_id=current_user.id,
            symbol=symbol,
            order_type=order_type,
            direction=direction,
            quantity=quantity,
            price=price if order_type == 'LIMIT' else None,
            leverage=leverage,
            take_profit=take_profit if take_profit > 0 else None,
            stop_loss=stop_loss if stop_loss > 0 else None,
            order_id=order['orderId'],
            status=order['status']
        )

        # 保存订单到数据库
        db.session.add(new_order)
        db.session.commit()

        # 记录订单信息
        current_app.logger.info(f"Order placed and saved: {new_order}")

        # 重定向到主页
        return redirect(url_for('/'))  # 假设您有一个名为 'main' 的蓝图，其中包含 'index' 路由

    except BinanceAPIException as e:
        db.session.rollback()
        current_app.logger.error(f"Binance API error: {str(e)}")
        return jsonify(success=False, error=f"Binance API error: {str(e)}"), 400
    except ValueError as e:
        current_app.logger.error(f"Value error: {str(e)}")
        return jsonify(success=False, error=f"Invalid input: {str(e)}"), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify(success=False, error="An unexpected error occurred"), 500
