#!/bin/bash
# dola.1task.cn HTTPS: ACME 签发 + :443 反代
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
DOMAIN=dola.1task.cn
PORT=39101  # dola-service

echo "=== 1. ACME challenge dir + DNS precheck ==="
ssh -i "$KEY" "$HOST" "mkdir -p /www/wwwroot/$DOMAIN"
echo ""

echo "=== 2. sign cert ==="
ssh -i "$KEY" "$HOST" "
if [ -d /www/server/panel/vhost/cert/$DOMAIN ]; then
  echo 'cert already exists, skip'
else
  /root/.acme.sh/acme.sh --issue -d $DOMAIN --webroot /www/wwwroot/$DOMAIN --server letsencrypt 2>&1 | tail -3
  mkdir -p /www/server/panel/vhost/cert/$DOMAIN
  /root/.acme.sh/acme.sh --install-cert -d $DOMAIN \
    --key-file /www/server/panel/vhost/cert/$DOMAIN/privkey.pem \
    --fullchain-file /www/server/panel/vhost/cert/$DOMAIN/fullchain.pem
fi
"
echo ""

echo "=== 3. :443 vhost ==="
ssh -i "$KEY" "$HOST" "cat > /www/server/panel/vhost/nginx/$DOMAIN.conf << 'NGINX'
server {
    listen 80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /www/wwwroot/$DOMAIN; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    ssl_certificate /www/server/panel/vhost/cert/$DOMAIN/fullchain.pem;
    ssl_certificate_key /www/server/panel/vhost/cert/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_connect_timeout 15s;
    }
}
NGINX
/www/server/nginx/sbin/nginx -t && /www/server/nginx/sbin/nginx -s reload"
sleep 2
echo ""

echo "=== 4. verify :443 ==="
ssh -i "$KEY" "$HOST" "curl -s --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/healthz"
echo ""
ssh -i "$KEY" "$HOST" "curl -s --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/v1/models | python3 -c 'import json,sys;d=json.load(sys.stdin);print(f\"models: {len(d[\\\"data\\\"])}\")'"
