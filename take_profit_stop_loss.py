import logging
from flask import Blueprint, render_template, request, session, flash, jsonify
from auth import login_required
from models import BinanceKey, Order, User
from extensions import db
from binance.client import Client
from binance.exceptions import BinanceAPIException

take_profit_stop_loss_bp = Blueprint('take_profit_stop_loss', __name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@take_profit_stop_loss_bp.route('/take_profit_stop_loss', methods=['GET'])
@login_required
def take_profit_stop_loss():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    user_id = session.get('user_id')
    
    if not user_id:
        logger.error("User ID not found in session")
        flash('请先登录', 'error')
        return render_template('take_profit_stop_loss.html', orders=[])
    
    user = User.query.get(user_id)
    if not user:
        logger.error(f"User not found for ID: {user_id}")
        flash('用户不存在', 'error')
        return render_template('take_profit_stop_loss.html', orders=[])
    
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        logger.warning(f"Binance API key not found for user: {user_id}")
        flash('未找到币安API密钥', 'error')
        return render_template('take_profit_stop_loss.html', orders=[])
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        all_open_orders = client.futures_get_open_orders()
        logger.info(f"Retrieved {len(all_open_orders)} open orders for user: {user_id}")
        
        tp_sl_orders = [order for order in all_open_orders if order['type'] in ['TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP']]
        
        start = (page - 1) * per_page
        end = start + per_page
        current_page_orders = tp_sl_orders[start:end]
        
        total_pages = (len(tp_sl_orders) + per_page - 1) // per_page
        
        return render_template('take_profit_stop_loss.html', 
                               orders=current_page_orders, 
                               page=page, 
                               total_pages=total_pages,
                               has_prev=(page > 1),
                               has_next=(page < total_pages))
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error for user {user_id}: {str(e)}")
        flash(f'币安API错误: {str(e)}', 'error')
        return render_template('take_profit_stop_loss.html', orders=[])
    except Exception as e:
        logger.error(f"Unexpected error for user {user_id}: {str(e)}")
        flash(f'发生错误: {str(e)}', 'error')
        return render_template('take_profit_stop_loss.html', orders=[])

@take_profit_stop_loss_bp.route('/update_tp_sl', methods=['POST'])
@login_required
def update_tp_sl():
    user_id = session.get('user_id')
    if not user_id:
        logger.error("User ID not found in session during TP/SL update")
        return jsonify({'success': False, 'message': '请先登录'})

    order_id = request.form.get('order_id')
    symbol = request.form.get('symbol')
    take_profit = request.form.get('take_profit')
    stop_loss = request.form.get('stop_loss')
    
    logger.info(f"Updating TP/SL for user {user_id}, order {order_id}, symbol {symbol}")
    
    user = User.query.get(user_id)
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        logger.warning(f"Binance API key not found for user: {user_id}")
        return jsonify({'success': False, 'message': '未找到币安API密钥'})
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        # 获取当前市场价格
        symbol_price = client.get_symbol_ticker(symbol=symbol)
        current_price = float(symbol_price['price'])

        # 获取当前持仓信息
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if float(p['positionAmt']) != 0), None)

        if not position:
            logger.warning(f"No open position found for user {user_id}, symbol {symbol}")
            return jsonify({'success': False, 'message': '没有找到开放的仓位'})

        position_side = 'BUY' if float(position['positionAmt']) > 0 else 'SELL'

        # 检查止盈止损价格是否有效
        if position_side == 'BUY':
            if take_profit and float(take_profit) <= current_price:
                return jsonify({'success': False, 'message': '止盈价格必须高于当前市场价格'})
            if stop_loss and float(stop_loss) >= current_price:
                return jsonify({'success': False, 'message': '止损价格必须低于当前市场价格'})
        elif position_side == 'SELL':
            if take_profit and float(take_profit) >= current_price:
                return jsonify({'success': False, 'message': '止盈价格必须低于当前市场价格'})
            if stop_loss and float(stop_loss) <= current_price:
                return jsonify({'success': False, 'message': '止损价格必须高于当前市场价格'})

        # 取消现有的止盈止损订单
        open_orders = client.futures_get_open_orders(symbol=symbol)
        for open_order in open_orders:
            if open_order['type'] in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                client.futures_cancel_order(symbol=symbol, orderId=open_order['orderId'])

        # 创建新的止盈订单
        if take_profit:
            client.futures_create_order(
                symbol=symbol,
                type='TAKE_PROFIT_MARKET',
                side='SELL' if position_side == 'BUY' else 'BUY',
                stopPrice=take_profit,
                closePosition=True
            )
        
        # 创建新的止损订单
        if stop_loss:
            client.futures_create_order(
                symbol=symbol,
                type='STOP_MARKET',
                side='SELL' if position_side == 'BUY' else 'BUY',
                stopPrice=stop_loss,
                closePosition=True
            )
        
        logger.info(f"Successfully updated TP/SL for user {user_id}, order {order_id}, symbol {symbol}")
        return jsonify({'success': True, 'message': '止盈止损更新成功'})
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error during TP/SL update for user {user_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'币安API错误: {str(e)}'})
    except Exception as e:
        logger.error(f"Unexpected error during TP/SL update for user {user_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

@take_profit_stop_loss_bp.route('/cancel_order', methods=['POST'])

@take_profit_stop_loss_bp.route('/cancel_order', methods=['POST'])
@login_required
def cancel_order():
    order_id = request.form.get('order_id')
    symbol = request.form.get('symbol')
    
    user = User.query.get(session['user_id'])
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        return jsonify({'success': False, 'message': '未找到币安API密钥'})
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        result = client.futures_cancel_order(symbol=symbol, orderId=order_id)
        return jsonify({'success': True, 'message': '订单已成功取消'})
    except BinanceAPIException as e:
        return jsonify({'success': False, 'message': f'币安API错误: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'取消失败: {str(e)}'})
