import sqlite3


DATABASE = "attendance.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection

def create_database():
    connection = get_db_connection()


    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            email TEXT,
            created_at timestamp default current_timestamp
        )
    """)
        
    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id integer not null,
            date TEXT NOT NULL,
            status text not null check (status in ('present', 'absent')),
            created_at timestamp default current_timestamp,

            foreign key (student_id) references students(id) on delete cascade,
            unique (student_id, date)
        )
    """)

    connection.commit()
    connection.close()

   


if __name__ == "__main__":
    create_database()
    print("Database created successfully!")

