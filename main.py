import asyncio
import random
import unicodedata
from datetime import datetime
from urllib.parse import quote

from pyscript import document, when, window   # 브라우저의 화면을 파이썬으로 다루는 도구
from pyodide.http import pyfetch              # 파일이 있는지 확인하는 도구

EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]   # 사진 확장자 후보

# 시간대 이름 (메뉴 데이터를 짧게 쓰기 위한 약어)
B, L, D, N = "아침", "점심", "저녁", "야식"


def make(tag, text="", css_class="", element_id=""):
    """화면 요소(HTML 태그)를 파이썬에서 만들어 주는 도우미 함수"""
    element = document.createElement(tag)
    if text:
        element.textContent = text
    if css_class:
        element.className = css_class
    if element_id:
        element.id = element_id
    return element


# =====================================================
# 클래스 1: Food (음식 하나)
#   속성: name, category, meal_times, weight, likes, dislikes, photo_url, checked
#   메서드: like(), dislike(), find_photo()
# =====================================================
class Food:
    MAX_WEIGHT = 8.0     # 가중치 최댓값
    MIN_WEIGHT = 0.1     # 가중치 최솟값 (0이 되면 영영 안 나오므로 조금 남김)

    def __init__(self, name, category, meal_times):
        self.name = name                # 음식 이름
        self.category = category        # 종류 (한식/중식/양식)
        self.meal_times = meal_times    # 어울리는 시간대 목록
        self.weight = 1.0               # 추천될 확률의 가중치 (클수록 잘 나옴)
        self.likes = 0                  # 좋아요 횟수
        self.dislikes = 0               # 싫어요 횟수
        self.photo_url = None           # 사진 주소 (없으면 None)
        self.checked = False            # 사진을 이미 찾아봤는지

    def like(self):
        """좋아요: 가중치를 2배로 (최대 8)"""
        self.likes += 1
        self.weight = min(self.weight * 2, Food.MAX_WEIGHT)

    def dislike(self):
        """싫어요: 가중치를 절반으로 (최소 0.1)"""
        self.dislikes += 1
        self.weight = max(self.weight / 2, Food.MIN_WEIGHT)

    async def find_photo(self):
        """images 폴더에서 '음식이름.jpg' 등을 찾아서 주소를 반환. 없으면 None"""
        if not self.checked:
            safe_name = quote(unicodedata.normalize("NFC", self.name))
            for ext in EXTENSIONS:
                url = "images/" + safe_name + ext
                try:
                    res = await pyfetch(url, method="HEAD")
                    if res.ok:
                        self.photo_url = url
                        break
                except Exception:
                    pass
            self.checked = True
        return self.photo_url


# =====================================================
# 클래스 2: Menu (전체 메뉴 목록)
#   속성: DATA, foods
#   메서드: get_foods(category, slot)
#   관계: Menu 1 ◆── * Food
# =====================================================
class Menu:
    # (음식 이름, 어울리는 시간대)  ※ 시간대는 직접 고쳐도 됨
    DATA = {
        "한식": [("김치찌개", [L, D]), ("비빔밥", [L, D]), ("불고기", [L, D]), ("삼겹살", [D, N]),
                ("떡볶이", [L, D, N]), ("순두부찌개", [B, L, D]), ("김밥", [B, L]), ("냉면", [L, D]),
                ("삼계탕", [L, D]), ("부대찌개", [L, D, N]), ("칼국수", [L, D]), ("닭갈비", [L, D, N])],
        "중식": [("짜장면", [L, D, N]), ("짬뽕", [L, D, N]), ("탕수육", [L, D, N]), ("마라탕", [L, D, N]),
                ("양꼬치", [D, N]), ("마파두부", [L, D]), ("볶음밥", [L, D]), ("훠궈", [D]),
                ("딤섬", [B, L]), ("깐풍기", [D, N]), ("꿔바로우", [D, N]), ("유린기", [L, D])],
        "양식": [("파스타", [L, D]), ("피자", [L, D, N]), ("스테이크", [D]), ("햄버거", [B, L, D, N]),
                ("리조또", [L, D]), ("샌드위치", [B, L]), ("샐러드", [B, L]), ("오믈렛", [B]),
                ("그라탕", [L, D]), ("감바스", [D, N]), ("로스트치킨", [D]), ("크림수프", [B, L])],
    }

    def __init__(self):
        self.foods = []
        for category, items in Menu.DATA.items():
            for name, times in items:
                self.foods.append(Food(name, category, times))

    def get_foods(self, category, slot=None):
        """종류(와 시간대)에 맞는 음식 목록. 조건에 맞는 음식이 없으면 종류만으로 반환"""
        if category == "전체":
            foods = self.foods
        else:
            foods = [f for f in self.foods if f.category == category]

        if slot is not None:
            timed = [f for f in foods if slot in f.meal_times]
            if timed:
                return timed
        return foods


# =====================================================
# 클래스 3: TimeSlot (지금이 어느 시간대인지)
#   메서드: get_hour(), current()
# =====================================================
class TimeSlot:
    # (시작 시, 끝 시, 이름)  → 그 외 시간(22시~다음 날 5시)은 야식
    SLOTS = [(5, 11, B), (11, 16, L), (16, 22, D)]

    @staticmethod
    def get_hour():
        """지금 몇 시인지 (브라우저의 시간 기준)"""
        try:
            return int(window.Date.new().getHours())
        except Exception:
            return datetime.now().hour

    @staticmethod
    def current():
        """지금 시간대 이름 반환 (아침/점심/저녁/야식)"""
        hour = TimeSlot.get_hour()
        for start, end, name in TimeSlot.SLOTS:
            if start <= hour < end:
                return name
        return N


# =====================================================
# 클래스 4: Recommender (가중치 랜덤 추천)
#   속성: menu, last_food, count, use_time
#   메서드: toggle_time_mode(), pick(category), confirm(food)
#   관계: Recommender ──> Menu, Recommender ┈> TimeSlot
# =====================================================
class Recommender:
    def __init__(self, menu):
        self.menu = menu
        self.last_food = None   # 바로 전에 추천한 음식
        self.count = 0          # 지금까지 추천한 횟수
        self.use_time = False   # 시간대 추천을 켰는지

    def toggle_time_mode(self):
        """시간대 추천 켜기/끄기. 바뀐 상태를 반환"""
        self.use_time = not self.use_time
        return self.use_time

    def pick(self, category):
        """가중치 랜덤으로 1개 고르기 (바로 전 음식은 제외)"""
        slot = TimeSlot.current() if self.use_time else None
        foods = self.menu.get_foods(category, slot)

        candidates = [f for f in foods if f is not self.last_food]
        if not candidates:                   # 음식이 하나뿐이면 어쩔 수 없이 그대로
            candidates = foods

        weights = [f.weight for f in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def confirm(self, food):
        """최종 추천으로 확정: 마지막 음식 저장, 횟수 +1"""
        self.last_food = food
        self.count += 1


# =====================================================
# 클래스 5: MenuApp (화면)
#   속성: recommender, category, busy, request_number + 화면 요소들
#   메서드: build_screen(), choose_category(), on_chip_click(), on_time_click(),
#          on_click_go(), roll(), show_text(), show_photo(), on_like(), on_dislike(), preload()
#   관계: MenuApp ──> Recommender, MenuApp ┈> Food, MenuApp ┈> TimeSlot
# =====================================================
class MenuApp:
    def __init__(self, recommender):
        self.recommender = recommender
        self.category = "전체"
        self.busy = False           # 돌아가는 동안 중복 클릭 방지
        self.request_number = 0     # 옛날 사진이 늦게 도착해서 덮어쓰는 것을 막는 번호

        self.build_screen()         # 화면을 파이썬으로 만들기
        self.connect_buttons()      # 버튼에 기능 연결

    # ----- 화면 만들기 (HTML 없이 파이썬으로 요소를 만들어 붙임) -----
    def build_screen(self):
        app = document.getElementById("app")
        app.textContent = ""                     # "불러오는 중..." 문구 지우기

        main = make("main")
        main.appendChild(make("h1", "오늘 뭐 먹지?"))

        # 종류 버튼
        chips = make("div", css_class="chips")
        for name in ["전체", "한식", "중식", "양식"]:
            chip = make("button", name, "chip")
            chip.setAttribute("data-c", name)
            chip.setAttribute("aria-pressed", "true" if name == "전체" else "false")
            chips.appendChild(chip)
        main.appendChild(chips)

        # 시간대 추천 줄
        row = make("div", css_class="timerow")
        self.time_button = make("button", "시간대 추천: 끔", "toggle", "timeButton")
        self.time_button.setAttribute("aria-pressed", "false")
        self.time_text = make("span", css_class="timetext")
        self.time_text.textContent = f"지금은 {TimeSlot.current()} 시간이에요"
        row.appendChild(self.time_button)
        row.appendChild(self.time_text)
        main.appendChild(row)

        # 결과 카드
        self.card = make("section", css_class="card", element_id="card")
        self.photo_box = make("div", "사진이 여기에 나와요", "photo")
        self.tag_text = make("div", "버튼을 눌러 시작하세요", "tag")
        self.name_text = make("div", "?", "name")
        self.card.appendChild(self.photo_box)
        self.card.appendChild(self.tag_text)
        self.card.appendChild(self.name_text)
        main.appendChild(self.card)

        # 좋아요 / 싫어요
        fbrow = make("div", css_class="fbrow")
        self.like_button = make("button", "좋아요", "fb", "likeButton")
        self.dislike_button = make("button", "싫어요", "fb", "dislikeButton")
        fbrow.appendChild(self.like_button)
        fbrow.appendChild(self.dislike_button)
        main.appendChild(fbrow)

        # 큰 버튼과 안내 문구
        self.go_button = make("button", "골라줘", "go", "goButton")
        self.hint_text = make("p", "마음에 안 들면 다시 눌러보세요", "hint")
        main.appendChild(self.go_button)
        main.appendChild(self.hint_text)

        app.appendChild(main)

    # ----- 버튼에 기능 연결 -----
    def connect_buttons(self):
        # when()은 일반 함수만 받기 때문에, 메서드를 일반 함수로 한 번 감싸서 넘김
        def chip_clicked(event):
            self.on_chip_click(event)

        def time_clicked(event):
            self.on_time_click(event)

        def go_clicked(event):
            self.on_click_go(event)

        def like_clicked(event):
            self.on_like(event)

        def dislike_clicked(event):
            self.on_dislike(event)

        when("click", ".chip")(chip_clicked)
        when("click", "#timeButton")(time_clicked)
        when("click", "#goButton")(go_clicked)
        when("click", "#likeButton")(like_clicked)
        when("click", "#dislikeButton")(dislike_clicked)

    # ----- 종류 선택 -----
    def on_chip_click(self, event=None):
        self.choose_category(event.target.getAttribute("data-c"))

    def choose_category(self, name):
        self.category = name
        chips = document.querySelectorAll(".chip")
        for chip in chips:
            if chip.getAttribute("data-c") == name:
                chip.setAttribute("aria-pressed", "true")
            else:
                chip.setAttribute("aria-pressed", "false")

    # ----- 시간대 추천 켜기/끄기 -----
    def on_time_click(self, event=None):
        is_on = self.recommender.toggle_time_mode()
        slot = TimeSlot.current()
        if is_on:
            self.time_button.textContent = "시간대 추천: 켬"
            self.time_button.setAttribute("aria-pressed", "true")
            self.hint_text.textContent = f"지금은 {slot} 시간이라서, {slot}에 어울리는 메뉴만 나와요"
        else:
            self.time_button.textContent = "시간대 추천: 끔"
            self.time_button.setAttribute("aria-pressed", "false")
            self.hint_text.textContent = "시간대 추천을 껐어요. 모든 메뉴가 나와요"
        self.time_text.textContent = f"지금은 {slot} 시간이에요"

    # ----- "골라줘 / 다른 거" 버튼 -----
    def on_click_go(self, event=None):
        if self.busy:
            return
        self.busy = True
        asyncio.ensure_future(self.roll())

    async def roll(self):
        """70ms마다 음식 이름을 바꾸다가 7번째에 확정"""
        self.request_number += 1                 # 이전 사진 요청은 무효로 만들기
        self.photo_box.textContent = "고르는 중..."
        self.card.classList.add("roll")

        for _ in range(7):
            self.show_text(self.recommender.pick(self.category))
            await asyncio.sleep(0.07)

        food = self.recommender.pick(self.category)
        self.recommender.confirm(food)
        self.show_text(food)

        self.card.classList.remove("roll")
        self.go_button.textContent = "다른 거"
        self.hint_text.textContent = f"{self.recommender.count}번 바꿨어요. 마음에 안 들면 다시 눌러요"
        self.busy = False

        await self.show_photo(food)

    # ----- 좋아요 / 싫어요 (가중치 조절) -----
    def on_like(self, event=None):
        food = self.recommender.last_food
        if food is None:
            self.hint_text.textContent = "먼저 '골라줘'를 눌러 주세요"
            return
        food.like()
        self.hint_text.textContent = f"{food.name}을(를) 더 자주 추천할게요 (가중치 ×{food.weight:g})"

    def on_dislike(self, event=None):
        food = self.recommender.last_food
        if food is None:
            self.hint_text.textContent = "먼저 '골라줘'를 눌러 주세요"
            return
        food.dislike()
        self.hint_text.textContent = f"{food.name}은(는) 덜 추천할게요 (가중치 ×{food.weight:g})"

    # ----- 결과 표시 -----
    def show_text(self, food):
        self.tag_text.textContent = food.category
        self.name_text.textContent = food.name

    async def show_photo(self, food):
        self.request_number += 1
        my_number = self.request_number
        self.photo_box.textContent = "불러오는 중..."

        url = await food.find_photo()
        if my_number != self.request_number:     # 그 사이 새 요청이 있었으면 버림
            return

        self.photo_box.textContent = ""
        if url:
            img = document.createElement("img")
            img.src = url
            img.alt = food.name
            self.photo_box.appendChild(img)
        else:
            self.photo_box.textContent = "이미지 없음"

    # ----- 페이지가 열리면 모든 사진을 미리 불러와 두기 -----
    async def preload(self):
        for food in self.recommender.menu.foods:
            url = await food.find_photo()
            if url:
                try:
                    warm = window.Image.new()
                    warm.src = url
                except Exception:
                    pass


# ---------- 프로그램 시작 ----------
menu = Menu()
recommender = Recommender(menu)
app = MenuApp(recommender)
asyncio.ensure_future(app.preload())
