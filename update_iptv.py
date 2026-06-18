import asyncio
import aiohttp
import json
import re
import os
import subprocess
import time
import requests

# ==================== 配置区域 ====================
# 1. 外部 M3U/TXT 抓取源池（涵盖GitHub分享及论坛接口）
RAW_SOURCES_URLS = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/zbefine/iptv/main/iptv.m3u",
    "https://testingcf.jsdelivr.net/gh/YueChan/Live@main/IPTV.m3u",
    "https://raw.githubusercontent.com/vamoschuck/TV/main/M3U",
    "https://raw.githubusercontent.com/YanG-1989/m3u/refs/heads/main/Migu.m3u",
    "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/refs/heads/main/GNTV.m3u",
    "https://iptv.yang-1989.eu.org/m3u/Gather.m3u",
    "https://cdn.qd.je/live.m3u",
]

# 2. 需要爬取的 Telegram 公开频道/群组用户名（不带 @）
TG_CHANNELS = [
    "kevinmejo", # 替换为实际分享直播源的TG频道名
    "iptv_channel_example", # 替换为实际分享直播源的TG频道名
    "iptv_channel_example", # 替换为实际分享直播源的TG频道名
    "iptv_channel_example", # 替换为实际分享直播源的TG频道名
]

OUTPUT_FILE = "live.m3u"
MAX_CONCURRENT_TASKS = 40  # Actions虚拟机性能好，并发可开大
MAX_RETAIN_PER_CHANNEL = 3  # 每个频道保留3-5个最优解
# ==================================================

# 智能精准分类规则
def get_group_title(name):
    name_upper = name.upper()
    # 成人类关键词过滤
    if any(x in name_upper for x in ["ADULT", "XXX", "18+", "AV", "HENTAI", "PORN", "SUTRA"]): return "成人频道"
    if "CCTV" in name_upper: return "央视频道"
    if "卫视" in name_upper: return "卫视频道"
    # 港台关键词
    if any(x in name_upper for x in ["TVB", "翡翠", "J2", "无线", "香港", "台湾", "CHC", "凤凰"]): return "港台频道"
    # 欧美国际关键词
    if any(x in name_upper for x in ["HBO", "NETFLIX", "DISCOVERY", "BBC", "CNN", "FOX", "NATIONAL"]): return "欧美经典"
    # 地方台
    return "地方频道"

# 1. 抓取模块 (GitHub + 论坛)
def fetch_web_sources():
    print("📡 正在抓取网络公开直播源...")
    collected = []
    for url in RAW_SOURCES_URLS:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                collected.extend(parse_content(res.text))
        except Exception as e:
            print(f"⚠️ 抓取 {url} 失败: {e}")
    return collected

# 解析文本（兼容 M3U 和 TXT 格式）
def parse_content(text):
    results = []
    lines = text.split('\n')
    current_name = None
    for line in lines:
        line = line.strip()
        if not line: continue
        # M3U 格式解析
        if line.startswith("#EXTINF"):
            match = re.search(r'tvg-name="([^"]+)"', line)
            current_name = match.group(1) if match else line.split(',')[-1]
        elif line.startswith("http"):
            if current_name:
                results.append({"name": current_name, "url": line})
            else:
                # 兼容纯链接或者某些TXT格式
                results.append({"name": "未知频道", "url": line})
        # TXT 格式解析 (如: 央视一套,http://xxx)
        elif "," in line and "http" in line:
            parts = line.split(',')
            if len(parts) >= 2 and parts[1].startswith("http"):
                results.append({"name": parts[0], "url": parts[1]})
    return results

# 2. 抓取模块 (Telegram 频道网页端预览旁路爬取 - 免登录极其稳定)
def fetch_telegram_sources():
    print("💬 正在通过 Web 旁路爬取 Telegram 频道...")
    tg_collected = []
    for channel in TG_CHANNELS:
        try:
            # 使用 TG 网页预览接口，无需登录，防止 Actions 登录被封号
            url = f"https://t.me/s/{channel}"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                # 提取网页中所有可能的直播链接及 M3U/TXT 文本文本
                links = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F]))+', res.text)
                for link in links:
                    if ".m3u8" in link or ".m3u" in link:
                        tg_collected.append({"name": "TG分享源", "url": link})
        except Exception as e:
            print(f"⚠️ 爬取 TG 频道 {channel} 失败: {e}")
    return tg_collected

# 3. 异步测速与 FFmpeg 深度验证
async def check_single_stream(semaphore, session, item):
    async with semaphore:
        url = item["url"]
        name = item["name"]
        start_time = time.time()
        
        # 阶段一：HTTP HEAD 探测快速过滤
        try:
            async with session.head(url, timeout=3, allow_redirects=True) as response:
                if response.status != 200: return None
        except:
            return None
            
        delay = int((time.time() - start_time) * 1000)
        
        # 阶段二：FFmpeg 探测画质
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-select_streams', 'v:0', '-i', url]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4)
            if proc.returncode == 0:
                data = json.loads(stdout.decode('utf-8'))
                if "streams" in data and len(data["streams"]) > 0:
                    w = data["streams"][0].get("width", 0)
                    h = data["streams"][0].get("height", 0)
                    print(f"✅ 成功: {name} | {w}x{h} | {delay}ms")
                    return {"name": name, "url": url, "delay": delay, "res": f"{w}x{h}"}
        except:
            pass
        return None

async def main():
    # 聚合所有抓取渠道
    total_raw = fetch_web_sources() + fetch_telegram_sources()
    if not total_raw: return
    
    # 异步并发控制
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_TASKS, ssl=False)
    
    print(f"🚀 开始并发检测 {len(total_raw)} 个原始直播源...")
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_single_stream(semaphore, session, item) for item in total_raw]
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if r is not None]
    
    # 分类、排序、去重
    channel_dict = {}
    for r in valid_results:
        channel_dict.setdefault(r["name"], []).append(r)
        
    final_list = []
    for name, sources in channel_dict.items():
        sources.sort(key=lambda x: x["delay"]) # 延迟低排前面
        final_list.extend(sources[:MAX_RETAIN_PER_CHANNEL]) # 仅保留前3-5个
        
    # 生成规范的 M3U 文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            group = get_group_title(item["name"])
            display_name = f"{item['name']} [{item['res']}]({item['delay']}ms)"
            f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{group}",{display_name}\n')
            f.write(f'{item["url"]}\n')
    print("🎉 自动化脚本任务圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
