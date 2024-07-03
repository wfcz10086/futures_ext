from flask import Flask, render_template, session, redirect, url_for, flash
from flask_login import LoginManager
from extensions import db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:10086@10.0.0.5:3306/qihuo'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # 指定登录视图的端点

from models import User
from auth import auth_bp, login_required
from binance_module import binance_bp

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

app.register_blueprint(auth_bp)
app.register_blueprint(binance_bp)
from get_futures_symbols import get_futures_symbols_bp

app.register_blueprint(get_futures_symbols_bp)

from get_klines import get_klines_bp
app.register_blueprint(get_klines_bp)

from order_management import order_management_bp
app.register_blueprint(order_management_bp)
from order_check import order_check_bp
app.register_blueprint(order_check_bp)

@app.route('/')
def index():
    if 'user_id' in session:
        user_id = session['user_id']
        user = User.query.get(user_id)
        return render_template('index.html', user=user)
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)
