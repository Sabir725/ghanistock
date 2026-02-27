import os
from datetime import date, datetime # Import datetime
from flask import Flask, render_template, jsonify, redirect, request, session, url_for
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel
from flask_socketio import SocketIO
import threading

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, template_folder='src')

# --- Application Configuration ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a-default-secret-key-for-development")
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
)
socketio = SocketIO(app, async_mode='eventlet')

# --- Fyers API Configuration ---
CLIENT_ID = os.getenv('FYERS_CLIENT_ID')
SECRET_KEY = os.getenv('FYERS_SECRET_KEY')

# --- In-memory store for price history and trend analysis ---
price_history = {}
PRICE_HISTORY_LENGTH = 3  # Keep the last 3 prices to detect a trend

# --- Bot Portfolio (In-memory store) ---
bot_portfolio = {} # Global dictionary to store bot-bought stocks

# Use the Nifty 100 list for a broader market view
STOCKS_TO_TRACK = [
    # Nifty 50
    "NSE:ADANIENT-EQ", "NSE:ADANIPORTS-EQ", "NSE:APOLLOHOSP-EQ", "NSE:ASIANPAINT-EQ",
    "NSE:AXISBANK-EQ", "NSE:BAJAJ-AUTO-EQ", "NSE:BAJFINANCE-EQ", "NSE:BAJAJFINSV-EQ",
    "NSE:BPCL-EQ", "NSE:BHARTIARTL-EQ", "NSE:BRITANNIA-EQ", "NSE:CIPLA-EQ",
    "NSE:COALINDIA-EQ", "NSE:DIVISLAB-EQ", "NSE:DRREDDY-EQ", "NSE:EICHERMOT-EQ",
    "NSE:GRASIM-EQ", "NSE:HCLTECH-EQ", "NSE:HDFCBANK-EQ", "NSE:HDFCLIFE-EQ",
    "NSE:HEROMOTOCO-EQ", "NSE:HINDALCO-EQ", "NSE:HINDUNILVR-EQ", "NSE:ICICIBANK-EQ",
    "NSE:ITC-EQ", "NSE:INDUSINDBK-EQ", "NSE:INFY-EQ", "NSE:JSWSTEEL-EQ",
    "NSE:KOTAKBANK-EQ", "NSE:LTIM-EQ", "NSE:LT-EQ", "NSE:M&M-EQ", "NSE:MARUTI-EQ",
    "NSE:NTPC-EQ", "NSE:NESTLEIND-EQ", "NSE:ONGC-EQ", "NSE:POWERGRID-EQ",
    "NSE:RELIANCE-EQ", "NSE:SBILIFE-EQ", "NSE:SBIN-EQ", "NSE:SUNPHARMA-EQ",
    "NSE:TATAMOTORS-EQ", "NSE:TCS-EQ", "NSE:TATASTEEL-EQ", "NSE:TATACONSUM-EQ",
    "NSE:TECHM-EQ", "NSE:TITAN-EQ", "NSE:UPL-EQ", "NSE:ULTRACEMCO-EQ", "NSE:WIPRO-EQ",
    # Nifty Next 50
    "NSE:AMBUJACEM-EQ", "NSE:ACC-EQ", "NSE:BANKBARODA-EQ", "NSE:BERGEPAINT-EQ", "NSE:COLPAL-EQ",
    "NSE:DABUR-EQ", "NSE:DMART-EQ", "NSE:DLF-EQ", "NSE:GAIL-EQ", "NSE:GODREJCP-EQ",
    "NSE:HAVELLS-EQ", "NSE:HDFCAMC-EQ", "NSE:ICICIGI-EQ", "NSE:ICICIPRULI-EQ", "NSE:IOC-EQ",
    "NSE:INDIGO-EQ", "NSE:JINDALSTEL-EQ", "NSE:LICI-EQ", "NSE:MARICO-EQ", "NSE:MUTHOOTFIN-EQ",
    "NSE:NAUKRI-EQ", "NSE:PIDILITIND-EQ", "NSE:PGHH-EQ", "NSE:PNB-EQ", "NSE:SAIL-EQ",
    "NSE:SBICARD-EQ", "NSE:SHREECEM-EQ", "NSE:SIEMENS-EQ", "NSE:SRF-EQ", "NSE:SAMVARDHANA-EQ",
    "NSE:TATAPOWER-EQ", "NSE:TRENT-EQ", "NSE:TVSMOTOR-EQ", "NSE:UNIONBANK-EQ", "NSE:VEDL-EQ",
    "NSE:VARUNBEV-EQ", "NSE:YESBANK-EQ", "NSE:ZEEL-EQ", "NSE:ZOMATO-EQ", "NSE:BOSCHLTD-EQ",
    "NSE:CHOLAFIN-EQ", "NSE:HAL-EQ", "NSE:HINDZINC-EQ", "NSE:ADANIGREEN-EQ", "NSE:ADANIENSOL-EQ",
    "NSE:TATACOMM-EQ", "NSE:ABB-EQ"
]

# --- Background Thread for Fetching Stock Data ---
thread = None
thread_stop_event = threading.Event()

def fetch_stock_data_for_websockets():
    """
    Fetches stock data from Fyers API in a loop and emits it to WebSocket clients.
    This function is designed to run in a background thread.
    """
    while not thread_stop_event.is_set():
        if 'access_token' in session:
            try:
                fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=session['access_token'], log_path=os.getcwd())
                data = {"symbols": ",".join(STOCKS_TO_TRACK)}
                response = fyers.quotes(data=data)

                if response.get('code') == 200 and response.get('d'):
                    stocks_data = []
                    for stock in response['d']:
                        details = stock['v']
                        stock_symbol = details.get('short_name', 'N/A')
                        current_price = details.get('lp', 0)

                        # --- Trend Detection Logic for WebSockets ---
                        suggestion = "Hold"
                        trend_strength = 0.0

                        if stock_symbol not in price_history:
                            price_history[stock_symbol] = []
                        history = price_history[stock_symbol]
                        if len(history) == 0 or history[-1] != current_price:
                            history.append(current_price)

                        if len(history) > PRICE_HISTORY_LENGTH:
                            history = history[-PRICE_HISTORY_LENGTH:]
                            price_history[stock_symbol] = history

                        if len(history) == PRICE_HISTORY_LENGTH:
                            if history[0] < history[1] < history[2]:
                                price_change = history[2] - history[0]
                                if history[0] > 0:
                                    percent_change = (price_change / history[0]) * 100
                                    suggestion = f"BUY NOW - {percent_change:.2f}% upward trend"
                                    trend_strength = percent_change
                            elif history[0] > history[1] > history[2]:
                                price_change = history[0] - history[2]
                                if history[0] > 0:
                                    percent_change = (price_change / history[0]) * 100
                                    suggestion = f"SELL NOW - {percent_change:.2f}% downward trend"
                                    trend_strength = -percent_change
                        # --- End of Trend Detection Logic ---

                        stocks_data.append({
                            'name': stock_symbol,
                            'price': current_price,
                            'change': details.get('ch', 0),
                            'percent_change': details.get('chp', 0),
                            'suggestion': suggestion,
                            'trend_strength': trend_strength
                        })

                    # --- Bot Automated Selling Logic ---
                    # Create a temporary list of active bot-bought stocks to avoid modifying
                    # bot_portfolio while iterating over it.
                    active_bot_stocks = list(bot_portfolio.items())
                    for symbol, bot_stock_data in active_bot_stocks:
                        if bot_stock_data['status'] == 'active':
                            # Find current price and trend for this symbol from stocks_data
                            current_stock_info = next((s for s in stocks_data if s['name'] == symbol), None)
                            
                            if current_stock_info:
                                current_price = current_stock_info['price']
                                trend_strength = current_stock_info['trend_strength']
                                suggestion = current_stock_info['suggestion']

                                # Example sell condition: If trend is downward by 5% or more
                                # This is a placeholder, a real bot would have more sophisticated logic.
                                if "SELL NOW" in suggestion and trend_strength <= -5.0: # -5.0 for a 5% downward trend
                                    print(f"Bot selling {symbol}: Downward trend of {trend_strength:.2f}%.")
                                    # Update bot_portfolio entry to reflect the sale
                                    bot_portfolio[symbol].update({
                                        "status": "sold",
                                        "sell_price": current_price,
                                        "sell_time": datetime.now().isoformat()
                                    })
                                    # In a real scenario, you would also place a sell order via Fyers API here
                                    # Example:
                                    # order_response = fyers.place_order(data={
                                    #     "symbol": f"NSE:{symbol}-EQ",
                                    #     "qty": bot_stock_data['quantity'],
                                    #     "type": 2, # Market Order
                                    #     "side": -1, # Sell
                                    #     "productType": "INTRADAY",
                                    #     "validity": "DAY"
                                    # })
                                    # print(f"Fyers sell order response for {symbol}: {order_response}")
                    # --- End of Bot Automated Selling Logic ---


                    # Sort based on the algorithm's trend detection
                    top_buys = sorted([s for s in stocks_data if s['trend_strength'] > 0], key=lambda x: x['trend_strength'], reverse=True)
                    top_sells = sorted([s for s in stocks_data if s['trend_strength'] < 0], key=lambda x: x['trend_strength'])

                    socketio.emit('stock_update', {
                        "market_status": "Open",
                        "top_gainers": top_buys[:15],    # Emitting as top_gainers for client compatibility
                        "top_losers": top_sells[:15]     # Emitting as top_losers for client compatibility
                    })
            except Exception as e:
                print(f"Error fetching stock data for websockets: {e}")
                socketio.emit('auth_error', {'error': 'Authentication failed or token expired.'})
        
        socketio.sleep(5)  # Use socketio.sleep for cooperative multitasking

# --- Fyers Authentication Handlers ---

@app.route("/login")
def login():
    redirect_uri = url_for('callback', _external=True)
    session_model = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=redirect_uri,
        response_type='code'
    )
    return redirect(session_model.generate_authcode())

@app.route("/fyers_callback")
def callback():
    auth_code = request.args.get('auth_code')
    if not auth_code:
        return "Authentication failed. No auth_code received.", 400
    
    redirect_uri = url_for('callback', _external=True)
    session_model = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=redirect_uri,
        response_type='code',
        grant_type='authorization_code'
    )
    session_model.set_token(auth_code)
    response = session_model.generate_token()
    
    if response.get("access_token"):
        session['access_token'] = response["access_token"]
        return redirect(url_for('stocks_page'))
    else:
        return f"Failed to generate access token: {response.get('message', 'Unknown error')}", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Main Application Routes ---

@app.route("/")
def index():
    if 'access_token' in session:
        return redirect(url_for('stocks_page'))
    return render_template('login.html')

@app.route("/stocks")
def stocks_page():
    if 'access_token' not in session:
        return redirect(url_for('index'))
    return render_template('stocks.html')

@app.route("/stocks2")
def stocks2_page():
    if 'access_token' not in session:
        return redirect(url_for('index'))
    return render_template('stocks2.html')

# --- API Endpoints ---

@app.route("/api/stocks")
def api_stocks():
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=session['access_token'], log_path=os.getcwd())
        data = {"symbols": ",".join(STOCKS_TO_TRACK)}
        response = fyers.quotes(data=data)

        if response.get('code') != 200 or not response.get('d'):
            return jsonify({"error": response.get('message', "Failed to fetch quotes")}), 500

        stocks_data = []
        for stock in response['d']:
            details = stock['v']
            stock_symbol = details.get('short_name', 'N/A')
            current_price = details.get('lp', 0)

            # --- Trend Detection Logic ---
            suggestion = "Hold"
            trend_strength = 0.0

            if stock_symbol not in price_history:
                price_history[stock_symbol] = []
            history = price_history[stock_symbol]
            if len(history) == 0 or history[-1] != current_price:
                history.append(current_price)

            if len(history) > PRICE_HISTORY_LENGTH:
                history = history[-PRICE_HISTORY_LENGTH:]
                price_history[stock_symbol] = history

            if len(history) == PRICE_HISTORY_LENGTH:
                if history[0] < history[1] < history[2]:
                    price_change = history[2] - history[0]
                    if history[0] > 0:
                        percent_change = (price_change / history[0]) * 100
                        suggestion = f"BUY NOW - {percent_change:.2f}% upward trend"
                        trend_strength = percent_change
                elif history[0] > history[1] > history[2]:
                    price_change = history[0] - history[2]
                    if history[0] > 0:
                        percent_change = (price_change / history[0]) * 100
                        suggestion = f"SELL NOW - {percent_change:.2f}% downward trend"
                        trend_strength = -percent_change
            # --- End of Trend Detection Logic ---

            stocks_data.append({
                'name': stock_symbol,
                'price': current_price,
                'change': details.get('ch', 0),
                'percent_change': details.get('chp', 0),
                'suggestion': suggestion,
                'trend_strength': trend_strength
            })

        # Sort based on the algorithm's trend detection
        top_buys = sorted([s for s in stocks_data if s['trend_strength'] > 0], key=lambda x: x['trend_strength'], reverse=True)
        top_sells = sorted([s for s in stocks_data if s['trend_strength'] < 0], key=lambda x: x['trend_strength'])

        return jsonify({
            "market_status": "Open",
            "top_gainers": top_buys[:15], # Now represents top buy signals
            "top_losers": top_sells[:15]   # Now represents top sell signals
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/history/<stock_symbol>")
def api_history(stock_symbol):
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=session['access_token'], log_path=os.getcwd())
        
        today = date.today().strftime("%Y-%m-%d")
        
        # --- Robust Symbol Formatting ---
        symbol_base = stock_symbol.replace('-EQ', '')
        final_symbol = f"NSE:{symbol_base}-EQ"
        # --- End of Formatting ---

        data = {
            "symbol": final_symbol,
            "resolution": "5", # 5-minute candles
            "date_format": "1",
            "range_from": today,
            "range_to": today,
            "cont_flag": "1"
        }
        
        history_response = fyers.history(data=data)

        if history_response.get('code') == 200 and history_response.get('candles'):
            return jsonify({"success": True, "candles": history_response['candles']})
        else:
            if history_response.get('s') == 'no_data':
                 return jsonify({"success": True, "candles": []})
            return jsonify({"success": False, "message": history_response.get('message', 'Failed to fetch history')}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/trade", methods=['POST'])
def place_trade():
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=session['access_token'], log_path=os.getcwd())
        trade_data = request.json
        
        # --- Robust Symbol Formatting ---
        raw_symbol = trade_data['symbol']
        symbol_base = raw_symbol.replace('-EQ', '')
        final_symbol = f"NSE:{symbol_base}-EQ"
        # --- End of Formatting ---
        
        order = {
            "symbol": final_symbol,
            "qty": int(trade_data['quantity']),
            "type": 2,  # Market Order
            "side": 1 if trade_data['action'].lower() == 'buy' else -1,
            "productType": "INTRADAY",
            "limitPrice": 0, "stopPrice": 0, "validity": "DAY",
            "disclosedQty": 0, "offlineOrder": "False"
        }

        order_response = fyers.place_order(data=order)
        
        if order_response.get('code') == 200 and order_response.get('s') == 'ok':
             return jsonify({"success": True, "message": order_response.get('message'), "order_id": order_response.get('id')})
        else:
             return jsonify({"success": False, "message": order_response.get('message', 'Failed to place order')}), 400

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/bot_buy", methods=['POST'])
def bot_buy():
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401
    
    try:
        trade_data = request.json
        symbol = trade_data.get('symbol')
        quantity = trade_data.get('quantity')
        purchase_price = trade_data.get('purchase_price')

        if not all([symbol, quantity, purchase_price]):
            return jsonify({"success": False, "message": "Missing symbol, quantity, or purchase_price"}), 400

        # Store in bot_portfolio. If multiple buys of the same stock, sum quantities and average price.
        # For simplicity, we'll overwrite or create a new entry for the symbol for now.
        # A more robust solution would handle multiple positions or update existing ones.
        bot_portfolio[symbol] = {
            "symbol": symbol,
            "quantity": int(quantity),
            "purchase_price": float(purchase_price),
            "purchase_time": datetime.now().isoformat(), # Store as ISO format string
            "status": "active"
        }
        return jsonify({"success": True, "message": f"Bot bought {quantity} of {symbol}"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/bot_portfolio", methods=['GET'])
def get_bot_portfolio():
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401
    
    return jsonify({"success": True, "portfolio": bot_portfolio}), 200

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    global thread
    if thread is None or not thread.is_alive():
        thread_stop_event.clear()
        thread = socketio.start_background_task(target=fetch_stock_data_for_websockets)
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# --- Main Application Runner ---
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)