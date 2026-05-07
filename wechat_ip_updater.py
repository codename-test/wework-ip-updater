#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
import time
import os
import requests
from datetime import datetime, timedelta
import socket
import platform
import netifaces
import random

# ==================== 工具函数 ====================
def get_timestamp():
    """获取当前时间戳"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log_with_timestamp(message):
    """带时间戳的日志输出"""
    print(f"[{get_timestamp()}] {message}")

def create_default_config():
    """创建默认配置文件"""
    default_config = {
        "Settings": {
            "interface1_interface": "eth0",
            "interface2_interface": "eth1", 
            "interface3_interface": "eth2",
            "wechatUrl": "https://work.weixin.qq.com/wework_admin/loginpage_wx",
            "cookie_header": "your_cookie_here",
            "detailsTime": 300,
            "webhook_url": "",
            "error_report_file": "error_report.json"
        }
    }
    config_dir = 'config'
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
        log_with_timestamp(f"创建配置目录: {config_dir}")
    config_path = os.path.join(config_dir, 'updater-config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)
        log_with_timestamp(f"已创建默认配置文件: {config_path}")
        log_with_timestamp("请编辑配置文件并设置正确的参数后重新运行程序")
        return True
    except Exception as e:
        log_with_timestamp(f"创建配置文件失败: {e}")
        return False

def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_path = 'config/updater-config.json'
    if not os.path.exists(config_path):
        log_with_timestamp("配置文件不存在，正在创建默认配置...")
        if create_default_config():
            exit(0)
        else:
            log_with_timestamp("创建配置文件失败，程序退出")
            exit(1)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        log_with_timestamp("配置文件加载成功")
        return config
    except Exception as e:
        log_with_timestamp(f"加载配置文件失败: {e}")
        if create_default_config():
            exit(0)
        else:
            exit(1)

# 读取JSON配置文件
config = load_config()

# 从配置文件获取参数
ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# 从配置文件获取三个网卡接口名称
interface_configs = [
    {'interface': config['Settings']['interface1_interface']},
    {'interface': config['Settings']['interface2_interface']},
    {'interface': config['Settings']['interface3_interface']}
]

# 当前IP地址存储
current_ips = ['192.168.1.1', '192.168.1.1', '192.168.1.1']
overwrite = True
wechatUrl = config['Settings']['wechatUrl']
cookie_header = config['Settings']['cookie_header']
detailsTime = config['Settings']['detailsTime']

# 错误报告配置
webhook_url = config['Settings'].get('webhook_url', '')
error_report_file = config['Settings'].get('error_report_file', 'error_report.json')

# Chrome配置
CHROME_MAX_RETRIES = 3
CHROME_RETRY_DELAY = 5

# 按运营商分类的IP检测服务
IP_SERVICES_BY_ISP = {
    "telecom": [
        "https://ip.3322.net",
        "http://www.net.cn/static/customercare/yourip.asp",
        "http://ddns.oray.com/checkip",
        "http://ip.cctv.cn",
        "https://myip.lefeng.com",
        "http://ip.taobao.com/service/getIpInfo2.php?ip=myip",
        "https://www.taobao.com/help/getip.php"
    ],
    "unicom": [
        "http://www.ipplus360.com/getip",
        "http://members.3322.org/dyndns/getip",
        "http://ip.taobao.com/service/getIpInfo2.php?ip=myip",
        "https://www.ip.cn/api/index?ip=&type=0",
        "http://ip.uniqode.net",
        "https://ip.ustc.edu.cn"
    ],
    "mobile": [
        "http://ip.chinamobile.com",
        "http://1212.ip138.com/ic.asp",
        "https://www.ip138.com/ip2city.asp",
        "http://ip.cmvideo.cn",
        "http://ip.mobilem.360.cn",
        "http://ip.10086.cn",
        "http://ip.monternet.com",
        "https://ip.ct10000.com"
    ],
    "edu": [
        "http://www.edu.cn/",
        "http://www.cernet.com/",
        "https://ip.ustc.edu.cn"
    ],
    "international": [
        "http://ipv4.icanhazip.com",
        "https://4.ipw.cn", 
        "http://checkip.amazonaws.com",
        "https://api.ipify.org",
        "http://myexternalip.com/raw",
        "http://ifconfig.me/ip",
        "http://ident.me",
        "http://ipecho.net/plain",
        "http://whatismyip.akamai.com",
        "http://wgetip.com"
    ]
}

INTERFACE_ISP_PRIORITY = {
    0: ["telecom", "international", "unicom", "mobile", "edu"],
    1: ["unicom", "international", "telecom", "mobile", "edu"],
    2: ["mobile", "international", "telecom", "unicom", "edu"]
}

# ==================== IP检测相关函数 ====================
def get_system_platform():
    system = platform.system().lower()
    if system == 'windows':
        return 'windows'
    elif system == 'linux':
        return 'linux'
    elif system == 'darwin':
        return 'macos'
    else:
        return 'unknown'

def check_command_available(command):
    try:
        if get_system_platform() == 'windows':
            result = subprocess.run(['where', command] if command != 'ip' else ['where', 'ipconfig'], capture_output=True, text=True, timeout=5)
        else:
            result = subprocess.run(['which', command], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False

def check_curl_available():
    try:
        result = subprocess.run(['curl', '--version'], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception as e:
        log_with_timestamp(f"curl命令检查失败: {e}")
        return False

def get_interface_ip(interface_name):
    """获取指定网卡接口的IP地址"""
    try:
        try:
            addresses = netifaces.ifaddresses(interface_name)
            if netifaces.AF_INET in addresses:
                for addr_info in addresses[netifaces.AF_INET]:
                    ip = addr_info.get('addr')
                    if ip and ip != '127.0.0.1' and not ip.startswith('169.254'):
                        return ip
        except (ValueError, KeyError):
            pass
        if check_command_available('ip'):
            try:
                result = subprocess.run(['ip', '-4', 'addr', 'show', interface_name], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if ip_match:
                        return ip_match.group(1)
            except Exception:
                pass
        if check_command_available('ifconfig'):
            try:
                result = subprocess.run(['ifconfig', interface_name], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if ip_match:
                        return ip_match.group(1)
            except Exception:
                pass
        log_with_timestamp(f"无法获取接口 {interface_name} 的IP地址")
        return None
    except Exception as e:
        log_with_timestamp(f"获取接口 {interface_name} IP地址失败: {e}")
        return None

def get_isp_services_for_interface(interface_index):
    isp_priority = INTERFACE_ISP_PRIORITY.get(interface_index, ["international", "telecom", "unicom", "mobile"])
    services = []
    for isp in isp_priority:
        if isp in IP_SERVICES_BY_ISP:
            isp_services = IP_SERVICES_BY_ISP[isp].copy()
            random.shuffle(isp_services)
            services.extend(isp_services)
    isp_names = {"telecom": "电信", "unicom": "联通", "mobile": "移动", "edu": "教育网", "international": "国际"}
    priority_names = [isp_names.get(isp, isp) for isp in isp_priority if isp in isp_names]
    interface_desc = ["电信优先", "联通优先", "移动优先"][interface_index]
    log_with_timestamp(f"接口{interface_index+1}({interface_desc}) 运营商检测优先级: {' → '.join(priority_names)}")
    return services

def get_ip_using_curl_source_binding(interface_ip, display_name, interface_index):
    isp_services = get_isp_services_for_interface(interface_index)
    for service_url in isp_services:
        try:
            cmd = ['curl', '--interface', interface_ip, '--connect-timeout', '8', '--max-time', '12', '--retry', '1', '-s', service_url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                if 'taobao.com' in service_url or 'ip.cn' in service_url:
                    try:
                        data = json.loads(result.stdout)
                        if 'ip' in data:
                            ip = data['ip']
                        elif 'data' in data and 'ip' in data['data']:
                            ip = data['data']['ip']
                        else:
                            continue
                    except:
                        continue
                else:
                    ip_match = re.search(ip_pattern, result.stdout.strip())
                    if not ip_match:
                        continue
                    ip = ip_match.group()
                if is_valid_ip(ip) and is_public_ip(ip):
                    isp_name = "未知"
                    for isp, services in IP_SERVICES_BY_ISP.items():
                        if service_url in services:
                            isp_names = {"telecom": "电信", "unicom": "联通", "mobile": "移动", "edu": "教育网", "international": "国际"}
                            isp_name = isp_names.get(isp, isp)
                            break
                    interface_desc = ["电信线路", "联通线路", "移动线路"][interface_index]
                    log_with_timestamp(f"{interface_desc} {display_name} IP: {ip} (运营商: {isp_name}, 来源: {service_url})")
                    return ip
        except Exception:
            continue
    return "获取IP失败"

def get_ip_using_python_source_binding(interface_ip, display_name, interface_index):
    isp_services = get_isp_services_for_interface(interface_index)
    try:
        class SourceIPAdapter(requests.adapters.HTTPAdapter):
            def __init__(self, source_ip, **kwargs):
                self.source_ip = source_ip
                super().__init__(**kwargs)
            def init_poolmanager(self, *args, **kwargs):
                kwargs['source_address'] = (self.source_ip, 0)
                return super().init_poolmanager(*args, **kwargs)
        session = requests.Session()
        adapter = SourceIPAdapter(interface_ip)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        for url in isp_services:
            try:
                response = session.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    if 'taobao.com' in url or 'ip.cn' in url:
                        try:
                            data = response.json()
                            if 'ip' in data:
                                ip = data['ip']
                            elif 'data' in data and 'ip' in data['data']:
                                ip = data['data']['ip']
                            else:
                                continue
                        except:
                            continue
                    else:
                        ip_match = re.search(ip_pattern, response.text.strip())
                        if not ip_match:
                            continue
                        ip = ip_match.group()
                    if is_valid_ip(ip):
                        isp_name = "未知"
                        for isp, services in IP_SERVICES_BY_ISP.items():
                            if url in services:
                                isp_names = {"telecom": "电信", "unicom": "联通", "mobile": "移动", "edu": "教育网", "international": "国际"}
                                isp_name = isp_names.get(isp, isp)
                                break
                        interface_desc = ["电信线路", "联通线路", "移动线路"][interface_index]
                        log_with_timestamp(f"{interface_desc} {display_name}(Python) IP: {ip} (运营商: {isp_name})")
                        return ip
            except Exception:
                continue
    except Exception as e:
        log_with_timestamp(f"使用Python绑定获取接口 {display_name} IP失败: {e}")
    return "获取IP失败"

def is_valid_ip(ip):
    if ip == "获取IP失败":
        return False
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False
    return True

def is_public_ip(ip):
    if not is_valid_ip(ip):
        return False
    octets = [int(x) for x in ip.split('.')]
    if octets[0] == 10:
        return False
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return False
    if octets[0] == 192 and octets[1] == 168:
        return False
    if octets[0] == 127:
        return False
    if octets[0] == 169 and octets[1] == 254:
        return False
    return True

def CheckIPs():
    global current_ips
    log_with_timestamp("开始获取各接口IP地址（电信→联通→移动优先级）...")
    new_ips = []
    changed = False
    for i, interface_config in enumerate(interface_configs):
        interface_name = interface_config['interface']
        display_name = f"接口{i+1}"
        interface_desc = ["电信线路", "联通线路", "移动线路"][i]
        log_with_timestamp(f"检查{display_name}({interface_desc}) - 网卡: {interface_name}")
        local_ip = get_interface_ip(interface_name)
        if not local_ip:
            log_with_timestamp(f"无法获取{display_name}的本地IP，跳过该接口")
            new_ips.append("获取IP失败")
            continue
        log_with_timestamp(f"{display_name} 本地IP: {local_ip}")
        ip = get_ip_using_curl_source_binding(local_ip, display_name, i)
        if ip == "获取IP失败":
            log_with_timestamp(f"尝试使用Python绑定获取{display_name} IP")
            ip = get_ip_using_python_source_binding(local_ip, display_name, i)
        new_ips.append(ip)
        if ip != "获取IP失败" and ip != current_ips[i]:
            changed = True
            log_with_timestamp(f"检测到{display_name} IP变化: {current_ips[i]} → {ip}")
            current_ips[i] = ip
        if i < len(interface_configs) - 1:
            time.sleep(2)
    valid_ips = [ip for ip in new_ips if ip != "获取IP失败"]
    unique_ips = set(valid_ips)
    if len(valid_ips) > 1 and len(unique_ips) < len(valid_ips):
        log_with_timestamp("警告：获取到的接口IP有重复，可能未正确区分线路")
        for ip in unique_ips:
            count = valid_ips.count(ip)
            if count > 1:
                log_with_timestamp(f"IP {ip} 出现了 {count} 次")
    return changed, new_ips

# ==================== Chrome 浏览器相关函数 ====================
def setup_chrome_options():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--memory-pressure-off')
    options.add_argument('--max_old_space_size=512')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--remote-debugging-port=0')
    options.add_argument('--user-data-dir=/tmp/chrome-data')
    options.add_argument('--disable-web-security')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-software-rasterizer')
    options.page_load_strategy = 'eager'
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging', 'ignore-certificate-errors'])
    options.add_experimental_option('prefs', {
        'profile.default_content_setting_values.notifications': 2,
        'profile.default_content_settings.popups': 0,
        'profile.managed_default_content_settings.images': 2,
    })
    return options

def create_chrome_service():
    service = Service()
    return service

def cleanup_chrome_processes():
    try:
        subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-f', 'chromedriver'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception as e:
        log_with_timestamp(f"清理Chrome进程时出错: {e}")

# ==================== 全局状态变量（用于错误限流和恢复）====================
last_error_time = None          # 上次错误报告时间
last_recovery_time = None       # 上次恢复通知时间
error_reported_for_failure = False  # 当前连续失败周期中是否已发送过错误报告
last_cycle_success = True            # 上一次完整周期是否成功（初始为True避免刚启动就发恢复）

# ==================== 带限流的错误/恢复通知 ====================
def send_error_report(error_message):
    """发送错误报告到Webhook，24小时内只发送一次"""
    global last_error_time
    if not webhook_url:
        log_with_timestamp("Webhook URL未配置，跳过错误报告")
        return
    current_time = datetime.now()
    if last_error_time and (current_time - last_error_time).total_seconds() < 86400:
        log_with_timestamp("24小时内已发送过错误报告，本次跳过")
        return
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"企业微信IP更新器发生错误:\n{error_message}\n时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }
    try:
        response = requests.post(webhook_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200:
            log_with_timestamp("✅ 错误报告发送成功")
            last_error_time = current_time
        else:
            log_with_timestamp(f"⚠️ 错误报告发送失败，状态码: {response.status_code}")
    except Exception as e:
        log_with_timestamp(f"❌ 发送错误报告时出错: {e}")

def send_recovery_report():
    """发送恢复通知到 Webhook，24小时内只发送一次"""
    global last_recovery_time
    if not webhook_url:
        log_with_timestamp("Webhook URL未配置，跳过恢复通知")
        return
    current_time = datetime.now()
    if last_recovery_time and (current_time - last_recovery_time).total_seconds() < 86400:
        log_with_timestamp("24小时内已发送过恢复通知，本次跳过")
        return
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"✅ 企业微信 IP 更新器已恢复\n\n⏰ 时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n系统状态：正常"
        }
    }
    try:
        response = requests.post(webhook_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200:
            log_with_timestamp("✅ 恢复通知发送成功")
            last_recovery_time = current_time
        else:
            log_with_timestamp(f"⚠️ 恢复通知发送失败，状态码：{response.status_code}")
    except Exception as e:
        log_with_timestamp(f"❌ 发送恢复通知时出错：{e}")

# ==================== 企业微信 IP 修改函数 ====================
def ChangeIP(driver, new_ips):
    """更新企业微信可信IP地址，返回 (success, error_message)"""
    try:
        log_with_timestamp("尝试更改企业微信可信IP地址")
        valid_ips = [ip for ip in new_ips if ip != "获取IP失败" and not ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.', '127.0.0.', '169.254.'))]
        unique_ips = []
        seen_ips = set()
        for ip in valid_ips:
            if ip not in seen_ips:
                unique_ips.append(ip)
                seen_ips.add(ip)
        if not unique_ips:
            return False, "没有有效的公网IP地址可以设置（所有IP都是私有IP或本地回环）"
        new_ips_str = ';'.join(unique_ips)
        if len(unique_ips) < len(valid_ips):
            log_with_timestamp(f"检测到重复IP，去重后设置: {new_ips_str} (原始: {len(valid_ips)}个 → 唯一: {len(unique_ips)}个)")
        
        settings_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[contains(@class, "app_card_operate") and contains(@class, "js_show_ipConfig_dialog")]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", settings_button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", settings_button)
        log_with_timestamp("已点击设置按钮")
        
        input_area = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
        )
        current_ips_str = input_area.get_attribute('value').strip()
        log_with_timestamp(f"当前已设置IP: {current_ips_str}")
        log_with_timestamp(f"准备设置新IP: {new_ips_str}")
        
        driver.execute_script("arguments[0].value = '';", input_area)
        input_area.send_keys(new_ips_str)
        log_with_timestamp(f"已设置新IP: {new_ips_str}")
        
        confirm_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@class, "js_ipConfig_confirmBtn")]'))
        )
        driver.execute_script("arguments[0].click();", confirm_button)
        log_with_timestamp("已提交IP变更")
        
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.XPATH, '//div[contains(@class, "js_ipConfig_dialog")]'))
        )
        log_with_timestamp("✅ IP地址更新成功")
        return True, ""
    except Exception as e:
        error_msg = f"更改IP地址失败: {e}"
        log_with_timestamp(error_msg)
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"error_{timestamp}.png"
            driver.save_screenshot(filename)
            log_with_timestamp(f"已保存错误截图: {filename}")
            error_msg += f"\n已保存截图: {filename}"
        except:
            pass
        return False, error_msg

# ==================== 浏览器启动函数（带重试） ====================
def OpenBrowser():
    """启动浏览器并访问企业微信，成功返回driver，失败返回None（内部重试3次）"""
    log_with_timestamp("启动Chrome浏览器访问企业微信")
    for attempt in range(CHROME_MAX_RETRIES):
        start_time = time.time()
        driver = None
        try:
            if attempt > 0:
                cleanup_chrome_processes()
                log_with_timestamp(f"第 {attempt + 1} 次尝试启动浏览器...")
            options = setup_chrome_options()
            service = create_chrome_service()
            log_with_timestamp("正在初始化Chrome驱动...")
            driver = webdriver.Chrome(service=service, options=options)
            log_with_timestamp(f"Chrome驱动初始化完成，耗时: {time.time() - start_time:.2f}秒")
            driver.set_page_load_timeout(15)
            driver.set_script_timeout(10)
            driver.implicitly_wait(5)
            log_with_timestamp(f"访问URL: {wechatUrl}")
            driver.get(wechatUrl)
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            log_with_timestamp(f"页面加载完成，总耗时: {time.time() - start_time:.2f}秒")
            # 应用cookies
            try:
                driver.delete_all_cookies()
                cookies = cookie_header.split(';')
                for cookie in cookies:
                    if '=' in cookie:
                        name, value = cookie.split('=', 1)
                        cookie_dict = {
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".work.weixin.qq.com",
                            "path": "/",
                        }
                        if wechatUrl.startswith('https'):
                            cookie_dict["secure"] = True
                        driver.add_cookie(cookie_dict)
                log_with_timestamp("重新加载页面应用cookies")
                driver.refresh()
                time.sleep(1)
            except Exception as e:
                log_with_timestamp(f"应用cookies异常: {e}")
                raise
            # 检查登录状态
            try:
                WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CLASS_NAME, 'login_stage_title_text')))
                raise Exception("登录状态失效，请更新cookie")
            except TimeoutException:
                log_with_timestamp("登录状态验证成功")
            return driver
        except Exception as e:
            error_msg = f"浏览器启动或页面加载异常(尝试 {attempt+1}/{CHROME_MAX_RETRIES}): {str(e)}"
            log_with_timestamp(error_msg)
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            if attempt == CHROME_MAX_RETRIES - 1:
                return None
            else:
                wait_time = CHROME_RETRY_DELAY * (attempt + 1)
                log_with_timestamp(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    return None

# ==================== 主循环 ====================
def main():
    global current_ips, error_reported_for_failure, last_cycle_success
    log_with_timestamp("企业微信三接口IP更新器启动（电信→联通→移动优先级）")
    for i, config in enumerate(interface_configs):
        log_with_timestamp(f"接口{i+1} - 网卡: {config['interface']}")
    if not check_curl_available():
        log_with_timestamp("错误：curl命令不可用")
        send_error_report("curl命令不可用")
        return
    while True:
        driver = None
        cycle_success = False
        error_detail = ""
        try:
            start_time = time.time()
            driver = OpenBrowser()
            if not driver:
                error_detail = "浏览器启动失败（重试3次后仍失败）"
                log_with_timestamp(error_detail)
                cycle_success = False
            else:
                try:
                    changed, new_ips = CheckIPs()
                except Exception as e:
                    error_detail = f"IP检测过程发生异常: {e}"
                    log_with_timestamp(error_detail)
                    changed = False
                    cycle_success = False
                else:
                    if changed:
                        log_with_timestamp("检测到IP变化，开始更新企业微信设置")
                        success, err_msg = ChangeIP(driver, new_ips)
                        if success:
                            cycle_success = True
                            log_with_timestamp("IP变更成功")
                        else:
                            cycle_success = False
                            error_detail = err_msg
                            log_with_timestamp(f"IP变更失败: {error_detail}")
                    else:
                        cycle_success = True
                        log_with_timestamp("所有接口IP均未发生变化，无需更新")
            # 处理成功/失败通知
            if cycle_success:
                if not last_cycle_success:
                    log_with_timestamp("从故障中恢复，发送恢复通知")
                    send_recovery_report()
                    error_reported_for_failure = False  # 重置错误标记
                last_cycle_success = True
            else:
                if not error_reported_for_failure:
                    send_error_report(error_detail)
                    error_reported_for_failure = True
                last_cycle_success = False
            # 等待下一个周期
            loop_duration = time.time() - start_time
            log_with_timestamp(f"本次循环总耗时: {loop_duration:.2f}秒")
            log_with_timestamp(f"等待 {detailsTime} 秒后进行下一次检查...")
            time.sleep(detailsTime)
        except Exception as e:
            error_detail = f"主循环未捕获异常: {e}"
            log_with_timestamp(error_detail)
            if not error_reported_for_failure:
                send_error_report(error_detail)
                error_reported_for_failure = True
            last_cycle_success = False
            time.sleep(detailsTime)
        finally:
            if driver:
                try:
                    driver.quit()
                    cleanup_chrome_processes()
                except:
                    pass

if __name__ == "__main__":
    main()