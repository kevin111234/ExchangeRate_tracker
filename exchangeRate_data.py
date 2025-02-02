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
        per_page = 1000
        start_index = 1
        all_rows = []

        while True:
            end_index = start_index + per_page - 1
            url = f"{self.base_url}/{self.api_key}/json/en/{start_index}/{end_index}/{stat_code}/{freq}/{start_date}/{end_date}/"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                print(f"Error fetching data for {stat_code} from {start_index} to {end_index}: {e}")
                break

            rows = data.get("StatisticSearch", {}).get("row", [])
            if not rows:
                break

            all_rows.extend(rows)
            # 만약 반환된 데이터 수가 per_page 미만이면 마지막 페이지
            if len(rows) < per_page:
                break

            start_index += per_page

        if not all_rows:
            print(f"No data found for stat_code={stat_code}, start_date={start_date}, end_date={end_date}")
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)

        return df

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
        {"name": "GDP Growth", "stat_code": "902Y015", "freq": "A", "start_date": "2001", "end_date": "2024"},
        {"name": "CPI", "stat_code": "902Y002", "freq": "A", "start_date": "2010", "end_date": "2024"},
        {"name": "Foreign Reserves", "stat_code": "901Y020", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "US Policy Interest Rate", "stat_code": "722Y002", "freq": "M", "start_date": "201001", "end_date": "202512"}, # 실행안됨
        {"name": "LT, ST Interest Rate", "stat_code": "902Y023", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "PPI", "stat_code": "902Y003", "freq": "A", "start_date": "2010", "end_date": "202512"}, # 실행안됨
        {"name": "Exports", "stat_code": "901Y010", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "Imports", "stat_code": "901Y011", "freq": "M", "start_date": "201001", "end_date": "202512"},
        {"name": "KTB Yield", "stat_code": "401Y001", "freq": "M", "start_date": "201001", "end_date": "202512"}, # 실행안됨
        {"name": "IRS", "stat_code": "IRS001", "freq": "M", "start_date": "201001", "end_date": "202512"}, # 실행안됨
        {"name": "CCS", "stat_code": "CCS001", "freq": "M", "start_date": "201001", "end_date": "202512"}, # 실행안됨
        ]

    # Fetch ECOS data
    try:
        ecos_data_dict = fetcher.fetch_multiple_data(data_specs)
        for name, df in ecos_data_dict.items():
            print(f"Data for {name}:")
            print(df)
    except Exception as e:
        print(f"Error fetching ECOS data: {e}")

    # Crawl exchange rate data
    try:
        crawler = ExchangeRateCrawler()
        exchange_rate_df = crawler.run()
        print("Exchange Rate Data:")
        print(exchange_rate_df)
    except Exception as e:
        print(f"Error fetching exchange rate data: {e}")
