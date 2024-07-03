from flask import Blueprint, render_template, request, session, jsonify
from auth import login_required
from models import BinanceKey, Order, FuturesSymbol
from extensions import db
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from decimal import Decimal
import math
import json
from decimal import Decimal, ROUND_DOWN
import logging
from flask import jsonify, request, current_app

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


def round_step_size(value, step_size):
    """
    将数值舍入到最接近的步长
    :param value: 要舍入的数值
    :param step_size: 步长
    :return: 舍入后的数值
    """
    precision = int(round(-math.log(step_size, 10), 0))
    return round(round(value / step_size) * step_size, precision)



def validate_order_response(order):
    if not isinstance(order, dict):
        raise ValueError(f"Invalid order response type: {type(order)}")
    if 'orderId' not in order:
        raise ValueError("Order ID not found in response")
    if 'status' not in order:
        raise ValueError("Order status not found in response")
    return order
@order_management_bp.route('/place_order/<symbol>', methods=['POST'])
@login_required
def place_order(symbol):
    logger = current_app.logger
    logger.info(f"Attempting to place order for symbol: {symbol}")

    try:
        # 获取用户的第一个 Binance API 密钥
        key = BinanceKey.query.filter_by(user_id=session['user_id']).first()
        if not key:
            logger.error("No API key found for user")
            return jsonify(success=False, error="No API key found"), 404

        # 初始化 Binance 客户端
        client = Client(key.api_key, key.secret_key)

        # 获取交易对信息
        exchange_info = client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        if not symbol_info:
            raise ValueError(f"Symbol {symbol} not found")

        # 从请求中获取参数
        leverage = int(request.form.get('leverage', 1))
        direction = request.form.get('direction', 'long')
        order_type = request.form.get('order_type', 'MARKET').upper()
        quantity = float(request.form.get('quantity', 0))
        limit_price = float(request.form.get('limit_price', 0))
        take_profit = float(request.form.get('take_profit', 0))
        stop_loss = float(request.form.get('stop_loss', 0))

        # 参数验证
        if quantity <= 0:
            raise ValueError("Invalid quantity")

        if order_type == 'LIMIT' and limit_price <= 0:
            raise ValueError("Invalid limit price")

        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
        price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', symbol_info['filters']))

        step_size = float(lot_size_filter['stepSize'])
        tick_size = float(price_filter['tickSize'])

        # 舍入数量和价格
        quantity = round_step_size(quantity, step_size)
        if order_type == 'LIMIT':
            limit_price = round_step_size(limit_price, tick_size)

        # 设置杠杆
        logger.info(f"Setting leverage to {leverage} for {symbol}")
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # 创建订单参数
        order_params = {
            'symbol': symbol,
            'side': 'BUY' if direction == 'long' else 'SELL',
            'type': order_type,
            'quantity': quantity,
        }

        if order_type == 'LIMIT':
            order_params['price'] = limit_price
            order_params['timeInForce'] = 'GTC'  # Good Till Cancel

        logger.info(f"Prepared order parameters: {order_params}")

        # 下单
        logger.info(f"Placing order with params: {order_params}")
        order = client.futures_create_order(**order_params)
        logger.info(f"Full Binance API response: {order}")

        # 验证订单响应
        order = validate_order_response(order)
        logger.info(f"Order placed successfully: {order}")

        # 设置止盈止损
        if take_profit > 0:
            tp_params = {
                'symbol': symbol,
                'side': 'SELL' if direction == 'long' else 'BUY',
                'type': 'TAKE_PROFIT_MARKET',
                'stopPrice': round_step_size(take_profit, tick_size),
                'closePosition': True
            }
            logger.info(f"Setting take profit: {tp_params}")
            client.futures_create_order(**tp_params)

        if stop_loss > 0:
            sl_params = {
                'symbol': symbol,
                'side': 'SELL' if direction == 'long' else 'BUY',
                'type': 'STOP_MARKET',
                'stopPrice': round_step_size(stop_loss, tick_size),
                'closePosition': True
            }
            logger.info(f"Setting stop loss: {sl_params}")
            client.futures_create_order(**sl_params)

        # 创建订单记录  
        new_order = Order(
            user_id=session['user_id'],
            symbol=symbol,
            order_type=order_type, 
            direction=direction,
            quantity=quantity,
            price=limit_price if order_type == 'LIMIT' else float(order['avgPrice']),
            leverage=leverage,
            take_profit=take_profit if take_profit > 0 else None,
            stop_loss=stop_loss if stop_loss > 0 else None,
            order_id=str(order['orderId']),
            status=order.get('status', 'UNKNOWN')
        )

        # 保存订单到数据库
        try:    
            db.session.add(new_order)
            db.session.commit()
            logger.info(f"Order saved to database: {new_order}")
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            db.session.rollback()  
            raise ValueError("Failed to save order to database")

        return jsonify(success=True, message="Order placed successfully", order_id=order['orderId'])

    except BinanceAPIException as e:
        logger.error(f"Binance API error in place_order: {str(e)}")
        return jsonify(success=False, error=f"Binance API error: {str(e)}"), 400

    except (ValueError, KeyError) as e:
        logger.error(f"Value error in place_order: {str(e)}")
        return jsonify(success=False, error=str(e)), 400
    
    except Exception as e:
        logger.error(f"Unexpected error in place_order: {str(e)}", exc_info=True)
        return jsonify(success=False, error=f"Unexpected error: {str(e)}"), 500
