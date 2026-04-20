import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget,QSpacerItem, QTextEdit, QLineEdit, QStackedWidget, QHBoxLayout, QListWidget, QLabel, QSizePolicy
from qasync import QEventLoop, asyncSlot
from PyQt6.QtWidgets import QComboBox, QCheckBox
import asyncio
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
import json
import os 
import subprocess
import itertools

VERSION = "1.0"


class Config:
    def __init__(self, configFile):
        self.configFile = configFile
        # Значения по умолчанию
        #self.ip = "109.248.42.94"
        self.ip = "127.0.0.1"
        self.port = 4545
        self.username = None
        self.password = None
        self.theme = "dark"
        self.autostart = False
        self.load()

    def load(self):
        if os.path.exists(self.configFile):
            with open(self.configFile, 'r') as file:
                data = json.load(file)
                # Обновляем атрибуты объекта данными из файла
                self.__dict__.update(data)
        else: 
            self.save()

    def save(self):
        # Создаем копию словаря атрибутов без служебного поля configFile
        data_to_save = self.__dict__.copy()
        del data_to_save['configFile']
        
        with open(self.configFile, 'w') as file:
            json.dump(data_to_save, file, indent=4)

    def set(self, key, value):
        """Изменяет один параметр и сразу сохраняет файл"""
        if hasattr(self, key):
            setattr(self, key, value)
            self.save()


class Client:
    def __init__(self, Config: Config):
        self.config = Config
        self.reader = None
        self.writer = None
        self.isAuthorized = False
        self.lock = asyncio.Lock()         
        self.serverVersion = None
        self.isAdmin = False
        self.username = None


    async def getInitials(self):
        await self.sendJsonCommand({"command": "USERDATA"})
        data = await self.getJson()

        self.username = data.get("username")
        self.isAdmin = data.get("is_admin")
        print(self.username)
        print(self.isAdmin)


    async def sendJsonCommand(self, dictionary):
        json_data = (json.dumps(dictionary) + "\n").encode('utf-8')
        self.writer.write(json_data)
        await self.writer.drain() 


    async def connect(self):
        retry_delay = 10

        for i in itertools.count(start=0, step=1):
            try:
                self.reader, self.writer = await asyncio.open_connection(
                    self.config.ip, self.config.port
                )
                print(f"Подключено к серверу (попытка {i+1})")

                await self.getInitials()
                


                version = await self.getVersion()
                self.serverVersion = version

                if version != VERSION:
                    self.isNewVersion = True

                return True 
            except Exception as e:
                print(f"Попытка {i+1} не удалась: {e}")
                await asyncio.sleep(retry_delay) 
          

    

    def isConnected(self):
        return self.writer is not None and not self.writer.is_closing()


    async def getJson(self):
        try:
            line = await self.reader.readuntil(b'\n')        
            return json.loads(line.decode('utf-8'))
        except (asyncio.IncompleteReadError, json.JSONDecodeError, TypeError):
            return None


    async def send_line(self, text: str):
        self.writer.write((text + "\n").encode("utf-8"))
        await self.writer.drain()   


    async def recv_line(self) -> str:
        line = await self.reader.readline()
        return line.decode("utf-8").rstrip("\n")
    

    async def getVersion(self):
        await self.sendJsonCommand({"command": "VERSION"})
        response = await self.getJson()
        return response.get("version") if response else None

    async def login(self, username, password):
        async with self.lock:
            await self.sendJsonCommand({"command": "LOGIN", "username": username, "password": password})
            response = await self.getJson()
            if response and response.get("status") == "OK":
                self.isAuthorized = True
                self.config.set("username", username)
                self.config.set("password", password)            
                self.isAdmin = response.get("isAdmin", False)
                print(response)

            return response
        

    async def register(self, username, password):
        async with self.lock:
            await self.sendJsonCommand({"command": "REGISTER", "username": username, "password": password})
            response = await self.getJson()
            if response and response.get("status") == "OK":
                self.config.set("username", username)
                self.config.set("password", password)
            return response
    

    async def addFriend(self, friend):
        if not self.isAuthorized:
            return False

        await self.sendJsonCommand({"command": "ADDFRIEND", "friend": friend})
        
        response = await self.getJson()

        if response and response.get("status") == "OK":
            return response
        
        return response


    async def deleteFriend(self, friend):
        if not self.isAuthorized:
            return False
        
        await self.sendJsonCommand({"command": "DELETEFRIEND", "friend": friend})

        response = await self.getJson()

        if response and response.get("status") == "OK":
            return response
        
        return response
        

    async def rejectFriend(self, friend):
        if not self.isAuthorized:
            return False
        
        await self.sendJsonCommand({"command": "REJECTFRIEND", "friend": friend})

        response = await self.getJson()

        if response and response.get("status") == "OK":
            return response
        
        return response
    

    async def acceptFriend(self, friend):
        if not self.isAuthorized:
            return False
        
        await self.sendJsonCommand({"command": "ACCEPTFRIEND", "friend": friend})

        response = await self.getJson()

        if response and response.get("status") == "OK":
            return response
        
        return response
    


    async def friendList(self):
        if not self.isAuthorized: return None
        async with self.lock:
            await self.sendJsonCommand({"command": "FRIENDLIST"})
            response = await self.getJson()
            if response and response.get("status") == "OK":
                return list(response.get("friends"))
        return None

    

    async def disconnect(self):
        if not self.isAuthorized:
            return False
        await self.sendJsonCommand({"command": "DISCONNECT"})
        response = await self.getJson()

        self.writer.close()
        await self.writer.wait_closed()
        self.isAuthorized = False
        return response
        

    async def sendMessage(self, text, receiver):
        if not self.isAuthorized: return None
        async with self.lock:
            await self.sendJsonCommand({"command": "SENDMESSAGE", "receiver": receiver, "message": text})
            return await self.getJson()
    
    
    async def requestList(self):
        if not self.isAuthorized: return None
        async with self.lock:
            await self.sendJsonCommand({"command": "REQUESTLIST"})
            response = await self.getJson()
            return list(response.get("requests")) if response and response.get("status") == "OK" else None
    


    async def getChat(self, friend):
        if not self.isAuthorized: return []
        async with self.lock:
            await self.sendJsonCommand({"command": "GETCHAT", "friend": friend})
            response = await self.getJson()
            return response.get("messages", []) if response and response.get("status") == "OK" else []
    


class registerWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        # Основной вертикальный лейаут
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(50, 50, 50, 50)
        main_layout.setSpacing(20)

        # Заголовок окна
        title = QLabel("Zgram")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title)


        self.statusLabel = QLabel(f"connection status: {self.mainWindow.client.isConnected()}")
        main_layout.addWidget(self.statusLabel)

        # Поля ввода
        self.usernameInput = QLineEdit()
        self.usernameInput.setPlaceholderText("Login")
        self.passwordInput = QLineEdit()
        self.passwordInput.setPlaceholderText("Password")
        self.passwordInput.setEchoMode(QLineEdit.EchoMode.Password)

        main_layout.addWidget(self.usernameInput)
        main_layout.addWidget(self.passwordInput)

        # Горизонтальный лейаут для кнопок
        button_layout = QHBoxLayout()
        btnLogin = QPushButton("Log in")
        btnLogin.clicked.connect(self.onLoginClick)
        btnLogin.setFixedHeight(50)
        btnRegister = QPushButton("Register")
        btnRegister.setFixedHeight(50)
        btnRegister.clicked.connect(self.onRegisterClick)

        button_layout.addWidget(btnLogin)
        button_layout.addWidget(btnRegister)
        main_layout.addLayout(button_layout)

        # Spacer для оставшегося места под картинку
        main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Картинка снизу (можно заменить на логотип или любую картинку)
        self.image_label = QLabel()
        pixmap = QPixmap("shadow.jpeg")  # укажите путь к изображению
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaledToWidth(400, Qt.TransformationMode.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(self.image_label)

        # Устанавливаем лейаут
        self.setLayout(main_layout)


    
    async def updateStatus(self):
        status = self.mainWindow.client.isConnected()
        self.statusLabel.setText(f"connection status: {status}")




    @asyncSlot()
    async def onLoginClick(self):
        user = self.usernameInput.text()
        password = self.passwordInput.text()

        if not user or not password:
            print("no password or username")
            return 

        if not self.mainWindow.client.isConnected():
            await self.mainWindow.client.connect()
            await self.updateStatus()


        if not self.mainWindow.client.isConnected():
            print("no connection")
            return 

        response = await self.mainWindow.client.login(user, password)

        if self.mainWindow.client.isAuthorized:
            self.mainWindow.settings_screen.updateAdminButton()
            self.mainWindow.switch_screen(1)
        else:
            error_text = response.get("comment") if response else "Неверные данные"
            print(f"Ошибка входа: {error_text}")
            self.passwordInput.clear()

    @asyncSlot()
    async def onRegisterClick(self):
        user = self.usernameInput.text()
        password = self.passwordInput.text()

        if not user or not password:
            print("no password or username")
            return 

        if not self.mainWindow.client.isConnected():
            await self.mainWindow.client.connect()

        if not self.mainWindow.client.isConnected():
            print("no connection")
            return 

        response = await self.mainWindow.client.register(user, password)

        if response and response.get("status") == "OK":
            print("Registration success! Logging in...")
            await self.mainWindow.client.login(user, password)

            if self.mainWindow.client.isAuthorized:
                self.settings_screen.updateAdminButton()
                self.mainWindow.switch_screen(1)
        else:   
            print(f"Registration error: {response}")





class AdminWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        layout = QHBoxLayout()
        
        btnBack = QPushButton("back")
        btnBack.clicked.connect(lambda: self.mainWindow.switch_screen(1))
        layout.addWidget(btnBack)


        self.adminList = QListWidget()
        layout.addWidget(QLabel("All users:"))
        layout.addWidget(self.adminList)

        
        btnRefresh = QPushButton("Refresh list")
        btnRefresh.clicked.connect(lambda: asyncio.create_task(self.loadUsers()))
        layout.addWidget(btnRefresh)




    async def loadUsers(self):
        if not self.mainWindow.client.isAuthorized:
            return
        
        await self.mainWindow.client.sendJsonCommand({"command": "GETALLUSERS"})
        response = await self.mainWindow.client.getJson()

        self.adminList.clear()
        if response and response.get("status") == "OK":
            for user in response.get("users", []):
                self.adminList.addItem(user)

        




class chatsWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow


        mainLayout = QHBoxLayout()

        leftPanel = QVBoxLayout()

        self.friendList = QListWidget()
        self.friendList.itemClicked.connect(self.onFriendSelected)

        btnSettings = QPushButton("Settings")
        btnSettings.clicked.connect(lambda: self.mainWindow.switch_screen(2))

        btnFriends = QPushButton("Friends")
        btnFriends.clicked.connect(lambda: self.mainWindow.switch_screen(3))


        leftPanel.addWidget(QLabel("<b>Friends:</b>"))
        leftPanel.addWidget(self.friendList)
        leftPanel.addWidget(btnSettings)
        leftPanel.addWidget(btnFriends)

        rightPanel = QVBoxLayout()  

        self.chatLabel = QLabel("Select friend for chatting")            
        self.messagesArea = QTextEdit()
        self.messagesArea.setReadOnly(True) 

        self.msgInput = QLineEdit(placeholderText="Your message")

        self.msgInput.returnPressed.connect(self.onSendMessage)

        btnSend = QPushButton("Send")
        btnSend.clicked.connect(self.onSendMessage)

        rightPanel.addWidget(self.chatLabel)
        rightPanel.addWidget(self.messagesArea)
        rightPanel.addWidget(self.msgInput)
        rightPanel.addWidget(btnSend)

        mainLayout.addLayout(leftPanel, 1)
        mainLayout.addLayout(rightPanel, 3)
        self.setLayout(mainLayout)
        
    
    def onFriendSelected(self, item):
        friend = item.text()
        asyncio.create_task(self.loadChat(friend))


    async def loadFriends(self):
        friends = await self.mainWindow.client.friendList()
        self.friendList.clear()
        if friends:        
            for friend in friends:
                self.friendList.addItem(friend)


    
    async def loadChat(self, friend):
        self.messagesArea.clear()
        self.chatLabel.setText(friend)
        messages = await self.mainWindow.client.getChat(friend)
        for msg in messages:
            sender = msg["sender"]
            text = msg["text"]
            self.messagesArea.append(f"<b>{sender}:</b> {text}")

        scroll = self.messagesArea.verticalScrollBar()
        scroll.setValue(scroll.maximum())


    @asyncSlot()
    async def onSendMessage(self):
        text = self.msgInput.text()
        current_item = self.friendList.currentItem()

        if not text or not current_item:
            return 
        
        friend = current_item.text()

        response = await self.mainWindow.client.sendMessage(text, friend)

        if response and response.get("status") == "OK":
            self.messagesArea.append(f"<b>You:</b> {text}")

            scroll = self.messagesArea.verticalScrollBar()
            scroll.setValue(scroll.maximum())

            self.msgInput.clear()


from PyQt6.QtWidgets import QComboBox

class settingsWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow


        layout = QVBoxLayout()
        

        self.infoLabel = QLabel("Settings")
        self.infoLabel.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(self.infoLabel)
        
        self.btnAccount = QPushButton("Account Info")
        self.btnAccount.clicked.connect(lambda: self.mainWindow.switch_screen(5))
        
        layout.addWidget(self.btnAccount)


        theme_layout = QHBoxLayout()
        themeLabel = QLabel("Выберите тему:")
        self.themeList = QComboBox()
        self.themeList.addItems(["Светлая", "Темная", "Морская"])
        

        self.labelVersion = QLabel(f"ваша версия: {VERSION}")

        self.latestVersion = QLabel(f"актуальная версия: {self.mainWindow.client.serverVersion}")
    
        layout.addWidget(self.labelVersion)
        layout.addWidget(self.latestVersion)
        
        autostartCheck = QCheckBox("Запуск при старте системы")
        is_active = getattr(self.mainWindow.config, 'autostart', False)
        autostartCheck.setChecked(is_active)
        autostartCheck.stateChanged.connect(self.toggleAutostart)
        
        layout.addWidget(autostartCheck)

        

        currentTheme = self.mainWindow.config.theme
        mapping = {"light": 0, "dark": 1, "blue": 2}
        self.themeList.setCurrentIndex(mapping.get(currentTheme, 0))
        self.themeList.currentIndexChanged.connect(self.onChangeTheme)

        theme_layout.addWidget(themeLabel)
        theme_layout.addWidget(self.themeList)
        layout.addLayout(theme_layout)

        
        layout.addStretch() 


        btnBack = QPushButton("Back")
        btnBack.clicked.connect(lambda: self.mainWindow.switch_screen(1))
        

        self.btnAdmin = QPushButton("AdminPanel")
        self.btnAdmin.clicked.connect(lambda: self.mainWindow.switch_screen(4))
        self.btnAdmin.setVisible(True)
        layout.addWidget(self.btnAdmin)



        layout.addWidget(btnBack)

        self.setLayout(layout)

    def updateAdminButton(self):
        print("isAdmin:", self.mainWindow.client.isAdmin)
        if self.mainWindow.client.isAdmin:
            self.btnAdmin.setVisible(True)


    def onChangeTheme(self, themeIndex):
        themes = ["light", "dark", "blue"]
        selected_theme = themes[themeIndex]
        self.mainWindow.apply_theme(selected_theme)


    def toggleAutostart(self, state):
        is_checked = (state == 2) # 2 — это Qt.CheckState.Checked
        self.mainWindow.config.set("autostart", is_checked)

        # Путь к папке автозапуска Linux
        autostart_folder = os.path.expanduser("~/.config/autostart/")
        desktop_file_path = os.path.join(autostart_folder, "fake_telegram.desktop")

        if is_checked:
            # Создаем папку, если её нет
            if not os.path.exists(autostart_folder):
                os.makedirs(autostart_folder)

            # Собираем пути: к интерпретатору python из venv и к самому скрипту
            python_exe = sys.executable
            script_path = os.path.abspath(sys.argv[0])

            desktop_entry = f"""[Desktop Entry]
    Type=Application
    Exec={python_exe} {script_path}
    Hidden=false
    NoDisplay=false
    X-GNOME-Autostart-enabled=true
    Name=Z ZOV GRAM
    Comment=Messenger Client
    """
            with open(desktop_file_path, "w") as f:
                f.write(desktop_entry)
            print("Автозагрузка включена")
        else:
            # Если галочку сняли — удаляем файл
            if os.path.exists(desktop_file_path):
                os.remove(desktop_file_path)
                print("Автозагрузка отключена")
       


class friendsWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        # Основной горизонтальный лейаут
        mainLayout = QHBoxLayout()
        mainLayout.setContentsMargins(20, 20, 20, 20)
        mainLayout.setSpacing(20)



        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(1300)  
        self.refresh_timer.timeout.connect(self.updateData)
        self.refresh_timer.start()

        leftPanel = QVBoxLayout()

        addLayout = QHBoxLayout()
        self.addInput = QLineEdit(placeholderText="Friend's username")
        btnAdd = QPushButton("Add")
        btnAdd.setFixedHeight(40)
        btnAdd.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btnAdd.clicked.connect(self.onAddFriend)
        self.addInput.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        addLayout.addWidget(self.addInput)
        addLayout.addWidget(btnAdd)
        leftPanel.addLayout(addLayout)

        # Список входящих запросов
        leftPanel.addWidget(QLabel("<b>Friend requests</b>"))
        self.requestList = QListWidget()
        self.requestList.setFixedWidth(200)
        leftPanel.addWidget(self.requestList)

        # Кнопки принять/отклонить
        reqButtons = QHBoxLayout()
        btnAccept = QPushButton("Accept")
        btnReject = QPushButton("Reject")
        for btn in [btnAccept, btnReject]:
            btn.setFixedHeight(40)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btnAccept.clicked.connect(self.onAcceptFriend)
        btnReject.clicked.connect(self.onRejectFriend)
        reqButtons.addWidget(btnAccept)
        reqButtons.addWidget(btnReject)
        leftPanel.addLayout(reqButtons)

        mainLayout.addLayout(leftPanel)

        # Правая панель — список друзей
        rightPanel = QVBoxLayout()
        rightPanel.addWidget(QLabel("<b>Your friends</b>"))
        self.friendsList = QListWidget()
        rightPanel.addWidget(self.friendsList)

        btnDelete = QPushButton("Delete Friend")
        btnDelete.setFixedHeight(40)
        btnDelete.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btnDelete.clicked.connect(self.onDeleteFriend)
        rightPanel.addWidget(btnDelete)

        btnBack = QPushButton("Back to chats")
        btnBack.setFixedHeight(40)
        btnBack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btnBack.clicked.connect(lambda: self.mainWindow.switch_screen(1))
        rightPanel.addWidget(btnBack)

        mainLayout.addLayout(rightPanel, stretch=1)
        self.setLayout(mainLayout)

    async def loadData(self):
        """Загрузка друзей и запросов"""
        friends = await self.mainWindow.client.friendList()
        self.friendsList.clear()
        if isinstance(friends, list):
            for f in friends:
                self.friendsList.addItem(f)

        requests = await self.mainWindow.client.requestList()
        self.requestList.clear()
        if isinstance(requests, list):
            for r in requests:
                self.requestList.addItem(r)

    
    @asyncSlot()
    async def updateData(self):
        try:
            friends = await self.mainWindow.client.friendList()
            requests = await self.mainWindow.client.requestList()

            self.friendsList.clear()
            if friends:
                for f in friends:
                    self.friendsList.addItem(f)

            self.requestList.clear()
            if requests:
                for r in requests:
                    self.requestList.addItem(r)
        except Exception as e:
            print("Ошибка автообновления друзей:", e)

    

    @asyncSlot()
    async def onAddFriend(self):
        name = self.addInput.text().strip()
        if name:
            await self.mainWindow.client.addFriend(name)
            self.addInput.clear()
            await self.loadData()

    @asyncSlot()
    async def onAcceptFriend(self):
        item = self.requestList.currentItem()
        if item:
            friend_name = item.text()
            
            requests = await self.mainWindow.client.requestList()
            if friend_name not in requests:
                print(f"No pending request from {friend_name}")
                return
            response = await self.mainWindow.client.acceptFriend(friend_name)
            print(f"Accepted {friend_name}: {response}")
            await self.loadData()

    @asyncSlot()
    async def onRejectFriend(self):
        item = self.requestList.currentItem()
        if item:
            await self.mainWindow.client.rejectFriend(item.text())
            await self.loadData()

    @asyncSlot()
    async def onDeleteFriend(self):
        item = self.friendsList.currentItem()
        if item:
            await self.mainWindow.client.deleteFriend(item.text())
            await self.loadData()



class AccountWindow(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Никнейм сверху
        self.labelUsername = QLabel(f"username: {self.mainWindow.client.username}")
        self.labelUsername.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.labelUsername.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.labelUsername)

        # Растягивающийся spacer, чтобы кнопки ушли вниз
        main_layout.addStretch()

        # Кнопки Back и Logout внизу по центру
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btnBack = QPushButton("Back")
        btnBack.setFixedSize(120, 30)  # маленькая кнопка
        btnBack.clicked.connect(lambda: self.mainWindow.switch_screen(2))
        bottom_layout.addWidget(btnBack)

        btnLogout = QPushButton("Log out")
        btnLogout.setFixedSize(120, 30)  # маленькая кнопка
        btnLogout.clicked.connect(self.onLogout)
        bottom_layout.addWidget(btnLogout)

        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def updateUsername(self):
        self.labelUsername.setText(f"username: {self.mainWindow.client.username}")

    @asyncSlot()
    async def onLogout(self):
        await self.mainWindow.client.disconnect()
        self.mainWindow.config.set("username", None)
        self.mainWindow.config.set("password", None)
        self.mainWindow.switch_screen(0)

    



class mainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.config = Config("config.json")
        self.client = Client(self.config)
        
        self.setWindowTitle("Zgram")
        self.resize(800, 500)

        self.apply_theme(self.config.theme)

        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.login_screen = registerWindow(self)
        self.chat_screen = chatsWindow(self)
        self.settings_screen = settingsWindow(self)
        self.friends_screen = friendsWindow(self)
        self.admin_screen = AdminWindow(self)
        self.account_screen = AccountWindow(self)

        self.stacked.addWidget(self.login_screen)
        self.stacked.addWidget(self.chat_screen)
        self.stacked.addWidget(self.settings_screen)
        self.stacked.addWidget(self.friends_screen)
        self.stacked.addWidget(self.admin_screen)
        self.stacked.addWidget(self.account_screen)
    

    def apply_theme(self, theme_name):
        themes_qss = {
            "light": "QWidget { background-color: white; color: black; }",
            "dark": "QWidget { background-color: #17212b; color: white; }",
            "blue": "QWidget { background-color: #0088cc; color: white; }"
        }
        
        style = themes_qss.get(theme_name, themes_qss["light"])
        self.setStyleSheet(style)
        
        
        self.config.set("theme", theme_name)



    def switch_screen(self, index):
        self.stacked.setCurrentIndex(index)
        if index == 1:
            asyncio.create_task(self.chat_screen.loadFriends())


        if index == 2:  
            server_version = self.client.serverVersion or "неизвестно"
            self.settings_screen.latestVersion.setText(f"актуальная версия: {server_version}")

            
                        
            if self.client.isNewVersion and not hasattr(self.settings_screen, "btnUpdateAdded"):
                self.settings_screen.btnUpdate = QPushButton("обновить клиент")
                self.settings_screen.btnUpdate.clicked.connect(self.onUpdateClient)
                self.settings_screen.layout().insertWidget(2, self.settings_screen.btnUpdate)  
                self.settings_screen.btnUpdateAdded = True


        if index == 3:
            asyncio.create_task(self.friends_screen.loadData())

        if index == 4:
            if self.client.isAdmin:
                asyncio.create_task(self.admin_screen.loadUsers())
                self.stacked.setCurrentIndex(4)
            else:
                print("Нет прав администратора")

        if index == 5:
            async def load_account():
                await self.client.getInitials()
                self.account_screen.updateUsername()
                self.stacked.setCurrentIndex(5)
            
            asyncio.create_task(load_account())


        
    def onUpdateClient(self):
        subprocess.run([sys.executable, "updater.py"])
        sys.exit()



    async def autologin(self):
        username = self.config.username
        password = self.config.password

        if not username or not password:
            return
        
        await self.client.connect()

        if not self.client.isConnected():
            return

        response = await self.client.login(username, password)

        if self.client.isConnected():
            self.switch_screen(1)

        else:
            print(response)




def main():
    app = QApplication(sys.argv)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    main_win = mainWindow()
    main_win.show()

    # автологин выполняем после запуска цикла
    async def start_autologin():
        await main_win.autologin()

    with loop:
        loop.create_task(start_autologin())
        loop.run_forever()



if __name__ == "__main__":
    main()