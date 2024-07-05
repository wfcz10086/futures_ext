from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app, jsonify
from auth import login_required
from models import BinanceKey
from extensions import db
from binance.client import Client
from binance.exceptions import BinanceAPIException
import math

pending_order_bp = Blueprint('pending_order', __name__)

def get_binance_client():
    key = BinanceKey.query.filter_by(user_id=session['user_id']).first()
    if not key:
        flash("未找到API密钥", "error")
        return None
    return Client(key.api_key, key.secret_key)

@pending_order_bp.route('/pending_orders')
@login_required
def pending_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    client = get_binance_client()
    if not client:
        return redirect(url_for('index'))

    try:
        open_orders = client.futures_get_open_orders()
        
        # 只保留限价单
        limit_orders = [order for order in open_orders if order['type'] == 'LIMIT']
        
        for order in limit_orders:
            order['origQty'] = float(order['origQty'])
            order['price'] = float(order['price'])

        total_orders = len(limit_orders)
        total_pages = math.ceil(total_orders / per_page)
        start = (page - 1) * per_page
        end = start + per_page
        
        paginated_orders = limit_orders[start:end]

        return render_template('pending_orders.html', 
                               orders=paginated_orders, 
                               page=page, 
                               total_pages=total_pages)
    except BinanceAPIException as e:
        current_app.logger.error(f"币安API错误: {str(e)}")
        flash(f"获取订单时出错: {str(e)}", "error")
    except Exception as e:
        current_app.logger.error(f"意外错误: {str(e)}", exc_info=True)
        flash("发生意外错误", "error")

    return redirect(url_for('index'))

@pending_order_bp.route('/update_order', methods=['POST'])
@login_required
def update_order():
    symbol = request.form.get('symbol')
    order_id = request.form.get('order_id')
    new_price = request.form.get('new_price')
    new_quantity = request.form.get('new_quantity')

    client = get_binance_client()
    if not client:
        return jsonify({"success": False, "error": "未找到API密钥"}), 400

    try:
        # 获取交易对信息
        exchange_info = client.futures_exchange_info()
        symbol_info = next(filter(lambda x: x['symbol'] == symbol, exchange_info['symbols']))
        price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', symbol_info['filters']))
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))

        min_price = float(price_filter['minPrice'])
        min_qty = float(lot_size_filter['minQty'])

        # 获取原订单信息
        original_order = client.futures_get_order(symbol=symbol, orderId=order_id)
        original_quantity = float(original_order['origQty'])

        # 验证新价格
        if new_price is None or new_price == '':
            new_price = float(original_order['price'])
        else:
            try:
                new_price = float(new_price)
                if new_price < min_price:
                    return jsonify({"success": False, "error": f"价格必须至少为 {min_price}"}), 400
            except ValueError:
                return jsonify({"success": False, "error": "无效的价格值"}), 400

        # 验证新数量
        if new_quantity is None or new_quantity == '':
            new_quantity = original_quantity
        else:
            try:
                new_quantity = float(new_quantity)
                if new_quantity > original_quantity:
                    return jsonify({"success": False, "error": "新数量不能超过原订单数量"}), 400
                if new_quantity < min_qty:
                    return jsonify({"success": False, "error": f"数量必须至少为 {min_qty}"}), 400
            except ValueError:
                return jsonify({"success": False, "error": "无效的数量值"}), 400

        # 取消原订单
        client.futures_cancel_order(symbol=symbol, orderId=order_id)

        # 创建新订单
        new_order = client.futures_create_order(
            symbol=symbol,
            side=original_order['side'],
            type='LIMIT',
            timeInForce='GTC',
            price=new_price,
            quantity=new_quantity
        )

        return jsonify({"success": True, "message": "订单更新成功"})
    except BinanceAPIException as e:
        current_app.logger.error(f"更新订单时币安API错误: {str(e)}")
        return jsonify({"success": False, "error": f"更新订单时出错: {str(e)}"}), 400
    except Exception as e:
        current_app.logger.error(f"更新订单时意外错误: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "更新订单时发生意外错误"}), 500

@pending_order_bp.route('/cancel_order', methods=['POST'])
@login_required
def cancel_order():
    symbol = request.form.get('symbol')
    order_id = request.form.get('order_id')

    client = get_binance_client()
    if not client:
        return redirect(url_for('pending_order.pending_orders'))

    try:
        client.futures_cancel_order(symbol=symbol, orderId=order_id)
        flash("订单取消成功", "success")
    except BinanceAPIException as e:
        current_app.logger.error(f"取消订单时币安API错误: {str(e)}")
        flash(f"取消订单时出错: {str(e)}", "error")
    except Exception as e:
        current_app.logger.error(f"取消订单时意外错误: {str(e)}", exc_info=True)
        flash("取消订单时发生意外错误", "error")

    return redirect(url_for('pending_order.pending_orders'))
