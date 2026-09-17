
import os
import sqlite3
import base64
from datetime import datetime
import cv2
import numpy as np
import csv
import io
from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    jsonify,
    flash,
    Response
)

app = Flask(__name__)
app.secret_key = "smart-attendance-secret-key"

DATABASE = "attendance.db"
UPLOAD_FOLDER = "static/uploads"
def get_current_meal():
    now = datetime.now().strftime("%H:%M")

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    meal = connection.execute(
        """
        SELECT meal_name
        FROM meal_config
        WHERE is_active = 1
        AND start_time <= ?
        AND end_time >= ?
        LIMIT 1
        """,
        (now, now)
    ).fetchone()

    connection.close()

    if meal:
        return meal["meal_name"]

    return None

def mark_mess_attendance(student_id):
    meal = get_current_meal()

    if meal is None:
        return False, "No meal is currently active."

    today = datetime.now().strftime("%Y-%m-%d")
    entry_time = datetime.now().strftime("%H:%M:%S")

    connection = sqlite3.connect(DATABASE)

    existing = connection.execute(
        """
        SELECT id
        FROM mess_attendance
        WHERE student_id = ?
        AND date = ?
        AND meal = ?
        """,
        (student_id, today, meal)
    ).fetchone()

    if existing:
        connection.close()
        return False, f"{meal} already marked."

    connection.execute(
        """
        INSERT INTO mess_attendance
        (student_id, date, meal, entry_time, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (student_id, today, meal, entry_time, "Consumed")
    )

    connection.commit()
    connection.close()

    return True, {
        "meal": meal,
        "entry_time": entry_time,
        "status": "Consumed"
    }

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SFACE_MODEL_PATH = (
    "face_data/models/face_recognition_sface_2021dec.onnx"
)

YUNET_MODEL_PATH = (
    "face_data/models/face_detection_yunet_2023mar.onnx"
)


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


def recognize_student_from_face(image_path, students):
    """
    Compare the captured face against all registered students
    and return the best matching student.
    """

    SFACE_THRESHOLD = 0.50

    best_student = None
    best_similarity = -1

    for student in students:

        photo_path = student["photo_path"]

        if not photo_path:
            continue

        if not os.path.exists(photo_path):
            continue

        similarity = compare_faces_sface(
            photo_path,
            image_path
        )

        if similarity is None:
            continue

        print(
            f"Comparing with {student['name']} "
            f"({student['roll_no']}) "
            f"→ similarity: {similarity:.4f}"
        )

        if similarity > best_similarity:
            best_similarity = similarity
            best_student = student

    if (
        best_student is not None
        and best_similarity >= SFACE_THRESHOLD
    ):
        return best_student, best_similarity

    return None, best_similarity


# ==========================================
# FACE RECOGNITION SETUP


FACE_CASCADE_PATH = (
    "face_data/haarcascade_frontalface_default.xml"
)

face_detector = cv2.CascadeClassifier(
    FACE_CASCADE_PATH
)


def detect_face(image_path):
    """
    Detect the largest face in an image and return
    the grayscale cropped face.
    """

    image = cv2.imread(image_path)

    if image is None:
        return None

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

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

    face = gray[
        y:y + h,
        x:x + w
    ]

    return face


def train_face_recognizer():
    """
    Train LBPH face recognizer using all registered
    student photos.
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

        face = cv2.resize(
            face,
            (200, 200)
        )

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
        np.array(
            labels,
            dtype=np.int32
        )
    )

    return recognizer


# ==========================================
# DATABASE
# ==========================================

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db_connection()

    # --------------------------------------
    # Students table
    # --------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            photo_path TEXT NOT NULL,
            password TEXT
        )
        """
    )

    # Keep existing attendance databases compatible
    # with student login.

    columns = conn.execute(
        "PRAGMA table_info(students)"
    ).fetchall()

    if not any(
        column["name"] == "password"
        for column in columns
    ):
        conn.execute(
            "ALTER TABLE students ADD COLUMN password TEXT"
        )

    # --------------------------------------
    # Admin users table
    # --------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )

    # --------------------------------------
    # Attendance table
    # --------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE(student_id, date),
            FOREIGN KEY (student_id)
                REFERENCES students(id)
        )
        """
    )

    conn.commit()
    conn.close()


# ==========================================
# DAILY ATTENDANCE
# ==========================================

def ensure_attendance_for_date(date_str):
    """
    Ensure every registered student has one attendance
    record for the given date.

    Existing Present/Absent records are not overwritten.
    Missing records are created as Absent.
    """

    conn = get_db_connection()

    students = conn.execute(
        "SELECT id FROM students"
    ).fetchall()

    for student in students:

        conn.execute(
            """
            INSERT OR IGNORE INTO attendance
            (student_id, date, status)
            VALUES (?, ?, ?)
            """,
            (
                student["id"],
                date_str,
                "Absent"
            )
        )

    conn.commit()
    conn.close()


def auto_mark_absent():

    today_str = datetime.now().strftime(
        "%Y-%m-%d"
    )

    ensure_attendance_for_date(
        today_str
    )


# ==========================================
# OLD OPENCV FACE VERIFICATION
# ==========================================

def verify_face_opencv(img1_path, img2_path):

    try:

        img1 = cv2.imread(
            img1_path,
            cv2.IMREAD_GRAYSCALE
        )

        img2 = cv2.imread(
            img2_path,
            cv2.IMREAD_GRAYSCALE
        )

        if img1 is None or img2 is None:
            return False

        img1 = cv2.resize(
            img1,
            (150, 150)
        )

        img2 = cv2.resize(
            img2,
            (150, 150)
        )

        res = cv2.matchTemplate(
            img1,
            img2,
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, _ = cv2.minMaxLoc(
            res
        )

        print(
            f"Comparing: "
            f"{os.path.basename(img1_path)} "
            f"vs "
            f"{os.path.basename(img2_path)} "
            f"→ Score: {score:.4f}"
        )

        return score > 0.40

    except Exception as e:

        print(
            "Matching error:",
            e
        )

        return False


# ==========================================
# MAIN LOGIN PAGE
# ==========================================

@app.route(
    "/login",
    methods=["GET"]
)
def login_page():

    return render_template(
        "login.html"
    )


# ==========================================
# ADMIN LOGIN
# ==========================================

@app.route(
    "/admin/login",
    methods=["POST"]
)
def admin_login():

    username = request.form.get(
        "username"
    )

    password = request.form.get(
        "password"
    )

    if (
        username == "admin"
        and password == "password123"
    ):

        session["admin_logged_in"] = True
        session["username"] = username

        session.pop(
            "student_logged_in",
            None
        )

        session.pop(
            "student_id",
            None
        )

        session.pop(
            "student_name",
            None
        )

        return redirect(
            url_for("home")
        )

    else:

        return render_template(
            "login.html",
            admin_error=(
                "Invalid Admin Username "
                "or Password!"
            )
        )


# ==========================================
# STUDENT LOGIN
# ==========================================

@app.route(
    "/student/login",
    methods=["POST"]
)
def student_login():

    student_id = request.form.get(
        "student_id"
    )

    password = request.form.get(
        "password"
    )

    conn = get_db_connection()

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        AND password = ?
        """,
        (
            student_id,
            password
        )
    ).fetchone()

    conn.close()

    if student:

        session["student_logged_in"] = True
        session["student_id"] = student["id"]
        session["student_name"] = student["name"]

        session.pop(
            "admin_logged_in",
            None
        )

        session.pop(
            "username",
            None
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    else:

        return render_template(
            "login.html",
            student_error=(
                "Invalid Student ID "
                "or Credentials!"
            )
        )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login_page")
    )


# ==========================================
# ADMIN MANAGEMENT
# ==========================================

@app.route(
    "/admin/create",
    methods=["GET", "POST"]
)
def create_admin():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    if request.method == "POST":

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
        )

        if not username or not password:

            flash(
                "Username and password are required!",
                "error"
            )

            return redirect(
                url_for("create_admin")
            )

        conn = get_db_connection()

        try:

            conn.execute(
                """
                INSERT INTO users
                (username, password)
                VALUES (?, ?)
                """,
                (
                    username,
                    password
                )
            )

            conn.commit()

            flash(
                "New admin account created successfully!",
                "success"
            )

        except sqlite3.IntegrityError:

            flash(
                "Username already exists!",
                "error"
            )

        finally:

            conn.close()

        return redirect(
            url_for("create_admin")
        )

    return render_template(
        "create_admin.html"
    )


@app.route("/admin/manage")
def manage_admins():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    admins = conn.execute(
        """
        SELECT id, username
        FROM users
        ORDER BY id ASC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "manage_admins.html",
        admins=admins
    )


@app.route(
    "/admin/delete/<int:admin_id>",
    methods=["POST"]
)
def delete_admin(admin_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    admin = conn.execute(
        """
        SELECT username
        FROM users
        WHERE id = ?
        """,
        (admin_id,)
    ).fetchone()

    if not admin:

        conn.close()

        flash(
            "Admin account not found!",
            "error"
        )

        return redirect(
            url_for("manage_admins")
        )

    # Prevent deleting currently logged-in admin
    if admin["username"] == session.get(
        "username"
    ):

        conn.close()

        flash(
            "You cannot delete the currently "
            "logged-in admin!",
            "error"
        )

        return redirect(
            url_for("manage_admins")
        )

    conn.execute(
        """
        DELETE FROM users
        WHERE id = ?
        """,
        (admin_id,)
    )

    conn.commit()
    conn.close()

    flash(
        "Admin account deleted successfully!",
        "success"
    )

    return redirect(
        url_for("manage_admins")
    )


# ==========================================
# ADMIN DASHBOARD
# ==========================================

@app.route("/")
def home():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    # Automatically create Absent records
    # for today's date.
    auto_mark_absent()

    today_str = datetime.now().strftime(
        "%Y-%m-%d"
    )

    conn = get_db_connection()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    present_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance a
        JOIN students s
            ON a.student_id = s.id
        WHERE a.date = ?
        AND a.status = 'Present'
        """,
        (today_str,)
    ).fetchone()[0]

    absent_today = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance a
        JOIN students s
            ON a.student_id = s.id
        WHERE a.date = ?
        AND a.status = 'Absent'
        """,
        (today_str,)
    ).fetchone()[0]

    if total_students > 0:

        attendance_percentage = round(
            (
                present_today
                / total_students
            ) * 100,
            2
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


# ==========================================
# STUDENT DASHBOARD
# ==========================================

@app.route("/student/dashboard")
def student_dashboard():

    if not session.get(
        "student_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    student_id = session.get(
        "student_id"
    )

    conn = get_db_connection()

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    attendance = conn.execute(
        """
        SELECT date, status
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC
        """,
        (student_id,)
    ).fetchall()

    total_days = len(
        attendance
    )

    present_days = sum(
        1
        for a in attendance
        if a["status"] == "Present"
    )

    absent_days = sum(
        1
        for a in attendance
        if a["status"] == "Absent"
    )

    percentage = (
        (present_days / total_days) * 100
        if total_days > 0
        else 0
    )

    conn.close()

    return render_template(
        "student_dashboard.html",
        student=student,
        attendance=attendance,
        total_days=total_days,
        present_days=present_days,
        absent_days=absent_days,
        percentage=round(
            percentage,
            2
        )
    )


# ==========================================
# STUDENT MANAGEMENT / REGISTRATION
# ==========================================

@app.route(
    "/students",
    methods=["GET", "POST"]
)
def students():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    if request.method == "POST":

        if request.is_json:

            data = request.get_json()

            name = data.get(
                "name"
            )

            roll_no = data.get(
                "roll_no"
            )

            email = data.get(
                "email"
            )

            password = data.get(
                "password"
            )

            image_data = data.get(
                "image"
            )

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

                # -----------------------------------
                # Decode captured image
                # -----------------------------------

                header, encoded = (
                    image_data.split(",", 1)
                )

                image_bytes = base64.b64decode(
                    encoded
                )

                # Save temporarily
                with open(
                    temp_path,
                    "wb"
                ) as f:

                    f.write(
                        image_bytes
                    )

                # -----------------------------------
                # CHECK IF NEW PHOTO CONTAINS A FACE
                # -----------------------------------

                new_face_feature = get_face_feature(
                    temp_path
                )

                if new_face_feature is None:

                    if os.path.exists(
                        temp_path
                    ):
                        os.remove(
                            temp_path
                        )

                    conn.close()

                    return jsonify({
                        "success": False,
                        "message": (
                            "No face detected. "
                            "Please position your face "
                            "clearly in the camera."
                        )
                    })

                # -----------------------------------
                # CHECK DUPLICATE FACE USING SFACE
                # -----------------------------------

                existing_students = conn.execute(
                    """
                    SELECT id, name, roll_no, photo_path
                    FROM students
                    """
                ).fetchall()

                SFACE_THRESHOLD = 0.50

                for existing_student in (
                    existing_students
                ):

                    existing_photo = (
                        existing_student["photo_path"]
                    )

                    if not os.path.exists(
                        existing_photo
                    ):
                        continue

                    similarity = compare_faces_sface(
                        existing_photo,
                        temp_path
                    )

                    if similarity is None:
                        continue

                    print(
                        f"Comparing "
                        f"{os.path.basename(existing_photo)} "
                        f"with new registration "
                        f"→ SFace similarity: "
                        f"{similarity:.4f}"
                    )

                    if similarity >= SFACE_THRESHOLD:

                        if os.path.exists(
                            temp_path
                        ):
                            os.remove(
                                temp_path
                            )

                        conn.close()

                        return jsonify({
                            "success": False,
                            "message": (
                                f"This face is already "
                                f"registered with student "
                                f"{existing_student['name']} "
                                f"(Roll No: "
                                f"{existing_student['roll_no']})."
                            )
                        })

                # -----------------------------------
                # SAVE NEW STUDENT
                # -----------------------------------

                # First insert student to get
                # permanent database ID.

                conn.execute(
                    """
                    INSERT INTO students
                    (
                        name,
                        roll_no,
                        email,
                        photo_path,
                        password
                    )
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

                # Use permanent student ID
                # for photo filename.

                photo_filename = (
                    f"student_{student_id}.jpg"
                )

                photo_path = os.path.join(
                    UPLOAD_FOLDER,
                    photo_filename
                )

                # Move temporary image
                # to permanent location.

                os.rename(
                    temp_path,
                    photo_path
                )

                # Store permanent photo path.

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

                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )

                conn.close()

                return jsonify({
                    "success": True,
                    "message": (
                        "Student registered successfully!"
                    )
                })

            except sqlite3.IntegrityError:

                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )

                conn.close()

                return jsonify({
                    "success": False,
                    "message": (
                        "Roll number already exists!"
                    )
                })

            except Exception as e:

                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )

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
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students_list
    )


# ==========================================
# VIEW ATTENDANCE
# ==========================================

@app.route(
    "/attendance",
    methods=["GET"]
)
def view_attendance():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    today_str = datetime.now().strftime(
        "%Y-%m-%d"
    )

    selected_date = (
        request.args.get("date")
        or today_str
    )

    # Ensure attendance records exist
    # for dates up to today.

    if selected_date <= today_str:

        ensure_attendance_for_date(
            selected_date
        )

    conn = get_db_connection()

    attendance = conn.execute(
        """
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
        """,
        (selected_date,)
    ).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        attendance=attendance,
        selected_date=selected_date
    )


# ==========================================
# CONTINUOUS AUTOMATIC FACE ATTENDANCE
# ==========================================

@app.route(
    "/attendance/mark",
    methods=["GET", "POST"]
)
def mark_attendance():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    today_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    # ======================================
    # POST - CAMERA SCAN
    # ======================================

    if request.method == "POST":

        if request.is_json:

            data = request.get_json()

            image_data = data.get(
                "image"
            )

            if not image_data:

                conn.close()

                return jsonify({
                    "success": False,
                    "message": "No image received."
                })

            temp_path = os.path.join(
                UPLOAD_FOLDER,
                "temp_attendance.jpg"
            )

            try:

                # ----------------------------------
                # Decode captured image
                # ----------------------------------

                header, encoded = (
                    image_data.split(",", 1)
                )

                image_bytes = base64.b64decode(
                    encoded
                )

                with open(
                    temp_path,
                    "wb"
                ) as f:

                    f.write(
                        image_bytes
                    )

                # ----------------------------------
                # Get all registered students
                # ----------------------------------

                students_list = conn.execute(
                    """
                    SELECT *
                    FROM students
                    """
                ).fetchall()

                # ----------------------------------
                # Automatically recognize student
                # ----------------------------------

                student, similarity = (
                    recognize_student_from_face(
                        temp_path,
                        students_list
                    )
                )

                # Remove temporary image
                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )

                # ----------------------------------
                # Face not recognized
                # ----------------------------------

                if student is None:

                    conn.close()

                    return jsonify({
                        "success": False,
                        "message": (
                            "Face not recognized. "
                            "Please look at the camera."
                        )
                    })

                print(
                    f"Recognized student: "
                    f"{student['name']} "
                    f"({student['roll_no']}) "
                    f"→ similarity: "
                    f"{similarity:.4f}"
                )

                # ----------------------------------
                # Check today's existing attendance
                # ----------------------------------

                existing = conn.execute(
                    """
                    SELECT status
                    FROM attendance
                    WHERE student_id = ?
                    AND date = ?
                    """,
                    (
                        student["id"],
                        today_date
                    )
                ).fetchone()

                # ----------------------------------
                # Already Present
                # ----------------------------------

                if (
                    existing
                    and existing["status"] == "Present"
                ):

                    conn.close()

                    return jsonify({
                        "success": False,
                        "message": (
                            f"Attendance already marked "
                            f"today for "
                            f"{student['name']}."
                        )
                    })

                # ----------------------------------
                # Mark Present
                #
                # If today's record is already Absent,
                # change it to Present.
                # ----------------------------------

                conn.execute(
                    """
                    INSERT INTO attendance
                    (
                        student_id,
                        date,
                        status
                    )
                    VALUES (?, ?, ?)

                    ON CONFLICT(student_id, date)
                    DO UPDATE SET status = 'Present'
                    """,
                    (
                        student["id"],
                        today_date,
                        "Present"
                    )
                )

                conn.commit()
                conn.close()

                return jsonify({
                    "success": True,
                    "student_name": student["name"],
                    "roll_no": student["roll_no"],
                    "similarity": round(
                        similarity,
                        4
                    )
                })

            except Exception as e:

                print(
                    "Attendance recognition error:",
                    e
                )

                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )

                conn.close()

                return jsonify({
                    "success": False,
                    "message": (
                        "Error during face recognition."
                    )
                })

        # --------------------------------------
        # Invalid POST request
        # --------------------------------------

        conn.close()

        return jsonify({
            "success": False,
            "message": "Invalid attendance request."
        })

    # ======================================
    # GET - OPEN AUTOMATIC ATTENDANCE CAMERA
    # ======================================

    conn.close()

    return render_template(
        "mark_attendance.html"
    )


# ==========================================
# OLD WEBCAM ROUTE
# ==========================================
#
# Kept for compatibility with any existing
# links/templates. The new system does not
# require student selection.
#

@app.route(
    "/attendance/webcam/<int:student_id>"
)
def webcam_scanner(student_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    conn.close()

    if not student:

        return redirect(
            url_for("mark_attendance")
        )

    # The new automatic attendance system
    # does not need a selected student.

    return render_template(
        "mark_attendance.html"
    )


# ==========================================
# UPDATE ATTENDANCE
# ==========================================

@app.route(
    "/attendance/update/<int:attendance_id>",
    methods=["POST"]
)
def update_attendance(attendance_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    status = request.form.get(
        "status"
    )

    conn = get_db_connection()

    conn.execute(
        """
        UPDATE attendance
        SET status = ?
        WHERE id = ?
        """,
        (
            status,
            attendance_id
        )
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("view_attendance")
    )


# ==========================================
# DELETE ATTENDANCE
# ==========================================

@app.route(
    "/attendance/delete/<int:attendance_id>",
    methods=["POST"]
)
def delete_attendance(attendance_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    conn.execute(
        """
        DELETE FROM attendance
        WHERE id = ?
        """,
        (attendance_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("view_attendance")
    )


# ==========================================
# ATTENDANCE PERCENTAGE
# ==========================================

@app.route(
    "/attendance/percentage"
)
def attendance_percentage():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    students = conn.execute(
        """
        SELECT
            students.id,
            students.name,
            students.roll_no,

            SUM(
                CASE
                    WHEN attendance.status = 'Present'
                    THEN 1
                    ELSE 0
                END
            ) AS present_days,

            SUM(
                CASE
                    WHEN attendance.status = 'Absent'
                    THEN 1
                    ELSE 0
                END
            ) AS absent_days,

            COUNT(attendance.id) AS total_days

        FROM students

        LEFT JOIN attendance
            ON students.id = attendance.student_id

        GROUP BY students.id

        ORDER BY students.id
        """
    ).fetchall()

    conn.close()

    result = []

    for student in students:

        total_days = (
            student["total_days"]
            or 0
        )

        present_days = (
            student["present_days"]
            or 0
        )

        absent_days = (
            student["absent_days"]
            or 0
        )

        percentage = (
            (
                present_days
                / total_days
            ) * 100
            if total_days > 0
            else 0
        )

        result.append({
            "name": student["name"],
            "roll_no": student["roll_no"],
            "present_days": present_days,
            "absent_days": absent_days,
            "total_days": total_days,
            "percentage": round(
                percentage,
                2
            )
        })

    # Students with attendance below 75%

    low_attendance = [
        student
        for student in result
        if (
            student["total_days"] > 0
            and student["percentage"] < 75
        )
    ]

    return render_template(
        "attendance_percentage.html",
        students=result,
        low_attendance=low_attendance
    )


# ==========================================
# DOWNLOAD ATTENDANCE REPORT
# ==========================================

@app.route(
    "/attendance/report/download"
)
def download_attendance_report():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    selected_date = request.args.get(
        "date"
    )

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

            JOIN students s
                ON a.student_id = s.id

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

            JOIN students s
                ON a.student_id = s.id

            ORDER BY
                a.date DESC,
                s.roll_no
            """
        ).fetchall()

    conn.close()

    output = io.StringIO()

    writer = csv.writer(
        output
    )

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
            "Content-Disposition":
                f"attachment; filename={filename}"
        }
    )


# ==========================================
# ATTENDANCE REPORT
# ==========================================

@app.route(
    "/attendance/report"
)
def attendance_report():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    selected_date = request.args.get(
        "date"
    )

    conn = get_db_connection()

    total_students = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

    if selected_date:

        total_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ?
            """,
            (selected_date,)
        ).fetchone()[0]

        present_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ?
            AND status = 'Present'
            """,
            (selected_date,)
        ).fetchone()[0]

        absent_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ?
            AND status = 'Absent'
            """,
            (selected_date,)
        ).fetchone()[0]

    else:

        total_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            """
        ).fetchone()[0]

        present_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE status = 'Present'
            """
        ).fetchone()[0]

        absent_records = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE status = 'Absent'
            """
        ).fetchone()[0]

    conn.close()

    overall_percentage = (
        (
            present_records
            / total_records
        ) * 100
        if total_records > 0
        else 0
    )

    return render_template(
        "attendance_report.html",
        total_students=total_students,
        total_records=total_records,
        present_records=present_records,
        absent_records=absent_records,
        overall_percentage=round(
            overall_percentage,
            2
        ),
        selected_date=selected_date
    )


# ==========================================
# DELETE STUDENT
# ==========================================

@app.route(
    "/students/delete/<int:student_id>",
    methods=["POST"]
)
def delete_student(student_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    student = conn.execute(
        """
        SELECT photo_path
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    # Delete student's photo

    if (
        student
        and student["photo_path"]
        and os.path.exists(
            student["photo_path"]
        )
    ):

        try:

            os.remove(
                student["photo_path"]
            )

        except:

            pass

    # Delete attendance records
    # of this student.

    conn.execute(
        """
        DELETE FROM attendance
        WHERE student_id = ?
        """,
        (student_id,)
    )

    # Delete student.

    conn.execute(
        """
        DELETE FROM students
        WHERE id = ?
        """,
        (student_id,)
    )

    conn.commit()
    conn.close()

    flash(
        "Student deleted successfully!",
        "success"
    )

    return redirect(
        url_for("students")
    )


# ==========================================
# EDIT STUDENT
# ==========================================

@app.route(
    "/students/edit/<int:student_id>",
    methods=["GET", "POST"]
)
def edit_student(student_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("login_page")
        )

    conn = get_db_connection()

    if request.method == "POST":

        name = request.form["name"]

        roll_no = request.form[
            "roll_no"
        ]

        email = request.form[
            "email"
        ]

        try:

            conn.execute(
                """
                UPDATE students
                SET
                    name = ?,
                    roll_no = ?,
                    email = ?
                WHERE id = ?
                """,
                (
                    name,
                    roll_no,
                    email,
                    student_id
                )
            )

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            flash(
                "Roll number already exists!",
                "error"
            )

            return redirect(
                url_for(
                    "edit_student",
                    student_id=student_id
                )
            )

        conn.close()

        flash(
            "Student updated successfully!",
            "success"
        )

        return redirect(
            url_for("students")
        )

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    conn.close()

    if student is None:

        return "Student not found!"

    return render_template(
        "edit_student.html",
        student=student
    )

# ==========================================
# ADVANCED ATTENDANCE CHATBOT
# ==========================================

@app.route("/chatbot", methods=["POST"])
def chatbot():

    if not session.get("admin_logged_in"):
        return jsonify({
            "success": False,
            "message": "Please login as administrator."
        }), 401

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({
            "success": False,
            "message": "Please enter a command."
        })

    query = message.lower()

    conn = get_db_connection()

    # ------------------------------------------
    # ALL STUDENTS
    # ------------------------------------------

    if (
        "all students" in query
        or "sabhi students" in query
        or "saare students" in query
        or "students dikhao" in query
    ):

        students = conn.execute("""
            SELECT id, name, roll_no, email
            FROM students
            ORDER BY name
        """).fetchall()

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_list",
            "message": "Here are all registered students.",
            "students": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "roll_no": s["roll_no"],
                    "email": s["email"]
                }
                for s in students
            ]
        })

    # ------------------------------------------
    # TODAY'S ABSENT
    # ------------------------------------------

    if (
        "today's absent" in query
        or "todays absent" in query
        or "aaj kaun absent" in query
        or "aaj absent" in query
    ):

        today = datetime.now().strftime("%Y-%m-%d")
        ensure_attendance_for_date(today)

        students = conn.execute("""
            SELECT s.name, s.roll_no
            FROM students s
            JOIN attendance a
                ON s.id = a.student_id
            WHERE a.date = ?
            AND a.status = 'Absent'
            ORDER BY s.roll_no
        """, (today,)).fetchall()

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_list",
            "message": f"Absent students today: {len(students)}",
            "students": [
                {
                    "name": s["name"],
                    "roll_no": s["roll_no"]
                }
                for s in students
            ]
        })

    # ------------------------------------------
    # TODAY'S PRESENT
    # ------------------------------------------

    if (
        "today's present" in query
        or "todays present" in query
        or "aaj kaun present" in query
        or "aaj present" in query
    ):

        today = datetime.now().strftime("%Y-%m-%d")
        ensure_attendance_for_date(today)

        students = conn.execute("""
            SELECT s.name, s.roll_no
            FROM students s
            JOIN attendance a
                ON s.id = a.student_id
            WHERE a.date = ?
            AND a.status = 'Present'
            ORDER BY s.roll_no
        """, (today,)).fetchall()

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_list",
            "message": f"Present students today: {len(students)}",
            "students": [
                {
                    "name": s["name"],
                    "roll_no": s["roll_no"]
                }
                for s in students
            ]
        })

        # ------------------------------------------
    # LOW ATTENDANCE STUDENTS
    # ------------------------------------------

    if (
        "low attendance" in query
        or "low attendance students" in query
        or "kam attendance" in query
        or "kam attendance wale" in query
        or "75 percent se kam" in query
        or "75% se kam" in query
    ):

        students = conn.execute("""
            SELECT
                s.name,
                s.roll_no,
                COUNT(a.id) AS total_days,
                SUM(
                    CASE
                        WHEN a.status = 'Present' THEN 1
                        ELSE 0
                    END
                ) AS present_days
            FROM students s
            LEFT JOIN attendance a
                ON s.id = a.student_id
            GROUP BY s.id
            ORDER BY s.roll_no
        """).fetchall()

        low_students = []

        for s in students:

            total_days = s["total_days"] or 0
            present_days = s["present_days"] or 0

            percentage = (
                (present_days / total_days) * 100
                if total_days > 0
                else 0
            )

            if total_days > 0 and percentage < 75:
                low_students.append({
                    "name": s["name"],
                    "roll_no": s["roll_no"],
                    "percentage": round(percentage, 2)
                })

        conn.close()

        return jsonify({
            "success": True,
            "type": "low_attendance",
            "message": f"Students with attendance below 75%: {len(low_students)}",
            "students": low_students
        })

# ------------------------------------------
    # SEARCH STUDENT BY ROLL NUMBER
    # ------------------------------------------

    import re

    roll_match = re.search(
        r"(?:student\s*|roll\s*(?:no|number)?|roll)\s*[:#-]?\s*(\d+)",
        query
    )
    

    student = None

    if roll_match:

        roll_no = roll_match.group(1)

        student = conn.execute("""
            SELECT *
            FROM students
            WHERE roll_no = ?
        """, (roll_no,)).fetchone()

    # ------------------------------------------
    # SEARCH STUDENT BY NAME
    # ------------------------------------------

    if student is None:

        students = conn.execute("""
            SELECT *
            FROM students
            ORDER BY name
        """).fetchall()

        for s in students:

            name = s["name"].lower()

            if name in query:
                student = s
                break

    # ------------------------------------------
    # STUDENT NOT FOUND
    # ------------------------------------------

    if student is None:

        conn.close()

        return jsonify({
            "success": False,
            "type": "text",
            "message": (
                "Student nahi mila. "
                "Please student ka naam ya roll number clearly likhein."
            )
        })

    student_id = student["id"]

    # ------------------------------------------
    # STUDENT ATTENDANCE
    # ------------------------------------------

    attendance = conn.execute("""
        SELECT date, status
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC
    """, (student_id,)).fetchall()

    total_days = len(attendance)

    present_days = sum(
        1 for a in attendance
        if a["status"] == "Present"
    )

    absent_days = sum(
        1 for a in attendance
        if a["status"] == "Absent"
    )

    percentage = (
        (present_days / total_days) * 100
        if total_days > 0
        else 0
    )

    # ------------------------------------------
    # EMAIL
    # ------------------------------------------

    if "email" in query:

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_info",
            "message": f"{student['name']} ka email hai: {student['email']}",
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            }
        })

    # ------------------------------------------
    # ROLL NUMBER
    # ------------------------------------------

    if (
        (
            "roll number" in query
            or "roll no" in query
            or "roll" in query
            or "ka number" in query
        )
        and "attendance" not in query
        and "percentage" not in query
        and "present" not in query
        and "absent" not in query
        and "email" not in query
        and "naam" not in query
        and "name" not in query
    ):

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_info",
            "message": (
                f"{student['name']} ka roll number hai "
                f"{student['roll_no']}."
            ),
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            }
        })

    # ------------------------------------------
    # PRESENT DAYS
    # ------------------------------------------

    if (
        "present" in query
        and (
            "kitne" in query
            or "days" in query
            or "din" in query
            or "attendance" in query
        )
    ):

        conn.close()

        return jsonify({
            "success": True,
            "type": "attendance",
            "message": (
                f"{student['name']} {present_days} din present tha."
            ),
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            },
            "attendance": {
                "total_days": total_days,
                "present_days": present_days,
                "absent_days": absent_days,
                "percentage": round(percentage, 2)
            }
        })

    # ------------------------------------------
    # ABSENT DAYS
    # ------------------------------------------

    if (
        "absent" in query
        and (
            "kitne" in query
            or "days" in query
            or "din" in query
            or "attendance" in query
        )
    ):

        conn.close()

        return jsonify({
            "success": True,
            "type": "attendance",
            "message": (
                f"{student['name']} {absent_days} din absent tha."
            ),
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            },
            "attendance": {
                "total_days": total_days,
                "present_days": present_days,
                "absent_days": absent_days,
                "percentage": round(percentage, 2)
            }
        })

    # ------------------------------------------
    # ATTENDANCE / PERCENTAGE
    # ------------------------------------------

    if (
        "attendance" in query
        or "percentage" in query
        or "%" in query
    ):

        conn.close()

        return jsonify({
            "success": True,
            "type": "attendance",
            "message": (
                f"{student['name']} ki attendance "
                f"{round(percentage, 2)}% hai."
            ),
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            },
            "attendance": {
                "total_days": total_days,
                "present_days": present_days,
                "absent_days": absent_days,
                "percentage": round(percentage, 2),
                "recent": [
                    {
                        "date": a["date"],
                        "status": a["status"]
                    }
                    for a in attendance[:10]
                ]
            }
        })
    
    # ------------------------------------------
    # STUDENT NAME
    # ------------------------------------------

    if (
        "naam" in query
        or "name" in query
    ):

        conn.close()

        return jsonify({
            "success": True,
            "type": "student_info",
            "message": f"Student ka naam {student['name']} hai.",
            "student": {
                "name": student["name"],
                "roll_no": student["roll_no"],
                "email": student["email"]
            }
        })


    # ------------------------------------------
    # DEFAULT = FULL BIO DATA
    # ------------------------------------------


    conn.close()

    return jsonify({
        "success": True,
        "type": "student_profile",

        "message": f"{student['name']} ki complete details:",

        "student": {
            "id": student["id"],
            "name": student["name"],
            "roll_no": student["roll_no"],
            "email": student["email"]
        },

        "attendance": {
            "total": total_days,
            "present": present_days,
            "absent": absent_days,
            "percentage": round(percentage, 2),

            "records": [
                {
                    "date": a["date"],
                    "status": a["status"]
                }
                for a in attendance[:10]
            ]
        }
    })


@app.route("/mess")
def mess_management():

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    meals = connection.execute(
        """
        SELECT meal_name, start_time, end_time, is_active
        FROM meal_config
        ORDER BY id
        """
    ).fetchall()

    today_attendance = connection.execute(
        """
        SELECT
            students.name,
            students.roll_no,
            mess_attendance.meal,
            mess_attendance.entry_time,
            mess_attendance.status
        FROM mess_attendance
        JOIN students
            ON students.id = mess_attendance.student_id
        WHERE mess_attendance.date = date('now', 'localtime')
        ORDER BY mess_attendance.entry_time DESC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "mess_management.html",
        meals=meals,
        today_attendance=today_attendance
    )

# ==========================================
# MESS QR SCAN
# ==========================================

@app.route("/mess/scanner")
def mess_scanner():
    return render_template("mess_scanner.html")

@app.route("/mess/scan", methods=["POST"])
def mess_scan():

    data = request.get_json()

    if not data or "student_id" not in data:
        return jsonify({
            "success": False,
            "message": "Student ID is required."
        }), 400

    try:
        student_id = int(data["student_id"])
        
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid student ID."
        }), 400

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    student = connection.execute(
        """
        SELECT id, name, roll_no
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    connection.close()

    if student is None:
        return jsonify({
            "success": False,
            "message": "Student not found."
        }), 404

    result = mark_mess_attendance(student_id)

    if result[0] is False:
        return jsonify({
            "success": False,
            "message": result[1],
            "student_id": student["id"],
            "name": student["name"],
            "roll_no": student["roll_no"]
        })

    attendance = result[1]

    return jsonify({
        "success": True,
        "message": "Mess attendance marked successfully.",
        "student_id": student["id"],
        "name": student["name"],
        "roll_no": student["roll_no"],
        "meal": attendance["meal"],
        "entry_time": attendance["entry_time"],
        "status": attendance["status"]
    }
    )
# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )

print("Current meal:", get_current_meal())