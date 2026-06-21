# -*- coding: utf-8 -*-
"""期末复习资料站 · 后端 API
功能：访问统计 | 考试日期管理 | 纠错反馈 | 静态文件服务
"""

import json, os, time, hashlib
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

# CORS — 允许前端从任何域名调用 API
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Admin-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS"
    return response

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

BASE = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE, "stats.json")
EXAMS_FILE = os.path.join(BASE, "exams.json")
FEEDBACK_FILE = os.path.join(BASE, "feedback.json")
TZ = timezone(timedelta(hours=8))  # UTC+8

# ─── 工具函数 ────────────────────────────────────────────

def load_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def client_ip():
    """获取真实客户端 IP"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

# ─── 路由：首页 → index.html ────────────────────────────

@app.route("/")
def index():
    return send_from_directory(BASE, "index.html")

# ─── API：访问统计 ───────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def api_stats():
    stats = load_json(STATS_FILE, {"total_views": 0, "today_views": 0, "date": "", "pages": {}, "log": []})
    # 通知前端触发了一次访问统计
    return jsonify({
        "total_views": stats.get("total_views", 0),
        "today_views": stats.get("today_views", 0),
        "popular_pages": sorted(
            stats.get("pages", {}).items(),
            key=lambda x: x[1], reverse=True
        )[:10]
    })

@app.route("/api/ping", methods=["POST"])
def api_ping():
    """前端上报页面访问"""
    stats = load_json(STATS_FILE, {"total_views": 0, "today_views": 0, "date": "", "pages": {}, "log": []})
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    if stats.get("date") != today:
        stats["date"] = today
        stats["today_views"] = 0

    stats["total_views"] = stats.get("total_views", 0) + 1
    stats["today_views"] = stats.get("today_views", 0) + 1

    # 记录具体页面
    page = request.json.get("page", "/") if request.is_json else "/"
    stats["pages"] = stats.get("pages", {})
    stats["pages"][page] = stats["pages"].get(page, 0) + 1

    # 保留最近 500 条日志
    log = stats.get("log", [])
    log.append({
        "ip": client_ip(),
        "page": page,
        "time": datetime.now(TZ).strftime("%H:%M:%S"),
        "ua": request.headers.get("User-Agent", "")[:120]
    })
    stats["log"] = log[-500:]

    save_json(STATS_FILE, stats)
    return jsonify({"ok": True})

# ─── API：考试日期 ───────────────────────────────────────

@app.route("/api/exams", methods=["GET"])
def api_exams():
    exams = load_json(EXAMS_FILE, {"exams": [], "updated": ""})
    return jsonify(exams)

@app.route("/api/exams", methods=["PUT"])
def api_exams_update():
    """更新考试日期（简单 token 鉴权）"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "需要 JSON body"}), 400
    token = request.headers.get("X-Admin-Token", "")
    if token != "fuxi2026":
        return jsonify({"error": "鉴权失败"}), 403
    exams = load_json(EXAMS_FILE, {"exams": []})
    exams["exams"] = data.get("exams", [])
    exams["updated"] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    save_json(EXAMS_FILE, exams)
    return jsonify({"ok": True, "count": len(exams["exams"])})

# ─── API：纠错反馈 ───────────────────────────────────────

@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "需要 JSON body"}), 400

    page = data.get("page", "未知页面")
    question = data.get("question", "")
    message = data.get("message", "")
    contact = data.get("contact", "")

    if not message.strip():
        return jsonify({"error": "反馈内容不能为空"}), 400

    feedback = load_json(FEEDBACK_FILE, [])
    feedback.append({
        "id": hashlib.md5(f"{time.time()}{message}".encode()).hexdigest()[:8],
        "page": page,
        "question": question,
        "message": message.strip(),
        "contact": contact.strip(),
        "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "ip": client_ip(),
        "resolved": False
    })
    save_json(FEEDBACK_FILE, feedback)
    return jsonify({"ok": True, "id": feedback[-1]["id"]})

@app.route("/api/feedback", methods=["GET"])
def api_feedback_list():
    """查看反馈列表（简单鉴权）"""
    token = request.args.get("token", "")
    if token != "fuxi2026":
        return jsonify({"error": "鉴权失败"}), 403
    feedback = load_json(FEEDBACK_FILE, [])
    resolved = request.args.get("resolved")
    if resolved is not None:
        want = resolved.lower() == "true"
        feedback = [f for f in feedback if f.get("resolved") == want]
    return jsonify({"feedback": feedback, "total": len(feedback)})

# ─── 启动 ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  期末复习资料站 · API Server")
    print("  http://localhost:8888")
    print("  /api/stats     → 访问统计")
    print("  /api/exams     → 考试日期")
    print("  /api/feedback  → 纠错反馈")
    print("  /api/ping      → 上报访问")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8888, debug=False)
