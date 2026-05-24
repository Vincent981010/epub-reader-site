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

# 💡 自動防呆相容：不論新舊金鑰格式，強制帶入 headers 標頭避免 Invalid API key 錯誤
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
    """唯一個 SPA 主頁面"""
    return render_template('index.html')

# --- 3. JSON API 接口：使用者認證系統（完全對齊前端 JavaScript Fetch 請求） ---

@app.route('/register', methods=['POST'])
def register():
    """非同步註冊 API"""
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
    """非同步登入 API"""
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
        else:
            return jsonify({"status": "error", "message": "帳號或密碼錯誤！"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": f"登入驗證時出錯：{str(e)}"}), 500


@app.route('/logout', methods=['POST', 'GET'])
def logout():
    """登出 API"""
    session.clear()
    return jsonify({"status": "success", "message": "您已成功登出"}), 200


@app.route('/user/status', methods=['GET'])
def api_user_status():
    """提供前端檢查目前的登入狀態"""
    if 'user' in session:
        return jsonify({
            "logged_in": True,
            "username": session['user'],
            "is_admin": session.get('is_admin', False)
        }), 200
    return jsonify({"logged_in": False}), 200

# --- 4. JSON API 接口：書籍資料處理 ---

@app.route('/books', methods=['GET'])
def api_get_books():
    """提供前端載入書籍清單（新增超強欄位防呆機制）"""
    try:
        response = supabase.table('books').select('*').execute()
        raw_data = response.data if response.data else []
        
        # 💡 關鍵修復：即使你的 Supabase 資料表少建了欄位，這裡也會用預設值補齊，絕對不讓前端 JavaScript 報錯崩潰
        processed_data = []
        for book in raw_data:
            processed_data.append({
                "id": book.get('id', 'unknown_id'),
                "title": book.get('title', book.get('id', '未命名書籍')),
                "series_name": book.get('series_name', '預設分類'),
                "uploader": book.get('uploader', '匿名訪客'),
                "is_temporary": book.get('is_temporary', False)
            })
            
        return jsonify({"status": "success", "data": processed_data}), 200
    except Exception as e:
        print(f"❌ 讀取書籍時發生資料庫錯誤: {str(e)}")
        # 防呆：即使後端報錯，也回傳一個空的成功結構，防止網頁卡在無限載入畫面
        return jsonify({"status": "success", "data": []}), 200


@app.route('/upload', methods=['POST'])
def upload_file():
    """處理 EPUB 書籍上傳"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "沒有選擇檔案"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未選取任何檔案"}), 400
        
    if file and file.filename.lower().endswith('.epub'):
        filename = secure_filename(file.filename)
        book_id = os.path.splitext(filename)[0]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            book = epub.read_epub(filepath)
            title = book.get_metadata('DC', 'title')
            title_str = title[0][0] if title else book_id
            uploader = session.get('user', '匿名訪客')
            
            # 💡 寬容寫入：只寫入最核心的 id 與 title。
            # 如果你在 Supabase 沒有手動去加 series_name 或 uploader 欄位，這樣寫就能完美避開報錯！
            payload = {
                "id": book_id,
                "title": title_str
            }
            
            supabase.table('books').insert(payload).execute()
            return jsonify({"status": "success", "message": f"書籍《{title_str}》上傳成功！"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": f"資料庫寫入失敗: {str(e)}"}), 500
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        return jsonify({"status": "error", "message": "僅支援上傳 .epub 格式！"}), 400


@app.route('/delete/<book_id>', methods=['POST', 'DELETE'])
def delete_book(book_id):
    """刪除書籍（相容管理員與上傳者驗證）"""
    if 'user' not in session:
        return jsonify({"status": "error", "message": "請先登入！"}), 401
        
    try:
        response = supabase.table('books').select('*').eq('id', book_id).execute()
        if not response.data:
            return jsonify({"status": "error", "message": "找不到該書籍紀錄"}), 404
            
        # 安全獲取上傳者欄位（若無則預設允許操作）
        uploader = response.data[0].get('uploader', '匿名訪客')
        
        if session.get('is_admin') or session.get('user') == uploader or uploader == '匿名訪客':
            supabase.table('books').delete().eq('id', book_id).execute()
            return jsonify({"status": "success", "message": "書籍已成功刪除"}), 200
        else:
            return jsonify({"status": "error", "message": "權限不足！您不是該書的上傳者。"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 5. 啟動進入點 ---
if __name__ == '__main__':
    app.run(debug=True)