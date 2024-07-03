from flask import Blueprint, render_template, redirect, url_for, flash, session, request, abort,jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from models import User, BinanceKey
from extensions import db
from auth import login_required
from binance.client import Client
from binance.exceptions import BinanceAPIException
import json
binance_bp = Blueprint('binance', __name__)

class BinanceKeyForm(FlaskForm):
    api_key = StringField('API Key', validators=[DataRequired()])
    secret_key = StringField('Secret Key', validators=[DataRequired()])
    comment = StringField('备注')
    submit = SubmitField('提交')

@binance_bp.route('/binance_keys')
@login_required
def list_binance_keys():
    user = User.query.get(session['user_id'])
    binance_keys = user.binance_keys
    return render_template('list_binance_keys.html', binance_keys=binance_keys)

@binance_bp.route('/add_binance_key', methods=['GET', 'POST'])
@login_required
def add_binance_key():
    form = BinanceKeyForm()
    if form.validate_on_submit():
        binance_key = BinanceKey(api_key=form.api_key.data, secret_key=form.secret_key.data, comment=form.comment.data, user_id=session['user_id'])
        db.session.add(binance_key)
        db.session.commit()
        flash('币安密钥添加成功。')
        return redirect(url_for('binance.list_binance_keys'))
    return render_template('add_binance_key.html', form=form)

@binance_bp.route('/edit_binance_key/<int:key_id>', methods=['GET', 'POST'])
@login_required
def edit_binance_key(key_id):
    binance_key = BinanceKey.query.get_or_404(key_id)
    if binance_key.user_id != session['user_id']:
        abort(403)
    form = BinanceKeyForm(obj=binance_key)
    if form.validate_on_submit():
        binance_key.api_key = form.api_key.data
        binance_key.secret_key = form.secret_key.data
        binance_key.comment = form.comment.data
        db.session.commit()
        flash('币安密钥更新成功。')
        return redirect(url_for('binance.list_binance_keys'))
    return render_template('edit_binance_key.html', form=form)

@binance_bp.route('/delete_binance_key/<int:key_id>', methods=['POST'])
@login_required
def delete_binance_key(key_id):
    binance_key = BinanceKey.query.get_or_404(key_id)
    if binance_key.user_id != session['user_id']:
        abort(403)
    db.session.delete(binance_key)
    db.session.commit()
    flash('币安密钥删除成功。')
    return redirect(url_for('binance.list_binance_keys'))
@binance_bp.route('/test_binance_key', methods=['POST'])
@login_required
def test_binance_key():
    key_id = request.form['binance_key']
    binance_key = BinanceKey.query.get(key_id)
    
    if binance_key and binance_key.user_id == session['user_id']:
        client = Client(binance_key.api_key, binance_key.secret_key)
        try:
            balance = client.futures_account_balance()
            return jsonify(success=True, balance=balance, api_key=binance_key.api_key, comment=binance_key.comment)
        except BinanceAPIException as e:
            return jsonify(success=False, error=f"Binance API Error: {e.status_code} - {e.message}"), 400
        except Exception as e:
            return jsonify(success=False, error=f"Error: {str(e)}"), 500
    else:
        return jsonify(success=False, error="Invalid Binance key."), 400

@binance_bp.route('/get_account_balance', methods=['POST'])
@login_required
def get_account_balance():
    key_id = request.form['binance_key']
    binance_key = BinanceKey.query.get(key_id)

    if binance_key and binance_key.user_id == session['user_id']:
        client = Client(binance_key.api_key, binance_key.secret_key)
        try:
            account_info = client.futures_account()
            balances = account_info['assets']
            return jsonify(success=True, balances=balances)
        except BinanceAPIException as e:
            return jsonify(success=False, error=f"Binance API Error: {e.status_code} - {e.message}"), 400
        except Exception as e:
            return jsonify(success=False, error=f"Error: {str(e)}"), 500
    else:
        return jsonify(success=False, error="Invalid Binance key."), 400
