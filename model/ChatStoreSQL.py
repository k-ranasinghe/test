import os
import json
import datetime
import mysql.connector
from langchain_core.messages import HumanMessage, AIMessage

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

# Function to establish MySQL connection
def get_mysql_connection():
    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB
    )
    return connection

def serialize_chat_history(chat_history):
    serialized_history = []
    for message in chat_history:
        if isinstance(message, HumanMessage) or isinstance(message, AIMessage):
            serialized_message = {
                "type": message.__class__.__name__,
                "content": message.content,
                "context": message.response_metadata
            }
            serialized_history.append(serialized_message)
        # Add additional handling for other message types if necessary
    return json.dumps(serialized_history)

def deserialize_chat_history(serialized_history):
    chat_history = []
    for serialized_message in json.loads(serialized_history):
        if serialized_message["type"] == "HumanMessage":
            message = HumanMessage(content=serialized_message["content"])
        elif serialized_message["type"] == "AIMessage":
            message = AIMessage(content=serialized_message["content"], response_metadata=serialized_message["context"])
        else:
            raise ValueError(f"Unknown message type: {serialized_message['type']}")
        
        chat_history.append(message)
    return chat_history

# Function to save chat history to MySQL
def save_chat_history(ChatID, UserID, chat_history, chat_summary):
    connection = get_mysql_connection()
    cursor = connection.cursor()
    
    serialized_history = serialize_chat_history(chat_history)
    
    cursor.execute("""
        INSERT INTO chat_data (ChatID, chat_history, chat_summary)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE chat_history = %s, chat_summary = %s
    """, (ChatID, serialized_history, chat_summary, serialized_history, chat_summary))

    # Insert or update `User_chats` table
    cursor.execute("""
        INSERT INTO user_chats (ChatID, UserID, Timestamp)
        VALUES (%s, %s, NOW())
        ON DUPLICATE KEY UPDATE Timestamp = NOW()
    """, (ChatID, UserID))
    
    connection.commit()
    cursor.close()
    connection.close()

# Function to load chat history from MySQL
def load_chat_history(ChatID):
    connection = get_mysql_connection()
    cursor = connection.cursor()
    
    cursor.execute("SELECT chat_history, chat_summary FROM chat_data WHERE ChatID = %s", (ChatID,))
    result = cursor.fetchone()
    
    if result:
        chat_history = deserialize_chat_history(result[0])
        chat_summary = result[1]
    else:
        chat_history = []
        chat_summary = ""
    
    cursor.close()
    connection.close()
    
    return chat_history, chat_summary


def get_instruction(parameter):
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)

    # Execute the query with the given parameters
    cursor.execute("""
    SELECT instruction 
    FROM Personalization_instructions 
    WHERE parameter = %s
    """, (parameter,))

    # Fetch the result
    result = cursor.fetchone()

    # Close the cursor and connection
    cursor.close()
    connection.close()

    return result['instruction']


def get_personalization_params(ChatID):
    # Connect to the MySQL database
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    # SQL query to fetch the personalization parameters
    query = """
    SELECT Chat_title, Student_type, Learning_style, Communication_format, Tone_style, Reasoning_framework 
    FROM Chat_info 
    WHERE ChatID = %s
    """
    cursor.execute(query, (ChatID,))
    result = cursor.fetchone()

    # Close the cursor and connection
    cursor.close()
    conn.close()

    # Return the result as a dictionary
    if result:
        return {
            "chat_title": result['Chat_title'],
            "student_type": result['Student_type'],
            "learning_style": result['Learning_style'],
            "communication_format": result['Communication_format'],
            "tone_style": result['Tone_style'],
            "reasoning_framework": result['Reasoning_framework']
        }
    else:
        return {}


def calculate_student_type(dob):
    # Calculate the user's age based on DOB
    today = datetime.date.today()
    birthdate = dob
    age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
    
    # Determine student type based on age
    if 10 <= age <= 15:
        return "type1"
    elif 16 <= age <= 18:
        return "type2"
    else:
        return None  # For users outside the 10-18 range, no specific type

def update_personalization_params(chat_id, UserID, chat_title, learning_style, communication_format, tone_style, reasoning_framework):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    # Get the user's DOB from the user_data table
    cursor.execute("SELECT Date_of_birth FROM user_data WHERE UserID = %s", (UserID,))
    user_data = cursor.fetchone()

    if not user_data or not user_data['Date_of_birth']:
        raise ValueError(f"No date of birth found for UserID: {UserID}")

    # Calculate the student type based on DOB
    dob = user_data['Date_of_birth']
    student_type = calculate_student_type(dob)
    
    if not student_type:
        raise ValueError(f"UserID: {UserID} is outside the valid student age range (10-18).")
    
    cursor.close()
    cursor = conn.cursor()
    
    # Check if the chat_id exists
    check_query = "SELECT COUNT(*) FROM Chat_info WHERE ChatID = %s"
    cursor.execute(check_query, (chat_id,))
    exists = cursor.fetchone()

    if exists[0] > 0:
        # If it exists, update the existing row
        query = """
            UPDATE Chat_info
            SET 
                Chat_title = %s,
                Student_type = %s,
                Learning_style = %s,
                Communication_format = %s,
                Tone_style = %s,
                Reasoning_framework = %s
            WHERE 
                ChatID = %s
        """
        cursor.execute(query, (chat_title, student_type, learning_style, communication_format, tone_style, reasoning_framework, chat_id))
    else:
        # If it does not exist, insert a new row
        query = """
            INSERT INTO Chat_info (ChatID, Chat_title, Student_type, Learning_style, Communication_format, Tone_style, Reasoning_framework)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (chat_id, chat_title, student_type, learning_style, communication_format, tone_style, reasoning_framework))

    # Insert or update User_chats table
    cursor.execute("""
        INSERT INTO user_chats (ChatID, UserID, Timestamp)
        VALUES (%s, %s, NOW())
        ON DUPLICATE KEY UPDATE Timestamp = NOW()
    """, (chat_id, UserID))

    conn.commit()
    
    cursor.close()
    conn.close()


def get_mentor_notes_by_course(studentid):
    # Establish a database connection
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)
    
    # SQL query to fetch notes for the given studentid
    query = """
    SELECT course, notes
    FROM mentor_notes
    WHERE studentid = %s
    """
    cursor.execute(query, (studentid,))
    
    # Fetch all results
    results = cursor.fetchall()
    
    # Close the cursor and connection
    cursor.close()
    connection.close()
    
    # Initialize a dictionary to hold concatenated notes by course
    notes_by_course = {}
    
    # Flag to check if any notes were found
    notes_found = False
    
    for result in results:
        course = result['course']
        notes = result['notes']
        
        if course not in notes_by_course:
            notes_by_course[course] = ""
        
        # Concatenate notes with a space
        notes_by_course[course] += " " + notes.strip()
        
        # Update the flag if notes are found
        notes_found = True
    
    # If no notes were found, add a default message for each course
    if not notes_found:
        # Query to get a list of all courses for the given studentid
        query_courses = """
        SELECT DISTINCT course
        FROM mentor_notes
        """
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query_courses)
        courses = cursor.fetchall()
        cursor.close()
        
        for course in [row['course'] for row in courses]:
            notes_by_course[course] = "there are no available notes."
    
    return notes_by_course


def get_past_chats(user_id):
    # Establish a database connection
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Fetching past chats with timestamps from `User_chats` and `Chat_info` for a specific UserID
    query = """
    SELECT uc.ChatID, ci.Chat_title, uc.Timestamp
    FROM User_chats uc
    JOIN Chat_info ci ON uc.ChatID = ci.ChatID
    WHERE uc.UserID = %s
    ORDER BY uc.Timestamp DESC
    """
    cursor.execute(query, (user_id,))
    
    # Fetch all results
    past_chats = cursor.fetchall()
    
    # Close the cursor and connection
    cursor.close()
    connection.close()
    
    return past_chats


def get_chat_ids():
    # Establish a database connection
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)
    
    # SQL query to get distinct ChatID values from User_chats
    query = """
    SELECT DISTINCT ChatID
    FROM User_chats
    """
    
    cursor.execute(query)
    
    # Fetch all results
    chat_ids = cursor.fetchall()
    
    # Close the cursor and connection
    cursor.close()
    connection.close()
    
    # Return a list of ChatID values
    return [row['ChatID'] for row in chat_ids]


def get_courses_and_subjects():
    # Establish a database connection
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)
    
    # SQL query to get distinct courses and subjects
    query = """
    SELECT DISTINCT Course, Subject 
    FROM Curriculum
    """
    
    cursor.execute(query)
    
    # Fetch all results
    distinct_courses_and_subjects = cursor.fetchall()
    
    # Close the cursor and connection
    cursor.close()
    connection.close()
    
    return distinct_courses_and_subjects
