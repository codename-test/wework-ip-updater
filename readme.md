基于https://github.com/suraxiuxiu/WeworkAutoIpConfig \n
做了一点微调,把配置部分独立了出来,留了个报警接口 /n
"wechatUrl":"",---#应用网址
"cookie_header": "",---#HeaderString格式的cookie,用Cookie-Editor插件,export header string导出后复制进来
"detailsTime": 300,---#刷新间隔,单位秒,建议不要超过30分钟 
"webhook_url": "https://your-webhook-url",---#webhook告警地址,刷新失败会通知,24小时内只通知一次
"error_report_file": "error_report.json"---#固定格式,没需求就不改了