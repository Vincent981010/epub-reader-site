import os
from flask import Flask, render_template, request, session, jsonify
from flask_session import Session
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_12345')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# 初始化 Supabase 客戶端
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

# --- 登入與使用者狀態 API ---
@app.route('/user/status', methods=['GET'])
def user_status():
    """讓前端啟動時檢查目前是否已登入"""
    if 'user' in session:
        return jsonify({
            "logged_in": True,
            "username": session['user'],
            "is_admin": session.get('is_admin', False)
        })
    return jsonify({"logged_in": False, "username": "", "is_admin": False})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    try:
        # 檢查帳號是否已存在
        exist = supabase.table('users').select('*').eq('username', username).execute()
        if exist.data:
            return jsonify({"error": "帳號已被使用"}), 400
        # 建立新帳號
        supabase.table('users').insert({"username": username, "password": password, "is_admin": False}).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    try:
        res = supabase.table('users').select('*').eq('username', data.get('username')).eq('password', data.get('password')).execute()
        if res.data:
            session['user'] = data.get('username')
            session['is_admin'] = res.data[0].get('is_admin', False)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "帳號密碼錯誤"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success"})

# --- 書籍與分類 API ---
@app.route('/books', methods=['GET'])
def get_books():
    user = session.get('user')
    if not user: return jsonify([]), 200
    
    try:
        if session.get('is_admin'):
            res = supabase.table('books').select('*').execute()
        else:
            res = supabase.table('books').select('*').eq('uploader', user).execute()
        return jsonify(res.data if res.data else []), 200
    except:
        return jsonify([]), 200

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return jsonify({"status": "error", "error": "未登入"}), 401
    try:
        file = request.files['file']
        filename = secure_filename(file.filename)
        book_id = os.path.splitext(filename)[0]
        
        supabase.table('books').insert({
            "id": book_id, 
            "title": filename, 
            "uploader": session['user'] 
        }).execute()
        return jsonify({"status": "success", "message": "上傳成功"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/series', methods=['POST'])
def manage_series():
    """提供新增/修改分類的擴充端點"""
    data = request.json
    name = data.get('name')
    if not name: return jsonify({"error": "缺少分類名稱"}), 400
    # 這裡可以加入寫入 series 資料表的邏輯，目前先回傳成功讓前端能運作
    return jsonify({"status": "success", "message": f"分類 {name} 已處理"})

if __name__ == '__main__':
    app.run(debug=True)