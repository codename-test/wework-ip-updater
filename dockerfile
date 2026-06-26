# ================================================================
# 企业微信IP更新器 - Docker 构建（精简版）
# ================================================================

# ---------- 构建阶段 ----------
FROM python:3.11-slim-bookworm AS builder

RUN echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev python3-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --user --no-cache-dir requests selenium netifaces

# ---------- 运行阶段 ----------
FROM python:3.11-slim-bookworm

RUN echo "deb https://repo.huaweicloud.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://repo.huaweicloud.com/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/*

# 只安装必要运行时依赖，去掉 xvfb/debug 工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl procps \
        chromium chromium-driver \
        libnss3 libasound2 libgbm1 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libpango-1.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && CHROMIUM_VER=$(chromium --version | grep -oP '\d+' | head -1) \
    && DRIVER_VER=$(chromedriver --version | grep -oP '\d+' | head -1) \
    && [ "$CHROMIUM_VER" = "$DRIVER_VER" ] || (echo "版本不匹配: chromium=$CHROMIUM_VER driver=$DRIVER_VER" && exit 1) \
    && ln -sf /usr/bin/chromium /usr/bin/google-chrome \
    && mkdir -p /tmp/chrome-data && chmod 777 /tmp/chrome-data

COPY --from=builder /root/.local /root/.local

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/root/.local/bin:/usr/lib/chromium:${PATH}" \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages

# 精简入口：不再启动 Xvfb（headless=new 不需要）
RUN printf '#!/bin/bash\nset -e\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

WORKDIR /app
COPY . .

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["python", "wechat_ip_updater.py"]
