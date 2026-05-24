import os
from flask import Flask, render_template, request, session, jsonify
from flask_session import Session
from supabase import create_client, Client
from supabase.client import ClientOptions
from werkzeug.utils import secure_filename
import ebooklib
from ebooklib import epub

app = Flask(__name__)

# --- 1. 配置與環境變數設定 ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'flask_secret_key_for_epub_reader')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase_options = ClientOptions(
    postgrest_client_timeout=10,
    headers={"apiKey": SUPABASE_KEY} if SUPABASE_KEY else {}
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=supabase_options)

UPLOAD_FOLDER = '/tmp' if os.environ.get('RENDER') else 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- 2. 路由定義：主頁面渲染 ---

@app.route('/')
def index():
    return render_template('index.html')

# --- 3. JSON API 接口：使用者認證系統 ---

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() if request.is_json else request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"status": "error", "message": "帳號與密碼不能留空！"}), 400
        
    try:
        user_check = supabase.table('users').select('*').eq('username', username).execute()
        if user_check.data:
            return jsonify({"status": "error", "message": "此帳號已被註冊！"}), 400
        
        supabase.table('users').insert({
            "username": username,
            "password": password,
            "is_admin": False
        }).execute()
        return jsonify({"status": "success", "message": "註冊成功！請登入"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"註冊失敗：{str(e)}"}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() if request.is_json else request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    try:
        response = supabase.table('users').select('*').eq('username', username).eq('password', password).execute()
        user_data = response.data
        
        if user_data:
            session['user'] = username
            session['is_admin'] = user_data[0].get('is_admin', False)
            return jsonify({
                "status": "success", 
                "message": f"歡迎回來，{username}！",
                "user": {"username": username, "is_admin": session['is_admin']}
            }), 200
        return jsonify({"status": "error", "message": "帳號或密碼錯誤！"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": f"登入出錯：{str(e)}"}), 500

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "您已成功登出"}), 200

@app.route('/user/status', methods=['GET'])
def api_user_status():
    if 'user' in session:
        return jsonify({
            "logged_in": True,
            "username": session['user'],
            "is_admin": session.get('is_admin', False)
        }), 200
    return jsonify({"logged_in": False}), 200

# --- 4. JSON API 接口：書籍資料處理 (隱私隔離版) ---

@app.route('/books', methods=['GET'])
def api_get_books():
    """載入書籍清單：管理員看全部，一般用戶只看自己上傳的內容"""
    try:
        current_user = session.get('user', '匿名訪客')
        is_admin = session.get('is_admin', False)
        
        # 💡 隱私過濾邏輯
        if is_admin:
            response = supabase.table('books').select('*').execute()
        else:
            response = supabase.table('books').select('*').eq('uploader', current_user).execute()
            
        raw_data = response.data if response.data else []
        
        processed_data = []
        for book in raw_data:
            book_id = book.get('id', 'unknown_id')
            file_url = supabase.storage.from_('epubs').get_public_url(f"{book_id}.epub")
            
            processed_data.append({
                "id": book_id,
                "title": book.get('title', book_id),
                "series_name": book.get('series_name', '預設分類'),
                "uploader": book.get('uploader', '匿名訪客'),
                "is_temporary": book.get('is_temporary', False),
                "file_url": file_url
            })
            
        return jsonify(processed_data), 200
    except Exception as e:
        print(f"❌ 讀取書籍錯誤: {str(e)}")
        return jsonify([]), 200

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "沒有選擇檔案"}), 400
        
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.epub'):
        return jsonify({"status": "error", "message": "無效的檔案格式！"}), 400
        
    filename = secure_filename(file.filename)
    book_id = os.path.splitext(filename)[0]
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        book = epub.read_epub(filepath)
        title = book.get_metadata('DC', 'title')
        title_str = title[0][0] if title else book_id
        
        with open(filepath, 'rb') as f:
            try:
                supabase.storage.from_('epubs').upload(
                    path=f"{book_id}.epub",
                    file=f,
                    file_options={"content-type": "application/epub+zip"}
                )
            except Exception as storage_err:
                print(f"⚠️ Storage 上傳警告: {str(storage_err)}")
        
        uploader = session.get('user', '匿名訪客')
        payload = {"id": book_id, "title": title_str, "uploader": uploader}
        supabase.table('books').insert(payload).execute()
        
        return jsonify({"status": "success", "message": f"書籍《{title_str}》上傳成功！"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"處理失敗: {str(e)}"}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@app.route('/delete/<book_id>', methods=['POST', 'DELETE'])
def delete_book(book_id):
    if 'user' not in session:
        return jsonify({"status": "error", "message": "請先登入！"}), 401
        
    try:
        response = supabase.table('books').select('*').eq('id', book_id).execute()
        if not response.data:
            return jsonify({"status": "error", "message": "找不到該書籍"}), 404
            
        uploader = response.data[0].get('uploader', '匿名訪客')
        
        if session.get('is_admin') or session.get('user') == uploader:
            supabase.storage.from_('epubs').remove([f"{book_id}.epub"])
            supabase.table('books').delete().eq('id', book_id).execute()
            return jsonify({"status": "success", "message": "書籍已刪除"}), 200
        return jsonify({"status": "error", "message": "權限不足"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/rename_category/<book_id>', methods=['POST', 'PUT'])
def rename_category(book_id):
    if 'user' not in session:
        return jsonify({"status": "error", "message": "請先登入！"}), 401
        
    data = request.get_json() if request.is_json else request.form
    new_category = data.get('new_category', '').strip()
    
    if not new_category:
        return jsonify({"status": "error", "message": "分類名稱不能為空"}), 400
        
    try:
        response = supabase.table('books').select('uploader').eq('id', book_id).execute()
        if not response.data:
            return jsonify({"status": "error", "message": "找不到該書籍"}), 404
            
        uploader = response.data[0].get('uploader', '匿名訪客')
        
        if session.get('is_admin') or session.get('user') == uploader:
            supabase.table('books').update({"series_name": new_category}).eq('id', book_id).execute()
            return jsonify({"status": "success", "message": "分類已成功更新！"}), 200
        
        return jsonify({"status": "error", "message": "權限不足"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)