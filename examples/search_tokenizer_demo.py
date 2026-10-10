from app.search import SearchTokenizer


def main() -> None:
    tokenizer = SearchTokenizer()

    cases = [
        "检查代码有没有线程安全问题",
        "SkillVectorIndex 和 Recall@K 是什么关系",
        "检查 OAuth2.0 API 是否存在 SQL 注入风险",
        "帮我用 Python 写一个读取 CSV 文件的函数",
        "根据文档解释一下 MRR 指标怎么计算",
        "把这个模块重构一下，降低代码耦合度",
    ]

    for text in cases:
        print("=" * 80)
        print("TEXT:")
        print(text)

        print("TOKENS:")
        print(
            tokenizer.tokenize(text)
        )

        print()


if __name__ == "__main__":
    main()