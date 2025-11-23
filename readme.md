基于https://github.com/suraxiuxiu/WeworkAutoIpConfig

做了一点微调,把配置部分独立了出来,留了个报警接口,使用前自己映射下配置文件updater-config.json到/app里面

"wechatUrl":"",---#应用网址

"cookie_header": "",---#HeaderString格式的cookie,用Cookie-Editor插件,export header string导出后复制进来

"detailsTime": 300,---#刷新间隔,单位秒,建议不要超过30分钟 

"webhook_url": "https://your-webhook-url",---#webhook告警地址,刷新失败会通知,24小时内只通知一次

"error_report_file": "error_report.json"---#固定格式,没需求就不改了


1.0版本针对单网卡,2.0可以多网卡(我自己的负载均衡也不能保证获取正确,但至少有机会取到正常IP,可能是网络环境问题)

2.0配置开头的三个IP就按自己网卡实际获取的填,可以重复不能留空,然后稍微比1.0优化了一点点无关痛痒的东西,普通用户1.0即可
