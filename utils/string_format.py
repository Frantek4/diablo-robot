import re


def to_kebab_case(string: str) -> str:
    cleaned = re.sub(r'[^\w\s-]', '', string).strip().lower()
    return re.sub(r'[-_\s]+', '-', cleaned)