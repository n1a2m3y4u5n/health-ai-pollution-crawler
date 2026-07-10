# !! 경고: 이 앱은 교육 목적으로만 사용되며,
# !! 의도적으로 보안 취약점이 삽입되어 있습니다.
# !! 실제 서비스에 절대 사용하지 마세요.

import os
import sys
import time
import sqlite3
import threading
import subprocess
from collections import deque
from flask import (Flask, render_template, request, redirect,
                   url_for, session, g, Response, jsonify, abort)

app = Flask(__name__)
app.secret_key = 'edu_secret_key_2024'

DATABASE = os.path.join(os.path.dirname(__file__), 'board.db')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')

# =============================================
# Cloudflare Tunnel 자동 실행
# =============================================
def start_tunnel():
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", "http://localhost:5002"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        for line in proc.stdout:
            line = line.decode(errors='ignore')
            if "trycloudflare.com" in line or "cloudflare" in line.lower():
                print(f"\n[접속 주소] {line.strip()}\n")
    except FileNotFoundError:
        print("[경고] cloudflared 없음 → http://localhost:5000 으로만 접속 가능")


# =============================================
# [DS-VULN-6] Hash Collision: 단순 modulo 해시 사용
# sum(ord(c)) % 100  →  같은 합계를 가진 다른 비밀번호로 로그인 가능
# 예) 'pass1' → 합=532, 532%100=32
#     'spass' → 합=532 → 동일 해시 → 로그인 성공
# =============================================
def simple_hash(password: str) -> int:
    # [DS-VULN-6] Hash Collision: 단순 modulo 해시 사용
    return sum(ord(c) for c in password) % 100


# =============================================
# [DS-VULN-8] LinkedList 조작: 게시글 순서 관리
# =============================================
class Node:
    def __init__(self, post_id: int):
        self.post_id = post_id
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None

    def append(self, post_id: int):
        node = Node(post_id)
        if not self.head:
            self.head = node
            return
        cur = self.head
        while cur.next:
            cur = cur.next
        cur.next = node

    def pin_to_front(self, post_id: int):
        # [DS-VULN-8] LinkedList 조작: 권한·존재 여부 검증 없이 맨 앞 이동
        if self.head and self.head.post_id == post_id:
            return
        prev, cur = None, self.head
        while cur:
            if cur.post_id == post_id:
                if prev:
                    prev.next = cur.next
                cur.next = self.head
                self.head = cur
                return
            prev, cur = cur, cur.next
        # 존재하지 않는 ID도 강제 삽입
        node = Node(post_id)
        node.next = self.head
        self.head = node

    def to_list(self):
        result, cur = [], self.head
        while cur:
            result.append(cur.post_id)
            cur = cur.next
        return result


post_list = LinkedList()

# =============================================
# [DS-VULN-9] Queue Race Condition: 출석 포인트 중복 지급
# =============================================
point_queue: deque = deque()
claimed_today: set = set()


def process_point_queue():
    while True:
        if point_queue:
            username = point_queue.popleft()
            # [DS-VULN-9] 큐에서 꺼낸 뒤 DB 업데이트 — 삽입 전 중복 체크만 있어 레이스 허용
            conn = sqlite3.connect(DATABASE)
            conn.execute("UPDATE users SET points = points + 50 WHERE username = ?", (username,))
            conn.commit()
            conn.close()
        time.sleep(0.01)


# =============================================
# 데이터베이스
# =============================================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash INTEGER NOT NULL,
        email TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        is_admin INTEGER DEFAULT 0,
        points INTEGER DEFAULT 100,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        author TEXT NOT NULL,
        category TEXT DEFAULT '일반',
        views INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        author TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 초기 유저
    users = [
        ('admin',  simple_hash('admin123'), 'admin@csboard.kr',  1, 500),
        ('user1',  simple_hash('pass1'),    'user1@csboard.kr',  0, 100),
        ('user2',  simple_hash('pass2'),    'user2@csboard.kr',  0, 100),
        ('user3',  simple_hash('pass3'),    'user3@csboard.kr',  0, 100),
    ]
    for u in users:
        try:
            c.execute("INSERT INTO users (username,password_hash,email,is_admin,points) VALUES (?,?,?,?,?)", u)
        except sqlite3.IntegrityError:
            pass

    # 초기 게시글
    if c.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
        posts = [
            ('자료구조 스터디 그룹 모집합니다 🙌',
             '안녕하세요! 이번 학기 자료구조 스터디 그룹을 모집합니다.\n\n'
             '매주 토요일 오후 2시에 만나 함께 공부할 분들을 찾고 있어요.\n'
             '링크드리스트, 스택, 큐, 해시테이블 순서로 진행 예정입니다.\n\n'
             '관심 있으신 분은 댓글 남겨주세요!',
             'user1', '스터디'),
            ('알고리즘 문제 사이트 추천해주세요',
             '링크드리스트, 스택, 큐 관련 좋은 알고리즘 문제 사이트 추천 부탁드립니다.\n'
             '백준이나 프로그래머스 외에 다른 곳도 있을까요?\n\n'
             '특히 자료구조 개념을 직접 구현해볼 수 있는 문제 위주로 알고 싶습니다.',
             'user2', '질문'),
            ('중간고사 범위 공유해요',
             '중간고사 범위가 4장까지라고 하시던데 맞나요?\n'
             '해시테이블도 포함되는지 궁금합니다.\n\n'
             '교수님께 여쭤보려고 하는데 같이 물어볼 분 계신가요?',
             'user3', '공지'),
            ('기말 프로젝트 아이디어 공유',
             '기말 프로젝트로 자료구조를 활용한 프로그램을 만들어야 하는데 막막하네요.\n\n'
             '- 도서관 대출 시스템 (연결리스트)\n'
             '- 미로 탐색 (스택/큐)\n'
             '- 연락처 앱 (해시테이블)\n\n'
             '혹시 더 좋은 아이디어 있으신 분 공유해 주세요!',
             'user1', '일반'),
            ('게시판 이용 규칙 안내',
             '본 게시판은 교육 목적으로 운영됩니다.\n\n'
             '① 서로 존중하는 언어를 사용해 주세요.\n'
             '② 학습과 관련 없는 게시물은 삭제될 수 있습니다.\n'
             '③ 타인의 개인정보를 무단으로 공유하지 마세요.\n\n'
             '좋은 학습 공간을 함께 만들어 나가요 😊',
             'admin', '공지'),
        ]
        for p in posts:
            c.execute("INSERT INTO posts (title,content,author,category) VALUES (?,?,?,?)", p)

    conn.commit()

    # LinkedList 초기화
    rows = conn.execute("SELECT id FROM posts ORDER BY id").fetchall()
    for row in rows:
        post_list.append(row[0])

    conn.close()


# =============================================
# 라우트
# =============================================

@app.route('/')
def index():
    db = get_db()
    posts = db.execute(
        "SELECT * FROM posts ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    points = None
    if session.get('username'):
        row = db.execute("SELECT points FROM users WHERE username=?",
                         (session['username'],)).fetchone()
        if row:
            points = row['points']
    return render_template('index.html', posts=posts,
                           user=session.get('username'),
                           is_admin=session.get('is_admin'),
                           points=points)


# --------------------------------------------------
# [VULN-1] SQL Injection  +  [DS-VULN-6] Hash Collision
# --------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        db = get_db()

        # [VULN-1] SQL Injection: f-string으로 쿼리 직접 조합
        query = f"SELECT * FROM users WHERE username = '{username}'"
        try:
            user = db.execute(query).fetchone()
        except Exception as e:
            error = f'쿼리 오류: {e}'
            return render_template('login.html', error=error)

        if user:
            # [DS-VULN-6] Hash Collision: 단순 해시 비교만으로 인증
            if user['password_hash'] == simple_hash(password):
                session['username'] = user['username']
                session['is_admin'] = bool(user['is_admin'])
                return redirect(url_for('index'))
            error = '비밀번호가 올바르지 않습니다.'
        else:
            error = '존재하지 않는 아이디입니다.'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        if not username or not password:
            error = '아이디와 비밀번호를 입력해주세요.'
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username,password_hash,email) VALUES (?,?,?)",
                    (username, simple_hash(password), email)
                )
                db.commit()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = '이미 사용 중인 아이디입니다.'
    return render_template('register.html', error=error)


@app.route('/board')
def board():
    db = get_db()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 10
    offset = (page - 1) * per_page
    category = request.args.get('category', '')

    if category:
        total = db.execute("SELECT COUNT(*) FROM posts WHERE category=?", (category,)).fetchone()[0]
        posts = db.execute(
            "SELECT * FROM posts WHERE category=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (category, per_page, offset)
        ).fetchall()
    else:
        total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        posts = db.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()

    pinned_ids = post_list.to_list()[:3]
    total_pages = (total + per_page - 1) // per_page

    return render_template('board.html', posts=posts, page=page,
                           total_pages=total_pages, category=category,
                           pinned_ids=pinned_ids,
                           user=session.get('username'),
                           is_admin=session.get('is_admin'))


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    db = get_db()
    db.execute("UPDATE posts SET views=views+1 WHERE id=?", (post_id,))
    db.commit()
    post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        abort(404)
    comments = db.execute(
        "SELECT * FROM comments WHERE post_id=? ORDER BY created_at", (post_id,)
    ).fetchall()
    return render_template('post.html', post=post, comments=comments,
                           user=session.get('username'),
                           is_admin=session.get('is_admin'))


@app.route('/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    if not session.get('username'):
        return redirect(url_for('login'))
    content = request.form.get('content', '').strip()
    if content:
        db = get_db()
        db.execute("INSERT INTO comments (post_id,author,content) VALUES (?,?,?)",
                   (post_id, session['username'], content))
        db.commit()
    return redirect(url_for('post_detail', post_id=post_id))


# --------------------------------------------------
# [VULN-2] Stored XSS: 게시글 이스케이프 없이 저장 및 렌더링
# --------------------------------------------------
@app.route('/write', methods=['GET', 'POST'])
def write():
    if not session.get('username'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        title    = request.form.get('title', '')
        content  = request.form.get('content', '')
        category = request.form.get('category', '일반')
        # [VULN-2] Stored XSS: 입력값 검증/이스케이프 없이 DB에 그대로 저장
        db = get_db()
        cur = db.execute(
            "INSERT INTO posts (title,content,author,category) VALUES (?,?,?,?)",
            (title, content, session['username'], category)
        )
        db.commit()
        post_list.append(cur.lastrowid)
        return redirect(url_for('post_detail', post_id=cur.lastrowid))
    return render_template('write.html', user=session.get('username'),
                           is_admin=session.get('is_admin'))


# --------------------------------------------------
# [VULN-3] Reflected XSS: 검색어 그대로 출력
# --------------------------------------------------
@app.route('/search')
def search():
    q = request.args.get('q', '')
    results = []
    if q:
        db = get_db()
        results = db.execute(
            "SELECT * FROM posts WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC",
            (f'%{q}%', f'%{q}%')
        ).fetchall()
    # [VULN-3] Reflected XSS: q를 템플릿에서 |safe 필터로 출력
    return render_template('search.html', q=q, results=results,
                           user=session.get('username'),
                           is_admin=session.get('is_admin'))


# --------------------------------------------------
# [VULN-4] CSRF + 프로필
# --------------------------------------------------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('username'):
        return redirect(url_for('login'))
    db = get_db()
    message = None
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        bio          = request.form.get('bio', '')
        username     = session['username']
        # [VULN-4] CSRF: CSRF 토큰 없이 비밀번호 변경 — 외부 폼으로 공격 가능
        if new_password:
            db.execute("UPDATE users SET password_hash=? WHERE username=?",
                       (simple_hash(new_password), username))
            db.commit()
            message = '비밀번호가 변경되었습니다.'
        if bio is not None:
            db.execute("UPDATE users SET bio=? WHERE username=?", (bio, username))
            db.commit()
    user_data = db.execute("SELECT * FROM users WHERE username=?",
                           (session['username'],)).fetchone()
    return render_template('profile.html', user=session.get('username'),
                           is_admin=session.get('is_admin'),
                           user_data=user_data, message=message)


# --------------------------------------------------
# [VULN-5] Path Traversal: 파일 다운로드
# --------------------------------------------------
@app.route('/download')
def download():
    filename = request.args.get('file', '')
    if not filename:
        return '파일명을 지정하세요. 예) /download?file=readme.txt', 400

    # [VULN-5] Path Traversal: os.path.join 후 경로 검증 없이 직접 오픈
    filepath = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        return Response(
            data,
            mimetype='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{os.path.basename(filename)}"'}
        )
    except FileNotFoundError:
        return f'파일을 찾을 수 없습니다: {filename}', 404
    except IsADirectoryError:
        return '디렉터리는 다운로드할 수 없습니다.', 400
    except Exception as e:
        return f'오류: {e}', 500


@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        abort(403)
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    posts = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    return render_template('admin.html', users=users, posts=posts,
                           user=session.get('username'),
                           is_admin=session.get('is_admin'))


# --------------------------------------------------
# [DS-VULN-7] Stack DoS: 재귀 깊이 제한 없음
# --------------------------------------------------
@app.route('/api/tree')
def api_tree():
    depth = request.args.get('depth', 5, type=int)

    # [DS-VULN-7] Stack DoS: sys.setrecursionlimit 조정 없이 무제한 재귀
    def build_tree(n):
        if n == 0:
            return {'value': 0, 'children': []}
        return {'value': n, 'children': [build_tree(n - 1), build_tree(n - 1)]}

    try:
        tree = build_tree(depth)
        return jsonify({'status': 'ok', 'depth': depth, 'nodes': 2**depth - 1})
    except RecursionError:
        return jsonify({'status': 'error',
                        'message': 'RecursionError: 스택 오버플로우 발생!'}), 500


# --------------------------------------------------
# [DS-VULN-8] LinkedList 조작: 임의 게시글 상단 고정
# --------------------------------------------------
@app.route('/api/pin')
def api_pin():
    post_id = request.args.get('id', type=int)
    if post_id is None:
        return jsonify({'status': 'error', 'message': 'id 파라미터가 필요합니다'}), 400
    # [DS-VULN-8] LinkedList 조작: 로그인·권한·존재 여부 검증 없이 pin 가능
    post_list.pin_to_front(post_id)
    return jsonify({'status': 'ok',
                    'message': f'게시글 {post_id}번이 상단으로 이동되었습니다.',
                    'order': post_list.to_list()[:10]})


# --------------------------------------------------
# [DS-VULN-9] Queue Race Condition: 출석 포인트 중복 지급
# --------------------------------------------------
@app.route('/point/claim', methods=['POST'])
def claim_point():
    if not session.get('username'):
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다'}), 401
    username = session['username']

    # [DS-VULN-9] Race Condition: 중복 체크 후 sleep → 두 요청이 동시에 통과 가능
    if username in claimed_today:
        return jsonify({'status': 'error', 'message': '오늘 이미 출석 체크를 완료했습니다.'}), 400

    time.sleep(0.15)  # 의도적 지연으로 레이스 컨디션 재현 용이하게

    claimed_today.add(username)
    point_queue.append(username)
    return jsonify({'status': 'ok', 'message': '출석 포인트 50점이 지급됩니다!',
                    'note': '잠시 후 포인트에 반영됩니다.'})


@app.route('/point/status')
def point_status():
    if not session.get('username'):
        return jsonify({'status': 'error'}), 401
    db = get_db()
    row = db.execute("SELECT points FROM users WHERE username=?",
                     (session['username'],)).fetchone()
    return jsonify({'status': 'ok', 'points': row['points'] if row else 0,
                    'username': session['username']})


# =============================================
# 실행
# =============================================
if __name__ == '__main__':
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    print("=================================")
    print(" 교육용 취약 웹 앱 실행됨")
    print(" [주의] 이 앱은 의도적 취약점 포함")
    print("=================================")

    init_db()

    print("[Cloudflare Tunnel 연결 중...]")
    threading.Thread(target=start_tunnel, daemon=True).start()
    threading.Thread(target=process_point_queue, daemon=True).start()

    print("=================================")
    print("심어진 취약점 목록:")
    print(" [VULN-1] SQL Injection          → /login")
    print(" [VULN-2] Stored XSS             → /write")
    print(" [VULN-3] Reflected XSS          → /search")
    print(" [VULN-4] CSRF                   → /profile")
    print(" [VULN-5] Path Traversal         → /download")
    print(" [DS-VULN-6] Hash Collision      → /login")
    print(" [DS-VULN-7] Stack DoS           → /api/tree")
    print(" [DS-VULN-8] LinkedList 조작     → /api/pin")
    print(" [DS-VULN-9] Queue RaceCondition → /point/claim")
    print("=================================")

    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
