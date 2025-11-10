# ================================================================
# 第一阶段：构建阶段
# ================================================================
FROM python:3.11-slim-bookworm as builder

# 安装基本工具和证书
RUN apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    apt-transport-https \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装系统构建依赖
RUN set -e; \
    for i in 1 2 3 4 5; do \
        apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
        apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        python3-dev \
        wget \
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

# 升级pip
RUN pip install --no-cache-dir --upgrade pip --timeout 120 --retries 5

# 复制requirements文件并安装Python依赖
COPY requirements.txt .
RUN set -e; \
    for i in 1 2 3 4 5; do \
        pip install --user --no-cache-dir --timeout 120 --retries 5 -r requirements.txt \
        && break || sleep $(($i * 15)); \
    done

# ================================================================
# 第二阶段：运行阶段 - 最小化镜像
# ================================================================
FROM python:3.11-slim-bookworm

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
    CHROME_BIN=/usr/bin/chromium

# 安装运行时依赖（包括Chromium和chromedriver）
RUN set -e; \
    for i in 1 2 3 4 5; do \
        apt-get update -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && \
        apt-get install -y --no-install-recommends \
        # Chromium运行依赖
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
        # 虚拟显示支持
        xvfb \
        # 调试工具
        strace \
        && break || sleep $(($i * 15)); \
    done; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    # 验证安装
    echo "验证Chromium安装: $(chromium --version)"; \
    echo "验证ChromeDriver安装: $(chromedriver --version)"; \
    # 创建符号链接
    ln -s /usr/bin/chromium /usr/bin/chromium-browser; \
    # 设置权限
    chmod 755 /usr/bin/chromedriver

# 从构建阶段复制已安装的Python依赖
COPY --from=builder /root/.local /root/.local

# 创建虚拟显示启动脚本
RUN printf '#!/bin/bash\n\
set -e\n\
# 启动虚拟显示\n\
Xvfb :99 -screen 0 3840x2160x24 -ac +extension GLX +render -noreset >/dev/null 2>&1 &\n\
# 设置DISPLAY变量\n\
export DISPLAY=:99\n\
# 执行后续命令\n\
exec "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# 验证脚本格式
RUN head -n 1 /entrypoint.sh | grep -q '^#!/bin/bash$' || (echo "ERROR: Invalid script format" && exit 1)

# 设置工作目录
WORKDIR /app
COPY . .

# 设置入口点
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# 默认命令
CMD ["python", "wechat_ip_updater.py"]