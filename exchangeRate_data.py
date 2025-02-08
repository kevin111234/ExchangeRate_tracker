import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import os
from dotenv import load_dotenv

class ExchangeRateCrawler:
    """
    네이버 금융에서 원/달러 환율을 크롤링하는 클래스.
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
        return pd.DataFrame({"Date": date_list, "Exchange Rate": rate_list})

    def run(self):
        urls = self.generate_urls(80)
        df = self.crawl_data(urls)
        df['Date'] = pd.to_datetime(df['Date'], format="%Y.%m.%d")
        return df

class ECOSFetcher:
    """
    한국은행 ECOS API로 데이터를 수집하는 클래스.
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
                print(f"Error fetching data for {stat_code} ({start_index}-{end_index}): {e}")
                break

            rows = data.get("StatisticSearch", {}).get("row", [])
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < per_page:
                break
            start_index += per_page

        if not all_rows:
            print(f"No data found for stat_code={stat_code}, start_date={start_date}, end_date={end_date}")
            return pd.DataFrame()
        return pd.DataFrame(all_rows)

    def clean_data(self, df, spec):
        """
        원본 df에서 TIME, DATA_VALUE 외에 국가나 금리 관련 정보가 담긴 
        ITEM_CODE1, ITEM_NAME1 컬럼이 있으면 함께 보존한 후,
        원하는 컬럼만 남기고 날짜와 값의 형식을 변환한다.
        """
        # ITEM_CODE1, ITEM_NAME1 컬럼이 있으면 extra_cols에 추가
        extra_cols = [col for col in ["ITEM_CODE1", "ITEM_NAME1"] if col in df.columns]
        keep_cols = ["TIME", "DATA_VALUE"] + extra_cols
        df_clean = df[keep_cols].copy()
        
        # 기준금리 데이터 특별 처리
        if spec["name"] == "Policy Interest Rate":
            try:
                # DATA_VALUE를 숫자형으로 변환
                df_clean["DATA_VALUE"] = pd.to_numeric(df_clean["DATA_VALUE"], errors='coerce')
                # 같은 날짜의 데이터는 평균값 사용
                df_clean = df_clean.groupby("TIME", as_index=False).agg({
                    "DATA_VALUE": "mean",
                    "ITEM_CODE1": "first",
                    "ITEM_NAME1": "first"
                })
            except Exception as e:
                print(f"Warning: Error processing Policy Interest Rate data - {e}")
                # 에러 발생 시 원본 데이터 유지
                pass
        
        # 컬럼명 변경: TIME -> Date, DATA_VALUE -> spec["name"]
        df_clean = df_clean.rename(columns={"TIME": "Date", "DATA_VALUE": spec["name"]})
        
        # freq에 따라 날짜 포맷 지정 (연간: %Y, 월간: %Y%m)
        freq = spec.get("freq", "M").upper()
        time_fmt = "%Y" if freq == "A" else "%Y%m"
        df_clean["Date"] = pd.to_datetime(df_clean["Date"], format=time_fmt, errors="coerce")
        df_clean[spec["name"]] = pd.to_numeric(df_clean[spec["name"]], errors="coerce")
        df_clean = df_clean.dropna(subset=["Date", spec["name"]])
        
        return df_clean

    def fetch_multiple_data(self, specs):
        data_dict = {}
        for spec in specs:
            print(f"Fetching data for {spec['name']}...")
            freq = spec.get("freq", "M")
            start_date = spec.get("start_date", "201001")
            end_date = spec.get("end_date", "202512")
            df = self.fetch_data(spec["stat_code"], start_date, end_date, freq)
            if df.empty:
                print(f"No data found for {spec['name']}.")
                data_dict[spec['name']] = pd.DataFrame()
            else:
                df_clean = self.clean_data(df, spec)
                data_dict[spec['name']] = df_clean
        return data_dict

# --- 데이터 분리 함수들 ---
def split_by_country(df, country_keyword):
    """
    ITEM_NAME1 컬럼에 country_keyword가 포함된 행만 추출.
    만약 해당 컬럼이 없으면 원본 df 반환.
    """
    if "ITEM_NAME1" not in df.columns:
        print("ITEM_NAME1 컬럼이 없어 국가별 분리가 불가능합니다.")
        return df
    return df[df["ITEM_NAME1"].str.contains(country_keyword, case=False, na=False)]

def split_by_country_code(df, country_keyword):
    """
    ITEM_NAME1 컬럼에 country_keyword가 포함된 행만 추출.
    만약 해당 컬럼이 없으면 원본 df 반환.
    """
    if "ITEM_CODE1" not in df.columns:
        print("ITEM_CODE1 컬럼이 없어 국가별 분리가 불가능합니다.")
        return df
    return df[df["ITEM_CODE1"].str.contains(country_keyword, case=False, na=False)]

def split_interest_rates(df):
    """
    ITEM_CODE1 컬럼을 기준으로 단기와 장기 금리 데이터를 분리.
    단기: ITEM_CODE1 == "IR3TIB", 장기: ITEM_CODE1 == "IRLT"
    만약 ITEM_CODE1 컬럼이 없으면 전체 df 반환.
    """
    if "ITEM_CODE1" not in df.columns:
        print("ITEM_CODE1 컬럼이 없어 금리 분리가 불가능합니다.")
        return {"long_term": df, "short_term": pd.DataFrame()}
    long_term = df[df["ITEM_CODE1"] == "IRLT"].copy()
    short_term = df[df["ITEM_CODE1"] == "IR3TIB"].copy()
    return {"long_term": long_term, "short_term": short_term}

def split_ktb_yields(df):
    """
    시장금리 데이터에서 국고채 수익률 데이터를 만기별로 분리
    ITEM_CODE1 기준으로 만기별 국고채 수익률 분리
    """
    if "ITEM_CODE1" not in df.columns:
        print("ITEM_CODE1 컬럼이 없어 국고채 수익률 분리가 불가능합니다.")
        return {}
    
    ktb_codes = {
        "1Y": "5030000",
        "3Y": "5020000",
        "5Y": "5040000",
        "10Y": "5050000",
    }
    
    result = {}
    for maturity, code in ktb_codes.items():
        # 코드를 문자열로 변환하여 비교
        ktb_data = df[df["ITEM_CODE1"].astype(str) == code].copy()
        if not ktb_data.empty:
            # 컬럼명 변경
            result[f"KTB_{maturity}"] = ktb_data.rename(
                columns={"KTB Yield": f"KTB_{maturity}_Yield"}
            )
            # 필요한 컬럼만 선택
            result[f"KTB_{maturity}"] = result[f"KTB_{maturity}"][
                ["Date", f"KTB_{maturity}_Yield", "ITEM_CODE1", "ITEM_NAME1"]
            ]
    
    return result

# --- 메인 실행부 ---
def data_saver():
    load_dotenv()
    api_key = os.getenv("ECOS_API_KEY")

    # 수집할 ECOS 데이터 스펙 (미제공 stat_code는 결과가 없을 수 있음)
    data_specs = [
        {"name": "Policy Interest Rate", "stat_code": "722Y001", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "GDP Growth", "stat_code": "902Y015", "freq": "A", "start_date": "2001", "end_date": "2025"},
        {"name": "CPI", "stat_code": "902Y002", "freq": "A", "start_date": "2001", "end_date": "2025"},
        {"name": "Foreign Reserves", "stat_code": "732Y001", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "LT, ST Interest Rate", "stat_code": "902Y023", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "PPI", "stat_code": "902Y007", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "Exports", "stat_code": "902Y012", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "Imports", "stat_code": "902Y013", "freq": "M", "start_date": "200101", "end_date": "202512"},
        {"name": "KTB Yield", "stat_code": "721Y001", "freq": "M", "start_date": "200101", "end_date": "202512"},
    ]
    data_dict = {}

    try:
        fetcher = ECOSFetcher(api_key)
        ecos_data_dict = fetcher.fetch_multiple_data(data_specs)
        for name, df in ecos_data_dict.items():
            if name not in ["GDP Growth", "CPI", "LT, ST Interest Rate", "PPI", "KTB Yield", "Exports", "Imports", "Foreign Reserves"]:
                data_dict[name] = df
    except Exception as e:
        print(f"Error fetching ECOS data: {e}")

    if "Policy Interest Rate" in ecos_data_dict and not ecos_data_dict["Policy Interest Rate"].empty:
        df_interest_rate = ecos_data_dict["Policy Interest Rate"]
        kor_interest_rate = split_by_country_code(df_interest_rate, "0101000")
        data_dict["Policy_Interest_Rate"] = kor_interest_rate

    # -- 국가별 분리 --
    # GDP Growth 데이터에서 미국과 한국 데이터를 분리
    if "GDP Growth" in ecos_data_dict and not ecos_data_dict["GDP Growth"].empty:
        df_gdp = ecos_data_dict["GDP Growth"]
        us_gdp = split_by_country(df_gdp, "United States")
        kor_gdp = split_by_country(df_gdp, "Korea")
        data_dict["US_GDP"] = us_gdp
        data_dict["KOR_GDP"] = kor_gdp

    if "CPI" in ecos_data_dict and not ecos_data_dict["CPI"].empty:
        df_cpi = ecos_data_dict["CPI"]
        us_cpi = split_by_country(df_cpi, "United States")
        kor_cpi = split_by_country(df_cpi, "Korea")
        data_dict["US_CPI"] = us_cpi
        data_dict["KOR_CPI"] = kor_cpi

    if "PPI" in ecos_data_dict and not ecos_data_dict["PPI"].empty:
        df_ppi = ecos_data_dict["PPI"]
        us_ppi = split_by_country(df_ppi, "United States")
        kor_ppi = split_by_country(df_ppi, "Korea")
        data_dict["US_PPI"] = us_ppi
        data_dict["KOR_PPI"] = kor_ppi

    if "Exports" in ecos_data_dict and not ecos_data_dict["Exports"].empty:
        df_export = ecos_data_dict["Exports"]
        us_export = split_by_country_code(df_export, "US")
        kor_export = split_by_country_code(df_export, "KR")
        data_dict["US_Exports"] = us_export
        data_dict["KOR_Exports"] = kor_export

    if "Imports" in ecos_data_dict and not ecos_data_dict["Imports"].empty:
        df_import = ecos_data_dict["Imports"]
        us_import = split_by_country_code(df_import, "US")
        kor_import = split_by_country_code(df_import, "KR")
        data_dict["US_Imports"] = us_import
        data_dict["KOR_Imports"] = kor_import

    if "Foreign Reserves" in ecos_data_dict and not ecos_data_dict["Foreign Reserves"].empty:
        df_FR = ecos_data_dict["Foreign Reserves"]
        kor_FR = split_by_country_code(df_FR, "04")
        data_dict["Foreign_Reserves"] = kor_FR

    # -- 장단기 금리 분리 예시 --
    # LT, ST Interest Rate 데이터에서 장기, 단기 금리로 분리
    if "LT, ST Interest Rate" in ecos_data_dict and not ecos_data_dict["LT, ST Interest Rate"].empty:
        df_ir = ecos_data_dict["LT, ST Interest Rate"]
        ir_split = split_interest_rates(df_ir)
        data_dict["LT_Interest_Rate"]=ir_split["long_term"]
        data_dict["ST_Interest_Rate"]=ir_split["short_term"]
    
    # 국고채 수익률 데이터 분리
    if "KTB Yield" in ecos_data_dict and not ecos_data_dict["KTB Yield"].empty:
        df_ktb = ecos_data_dict["KTB Yield"]
        ktb_yields = split_ktb_yields(df_ktb)
        
        for maturity, df in ktb_yields.items():
            data_dict[f"KTB_{maturity}"] = df

    # 환율 데이터 크롤링
    try:
        crawler = ExchangeRateCrawler()
        exchange_rate_df = crawler.run()
        data_dict["exchange_rate"] = exchange_rate_df
    except Exception as e:
        print(f"Error fetching exchange rate data: {e}")

    return data_dict

if __name__ == "__main__":
    print(data_saver())