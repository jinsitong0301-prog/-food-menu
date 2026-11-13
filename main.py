import asyncio
import random
import unicodedata
from urllib.parse import quote

from pyscript import document, when, window   # 브라우저의 HTML을 파이썬으로 다루는 도구
from pyodide.http import pyfetch              # 파일이 있는지 확인하는 도구

EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]   # 사진 확장자 후보


# =====================================================
# 클래스 1: Food (음식 하나)
#   속성: name, category, photo_url, checked
#   메서드: find_photo()
# =====================================================
class Food:
    def __init__(self, name, category):
        self.name = name            # 음식 이름 (예: 비빔밥)
        self.category = category    # 종류 (한식/중식/양식)
        self.photo_url = None       # 사진 주소 (없으면 None)
        self.checked = False        # 사진을 이미 찾아봤는지

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
#   메서드: get_foods(category)
#   관계: Menu 1 ◆── * Food
# =====================================================
class Menu:
    DATA = {
        "한식": ["김치찌개", "비빔밥", "불고기", "삼겹살", "떡볶이", "순두부찌개",
                "김밥", "냉면", "삼계탕", "부대찌개", "칼국수", "닭갈비"],
        "중식": ["짜장면", "짬뽕", "탕수육", "마라탕", "양꼬치", "마파두부",
                "볶음밥", "훠궈", "딤섬", "깐풍기", "꿔바로우", "유린기"],
        "양식": ["파스타", "피자", "스테이크", "햄버거", "리조또", "샌드위치",
                "샐러드", "오믈렛", "그라탕", "감바스", "로스트치킨", "크림수프"],
    }

    def __init__(self):
        self.foods = []
        for category, names in Menu.DATA.items():
            for name in names:
                self.foods.append(Food(name, category))

    def get_foods(self, category):
        """종류에 맞는 음식 목록 ('전체'면 모두)"""
        if category == "전체":
            return self.foods
        return [f for f in self.foods if f.category == category]


# =====================================================
# 클래스 3: Recommender (랜덤 추천)
#   속성: menu, last_food, count
#   메서드: pick(category), confirm(food)
#   관계: Recommender ──> Menu
# =====================================================
class Recommender:
    def __init__(self, menu):
        self.menu = menu
        self.last_food = None   # 바로 전에 추천한 음식
        self.count = 0          # 지금까지 추천한 횟수

    def pick(self, category):
        """랜덤으로 하나 고르기 (바로 전 음식은 제외)"""
        foods = self.menu.get_foods(category)
        food = random.choice(foods)
        while food is self.last_food and len(foods) > 1:
            food = random.choice(foods)
        return food

    def confirm(self, food):
        """최종 추천으로 확정: 마지막 음식 저장, 횟수 +1"""
        self.last_food = food
        self.count += 1


# =====================================================
# 클래스 4: MenuApp (화면)
#   속성: recommender, category, busy, request_number + 화면 요소들
#   메서드: choose_category(), on_chip_click(), on_click_go(), roll(), show_text(), show_photo(), preload()
#   관계: MenuApp ──> Recommender, MenuApp ┈> Food
# =====================================================
class MenuApp:
    def __init__(self, recommender):
        self.recommender = recommender
        self.category = "전체"
        self.busy = False           # 돌아가는 동안 중복 클릭 방지
        self.request_number = 0     # 옛날 사진이 늦게 도착해서 덮어쓰는 것을 막는 번호

        # 화면의 요소들 (index.html 안의 id)
        self.card = document.getElementById("card")
        self.photo_box = document.getElementById("photoBox")
        self.tag_text = document.getElementById("tagText")
        self.name_text = document.getElementById("nameText")
        self.go_button = document.getElementById("goButton")
        self.hint_text = document.getElementById("hintText")

        # 버튼에 기능 연결
        # (when()은 일반 함수만 받기 때문에, 메서드를 일반 함수로 한 번 감싸서 넘김)
        def chip_clicked(event):
            self.on_chip_click(event)

        def go_clicked(event):
            self.on_click_go(event)

        when("click", ".chip")(chip_clicked)
        when("click", "#goButton")(go_clicked)

        self.hint_text.textContent = "마음에 안 들면 다시 눌러보세요"

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
