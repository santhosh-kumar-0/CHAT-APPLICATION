import sys
import os
import socket
import threading
import sqlite3
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget, QMessageBox, QFileDialog
)
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt

# Encryption for messages
from cryptography.fernet import Fernet

# Server Address and Port
HOST = '127.0.0.1'
PORT = 5000

# Initialize SQLite Database
DB_FILE = "chat_app.db"

# Generate a key for encryption
ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)


def encrypt_message(message):
    return cipher.encrypt(message.encode()).decode()


def decrypt_message(message):
    return cipher.decrypt(message.encode()).decode()


def initialize_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS followers (
            follower TEXT NOT NULL,
            followed TEXT NOT NULL,
            PRIMARY KEY (follower, followed)
        )
    """)
    conn.commit()
    conn.close()


# Backend: Server Code
class ChatServer:
    def __init__(self, host, port):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen(5)
        print(f"Server started on {host}:{port}")
        self.clients = {}  # Map client sockets to usernames

    def can_send_message(self, sender, recipient):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM followers
            WHERE follower = ? AND followed = ?
        """, (sender, recipient))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def broadcast(self, message, sender_username, recipient_username):
        if self.can_send_message(sender_username, recipient_username):
            for client_socket, username in self.clients.items():
                if username == recipient_username:
                    try:
                        client_socket.sendall(f"{sender_username}: {message}".encode())
                    except Exception as e:
                        print(f"Error broadcasting message: {e}")
        else:
            print(f"Message blocked: {sender_username} does not follow {recipient_username}.")

    def handle_client(self, client_socket):
        username = client_socket.recv(1024).decode()  # First message is the username
        self.clients[client_socket] = username
        print(f"New connection: {username}")

        while True:
            try:
                data = client_socket.recv(1024).decode()
                if data.startswith("FILE|"):
                    parts = data.split("|", 4)
                    sender, recipient, file_name = parts[1], parts[2], parts[3]
                    if self.can_send_message(sender, recipient):
                        file_data = client_socket.recv(4096)  # Adjust buffer size as needed
                        with open(f"received_{file_name}", "wb") as file:
                            file.write(file_data)
                        print(f"File {file_name} received from {sender}.")
                else:
                    sender, recipient, message = data.split('|', 2)
                    decrypted_message = decrypt_message(message)
                    self.save_message(sender, recipient, decrypted_message)
                    self.broadcast(message, sender, recipient)
            except Exception as e:
                print(f"Error handling client: {e}")
                del self.clients[client_socket]
                client_socket.close()
                break

    def save_message(self, sender, recipient, message):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (sender, recipient, message)
            VALUES (?, ?, ?)
        """, (sender, recipient, message))
        conn.commit()
        conn.close()

    def start(self):
        while True:
            client_socket, _ = self.server.accept()
            threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()


# Login Window
class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Login to Chat")
        self.setGeometry(100, 100, 400, 300)

        layout = QVBoxLayout()

        # Header
        header = QLabel("Welcome to Chat App", self)
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Username
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("Enter Username")
        layout.addWidget(self.username_input)

        # Password
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Password")
        layout.addWidget(self.password_input)

        # Buttons
        btn_layout = QHBoxLayout()
        self.login_button = QPushButton("Login", self)
        self.login_button.clicked.connect(self.login_user)
        btn_layout.addWidget(self.login_button)

        self.register_button = QPushButton("Register", self)
        self.register_button.clicked.connect(self.register_user)
        btn_layout.addWidget(self.register_button)

        layout.addLayout(btn_layout)

        # Set central widget
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def login_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            self.open_chat_window(username)
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password.")

    def register_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            QMessageBox.information(self, "Registration Successful", "You can now log in.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Registration Failed", "Username already exists.")
        conn.close()

    def open_chat_window(self, username):
        self.chat_window = ChatApp(username)
        self.chat_window.show()
        self.close()


class ChatApp(QMainWindow):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.current_recipient = None
        self.dark_mode = False  # Initialize with light mode
        self.init_ui()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_connected = False
        self.connect_to_server()

    def init_ui(self):
        self.setWindowTitle(f'Chat - {self.username}')
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # Toggle Light/Dark Mode
        toggle_layout = QHBoxLayout()
        self.toggle_button = QPushButton("Toggle Dark Mode", self)
        self.toggle_button.clicked.connect(self.toggle_theme)
        toggle_layout.addWidget(self.toggle_button)
        layout.addLayout(toggle_layout)

        # Header
        header = QLabel(f"Welcome, {self.username}")
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Main Content Layout
        main_layout = QHBoxLayout()

        # User List
        self.user_list = QListWidget(self)
        self.user_list.itemClicked.connect(self.select_user)
        main_layout.addWidget(self.user_list, 1)

        # Chat Layout
        chat_layout = QVBoxLayout()

        # Chat Display
        self.chat_display = QTextEdit(self)
        self.chat_display.setReadOnly(True)
        chat_layout.addWidget(self.chat_display)

        # Message Input Layout
        message_layout = QHBoxLayout()

        self.msg_input = QLineEdit(self)
        self.msg_input.setPlaceholderText("Type your message...")
        message_layout.addWidget(self.msg_input)

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self.send_message)
        message_layout.addWidget(self.send_button)

        chat_layout.addLayout(message_layout)

        # Action Buttons Layout
        action_layout = QHBoxLayout()

        self.follow_button = QPushButton("Follow", self)
        self.follow_button.clicked.connect(self.follow_user)
        action_layout.addWidget(self.follow_button)

        self.unfollow_button = QPushButton("Unfollow", self)
        self.unfollow_button.clicked.connect(self.unfollow_user)
        action_layout.addWidget(self.unfollow_button)

        self.file_button = QPushButton("Share File", self)
        self.file_button.clicked.connect(self.share_file)
        action_layout.addWidget(self.file_button)

        self.export_button = QPushButton("Export Chat", self)
        self.export_button.clicked.connect(self.export_chat)
        action_layout.addWidget(self.export_button)

        # Accept Button
        self.accept_button = QPushButton("Accept", self)
        self.accept_button.clicked.connect(self.accept_user)
        action_layout.addWidget(self.accept_button)

        chat_layout.addLayout(action_layout)
        main_layout.addLayout(chat_layout, 3)

        layout.addLayout(main_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def toggle_theme(self):
        """Toggle between light and dark modes."""
        if self.dark_mode:
            self.set_light_mode()
        else:
            self.set_dark_mode()
        self.dark_mode = not self.dark_mode

    def set_light_mode(self):
        """Set light theme."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
        QApplication.setPalette(palette)

    def set_dark_mode(self):
        """Set dark theme."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        QApplication.setPalette(palette)

    def accept_user(self):
        """Accept incoming user requests or messages."""
        if self.current_recipient:
            self.chat_display.append(f"You accepted a request from {self.current_recipient}.")


    def connect_to_server(self):
        try:
            self.socket.connect((HOST, PORT))
            self.socket.sendall(self.username.encode())
            self.is_connected = True

            threading.Thread(target=self.receive_messages, daemon=True).start()
            self.load_users()
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", str(e))

    def load_users(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username != ?", (self.username,))
        users = cursor.fetchall()
        for user in users:
            self.user_list.addItem(user[0])
        conn.close()

    def select_user(self, item):
        self.current_recipient = item.text()
        self.chat_display.append(f"Chatting with {self.current_recipient}")

    def receive_messages(self):
        while self.is_connected:
            try:
                data = self.socket.recv(1024).decode()
                decrypted_message = decrypt_message(data)
                self.chat_display.append(decrypted_message)
            except Exception as e:
                self.chat_display.append(f"Error: {e}")
                break

    def send_message(self):
        message = self.msg_input.text()
        if message and self.current_recipient:
            try:
                encrypted_message = encrypt_message(message)
                full_message = f"{self.username}|{self.current_recipient}|{encrypted_message}"
                self.socket.sendall(full_message.encode())
                self.chat_display.append(f"You: {message}")
                self.msg_input.clear()
            except Exception as e:
                self.chat_display.append(f"Error: {e}")

    def follow_user(self):
        if self.current_recipient:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO followers (follower, followed) VALUES (?, ?)", (self.username, self.current_recipient))
                conn.commit()
                self.chat_display.append(f"You are now following {self.current_recipient}.")
            except sqlite3.IntegrityError:
                self.chat_display.append(f"You are already following {self.current_recipient}.")
            conn.close()

    def unfollow_user(self):
        if self.current_recipient:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM followers WHERE follower = ? AND followed = ?", (self.username, self.current_recipient))
            conn.commit()
            conn.close()
            self.chat_display.append(f"You unfollowed {self.current_recipient}.")

    def share_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_name and self.current_recipient:
            try:
                with open(file_name, "rb") as file:
                    file_data = file.read()
                    # Send file info and data
                    self.socket.sendall(f"FILE|{self.username}|{self.current_recipient}|{file_name}|".encode())
                    self.socket.sendall(file_data)
                self.chat_display.append(f"File {file_name} sent to {self.current_recipient}.")
            except Exception as e:
                self.chat_display.append(f"Error sending file: {e}")

    def export_chat(self):
        if self.current_recipient:
            file_name, _ = QFileDialog.getSaveFileName(self, "Save Chat", f"{self.username}_chat.txt", "Text Files (*.txt)")
            if file_name:
                with open(file_name, "w") as file:
                    file.write(self.chat_display.toPlainText())
                QMessageBox.information(self, "Export Successful", f"Chat saved to {file_name}")


if __name__ == '__main__':
    initialize_database()
    threading.Thread(target=lambda: ChatServer(HOST, PORT).start(), daemon=True).start()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec_())
