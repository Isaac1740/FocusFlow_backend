import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__)

# ===================== CORS FIX (WORKS FOR VERCEL + DEV + ANDROID) =====================

CORS(app, resources={
    r"/*": {
        "origins": [
            "*",  # allow everything (best for dev + APK)
            "https://focus-flow-jet.vercel.app",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8080",
            "capacitor://localhost"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

@app.before_request
def handle_options():
    """Handle OPTIONS preflight requests."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200


# ===================== DATABASE CONNECTION =====================

try:
    DB_HOST = os.environ.get("MYSQL_HOST", "localhost")
    DB_USER = os.environ.get("MYSQL_USER", "root")
    DB_PASS = os.environ.get("MYSQL_PASSWORD", "")
    DB_NAME = os.environ.get("MYSQL_DB", "focusflow")
    DB_PORT = int(os.environ.get("MYSQL_PORT", 3306))

    db = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        port=DB_PORT
    )

    cursor = db.cursor()
    print("✅ MySQL Connected Successfully")

except mysql.connector.Error as err:
    print("❌ Database Connection Failed:", err)


# ===================== TABLES =====================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL
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


# ===================== SIGNUP =====================

@app.post("/api/signup")
def signup():
    try:
        data = request.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields are required"})

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "User already exists"})

        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, password)
        )
        db.commit()

        return jsonify({"success": True, "message": "Signup successful"})

    except Exception as e:
        print("❌ Signup Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== LOGIN =====================

@app.post("/api/login")
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"success": False, "message": "Email and password required."})

        cursor.execute("SELECT id, username, password FROM users WHERE email=%s", (email,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        user_id, username, stored_password = row

        if stored_password != password:
            return jsonify({"success": False, "message": "Incorrect password"})

        return jsonify({
            "success": True,
            "message": "Login successful",
            "user_id": user_id,
            "username": username,
            "email": email
        })

    except Exception as e:
        print("❌ Login Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== USER PROFILE =====================

@app.post("/api/profile")
def profile():
    try:
        user_id = request.get_json().get("user_id")

        if not user_id:
            return jsonify({"success": False, "message": "Missing user_id"})

        cursor.execute("SELECT id, username, email FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        user_id, username, email = row

        return jsonify({
            "success": True,
            "user": {
                "id": user_id,
                "username": username,
                "email": email
            }
        })

    except Exception as e:
        print("❌ Profile Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== ADD TASK =====================

@app.post("/api/add_task")
def add_task():
    try:
        data = request.get_json()
        required = ["user_id", "date", "time", "task", "icon", "color", "duration"]

        if any(field not in data for field in required):
            return jsonify({"success": False, "message": "Missing required fields"})

        cursor.execute("""
            INSERT INTO tasks (user_id, date, time, task, icon, color, duration)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data["user_id"], data["date"], data["time"],
            data["task"], data["icon"], data["color"], data["duration"]
        ))
        db.commit()

        return jsonify({"success": True, "message": "Task added"})

    except Exception as e:
        print("❌ Add Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== GET TASKS =====================

@app.get("/api/get_tasks")
def get_tasks():
    try:
        user_id = request.args.get("user_id")
        date = request.args.get("date")

        if not user_id or not date:
            return jsonify({"success": False, "message": "Missing user_id or date"})

        cursor.execute("""
            SELECT id, date, time, task, icon, color, duration
            FROM tasks
            WHERE user_id=%s AND date=%s
            ORDER BY time ASC
        """, (user_id, date))

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


# ===================== UPDATE TASK =====================

@app.put("/api/update_task/<int:task_id>")
def update_task(task_id):
    try:
        data = request.get_json()

        cursor.execute("""
            UPDATE tasks
            SET date=%s, time=%s, task=%s, icon=%s, color=%s, duration=%s
            WHERE id=%s
        """, (
            data.get("date"), data.get("time"), data.get("task"),
            data.get("icon"), data.get("color"), data.get("duration"), task_id
        ))

        db.commit()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Update Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== DELETE TASK =====================

@app.delete("/api/delete_task/<int:task_id>")
def delete_task(task_id):
    try:
        cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
        db.commit()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Delete Task Error:", e)
        return jsonify({"success": False, "message": "Server error"})


# ===================== ROOT =====================

@app.get("/")
def root():
    return jsonify({"ok": True, "message": "FocusFlow backend is running"})


# ===================== LOCAL DEV ONLY =====================

if __name__ == "__main__":
    app.run()
