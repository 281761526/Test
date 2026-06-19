import asyncio
import aiohttp
import json
import re
import os
import subprocess
import time
import requests
import datetime
from bs4 import BeautifulSoup
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==================== 1. 基础抓取配置区域 ====================
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
    "https://epg.pw/test_channels_hong_kong.m3u",
    "https://epg.pw/test_channels_macau.m3u",
    "https://epg.pw/test_channels_taiwan.m3u",
    "https://raw.githubusercontent.com/mytv-android/BRTV-Live-M3U8/main/iptv.m3u",
    "https://iptv-org.github.io/iptv/countries/tw.m3u//cdn.qd.je/live.m3u",
    "https://raw.githubusercontent.com/BigBigGrandG/IPTV-URL/release/Gather.m3u",
    "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
]

# ==================== TG群组配置区域 ====================
TG_CHANNELS = [
    "kevinmejo", 
    "AptvPlayer",
    "Player_Ku9", 
    "tvzby", 
    "iptvofficalgroup",
]

OUTPUT_FILE = "live.m3u"
MAX_CONCURRENT_TASKS = 40  
MAX_RETAIN_PER_CHANNEL = 5 

# 读取安全环境变量
TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")
TG_SESSION = os.environ.get("TG_SESSION")

# ==================== 2. 精准排序权重配置区 ====================
CATEGORY_WEIGHT = {
    "央视频道": 10, "卫视频道": 20, 
    # 地方省份频道的权重动态分配为 30
    "体育频道": 31, "电影频道": 32, "电视剧频道": 33, 
    "少儿频道": 34, "纪录频道": 35, "音乐频道": 36,
    "港台频道": 40, "日本频道": 50, "韩国频道": 60,
    "新马泰频道": 70, "欧美频道": 80, "其他频道": 90, 
    "成人频道": 100
}

PROVINCE_WEIGHT = {
    "北京": 1, "上海": 2, "天津": 3, "重庆": 4, "广东": 5, "浙江": 6, "江苏": 7, "山东": 8,
    "四川": 9, "湖南": 10, "湖北": 11, "福建": 12, "安徽": 13, "江西": 14, "河南": 15, "河北": 16,
    "山西": 17, "陕西": 18, "黑龙江": 19, "吉林": 20, "辽宁": 21, "云南": 22, "贵州": 23, "广西": 24,
    "海南": 25, "内蒙古": 26, "甘肃": 27, "宁夏": 28, "青海": 29, "新疆": 30, "西藏": 31
}

CITY_MAPPING = {
    "广州": "广东", "深圳": "广东", "杭州": "浙江", "宁波": "浙江", "温州": "浙江", "南京": "江苏", 
    "苏州": "江苏", "无锡": "江苏", "成都": "四川", "武汉": "湖北", "济南": "山东", "青岛": "山东",
    "厦门": "福建", "福州": "福建", "泉州": "福建", "长沙": "湖南", "郑州": "河南", "合肥": "安徽", 
    "南昌": "江西", "哈尔滨": "黑龙江", "长春": "吉林", "沈阳": "辽宁", "大连": "辽宁", "昆明": "云南", 
    "贵阳": "贵州", "南宁": "广西", "海口": "海南", "呼和浩特": "内蒙古", "兰州": "甘肃", "银川": "宁夏", 
    "西宁": "青海", "乌鲁木齐": "新疆", "拉萨": "西藏"
}

# ==================== 3. 核心清洗与排序函数 ====================
def standardize_name(name):
    """超级名称清洗：将乱七八糟的后缀剥离，强制统一格式"""
    name = name.upper()
    noise_words = ['HD', 'FHD', 'SD', '1080P', '4K', '8K', '高清', '超清', '标清', '蓝光', '频道', '综合', '测试', '线路', 'VIP']
    for word in noise_words:
        name = name.replace(word, '')
        
    name = re.sub(r'[\s\-_\[\]\(\)（）【】]', '', name)
    
    cctv_match = re.search(r'(CCTV|中央)(\d+\+?)', name)
    if cctv_match: return f"CCTV-{cctv_match.group(2)}"
        
    if "卫视" in name:
        weishi_match = re.search(r'(.{2,4}卫视)', name)
        if weishi_match: return weishi_match.group(1)
            
    return name

def get_group_title(name):
    """智能分类引擎：支持垂直主题、多国地区与省份独立建组"""
    name_upper = name.upper()
    
    # 1. 成人过滤器 (最高优先级)
    adult_keywords = [
        "ADULT", "XXX", "18+", "AV", "HENTAI", "PORN", "SUTRA",
        "松视", "麻豆", "潘多", "潘朵", "彩虹", "惊艳", "香蕉", 
        "一本道", "东京热", "加勒比", "千人斩", "寻花", "探花", 
        "玉蒲团", "金瓶梅", "肉蒲团", "三级", "艳谭", "人妻",
        "熟女", "巨乳", "无码", "激情", "🔞", "🈲", "情色", "色戒", "春药"
    ]
    if any(x in name_upper for x in adult_keywords): return "成人频道"
        
    # 2. 国内核心频道
    if "CCTV" in name_upper or "中央" in name_upper: return "央视频道"
    if "卫视" in name_upper: return "卫视频道"
    
    # 3. 垂直主题频道
    if any(x in name_upper for x in ["电影", "影院", "影迷", "MOVIE", "CINEMA", "星影", "动作", "大片"]): return "电影频道"
    if any(x in name_upper for x in ["剧", "电视剧"]): return "电视剧频道"
    if any(x in name_upper for x in ["音乐", "MTV", "MUSIC", "KTV", "演唱会", "好声音"]): return "音乐频道"
    if any(x in name_upper for x in ["体育", "SPORTS", "足球", "NBA", "CBA", "台球", "高尔夫", "奥运"]): return "体育频道"
    if any(x in name_upper for x in ["少儿", "动漫", "卡通", "动画", "CARTOON", "KIDS", "金鹰卡通", "炫动卡通"]): return "少儿频道"
    if any(x in name_upper for x in ["纪录", "纪实", "地理", "DISCOVERY", "NATIONAL", "HISTORY", "科教"]): return "纪录频道"

    # 4. 国际与地区精准识别
    if any(x in name_upper for x in ["TVB", "翡翠", "J2", "明珠", "星空", "凤凰", "纬来", "东森", "八大", "中天", "三立", "民视", "台视", "华视", "年代", "非凡", "香港", "台湾"]): return "港台频道"
    if any(x in name_upper for x in ["NHK", "FUJI", "TOKYO", "TBS", "WOWOW", "J-SPORTS", "JSPORTS", "NTV", "朝日", "日本", "JAPAN"]): return "日本频道"
    if any(x in name_upper for x in ["KBS", "SBS", "MBC", "TVN", "JTBC", "OCN", "MNET", "韩国", "KOREA"]): return "韩国频道"
    if any(x in name_upper for x in ["ASTRO", "STARHUB", "SINGAPORE", "MALAYSIA", "THAILAND", "新加坡", "大马", "马来西亚", "泰国", "CH3", "CH7", "8频道", "U频道"]): return "新马泰频道"
    if any(x in name_upper for x in ["HBO", "NETFLIX", "BBC", "CNN", "FOX", "SKY", "ESPN", "ABC", "NBC", "CBS", "美国", "英国", "USA", "UK"]): return "欧美频道"
    
    # 5. 地方频道按省份兜底
    for prov in PROVINCE_WEIGHT.keys():
        if prov in name_upper: return f"{prov}频道"
    for city, prov in CITY_MAPPING.items():
        if city in name_upper: return f"{prov}频道"
        
    return "其他频道"

def custom_sort_key(item):
    name = item["name"]
    group = item["group"]
    cat_weight = CATEGORY_WEIGHT.get(group, 99)
    prov_weight = 999
    
    prov_name = group.replace("频道", "")
    if prov_name in PROVINCE_WEIGHT:
        cat_weight = 30 
        prov_weight = PROVINCE_WEIGHT[prov_name]
                    
    sort_name = re.sub(r'\d+', lambda x: x.group().zfill(3), name)
    return (cat_weight, prov_weight, sort_name, item["delay"])

def parse_content(text):
    results = []
    text = text.replace("p3p://", "http://")
    lines = text.split('\n')
    current_name = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith("#EXTINF"):
            match = re.search(r'tvg-name="([^"]+)"', line)
            current_name = match.group(1) if match else line.split(',')[-1].strip()
        elif "://" in line and "," not in line: 
            clean_url = line.split('$')[0].strip()
            if current_name:
                results.append({"name": current_name, "url": clean_url})
            else:
                results.append({"name": "未知频道", "url": clean_url})
            current_name = None 
            
    txt_matches = re.findall(r'([^\s,]+),([a-zA-Z0-9]+://[^\s]+)', text)
    existing_urls = {item['url'] for item in results}
    for name, url in txt_matches:
        clean_url = url.split('$')[0].strip()
        if clean_url not in existing_urls and "#genre#" not in clean_url:
            results.append({"name": name.strip(), "url": clean_url})
            existing_urls.add(clean_url)
            
    return results

# ==================== 4. 数据抓取模块 ====================
def fetch_web_sources():
    print("📡 正在抓取网络公开直播源...")
    collected = []
    for url in RAW_SOURCES_URLS:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                collected.extend(parse_content(res.text))
        except: pass
    return collected

async def fetch_telegram_sources_async():
    print("💬 正在通过 Telethon 协议解析 TG 群组...")
    tg_collected = []
    if not TG_SESSION or not TG_API_ID or not TG_API_HASH: return tg_collected

    client = TelegramClient(StringSession(TG_SESSION), int(TG_API_ID), TG_API_HASH)
    await client.connect()

    for channel in TG_CHANNELS:
        try:
            async for message in client.iter_messages(channel, limit=30):
                if message.text: tg_collected.extend(parse_content(message.text))
                if message.document and message.file.name:
                    file_name = message.file.name.lower()
                    if '.m3u' in file_name or '.txt' in file_name:
                        try:
                            file_bytes = await client.download_media(message.document, bytes)
                            if file_bytes:
                                text_content = file_bytes.decode('utf-8', errors='ignore')
                                tg_collected.extend(parse_content(text_content))
                        except: pass
        except: pass
    await client.disconnect()
    return tg_collected

async def fetch_github_search_sources():
    print("🌐 启动 GitHub 全网雷达，搜索最新野生开源 IPTV 仓库...")
    collected = []
    github_token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token: headers["Authorization"] = f"token {github_token}"
        
    date_limit = (datetime.datetime.utcnow() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
    query = f"iptv OR m3u pushed:>{date_limit}"
    search_url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=5"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(search_url, headers=headers, timeout=10) as res:
                if res.status != 200: return collected
                data = await res.json()
                repos = data.get("items", [])
                
            for repo in repos:
                repo_name = repo["full_name"]
                default_branch = repo["default_branch"]
                print(f"   -> 🔍 锁定活跃仓库: {repo_name}")
                
                tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{default_branch}?recursive=1"
                async with session.get(tree_url, headers=headers, timeout=10) as tree_res:
                    if tree_res.status != 200: continue
                    tree_data = await tree_res.json()
                    tree = tree_data.get("tree", [])
                    
                m3u_files = [item["path"] for item in tree if str(item["path"]).lower().endswith(".m3u")]
                for path in m3u_files[:3]: 
                    raw_url = f"https://raw.githubusercontent.com/{repo_name}/{default_branch}/{path}"
                    try:
                        async with session.get(raw_url, timeout=15) as raw_res:
                            if raw_res.status == 200:
                                text = await raw_res.text()
                                collected.extend(parse_content(text))
                    except: pass
        except Exception as e:
            print(f"⚠️ GitHub 雷达运行异常: {e}")
            
    return collected

# ==================== 5. 测速验证与主程序 ====================
async def check_single_stream(semaphore, session, item):
    async with semaphore:
        url = item["url"]
        name = item["name"]
        
        if "webview.js" in url:
            return {"name": name, "url": url, "delay": 1, "res": "Webview"}

        start_time = time.time()
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        
        try:
            async with session.head(url, headers=headers, timeout=5, allow_redirects=True) as response:
                if response.status not in [200, 301, 302]: return None
        except: return None
            
        delay = int((time.time() - start_time) * 1000)
        
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-user_agent', 'Mozilla/5.0',
            '-show_streams', '-select_streams', 'v:0', '-i', url
        ]
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
        except: pass
        return None

async def main():
    web_raw = fetch_web_sources()
    tg_raw = await fetch_telegram_sources_async()
    github_raw = await fetch_github_search_sources()
    
    total_raw = web_raw + tg_raw + github_raw
    if not total_raw: return
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_TASKS, ssl=False)
    
    print(f"\n🚀 开始并发检测 {len(total_raw)} 个合并后的直播源...")
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_single_stream(semaphore, session, item) for item in total_raw]
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if r is not None]
    
    channel_dict = {}
    for r in valid_results:
        clean_name = standardize_name(r["name"])
        r["name"] = clean_name 
        channel_dict.setdefault(clean_name, []).append(r)
        
    final_list = []
    for name, sources in channel_dict.items():
        sources.sort(key=lambda x: x["delay"]) 
        group_title = get_group_title(name)
        for s in sources[:MAX_RETAIN_PER_CHANNEL]:
            s["group"] = group_title
            final_list.append(s)
            
    final_list.sort(key=custom_sort_key)
        
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            lock_tag = ' tvg-lock="1"' if item["group"] == "成人频道" else ""
            display_name = f"{item['name']} [{item['res']}]({item['delay']}ms)"
            f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{item["group"]}"{lock_tag},{display_name}\n')
            f.write(f'{item["url"]}\n')
            
    print("\n🎉 自动化脚本全网抓取、深度洗澡及精准排序任务圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
