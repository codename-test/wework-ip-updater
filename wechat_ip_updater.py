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
    
    # 确保配置目录存在
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
            # 创建配置文件后退出程序，让用户编辑配置
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
    {
        'interface': config['Settings']['interface1_interface']
    },
    {
        'interface': config['Settings']['interface2_interface']
    },
    {
        'interface': config['Settings']['interface3_interface']
    }
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

# Host网络模式检测
HOST_NETWORK_MODE = os.getenv('HOST_NETWORK_MODE', 'false').lower() == 'true'

# 按运营商分类的IP检测服务（增强移动网络检测）
IP_SERVICES_BY_ISP = {
    # 电信 - 增强电信网络检测
    "telecom": [
        "https://ip.3322.net",
        "http://www.net.cn/static/customercare/yourip.asp",
        "http://ddns.oray.com/checkip",
        "http://ip.cctv.cn",
        "https://myip.lefeng.com",
        "http://ip.taobao.com/service/getIpInfo2.php?ip=myip",
        "https://www.taobao.com/help/getip.php"
    ],
    # 联通 - 增强联通网络检测
    "unicom": [
        "http://www.ipplus360.com/getip",
        "http://members.3322.org/dyndns/getip",
        "http://ip.taobao.com/service/getIpInfo2.php?ip=myip",
        "https://www.ip.cn/api/index?ip=&type=0",
        "http://ip.uniqode.net",
        "https://ip.ustc.edu.cn"
    ],
    # 移动 - 特别增强移动网络检测
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
    # 教育网
    "edu": [
        "http://www.edu.cn/",
        "http://www.cernet.com/",
        "https://ip.ustc.edu.cn"
    ],
    # 国际通用
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

# 为每个接口分配不同的运营商优先级（按照您的要求）
INTERFACE_ISP_PRIORITY = {
    0: ["telecom", "unicom", "mobile", "international", "edu"],  # 接口1：优先电信
    1: ["unicom", "telecom", "mobile", "international", "edu"],  # 接口2：优先联通  
    2: ["mobile", "telecom", "unicom", "international", "edu"]   # 接口3：优先移动
}

def get_isp_services_for_interface(interface_index):
    """为指定接口获取按运营商优先级排序的IP检测服务"""
    isp_priority = INTERFACE_ISP_PRIORITY.get(interface_index, ["international", "telecom", "unicom", "mobile"])
    
    services = []
    for isp in isp_priority:
        if isp in IP_SERVICES_BY_ISP:
            # 随机打乱同一运营商内的服务顺序，避免总是使用同一个
            isp_services = IP_SERVICES_BY_ISP[isp].copy()
            random.shuffle(isp_services)
            services.extend(isp_services)
    
    # 记录使用的运营商策略
    isp_names = {
        "telecom": "电信",
        "unicom": "联通", 
        "mobile": "移动",
        "edu": "教育网",
        "international": "国际"
    }
    priority_names = [isp_names.get(isp, isp) for isp in isp_priority if isp in isp_names]
    
    # 根据接口索引显示更清晰的描述
    interface_desc = ["电信优先", "联通优先", "移动优先"][interface_index]
    log_with_timestamp(f"接口{interface_index+1}({interface_desc}) 运营商检测优先级: {' → '.join(priority_names)}")
    
    return services

def get_system_platform():
    """获取系统平台信息"""
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
    """检查命令是否可用"""
    try:
        if get_system_platform() == 'windows':
            result = subprocess.run(
                ['where', command] if command != 'ip' else ['where', 'ipconfig'],
                capture_output=True, 
                text=True,
                timeout=5
            )
        else:
            result = subprocess.run(
                ['which', command],
                capture_output=True, 
                text=True,
                timeout=5
            )
        return result.returncode == 0
    except Exception:
        return False

def check_curl_available():
    """检查curl命令是否可用"""
    try:
        result = subprocess.run(['curl', '--version'], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception as e:
        log_with_timestamp(f"curl命令检查失败: {e}")
        return False

def get_interface_ip(interface_name):
    """获取指定网卡接口的IP地址"""
    try:
        # 方法1: 使用netifaces库（推荐）
        try:
            addresses = netifaces.ifaddresses(interface_name)
            if netifaces.AF_INET in addresses:
                for addr_info in addresses[netifaces.AF_INET]:
                    ip = addr_info.get('addr')
                    if ip and ip != '127.0.0.1' and not ip.startswith('169.254'):
                        return ip
        except (ValueError, KeyError):
            pass
        
        # 方法2: 使用ip命令 (Linux)
        if check_command_available('ip'):
            try:
                result = subprocess.run(
                    ['ip', '-4', 'addr', 'show', interface_name],
                    capture_output=True, 
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if ip_match:
                        return ip_match.group(1)
            except Exception as e:
                log_with_timestamp(f"使用ip命令获取{interface_name} IP失败: {e}")
        
        # 方法3: 使用ifconfig命令
        if check_command_available('ifconfig'):
            try:
                result = subprocess.run(
                    ['ifconfig', interface_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if ip_match:
                        return ip_match.group(1)
            except Exception as e:
                log_with_timestamp(f"使用ifconfig获取{interface_name} IP失败: {e}")
        
        log_with_timestamp(f"无法获取接口 {interface_name} 的IP地址")
        return None
        
    except Exception as e:
        log_with_timestamp(f"获取接口 {interface_name} IP地址失败: {e}")
        return None

def get_ip_using_curl_source_binding(interface_ip, display_name, interface_index):
    """使用curl通过源IP绑定获取公网IP，按运营商优先级"""
    # 获取该接口的运营商优先级服务列表
    isp_services = get_isp_services_for_interface(interface_index)
    successful_services = []
    
    for service_url in isp_services:
        try:
            cmd = [
                'curl', 
                '--interface', interface_ip,  # 使用源IP绑定
                '--connect-timeout', '8',
                '--max-time', '12', 
                '--retry', '1',
                '-s',
                service_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                # 特殊处理返回JSON的API
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
                    # 普通文本响应
                    ip_match = re.search(ip_pattern, result.stdout.strip())
                    if not ip_match:
                        continue
                    ip = ip_match.group()
                
                if is_valid_ip(ip):
                    # 获取服务所属运营商用于日志
                    isp_name = "未知"
                    for isp, services in IP_SERVICES_BY_ISP.items():
                        if service_url in services:
                            isp_names = {
                                "telecom": "电信",
                                "unicom": "联通", 
                                "mobile": "移动", 
                                "edu": "教育网",
                                "international": "国际"
                            }
                            isp_name = isp_names.get(isp, isp)
                            break
                    
                    # 根据接口索引显示更清晰的描述
                    interface_desc = ["电信线路", "联通线路", "移动线路"][interface_index]
                    log_with_timestamp(f"{interface_desc} {display_name} IP: {ip} (运营商: {isp_name}, 来源: {service_url})")
                    successful_services.append(service_url)
                    return ip
            elif result.returncode != 0:
                log_with_timestamp(f"接口 {display_name} {service_url} 请求失败: {result.stderr.strip()}")
                    
        except subprocess.TimeoutExpired:
            log_with_timestamp(f"接口 {display_name} {service_url} 请求超时")
        except Exception as e:
            log_with_timestamp(f"接口 {display_name} {service_url} 请求异常: {e}")
    
    # 如果所有服务都失败，记录成功的服务数量
    if successful_services:
        log_with_timestamp(f"接口 {display_name} 有{len(successful_services)}个服务返回了IP但格式无效")
    else:
        log_with_timestamp(f"接口 {display_name} 所有{len(isp_services)}个检测服务均失败")
    
    return "获取IP失败"

def get_ip_using_python_source_binding(interface_ip, display_name, interface_index):
    """使用Python通过源IP绑定获取公网IP，按运营商优先级"""
    # 获取该接口的运营商优先级服务列表
    isp_services = get_isp_services_for_interface(interface_index)
    
    try:
        # 创建自定义适配器绑定源IP
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
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for url in isp_services:
            try:
                response = session.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # 特殊处理返回JSON的API
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
                        # 普通文本响应
                        ip_match = re.search(ip_pattern, response.text.strip())
                        if not ip_match:
                            continue
                        ip = ip_match.group()
                    
                    if is_valid_ip(ip):
                        # 获取服务所属运营商用于日志
                        isp_name = "未知"
                        for isp, services in IP_SERVICES_BY_ISP.items():
                            if url in services:
                                isp_names = {
                                    "telecom": "电信",
                                    "unicom": "联通", 
                                    "mobile": "移动", 
                                    "edu": "教育网",
                                    "international": "国际"
                                }
                                isp_name = isp_names.get(isp, isp)
                                break
                        
                        # 根据接口索引显示更清晰的描述
                        interface_desc = ["电信线路", "联通线路", "移动线路"][interface_index]
                        log_with_timestamp(f"{interface_desc} {display_name}(Python) IP: {ip} (运营商: {isp_name})")
                        return ip
            except Exception as e:
                log_with_timestamp(f"接口 {display_name} Python请求失败 {url}: {e}")
    
    except Exception as e:
        log_with_timestamp(f"使用Python绑定获取接口 {display_name} IP失败: {e}")
    
    return "获取IP失败"

def CheckIPs():
    """
    检查三个接口的IP地址变化 - 按运营商优先级版本
    返回: (changed, new_ips)
    """
    global current_ips
    
    log_with_timestamp("开始获取各接口IP地址（电信→联通→移动优先级）...")
    
    new_ips = []
    changed = False
    
    # 为每个接口获取IP
    for i, interface_config in enumerate(interface_configs):
        interface_name = interface_config['interface']
        display_name = f"接口{i+1}"
        
        # 根据接口索引显示更清晰的描述
        interface_desc = ["电信线路", "联通线路", "移动线路"][i]
        log_with_timestamp(f"检查{display_name}({interface_desc}) - 网卡: {interface_name}")
        
        # 获取接口本地IP
        local_ip = get_interface_ip(interface_name)
        if not local_ip:
            log_with_timestamp(f"无法获取{display_name}的本地IP，跳过该接口")
            new_ips.append("获取IP失败")
            continue
        
        log_with_timestamp(f"{display_name} 本地IP: {local_ip}")
        
        # 方法1: 使用curl通过源IP绑定获取公网IP（按运营商优先级）
        ip = get_ip_using_curl_source_binding(local_ip, display_name, i)
        
        # 方法2: 如果curl失败，尝试Python绑定（按运营商优先级）
        if ip == "获取IP失败":
            log_with_timestamp(f"尝试使用Python绑定获取{display_name} IP")
            ip = get_ip_using_python_source_binding(local_ip, display_name, i)
        
        new_ips.append(ip)
        
        # 检查IP是否发生变化
        if ip != "获取IP失败" and ip != current_ips[i]:
            changed = True
            log_with_timestamp(f"检测到{display_name} IP变化: {current_ips[i]} → {ip}")
            current_ips[i] = ip
        
        # 在接口间添加延迟
        if i < len(interface_configs) - 1:
            time.sleep(2)
    
    # 检查获取到的IP是否有重复
    valid_ips = [ip for ip in new_ips if ip != "获取IP失败"]
    unique_ips = set(valid_ips)
    
    if len(valid_ips) > 1 and len(unique_ips) < len(valid_ips):
        log_with_timestamp("警告：获取到的接口IP有重复，可能未正确区分线路")
        for ip in unique_ips:
            count = valid_ips.count(ip)
            if count > 1:
                log_with_timestamp(f"IP {ip} 出现了 {count} 次")
    
    return changed, new_ips

def is_valid_ip(ip):
    """验证IP地址格式"""
    if ip == "获取IP失败":
        return False
        
    parts = ip.split('.')
    if len(parts) != 4:
        return False
        
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False
            
    return True

def send_error_report(error_message):
    """发送错误报告到Webhook，并确保24小时内只发送一次"""
    if not webhook_url:
        log_with_timestamp("Webhook URL未配置，跳过错误报告")
        return
    
    last_sent_time = None
    if os.path.exists(error_report_file):
        try:
            with open(error_report_file, 'r') as f:
                report_data = json.load(f)
                last_sent_time = datetime.fromisoformat(report_data['last_sent'])
        except Exception as e:
            log_with_timestamp(f"读取错误报告文件失败: {e}")
    
    current_time = datetime.now()
    if last_sent_time and current_time - last_sent_time < timedelta(hours=24):
        log_with_timestamp("24小时内已发送过错误报告，本次跳过")
        return
    
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"企业微信IP更新器发生错误:\n{error_message}\n时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            log_with_timestamp("错误报告发送成功")
            with open(error_report_file, 'w') as f:
                json.dump({'last_sent': current_time.isoformat()}, f)
        else:
            log_with_timestamp(f"错误报告发送失败，状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        log_with_timestamp(f"发送错误报告时出错: {e}")

def setup_chrome_options():
    """优化的Chrome选项设置"""
    options = webdriver.ChromeOptions()
    
    # 1. 核心无头模式参数 - 修复稳定性
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # 2. 性能与稳定性优化
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    
    # 3. 资源限制与沙箱优化
    options.add_argument('--memory-pressure-off')
    options.add_argument('--max_old_space_size=512')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--remote-debugging-port=0')  # 自动选择端口
    options.add_argument('--user-data-dir=/tmp/chrome-data')
    
    # 4. 安全与网络优化
    options.add_argument('--disable-web-security')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-software-rasterizer')
    
    # 5. 页面加载策略优化
    options.page_load_strategy = 'eager'  # 关键优化，不等待资源加载完成
    
    # 6. 实验性选项
    options.add_experimental_option('excludeSwitches', [
        'enable-automation',
        'enable-logging',
        'ignore-certificate-errors'
    ])
    options.add_experimental_option('prefs', {
        'profile.default_content_setting_values.notifications': 2,
        'profile.default_content_settings.popups': 0,
        'profile.managed_default_content_settings.images': 2,
    })
    
    return options

def create_chrome_service():
    """创建Chrome服务配置"""
    service = Service()
    # 优化服务参数
    service.creationflags = 0  # 在Linux下不需要特殊标志
    return service

def cleanup_chrome_processes():
    """清理可能的Chrome残留进程"""
    try:
        subprocess.run(['pkill', '-f', 'chrome'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-f', 'chromedriver'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception as e:
        log_with_timestamp(f"清理Chrome进程时出错: {e}")

def OpenBrowser():
    """启动浏览器并访问企业微信 - 增加重试机制"""
    log_with_timestamp("启动Chrome浏览器访问企业微信")
    
    for attempt in range(CHROME_MAX_RETRIES):
        start_time = time.time()
        driver = None
        
        try:
            cookies = cookie_header.split(';')
            
            # 清理可能的残留进程
            if attempt > 0:
                cleanup_chrome_processes()
                log_with_timestamp(f"第 {attempt + 1} 次尝试启动浏览器...")
            
            # 使用优化的Chrome选项
            options = setup_chrome_options()
            service = create_chrome_service()
            
            # 尝试创建驱动
            log_with_timestamp("正在初始化Chrome驱动...")
            driver = webdriver.Chrome(service=service, options=options)
            
            log_with_timestamp(f"Chrome驱动初始化完成，耗时: {time.time() - start_time:.2f}秒")
            
            # 设置合理的超时时间
            driver.set_page_load_timeout(15)  # 减少页面加载超时
            driver.set_script_timeout(10)
            driver.implicitly_wait(5)
            
            log_with_timestamp(f"访问URL: {wechatUrl}")
            driver.get(wechatUrl)
            
            # 使用更短的等待时间检查页面基本元素
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            log_with_timestamp(f"页面加载完成，总耗时: {time.time() - start_time:.2f}秒")
            
            # 应用cookies
            try:
                driver.delete_all_cookies()
                
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
                driver.refresh()  # 使用refresh而不是重新get
                time.sleep(1)
                
            except Exception as e:
                error_msg = f"应用cookies异常: {e}"
                log_with_timestamp(error_msg)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                if attempt == CHROME_MAX_RETRIES - 1:
                    send_error_report(error_msg)
                continue
            
            # 检查登录状态
            try:
                # 使用更短的超时时间检查登录状态
                login_element = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'login_stage_title_text'))
                )
                error_msg = "登录状态失效，请更新cookie"
                log_with_timestamp(error_msg)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                if attempt == CHROME_MAX_RETRIES - 1:
                    send_error_report(error_msg)
                continue
            except TimeoutException:
                log_with_timestamp("登录状态验证成功")
                return driver
            except Exception as e:
                error_msg = f"登录状态检查异常: {e}"
                log_with_timestamp(error_msg)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                if attempt == CHROME_MAX_RETRIES - 1:
                    send_error_report(error_msg)
                continue
            
        except WebDriverException as e:
            error_msg = f"浏览器启动或页面加载异常(尝试 {attempt + 1}/{CHROME_MAX_RETRIES}): {str(e)}"
            log_with_timestamp(error_msg)
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            if attempt == CHROME_MAX_RETRIES - 1:
                send_error_report(error_msg)
                return None
            else:
                wait_time = CHROME_RETRY_DELAY * (attempt + 1)
                log_with_timestamp(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                
        except Exception as e:
            error_msg = f"浏览器初始化异常(尝试 {attempt + 1}/{CHROME_MAX_RETRIES}): {str(e)}"
            log_with_timestamp(error_msg)
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            if attempt == CHROME_MAX_RETRIES - 1:
                send_error_report(error_msg)
                return None
            else:
                wait_time = CHROME_RETRY_DELAY * (attempt + 1)
                log_with_timestamp(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    
    return None

def ChangeIP(driver, new_ips):
    """更新企业微信可信IP地址"""
    try:
        log_with_timestamp("尝试更改企业微信可信IP地址")
        
        # 准备要设置的IP内容
        valid_ips = [ip for ip in new_ips if ip != "获取IP失败"]
        if not valid_ips:
            log_with_timestamp("没有有效的IP地址可以设置")
            return
            
        # 去重处理
        unique_ips = list(set(valid_ips))
        new_ips_str = ';'.join(unique_ips)
        
        if len(unique_ips) < len(valid_ips):
            log_with_timestamp(f"检测到重复IP，去重后设置: {new_ips_str}")
        
        settings_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[contains(@class, "app_card_operate") and contains(@class, "js_show_ipConfig_dialog")]'))
        )
        
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'});", settings_button)
        time.sleep(0.5)
        
        driver.execute_script("arguments[0].click();", settings_button)
        log_with_timestamp("已点击设置按钮")
        
        log_with_timestamp("等待对话框加载...")
        try:
            input_area = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
            )
            log_with_timestamp("对话框加载成功")
        except TimeoutException:
            log_with_timestamp("标准输入框加载超时，尝试备用定位方式...")
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, '//div[contains(text(), "设置可信IP") or contains(text(), "可信IP")]'))
            )
            log_with_timestamp("检测到对话框标题，尝试再次定位输入框...")
            input_area = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
            )
            log_with_timestamp("成功定位到输入框")
        
        current_ips_str = input_area.get_attribute('value').strip()
        log_with_timestamp(f"当前已设置IP: {current_ips_str}")
        log_with_timestamp(f"准备设置新IP: {new_ips_str}")
        
        # 清空并输入新IP
        driver.execute_script("arguments[0].value = '';", input_area)
        input_area.send_keys(new_ips_str)
        log_with_timestamp(f"已设置新IP: {new_ips_str}")
        
        confirm_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@class, "js_ipConfig_confirmBtn")]'))
        )
        driver.execute_script("arguments[0].click();", confirm_button)
        log_with_timestamp("已提交IP变更")
        
        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((By.XPATH, '//div[contains(@class, "js_ipConfig_dialog")]'))
            )
            log_with_timestamp("IP地址更新成功")
        except TimeoutException:
            log_with_timestamp("警告：未检测到对话框关闭，但操作可能已完成")
        
    except TimeoutException:
        error_msg = "操作超时，未能找到页面元素"
        log_with_timestamp(error_msg)
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"timeout_error_{timestamp}.png"
            driver.save_screenshot(filename)
            log_with_timestamp(f"已保存超时错误截图: {filename}")
            error_msg += f"\n已保存截图: {filename}"
        except:
            log_with_timestamp("无法保存截图")
        send_error_report(error_msg)
    except NoSuchElementException:
        error_msg = "页面元素不存在"
        log_with_timestamp(error_msg)
        send_error_report(error_msg)
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
            log_with_timestamp("无法保存截图")
        send_error_report(error_msg)

# 主程序循环
def main():
    global current_ips
    
    # 初始化日志
    log_with_timestamp("企业微信三接口IP更新器启动（电信→联通→移动优先级）")
    
    # 显示接口配置和线路分配
    interface_descs = ["电信线路", "联通线路", "移动线路"]
    for i, config in enumerate(interface_configs):
        log_with_timestamp(f"接口{i+1}({interface_descs[i]}) - 网卡: {config['interface']}")
    
    # 检查网卡接口可用性
    for i, config in enumerate(interface_configs):
        interface_desc = interface_descs[i]
        local_ip = get_interface_ip(config['interface'])
        if local_ip:
            log_with_timestamp(f"接口{i+1}({interface_desc}) 网卡 {config['interface']} 状态: 可用, 本地IP: {local_ip}")
        else:
            log_with_timestamp(f"警告: 接口{i+1}({interface_desc}) 网卡 {config['interface']} 不可用或未分配IP")
    
    # 检查curl是否可用
    if not check_curl_available():
        log_with_timestamp("错误：curl命令不可用，请确保系统中已安装curl")
        send_error_report("curl命令不可用，请确保系统中已安装curl")
        return
    
    # 运行主循环
    consecutive_failures = 0
    max_consecutive_failures = 3
    
    while True:
        driver = None
        try:
            start_loop_time = time.time()
            
            driver = OpenBrowser()
            if not driver:
                consecutive_failures += 1
                log_with_timestamp(f"浏览器初始化失败，连续失败次数: {consecutive_failures}")
                
                if consecutive_failures >= max_consecutive_failures:
                    error_msg = f"连续{consecutive_failures}次浏览器初始化失败，暂停重试"
                    log_with_timestamp(error_msg)
                    send_error_report(error_msg)
                    consecutive_failures = 0
                    log_with_timestamp("等待120秒后继续...")
                    time.sleep(120)
                else:
                    wait_time = consecutive_failures * 15
                    log_with_timestamp(f"将在{wait_time}秒后重试...")
                    time.sleep(wait_time)
                continue
            
            # 重置连续失败计数
            consecutive_failures = 0
                
            # 检查三个接口的IP变化
            changed, new_ips = CheckIPs()
            
            # 记录当前IP状态
            interface_descs = ["电信线路", "联通线路", "移动线路"]
            for i, ip in enumerate(current_ips):
                log_with_timestamp(f"当前接口{i+1}({interface_descs[i]}) IP: {ip}")
            
            # 如果有任一接口IP发生变化，则更新企业微信设置
            if changed:
                log_with_timestamp("检测到IP变化，开始更新企业微信设置")
                ChangeIP(driver, new_ips)
                
                # 更新后记录最终状态
                for i, ip in enumerate(current_ips):
                    log_with_timestamp(f"更新后接口{i+1}({interface_descs[i]}) IP: {ip}")
            else:
                log_with_timestamp("所有接口IP均未发生变化")
            
            loop_duration = time.time() - start_loop_time
            log_with_timestamp(f"本次循环总耗时: {loop_duration:.2f}秒")
            log_with_timestamp(f"等待 {detailsTime} 秒后进行下一次检查...")
            time.sleep(detailsTime)
            
        except Exception as e:
            consecutive_failures += 1
            error_msg = f"主循环发生错误: {e}"
            log_with_timestamp(error_msg)
            send_error_report(error_msg)
            
            if consecutive_failures >= max_consecutive_failures:
                log_with_timestamp(f"连续{consecutive_failures}次失败，暂停重试")
                consecutive_failures = 0
                time.sleep(120)
            else:
                wait_time = consecutive_failures * 15
                time.sleep(wait_time)
        finally:
            if driver:
                try:
                    driver.quit()
                    log_with_timestamp("浏览器已关闭")
                    # 清理可能的残留进程
                    cleanup_chrome_processes()
                except:
                    log_with_timestamp("关闭浏览器时发生异常")

if __name__ == "__main__":
    main()