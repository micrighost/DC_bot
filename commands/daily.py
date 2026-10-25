import discord
from discord.ext import commands
import requests
import pandas as pd
import datetime
import os
# 💡 導入 FinMind 官方套件
from FinMind.data import DataLoader

OLLAMA_API = "http://localhost:11434/api/generate"
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")

class Daily(commands.Cog, description="綜合籌碼與技術面分析指令"):
    def __init__(self, bot):
        self.bot = bot
        # 💡 初始化 FinMind 官方的 DataLoader
        self.dl = DataLoader()
        if FINMIND_TOKEN:
            self.dl.login(token=FINMIND_TOKEN)

    def _calculate_indicators(self, df_price):
        """利用 pandas 計算價格技術指標"""
        df = df_price.sort_values("date").reset_index(drop=True)
        latest_data = {
            'Date': df['date'].iloc[-1],
            'Close': float(df["close"].iloc[-1]),
            'Volume': int(df["Trading_Volume"].iloc[-1])
        }
        
        # 移動平均線 (SMA)
        df['SMA20'] = df["close"].rolling(window=20).mean()
        df['SMA60'] = df["close"].rolling(window=60).mean()
        latest_data['SMA20'] = float(df['SMA20'].iloc[-1])
        latest_data['SMA60'] = float(df['SMA60'].iloc[-1])
        
        # RSI14
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        latest_data['RSI14'] = float(100 - (100 / (1 + rs)).iloc[-1])
        
        # 布林通道
        std20 = df["close"].rolling(window=20).std()
        latest_data['BB_middle'] = latest_data['SMA20']
        latest_data['BB_upper'] = float(latest_data['BB_middle'] + (2 * std20.iloc[-1]))
        latest_data['BB_lower'] = float(latest_data['BB_middle'] - (2 * std20.iloc[-1]))
        
        return latest_data

    @commands.command(name="daily", help="綜合籌碼與技術面分析。用法: !daily <股票代號>")
    async def daily(self, ctx, stock_id: str = "2330"):
        # 修正先前字串切割的 bug
        stock_id_clean = stock_id.split(".")[0].strip()
        await ctx.send(f"🔍 正在透過 FinMind 官方套件下載並分析 {stock_id_clean} 的外資 MA 交叉與技術數據...")

        # 設定時間區間
        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")

        try:
            async with ctx.typing():
                # 1. 💡 使用 FinMind 官方套件功能抓取三大資料
                # 抓取日K線價格
                df_price = self.dl.taiwan_stock_daily(stock_id=stock_id_clean, start_date=start_date, end_date=end_date)
                # 抓取三大法人買賣超
                df_inst = self.dl.taiwan_stock_institutional_investors(stock_id=stock_id_clean, start_date=start_date, end_date=end_date)
                # 抓取融資融券
                df_margin = self.dl.taiwan_stock_margin_purchase_short_sale(stock_id=stock_id_clean, start_date=start_date, end_date=end_date)

                if df_price is None or df_price.empty:
                    await ctx.send(f"❌ 無法獲取 {stock_id_clean} 的股價資料，請確認代號是否正確。")
                    return

                # 2. 計算價格技術指標
                tech = self._calculate_indicators(df_price)

                # 3. 💡 完美融合你提供的 21 日外資籌碼 5MA/20MA 驗算邏輯
                chip_log_str = "⚠️ 暫無足夠的外資籌碼數據。"
                if df_inst is not None and not df_inst.empty:
                    df_foreign = df_inst[df_inst['name'] == 'Foreign_Investor'].copy()
                    if not df_foreign.empty:
                        df_foreign = df_foreign.sort_values('date').reset_index(drop=True)
                        df_foreign['f_net'] = pd.to_numeric(df_foreign['buy']) - pd.to_numeric(df_foreign['sell'])
                        
                        # 計算外資買賣超均線
                        df_foreign['inst_fastma'] = df_foreign['f_net'].rolling(5).mean()
                        df_foreign['inst_slowma'] = df_foreign['f_net'].rolling(20).mean()
                        
                        df_foreign.dropna(subset=['inst_fastma', 'inst_slowma'], inplace=True)
                        
                        if len(df_foreign) >= 21:
                            last_21_days = df_foreign.tail(21)
                            history_lines = []
                            for _, row in last_21_days.iterrows():
                                # 格式化日期格式
                                date_str = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
                                is_latest = " (最新)" if row['date'] == last_21_days['date'].iloc[-1] else ""
                                history_lines.append(f" 📅 【{date_str}】外資買賣超: {int(row['f_net']):+,} 股{is_latest}")
                            
                            latest_data = last_21_days.iloc[-1]
                            fast_today = latest_data['inst_fastma']
                            slow_today = latest_data['inst_slowma']
                            
                            chip_log_str = "\n".join(history_lines)
                            chip_log_str += f"\n --------------------------------------------------\n"
                            chip_log_str += f" 🔥 最新外資籌碼 5MA: {fast_today:,.2f} | 20MA: {slow_today:,.2f}"

                # 4. 處理資券餘額 (使用官方欄位名稱)
                margin_summary = "⚠️ 暫無融資融券數據。"
                if df_margin is not None and not df_margin.empty:
                    latest_margin = df_margin.sort_values('date').iloc[-1]
                    margin_summary = (
                        f"【信用交易 - 日期 {latest_margin['date']}】\n"
                        f" 🔹 融資買進: {latest_margin['MarginPurchaseBuy']:,} 股 / 餘額: {latest_margin['MarginPurchaseLimit']:,} 股\n"
                        f" 🔹 融券賣出: {latest_margin['ShortSaleBuy']:,} 股 / 餘額: {latest_margin['ShortSaleLimit']:,} 股"
                    )

                # 5. 構建升級後的 AI Prompt
                prompt = (
                    f"你是一位精通台灣股市的專業量化分析師，請針對以下最新技術面與【外資多空均線交叉】進行『實戰解讀』。\n"
                    f"規則：\n"
                    f"1. 必須完全使用『台灣繁體中文』回答。\n"
                    f"2. 著重分析外資買賣超 5MA 與 20MA 的相對位置（黃金交叉代表主力持續吸籌，死亡交叉代表主力出貨、扣抵壓力大）。\n"
                    f"3. 結合散戶資券動向，判斷短期是『散戶接外資刀』還是『散戶軋空、主力抬轎』。\n"
                    f"4. 給出明確的壓力、支撐位與操盤建議，限制 1000 字內。\n\n"
                    f"數據如下：\n"
                    f"股票代號: {stock_id_clean}\n"
                    f"資料日期: {tech['Date']}\n"
                    f"當前收盤價: {tech['Close']:.2f}\n"
                    f"今日成交量: {tech['Volume']:,} 股\n\n"
                    f"【技術指標】\n"
                    f" - 移動平均線: SMA20={tech['SMA20']:.2f}, SMA60={tech['SMA60']:.2f}\n"
                    f" - 相對強弱指標: RSI14={tech['RSI14']:.2f}\n"
                    f" - 布林通道: 上軌={tech['BB_upper']:.2f}, 中軌={tech['BB_middle']:.2f}, 下軌={tech['BB_lower']:.2f}\n\n"
                    f"【外資 21日籌碼明細與 MA 驗算】\n"
                    f"{chip_log_str}\n\n"
                    f"{margin_summary}"
                )

                # 6. 呼叫 Ollama 模型
                response = requests.post(
                    OLLAMA_API,
                    json={
                        "model": os.getenv("OLLAMA_MODEL"),
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=180
                )
                
                if response.status_code == 200:
                    model_reply = response.json().get("response", "")
                else:
                    await ctx.send(f"⚠️ AI 伺服器回傳錯誤代碼: {response.status_code}")
                    return

            # 7. 輸出（分段發送防止爆字數）
            if model_reply.strip():
                full_msg = f"🧑‍💻 **個股 {stock_id_clean} 官方套件實戰籌碼均線 X 技術面綜合解讀**：\n{model_reply}"
                for i in range(0, len(full_msg), 1900):
                    await ctx.send(full_msg[i:i+1900])
            else:
                await ctx.send("⚠️ 模型未回傳分析結果。")

        except Exception as e:
            await ctx.send(f"❌ 綜合分析失敗：{e}")

async def setup(bot):
    await bot.add_cog(Daily(bot))
