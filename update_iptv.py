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
import zhconv  # 🟢 引入强大的简繁体转换库

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
    "http://210.245.166.84:1299/live/live.txt",
    "http://bh666.filegear-sg.me/php/bhlive.php",
    "http://ttkx.cc:55/lib/kx2024.txt",
    "http://aktv.top/live.m3u",
    "https://live.fanmingming.com/tv/m3u/ipv6.m3u",
    "https://ghp.ci/raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    "https://cdn09022024.gitlink.org.cn/api/v1/repos/qianx/123/raw/1231?ref=master&access_token=9cdba3b67a6dadb223a75cde19bbca6125757e5e",
    "https://raw.githubusercontent.com/281761526/HBD/refs/heads/main/7.m3u",
    "https://gitee.com/main-stream/tv/raw/master/BOSS.json",
    "https://iptv-org.github.io/api/streams.json",
    "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/refs/heads/main/cnTV_AutoUpdate.m3u8",
    "https://raw.githubusercontent.com/FunctionError/PiratesTv/refs/heads/main/combined_playlist.m3u",
]

TG_CHANNELS = ["kevinmejo", "AptvPlayer", "Player_Ku9", "tvzby", "iptvofficalgroup"]

OUTPUT_M3U = "live.m3u"
OUTPUT_TXT = "live.txt"  
MAX_CONCURRENT_TASKS = 40  
MAX_RETAIN_PER_CHANNEL = 5 

TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")
TG_SESSION = os.environ.get("TG_SESSION")

# ==================== 2. 极简排序权重与地市深度字典 ====================
CATEGORY_WEIGHT = {
    "央视频道": 10, "卫视频道": 20, 
    "港澳台频道": 30,
    "新闻资讯": 40, "体育频道": 41, "影视频道": 42, 
    "少儿频道": 43, "科教纪录": 44, "综合文娱": 45, 
    "国际频道": 60, 
    "其他频道": 90, 
    "成人频道": 100
}

PROVINCE_WEIGHT = {
    "北京": 1, "上海": 2, "天津": 3, "重庆": 4, "广东": 5, "浙江": 6, "江苏": 7, "山东": 8,
    "四川": 9, "湖南": 10, "湖北": 11, "福建": 12, "安徽": 13, "江西": 14, "河南": 15, "河北": 16,
    "山西": 17, "陕西": 18, "黑龙江": 19, "吉林": 20, "辽宁": 21, "云南": 22, "贵州": 23, "广西": 24,
    "海南": 25, "内蒙古": 26, "甘肃": 27, "宁夏": 28, "青海": 29, "新疆": 30, "西藏": 31
}

CITY_MAPPING = {
    "广州": "广东", "深圳": "广东", "珠海": "广东", "汕头": "广东", "佛山": "广东", "东莞": "广东", "湛江": "广东", "中山": "广东", "惠州": "广东", "江门": "广东", "潮州": "广东", "河源": "广东",
    "杭州": "浙江", "宁波": "浙江", "温州": "浙江", "绍兴": "浙江", "金华": "浙江", "嘉兴": "浙江", "台州": "浙江", "湖州": "浙江", "丽水": "浙江", "义乌": "浙江", "文成": "浙江",
    "青田": "浙江", "钱江": "浙江", "之江": "浙江", "余杭": "浙江", "云和": "浙江", "上虞": "浙江","遂昌": "浙江","象山": "浙江",
    "南京": "江苏", "苏州": "江苏", "无锡": "江苏", "徐州": "江苏", "常州": "江苏", "南通": "江苏", "连云港": "江苏", "淮安": "江苏", "盐城": "江苏", "扬州": "江苏", "镇江": "江苏", "泰州": "江苏", "宿迁": "江苏", "新沂": "江苏", "沭阳": "江苏", "邳州": "江苏", "句容": "江苏",
    "成都": "四川", "绵阳": "四川", "广安": "四川", "南充": "四川", "达州": "四川", "宜宾": "四川", "泸州": "四川", "德阳": "四川", "乐山": "四川", "巴中": "四川",
    "金川": "四川", "汶川": "四川", "沐川": "四川","荣昌": "四川", "潼南": "四川",
    "长春": "吉林", "吉林市": "吉林", "四平": "吉林", "辽源": "吉林", "通化": "吉林", "白山": "吉林", "松原": "吉林", "白城": "吉林", "延边": "吉林", "梅河口": "吉林", "桦甸": "吉林",
    "靖宇": "吉林", "汪清": "吉林", "江源": "吉林", "永吉": "吉林", "柳河": "吉林", "敦化": "吉林", "双阳": "吉林", "东辽": "吉林", "东丰": "吉林", "农安": "吉林","集安": "吉林","吉安": "吉林",
    "武汉": "湖北", "宜昌": "湖北", "襄阳": "湖北", "荆州": "湖北", "黄石": "湖北", "十堰": "湖北", "荆门": "湖北",
    "济南": "山东", "青岛": "山东", "烟台": "山东", "潍坊": "山东", "威海": "山东", "临沂": "山东", "济宁": "山东", "淄博": "山东", "梁山": "山东",
    "厦门": "福建", "福州": "福建", "泉州": "福建", "漳州": "福建","梅州": "福建",
    "石家庄": "河北", "唐山": "河北", "秦皇岛": "河北", "邯郸": "河北", "邢台": "河北", "保定": "河北", "张家口": "河北", "承德": "河北", "沧州": "河北", "廊坊": "河北", "衡水": "河北",
    "迁西": "河北", "清河": "河北", "兴隆": "河北", "丰宁": "河北", "昌黎": "河北",
    "长沙": "湖南", "株洲": "湖南", "岳阳": "湖南", "郑州": "河南", "洛阳": "河南", "开封": "河南", "合肥": "安徽", "芜湖": "安徽", "蚌埠": "安徽",
    "灵璧": "安徽", "固镇": "安徽",
    "南昌": "江西", "赣州": "江西", "九江": "江西", "哈尔滨": "黑龙江", "大庆": "黑龙江", "齐齐哈尔": "黑龙江",
    "沈阳": "辽宁", "大连": "辽宁", "鞍山": "辽宁", "昆明": "云南", "大理": "云南",
    "贵阳": "贵州", "遵义": "贵州", "南宁": "广西", "桂林": "广西", "柳州": "广西", "海口": "海南", "三亚": "海南",
    "南国": "海南", 
    "呼和浩特": "内蒙古", "包头": "内蒙古", "鄂尔多斯": "内蒙古", "巴彦淖尔": "内蒙古", "乌兰察布": "内蒙古", "乌海": "内蒙古", "兴安": "内蒙古", "锡林郭勒盟": "内蒙古",
    "兰州": "甘肃", "天水": "甘肃", "银川": "宁夏", 
    "西宁": "青海", "乌鲁木齐": "新疆", "克拉玛依": "新疆", "拉萨": "西藏", "BTV": "北京", "兵团": "新疆",
    "奎屯": "新疆", "吉木萨尔": "新疆",
    "娱乐新闻": "文娱", 
    "晋城": "山西" 
}

# ==================== 3. 核心清洗与极简分类引擎 ====================
def standardize_name(name):
    """🟢 终极规范名称引擎：强迫症专属央视/CGTN官方定名"""
    name_upper = zhconv.convert(name, 'zh-cn').upper()
    
    # 【拦截区 1】：CGTN 国际频道强制洗澡
    if "CGTN" in name_upper:
        if any(x in name_upper for x in ["西语", "西班牙", "ESPA"]): return "CGTN Español 西班牙语频道"
        if any(x in name_upper for x in ["法语", "FRAN"]): return "CGTN Français 法语频道"
        if any(x in name_upper for x in ["阿语", "阿拉伯", "ARAB"]): return "CGTN العربية 阿拉伯语频道"
        if any(x in name_upper for x in ["俄语", "RUS"]): return "CGTN Русский 俄语频道"
        if any(x in name_upper for x in ["纪录", "DOC"]): return "CGTN Documentary 环球纪录频道"
        return "CGTN（英语新闻频道）"
    
    # 【拦截区 2】：CCTV 央视频道强制洗澡
    if "CCTV" in name_upper or "中央" in name_upper:
        if "4K" in name_upper: return "CCTV-4K 超高清"
        if "8K" in name_upper: return "CCTV-8K 超高清"
        
        cctv_match = re.search(r'(CCTV|中央)[^\d]*(\d+\+?)', name_upper)
        if cctv_match:
            num = cctv_match.group(2)
            
            # 🟢 终极容错：去除数字开头的 '0'（把 '01', '001' 变成 '1'，但保留 '5+'）
            if num.startswith('0') and len(num) > 1:
                num = num.lstrip('0')
            
            # 特殊处理：CCTV-4 多版本
            if num == "4":
                if "欧洲" in name_upper: return "CCTV-4 中文国际频道（欧洲版）"
                if "美洲" in name_upper: return "CCTV-4 中文国际频道（美洲版）"
                if "亚洲" in name_upper: return "CCTV-4 中文国际频道（亚洲版）"
                return "CCTV-4 中文国际"
                
            # 特殊处理：CCTV-9 双语版本
            if num == "9":
                if any(x in name_upper for x in ["英", "DOC"]): return "CCTV-9 Documentary 纪录频道（英文版）"
                return "CCTV-9 纪录频道"
                
            # 常规央视标准映射
            cctv_map = {
                "1": "CCTV-1 综合频道", "2": "CCTV-2 财经频道", "3": "CCTV-3 综艺频道",
                "5": "CCTV-5 体育频道", "5+": "CCTV-5+ 体育赛事", "6": "CCTV-6 电影频道",
                "7": "CCTV-7 国防军事", "8": "CCTV-8 电视剧", "10": "CCTV-10 科教频道",
                "11": "CCTV-11 戏曲频道", "12": "CCTV-12 社会与法", "13": "CCTV-13 新闻频道",
                "14": "CCTV-14 少儿频道", "15": "CCTV-15 音乐频道", "16": "CCTV-16 奥林匹克",
                "17": "CCTV-17 农业农村"
            }
            if num in cctv_map:
                return cctv_map[num]
            else:
                return f"CCTV-{num}"
                
    # 【常规区】：其他频道剔除杂乱后缀
    noise_words = ['HD', 'FHD', 'SD', 'BD', '1080P', '4K', '8K', '高清', '超清', '标清', '蓝光', '频道', '综合', '测试', '线路', 'VIP']
    for word in noise_words:
        name_upper = name_upper.replace(word, '')
        
    name_upper = re.sub(r'[\s\-_\[\]\(\)（）【】]', '', name_upper)
        
    if "卫视" in name_upper:
        weishi_match = re.search(r'(.{2,4}卫视)', name_upper)
        if weishi_match: return weishi_match.group(1)
            
    return name_upper

def is_adult_channel(name):
    name_upper = name.upper()
    if re.search(r'(?:^|[^A-Z])(ADULT|XXX|18\+|AV|HENTAI|PORN|SUTRA|EROTIC|EROX|HUSTLER|PLAYBOY|PENTHOUSE|MILF|BABES|BRAZZERS|DORCEL|VIVID|REDLIGHT|X-DREAM|XXL)(?:[^A-Z]|$)', name_upper):
        return True
    if any(x in name_upper for x in ["ECOTICA", "EROTA", "EXTASY", "SEXTREME", "PLAYHOUSE"]):
        return True
    zh_keywords = ["松视", "麻豆", "潘多", "潘朵", "一本道", "日本道", "东京热", "加勒比", "千人斩", "寻花", "探花", "玉蒲团", "金瓶梅", "肉蒲团", "艳谭", "人妻", "熟女", "无码", "🔞", "🈲", "春药", "巨乳", "惊艳", "啪啪啪"]
    if any(k in name_upper for k in zh_keywords):
        return True
    return False

def get_group_title(name):
    """🟢 极简大类合并引擎"""
    name_simp = zhconv.convert(name, 'zh-cn').upper()
    
    if is_adult_channel(name_simp): return "成人频道"
    if "娱乐新闻" in name_simp: return "综合文娱"
        
    global_countries = ["CGTN", "国际", "INTERNATIONAL", "GLOBAL", "环球", "半岛", "华文", "唐NTD", "NTD", "阿富汗", "韩国", "新加坡", "芬兰", "西班牙", "俄罗斯", "法国", "德国", "意大利", "英国", "阿拉伯", "印尼", "印度", "荷兰", "卡塔尔", "罗马尼亚", "南非", "美国", "澳洲", "澳大利亚", "巴西", "老挝", "泰国", "伊朗", "智利", "爱尔兰", "哥伦比亚", "哥斯达黎加", "加拿大", "越南", "缅甸", "NHK", "FUJI", "TOKYO", "TBS", "WOWOW", "JAPAN", "KBS", "SBS", "MBC", "TVN", "KOREA", "ASTRO", "STARHUB", "HBO", "NETFLIX", "BBC", "CNN", "FOX", "SKY", "ESPN"]
    if any(x in name_simp for x in global_countries): return "国际频道"
        
    if "CCTV" in name_simp or "中央" in name_simp: return "央视频道"
    if "卫视" in name_simp: return "卫视频道"
    if any(x in name_simp for x in ["香港", "台湾", "大力",  "澳门", "HK", "TW", "MACAU", "TVB", "翡翠", "凤凰", "台视", "华视", "民视", "三立", "东森", "中天", "纬来", "非凡", "靖天", "大爱", "年代", "澳亚", "莲花", "中旺", "大力", "唯心", "美亚", "明珠", "明珠台", "有线"]): return "港澳台频道"

    for prov in PROVINCE_WEIGHT.keys():
        if prov in name_simp: return f"{prov}频道"
    for city, prov in CITY_MAPPING.items():
        if city in name_simp: return f"{prov}频道"
    
    if any(x in name_simp for x in ["新闻", "NEWS", "资讯", "早班车", "看东方", "财经", "经济", "股市", "理财"]): return "新闻资讯"
    if any(x in name_simp for x in ["电影", "天映",  "天映经典", "影院", "影迷", "MOVIE", "CINEMA", "大片", "邵氏", "龙华", "好莱坞", "剧", "电视剧", "剧场"]): return "影视频道"
    if any(x in name_simp for x in ["体育", "SPORTS", "足球", "NBA", "CBA", "台球", "高尔夫", "奥运", "红牛", "垂钓", "电竞"]): return "体育频道"
    if any(x in name_simp for x in ["少儿", "动漫", "卡通", "动画", "CARTOON", "KIDS", "炫动", "宝宝"]): return "少儿频道"
    if any(x in name_simp for x in ["教育", "CETV", "公开课", "课堂", "纪录", "纪实", "地理", "DISCOVERY", "HISTORY", "通史", "历史", "文化", "人文", "兵器", "科教", "文物"]): return "科教纪录"
    if any(x in name_simp for x in ["戏曲", "梨园", "京剧", "越剧", "音乐", "MTV", "MUSIC", "演唱会", "生活", "健康", "养生", "美食", "重温经典", "农牧", "娱乐", "综艺", "休闲", "游戏"]): return "综合文娱"

    if len(name_simp) >= 2 and not any(char in name_simp for char in ["频", "道", "台", "测", "试"]):
         return "其他频道"
         
    return "其他频道"

def custom_sort_key(item):
    name = item["name"]
    group = item["group"]
    cat_weight = CATEGORY_WEIGHT.get(group, 99)
    prov_weight = 999
    
    prov_name = group.replace("频道", "")
    if prov_name in PROVINCE_WEIGHT:
        cat_weight = 50 
        prov_weight = PROVINCE_WEIGHT[prov_name]
        
    cctv_weight = 999
    if group == "央视频道":
        match = re.search(r'CCTV-(\d+\+?|4K|8K)', name)
        if match:
            m = match.group(1)
            if m == "5+": cctv_weight = 5.5
            elif m == "4K": cctv_weight = 900
            elif m == "8K": cctv_weight = 901
            elif m.isdigit(): cctv_weight = int(m)
            else: cctv_weight = 990
                    
    sort_name = re.sub(r'\d+', lambda x: x.group().zfill(3), name)
    return (cat_weight, prov_weight, cctv_weight, sort_name, item.get("delay", 9999))

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
    search_url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=3" 
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(search_url, headers=headers, timeout=10) as res:
                if res.status != 200: return collected
                data = await res.json()
                repos = data.get("items", [])
                
            for repo in repos:
                repo_name = repo["full_name"]
                default_branch = repo["default_branch"]
                
                tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{default_branch}?recursive=1"
                async with session.get(tree_url, headers=headers, timeout=10) as tree_res:
                    if tree_res.status != 200: continue
                    tree_data = await tree_res.json()
                    tree = tree_data.get("tree", [])
                    
                m3u_files = [item["path"] for item in tree if str(item["path"]).lower().endswith(".m3u")]
                for path in m3u_files[:2]: 
                    raw_url = f"https://raw.githubusercontent.com/{repo_name}/{default_branch}/{path}"
                    try:
                        async with session.get(raw_url, timeout=15) as raw_res:
                            if raw_res.status == 200:
                                text = await raw_res.text()
                                collected.extend(parse_content(text))
                    except: pass
        except: pass
            
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
        top_sources = sources[:MAX_RETAIN_PER_CHANNEL]
        
        best_delay = top_sources[0]["delay"]
        best_res = top_sources[0]["res"]
        
        final_list.append({
            "name": name,
            "group": group_title,
            "top_sources": top_sources, 
            "delay": best_delay,
            "res": best_res
        })
            
    final_list.sort(key=custom_sort_key)
        
    # ================= 写入 M3U 文件 =================
  
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            lock_tag = ' tvg-lock="1"' if item["group"] == "成人频道" else ""
            
            # 🟢 精简修改：去除了 [{item['res']}]，只保留频道名称和 (延时ms)
            display_name = f"{item['name']} ({item['delay']}ms)"
            
            for s in item["top_sources"]:
                f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{item["group"]}"{lock_tag},{display_name}\n')
                f.write(f'{s["url"]}\n')
            
    # ================= 写入 TXT 文件 =================
    txt_dict = {}
    for item in final_list:
        txt_dict.setdefault(item["group"], []).append(item)
        
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        for group, items in txt_dict.items():
            f.write(f"{group},#genre#\n")
            for item in items:
                merged_url = "#".join([s["url"] for s in item["top_sources"]])
                f.write(f"{item['name']},{merged_url}\n")
            
    print("\n🎉 自动化脚本已应用央视/CGTN官方规范定名，圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
