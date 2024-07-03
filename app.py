from flask import Flask, render_template, session, redirect, url_for, flash
from flask_login import LoginManager

from extensions import db
login_manager = LoginManager()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://*****:*****@127.0.0.1:3306/qihuo'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

from models import User
from auth import auth_bp, login_required
from binance_module import binance_bp

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