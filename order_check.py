from flask import Blueprint, request, jsonify, session
from models import BinanceKey
from binance.client import Client
from auth import login_required
import logging

order_check_bp = Blueprint('order_check', __name__)
logger = logging.getLogger(__name__)

@order_check_bp.route('/get_symbol_prices', methods=['POST'])
@login_required
def get_symbol_prices():
    symbol = request.form.get('symbol')
    key_id = request.form.get('key_id')
    binance_key = BinanceKey.query.get(key_id)
    client = get_client(binance_key.api_key, binance_key.secret_key)

    try:
        total_balance, usdt_balance = get_account_info(client)
        symbol_info = get_symbol_info(client, symbol)
        current_price, prices, price_changes = get_prices(client, symbol)

        leverage_options = [1, 2, 3, 4, 5]
        contract_size = float(symbol_info['contractSize'])
        max_quantities = {leverage: get_max_quantity(usdt_balance, leverage, current_price, contract_size) for leverage in leverage_options}
        liquidation_prices = get_liquidation_prices(current_price, leverage_options)

        total_contract_value = {leverage: round(max_quantities[leverage] * contract_size, 2) for leverage in leverage_options}
        max_contracts = {leverage: max_quantities[leverage] for leverage in leverage_options}

        return jsonify(success=True, prices=prices, price_changes=price_changes,
                       leverage_options=leverage_options, max_quantities=max_quantities,
                       liquidation_prices=liquidation_prices, total_balance=total_balance,
                       contract_size=contract_size, total_contract_value=total_contract_value,
                       max_contracts=max_contracts, current_price=current_price)
    except ValueError as ve:
        logger.error(f"ValueError: {ve}")
        return jsonify(success=False, error=str(ve))
    except Exception as e:
        logger.error(f"Exception: {e}")
        return jsonify(success=False, error="An error occurred while fetching symbol prices")

def get_client(api_key, secret_key):
    return Client(api_key, secret_key)

def get_account_info(client):
    account_info = client.futures_account()
    total_balance = float(account_info['totalWalletBalance'])
    usdt_balance = float(account_info['assets'][6]['walletBalance'])
    return total_balance, usdt_balance

def get_symbol_info(client, symbol):
    exchange_info = client.futures_exchange_info()
    symbol_info = next(filter(lambda x: x['symbol'] == symbol, exchange_info['symbols']))
    return symbol_info

def get_prices(client, symbol):
    klines = client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=49)
    prices = {
        'current': float(klines[-1][4]),
        '2h': float(klines[-3][4]),
        '4h': float(klines[-5][4]),
        '12h': float(klines[-13][4]),
        '48h': float(klines[-49][4])
    }
    price_changes = {
        '2h': round((prices['current'] - prices['2h']) / prices['2h'] * 100, 2),
        '4h': round((prices['current'] - prices['4h']) / prices['4h'] * 100, 2),
        '12h': round((prices['current'] - prices['12h']) / prices['12h'] * 100, 2),
        '48h': round((prices['current'] - prices['48h']) / prices['48h'] * 100, 2)
    }
    return prices['current'], prices, price_changes

def get_max_quantity(usdt_balance, leverage, current_price, contract_size):
    max_cost = usdt_balance * leverage
    return int(max_cost / (current_price * contract_size))

def get_liquidation_prices(current_price, leverage_options):
    liquidation_prices = {}
    for leverage in leverage_options:
        liquidation_prices[leverage] = {
            'long': current_price * (1 - 1/leverage),
            'short': current_price * (1 + 1/leverage)
        }
    return liquidation_prices
