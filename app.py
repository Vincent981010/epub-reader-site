import os
from flask import Flask, render_template, request, session, jsonify, send_from_directory
from flask_session import Session
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_12345')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# 建立儲存 EPUB 的實體資料夾
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/user/status', methods=['GET'])
def user_status():
    if 'user' in session:
        return jsonify({"logged_in": True, "username": session['user'], "is_admin": session.get('is_admin', False)})
    return jsonify({"logged_in": False, "username": "", "is_admin": False})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    try:
        if supabase.table('users').select('*').eq('username', data.get('username')).execute().data:
            return jsonify({"error": "帳號已被使用"}), 400
        supabase.table('users').insert({"username": data.get('username'), "password": data.get('password'), "is_admin": False}).execute()
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

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
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success"})

@app.route('/books', methods=['GET'])
def get_books():
    user = session.get('user')
    if not user: return jsonify([]), 200
    try:
        res = supabase.table('books').select('*').eq('uploader', user).execute()
        return jsonify(res.data if res.data else []), 200
    except: return jsonify([]), 200

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    try:
        file = request.files['file']
        filename = secure_filename(file.filename)
        
        # 1. 實際儲存檔案到伺服器
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # 2. 將資訊寫入資料庫 (包含 file_url 與預設分類)
        book_id = os.path.splitext(filename)[0]
        file_url = f"/static/uploads/{filename}"
        
        supabase.table('books').insert({
            "id": book_id, 
            "title": filename, 
            "uploader": session['user'],
            "series_name": "未分類",
            "file_url": file_url
        }).execute()
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 強化的分類與書籍管理 API ---
@app.route('/series/update', methods=['POST'])
def update_series():
    """批次修改分類名稱"""
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    try:
        # 將該用戶旗下，舊分類名稱的所有書，更新為新分類名稱
        supabase.table('books').update({'series_name': new_name}).eq('series_name', old_name).eq('uploader', session['user']).execute()
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/books/update_category', methods=['POST'])
def update_book_category():
    """更改單一書籍的分類"""
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    try:
        supabase.table('books').update({'series_name': data.get('new_category')}).eq('id', data.get('book_id')).eq('uploader', session['user']).execute()
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)