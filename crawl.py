from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

CHROMEDRIVER_PATH = "C:/dmu/chromedriver.exe"  # 크롬드라이버 위치

options = Options()
options.add_argument("--headless")  # 창 안 띄우기
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

service = Service(CHROMEDRIVER_PATH)
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://www.dongyang.ac.kr/dmu/4779/subview.do")
print(driver.title)
print(driver.find_element("css selector", "body").text[:500])
driver.quit()
