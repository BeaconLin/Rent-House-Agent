import httpx
from typing import Optional

BASE_URL = "http://7.225.29.223:8080"
DEFAULT_USER_ID = "t00598420"
REQUEST_TIMEOUT = 30.0  # 增加超时时间到30秒


def _headers():
    return {"X-User-ID": DEFAULT_USER_ID}


# 创建全局HTTP客户端，禁用代理
_http_client = httpx.Client(
    timeout=REQUEST_TIMEOUT,
    proxy=None,  # 显式禁用代理
    trust_env=False,  # 不信任环境变量中的代理设置
    limits=httpx.Limits(
        max_keepalive_connections=5,
        max_connections=10,
        keepalive_expiry=30.0
    ),
    verify=False  # 如果是HTTPS且证书有问题，可以禁用验证
)


def search_houses(
        listing_platform: Optional[str] = None,
        district: Optional[str] = None,
        area: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        bedrooms: Optional[str] = None,
        rental_type: Optional[str] = None,
        decoration: Optional[str] = None,
        orientation: Optional[str] = None,
        elevator: Optional[str] = None,
        min_area: Optional[int] = None,
        max_area: Optional[int] = None,
        property_type: Optional[str] = None,
        subway_line: Optional[str] = None,
        max_subway_dist: Optional[int] = None,
        subway_station: Optional[str] = None,
        utilities_type: Optional[str] = None,
        available_from_before: Optional[str] = None,
        commute_to_xierqi_max: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
) -> dict:
    """按条件筛选房源"""
    params = {k: v for k, v in {
        "listing_platform": listing_platform,
        "district": district,
        "area": area,
        "min_price": min_price,
        "max_price": max_price,
        "bedrooms": bedrooms,
        "rental_type": rental_type,
        "decoration": decoration,
        "orientation": orientation,
        "elevator": elevator,
        "min_area": min_area,
        "max_area": max_area,
        "property_type": property_type,
        "subway_line": subway_line,
        "max_subway_dist": max_subway_dist,
        "subway_station": subway_station,
        "utilities_type": utilities_type,
        "available_from_before": available_from_before,
        "commute_to_xierqi_max": commute_to_xierqi_max,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "page": page,
        "page_size": page_size,
    }.items() if v is not None}

    resp = _http_client.get(f"{BASE_URL}/api/houses/by_platform", params=params, headers=_headers())
    return resp.json()


def get_house_detail(house_id: str) -> dict:
    """获取房源详情"""
    resp = _http_client.get(f"{BASE_URL}/api/houses/{house_id}", headers=_headers())
    return resp.json()


def get_houses_nearby(
        landmark_id: str,
        max_distance: int = 2000,
        listing_platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
) -> dict:
    """查询地标附近房源"""
    params = {"landmark_id": landmark_id, "max_distance": max_distance, "page": page, "page_size": page_size}
    if listing_platform:
        params["listing_platform"] = listing_platform
    resp = _http_client.get(f"{BASE_URL}/api/houses/nearby", params=params, headers=_headers())
    return resp.json()


def search_landmark(q: str, category: Optional[str] = None, district: Optional[str] = None) -> dict:
    """搜索地标"""
    params = {"q": q}
    if category:
        params["category"] = category
    if district:
        params["district"] = district
    resp = _http_client.get(f"{BASE_URL}/api/landmarks/search", params=params, headers=_headers())
    return resp.json()


def get_nearby_landmarks(community: str, type: Optional[str] = None, max_distance_m: int = 3000) -> dict:
    """查询小区周边地标"""
    params = {"community": community, "max_distance_m": max_distance_m}
    if type:
        params["type"] = type
    resp = _http_client.get(f"{BASE_URL}/api/houses/nearby_landmarks", params=params, headers=_headers())
    return resp.json()


def get_house_listings(house_id: str) -> dict:
    """获取房源各平台挂牌记录（用于核验）"""
    resp = _http_client.get(f"{BASE_URL}/api/houses/listings/{house_id}", headers=_headers())
    return resp.json()


def get_landmarks(category: Optional[str] = None, district: Optional[str] = None) -> dict:
    """获取地标列表，支持category、district同时筛选（取交集）"""
    params = {k: v for k, v in {
        "category": category,
        "district": district
    }.items() if v is not None}
    resp = _http_client.get(f"{BASE_URL}/api/landmarks", params=params, headers=_headers())
    return resp.json()


def get_landmark_by_name(name: str) -> dict:
    """按名称精确查询地标，如西二旗站、百度"""
    resp = _http_client.get(f"{BASE_URL}/api/landmarks/name/{name}", headers=_headers())
    return resp.json()


def get_landmark_by_id(landmark_id: str) -> dict:
    """按地标ID查询地标详情"""
    resp = _http_client.get(f"{BASE_URL}/api/landmarks/{landmark_id}", headers=_headers())
    return resp.json()


def get_landmark_stats() -> dict:
    """获取地标统计信息（总数、按类别分布等）"""
    resp = _http_client.get(f"{BASE_URL}/api/landmarks/stats", headers=_headers())
    return resp.json()


def get_houses_by_community(
        community: str,
        listing_platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
) -> dict:
    """按小区名查询该小区下可租房源"""
    params = {"community": community, "page": page, "page_size": page_size}
    if listing_platform:
        params["listing_platform"] = listing_platform
    resp = _http_client.get(f"{BASE_URL}/api/houses/by_community", params=params, headers=_headers())
    return resp.json()


def get_house_stats() -> dict:
    """获取房源统计信息（总套数、按状态/行政区/户型分布、价格区间等）"""
    resp = _http_client.get(f"{BASE_URL}/api/houses/stats", headers=_headers())
    return resp.json()


def rent_house(house_id: str, listing_platform: str) -> dict:
    """租房操作，将当前用户视角下该房源设为已租"""
    params = {"listing_platform": listing_platform}
    resp = _http_client.post(f"{BASE_URL}/api/houses/{house_id}/rent", params=params, headers=_headers())
    return resp.json()


def terminate_rental(house_id: str, listing_platform: str) -> dict:
    """退租操作，将当前用户视角下该房源恢复为可租"""
    params = {"listing_platform": listing_platform}
    resp = _http_client.post(f"{BASE_URL}/api/houses/{house_id}/terminate", params=params, headers=_headers())
    return resp.json()


def take_offline(house_id: str, listing_platform: str) -> dict:
    """下架操作，将当前用户视角下该房源设为下架"""
    params = {"listing_platform": listing_platform}
    resp = _http_client.post(f"{BASE_URL}/api/houses/{house_id}/offline", params=params, headers=_headers())
    return resp.json()


# 工具定义（OpenAI function calling格式）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_houses",
            "description": "按条件筛选可租房源，支持区域、价格、户型、地铁等多维度筛选",
            "parameters": {
                "type": "object",
                "properties": {
                    "listing_platform": {"type": "string", "description": "挂牌平台，可选：链家、安居客、58同城，不传则默认安居客"},
                    "district": {"type": "string", "description": "行政区，如 海淀,朝阳"},
                    "area": {"type": "string", "description": "商圈，如 西二旗,上地"},
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "bedrooms": {"type": "string", "description": "卧室数，如 1,2"},
                    "rental_type": {"type": "string", "description": "整租 或 合租"},
                    "decoration": {"type": "string", "description": "装修类型，如 精装、简装"},
                    "orientation": {"type": "string", "description": "朝向，如 朝南、南北"},
                    "elevator": {"type": "string", "description": "是否有电梯：true/false"},
                    "min_area": {"type": "integer", "description": "最小面积（平米）"},
                    "max_area": {"type": "integer", "description": "最大面积（平米）"},
                    "property_type": {"type": "string", "description": "物业类型，如 住宅"},
                    "subway_line": {"type": "string", "description": "地铁线路，如 13号线"},
                    "max_subway_dist": {"type": "integer", "description": "最大地铁距离（米）"},
                    "subway_station": {"type": "string", "description": "地铁站名，如 车公庄站"},
                    "utilities_type": {"type": "string", "description": "水电类型，如 民水民电"},
                    "available_from_before": {"type": "string", "description": "可入住日期上限 YYYY-MM-DD"},
                    "commute_to_xierqi_max": {"type": "integer", "description": "到西二旗通勤时间上限（分钟）"},
                    "sort_by": {"type": "string", "description": "排序字段 price/area/subway"},
                    "sort_order": {"type": "string", "description": "asc 或 desc"},
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页条数，默认10，最大10000"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_detail",
            "description": "根据房源ID获取单套房源详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_nearby",
            "description": "以地标为中心查询附近房源，适合'XX地铁站附近'类需求。注意：此工具不支持 rental_type 参数，如需按整租/合租筛选，请使用 search_houses 工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string", "description": "地标ID或名称"},
                    "max_distance": {"type": "integer", "description": "最大距离（米），默认2000"},
                    "listing_platform": {"type": "string", "description": "挂牌平台，可选：链家、安居客、58同城，不传则默认安居客"},
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页条数，默认10，最大10000"}
                },
                "required": ["landmark_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_landmark",
            "description": "搜索地标（地铁站、公司、商圈等）获取ID和位置",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "搜索关键词，如 西二旗"},
                    "category": {"type": "string", "description": "类别: subway/company/landmark"},
                    "district": {"type": "string", "description": "可选，限定行政区，如 海淀、朝阳"}
                },
                "required": ["q"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取房源在各平台的挂牌记录，用于核验房源真实性和价格一致性",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_landmarks",
            "description": "查询小区周边商超、公园等生活配套设施",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string", "description": "小区名称"},
                    "type": {"type": "string", "description": "地标类型: shopping(商超)/park(公园)"},
                    "max_distance_m": {"type": "integer", "description": "最大距离（米），默认3000"}
                },
                "required": ["community"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmarks",
            "description": "获取地标列表，支持category、district同时筛选（取交集），用于查地铁站、公司、商圈等地标",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "地标类别：subway(地铁)/company(公司)/landmark(商圈等)，不传则不过滤"},
                    "district": {"type": "string", "description": "行政区，如 海淀、朝阳"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_by_name",
            "description": "按名称精确查询地标，如西二旗站、百度，返回地标id、经纬度等，用于后续nearby查房",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "地标名称，如 西二旗站、国贸"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_by_id",
            "description": "按地标ID查询地标详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string", "description": "地标ID，如 SS_001、LM_002"}
                },
                "required": ["landmark_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_stats",
            "description": "获取地标统计信息（总数、按类别分布等）",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_by_community",
            "description": "按小区名查询该小区下可租房源，用于指代消解、查某小区地铁信息或隐性属性",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string", "description": "小区名，与数据一致，如 建清园(南区)、保利锦上(二期)"},
                    "listing_platform": {"type": "string", "description": "挂牌平台，不传则默认安居客，可选：链家、安居客、58同城"},
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页条数，默认10，最大10000"}
                },
                "required": ["community"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_stats",
            "description": "获取房源统计信息（总套数、按状态/行政区/户型分布、价格区间等），按当前用户视角统计",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rent_house",
            "description": "租房操作，将当前用户视角下该房源设为已租，需要明确租赁哪个平台",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "description": "必填，明确租赁哪个平台，可选：链家、安居客、58同城"}
                },
                "required": ["house_id", "listing_platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminate_rental",
            "description": "退租操作，将当前用户视角下该房源恢复为可租，需要明确操作哪个平台",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "description": "必填，明确操作哪个平台，可选：链家、安居客、58同城"}
                },
                "required": ["house_id", "listing_platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_offline",
            "description": "下架操作，将当前用户视角下该房源设为下架，需要明确操作哪个平台",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "description": "必填，明确操作哪个平台，可选：链家、安居客、58同城"}
                },
                "required": ["house_id", "listing_platform"]
            }
        }
    }
]