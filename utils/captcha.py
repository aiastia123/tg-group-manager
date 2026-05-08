"""验证码生成"""
import random
import string


def generate_math_captcha() -> tuple[str, str]:
    """生成数学验证码，返回 (题目, 答案)"""
    a = random.randint(1, 50)
    b = random.randint(1, 50)
    ops = ["+", "-", "×"]
    op = random.choice(ops)
    if op == "+":
        answer = a + b
    elif op == "-":
        # 确保结果非负
        if a < b:
            a, b = b, a
        answer = a - b
    else:
        a = random.randint(1, 12)
        b = random.randint(1, 12)
        answer = a * b
    question = f"{a} {op} {b} = ?"
    return question, str(answer)


def generate_text_captcha() -> tuple[str, str]:
    """生成文字验证码，返回 (显示文本, 答案)"""
    chars = string.ascii_uppercase + string.digits
    answer = "".join(random.choices(chars, k=5))
    return answer, answer
