import os
import random
import shutil
import discord
from discord.ext import commands

# 音樂檔案資料夾
MUSIC_DIR = os.path.join(os.getcwd(), "songs")
os.makedirs(MUSIC_DIR, exist_ok=True)

# 檢查 FFmpeg 是否安裝
def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("⚠️ 找不到 FFmpeg！請確認已安裝並設定好 PATH")
    else:
        print("✅ FFmpeg 已安裝，可以使用。")

class Music(commands.Cog, description="音樂相關指令"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="測試 Bot 是否在線")
    async def ping(self, ctx):
        await ctx.send("呱")

    @commands.command(help="播放歌曲（輸入歌名僅限本地播放，輸入網址則從 YouTube 下載）")
    async def play(self, ctx, *, url: str):
        if ctx.author.voice is None:
            await ctx.send("請先加入語音頻道！")
            return

        if ctx.voice_client:
            voice_client = ctx.voice_client
        else:
            channel = ctx.author.voice.channel
            voice_client = await channel.connect()

        clean_input = url.strip()
        is_url = clean_input.startswith(('http://', 'https://'))

        # --------------------------------------------------------
        # 🔍 情況一：使用者輸入的是歌名，只在本地找
        # --------------------------------------------------------
        if not is_url:
            local_file_path = None
            local_files = os.listdir(MUSIC_DIR)
            clean_query = clean_input.lower()
            display_name = clean_input

            for file in local_files:
                # 💡 [關鍵修正] 加上 [0]，精準提取出不含副檔名的「純字串檔名」
                name_without_ext = os.path.splitext(file)[0]
                
                # 如果輸入完全符合「檔名.mp3」或「純檔名」
                if clean_query == file.lower() or clean_query == name_without_ext.lower():
                    local_file_path = os.path.join(MUSIC_DIR, file)
                    display_name = name_without_ext
                    break

            if local_file_path and os.path.exists(local_file_path):
                if voice_client.is_playing():
                    voice_client.stop()
                voice_client.play(discord.FFmpegPCMAudio(local_file_path))
                await ctx.send(f"📁 發現本地檔案，直接播放：**{display_name}**")
                return
            else:
                await ctx.send(f"❌ 本地找不到歌曲 ` {clean_input} `。若要下載新歌，請貼上 YouTube 完整網址！")
                return

        # --------------------------------------------------------
        # 🌐 情況二：使用者輸入的是網址，啟動 YouTube 直接下載
        # --------------------------------------------------------
        await ctx.send("📥 偵測到 YouTube 網址，正在下載音訊中...")

        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'outtmpl': os.path.join(MUSIC_DIR, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }]
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_input, download=True)
                file_path = ydl.prepare_filename(info)
                file_path = os.path.splitext(file_path)[0] + ".mp3"
        except Exception as e:
            await ctx.send(f"❌ 錯誤：無法從該網址下載音訊（{e}）")
            return

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(discord.FFmpegPCMAudio(file_path))
        await ctx.send(f"🎵 網址下載完成並開始播放：**{info['title']}**")




    @commands.command(help="停止播放並離開語音頻道")
    async def stop(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("已停止播放並離開語音頻道")

    @commands.command(help="顯示目前已下載的歌曲清單")
    async def list(self, ctx):
        files = os.listdir(MUSIC_DIR)
        if not files:
            await ctx.send("目前音樂資料夾是空的喔！")
            return

        # 先產生完整的字串
        full_list = "\n".join([f"{i+1}. {file}" for i, file in enumerate(files)])

        # 如果總長度超過 1900 字，就分段傳送
        if len(full_list) > 1900:
            # 使用 list comprehension 或 迴圈切片
            for i in range(0, len(full_list), 1900):
                part = full_list[i:i+1900]
                await ctx.send(f"```{part}```")
        else:
            await ctx.send(f"目前有的歌曲：\n```{full_list}```")



    @commands.command(help="刪除指定歌曲檔案")
    async def delete(self, ctx, *, filename: str):
        file_path = os.path.join(MUSIC_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            await ctx.send(f"已刪除歌曲：{filename}")
        else:
            await ctx.send("找不到指定的歌曲檔案。")

    @commands.command(help="隨機連續播放已下載的歌曲")
    async def randomplay(self, ctx):
        if ctx.author.voice is None:
            await ctx.send("請先加入語音頻道！")
            return

        if ctx.voice_client:
            voice_client = ctx.voice_client
        else:
            channel = ctx.author.voice.channel
            voice_client = await channel.connect()

        self.play_random_song(ctx, voice_client)

    def play_random_song(self, ctx, voice_client):
        files = os.listdir(MUSIC_DIR)
        if not files:
            return

        chosen = random.choice(files)
        file_path = os.path.join(MUSIC_DIR, chosen)

        def after_playing(error):
            if error:
                print(f"播放錯誤: {error}")
            else:
                self.play_random_song(ctx, voice_client)

        voice_client.play(discord.FFmpegPCMAudio(file_path), after=after_playing)
        coro = ctx.send(f"隨機播放：{chosen}")
        self.bot.loop.create_task(coro)



async def setup(bot):
    await bot.add_cog(Music(bot))

