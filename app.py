import os
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 載入主頁面
@app.route('/')
def index():
    return render_template('index.html')

# 取得書籍列表
@app.route('/books', methods=['GET'])
def get_books():
    # 這裡未來連接你的資料庫，現在回傳模擬資料
    return jsonify([
        {"id": "1", "title": "範例書籍.epub", "file_url": "/static/uploads/範例書籍.epub", "series_name": "未分類"}
    ])

# 處理多檔案上傳
@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('file') # 接收多檔案
    for file in files:
        if file and file.filename.endswith('.epub'):
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    return jsonify({"status": "success"}), 200

# 處理批次刪除
@app.route('/books/delete', methods=['POST'])
def delete_books():
    data = request.get_json()
    ids_to_delete = data.get('ids', []) # 接收 ID 列表
    # 在此加入刪除資料庫與實體檔案的邏輯
    return jsonify({"status": "deleted", "count": len(ids_to_delete)}), 200

if __name__ == '__main__':
    app.run(debug=True)