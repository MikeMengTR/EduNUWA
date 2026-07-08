import os
import sys

# Windows 控制台默认 GBK：合成路径里厂商代码(GPT-SoVITS inference_webui)会 print 含 ²、
# 希腊字母等非 GBK 字符的目标文本，触发 UnicodeEncodeError 使该句合成崩溃（表现为"跳句子"）。
# 把标准流重配为 UTF-8 并对无法编码的字符 replace 兜底，确保任何 print 都不再因编码崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 确保项目根在 path 中，使所有模块可被 import
# modules/M6_platform/backend/app.py → 上4层 = EduNUWA/
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

# 后端只调国内 API（DeepSeek / DashScope）与本机服务，绝不需要系统代理；而 Clash 之类
# 代理会掐断 api.deepseek.com 的 TLS/长连接（表现为 Request timed out 或 incomplete
# chunked read，讲课流式中断）。这里在进程级清掉代理环境变量，让所有 httpx/OpenAI 客户端
# 一律直连，免去对 .env NO_PROXY 与手动重启时机的依赖（实测直连流式 1.7s、稳定）。
for _pv in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_pv, None)

from flask import Flask, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 修复 MIME 类型检测（关键：ES 模块需要 text/javascript）
import mimetypes
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/json', '.json')
mimetypes.add_type('image/svg+xml', '.svg')

# 静态文件服务
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
_m5_frontend = os.path.join(_project_root, "modules", "M5_runtime", "frontend", "dist")

import auth
import teachers
import upload
import video
import chat
import pipeline
import distill
import feedback
import course
import evolution
import voice_train
import materials
import media_admin
import platform_admin

auth.register_routes(app)
teachers.register_routes(app)
upload.register_routes(app)
video.register_routes(app)
chat.register_routes(app)
pipeline.register_routes(app)
distill.register_routes(app)
feedback.register_routes(app)
course.register_routes(app)
evolution.register_routes(app)
voice_train.register_routes(app)
materials.register_routes(app)
media_admin.register_routes(app)
platform_admin.register_routes(app)

# 教师头像服务
@app.route("/api/v1/avatar/<teacher_id>/<filename>")
def serve_avatar(teacher_id, filename):
    """提供教师头像图片"""
    avatar_dir = os.path.join(_project_root, "data", "teachers", teacher_id, "avatar")
    path = os.path.join(avatar_dir, filename)
    if os.path.exists(path):
        return send_from_directory(avatar_dir, filename)
    return "Not found", 404

# M5 运行时前端
@app.route("/runtime/", defaults={"path": ""})
@app.route("/runtime/<path:path>")
def serve_m5_frontend(path):
    """M5 学习运行时前端（数字人+黑板） — 禁用缓存确保 JS 以正确 MIME 加载"""
    if path and os.path.exists(os.path.join(_m5_frontend, path)):
        resp = send_from_directory(_m5_frontend, path)
    else:
        resp = send_from_directory(_m5_frontend, "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# M6 主前端 SPA fallback
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(_frontend_dist, path)):
        return send_from_directory(_frontend_dist, path)
    return send_from_directory(_frontend_dist, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    DEBUG = True
    print(f"EduNUWA M6 Platform 启动: http://localhost:{port}")

    # 后台预热所有教师 GPT-SoVITS 模型（减少首句延迟）。
    # 注意：debug 重载器会跑父(监视)+子(服务)两个进程，这段 __main__ 会被执行两遍。
    # 只在真正服务的子进程(WERKZEUG_RUN_MAIN=true)里预热，否则模型会在 GPU 上加载两份
    # （显存翻倍、预热时间翻倍、可能 OOM）。debug 关闭时无重载器，正常预热。
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        try:
            import voice_service
            voice_service.prewarm_all()
        except Exception as e:
            print(f"[启动] 预热跳过: {e}")

    # threaded=True：并发请求各用一个线程，避免换老师首次加载 GPT 模型（数秒）时
    # 单线程阻塞导致预取等并发 /tts 请求连接被重置（ECONNRESET）。
    # GPU 合成仍由 voice_service 的锁保证串行，这里只是不让 HTTP 连接因排队而中断。
    app.run(host="0.0.0.0", port=port, debug=DEBUG, threaded=True)
