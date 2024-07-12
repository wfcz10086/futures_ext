import logging
from flask import Blueprint, request, render_template, session, flash, redirect, url_for
from sqlalchemy import func
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime, timedelta
from auth import login_required
from models import User, BinanceKey, FundFlow
from extensions import db
from datetime import datetime

fund_flow_bp = Blueprint('fund_flow', __name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INCOME_TYPES = ['COMMISSION', 'FUNDING_FEE', 'REALIZED_PNL', 'TRANSFER']

@fund_flow_bp.route('/fund_flow', methods=['GET', 'POST'])
@login_required
def fund_flow():
    user_id = session.get('user_id')
    if not user_id:
        logger.error("User ID not found in session")
        flash('请先登录', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        logger.error(f"User not found for ID: {user_id}")
        flash('用户不存在', 'error')
        return redirect(url_for('auth.login'))

    binance_key = BinanceKey.query.filter_by(user_id=user.id).first()
    if not binance_key:
        logger.warning(f"Binance API key not found for user: {user_id}")
        flash('未找到币安API密钥', 'error')
        return render_template('fund_flow.html', error='未找到币安API密钥')

    client = Client(binance_key.api_key, binance_key.secret_key)

    if request.method == 'POST':
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        
        try:
            # 使用 datetime.strptime 替代 fromisoformat
            start_time = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
            end_time = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)
        except ValueError:
            flash('无效的日期格式', 'error')
            return render_template('fund_flow.html', error='无效的日期格式')


        try:
            for income_type in INCOME_TYPES:
                income_history = client.futures_income_history(
                    incomeType=income_type,
                    startTime=start_time,
                    endTime=end_time
                )
                for item in income_history:
                    FundFlow.create_or_update(user.id, item)
                db.session.commit()
            
            flash('资金流水更新成功', 'success')
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {str(e)}")
            flash(f'币安API错误: {str(e)}', 'error')
        except Exception as e:
            logger.error(f"Error updating fund flow: {str(e)}")
            db.session.rollback()
            flash(f'更新资金流水时发生错误: {str(e)}', 'error')

    # 获取资金流水数据
    page = request.args.get('page', 1, type=int)
    per_page = 20
    income_type = request.args.get('income_type')

    query = FundFlow.query.filter_by(user_id=user.id)
    if income_type:
        query = query.filter_by(income_type=income_type)
    
    pagination = query.order_by(FundFlow.time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    fund_flows = pagination.items

    # 获取汇总数据
    summary_data = fund_flow_summary()

    return render_template('fund_flow.html', 
                           fund_flows=fund_flows, 
                           pagination=pagination,
                           summary_data=summary_data,
                           income_types=INCOME_TYPES)

@fund_flow_bp.route('/fund_flow/summary', methods=['GET'])
@login_required
def fund_flow_summary():
    user_id = session.get('user_id')
    if not user_id:
        return []

    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=4)  # 获取最近4周的数据

    summary = []
    current_week_start = start_date

    while current_week_start <= end_date:
        current_week_end = current_week_start + timedelta(days=6)
        if current_week_end > end_date:
            current_week_end = end_date

        week_summary = db.session.query(
            FundFlow.income_type,
            func.sum(FundFlow.income).label('total_income')
        ).filter(
            FundFlow.user_id == user_id,
            FundFlow.time >= current_week_start,
            FundFlow.time <= current_week_end
        ).group_by(FundFlow.income_type).all()

        summary.append({
            'week_start': current_week_start.isoformat(),
            'week_end': current_week_end.isoformat(),
            'data': {item.income_type: float(item.total_income) for item in week_summary}
        })

        current_week_start += timedelta(days=7)

    return summary
