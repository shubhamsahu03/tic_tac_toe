# database_setup.py
import mysql.connector
from mysql.connector import Error

def create_database_connection():
    """Establishes a connection to MySQL."""
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="your_username",
            password="your_password"
        )
        if connection.is_connected():
            print("Connected to MySQL server")
        return connection
    except Error as e:
        print(f"Error: {e}")
        return None

def execute_script(connection, script_file):
    """Executes SQL script from a file."""
    try:
        cursor = connection.cursor()
        with open(script_file, 'r') as file:
            sql_script = file.read()
        for statement in sql_script.split(';'):
            if statement.strip():
                cursor.execute(statement)
        connection.commit()
        print("Database and tables created successfully.")
    except Error as e:
        print(f"Error executing script: {e}")

def main():
    connection = create_database_connection()
    if connection:
        execute_script(connection, 'db.sql')
        connection.close()
        print("Connection closed.")

if __name__ == "__main__":
    main()
