Evaluación de Capacidades (Flask + SQLite)

Aplicación web de una sola pieza (app.py) para registrar usuarios, iniciar sesión y evaluar capacidades con puntajes 1–10.
Incluye panel de administración con una gráfica radar (araña) de promedios globales por capacidad.

✨ Características

Registro/Login/Logout con contraseñas hasheadas (Werkzeug).

Formulario de evaluación con 12 parámetros (ajustables) en escala 1–10 + notas.

Historial de las últimas 10 evaluaciones por usuario.

Admin:

Tabla con hasta 100 evaluaciones combinadas de todos los usuarios.

Radar de promedios globales (Matplotlib sin interfaz gráfica, backend Agg).

Persistencia en SQLite (app.db) y creación de esquema automática.

Código y vistas embebidas (HTML/CSS minimalista con render_template_string).

🧱 Stack

Python (Flask, SQLite, Werkzeug)

Matplotlib (backend Agg para generar PNG en memoria)

NumPy