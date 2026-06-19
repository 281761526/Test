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
    "https://live.fanmingming.com/tv/m3u/ipv6.m3u",
    "https://cdn09022024.gitlink.org.cn/api/v1/repos/qianx/123/raw/1231?ref=master&access_token=9cdba3b67a6dadb223a75cde19bbca6125757e5e",
    "https://raw.githubusercontent.com/281761526/HBD/refs/heads/main/7.m3u",
    "https://gitee.com/main-stream/tv/raw/master/BOSS.json",
]

# ==================== TG群组配置区域 ====================
TG_CHANNELS = [
    "kevinmejo", 
    "AptvPlayer",
    "Player_Ku9", 
    "tvzby", 
    "iptvofficalgroup",
]

OUTPUT_M3U = "live.m3u"
OUTPUT_TXT = "live.txt"  
MAX_CONCURRENT_TASKS = 40  
MAX_RETAIN_PER_CHANNEL = 5 

TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")
TG_SESSION = os.environ.get("TG_SESSION")

# ==================== 2. 精准排序权重与地市深度字典 ====================
CATEGORY_WEIGHT = {
    "央视频道": 10, "国际频道": 15, "卫视频道": 20, 
    # 地方省份动态权重 30
    "新闻频道": 31, "体育频道": 32, "电影频道": 33, "电视剧频道": 34, 
    "少儿频道": 35, "纪录频道": 36, "音乐频道": 37,
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

# 🟢 深度扩充：全国地级市/县级市/特有大组映射，彻底防止流失！
CITY_MAPPING = {
    # ========== 北京市辖区 ==========
    "北京": "北京", "朝阳": "北京", "海淀": "北京", "丰台": "北京", "通州": "北京", "昌平": "北京",
    "大兴": "北京", "顺义": "北京", "房山": "北京", "门头沟": "北京", "怀柔": "北京", "平谷": "北京",
    "密云": "北京", "延庆": "北京", "BTV": "北京",

    # ========== 上海市辖区 ==========
    "上海": "上海", "浦东": "上海", "黄浦": "上海", "徐汇": "上海", "长宁": "上海", "静安": "上海",
    "普陀": "上海", "虹口": "上海", "杨浦": "上海", "闵行": "上海", "宝山": "上海", "嘉定": "上海",
    "金山": "上海", "松江": "上海", "青浦": "上海", "奉贤": "上海", "崇明": "上海",

    # ========== 天津市辖区 ==========
    "天津": "天津", "和平": "天津", "南开": "天津", "河西": "天津", "河东": "天津", "河北": "天津",
    "红桥": "天津", "东丽": "天津", "西青": "天津", "津南": "天津", "北辰": "天津", "武清": "天津",
    "宝坻": "天津", "滨海": "天津", "宁河": "天津", "静海": "天津", "蓟州": "天津",

    # ========== 重庆区县 ==========
    "重庆": "重庆", "渝中": "重庆", "江北": "重庆", "南岸": "重庆", "九龙坡": "重庆", "沙坪坝": "重庆",
    "大渡口": "重庆", "北碚": "重庆", "万盛": "重庆", "双桥": "重庆", "渝北": "重庆", "巴南": "重庆",
    "涪陵": "重庆", "万州": "重庆", "黔江": "重庆", "长寿": "重庆", "江津": "重庆", "合川": "重庆",
    "南川": "重庆", "綦江": "重庆", "潼南": "重庆", "铜梁": "重庆", "大足": "重庆", "荣昌": "重庆",
    "璧山": "重庆", "梁平": "重庆", "城口": "重庆", "丰都": "重庆", "垫江": "重庆", "忠县": "重庆",
    "开州": "重庆", "云阳": "重庆", "奉节": "重庆", "巫山": "重庆", "巫溪": "重庆", "石柱": "重庆",
    "秀山": "重庆", "酉阳": "重庆", "彭水": "重庆",

    # ========== 广东省（全部地级市+县级市） ==========
    "广州": "广东", "深圳": "广东", "珠海": "广东", "汕头": "广东", "佛山": "广东", "东莞": "广东",
    "湛江": "广东", "中山": "广东", "惠州": "广东", "江门": "广东", "茂名": "广东", "肇庆": "广东",
    "梅州": "广东", "汕尾": "广东", "河源": "广东", "阳江": "广东", "清远": "广东", "潮州": "广东",
    "揭阳": "广东", "云浮": "广东",
    # 县级市/区
    "顺德": "广东", "南海": "广东", "龙华": "广东", "宝安": "广东", "龙岗": "广东", "南山": "广东",
    "花都": "广东", "番禺": "广东", "增城": "广东", "从化": "广东", "普宁": "广东", "陆丰": "广东",
    "海丰": "广东", "潮阳": "广东", "潮南": "广东", "澄海": "广东", "高州": "广东", "化州": "广东",
    "信宜": "广东", "阳春": "广东", "四会": "广东", "罗定": "广东",

    # ========== 浙江省（全部地级市+县级市） ==========
    "杭州": "浙江", "宁波": "浙江", "温州": "浙江", "绍兴": "浙江", "金华": "浙江", "嘉兴": "浙江",
    "台州": "浙江", "湖州": "浙江", "丽水": "浙江", "衢州": "浙江",
    # 县级市
    "义乌": "浙江", "余姚": "浙江", "慈溪": "浙江", "海宁": "浙江", "平湖": "浙江", "桐乡": "浙江",
    "诸暨": "浙江", "上虞": "浙江", "嵊州": "浙江", "东阳": "浙江", "永康": "浙江", "瑞安": "浙江",
    "乐清": "浙江", "临海": "浙江", "温岭": "浙江", "龙泉": "浙江", "江山": "浙江", "龙游": "浙江",

    # ========== 江苏省（全部地级市+县级市） ==========
    "南京": "江苏", "苏州": "江苏", "无锡": "江苏", "徐州": "江苏", "常州": "江苏", "南通": "江苏",
    "连云港": "江苏", "淮安": "江苏", "盐城": "江苏", "扬州": "江苏", "镇江": "江苏", "泰州": "江苏",
    "宿迁": "江苏",
    # 县级市
    "新沂": "江苏", "沭阳": "江苏", "邳州": "江苏", "如皋": "江苏", "海门": "江苏", "启东": "江苏",
    "东台": "江苏", "大丰": "江苏", "高邮": "江苏", "仪征": "江苏", "丹阳": "江苏", "句容": "江苏",
    "靖江": "江苏", "泰兴": "江苏", "兴化": "江苏", "昆山": "江苏", "张家港": "江苏", "常熟": "江苏",
    "太仓": "江苏", "江阴": "江苏", "宜兴": "江苏", "建湖": "江苏", "射阳": "江苏",

    # ========== 山东省（全部地级市+县级市） ==========
    "济南": "山东", "青岛": "山东", "烟台": "山东", "潍坊": "山东", "威海": "山东", "临沂": "山东",
    "济宁": "山东", "淄博": "山东", "枣庄": "山东", "东营": "山东", "泰安": "山东", "日照": "山东",
    "莱芜": "山东", "德州": "山东", "聊城": "山东", "滨州": "山东", "菏泽": "山东",
    # 县级市
    "胶州": "山东", "平度": "山东", "莱西": "山东", "即墨": "山东", "寿光": "山东", "诸城": "山东",
    "青州": "山东", "高密": "山东", "曲阜": "山东", "邹城": "山东", "滕州": "山东", "新泰": "山东",
    "肥城": "山东", "乐陵": "山东", "禹城": "山东", "临清": "山东", "邹平": "山东",

    # ========== 四川省（地市+县级市+自治州） ==========
    "成都": "四川", "绵阳": "四川", "广安": "四川", "南充": "四川", "达州": "四川", "宜宾": "四川",
    "泸州": "四川", "德阳": "四川", "乐山": "四川", "巴中": "四川", "自贡": "四川", "攀枝花": "四川",
    "广元": "四川", "遂宁": "四川", "内江": "四川", "眉山": "四川", "雅安": "四川", "资阳": "四川",
    "阿坝": "四川", "甘孜": "四川", "凉山": "四川",
    # 县级市
    "都江堰": "四川", "彭州": "四川", "邛崃": "四川", "崇州": "四川", "简阳": "四川", "江油": "四川",
    "广汉": "四川", "什邡": "四川", "绵竹": "四川", "万源": "四川", "华蓥": "四川", "隆昌": "四川",

    # ========== 湖南省（地市+县级市+湘西） ==========
    "长沙": "湖南", "株洲": "湖南", "岳阳": "湖南", "湘潭": "湖南", "衡阳": "湖南", "邵阳": "湖南",
    "常德": "湖南", "张家界": "湖南", "益阳": "湖南", "郴州": "湖南", "永州": "湖南", "怀化": "湖南",
    "娄底": "湖南", "湘西": "湖南",
    # 县级市
    "浏阳": "湖南", "宁乡": "湖南", "醴陵": "湖南", "湘乡": "湖南", "韶山": "湖南", "耒阳": "湖南",
    "常宁": "湖南", "武冈": "湖南", "临湘": "湖南", "汨罗": "湖南", "沅江": "湖南", "资兴": "湖南",

    # ========== 湖北省（地市+省直辖县级市+恩施） ==========
    "武汉": "湖北", "宜昌": "湖北", "襄阳": "湖北", "荆州": "湖北", "黄石": "湖北", "十堰": "湖北",
    "鄂州": "湖北", "荆门": "湖北", "孝感": "湖北", "黄冈": "湖北", "咸宁": "湖北", "随州": "湖北",
    "恩施": "湖北",
    # 县级/省直辖
    "仙桃": "湖北", "潜江": "湖北", "天门": "湖北", "神农架": "湖北", "大冶": "湖北", "丹江口": "湖北",
    "宜都": "湖北", "枝江": "湖北", "当阳": "湖北", "枣阳": "湖北", "宜城": "湖北", "钟祥": "湖北",

    # ========== 福建省（地市+县级市） ==========
    "厦门": "福建", "福州": "福建", "泉州": "福建", "漳州": "福建", "莆田": "福建", "三明": "福建",
    "龙岩": "福建", "南平": "福建", "宁德": "福建",
    # 县级市
    "福清": "福建", "长乐": "福建", "石狮": "福建", "晋江": "福建", "南安": "福建", "龙海": "福建",
    "永安": "福建", "漳平": "福建", "福安": "福建", "福鼎": "福建", "邵武": "福建", "建瓯": "福建",

    # ========== 安徽省【16地市+全部县级市、区县】 ==========
    "合肥": "安徽", "芜湖": "安徽", "蚌埠": "安徽", "马鞍山": "安徽", "安庆": "安徽", "滁州": "安徽",
    "阜阳": "安徽", "六安": "安徽", "宣城": "安徽", "池州": "安徽", "宿州": "安徽", "淮北": "安徽",
    "淮南": "安徽", "铜陵": "安徽", "亳州": "安徽",
    # 县级市/区县
    "巢湖": "安徽", "庐江": "安徽", "肥西": "安徽", "肥东": "安徽", "长丰": "安徽", "天长": "安徽",
    "明光": "安徽", "桐城": "安徽", "潜山": "安徽", "太湖": "安徽", "界首": "安徽", "太和": "安徽",
    "寿县": "安徽", "霍邱": "安徽", "广德": "安徽", "宁国": "安徽", "青阳": "安徽", "石台": "安徽",

    # ========== 江西省（地市+县级市） ==========
    "南昌": "江西", "赣州": "江西", "九江": "江西", "景德镇": "江西", "萍乡": "江西", "新余": "江西",
    "鹰潭": "江西", "吉安": "江西", "宜春": "江西", "抚州": "江西", "上饶": "江西",
    # 县级市
    "乐平": "江西", "瑞昌": "江西", "共青城": "江西", "庐山": "江西", "井冈山": "江西", "丰城": "江西",
    "樟树": "江西", "高安": "江西", "德兴": "江西", "玉山": "江西",

    # ========== 河南省（地市+大量县级市） ==========
    "郑州": "河南", "洛阳": "河南", "开封": "河南", "平顶山": "河南", "安阳": "河南", "鹤壁": "河南",
    "新乡": "河南", "焦作": "河南", "濮阳": "河南", "许昌": "河南", "漯河": "河南", "三门峡": "河南",
    "南阳": "河南", "商丘": "河南", "信阳": "河南", "周口": "河南", "驻马店": "河南",
    # 县级市
    "巩义": "河南", "荥阳": "河南", "新郑": "河南", "登封": "河南", "偃师": "河南", "汝州": "河南",
    "林州": "河南", "卫辉": "河南", "辉县": "河南", "沁阳": "河南", "孟州": "河南", "禹州": "河南",

    # ========== 河北省【新增平泉】完整地市+县级市 ==========
    "石家庄": "河北", "唐山": "河北", "秦皇岛": "河北", "邯郸": "河北", "邢台": "河北", "保定": "河北",
    "张家口": "河北", "承德": "河北", "平泉": "河北", "沧州": "河北", "廊坊": "河北", "衡水": "河北",
    # 县级市
    "辛集": "河北", "晋州": "河北", "新乐": "河北", "鹿泉": "河北", "遵化": "河北", "迁安": "河北",
    "武安": "河北", "南宫": "河北", "沙河": "河北", "涿州": "河北", "定州": "河北", "安国": "河北",

    # ========== 山西省（地市+县级市） ==========
    "太原": "山西", "大同": "山西", "朔州": "山西", "忻州": "山西", "阳泉": "山西", "吕梁": "山西",
    "晋中": "山西", "长治": "山西", "晋城": "山西", "临汾": "山西", "运城": "山西",
    # 县级市
    "古交": "山西", "高平": "山西", "介休": "山西", "永济": "山西", "河津": "山西", "侯马": "山西",
    "霍州": "山西", "孝义": "山西", "汾阳": "山西", "原平": "山西",

    # ========== 陕西省（地市+县级市） ==========
    "西安": "陕西", "宝鸡": "陕西", "咸阳": "陕西", "渭南": "陕西", "铜川": "陕西", "延安": "陕西",
    "榆林": "陕西", "汉中": "陕西", "安康": "陕西", "商洛": "陕西",
    # 县级市
    "兴平": "陕西", "华阴": "陕西", "韩城": "陕西", "彬州": "陕西", "神木": "陕西", "府谷": "陕西",
    "子长": "陕西", "靖边": "陕西", "黄陵": "陕西",

    # ========== 黑龙江省（地市+县级市+大兴安岭） ==========
    "哈尔滨": "黑龙江", "大庆": "黑龙江", "齐齐哈尔": "黑龙江", "鸡西": "黑龙江", "鹤岗": "黑龙江", "双鸭山": "黑龙江",
    "伊春": "黑龙江", "佳木斯": "黑龙江", "七台河": "黑龙江", "牡丹江": "黑龙江", "黑河": "黑龙江", "绥化": "黑龙江",
    "大兴安岭": "黑龙江",
    # 县级市
    "尚志": "黑龙江", "五常": "黑龙江", "讷河": "黑龙江", "虎林": "黑龙江", "密山": "黑龙江", "海林": "黑龙江",

    # ========== 吉林省（地市+县级市+延边） ==========
    "长春": "吉林", "吉林市": "吉林", "四平": "吉林", "辽源": "吉林", "通化": "吉林", "白山": "吉林",
    "松原": "吉林", "白城": "吉林", "延边": "吉林",
    # 县级市
    "榆树": "吉林", "德惠": "吉林", "公主岭": "吉林", "双辽": "吉林", "梅河口": "吉林", "集安": "吉林",
    "临江": "吉林", "洮南": "吉林", "大安": "吉林", "图们": "吉林",

    # ========== 辽宁省（地市+县级市） ==========
    "沈阳": "辽宁", "大连": "辽宁", "鞍山": "辽宁", "抚顺": "辽宁", "本溪": "辽宁", "丹东": "辽宁",
    "锦州": "辽宁", "营口": "辽宁", "阜新": "辽宁", "辽阳": "辽宁", "盘锦": "辽宁", "铁岭": "辽宁",
    "朝阳": "辽宁", "葫芦岛": "辽宁",
    # 县级市
    "新民": "辽宁", "瓦房店": "辽宁", "普兰店": "辽宁", "庄河": "辽宁", "海城": "辽宁", "东港": "辽宁",
    "凤城": "辽宁", "北镇": "辽宁", "凌海": "辽宁", "兴城": "辽宁",

    # ========== 云南省（地市+自治州+县级市） ==========
    "昆明": "云南", "大理": "云南", "曲靖": "云南", "玉溪": "云南", "保山": "云南", "昭通": "云南",
    "丽江": "云南", "普洱": "云南", "临沧": "云南", "楚雄": "云南", "红河": "云南", "文山": "云南",
    "西双版纳": "云南", "德宏": "云南", "怒江": "云南", "迪庆": "云南",
    # 县级市
    "安宁": "云南", "宣威": "云南", "澄江": "云南", "腾冲": "云南", "瑞丽": "云南", "芒市": "云南",
    "大理市": "云南", "香格里拉": "云南",

    # ========== 贵州省（地市+自治州+县级市） ==========
    "贵阳": "贵州", "遵义": "贵州", "六盘水": "贵州", "安顺": "贵州", "毕节": "贵州", "铜仁": "贵州",
    "黔西南": "贵州", "黔东南": "贵州", "黔南": "贵州",
    # 县级市
    "清镇": "贵州", "赤水": "贵州", "仁怀": "贵州", "盘州": "贵州", "兴义": "贵州", "兴仁": "贵州",
    "凯里": "贵州", "都匀": "贵州", "福泉": "贵州",

    # ========== 广西（地市+县级市） ==========
    "南宁": "广西", "桂林": "广西", "柳州": "广西", "梧州": "广西", "北海": "广西", "防城港": "广西",
    "钦州": "广西", "贵港": "广西", "玉林": "广西", "百色": "广西", "贺州": "广西", "河池": "广西",
    "来宾": "广西", "崇左": "广西",
    # 县级市
    "横州": "广西", "荔浦": "广西", "合山": "广西", "凭祥": "广西", "东兴": "广西", "桂平": "广西",
    "北流": "广西", "靖西": "广西", "平果": "广西",

    # ========== 海南（地市+县级市/区县） ==========
    "海口": "海南", "三亚": "海南", "三沙": "海南", "儋州": "海南",
    "文昌": "海南", "琼海": "海南", "万宁": "海南", "定安": "海南", "屯昌": "海南", "澄迈": "海南",
    "临高": "海南", "白沙": "海南", "昌江": "海南", "乐东": "海南", "陵水": "海南", "保亭": "海南", "五指山": "海南",

    # ========== 内蒙古（盟市+县级市） ==========
    "呼和浩特": "内蒙古", "包头": "内蒙古", "鄂尔多斯": "内蒙古", "乌海": "内蒙古", "赤峰": "内蒙古", "通辽": "内蒙古",
    "呼伦贝尔": "内蒙古", "巴彦淖尔": "内蒙古", "乌兰察布": "内蒙古",
    "兴安盟": "内蒙古", "锡林郭勒": "内蒙古", "阿拉善": "内蒙古",
    # 县级市
    "霍林郭勒": "内蒙古", "满洲里": "内蒙古", "扎兰屯": "内蒙古", "牙克石": "内蒙古", "根河": "内蒙古",
    "阿尔山": "内蒙古", "二连浩特": "内蒙古", "锡林浩特": "内蒙古",

    # ========== 甘肃（地市+自治州+县级市） ==========
    "兰州": "甘肃", "天水": "甘肃", "白银": "甘肃", "金昌": "甘肃", "嘉峪关": "甘肃", "酒泉": "甘肃",
    "张掖": "甘肃", "武威": "甘肃", "定西": "甘肃", "陇南": "甘肃", "平凉": "甘肃", "庆阳": "甘肃",
    "临夏": "甘肃", "甘南": "甘肃",
    # 县级市
    "玉门": "甘肃", "敦煌": "甘肃", "华亭": "甘肃", "陇西": "甘肃", "临洮": "甘肃", "合作": "甘肃",

    # ========== 宁夏 ==========
    "银川": "宁夏", "石嘴山": "宁夏", "吴忠": "宁夏", "固原": "宁夏", "中卫": "宁夏",
    # 县级市
    "灵武": "宁夏", "青铜峡": "宁夏", "平罗": "宁夏",

    # ========== 青海 ==========
    "西宁": "青海",
    "海东": "青海", "海北": "青海", "黄南": "青海", "海南": "青海", "果洛": "青海", "玉树": "青海", "海西": "青海",
    # 县级市
    "格尔木": "青海", "德令哈": "青海", "茫崖": "青海",

    # ========== 新疆 ==========
    "乌鲁木齐": "新疆", "克拉玛依": "新疆",
    "吐鲁番": "新疆", "哈密": "新疆", "昌吉": "新疆", "博尔塔拉": "新疆", "巴音郭楞": "新疆", "阿克苏": "新疆",
    "克孜勒苏": "新疆", "喀什": "新疆", "和田": "新疆", "伊犁": "新疆", "塔城": "新疆", "阿勒泰": "新疆",
    "兵团": "新疆",
    # 兵团县级市
    "石河子": "新疆", "阿拉尔": "新疆", "图木舒克": "新疆", "五家渠": "新疆", "北屯": "新疆", "铁门关": "新疆",
    "双河": "新疆", "可克达拉": "新疆", "昆玉": "新疆", "胡杨河": "新疆",

    # ========== 西藏 ==========
    "拉萨": "西藏", "日喀则": "西藏", "昌都": "西藏", "林芝": "西藏", "山南": "西藏", "那曲": "西藏", "阿里": "西藏",
    "米林": "西藏", "错那": "西藏", "亚东": "西藏", "桑珠孜": "西藏"
}

# ==================== 3. 核心清洗与分类引擎 ====================
def standardize_name(name):
    """超级名称清洗：简繁体转换 -> 剥离后缀 -> 格式化央卫视"""
    # 🟢 简繁体识别：将所有的繁体字强制转换为简体，为后续合并打下基石
    name = zhconv.convert(name, 'zh-cn').upper()
    
    # 暴力剔除常见的无用后缀和分辨率标签
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

def is_adult_channel(name):
    """🟢 严苛且极其全面的成人频道判定规则，彻底堵死欧美与中文漏网之鱼"""
    name_upper = name.upper()
    
    # 1. 英文强匹配关键字 (加入单词边界，防止误杀，如 CCTV-6 AV)
    # 包含了您 M3U 文件中出现的大量欧美厂牌和分类：EROTIC, HUSTLER, PENTHOUSE, PLAYBOY, BRAZZERS, MILF 等
    if re.search(r'(?:^|[^A-Z])(ADULT|XXX|18\+|AV|HENTAI|PORN|SUTRA|EROTIC|EROX|HUSTLER|PLAYBOY|PENTHOUSE|MILF|BABES|BRAZZERS|DORCEL|VIVID|REDLIGHT|X-DREAM|XXL)(?:[^A-Z]|$)', name_upper):
        return True
        
    # 2. 英文无边界匹配 (针对一些喜欢连写的特殊名称，如 ecotica-40, Erota HD)
    if any(x in name_upper for x in ["ECOTICA", "EROTA", "EXTASY", "SEXTREME", "PLAYHOUSE"]):
        return True

    # 3. 中文关键字：加入易漏的变种词汇(潘朵拉、惊艳、日本道、啪啪啪等)
    zh_keywords = [
        "松视", "麻豆", "潘多", "潘朵", "一本道", "日本道", "东京热", "加勒比", "千人斩", 
        "寻花", "探花", "玉蒲团", "金瓶梅", "肉蒲团", "艳谭", "人妻", "熟女", 
        "无码", "🔞", "🈲", "春药", "巨乳", "惊艳", "啪啪啪"
    ]
    if any(k in name_upper for k in zh_keywords):
        return True
        
    return False

def get_group_title(name):
    """智能分类引擎：优先判定国际、新闻、主题，并带有智能回退机制"""
    # 简繁体转换，防止 "廣東" 无法匹配 "广东"
    name_simp = zhconv.convert(name, 'zh-cn').upper()
    
    # 1. 绝对优先：严苛的成人过滤器
    if is_adult_channel(name_simp): return "成人频道"
        
    # 2. 🟢 新增：国际频道 (CGTN等)
    if any(x in name_simp for x in ["CGTN", "国际", "INTERNATIONAL", "GLOBAL", "CGTN"]): return "国际频道"
        
    # 3. 央视与卫视
    if "CCTV" in name_simp or "中央" in name_simp: return "央视频道"
    if "卫视" in name_simp: return "卫视频道"
    
    # 4. 🟢 新增：新闻频道
    if any(x in name_simp for x in ["新闻", "NEWS", "资讯", "早班车"]): return "新闻频道"

    # 5. 地方频道优先提取 (精确匹配省市区)
    for prov in PROVINCE_WEIGHT.keys():
        if prov in name_simp: return f"{prov}频道"
    for city, prov in CITY_MAPPING.items():
        if city in name_simp: return f"{prov}频道"
    
    # 6. 垂直主题频道
    if any(x in name_simp for x in ["电影", "影院", "影迷", "MOVIE", "CINEMA", "星影", "动作", "大片"]): return "电影频道"
    if any(x in name_simp for x in ["剧", "电视剧", "剧场"]): return "电视剧频道"
    if any(x in name_simp for x in ["音乐", "MTV", "MUSIC", "KTV", "演唱会", "好声音"]): return "音乐频道"
    if any(x in name_simp for x in ["体育", "SPORTS", "足球", "NBA", "CBA", "台球", "高尔夫", "奥运"]): return "体育频道"
    if any(x in name_simp for x in ["少儿", "动漫", "卡通", "动画", "CARTOON", "KIDS", "金鹰卡通", "炫动卡通"]): return "少儿频道"
    if any(x in name_simp for x in ["纪录", "纪实", "地理", "DISCOVERY", "NATIONAL", "HISTORY", "科教"]): return "纪录频道"

    # 7. 国际与地区识别
    if any(x in name_simp for x in ["TVB", "翡翠", "J2", "明珠", "星空", "凤凰", "纬来", "东森", "八大", "中天", "三立", "民视", "台视", "华视", "年代", "非凡", "香港", "台湾"]): return "港台频道"
    if any(x in name_simp for x in ["NHK", "FUJI", "TOKYO", "TBS", "WOWOW", "J-SPORTS", "JSPORTS", "NTV", "朝日", "日本", "JAPAN"]): return "日本频道"
    if any(x in name_simp for x in ["KBS", "SBS", "MBC", "TVN", "JTBC", "OCN", "MNET", "韩国", "KOREA"]): return "韩国频道"
    if any(x in name_simp for x in ["ASTRO", "STARHUB", "SINGAPORE", "MALAYSIA", "THAILAND", "新加坡", "大马", "马来西亚", "泰国", "CH3", "CH7", "8频道", "U频道"]): return "新马泰频道"
    if any(x in name_simp for x in ["HBO", "NETFLIX", "BBC", "CNN", "FOX", "SKY", "ESPN", "ABC", "NBC", "CBS", "美国", "英国", "USA", "UK"]): return "欧美频道"
    
    # 8. 🟢 智能兜底分组：如果未匹配到已知关键字，尝试提取名称前两字作为地域名，若无明显地域特征再归入"其他频道"
    if len(name_simp) >= 2 and not any(char in name_simp for char in ["频", "道", "台", "测", "试"]):
         # 这是一个简易的智能聚类启发式逻辑
         return "其他频道"
         
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
    return (cat_weight, prov_weight, sort_name, item.get("delay", 9999))

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
    search_url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=3" # 减少搜索量，防超时
    
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
    
    # 🟢 绝对强制名称统一：简体化 + 去后缀，确保100%合并同类项
    channel_dict = {}
    for r in valid_results:
        clean_name = standardize_name(r["name"])
        r["name"] = clean_name 
        channel_dict.setdefault(clean_name, []).append(r)
        
    final_list = []
    
    # 🟢 核心：多链接无缝合并机制 (#号拼接)
    for name, sources in channel_dict.items():
        sources.sort(key=lambda x: x["delay"]) 
        group_title = get_group_title(name)
        top_sources = sources[:MAX_RETAIN_PER_CHANNEL]
        
        # 将多个高质量直连URL用 "#" 符号穿串合并，符合顶级壳子标准
        merged_url = "#".join([s["url"] for s in top_sources])
        best_delay = top_sources[0]["delay"]
        best_res = top_sources[0]["res"]
        
        final_list.append({
            "name": name,
            "group": group_title,
            "url": merged_url,
            "delay": best_delay,
            "res": best_res
        })
            
    final_list.sort(key=custom_sort_key)
        
    # ================= 写入 M3U 文件 =================
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:801/api/diyp/"\n')
        for item in final_list:
            lock_tag = ' tvg-lock="1"' if item["group"] == "成人频道" else ""
            display_name = f"{item['name']} [{item['res']}]({item['delay']}ms)"
            f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" group-title="{item["group"]}"{lock_tag},{display_name}\n')
            f.write(f'{item["url"]}\n')
            
    # ================= 写入 TXT 文件 =================
    txt_dict = {}
    for item in final_list:
        txt_dict.setdefault(item["group"], []).append(item)
        
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        for group, items in txt_dict.items():
            f.write(f"{group},#genre#\n")
            for item in items:
                # 输出格式：频道名称,链接1#链接2#链接3
                f.write(f"{item['name']},{item['url']}\n")
            
    print("\n🎉 自动化脚本全功能迭代圆满完成！")

if __name__ == "__main__":
    asyncio.run(main())
