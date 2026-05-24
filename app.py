import os
from flask import Flask, render_template, request, session, jsonify
from flask_session import Session
from supabase import create_client, Client
from supabase.client import ClientOptions
from werkzeug.utils import secure_filename
from ebooklib import epub

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_12345')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Supabase 設定
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 檔案路徑設定
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

# --- 認證路由 ---
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    try:
        res = supabase.table('users').select('*').eq('username', username).eq('password', password).execute()
        if res.data:
            session['user'] = username
            session['is_admin'] = res.data[0].get('is_admin', False)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "帳號或密碼錯誤"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 書籍路由 ---
@app.route('/books', methods=['GET'])
def get_books():
    try:
        res = supabase.table('books').select('*').execute()
        return jsonify(res.data if res.data else []), 200
    except:
        return jsonify([]), 200

@app.route('/rename_category/<book_id>', methods=['POST'])
def rename_category(book_id):
    if 'user' not in session: return jsonify({"status": "error"}), 401
    new_cat = request.json.get('new_category')
    supabase.table('books').update({"series_name": new_cat}).eq('id', book_id).execute()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)