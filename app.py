import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_session import Session
from supabase import create_client, Client
from supabase.client import ClientOptions
from werkzeug.utils import secure_filename
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- 1. 配置與環境變數設定 ---
# 密鑰用於 Flask 內部的 Session 簽章，若環境變數沒有則提供預設值
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'flask_secret_key_for_epub_reader')

# Flask-Session 記憶體形式配置（避免 Vercel/Render 重啟後重置檔案型 Session）
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# 讀取 Render 後台設定的 Supabase 環境變數
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 💡 自動防呆：透過 ClientOptions 強制加上 headers
# 這樣無論你 Render 環境變數填新金鑰 (sb_secret_) 還是舊金鑰 (eyJ...)，都不會噴 Invalid API key
supabase_options = ClientOptions(
    postgrest_client_timeout=10,
    headers={"apiKey": SUPABASE_KEY} if SUPABASE_KEY else {}
)

# 初始化 Supabase 用戶端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=supabase_options)

# 暫存上傳檔案的資料夾配置
UPLOAD_FOLDER = '/tmp' if os.environ.get('RENDER') else 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- 2. 路由定義：使用者認證系統 ---

@app.route('/')
def index():
    """首頁：展示書籍列表（標準後端渲染）"""
    try:
        response = supabase.table('books').select('*').execute()
        books = response.data if response.data else []
    except Exception as e:
        flash(f"讀取資料庫失敗：{str(e)}", "danger")
        books = []
    return render_template('index.html', books=books)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """註冊功能"""
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        
        if not username or not password:
            flash("帳號與密碼不能留空！", "warning")
            return redirect(url_for('register'))
            
        try:
            # 檢查帳號是否已被註冊
            user_check = supabase.table('users').select('*').eq('username', username).execute()
            if user_check.data:
                flash("此帳號已被註冊！", "danger")
                return redirect(url_for('register'))
            
            # 寫入新使用者資料（預設非管理員）
            supabase.table('users').insert({
                "username": username,
                "password": password,
                "is_admin": False
            }).execute()
            
            flash("註冊成功！請登入", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"註冊失敗：{str(e)}", "danger")
            
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登入功能"""
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        
        try:
            # 查詢使用者
            response = supabase.table('users').select('*').eq('username', username).eq('password', password).execute()
            user_data = response.data
            
            if user_data:
                session['user'] = username
                session['is_admin'] = user_data[0].get('is_admin', False)
                flash(f"歡迎回來，{username}！", "success")
                return redirect(url_for('index'))
            else:
                flash("帳號或密碼錯誤！", "danger")
        except Exception as e:
            flash(f"登入驗證時出錯：{str(e)}", "danger")
            
    return render_template('login.html')


@app.route('/logout')
def logout():
    """登出功能"""
    session.clear()
    flash("您已成功登出", "info")
    return redirect(url_for('index'))

# --- 3. 路由定義：書籍解析與上傳管理 ---

@app.route('/upload', methods=['POST'])
def upload_file():
    """處理 EPUB 書籍上傳"""
    if 'file' not in request.files:
        flash('沒有選擇檔案', 'warning')
        return redirect(url_for('index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('未選取任何檔案', 'warning')
        return redirect(url_for('index'))
        
    if file and file.filename.lower().endswith('.epub'):
        filename = secure_filename(file.filename)
        # 用於存入資料庫的唯一 ID（移除副檔名）
        book_id = os.path.splitext(filename)[0]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # 解析 EPUB 獲取書名
            book = epub.read_epub(filepath)
            title = book.get_metadata('DC', 'title')
            title_str = title[0][0] if title else book_id
            
            # 判斷上傳者身分
            uploader = session.get('user', '匿名訪客')
            
            # 將書籍資訊寫入 Supabase books 資料表
            supabase.table('books').insert({
                "id": book_id,
                "title": title_str,
                "series_name": "預設分類",
                "is_temporary": False,
                "uploader": uploader
            }).execute()
            
            flash(f"書籍《{title_str}》上傳並紀錄成功！", "success")
        except Exception as e:
            flash(f"書籍處理或資料庫寫入失敗：{str(e)}", "danger")
        finally:
            # 清理本機暫存檔案
            if os.path.exists(filepath):
                os.remove(filepath)
                
    else:
        flash('僅支援上傳 .epub 格式的電子書！', 'danger')
        
    return redirect(url_for('index'))


@app.route('/delete/<book_id>', methods=['POST'])
def delete_book(book_id):
    """刪除書籍（僅限管理員或上傳者本人）"""
    if 'user' not in session:
        flash("請先登入後再執行刪除！", "warning")
        return redirect(url_for('login'))
        
    try:
        # 查出該書的上傳者
        response = supabase.table('books').select('uploader').eq('id', book_id).execute()
        if not response.data:
            flash("找不到該書籍紀錄！", "danger")
            return redirect(url_for('index'))
            
        uploader = response.data[0].get('uploader')
        
        # 權限檢查：必須是管理員，或是上傳者本人
        if session.get('is_admin') or session.get('user') == uploader:
            supabase.table('books').delete().eq('id', book_id).execute()
            flash("書籍紀錄已成功刪除！", "success")
        else:
            flash("權限不足！您不是該書的上傳者或系統管理員。", "danger")
            
    except Exception as e:
        flash(f"刪除失敗：{str(e)}", "danger")
        
    return redirect(url_for('index'))


# --- 4. 前端 JavaScript AJAX 請求所需的 API 接口（解決 404 轉圈圈問題） ---

@app.route('/books', methods=['GET'])
def api_get_books():
    """提供前端 AJAX 非同步載入書籍清單"""
    try:
        response = supabase.table('books').select('*').execute()
        return {"status": "success", "data": response.data if response.data else []}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/user/status', methods=['GET'])
def api_user_status():
    """提供前端 AJAX 檢查目前使用者的登入狀態"""
    if 'user' in session:
        return {
            "logged_in": True,
            "username": session['user'],
            "is_admin": session.get('is_admin', False)
        }, 200
    return {"logged_in": False}, 200


# --- 5. 啟動進入點 ---
if __name__ == '__main__':
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ 警告: 偵測到未設定 SUPABASE_URL 或 SUPABASE_KEY 環境變數。")
    app.run(debug=True)