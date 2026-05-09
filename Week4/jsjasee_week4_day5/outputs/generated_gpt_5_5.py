import os
import sys
import json
from decimal import Decimal, InvalidOperation

import requests


SYMBOL = "AAPL"
EXPECTED_PAPER_ENDPOINT = "https://paper-api.alpaca.markets/v2"
DATA_ENDPOINT = "https://data.alpaca.markets/v2"
TIMEOUT_SECONDS = 20


def load_env_file(path=".env"):
    try:
        from dotenv import load_dotenv
        load_dotenv(path)
        return
    except ImportError:
        pass

    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as e:
        print(f"Could not read .env file: {e}")


def alpaca_headers(api_key, secret_key):
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def print_json(label, data):
    try:
        print(f"{label}: {json.dumps(data, indent=2, sort_keys=True)}")
    except TypeError:
        print(f"{label}: {data}")


def api_request(method, url, headers, **kwargs):
    try:
        response = requests.request(method, url, headers=headers, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.RequestException as e:
        return None, f"Request failed: {e}"

    try:
        body = response.json()
    except ValueError:
        body = response.text

    if not response.ok:
        return None, f"HTTP {response.status_code}: {body}"

    return body, None


def parse_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def get_latest_trade_price(headers):
    url = f"{DATA_ENDPOINT}/stocks/{SYMBOL}/trades/latest"
    body, error = api_request("GET", url, headers)
    if error:
        return None, None, error

    trade = body.get("trade") if isinstance(body, dict) else None
    price = trade.get("p") if isinstance(trade, dict) else None
    parsed_price = parse_decimal(price)

    if parsed_price is None:
        return None, body, "Latest trade response did not contain a valid trade price."

    return parsed_price, body, None


def get_account_buying_power(paper_endpoint, headers):
    url = f"{paper_endpoint}/account"
    body, error = api_request("GET", url, headers)
    if error:
        return None, body, error

    buying_power = parse_decimal(body.get("buying_power") if isinstance(body, dict) else None)
    if buying_power is None:
        return None, body, "Account response did not contain valid buying_power."

    return buying_power, body, None


def get_aapl_position_qty(paper_endpoint, headers):
    url = f"{paper_endpoint}/positions/{SYMBOL}"

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        return None, None, f"Request failed: {e}"

    try:
        body = response.json()
    except ValueError:
        body = response.text

    if response.status_code == 404:
        return Decimal("0"), body, None

    if not response.ok:
        return None, body, f"HTTP {response.status_code}: {body}"

    qty = parse_decimal(body.get("qty") if isinstance(body, dict) else None)
    if qty is None:
        return None, body, "Position response did not contain valid qty."

    return qty, body, None


def submit_order(paper_endpoint, headers, side):
    url = f"{paper_endpoint}/orders"
    payload = {
        "symbol": SYMBOL,
        "qty": "1",
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    return api_request("POST", url, headers, json=payload)


def main():
    load_env_file()

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    alpaca_api_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY")
    alpaca_paper_endpoint = os.getenv("ALPACA_PAPER_ENDPOINT")

    missing = []
    if not openrouter_api_key:
        missing.append("OPENROUTER_API_KEY")
    if not alpaca_api_key:
        missing.append("ALPACA_API_KEY")
    if not alpaca_secret_key:
        missing.append("ALPACA_SECRET_KEY")
    if not alpaca_paper_endpoint:
        missing.append("ALPACA_PAPER_ENDPOINT")

    if missing:
        print(f"Missing credentials/configuration: {', '.join(missing)}")
        print("Order submitted: no")
        return

    alpaca_paper_endpoint = alpaca_paper_endpoint.rstrip("/")

    if alpaca_paper_endpoint != EXPECTED_PAPER_ENDPOINT:
        print(f"Invalid ALPACA_PAPER_ENDPOINT: {alpaca_paper_endpoint}")
        print(f"Expected paper trading endpoint only: {EXPECTED_PAPER_ENDPOINT}")
        print("Order submitted: no")
        return

    headers = alpaca_headers(alpaca_api_key, alpaca_secret_key)

    latest_price, latest_trade_response, price_error = get_latest_trade_price(headers)
    if price_error:
        print(f"Latest {SYMBOL} trade price: unavailable")
        print(f"Decision made: skip")
        print(f"Precondition checks: failed to fetch latest trade price using latest trade endpoint: {price_error}")
        print("Order submitted: no")
        if latest_trade_response is not None:
            print_json("Latest trade response", latest_trade_response)
        return

    print(f"Latest {SYMBOL} trade price: {latest_price}")

    order_submitted = False
    order_response = None
    order_error = None

    if latest_price < Decimal("300"):
        print("Decision made: buy exactly 1 share")
        buying_power, account_response, account_error = get_account_buying_power(alpaca_paper_endpoint, headers)

        if account_error:
            print(f"Precondition checks: failed to check buying power: {account_error}")
            print("Order submitted: no")
            if account_response is not None:
                print_json("Account response", account_response)
            return

        print(f"Precondition checks: buying_power={buying_power}, required_at_least_latest_price={latest_price}")

        if buying_power >= latest_price:
            order_response, order_error = submit_order(alpaca_paper_endpoint, headers, "buy")
            if order_error:
                print("Order submitted: attempted, but failed")
                print(f"Order error message: {order_error}")
            else:
                order_submitted = True
                print("Order submitted: yes")
                print_json("Order response", order_response)
        else:
            print("Order submitted: no")
            print(f"Reason: insufficient buying power to buy 1 share of {SYMBOL}")

    elif latest_price > Decimal("310"):
        print("Decision made: sell exactly 1 share")
        qty, position_response, position_error = get_aapl_position_qty(alpaca_paper_endpoint, headers)

        if position_error:
            print(f"Precondition checks: failed to check current {SYMBOL} position: {position_error}")
            print("Order submitted: no")
            if position_response is not None:
                print_json("Position response", position_response)
            return

        print(f"Precondition checks: current_{SYMBOL}_position_qty={qty}, required_at_least=1")

        if qty >= Decimal("1"):
            order_response, order_error = submit_order(alpaca_paper_endpoint, headers, "sell")
            if order_error:
                print("Order submitted: attempted, but failed")
                print(f"Order error message: {order_error}")
            else:
                order_submitted = True
                print("Order submitted: yes")
                print_json("Order response", order_response)
        else:
            print("Order submitted: no")
            print(f"Reason: cannot sell 1 share because current {SYMBOL} position is less than 1 share; no short selling")

    else:
        print("Decision made: do nothing")
        print("Precondition checks: latest price is between 300 and 310 inclusive")
        print("Order submitted: no")
        print("Reason: no trade condition met")

    if not order_submitted and order_response is not None:
        print_json("Order response", order_response)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)