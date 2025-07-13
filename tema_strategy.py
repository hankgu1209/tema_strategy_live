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
LEVERAGE     = float(os.environ.get('LEVERAGE', 2))
POLL_SECONDS = int(os.environ.get('POLL_SECONDS', 3600))
MODE         = os.environ.get('MODE', 'paper')  # paper 或 live


client = Client(API_KEY, API_SECRET)

def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """拉取 limit 根指定 interval 的合约 K 线"""
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
    """三重指数移动平均"""
    ema1 = series.ewm(span=n, adjust=False).mean()
    ema2 = ema1.ewm(span=n, adjust=False).mean()
    ema3 = ema2.ewm(span=n, adjust=False).mean()
    return 3*(ema1 - ema2) + ema3


def signal_generator():
    # —— 拉 1h 和 4h 数据
    df1 = fetch_klines(SYMBOL, INTERVAL_1H, limit=LOOKBACK*3)
    df4 = fetch_klines(SYMBOL, INTERVAL_4H, limit=LOOKBACK*3)

    # —— 计算 1h 指标
    df1['tema10_1h'] = compute_tema(df1['close'], 10)
    df1['tema80_1h'] = compute_tema(df1['close'], 80)
    df1['atr']       = df1.ta.atr(length=14)
    adx1 = df1.ta.adx(length=14)[f'ADX_{14}']
    df1['adx']       = adx1
    df1['cmo']       = df1.ta.cmo(length=14)

    latest1 = df1.iloc[-1]
    st_1h = 1 if latest1['tema10_1h'] > latest1['tema80_1h'] else -1

    # —— 计算 4h 指标
    df4['tema20_4h'] = compute_tema(df4['close'], 20)
    df4['tema70_4h'] = compute_tema(df4['close'], 70)
    latest4 = df4.iloc[-1]
    st_4h = 1 if latest4['tema20_4h'] > latest4['tema70_4h'] else -1

    # —— 汇总信号条件
    adx = latest1['adx']
    cmo = latest1['cmo']
    price = latest1['close']
    atr   = latest1['atr']

    # 只有当 1h 和 4h 同向 && ADX/CMO 符合才交易
    if st_1h == 1 and st_4h == 1 and adx > 40 and cmo > 40:
        return 'LONG', price, atr
    if st_1h == -1 and st_4h == -1 and adx > 40 and cmo < -40:
        return 'SHORT', price, atr

    return None, None, None


def place_order(signal: str, price: float, atr: float):
    size = LEVERAGE
    if signal == 'LONG':
        qty = size
        order = client.futures_create_order(
            symbol=SYMBOL, side='BUY', type='LIMIT', timeInForce='GTC',
            quantity=qty, price=round(price-atr, 2)
        )
    else:
        qty = size
        order = client.futures_create_order(
            symbol=SYMBOL, side='SELL', type='LIMIT', timeInForce='GTC',
            quantity=qty, price=round(price+atr, 2)
        )
    print(datetime.utcnow(), signal, order)


def main_loop():
    print("Starting live bot in", MODE, "mode.")
    while True:
        try:
            sig, price, atr = signal_generator()
            if sig:
                place_order(sig, price, atr)
        except Exception as e:
            print("Error:", e)
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main_loop()
