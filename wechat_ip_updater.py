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

# 读取JSON配置文件
with open('updater-config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 从配置文件获取参数
ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# 从配置文件获取三个接口IP
interface_ips = [
    config['Settings']['interface1_ip'],  # 第一个接口IP
    config['Settings']['interface2_ip'],  # 第二个接口IP
    config['Settings']['interface3_ip']   # 第三个接口IP
]

# 当前IP地址存储
current_ips = ['192.168.1.1', '192.168.1.1', '192.168.1.1']  # 三个接口的当前IP
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

def get_timestamp():
    """获取当前时间戳"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log_with_timestamp(message):
    """带时间戳的日志输出"""
    print(f"[{get_timestamp()}] {message}")

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

def check_curl_available():
    """检查curl命令是否可用"""
    try:
        result = subprocess.run(['curl', '--version'], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception as e:
        log_with_timestamp(f"curl命令检查失败: {e}")
        return False

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

def get_ip_using_curl(interface_ip, interface_name):
    """使用curl命令通过指定源IP获取公网IP"""
    ip_services = [
        "http://ipv4.icanhazip.com",
        "https://4.ipw.cn", 
        "http://checkip.amazonaws.com",
        "https://api.ipify.org",
        "http://myexternalip.com/raw",
        "http://ifconfig.me/ip",
        "http://ident.me",
        "http://ipecho.net/plain"
    ]
    
    for service_url in ip_services:
        try:
            cmd = [
                'curl', 
                '--interface', interface_ip,
                '--connect-timeout', '5',
                '--max-time', '8', 
                '--retry', '1',
                '-s',
                service_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                ip_match = re.search(ip_pattern, result.stdout.strip())
                if ip_match and is_valid_ip(ip_match.group()):
                    log_with_timestamp(f"接口 {interface_name}({interface_ip}) IP: {ip_match.group()} (来源: {service_url})")
                    return ip_match.group()
        except subprocess.TimeoutExpired:
            log_with_timestamp(f"接口 {interface_name} curl命令超时: {service_url}")
        except Exception as e:
            log_with_timestamp(f"接口 {interface_name} curl命令异常 {service_url}: {e}")
    
    log_with_timestamp(f"接口 {interface_name} 所有curl查询服务均失败")
    return "获取IP失败"

def get_ip_using_python_requests(interface_ip, interface_name):
    """使用Python requests通过绑定源IP获取公网IP"""
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
        
        ip_services = [
            "http://ipv4.icanhazip.com",
            "https://4.ipw.cn",
            "http://checkip.amazonaws.com"
        ]
        
        for url in ip_services:
            try:
                response = session.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    ip_match = re.search(ip_pattern, response.text.strip())
                    if ip_match and is_valid_ip(ip_match.group()):
                        log_with_timestamp(f"接口 {interface_name}({interface_ip}) IP(Python): {ip_match.group()}")
                        return ip_match.group()
            except Exception as e:
                log_with_timestamp(f"接口 {interface_name} Python请求失败 {url}: {e}")
    
    except Exception as e:
        log_with_timestamp(f"使用Python requests获取接口 {interface_name} IP失败: {e}")
    
    return "获取IP失败"

def get_ip_from_isp_specific_service(interface_name, interface_index):
    """从运营商特定的IP查询服务获取IP"""
    # 为不同接口使用不同的查询服务，增加获取不同IP的机会
    if interface_index == 0:  # 接口1
        specific_urls = [
            "https://ip.3322.net",
            "http://ip.taobao.com/service/getIpInfo2.php?ip=myip"
        ]
    elif interface_index == 1:  # 接口2
        specific_urls = [
            "https://ip.cn/api/index?ip=&type=0",
            "http://whois.pconline.com.cn/ipJson.jsp"
        ]
    else:  # 接口3
        specific_urls = [
            "http://www.net.cn/static/customercare/yourip.asp",
            "https://www.ip138.com/"
        ]
    
    for url in specific_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # 尝试从响应中提取IP地址
                ip_match = re.search(ip_pattern, response.text)
                if ip_match and is_valid_ip(ip_match.group()):
                    log_with_timestamp(f"接口 {interface_name} IP(特定服务): {ip_match.group()}")
                    return ip_match.group()
                
                # 尝试解析JSON响应
                if 'application/json' in response.headers.get('Content-Type', ''):
                    try:
                        data = response.json()
                        # 尝试从常见JSON字段中提取IP
                        ip_fields = ['ip', 'IP', 'query', 'addr']
                        for field in ip_fields:
                            if field in data and is_valid_ip(str(data[field])):
                                log_with_timestamp(f"接口 {interface_name} IP(JSON): {data[field]}")
                                return data[field]
                    except:
                        pass
        except Exception as e:
            log_with_timestamp(f"接口 {interface_name} 特定服务请求失败 {url}: {e}")
    
    return "获取IP失败"

def CheckIPs():
    """
    检查三个接口的IP地址变化
    返回: (changed, new_ips)
    """
    global current_ips
    
    log_with_timestamp("开始获取各接口IP地址...")
    
    new_ips = []
    changed = False
    
    # 为每个接口获取IP，使用不同的方法和延迟
    for i, interface_ip in enumerate(interface_ips):
        interface_name = f"接口{i+1}"
        
        # 方法1: 使用curl命令获取IP
        ip = get_ip_using_curl(interface_ip, interface_name)
        
        # 方法2: 如果curl失败，尝试Python requests绑定源IP
        if ip == "获取IP失败":
            log_with_timestamp(f"尝试使用Python requests获取{interface_name} IP")
            ip = get_ip_using_python_requests(interface_ip, interface_name)
        
        # 方法3: 如果仍然失败，尝试运营商特定服务
        if ip == "获取IP失败":
            log_with_timestamp(f"尝试使用特定服务获取{interface_name} IP")
            ip = get_ip_from_isp_specific_service(interface_name, i)
        
        new_ips.append(ip)
        
        # 检查IP是否发生变化
        if ip != "获取IP失败" and ip != current_ips[i]:
            changed = True
            log_with_timestamp(f"检测到接口{i+1} IP变化: {current_ips[i]} -> {ip}")
            current_ips[i] = ip
        
        # 在接口间添加延迟，减少同时请求导致的相同IP问题
        if i < len(interface_ips) - 1:
            time.sleep(2)
    
    # 检查获取到的IP是否有重复
    valid_ips = [ip for ip in new_ips if ip != "获取IP失败"]
    unique_ips = set(valid_ips)
    
    if len(valid_ips) > 1 and len(unique_ips) < len(valid_ips):
        log_with_timestamp("警告：获取到的接口IP有重复，可能未正确区分线路")
        # 记录重复的IP
        for ip in unique_ips:
            count = valid_ips.count(ip)
            if count > 1:
                log_with_timestamp(f"IP {ip} 出现了 {count} 次")
    
    # 如果所有IP都相同，只保留一个
    if len(unique_ips) == 1 and len(valid_ips) > 1:
        log_with_timestamp("所有接口获取到相同的IP，将只设置一个IP")
        unique_ip = list(unique_ips)[0]
        new_ips = [unique_ip if ip != "获取IP失败" else "获取IP失败" for ip in new_ips]
        # 只更新第一个接口的IP，避免重复设置
        for i in range(1, len(current_ips)):
            if current_ips[i] != "获取IP失败":
                current_ips[i] = unique_ip
    
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
    log_with_timestamp("企业微信三接口IP更新器启动（优化Chrome版本）")
    log_with_timestamp(f"接口1 IP: {interface_ips[0]}")
    log_with_timestamp(f"接口2 IP: {interface_ips[1]}")
    log_with_timestamp(f"接口3 IP: {interface_ips[2]}")
    
    # 检查配置问题
    if interface_ips[0] == interface_ips[2]:
        log_with_timestamp("警告：接口1和接口3的IP地址相同，这可能导致无法正确区分线路")
    
    # 检查curl是否可用
    if not check_curl_available():
        log_with_timestamp("错误：curl命令不可用，请确保系统中已安装curl")
        send_error_report("curl命令不可用，请确保系统中已安装curl")
        return
    
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
            for i, ip in enumerate(current_ips):
                log_with_timestamp(f"当前接口{i+1} IP: {ip}")
            
            # 如果有任一接口IP发生变化，则更新企业微信设置
            if changed:
                log_with_timestamp("检测到IP变化，开始更新企业微信设置")
                ChangeIP(driver, new_ips)
                
                # 更新后记录最终状态
                for i, ip in enumerate(current_ips):
                    log_with_timestamp(f"更新后接口{i+1} IP: {ip}")
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