#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
상장법인 목록 Excel 파일을 파싱하여 korea-stocks.json을 생성하는 스크립트

사용법:
    python scripts/parse-stocks/parse_stocks.py /path/to/상장법인목록.xls
"""

import sys
import json
import os
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("pandas가 설치되지 않았습니다. 설치 중...")
    os.system("pip install pandas openpyxl")
    import pandas as pd


def parse_stocks_from_excel(file_path):
    """Excel 파일에서 상장법인 목록을 파싱합니다."""
    print(f"Excel 파일 읽기: {file_path}")
    
    # Excel 파일 읽기 (HTML 형식이거나 실제 Excel 형식 모두 지원)
    try:
        # 먼저 HTML 형식으로 시도
        if file_path.endswith('.xls') or file_path.endswith('.html'):
            # HTML 테이블로 읽기
            try:
                # euc-kr 인코딩으로 읽기
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                # euc-kr을 utf-8로 변환
                try:
                    content = content.decode('euc-kr')
                except UnicodeDecodeError:
                    # utf-8로 시도
                    content = content.decode('utf-8', errors='ignore')
                
                # HTML 테이블 읽기
                dfs = pd.read_html(content, encoding='utf-8')
                if dfs:
                    df = dfs[0]
                else:
                    raise ValueError("HTML 테이블을 찾을 수 없습니다.")
            except Exception as e:
                print(f"HTML 파싱 실패: {e}")
                # 실제 Excel 파일로 시도
                df = pd.read_excel(file_path, engine='openpyxl')
        else:
            # 실제 Excel 파일로 읽기
            df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        print(f"Excel 파일 읽기 실패: {e}")
        print("HTML 형식으로 다시 시도 중...")
        # HTML 형식으로 다시 시도
        with open(file_path, 'rb') as f:
            content = f.read()
        try:
            content = content.decode('euc-kr')
        except UnicodeDecodeError:
            content = content.decode('utf-8', errors='ignore')
        dfs = pd.read_html(content, encoding='utf-8')
        if dfs:
            df = dfs[0]
        else:
            raise ValueError("파일을 파싱할 수 없습니다.")
    
    print(f"총 {len(df)} 행을 찾았습니다.")
    print(f"컬럼: {list(df.columns)}")
    
    # 헤더 매핑 찾기
    header_map = {}
    for idx, col in enumerate(df.columns):
        col_str = str(col).strip()
        col_lower = col_str.lower()
        
        if '회사명' in col_str or '종목명' in col_str or '기업명' in col_str:
            header_map['name'] = idx
        if '종목코드' in col_str or '코드' in col_str:
            header_map['symbol'] = idx
        if '시장' in col_str or '시장구분' in col_str:
            header_map['market'] = idx
        if '업종' in col_str or '산업' in col_str:
            header_map['industry'] = idx
        if '섹터' in col_str or '부문' in col_str:
            header_map['sector'] = idx
    
    # 헤더가 제대로 매핑되지 않았으면 기본 순서 사용
    if not header_map:
        print("헤더 매핑 실패, 기본 순서 사용: 회사명, 시장구분, 종목코드, 업종")
        if len(df.columns) >= 4:
            header_map = {
                'name': 0,
                'market': 1,
                'symbol': 2,
                'industry': 3
            }
        else:
            raise ValueError("컬럼 수가 부족합니다.")
    
    print(f"헤더 매핑: {header_map}")
    
    # 데이터 파싱
    stocks = []
    
    for idx, row in df.iterrows():
        try:
            # 종목 코드와 이름 가져오기
            symbol_col = df.columns[header_map.get('symbol', 2)]
            name_col = df.columns[header_map.get('name', 0)]
            
            symbol = str(row[symbol_col]).strip() if pd.notna(row[symbol_col]) else ''
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
            
            # 종목 코드와 이름이 있어야 함
            if not symbol or not name or symbol == 'nan' or name == 'nan':
                continue
            
            # 종목 코드 정규화 (6자리 숫자)
            symbol_clean = ''.join(filter(str.isdigit, symbol))
            if len(symbol_clean) < 6:
                symbol_clean = symbol_clean.zfill(6)
            symbol_clean = symbol_clean[:6]
            
            if len(symbol_clean) != 6 or symbol_clean == '000000':
                continue
            
            # 시장 구분
            market = 'KOSPI'
            if 'market' in header_map:
                market_col = df.columns[header_map['market']]
                market_str = str(row[market_col]).upper() if pd.notna(row[market_col]) else ''
                if 'KOSDAQ' in market_str or '코스닥' in market_str:
                    market = 'KOSDAQ'
                elif 'KOSPI' in market_str or '코스피' in market_str:
                    market = 'KOSPI'
                else:
                    # 종목 코드로 판단
                    if symbol_clean[0] not in ['0', '1', '2']:
                        market = 'KOSDAQ'
            
            # 업종
            industry = None
            if 'industry' in header_map:
                industry_col = df.columns[header_map['industry']]
                industry = str(row[industry_col]).strip() if pd.notna(row[industry_col]) else None
                if industry == 'nan':
                    industry = None
            
            # 섹터
            sector = None
            if 'sector' in header_map:
                sector_col = df.columns[header_map['sector']]
                sector = str(row[sector_col]).strip() if pd.notna(row[sector_col]) else None
                if sector == 'nan':
                    sector = None
            
            stocks.append({
                'symbol': symbol_clean,
                'name': name,
                'market': market,
                'sector': sector,
                'industry': industry
            })
        except Exception as e:
            print(f"행 {idx} 파싱 실패: {e}")
            continue
    
    print(f"파싱된 종목 수: {len(stocks)}")
    
    # 중복 제거 (종목 코드 기준)
    unique_stocks = {}
    for stock in stocks:
        if stock['symbol'] not in unique_stocks:
            unique_stocks[stock['symbol']] = stock
    
    stocks_list = list(unique_stocks.values())
    print(f"중복 제거 후: {len(stocks_list)} 종목")
    
    return stocks_list


def load_existing_stocks(output_path):
    """기존 종목 목록을 로드합니다."""
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                print(f"기존 종목 {len(existing)}개를 찾았습니다.")
                return existing
        except Exception as e:
            print(f"기존 파일 읽기 실패: {e}")
    return []


def merge_stocks(new_stocks, existing_stocks):
    """새로운 종목 목록과 기존 종목 목록을 병합합니다."""
    # 기존 종목을 symbol을 키로 하는 딕셔너리로 변환
    merged = {stock['symbol']: stock for stock in existing_stocks}
    
    # 새로운 종목 추가 (기존 종목이 있으면 업데이트, 없으면 추가)
    for stock in new_stocks:
        symbol = stock['symbol']
        if symbol in merged:
            # 기존 종목이 있으면 새로운 데이터로 업데이트 (단, 기존에 sector/industry가 있으면 유지)
            existing = merged[symbol]
            # 새로운 데이터로 업데이트
            merged[symbol] = {
                'symbol': symbol,
                'name': stock['name'],  # 이름은 새로운 것으로 업데이트
                'market': stock['market'],  # 시장 구분도 새로운 것으로 업데이트
                'sector': existing.get('sector') or stock.get('sector'),  # 기존 sector가 있으면 유지
                'industry': stock.get('industry') or existing.get('industry'),  # 새로운 industry가 있으면 사용
            }
        else:
            # 새로운 종목 추가
            merged[symbol] = stock
    
    return list(merged.values())


def save_stocks(stocks, output_path):
    """종목 목록을 JSON 파일로 저장합니다."""
    # 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # JSON 파일로 저장 (UTF-8 인코딩)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)
    
    print(f"\n{len(stocks)}개 종목을 {output_path}에 저장했습니다.")


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/parse-stocks/parse_stocks.py <excel-file-path>")
        sys.exit(1)
    
    excel_file_path = sys.argv[1]
    
    if not os.path.exists(excel_file_path):
        print(f"파일을 찾을 수 없습니다: {excel_file_path}")
        sys.exit(1)
    
    # 프로젝트 루트 디렉토리 찾기
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    output_path = project_root / 'data' / 'korea-stocks.json'
    
    print("상장법인 목록 파싱 시작...")
    
    try:
        # 기존 종목 목록 로드
        existing_stocks = load_existing_stocks(str(output_path))
        
        # Excel 파일에서 종목 목록 파싱
        new_stocks = parse_stocks_from_excel(excel_file_path)
        
        if not new_stocks:
            print("종목을 찾을 수 없습니다. 파일 형식을 확인해주세요.")
            sys.exit(1)
        
        # 기존 종목과 새로운 종목 병합
        if existing_stocks:
            print(f"\n기존 종목 {len(existing_stocks)}개와 새로운 종목 {len(new_stocks)}개를 병합 중...")
            merged_stocks = merge_stocks(new_stocks, existing_stocks)
            print(f"병합 후 총 {len(merged_stocks)}개 종목")
        else:
            merged_stocks = new_stocks
        
        # 종목 목록 저장
        save_stocks(merged_stocks, str(output_path))
        
        # 통계 출력
        kospi_count = sum(1 for s in merged_stocks if s['market'] == 'KOSPI')
        kosdaq_count = sum(1 for s in merged_stocks if s['market'] == 'KOSDAQ')
        
        print(f"\n성공적으로 {len(merged_stocks)}개 종목을 저장했습니다.")
        print(f"KOSPI: {kospi_count}개")
        print(f"KOSDAQ: {kosdaq_count}개")
        if existing_stocks:
            print(f"  - 기존 종목: {len(existing_stocks)}개")
            print(f"  - 새로 추가된 종목: {len(new_stocks)}개")
        print(f"\n저장 위치: {output_path}")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

