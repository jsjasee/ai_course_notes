import os
import sys

try:
    import requests
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing required package: {e}")
    sys.exit(1)

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER_ENDPOINT = os.getenv("ALPACA_PAPER_ENDPOINT")

missing = []
if not ALPACA_API_KEY:
    missing.append("ALPACA_API_KEY")
if not ALPACA_SECRET_KEY:
    missing.append("ALPACA_SECRET_KEY")
if not ALPACA_PAPER_ENDPOINT:
    missing.append("ALPACA_PAPER_ENDPOINT")

if missing:
    print(f"Missing required credentials: {', '.join(missing)}")
    sys.exit(1)

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    "Content-Type": "application/json"
}

DATA_BASE_URL = "https://data.alpaca.markets/v2"
TRADE_BASE_URL = ALPACA_PAPER_ENDPOINT.rstrip("/")
SYMBOL = "AAPL"

def main():
    try:
        response = requests.get(
            f"{DATA_BASE_URL}/stocks/{SYMBOL}/trades/latest",
            headers=HEADERS,
            timeout=10
        )
        response.raise_for_status()
        trade_data = response.json()
        latest_price = float(trade_data["trade"]["p"])
    except Exception as e:
        print(f"Error fetching latest trade price: {e}")
        sys.exit(1)

    print(f"Latest AAPL trade price: {latest_price}")

    decision = ""
    precondition = ""
    order_submitted = False
    order_response = ""

    if latest_price < 300:
        decision = "BUY"
        try:
            acc_resp = requests.get(
                f"{TRADE_BASE_URL}/account",
                headers=HEADERS,
                timeout=10
            )
            acc_resp.raise_for_status()
            account = acc_resp.json()
            buying_power = float(account.get("buying_power", 0))
            precondition = f"Buying power: {buying_power}"
            if buying_power >= latest_price:
                order_payload = {
                    "symbol": SYMBOL,
                    "qty": "1",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day"
                }
                order_resp = requests.post(
                    f"{TRADE_BASE_URL}/orders",
                    json=order_payload,
                    headers=HEADERS,
                    timeout=10
                )
                order_resp.raise_for_status()
                order_response = order_resp.json()
                order_submitted = True
            else:
                precondition += " (insufficient)"
                order_response = "Skipped: Insufficient buying power to purchase 1 share."
        except Exception as e:
            order_response = f"Error during buy check or order submission: {e}"

    elif latest_price > 310:
        decision = "SELL"
        try:
            pos_resp = requests.get(
                f"{TRADE_BASE_URL}/positions/{SYMBOL}",
                headers=HEADERS,
                timeout=10
            )
            if pos_resp.status_code == 404:
                precondition = "Position: 0 shares"
                order_response = "Skipped: No AAPL position to sell."
            else:
                pos_resp.raise_for_status()
                position = pos_resp.json()
                qty = float(position.get("qty", 0))
                precondition = f"Position: {qty} shares"
                if qty >= 1:
                    order_payload = {
                        "symbol": SYMBOL,
                        "qty": "1",
                        "side": "sell",
                        "type": "market",
                        "time_in_force": "day"
                    }
                    order_resp = requests.post(
                        f"{TRADE_BASE_URL}/orders",
                        json=order_payload,
                        headers=HEADERS,
                        timeout=10
                    )
                    order_resp.raise_for_status()
                    order_response = order_resp.json()
                    order_submitted = True
                else:
                    order_response = "Skipped: Less than 1 share held."
        except Exception as e:
            order_response = f"Error during sell check or order submission: {e}"

    else:
        decision = "HOLD"
        precondition = "Price between 300 and 310 inclusive"
        order_response = "No action taken."

    print(f"Decision: {decision}")
    print(f"Precondition: {precondition}")
    print(f"Order submitted: {order_submitted}")
    print(f"Order response: {order_response}")

if __name__ == "__main__":
    main()