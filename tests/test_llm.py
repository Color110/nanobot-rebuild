from app.llm import build_messages


def test_build_messages():
    messages = build_messages("你好")

    assert messages == [
        {
            "role": "user",
            "content": "你好",
        }
    ]
