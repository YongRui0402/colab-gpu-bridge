# S10(E10 檔案系統)產出;映像組成照 research.md R11。S11(E11 部署與網路)補上 HTTP 健康檢查與兩個入口的 port。
# build context 是 repo 根目錄(compose.yaml 的 build.context);只送進下面 COPY 用到的檔,見 .dockerignore。
FROM python:3.12-slim

RUN apt-get update \
	&& apt-get install -y --no-install-recommends openssh-client \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir google-colab-cli==0.7.5

# Colab CLI 0.7.5 把 token.json、sessions.json、settings.json、colab.log、history/ 寫死在 ~/.config/colab-cli/,
# 不吃環境變數;整個資料夾以符號連結指到掛載的 /data/colab-cli。
RUN mkdir -p /root/.config && ln -s /data/colab-cli /root/.config/colab-cli

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY deploy/prepare-data.sh /usr/local/bin/cgb-prepare-data
COPY deploy/healthcheck.py /usr/local/bin/cgb-healthcheck
RUN chmod 755 /usr/local/bin/cgb-prepare-data /usr/local/bin/cgb-healthcheck

# 兩個入口(compose.yaml 的 x-ports):8780 是 UI 與 UI API、11434 是 Ollama 相容端點;
# 後端讀 CGB_LISTEN_HOST、CGB_UI_PORT、CGB_OLLAMA_PORT listen。SSH 通道的 127.0.0.1:11435 只在容器內,不列在這裡。
ENV CGB_LISTEN_HOST=0.0.0.0 \
	CGB_UI_PORT=8780 \
	CGB_OLLAMA_PORT=11434 \
	CGB_TUNNEL_LOCAL_PORT=11435
EXPOSE 8780 11434

ENTRYPOINT ["cgb-prepare-data"]
CMD ["python", "-m", "cgb"]
