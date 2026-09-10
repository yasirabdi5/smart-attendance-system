from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3
from datetime import datetime

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
UNIQUE(student_id, date),
FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "User already exists! Try a different username."

        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "admin123":
            session["admin_logged_in"] = True
            session["username"] = username
            return redirect(url_for("home"))

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["admin_logged_in"] = True
            session["username"] = username
            return redirect(url_for("home"))

        return "Invalid Username or Password!"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def home():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    # Total number of students
    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    # Number of students present today
    present_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = DATE('now')
        AND status = 'Present'
        """
    ).fetchone()[0]

    # Number of students absent today
    absent_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = DATE('now')
        AND status = 'Absent'
        """
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today
    )

@app.route("/students", methods=["GET", "POST"])
def students():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

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

    return render_template("students.html", students=students)

@app.route("/attendance", methods=["GET"])
def view_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    
    
    records = conn.execute("""
        SELECT students.name, students.roll_no, attendance.date, attendance.status 
        FROM attendance 
        JOIN students ON attendance.student_id = students.id 
        ORDER BY attendance.id DESC
    """).fetchall()    
    conn.close()

    return render_template("attendance.html", records=records)

@app.route("/attendance/mark", methods=["GET", "POST"])
def mark_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        date = request.form.get("date")
        status = request.form.get("status")

        conn.execute(
            "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
            (student_id, date, status)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for("view_attendance"))

    students_list = conn.execute("SELECT * FROM students").fetchall()
    conn.close()
    
    return render_template("mark_attendance.html", students=students_list)

@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()

    return "Student deleted successfully!"

@app.route("/students/edit/<int:student_id>", methods=["POST"])
def edit_student(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    name = request.form["name"]
    roll_no = request.form["roll_no"]
    email = request.form["email"]

    conn = get_db_connection()
    try:
        conn.execute(
            """
            UPDATE students
            SET name = ?, roll_no = ?, email = ?
            WHERE id = ?
            """,
            (name, roll_no, email, student_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "Roll number already exists!"

    conn.close()

    return "Student updated successfully!"


if __name__ == "__main__":
    init_db()
    app.run(debug=True)