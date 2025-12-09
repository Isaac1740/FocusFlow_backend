import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps

# =========================================
# APP & CONFIG
# =========================================
app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key_change_in_prod")

# =========================================
# CORS (supports Vercel + local dev + Android APK)
# =========================================
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://focus-flow-jet.vercel.app",
            "https://focusflow-backend-kezy.onrender.com",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "capacitor://localhost",
            "*"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200


# =========================================
# DATABASE CONNECTION (Render format)
# =========================================
try:
    DB_HOST = os.environ.get("DATABASE_HOST", "localhost")
    DB_USER = os.environ.get("DATABASE_USER", "root")
    DB_PASS = os.environ.get("DATABASE_PASSWORD", "")
    DB_NAME = os.environ.get("DATABASE_NAME", "focusflow")
    DB_PORT = int(os.environ.get("DATABASE_PORT", 3306))

    db = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        port=DB_PORT
    )

    cursor = db.cursor()
    print("✅ Connected to MySQL")

except mysql.connector.Error as err:
    cursor = None
    print("❌ DB Connection Error:", err)


# =========================================
# TABLE CREATION IF NOT EXISTS
# =========================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
)
""")
db.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    date DATE NOT NULL,
    time VARCHAR(20) NOT NULL,
    task VARCHAR(255) NOT NULL,
    icon VARCHAR(50) NOT NULL,
    color VARCHAR(50) NOT NULL,
    duration VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
db.commit()


# =========================================
# JWT AUTH DECORATOR
# =========================================
def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"success": False, "message": "Missing token"}), 401

        try:
            token = token.replace("Bearer ", "")
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = decoded["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "message": "Token expired"}), 401
        except Exception:
            return jsonify({"success": False, "message": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper


# =========================================
# SIGNUP
# =========================================
@app.post("/api/signup")
def signup():
    try:
        data = request.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields required"})

        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "User already exists"})

        hashed_pw = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_pw)
        )
        db.commit()

        return jsonify({"success": True, "message": "Signup successful"})

    except Exception as e:
        print("❌ Signup Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# LOGIN → returns JWT token
# =========================================
@app.post("/api/login")
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        cursor.execute("SELECT id, username, password FROM users WHERE email=%s", (email,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        user_id, username, hashed_pw = row

        if not check_password_hash(hashed_pw, password):
            return jsonify({"success": False, "message": "Incorrect password"})

        token = jwt.encode(
            {
                "user_id": user_id,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
            },
            SECRET_KEY,
            algorithm="HS256"
        )

        return jsonify({
            "success": True,
            "token": token,
            "user_id": user_id,
            "username": username,
            "email": email
        })

    except Exception as e:
        print("❌ Login Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# PROFILE (Protected)
# =========================================
@app.post("/api/profile")
@require_auth
def profile():
    try:
        cursor.execute("SELECT id, username, email FROM users WHERE id=%s", (request.user_id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        return jsonify({
            "success": True,
            "user": {
                "id": row[0],
                "username": row[1],
                "email": row[2]
            }
        })

    except Exception as e:
        print("❌ Profile Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# ADD TASK (Protected)
# =========================================
@app.post("/api/add_task")
@require_auth
def add_task():
    try:
        data = request.get_json()

        cursor.execute("""
            INSERT INTO tasks (user_id, date, time, task, icon, color, duration)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            request.user_id,
            data["date"], data["time"], data["task"],
            data["icon"], data["color"], data["duration"]
        ))

        db.commit()
        return jsonify({"success": True, "message": "Task added"})

    except Exception as e:
        print("❌ Add Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# GET TASKS (Protected)
# =========================================
@app.get("/api/get_tasks")
@require_auth
def get_tasks():
    try:
        date = request.args.get("date")

        cursor.execute("""
            SELECT id, date, time, task, icon, color, duration
            FROM tasks
            WHERE user_id=%s AND date=%s
            ORDER BY time ASC
        """, (request.user_id, date))

        rows = cursor.fetchall()

        tasks = [{
            "id": r[0],
            "date": r[1].strftime("%Y-%m-%d"),
            "time": r[2],
            "task": r[3],
            "icon": r[4],
            "color": r[5],
            "duration": r[6]
        } for r in rows]

        return jsonify({"success": True, "tasks": tasks})

    except Exception as e:
        print("❌ Get Tasks Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# UPDATE TASK (Protected)
# =========================================
@app.put("/api/update_task/<int:task_id>")
@require_auth
def update_task(task_id):
    try:
        data = request.get_json()

        cursor.execute("""
            UPDATE tasks
            SET date=%s, time=%s, task=%s, icon=%s, color=%s, duration=%s
            WHERE id=%s AND user_id=%s
        """, (
            data.get("date"), data.get("time"), data.get("task"),
            data.get("icon"), data.get("color"), data.get("duration"),
            task_id, request.user_id
        ))

        db.commit()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Update Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# DELETE TASK (Protected)
# =========================================
@app.delete("/api/delete_task/<int:task_id>")
@require_auth
def delete_task(task_id):
    try:
        cursor.execute(
            "DELETE FROM tasks WHERE id=%s AND user_id=%s",
            (task_id, request.user_id)
        )

        db.commit()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Delete Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# =========================================
# ROOT
# =========================================
@app.get("/")
def root():
    return jsonify({"ok": True, "message": "FocusFlow backend running"})


# =========================================
# RENDER START
# =========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
