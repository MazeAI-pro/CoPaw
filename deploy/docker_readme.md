# CoPaw Docker 部署指南

本指南介绍如何使用 Docker 部署带有登录验证功能的 CoPaw。

## 快速开始

### 1. 构建镜像

在项目根目录执行：

```bash
docker build -t copaw-auth -f deploy/Dockerfile.auth .
```

### 2. 启动容器

**使用默认凭据：**

```bash
docker run -d \
  --name copaw \
  -p 8088:8088 \
  -v copaw-data:/app/working \
  copaw-auth
```

**使用自定义凭据：**

```bash
docker run -d \
  --name copaw \
  -p 8088:8088 \
  -v copaw-data:/app/working \
  -e COPAW_AUTH_USERNAME="your_username" \
  -e COPAW_AUTH_PASSWORD="your_secure_password" \
  copaw-auth
```

### 3. 访问控制台

打开浏览器访问 `http://your-server:8088/`，使用凭据登录。

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `COPAW_AUTH_ENABLED` | 是否启用认证 | `true` |
| `COPAW_AUTH_USERNAME` | 登录用户名 | `copaw_admin` |
| `COPAW_AUTH_PASSWORD` | 登录密码 | `Xk9#mP2$vL7@nQ4wR8tY` |
| `COPAW_AUTH_SESSION_EXPIRE_HOURS` | Session 过期时间（小时） | `24` |
| `COPAW_PORT` | 服务端口 | `8088` |

## 数据持久化

使用 Docker volume 持久化数据：

```bash
# 创建 volume
docker volume create copaw-data

# 启动时挂载
docker run -d -p 8088:8088 -v copaw-data:/app/working copaw-auth
```

持久化的数据包括：
- 模型配置 (`providers.json`) - API keys、活跃模型等
- 应用配置 (`config.json`)
- 对话历史
- 技能文件
- 记忆数据

## 配置 API Key

CoPaw 需要配置 LLM API Key 才能正常工作。有两种方式：

### 方式一：环境变量

```bash
docker run -d \
  -p 8088:8088 \
  -v copaw-data:/app/working \
  -e DASHSCOPE_API_KEY="your_api_key" \
  copaw-auth
```

### 方式二：登录后配置

1. 登录控制台
2. 进入 Settings → Models
3. 选择 Provider 并填入 API Key

## 完整示例

```bash
# 构建镜像
docker build -t copaw-auth -f deploy/Dockerfile.auth .

# 启动容器（自定义配置）
docker run -d \
  --name copaw \
  --restart unless-stopped \
  -p 8088:8088 \
  -v copaw-data:/app/working \
  -e COPAW_AUTH_USERNAME="admin" \
  -e COPAW_AUTH_PASSWORD="MySecureP@ssw0rd!" \
  -e COPAW_AUTH_SESSION_EXPIRE_HOURS=48 \
  -e DASHSCOPE_API_KEY="sk-xxx" \
  copaw-auth

# 查看日志
docker logs -f copaw

# 停止容器
docker stop copaw

# 启动容器
docker start copaw

# 删除容器
docker rm -f copaw
```

## Docker Compose

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  copaw:
    build:
      context: .
      dockerfile: deploy/Dockerfile.auth
    image: copaw-auth
    container_name: copaw
    restart: unless-stopped
    ports:
      - "8088:8088"
    volumes:
      - copaw-data:/app/working
    environment:
      - COPAW_AUTH_USERNAME=admin
      - COPAW_AUTH_PASSWORD=MySecureP@ssw0rd!
      - COPAW_AUTH_SESSION_EXPIRE_HOURS=48
      - DASHSCOPE_API_KEY=sk-xxx

volumes:
  copaw-data:
```

启动：

```bash
docker-compose up -d
```

## 禁用认证

如果不需要认证（如内网环境）：

```bash
docker run -d \
  -p 8088:8088 \
  -v copaw-data:/app/working \
  -e COPAW_AUTH_ENABLED=false \
  copaw-auth
```

## 常见问题

### Q: 忘记密码怎么办？

A: 重启容器时设置新的 `COPAW_AUTH_USERNAME` 和 `COPAW_AUTH_PASSWORD` 环境变量即可。

### Q: 如何更新镜像？

```bash
# 拉取最新代码
git pull

# 重新构建
docker build -t copaw-auth -f deploy/Dockerfile.auth .

# 停止并删除旧容器
docker stop copaw && docker rm copaw

# 使用新镜像启动（数据在 volume 中保留）
docker run -d --name copaw -p 8088:8088 -v copaw-data:/app/working copaw-auth
```

### Q: 如何查看默认凭据？

A: 启动时会在日志中显示：

```bash
docker logs copaw | head -20
```

输出示例：
```
======================================
CoPaw Authentication Enabled
======================================

Using default credentials:
  Username: copaw_admin
  Password: Xk9#mP2$vL7@nQ4wR8tY

Set COPAW_AUTH_USERNAME and COPAW_AUTH_PASSWORD to customize.
Starting CoPaw on port 8088...
```

## 安全建议

1. **修改默认密码**：生产环境务必设置自定义密码
2. **使用 HTTPS**：建议在前面加一层反向代理（Nginx/Caddy）配置 SSL
3. **限制端口访问**：使用防火墙限制 8088 端口仅对内网开放
4. **定期更新**：定期更新镜像获取安全修复

## Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name copaw.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name copaw.example.com;

    ssl_certificate /etc/letsencrypt/live/copaw.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/copaw.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```