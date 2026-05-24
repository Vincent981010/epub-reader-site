import os
from flask import Flask, request, jsonify, render_template, session

app = Flask(__name__)
# 設定 Session 金鑰以支援登入狀態管理[cite: 1]
app.secret_key = 'your_secure_secret_key' 
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 初始化資料庫為空列表，移除所有範例書籍[cite: 1]
books_db = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books_db)

@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('file')
    for file in files:
        if file and file.filename.endswith('.epub'):
            # 儲存檔案到伺服器磁碟[cite: 1]
            save_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(save_path)
            
            # 將檔案資訊加入資料庫[cite: 1]
            new_id = str(len(books_db) + 1)
            books_db.append({
                "id": new_id, 
                "title": file.filename, 
                "file_url": f"/static/uploads/{file.filename}", 
                "series_name": "未分類"
            })
    return jsonify({"status": "success"}), 200

@app.route('/books/delete', methods=['POST'])
def delete_books():
    data = request.get_json()
    ids_to_delete = data.get('ids', [])
    global books_db
    
    # 同步刪除實體檔案與資料庫列表[cite: 1]
    new_db = []
    for b in books_db:
        if b['id'] in ids_to_delete:
            # 刪除磁碟中的 EPUB 檔案[cite: 1]
            file_path = os.path.join(UPLOAD_FOLDER, b['title'])
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            new_db.append(b)
    
    books_db = new_db
    return jsonify({"status": "deleted"}), 200

# 用戶狀態管理，修復前端無限載入迴圈問題[cite: 1]
@app.route('/user/status', methods=['GET'])
def get_user_status():
    return jsonify(session.get('user', {"logged_in": False}))

@app.route('/login', methods=['POST'])
def login():
    session['user'] = {"logged_in": True, "username": "User"}
    return jsonify({"status": "success"})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)