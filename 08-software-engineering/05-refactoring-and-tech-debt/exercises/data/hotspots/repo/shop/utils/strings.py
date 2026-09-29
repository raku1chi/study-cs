"""文字列の補助関数。"""
import unicodedata


def normalize(text):
    return unicodedata.normalize("NFKC", text).strip()


def truncate(text, width):
    return text if len(text) <= width else text[: width - 1] + "…"
