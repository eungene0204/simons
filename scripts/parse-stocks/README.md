# 상장법인 목록 파싱 스크립트

Excel 파일에서 상장법인 목록을 파싱하여 `korea-stocks.json`을 생성하는 Python 스크립트입니다.

## 설치

```bash
pip install -r requirements.txt
```

또는

```bash
pip install pandas openpyxl lxml html5lib
```

## 사용법

```bash
python scripts/parse-stocks/parse_stocks.py /path/to/상장법인목록.xls
```

## 출력

- `data/korea-stocks.json`: 파싱된 상장법인 목록 (UTF-8 인코딩)

## 지원 형식

- Excel 파일 (.xls, .xlsx)
- HTML 형식의 Excel 파일 (.xls)

## 데이터 구조

```json
{
  "symbol": "005930",
  "name": "삼성전자",
  "market": "KOSPI",
  "sector": "정보기술",
  "industry": "반도체"
}
```

