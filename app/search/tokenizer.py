from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

import jieba


# 英文、技术标识符、版本号、错误码等。
#
# 尽量整体保留：
#   BM25
#   HNSW
#   OAuth2.0
#   Recall@K
#   code-review
#   IVF-PQ
#   P99
#   SkillVectorIndex
_TECHNICAL_TOKEN_PATTERN = re.compile(
    r"""
    [A-Za-z][A-Za-z0-9_.@/+:#-]*
    |
    \d+(?:\.\d+)*
    """,
    re.VERBOSE,
)


# 连续中文片段。
_CHINESE_BLOCK_PATTERN = re.compile(
    r"[\u3400-\u9fff]+"
)


# CamelCase / PascalCase 拆分。
#
# SkillVectorIndex
# →
# Skill / Vector / Index
_CAMEL_CASE_PATTERN = re.compile(
    r"""
    [A-Z]+(?=[A-Z][a-z]|\d|\b)
    |
    [A-Z]?[a-z]+
    |
    [A-Z]+
    |
    \d+
    """,
    re.VERBOSE,
)


# 第一版保持非常保守。
#
# 注意：
# “写、生成、检查、修复、比较、总结、解释”
# 这些虽然常见，但对 Skill Routing 是强意图词，
# 绝对不能当停用词删掉。
_DEFAULT_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "呢",
        "啊",
        "呀",
        "吧",
    }
)


# 这是稳定的 Skill / 软件工程领域术语，
# 不是从某几条 Eval Case 中临时抄出来的。
_DEFAULT_DOMAIN_TERMS = (
    "代码审查",
    "代码生成",
    "代码重构",
    "安全审计",
    "性能优化",
    "线程安全",
    "并发安全",
    "竞态条件",
    "单元测试",
    "集成测试",
    "压力测试",
    "异常处理",
    "错误处理",
    "资源泄漏",
    "内存泄漏",
    "路径遍历",
    "SQL注入",
    "权限控制",
    "权限绕过",
    "数据脱敏",
    "日志分析",
    "接口设计",
    "知识库",
    "向量检索",
    "混合检索",
    "语义检索",
    "关键词检索",
)


class SearchTokenizer:
    """
    面向检索场景的中英文混合 Tokenizer。

    设计目标：
    1. 中文使用 jieba 搜索模式。
    2. 尽量整体保留技术 Token。
    3. CamelCase 标识符额外拆词。
    4. 支持领域词典。
    5. 使用保守停用词策略。
    6. Query 与 Document 使用同一套分析逻辑。
    """

    def __init__(
        self,
        *,
        stopwords: Iterable[str] | None = None,
        domain_terms: Iterable[str] | None = None,
        use_default_stopwords: bool = True,
        use_default_domain_terms: bool = True,
    ) -> None:
        resolved_stopwords: set[str] = set()

        if use_default_stopwords:
            resolved_stopwords.update(
                _DEFAULT_STOPWORDS
            )

        if stopwords is not None:
            resolved_stopwords.update(
                self._normalize_token(word)
                for word in stopwords
                if word.strip()
            )

        self.stopwords = frozenset(
            resolved_stopwords
        )

        resolved_domain_terms: list[str] = []

        if use_default_domain_terms:
            resolved_domain_terms.extend(
                _DEFAULT_DOMAIN_TERMS
            )

        if domain_terms is not None:
            resolved_domain_terms.extend(
                term
                for term in domain_terms
                if term.strip()
            )

        # 去重但保持顺序。
        self.domain_terms = tuple(
            dict.fromkeys(
                term.strip()
                for term in resolved_domain_terms
                if term.strip()
            )
        )

        self._register_domain_terms()

    def tokenize(
        self,
        text: str,
    ) -> list[str]:
        if not isinstance(text, str):
            raise TypeError(
                "text 必须是 str"
            )

        text = self._normalize_text(text)

        if not text:
            return []

        tokens: list[str] = []

        cursor = 0

        for match in (
            _TECHNICAL_TOKEN_PATTERN.finditer(
                text
            )
        ):
            start, end = match.span()

            # 先处理技术 Token 前面的中文区域。
            if start > cursor:
                tokens.extend(
                    self._tokenize_natural_segment(
                        text[cursor:start]
                    )
                )

            raw_token = match.group(0)

            tokens.extend(
                self._expand_technical_token(
                    raw_token
                )
            )

            cursor = end

        # 处理最后剩余区域。
        if cursor < len(text):
            tokens.extend(
                self._tokenize_natural_segment(
                    text[cursor:]
                )
            )

        return [
            token
            for token in tokens
            if self._keep(token)
        ]

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:
        """
        NFKC 统一全角/半角等 Unicode 表示。

        例如：
        ＡＰＩ → API
        """
        return unicodedata.normalize(
            "NFKC",
            text,
        ).strip()

    @staticmethod
    def _normalize_token(
        token: str,
    ) -> str:
        return unicodedata.normalize(
            "NFKC",
            token,
        ).strip().lower()

    def _tokenize_natural_segment(
        self,
        text: str,
    ) -> list[str]:
        """
        当前主要提取连续中文片段，
        再交给 jieba 搜索模式。
        """
        tokens: list[str] = []

        for block in (
            _CHINESE_BLOCK_PATTERN.findall(
                text
            )
        ):
            words = jieba.lcut_for_search(
                block
            )

            for word in words:
                normalized = (
                    self._normalize_token(
                        word
                    )
                )

                if normalized:
                    tokens.append(
                        normalized
                    )

        return tokens

    def _expand_technical_token(
        self,
        raw_token: str,
    ) -> list[str]:
        """
        技术 Token 既保留整体形式，
        也尽量拆出 CamelCase 子词。

        SkillVectorIndex
        →
        skillvectorindex
        skill
        vector
        index
        """
        normalized = self._normalize_token(
            raw_token
        )

        if not normalized:
            return []

        result: list[str] = [
            normalized
        ]

        # 只有原始 Token 存在大写信息时，
        # CamelCase 拆分才有意义。
        if any(
            char.isupper()
            for char in raw_token
        ):
            parts = (
                _CAMEL_CASE_PATTERN.findall(
                    raw_token
                )
            )

            for part in parts:
                part = (
                    self._normalize_token(
                        part
                    )
                )

                if (
                    part
                    and part != normalized
                ):
                    result.append(part)

        # 去重且保持顺序。
        return list(
            dict.fromkeys(result)
        )

    def _keep(
        self,
        token: str,
    ) -> bool:
        if not token:
            return False

        if token in self.stopwords:
            return False

        return True

    def _register_domain_terms(
        self,
    ) -> None:
        """
        注册稳定的领域词。

        不应该把某条 Eval Query 的完整表达
        临时加入这里，否则会造成测试泄漏。
        """
        for term in self.domain_terms:
            jieba.add_word(
                term,
                freq=10000,
            )