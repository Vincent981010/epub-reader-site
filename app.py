import os
import uuid
from flask import Flask, request, jsonify, session, Response, send_file
from flask_session import Session
from supabase import create_client, Client
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

app = Flask(__name__)

# 配置 Session (儲存於伺服器記憶體中)
app.config["SECRET_KEY"] = os.urandom(24)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# 🌐 串接 Supabase 雲端資料庫環境變數
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 如果在本地電腦測試且尚未設定環境變數，可以在下方填入你的金鑰（上傳 GitHub 前記得刪除以免洩漏）
if not SUPABASE_URL or not SUPABASE_KEY:
    SUPABASE_URL = "你的_SUPABASE_URL"
    SUPABASE_KEY = "你的_SUPABASE_ANON_KEY"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SERIES = ["預設分類"]

# 首頁路由
@app.route('/')
def index():
    try:
        template_path = os.path.join(app.root_path, 'templates', 'index.html')
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return Response(html_content, mimetype='text/html')
    except Exception as e:
        return f"找不到 templates/index.html 檔案，錯誤：{str(e)}", 404

# 🔐 會員系統 API
@app.route('/user/status', methods=['GET'])
def user_status():
    if "username" in session:
        return jsonify({
            "logged_in": True,
            "username": session["username"],
            "is_admin": session.get("is_admin", False)
        })
    return jsonify({"logged_in": False})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    # 從 Supabase 雲端資料庫查詢使用者
    response = supabase.table("users").select("*").eq("username", username).execute()
    user_list = response.data
    
    if user_list and user_list[0]["password"] == password:
        session["username"] = username
        session["is_admin"] = user_list[0]["is_admin"]
        return "", 200
    return "Unauthorized", 401

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    # 修正先前的語法錯誤，改為正確的 Python 邏輯運算子
    if not username or not password:
        return jsonify({"success": False, "error": "帳號密碼不能為空"}), 400

    # 檢查帳號是否已被註冊
    check_user = supabase.table("users").select("username").eq("username", username).execute()
    if check_user.data:
        return jsonify({"success": False, "error": "帳號已被註冊"}), 400
        
    # 寫入 Supabase 雲端資料庫
    supabase.table("users").insert({
        "username": username,
        "password": password,
        "is_admin": False
    }).execute()
    
    return jsonify({"success": True})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return "", 200

# 📥 書籍管理 API
@app.route('/books', methods=['GET'])
def get_books():
    # 從雲端資料庫獲取所有書籍目錄
    response = supabase.table("books").select("*").execute()
    return jsonify(response.data)

# 📥 批次上傳 API
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "沒有檔案欄位"}), 400
        
    files = request.files.getlist('file')
    
    if not files or files[0].filename == '':
        return jsonify({"error": "未選擇任何檔案"}), 400
        
    uploaded_books = []
    errors = []
    
    # 建立本地暫存資料夾（僅供解析結構使用）
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    for file in files:
        if file and file.filename.endswith('.epub'):
            book_id = str(uuid.uuid4())
            base_filename = os.path.basename(file.filename)
            file_path = os.path.join(upload_dir, f"{book_id}.epub")
            file.save(file_path)
            
            try:
                epub_book = epub.read_epub(file_path)
                title_meta = epub_book.get_metadata('DC', 'title')
                title = title_meta[0][0] if title_meta else base_filename.rsplit('.', 1)[0]
            except Exception:
                title = base_filename.rsplit('.', 1)[0]

            is_logged_in = "username" in session
            new_book = {
                "id": book_id,
                "title": title,
                "series_name": SERIES[0],
                "is_temporary": not is_logged_in,
                "uploader": session["username"] if is_logged_in else "匿名訪客"
            }
            
            # 將書籍 meta 資訊安全地寫入 Supabase
            supabase.table("books").insert(new_book).execute()
            uploaded_books.append(new_book)
        else:
            if file.filename:
                errors.append(f"檔案 {file.filename} 格式不符，已被系統跳過")

    return jsonify({
        "message": f"成功匯入並解析 {len(uploaded_books)} 本書籍！",
        "books": uploaded_books,
        "errors": errors
    })

# 📥 一鍵導出 TXT API
@app.route('/books/<book_id>/download/txt', methods=['GET'])
def download_txt(book_id):
    # 從雲端資料庫確認書籍是否存在
    response = supabase.table("books").select("*").eq("id", book_id).execute()
    if not response.data:
        return "Book not found", 404
        
    book = response.data[0]
    file_path = os.path.join("uploads", f"{book_id}.epub")
    txt_path = os.path.join("uploads", f"{book_id}.txt")
    
    if not os.path.exists(file_path):
        return "本地暫存檔案已隨伺服器重啟釋放，無法導出。請嘗試重新拖入解析！", 410
        
    try:
        epub_book = epub.read_epub(file_path)
        full_text = []
        
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                for script in soup(["script", "style"]):
                    script.decompose()
                full_text.append(soup.get_text())
                
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"📖 書名：{book['title']}\n")
            f.write(f"分流：{book['series_name']}\n")
            f.write("="*30 + "\n\n")
            f.write("\n\n".join(full_text))
            
        return send_file(txt_path, as_attachment=True, download_name=f"{book['title']}.txt")
    except Exception as e:
        return f"轉換失敗: {str(e)}", 500

# 👑 管理員功能 API
@app.route('/series', methods=['POST'])
def create_series():
    if not session.get("is_admin"):
        return jsonify({"error": "權限不足，您不是管理員！"}), 403
        
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "分類名稱不能為空"}), 400
        
    if name in SERIES:
        return jsonify({"error": "該分類已存在"}), 400
        
    SERIES.append(name)
    return jsonify({"name": name})

if __name__ == '__main__':
    app.run(debug=True, port=5000)