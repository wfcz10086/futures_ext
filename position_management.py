import logging
from flask import Blueprint, render_template, request, session, flash, jsonify
from auth import login_required
from models import BinanceKey, User
from extensions import db
from binance.client import Client
from binance.exceptions import BinanceAPIException

position_management_bp = Blueprint('position_management', __name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@position_management_bp.route('/position_management', methods=['GET'])
@login_required
def position_management():
    user_id = session.get('user_id')
    
    if not user_id:
        logger.error("User ID not found in session")
        flash('请先登录', 'error')
        return render_template('position_management.html', positions=[])
    
    user = User.query.get(user_id)
    if not user:
        logger.error(f"User not found for ID: {user_id}")
        flash('用户不存在', 'error')
        return render_template('position_management.html', positions=[])
    
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        logger.warning(f"Binance API key not found for user: {user_id}")
        flash('未找到币安API密钥', 'error')
        return render_template('position_management.html', positions=[])
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        # 获取所有持仓信息
        positions = client.futures_position_information()
        
        # 获取账户信息
        account_info = client.futures_account()
        
        # 获取所有挂单
        open_orders = client.futures_get_open_orders()
        
        # 处理持仓信息
        processed_positions = []
        total_position_value = 0
        total_margin = 0
        total_pnl = 0
        
        for position in positions:
            if float(position['positionAmt']) != 0:
                symbol = position['symbol']
                leverage = float(position['leverage'])
                entry_price = float(position['entryPrice'])
                mark_price = float(position['markPrice'])
                unrealized_pnl = float(position['unRealizedProfit'])
                position_amt = float(position['positionAmt'])
                
                # 计算持仓价值
                position_value = abs(position_amt * mark_price)
                total_position_value += position_value
                
                # 计算保证金
                margin = position_value / leverage
                total_margin += margin
                
                # 计算收益率
                roi_percentage = (mark_price - entry_price) / entry_price * 100
                roi = roi_percentage * leverage
                
                # 计算盈利金额
                pnl = unrealized_pnl
                total_pnl += pnl
                
                # 计算盈利百分比
                pnl_percentage = (pnl / margin) * 100 if margin != 0 else 0
                
                # 获取该交易对的挂单
                symbol_orders = [order for order in open_orders if order['symbol'] == symbol]
                
                processed_positions.append({
                    'symbol': symbol,
                    'leverage': leverage,
                    'entryPrice': entry_price,
                    'markPrice': mark_price,
                    'unrealizedPnl': unrealized_pnl,
                    'roi': roi,
                    'roiPercentage': roi_percentage,
                    'positionAmt': position_amt,
                    'positionValue': position_value,
                    'margin': margin,
                    'pnl': pnl,
                    'pnlPercentage': pnl_percentage,
                    'orders': symbol_orders
                })
        
        # 获取可用余额和锁定金额
        available_balance = float(account_info['availableBalance'])
        total_wallet_balance = float(account_info['totalWalletBalance'])
        locked_amount = total_wallet_balance - available_balance
        
        summary = {
            'totalPositionValue': total_position_value,
            'totalMargin': total_margin,
            'totalPnl': total_pnl,
            'availableBalance': available_balance,
            'lockedAmount': locked_amount
        }
        
        return render_template('position_management.html', 
                               positions=processed_positions, 
                               account_info=account_info,
                               summary=summary)
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error for user {user_id}: {str(e)}")
        flash(f'币安API错误: {str(e)}', 'error')
        return render_template('position_management.html', positions=[])
    except Exception as e:
        logger.error(f"Unexpected error for user {user_id}: {str(e)}")
        flash(f'发生错误: {str(e)}', 'error')
        return render_template('position_management.html', positions=[])
@position_management_bp.route('/close_position', methods=['POST'])
@login_required
def close_position():
    user_id = session.get('user_id')
    symbol = request.form.get('symbol')
    close_type = request.form.get('close_type')  # 'market' or 'limit'
    price = request.form.get('price')  # 仅在限价平仓时使用
    
    user = User.query.get(user_id)
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        return jsonify({'success': False, 'message': '未找到币安API密钥'})
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        position = client.futures_position_information(symbol=symbol)[0]
        amount = abs(float(position['positionAmt']))
        side = 'SELL' if float(position['positionAmt']) > 0 else 'BUY'
        
        if close_type == 'market':
            order = client.futures_create_order(
                symbol=symbol,
                type='MARKET',
                side=side,
                quantity=amount
            )
        elif close_type == 'limit':
            order = client.futures_create_order(
                symbol=symbol,
                type='LIMIT',
                side=side,
                quantity=amount,
                price=price,
                timeInForce='GTC'
            )
        
        return jsonify({'success': True, 'message': '平仓订单已提交'})
    except BinanceAPIException as e:
        return jsonify({'success': False, 'message': f'币安API错误: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'平仓失败: {str(e)}'})
@position_management_bp.route('/adjust_margin', methods=['POST'])
@login_required
def adjust_margin():
    user_id = session.get('user_id')
    symbol = request.form.get('symbol')
    amount = float(request.form.get('amount'))
    type = request.form.get('type')  # 'ADD' or 'REMOVE'
    
    user = User.query.get(user_id)
    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    
    if not binance_key:
        return jsonify({'success': False, 'message': '未找到币安API密钥'})
    
    client = Client(binance_key.api_key, binance_key.secret_key)
    
    try:
        # 首先，获取当前的保证金类型
        position_info = client.futures_position_information(symbol=symbol)[0]
        margin_type = position_info['marginType']

        # 调整保证金
        result = client.futures_change_position_margin(
            symbol=symbol,
            amount=abs(amount),
            type=1 if type == 'ADD' else 2
        )
        return jsonify({'success': True, 'message': '保证金调整成功'})
    except BinanceAPIException as e:
        return jsonify({'success': False, 'message': f'币安API错误: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保证金调整失败: {str(e)}'})
# app.register_blueprint(position_management_bp)
