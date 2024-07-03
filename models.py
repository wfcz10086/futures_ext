from extensions import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    binance_keys = db.relationship('BinanceKey', backref='user', lazy=True)

class BinanceKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(64), nullable=False)
    secret_key = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment = db.Column(db.String(100), nullable=True)

class FuturesSymbol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('futures_symbols', lazy=True))

from datetime import datetime

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    order_type = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float)
    leverage = db.Column(db.Integer, nullable=False)
    take_profit = db.Column(db.Float)
    stop_loss = db.Column(db.Float)
    order_id = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Order {self.id} {self.symbol} {self.order_type}>'
