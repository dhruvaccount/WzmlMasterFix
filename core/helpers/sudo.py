_sudo_users = set()
_auth_chats = set()


def load_sudo_users(users: dict) -> None:
    global _sudo_users, _auth_chats
    _sudo_users.clear()
    _auth_chats.clear()
    for uid, data in users.items():
        if isinstance(data, dict):
            if data.get("SUDO"):
                _sudo_users.add(uid)
            if data.get("AUTH"):
                _auth_chats.add(uid)


def is_sudo_user(user_id: int) -> bool:
    return user_id in _sudo_users


def is_authorized_user(user_id: int) -> bool:
    return user_id in _sudo_users or user_id in _auth_chats


def add_sudo_user(user_id: int) -> None:
    _sudo_users.add(user_id)


def remove_sudo_user(user_id: int) -> None:
    _sudo_users.discard(user_id)


def get_sudo_users() -> set:
    return _sudo_users.copy()


def add_auth_chat(chat_id: int) -> None:
    _auth_chats.add(chat_id)


def remove_auth_chat(chat_id: int) -> None:
    _auth_chats.discard(chat_id)


def get_auth_chats() -> set:
    return _auth_chats.copy()
