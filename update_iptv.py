import asyncio
import aiohttp
import json
import re
import os
import subprocess
import time
import requests
from bs4 import BeautifulSoup

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
    "Player_Ku9", 
    "tvzby", 
    "iptvofficalgroup",
]

OUTPUT_FILE = "live.m3u"
MAX_CONCURRENT_TASKS = 40  # Actions 虚拟机并发检测数
MAX_RETAIN_PER_CHANNEL = 5 # 每个频道保留的最优源数量（延迟最低的 3 个）

# ==================== 2. 精准排序权重配置区 ====================
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

# ==================== 3. 核心清洗与排序函数 ====================
def get_group_title(name):
    """智能分类：包含中文成人关键词的终极隔离过滤"""
    name_upper = name.upper()
    
    adult_keywords = [
        "ADULT", "XXX", "18+", "AV", "HENTAI", "PORN", "SUTRA",
        "松视", "麻豆", "潘多", "潘朵", "彩虹", "惊艳", "香蕉", 
        "一本道", "东京热", "加勒比", "千人斩", "寻花", "探花", 
        "玉蒲团", "金瓶梅", "肉蒲团", "三级", "艳谭", "人妻",
        "熟女", "巨乳", "无码", "激情", "🔞", "🈲", "情色", "色戒", "春药"
    ]
    if any(x in name_upper for x in adult_keywords): return "成人频道"
        
    if "CCTV" in name_upper: return "央视频道"
    if "卫视" in name_upper: return "卫视频道"
    if any(x in name_upper for x in ["TVB", "翡翠", "J2", "无线", "香港", "台湾", "CHC", "凤凰", "纬来", "东森"]): return "港台频道"
    if any(x in name_upper for x in ["HBO", "NETFLIX", "DISCOVERY", "BBC", "CNN", "FOX", "NATIONAL"]): return "欧美经典"
    
    return "地方频道"

def custom_sort_key(item):
    """多级排序核心引擎：大类 -> 省份/地级市 -> 频道号补零 -> 延迟"""
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
                    
    # 频道名称数字补零，如 CCTV-2 变为 CCTV-002
    sort_name = re.sub(r'\d+', lambda x: x.group().zfill(3), name)
    return (cat_weight, prov_weight, sort_name, item["delay"])

def parse_content(text):
    """终极防漏解析：处理 M3U, TXT, 空格连排, p3p 协议及 $ 尾巴"""
    results = []
    # 核心修复 1：将 p3p 伪装协议强转为 http
    text = text.replace("p3p://", "http://")
    
    lines = text.split('\n')
    current_name = None
    
    # 阶段一：处理标准 M3U
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith("#EXTINF"):
            match = re.search(r'tvg-name="([^"]+)"', line)
            current_name = match.group(1) if match else line.split(',')[-1].strip()
        elif "://" in line and "," not in line: 
            # 核心修复 2：切除链接尾部的 $ 干扰后缀（如 $官网）
            clean_url = line.split('$')[0].strip()
            if current_name:
                results.append({"name": current_name, "url": clean_url})
            else:
                results.append({"name": "未知频道", "url": clean_url})
            current_name = None 
            
    # 阶段二：暴力正则提取 "频道名,协议://链接"，应对无换行 TXT 格式
    txt_matches = re.findall(r'([^\s,]+),([a-zA-Z0-9]+://[^\s]+)', text)
    existing_urls = {item['url'] for item in results}
    for name, url in txt_matches:
        clean_url = url.split('$')[0].strip()
        # 核心修复 3：过滤掉 #genre# 分类标签的干扰
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
        except Exception as e:
            print(f"⚠️ 抓取 {url} 失败: {e}")
    return collected

def fetch_telegram_sources():
    print("💬 正在通过 Web 旁路深度解析 Telegram 频道及订阅源...")
    tg_collected = []
    for channel in TG_CHANNELS:
        try:
            url = f"https://t.me/s/{channel}"
            res = requests.get(url, timeout=15)
            if res.status_code != 200: continue
            
            # 第一层：解析群友手发文本
            soup = BeautifulSoup(res.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message_text')
            for msg in messages:
                text = msg.get_text(separator='\n')
                tg_collected.extend(parse_content(text))
            
            # 第二、三层：深度展开配置文件和拾取散落链接
            links = list(set(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F]))+', res.text)))
            for link in links:
                link_lower = link.lower()
                if "t.me/" in link_lower or "telegram.org" in link_lower: continue
                
                if (".m3u" in link_lower and ".m3u8" not in link_lower) or ".txt" in link_lower:
                    try:
                        print(f"   -> 🔍 发现TG订阅配置文件，正在深度展开提取: {link}")
                        sub_res = requests.get(link, timeout=10)
                        if sub_res.status_code == 200:
                            extracted = parse_content(sub_res.text)
                            print(f"      ✅ 成功从该订阅提取了 {len(extracted)} 个频道")
                            tg_collected.extend(extracted)
                    except: pass
                elif ".m3u8" in link_lower or ".flv" in link_lower or ".mp4" in link_lower:
                    if not any(item['url'] == link for item in tg_collected):
                        tg_collected.append({"name": "TG散落源", "url": link})
        except Exception as e:
            print(f"⚠️ 爬取 TG 频道 {channel} 失败: {e}")
    return tg_collected

# ==================== 5. 测速验证与主程序 ====================
async def check_single_stream(semaphore, session, item):
    """异步测速：加入 User-Agent 伪装，大幅提高 PHP 动态防盗链存活率"""
    async with semaphore:
        url = item["url"]
        name = item["name"]
        start_time = time.time()
        
        # 伪装成 Mac 上的 Chrome 浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            # 加入 headers 进行伪装探测，兼容 301/302 动态重定向
            async with session.head(url, headers=headers, timeout=5, allow_redirects=True) as response:
                if response.status not in [200, 301, 302]: return None
        except:
            return None
            
        delay = int((time.time() - start_time) * 1000)
        
        # 给 ffprobe 也加上 user-agent 伪装
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
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
        except Exception as e:
            # 修改了这里，防止被静默吞噬错误
            # print(f"⚠️ ffprobe探测失败 {name}: {e}") # 取消注释可查看具体探测失败原因
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
        # 仅保留每个频道速度最快的 N 个源
        for s in sources[:MAX_RETAIN_PER_CHANNEL]:
            s["group"] = group_title
            final_list.append(s)
            
    # 执行终极多级排序
    final_list.sort(key=custom_sort_key)
        
    # 生成最终 M3U 文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            display_name = f"{item['name']} [{item['res']}]({item['delay']}ms)"
            f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{item["group"]}",{display_name}\n')
            f.write(f'{item["url"]}\n')
            
    print("\n🎉 自动化脚本抓取及精准排序任务圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
