import os
import datetime
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet

# ================================================
# APP INIT
# ================================================
app = Flask(__name__)

# ================================================
# SECRETS
# ================================================
SECRET_KEY = os.environ.get("SECRET_KEY")
FERNET_KEY = os.environ.get("FERNET_KEY")

if not SECRET_KEY or not FERNET_KEY:
    raise RuntimeError("Missing SECRET_KEY or FERNET_KEY environment variable")

fernet = Fernet(FERNET_KEY)

# ================================================
# HELPERS (ENCRYPTION)
# ================================================
def encrypt(text: str) -> str:
    return fernet.encrypt(text.encode()).decode()

def decrypt(text: str) -> str:
    return fernet.decrypt(text.encode()).decode()

# ================================================
# CORS (CORRECT)
# ================================================
CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://focus-flow-jet.vercel.app",
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8080",
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
        }
    },
)

@app.before_request
def preflight():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

# ================================================
# DATABASE CONNECTION
# ================================================
db = mysql.connector.connect(
    host=os.environ.get("MYSQL_HOST"),
    user=os.environ.get("MYSQL_USER"),
    password=os.environ.get("MYSQL_PASSWORD"),
    database=os.environ.get("MYSQL_DB"),
    port=int(os.environ.get("MYSQL_PORT")),
)
cursor = db.cursor()
print("✅ Database connected")

# ================================================
# TABLES
# ================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT NOT NULL,
    password VARCHAR(255) NOT NULL
)
""")
db.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    date DATE,
    time VARCHAR(20),
    task VARCHAR(255),
    icon VARCHAR(50),
    color VARCHAR(50),
    duration VARCHAR(50),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
db.commit()

# ================================================
# JWT DECORATOR
# ================================================
def require_auth(fn):
    @wraps(fn)
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

        return fn(*args, **kwargs)
    return wrapper

# ================================================
# SIGNUP
# ================================================
@app.post("/api/signup")
def signup():
    try:
        data = request.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields required"})

        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (
                encrypt(username),
                encrypt(email),
                generate_password_hash(password),
            ),
        )
        db.commit()

        return jsonify({"success": True, "message": "Signup successful"})
    except Exception as e:
        print("❌ Signup error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# ================================================
# LOGIN
# ================================================
@app.post("/api/login")
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        cursor.execute("SELECT id, username, email, password FROM users")
        users = cursor.fetchall()

        for user_id, enc_username, enc_email, hashed_pw in users:
            if decrypt(enc_email) == email:
                if not check_password_hash(hashed_pw, password):
                    return jsonify({"success": False, "message": "Incorrect password"})

                token = jwt.encode(
                    {
                        "user_id": user_id,
                        "exp": datetime.datetime.utcnow()
                        + datetime.timedelta(days=7),
                    },
                    SECRET_KEY,
                    algorithm="HS256",
                )

                return jsonify(
                    {
                        "success": True,
                        "token": token,
                        "user_id": user_id,
                        "username": decrypt(enc_username),
                        "email": email,
                    }
                )

        return jsonify({"success": False, "message": "User not found"})
    except Exception as e:
        print("❌ Login error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# ================================================
# PROFILE
# ================================================
@app.get("/api/profile")
@require_auth
def profile():
    try:
        cursor.execute(
            "SELECT username, email FROM users WHERE id=%s",
            (request.user_id,),
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        return jsonify(
            {
                "success": True,
                "user": {
                    "id": request.user_id,
                    "username": decrypt(row[0]),
                    "email": decrypt(row[1]),
                },
            }
        )
    except Exception as e:
        print("❌ Profile error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# ================================================
# TASKS
# ================================================
@app.post("/api/add_task")
@require_auth
def add_task():
    data = request.get_json()
    cursor.execute(
        """
        INSERT INTO tasks (user_id, date, time, task, icon, color, duration)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.user_id,
            data["date"],
            data["time"],
            data["task"],
            data["icon"],
            data["color"],
            data["duration"],
        ),
    )
    db.commit()
    return jsonify({"success": True})

@app.get("/api/get_tasks")
@require_auth
def get_tasks():
    date = request.args.get("date")

    cursor.execute(
        """
        SELECT id, date, time, task, icon, color, duration
        FROM tasks
        WHERE user_id=%s AND date=%s
        ORDER BY time ASC
        """,
        (request.user_id, date),
    )

    rows = cursor.fetchall()
    tasks = [
        {
            "id": r[0],
            "date": r[1].strftime("%Y-%m-%d"),
            "time": r[2],
            "task": r[3],
            "icon": r[4],
            "color": r[5],
            "duration": r[6],
        }
        for r in rows
    ]

    return jsonify({"success": True, "tasks": tasks})

# ================================================
# ROOT
# ================================================
@app.get("/")
def home():
    return jsonify({"ok": True, "message": "FocusFlow backend running"})

# ================================================
# START
# ================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
