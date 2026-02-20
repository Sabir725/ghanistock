import os
from flask import Flask, render_template, jsonify, redirect, request, session, url_for
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, template_folder='src')

# --- Application Configuration ---
# Set a static secret key for session management.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a-default-secret-key-for-development")
# Configure the session cookie for cross-site requests.
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
)


# --- Fyers API Configuration ---
CLIENT_ID = os.getenv('FYERS_CLIENT_ID')
SECRET_KEY = os.getenv('FYERS_SECRET_KEY')
# REDIRECT_URI is now generated dynamically in the routes.

# Predefined list of NSE stocks to track
STOCKS_TO_TRACK = [
    "NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:HDFCBANK-EQ", "NSE:INFY-EQ", "NSE:ICICIBANK-EQ",
    "NSE:HINDUNILVR-EQ", "NSE:SBIN-EQ", "NSE:BAJFINANCE-EQ", "NSE:BHARTIARTL-EQ",
    "NSE:KOTAKBANK-EQ", "NSE:WIPRO-EQ", "NSE:HCLTECH-EQ", "NSE:ASIANPAINT-EQ",
    "NSE:MARUTI-EQ", "NSE:AXISBANK-EQ"
]

# --- Fyers Authentication Handlers ---

@app.route("/login")
def login():
    """Redirects the user to the Fyers login page to generate an auth code."""
    # Generate the redirect URI dynamically to match the current host
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
    """Handles the callback from Fyers, generates the access token, and stores it."""
    auth_code = request.args.get('auth_code')
    if not auth_code:
        return "Authentication failed. No auth_code received.", 400
    
    # Generate the redirect URI dynamically to match the current host
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
            stocks_data.append({
                'name': details.get('short_name', 'N/A'),
                'price': details.get('lp', 0),
                'change': details.get('ch', 0),
                'percent_change': details.get('chp', 0)
            })

        gainers = sorted([s for s in stocks_data if s['change'] >= 0], key=lambda x: x['change'], reverse=True)
        losers = sorted([s for s in stocks_data if s['change'] < 0], key=lambda x: x['change'])
        
        return jsonify({
            "market_status": "Open",
            "top_gainers": gainers,
            "top_losers": losers
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/trade", methods=['POST'])
def place_trade():
    if 'access_token' not in session:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=session['access_token'], log_path=os.getcwd())
        trade_data = request.json
        
        order = {
            "symbol": f"NSE:{trade_data['symbol']}-EQ",
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)
