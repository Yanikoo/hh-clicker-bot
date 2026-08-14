from app.llm import _looks_like_invalid_reply
from app.manager import _employer_message_requires_reply


def test_reasoning_leak_is_rejected():
    text = "Okay, let me handle this response. The user is Nikita."
    assert _looks_like_invalid_reply(text) is True


def test_rejection_does_not_require_reply():
    text = "К сожалению, сейчас мы не готовы пригласить вас на следующий этап."
    assert _employer_message_requires_reply(text) is False


def test_robot_confirmation_does_not_require_reply():
    text = "Спасибо! Ваши ответы отправлены работодателю."
    assert _employer_message_requires_reply(text) is False


def test_real_question_requires_reply():
    text = "Подскажите, готовы ли вы пройти livecoding по Vue 3 и TypeScript?"
    assert _employer_message_requires_reply(text) is True
