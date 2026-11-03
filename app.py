"""屏東縣 YouBike 站點快照地圖。

將本檔放在 GISprog 專案根目錄，執行：solara run app.py
可用環境變數 YOUBIKE_PROJECT_ROOT、YOUBIKE_STATION_CSV 與
YOUBIKE_TOWN_SHP 指定專案根目錄、站點 CSV 及鄉鎮界線檔。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import leafmap.leafmap as leafmap
import pandas as pd
import plotly.express as px
import requests
import solara
from ipyleaflet import FullScreenControl, GeoJSON, ScaleControl
from shapely.geometry import Point


# TDX 屏東縣公共自行車即時可用量；每個瀏覽器工作階段只載入一次。
AVAILABILITY_API = (
    "https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/"
    "PingtungCounty"
)
TDX_TOKEN_API = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/"
    "protocol/openid-connect/token"
)
TAIPEI_TZ = timezone(timedelta(hours=8))
ALL_TOWNS = "屏東縣（全縣）"


def _project_root() -> Path:
    """尋找包含 data/ 與 outputs/ 的專案根目錄。"""
    configured_root = os.getenv("YOUBIKE_PROJECT_ROOT")
    candidates: list[Path] = []
    if configured_root:
        candidates.append(Path(configured_root).expanduser())

    app_dir = Path(__file__).resolve().parent
    candidates.extend([app_dir, Path.cwd(), *app_dir.parents])

    for candidate in candidates:
        if (
            (candidate / "data" / "raw" / "Taiwan_boundaries" / "Town" / "Taiwan_town.shp").exists()
            and (candidate / "outputs").is_dir()
        ):
            return candidate

    return Path(configured_root).expanduser() if configured_root else app_dir


PROJECT_ROOT = _project_root()
STATION_CSV = Path(
    os.getenv(
        "YOUBIKE_STATION_CSV",
        str(PROJECT_ROOT / "outputs" / "PingtungCounty_YouBike_stations_20261103_230447.csv"),
    )
).expanduser()
TOWNSHIP_SHP = Path(
    os.getenv(
        "YOUBIKE_TOWN_SHP",
        str(PROJECT_ROOT / "data" / "Taiwan_town.shp"),
    )
).expanduser()


def _display_time(value: Any) -> str:
    """把來源時間顯示為台灣時間。"""
    if value is None or pd.isna(value):
        return "未提供"
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return str(value)
    return timestamp.tz_convert(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _assign_townships(stations: pd.DataFrame, towns: gpd.GeoDataFrame) -> pd.DataFrame:
    """用站點座標與鄉鎮界線配對，避免依賴額外的空間索引套件。"""
    result = stations.copy()
    result["鄉鎮市區"] = "未匹配"

    points: dict[Any, Point] = {}
    for index, row in result.iterrows():
        lon = row["StationPosition.PositionLon"]
        lat = row["StationPosition.PositionLat"]
        if pd.notna(lon) and pd.notna(lat):
            points[index] = Point(float(lon), float(lat))

    assigned: set[Any] = set()
    for town_name, geometry in zip(towns["TOWNNAME"], towns.geometry):
        if geometry is None or geometry.is_empty:
            continue
        for index, point in points.items():
            if index not in assigned and geometry.covers(point):
                result.at[index, "鄉鎮市區"] = str(town_name).strip()
                assigned.add(index)

    return result


def _load_static_data() -> dict[str, Any]:
    """讀取站點清冊與鄉鎮界線，建立可篩選的站點資料。"""
    if not STATION_CSV.exists():
        raise FileNotFoundError(
            f"找不到屏東站點 CSV：{STATION_CSV}。"
            "請將 app.py 放在專案根目錄，或設定 YOUBIKE_STATION_CSV。"
        )
    if not TOWNSHIP_SHP.exists():
        raise FileNotFoundError(
            f"找不到鄉鎮界線 Shapefile：{TOWNSHIP_SHP}。"
            "請保留 .shp、.shx、.dbf、.prj 等同名檔案，"
            "或設定 YOUBIKE_TOWN_SHP。"
        )

    stations = pd.read_csv(STATION_CSV, encoding="utf-8-sig", dtype={"StationUID": str, "StationID": str})
    required_station_fields = {
        "StationUID",
        "StationID",
        "BikesCapacity",
        "StationName.Zh_tw",
        "StationPosition.PositionLon",
        "StationPosition.PositionLat",
    }
    missing_station_fields = required_station_fields.difference(stations.columns)
    if missing_station_fields:
        raise ValueError(f"站點 CSV 缺少必要欄位：{', '.join(sorted(missing_station_fields))}")

    for column in ("StationPosition.PositionLon", "StationPosition.PositionLat", "BikesCapacity"):
        stations[column] = pd.to_numeric(stations[column], errors="coerce")
    stations["StationUID"] = stations["StationUID"].astype(str).str.strip()
    stations["StationID"] = stations["StationID"].astype(str).str.strip()

    all_towns = gpd.read_file(TOWNSHIP_SHP, encoding="utf-8")

    required_boundary_fields = {"COUNTYNAME", "TOWNNAME", "geometry"}
    missing_boundary_fields = required_boundary_fields.difference(all_towns.columns)
    if missing_boundary_fields:
        raise ValueError(
            f"鄉鎮界線缺少必要欄位：{', '.join(sorted(missing_boundary_fields))}"
        )
    if all_towns.crs is None:
        raise ValueError("鄉鎮界線沒有座標系統資訊，請確認同目錄的 .prj 檔案存在。")

    county_names = all_towns["COUNTYNAME"].astype(str).str.strip()
    pingtung = all_towns.loc[
        county_names.str.contains("屏東", regex=False),
        ["COUNTYNAME", "TOWNNAME", "geometry"],
    ].copy()
    if pingtung.empty:
        raise ValueError("鄉鎮界線中找不到屏東縣，請確認圖層編碼及欄位內容。")

    pingtung = pingtung.to_crs("EPSG:4326").reset_index(drop=True)
    stations = _assign_townships(stations, pingtung)

    catalog_time = None
    snapshot_time_field = "快照時間（台北）"
    if snapshot_time_field in stations.columns and not stations.empty:
        catalog_time = stations[snapshot_time_field].dropna().iloc[0] if stations[snapshot_time_field].notna().any() else None

    return {
        "stations": stations,
        "towns": pingtung,
        "catalog_time": catalog_time,
    }


def _load_static_data_safe() -> dict[str, Any]:
    """將讀檔錯誤轉成頁面可顯示的訊息。"""
    try:
        return {"data": _load_static_data(), "error": None}
    except Exception as error:
        return {"data": None, "error": str(error)}


def _get_tdx_access_token() -> str:
    """使用環境變數中的 TDX 憑證取得存取權杖。"""
    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "尚未設定 TDX_CLIENT_ID 與 TDX_CLIENT_SECRET。"
            "請在 Render 的 Environment 設定這兩個值。"
        )

    response = requests.post(
        TDX_TOKEN_API,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=25,
    )
    response.raise_for_status()
    access_token = response.json().get("access_token")
    if not access_token:
        raise ValueError("TDX OAuth 回應中沒有 access_token。")
    return access_token


def _load_availability_snapshot() -> dict[str, Any]:
    """從 TDX 取得一筆車況快照，不在頁面內輪詢更新。"""
    requested_at = datetime.now(timezone.utc).astimezone(TAIPEI_TZ)
    try:
        access_token = _get_tdx_access_token()
        response = requests.get(
            AVAILABILITY_API,
            params={"$format": "JSON"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Pingtung-YouBike-Snapshot-App/1.0",
            },
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            records = payload.get("value", payload.get("records", []))
        else:
            records = payload
        if not isinstance(records, list):
            raise ValueError("TDX 回傳格式不是站點清單。")

        availability = pd.DataFrame.from_records(records)
        required_fields = {
            "StationUID",
            "AvailableRentBikes",
            "AvailableReturnBikes",
        }
        missing = required_fields.difference(availability.columns)
        if missing:
            raise ValueError(f"TDX 回應缺少必要欄位：{', '.join(sorted(missing))}")

        availability["StationUID"] = availability["StationUID"].astype(str).str.strip()
        for column in ("AvailableRentBikes", "AvailableReturnBikes", "ServiceStatus"):
            if column in availability.columns:
                availability[column] = pd.to_numeric(availability[column], errors="coerce")

        source_update_time = None
        for column in ("SrcUpdateTime", "UpdateTime"):
            if column in availability.columns:
                parsed = pd.to_datetime(availability[column], errors="coerce", utc=True).dropna()
                if not parsed.empty:
                    source_update_time = parsed.max().tz_convert(TAIPEI_TZ).isoformat()
                    break

        return {
            "data": availability.drop_duplicates("StationUID", keep="last"),
            "captured_at": requested_at.isoformat(),
            "source_update_time": source_update_time,
            "error": None,
        }
    except Exception as error:
        return {
            "data": pd.DataFrame(),
            "captured_at": requested_at.isoformat(),
            "source_update_time": None,
            "error": str(error),
        }


def _join_snapshot(stations: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    """以 TDX StationUID 將快照車況接回站點清冊。"""
    if availability.empty or "StationUID" not in availability.columns:
        result = stations.copy()
        for column in ("AvailableRentBikes", "AvailableReturnBikes", "ServiceStatus"):
            result[column] = pd.NA
        return result

    selected_fields = ["StationUID", "AvailableRentBikes", "AvailableReturnBikes"]
    if "ServiceStatus" in availability.columns:
        selected_fields.append("ServiceStatus")
    result = stations.merge(
        availability[selected_fields].drop_duplicates("StationUID", keep="last"),
        on="StationUID",
        how="left",
    )
    if "ServiceStatus" not in result.columns:
        result["ServiceStatus"] = pd.NA
    return result


def _map_feature_collection(stations: pd.DataFrame) -> dict[str, Any]:
    """建立 Leaflet 可使用的 GeoJSON 點圖層。"""
    features = []
    for _, row in stations.iterrows():
        lon = row["StationPosition.PositionLon"]
        lat = row["StationPosition.PositionLat"]
        if pd.isna(lon) or pd.isna(lat):
            continue

        station_uid = str(row["StationUID"])
        station_name = str(row["StationName.Zh_tw"])
        available = row.get("AvailableRentBikes")
        if pd.isna(available):
            available = None
        else:
            available = int(available)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                },
                "properties": {
                    "StationUID": station_uid,
                    "StationName": station_name,
                    "AvailableRentBikes": available,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _build_map(
    stations: pd.DataFrame,
    towns: gpd.GeoDataFrame,
    selected_town: str,
    set_selected_station: Any,
) -> leafmap.Map:
    """建立 Leafmap 地圖、鄉鎮界線與可點選站點。"""
    if selected_town == ALL_TOWNS:
        min_lon, min_lat, max_lon, max_lat = towns.total_bounds
        center = ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
        zoom = 9
    else:
        selected_geometry = towns.loc[towns["TOWNNAME"].astype(str).str.strip() == selected_town]
        if selected_geometry.empty:
            min_lon, min_lat, max_lon, max_lat = towns.total_bounds
            center = ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
            zoom = 9
        else:
            point = selected_geometry.geometry.iloc[0].representative_point()
            center = (point.y, point.x)
            zoom = 12

    map_widget = leafmap.Map(
        center=center,
        zoom=zoom,
        scroll_wheel_zoom=True,
        tap=True,
    )
    map_widget.layout.width = "100%"
    map_widget.layout.height = "500px"

    boundary_data = json.loads(towns.to_json())

    def town_style(feature: dict[str, Any]) -> dict[str, Any]:
        name = str(feature.get("properties", {}).get("TOWNNAME", "")).strip()
        selected = selected_town == ALL_TOWNS or name == selected_town
        return {
            "color": "#0f766e" if selected else "#64748b",
            "weight": 3 if name == selected_town else 1,
            "fillColor": "#14b8a6" if name == selected_town else "#94a3b8",
            "fillOpacity": 0.18 if name == selected_town else 0.04,
        }

    map_widget.add_layer(
        GeoJSON(
            data=boundary_data,
            name="屏東縣鄉鎮市區界線",
            style_callback=town_style,
            hover_style={"color": "#f97316", "weight": 3, "fillOpacity": 0.25},
        )
    )

    point_data = _map_feature_collection(stations)

    def station_style(feature: dict[str, Any]) -> dict[str, Any]:
        value = feature.get("properties", {}).get("AvailableRentBikes")
        if value is None:
            color = "#64748b"
        elif value == 0:
            color = "#dc2626"
        elif value <= 5:
            color = "#f59e0b"
        else:
            color = "#16a34a"
        return {
            "color": "#ffffff",
            "weight": 1,
            "fillColor": color,
            "fillOpacity": 0.9,
        }

    station_layer = GeoJSON(
        data=point_data,
        name="YouBike 站點（點擊查看）",
        point_style={"radius": 7},
        style_callback=station_style,
    )

    def handle_station_click(event: dict[str, Any], feature: dict[str, Any]) -> None:
        station_uid = feature.get("properties", {}).get("StationUID")
        if station_uid:
            set_selected_station(str(station_uid))

    station_layer.on_click(handle_station_click)
    map_widget.add_layer(station_layer)
    map_widget.add_control(ScaleControl(position="bottomleft"))
    map_widget.add_control(FullScreenControl(position="topleft"))
    map_widget.add_layer_control()
    return map_widget


def _build_map_safe(
    stations: pd.DataFrame,
    towns: gpd.GeoDataFrame,
    selected_town: str,
    set_selected_station: Any,
) -> dict[str, Any]:
    """將建圖錯誤轉成頁面可顯示的訊息。"""
    try:
        return {
            "map": _build_map(stations, towns, selected_town, set_selected_station),
            "error": None,
        }
    except Exception as error:
        return {"map": None, "error": str(error)}


def _availability_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value):,}"


@solara.component
def Page():
    # 每個瀏覽器工作階段各載入一次檔案與車況快照。
    static_response = solara.use_memo(_load_static_data_safe, dependencies=[])
    snapshot_result = solara.use_memo(_load_availability_snapshot, dependencies=[])
    selected_town, set_selected_town = solara.use_state(ALL_TOWNS)
    selected_station_uid, set_selected_station_uid = solara.use_state(None)

    solara.Title("屏東縣 YouBike 車況地圖")

    if static_response["error"]:
        solara.Error(f"讀取站點或鄉鎮界線失敗：{static_response['error']}")
        return

    static_result = static_response["data"]
    towns = static_result["towns"]
    all_stations = _join_snapshot(
        static_result["stations"],
        snapshot_result["data"],
    )
    town_options = [ALL_TOWNS] + sorted(
        towns["TOWNNAME"].astype(str).str.strip().dropna().unique().tolist()
    )
    if selected_town not in town_options:
        selected_town = ALL_TOWNS

    filtered = all_stations
    if selected_town != ALL_TOWNS:
        filtered = all_stations.loc[all_stations["鄉鎮市區"] == selected_town].copy()

    map_response = solara.use_memo(
        lambda: _build_map_safe(
            filtered,
            towns,
            selected_town,
            set_selected_station_uid,
        ),
        dependencies=[selected_town],
    )

    def change_town(value: str) -> None:
        set_selected_town(value)
        set_selected_station_uid(None)

    with solara.Column(gap="12px"):
        solara.Markdown(
            "# 屏東縣 YouBike 站點快照\n"
            "選擇鄉鎮市區後，地圖、站點表格與可租車數圖表會同步篩選。"
        )
        with solara.ColumnsResponsive(12, medium=6):
            solara.Select(
                label="行政區",
                values=town_options,
                value=selected_town,
                on_value=change_town,
            )
            solara.Markdown(
                f"**資料來源**：TDX 屏東縣 YouBike 可用量 API  "
                f"**車況快照載入時間**：{_display_time(snapshot_result['captured_at'])}  "
                f"**API 資料更新時間**：{_display_time(snapshot_result['source_update_time'])}  "
                f"**站點清冊時間**：{_display_time(static_result['catalog_time'])}"
            )

        if snapshot_result["error"]:
            solara.Warning(
                "本次無法取得 TDX 車況快照；站點與容量仍可檢視，"
                f"可租車數將顯示為空白。原因：{snapshot_result['error']}"
            )
        else:
            matched_count = int(filtered["AvailableRentBikes"].notna().sum())
            if matched_count < len(filtered):
                solara.Warning(
                    f"本區有 {len(filtered) - matched_count} 個站點未配對到車況資料。"
                )

        available = pd.to_numeric(filtered["AvailableRentBikes"], errors="coerce")
        capacity = pd.to_numeric(filtered["BikesCapacity"], errors="coerce")
        total_available = "—" if available.notna().sum() == 0 else f"{int(available.sum()):,}"
        total_capacity = "—" if capacity.notna().sum() == 0 else f"{int(capacity.sum()):,}"
        station_count = len(filtered)

        with solara.ColumnsResponsive(12, small=4):
            with solara.Card("站點數"):
                solara.Markdown(f"## {station_count:,}")
            with solara.Card("目前可租車數"):
                solara.Markdown(f"## {total_available}")
            with solara.Card("站點總容量"):
                solara.Markdown(f"## {total_capacity}")

        if map_response["error"]:
            solara.Error(f"建立地圖失敗：{map_response['error']}")
            return

        with solara.ColumnsResponsive(12, large=[7, 5]):
            with solara.Card("屏東縣站點地圖"):
                solara.display(map_response["map"])
                solara.Markdown(
                    "站點顏色：綠色表示可租車數大於 5，橘色為 1–5，"
                    "紅色為 0，灰色表示沒有車況資料。點擊站點可查看詳細資料。"
                )

            with solara.Column(gap="12px"):
                selected = filtered.loc[
                    filtered["StationUID"].astype(str) == str(selected_station_uid)
                ] if selected_station_uid else pd.DataFrame()

                with solara.Card("站點資訊"):
                    if selected.empty:
                        solara.Info("點選地圖站點或圖表長條，即可查看站名與可租車數。")
                    else:
                        station = selected.iloc[0]
                        name = station.get("StationName.Zh_tw", "未提供")
                        available_bikes = _availability_text(
                            station.get("AvailableRentBikes")
                        )
                        return_bikes = _availability_text(
                            station.get("AvailableReturnBikes")
                        )
                        solara.Markdown(
                            f"### {name}\n"
                            f"- 鄉鎮市區：{station.get('鄉鎮市區', '未匹配')}\n"
                            f"- 可租車數：**{available_bikes}**\n"
                            f"- 可還車位：{return_bikes}\n"
                            f"- 站點容量：{_availability_text(station.get('BikesCapacity'))}\n"
                            f"- 站點編號：{station.get('StationID', '未提供')}"
                        )

                chart_data = filtered.dropna(subset=["AvailableRentBikes"]).copy()
                if chart_data.empty:
                    with solara.Card("各站可租車數"):
                        solara.Info("目前沒有可繪製的車況資料。")
                else:
                    chart_data["AvailableRentBikes"] = pd.to_numeric(
                        chart_data["AvailableRentBikes"], errors="coerce"
                    )
                    chart_data = chart_data.sort_values(
                        "AvailableRentBikes", ascending=False
                    ).head(15)
                    chart_data = chart_data.sort_values(
                        "AvailableRentBikes", ascending=True
                    )

                    def handle_chart_click(click_data: dict[str, Any]) -> None:
                        points = click_data.get("points", {}) if click_data else {}
                        indexes = points.get("point_indexes", [])
                        if indexes:
                            row_index = int(indexes[0])
                            if 0 <= row_index < len(chart_data):
                                uid = chart_data.iloc[row_index]["StationUID"]
                                set_selected_station_uid(str(uid))

                    figure = px.bar(
                        chart_data,
                        x="AvailableRentBikes",
                        y="StationName.Zh_tw",
                        orientation="h",
                        labels={
                            "AvailableRentBikes": "可租車數",
                            "StationName.Zh_tw": "站名",
                        },
                        title="可租車數最多的 15 個站點",
                    )
                    figure.update_layout(
                        height=max(300, min(440, len(chart_data) * 28 + 80)),
                        margin=dict(l=8, r=12, t=48, b=24),
                        yaxis_title=None,
                        xaxis_title="可租車數",
                        showlegend=False,
                    )
                    with solara.Card("各站可租車數"):
                        solara.FigurePlotly(figure, on_click=handle_chart_click)

        table = filtered[
            [
                "StationName.Zh_tw",
                "鄉鎮市區",
                "AvailableRentBikes",
                "AvailableReturnBikes",
                "BikesCapacity",
                "ServiceStatus",
            ]
        ].copy()
        table = table.rename(
            columns={
                "StationName.Zh_tw": "站名",
                "鄉鎮市區": "鄉鎮市區",
                "AvailableRentBikes": "可租車數",
                "AvailableReturnBikes": "可還車位",
                "BikesCapacity": "站點容量",
                "ServiceStatus": "服務狀態代碼",
            }
        )
        table = table.sort_values("可租車數", ascending=False, na_position="last")
        with solara.Card(f"站點資料表（{len(table):,} 站）"):
            solara.DataFrame(table, items_per_page=12, scrollable=True)

        solara.Markdown(
            "車況資料在每次開啟頁面時載入一次；切換行政區不會重新抓取。"
            "重新整理頁面會取得另一筆快照。地圖底圖為 OpenStreetMap。"
        )


if __name__ == "__main__":
    # 直接以 Python 執行時提示正確的 Solara 啟動方式。
    print("請使用：solara run app.py") 
