import requests
import json

def get_krx_sectors():
    url = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
    
    # KOSPI
    params = {
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT01501',
        'locale': 'ko_KR',
        'share': '1',
        'money': '1',
    }
    
    sectors = set()
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for item in data.get('OutBlock_1', []):
            sectors.add(item.get('IDX_IND_NM'))
    except Exception as e:
        print(f"Error fetching KOSPI: {e}")

    # KOSDAQ
    params = {
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT02501',
        'locale': 'ko_KR',
        'share': '1',
        'money': '1',
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for item in data.get('OutBlock_1', []):
            sectors.add(item.get('IDX_IND_NM'))
    except Exception as e:
        print(f"Error fetching KOSDAQ: {e}")
        
    return sorted(list(sectors))

if __name__ == "__main__":
    sectors = get_krx_sectors()
    print(json.dumps(sectors, ensure_ascii=False, indent=2))
