"""
Data query routes: applied, tests, interviews, vacancies, HR contacts.
"""

import threading

from fastapi import APIRouter

from app.storage import (
    _load_cache, _cache_applied, _cache_tests, _cache_lock,
    get_applied_list, get_vacancy_db, get_test_list,
    get_interview, get_interviews_list, get_applied_accounts, upsert_interview,
    _save_applied_async, _save_tests_async,
)
from app.instances import bot
from app.manager import _employer_message_requires_reply
from app.hh_chat import (
    _fetch_chat_list, _build_thread_from_chat_item,
    mark_chat_read, send_negotiation_message,
)


router = APIRouter()


@router.get("/api/applied")
async def api_applied(limit: int = 300):
    return get_applied_list(limit)


@router.get("/api/tests")
async def api_tests(limit: int = 300):
    return get_test_list(limit)


@router.get("/api/interviews")
async def api_interviews(acc: str = "", limit: int = 2000, status: str = "", redact: bool = False):
    items = get_interviews_list(acc=acc, limit=limit, status=status)
    if not redact:
        return items
    redacted = []
    for item in items:
        copy = dict(item)
        for field in ("llm_reply", "employer_last_msg"):
            val = copy.get(field)
            if isinstance(val, str) and len(val) > 80:
                copy[field] = val[:80] + "…"
        redacted.append(copy)
    return redacted


@router.post("/api/interviews/{neg_id}/send")
async def api_interview_send(neg_id: str):
    """Manually send one reviewed LLM draft to HH."""
    record = get_interview(neg_id)
    if not record:
        return {"ok": False, "error": "Черновик не найден"}
    if record.get("llm_sent"):
        return {"ok": False, "error": "Этот ответ уже отправлен"}
    draft = str(record.get("llm_reply") or "").strip()
    if not draft:
        return {"ok": False, "error": "Текст черновика пуст"}

    states = [
        state for state in list(bot.account_states) + list(bot.temp_states.values())
        if not getattr(state, "_deleted", False)
    ]
    applied_accounts = get_applied_accounts(record.get("vacancy_id", ""))
    matching = [
        state for state in states
        if state.name in applied_accounts or state.short in applied_accounts
    ]
    if not matching:
        matching = [state for state in states if state.short == record.get("acc")]
    if not matching:
        return {"ok": False, "error": "Запустите бота нужного резюме и повторите"}
    state = matching[0]

    items_by_id, display_info, cur_pid = _fetch_chat_list(state.acc, max_pages=3)
    item = items_by_id.get(str(neg_id)) or items_by_id.get(neg_id)
    if not item:
        return {"ok": False, "error": "Чат не найден в HH"}
    thread = _build_thread_from_chat_item(item, display_info, cur_pid, str(neg_id))
    if thread.get("error"):
        return {"ok": False, "error": "Не удалось прочитать актуальный чат HH"}
    if thread.get("chat_locked"):
        return {"ok": False, "error": "Переписка в HH закрыта"}

    current_employer_msg = str(thread.get("last_employer_msg") or "").strip()
    draft_employer_msg = str(record.get("employer_last_msg") or "").strip()
    if draft_employer_msg and current_employer_msg and current_employer_msg != draft_employer_msg:
        return {"ok": False, "error": "Работодатель уже написал новое сообщение — обновите черновик"}

    last_msg_id = str(thread.get("last_msg_id") or "")
    global_key = (cur_pid, str(neg_id), last_msg_id)
    with bot._llm_sent_lock:
        if global_key in bot._llm_sent_global:
            return {"ok": False, "error": "Ответ уже отправляется или отправлен"}
        bot._llm_sent_global.add(global_key)
        bot._llm_sent_by_neg_id.setdefault(str(neg_id), set()).add(global_key)

    try:
        try:
            mark_chat_read(state.acc, str(neg_id), last_msg_id)
        except Exception:
            pass
        ok = send_negotiation_message(
            state.acc,
            str(neg_id),
            draft,
            topic_id=thread.get("topic_id", ""),
        )
        if not ok or ok == "chat_not_found":
            with bot._llm_sent_lock:
                bot._llm_sent_global.discard(global_key)
                bot._llm_sent_by_neg_id.get(str(neg_id), set()).discard(global_key)
            return {"ok": False, "error": "HH не принял сообщение; черновик сохранён"}

        key = (str(neg_id), last_msg_id)
        state.llm_replied_msgs[key] = None
        for candidate in states:
            with candidate._llm_drafts_lock:
                candidate._llm_drafts.pop(key, None)
        upsert_interview(
            str(neg_id),
            acc=state.short,
            acc_color=state.color,
            llm_reply=draft,
            llm_sent=True,
            needs_reply=False,
            replied_msg_id=last_msg_id,
            chat_status="replied",
        )
        bot._add_log(
            state.short,
            state.color,
            f"🤖 Черновик отправлен вручную → {record.get('employer', '')}",
            "success",
            neg_id=str(neg_id),
        )
        return {"ok": True}
    except Exception:
        with bot._llm_sent_lock:
            bot._llm_sent_global.discard(global_key)
            bot._llm_sent_by_neg_id.get(str(neg_id), set()).discard(global_key)
        return {"ok": False, "error": "Ошибка отправки; черновик сохранён"}


@router.post("/api/interviews/reclassify/no-reply")
async def api_interviews_reclassify_no_reply():
    """Hide stale drafts for rejections, confirmations and informational messages."""
    changed = 0
    for record in get_interviews_list(limit=10000):
        if record.get("llm_sent") or record.get("status") not in ("draft", "pending_reply"):
            continue
        employer_msg = str(record.get("employer_last_msg") or "")
        if _employer_message_requires_reply(employer_msg):
            continue
        upsert_interview(
            str(record.get("neg_id") or ""),
            acc=str(record.get("acc") or ""),
            acc_color=str(record.get("acc_color") or ""),
            needs_reply=False,
            chat_status="waiting_hr",
        )
        changed += 1
    return {"ok": True, "changed": changed}


@router.get("/api/vacancies")
async def api_vacancies(limit: int = 3000):
    return get_vacancy_db(limit)


@router.delete("/api/vacancy/{vacancy_id}")
async def api_vacancy_delete(vacancy_id: str, account: str = ""):
    """Удалить вакансию из applied и/или test кэша."""
    _load_cache()
    removed = []
    with _cache_lock:
        if account:
            if account in _cache_applied and vacancy_id in _cache_applied[account]:
                del _cache_applied[account][vacancy_id]
                removed.append(f"applied:{account}")
        else:
            for acc_name in list(_cache_applied.keys()):
                if vacancy_id in _cache_applied[acc_name]:
                    del _cache_applied[acc_name][vacancy_id]
                    removed.append(f"applied:{acc_name}")
        if vacancy_id in _cache_tests:
            del _cache_tests[vacancy_id]
            removed.append("test")
    if "applied" in " ".join(removed):
        threading.Thread(target=_save_applied_async, daemon=True).start()
    if "test" in " ".join(removed):
        threading.Thread(target=_save_tests_async, daemon=True).start()
    return {"ok": True, "removed": removed}


@router.get("/api/hr_contacts")
async def api_hr_contacts():
    """Return collected HR contact info from vacancy pre-checks."""
    return {"contacts": list(bot.hr_contacts), "total": len(bot.hr_contacts)}
