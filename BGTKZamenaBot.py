import requests
import csv
import io
import re
import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

BOT_TOKEN = os.environ.get("BOT_TOKEN", "") <=== сюда токен
SCHEDULE_URL = os.environ.get(
    "SCHEDULE_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgODzWJhSfml2SVezD2P4wdEyp92gZ7y3-tyjFssLI80j3CCTv7-cmJhcCsvQNKcPnzP-m2r9pswd8/pub?output=csv",
)

DEFAULT_GROUP = os.environ.get("DEFAULT_GROUP", "2П065")
USERS_FILE = os.environ.get("USERS_FILE", "users.json")

RUSSIAN_DAYS = {
    'MONDAY': 'ПОНЕДЕЛЬНИК', 'TUESDAY': 'ВТОРНИК', 'WEDNESDAY': 'СРЕДА',
    'THURSDAY': 'ЧЕТВЕРГ', 'FRIDAY': 'ПЯТНИЦА', 'SATURDAY': 'СУББОТА',
    'SUNDAY': 'ВОСКРЕСЕНЬЕ'
}
DAYS_SET = set(RUSSIAN_DAYS.values())

GROUP_RE = re.compile(r'^[1-4][А-ЯA-Z]\d{3}$')
PREFIX_RE = re.compile(r'^[1-4][А-ЯA-Z]\d{0,2}$')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

LAST_MESSAGES = {}


def load_users() -> Dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_users(u: Dict):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(u, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_users: {e}")


def get_user_group(user_id) -> Optional[str]:
    return load_users().get(str(user_id), {}).get('group')


def set_user_group(user_id, group: str):
    u = load_users()
    u.setdefault(str(user_id), {})['group'] = group
    save_users(u)


def set_user_state(user_id, state: Optional[str]):
    u = load_users()
    u.setdefault(str(user_id), {})['state'] = state
    save_users(u)


def get_user_state(user_id) -> Optional[str]:
    return load_users().get(str(user_id), {}).get('state')


def _clean_group_text(text: str) -> str:
    return text.upper().replace(' ', '').replace('-', '').strip()


def normalize_group(text: str) -> Optional[str]:
    if not text:
        return None
    t = _clean_group_text(text)
    if GROUP_RE.fullmatch(t):
        return t
    if re.fullmatch(r'[А-ЯA-Z]\d{3}', t):
        return '1' + t
    return None


def parse_group_query(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    t = _clean_group_text(text)
    exact = normalize_group(t)
    if exact:
        return exact, None
    if PREFIX_RE.fullmatch(t):
        return None, t
    return None, None


def find_groups_by_prefix(rows, prefix: str) -> List[str]:
    out = []
    seen = set()
    for row in rows:
        if row:
            first = _clean_group_text(row[0])
            if GROUP_RE.match(first) and first.startswith(prefix) and first not in seen:
                seen.add(first)
                out.append(first)
    return out


def get_current_russian_day() -> str:
    return RUSSIAN_DAYS.get(datetime.now().strftime('%A').upper(), '')


def get_tomorrow_russian_day() -> str:
    return RUSSIAN_DAYS.get((datetime.now() + timedelta(days=1)).strftime('%A').upper(), '')


def fetch_rows() -> List[List[str]]:
    resp = requests.get(SCHEDULE_URL, timeout=20)
    resp.raise_for_status()
    text = resp.content.decode('utf-8-sig')
    return [r for r in csv.reader(io.StringIO(text))]


def extract_week(rows) -> Optional[str]:
    week_re = re.compile(r'^\d+\s*неделя$', re.IGNORECASE)
    for row in rows:
        for cell in row:
            if week_re.match(cell.strip()):
                return cell.strip()
    return None


def find_day_blocks(rows) -> List[Tuple[int, str, Optional[str]]]:
    date_re = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
    blocks: List[Tuple[int, str, Optional[str]]] = []
    for i, row in enumerate(rows):
        day_found = None
        date_found = None
        for cell in row:
            c = cell.strip()
            cu = c.upper()
            if not day_found and cu in DAYS_SET:
                day_found = cu
            if not date_found and date_re.match(c):
                date_found = c
        if day_found:
            if not date_found:
                for j in range(max(0, i - 2), min(len(rows), i + 3)):
                    for cell in rows[j]:
                        c = cell.strip()
                        if date_re.match(c):
                            date_found = c
                            break
                    if date_found:
                        break
            blocks.append((i, day_found, date_found))
    return blocks


def find_group_row(rows, group: str, start: int = 0, end: Optional[int] = None) -> Optional[int]:
    end = len(rows) if end is None else end
    for i in range(start, end):
        row = rows[i]
        if row and _clean_group_text(row[0]) == group:
            return i
    return None


def clean_cell(cell: str) -> str:
    if not cell:
        return ""
    return ' | '.join(p.strip() for p in cell.split('\n') if p.strip())


def list_all_groups(rows) -> List[str]:
    out = []
    seen = set()
    for row in rows:
        if row:
            first = _clean_group_text(row[0])
            if GROUP_RE.match(first) and first not in seen:
                seen.add(first)
                out.append(first)
    return out


def extract_lesson_titles(rows, block_start: int, block_end: int) -> List[str]:
    for i in range(block_start, min(block_end, block_start + 5)):
        row = rows[i]
        if row and row[0].strip().upper() == 'ГРУППА':
            titles = []
            for cell in row[1:]:
                c = cell.strip()
                if c and c.lower().endswith('пара'):
                    titles.append(c)
            if titles:
                return titles
    return [f"{i} пара" for i in range(1, 6)]


def format_pairs(rows, idx: int, lesson_titles: List[str]) -> List[str]:
    row = rows[idx]
    pairs = []
    col = 1
    pn = 0
    while col < len(row) and pn < 5:
        name = clean_cell(row[col]) if col < len(row) else ""
        room = clean_cell(row[col + 1]) if col + 1 < len(row) else ""
        title = lesson_titles[pn] if pn < len(lesson_titles) else f"{pn + 1} пара"
        pairs.append((title, name, room))
        col += 2
        pn += 1

    lines = []
    any_lesson = False
    for title, name, room in pairs:
        if not name and not room:
            continue
        any_lesson = True
        lines.append(f"🔹 <b>{title}</b>")
        lines.append(f"   📚 {name or '—'}")
        lines.append(f"   🏫 {room or '—'}")
        lines.append("")
    if not any_lesson:
        lines.append("ℹ️ На этот день пар нет (или они не заполнены).")
    return lines


def parse_schedule(rows, group: str,
                   date_filter: Optional[str] = None,
                   day_filter: Optional[str] = None) -> List[str]:
    header_week = extract_week(rows)
    blocks = find_day_blocks(rows)
    warnings: List[str] = []

    target_day = day_filter.upper() if day_filter else None

    if target_day:
        matching = [(i, d, dt) for (i, d, dt) in blocks if d == target_day]
        if not matching:
            avail = ', '.join(sorted({d for _, d, _ in blocks})) or 'нет'
            return [f"❌ В таблице нет блока дня <b>{target_day}</b>.\n\n"
                    f"🔎 Есть блоки: {avail}"]

        chosen = None
        if date_filter:
            for (i, d, dt) in matching:
                if dt == date_filter:
                    chosen = (i, d, dt)
                    break
            if chosen is None:
                chosen = matching[0]
                warnings.append(
                    f"⚠️ Дата <b>{date_filter}</b> в блоке <b>{target_day}</b> не найдена; "
                    f"показываю блок от <b>{chosen[2] or '—'}</b>."
                )
        else:
            chosen = matching[0]

        block_start, block_day, block_date = chosen
        next_starts = [i for (i, _, _) in blocks if i > block_start]
        block_end = min(next_starts) if next_starts else len(rows)

        idx = find_group_row(rows, group, block_start, block_end)
        if idx is None:
            av = list_all_groups(rows[block_start:block_end])
            return [f"❌ Группа <b>{group}</b> не найдена в блоке <b>{block_day}</b>.\n\n"
                    f"🔎 В этом блоке есть: {', '.join(av) or 'нет'}"]

        lesson_titles = extract_lesson_titles(rows, block_start, block_end)

        lines = [f"📚 <b>Расписание для {group}</b>"]
        if header_week:
            lines.append(f"📅 Неделя: {header_week}")
        if block_date:
            lines.append(f"🗓️ Дата: {block_date}")
        lines.append(f"📋 День: {block_day}")
        lines.extend(warnings)
        lines.append("")
        lines.extend(format_pairs(rows, idx, lesson_titles))
        return ["\n".join(lines)]

    idx = find_group_row(rows, group)
    if idx is None:
        av = list_all_groups(rows)
        return [f"❌ Группа <b>{group}</b> не найдена.\n\n"
                f"🔎 В таблице есть: {', '.join(av) or 'нет'}"]

    containing = None
    for k, (start, d, dt) in enumerate(blocks):
        next_starts = [i for (i, _, _) in blocks if i > start]
        end = min(next_starts) if next_starts else len(rows)
        if start <= idx < end:
            containing = (start, d, dt, end)
            break

    if containing:
        block_start, block_day, block_date, block_end = containing
        lesson_titles = extract_lesson_titles(rows, block_start, block_end)
        lines = [f"📚 <b>Расписание для {group}</b>"]
        if header_week:
            lines.append(f"📅 Неделя: {header_week}")
        if block_date:
            lines.append(f"🗓️ Дата: {block_date}")
        lines.append(f"📋 День: {block_day}")
        lines.append("")
        lines.extend(format_pairs(rows, idx, lesson_titles))
        return ["\n".join(lines)]

    lesson_titles = [f"{i} пара" for i in range(1, 6)]
    lines = [f"📚 <b>Расписание для {group}</b>"]
    if header_week:
        lines.append(f"📅 Неделя: {header_week}")
    lines.append("")
    lines.extend(format_pairs(rows, idx, lesson_titles))
    return ["\n".join(lines)]


def search_schedule(group, date_filter=None, day_filter=None) -> List[str]:
    try:
        return parse_schedule(fetch_rows(), group, date_filter, day_filter)
    except Exception as e:
        logger.exception("Ошибка поиска")
        return [f"❌ Ошибка: {e}"]


def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text() or ""
                tables = page.extract_tables()
                if tables:
                    t += "\n\n[Таблицы]\n"
                    for tbl in tables:
                        for r in tbl:
                            t += " | ".join((c or "").strip() for c in r) + "\n"
                pages.append(f"── Страница {i} ──\n{t}")
            return "\n\n".join(pages).strip()
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"pdfplumber: {e}")

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for i, page in enumerate(reader.pages, 1):
            pages.append(f"── Страница {i} ──\n{page.extract_text() or ''}")
        return "\n\n".join(pages).strip()
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"pypdf: {e}")

    return ""


class Bot:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"

    def api(self, method: str, **kwargs):
        try:
            r = requests.post(f"{self.base}/{method}", json=kwargs, timeout=20)
            return r.json()
        except Exception as e:
            logger.error(f"{method}: {e}")
            return {"ok": False}

    def get_updates(self, offset=None):
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        try:
            r = requests.get(f"{self.base}/getUpdates", params=params, timeout=35)
            return r.json().get("result", [])
        except Exception as e:
            logger.error(f"getUpdates: {e}")
            return []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = reply_markup
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                res = self.api("sendMessage", **{**data, "text": text[i:i+4000]})
                if res and res.get("ok"):
                    LAST_MESSAGES[chat_id] = res["result"]["message_id"]
            return None
        res = self.api("sendMessage", **data)
        if res and res.get("ok"):
            LAST_MESSAGES[chat_id] = res["result"]["message_id"]
        return res

    def delete_message(self, chat_id, message_id):
        if not message_id:
            return
        try:
            self.api("deleteMessage", chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    def delete_previous_message(self, chat_id):
        if chat_id in LAST_MESSAGES:
            msg_id = LAST_MESSAGES.pop(chat_id)
            self.delete_message(chat_id, msg_id)

    def answer_callback(self, cb_id, text=""):
        self.api("answerCallbackQuery", callback_query_id=cb_id, text=text)

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        data = {"chat_id": chat_id, "message_id": message_id,
                "text": text, "parse_mode": "HTML"}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.api("editMessageText", **data)

    def reply_main(self):
        return {"keyboard": [
            [{"text": "📅 Сегодня"}, {"text": "📅 Завтра"}],
            [{"text": "🔍 Группа"}, {"text": "⚙️ Моя группа"}],
            [{"text": "⭐️ Поддержать"}]
        ], "resize_keyboard": True}

    def inline_main(self):
        g = DEFAULT_GROUP
        return {"inline_keyboard": [
            [{"text": f"🚀 Расписание {g}", "callback_data": f"grp|{g}"}],
            [{"text": "📅 Сегодня", "callback_data": "day|today"},
             {"text": "📅 Завтра", "callback_data": "day|tomorrow"}],
            [{"text": "🔍 Другая группа", "callback_data": "enter_group"},
             {"text": "⚙️ Моя группа", "callback_data": "my_group"}],
            [{"text": "⭐️ Поддержать", "callback_data": "donate"}]
        ]}

    def inline_back(self):
        return {"inline_keyboard": [[{"text": "⬅️ В меню", "callback_data": "menu"}]]}

    def show_main_menu(self, chat_id, user_id, edit_msg_id=None):
        g = get_user_group(user_id) or DEFAULT_GROUP
        text = (
            f"👋 <b>Бот поиска замен</b>\n\n"
            f"📅 Сегодня: {get_current_russian_day()}\n"
            f"📅 Завтра: {get_tomorrow_russian_day()}\n"
            f"⚙️ Ваша группа: <b>{g}</b>\n\n"
            f"Выберите действие на кнопках ниже."
        )
        kb = self.inline_main()
        if edit_msg_id:
            self.edit_message(chat_id, edit_msg_id, text, kb)
        else:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, text, self.reply_main())
            self.send_message(chat_id, "Меню:", kb)

    def send_stars_invoice(self, chat_id, amount: int):
        title = f"Поддержка автора — {amount} ⭐"
        description = "Спасибо на века запомню твои добрые деяния!"
        payload = f"donate_{amount}_{int(time.time())}"
        currency = "XTR"
        prices = [{"label": f"{amount} Stars", "amount": amount}]
        res = self.api(
            "sendInvoice",
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            currency=currency,
            prices=prices,
        )
        if not res.get("ok"):
            self.delete_previous_message(chat_id)
            self.send_message(
                chat_id,
                "⚠️ Telegram Stars пока не подключены.\n"
                "ждите."
            )

    def send_donate_menu(self, chat_id, edit_msg_id=None):
        text = (
            "⭐️ <b>Поддержать автора</b>\n\n"
            "Закинь звезд на сервак.\n"
            "Нажмите на одну из кнопок ниже или введите команду <code>/star 10</code> (где 10 — количество звезд)."
        )
        kb = {"inline_keyboard": [
            [{"text": "⭐ 1", "callback_data": "stars|1"},
             {"text": "⭐ 5", "callback_data": "stars|5"},
             {"text": "⭐ 10", "callback_data": "stars|10"}],
            [{"text": "⭐ 25", "callback_data": "stars|25"},
             {"text": "⭐ 50", "callback_data": "stars|50"}],
            [{"text": "⬅️ В меню", "callback_data": "menu"}]
        ]}
        if edit_msg_id:
            self.edit_message(chat_id, edit_msg_id, text, kb)
        else:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, text, kb)

    def handle_pdf_document(self, chat_id, document: dict):
        mime = document.get("mime_type", "")
        name = document.get("file_name", "file.pdf")
        if mime != "application/pdf" and not name.lower().endswith(".pdf"):
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, "❌ Это не PDF. Пришлите файл .pdf")
            return
        if document.get("file_size", 0) > 20 * 1024 * 1024:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, "❌ Файл больше 20 МБ — Telegram не даст скачать.")
            return

        self.delete_previous_message(chat_id)
        self.send_message(chat_id, "📄 Читаю PDF...")
        f = self.api("getFile", file_id=document["file_id"])
        if not f.get("ok"):
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, "❌ Не удалось получить файл.")
            return
        file_path = f["result"]["file_path"]
        url = f"{self.file_base}/{file_path}"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.content
        except Exception as e:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, f"❌ Ошибка скачивания: {e}")
            return

        text = extract_pdf_text(data)
        self.delete_previous_message(chat_id)
        if not text.strip():
            self.send_message(
                chat_id,
                "⚠️ Не удалось извлечь текст (возможно, скан без OCR).\n"
                "Установите на сервере: <code>pip install pdfplumber</code>\n"
                "Для сканов нужен OCR (tesseract)."
            )
            return

        if len(text) > 3500:
            self.send_message(chat_id, f"📄 <b>{name}</b> — текст ({len(text)} симв.):")
            for i in range(0, len(text), 3500):
                self.send_message(chat_id, f"<pre>{text[i:i+3500]}</pre>")
        else:
            self.send_message(chat_id, f"📄 <b>{name}</b>:\n\n<pre>{text}</pre>")

    def show_group_choices(self, chat_id, prefix, edit_msg_id=None):
        try:
            rows = fetch_rows()
        except Exception as e:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, f"❌ Не удалось получить таблицу: {e}")
            return

        groups = find_groups_by_prefix(rows, prefix)
        if not groups:
            self.delete_previous_message(chat_id)
            self.send_message(
                chat_id,
                f"❌ Групп, начинающихся с <b>{prefix}</b>, не найдено.\n"
                f"Попробуйте, например: <code>{prefix}065</code>",
                self.inline_back()
            )
            return

        buttons = []
        row_btns = []
        for g in groups:
            row_btns.append({"text": g, "callback_data": f"gsel|{g}"})
            if len(row_btns) == 3:
                buttons.append(row_btns)
                row_btns = []
        if row_btns:
            buttons.append(row_btns)
        buttons.append([{"text": "⬅️ В меню", "callback_data": "menu"}])

        text = (
            f"🔍 Найдено групп по запросу <b>{prefix}</b>: {len(groups)}\n"
            f"Выберите нужную:"
        )
        kb = {"inline_keyboard": buttons}
        if edit_msg_id:
            self.edit_message(chat_id, edit_msg_id, text, kb)
        else:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, text, kb)

    def run_search(self, chat_id, group, date_filter=None, day_filter=None, edit_msg_id=None):
        if edit_msg_id:
            results = search_schedule(group, date_filter, day_filter)
            text = "\n\n".join(results)
            if len(text) > 4000:
                text = text[:4000] + "\n…"
            self.edit_message(chat_id, edit_msg_id, text, self.inline_back())
        else:
            self.delete_previous_message(chat_id)
            results = search_schedule(group, date_filter, day_filter)
            text = "\n\n".join(results)
            self.send_message(chat_id, text, self.inline_back())

    def send_debug(self, chat_id):
        try:
            rows = fetch_rows()
        except Exception as e:
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, f"❌ Не удалось получить CSV: {e}")
            return
        blocks = find_day_blocks(rows)
        lines = [f"📊 <b>Отладка CSV</b>", f"Строк: {len(rows)}", ""]
        lines.append("<b>Найденные блоки дней:</b>")
        if blocks:
            for (i, d, dt) in blocks:
                lines.append(f"• строка {i}: <b>{d}</b> — {dt or '—'}")
        else:
            lines.append("• нет ни одного дня недели в шапках")
        lines.append("")
        lines.append("<b>Первые 15 строк (первые 2 колонки):</b>")
        for i, r in enumerate(rows[:15]):
            c0 = (r[0] if len(r) > 0 else "").strip()
            c1 = (r[1] if len(r) > 1 else "").strip()
            lines.append(f"{i}: {c0!r} | {c1!r}")
        text = "\n".join(lines)
        if len(text) > 3800:
            text = text[:3800] + "\n…"
        self.delete_previous_message(chat_id)
        self.send_message(chat_id, text, self.inline_back())

    def handle_update(self, update):
        if "callback_query" in update:
            self.handle_callback(update["callback_query"])
            return
        msg = update.get("message")
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        user_id = msg.get("from", {}).get("id")

        if "document" in msg:
            self.handle_pdf_document(chat_id, msg["document"])
            return

        text = (msg.get("text") or "").strip()
        if not text:
            return
        text = re.sub(r'@\w+', '', text).strip()

        m_start = re.match(r'^/start(?:\s+(\d+))?$', text)
        if m_start:
            if m_start.group(1):
                n = int(m_start.group(1))
                if 1 <= n <= 10000:
                    self.send_stars_invoice(chat_id, n)
                else:
                    self.delete_previous_message(chat_id)
                    self.send_message(chat_id, "❌ Число звёзд: от 1 до 10000.")
            self.show_main_menu(chat_id, user_id)
            return

        if text == '/menu':
            self.show_main_menu(chat_id, user_id)
            return

        if text in ['/donate', '/star', '⭐️ Поддержать', '💸 Поддержать']:
            self.send_donate_menu(chat_id)
            return

        m_star = re.match(r'^/star\s+(\d+)$', text)
        if m_star:
            n = int(m_star.group(1))
            if 1 <= n <= 10000:
                self.send_stars_invoice(chat_id, n)
            else:
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, "❌ Число звёзд: от 1 до 10000.")
            return

        if text in ['📅 Сегодня', '/today']:
            g = get_user_group(user_id) or DEFAULT_GROUP
            self.run_search(chat_id, g,
                            date_filter=datetime.now().strftime('%d.%m.%Y'),
                            day_filter=get_current_russian_day())
            return
        if text in ['📅 Завтра', '/tomorrow', '/zavtra']:
            g = get_user_group(user_id) or DEFAULT_GROUP
            self.run_search(chat_id, g,
                            date_filter=(datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y'),
                            day_filter=get_tomorrow_russian_day())
            return

        if text == '/debug':
            self.send_debug(chat_id)
            return

        parts = text.split()
        cmd = parts[0].lower()

        if cmd in ['/zamena', '/pe', '/search']:
            if len(parts) < 2:
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, "Использование: <code>/zamena 2П065</code>")
                return
            exact, prefix = parse_group_query(parts[1])
            if exact:
                g = exact
            elif prefix:
                self.delete_previous_message(chat_id)
                self.show_group_choices(chat_id, prefix)
                return
            else:
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, "❌ Неверный формат группы.")
                return
            day = None
            if len(parts) >= 3:
                cand = parts[2].upper()
                if cand in DAYS_SET:
                    day = cand
            self.run_search(chat_id, g, day_filter=day)
            return

        if cmd == '/set':
            if len(parts) < 2:
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, "Использование: <code>/set 2П065</code>")
                return
            exact, prefix = parse_group_query(parts[1])
            if not exact:
                self.delete_previous_message(chat_id)
                if prefix:
                    self.send_message(
                        chat_id,
                        f"⚠️ <b>{prefix}</b> — это префикс, а не полный номер.\n"
                        f"Укажите полный номер, например <code>{prefix}065</code>."
                    )
                else:
                    self.send_message(chat_id, "❌ Неверный формат группы.")
                return
            set_user_group(user_id, exact)
            self.delete_previous_message(chat_id)
            self.send_message(chat_id, f"✅ Ваша группа: <b>{exact}</b>")
            return

        if get_user_state(user_id) == "await_group":
            exact, prefix = parse_group_query(text)
            if exact:
                set_user_group(user_id, exact)
                set_user_state(user_id, None)
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, f"✅ Группа сохранена: <b>{exact}</b>")
                self.run_search(chat_id, exact)
            elif prefix:
                set_user_state(user_id, None)
                self.show_group_choices(chat_id, prefix)
            else:
                self.delete_previous_message(chat_id)
                self.send_message(chat_id, "❌ Неверный формат. Пример: <code>2П065</code>")
            return

        exact, prefix = parse_group_query(text)
        if exact:
            self.run_search(chat_id, exact)
            return
        if prefix:
            self.show_group_choices(chat_id, prefix)
            return

        self.delete_previous_message(chat_id)
        self.send_message(chat_id, "❌ Не понял. /menu — меню, /debug — диагностика.")

    def handle_callback(self, cb):
        cb_id = cb["id"]
        data = cb.get("data", "")
        msg = cb["message"]
        chat_id = msg["chat"]["id"]
        msg_id = msg["message_id"]
        user_id = cb.get("from", {}).get("id")

        self.answer_callback(cb_id)

        if data == "menu":
            self.show_main_menu(chat_id, user_id, edit_msg_id=msg_id)
            return
        if data == "donate":
            self.send_donate_menu(chat_id, edit_msg_id=msg_id)
            return
        if data.startswith("stars|"):
            n = int(data.split("|")[1])
            self.send_stars_invoice(chat_id, n)
            return
        if data == "my_group":
            g = get_user_group(user_id) or DEFAULT_GROUP
            self.edit_message(chat_id, msg_id,
                              f"⚙️ Ваша группа: <b>{g}</b>",
                              {"inline_keyboard": [
                                  [{"text": "✏️ Изменить", "callback_data": "enter_group"}],
                                  [{"text": "⬅️ В меню", "callback_data": "menu"}]
                              ]})
            return
        if data == "enter_group":
            set_user_state(user_id, "await_group")
            self.edit_message(chat_id, msg_id,
                              "Введите номер группы, например <code>2П065</code>,\n"
                              "или префикс, например <code>2П</code> / <code>1А</code>:",
                              {"inline_keyboard": [[{"text": "⬅️ Отмена", "callback_data": "menu"}]]})
            return
        if data.startswith("grp|"):
            g = data.split("|", 1)[1]
            self.run_search(chat_id, g, edit_msg_id=msg_id)
            return
        if data.startswith("gsel|"):
            g = data.split("|", 1)[1]
            self.run_search(chat_id, g, edit_msg_id=msg_id)
            return
        if data.startswith("day|"):
            which = data.split("|")[1]
            g = get_user_group(user_id) or DEFAULT_GROUP
            if which == "today":
                self.run_search(chat_id, g,
                                date_filter=datetime.now().strftime('%d.%m.%Y'),
                                day_filter=get_current_russian_day(),
                                edit_msg_id=msg_id)
            else:
                self.run_search(chat_id, g,
                                date_filter=(datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y'),
                                day_filter=get_tomorrow_russian_day(),
                                edit_msg_id=msg_id)
            return

    def run(self):
        offset = None
        logger.info("Бот запущен")
        while True:
            try:
                for upd in self.get_updates(offset):
                    offset = upd["update_id"] + 1
                    try:
                        self.handle_update(upd)
                    except Exception:
                        logger.exception("update")
                time.sleep(1)
            except Exception as e:
                logger.error(f"main: {e}")
                time.sleep(5)


def main():
    Bot(BOT_TOKEN).run()


if __name__ == "__main__":
    main()
