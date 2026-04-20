import sqlite3 as sq



connection = sq.connect("/home/jenya/coding/Zgram/server/users.db")
cursor = connection.cursor()

def giveAdmin(username):
    cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
    if cursor.rowcount == 0:
        print(f"Пользователь {username} не найден")
    else:
        print(f"Пользователю {username} выданы права администратора")
    connection.commit()

username = input("username: ")
username.strip()
giveAdmin(username)