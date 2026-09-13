import os
import sqlite3
import base64
from datetime import datetime
import cv2
import numpy as np
import csv
import io
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response

app = Flask(__name__)
app.secret_key = "smart-attendance-secret-key"

DATABASE = "attendance.db"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# SFace + YuNet Face Recognition
# ==========================================

SFACE_MODEL_PATH = "face_data/models/face_recognition_sface_2021dec.onnx"
YUNET_MODEL_PATH = "face_data/models/face_detection_yunet_2023mar.onnx"

# Load SFace
sface_recognizer = cv2.FaceRecognizerSF_create(
    SFACE_MODEL_PATH,
    ""
)

# Load YuNet
yunet_detector = cv2.FaceDetectorYN_create(
    YUNET_MODEL_PATH,
    "",
    (320, 320),
    0.9,
    0.3,
    5000
)


def get_face_feature(image_path):
    """
    Detect a face using YuNet and generate
    an SFace feature vector.
    """

    image = cv2.imread(image_path)

    if image is None:
        return None

    height, width = image.shape[:2]

    yunet_detector.setInputSize((width, height))

    _, faces = yunet_detector.detect(image)

    if faces is None:
        return None

    # Select the largest detected face
    face = max(
        faces,
        key=lambda f: f[2] * f[3]
    )

    # Align face using YuNet landmarks
    aligned_face = sface_recognizer.alignCrop(
        image,
        face
    )

    # Generate SFace feature
    feature = sface_recognizer.feature(
        aligned_face
    )

    return feature


def compare_faces_sface(image1_path, image2_path):
    """
    Compare two faces using SFace cosine similarity.
    """

    feature1 = get_face_feature(image1_path)
    feature2 = get_face_feature(image2_path)

    if feature1 is None or feature2 is None:
        return None

    score = sface_recognizer.match(
        feature1,
        feature2,
        cv2.FaceRecognizerSF_FR_COSINE
    )

    return float(score)

# ==========================================
# FACE RECOGNITION SETUP
# ==========================================

FACE_CASCADE_PATH = "face_data/haarcascade_frontalface_default.xml"

face_detector = cv2.CascadeClassifier(FACE_CASCADE_PATH)


def detect_face(image_path):
    """
    Detect the largest face in an image and return
    the grayscale cropped face.
    """

    image = cv2.imread(image_path)

    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    faces = face_detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(100, 100)
    )

    if len(faces) == 0:
        return None

    # Select the largest detected face
    x, y, w, h = max(
        faces,
        key=lambda face: face[2] * face[3]
    )

    face = gray[y:y+h, x:x+w]

    return face

def train_face_recognizer():
    """
    Train LBPH face recognizer using all registered student photos.
    """

    conn = get_db_connection()

    students = conn.execute(
        """
        SELECT id, photo_path
        FROM students
        WHERE photo_path IS NOT NULL
        AND photo_path != ''
        """
    ).fetchall()

    conn.close()

    faces = []
    labels = []

    for student in students:

        photo_path = student["photo_path"]

        if not os.path.exists(photo_path):
            continue

        face = detect_face(photo_path)

        if face is None:
            continue

        face = cv2.resize(face, (200, 200))

        faces.append(face)
        labels.append(student["id"])

    if len(faces) == 0:
        return None

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )

    recognizer.train(
        faces,
        np.array(labels, dtype=np.int32)
    )

    return recognizer

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Added password column for student login
    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            photo_path TEXT NOT NULL
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

def verify_face_opencv(img1_path, img2_path):
    try:
        img1 = cv2.imread(img1_path, cv2.IMREAD_GRAYSCALE)
        img2 = cv2.imread(img2_path, cv2.IMREAD_GRAYSCALE)

        if img1 is None or img2 is None:
            return False

        img1 = cv2.resize(img1, (150, 150))
        img2 = cv2.resize(img2, (150, 150))

        res = cv2.matchTemplate(
            img1,
            img2,
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, _ = cv2.minMaxLoc(res)

        print(
            f"Comparing: {os.path.basename(img1_path)} "
            f"vs {os.path.basename(img2_path)} "
            f"→ Score: {score:.4f}"
        )

        return score > 0.40

    except Exception as e:
        print("Matching error:", e)
        return False

# --- ADMIN AUTHENTICATION ---
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
        return "Invalid Admin Username or Password!"
    return render_template("login.html")

# --- ADMIN MANAGEMENT ---
@app.route("/admin/create", methods=["GET", "POST"])
def create_admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password are required!", "error")
            return redirect(url_for("create_admin"))

        conn = get_db_connection()

        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
            flash("New admin account created successfully!", "success")

        except sqlite3.IntegrityError:
            flash("Username already exists!", "error")

        finally:
            conn.close()

        return redirect(url_for("create_admin"))

    return render_template("create_admin.html")

@app.route("/admin/manage")
def manage_admins():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    admins = conn.execute(
        "SELECT id, username FROM users ORDER BY id ASC"
    ).fetchall()
    conn.close()

    return render_template("manage_admins.html", admins=admins)


@app.route("/admin/delete/<int:admin_id>", methods=["POST"])
def delete_admin(admin_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    admin = conn.execute(
        "SELECT username FROM users WHERE id = ?",
        (admin_id,)
    ).fetchone()

    if not admin:
        conn.close()
        flash("Admin account not found!", "error")
        return redirect(url_for("manage_admins"))

    # Prevent deleting the currently logged-in admin
    if admin["username"] == session.get("username"):
        conn.close()
        flash("You cannot delete the currently logged-in admin!", "error")
        return redirect(url_for("manage_admins"))

    conn.execute(
        "DELETE FROM users WHERE id = ?",
        (admin_id,)
    )
    conn.commit()
    conn.close()

    flash("Admin account deleted successfully!", "success")
    return redirect(url_for("manage_admins"))

# --- STUDENT AUTHENTICATION ---
@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        roll_no = request.form.get("roll_no")
        password = request.form.get("password")

        conn = get_db_connection()

        student = conn.execute(
            "SELECT * FROM students WHERE roll_no = ? AND password = ?",
            (roll_no, password)
        ).fetchone()

        conn.close()

        if student:
            session["student_logged_in"] = True
            session["student_id"] = student["id"]
            session["student_name"] = student["name"]

            return redirect(url_for("student_dashboard"))

        return "Invalid Roll Number or Password!"

    return render_template("student_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# --- ADMIN DASHBOARD ---
@app.route("/")
def home():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    auto_mark_absent()

    conn = get_db_connection()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    present_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.date = DATE('now')
        AND a.status = 'Present'
        """
    ).fetchone()[0]

    absent_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.date = DATE('now')
        AND a.status = 'Absent'
        """
    ).fetchone()[0]

    if total_students > 0:
        attendance_percentage = round(
            (present_today / total_students) * 100, 2
        )
    else:
        attendance_percentage = 0

    conn.close()

    return render_template(
        "index.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        attendance_percentage=attendance_percentage,
        chart_present=present_today,
        chart_absent=absent_today
)

# --- STUDENT DASHBOARD ---
@app.route("/student/dashboard")
def student_dashboard():
    if not session.get("student_logged_in"):
        return redirect(url_for("student_login"))
    
    student_id = session.get("student_id")
    conn = get_db_connection()
    
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    attendance = conn.execute("""
        SELECT date, status FROM attendance 
        WHERE student_id = ? 
        ORDER BY date DESC
    """, (student_id,)).fetchall()
    
    total_days = len(attendance)
    present_days = sum(1 for a in attendance if a["status"] == "Present")
    absent_days = sum(1 for a in attendance if a["status"] == "Absent")
    percentage = (present_days / total_days) * 100 if total_days > 0 else 0
    
    conn.close()
    return render_template(
        "student_dashboard.html",
        student=student,
        attendance=attendance,
        total_days=total_days,
        present_days=present_days,
        absent_days=absent_days,
        percentage=round(percentage, 2)
    )

@app.route("/students", methods=["GET", "POST"])
def students():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        if request.is_json:
            data = request.get_json()

            name = data.get("name")
            roll_no = data.get("roll_no")
            email = data.get("email")
            password = data.get("password")
            image_data = data.get("image")

            if not password:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": "Password is required!"
                })

            if not image_data:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": "Photo is required!"
                })

            temp_path = os.path.join(
                UPLOAD_FOLDER,
                f"temp_register_{roll_no}.jpg"
            )

            try:
                # Decode captured image
                header, encoded = image_data.split(",", 1)
                image_bytes = base64.b64decode(encoded)

                # Save temporarily
                with open(temp_path, "wb") as f:
                    f.write(image_bytes)

                # -----------------------------------
                # CHECK IF NEW PHOTO CONTAINS A FACE
                # -----------------------------------

                new_face_feature = get_face_feature(temp_path)

                if new_face_feature is None:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    conn.close()

                    return jsonify({
                        "success": False,
                        "message": "No face detected. Please position your face clearly in the camera."
                    })

                # -----------------------------------
                # CHECK FOR DUPLICATE FACE USING SFACE
                # -----------------------------------

                existing_students = conn.execute(
                    "SELECT id, name, roll_no, photo_path FROM students"
                ).fetchall()

                SFACE_THRESHOLD = 0.50

                for existing_student in existing_students:

                    existing_photo = existing_student["photo_path"]

                    if not os.path.exists(existing_photo):
                        continue

                    similarity = compare_faces_sface(
                        existing_photo,
                        temp_path
                    )

                    if similarity is None:
                        continue

                    print(
                        f"Comparing {os.path.basename(existing_photo)} "
                        f"with new registration "
                        f"→ SFace similarity: {similarity:.4f}"
                    )

                    if similarity >= SFACE_THRESHOLD:

                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                        conn.close()

                        return jsonify({
                            "success": False,
                            "message": (
                                f"This face is already registered "
                                f"with student {existing_student['name']} "
                                f"(Roll No: {existing_student['roll_no']})."
                            )
                        })

               # -----------------------------------
               # SAVE NEW STUDENT
               # -----------------------------------

                # First insert the student to get the permanent database ID
                conn.execute(
                    """
                    INSERT INTO students
                    (name, roll_no, email, photo_path, password)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        roll_no,
                        email,
                        "",
                        password
                    )
                )

                student_id = conn.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

                # Use permanent student ID for photo filename
                photo_filename = f"student_{student_id}.jpg"

                photo_path = os.path.join(
                    UPLOAD_FOLDER,
                    photo_filename
                )

                # Move temporary image to permanent location
                os.rename(temp_path, photo_path)

                # Store the permanent photo path
                conn.execute(
                    """
                    UPDATE students
                    SET photo_path = ?
                    WHERE id = ?
                    """,
                    (
                        photo_path,
                        student_id
                    )
                )

                conn.commit()

                if os.path.exists(temp_path):
                    os.remove(temp_path)

                conn.close()

                return jsonify({
                    "success": True,
                    "message": "Student registered successfully!"
                })

            except sqlite3.IntegrityError:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                conn.close()

                return jsonify({
                    "success": False,
                    "message": "Roll number already exists!"
                })

            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                conn.close()

                return jsonify({
                    "success": False,
                    "message": f"Error: {str(e)}"
                })

        conn.close()
        return jsonify({
            "success": False,
            "message": "Invalid request!"
        })

    students_list = conn.execute(
        "SELECT * FROM students ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students_list
    )

@app.route("/attendance", methods=["GET"])
def view_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    
    auto_mark_absent()
    selected_date = request.args.get("date")

    conn = get_db_connection()
    if selected_date:
        attendance = conn.execute("""
            SELECT attendance.id, students.name, students.roll_no, attendance.date, attendance.status
            FROM attendance JOIN students ON attendance.student_id = students.id
            WHERE attendance.date = ? ORDER BY students.roll_no
        """, (selected_date,)).fetchall()
    else:
        attendance = conn.execute("""
            SELECT attendance.id, students.name, students.roll_no, attendance.date, attendance.status
            FROM attendance JOIN students ON attendance.student_id = students.id
            ORDER BY attendance.date DESC
        """).fetchall()
    conn.close()
    return render_template("attendance.html", attendance=attendance, selected_date=selected_date)

@app.route("/attendance/mark", methods=["GET", "POST"])
def mark_attendance():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")

    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
            student_id = data.get("student_id")
            image_data = data.get("image")
            
            student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
            if not student:
                conn.close()
                return jsonify({"success": False, "message": "Student not found."})
            
            temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{student_id}.jpg")
            try:
                header, encoded = image_data.split(",", 1)
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(encoded))
                
                similarity = compare_faces_sface(
                    student["photo_path"],
                    temp_path
                )

                SFACE_THRESHOLD = 0.50

                if similarity is None:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    conn.close()

                    return jsonify({
                        "success": False,
                        "message": "No face detected. Please position your face clearly in the camera."
                    })

                is_matched = similarity >= SFACE_THRESHOLD

                print(
                    f"Attendance face similarity for {student['name']}: "
                    f"{similarity:.4f}"
                )
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                if is_matched:
                    try:
                        conn.execute(
                            "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)", 
                            (student_id, today_date, "Present")
                        )
                        conn.commit()
                        conn.close()
                        return jsonify({"success": True, "student_name": student['name'], "roll_no": student['roll_no']})
                    except sqlite3.IntegrityError:
                        conn.close()
                        return jsonify({"success": False, "message": "Attendance already marked for today!"})
                else:
                    conn.close()
                    return jsonify({"success": False, "message": "Face did not match! Attendance rejected."})
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                conn.close()
                return jsonify({"success": False, "message": "Error during face verification!"})

        student_id = request.form.get("student_id")
        if student_id:
            conn.close()
            return redirect(url_for("webcam_scanner", student_id=student_id))

    students_list = conn.execute("SELECT * FROM students").fetchall()
    conn.close()
    return render_template("select_student.html", students=students_list)

@app.route("/attendance/webcam/<int:student_id>")
def webcam_scanner(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    if not student:
        return redirect(url_for("mark_attendance"))
    return render_template("mark_attendance.html", student=student)

@app.route("/attendance/update/<int:attendance_id>", methods=["POST"])
def update_attendance(attendance_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    status = request.form.get("status")
    conn = get_db_connection()
    conn.execute("UPDATE attendance SET status = ? WHERE id = ?", (status, attendance_id))
    conn.commit()
    conn.close()
    return redirect(url_for("view_attendance"))

@app.route("/attendance/delete/<int:attendance_id>", methods=["POST"])
def delete_attendance(attendance_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM attendance WHERE id = ?", (attendance_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("view_attendance"))

@app.route("/attendance/percentage")
def attendance_percentage():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    students = conn.execute("""
        SELECT students.id,
            students.name,
            students.roll_no,
            SUM(CASE WHEN attendance.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
            SUM(CASE WHEN attendance.status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
            COUNT(attendance.id) AS total_days
        FROM students
        LEFT JOIN attendance
            ON students.id = attendance.student_id
        GROUP BY students.id
        ORDER BY students.id
    """).fetchall()

    conn.close()

    result = []

    for student in students:
        total_days = student["total_days"] or 0
        present_days = student["present_days"] or 0
        absent_days = student["absent_days"] or 0

        percentage = (
            (present_days / total_days) * 100
            if total_days > 0
            else 0
        )

        result.append({
            "name": student["name"],
            "roll_no": student["roll_no"],
            "present_days": present_days,
            "absent_days": absent_days,
            "total_days": total_days,
            "percentage": round(percentage, 2)
        })

    # Students with attendance below 75%
    low_attendance = [
        student for student in result
        if student["total_days"] > 0
        and student["percentage"] < 75
    ]

    return render_template(
        "attendance_percentage.html",
        students=result,
        low_attendance=low_attendance
    )

@app.route("/attendance/report/download")
def download_attendance_report():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    selected_date = request.args.get("date")

    conn = get_db_connection()

    if selected_date:
        records = conn.execute(
            """
            SELECT
                s.roll_no,
                s.name,
                a.date,
                a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.date = ?
            ORDER BY s.roll_no
            """,
            (selected_date,)
        ).fetchall()
    else:
        records = conn.execute(
            """
            SELECT
                s.roll_no,
                s.name,
                a.date,
                a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            ORDER BY a.date DESC, s.roll_no
            """
        ).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Roll No",
        "Student Name",
        "Date",
        "Status"
    ])

    for record in records:
        writer.writerow([
            record["roll_no"],
            record["name"],
            record["date"],
            record["status"]
        ])

    output.seek(0)

    filename = (
        f"attendance_report_{selected_date}.csv"
        if selected_date
        else "attendance_report_all.csv"
    )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@app.route("/attendance/report")
def attendance_report():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    selected_date = request.args.get("date")

    conn = get_db_connection()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    if selected_date:
        total_records = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date = ?",
            (selected_date,)
        ).fetchone()[0]

        present_records = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date = ? AND status = 'Present'",
            (selected_date,)
        ).fetchone()[0]

        absent_records = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date = ? AND status = 'Absent'",
            (selected_date,)
        ).fetchone()[0]

    else:
        total_records = conn.execute(
            "SELECT COUNT(*) FROM attendance"
        ).fetchone()[0]

        present_records = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE status = 'Present'"
        ).fetchone()[0]

        absent_records = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE status = 'Absent'"
        ).fetchone()[0]

    conn.close()

    overall_percentage = (
        (present_records / total_records) * 100
        if total_records > 0
        else 0
    )

    return render_template(
        "attendance_report.html",
        total_students=total_students,
        total_records=total_records,
        present_records=present_records,
        absent_records=absent_records,
        overall_percentage=round(overall_percentage, 2),
        selected_date=selected_date
    )

@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    student = conn.execute(
        "SELECT photo_path FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()

    # Delete student's photo
    if student and student["photo_path"] and os.path.exists(student["photo_path"]):
        try:
            os.remove(student["photo_path"])
        except:
            pass

    # Delete attendance records of this student
    conn.execute(
        "DELETE FROM attendance WHERE student_id = ?",
        (student_id,)
    )

    # Delete student
    conn.execute(
        "DELETE FROM students WHERE id = ?",
        (student_id,)
    )

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
            conn.execute("UPDATE students SET name = ?, roll_no = ?, email = ? WHERE id = ?", (name, roll_no, email, student_id))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("Roll number already exists!", "error")
            return redirect(url_for("edit_student", student_id=student_id))
        conn.close()
        flash("Student updated successfully!", "success")
        return redirect(url_for("students"))
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    if student is None:
        return "Student not found!"
    return render_template("edit_student.html", student=student)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)