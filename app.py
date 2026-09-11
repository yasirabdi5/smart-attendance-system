from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
import sqlite3
import base64
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

# Automatic function jo check karega ki kis student ne pichle dino mein attendance nahi lagayi aur use Absent kar dega
def auto_mark_absent():
    conn = get_db_connection()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    dates = conn.execute("SELECT DISTINCT date FROM attendance").fetchall()
    students = conn.execute("SELECT id FROM students").fetchall()
    
    for d in dates:
        date_str = d['date']
        if date_str == today_str:
            continue
            
        for s in students:
            student_id = s['id']
            exists = conn.execute(
                "SELECT 1 FROM attendance WHERE student_id = ? AND date = ?",
                (student_id, date_str)
            ).fetchone()
            
            if not exists:
                try:
                    conn.execute(
                        "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                        (student_id, date_str, "Absent")
                    )
                except sqlite3.IntegrityError:
                    pass
    conn.commit()
    conn.close()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
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
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
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
    
    auto_mark_absent()
    
    conn = get_db_connection()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    
    present_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = DATE('now')
        AND status = 'Present'
        """
    ).fetchone()[0]

    absent_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = DATE('now')
        AND status = 'Absent'
        """
    ).fetchone()[0]

    conn.close()
    return render_template("index.html", total_students=total_students, present_today=present_today, absent_today=absent_today)

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
            conn.execute("INSERT INTO students (name, roll_no, email) VALUES (?, ?, ?)", (name, roll_no, email))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Roll number already exists!"
        conn.close()
        flash("Student added successfully!", "success")
        return redirect(url_for("students"))

    students_list = conn.execute(
        "SELECT * FROM students ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("students.html", students=students_list)

@app.route("/attendance", methods=["GET"])
def view_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    
    auto_mark_absent()
    selected_date = request.args.get("date")

    conn = get_db_connection()

    if selected_date:
        attendance = conn.execute("""
            SELECT
                attendance.id,
                students.name,
                students.roll_no,
                attendance.date,
                attendance.status
            FROM attendance
            JOIN students
            ON attendance.student_id = students.id
            WHERE attendance.date = ?
            ORDER BY students.roll_no
        """, (selected_date,)).fetchall()
    else:
        attendance = conn.execute("""
            SELECT
                attendance.id,
                students.name,
                students.roll_no,
                attendance.date,
                attendance.status
            FROM attendance
            JOIN students
            ON attendance.student_id = students.id
            ORDER BY attendance.date DESC
        """).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        attendance=attendance,
        selected_date=selected_date
    )

@app.route("/attendance/mark", methods=["GET", "POST"])
def mark_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")

    if request.method == "POST":
        student_id = request.form.get("student_id")
        status = request.form.get("status", "Present")
        
        if student_id:
            try:
                conn.execute(
                    "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                    (student_id, today_date, status)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return "Attendance already marked for this student today!"
        
        conn.close()
        return redirect(url_for("view_attendance"))

    students_list = conn.execute("SELECT * FROM students").fetchall()
    conn.close()

    return render_template(
        "mark_attendance.html",
        students=students_list
    )

@app.route("/attendance/update/<int:attendance_id>", methods=["POST"])
def update_attendance(attendance_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    status = request.form.get("status")
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE attendance
        SET status = ?
        WHERE id = ?
        """,
        (status, attendance_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("view_attendance"))

@app.route("/attendance/delete/<int:attendance_id>", methods=["POST"])
def delete_attendance(attendance_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute(
        "DELETE FROM attendance WHERE id = ?",
        (attendance_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("view_attendance"))

@app.route("/attendance/percentage")
def attendance_percentage():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    students = conn.execute("""
       SELECT
            students.id,
            students.name,
            students.roll_no,
            SUM(CASE WHEN attendance.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
            SUM(CASE WHEN attendance.status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
            COUNT(attendance.id) AS total_days
        FROM students
        LEFT JOIN attendance ON students.id = attendance.student_id
        GROUP BY students.id
        ORDER BY students.id
    """).fetchall()
    conn.close()

    result = []
    for student in students:
        total_days = student["total_days"]
        present_days = student["present_days"] or 0
        percentage = (present_days / total_days) * 100 if total_days > 0 else 0

        result.append({
            "name": student["name"],
            "roll_no": student["roll_no"],
            "present_days": present_days,
            "absent_days": student["absent_days"] or 0,
            "total_days": total_days,
            "percentage": round(percentage, 2)
        })

    return render_template(
        "attendance_percentage.html",
        students=result
    )

@app.route("/attendance/report")
def attendance_report():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    total_records = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    present_records = conn.execute("SELECT COUNT(*) FROM attendance WHERE status = 'Present'").fetchone()[0]
    absent_records = conn.execute("SELECT COUNT(*) FROM attendance WHERE status = 'Absent'").fetchone()[0]
    conn.close()

    overall_percentage = (present_records / total_records) * 100 if total_records > 0 else 0

    return render_template(
        "attendance_report.html",
        total_students=total_students,
        total_records=total_records,
        present_records=present_records,
        absent_records=absent_records,
        overall_percentage=round(overall_percentage, 2)
    )

@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()
    flash("Student deleted successfully!", "success")
    return redirect(url_for("students"))

@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    if request.method == "POST":
        name = request.form["name"]
        roll_no = request.form["roll_no"]
        email = request.form["email"]

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
            flash("Roll number already exists!", "error")
            return redirect(url_for("edit_student", student_id=student_id))

        conn.close()
        flash("Student updated successfully!", "success")
        return redirect(url_for("students"))

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()
    conn.close()

    if student is None:
        return "Student not found!"

    return render_template(
        "edit_student.html",
        student=student
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)