import re
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import requests
import os
from datetime import datetime, timedelta

# 读取JSON配置文件
with open('updater-config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 从配置文件获取参数
ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
ip_urls = ["https://ip.3322.net", "http://ipv4.icanhazip.com", "https://4.ipw.cn"]
current_ip_address = '192.168.1.1'
overwrite = True
wechatUrl = config['Settings']['wechatUrl']
cookie_header = config['Settings']['cookie_header']
detailsTime = config['Settings']['detailsTime']

# 新增错误报告配置
webhook_url = config['Settings'].get('webhook_url', '')  # Webhook URL
error_report_file = config['Settings'].get('error_report_file', 'error_report.json')  # 错误报告文件

def send_error_report(error_message):
    """发送错误报告到Webhook，并确保24小时内只发送一次"""
    # 检查Webhook URL是否配置
    if not webhook_url:
        print("Webhook URL未配置，跳过错误报告")
        return
    
    # 检查错误报告文件是否存在
    last_sent_time = None
    if os.path.exists(error_report_file):
        try:
            with open(error_report_file, 'r') as f:
                report_data = json.load(f)
                last_sent_time = datetime.fromisoformat(report_data['last_sent'])
        except Exception as e:
            print(f"读取错误报告文件失败: {e}")
    
    # 检查是否在24小时内发送过
    current_time = datetime.now()
    if last_sent_time and current_time - last_sent_time < timedelta(hours=24):
        print("24小时内已发送过错误报告，本次跳过")
        return
    
    # 准备发送数据
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
            print("错误报告发送成功")
            # 更新发送时间
            with open(error_report_file, 'w') as f:
                json.dump({'last_sent': current_time.isoformat()}, f)
        else:
            print(f"错误报告发送失败，状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        print(f"发送错误报告时出错: {e}")

def OpenBrowser():
    print("启动Chrome浏览器访问企业微信")
    cookies = cookie_header.split(';')
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=options)
    
    try:
        print(f"访问URL: {wechatUrl}")
        driver.get(wechatUrl)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    except Exception as e:
        error_msg = f"页面加载异常: {str(e)}"
        print(error_msg)
        driver.quit()
        send_error_report(error_msg)
        return None
    
    # 清除旧cookies并添加新cookies
    driver.delete_all_cookies()
    
    for cookie in cookies:
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            driver.add_cookie({
                "name": name.strip(), 
                "value": value.strip(),
                "domain": ".work.weixin.qq.com",
                "path": "/",
                "secure": True if wechatUrl.startswith('https') else False
            })
    
    print("重新加载页面应用cookies")
    driver.get(wechatUrl)
    time.sleep(2)
    
    # 检查登录状态
    try:
        login_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'login_stage_title_text'))
        )
        error_msg = "登录状态失效，请更新cookie"
        print(error_msg)
        driver.quit()
        send_error_report(error_msg)
        return None
    except TimeoutException:
        print("登录状态验证成功")
        return driver
    except Exception as e:
        error_msg = f"登录状态检查异常: {e}"
        print(error_msg)
        driver.quit()
        send_error_report(error_msg)
        return None

def CheckIP():
    print("获取最新公网IP地址...")
    global current_ip_address
    valid_ip = None
    
    for url in ip_urls:
        try:
            ip_address = get_ip_from_url(url)
            if ip_address != "获取IP失败":
                print(f"成功获取IP: {url} → {ip_address}")
                valid_ip = ip_address
                break
            else:
                print(f"请求失败: {url}")
        except Exception as e:
            error_msg = f"IP获取异常 {url}: {e}"
            print(error_msg)
            send_error_report(error_msg)
    
    if not valid_ip:
        print("所有IP源均不可用，使用上次记录的IP")
        return False
    
    if valid_ip != current_ip_address:
        print(f"检测到IP变化: {current_ip_address} → {valid_ip}")
        current_ip_address = valid_ip
        return True
    else:
        print("IP地址未发生变化")
        return False

def get_ip_from_url(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            ip_match = re.search(ip_pattern, response.text)
            return ip_match.group() if ip_match else "获取IP失败"
        else:
            return "获取IP失败"
    except Exception as e:
        print(f"IP获取失败 {url}: {e}")
        return "获取IP失败"

def ChangeIP(driver):
    try:
        print("尝试更改企业微信可信IP地址")
        
        # 使用JavaScript滚动到元素位置并点击
        settings_button = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "app_card_operate") and contains(@class, "js_show_ipConfig_dialog")]'))
        )
        
        # 滚动到元素位置
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'});", settings_button)
        time.sleep(0.5)
        
        # 使用JavaScript直接点击
        driver.execute_script("arguments[0].click();", settings_button)
        print("已点击设置按钮")
        
        # 等待对话框完全加载 - 使用更可靠的等待条件
        print("等待对话框加载...")
        try:
            # 尝试等待输入框出现
            input_area = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
            )
            print("对话框加载成功")
        except TimeoutException:
            print("标准输入框加载超时，尝试备用定位方式...")
            # 尝试定位对话框标题作为备选
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, '//div[contains(text(), "设置可信IP") or contains(text(), "可信IP")]'))
            )
            print("检测到对话框标题，尝试再次定位输入框...")
            input_area = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//textarea[contains(@class, "js_ipConfig_textarea")]'))
            )
            print("成功定位到输入框")
        
        # 获取当前已设置的IP
        current_ips = input_area.get_attribute('value').strip()
        print(f"当前已设置IP: {current_ips}")
        
        # 准备新的IP内容
        if overwrite:
            new_ips = current_ip_address
        else:
            # 追加模式，确保不重复添加
            ips = [ip.strip() for ip in current_ips.split(';') if ip.strip()]
            if current_ip_address in ips:
                print("IP已存在于列表中，无需添加")
                # 关闭对话框
                cancel_button = driver.find_element(By.XPATH, '//a[contains(@class, "js_ipConfig_cancelBtn")]')
                driver.execute_script("arguments[0].click();", cancel_button)
                return
            new_ips = f"{current_ips};{current_ip_address}" if current_ips else current_ip_address
        
        # 清空并输入新IP
        driver.execute_script("arguments[0].value = '';", input_area)
        input_area.send_keys(new_ips)
        print(f"已设置新IP: {new_ips}")
        
        # 定位确认按钮并使用JavaScript点击
        confirm_button = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//a[contains(@class, "js_ipConfig_confirmBtn")]'))
        )
        driver.execute_script("arguments[0].click();", confirm_button)
        print("已提交IP变更")
        
        # 等待操作完成 - 检查对话框是否消失
        try:
            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.XPATH, '//div[contains(@class, "js_ipConfig_dialog")]'))
            )
            print("IP地址更新成功")
        except TimeoutException:
            print("警告：未检测到对话框关闭，但操作可能已完成")
        
    except TimeoutException:
        error_msg = "操作超时，未能找到页面元素"
        print(error_msg)
        # 尝试截屏以便调试
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"timeout_error_{timestamp}.png"
            driver.save_screenshot(filename)
            print(f"已保存超时错误截图: {filename}")
            error_msg += f"\n已保存截图: {filename}"
        except:
            print("无法保存截图")
        send_error_report(error_msg)
    except NoSuchElementException:
        error_msg = "页面元素不存在"
        print(error_msg)
        send_error_report(error_msg)
    except Exception as e:
        error_msg = f"更改IP地址失败: {e}"
        print(error_msg)
        # 尝试截屏以便调试
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"error_{timestamp}.png"
            driver.save_screenshot(filename)
            print(f"已保存错误截图: {filename}")
            error_msg += f"\n已保存截图: {filename}"
        except:
            print("无法保存截图")
        send_error_report(error_msg)

# 主程序循环
while True:
    driver = None
    try:
        driver = OpenBrowser()
        if not driver:
            print("浏览器初始化失败，将在5秒后重试...")
            time.sleep(5)
            continue
            
        if CheckIP():
            ChangeIP(driver)
            # 更新后再次验证
            CheckIP()
            
        print(f"等待 {detailsTime} 秒后进行下一次检查...")
        time.sleep(detailsTime)
        
    except Exception as e:
        error_msg = f"主循环发生错误: {e}"
        print(error_msg)
        send_error_report(error_msg)
        time.sleep(10)
    finally:
        if driver:
            driver.quit()
