import json
import os
import pandas as pd
from pathlib import Path
from tqdm import tqdm

# Define industry-to-sector mapping based on keywords
# Sectors defined in Step1Universe.tsx
SECTORS = [
    "반도체", "이차전지", "디스플레이/부품", "IT 하드웨어", "소프트웨어/플랫폼", "게임", 
    "바이오/제약", "의료기기", "반도체 소재", "자동차", "자동차부품", "에너지/원자력", "화학", 
    "철강/금속", "조선/해운", "기계/장비", "우주항공/방산", "건설", "운송/물류", 
    "은행/금융지주", "증권/보험", "유통/상사", "화장품/패션", "식품/음료", "미디어/엔터", "통신/유틸리티", "교육", "부동산", "종이", "가구/인테리어", "시멘트", "수산", "수산가공", "욕실", "사료/축산", "목재", "기타 서비스", "기타 제조업"
]

MAPPING_RULES = {
    "반도체": ["반도체"],
    "이차전지": ["배터리", "축전지", "이차전지", "전지", "양극재", "음극재", "분리막", "전해질", "리튬"],
    "디스플레이/부품": ["디스플레이", "패널", "LCD", "OLED", "LED", "전자부품", "회로", "PCB", "인쇄회로"],
    "IT 하드웨어": ["하드웨어", "전자제품", "컴퓨터", "장비", "전기장비", "전기전자", "명영상", "통신장비", "네트워크장비", "절연선", "케이블", "측정", "정밀기기", "계측", "센서", "시험", "광학기기", "음향기기", "가정용 기기"],
    "소프트웨어/플랫폼": ["소프트웨어", "애플리케이션", "플랫폼", "보안", "포털", "클라우드", "데이터", "인공지능", "AI", "정보 서비스", "전문 서비스"],
    "게임": ["게임", "모바일 게임", "온라인 게임"],
    "바이오/제약": ["바이오", "생명공학", "유전자", "세포", "임상", "바이오닉스", "시약", "제약", "의약품", "의약", "보건", "기초 의약", "완제 의약", "연구개발", "나노"],
    "의료기기": ["의료용 기기", "의료기기", "의학 및 치과용", "건강관리", "진단", "헬스케어"],
    "반도체 소재": ["웨이퍼", "포토레지스트", "블랭크마스크", "특수가스", "반도체 케미칼", "희귀가스", "에칭", "식각", "증착", "세정", "CMP", "봉지재", "감광액", "PR", "포토마스크", "펠리클", "전구체", "쿼츠", "전자재료", "반도체 부품", "반도체 재료"],
    "자동차": ["자동차 제조업", "완성차", "자동차 신품", "승용차"],
    "자동차부품": ["자동차부품", "자동차용", "트레일러", "자동차 부품"],
    "에너지/원자력": ["원자력", "원전", "태양광", "풍력", "에너지", "석유", "가스", "정유", "열공급", "발전", "원자력", "수소", "발전소", "정비", "탄소", "배출권", "전력 관리"],
    "화학": ["화학", "고무", "플라스틱", "비료", "도료", "잉크", "세정제", "금속", "유리", "세라믹", "강재", "소재", "연마", "판유리", "석재", "첨단소재"],
    "철강/금속": ["철강", "제강", "제철", "비철금속"],
    "조선/해운": ["조선", "선박", "선체", "해운", "항만", "운송 (수상)"],
    "기계/장비": ["기계", "엔진", "터빈", "공작", "금형", "밸브", "베어링", "펌프", "승강기", "로봇", "공장자동화", "설비", "설치"],
    "우주항공/방산": ["항공", "공항", "항공기", "방위", "방산", "전투기", "위성", "무기", "총포탄"],
    "건설": ["건설", "토목", "건축", "시설물 축조", "전문공사"],
    "운송/물류": ["운송", "택배", "물류", "창고", "육상운송", "상업서비스"],
    "은행/금융지주": ["은행", "지주", "금융 지원", "기타 금융"],
    "증권/보험": ["증권", "투자심매", "보험", "카드", "캐피탈", "리스", "창투", "신탁", "투자", "경영 컨설팅", "벤처캐피탈", "다각화금융"],
    "유통/상사": ["유통", "도매", "소매", "백화점", "마트", "편의점", "중개", "종합상사", "전자상거래", "판매업", "소비재"],
    "화장품/패션": ["화장품", "비누", "미용", "섬유", "의류", "봉제", "신발", "가죽", "방직", "의복", "의류 제조업", "직물", "방적", "편조"],
    "식품/음료": ["식품", "식료품", "육가공", "제과", "제빵", "설탕", "낙농", "도축", "음료", "주류", "커피", "담배", "가공", "저장", "농산물", "채소"],
    "미디어/엔터": ["미디어", "엔터", "방송", "영화", "음반", "신문", "웹툰", "콘텐츠", "광고업", "출판업", "관광", "명지", "유원지", "오락", "카지노", "예술", "창작", "오디오물", "녹음", "여행", "숙박"],
    "통신/유틸리티": ["통신", "통신서비스", "유틸리티", "전기", "수도", "증기"],
    "교육": ["교육", "학원", "학교", "이러닝", "온라인 교육"],
    "부동산": ["부동산", "리츠", "부동산 임대 및 공급업"],
    "종이": ["펄프", "제지", "판지", "골판지", "종이 상자"],
    "가구/인테리어": ["가구 제조업", "가구", "침대", "조명", "전구"],
    "시멘트": ["시멘트, 석회, 플라스터 제조업", "시멘트", "석회", "플라스터", "콘크리트"],
    "수산": ["어로 어업", "어업", "어로"],
    "수산가공": ["수산물 가공", "씨푸드", "수산물"],
    "욕실": ["요업제품", "내화 요업", "비내화 요업", "위생도기", "수전", "타일"],
    "사료/축산": ["배합 사료", "사료", "도축", "육류 가공", "축산", "육가공"],
    "목재": ["나무제품", "목재", "합판", "마루"],
    "기타 서비스": ["서비스"],
    "기타 제조업": ["제조업", "기타 제품"],
}

# Explicit overrides for major stocks to ensure UI consistency
OVERRIDDEN_SYMBOLS = {
    "005930": "반도체", # Samsung
    "000660": "반도체", # Hynix
    "373220": "이차전지", # LG Energy Solution
    "005380": "자동차", # Hyundai
    "000270": "자동차", # Kia
    "035420": "소프트웨어/플랫폼", # Naver
    "035720": "소프트웨어/플랫폼", # Kakao
    "207940": "바이오/제약", # Samsung Biologics
    "068270": "바이오/제약", # Celltrion
    "326030": "바이오/제약", # SK Biopharm
    "330860": "반도체", # 네패스아크
    "381970": "유통/상사", # 케이카
    "025870": "수산가공", # 신라에스지
    "036580": "사료/축산", # 팜스코
    "006910": "사료/축산", # 우성
    "007460": "바이오/제약", # 에이프로젠
    "041910": "바이오/제약", # 폴라리스AI파마
    "054180": "바이오/제약", # 메디콕스
    "226330": "바이오/제약", # 신테카바이오
    "071200": "의료기기", # 인피니트헬스케어
    "086520": "이차전지", # 에코프로
}

def get_sector_from_industry(symbol, industry, name=""):
    if symbol in OVERRIDDEN_SYMBOLS:
        return OVERRIDDEN_SYMBOLS[symbol]
        
    combined_text = f"{industry} {name}".lower() if name else str(industry).lower()
    
    if not combined_text or combined_text == "nan":
        return "기타 제조업"
    
    # Priority ordered match
    for sector in [
        "반도체", "반도체 소재", "이차전지", "디스플레이/부품", "소프트웨어/플랫폼", "게임", 
        "바이오/제약", "자동차", "에너지/원자력", "부동산", "수산", "수산가공", "욕실", "사료/축산", "교육", "목재"
    ]:
        if sector in MAPPING_RULES:
            for kw in MAPPING_RULES[sector]:
                if kw.lower() in combined_text:
                    return sector

    # General match for rest
    for sector, keywords in MAPPING_RULES.items():
        for kw in keywords:
            if kw.lower() in combined_text:
                return sector
    
    # Fallback to ensure no nulls
    if "서비스" in combined_text or "업" in combined_text:
        return "기타 서비스"
    
    return "기타 제조업"

def main():
    base_dir = Path("/Users/eugene/nullalgo/simons")
    stocks_path = base_dir / "data" / "korea-stocks.json"
    ohlcv_dir = base_dir / "data" / "ohlcv"
    
    print(f"Loading {stocks_path}...")
    with open(stocks_path, "r", encoding="utf-8") as f:
        stocks = json.load(f)
    
    print("Mapping industries to sectors...")
    mapped_count = 0
    symbol_to_sector = {}
    
    for stock in stocks:
        symbol = stock.get("symbol")
        industry = stock.get("industry")
        name = stock.get("name", "")
        sector = get_sector_from_industry(symbol, industry, name)
        if sector:
            stock["sector"] = sector
            symbol_to_sector[symbol] = sector
            mapped_count += 1
        else:
            stock["sector"] = None
            
    print(f"Mapped {mapped_count} / {len(stocks)} stocks.")
    
    # Save enriched JSON
    with open(stocks_path, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)
    print("Updated korea-stocks.json")
    
    # Update Parquet files
    parquet_files = list(ohlcv_dir.glob("*.parquet"))
    print(f"Enriching {len(parquet_files)} Parquet files...")
    
    updated_parquets = 0
    for file_path in tqdm(parquet_files):
        symbol = file_path.stem
        sector = symbol_to_sector.get(symbol)
        if not sector:
            continue
            
        try:
            df = pd.read_parquet(file_path)
            # Add sector column
            df["sector"] = sector
            df.to_parquet(file_path)
            updated_parquets += 1
        except Exception as e:
            print(f"Error updating {file_path}: {e}")
            
    print(f"Successfully updated {updated_parquets} Parquet files.")

if __name__ == "__main__":
    main()
