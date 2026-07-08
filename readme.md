# WeWork IP Updater

> 自动更新企业微信后台 IP 白名单。基于 [WeworkAutoIpConfig](https://github.com/suraxiuxiu/WeworkAutoIpConfig) 二次开发。

## 功能

- 定时检测多线路（电信/联通/移动）出口公网 IP
- 通过 Selenium 自动化登录企业微信管理后台，更新可信 IP
- IP 变更或更新失败时通过 Webhook 告警（24h 限流）
- 首次运行自动生成配置文件

## 快速开始

### Docker 部署（推荐）

```bash
docker run -d \
  --name wework-ip-updater \
  --network host \
  -v $(pwd)/config:/app/config \
  codenametest/wework-ip-updater:latest
```

首次运行后会在 `./config/` 下生成 `updater-config.json`，修改配置后重启容器即可。

### 手动部署

```bash
git clone https://github.com/codename-test/wework-ip-updater.git
cd wework-ip-updater
pip install -r requirements.txt
python wechat_ip_updater.py
```

## 配置说明

配置文件位于 `config/updater-config.json`：

```json
{
  "Settings": {
    "interface1_interface": "eth0",
    "interface2_interface": "eth1",
    "interface3_interface": "eth2",
    "wechatUrl": "https://work.weixin.qq.com/wework_admin/loginpage_wx",
    "cookie_header": "",
    "detailsTime": 300,
    "webhook_url": "",
    "error_report_file": "error_report.json"
  }
}
```

| 字段 | 说明 |
|------|------|
| `interface1_interface` | 线路一网卡名（优先电信） |
| `interface2_interface` | 线路二网卡名（优先联通） |
| `interface3_interface` | 线路三网卡名（优先移动） |
| `wechatUrl` | 企业微信管理后台地址，默认即可 |
| `cookie_header` | 浏览器 Cookie（Header String 格式） |
| `detailsTime` | 检测间隔（秒），建议 300~1800 |
| `webhook_url` | 告警 Webhook 地址，留空则不通知 |
| `error_report_file` | 错误记录文件，固定不变 |

### 获取 Cookie

1. 浏览器安装 **Cookie-Editor** 插件
2. 登录企业微信管理后台
3. 点击插件 → Export → **Header String**
4. 复制全部内容粘贴到 `cookie_header`

## 致谢

基于 [suraxiuxiu/WeworkAutoIpConfig](https://github.com/suraxiuxiu/WeworkAutoIpConfig)，感谢原作者。

## License

MIT
