import discord
from discord.ext import commands
import requests
import json
import asyncio
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

AI_API_URL = os.getenv("AI_API_URL")
AI_API_KEY = os.getenv("AI_API_KEY", "any_string")
AI_MODEL = os.getenv("AI_MODEL")

DB_PATH = "frog_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frog_summary (
            user_id INTEGER PRIMARY KEY,
            summary TEXT DEFAULT '我們剛剛開始認識。'
        )
    ''')
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

init_db()

class Chat(commands.Cog, description="具備高度偵錯功能的通用聊天模組"):
    def __init__(self, bot):
        self.bot = bot

    async def _get_ai_response(self, messages):
        def sync_post():
            print("\n=== ⚙️ AI API 偵錯起點 ===")
            print(f"📡 目標網址: '{AI_API_URL}'")
            print(f"🏷️ 請求型號: '{AI_MODEL}'")
            print(f"🔑 金鑰前五碼: '{AI_API_KEY[:5] if AI_API_KEY else 'None'}... (總長: {len(AI_API_KEY) if AI_API_KEY else 0})'")
            
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}"
                }
                payload = {
                    "model": AI_MODEL,
                    "messages": messages,
                    "temperature": 0.7
                }
                
                print(f"📦 準備送出的 Payload 結構:\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
                print("⏳ 正在發送網路請求 (Timeout 設定為 30 秒)...")
                
                response = requests.post(AI_API_URL, json=payload, headers=headers, timeout=30)
                
                print(f"📥 收到回應！HTTP 狀態碼: {response.status_code}")
                
                try:
                    res_json = response.json()
                    print(f"📄 原始 JSON 回覆:\n{json.dumps(res_json, ensure_ascii=False, indent=2)}")
                except Exception as json_e:
                    print(f"❌ 無法解析回傳的文字為 JSON. 原始回傳純文字為:\n{response.text}")
                    return ""

                if response.status_code == 200:
                    if 'choices' in res_json:
                        return res_json['choices'][0]['message']['content'].strip()
                    else:
                        print("❌ 警告: 狀態碼 200 但格式不符合 OpenAI 規範 (找不到 'choices')")
                        return ""
                else:
                    print(f"❌ 伺服器拒絕請求，錯誤資訊: {response.text}")
                    return ""
            except requests.exceptions.Timeout:
                print("❌ 錯誤: 網路連線完全超時 (Timeout)，伺服器毫無回應！")
                return ""
            except Exception as e:
                print(f"❌ 網路連線期間發生未預期的崩潰: {type(e).__name__} - {e}")
                return ""
            finally:
                print("=== 🔚 AI API 偵錯終點 ===\n")
                
        return await asyncio.to_thread(sync_post)

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
                summary = str(row[0])
            conn.close()
            return summary
        return await asyncio.to_thread(fetch)

    async def _db_get_recent(self, user_id):
        def fetch():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM frog_recent_chats WHERE user_id = ? ORDER BY id ASC", (user_id,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        return await asyncio.to_thread(fetch)

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

    async def _db_cycle_summary(self, user_id, new_summary):
        def cycle():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE frog_summary SET summary = ? WHERE user_id = ?", (new_summary, user_id))
            cursor.execute("DELETE FROM frog_recent_chats WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(cycle)

    async def summarize_memory(self, user_id, current_summary, recent_chats):
        recent_text = "\n".join([f"{r}: {c}" for r, c in recent_chats])
        prompt = (
            f"你是一個記憶整理助手。請將以下對話內容總結成一段 100 字內的繁體中文精華，"
            f"保留使用者的偏好、提到的重要資訊 or 特殊性格。\n"
            f"現有記憶：{current_summary}\n"
            f"新對話內容：\n{recent_text}\n"
            f"請輸出新的綜合記憶精華："
        )
        messages = [{"role": "user", "content": prompt}]
        new_summary = await self._get_ai_response(messages)
        if new_summary:
            await self._db_cycle_summary(user_id, new_summary)

    @commands.command(help="與青蛙聊天 (具備長短期記憶)")
    async def chat(self, ctx, *, message: str = None):
        if not message:
            await ctx.send("⚠️ 呱！請跟我說點話，例如：`!chat 你是誰？`")
            return

        user_id = ctx.author.id
        
        current_summary = await self._db_get_summary(user_id)
        recent_chats = await self._db_get_recent(user_id)

        if len(recent_chats) >= 20:
            await ctx.send("⌛ *青蛙正在整理腦袋裡的記憶...*")
            await self.summarize_memory(user_id, current_summary, recent_chats)
            current_summary = await self._db_get_summary(user_id)
            recent_chats = await self._db_get_recent(user_id)

        system_instruction = "你是一隻住在台灣、語音幽默且友善的青蛙，請用『繁體中文』回答，結尾可以帶點青蛙的叫聲如『呱』。"

        messages = []
        is_first = True
        for role, content in recent_chats:
            api_role = "user" if role == "使用者" else "assistant"
            if is_first and api_role == "user":
                messages.append({
                    "role": "user",
                    "content": f"【系統任務：{system_instruction} 歷史記憶：{current_summary}】\n\n對話開始：\n{content}"
                })
                is_first = False
            else:
                messages.append({"role": api_role, "content": content})

        if is_first:
            messages.append({
                "role": "user",
                "content": f"【系統任務：{system_instruction} 歷史記憶：{current_summary}】\n\n使用者問：{message}"
            })
        else:
            messages.append({"role": "user", "content": message})

        async with ctx.typing():
            reply = await self._get_ai_response(messages)

        if reply:
            await self._db_save_chat(user_id, "使用者", message)
            await self._db_save_chat(user_id, "青蛙助理", reply)

            for i in range(0, len(reply), 1900):
                await ctx.send(reply[i:i+1900])
        else:
            await ctx.send("⚠️ 呱... 執行失敗，除錯日誌已列印在後台。")

    @commands.command(help="清除青蛙對你的所有記憶")
    async def resetchat(self, ctx):
        user_id = ctx.author.id
        def delete_history():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM frog_summary WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM frog_recent_chats WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()

        try:
            await asyncio.to_thread(delete_history)
            await ctx.send("🗑️ *青蛙喝了忘情水，把你全忘光了！*")
        except Exception as e:
            print(f"清除資料庫失敗: {e}")
            await ctx.send("⚠️ 呱... 忘情水打翻了，清除失敗。")

async def setup(bot):
    await bot.add_cog(Chat(bot))
