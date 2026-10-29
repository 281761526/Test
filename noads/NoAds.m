// =============================================================================
//  NoAds.m — 喜马拉雅 (com.gemd.iting) 9.5.13 全量去广告补丁
//  v1.2：新增 XMAd* 前缀（+162 自研广告类，含播放页信息流/解锁/激励视频）、
//        12 项排除表保住 XMAdd*/通讯录等功能类、8 个喜马拉雅自有广告域
//  v1.1：21 前缀 352 类
//  ---------------------------------------------------------------------------
//  配套：脱壳修复版主二进制（链接修复，见交付说明）
//  加载：LC_LOAD_WEAK_DYLIB @executable_path/NoAds.dylib
//        （TrollFools 注入或 inject_noads.py 打包均可）
//
//  三层拦截：
//    Tier 1  网络汇沉点 —— NSURLSession 4 个 dataTask 入口，广告域名请求
//            重定向到 http://127.0.0.1:9/nadsink（discard 端口，必然失败）
//    Tier 2  类中和 —— 按前缀/精确名匹配全部广告类，所有自有方法（类方法+
//            实例方法）替换为按返回类型编码选定的空实现 trampoline
//    Tier 3  开屏推送链特杀 —— XMLaunchAd* / TADSplash* / TMEAdSplash* /
//            TGGDTPreloadSplash* 等预加载调度类整类中和，开屏广告在
//            "拉取→缓存→选中→展示" 全链路上任一环直接断链
//
//  开关：defaults write com.gemd.iting nad_disabled -bool YES   （关闭补丁）
//        defaults write com.gemd.iting nad_disabled -bool NO    （恢复补丁）
//  日志：idevicesyslog | grep NoAds
//
//  云编译：见 .github/workflows/build.yml（GitHub Actions macos-14 免费云 Mac）
//  本地编译：
//    xcrun -sdk iphoneos clang -arch arm64 -miphoneos-version-min=13.0 \
//      -dynamiclib -fobjc-arc -O2 \
//      -framework Foundation -framework UIKit \
//      -install_name "@executable_path/NoAds.dylib" \
//      -o NoAds.dylib NoAds.m
//    codesign --force --sign - NoAds.dylib
// =============================================================================

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dispatch/dispatch.h>

#pragma mark - 配置区（改这里即可增删目标）

// ---- Tier 2 前缀命中：名称以这些前缀开头的类 = 广告类，整类中和 ----
static const char *NAD_neuterPrefixes[] = {
    // 优量汇 GDT（腾讯广告）开屏链
    "GDTSplash",
    "TGGDTSplash",
    "TGGDTPreloadSplash",
    // 穿山甲 CSJ / 巨量 BU
    "CSJSplash",
    "CSJADLoadSplash",
    "BUSplash",
    // 百度
    "BaiduMobAdSplash",
    // 京东 JAD
    "JADSplash",
    // 腾讯音乐 TME 广告中台（含 TAD 数据层、AMS 联合广告）
    "TMEAdSplash",
    "TMEAdOperateSplash",
    "TADSplash",
    "AMS",
    // 喜马拉雅自研：五家 SDK 的壳类（开屏具体实现）
    "XMGDTSplashAd",
    "XMBUSplashAd",
    "XMBaiduSplashAd",
    "XMTMESplashAd",
    "XMJADSplashAd",
    // 喜马拉雅自研：开屏广告推送/预加载调度链（闪屏核心）
    "XMLaunchAd",
    "XMLaunchInteractAd",
    "XMLaunchVoiceAd",
    // 喜马拉雅自研广告内核（XMIAd* 全家 = 请求/竞价/曝光/展示/上报）
    "XMIAd",
    // 喜马拉雅自研广告全家桶 v1.2：XMAd* 162 类（播放页信息流/解锁页/
    // 激励视频/换肤/会员推广弹窗/GX 模板渲染）。XMAdd*/XMAddress 等
    // 非广告类由 NAD_excludeClasses 排除
    "XMAd",
};
static const int NAD_neuterPrefixCount =
    (int)(sizeof(NAD_neuterPrefixes) / sizeof(NAD_neuterPrefixes[0]));

// ---- 前缀命中的排除表：名字以这些前缀开头 = 非广告功能类，绝不动 ----
// XMAdd* 是"添加"功能（闹钟/播放列表/评论/好友），XMAddress* 通讯录，
// XMAdminCell/XMAdvancedQueue 与广告无关
static const char *NAD_excludeClasses[] = {
    "XMAddAlarmClock",
    "XMAddAlbumItemCell",
    "XMAddCommentViewController",
    "XMAddMediaIntentHandler",
    "XMAddSocialFriendViewController",
    "XMAddToHearListPopView",
    "XMAddToPLViewController",
    "XMAddToPlayListPop",
    "XMAddressBook",
    "XMAddressBookHandle",
    "XMAdminCell",
    "XMAdvancedQueue",
};
static const int NAD_excludeClassCount =
    (int)(sizeof(NAD_excludeClasses) / sizeof(NAD_excludeClasses[0]));

// ---- Tier 2 精确命中：不开屏但承载广告请求/竞价/管理的关键类 ----
static const char *NAD_neuterClasses[] = {
    // GDT 请求与奖励
    "GDTAdRequest",
    "GDTRewardVideoConfig",
    "GDTUnifiedNativeRewardAd",
    "GDTTangramUnifiedNativeAdService",
    // TGGDT 封装层
    "TGGDTAdManager",
    "TGGDTAdService",
    "TGGDTAdServiceFetchAdParams",
    "TGGDTAdFrequencyCheckManager",
    "TGGDTLoadAdRequestManager",
    "TGGDTPreloadAdHandler",
    "TGGDTLoadRewardVideoAdHandler",
    // 穿山甲/巨量
    "BUNativeExpressAdManager",
    "BUNativeAdsManager",
    "BUNativeAd",
    "BURewardedVideoModel",
    "CSJAdActionManager",
    // 百度
    "BaiduMobAdSplashRequestInfo",
    "BaiduMobAdSplashSlot",
    // 喜马拉雅自研调度
    "XMAdManager",
    "XMAdSDKManager",
    "XMAdAgent",
    "XMAdController",
    "XMAdLoader",
    "XMAdRequest",
    "XMAdApiAgent",
    "XMAdRewardAdManager",
    // TME 通用
    "TMEAdSDKConfig",
    "TMEAdClickManager",
    "TMEAdCacheManager",
};
static const int NAD_neuterClassCount =
    (int)(sizeof(NAD_neuterClasses) / sizeof(NAD_neuterClasses[0]));

// ---- 中和保护名单：这些方法绝不中和（保对象生命周期/消息转发不崩） ----
static NSString * const NAD_protectedSelectors[] = {
    @"dealloc",
    @"retain",
    @"release",
    @"autorelease",
    @"methodSignatureForSelector:",
    @"forwardInvocation:",
    @"forwardingTargetForSelector:",
    @"doesNotRecognizeSelector:",
    @"copyWithZone:",
    @"mutableCopyWithZone:",
    @"load",   // 已执行，防万一
};

// ---- Tier 1 广告域名黑名单（后缀匹配，自动覆盖所有子域） ----
static const char *NAD_adHosts[] = {
    // 优量汇 GDT（腾讯）
    "gdt.qq.com",
    "gdtms.qq.com",
    "gdtiosf.qq.com",
    // 穿山甲 CSJ / 巨量引擎（字节）
    "csjapi.com",
    "snssdk.com",
    "pstatp.com",
    "pangle.io",
    "pangolin-sdk-toutiao.com",
    "oceanengine.com",
    // 百度
    "mobads.baidu.com",
    "mobads-logs.baidu.com",
    "hmma.baidu.com",
    // 京东 JAD
    "jmad.jd.com",
    "chi.jd.com",
    // 腾讯音乐 TME
    "adstats.tencentmusic.com",
    "ad.tencentmusic.com",
    // 喜马拉雅自有广告域（v1.2：二进制实测命中 + 全环境变体）
    "ad.ximalaya.com",
    "adse.ximalaya.com",
    "adwelfare.ximalaya.com",
    "adbehavior.ximalaya.com",
    "ad-incentive.ximalaya.com",
    // 测试/UAT 环境（开关配置在包里，也一并封掉）
    "ad.test.ximalaya.com",
    "adse.test.ximalaya.com",
    "adse.uat.ximalaya.com",
};
static const int NAD_adHostCount =
    (int)(sizeof(NAD_adHosts) / sizeof(NAD_adHosts[0]));

#define NAD_SINK_URL @"http://127.0.0.1:9/nadsink"

// 日志开关：1 = 打印每次拦截（联调期用），0 = 只打印安装摘要
#define NAD_VERBOSE 0

// =============================================================================

static BOOL NAD_killed(void) {
    return [[NSUserDefaults standardUserDefaults] boolForKey:@"nad_disabled"];
}

#define NADLog(fmt, ...) NSLog(@"[NoAds] " fmt, ##__VA_ARGS__)

static void NADLogHit(NSString *fmt, ...) NS_FORMAT_FUNCTION(1,2);
static void NADLogHit(NSString *fmt, ...) {
#if NAD_VERBOSE
    va_list ap; va_start(ap, fmt);
    NSLog(@"[NoAds] %@", [[NSString alloc] initWithFormat:fmt arguments:ap]);
    va_end(ap);
#else
    (void)fmt;
#endif
}

#pragma mark - Tier 1 · 网络汇沉点

static BOOL NAD_isAdURL(NSURL *url) {
    if (!url) return NO;
    NSString *host = url.host.lowercaseString;
    if (host.length == 0) return NO;
    for (int i = 0; i < NAD_adHostCount; i++) {
        const char *d = NAD_adHosts[i];
        NSString *dom = [NSString stringWithUTF8String:d];
        if ([host isEqualToString:dom] || [host hasSuffix:[@"." stringByAppendingString:dom]]) {
            return YES;
        }
    }
    return NO;
}

@interface NSURLSession (NoAds)
@end

@implementation NSURLSession (NoAds)

// 交换后，原实现挂在 nad_* 名下；命中广告域则改写 URL 到汇沉点再走原实现，
// 产物是一个真实 dataTask —— 它必然连接失败，completionHandler 收到 error，
// SDK 的失败分支被正常触发，不会挂起、不会野指针。

- (NSURLSessionDataTask *)nad_sinkTaskWithRequest:(NSURLRequest *)request
{
    if (NAD_isAdURL(request.URL)) {
        NADLogHit(@"net-block(req): %@", request.URL);
        NSMutableURLRequest *sink =
            request.mutableCopy ?: [NSMutableURLRequest new];
        sink.URL = [NSURL URLWithString:NAD_SINK_URL];
        return [self nad_sinkTaskWithRequest:sink];
    }
    return [self nad_sinkTaskWithRequest:request]; // 原实现
}

- (NSURLSessionDataTask *)nad_sinkTaskWithRequest:(NSURLRequest *)request
                                 completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))handler
{
    if (NAD_isAdURL(request.URL)) {
        NADLogHit(@"net-block(req+h): %@", request.URL);
        NSMutableURLRequest *sink =
            request.mutableCopy ?: [NSMutableURLRequest new];
        sink.URL = [NSURL URLWithString:NAD_SINK_URL];
        return [self nad_sinkTaskWithRequest:sink completionHandler:handler];
    }
    return [self nad_sinkTaskWithRequest:request completionHandler:handler];
}

- (NSURLSessionDataTask *)nad_sinkTaskWithURL:(NSURL *)url
{
    if (NAD_isAdURL(url)) {
        NADLogHit(@"net-block(url): %@", url);
        return [self nad_sinkTaskWithURL:[NSURL URLWithString:NAD_SINK_URL]];
    }
    return [self nad_sinkTaskWithURL:url];
}

- (NSURLSessionDataTask *)nad_sinkTaskWithURL:(NSURL *)url
                            completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))handler
{
    if (NAD_isAdURL(url)) {
        NADLogHit(@"net-block(url+h): %@", url);
        return [self nad_sinkTaskWithURL:[NSURL URLWithString:NAD_SINK_URL]
                       completionHandler:handler];
    }
    return [self nad_sinkTaskWithURL:url completionHandler:handler];
}

@end

static int NAD_installNetworkSink(void)
{
    Class c = [NSURLSession class];
    if (!c) return 0;
    struct { SEL orig; SEL alt; } pairs[] = {
        {@selector(dataTaskWithRequest:),                          @selector(nad_sinkTaskWithRequest:)},
        {@selector(dataTaskWithRequest:completionHandler:),        @selector(nad_sinkTaskWithRequest:completionHandler:)},
        {@selector(dataTaskWithURL:),                              @selector(nad_sinkTaskWithURL:)},
        {@selector(dataTaskWithURL:completionHandler:),            @selector(nad_sinkTaskWithURL:completionHandler:)},
    };
    int n = 0;
    for (unsigned i = 0; i < sizeof(pairs)/sizeof(pairs[0]); i++) {
        Method m1 = class_getInstanceMethod(c, pairs[i].orig);
        Method m2 = class_getInstanceMethod(c, pairs[i].alt);
        if (m1 && m2) { method_exchangeImplementations(m1, m2); n++; }
    }
    return n;
}

#pragma mark - Tier 2 · 类中和（按返回类型编码选空实现）

// arm64 上，固定签名的 C 函数作 IMP 时多出的参数留在寄存器里被忽略，
// 因此只需按「返回值类型编码」分派到 5 个 trampoline：
//   v → void        @ # : ^ → nil(0)      c B → NO(0)
//   i l I L q Q s S → 0                   f d → 0.0
//   { ( (结构体/联合) → 不动，保留原实现并计入 skip

static void   _nad_void_tramp (id self, SEL _cmd)              { (void)self; (void)_cmd; }
static id     _nad_nil_tramp  (id self, SEL _cmd)              { (void)self; (void)_cmd; return nil; }
static BOOL   _nad_no_tramp   (id self, SEL _cmd)              { (void)self; (void)_cmd; return NO; }
static NSInteger _nad_zero_tramp (id self, SEL _cmd)           { (void)self; (void)_cmd; return 0; }
static double _nad_dzero_tramp(id self, SEL _cmd)              { (void)self; (void)_cmd; return 0.0; }

static BOOL NAD_selProtected(SEL sel) {
    NSString *name = NSStringFromSelector(sel);
    for (unsigned i = 0; i < sizeof(NAD_protectedSelectors)/sizeof(NAD_protectedSelectors[0]); i++) {
        if ([name isEqualToString:NAD_protectedSelectors[i]]) return YES;
    }
    return NO;
}

// 返回应替换的 IMP；NULL = 该方法类型未覆盖，保留原实现
static IMP NAD_impForEncoding(const char *enc) {
    if (!enc || !*enc) return NULL;
    // 跳过类型限定符 r n N o O R V
    while (*enc == 'r' || *enc == 'n' || *enc == 'N' ||
           *enc == 'o' || *enc == 'O' || *enc == 'R' || *enc == 'V') enc++;
    switch (*enc) {
        case 'v': return (IMP)_nad_void_tramp;
        case '@': case '#': case ':': case '^': return (IMP)_nad_nil_tramp;
        case 'B': case 'c': return (IMP)_nad_no_tramp;
        case 'i': case 'I': case 'l': case 'L':
        case 'q': case 'Q': case 's': case 'S': return (IMP)_nad_zero_tramp;
        case 'f': case 'd': return (IMP)_nad_dzero_tramp;
        default:  return NULL;   // 结构体 / 联合 / 未知 → 不动
    }
}

// 中和一个类的全部自有方法（实例 + 类方法），返回替换掉的方法数
static int NAD_neuterClass(Class cls, int *skipped) {
    if (!cls) return 0;
    int replaced = 0;
    for (int pass = 0; pass < 2; pass++) {
        Class target   = (pass == 0) ? cls : object_getClass(cls); // 实例方法 / 类方法
        if (!target) continue;
        unsigned int count = 0;
        Method *methods = class_copyMethodList(target, &count);
        for (unsigned int i = 0; i < count; i++) {
            Method m = methods[i];
            SEL sel = method_getName(m);
            if (NAD_selProtected(sel)) continue;
            IMP imp = NAD_impForEncoding(method_getTypeEncoding(m));
            if (!imp) { if (skipped) (*skipped)++; continue; }
            method_setImplementation(m, imp);
            replaced++;
            NADLogHit(@"neutered %@[%@ %@]", pass == 0 ? @"-" : @"+",
                      NSStringFromClass(cls), NSStringFromSelector(sel));
        }
        free(methods);
    }
    return replaced;
}

static BOOL NAD_prefixMatch(const char *name) {
    for (int i = 0; i < NAD_neuterPrefixCount; i++) {
        if (strncmp(name, NAD_neuterPrefixes[i], strlen(NAD_neuterPrefixes[i])) == 0)
            return YES;
    }
    return NO;
}

static BOOL NAD_excluded(const char *name) {
    for (int i = 0; i < NAD_excludeClassCount; i++) {
        if (strncmp(name, NAD_excludeClasses[i], strlen(NAD_excludeClasses[i])) == 0)
            return YES;
    }
    return NO;
}

static int NAD_installClassNeuter(int *skippedOut)
{
    int neuteredClasses = 0, totalMethods = 0, skipped = 0;

    int numClasses = objc_getClassList(NULL, 0);
    if (numClasses <= 0) return 0;
    Class *classes = (Class *)malloc(sizeof(Class) * numClasses);
    if (!classes) return 0;
    numClasses = objc_getClassList(classes, numClasses);

    @autoreleasepool {
        // Pass 1：前缀命中（覆盖 SDK 全部派生类，含 Model/View/Service），
        // 排除表先判 —— XMAdd*/XMAddress* 等功能类绝不中和
        for (int i = 0; i < numClasses; i++) {
            const char *name = class_getName(classes[i]);
            if (!NAD_prefixMatch(name)) continue;
            if (NAD_excluded(name)) continue;
            totalMethods += NAD_neuterClass(classes[i], &skipped);
            neuteredClasses++;
        }
        // Pass 2：精确命中（请求/竞价/管理类）
        for (int i = 0; i < NAD_neuterClassCount; i++) {
            Class c = objc_getClass(NAD_neuterClasses[i]);
            if (!c) continue;
            totalMethods += NAD_neuterClass(c, &skipped);
            neuteredClasses++;
        }
    }

    free(classes);
    if (skippedOut) *skippedOut = skipped;
    NADLog(@"neuter: %d classes, %d methods, %d skipped(struct-return)",
           neuteredClasses, totalMethods, skipped);
    return neuteredClasses;
}

#pragma mark - 入口

// 构造函数：在本 dylib 的初始化阶段执行（早于 app 的 +load 与 main），
// 此时主二进制 + 全部 Frameworks 的 ObjC 类均已注册，可完整扫描。
// 同步执行以抢在首个开屏广告请求之前完成挂钩。
__attribute__((constructor))
static void NoAdsMain(void)
{
    @autoreleasepool {
        if (NAD_killed()) {
            NADLog(@"disabled by kill switch (nad_disabled=YES), standing down.");
            return;
        }

        int net = NAD_installNetworkSink();          // Tier 1 先行：掐网络
        int skipped = 0;
        int cls = NAD_installClassNeuter(&skipped);  // Tier 2/3：中和类

        NADLog(@"installed. net-sink=%d/4 + neuter %d classes. "
               @"kill: defaults write com.gemd.iting nad_disabled -bool YES",
               net, cls);
    }
}
