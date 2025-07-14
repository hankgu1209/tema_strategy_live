import os
import time
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import requests
import pandas_ta as ta
from binance.client import Client

load_dotenv()  # 从 .env 读取环境变量

# —— 配置 ——
API_KEY      = os.environ['BINANCE_API_KEY']
API_SECRET   = os.environ['BINANCE_API_SECRET']
SYMBOL       = os.environ.get('SYMBOL', 'BTCUSDT')
INTERVAL_1H  = '1h'
INTERVAL_4H  = '4h'
LOOKBACK     = int(os.environ.get('CHANNEL_PERIOD', 20))
TP_RATIO     = float(os.environ.get('TP_RATIO', 0.02))
SL_RATIO     = float(os.environ.get('SL_RATIO', 0.01))
FEE_RATE     = float(os.environ.get('FEE_RATE', 0.0004))
LEVERAGE     = float(os.environ.get('LEVERAGE', 0.02))    # 建议 1-5 之间
POLL_SECONDS = int(os.environ.get('POLL_SECONDS', 3600))
MODE         = os.environ.get('MODE', 'paper')         # paper 或 live

client = Client(API_KEY, API_SECRET, testnet=(MODE == 'paper'))

def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = 'https://fapi.binance.com/fapi/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','x','x','x','x','x'
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df.set_index('open_time', inplace=True)
    df[['high','low','close']] = df[['high','low','close']].astype(float)
    return df

def compute_tema(series: pd.Series, n: int) -> pd.Series:
    ema1 = series.ewm(span=n, adjust=False).mean()
    ema2 = ema1.ewm(span=n, adjust=False).mean()
    ema3 = ema2.ewm(span=n, adjust=False).mean()
    return 3*(ema1 - ema2) + ema3

def signal_generator():
    df1 = fetch_klines(SYMBOL, INTERVAL_1H, LOOKBACK*3)
    df4 = fetch_klines(SYMBOL, INTERVAL_4H, LOOKBACK*3)

    # 1h 指标
    df1['tema10'] = compute_tema(df1['close'], 10)
    df1['tema80'] = compute_tema(df1['close'], 80)
    df1['atr']   = df1.ta.atr(length=14)
    df1['adx']   = df1.ta.adx(length=14)[f"ADX_{14}"]
    df1['cmo']   = df1.ta.cmo(length=14)
    last1 = df1.iloc[-1]
    st1 = 1 if last1['tema10'] > last1['tema80'] else -1

    # 4h 指标
    df4['tema20'] = compute_tema(df4['close'], 20)
    df4['tema70'] = compute_tema(df4['close'], 70)
    last4 = df4.iloc[-1]
    st4 = 1 if last4['tema20'] > last4['tema70'] else -1

    # 汇总
    if st1 == 1 and st4 == 1 and last1['adx'] > 40 and last1['cmo'] > 40:
        return 'LONG', last1['close'], last1['atr']
    if st1 == -1 and st4 == -1 and last1['adx'] > 40 and last1['cmo'] < -40:
        return 'SHORT', last1['close'], last1['atr']
    return None, None, None

def place_order(signal: str, price: float, atr: float):
    qty = LEVERAGE
    # 先市价或限价开仓
    if signal == 'LONG':
        resp = client.futures_create_order(
            symbol=SYMBOL,
            side='BUY',
            type='MARKET',
            quantity=qty
        )
    else:
        resp = client.futures_create_order(
            symbol=SYMBOL,
            side='SELL',
            type='MARKET',
            quantity=qty
        )
    entry_price = float(resp['avgFillPrice'])
    print(datetime.utcnow(), f"{signal} opened @ {entry_price}")

    # 计算止盈/止损价
    if signal == 'LONG':
        tp_price = round(entry_price * (1 + TP_RATIO), 2)
        sl_price = round(entry_price * (1 - SL_RATIO),  2)
        # 止盈市价单
        client.futures_create_order(
            symbol=SYMBOL,
            side='SELL',
            type='TAKE_PROFIT_MARKET',
            stopPrice=tp_price,
            closePosition=True,
            workingType='CONTRACT_PRICE'
        )
        # 止损市价单
        client.futures_create_order(
            symbol=SYMBOL,
            side='SELL',
            type='STOP_MARKET',
            stopPrice=sl_price,
            closePosition=True,
            workingType='CONTRACT_PRICE'
        )
    else:
        tp_price = round(entry_price * (1 - TP_RATIO), 2)
        sl_price = round(entry_price * (1 + SL_RATIO),  2)
        client.futures_create_order(
            symbol=SYMBOL,
            side='BUY',
            type='TAKE_PROFIT_MARKET',
            stopPrice=tp_price,
            closePosition=True,
            workingType='CONTRACT_PRICE'
        )
        client.futures_create_order(
            symbol=SYMBOL,
            side='BUY',
            type='STOP_MARKET',
            stopPrice=sl_price,
            closePosition=True,
            workingType='CONTRACT_PRICE'
        )
    print(f"  → TP @ {tp_price}, SL @ {sl_price}")

print("🔔 Starting live bot in", MODE, "mode.", flush=True)
def main_loop():
    print("🏁 Entering main loop", flush=True)
    while True:
        try:
            sig, price, atr = signal_generator()
            if sig:
                print(f"⏱ Signal: {sig} @ {price}", flush=True)
                place_order(sig, price, atr)
        except Exception as e:
            print("❌ Error:", e, flush=True)
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    main_loop()
