import os
from flask import Flask, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'your_secret_key' # 請自行更換

# 設定上傳目錄
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- 處理多檔案上傳 ---
@app.route('/upload', methods=['POST'])
def upload():
    # 檢查是否登入
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    files = request.files.getlist('file') # 關鍵：使用 getlist 接收多個檔案
    for file in files:
        if file and file.filename.endswith('.epub'):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            # 這裡加入你的資料庫存入邏輯 (例如：db.insert(file.filename, file_path))
    return jsonify({"message": "success"}), 200

# --- 處理批次刪除 ---
@app.route('/books/delete', methods=['POST'])
def delete_books():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    ids_to_delete = data.get('ids', [])
    
    # 在此執行刪除資料庫紀錄，並刪除實體檔案
    # for book_id in ids_to_delete:
    #     db.execute("DELETE FROM books WHERE id = ?", book_id)
    
    return jsonify({"message": f"Successfully deleted {len(ids_to_delete)} books"}), 200

# ... 其他路由 (login, status, update_category) ...

if __name__ == '__main__':
    app.run(debug=True)