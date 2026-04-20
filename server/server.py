import socket 
import sqlite3 as sq
import hashlib
import os
import hmac
import threading
import json


CHUNK_SIZE = 1024 * 64


def getVersion():
    version = open("server/version.txt", 'r')
    return version.read()
    
#-------------------------------------------------------------

class Config:
    def __init__(self, path: str, defaults: dict | None = None):
        self._path = path
        self._data = defaults or {}

        self.load()

    def load(self):
        if not os.path.exists(self._path):
            self.save()
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._data.update(data)

        except Exception as e:
            print("Config load error:", e)

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
        except Exception as e:
            print("Config save error:", e)

    def __getattr__(self, item):
        return self._data.get(item)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self._data[key] = value

#----------------------------------------------------------

class User:
    def __init__(self, username, is_admin):
        self.username = username
        self.is_admin = is_admin

#----------------------------------------------------------

class ClientSession:
    def __init__(self, sock, addr, config: Config):
        self._recv_buffer = b""
        self.sock = sock
        self.addr = addr 
        self.user: User = None

        self.config = config


        self.connection = sq.connect(self.config.database_path, check_same_thread=False, timeout=10)
        

        
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys = ON")



        
        self.cursor = self.connection.cursor()
        
        
        #таблица с юзерами
        self.users_table = '''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, 
        username TEXT UNIQUE CHECK(length(username) <=16), 
        hash_password BLOB  , 
        salt BLOB, 
        is_admin INTEGER, 
        is_banned INTEGER)'''
        self.cursor.execute(self.users_table)

        # таблица с сообщениями
        self.messages_table = '''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY, 
        sender TEXT,
        receiver TEXT,
        text TEXT, 
        message_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender) REFERENCES users(username) ON DELETE CASCADE,
        FOREIGN KEY (receiver) REFERENCES users(username) ON DELETE CASCADE) '''

        self.cursor.execute(self.messages_table)

        #таблица с связками друзей
        self.friendship_table = '''CREATE TABLE IF NOT EXISTS friendship (id INTEGER PRIMARY KEY, 
        user_username TEXT, 
        friend_username TEXT, 
        status DEFAULT 'requested',
        FOREIGN KEY (user_username) REFERENCES users(username) ON DELETE CASCADE, 
        FOREIGN KEY (friend_username) REFERENCES users(username) ON DELETE CASCADE, 
        UNIQUE(user_username, friend_username))'''

        self.cursor.execute(self.friendship_table)

        self.connection.commit()

    def return_response(self, status, comment):
        return {"status": status, "comment": comment}


    def register(self, username, password):
        if self.get_user(username):
            return self.return_response("ERROR", "this user already registed")
        
        salt = os.urandom(16)
        hashed_password = hashlib.pbkdf2_hmac("sha256", password.encode("UTF-8"), salt, 200000)
        try:
            self.connection.execute("INSERT INTO users (username, hash_password, salt, is_admin, is_banned) VALUES (?, ?, ?, 0, 0)", (username, hashed_password, salt))
            self.connection.commit()
            return self.return_response("OK", "registed")


        except Exception:
            return self.return_response("ERROR", "unknown error (register)")

    def login(self, username, password):
        if not self.get_user(username):
            return {"status": "ERROR", "comment": "invalid password or username"}

        self.cursor.execute("SELECT salt, hash_password, is_banned, is_admin FROM users WHERE username = ?", (username,))
        result = self.cursor.fetchone()
        if not result:
            return {"status": "ERROR", "comment": "invalid password or username"}

        salt, hash_db, is_banned, is_admin = result
        hash_db = bytes(hash_db)

        if is_banned:
            return {"status": "ERROR", "comment": "this user banned"}

        hash_new = hashlib.pbkdf2_hmac("sha256", password.encode("UTF-8"), salt, 200000)

        if hmac.compare_digest(hash_new, hash_db):
            self.user = User(username=username, is_admin=bool(is_admin))
            return {"status": "OK", "comment": "logined", "isAdmin": bool(is_admin)}
        else:
            return {"status": "ERROR", "comment": "invalid password or username"}

    def ban_user(self, actor, banned_user):
        actor_user = self.get_user(actor)

        if not actor_user:
            return self.return_response("ERROR", "actor not found")

        # проверяем что actor админ
        self.cursor.execute("SELECT is_admin FROM users WHERE username = ?", (actor,))
        row = self.cursor.fetchone()

        if not row or not row[0]:
            return self.return_response("ERROR", "not admin")

        if not self.get_user(banned_user):
            return self.return_response("ERROR", "user not found")

        self.cursor.execute(
            "UPDATE users SET is_banned = 1 WHERE username = ?",
            (banned_user,)
        )
        self.connection.commit()

        return self.return_response("OK", "user banned")


    def unban_user(self, actor, banned_user):
        actor_user = self.get_user(actor)
        if not actor_user:
            return self.return_response("ERROR", "actor not found")

        # проверяем что actor админ
        self.cursor.execute("SELECT is_admin FROM users WHERE username = ?", (actor,))
        row = self.cursor.fetchone()

        if not row or not row[0]:
            return self.return_response("ERROR", "not admin")

        if not self.get_user(banned_user):
            return self.return_response("ERROR", "user not found")

        self.cursor.execute(
            "UPDATE users SET is_banned = 0 WHERE username = ?",
            (banned_user,)
        )
        self.connection.commit()

        return self.return_response("OK", "user unbanned")


    def friend_list(self, user):
        self.cursor.execute("""
    SELECT 
        CASE WHEN user_username = ? THEN friend_username ELSE user_username END AS friend
    FROM friendship
    WHERE status = 'accepted' AND (user_username = ? OR friend_username = ?)
    """, (user, user, user))


        friends = [row[0] for row in self.cursor.fetchall()]
        return {"status": "OK", "friend_list": friends}
        

    def ban_list(self):
        if not self.user.is_admin:
            return self.return_response("ERROR", "not admin")

        self.cursor.execute(
            "SELECT username FROM users WHERE is_banned = 1"
        )

        banned_users = [row[0] for row in self.cursor.fetchall()]

        return {
            "status": "OK",
            "banned_users": banned_users
        }


    def requests_list(self, user):
        self.cursor.execute("SELECT user_username FROM friendship WHERE friend_username = ? AND status = 'requested'", (user,))
        requests_list = self.cursor.fetchall()
        request_list = [req[0] for req in requests_list]
        return {"status": "OK", "requests": request_list}


    def add_friend(self, friend1, friend2):

        if friend1 == friend2:
            return self.return_response("ERROR", "you can't add yourself")

        if not self.get_user(friend2):
            return self.return_response("ERROR", f"user {friend2} not found")

        # проверяем существование любой записи
        self.cursor.execute(
            """
            SELECT status FROM friendship
            WHERE (user_username=? AND friend_username=?)
            OR (user_username=? AND friend_username=?)
            """,
            (friend1, friend2, friend2, friend1)
        )

        row = self.cursor.fetchone()

        if row:
            status = row[0]

            if status == "accepted":
                return self.return_response("ERROR", "already friends")

            if status == "requested":
                return self.return_response("ERROR", "request already sent")

        # создаём заявку
        try:
            self.cursor.execute(
                "INSERT INTO friendship (user_username, friend_username, status) VALUES (?, ?, 'requested')",
                (friend1, friend2)
            )
            self.connection.commit()

            return self.return_response("OK", "request sent")

        except Exception as e:
            print(e)
            return self.return_response("ERROR", "database error")


    def accept_friend(self, friend1, friend2):
        # обновляем запись, если есть запрос
        self.cursor.execute(
            """
            UPDATE friendship
            SET status='accepted'
            WHERE user_username=? AND friend_username=? AND status='requested'
            """,
            (friend1, friend2)
        )

        if self.cursor.rowcount == 0:
            return self.return_response("ERROR", "no friend request")

        self.connection.commit()
        return self.return_response("OK", "friend accepted")

    def reject_friend(self, friend1, friend2):

        self.cursor.execute("DELETE FROM friendship WHERE user_username = ? AND friend_username = ? AND status = 'requested'", (friend2, friend1,))

        if self.cursor.rowcount == 0:
            return self.return_response("OK", "no friend request")
        self.connection.commit()
        return self.return_response("OK", "rejected")        


    def delete_friend(self, friend1, friend2):
        
        self.cursor.execute("DELETE FROM friendship WHERE (user_username = ? AND friend_username = ?) OR (user_username = ? AND friend_username = ?)", (friend1, friend2, friend2, friend1))
        
        if self.cursor.rowcount == 0:
            return self.return_response("ERROR", "not in friends")

        self.connection.commit()
        return self.return_response("OK", "deleted")
    


    def give_admin(self, actor, admin_user):
        if not self.get_user(actor):
            return self.return_response("ERROR", "actor not found")

        self.cursor.execute(
            "SELECT is_admin FROM users WHERE username = ?",
            (actor,)
        )
        row = self.cursor.fetchone()

        if  not row or not row[0]:
            return self.return_response("ERROR", "not admin")

        if not self.get_user(admin_user):
            return self.return_response("ERROR", "user not found")

        self.cursor.execute(
            "SELECT is_admin FROM users WHERE username = ?",
            (admin_user,)
        )
        row = self.cursor.fetchone()

        if row and row[0]:
            return self.return_response("ERROR", "user already admin")

        self.cursor.execute(
            "UPDATE users SET is_admin = 1 WHERE username = ?",
            (admin_user,)
        )

        self.connection.commit()

        return self.return_response("OK", "admin given")

    

    def remove_admin(self, actor, admin_user):
        if not self.get_user(actor):
            return self.return_response("ERROR", "actor not found")

        self.cursor.execute(
            "SELECT is_admin FROM users WHERE username = ?",
            (actor,)
        )
        row = self.cursor.fetchone()

        if not row or not row[0]:
            return self.return_response("ERROR", "not admin")

        if not self.get_user(admin_user):
            return self.return_response("ERROR", "user not found")

        self.cursor.execute(
            "SELECT is_admin FROM users WHERE username = ?",
            (admin_user,)
        )
        row = self.cursor.fetchone()

        if not row or not row[0]:
            return self.return_response("ERROR", "user is not admin")

        self.cursor.execute(
            "UPDATE users SET is_admin = 0 WHERE username = ?",
            (admin_user,)
        )

        self.connection.commit()

        return self.return_response("OK", "admin removed")


    def is_banned(self, user):
        if not self.get_user(user):
            return False
        self.cursor.execute("SELECT is_banned FROM users WHERE username = ?", (user,))
        row = self.cursor.fetchone()
        return bool(row and row[0])



    def is_friends(self, friend1, friend2):
        self.cursor.execute(
            """
            SELECT 1 FROM friendship
            WHERE (
                (user_username=? AND friend_username=?)
                OR
                (user_username=? AND friend_username=?)
            )
            AND status='accepted'
            """,
            (friend1, friend2, friend2, friend1)
        )
        return self.cursor.fetchone() is not None


    def get_user(self, user):
        self.cursor.execute("SELECT 1 FROM users WHERE username = ?", (user,))
        return self.cursor.fetchone() is not None        
        

    def get_chat(self, user, friend):

        if not self.get_user(user) or not self.get_user(friend):
            return {"status": "ERROR", "comment": "user not found"}

        if not self.is_friends(user, friend):
            return {"status": "ERROR", "comment": "not friends"}

        self.cursor.execute(
            """
            SELECT sender, text, message_time
            FROM messages
            WHERE (sender = ? AND receiver = ?)
            OR (sender = ? AND receiver = ?)
            ORDER BY message_time ASC
            """,
            (user, friend, friend, user)
        )

        rows = self.cursor.fetchall()

        messages = [
            {"sender": r[0], "text": r[1], "time": r[2]}
            for r in rows
        ]

        return {
            "status": "OK",
            "messages": messages
        }



    def send_message(self, sender, receiver, text: str):
        if text.strip() == "":
            return self.return_response("ERROR", "empty message")
        
        if not self.get_user(sender) or not self.get_user(receiver):
            return self.return_response("ERROR", "sender or receiver not found")

        if self.is_banned(sender):
            return self.return_response("ERROR", "user banned")
        
        if not self.is_friends(sender, receiver):
            return self.return_response("ERROR","not friends")
        
        self.cursor.execute("INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)", (sender, receiver, text))
        self.connection.commit()
        return self.return_response("OK", "message sent")
    
        
    def recv_line(self):
        while b"\n" not in self._recv_buffer:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("Client disconnected")
            self._recv_buffer += chunk
        line, _, self._recv_buffer = self._recv_buffer.partition(b"\n")
        return line.decode().strip()
    

    def send_line(self, text):
        self.sock.sendall((text + "\n").encode("utf-8"))


    def require_auth(self):
        if self.user is None:
            self.send_error("not authorized")
            return False

        if self.is_banned(self.user.username):
            self.send_error("user are banned")
            return False
    
        return True
    

    def send_error(self, comment):
        self.send_line(json.dumps({"status": "ERROR", "comment": comment}))
        


    def send_file(self, file_path):
        if not os.path.exists(file_path):
            self.send_error("file not found")
            return 
        
        filesize = os.path.getsize(file_path)
        self.send_line(json.dumps({"status": "OK", "size": filesize}))

        anser = self.recv_line()
        if anser != "READY":
            return

        hash_sha256 = hashlib.sha256()

        with open(file_path, "rb") as file:
            while chunk := file.read(1024):
                self.sock.sendall(chunk)
                hash_sha256.update(chunk)

        self.send_line(hash_sha256.hexdigest())


    def upload_file(self, filesize, filename, saveDir):
        try: 
            if not filename or not filesize:
                self.send_error("no filename or filesize")
        
            filesize = int(filesize)

            os.makedirs(saveDir, exist_ok=True)
            full_path = os.path.join(saveDir, filename)
            
            self.send_line("READY")

            received = 0
            hash_sha256 = hashlib.sha256()


            
            while received < filesize:
                chunk_size = min(CHUNK_SIZE, filesize - received)
                chunk = self.sock.recv(chunk_size)
                if not chunk:
                    raise ConnectionError("Client disconnected during upload")
                full_path_bytes = chunk
                with open(full_path, "ab") as f:
                    f.write(chunk)
                hash_sha256.update(chunk)
                received += len(chunk)


                client_hash = self.recv_line()
                server_hash = hash_sha256.hexdigest()
            
                if client_hash != server_hash:
                    self.send_error("hash mismatch")
                    os.remove(full_path)
                    return

                self.send_line(json.dumps({"status": "OK", "comment": f"file {filename} received"}))



        except Exception as e:
            self.send_error(e)




    def start(self):
        try:
            while True:
                try:
                    request = json.loads(self.recv_line())
                except json.JSONDecodeError:
                    self.send_error("invalid request")
                    continue

                command = request.get("command")

                if not command:
                    self.send_error("Unknown command in request")
                    continue

                if command == "REGISTER":
                    try:
                        username, password = request.get("username"), request.get("password")
                        if not username or not password:
                            self.send_error("empty username or password")
                            continue
                    except:
                        self.send_error("unknown error in REGISTER")
                        continue
                        
                    password = password.strip()
                        
                    if len(password) > 100 or len(password) < 6:
                        self.send_error("password is too small or big")
                        continue

                    # тут тоже надо сделать json
                    
                    if len(username) > 16 or len(username) < 3:
                        self.send_error("username is too small or big")
                        continue

                    result = self.register(username, password)
                    status = result["status"] 
                    comment = result["comment"]
                    #функция регистрации возращает не то, пофиксить
                                        
                    self.send_line(json.dumps({"status": status, "comment": comment}))


                elif command == "LOGIN":
                    try:
                        username, password = request.get("username"), request.get("password")
                        if not username or not password:
                            self.send_error("empty username or password")
                            continue
                    except:  
                        self.send_line(json.dumps({"status": "ERROR", "comment": "unknown error"}))
                        continue

                    result = self.login(username, password)
                    status = result["status"]   
                    comment = result["comment"]
                    self.send_line(json.dumps({"status": status, "comment": comment}))
                    # по идее тут будет непонятный result т.к. функция логин возращает непонятно что 



                elif command == "ADDFRIEND":
                    if not self.require_auth():
                        continue

                    try:
                        friend = request.get("friend")

                        if not friend: 
                            self.send_error("friend not found")
                            continue

                    except:
                        self.send_error("unknown error (ADDFRIEND)")
                        continue

                    try:
                        result = self.add_friend(self.user.username, friend)
                        status = result["status"]
                        comment = result["comment"]

                        self.send_line(json.dumps({"status": status, "comment": comment}))

                    except:
                        self.send_error("unknown error (addfriend)")
                        continue

            

                elif command == "DELETEFRIEND":
                    if not self.require_auth():
                        continue
                
                    try:
                        friend = request.get("friend") 

                        if not friend:
                            self.send_error("friend not found")
                            continue

                    except:
                        self.send_error("unknown error (DELETEFRIEND)")
                        continue

                    result = self.delete_friend(self.user.username, friend)

                    status = result["status"]
                    comment = result["comment"]                    
                    
                    self.send_line(json.dumps({"status": status, "comment": comment}))



                elif command == "REJECTFRIEND":
                    if not self.require_auth():
                        continue

                    try:
                        friend = request.get("friend")

                        if not friend:
                            self.send_error("Incorrect request")
                            continue
                    except:
                        self.send_error("unknown error (rejectfriend)")
                        continue


                    result = self.reject_friend(self.user.username, friend)

                    status = result["status"]
                    comment = result["comment"]
                    
                    self.send_line(json.dumps({"status": status, "comment": comment}))
                    

                elif command == "ACCEPTFRIEND":
                    if not self.require_auth():
                        continue

                    try:
                        friend = request.get("friend")

                        if not friend:
                            self.send_error("Incorrect request")
                            continue
                
                    except:
                        self.send_error("unknown error (acceptfriend)")

                    result = self.accept_friend(friend, self.user.username)

                    status = result["status"]
                    comment = result["comment"]
                    
                    self.send_line(json.dumps({"status": status, "comment": comment}))


                elif command == "FRIENDLIST":
                    if not self.require_auth():
                        continue

                    result = self.friend_list(self.user.username)
                    status = result["status"]
                    friend_list = result["friend_list"]


                    self.send_line(json.dumps({"status": status, "friends": friend_list}))         


                elif command == "DISCONNECT":
                    self.send_line(json.dumps({"status": "OK", "comment": "disconnected"}))
                    break

                elif command == "SENDMESSAGE":
                    if not self.require_auth():
                        continue

                    try:
                        receiver, message = request["receiver"], request["message"]
                        if not receiver or not message:
                            self.send_error("empty receiver or message")
                            continue


                    except:
                        self.send_error("unknown error (sendmessage)")
                        continue

                    result = self.send_message(self.user.username, receiver, message)

                    status = result["status"]
                    comment = result["comment"]

                    self.send_line(json.dumps({"status": status, "comment": comment}))
                

                elif command == "REQUESTLIST":
                    if not self.require_auth():
                        continue

                    result = self.requests_list(self.user.username)
                    status = result["status"]

                    request_list = result["requests"]


                    self.send_line(json.dumps({"status": status, "requests": request_list}))      




                elif command == "GETCHAT":

                    if not self.require_auth():
                        continue

                    friend = request.get("friend")

                    if not friend:
                        self.send_error("empty username")
                        continue

                    result = self.get_chat(self.user.username, friend)
                    self.send_line(json.dumps(result))


                elif command == "VERSION":
                    self.send_line(json.dumps({"status": "OK", "version":self.config.version}))


                elif command == "LATESTVERSION":
                    print("LATESTVERSION command received")
                    self.send_file(self.config.pathToClientBin)


                elif command == "BAN":
                    if not self.require_auth():
                        continue

                    if not self.user.is_admin:
                        self.send_error("not admin")
                        continue

                    banned_user = request.get("user")
                    result = self.ban_user(self.user.username, banned_user)
                    
                    self.send_line(json.dumps(result))


                elif command == "UNBAN":
                    if not self.require_auth():
                        continue

                    if not self.user.is_admin:
                        self.send_error("not admin")
                        continue

                    banned_user = request.get("user")
                    result = self.unban_user(self.user.username, banned_user)
                    
                    self.send_line(json.dumps(result))


                elif command == "BANLIST":
                    if not self.require_auth():
                        continue

                    if not self.user.is_admin:
                        self.send_error("not admin")
                        continue

                    result = self.ban_list()
                    self.send_line(json.dumps(result))


                elif command == "GIVEADMIN":
                    if not self.require_auth():
                        continue

                    if not self.user.is_admin:
                        self.send_error("not admin")
                        continue

                    user = request.get("user")

                    if not user:
                        self.send_error("user not specified")
                        continue

                    result = self.give_admin(self.user.username, user)
                    self.send_line(json.dumps(result))
                
                
                elif command == "REMOVEADMIN":
                    if not self.require_auth():
                        continue

                    if not self.user.is_admin:
                        self.send_error("not admin")
                        continue

                    user = request.get("user")

                    if not user:
                        self.send_error("user not specified")
                        continue

                    result = self.remove_admin(self.user.username, user)
                    self.send_line(json.dumps(result))


                elif command == "UPLOADFILE":
                    if not self.require_auth():
                        continue

                    filename = request.get("filename")
                    filesize = request.get("size")
                    
                    if not filename or not filesize:
                        self.send_error("missing filename or size")
                        continue

                    save_dir = self.config.upload_folder or "uploads"
                    self.upload_file(filesize, filename, save_dir)


                elif command == "USERDATA":
                    if not self.require_auth():
                        continue
                        
                        
                    self.send_line(json.dumps({"status": "OK", "username": f"{self.user.username}", "is_admin": f"{self.user.is_admin}"}))



        except Exception as e:
            print(f"error: {e}")


        finally:
            self.sock.close()
            self.connection.close()
        

#-----------------------------------------------------------------------

class Server:
    def __init__(self, config: Config):
        self.config = config
        
        self.port = self.config.port
        
        
        self.host = "0.0.0.0"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        print(f"server hosted on: {self.host}:{self.port}")

    def start(self):
        try:
            while True:
                client_sock, addr = self.sock.accept()
                session = ClientSession(client_sock, addr, self.config)
                threading.Thread(target=session.start, daemon=True).start()
        finally:
            self.sock.close()

#-------------------------------------------------------

x = "conf.json"


config = Config(os.path.join(x))

server = Server(config)
server.start()


# почту, логи сообщений, сделать конфиг и его настройку
# сделать понятнее class user, добавить к этому все функции: ban, unban

