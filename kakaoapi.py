import os
import math
import requests
import dotenv
dotenv.load_dotenv()
# KAKAO_API_KEY = os.getenv('KAKAO_API_KEY')
KAKAO_API_KEY = '11320e3940a6d61627018f9e4e4a493b'

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def get_gu_dong(lat: float, lon: float,timeout=5):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"x": lon, "y": lat, "input_coord": "WGS84"}  # x=경도, y=위도 주의!

    r = requests.get(
        "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json",
        headers=headers, params=params, timeout=timeout
    )
    r.raise_for_status()
    docs = r.json().get("documents", [])

    b = next((d for d in docs if d.get("region_type") == "B"), None)  # 법정동
    h = next((d for d in docs if d.get("region_type") == "H"), None)  # 행정동
    src = b or h
    if not src:
        return {"gu": None, "dong": None}

    gu   = src.get("region_2depth_name")
    dong = src.get("region_3depth_name")
    return {"gu": gu, "dong": dong}

def kakao_keyword_nearby(lat=None, lon=None, query="", TOP_N_STORES=5, radius=5000, sort="accuracy", max_pages=1):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    results = []

    for page in range(1, max_pages + 1):
        params = {
            "query": query,
            "page": page,
            "size": 15,
            "sort": sort
        }
        #좌표가 있으면 근처 검색
        query_tokens = query.strip().split()

        if lat is not None and lon is not None:
            if len(query_tokens) >= 2 and query_tokens[0].endswith("동"):
                params.update({"x": None, "y": None, "radius": radius})
            else:
                params.update({"x": lon, "y": lat, "radius": radius})

        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        for doc in data.get("documents", []):
            place_lat = float(doc["y"])
            place_lon = float(doc["x"])
            dist_m = None
            if lat and lon:
                dist_m = int(haversine_m(lat, lon, place_lat, place_lon))
            results.append({
                "name": doc["place_name"],
                "address": doc.get("address_name"),
                "category": doc.get("category_name"),
                "phone": doc.get("phone"),
                "lat": place_lat,
                "lon": place_lon,
                "distance_m": dist_m,
                "place_url": doc.get("place_url"),
                "id": doc.get("id")
            })

        if data.get("meta", {}).get("is_end", True):
            break

    res, distance = {}, {}
    for r in results[:TOP_N_STORES]:
        res[r["name"]] = (r["address"], (r["lat"], r['lon']))
        distance[r["name"]] = r.get("distance_m")
    return res, distance

if __name__ == "__main__":
    JEONGJA_LAT, JEONGJA_LON = 37.3670, 127.1080
    rows = kakao_keyword_nearby(JEONGJA_LAT, JEONGJA_LON,TOP_N_STORES=5, query="근처 삼겹살", radius=5000)
    print(rows)
