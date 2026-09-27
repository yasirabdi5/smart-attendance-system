# Smart Attendance & Mess Management System

A Flask-based web application designed to manage student registration, attendance, student records, and QR-based mess attendance through separate admin and student workflows.

## Overview

The **Smart Attendance & Mess Management System** is a college mini-project developed using Python and Flask.

The system provides an admin dashboard for managing students and attendance, along with a student dashboard where students can view their profile and attendance information.

It also includes a **QR-based Mess Management System** that allows students with mess access to use their generated QR code for meal attendance.

## Features

### Admin Features

* Admin registration and login
* Admin session management
* Admin management
  * Create admins
  * View admins
  * Delete admins
* Student registration
* Student profile/photo capture
* Edit student information
* Delete students
* Student list management
* Attendance marking
* Attendance percentage calculation
* Attendance reports
* Dashboard statistics
* Attendance visualization
* Mess Management
* Meal timing configuration
* QR-based mess attendance
* Continuous QR scanner

### Student Features

* Student login using roll number and password
* Student dashboard
* View personal profile
* View attendance statistics
* View attendance percentage
* View attendance history
* Present/Absent visualization
* Logout
* Mess QR code access for eligible students

## Mess Management

The system includes a QR-based mess attendance system.

Students can be assigned **Mess Access: Yes or No** by the administrator.

When mess access is enabled:

1. A unique QR code is generated for the student.
2. The QR code is displayed on the student's dashboard.
3. The student presents the QR code to the mess scanner.
4. The scanner identifies the student.
5. The system checks the currently active meal.
6. Mess attendance is recorded.
7. Duplicate attendance for the same meal is prevented.

### Configurable Meal Timings

Meal timings can be configured through the Mess Management section.

The system supports meals such as:

* Breakfast
* Lunch
* Evening Snacks
* Dinner

The active meal is determined dynamically according to the configured time range.

## QR Scanner

The project uses a local QR scanning implementation with:

* `qr-scanner.umd.min.js`
* `qr-scanner-worker.min.js`

The scanner supports **continuous scanning**, allowing multiple student QR codes to be scanned without restarting the camera after every scan.

## Attendance System

The application supports attendance management through the admin interface.

Attendance-related functionality includes:

* Marking attendance
* Present/Absent records
* Attendance percentage
* Attendance history
* Attendance reports
* Dashboard statistics
* Attendance charts

The project also contains face-recognition related components using OpenCV models.

## Technology Stack

### Backend

* Python
* Flask
* SQLite

### Frontend

* HTML5
* CSS3
* JavaScript
* Chart.js

### Computer Vision

* OpenCV
* YuNet face detection
* SFace face recognition

### QR System

* Python `qrcode`
* QR Scanner JavaScript library

### Development Tools

* Visual Studio Code
* Git
* GitHub

## Project Structure

```text
smart-attendance-system/
|
+-- app.py
+-- database.py
+-- generate_qr.py
+-- mess_qr_scanner.py
+-- requirements.txt
+-- .gitignore
|
+-- face_data/
|   +-- haarcascade_frontalface_default.xml
|   +-- models/
|       +-- face_detection_yunet_2023mar.onnx
|       +-- face_recognition_sface_2021dec.onnx
|
+-- static/
|   +-- styles.css
|   +-- qr-scanner.umd.min.js
|   +-- qr-scanner-worker.min.js
|   +-- uploads/
|   +-- mess_qr/
|
+-- templates/
    +-- index.html
    +-- login.html
    +-- register.html
    +-- students.html
    +-- edit_student.html
    +-- attendance.html
    +-- mark_attendance.html
    +-- attendance_percentage.html
    +-- attendance_report.html
    +-- student_login.html
    +-- student_dashboard.html
    +-- select_student.html
    +-- create_admin.html
    +-- manage_admins.html
    +-- mess_management.html
    +-- mess_scanner.html


## Installation

### 1. Clone the repository


git clone https://github.com/yasirabdi5/smart-attendance-system.git
cd smart-attendance-system
2. Create a virtual environment
python -m venv .venv

3. Activate the virtual environment

PowerShell:

.venv\Scripts\Activate.ps1

If using Command Prompt:

.venv\Scripts\activate

4. Install dependencies
pip install -r requirements.txt
Running the Application

Start the Flask application:

python app.py

The application will normally be available at:

http://127.0.0.1:5000

Open the address in a web browser.

-->Basic Workflow<--

->Admin<-

Admin Login
    |
    v
Dashboard
    |
    v
Manage Students
    |
    v
Register / Edit Students
    |
    v
Manage Attendance
    |
    v
View Reports
    |
    v
Mess Management
    |
    v
Configure Meals / Scan QR


->Student<-

Student Login
    |
    v
Student Dashboard
    |
    v
View Profile
    |
    v
View Attendance
    |
    v
View Attendance History
    |
    v
View Mess QR

->Mess Attendance Workflow<-

Student
   |
   v
Student Dashboard
   |
   v
Display Mess QR
   |
   v
Mess Scanner
   |
   v
QR Detection
   |
   v
Identify Student
   |
   v
Check Active Meal
   |
   v
Record Mess Attendance


-->Screenshots<--

Home Page

The landing page provides access to the main attendance and student management system.

Admin Dashboard

The admin dashboard provides an overview of students, attendance, and system management features.

Student Registration

Administrators can register students with their personal details, login credentials, photo, and mess access.

Attendance Management

Administrators can mark and manage student attendance and view attendance-related information.

Student Dashboard

Students can log in to view their profile, attendance statistics, attendance history, and mess QR code.

Mess Management

The Mess Management section allows administrators to configure meal timings and manage mess attendance.

Mess QR Scanner

The QR scanner supports continuous scanning for recording mess attendance for multiple students.

Student Mess QR

Students with mess access receive a generated QR code that can be scanned at the mess.

->Current Project Status<-

The project currently provides a working MVP containing:

Admin authentication
Student authentication
Student management
Attendance management
Attendance reports
Student dashboard
Attendance visualization
Mess management
Configurable meal timings
Student mess access control
QR generation
Continuous QR scanning
Database-backed records

->Future Improvements<-

Possible future improvements include:

Role-based access for faculty and mess operators
Subject-wise attendance
Department/course/semester management
Leave management
Attendance correction and approval
Bulk student import
Excel/PDF report export
Notifications
Improved security and access control
PostgreSQL database for production
Cloud deployment
Automated database backups
Mobile-responsive improvements
Secure QR tokens instead of exposing numeric student IDs
Improved offline handling for QR scanning
College-wide integration

->Development Workflow<-

The project uses Git and GitHub for version control.

Development branches:

yasir
  |
  v
backend
  |
  v
main

yasir — development work
backend — integration branch
main — stable/release version
Disclaimer

This project is currently developed as a college mini-project / MVP. It is not intended to be considered a production-ready college ERP system without additional security, scalability, deployment, backup, and infrastructure work.

Author

Syed Yasir Ali

B.Tech Computer Science and Engineering

Dr. M.C. Saxena College of Engineering and Technology

Expected Graduation: 2028