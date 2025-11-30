基于https://github.com/suraxiuxiu/WeworkAutoIpConfig

做了一点微调,把配置部分独立了出来,留了个报警接口,映射一个文件夹到app/config,首次运行以后会创建配置模板

(自己配置updater-config.json以后映射过去也可以)

"interface1_interface": "",----接口1,优先尝试电信线路

"interface2_interface": "",,----接口1,优先尝试联通线路

"interface3_interface": "",,----接口1,优先尝试移动线路

"wechatUrl":"",---#应用网址

"cookie_header": "",---#HeaderString格式的cookie,用Cookie-Editor插件,export header string导出后复制进来(正常应该是一大串内容,如果不对 可以换Cookie Editor,中间没有横杠的)

"detailsTime": 300,---#刷新间隔,单位秒,建议不要超过30分钟 

"webhook_url": "https://your-webhook-url",---#webhook告警地址,刷新失败会通知,24小时内只通知一次,没有就留空好了

"error_report_file": "error_report.json"---#固定内容,不用动



配置模板
{

    "Settings": {

        "interface1_interface": "eth0",

        "interface2_interface": "eth1",

        "interface3_interface": "eth2",

        "wechatUrl":"",

        "cookie_header": "",

        "detailsTime": 300,

        "webhook_url": "https://your-webhook-url",

        "error_report_file": "error_report.json"

    }

}
