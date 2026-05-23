import os
import uuid
from flask import Flask, request, jsonify, render_template, session, send_file[cite: 6]
from flask_session import Session[cite: 6]
import ebooklib[cite: 6]
from ebooklib import epub[cite: 6]
from bs4 import BeautifulSoup[cite: 6]

app = Flask(__name__)

# 配置 Session (儲存於伺服器記憶體中)
app.config["SECRET_KEY"] = os.urandom(24)[cite: 6]
app.config["SESSION_TYPE"] = "filesystem"[cite: 6]
Session(app)[cite: 6]

# 模擬資料庫 (實際開發建議改用 SQLite 或 PostgreSQL)
USERS = {
    "admin": {"password": "adminpassword", "is_admin": True},[cite: 6]
    "user1": {"password": "user1password", "is_admin": False}[cite: 6]
}
BOOKS = [][cite: 6]
SERIES = ["預設分類"][cite: 6]

# 首頁路由：改用標準的 render_template，徹底解決瀏覽器文字排版錯誤問題
@app.route('/')
def index():
    return render_template("index.html")

# 🔐 會員系統 API
@app.route('/user/status', methods=['GET'])
def user_status():
    if "username" in session:[cite: 6]
        return jsonify({
            "logged_in": True,[cite: 6]
            "username": session["username"],[cite: 6]
            "is_admin": session.get("is_admin", False)[cite: 6]
        })
    return jsonify({"logged_in": False})[cite: 6]

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()[cite: 6]
    username = data.get("username")[cite: 6]
    password = data.get("password")[cite: 6]
    
    user = USERS.get(username)[cite: 6]
    if user and user["password"] == password:[cite: 6]
        session["username"] = username[cite: 6]
        session["is_admin"] = user["is_admin"][cite: 6]
        return "", 200[cite: 6]
    return "Unauthorized", 401[cite: 6]

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()[cite: 6]
    username = data.get("username")[cite: 6]
    password = data.get("password")[cite: 6]
    
    if username in USERS:[cite: 6]
        return jsonify({"success": False, "error": "帳號已被註冊"}), 400[cite: 6]
        
    USERS[username] = {"password": password, "is_admin": False}[cite: 6]
    return jsonify({"success": True})[cite: 6]

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()[cite: 6]
    return "", 200[cite: 6]

# 📥 書籍管理 API
@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(BOOKS)[cite: 6]

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:[cite: 6]
        return jsonify({"error": "沒有檔案"}), 400[cite: 6]
    file = request.files['file'][cite: 6]
    if file.filename == '':[cite: 6]
        return jsonify({"error": "未選擇檔案"}), 400[cite: 6]
        
    if file and file.filename.endswith('.epub'):[cite: 6]
        book_id = str(uuid.uuid4())[cite: 6]
        # 安全存檔
        upload_dir = "uploads"[cite: 6]
        os.makedirs(upload_dir, exist_ok=True)[cite: 6]
        file_path = os.path.join(upload_dir, f"{book_id}.epub")[cite: 6]
        file.save(file_path)[cite: 6]
        
        # 解析 EPUB 標題
        try:
            epub_book = epub.read_epub(file_path)[cite: 6]
            title = epub_book.get_metadata('DC', 'title')[0][0] if epub_book.get_metadata('DC', 'title') else "未知名稱書籍"[cite: 6]
        except Exception:
            title = file.filename.rsplit('.', 1)[0][cite: 6]

        is_logged_in = "username" in session[cite: 6]
        new_book = {
            "id": book_id,[cite: 6]
            "title": title,[cite: 6]
            "series_name": SERIES[0], # 預設歸類到第一個分類[cite: 6]
            "is_temporary": not is_logged_in,[cite: 6]
            "uploader": session["username"] if is_logged_in else "匿名訪客"[cite: 6]
        }
        BOOKS.append(new_book)[cite: 6]
        return jsonify({"message": f"書籍《{title}》上傳並解析成功！", "book": new_book})[cite: 6]
        
    return jsonify({"error": "不支援的檔案格式，請上傳 EPUB"}), 400[cite: 6]

# 📥 一鍵導出 TXT API
@app.route('/books/<book_id>/download/txt', methods=['GET'])
def download_txt(book_id):
    book = next((b for b in BOOKS if b["id"] == book_id), None)[cite: 6]
    if not book:[cite: 6]
        return "Book not found", 404[cite: 6]
        
    file_path = os.path.join("uploads", f"{book_id}.epub")[cite: 6]
    txt_path = os.path.join("uploads", f"{book_id}.txt")[cite: 6]
    
    try:
        # 讀取 EPUB 並將 HTML 內文清洗成純文字
        epub_book = epub.read_epub(file_path)[cite: 6]
        full_text = [][cite: 6]
        
        for item in epub_book.get_items():[cite: 6]
            if item.get_type() == ebooklib.ITEM_DOCUMENT:[cite: 6]
                soup = BeautifulSoup(item.get_content(), 'html.parser')[cite: 6]
                # 簡單過濾掉腳本與樣式
                for script in soup(["script", "style"]):[cite: 6]
                    script.decompose()[cite: 6]
                full_text.append(soup.get_text())[cite: 6]
                
        with open(txt_path, "w", encoding="utf-8") as f:[cite: 6]
            f.write(f"📖 書名：{book['title']}\n")[cite: 6]
            f.write(f"分流：{book['series_name']}\n")[cite: 6]
            f.write("="*30 + "\n\n")[cite: 6]
            f.write("\n\n".join(full_text))[cite: 6]
            
        return send_file(txt_path, as_attachment=True, download_name=f"{book['title']}.txt")[cite: 6]
    except Exception as e:
        return f"轉換失敗: {str(e)}", 500[cite: 6]

# 👑 管理員功能 API
@app.route('/series', methods=['POST'])
def create_series():
    if not session.get("is_admin"):[cite: 6]
        return jsonify({"error": "權限不足，您不是管理員！"}), 403[cite: 4, 6]
        
    data = request.get_json()[cite: 6]
    name = data.get("name", "").strip()[cite: 6]
    if not name:[cite: 6]
        return jsonify({"error": "分類名稱不能為空"}), 400[cite: 6]
        
    if name in SERIES:[cite: 6]
        return jsonify({"error": "該分類已存在"}), 400[cite: 6]
        
    SERIES.append(name)[cite: 6]
    return jsonify({"name": name})[cite: 6]

if __name__ == '__main__':
    app.run(debug=True, port=5000)[cite: 6]