import asyncio
import aiohttp
import json
import re
import os
import subprocess
import time
import requests
from bs4 import BeautifulSoup  # 新增：用于深度解析 TG 网页文本

# ==================== 配置区域 ====================
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
# ==================== TG群组配置区域 ====================
TG_CHANNELS = [
    "kevinmejo", 
    "Player_Ku9", 
    "tvzby", 
    "iptvofficalgroup",
]

OUTPUT_FILE = "live.m3u"
MAX_CONCURRENT_TASKS = 40
MAX_RETAIN_PER_CHANNEL = 3

# ==================== 排序权重配置区 ====================
CATEGORY_WEIGHT = {
    "央视频道": 10, "卫视频道": 20, "地方频道": 30,
    "港台频道": 40, "欧美经典": 50, "成人频道": 60
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
# ==================================================

def get_group_title(name):
    name_upper = name.upper()
    if any(x in name_upper for x in ["ADULT", "XXX", "18+", "AV", "HENTAI", "PORN", "SUTRA"]): return "成人频道"
    if "CCTV" in name_upper: return "央视频道"
    if "卫视" in name_upper: return "卫视频道"
    if any(x in name_upper for x in ["TVB", "翡翠", "J2", "无线", "香港", "台湾", "CHC", "凤凰"]): return "港台频道"
    if any(x in name_upper for x in ["HBO", "NETFLIX", "DISCOVERY", "BBC", "CNN", "FOX", "NATIONAL"]): return "欧美经典"
    return "地方频道"

def custom_sort_key(item):
    name = item["name"]
    group = item["group"]
    cat_weight = CATEGORY_WEIGHT.get(group, 99)
    prov_weight = 999
    if group == "地方频道":
        for prov, weight in PROVINCE_WEIGHT.items():
            if prov in name:
                prov_weight = weight
                break
        if prov_weight == 999:
            for city, prov in CITY_MAPPING.items():
                if city in name:
                    prov_weight = PROVINCE_WEIGHT[prov]
                    break
    sort_name = re.sub(r'\d+', lambda x: x.group().zfill(3), name)
    return (cat_weight, prov_weight, sort_name, item["delay"])

def parse_content(text):
    """解析文本为频道字典，兼容 M3U 和 TXT，加固防漏错"""
    results = []
    lines = text.split('\n')
    current_name = None
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith("#EXTINF"):
            match = re.search(r'tvg-name="([^"]+)"', line)
            current_name = match.group(1) if match else line.split(',')[-1].strip()
        elif line.startswith("http"):
            if current_name:
                results.append({"name": current_name, "url": line})
            else:
                results.append({"name": "未知频道", "url": line})
            current_name = None # 提取完链接后重置名字，防止串台
        elif "," in line and "http" in line:
            parts = line.split(',')
            if len(parts) >= 2 and parts[1].strip().startswith("http"):
                results.append({"name": parts[0].strip(), "url": parts[1].strip()})
    return results

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

# ==================== 核心升级：TG 深度解析模块 ====================
def fetch_telegram_sources():
    print("💬 正在通过 Web 旁路深度解析 Telegram 频道及订阅源...")
    tg_collected = []
    
    for channel in TG_CHANNELS:
        try:
            url = f"https://t.me/s/{channel}"
            res = requests.get(url, timeout=15)
            if res.status_code != 200: continue
            
            # 第一层：解析群友手发的纯文本格式 (例如：CCTV1,http://...m3u8)
            soup = BeautifulSoup(res.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message_text')
            for msg in messages:
                text = msg.get_text(separator='\n')
                tg_collected.extend(parse_content(text))
            
            # 提取网页中所有的 URL
            links = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F]))+', res.text)
            links = list(set(links)) # 去重，防止同一个文件下载多次
            
            for link in links:
                link_lower = link.lower()
                # 排除非相关链接
                if "t.me/" in link_lower or "telegram.org" in link_lower: continue
                
                # 第二层：如果发现 M3U 或 TXT 订阅文件，进行“深度展开”
                if (".m3u" in link_lower and ".m3u8" not in link_lower) or ".txt" in link_lower:
                    try:
                        print(f"   -> 🔍 发现TG订阅配置文件，正在深度展开提取: {link}")
                        sub_res = requests.get(link, timeout=10)
                        if sub_res.status_code == 200:
                            extracted = parse_content(sub_res.text)
                            print(f"      ✅ 成功从该订阅提取了 {len(extracted)} 个频道")
                            tg_collected.extend(extracted)
                    except:
                        pass
                        
                # 第三层：拾取散落的单一独立播放源
                elif ".m3u8" in link_lower or ".flv" in link_lower or ".mp4" in link_lower:
                    # 避免与第一层已经提取出的频道重复
                    if not any(item['url'] == link for item in tg_collected):
                        tg_collected.append({"name": "TG散落源", "url": link})
                        
        except Exception as e:
            print(f"⚠️ 爬取 TG 频道 {channel} 失败: {e}")
            
    return tg_collected

# ==================================================

async def check_single_stream(semaphore, session, item):
    async with semaphore:
        url = item["url"]
        name = item["name"]
        start_time = time.time()
        
        try:
            async with session.head(url, timeout=3, allow_redirects=True) as response:
                if response.status != 200: return None
        except:
            return None
            
        delay = int((time.time() - start_time) * 1000)
        
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
    total_raw = fetch_web_sources() + fetch_telegram_sources()
    if not total_raw: return
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_TASKS, ssl=False)
    
    print(f"\n🚀 开始并发检测 {len(total_raw)} 个原始直播源...")
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_single_stream(semaphore, session, item) for item in total_raw]
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if r is not None]
    
    channel_dict = {}
    for r in valid_results:
        channel_dict.setdefault(r["name"], []).append(r)
        
    final_list = []
    for name, sources in channel_dict.items():
        sources.sort(key=lambda x: x["delay"]) 
        group_title = get_group_title(name)
        
        for s in sources[:MAX_RETAIN_PER_CHANNEL]:
            s["group"] = group_title
            final_list.append(s)
            
    # 执行终极多级排序
    final_list.sort(key=custom_sort_key)
        
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            display_name = f"{item['name']} [{item['res']}]({item['delay']}ms)"
            f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{item["group"]}",{display_name}\n')
            f.write(f'{item["url"]}\n')
            
    print("🎉 自动化脚本抓取及精准排序任务圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
