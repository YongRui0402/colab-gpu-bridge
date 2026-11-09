# S10(E10 檔案系統)產出;映像組成照 research.md R11。對外 port 與啟動指令留給 S11 接著改。
# build context 是 repo 根目錄(compose.yaml 的 build.context);只送進下面 COPY 用到的檔,見 Dockerfile.dockerignore。
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

COPY specs/001-session-model-catalog/deploy/prepare-data.sh /usr/local/bin/cgb-prepare-data
RUN chmod 755 /usr/local/bin/cgb-prepare-data

ENTRYPOINT ["cgb-prepare-data"]
CMD ["python", "-m", "cgb"]
