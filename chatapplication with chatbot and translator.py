import sys
import os
import socket
import threading
import sqlite3
import requests
import argparse
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget, QMessageBox, QFileDialog, QColorDialog, QInputDialog
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QMessageBox
from googletrans import Translator
# Encryption for messages
from cryptography.fernet import Fernet

# Server Address and Port
HOST = '192.168.39.187'
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
        """
        Send the message to the intended recipient if the sender is allowed.
        """
        if not self.can_send_message(sender_username, recipient_username):
            print(f"Message blocked: {sender_username} does not follow {recipient_username}.")
            return

        # Look for the recipient in the connected clients
        recipient_socket = None
        for client_socket, username in self.clients.items():
            if username == recipient_username:
                recipient_socket = client_socket
                break

        if recipient_socket:
            try:
                # Send the message to the recipient
                recipient_socket.sendall(f"{sender_username}: {message}".encode())
            except Exception as e:
                print(f"Error sending message to {recipient_username}: {e}")
        else:
            print(f"Recipient {recipient_username} is not online.")

    def handle_client(self, client_socket):
        try:
            username = client_socket.recv(1024).decode()  # First message is the username
            self.clients[client_socket] = username
            print(f"New connection: {username}")

            # Notify other users about the new user
            for sock, uname in self.clients.items():
                if sock != client_socket:  # Don't notify the new user about themselves
                    try:
                        sock.sendall(f"SERVER: {username} has joined the chat.".encode())
                    except Exception as e:
                        print(f"Error notifying user {uname}: {e}")

            # Handle incoming messages
            while True:
                data = client_socket.recv(1024).decode()
                if not data:
                    break  # Connection closed

                if data.startswith("FILE|"):
                    # Handle file messages
                    parts = data.split("|", 4)
                    sender, recipient, file_name = parts[1], parts[2], parts[3]
                    if self.can_send_message(sender, recipient):
                        file_data = client_socket.recv(4096)
                        with open(f"received_{file_name}", "wb") as file:
                            file.write(file_data)
                        print(f"File {file_name} received from {sender}.")
                else:
                    # Regular message handling
                    sender, recipient, message = data.split('|', 2)
                    decrypted_message = decrypt_message(message)
                    self.save_message(sender, recipient, decrypted_message)
                    self.broadcast(decrypted_message, sender, recipient)
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            # Clean up on client disconnect
            username = self.clients.get(client_socket, "Unknown")
            del self.clients[client_socket]
            client_socket.close()
            print(f"{username} disconnected.")

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
        self.setWindowTitle("CHAT APPLICATION")
        self.setGeometry(100, 100, 400, 300)

        layout = QVBoxLayout()

        # Application Logo
        logo = QLabel(self)
        pixmap = QPixmap("logo.png")  # Replace 'logo.png' with your actual logo file path
        pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio)
        logo.setPixmap(pixmap)
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        # Header
        header = QLabel("Welcome to Chat App", self)
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Username
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("Enter Username")
        self.username_input.setFixedHeight(40)
        layout.addWidget(self.username_input)

        # Password
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Password")
        self.password_input.setFixedHeight(40)
        layout.addWidget(self.password_input)

          # Buttons
        btn_layout = QHBoxLayout()
        
        # Login Button
        self.login_button = QPushButton("Login", self)
        self.login_button.setStyleSheet("""
            QPushButton {background-color: #4CAF50;  /* Green */color: white;font-size: 14px;padding: 10px;border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.login_button.clicked.connect(self.login_user)
        btn_layout.addWidget(self.login_button)

        # Register Button
        self.register_button = QPushButton("Register", self)
        self.register_button.setStyleSheet("""
            QPushButton {background-color: #008CBA;  /* Blue */color: white;font-size: 14px;padding: 10px;border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #007bb5;
            }
        """)
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
class APIHandler:
    def __init__(self):
        self.api_url = "https://api.gemini.ai/v1/translate"  # Replace with the actual API URL
        self.api_key = "AIzaSyAdBZQ55OeV1pGWnWiI2QVsWCO97wUvY2I"  # Replace with your Gemini AI API key

    def translate_text(self, text, target_language="en"):
        """
        Translate text using Gemini AI or any translation API.
        """
        api_url = "https://api.gemini.ai/v1/translate"  # Replace with the correct API URL
        api_key = "AIzaSyAdBZQ55OeV1pGWnWiI2QVsWCO97wUvY2I"  # Replace with your API key

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "target_language": target_language
        }
        try:
            response = requests.post(api_url, json=payload, headers=headers)
            if response.status_code == 200:
                return response.json().get("translated_text", "")
            else:
                return f"Error: {response.json().get('message', 'Translation failed.')}"
        except requests.RequestException as e:
            return f"Error: {str(e)}"

class ChatApp(QMainWindow):
    def __init__(self, username):
        super().__init__()  # Initialize QMainWindow
        self.username = username 
        self.dark_mode = False # Store the username
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_connected = False
        self.current_recipient = None
        self.translator = Translator()
        self.init_ui()  # Set up the UI
        self.connect_to_server()

    def init_ui(self):
        self.setWindowTitle(f"Chat Application - {self.username}")
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
        self.user_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.user_list.customContextMenuRequested.connect(self.show_user_context_menu)
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

        self.translate_button = QPushButton("Translate", self)
        self.translate_button.clicked.connect(self.translate_selected_message)
        self.translate_button.setStyleSheet("""
            QPushButton {background-color: #FF6347; /* Tomato Red */color: #FFFFFF; /* White text */font-weight: bold;border-radius: 8px;padding: 5px;
            }
            QPushButton:hover {
                background-color: #FF4500; /* Orange Red */
            }
        """)
        chat_layout.addWidget(self.translate_button)  # Add to chat layout

        chat_layout.addLayout(message_layout)
        # Dropdown Actions Button
        self.actions_button = QPushButton("MORE OPTIONS", self)
        self.actions_menu = QMenu(self)

        # Add menu options
        
        self.actions_menu.addAction("Share File", self.share_file)
        self.actions_menu.addAction("Export Chat", self.export_chat)
        self.actions_menu.addAction("Change Chat Background", self.change_chat_display_background)

        # Attach the menu to the button
        self.actions_button.setMenu(self.actions_menu)
        chat_layout.addWidget(self.actions_button)

        main_layout.addLayout(chat_layout, 3)

        layout.addLayout(main_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Apply colorful button styles
        self.apply_button_styles()

    def toggle_theme(self):
        """Toggle between light and dark modes."""
        if self.dark_mode:
            self.set_light_mode()
        else:
            self.set_dark_mode()
        self.dark_mode = not self.dark_mode

    def translate_selected_message(self):
        # Get the selected chat message
        selected_message = self.get_selected_message()
        if not selected_message:
            QMessageBox.warning(self, "Error", "Please select a message to translate.")
            return

        # Provide a list of common languages
        language_options = {"English": "en","Spanish": "es","French": "fr","German": "de","Chinese (Simplified)": "zh-cn","Hindi": "hi","Arabic": "ar","Japanese": "ja","Tamil": "ta"  # Added Tamil
        }
        items = list(language_options.keys())
        choice, ok = QInputDialog.getItem(
            self, "Translate", "Choose target language:", items, 0, editable=False
        )
        if not ok or not choice:
            return

        # Get the language code
        target_language = language_options[choice]

        try:
            # Translate the message
            translated = self.translator.translate(selected_message, dest=target_language)
            translated_text = translated.text
            self.chat_display.append(f"Translated ({choice}): {translated_text}")
        except Exception as e:
            QMessageBox.critical(self, "Translation Error", f"Error translating message: {str(e)}")

    def get_selected_message(self):
        cursor = self.chat_display.textCursor()
        selected_text = cursor.selectedText()
        return selected_text if selected_text else None

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

    def change_chat_display_background(self):
        """Allow the user to select and change the chat display background color or set a single image."""
        try:
            items = ["Color", "Image"]
            choice, ok = QInputDialog.getItem(
                self,
                "Change Chat Background",
                "Choose background type:",
                items,
                0,
                editable=False
            )
            if ok:
                if choice == "Color":
                    color = QColorDialog.getColor()
                    if color.isValid():
                        self.chat_display.setStyleSheet(f"background-color: {color.name()}; color: #000000;")
                elif choice == "Image":
                    file_path, _ = QFileDialog.getOpenFileName(
                        self,
                        "Select Background Image",
                        "",
                        "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.svg *.webp)"
                    )
                    if file_path:
                        self.chat_display.setStyleSheet(
                            f"background-image: url('{file_path}'); background-repeat: no-repeat; "
                            f"background-position: center; background-size: cover; color: #000000;"
                        )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def apply_button_styles(self):
        """Apply colorful styles to buttons."""
        button_style = """
        QPushButton {
            background-color: #4682B4;border-radius: 8px;padding: 5px;font-weight: bold;color: #FFFFFF;
        }
        QPushButton:hover {
            background-color: #5A9BD4;
        }
        """
        self.actions_button.setStyleSheet(button_style)
        self.send_button.setStyleSheet(button_style)
        self.toggle_button.setStyleSheet(button_style)

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

    def show_user_context_menu(self, position):
        """Show context menu for user actions."""
        item = self.user_list.itemAt(position)
        if item:
            self.current_recipient = item.text()
            menu = QMenu(self)
            menu.addAction("Follow", self.follow_user)
            menu.addAction("Unfollow", self.unfollow_user)
            menu.exec_(self.user_list.viewport().mapToGlobal(position))

    def select_user(self, item):
        self.current_recipient = item.text()
        self.chat_display.append(f"Chatting with {self.current_recipient}")

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

    def receive_messages(self):
        while self.is_connected:
            try:
                data = self.socket.recv(1024).decode()
                if data:
                    self.chat_display.append(data)  # Decrypted message is displayed directly
            except Exception as e:
                self.chat_display.append(f"Connection lost: {e}")
                break

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