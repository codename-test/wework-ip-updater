#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
企业微信可信IP自动更新器
监测多条线路的公网IP，变化时通过 Selenium 更新企业微信后台配置。
"""

import ipaddress
import json
import logging
import os
import platform
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    import netifaces
except ImportError:
    netifaces = None

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ==================== 常量 ====================
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ISP_NAMES = {
    "telecom": "电信", "unicom": "联通", "mobile": "移动",
    "edu": "教育网", "international": "国际",
}
INTERFACE_LABELS = ["电信线路", "联通线路", "移动线路"]

# 按运营商分类的 IP 检测服务
IP_SERVICES_BY_ISP = {
    "telecom": [
        "https://ip.3322.net",
        "http://www.net.cn/static/customercare/yourip.asp",
        "http://ddns.oray.com/checkip",
        "http://members.3322.org/dyndns/getip",
    ],
    "unicom": [
        "http://www.ipplus360.com/getip",
        "https://ip.ustc.edu.cn",
        "https://www.ip.cn/api/index?ip=&type=0",
    ],
    "mobile": [
        "http://ip.chinamobile.com",
        "http://1212.ip138.com/ic.asp",
        "https://www.ip138.com/ip2city.asp",
    ],
    "international": [
        "http://ipv4.icanhazip.com",
        "https://4.ipw.cn",
        "http://checkip.amazonaws.com",
        "https://api.ipify.org",
        "http://ifconfig.me/ip",
        "http://ipecho.net/plain",
    ],
}

# 每个接口按优先级排列的运营商
INTERFACE_ISP_PRIORITY = {
    0: ["telecom", "international", "unicom", "mobile"],
    1: ["unicom", "international", "telecom", "mobile"],
    2: ["mobile", "international", "telecom", "unicom"],
}

# Chrome 重试配置
CHROME_MAX_RETRIES = 3
CHROME_RETRY_DELAY = 5

# 错误/恢复通知限流（秒）
NOTIFICATION_COOLDOWN = 86400  # 24h


# ==================== 配置管理 ====================
CONFIG_DIR = Path("config")
CONFIG_PATH = CONFIG_DIR / "updater-config.json"

DEFAULT_CONFIG = {
    "Settings": {
        "interface1_interface": "eth0",
        "interface2_interface": "eth1",
        "interface3_interface": "eth2",
        "wechatUrl": "https://work.weixin.qq.com/wework_admin/loginpage_wx",
        "cookie_header": "your_cookie_here",
        "detailsTime": 300,
        "webhook_url": "",
        "error_report_file": "error_report.json",
    }
}


def create_default_config() -> bool:
    """创建默认配置文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        log.info("已创建默认配置文件: %s", CONFIG_PATH)
        log.info("请编辑配置文件并设置正确的参数后重新运行程序")
        return True
    except Exception as e:
        log.error("创建配置文件失败: %s", e)
        return False


def load_config() -> dict:
    """加载配置文件，不存在则创建默认配置"""
    if not CONFIG_PATH.exists():
        log.info("配置文件不存在，正在创建默认配置...")
        create_default_config()
        sys.exit(0)
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        log.info("配置文件加载成功")
        return config
    except Exception as e:
        log.error("加载配置文件失败: %s", e)
        if create_default_config():
            sys.exit(0)
        sys.exit(1)


# ==================== IP 工具函数 ====================
def is_valid_ip(ip: str) -> bool:
    """校验是否为合法 IPv4 地址"""
    try:
        addr = ipaddress.IPv4Address(ip)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_public_ip(ip: str) -> bool:
    """判断是否为公网 IP"""
    try:
        addr = ipaddress.IPv4Address(ip)
        return addr.is_global
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_private_ip(ip: str) -> bool:
    """判断是否为私有/保留 IP（用于过滤不应设置的地址）"""
    try:
        addr = ipaddress.IPv4Address(ip)
        # is_global 的反面：私有、回环、链路本地、保留段等
        return not addr.is_global
    except (ipaddress.AddressValueError, ValueError):
        return True


def extract_ip_from_text(text: str) -> str | None:
    """从文本中提取第一个合法 IP"""
    match = IP_PATTERN.search(text.strip())
    return match.group() if match else None


def extract_ip_from_json_response(data: dict) -> str | None:
    """从 JSON API 响应中提取 IP 字段"""
    # 兼容多种 API 返回格式
    if "ip" in data:
        return data["ip"]
    if "data" in data and isinstance(data["data"], dict) and "ip" in data["data"]:
        return data["data"]["ip"]
    return None


# ==================== 网卡接口 IP 获取 ====================
def get_interface_ip(interface_name: str) -> str | None:
    """获取指定网卡接口的内网 IP 地址"""
    # 方式1: netifaces
    if netifaces is not None:
        try:
            addresses = netifaces.ifaddresses(interface_name)
            for addr_info in addresses.get(netifaces.AF_INET, []):
                ip = addr_info.get("addr")
                if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
                    return ip
        except (ValueError, KeyError, OSError):
            pass

    # 方式2: ip 命令 (Linux)
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", interface_name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except (FileNotFoundError, Exception):
        pass

    # 方式3: ifconfig (macOS/旧Linux)
    try:
        result = subprocess.run(
            ["ifconfig", interface_name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except (FileNotFoundError, Exception):
        pass

    log.warning("无法获取接口 %s 的IP地址", interface_name)
    return None


# ==================== 公网 IP 检测 ====================
def build_service_list(interface_index: int) -> list[tuple[str, str]]:
    """
    按运营商优先级构建检测服务列表。
    返回 [(url, isp_key), ...]
    """
    priority = INTERFACE_ISP_PRIORITY.get(interface_index, ["international"])
    services = []
    for isp in priority:
        isp_urls = IP_SERVICES_BY_ISP.get(isp, [])
        shuffled = list(isp_urls)
        random.shuffle(shuffled)
        for url in shuffled:
            services.append((url, isp))
    return services


def parse_ip_response(url: str, text: str) -> str | None:
    """统一解析 IP 检测服务的响应"""
    text = text.strip()
    if not text:
        return None
    # JSON 类 API
    if "taobao.com" in url or "ip.cn" in url:
        try:
            data = json.loads(text)
            return extract_ip_from_json_response(data)
        except (json.JSONDecodeError, KeyError):
            return None
    # 纯文本类 API
    return extract_ip_from_text(text)


def get_public_ip_via_curl(source_ip: str, interface_index: int) -> str | None:
    """通过 curl 绑定源 IP 获取公网 IP"""
    services = build_service_list(interface_index)
    for url, isp_key in services:
        try:
            result = subprocess.run(
                [
                    "curl", "--interface", source_ip,
                    "--connect-timeout", "8", "--max-time", "12",
                    "--retry", "1", "-s", url,
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                continue
            ip = parse_ip_response(url, result.stdout)
            if ip and is_valid_ip(ip) and is_public_ip(ip):
                isp_name = ISP_NAMES.get(isp_key, isp_key)
                label = INTERFACE_LABELS[interface_index]
                log.info("%s IP: %s (运营商: %s, 来源: %s)", label, ip, isp_name, url)
                return ip
        except Exception:
            continue
    return None


def get_public_ip_via_requests(source_ip: str, interface_index: int) -> str | None:
    """通过 Python requests 绑定源 IP 获取公网 IP（curl 失败时的后备方案）"""
    # 自定义 Adapter 绑定源地址
    class SourceBindingAdapter(requests.adapters.HTTPAdapter):
        def __init__(self, src_ip, **kwargs):
            self._src_ip = src_ip
            super().__init__(**kwargs)

        def init_poolmanager(self, *args, **kwargs):
            kwargs["source_address"] = (self._src_ip, 0)
            return super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    try:
        adapter = SourceBindingAdapter(source_ip)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        }
        services = build_service_list(interface_index)
        for url, isp_key in services:
            try:
                resp = session.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    continue
                ip = parse_ip_response(url, resp.text)
                if ip and is_valid_ip(ip) and is_public_ip(ip):
                    isp_name = ISP_NAMES.get(isp_key, isp_key)
                    label = INTERFACE_LABELS[interface_index]
                    log.info("%s IP (requests): %s (运营商: %s)", label, ip, isp_name)
                    return ip
            except Exception:
                continue
    finally:
        session.close()
    return None


def detect_all_interface_ips(interface_configs: list[dict]) -> list[str | None]:
    """
    检测所有接口的公网 IP。
    返回 (has_changed, [ip_or_None, ...])
    """
    log.info("开始获取各接口IP地址...")
    new_ips: list[str | None] = []

    for i, iface_cfg in enumerate(interface_configs):
        iface_name = iface_cfg["interface"]
        label = INTERFACE_LABELS[i] if i < len(INTERFACE_LABELS) else f"接口{i+1}"
        log.info("检查 %s - 网卡: %s", label, iface_name)

        local_ip = get_interface_ip(iface_name)
        if not local_ip:
            log.warning("无法获取 %s 的内网IP，跳过", label)
            new_ips.append(None)
            continue

        log.info("%s 本地IP: %s", label, local_ip)

        # 优先用 curl（更快），失败则用 requests
        public_ip = get_public_ip_via_curl(local_ip, i)
        if public_ip is None:
            log.info("curl 获取失败，尝试 Python requests...")
            public_ip = get_public_ip_via_requests(local_ip, i)

        if public_ip is None:
            log.error("%s 公网IP获取失败", label)
        new_ips.append(public_ip)

        if i < len(interface_configs) - 1:
            time.sleep(2)

    # 检查是否有重复 IP（可能表示线路未正确区分）
    valid = [ip for ip in new_ips if ip]
    if len(valid) > 1 and len(set(valid)) < len(valid):
        log.warning("获取到的接口IP有重复，可能未正确区分线路:")
        for ip in set(valid):
            count = valid.count(ip)
            if count > 1:
                log.warning("  IP %s 出现了 %d 次", ip, count)

    return new_ips


# ==================== Chrome 浏览器 ====================
def setup_chrome_options() -> webdriver.ChromeOptions:
    """配置 Chrome 选项（headless、低内存）"""
    options = webdriver.ChromeOptions()
    # 基础：headless + 无沙箱
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # 精简：禁用一切不需要的功能
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-application-cache")
    options.add_argument("--disable-add-to-shelf")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-translate")
    # 内存限制
    options.add_argument("--js-flags=--max-old-space-size=256")
    options.add_argument("--single-process")
    options.add_argument("--no-zygote")
    # 窗口缩小（减少渲染内存）
    options.add_argument("--window-size=1280,720")
    # 页面加载策略
    options.page_load_strategy = "eager"
    # 隐藏自动化标记
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_settings.popups": 0,
        "profile.managed_default_content_settings.images": 2,
    })
    return options


def cleanup_chrome_processes():
    """清理残留 Chrome 进程"""
    for pattern in ["chrome", "chromedriver", "chromium"]:
        try:
            subprocess.run(
                ["pkill", "-f", pattern],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    time.sleep(1)


def launch_browser(wechat_url: str, cookie_header: str) -> webdriver.Chrome | None:
    """
    启动浏览器并访问企业微信，应用 cookie 完成登录。
    失败时内部重试 CHROME_MAX_RETRIES 次。
    """
    log.info("启动Chrome浏览器访问企业微信")

    for attempt in range(CHROME_MAX_RETRIES):
        driver = None
        start_time = time.time()
        try:
            if attempt > 0:
                cleanup_chrome_processes()
                log.info("第 %d 次尝试启动浏览器...", attempt + 1)

            options = setup_chrome_options()
            service = Service()
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(15)
            driver.set_script_timeout(10)
            driver.implicitly_wait(5)

            log.info("Chrome驱动初始化完成 (%.1fs)", time.time() - start_time)
            driver.get(wechat_url)
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # 应用 cookies
            driver.delete_all_cookies()
            for part in cookie_header.split(";"):
                if "=" not in part:
                    continue
                name, value = part.split("=", 1)
                cookie_dict = {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".work.weixin.qq.com",
                    "path": "/",
                }
                if wechat_url.startswith("https"):
                    cookie_dict["secure"] = True
                driver.add_cookie(cookie_dict)

            log.info("应用cookies，重新加载页面")
            driver.refresh()
            time.sleep(1)

            # 检查登录状态
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "login_stage_title_text"))
                )
                raise RuntimeError("登录状态失效，请更新cookie")
            except TimeoutException:
                log.info("登录状态验证成功")

            log.info("浏览器启动完成，总耗时 %.1fs", time.time() - start_time)
            return driver

        except Exception as e:
            log.error("浏览器启动异常 (%d/%d): %s", attempt + 1, CHROME_MAX_RETRIES, e)
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if attempt < CHROME_MAX_RETRIES - 1:
                wait = CHROME_RETRY_DELAY * (attempt + 1)
                log.info("等待 %d 秒后重试...", wait)
                time.sleep(wait)

    return None


# ==================== 企业微信 IP 更新 ====================
def update_wecom_ip(driver: webdriver.Chrome, new_ips: list[str | None]) -> tuple[bool, str]:
    """
    更新企业微信可信 IP 地址。
    返回 (success, error_message)
    """
    try:
        # 过滤有效公网 IP 并去重
        valid_ips = []
        seen = set()
        for ip in new_ips:
            if ip and is_public_ip(ip) and ip not in seen:
                valid_ips.append(ip)
                seen.add(ip)

        if not valid_ips:
            return False, "没有有效的公网IP地址可以设置"

        new_ips_str = ";".join(valid_ips)
        log.info("准备设置可信IP: %s", new_ips_str)

        # 点击设置按钮
        settings_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                '//div[contains(@class, "app_card_operate") and contains(@class, "js_show_ipConfig_dialog")]',
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", settings_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", settings_btn)
        log.info("已点击设置按钮")

        # 填写 IP
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
        )
        old_ips_str = textarea.get_attribute("value").strip()
        log.info("当前已设置IP: %s", old_ips_str)

        driver.execute_script("arguments[0].value = '';", textarea)
        textarea.send_keys(new_ips_str)

        # 确认
        confirm_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@class, "js_ipConfig_confirmBtn")]'))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        log.info("已提交IP变更")

        # 等待对话框关闭
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.XPATH, '//div[contains(@class, "js_ipConfig_dialog")]'))
        )
        log.info("IP地址更新成功: %s", new_ips_str)
        return True, ""

    except Exception as e:
        error_msg = f"更改IP地址失败: {e}"
        log.error(error_msg)
        # 保存截图
        try:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = f"error_{ts}.png"
            driver.save_screenshot(path)
            log.info("错误截图已保存: %s", path)
            error_msg += f"\n截图: {path}"
        except Exception:
            pass
        return False, error_msg


# ==================== Webhook 通知 ====================
class Notifier:
    """带限流的 Webhook 通知器"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._last_error_time: datetime | None = None
        self._last_recovery_time: datetime | None = None
        self._error_sent_for_current_failure = False
        self._last_cycle_ok = True  # 初始 True，避免启动就发恢复通知

    def _post(self, content: str) -> bool:
        if not self.webhook_url:
            return False
        try:
            resp = requests.post(
                self.webhook_url,
                json={"msgtype": "text", "text": {"content": content}},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            log.error("Webhook 发送失败: %s", e)
            return False

    def report_error(self, message: str):
        """发送错误通知（24h 内同一故障周期只发一次）"""
        now = datetime.now()
        if self._last_error_time and (now - self._last_error_time).total_seconds() < NOTIFICATION_COOLDOWN:
            log.info("24h内已发送过错误报告，跳过")
            return
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        ok = self._post(f"企业微信IP更新器发生错误:\n{message}\n时间: {ts}")
        if ok:
            log.info("错误报告发送成功")
            self._last_error_time = now
            self._error_sent_for_current_failure = True
        else:
            log.warning("错误报告发送失败")

    def report_recovery(self):
        """发送恢复通知"""
        now = datetime.now()
        if self._last_recovery_time and (now - self._last_recovery_time).total_seconds() < NOTIFICATION_COOLDOWN:
            return
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        ok = self._post(f"企业微信 IP 更新器已恢复\n\n时间：{ts}\n\n系统状态：正常")
        if ok:
            log.info("恢复通知发送成功")
            self._last_recovery_time = now

    def on_cycle_result(self, cycle_ok: bool, error_detail: str = ""):
        """根据周期结果决定通知策略"""
        if cycle_ok:
            if not self._last_cycle_ok:
                log.info("从故障中恢复")
                self.report_recovery()
                self._error_sent_for_current_failure = False
            self._last_cycle_ok = True
        else:
            if not self._error_sent_for_current_failure:
                self.report_error(error_detail)
            self._last_cycle_ok = False


# ==================== Cookie 保活 ====================
def keep_cookie_alive(wechat_url: str, cookie_header: str) -> bool:
    """
    用 requests 轻量请求访问企业微信页面，保持 cookie/session 不过期。
    不启动浏览器，内存开销极小（几 MB）。
    返回 True 表示 cookie 仍有效，False 表示已失效。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie_header,
    }
    try:
        resp = requests.get(wechat_url, headers=headers, timeout=15, allow_redirects=True)
        # 如果被重定向到登录页，说明 cookie 已失效
        if "loginpage_wx" in resp.url or "login" in resp.url.lower():
            log.warning("Cookie 已失效（被重定向到登录页）")
            return False
        if resp.status_code == 200:
            log.info("Cookie 保活成功（HTTP %d）", resp.status_code)
            return True
        log.warning("Cookie 保活异常，HTTP 状态码: %d", resp.status_code)
        return False
    except Exception as e:
        log.warning("Cookie 保活请求失败: %s", e)
        return False


# ==================== 主循环 ====================
def main():
    config = load_config()
    settings = config["Settings"]

    interface_configs = [
        {"interface": settings[f"interface{i+1}_interface"]}
        for i in range(3)
    ]
    wechat_url = settings["wechatUrl"]
    cookie_header = settings["cookie_header"]
    interval = settings["detailsTime"]
    webhook_url = settings.get("webhook_url", "")

    notifier = Notifier(webhook_url)
    current_ips: list[str | None] = [None, None, None]

    log.info("企业微信三接口IP更新器启动")
    for i, cfg in enumerate(interface_configs):
        log.info("  接口%d (%s) - 网卡: %s", i + 1, INTERFACE_LABELS[i], cfg["interface"])

    # 检查 curl
    try:
        subprocess.run(["curl", "--version"], capture_output=True, timeout=5)
    except Exception:
        log.error("curl 命令不可用，程序退出")
        notifier.report_error("curl命令不可用")
        return

    while True:
        cycle_ok = False
        error_detail = ""
        start_time = time.time()

        try:
            # 第零步：用轻量请求保活 cookie（不启动浏览器，几 MB 内存）
            cookie_ok = keep_cookie_alive(wechat_url, cookie_header)
            if not cookie_ok:
                error_detail = "Cookie 已失效，请更新配置文件中的 cookie_header"
                log.error(error_detail)
                notifier.on_cycle_result(False, error_detail)
                time.sleep(interval)
                continue

            # 第一步：检测 IP（不需要浏览器）
            try:
                new_ips = detect_all_interface_ips(interface_configs)
            except Exception as e:
                error_detail = f"IP检测异常: {e}"
                log.error(error_detail)
                notifier.on_cycle_result(False, error_detail)
                time.sleep(interval)
                continue

            # 判断是否有变化
            changed = any(
                new_ip is not None and new_ip != current_ips[i]
                for i, new_ip in enumerate(new_ips)
            )

            if not changed:
                cycle_ok = True
                log.info("所有接口IP均未变化，无需更新")
            else:
                # 第二步：IP 有变化，才启动浏览器去更新企业微信
                log.info("检测到IP变化，启动浏览器更新企业微信")
                driver = None
                try:
                    driver = launch_browser(wechat_url, cookie_header)
                    if not driver:
                        error_detail = "浏览器启动失败（重试3次后仍失败）"
                        log.error(error_detail)
                    else:
                        ok, err = update_wecom_ip(driver, new_ips)
                        if ok:
                            for i, ip in enumerate(new_ips):
                                if ip is not None:
                                    current_ips[i] = ip
                            cycle_ok = True
                            log.info("IP变更成功")
                        else:
                            error_detail = err
                            log.error("IP变更失败: %s", err)
                finally:
                    if driver:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        cleanup_chrome_processes()

            notifier.on_cycle_result(cycle_ok, error_detail)

        except Exception as e:
            error_detail = f"主循环异常: {e}"
            log.error(error_detail)
            notifier.on_cycle_result(False, error_detail)

        elapsed = time.time() - start_time
        log.info("本次循环耗时 %.1fs，等待 %ds 后下次检查...", elapsed, interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
