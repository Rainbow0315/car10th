# Backend 后端服务

## 目录结构

```
backend/
├── apps/
│   ├── web_api/              # FastAPI REST 网关
│   │   ├── main.py
│   │   ├── dependencies.py   # JWT 鉴权依赖
│   │   ├── routers/          # 路由（auth 等）
│   │   └── services/         # 业务逻辑
│   ├── ros_bridge/
│   └── ai_service/
├── common/
│   ├── models/               # SQLAlchemy ORM 模型（11张表）
│   ├── schemas/              # Pydantic 请求/响应模型
│   ├── config/
│   └── utils/                # JWT、密码哈希等工具
├── db/schema.sql
├── scripts/init_admin.py     # 初始化 admin 密码
└── main.py
```

## 本地启动

```powershell
cd g:\personal\Desktop\car\car10th\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. 确认 .env 中 MYSQL_PASSWORD 正确
# 2. 建库建表（数据库存在但无表时执行）
python scripts/init_db.py

# 3. 初始化 admin 密码（默认 admin123）
python scripts/init_admin.py

# 4. 启动服务
python main.py
```

访问 http://127.0.0.1:8000/docs

## 鉴权 API

| 方法 | 路径 | 说明 | 是否需要 Token |
|------|------|------|----------------|
| POST | `/api/auth/login` | 登录，返回 JWT | 否 |
| GET | `/api/auth/me` | 获取当前用户信息 | 是 |
| POST | `/api/auth/change-password` | 修改密码 | 是 |

### 登录示例

```json
POST /api/auth/login
{
  "username": "admin",
  "password": "admin123"
}
```

响应：

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "display_name": "系统管理员",
    "role": { "role_code": "admin", "role_name": "管理员" }
  }
}
```

后续请求在 Header 携带：`Authorization: Bearer <access_token>`
