import os
import hashlib
import datetime
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from cryptography.fernet import Fernet


# ================================================
# APP SETUP
# ================================================
app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY")
FERNET_KEY = os.environ.get("FERNET_KEY")

fernet = Fernet(FERNET_KEY)


# ================================================
# HELPERS
# ================================================
def encrypt_text(text):
    return fernet.encrypt(text.encode()).decode()

def decrypt_text(text):
    return fernet.decrypt(text.encode()).decode()

def hash_text(text):
    return hashlib.sha256(text.lower().encode()).hexdigest()


# ================================================
# CORS
# ================================================
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200


# ================================================
# DATABASE CONNECTION (Render MySQL)
# ================================================
db = mysql.connector.connect(
    host=os.environ.get("MYSQL_HOST"),
    user=os.environ.get("MYSQL_USER"),
    password=os.environ.get("MYSQL_PASSWORD"),
    database=os.environ.get("MYSQL_DB"),
    port=int(os.environ.get("MYSQL_PORT"))
)
cursor = db.cursor()

print("✅ DB connected")


# ================================================
# JWT DECORATOR
# ================================================
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
        except:
            return jsonify({"success": False, "message": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper


# ================================================
# SIGNUP
# ================================================
@app.post("/api/signup")
def signup():
    data = request.get_json()

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return jsonify({"success": False, "message": "All fields required"})

    email_hash = hash_text(email)

    cursor.execute("SELECT id FROM users WHERE email_hash=%s", (email_hash,))
    if cursor.fetchone():
        return jsonify({"success": False, "message": "User already exists"})

    cursor.execute(
        """
        INSERT INTO users (
            username_encrypted,
            username_hash,
            email_encrypted,
            email_hash,
            password
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            encrypt_text(username),
            hash_text(username),
            encrypt_text(email),
            email_hash,
            generate_password_hash(password)
        )
    )

    db.commit()
    return jsonify({"success": True, "message": "Signup successful"})


# ================================================
# LOGIN
# ================================================
@app.post("/api/login")
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    email_hash = hash_text(email)

    cursor.execute(
        "SELECT id, password FROM users WHERE email_hash=%s",
        (email_hash,)
    )
    row = cursor.fetchone()

    if not row:
        return jsonify({"success": False, "message": "User not found"})

    user_id, hashed_pw = row

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

    return jsonify({"success": True, "token": token})


# ================================================
# PROFILE
# ================================================
@app.get("/api/profile")
@require_auth
def profile():
    cursor.execute(
        """
        SELECT username_encrypted, email_encrypted
        FROM users WHERE id=%s
        """,
        (request.user_id,)
    )

    row = cursor.fetchone()
    if not row:
        return jsonify({"success": False, "message": "User not found"})

    return jsonify({
        "success": True,
        "user": {
            "id": request.user_id,
            "username": decrypt_text(row[0]),
            "email": decrypt_text(row[1])
        }
    })


# ================================================
# ROOT
# ================================================
@app.get("/")
def home():
    return jsonify({"ok": True, "message": "Encrypted FocusFlow backend running"})


# ================================================
# RUN
# ================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
