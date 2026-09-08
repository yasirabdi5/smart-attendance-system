from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

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


@app.route("/")
def home():
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

    if request.method == "POST":

        name = request.form["name"]
        roll_no = request.form["roll_no"]
        email = request.form["email"]

        conn = get_db_connection()

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

    return render_template("students.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)