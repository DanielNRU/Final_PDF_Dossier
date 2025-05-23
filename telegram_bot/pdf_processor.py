import subprocess
from langchain_ollama import OllamaLLM
from pathlib import Path
import pdfplumber
import re
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm
from reportlab.lib import colors
import os
from emojipy import Emoji
import yaml
from reference_data import types_info, hidden_talents_info, personality_info, orientations

# Подавляем предупреждения pdfminer
logging.getLogger("pdfminer").setLevel(logging.ERROR)
ollama = OllamaLLM(base_url="http://llm_service:11434", model="yandex/YandexGPT-5-Lite-8B-instruct-GGUF:latest")

# Используемые функции

def extract_text_from_pdf(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def clean_text(text):
    # Удаляем ссылки вида:
    # "https://bot.youcan.by/admin/info/user/<число>/" с опциональным номером страницы типа "18/20"
    text = re.sub(
        r"(https?://)?bot\.youcan\.by/admin/info/user/\d+/\s*\d+/\d+",
        "",
        text
    )
    # Удаляем ссылки вида "https://bot.youcan.by/admin/info/user/<число>/"
    text = re.sub(
        r"(https?://)?bot\.youcan\.by/admin/info/user/\d+/",
        "",
        text
    )
    # Удаляем дату и время в формате "23 сентября 2024 г. 12:02", "23.09.2024, 12:58" и "2024-09-23 12:03:45"
#    text = re.sub(r"\d{1,2} (?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря) \d{4} г?\.? \d{1,2}:\d{2}", "", text)
    text = re.sub(r"\d{1,2}\.\d{1,2}\.\d{4},? \d{1,2}:\d{2}", "", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "", text)
    # Удаляем номера страниц в формате "18/20"
    text = re.sub(r"\d+/\d+", "", text)
    # Удаляем фразу "Тест пройден:"
#    text = re.sub(r"Тест пройден:\s*", "", text)
    return text.strip()

def parse_user_info(text):
    lines = text.strip().splitlines()
    name_pattern = re.compile(r"^[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)+$")
    for line in lines[:10]:
        candidate = line.strip()
        if name_pattern.match(candidate):
            return candidate
    return lines[0].strip() if lines else ""

def get_task_body(task_text):
    """
    Из блока задания возвращает содержимое после строки, содержащей "Тест пройден:"
    (то есть пропускает заголовок с датой и временем).
    """
    pattern = re.compile(r"Тест пройден:\s*\n.*?\n(.*)", re.DOTALL)
    m = pattern.search(task_text)
    if m:
        return m.group(1).strip()
    else:
        return task_text.strip()

def extract_task(text, task_number):
    # Извлекаем блок от "Задание №<task_number>" до следующего "Задание №" или конца текста,
    # затем возвращаем содержимое после строки с "Тест пройден:".
    pattern = re.compile(rf"(Задание\s*№{task_number}\..*?)(?=Задание\s*№\d+|$)", re.DOTALL)
    match = pattern.search(text)
    if match:
        task_block = match.group(1)
        return get_task_body(task_block)
    else:
        return ""

def parse_task1(task_text):
    pattern = re.compile(r"(\d+)\.\s*(.+?)\s*💡.*?Количество баллов:\s*(\d+)", re.DOTALL)
    results = pattern.findall(task_text)
    parsed = []
    header = "профессиональные склонности"
    for num, description, points in results:
        normalized = " ".join(description.split()).lower()
        if normalized == header:
            continue
        parsed.append({
            "пункт": int(num),
            "описание": description.strip(),
            "баллы": int(points)
        })
    # Удаляем переносы строк в значениях словаря перед возвратом
    for item in parsed:
        item['описание'] = item['описание'].replace('\n', ' ').replace('\r', '')
    return parsed


def parse_task2(task_text):
    pattern = re.compile(r"(.+\(\w+\))", re.DOTALL)
    m = pattern.search(task_text)
    result = m.group(1).strip() if m else ""
    # Удаляем переносы строк перед возвратом
    return result.replace('\n', '<br/>').replace('\r', '')


def parse_task2(task_text):
    pattern = re.compile(r"(.+\(\w+\))", re.DOTALL)
    m = pattern.search(task_text)
    result = m.group(1).strip() if m else ""
    # Удаляем переносы строк перед возвратом
    return task_text.replace('\n', '<br/>').replace('\r', '')

def parse_task3(task_text):
    pattern = re.compile(r"(\d+)\.\s*(.+?)\s*💡.*?Количество баллов:\s*(\d+)", re.DOTALL)
    results = pattern.findall(task_text)
    parsed = []
    header = "профессиональный тип личности"
    for num, description, points in results:
        normalized = " ".join(description.split()).lower()
        if normalized == header:
            continue
        parsed.append({
            "пункт": int(num),
            "описание": description.strip(),
            "баллы": int(points)
        })
    # Удаляем переносы строк в значениях словаря перед возвратом
    for item in parsed:
        if isinstance(item['описание'], str):
            item['описание'] = item['описание'].replace('\n', ' ').replace('\r', '')
    return parsed

def parse_task4(task_text):
    pattern = re.compile(
        r"(\d+)\.\s*(.+?)(?=\s+[А-ЯЁ])(?:.*?Количество баллов:\s*(\d+))",
        re.DOTALL
    )
    header = "ценностные ориентиры"
    results = pattern.findall(task_text)
    parsed = [
        {
            "описание": " ".join(description.split()),
            "баллы": int(points)
        }
        for num, description, points in results
        if " ".join(description.split()).lower() != header
    ]
    # Сортировка по количеству баллов (от большего к меньшему)
    return sorted(parsed, key=lambda x: x["баллы"], reverse=True)


def parse_task5(task_text):
    pattern = re.compile(r"Ответ\s*(.*?)\s*(?=(Задание\s*№|Вопрос\s*№|$))", re.DOTALL)
    match = pattern.search(task_text)
    result = match.group(1).strip() if match else ""
    # Удаляем переносы строк перед возвратом
    return result.replace('\n', ' ').replace('\r', '')

def parse_task6(task_text):
    pattern = re.compile(r'Ответ\s*(.*?)\s*(?=(Вопрос\s*№\d+|$))', re.DOTALL)
    matches = pattern.findall(task_text)
    # Очищаем и возвращаем список ответов
    return [match[0].replace('\n', ' ').replace('\r', '') for match in matches]

def parse_task7(task_text):
    pattern = re.compile(r"Ответ\s*(.*?)\s*(?=(Задание\s*№|Вопрос\s*№|$))", re.DOTALL)
    match = pattern.search(task_text)
    result = match.group(1).strip() if match else ""
    # Удаляем переносы строк перед возвратом

    return result.replace('\n', '<br/>').replace('\r', '<br/>')

def parse_task8(task_text):
    date_pattern = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4},\s*\d{1,2}:\d{2}")
    date_match = date_pattern.search(task_text)
    if date_match:
        start_index = date_match.end()
        remaining_text = task_text[start_index:]
    else:
        remaining_text = task_text

    lines = remaining_text.splitlines()
    filtered_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r"(https?://|www\.)", line) or re.search(r"\d+/\d+", line):
            continue
        words = line.split()
        if 1 <= len(words) <= 2 and all(re.fullmatch(r"[А-ЯЁа-яё]+", word) for word in words):
            filtered_lines.append(line)
    return filtered_lines

def replace_with_emoji_pdf(text, size):
    # Конвертируем эмодзи в HTML-теги <img>
    text = Emoji.to_image(text)
    # Задаем размеры: указываем явно маленькие значения (size в пикселях)
    text = re.sub(r'class="[^"]*"', '', text)  # удаляем атрибут class
    text = re.sub(r'style="[^"]*"', '', text)   # удаляем атрибут style
    text = re.sub(r'alt="[^"]*"', '', text)       # удаляем alt
    # Добавляем атрибуты width и height с нужными значениями:
    # можно выбрать size в зависимости от нужного масштаба (например, 14)
    text = re.sub(r'<img', f'<img height="{size}" width="{size}"', text)
    return text


 ###########################################################   

def process_pdf(input_pdf_path: str, custom_prof_resume=None, custom_talents_resume=None, custom_final_resume=None) -> str:
    """
    Обрабатывает входной PDF, вызывает модель через Ollama,
    генерирует новый PDF (например, dossier.pdf) и возвращает путь к нему.
    """
    # Извлечение текста из PDF
    text = extract_text_from_pdf(input_pdf_path)
    text = clean_text(text)
    user_name = parse_user_info(text)

    tasks = {}
    for i in range(1, 9):
        task_text = extract_task(text, i)
        tasks[f"Задание №{i}"] = task_text.strip()

    # Задание №1-8
    task1_parsed = parse_task1(tasks.get("Задание №1", ""))
    task2_parsed = parse_task2(tasks.get("Задание №2", ""))
    task3_parsed = parse_task3(tasks.get("Задание №3", ""))
    task4_parsed = parse_task4(tasks.get("Задание №4", ""))
    task5_parsed = parse_task5(tasks.get("Задание №5", ""))
    task6_parsed = parse_task6(tasks.get("Задание №6", ""))
    task7_parsed = parse_task7(tasks.get("Задание №7", ""))
    task8_parsed = parse_task8(tasks.get("Задание №8", ""))

    # Профессиональные склонности
    # Правила сопоставления (поиск подстрок в описании)
    mappings = [
        ({"task1": "работе с людьми", "task3": "социальный"}, "Социальный"),
        ({"task1": "эстетическ", "task3": "артистичный"}, "Артистический"),
        ({"task1": "работы с информацией", "task3": "консервативный"}, "Информационный"),
        ({"task1": "практической", "task3": "практический"}, "Практический"),
        ({"task1": "экстремальн"}, "Экстремальный"),
        ({"task1": "исследовательской", "task3": "интеллектуальный"}, "Интеллектуальный"),
        ({"task3": "инициативный"}, "Инициативный")
    ]

    # Функция для проверки наличия подстроки (без учета регистра)
    def match(description, substr):
        return substr.lower() in description.lower()

    # Словарь для суммирования баллов по каждому типу
    scores = {}

    # Расчет баллов по правилам
    for rule, type_name in mappings:
        total = 0
        # Если правило содержит оба условия: task1 и task3
        if "task1" in rule and "task3" in rule:
            for t1 in task1_parsed:
                if match(t1["описание"], rule["task1"]):
                    for t3 in task3_parsed:
                        if match(t3["описание"], rule["task3"]):
                            total += t1["баллы"] + t3["баллы"]
        # Если правило задано только для task1
        elif "task1" in rule:
            for t1 in task1_parsed:
                if match(t1["описание"], rule["task1"]):
                    total += t1["баллы"]
        # Если правило задано только для task3
        elif "task3" in rule:
            for t3 in task3_parsed:
                if match(t3["описание"], rule["task3"]):
                    total += t3["баллы"]
        if total > 0:
            scores[type_name] = scores.get(type_name, 0) + total

    # Сортировка типов по убыванию баллов
    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Функция для форматирования строки с баллами
    def format_score(score):
        if 11 <= score % 100 <= 19:
            return f"{score} баллов"
        else:
            last_digit = score % 10
            if last_digit == 1:
                return f"{score} балл"
            elif last_digit in [2, 3, 4]:
                return f"{score} балла"
            else:
                return f"{score} баллов"

    # Собираем итоговый текст профиля с единым оформлением и emoji
    aggregated_text_prof = ""
    for type_name, score in sorted_types:
        aggregated_text_prof += f"<br/>👉 <b>{type_name} тип деятельности:</b><br/>"
        if type_name in types_info:
            info = types_info[type_name]
            aggregated_text_prof += f"📝 {info['description']}<br/>"
            aggregated_text_prof += "💼 Подходящие профессии:<br/>"
            for prof in info["professions"]:
                aggregated_text_prof += f"   ✔️ {prof}<br/>"

    # Формирование prompt для генерации резюме по разделу "Профессиональные склонности".
    prompts = load_prompts()
    if custom_prof_resume is not None:
        prof_resume = custom_prof_resume
    else:
        prompt_prof = prompts['prof_resume']['template'].format(
            user_name=user_name,
            aggregated_text_prof=aggregated_text_prof
        )
    prof_resume = ollama.invoke(prompt_prof)

    # Личностные особенности
    # Функция для извлечения кода личности из строки (находим содержимое в скобках)
    def extract_personality(code_str):
        start = code_str.find("(")
        end = code_str.find(")")
        if start != -1 and end != -1:
            return code_str[start+1:end].strip()
        return None

    personality_code = extract_personality(task2_parsed)

    # Собираем информацию по типу личности в формате списка
    aggregated_text_personality = ""
    if personality_code and personality_code in personality_info:
        info = personality_info[personality_code]
        aggregated_text_personality += f"<br/><br/>🎭 Тип личности: {info['name']}<br/>"
        aggregated_text_personality += f"📝 {info['description']}<br/><br/>"
        aggregated_text_personality += "🚀 Давай разберём, что делает тебя таким особенным:<br/><br/>"
        for feature in info["features"]:
            aggregated_text_personality += f"🔑 {feature['feature']}:<br/>"
            aggregated_text_personality += f"📝 {feature['description']}<br/>"
            aggregated_text_personality += f"💡 {feature['examples']}<br/><br/>"
    else:
        aggregated_text_personality = task2_parsed

    # Ценностные ориентиры
    # Функция для сборки итогового текста для ценностных ориентиров
    def build_orientations_text(task_results, orientations):
        aggregated_text_orientations = "Твои ценностные ориентиры помогают тебе понять, что действительно важно для тебя в жизни и карьере. Реализуя их, ты можешь чувствовать себя максимально успешным и гармоничным в своей профессии. <br/> Давай разберём, что значит каждая из них и как они могут реализоваться:"
        for result in task_results:
            desc = result['описание']
            data = orientations.get(desc)
            if data:
                aggregated_text_orientations += (
                    f"<br/>💡{data['ориентир']}<br/>"
                    f"📝{data['описание']}<br/>"
                    "✔️ Какой путь тебе подойдет?<br/>"
                    f"{data['путь']}<br/>"
                )
            else:
                aggregated_text_orientations += f"<br/><br/>❗ Нет данных для описания: {desc}<br/>"
        return aggregated_text_orientations


    # Получаем итоговый текст для ценностных ориентиров
    aggregated_text_orientations = build_orientations_text(task4_parsed, orientations)

    # Скрытые таланты
    # Собираем информацию по каждому таланту в единый формат
    aggregated_text_talents = ""
    for talent in task8_parsed:
        info = hidden_talents_info.get(talent)
        if info:
            aggregated_text_talents += f"<br/>✨ {talent}:<br/>"
            aggregated_text_talents += f"📝 {info['description']}<br/><br/>"
            aggregated_text_talents += "💡 Примеры реализации:<br/>"
            aggregated_text_talents += f"{info['examples']}<br/>"
        else:
            aggregated_text_talents += f"<br/><br/>❗ Информация по таланту «{talent}» не найдена.<br/><br/>"

    # Формирование prompt для генерации резюме по разделу "Скрытые таланты".
    if custom_talents_resume is not None:
        talents_resume = custom_talents_resume
    else:
        prompt_talents = prompts['talents_resume']['template'].format(
            user_name=user_name,
            aggregated_text_talents=aggregated_text_talents
        )
    talents_resume = ollama.invoke(prompt_talents)

    # Приветствие
    if custom_final_resume is not None:
        resume = custom_final_resume
    else:
        prompt_final = prompts['final_resume']['template'].format(
            user_name=user_name,
            aggregated_text_prof=aggregated_text_prof,
            prof_resume=prof_resume,
            aggregated_text_personality=aggregated_text_personality,
            aggregated_text_orientations=aggregated_text_orientations,
            aggregated_text_talents=aggregated_text_talents,
            talents_resume=talents_resume
        )
    resume = ollama.invoke(prompt_final)

    # Формирование PDF
    # Путь к шрифту Symbola
    mulish_regular_path = 'Mulish-Regular.ttf'
    if not os.path.exists(mulish_regular_path):
        raise FileNotFoundError(f"Файл шрифта '{mulish_regular_path}' не найден.")

    # Путь к шрифту M PLUS Rounded 1c Bold
    mplus_bold_path = 'MPLUSRounded1c-ExtraBold.ttf'
    if not os.path.exists(mplus_bold_path):
        raise FileNotFoundError(f"Файл шрифта '{rounded_b_font_path}' не найден.")

    # Регистрация шрифтов
    pdfmetrics.registerFont(TTFont('Mulish-Regular', mulish_regular_path))
    pdfmetrics.registerFont(TTFont('MPlusRounded1cB', mplus_bold_path))

    # Имя PDF-файла
    # Определяем путь к директории "downloads" в текущей рабочей директории
    downloads_dir = Path.cwd() / "downloads"
    # Формируем путь к выходному PDF-файлу с использованием кириллических символов в имени
    output_pdf_path = str(downloads_dir / f"Досье {user_name}.pdf")

    # Увеличиваем верхний отступ на высоту header (3 см) + дополнительное пространство, например, 40
    doc = SimpleDocTemplate(output_pdf_path,
                            pagesize=A4,
                            rightMargin=40,
                            leftMargin=40,
                            topMargin=3*cm + 40,
                            bottomMargin=40)


    # Настройка стилей
    styles = getSampleStyleSheet()
    # Основной текст
    styles['Normal'].fontName = 'Mulish-Regular'
    styles['Normal'].fontSize = 14
    styles['Normal'].leading = 16

    # Заголовки блоков
    styles['Heading2'].fontName = "MPlusRounded1cB"
    styles['Heading2'].fontSize = 16
    styles['Heading2'].leading = 20

    # Стиль для заголовка документа – используем жирный шрифт
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading2'],
        fontSize=28,
        alignment=1,  # по центру
        spaceAfter=16,
    )

    # Стиль для названий блоков
    block_header_style = ParagraphStyle(
        'BlockHeader',
        parent=styles['Heading2'],
        fontSize=18,
        spaceAfter=8,
    )

    normal_style = styles['Normal']

    # Класс для оборачивания текста с пунктирной рамкой и закруглёнными углами
    class RoundedBorderedParagraph(Flowable):
        def __init__(self, text, style, padding=0.5*cm, radius=10, dash=(3, 3)):
            Flowable.__init__(self)
            self.text = text
            self.style = style
            self.padding = padding
            self.radius = radius
            self.dash = dash
            self.paragraph = Paragraph(text, style)
            self.width = 0
            self.height = 0

        def wrap(self, availWidth, availHeight):
            # Доступная ширина для текста – с учётом отступов
            available_text_width = availWidth - 2 * self.padding
            w, h = self.paragraph.wrap(available_text_width, availHeight - 2 * self.padding)
            self.width = w + 2 * self.padding
            self.height = h + 2 * self.padding
            return self.width, self.height

        def draw(self):
            # Рисуем пунктирную рамку с закруглёнными углами
            self.canv.saveState()
            self.canv.setStrokeColor(colors.HexColor('#f8bb42'))
            self.canv.setLineWidth(1)
            self.canv.setDash(self.dash[0], self.dash[1])
            self.canv.roundRect(0, 0, self.width, self.height, self.radius, stroke=1, fill=0)
            self.canv.restoreState()
            # Рисуем текст с отступом (padding)
            self.paragraph.drawOn(self.canv, self.padding, self.padding)

        def split(self, availWidth, availHeight):
            """
            Если содержимое не помещается, разбиваем Paragraph на несколько частей.
            Каждый элемент списка – новый RoundedBorderedParagraph, подходящий для текущей области.
            """
            available_text_width = availWidth - 2 * self.padding
            available_text_height = availHeight - 2 * self.padding
            # Используем встроенный метод split у Paragraph
            split_paragraphs = self.paragraph.split(available_text_width, available_text_height)
            if not split_paragraphs:
                return []
            flowables = []
            for p in split_paragraphs:
                new_flowable = RoundedBorderedParagraph("", self.style, self.padding, self.radius, self.dash)
                new_flowable.paragraph = p
                w, h = p.wrap(available_text_width, available_text_height)
                new_flowable.width = w + 2 * self.padding
                new_flowable.height = h + 2 * self.padding
                flowables.append(new_flowable)
            return flowables

    # Кастомный Flowable для пунктирной линии под заголовками блоков
    class DashedHRFlowable(Flowable):
        def __init__(self, width, thickness=1):
            Flowable.__init__(self)
            self.width = width
            self.thickness = thickness

        def wrap(self, availWidth, availHeight):
            return self.width, self.thickness

        def draw(self):
            self.canv.saveState()
            self.canv.setStrokeColor(colors.HexColor('#f8bb42'))
            self.canv.setLineWidth(self.thickness)
            self.canv.setDash(3, 3)  # 3 пункта линия, 3 пункта пробел
            self.canv.line(0, self.thickness/2.0, self.width, self.thickness/2.0)
            self.canv.restoreState()

    # Функция для добавления блока с заголовком, линией и текстом с рамкой
    def add_block(title, text_content, story):
        story.append(Paragraph(title, block_header_style))
        story.append(Spacer(1, 14))
        bordered_paragraph = RoundedBorderedParagraph(text_content, normal_style)
        story.append(bordered_paragraph)
        story.append(Spacer(1, 24))

    # Функция для добавления верхнего колонтитула на каждой странице
    def header(canvas, doc):
        width, height = A4
        header_height = 3 * cm
        canvas.saveState()
        # Рисуем жёлтую полосу с цветом #f8bb42
        canvas.setFillColor(colors.HexColor('#f8bb42'))
        canvas.rect(0, height - header_height, width, header_height, stroke=0, fill=1)

        # Параметры логотипа
        logo_path = "logo.png"  
        logo_width = 2.5 * cm
        logo_height = 2.5 * cm
        logo_x = 1 * cm  # отступ от левого края
        logo_y = height - header_height + (header_height - logo_height) / 2.0
        canvas.drawImage(logo_path, logo_x, logo_y,
                        width=logo_width, height=logo_height,
                        preserveAspectRatio=True, mask='auto')

        # Параметры текста, располагаемого рядом с логотипом
        text_lines = ["Помогаем реализовывать", "твои таланты"]
        text_font = "MPlusRounded1cB"
        text_size = 20
        text_color = colors.black
        text_x = logo_x + logo_width + 0.5 * cm  # отступ от логотипа
        total_text_height = 2 * text_size + 2
        text_y = height - header_height + (header_height + total_text_height) / 2.0 - text_size

        canvas.setFont(text_font, text_size)
        canvas.setFillColor(text_color)
        for line in text_lines:
            canvas.drawString(text_x, text_y, line)
            text_y -= text_size + 2
        canvas.restoreState()


    # Сбор элементов документа
    story = []


    # Определяем размер эмодзи в зависимости от стиля (например, размер основного текста)
    emoji_font_size = normal_style.fontSize  # здесь 14, согласно настройкам

    # Преобразуем текстовые переменные:
    resume = replace_with_emoji_pdf(resume, emoji_font_size)
    aggregated_text_prof = replace_with_emoji_pdf(aggregated_text_prof, emoji_font_size)
    prof_resume = replace_with_emoji_pdf(prof_resume, emoji_font_size)
    aggregated_text_personality = replace_with_emoji_pdf(aggregated_text_personality, emoji_font_size)
    aggregated_text_orientations = replace_with_emoji_pdf(aggregated_text_orientations, emoji_font_size)
    aggregated_text_talents = replace_with_emoji_pdf(aggregated_text_talents, emoji_font_size)
    talents_resume = replace_with_emoji_pdf(talents_resume, emoji_font_size)


    # Заголовок документа
    story.append(Paragraph("ПРОФДИЗАЙН", title_style))
    story.append(DashedHRFlowable(doc.width, thickness=1))
    story.append(Spacer(1, 24))
    story.append(Paragraph(resume, normal_style))
    story.append(Spacer(1, 24))

    # Добавление блоков документа с рамками
    add_block("Профессиональные склонности", aggregated_text_prof + "<br/><br/>" + prof_resume, story)
    add_block("Личностные особенности", aggregated_text_personality, story)
    add_block("Ценностные ориентиры", aggregated_text_orientations, story)
    add_block("Скрытые таланты", aggregated_text_talents + "<br/><br/>" + talents_resume, story)

    # Создание PDF-файла с автоматическим разбиением на страницы и добавлением колонтитула
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return output_pdf_path, prof_resume, talents_resume, resume

PROMPTS_PATH = 'prompts.yaml'
PROMPTS_DEFAULT_PATH = 'prompts_default.yaml'

def load_prompts():
    with open(PROMPTS_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_prompts(prompts):
    with open(PROMPTS_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(prompts, f, allow_unicode=True)

def reset_prompts():
    with open(PROMPTS_DEFAULT_PATH, 'r', encoding='utf-8') as f:
        default_prompts = yaml.safe_load(f)
    save_prompts(default_prompts)
    return default_prompts

# --- parse_and_cache_pdf ---
def parse_and_cache_pdf(input_path):
    text = extract_text_from_pdf(input_path)
    text = clean_text(text)
    user_name = parse_user_info(text)
    tasks = {}
    for i in range(1, 9):
        task_text = extract_task(text, i)
        tasks[f"Задание №{i}"] = task_text.strip()
    return {
        'user_name': user_name,
        'tasks': tasks,
        'task1_parsed': parse_task1(tasks.get("Задание №1", "")),
        'task2_parsed': parse_task2(tasks.get("Задание №2", "")),
        'task3_parsed': parse_task3(tasks.get("Задание №3", "")),
        'task4_parsed': parse_task4(tasks.get("Задание №4", "")),
        'task5_parsed': parse_task5(tasks.get("Задание №5", "")),
        'task6_parsed': parse_task6(tasks.get("Задание №6", "")),
        'task7_parsed': parse_task7(tasks.get("Задание №7", "")),
        'task8_parsed': parse_task8(tasks.get("Задание №8", "")),
        'raw_text': text,
        'input_path': input_path
    }


# --- АГРЕГАЦИЯ ТЕКСТОВ ДЛЯ РАЗДЕЛОВ ---
def build_aggregated_prof_text(pdf_data):
    # Аналогично агрегации профиля в process_pdf
    task1_parsed = pdf_data['task1_parsed']
    task3_parsed = pdf_data['task3_parsed']

    mappings = [
        ({"task1": "работе с людьми", "task3": "социальный"}, "Социальный"),
        ({"task1": "эстетическ", "task3": "артистичный"}, "Артистический"),
        ({"task1": "работы с информацией", "task3": "консервативный"}, "Информационный"),
        ({"task1": "практической", "task3": "практический"}, "Практический"),
        ({"task1": "экстремальн"}, "Экстремальный"),
        ({"task1": "исследовательской", "task3": "интеллектуальный"}, "Интеллектуальный"),
        ({"task3": "инициативный"}, "Инициативный")
    ]
    def match(description, substr):
        return substr.lower() in description.lower()
    scores = {}
    for rule, type_name in mappings:
        total = 0
        if "task1" in rule and "task3" in rule:
            for t1 in task1_parsed:
                if match(t1["описание"], rule["task1"]):
                    for t3 in task3_parsed:
                        if match(t3["описание"], rule["task3"]):
                            total += t1["баллы"] + t3["баллы"]
        elif "task1" in rule:
            for t1 in task1_parsed:
                if match(t1["описание"], rule["task1"]):
                    total += t1["баллы"]
        elif "task3" in rule:
            for t3 in task3_parsed:
                if match(t3["описание"], rule["task3"]):
                    total += t3["баллы"]
        if total > 0:
            scores[type_name] = scores.get(type_name, 0) + total
    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    aggregated_text_prof = ""
    for type_name, score in sorted_types:
        aggregated_text_prof += f"<br/>👉 <b>{type_name} тип деятельности:</b><br/>"
        if type_name in types_info:
            info = types_info[type_name]
            aggregated_text_prof += f"📝 {info['description']}<br/>"
            aggregated_text_prof += "💼 Подходящие профессии:<br/>"
            for prof in info["professions"]:
                aggregated_text_prof += f"   ✔️ {prof}<br/>"
    return aggregated_text_prof

def build_aggregated_talents_text(pdf_data):
    task8_parsed = pdf_data['task8_parsed']
    aggregated_text_talents = ""
    for talent in task8_parsed:
        info = hidden_talents_info.get(talent)
        if info:
            aggregated_text_talents += f"<br/>✨ {talent}:<br/>"
            aggregated_text_talents += f"📝 {info['description']}<br/><br/>"
            aggregated_text_talents += "💡 Примеры реализации:<br/>"
            aggregated_text_talents += f"{info['examples']}<br/>"
        else:
            aggregated_text_talents += f"<br/><br/>❗ Информация по таланту «{talent}» не найдена.<br/><br/>"
    return aggregated_text_talents

def build_aggregated_personality_text(pdf_data):
    task2_parsed = pdf_data['task2_parsed']
    def extract_personality(code_str):
        start = code_str.find("(")
        end = code_str.find(")")
        if start != -1 and end != -1:
            return code_str[start+1:end].strip()
        return None
    personality_code = extract_personality(task2_parsed)
    aggregated_text_personality = ""
    if personality_code and personality_code in personality_info:
        info = personality_info[personality_code]
        aggregated_text_personality += f"<br/><br/>🎭 Тип личности: {info['name']}<br/>"
        aggregated_text_personality += f"📝 {info['description']}<br/><br/>"
        aggregated_text_personality += "🚀 Давай разберём, что делает тебя таким особенным:<br/><br/>"
        for feature in info["features"]:
            aggregated_text_personality += f"🔑 {feature['feature']}:<br/>"
            aggregated_text_personality += f"📝 {feature['description']}<br/>"
            aggregated_text_personality += f"💡 {feature['examples']}<br/><br/>"
    else:
        aggregated_text_personality = task2_parsed
    return aggregated_text_personality

def build_aggregated_orientations_text(pdf_data):
    task4_parsed = pdf_data['task4_parsed']
    def build_orientations_text(task_results, orientations):
        aggregated_text_orientations = "Твои ценностные ориентиры помогают тебе понять, что действительно важно для тебя в жизни и карьере. Реализуя их, ты можешь чувствовать себя максимально успешным и гармоничным в своей профессии. <br/> Давай разберём, что значит каждая из них и как они могут реализоваться:"
        for result in task_results:
            desc = result['описание']
            data = orientations.get(desc)
            if data:
                aggregated_text_orientations += (
                    f"<br/>💡{data['ориентир']}<br/>"
                    f"📝{data['описание']}<br/>"
                    "✔️ Какой путь тебе подойдет?<br/>"
                    f"{data['путь']}<br/>"
                )
            else:
                aggregated_text_orientations += f"<br/><br/>❗ Нет данных для описания: {desc}<br/>"
        return aggregated_text_orientations
    return build_orientations_text(task4_parsed, orientations)


# --- create_pdf ---
def create_pdf(output_path, pdf_data, prof_resume, talents_resume, final_resume):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Flowable
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    mulish_regular_path = os.path.join(base_dir, 'Mulish-Regular.ttf')
    mplus_bold_path = os.path.join(base_dir, 'MPLUSRounded1c-ExtraBold.ttf')
    if not os.path.exists(mulish_regular_path):
        raise FileNotFoundError(f"Файл шрифта '{mulish_regular_path}' не найден.")
    if not os.path.exists(mplus_bold_path):
        raise FileNotFoundError(f"Файл шрифта '{mplus_bold_path}' не найден.")
    pdfmetrics.registerFont(TTFont('Mulish-Regular', mulish_regular_path))
    pdfmetrics.registerFont(TTFont('MPlusRounded1cB', mplus_bold_path))
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = 'Mulish-Regular'
    styles['Normal'].fontSize = 14
    styles['Normal'].leading = 16
    styles['Heading2'].fontName = "MPlusRounded1cB"
    styles['Heading2'].fontSize = 16
    styles['Heading2'].leading = 20
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading2'], fontSize=28, alignment=1, spaceAfter=16,
    )
    block_header_style = ParagraphStyle(
        'BlockHeader', parent=styles['Heading2'], fontSize=18, spaceAfter=8,
    )
    normal_style = styles['Normal']
    class RoundedBorderedParagraph(Flowable):
        def __init__(self, text, style, padding=0.5*cm, radius=10, dash=(3, 3)):
            Flowable.__init__(self)
            self.text = text
            self.style = style
            self.padding = padding
            self.radius = radius
            self.dash = dash
            self.paragraph = Paragraph(text, style)
            self.width = 0
            self.height = 0
        def wrap(self, availWidth, availHeight):
            available_text_width = availWidth - 2 * self.padding
            w, h = self.paragraph.wrap(available_text_width, availHeight - 2 * self.padding)
            self.width = w + 2 * self.padding
            self.height = h + 2 * self.padding
            return self.width, self.height
        def draw(self):
            self.canv.saveState()
            self.canv.setStrokeColor(colors.HexColor('#f8bb42'))
            self.canv.setLineWidth(1)
            self.canv.setDash(self.dash[0], self.dash[1])
            self.canv.roundRect(0, 0, self.width, self.height, self.radius, stroke=1, fill=0)
            self.canv.restoreState()
            self.paragraph.drawOn(self.canv, self.padding, self.padding)
        def split(self, availWidth, availHeight):
            available_text_width = availWidth - 2 * self.padding
            available_text_height = availHeight - 2 * self.padding
            split_paragraphs = self.paragraph.split(available_text_width, available_text_height)
            if not split_paragraphs:
                return []
            flowables = []
            for p in split_paragraphs:
                new_flowable = RoundedBorderedParagraph("", self.style, self.padding, self.radius, self.dash)
                new_flowable.paragraph = p
                w, h = p.wrap(available_text_width, available_text_height)
                new_flowable.width = w + 2 * self.padding
                new_flowable.height = h + 2 * self.padding
                flowables.append(new_flowable)
            return flowables
    class DashedHRFlowable(Flowable):
        def __init__(self, width, thickness=1):
            Flowable.__init__(self)
            self.width = width
            self.thickness = thickness
        def wrap(self, availWidth, availHeight):
            return self.width, self.thickness
        def draw(self):
            self.canv.saveState()
            self.canv.setStrokeColor(colors.HexColor('#f8bb42'))
            self.canv.setLineWidth(self.thickness)
            self.canv.setDash(3, 3)
            self.canv.line(0, self.thickness/2.0, self.width, self.thickness/2.0)
            self.canv.restoreState()
    def add_block(title, text_content, story):
        story.append(Paragraph(title, block_header_style))
        story.append(Spacer(1, 14))
        bordered_paragraph = RoundedBorderedParagraph(text_content, normal_style)
        story.append(bordered_paragraph)
        story.append(Spacer(1, 24))
    def header(canvas, doc):
        width, height = A4
        header_height = 3 * cm
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#f8bb42'))
        canvas.rect(0, height - header_height, width, header_height, stroke=0, fill=1)
        logo_path = os.path.join(base_dir, "logo.png")
        logo_width = 2.5 * cm
        logo_height = 2.5 * cm
        logo_x = 1 * cm
        logo_y = height - header_height + (header_height - logo_height) / 2.0
        try:
            canvas.drawImage(logo_path, logo_x, logo_y, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        text_lines = ["Помогаем реализовывать", "твои таланты"]
        text_font = "MPlusRounded1cB"
        text_size = 20
        text_color = colors.black
        text_x = logo_x + logo_width + 0.5 * cm
        total_text_height = 2 * text_size + 2
        text_y = height - header_height + (header_height + total_text_height) / 2.0 - text_size
        try:
            canvas.setFont(text_font, text_size)
        except Exception:
            canvas.setFont("Helvetica-Bold", text_size)
        canvas.setFillColor(text_color)
        for line in text_lines:
            canvas.drawString(text_x, text_y, line)
            text_y -= text_size + 2
        canvas.restoreState()
    emoji_font_size = normal_style.fontSize
    def safe(text):
        return text if text else ""
    # Преобразуем текстовые переменные заранее (ускоряет работу при редактировании)
    resume = replace_with_emoji_pdf(final_resume, emoji_font_size)
    aggregated_text_prof = replace_with_emoji_pdf(build_aggregated_prof_text(pdf_data), emoji_font_size)
    prof_resume = replace_with_emoji_pdf(prof_resume, emoji_font_size)
    aggregated_text_personality = replace_with_emoji_pdf(build_aggregated_personality_text(pdf_data), emoji_font_size)
    aggregated_text_orientations = replace_with_emoji_pdf(build_aggregated_orientations_text(pdf_data), emoji_font_size)
    aggregated_text_talents = replace_with_emoji_pdf(build_aggregated_talents_text(pdf_data), emoji_font_size)
    talents_resume = replace_with_emoji_pdf(talents_resume, emoji_font_size)
    story = []
    story.append(Paragraph("ПРОФДИЗАЙН", title_style))
    story.append(DashedHRFlowable(A4[0] - 80, thickness=1))
    story.append(Spacer(1, 24))
    # Финальный вывод в начале, как в эталоне
    story.append(Paragraph(resume, normal_style))
    story.append(Spacer(1, 24))
    add_block("Профессиональные склонности", aggregated_text_prof + "<br/><br/>" + prof_resume, story)
    add_block("Личностные особенности", aggregated_text_personality, story)
    add_block("Ценностные ориентиры", aggregated_text_orientations, story)
    add_block("Скрытые таланты", aggregated_text_talents + "<br/><br/>" + talents_resume, story)
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=3*cm + 40, bottomMargin=40)
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return output_path

def get_pdf_output_path(user_name):
    downloads_dir = Path(os.getcwd()) / "downloads"
    # Заменяем только / и \, пробелы оставляем
    safe_name = str(user_name).replace('/', '_').replace('\\', '_')
    return str(downloads_dir / f"Досье {safe_name}.pdf")
