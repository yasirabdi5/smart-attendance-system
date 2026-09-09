import sqlite3


DATABASE = "attendance.db"


def create_database():
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            email TEXT
        )
    """)
        
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_number TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREING KEY (roll_no) REFERENCES students (roll_no)
    )
    """)

    connection.commit()
    connection.close()

   


if __name__ == "__main__":
    create_database()
    print("Database created successfully!")

