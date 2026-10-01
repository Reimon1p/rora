import os
import ast
import requests

from flask import Flask, jsonify, request, send_from_directory


app = Flask(__name__)


api_key = os.getenv("ORS_API_KEY")

FOCUS_LAT = 40.59408
FOCUS_LON = -73.78921

EVENTS_URL = "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"
METADATA_URL = "https://data.cityofnewyork.us/resource/kb2e-tjy3.json"

FLOOD_THRESHOLD = 0.4


def get_severity(depth):

    if depth < 0.4:
        return "none"

    elif depth < 1:
        return "low"

    elif depth < 2:
        return "moderate"

    elif depth < 3:
        return "high"

    else:
        return "severe"


def make_hazard_polygon(latitude, longitude):

    lat_size = 0.00033
    lon_size = 0.00039

    return [
        [longitude - lon_size, latitude - lat_size],
        [longitude + lon_size, latitude - lat_size],
        [longitude + lon_size, latitude + lat_size],
        [longitude - lon_size, latitude + lat_size],
        [longitude - lon_size, latitude - lat_size]
    ]


def parse_depth_profile(profile):

    if not profile:
        return []

    try:

        if isinstance(profile, str):
            profile = ast.literal_eval(profile)

        return [
            float(depth)
            for depth in profile
        ]

    except Exception:
        return []


def load_demo_sensors():

    sensors = []


    try:

        metadata_response = requests.get(
            METADATA_URL,
            params={
                "$limit": 50000
            },
            timeout=30
        )

        metadata_response.raise_for_status()

        metadata_rows = metadata_response.json()

    except Exception as error:

        print(
            "FloodNet metadata loading error:",
            error
        )

        return []


    metadata_by_id = {}


    for row in metadata_rows:

        sensor_id = row.get("sensor_id")

        if not sensor_id:
            continue

        if (
            not row.get("latitude")
            or
            not row.get("longitude")
        ):
            continue

        metadata_by_id[sensor_id] = row


    events = []

    batch_size = 5000
    offset = 0


    while True:

        try:

            response = requests.get(
                EVENTS_URL,
                params={
                    "$order": "flood_start_time DESC",
                    "$limit": batch_size,
                    "$offset": offset
                },
                timeout=30
            )

            response.raise_for_status()

            batch = response.json()

        except Exception as error:

            print(
                "FloodNet event loading error:",
                error
            )

            break


        if not batch:
            break


        events.extend(batch)


        if len(batch) < batch_size:
            break


        offset += batch_size


    used_sensor_ids = set()


    for event in events:

        sensor_id = event.get("sensor_id")


        if (
            not sensor_id
            or
            sensor_id in used_sensor_ids
            or
            sensor_id not in metadata_by_id
        ):
            continue


        depths = parse_depth_profile(
            event.get(
                "flood_profile_depth_inches"
            )
        )


        flood_depths = [
            depth
            for depth in depths
            if depth >= FLOOD_THRESHOLD
        ]


        if not flood_depths:
            continue


        sensor_metadata = metadata_by_id[sensor_id]


        try:

            latitude = float(
                sensor_metadata["latitude"]
            )

            longitude = float(
                sensor_metadata["longitude"]
            )

        except (
            KeyError,
            TypeError,
            ValueError
        ):
            continue


        sensors.append({

            "sensor_id":
                sensor_id,

            "sensor_name":
                sensor_metadata.get(
                    "sensor_name",
                    event.get(
                        "sensor_name",
                        sensor_id
                    )
                ),

            "latitude":
                latitude,

            "longitude":
                longitude,

            "depths":
                flood_depths,

            "index":
                0,

            "polygon":
                make_hazard_polygon(
                    latitude,
                    longitude
                ),

            "event_start":
                event.get(
                    "flood_start_time"
                )

        })


        used_sensor_ids.add(sensor_id)


    print(
        "Loaded",
        len(sensors),
        "FloodNet sensors"
    )


    return sensors


demo_sensors = load_demo_sensors()


def point_inside_polygon(point, polygon):

    longitude = point[0]
    latitude = point[1]


    longitudes = [
        coordinate[0]
        for coordinate in polygon
    ]


    latitudes = [
        coordinate[1]
        for coordinate in polygon
    ]


    return (
        min(longitudes)
        <= longitude
        <= max(longitudes)

        and

        min(latitudes)
        <= latitude
        <= max(latitudes)
    )


def orientation(a, b, c):

    value = (
        (b[1] - a[1])
        *
        (c[0] - b[0])

        -

        (b[0] - a[0])
        *
        (c[1] - b[1])
    )


    if abs(value) < 0.000000001:
        return 0


    if value > 0:
        return 1


    return 2


def on_segment(a, b, c):

    return (
        min(a[0], c[0])
        <= b[0]
        <= max(a[0], c[0])

        and

        min(a[1], c[1])
        <= b[1]
        <= max(a[1], c[1])
    )


def segments_intersect(
    p1,
    q1,
    p2,
    q2
):

    o1 = orientation(
        p1,
        q1,
        p2
    )

    o2 = orientation(
        p1,
        q1,
        q2
    )

    o3 = orientation(
        p2,
        q2,
        p1
    )

    o4 = orientation(
        p2,
        q2,
        q1
    )


    if (
        o1 != o2
        and
        o3 != o4
    ):
        return True


    if (
        o1 == 0
        and
        on_segment(
            p1,
            p2,
            q1
        )
    ):
        return True


    if (
        o2 == 0
        and
        on_segment(
            p1,
            q2,
            q1
        )
    ):
        return True


    if (
        o3 == 0
        and
        on_segment(
            p2,
            p1,
            q2
        )
    ):
        return True


    if (
        o4 == 0
        and
        on_segment(
            p2,
            q1,
            q2
        )
    ):
        return True


    return False


def route_intersects_flood(
    route,
    polygons
):

    if route is None:
        return False


    features = route.get(
        "features",
        []
    )


    if not features:
        return False


    coordinates = (
        features[0]
        ["geometry"]
        ["coordinates"]
    )


    for polygon in polygons:


        for point in coordinates:

            if point_inside_polygon(
                point,
                polygon
            ):
                return True


        for i in range(
            len(coordinates) - 1
        ):

            route_start = coordinates[i]
            route_end = coordinates[i + 1]


            for j in range(
                len(polygon) - 1
            ):

                if segments_intersect(
                    route_start,
                    route_end,
                    polygon[j],
                    polygon[j + 1]
                ):
                    return True


    return False


def get_route_bounds(route):

    features = route.get(
        "features",
        []
    )


    if not features:
        return None


    coordinates = (
        features[0]
        ["geometry"]
        ["coordinates"]
    )


    if not coordinates:
        return None


    longitudes = [
        point[0]
        for point in coordinates
    ]


    latitudes = [
        point[1]
        for point in coordinates
    ]


    return {

        "min_lon":
            min(longitudes),

        "max_lon":
            max(longitudes),

        "min_lat":
            min(latitudes),

        "max_lat":
            max(latitudes)

    }


def get_route_hazards(route):

    route_bounds = get_route_bounds(
        route
    )


    if route_bounds is None:
        return []


    buffer_size = 0.01


    min_lat = (
        route_bounds["min_lat"]
        -
        buffer_size
    )

    max_lat = (
        route_bounds["max_lat"]
        +
        buffer_size
    )

    min_lon = (
        route_bounds["min_lon"]
        -
        buffer_size
    )

    max_lon = (
        route_bounds["max_lon"]
        +
        buffer_size
    )


    results = []


    for sensor in demo_sensors:

        latitude = sensor["latitude"]
        longitude = sensor["longitude"]


        if not (
            min_lat
            <= latitude
            <= max_lat

            and

            min_lon
            <= longitude
            <= max_lon
        ):
            continue


        if not sensor["depths"]:
            continue


        depth = (
            sensor["depths"]
            [
                sensor["index"]
            ]
        )


        if depth < FLOOD_THRESHOLD:
            continue


        if route_intersects_flood(
            route,
            [
                sensor["polygon"]
            ]
        ):

            results.append({

                "sensor":
                    sensor,

                "depth":
                    depth

            })


    return results


def geocode_address(address):

    if not api_key:

        print(
            "ORS_API_KEY is missing."
        )

        return None


    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )


    headers = {

        "Authorization":
            api_key

    }


    params = {

        "text":
            address,

        "size":
            1,

        "boundary.country":
            "US",

        "focus.point.lat":
            FOCUS_LAT,

        "focus.point.lon":
            FOCUS_LON

    }


    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

    except Exception as error:

        print(
            "Geocoding request error:",
            error
        )

        return None


    if response.status_code != 200:

        print(
            "Geocoding error:",
            response.status_code
        )

        return None


    data = response.json()


    features = data.get(
        "features",
        []
    )


    if not features:
        return None


    feature = features[0]


    label = (
        feature["properties"]
        .get(
            "label",
            address
        )
    )


    label = label.replace(
        ", United States",
        ""
    )


    label = label.replace(
        ", USA",
        ""
    )


    return {

        "coordinates":
            feature[
                "geometry"
            ][
                "coordinates"
            ],

        "label":
            label

    }


def get_route(
    start,
    destination,
    mode,
    avoid_polygons=None
):

    if not api_key:

        print(
            "ORS_API_KEY is missing."
        )

        return None


    if mode == "driving":

        profile = "driving-car"

    elif mode == "walking":

        profile = "foot-walking"

    else:

        return None


    url = (
        "https://api.heigit.org/"
        "openrouteservice/v2/directions/"
        f"{profile}/geojson"
    )


    headers = {

        "Authorization":
            api_key,

        "Content-Type":
            "application/json"

    }


    body = {

        "coordinates": [
            start,
            destination
        ],

        "preference":
            "recommended",

        "instructions":
            True,

        "instructions_format":
            "text"

    }


    if avoid_polygons:


        if len(
            avoid_polygons
        ) == 1:

            geometry = {

                "type":
                    "Polygon",

                "coordinates": [
                    avoid_polygons[0]
                ]

            }

        else:

            geometry = {

                "type":
                    "MultiPolygon",

                "coordinates": [

                    [polygon]

                    for polygon
                    in avoid_polygons

                ]

            }


        body["options"] = {

            "avoid_polygons":
                geometry

        }


    try:

        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=25
        )

    except Exception as error:

        print(
            "Routing request error:",
            error
        )

        return None


    if response.status_code != 200:

        print(
            "Routing error:",
            response.status_code
        )

        print(
            response.text
        )

        return None


    return response.json()


@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


@app.route("/autocomplete")
def autocomplete():

    text = request.args.get(
        "text",
        ""
    )


    if (
        len(
            text.strip()
        ) < 2
        or
        not api_key
    ):

        return jsonify([])


    url = (
        "https://api.heigit.org/"
        "pelias/v1/autocomplete"
    )


    headers = {

        "Authorization":
            api_key

    }


    params = {

        "text":
            text,

        "size":
            5,

        "boundary.country":
            "US",

        "focus.point.lat":
            FOCUS_LAT,

        "focus.point.lon":
            FOCUS_LON

    }


    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

    except Exception:
        return jsonify([])


    if response.status_code != 200:
        return jsonify([])


    results = []


    for feature in (
        response
        .json()
        .get(
            "features",
            []
        )
    ):

        coordinates = (
            feature[
                "geometry"
            ][
                "coordinates"
            ]
        )


        properties = feature.get(
            "properties",
            {}
        )


        label = properties.get(
            "label",
            "Unknown location"
        )


        label = label.replace(
            ", United States",
            ""
        )


        label = label.replace(
            ", USA",
            ""
        )


        results.append({

            "label":
                label,

            "longitude":
                coordinates[0],

            "latitude":
                coordinates[1]

        })


    return jsonify(results)


@app.route("/routes")
def routes():

    mode = request.args.get(
        "mode",
        "driving"
    )


    start_text = request.args.get(
        "start",
        ""
    )


    destination_text = request.args.get(
        "destination",
        ""
    )


    start_lat = request.args.get(
        "start_lat"
    )

    start_lon = request.args.get(
        "start_lon"
    )


    destination_lat = request.args.get(
        "destination_lat"
    )

    destination_lon = request.args.get(
        "destination_lon"
    )


    if (
        start_lat
        and
        start_lon
    ):

        start = [
            float(start_lon),
            float(start_lat)
        ]

        start_label = (
            start_text
            or
            "Current location"
        )

    else:

        start_result = geocode_address(
            start_text
        )


        if start_result is None:

            return jsonify({

                "error":
                    "Starting location could not be found."

            }), 400


        start = start_result[
            "coordinates"
        ]

        start_label = start_result[
            "label"
        ]


    if (
        destination_lat
        and
        destination_lon
    ):

        destination = [
            float(destination_lon),
            float(destination_lat)
        ]

        destination_label = (
            destination_text
            or
            "Destination"
        )

    else:

        destination_result = (
            geocode_address(
                destination_text
            )
        )


        if destination_result is None:

            return jsonify({

                "error":
                    "Destination could not be found."

            }), 400


        destination = (
            destination_result[
                "coordinates"
            ]
        )

        destination_label = (
            destination_result[
                "label"
            ]
        )


    normal_route = get_route(
        start,
        destination,
        mode
    )


    if normal_route is None:

        return jsonify({

            "error":
                "The normal route could not be calculated."

        }), 500


    route_hazards = get_route_hazards(
        normal_route
    )


    active_polygons = [

        item[
            "sensor"
        ][
            "polygon"
        ]

        for item
        in route_hazards

    ]


    intersects_flood = (
        len(
            route_hazards
        )
        >
        0
    )


    if (
        intersects_flood
        and
        active_polygons
    ):

        safe_route = get_route(
            start,
            destination,
            mode,
            active_polygons
        )


        if safe_route is None:

            safe_route = normal_route

    else:

        safe_route = normal_route


    route_hazard_data = []


    for item in route_hazards:

        sensor = item[
            "sensor"
        ]

        depth = item[
            "depth"
        ]


        route_hazard_data.append({

            "sensor_id":
                sensor["sensor_id"],

            "sensor_name":
                sensor["sensor_name"],

            "latitude":
                sensor["latitude"],

            "longitude":
                sensor["longitude"],

            "depth_inches":
                depth,

            "severity":
                get_severity(
                    depth
                ),

            "flood_active":
                True,

            "route_hazard":
                True

        })


    return jsonify({

        "normal":
            normal_route,

        "safe":
            safe_route,

        "intersects_flood":
            intersects_flood,

        "route_hazards":
            route_hazard_data,

        "active_hazard_count":
            len(
                route_hazard_data
            ),

        "start": {

            "label":
                start_label,

            "coordinates":
                start

        },

        "destination": {

            "label":
                destination_label,

            "coordinates":
                destination

        }

    })


@app.route("/hazards")
def hazards():

    try:

        min_lat = float(
            request.args.get(
                "min_lat",
                -90
            )
        )

        max_lat = float(
            request.args.get(
                "max_lat",
                90
            )
        )

        min_lon = float(
            request.args.get(
                "min_lon",
                -180
            )
        )

        max_lon = float(
            request.args.get(
                "max_lon",
                180
            )
        )

        limit = int(
            request.args.get(
                "limit",
                100
            )
        )

        offset = int(
            request.args.get(
                "offset",
                0
            )
        )

    except ValueError:

        return jsonify({

            "error":
                "Invalid map bounds."

        }), 400


    limit = max(
        1,
        min(
            limit,
            150
        )
    )


    matching_sensors = []


    for sensor in demo_sensors:

        latitude = sensor[
            "latitude"
        ]

        longitude = sensor[
            "longitude"
        ]


        if (
            min_lat
            <= latitude
            <= max_lat

            and

            min_lon
            <= longitude
            <= max_lon
        ):

            matching_sensors.append(
                sensor
            )


    matching_sensors.sort(
        key=lambda sensor:
            str(
                sensor[
                    "sensor_id"
                ]
            )
    )


    total = len(
        matching_sensors
    )


    page = matching_sensors[
        offset:
        offset + limit
    ]


    hazards_list = []


    for sensor in page:

        if not sensor["depths"]:
            continue


        depth = (
            sensor["depths"]
            [
                sensor["index"]
            ]
        )


        hazards_list.append({

            "sensor_id":
                sensor[
                    "sensor_id"
                ],

            "sensor_name":
                sensor[
                    "sensor_name"
                ],

            "latitude":
                sensor[
                    "latitude"
                ],

            "longitude":
                sensor[
                    "longitude"
                ],

            "depth_inches":
                depth,

            "severity":
                get_severity(
                    depth
                ),

            "flood_active":
                depth >= FLOOD_THRESHOLD,

            "event_start":
                sensor.get(
                    "event_start"
                )

        })


    next_offset = (
        offset
        +
        len(page)
    )


    return jsonify({

        "hazards":
            hazards_list,

        "total":
            total,

        "returned":
            len(
                hazards_list
            ),

        "next_offset":
            next_offset,

        "has_more":
            next_offset
            <
            total

    })


@app.route("/health")
def health():

    return jsonify({

        "status":
            "ok",

        "sensor_count":
            len(
                demo_sensors
            ),

        "ors_key_loaded":
            bool(
                api_key
            )

    })


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(
        host="0.0.0.0",
        port=port
    )