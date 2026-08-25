import pytest

from app.conversation import add_message
from app.session import SessionManager


def test_create_new_session(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("demo")

    assert session.session_id == "demo"
    assert session.messages[0]["role"] == "system"


def test_save_and_restore_session(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("demo")

    add_message(session.messages, role="user", content="我叫张三")
    add_message(session.messages, role="assistant", content="你好张三")

    manager.save(session)

    # 故意创建一个新的 Manager，模拟程序重启后的新进程。
    new_manager = SessionManager(tmp_path)
    restored = new_manager.load("demo")

    assert restored is not None
    assert restored.session_id == "demo"
    assert restored.messages == session.messages


def test_session_isolation(tmp_path):
    manager = SessionManager(tmp_path)

    alice = manager.get_or_create("alice")
    bob = manager.get_or_create("bob")

    add_message(alice.messages, "user", "我是Alice")
    add_message(bob.messages, "user", "我是Bob")

    manager.save(alice)
    manager.save(bob)

    restored_alice = manager.load("alice")
    restored_bob = manager.load("bob")

    assert restored_alice is not None
    assert restored_bob is not None
    assert restored_alice.messages[-1]["content"] == "我是Alice"
    assert restored_bob.messages[-1]["content"] == "我是Bob"


def test_tool_history_is_persisted(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("tool-test")

    session.messages.extend([
        {
            "role": "user",
            "content": "计算12乘8",
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"left":12,"operator":"*","right":8}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "96",
        },
        {
            "role": "assistant",
            "content": "12乘8等于96",
        },
    ])

    manager.save(session)

    restored = manager.load("tool-test")

    assert restored is not None
    assert restored.messages == session.messages


def test_invalid_session_id(tmp_path):
    manager = SessionManager(tmp_path)

    with pytest.raises(ValueError):
        manager.get_or_create("../../secret")


def test_clear_session(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("demo")

    add_message(session.messages, "user", "hello")

    session.clear()

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "system"


def test_atomic_save_leaves_no_temp_file(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("demo")

    manager.save(session)

    temp_files = list(tmp_path.glob("*.tmp"))

    assert temp_files == []