from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3

app = Flask(__name__)

app.secret_key = "smart-attendance-secret-key"

DATABASE = "attendance.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "admin123":
            session["admin_logged_in"] = True
            return redirect(url_for("home"))

        return "Invalid username or password!"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("login"))

@app.route("/")
def home():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_students=total_students
    )

@app.route("/students", methods=["GET", "POST"])
def students():

    conn=get_db_connection()

    if request.method == "POST":

        name = request.form["name"]
        roll_no = request.form["roll_no"]
        email = request.form["email"]


        try:
            conn.execute(
                "INSERT INTO students (name, roll_no, email) VALUES (?, ?, ?)",
                (name, roll_no, email)
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.close()
            return "Roll number already exists!"

        conn.close()

        return "Student added successfully!"
    students = conn.execute(
        "SELECT * FROM students ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template("students.html",students=students)

@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM students WHERE id = ?",
        (student_id,)
    )

    conn.commit()
    conn.close()

    return "Student deleted successfully!"


if __name__ == "__main__":
    init_db()
    app.run(debug=True)