import hashlib
import secrets
import json
import os
from functools import wraps
from flask import request, jsonify

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(_project_root, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

def ok(data=None, message="ok"):
    return jsonify({"code": 0, "message": message, "data": data})

def err(message, code=4000, http_status=400):
    return jsonify({"code": code, "message": message, "data": None}), http_status

def load_users():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token():
    return secrets.token_hex(32)

tokens = {}

def register_routes(app):
    @app.route("/api/v1/auth/register", methods=["POST"])
    def register():
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "").strip()

        if not username or not password:
            return err("用户名和密码不能为空")
        if role not in ("teacher", "student"):
            return err("角色必须是 teacher 或 student")
        if len(password) < 4:
            return err("密码至少4位")

        users = load_users()
        if any(u["username"] == username for u in users):
            return err("用户名已存在", 4090, 409)

        user = {
            "id": secrets.token_hex(8),
            "username": username,
            "password": hash_password(password),
            "role": role,
        }
        users.append(user)
        save_users(users)
        return ok({"userId": user["id"]}, "注册成功")

    @app.route("/api/v1/auth/login", methods=["POST"])
    def login():
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        users = load_users()
        user = next((u for u in users if u["username"] == username), None)
        if not user or user["password"] != hash_password(password):
            return err("用户名或密码错误", 4010, 401)

        token = generate_token()
        tokens[token] = user["id"]
        return ok({
            "token": token,
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]}
        })

    @app.route("/api/v1/auth/me", methods=["GET"])
    def me():
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = tokens.get(token)
        if not user_id:
            return err("未登录", 4010, 401)
        users = load_users()
        user = next((u for u in users if u["id"] == user_id), None)
        if not user:
            return err("用户不存在", 4040, 404)
        return ok({"id": user["id"], "username": user["username"], "role": user["role"]})


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = tokens.get(token)
        if not user_id:
            return err("请先登录", 4010, 401)
        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated

def require_role(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            user_id = tokens.get(token)
            if not user_id:
                return err("请先登录", 4010, 401)
            users = load_users()
            user = next((u for u in users if u["id"] == user_id), None)
            if not user or user["role"] != role:
                return err("权限不足", 4030, 403)
            request.user_id = user_id
            return f(*args, **kwargs)
        return decorated
    return decorator
