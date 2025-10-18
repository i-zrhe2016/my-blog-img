Image Host (图床)

快速本地图床服务，支持上传图片、获取直链/Markdown/HTML 链接，图片与元数据均存储在本地文件系统中：

- 图片目录：`uploads/`
- 元数据文件：`data/images.jsonl`（每行一条 JSON 记录）

快速开始

1) 安装依赖

```
pip install -r requirements.txt
```

2) 运行服务

```
python app.py
# 默认 http://localhost:8000
```

可选环境变量

- `BASE_URL`：生成外链时使用的基地址；默认取请求的 `url_root`。
- `PORT`：服务端口，默认 `8000`。
- `MAX_CONTENT_LENGTH`：最大上传大小（字节），默认 `10485760`（10MB）。

功能

- 网页上传：`/` 表单上传，成功后返回预览与多种链接。
- 图库：`/gallery` 浏览全部图片。
- 直链：`/img/<id>.<ext>` 直接访问图片。
- 元数据与链接：`/links/<id>` 返回该图片的 JSON 信息与常用链接。
- API 上传：`POST /api/upload`，`multipart/form-data`，字段名 `image`。

示例

```
curl -F image=@your.png http://localhost:8000/api/upload
```

数据文件格式（JSONL）

`data/images.jsonl` 每行一条记录，包含：

```
{
  "id": "<短ID>",
  "ext": "png|jpg|...",
  "filename": "原始文件名",
  "stored_name": "<id>.<ext>",
  "path": "uploads/<id>.<ext>",
  "size": 12345,
  "sha256": "...",
  "uploaded_at": "UTC 时间",
  "url": "http(s)://.../img/<id>.<ext>"
}
```

注意

- 仅按扩展名做基本类型校验，如需更严格校验可引入 Pillow 或额外检测。
- 简单 JSONL 追加写入，适合轻量使用；若需更复杂查询/并发，请考虑 SQLite 等数据库。

对外访问与部署

- 监听所有地址：默认已 `0.0.0.0:8000`，若需更改端口设 `PORT`。
- 直链域名：设置 `BASE_URL` 为你的外网域名/IP，例如：

  ```
  BASE_URL=https://img.example.com PORT=8000 python app.py
  ```

- 反向代理（Nginx/Caddy）或 HTTPS：设置 `TRUST_PROXY=1` 以信任 `X-Forwarded-*` 请求头，从而生成正确的外链（协议/主机/前缀）。

  Nginx 示例（根路径部署）：

  ```nginx
  server {
    listen 80;
    server_name img.example.com;
    location / {
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header X-Forwarded-Host $host;
      proxy_pass http://127.0.0.1:8000;
    }
  }
  ```

- 生产运行（可选）：

  ```
  pip install gunicorn
  TRUST_PROXY=1 BASE_URL=https://img.example.com \
  gunicorn -b 0.0.0.0:8000 'app:app'
  ```
