import sys
import socket
import threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTextEdit, QLineEdit, QPushButton, QLabel, QMessageBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSlot, Qt

# Server Address and Port
HOST = '127.0.0.1'
PORT = 5000

# In-Memory User Database
USER_DATABASE = {
    "admin": "password123"  # Example: username: password
}

# Backend: Server Code
class ChatServer:
    def __init__(self, host, port):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen(5)
        print(f"Server started on {host}:{port}")
        self.clients = []

    def broadcast(self, message, client_socket):
        for client in self.clients:
            if client != client_socket:
                try:
                    client.sendall(message)
                except Exception as e:
                    print(f"Error broadcasting message: {e}")

    def handle_client(self, client_socket):
        while True:
            try:
                message = client_socket.recv(1024)
                if message:
                    print(f"Received: {message.decode()}")
                    self.broadcast(message, client_socket)
            except Exception as e:
                print(f"Error handling client: {e}")
                self.clients.remove(client_socket)
                client_socket.close()
                break

    def start(self):
        while True:
            client_socket, client_address = self.server.accept()
            print(f"New connection from {client_address}")
            self.clients.append(client_socket)
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
        header.setStyleSheet("background-color: #2d89ef; color: white; padding: 10px; border-radius: 8px;")
        layout.addWidget(header)

        # Username
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("Enter Username")
        self.username_input.setStyleSheet("padding: 10px; border: 1px solid #ccc; border-radius: 8px;")
        layout.addWidget(self.username_input)

        # Password
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Password")
        self.password_input.setStyleSheet("padding: 10px; border: 1px solid #ccc; border-radius: 8px;")
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

        if username in USER_DATABASE and USER_DATABASE[username] == password:
            self.open_chat_window(username)
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password.")

    def register_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if username in USER_DATABASE:
            QMessageBox.warning(self, "Registration Failed", "Username already exists.")
        else:
            USER_DATABASE[username] = password
            QMessageBox.information(self, "Registration Successful", "You can now log in.")

    def open_chat_window(self, username):
        self.chat_window = ChatApp(username)
        self.chat_window.show()
        self.close()

# Chat Application Class
class ChatApp(QMainWindow):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.init_ui()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_connected = False
        self.connect_to_server()

    def init_ui(self):
        self.setWindowTitle(f'Chat - {self.username}')
        self.setGeometry(100, 100, 500, 600)

        # Fonts and Styles
        font = QFont('Arial', 12)
        self.setFont(font)

        # Main Layout
        layout = QVBoxLayout()

        # Header
        header = QLabel(f"Logged in as: {self.username}", self)
        header.setFont(QFont('Arial', 14, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("background-color: #2d89ef; color: white; padding: 10px; border-radius: 8px;")
        layout.addWidget(header)

        # Chat Display
        self.chat_display = QTextEdit(self)
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("border: 1px solid #ccc; border-radius: 8px; padding: 10px;")
        layout.addWidget(QLabel("Chat Window:"))
        layout.addWidget(self.chat_display)

        # Message Input Layout
        input_layout = QHBoxLayout()

        self.msg_input = QLineEdit(self)
        self.msg_input.setPlaceholderText("Type your message here...")
        self.msg_input.setStyleSheet("border: 1px solid #ccc; border-radius: 8px; padding: 10px;")
        input_layout.addWidget(self.msg_input)

        self.send_button = QPushButton('Send', self)
        self.send_button.setStyleSheet(
            "background-color: #4CAF50; color: white; border: none; padding: 10px 20px; border-radius: 8px;"
        )
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        layout.addLayout(input_layout)

        # Set central widget
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def connect_to_server(self):
        try:
            self.socket.connect((HOST, PORT))
            self.is_connected = True
            self.chat_display.append("Connected to server.")

            # Start a thread to listen for incoming messages
            threading.Thread(target=self.receive_messages, daemon=True).start()
        except Exception as e:
            self.chat_display.append(f"Failed to connect: {e}")

    def receive_messages(self):
        while self.is_connected:
            try:
                message = self.socket.recv(1024).decode()
                if message:
                    self.chat_display.append(message)
            except Exception as e:
                self.chat_display.append(f"Error receiving message: {e}")
                break

    @pyqtSlot()
    def send_message(self):
        message = self.msg_input.text()
        if message and self.is_connected:
            try:
                full_message = f"{self.username}: {message}"
                self.socket.sendall(full_message.encode())
                self.chat_display.append(full_message)
                self.msg_input.clear()
            except Exception as e:
                self.chat_display.append(f"Error sending message: {e}")

if __name__ == '__main__':
    # Start the server in a separate thread
    threading.Thread(target=lambda: ChatServer(HOST, PORT).start(), daemon=True).start()

    # Start the Login Window
    app = QApplication(sys.argv)
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec_())
