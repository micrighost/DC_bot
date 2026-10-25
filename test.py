"""
【直球對決實驗】直接下載 Yahoo 官方 30m 資料，不做任何相減、不取絕對值。
我們直接在後台 print 出它原生的 30分K 數據，看它的量到底是累積的還是獨立的！
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os

# 設定監控名單 (台股 + 美股)
tickers = ["2330.TW", "NVDA"] 

def run_experiment():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 啟動 30分K 官方原始數據下載...")
    print("-" * 75)

    try:
        # 🌟 直接跟 Yahoo 請求 30m 的資料 (這裡抓 5d 就夠看歷史趨勢)
        all_data = yf.download(tickers, period="5d", interval="30m", threads=True, progress=False)
        
        for symbol in tickers:
            print(f"\n📊 【{symbol}】Yahoo 伺服器回傳的 30分K 原始帳面數據：")
            print(f"  {'K線結束時間':<15} | {'開盤價':<7} | {'收盤價':<7} | {'Yahoo 原始成交量':<15}")
            print("  " + "-" * 60)
            
            # 擷取該股票的資料
            df_30m = all_data.xs(symbol, axis=1, level=1).dropna().copy()
            
            # 我們只列出最近一天的最後 8 根 30分K (約 4 小時交易時間) 來看趨勢
            test_show = df_30m.tail(8)
            
            for timestamp, row in test_show.iterrows():
                # 轉成台灣時間對照
                t_show = timestamp.strftime('%Y-%m-%d %H:%M')
                if ".TW" in symbol:
                    corrected_hour = (int(t_show[11:13]) + 8) % 24
                    t_show = f"{t_show[:11]}{corrected_hour:02d}{t_show[13:]}"
                
                print(f"  {t_show:<15} | {row['Open']:>7.2f} | {row['Close']:>7.2f} | {int(row['Volume']):>15,} 股")
            print("  " + "-" * 60)
                
    except Exception as e:
        print(f"實驗下載失敗: {e}")

if __name__ == "__main__":
    run_experiment()
