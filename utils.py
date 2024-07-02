def make_tag(t: str):
    t = t.title().replace(" ", "").replace(".", "")
    return f"#{t}"
