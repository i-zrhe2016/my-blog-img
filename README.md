Image Host（图床）

最小可用的本地图床：上传图片，拿直链。够用即可。

快速开始

1) 安装依赖

```
pip install -r requirements.txt
```

2) 运行

```
python app.py
# 默认服务： http://localhost:8000
```

怎么用

- 网页上传：打开 `/`，选择图片提交。
- 图库：`/gallery` 浏览所有图片。
- 直链：`/img/<id>.<ext>` 直接访问图片。
- API：`POST /api/upload`，`multipart/form-data` 字段名 `image`。

API 示例

```
curl -F image=@your.png http://localhost:8000/api/upload
```

存储位置

- 图片：`uploads/`
- 元数据：`data/images.jsonl`（一行一条 JSON）

可选配置（按需）

- `PORT`：端口，默认 `8000`
- `BASE_URL`：生成外链的基地址（不设则按请求推断）

就这些。
