# ================================================================
# 第一阶段：构建阶段 - 使用国内镜像加速
# ================================================================
FROM python:3.11-slim-bookworm as builder

# 设置Debian国内源（华为云镜像）
RUN set -e; \
    echo "设置华为云镜像源..."; \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list; \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list; \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list; \
    rm -rf /etc/apt/sources.list.d/*

# 安装基本工具和证书
RUN apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    apt-transport-https \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装系统构建依赖
RUN set -e; \
    for i in 1 2 3; do \
        apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
        apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        python3-dev \
        wget \
        curl \
        gnupg \
        # 安装Chromium构建依赖
        libnss3-dev \
        libxss1 \
        libasound2 \
        libxtst6 \
        libgtk-3-0 \
        libgbm-dev \
        && break || sleep $(($i * 15)); \
    done; \
    rm -rf /var/lib/apt/lists/*

# 设置pip国内源（清华大学镜像）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip config set global.timeout 300 && \
    pip config set global.retries 10 && \
    pip config set global.default-timeout 300

# 安装Python依赖
RUN set -e; \
    for i in 1 2 3; do \
        pip install --user --no-cache-dir --timeout 120 --retries 5 \
        requests \
        selenium \
        pyvirtualdisplay \
        webdriver-manager \
        netifaces \
        && break || sleep $(($i * 15)); \
    done

# ================================================================
# 第二阶段：运行阶段 - 最小化镜像
# ================================================================
FROM python:3.11-slim-bookworm

# 设置Debian国内源（华为云镜像）
RUN set -e; \
    echo "设置华为云镜像源..."; \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list; \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list; \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list; \
    rm -rf /etc/apt/sources.list.d/*

# 安装基本工具和证书
RUN apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    apt-transport-https \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY=:99 \
    PATH="/usr/lib/chromium:/root/.local/bin:${PATH}" \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    CHROME_BIN=/usr/bin/chromium \
    # Chrome优化环境变量
    CHROME_DRIVER_TIMEOUT=30 \
    CHROME_HEADLESS=true \
    WEBDRIVER_TIMEOUT=20 \
    # Host网络模式专用环境变量
    HOST_NETWORK_MODE=true \
    DOCKER_HOST_NETWORK=true

# 安装运行时依赖（包括Chromium和chromedriver）- 优化版本管理
RUN set -e; \
    for i in 1 2 3; do \
        apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
        # 明确指定版本以避免不匹配
        apt-get install -y --no-install-recommends \
        curl \
        net-tools \
        iproute2 \
        iputils-ping \
        dnsutils \
        iptables \
        ethtool \
        tcpdump \
        chromium \
        chromium-driver \
        libnss3 \
        libxss1 \
        libasound2 \
        libxtst6 \
        libgtk-3-0 \
        libgbm1 \
        libdrm2 \
        libxcb1 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libxkbcommon0 \
        xvfb \
        strace \
        procps \
        lsof \
        && break || sleep $(($i * 15)); \
    done; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \

    # 验证网络工具安装
    echo "验证网络工具安装:"; \
    echo "ifconfig: $(which ifconfig || echo 'not found')"; \
    echo "ip: $(which ip || echo 'not found')"; \
    echo "ping: $(which ping || echo 'not found')"; \
    echo "curl: $(which curl || echo 'not found')"; \
    echo "netstat: $(which netstat || echo 'not found')"; \
    echo "nc: $(which nc || echo 'not found')"; \
    echo "ethtool: $(which ethtool || echo 'not found')"; \
    # 验证Chromium安装和版本匹配
    echo "验证Chromium安装: $(chromium --version || echo 'chromium not found')"; \
    echo "验证ChromeDriver安装: $(chromedriver --version || echo 'chromedriver not found')"; \
    # 增强版本检查逻辑
    if command -v chromium >/dev/null 2>&1 && command -v chromedriver >/dev/null 2>&1; then \
        CHROMIUM_VERSION=$(chromium --version | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1); \
        CHROMEDRIVER_VERSION=$(chromedriver --version | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1); \
        echo "Chromium版本: $CHROMIUM_VERSION"; \
        echo "ChromeDriver版本: $CHROMEDRIVER_VERSION"; \
        # 检查主版本是否匹配
        CHROMIUM_MAJOR=$(echo "$CHROMIUM_VERSION" | cut -d. -f1); \
        CHROMEDRIVER_MAJOR=$(echo "$CHROMEDRIVER_VERSION" | cut -d. -f1); \
        if [ "$CHROMIUM_MAJOR" = "$CHROMEDRIVER_MAJOR" ]; then \
            echo "✓ Chromium和ChromeDriver主版本匹配: $CHROMIUM_MAJOR"; \
        else \
            echo "✗ 错误: Chromium($CHROMIUM_MAJOR)和ChromeDriver($CHROMEDRIVER_MAJOR)主版本不匹配!"; \
            exit 1; \
        fi; \
    else \
        echo "错误：Chromium 或 ChromeDriver 未成功安装。"; \
        exit 1; \
    fi; \
    # 创建符号链接和权限设置
    ln -sf /usr/bin/chromium /usr/bin/chromium-browser; \
    ln -sf /usr/bin/chromium /usr/bin/google-chrome; \
    # 确保chromedriver路径正确并设置权限
    if [ -f /usr/bin/chromedriver ]; then \
        chmod 755 /usr/bin/chromedriver; \
    else \
        echo "错误：/usr/bin/chromedriver 不存在。"; \
        exit 1; \
    fi; \
    # 创建Chrome数据目录并设置权限
    mkdir -p /tmp/chrome-data && chmod 777 /tmp/chrome-data

# 从构建阶段复制已安装的Python依赖
COPY --from=builder /root/.local /root/.local

# 创建优化的虚拟显示启动脚本（host网络专用）
RUN printf '#!/bin/bash\n\
set -e\n\
# 清理可能的残留进程\n\
pkill -f "Xvfb" 2>/dev/null || true\n\
pkill -f "Xorg" 2>/dev/null || true\n\
sleep 1\n\
# 检查并创建必要的目录\n\
mkdir -p /tmp/.X11-unix\n\
chmod 1777 /tmp/.X11-unix\n\
# 启动虚拟显示 - 简化参数\n\
Xvfb :99 -screen 0 1280x1024x16 -ac +extension RANDR 2>/dev/null &\n\
XVFB_PID=$!\n\
# 设置DISPLAY变量\n\
export DISPLAY=:99\n\
# 等待Xvfb启动\n\
sleep 3\n\
# 检查Xvfb是否正常运行\n\
if xdpyinfo >/dev/null 2>&1; then\n\
    echo "虚拟显示启动成功 (PID: $XVFB_PID)"\n\
else\n\
    echo "错误: Xvfb启动失败"\n\
    # 尝试备用方式启动\n\
    pkill -f "Xvfb" 2>/dev/null || true\n\
    Xvfb :99 -screen 0 1024x768x16 2>/dev/null &\n\
    sleep 2\n\
    if xdpyinfo >/dev/null 2>&1; then\n\
        echo "虚拟显示通过备用方式启动成功"\n\
    else\n\
        echo "错误: Xvfb备用启动也失败"\n\
        exit 1\n\
    fi\n\
fi\n\
# 执行后续命令\n\
exec "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# 验证脚本格式
RUN head -n 1 /entrypoint.sh | grep -q '^#!/bin/bash$' || (echo "ERROR: Invalid script format" && exit 1)

# 创建host网络专用诊断脚本
RUN printf '#!/bin/bash\n\
echo "=== Host网络模式诊断 === "\n\
echo "容器环境检查: "\n\
if [ "$HOST_NETWORK_MODE" = "true" ]; then\n\
    echo "✓ 运行在host网络模式"\n\
else\n\
    echo "✗ 未检测到host网络模式"\n\
fi\n\
echo ""\n\
echo "=== 网络接口状态 ==="\n\
ip addr show 2>/dev/null || ifconfig 2>/dev/null || echo "无法获取网络接口信息"\n\
echo ""\n\
echo "=== 路由表 ==="\n\
ip route show 2>/dev/null || route -n 2>/dev/null || echo "无法获取路由信息"\n\
echo ""\n\
echo "=== 网卡详细信息 ==="\n\
for iface in $(ip link show | grep -E "^[0-9]+:" | cut -d: -f2 | tr -d " "); do\n\
    if [ "$iface" != "lo" ]; then\n\
        echo "接口 $iface:"\n\
        ip addr show dev $iface 2>/dev/null | grep -E "inet|state" || echo "  无IP地址或状态未知"\n\
        ethtool $iface 2>/dev/null | grep -E "Link detected|Speed" || echo "  无法获取网卡信息"\n\
        echo "---"\n\
    fi\n\
done\n\
echo ""\n\
echo "=== 网络连接测试 ==="\n\
for host in ipv4.icanhazip.com 4.ipw.cn checkip.amazonaws.com; do\n\
    echo "测试连接到 $host:"\n\
    timeout 5 curl -s --connect-timeout 3 "http://$host" 2>/dev/null | head -c 50 || echo "连接失败"\n\
    echo "---"\n\
done' > /host-network-diag.sh && \
    chmod +x /host-network-diag.sh

# 设置工作目录
WORKDIR /app
COPY . .

# 验证Python依赖
RUN python -c "import requests, selenium, netifaces; print('✓ Python依赖导入成功')"

# 设置入口点
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# 默认命令
CMD ["python", "wechat_ip_updater.py"]