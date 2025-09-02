"""
App web en 1 archivo con:
1) Registro de usuario (usuario + contraseña)
2) Login/Logout
3) Formulario para ingresar parámetros (1–10) sobre capacidades
4) Almacenamiento en SQLite (usuarios + evaluaciones), contraseñas con hash

Requisitos (requirements.txt):
Flask>=2.3,<4
matplotlib>=3.7
numpy>=1.24

Ejecutar:
- python app.py
- Abrir http://127.0.0.1:5000

La base se crea automáticamente (app.db).
"""
from __future__ import annotations
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import io, base64

from flask import (
    Flask, g, redirect, render_template_string, request, session, url_for, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------- Config -------------------------
APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "app.db"
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)

# ------------------------- DB helpers ---------------------

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    technical_skill INTEGER,
    problem_solving INTEGER,
    communication INTEGER,
    teamwork INTEGER,
    adaptability INTEGER,
    initiative INTEGER,
    reliability INTEGER,
    time_management INTEGER,
    leadership INTEGER,
    learning_agility INTEGER,
    safety_awareness INTEGER,
    attention_to_detail INTEGER,
    notes TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    # Migración suave: agregar columna is_admin si falta
    cols = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    if "is_admin" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    # Crear admin inicial si se especifica por entorno
    admin_user = os.environ.get("FLASK_ADMIN_USERNAME")
    admin_pass = os.environ.get("FLASK_ADMIN_PASSWORD")
    if admin_user and admin_pass:
        cur = db.execute("SELECT id FROM users WHERE username=?", (admin_user,))
        if cur.fetchone() is None:
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                (admin_user, generate_password_hash(admin_pass), datetime.utcnow().isoformat()),
            )
    db.commit()

# ------------------------- Domain -------------------------
# Parámetros (1–10) — puedes ajustar nombres sin cambiar el código de DB
PARAMS = [
    ("technical_skill", "Dominio técnico"),
    ("problem_solving", "Resolución de problemas"),
    ("communication", "Comunicación"),
    ("teamwork", "Trabajo en equipo"),
    ("adaptability", "Adaptabilidad"),
    ("initiative", "Iniciativa"),
    ("reliability", "Responsabilidad/Confiabilidad"),
    ("time_management", "Gestión del tiempo"),
    ("leadership", "Liderazgo"),
    ("learning_agility", "Aprendizaje/Curiosidad"),
    ("safety_awareness", "Seguridad/Procedimientos"),
    ("attention_to_detail", "Atención al detalle"),
]

# ------------------------- Auth utils ---------------------

def get_user_by_username(username: str):
    cur = get_db().execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def current_user() -> sqlite3.Row | None:
    uid = session.get("user_id")
    if not uid:
        return None
    cur = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cur.fetchone()

def require_admin() -> bool:
    user = current_user()
    return bool(user and user["is_admin"] == 1)

# ------------------------- Routes -------------------------
@app.before_request
def _ensure_db():
    if not DB_PATH.exists():
        init_db()

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Usuario y contraseña son obligatorios", "error")
        elif get_user_by_username(username):
            flash("Ese usuario ya existe", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            db.commit()
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
    return render_page(TPL_REGISTER)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Sesión iniciada", "success")
            # cache simple para plantilla
            session["is_admin"] = user["is_admin"] == 1
            return redirect(url_for("dashboard"))
    return render_page(TPL_LOGIN)

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada", "success")
    return redirect(url_for("login"))

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        scores: Dict[str, int] = {}
        for key, _label in PARAMS:
            try:
                val = int(request.form.get(key, "0"))
            except ValueError:
                val = 0
            scores[key] = max(1, min(10, val))  # clamp 1..10
        notes = request.form.get("notes", "").strip() or None
        placeholders = ", ".join([f"{k}" for k, _ in PARAMS])
        columns = ", ".join(["user_id", "created_at", placeholders, "notes"])
        qmarks = ", ".join(["?" for _ in columns.split(", ")])
        db = get_db()
        db.execute(
            f"INSERT INTO assessments ({columns}) VALUES ({qmarks})",
            (
                session["user_id"],
                datetime.utcnow().isoformat(),
                *[scores[k] for k, _ in PARAMS],
                notes,
            ),
        )
        db.commit()
        flash("Evaluación guardada", "success")
        return redirect(url_for("dashboard"))

    # Cargar últimas evaluaciones del usuario
    db = get_db()
    rows = db.execute(
        "SELECT * FROM assessments WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (session["user_id"],),
    ).fetchall()

    return render_page(TPL_DASHBOARD, evals=rows, params=PARAMS)

# ------------------------- Templates ----------------------
BASE_CSS = """
:root{ --bg:#0f172a; --card:#111827; --muted:#94a3b8; --text:#e2e8f0; --acc:#22d3ee; }
*{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Arial;background:linear-gradient(180deg,#0b1220,#0f172a);color:var(--text)}
.container{max-width:900px;margin:40px auto;padding:24px}
.card{background:rgba(17,24,39,0.9);border:1px solid rgba(255,255,255,0.05);border-radius:16px;padding:24px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
.h1{font-size:28px;margin:0 0 8px}
.p{color:var(--muted);margin:0 0 16px}
.input, .btn, select, textarea{width:100%;padding:12px 14px;border-radius:12px;border:1px solid rgba(255,255,255,0.08);background:#0b1220;color:var(--text)}
.btn{cursor:pointer;font-weight:600}
.btn-primary{background:linear-gradient(90deg,#06b6d4,#22d3ee);color:#04212a;border:none}
.btn-link{background:transparent;border:none;color:var(--acc);padding:0;cursor:pointer}
.grid{display:grid;gap:16px}
.grid-2{grid-template-columns:repeat(2,1fr)}
.grid-3{grid-template-columns:repeat(3,1fr)}
label{font-size:14px;color:var(--muted);margin-bottom:6px;display:block}
.nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.alert{padding:12px 14px;border-radius:12px;margin-bottom:12px}
.alert.error{background:#3f1d2b;border:1px solid #ff5978;color:#ffd7de}
.alert.success{background:#0f2e2e;border:1px solid #22d3ee;color:#bbf7f3}
.table{width:100%;border-collapse:collapse}
.table th,.table td{padding:10px;border-bottom:1px solid rgba(255,255,255,0.06);text-align:left}
.small{font-size:12px;color:var(--muted)}
hr{border:none;border-top:1px solid rgba(255,255,255,0.06);margin:16px 0}
.range{width:100%}
.footer{margin-top:24px;color:var(--muted);font-size:12px;text-align:center}
"""

TPL_BASE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title or 'Evaluación de Capacidades' }}</title>
  <style>{{ css }}</style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="nav">
        <div><strong>Evaluación de Capacidades</strong></div>
        <div>
          {% if session.username %}
            <span class="small">Conectado como <strong>{{ session.username }}</strong></span>
            {% if session.is_admin %}&nbsp;·&nbsp;<a class="btn-link" href="{{ url_for('admin') }}">Admin</a>{% endif %}
            &nbsp;·&nbsp;
            <a class="btn-link" href="{{ url_for('logout') }}">Salir</a>
          {% else %}
            <a class="btn-link" href="{{ url_for('login') }}">Ingresar</a>
            &nbsp;·&nbsp;
            <a class="btn-link" href="{{ url_for('register') }}">Crear cuenta</a>
          {% endif %}
        </div>
      </div>

      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for cat, msg in messages %}
            <div class="alert {{ cat }}">{{ msg }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}

      {{ body|safe }}
    </div>
    <div class="footer">Hecho con Flask + SQLite · Guardado en <code>app.db</code></div>
  </div>
</body>
</html>
"""

TPL_REGISTER = """
<h1 class="h1">Crear cuenta</h1>
<p class="p">Regístrate para evaluar capacidades (1–10).</p>
<form method="post" class="grid">
  <div>
    <label>Usuario</label>
    <input class="input" name="username" required />
  </div>
  <div>
    <label>Contraseña</label>
    <input class="input" type="password" name="password" required />
  </div>
  <button class="btn btn-primary" type="submit">Crear cuenta</button>
</form>
<p class="small">¿Ya tienes cuenta? <a class="btn-link" href="{{ url_for('login') }}">Inicia sesión</a></p>
"""

TPL_LOGIN = """
<h1 class="h1">Iniciar sesión</h1>
<form method="post" class="grid">
  <div>
    <label>Usuario</label>
    <input class="input" name="username" required />
  </div>
  <div>
    <label>Contraseña</label>
    <input class="input" type="password" name="password" required />
  </div>
  <button class="btn btn-primary" type="submit">Ingresar</button>
</form>
<p class="small">¿No tienes cuenta? <a class="btn-link" href="{{ url_for('register') }}">Regístrate</a></p>
"""

TPL_DASHBOARD = """
<h1 class="h1">Evaluación de Capacidades (1–10)</h1>
<p class="p">Asigna puntajes del 1 al 10. Puedes repetir evaluaciones y ver el historial.</p>
<form method="post" class="grid">
  <div class="grid grid-2">
    {% for key, label in params %}
      <div>
        <label>{{ label }} (1–10)</label>
        <input class="range" type="range" name="{{ key }}" min="1" max="10" value="5" oninput="this.nextElementSibling.value=this.value" />
        <output>5</output>
      </div>
    {% endfor %}
  </div>
  <div>
    <label>Notas (opcional)</label>
    <textarea class="input" name="notes" rows="3" placeholder="Observaciones relevantes..."></textarea>
  </div>
  <button class="btn btn-primary" type="submit">Guardar evaluación</button>
</form>
<hr />
<h3>Últimas 10 evaluaciones</h3>
<table class="table">
  <thead>
    <tr>
      <th>Fecha (UTC)</th>
      {% for key, label in params %}<th title="{{ key }}">{{ label }}</th>{% endfor %}
      <th>Notas</th>
    </tr>
  </thead>
  <tbody>
    {% for r in evals %}
      <tr>
        <td class="small">{{ r['created_at'] }}</td>
        {% for key, _ in params %}
          <td>{{ r[key] }}</td>
        {% endfor %}
        <td class="small">{{ r['notes'] or '' }}</td>
      </tr>
    {% else %}
      <tr><td colspan="{{ 2 + params|length }}" class="small">Aún no hay evaluaciones.</td></tr>
    {% endfor %}
  </tbody>
</table>
"""

# ------------------------- Template ctx -------------------

def tpl_ctx(**extra):
    # Propaga flag de admin a las plantillas
    is_admin = False
    try:
        u = current_user()
        is_admin = bool(u and u["is_admin"])
    except Exception:
        pass
    return dict(
        base=TPL_BASE,
        css=BASE_CSS,
        title="Evaluación de Capacidades",
        **extra,
        session=dict(username=session.get("username"), is_admin=is_admin),
    )

# ------------------------- Render helper ------------------

def render_page(body_tmpl: str, **ctx):
    body_html = render_template_string(body_tmpl, **tpl_ctx(**ctx))
    return render_template_string(TPL_BASE, body=body_html, **tpl_ctx(**ctx))

# ------------------------- Admin (vista y gráfico radar) ---

def build_radar_base64(labels: List[str], values: List[float]) -> str:
    # Radar básico con matplotlib -> PNG en base64
    N = len(labels)
    if N == 0:
        return ""
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values = values + values[:1]
    angles = angles + angles[:1]

    fig = plt.figure(figsize=(5, 5))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles, values)
    ax.fill(angles, values, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_yticklabels([])
    ax.set_ylim(0, 10)
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"

TPL_ADMIN = """
<h1 class=\"h1\">Panel Admin</h1>
<p class=\"p\">Vista de todas las evaluaciones y radar con promedios globales.</p>

<h3>Promedios globales</h3>
<img src=\"{{ radar_uri }}\" alt=\"Radar promedios\" style=\"max-width:100%;border-radius:12px;\"/>

<hr />
<h3>Últimas 100 evaluaciones (todas)</h3>
<table class=\"table\">
  <thead>
    <tr>
      <th>Usuario</th>
      <th>Fecha (UTC)</th>
      {% for key, label in params %}<th title=\"{{ key }}\">{{ label }}</th>{% endfor %}
      <th>Notas</th>
    </tr>
  </thead>
  <tbody>
    {% for r in rows %}
      <tr>
        <td class=\"small\">{{ r['username'] }}</td>
        <td class=\"small\">{{ r['created_at'] }}</td>
        {% for key, _ in params %}
          <td>{{ r[key] }}</td>
        {% endfor %}
        <td class=\"small\">{{ r['notes'] or '' }}</td>
      </tr>
    {% else %}
      <tr><td colspan=\"{{ 3 + params|length }}\" class=\"small\">Sin datos.</td></tr>
    {% endfor %}
  </tbody>
</table>
"""

@app.route("/admin")
def admin():
    if not require_admin():
        flash("Requiere perfil administrador", "error")
        return redirect(url_for("login"))
    db = get_db()
    rows = db.execute(
        """
        SELECT a.*, u.username
        FROM assessments a
        JOIN users u ON u.id = a.user_id
        ORDER BY a.created_at DESC
        LIMIT 100
        """
    ).fetchall()

    # Calcular promedios globales por parámetro sobre todas las evaluaciones
    labels = [label for _k, label in PARAMS]
    keys = [k for k, _l in PARAMS]
    if rows:
        arr = np.array([[r[k] or 0 for k in keys] for r in rows], dtype=float)
        # promedio simple (ignorando ceros inexistentes)
        counts = (arr != 0).sum(axis=0)
        counts[counts == 0] = 1
        avg = (arr.sum(axis=0) / counts).tolist()
    else:
        avg = [0.0] * len(keys)

    radar_uri = build_radar_base64(labels, avg)
    return render_page(TPL_ADMIN, rows=rows, params=PARAMS, radar_uri=radar_uri)

# ------------------------- Main ---------------------------
if __name__ == "__main__":
    # Inicializa la base de datos dentro del contexto de la app
    with app.app_context():
        init_db()
    app.run(debug=True)
