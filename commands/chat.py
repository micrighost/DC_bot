import discord
from discord.ext import commands
import requests
import json
import asyncio
import os
import sqlite3  # 💡 引入內建的 SQLite 套件
from datetime import datetime

OLLAMA_API = "http://localhost:11434/api/generate"
DB_PATH = "frog_memory.db"  # 資料庫檔案路徑

# 💡 初始化資料庫與建立資料表
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 1. 儲存長期記憶摘要的資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frog_summary (
            user_id INTEGER PRIMARY KEY,
            summary TEXT DEFAULT '我們剛剛開始認識。'
        )
    ''')
    # 2. 儲存近期對話細節的資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frog_recent_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 啟動時自動初始化資料庫
init_db()

class Chat(commands.Cog, description="具備 SQLite 摘要記憶功能的青蛙聊天"):
    def __init__(self, bot):
        self.bot = bot

    # 💡 核心優化：保留 requests，但用 to_thread 丟到背景執行緒，徹底防止機器人斷線（Heartbeat Blocked）
    async def _get_ai_response(self, prompt, timeout=120):
        def sync_post():
            try:
                response = requests.post(
                    OLLAMA_API,
                    json={"model": os.getenv("OLLAMA_MODEL"), "prompt": prompt, "stream": False},
                    timeout=timeout
                )
                if response.status_code == 200:
                    return response.json().get("response", "").strip()
                return ""
            except Exception as e:
                print(f"Ollama 連線錯誤: {e}")
                return ""
        return await asyncio.to_thread(sync_post)

    # 💡 DB 操作：獲取或初始化長期記憶摘要
    async def _db_get_summary(self, user_id):
        def fetch():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT summary FROM frog_summary WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("INSERT INTO frog_summary (user_id, summary) VALUES (?, ?)", (user_id, "我們剛剛開始認識。"))
                conn.commit()
                summary = "我們剛剛開始認識。"
            else:
                summary = row[0]
            conn.close()
            return summary
        return await asyncio.to_thread(fetch)

    # 💡 DB 操作：讀取近期對話清單
    async def _db_get_recent(self, user_id):
        def fetch():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM frog_recent_chats WHERE user_id = ? ORDER BY id ASC", (user_id,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        return await asyncio.to_thread(fetch)

    # 💡 DB 操作：寫入一筆新對話
    async def _db_save_chat(self, user_id, role, content):
        def save():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO frog_recent_chats (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, role, content, now)
            )
            conn.commit()
            conn.close()
        await asyncio.to_thread(save)

    # 💡 DB 操作：摘要完成後，更新長期記憶並清空近期對話
    async def _db_cycle_summary(self, user_id, new_summary):
        def cycle():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            # 更新摘要
            cursor.execute("UPDATE frog_summary SET summary = ? WHERE user_id = ?", (new_summary, user_id))
            # 清空近期詳細對話
            cursor.execute("DELETE FROM frog_recent_chats WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(cycle)

    async def summarize_memory(self, user_id, current_summary, recent_chats):
        """將使用者的對話紀錄進行摘要，減輕記憶體負擔"""
        recent_text = "\n".join([f"{r}: {c}" for r, c in recent_chats])
        
        prompt = (
            f"你是一個記憶整理助手。請將以下對話內容總結成一段 100 字內的繁體中文精華，"
            f"保留使用者的偏好、提到的重要資訊或特殊性格。\n"
            f"現有記憶：{current_summary}\n"
            f"新對話內容：\n{recent_text}\n"
            f"請輸出新的綜合記憶精華："
        )
        
        # 加上關鍵的 await 呼叫非同步 AI
        new_summary = await self._get_ai_response(prompt, timeout=60)
        if new_summary:
            # 💡 改為將新摘要刷進 SQLite
            await self._db_cycle_summary(user_id, new_summary)

    @commands.command(help="與青蛙聊天 (具備長短期記憶)")
    async def chat(self, ctx, *, message: str = None):
        if not message:
            await ctx.send("⚠️ 呱！請跟我說點話，例如：`!chat 你是誰？`")
            return

        user_id = ctx.author.id
        
        # 1. 從 SQLite 讀取該用戶目前的長短期記憶狀態
        current_summary = await self._db_get_summary(user_id)
        recent_chats = await self._db_get_recent(user_id)

        # 2. 檢查是否需要啟動「摘要機制」 (累積 20 句時)
        if len(recent_chats) >= 20:
            await ctx.send("⌛ *青蛙正在整理腦袋裡的記憶...*")
            await self.summarize_memory(user_id, current_summary, recent_chats)
            # 摘要更新完成後，重新從資料庫撈取最新的狀態
            current_summary = await self._db_get_summary(user_id)
            recent_chats = await self._db_get_recent(user_id)

        # 3. 組合 Prompt
        history_text = "\n".join([f"{role}: {content}" for role, content in recent_chats])
        prompt = (
            f"系統設定：你是一隻住在台灣、語音幽默且友善的青蛙，請用『繁體中文』回答。\n"
            f"長期記憶：{current_summary}\n"
            f"{history_text}\n"
            f"使用者: {message}\n"
            f"青蛙助理:"
        )

        # 4. 呼叫 AI (顯示正在輸入中)
        async with ctx.typing():
            reply = await self._get_ai_response(prompt, timeout=120)

        if reply:
            # 5. 更新對話紀錄到 SQLite 資料庫
            await self._db_save_chat(user_id, "使用者", message)
            await self._db_save_chat(user_id, "青蛙助理", reply)

            # 6. 分段發送訊息 (解決 2000 字限制)
            for i in range(0, len(reply), 1900):
                await ctx.send(reply[i:i+1900])
        else:
            await ctx.send("⚠️ 呱... 我好像恍神了，沒聽到你說什麼。")

    @commands.command(help="清除青蛙對你的所有記憶")
    async def resetchat(self, ctx):
        user_id = ctx.author.id
        
        # 💡 移除不必要的 if 判斷，只要下指令，就無條件對該用戶的資料進行全面清洗
        def delete_history():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM frog_summary WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM frog_recent_chats WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()

        try:
            # 丟到背景執行緒安全刪除
            await asyncio.to_thread(delete_history)
            await ctx.send("🗑️ *青蛙喝了忘情水，把你全忘光了！*")
        except Exception as e:
            print(f"清除資料庫失敗: {e}")
            await ctx.send("⚠️ 呱... 忘情水打翻了，清除失敗。")

async def setup(bot):
    await bot.add_cog(Chat(bot))
