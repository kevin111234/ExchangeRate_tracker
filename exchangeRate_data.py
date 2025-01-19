import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import os
from dotenv import load_dotenv

class ExchangeRateCrawler:
    """
    A class to crawl exchange rate data from Naver Finance.
    """
    def __init__(self):
        self.base_url = 'https://finance.naver.com/marketindex/exchangeDailyQuote.naver?marketindexCd=FX_USDKRW&page='

    def generate_urls(self, pages):
        return [f'{self.base_url}{i+1}' for i in range(pages)]

    def crawl_data(self, urls):
        date_list = []
        rate_list = []
        for url in tqdm(urls, desc="Crawling progress", unit="page"):
            response = requests.get(url)
            soup = BeautifulSoup(response.content, "html.parser")
            for row in soup.find_all("tr"):
                cells_date = row.find_all("td", class_="date")
                cells_num = row.find_all("td", class_="num")
                if cells_date and cells_num:
                    date_text = cells_date[0].text.strip()
                    rate_text = cells_num[0].text.strip().replace(",", "")
                    date_list.append(date_text)
                    rate_list.append(float(rate_text))

        return pd.DataFrame({
            "Date": date_list,
            "Exchange Rate": rate_list
        })

    def run(self):
        urls = self.generate_urls(80)
        df = self.crawl_data(urls)
        df['Date'] = pd.to_datetime(df['Date'], format="%Y.%m.%d")
        return df

class ECOSFetcher:
    """
    A class to fetch data from the Bank of Korea ECOS API.
    """

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://ecos.bok.or.kr/api/StatisticSearch"

    def fetch_data(self, stat_code, start_date, end_date, freq):
        url = f"{self.base_url}/{self.api_key}/json/en/1/1000/{stat_code}/{freq}/{start_date}/{end_date}/"

        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch data: HTTP {response.status_code}")

        data = response.json()
        rows = data.get("StatisticSearch", {}).get("row", [])
        if not rows:
            print(f"No data found for stat_code={stat_code}, start_date={start_date}, end_date={end_date}")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df[["TIME", "DATA_VALUE"]].rename(columns={"TIME": "Date", "DATA_VALUE": stat_code})

    def fetch_multiple_data(self, specs):
        data_dict = {}

        for spec in specs:
            print(f"Fetching data for {spec['name']}...")
            freq = spec.get("freq", "M")  # Use frequency specified for each dataset or default to "M"
            start_date = spec.get("start_date", "201001")
            end_date = spec.get("end_date", "202512")
            df = self.fetch_data(spec["stat_code"], start_date, end_date, freq)
            if df.empty:
                print(f"No data found for {spec['name']}.")
                data_dict[spec['name']] = pd.DataFrame()
            else:
                df = df.rename(columns={spec["stat_code"]: spec["name"]})
                data_dict[spec['name']] = df

        return data_dict

if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("ECOS_API_KEY")

    # Instantiate ECOSFetcher
    fetcher = ECOSFetcher(api_key)

    # Define datasets to fetch
    data_specs = [
        {"name": "Policy Interest Rate", "stat_code": "722Y001", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "GDP Growth", "stat_code": "902Y015", "freq": "A", "start_date": "2001", "end_date": "2021"},
        {"name": "CPI", "stat_code": "902Y002", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "Foreign Reserves", "stat_code": "901Y020", "freq": "M", "start_date": "201001", "end_date": "202512"}
    ]

    # Fetch ECOS data
    try:
        ecos_data_dict = fetcher.fetch_multiple_data(data_specs)
        for name, df in ecos_data_dict.items():
            print(f"Data for {name}:")
            print(df.head())
    except Exception as e:
        print(f"Error fetching ECOS data: {e}")

    # Crawl exchange rate data
    try:
        crawler = ExchangeRateCrawler()
        exchange_rate_df = crawler.run()
        print("Exchange Rate Data:")
        print(exchange_rate_df.head())
    except Exception as e:
        print(f"Error fetching exchange rate data: {e}")

# 필요한 데이터
"""
경제 성장률: 한국의 경제 성장률이 미국보다 높으면 원화가 강세를 보이고, 반대의 경우 달러화가 강세를 보입니다.

무역 수지: 한국의 대미 무역 수지 흑자 규모가 클수록 원화 강세 압력이 높아집니다. 반대로 무역 적자가 커지면 달러화 강세 압력이 높아집니다.

금리 차이: 미국의 기준금리가 한국보다 높으면 달러화 강세 요인이 됩니다.

외국인 투자 동향: 외국인의 한국 주식 및 채권 투자 규모 변화가 환율에 영향을 줍니다. 외국인 자금 유출시 원화 약세 요인이 됩니다.

국제 원자재 가격: 국제 유가, 곡물 가격 등 원자재 가격 변동은 수출입 물가에 영향을 미쳐 환율 변동을 초래합니다.

시장 심리: 투자자들의 환율에 대한 심리적 기대감도 실제 환율 변동에 영향을 줍니다.
"""

"""
무역수지
    무역수지 데이터는 보통 월별로 발표되므로 월별 시계열 데이터로 구축
    무역수지 금액을 GDP 대비 비율로 변환하여 활용하면 더욱 유의미한 지표가 될 수 있음
    계절성 요인 제거를 위해 12개월 이동평균 등을 활용할 수 있음

금리 차이
    한국과 미국의 정책금리, 국채금리, 회사채금리 등 다양한 금리지표를 활용 가능
    두 국가 간 금리 차이를 계산하여 시계열 데이터로 구축
    금리 데이터는 일별, 주별 등 고빈도로 관측되므로 적절한 주기로 집계

외국인 투자 동향
    외국인의 주식/채권 순매수 규모를 시계열 데이터로 구축
    외국인 투자 비중 등 다른 지표들도 함께 고려할 수 있음
    계절성, 추세 등 제거를 위해 데이터 정규화 및 차분 등의 전처리 필요

경제성장률 차이
    한국과 미국의 분기별 GDP 성장률 데이터를 활용
    두 국가 간 성장률 차이를 계산하여 시계열 데이터로 구축
    계절조정 데이터 사용, 전년동기 대비 증감률 등으로 변환 가능

물가상승률 차이
    한국과 미국의 소비자물가지수(CPI) 데이터를 활용
    두 국가 간 물가상승률 차이를 계산하여 시계열 데이터로 구축
    계절조정, 근원 물가지수 등으로 변환하여 활용 가능

정책금리 차이
    한국과 미국의 기준금리 데이터를 활용
    두 국가 간 정책금리 차이를 계산하여 시계열 데이터로 구축

국제 원자재 가격
    국제 유가, 곡물가격 등의 시계열 데이터를 구축
    가격 변동성, 변동폭 등의 지표로 활용 가능
"""