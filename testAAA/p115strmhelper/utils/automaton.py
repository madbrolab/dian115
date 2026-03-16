__all__ = ["AutomatonUtils"]


from ahocorasick import Automaton


class AutomatonUtils:
    """
    Aho-Corasick 工具
    """

    @staticmethod
    def build_automaton(value) -> Automaton:
        """
        构建并返回 Aho-Corasick 自动机
        """
        a = Automaton()
        if not value:
            a.make_automaton()
            return a
        for keyword in value:
            if keyword:
                a.add_word(keyword.lower(), (keyword, keyword.lower()))
        a.make_automaton()
        return a
