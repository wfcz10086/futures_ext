from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from models import FundingFlow, PositionHistory, User, BinanceKey
from extensions import db
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime, timedelta
import logging
from pytz import timezone
import traceback

account_analysis_bp = Blueprint('account_analysis', __name__)
logger = logging.getLogger(__name__)

@account_analysis_bp.route('/account_analysis')
@login_required
def show_account_analysis():
    selected_type = request.args.get('income_type', 'all')
    return render_template('account_analysis.html', selected_type=selected_type)

@account_analysis_bp.route('/update_account_data', methods=['POST'])
@login_required
def update_account_data():
    logger.info(f"Starting account data update for user {current_user.id}")
    try:
        if not current_user.binance_keys:
            return jsonify({"success": False, "message": "No Binance API keys found. Please add your keys first."}), 400

        client = Client(current_user.binance_keys[0].api_key, current_user.binance_keys[0].secret_key)
        
        funding_flow_count = update_funding_flow(current_user, client)
        trade_history_count = update_trade_history(current_user, client)

        db.session.commit()
        logger.info("Database transaction committed successfully")

        return jsonify({
            "success": True, 
            "message": f"Data updated successfully. Added {funding_flow_count} funding flows and {trade_history_count} trade histories."
        })

    except BinanceAPIException as e:
        logger.error(f"Binance API error for user {current_user.id}: {str(e)}")
        return jsonify({"success": False, "message": f"Binance API error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error updating account data for user {current_user.id}: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating account data: {str(e)}"}), 500

@account_analysis_bp.route('/get_funding_flows')
@login_required
def get_funding_flows():
    try:
        income_type = request.args.get('income_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))

        query = FundingFlow.query.filter_by(user_id=current_user.id)

        if income_type and income_type.lower() != 'all':
            query = query.filter_by(incomeType=income_type)

        utc = timezone('UTC')
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=utc)
            query = query.filter(FundingFlow.time >= start_date)
        if end_date:
            end_date = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).replace(tzinfo=utc)
            query = query.filter(FundingFlow.time < end_date)

        query = query.order_by(FundingFlow.time.desc())
        pagination = query.paginate(page=page, per_page=20, error_out=False)

        items = [item.to_dict() for item in pagination.items]

        response_data = {
            'funding_flows': items,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        }

        return jsonify(response_data)

    except Exception as e:
        current_app.logger.error(f"Error in get_funding_flows: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': 'An internal error occurred'}), 500

@account_analysis_bp.route('/refresh_trades', methods=['POST'])
@login_required
def refresh_trades():
    logger.info(f"Starting trade history refresh for user {current_user.id}")
    try:
        if not current_user.binance_keys:
            return jsonify({"success": False, "message": "No Binance API keys found. Please add your keys first."}), 400

        client = Client(current_user.binance_keys[0].api_key, current_user.binance_keys[0].secret_key)
        
        new_trade_count = update_trade_history(current_user, client)

        db.session.commit()
        logger.info("Database transaction committed successfully")

        return jsonify({
            "success": True, 
            "message": f"Trade history updated successfully. Added {new_trade_count} new trades."
        })

    except BinanceAPIException as e:
        logger.error(f"Binance API error for user {current_user.id}: {str(e)}")
        return jsonify({"success": False, "message": f"Binance API error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error updating trade history for user {current_user.id}: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating trade history: {str(e)}"}), 500

@account_analysis_bp.route('/api/position_history', methods=['GET'])
@login_required
def get_position_history():
    logger.info(f"Fetching position history for user {current_user.id}")
    try:
        if not current_user.binance_keys:
            return jsonify({"success": False, "message": "No Binance API keys found. Please add your keys first."}), 400

        client = Client(current_user.binance_keys[0].api_key, current_user.binance_keys[0].secret_key)
        
        positions = client.futures_position_information()
        
        # 开始一个新的事务
        db.session.begin_nested()
        
        # 删除用户现有的持仓历史记录
        PositionHistory.query.filter_by(user_id=current_user.id).delete()
        
        new_position_count = 0
        for position in positions:
            if float(position['positionAmt']) != 0:
                try:
                    position_history = PositionHistory.from_api_response(current_user.id, position)
                    db.session.add(position_history)
                    new_position_count += 1
                except Exception as e:
                    logger.error(f"Error adding position for symbol {position['symbol']}: {str(e)}")
                    continue
        
        db.session.commit()
        logger.info(f"Position history updated successfully. Added {new_position_count} new positions.")
        
        latest_positions = PositionHistory.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            "success": True,
            "message": f"Position history updated successfully. Added {new_position_count} new positions.",
            "positions": [position.to_dict() for position in latest_positions]
        })
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error for user {current_user.id}: {str(e)}")
        return jsonify({"success": False, "message": f"Binance API error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error updating position history for user {current_user.id}: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating position history: {str(e)}"}), 500
def update_funding_flow(user, client):
    logger.info(f"Updating funding flow for user {user.id}")
    new_flow_count = 0
    income_types = ['REALIZED_PNL', 'FUNDING_FEE', 'COMMISSION', 'TRANSFER']
    
    for income_type in income_types:
        start_time = 0
        while True:
            funding_flows = client.futures_income_history(incomeType=income_type, startTime=start_time, limit=1000)
            if not funding_flows:
                break
            
            for flow in funding_flows:
                existing_flow = FundingFlow.query.filter_by(
                    user_id=user.id,
                    incomeType=flow['incomeType'],
                    symbol=flow['symbol'],
                    time=datetime.fromtimestamp(flow['time'] / 1000)
                ).first()

                if existing_flow is None:
                    new_flow = FundingFlow.from_api_response(user.id, flow)
                    db.session.add(new_flow)
                    new_flow_count += 1
            
            start_time = funding_flows[-1]['time'] + 1

    logger.info(f"Added {new_flow_count} new funding flow records for user {user.id}")
    return new_flow_count

def update_trade_history(user, client):
    logger.info(f"Updating all historical trade data for user {user.id}")
    new_trade_count = 0
    start_time = 0
    
    while True:
        try:
            trades = client.futures_account_trades(startTime=start_time, limit=1000)
            
            if not trades:
                break

            for trade in trades:
                existing_trade = TradeHistory.query.filter_by(
                    user_id=user.id,
                    symbol=trade['symbol'],
                    trade_id=int(trade['id']),
                    order_id=int(trade['orderId']),
                    time=datetime.fromtimestamp(int(trade['time']) / 1000)
                ).first()

                if existing_trade is None:
                    new_trade = TradeHistory.from_api_response(user.id, trade)
                    db.session.add(new_trade)
                    new_trade_count += 1
            
            start_time = int(trades[-1]['time']) + 1

        except Exception as e:
            logger.error(f"Error processing trades: {str(e)}")
            break

    logger.info(f"Added {new_trade_count} new trade history records for user {user.id}")
    return new_trade_count
