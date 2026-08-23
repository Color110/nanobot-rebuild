from app.llm import ask_llm


def main() -> None:
    print("nanobot-rebuild")
    print("stage 1: single-turn LLM")
    print("输入 exit 退出")

    user_message = input("\nYou > ").strip()

    if user_message.lower() == "exit":
        print("Bye.")
        return

    if not user_message:
        print("输入不能为空。")
        return

    try:
        answer = ask_llm(user_message)
    except Exception as exc:
        print(f"\nLLM 调用失败: {exc}")
        return

    print(f"\nAssistant > {answer}")


if __name__ == "__main__":
    main()