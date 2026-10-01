def normalize_phone(phone: str) -> str:
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if len(cleaned) < 7:
        raise ValueError("Invalid phone number")
    return cleaned
