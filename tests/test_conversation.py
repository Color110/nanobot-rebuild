from app.conversation import (
    SYSTEM_PROMPT,
    add_message,
    create_conversation,
    format_history,
)


def test_create_conversation():
    messages = create_conversation()

    assert messages == [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]


def test_add_message():
    messages = create_conversation()

    add_message(
        messages,
        role="user",
        content="你好",
    )

    assert messages[-1] == {
        "role": "user",
        "content": "你好",
    }


def test_multi_turn_history():
    messages = create_conversation()

    add_message(
        messages,
        role="user",
        content="我叫张三",
    )

    add_message(
        messages,
        role="assistant",
        content="你好张三",
    )

    add_message(
        messages,
        role="user",
        content="我叫什么？",
    )

    assert len(messages) == 4

    assert messages[1]["content"] == "我叫张三"
    assert messages[2]["content"] == "你好张三"
    assert messages[3]["content"] == "我叫什么？"


def test_format_history():
    messages = create_conversation()

    add_message(
        messages,
        role="user",
        content="hello",
    )

    history = format_history(messages)

    assert "[system]" in history
    assert "[user] hello" in history