from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__)
CORS(app)

# ===== DB CONNECTION =====
try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Isaac@174",  # change if needed
        database="focusflow"
    )
    cursor = db.cursor()
    print("✅ MySQL Connected Successfully")
except mysql.connector.Error as err:
    print("❌ Database connection failed:", err)

# ===== ENSURE TABLES =====
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

# ===== AUTH =====
@app.post("/api/signup")
def signup():
    try:
        data = request.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields are required"})

        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "User already exists"})

        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, password)
        )
        db.commit()
        return jsonify({"success": True, "message": "Signup successful"})
    except Exception as e:
        print("❌ Signup error:", e)
        return jsonify({"success": False, "message": "Database error"})

@app.post("/api/login")
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return jsonify({"success": False, "message": "Email and password required."})

        with db.cursor() as cur:
            cur.execute("SELECT id, username, password FROM users WHERE email=%s", (email,))
            row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "User not found."})

        user_id, username, stored_password = row
        if stored_password != password:
            return jsonify({"success": False, "message": "Invalid password."})

        return jsonify({"success": True, "message": "Login successful",
                        "user_id": user_id, "username": username, "email": email})
    except Exception as e:
        print("❌ Login error:", e)
        return jsonify({"success": False, "message": "Internal server error."})

@app.post("/api/profile")
def profile():
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"success": False, "message": "Missing user_id"})

        # ✅ Ensure it's an integer
        user_id = int(user_id)

        cursor.execute(
            "SELECT id, username, email FROM users WHERE id=%s",
            (user_id,)
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({"success": False, "message": "User not found"})

        user_id, username, email = row

        return jsonify({
            "success": True,
            "user": {
                "id": user_id,
                "username": username,
                "email": email,
            }
        })

    except Exception as e:
        print("❌ Profile error:", e)
        return jsonify({"success": False, "message": "Database error"})


# ===== TASKS (date-aware) =====
@app.post("/api/add_task")
def add_task():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        date = data.get("date")          # "YYYY-MM-DD"
        time = data.get("time")
        task = data.get("task")
        icon = data.get("icon")
        color = data.get("color")
        duration = data.get("duration")
        if not user_id or not date or not task:
            return jsonify({"success": False, "message": "Missing required fields"})

        cursor.execute("""
            INSERT INTO tasks (user_id, date, time, task, icon, color, duration)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, date, time, task, icon, color, duration))
        db.commit()
        return jsonify({"success": True, "message": "Task added"})
    except Exception as e:
        print("❌ Add Task error:", e)
        return jsonify({"success": False, "message": "Database error"})

@app.get("/api/get_tasks")
def get_tasks():
    try:
        user_id = request.args.get("user_id")
        date = request.args.get("date")  # "YYYY-MM-DD"
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
        print("❌ Get Tasks error:", e)
        return jsonify({"success": False, "message": "Database error"})

@app.put("/api/update_task/<int:task_id>")
def update_task(task_id):
    try:
        data = request.get_json()
        date = data.get("date")          # allow changing date too
        time = data.get("time")
        task = data.get("task")
        icon = data.get("icon")
        color = data.get("color")
        duration = data.get("duration")

        cursor.execute("""
            UPDATE tasks
            SET date=%s, time=%s, task=%s, icon=%s, color=%s, duration=%s
            WHERE id=%s
        """, (date, time, task, icon, color, duration, task_id))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Update Task error:", e)
        return jsonify({"success": False, "message": "Database error"})

@app.delete("/api/delete_task/<int:task_id>")
def delete_task(task_id):
    try:
        cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Delete Task error:", e)
        return jsonify({"success": False, "message": "Database error"})

@app.get("/")
def root():
    return jsonify({"ok": True, "msg": "FocusFlow backend running"})

if __name__ == "__main__":
    app.run(debug=True)
