# ========== 全局状态变量 ==========
last_error_time = None          # 上次错误报告时间（用于限流）
last_recovery_time = None       # 上次恢复通知时间（可选，避免短时间内多次恢复）
error_reported_for_failure = False  # 当前连续失败周期中是否已发送过错误报告
last_cycle_success = True            # 上一次完整周期是否成功（初始为True，避免刚启动就发恢复）

# ========== 修改 send_error_report，增加限流（24小时） ==========
def send_error_report(error_message):
    """发送错误报告到Webhook，24小时内只发送一次"""
    global last_error_time
    
    if not webhook_url:
        log_with_timestamp("Webhook URL未配置，跳过错误报告")
        return
    
    current_time = datetime.now()
    # 24小时内已发送过，跳过
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

# ========== 修改 send_recovery_report，增加限流（24小时） ==========
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

# ========== 修改 ChangeIP，移除内部错误报告发送，只返回成功与否 ==========
def ChangeIP(driver, new_ips):
    """更新企业微信可信IP地址，返回 (success, error_message)"""
    try:
        log_with_timestamp("尝试更改企业微信可信IP地址")
        
        # 准备要设置的IP内容（保留顺序 + 去重）
        valid_ips = [ip for ip in new_ips if ip != "获取IP失败" and not ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.', '127.0.0.', '169.254.'))]
        
        # 保留顺序去重
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
            log_with_timestamp(f"检测到重复IP，去重后设置: {new_ips_str}")
        
        # 点击设置按钮
        settings_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[contains(@class, "app_card_operate") and contains(@class, "js_show_ipConfig_dialog")]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", settings_button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", settings_button)
        log_with_timestamp("已点击设置按钮")
        
        # 等待对话框输入框
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
        
        # 等待对话框关闭
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.XPATH, '//div[contains(@class, "js_ipConfig_dialog")]'))
        )
        log_with_timestamp("✅ IP地址更新成功")
        return True, ""
        
    except TimeoutException as e:
        error_msg = f"操作超时，未能找到页面元素: {e}"
        log_with_timestamp(error_msg)
        # 尝试截图
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"timeout_error_{timestamp}.png"
            driver.save_screenshot(filename)
            log_with_timestamp(f"已保存超时错误截图: {filename}")
            error_msg += f"\n已保存截图: {filename}"
        except:
            pass
        return False, error_msg
    except NoSuchElementException as e:
        error_msg = f"页面元素不存在: {e}"
        log_with_timestamp(error_msg)
        return False, error_msg
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

# ========== 修改 OpenBrowser，移除内部恢复通知，只做重试 ==========
def OpenBrowser():
    """启动浏览器并访问企业微信，成功返回driver，失败返回None（内部重试3次）"""
    log_with_timestamp("启动Chrome浏览器访问企业微信")
    
    for attempt in range(CHROME_MAX_RETRIES):
        start_time = time.time()
        driver = None
        try:
            # 清理可能的残留进程（仅重试时）
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
            
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
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
                raise  # 抛出异常让外层重试
            
            # 检查登录状态（如果出现登录界面则视为失败）
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'login_stage_title_text'))
                )
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

# ========== 修改主循环 ==========
def main():
    global current_ips, error_reported_for_failure, last_cycle_success
    
    log_with_timestamp("企业微信三接口IP更新器启动（电信→联通→移动优先级）")
    # 显示接口配置...
    for i, config in enumerate(interface_configs):
        log_with_timestamp(f"接口{i+1} - 网卡: {config['interface']}")
    
    if not check_curl_available():
        log_with_timestamp("错误：curl命令不可用")
        send_error_report("curl命令不可用")
        return
    
    # 主循环
    while True:
        driver = None
        cycle_success = False   # 本次周期是否成功
        error_detail = ""       # 失败时的详细信息
        
        try:
            start_time = time.time()
            
            # 1. 启动浏览器
            driver = OpenBrowser()
            if not driver:
                error_detail = "浏览器启动失败（重试3次后仍失败）"
                log_with_timestamp(error_detail)
                cycle_success = False
            else:
                # 2. 检查IP变化
                try:
                    changed, new_ips = CheckIPs()
                except Exception as e:
                    error_detail = f"IP检测过程发生异常: {e}"
                    log_with_timestamp(error_detail)
                    changed = False
                    cycle_success = False
                
                # 3. 如果有变化，则执行变更
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
                    # 没有变化，且没有异常，视为成功
                    cycle_success = True
                    log_with_timestamp("所有接口IP均未发生变化，无需更新")
            
            # 4. 处理通知（成功/失败）
            if cycle_success:
                # 如果上一次周期是失败的，则发送恢复通知
                if not last_cycle_success:
                    log_with_timestamp("从故障中恢复，发送恢复通知")
                    send_recovery_report()
                    # 重置错误限流标志，以便下次失败能重新发送错误报告
                    error_reported_for_failure = False
                last_cycle_success = True
            else:
                # 当前周期失败，且本连续失败周期内尚未发送错误报告，则发送
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
            # 捕获主循环中未预料的异常，视为失败
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