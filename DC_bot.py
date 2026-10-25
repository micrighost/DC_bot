import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True


class MyBot(commands.Bot):
    async def setup_hook(self):
        extensions = ["commands.music", "commands.chat", "commands.daily"]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ 成功載入 {ext}")
            except Exception as e:
                print(f"❌ 載入 {ext} 失敗: {e}")

# 關掉預設的 HelpCommand
bot = MyBot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"已登入：{bot.user}")

# 自訂 help 指令
@bot.command(name="help", help="顯示所有可用指令")
async def help_command(ctx):
    help_text = "**可用指令列表：**\n"
    for command in bot.commands:
        help_text += f"`!{command.name}` - {command.help or '沒有描述'}\n"
    await ctx.send(help_text)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))