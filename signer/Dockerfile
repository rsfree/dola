FROM node:22-slim
# Chrome 依赖（slim 无浏览器，装 chromium）
RUN apt-get update && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY package.json ./
RUN npm install --omit=dev --no-fund --no-audit
COPY server.js .
ENV CHROME_PATH=/usr/bin/chromium
ENV PORT=8491
EXPOSE 8491
CMD ["node", "server.js"]
