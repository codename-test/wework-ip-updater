# ================================================================
# 企业微信IP更新器 - Docker 构建
# ================================================================

# ---------- 构建阶段 ----------
FROM python:3.11-slim-bookworm AS builder

# 国内镜像源
RUN echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装构建依赖 + Python 包
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev python3-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --user --no-cache-dir requests selenium pyvirtualdisplay webdriver-manager netifaces

# ---------- 运行阶段 ----------
FROM python:3.11-slim-bookworm

# 国内镜像源
RUN echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/*

# 一次性安装所有运行时依赖（合并为单层，减少镜像体积）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl procps \
        chromium chromium-driver \
        libnss3 libxss1 libasound2 libxtst6 libgtk-3-0 libgbm1 \
        xvfb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    # 验证 Chromium / ChromeDriver 版本匹配
    && CHROMIUM_VER=$(chromium --version | grep -oP '\d+' | head -1) \
    && DRIVER_VER=$(chromedriver --version | grep -oP '\d+' | head -1) \
    && [ "$CHROMIUM_VER" = "$DRIVER_VER" ] || (echo "版本不匹配: chromium=$CHROMIUM_VER driver=$DRIVER_VER" && exit 1) \
    # 符号链接 + 权限
    && ln -sf /usr/bin/chromium /usr/bin/google-chrome \
    && mkdir -p /tmp/chrome-data && chmod 777 /tmp/chrome-data

# 从构建阶段复制 Python 依赖
COPY --from=builder /root/.local /root/.local

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY=:99 \
    PATH="/root/.local/bin:/usr/lib/chromium:${PATH}" \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages

# 入口脚本：启动 Xvfb 虚拟显示后执行主程序
RUN printf '#!/bin/bash\nset -e\npkill -f Xvfb 2>/dev/null || true\nsleep 1\nmkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix\nXvfb :99 -screen 0 1280x1024x16 -ac +extension RANDR 2>/dev/null &\nsleep 2\nexec "$@"' \
    > /entrypoint.sh && chmod +x /entrypoint.sh

WORKDIR /app
COPY . .

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["python", "wechat_ip_updater.py"]
