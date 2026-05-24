import os
from flask import Flask, render_template, request, session, jsonify
from flask_session import Session
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from ebooklib import epub

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_12345')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    res = supabase.table('users').select('*').eq('username', data.get('username')).eq('password', data.get('password')).execute()
    if res.data:
        session['user'] = data.get('username')
        session['is_admin'] = res.data[0].get('is_admin', False)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "帳號密碼錯誤"}), 401

@app.route('/books', methods=['GET'])
def get_books():
    user = session.get('user')
    if not user: return jsonify([]), 200
    
    # 隱私隔離：一般用戶只看自己的，管理員看全部
    if session.get('is_admin'):
        res = supabase.table('books').select('*').execute()
    else:
        res = supabase.table('books').select('*').eq('uploader', user).execute()
    return jsonify(res.data if res.data else []), 200

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    file = request.files['file']
    filename = secure_filename(file.filename)
    book_id = os.path.splitext(filename)[0]
    
    # 上傳時強制綁定 uploader
    supabase.table('books').insert({
        "id": book_id, 
        "title": filename, 
        "uploader": session['user'] 
    }).execute()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)