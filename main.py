import os
import ast
import requests

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

api_key = os.getenv("ORS_API_KEY")


SENSOR_ID = "Q-beach-59th-st-beach-channel-dr-1zbc0d"
SENSOR_LAT = 40.59408
SENSOR_LON = -73.78921


FLOOD_POLYGON = [
    [-73.78960, 40.59375],
    [-73.78882, 40.59375],
    [-73.78882, 40.59441],
    [-73.78960, 40.59441],
    [-73.78960, 40.59375]
]


events_url = "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"

params = {
    "$where": (
        f"sensor_id='{SENSOR_ID}' "
        "AND flood_start_time='2026-04-20T01:35:56.000'"
    ),
    "$limit": 1
}


try:

    response = requests.get(
        events_url,
        params=params,
        timeout=10
    )

    events = response.json()

    if len(events) == 0:

        flood_depths = [0.0]

    else:

        flood_depths = ast.literal_eval(
            events[0]["flood_profile_depth_inches"]
        )

except Exception as error:

    print("FloodNet loading error:", error)

    flood_depths = [0.0]


current_depth_index = 0


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


def point_inside_flood(point):

    longitude = point[0]
    latitude = point[1]

    longitudes = [
        coordinate[0]
        for coordinate in FLOOD_POLYGON
    ]

    latitudes = [
        coordinate[1]
        for coordinate in FLOOD_POLYGON
    ]

    return (
        min(longitudes) <= longitude <= max(longitudes)
        and
        min(latitudes) <= latitude <= max(latitudes)
    )


def orientation(a, b, c):

    value = (
        (b[1] - a[1]) * (c[0] - b[0])
        -
        (b[0] - a[0]) * (c[1] - b[1])
    )

    if abs(value) < 0.000000001:
        return 0

    if value > 0:
        return 1

    return 2


def on_segment(a, b, c):

    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
        and
        min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def segments_intersect(p1, q1, p2, q2):

    o1 = orientation(p1, q1, p2)
    o2 = orientation(p1, q1, q2)
    o3 = orientation(p2, q2, p1)
    o4 = orientation(p2, q2, q1)


    if o1 != o2 and o3 != o4:
        return True


    if o1 == 0 and on_segment(p1, p2, q1):
        return True

    if o2 == 0 and on_segment(p1, q2, q1):
        return True

    if o3 == 0 and on_segment(p2, p1, q2):
        return True

    if o4 == 0 and on_segment(p2, q1, q2):
        return True


    return False


def route_intersects_flood(route):

    if route is None:
        return False


    features = route.get(
        "features",
        []
    )


    if len(features) == 0:
        return False


    coordinates = (
        features[0]
        ["geometry"]
        ["coordinates"]
    )


    for point in coordinates:

        if point_inside_flood(point):
            return True


    for i in range(
        len(coordinates) - 1
    ):

        route_start = coordinates[i]
        route_end = coordinates[i + 1]


        for j in range(
            len(FLOOD_POLYGON) - 1
        ):

            flood_start = FLOOD_POLYGON[j]
            flood_end = FLOOD_POLYGON[j + 1]


            if segments_intersect(
                route_start,
                route_end,
                flood_start,
                flood_end
            ):

                return True


    return False


def geocode_address(address):

    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )


    headers = {
        "Authorization": api_key
    }

    params = {

        "text": address,

        "size": 1,

        "boundary.country": "US",

        "focus.point.lat":
            SENSOR_LAT,

        "focus.point.lon":
            SENSOR_LON

    }


    response = requests.get(
        url,
        headers=headers,
        params=params
    )


    if response.status_code != 200:

        print(
            "Geocoding error:",
            response.status_code
        )

        print(
            response.text
        )

        return None


    data = response.json()

    features = data.get(
        "features",
        []
    )


    if len(features) == 0:
        return None


    feature = features[0]


    return {

        "coordinates":
            feature["geometry"]["coordinates"],

        "label":
            feature["properties"].get(
                "label",
                address
            )

    }


def get_route(
    start,
    destination,
    mode,
    avoid_flood=False
):

    if mode == "driving":

        profile = "driving-car"

    elif mode == "walking":

        profile = "foot-walking"

    else:

        return None


    url = (
        "https://api.heigit.org/"
        f"openrouteservice/v2/directions/{profile}/geojson"
    )


    headers = {

        "Authorization": api_key,

        "Content-Type": "application/json"

    }


    body = {

        "coordinates": [
            start,
            destination
        ],

        "preference": "recommended"

    }


    if avoid_flood:

        body["options"] = {

            "avoid_polygons": {

                "type": "Polygon",

                "coordinates": [
                    FLOOD_POLYGON
                ]

            }

        }


    response = requests.post(
        url,
        json=body,
        headers=headers
    )


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


    if len(text.strip()) < 2:
        return jsonify([])


    url = (
        "https://api.heigit.org/"
        "pelias/v1/autocomplete"
    )


    headers = {
        "Authorization": api_key
    }

    params = {

        "text": text,

        "size": 5,

        "boundary.country": "US",

        "focus.point.lat":
            SENSOR_LAT,

        "focus.point.lon":
            SENSOR_LON

    }


    response = requests.get(
        url,
        headers=headers,
        params=params
    )


    if response.status_code != 200:

        print(
            "Autocomplete error:",
            response.status_code
        )

        print(
            response.text
        )

        return jsonify([])


    data = response.json()

    results = []


    for feature in data.get(
        "features",
        []
    ):

        coordinates = (
            feature["geometry"]["coordinates"]
        )

        properties = feature.get(
            "properties",
            {}
        )

        country_code = properties.get(
            "country_a",
            ""
        )

        if country_code != "USA":
            continue

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


    return jsonify(
        results
    )


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


    if start_lat and start_lon:

        start = [
            float(start_lon),
            float(start_lat)
        ]

        start_label = (
            start_text
            or "Current location"
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


        start = (
            start_result["coordinates"]
        )

        start_label = (
            start_result["label"]
        )


    if (
        destination_lat
        and destination_lon
    ):

        destination = [
            float(destination_lon),
            float(destination_lat)
        ]

        destination_label = (
            destination_text
            or "Destination"
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


    intersects_flood = (
        route_intersects_flood(
            normal_route
        )
    )


    safe_route = get_route(
        start,
        destination,
        mode,
        True
    )


    if safe_route is None:

        safe_route = normal_route


    return jsonify({

        "normal":
            normal_route,

        "safe":
            safe_route,

        "intersects_flood":
            intersects_flood,

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


@app.route("/hazard")
def hazard():

    global current_depth_index


    depth = flood_depths[
        current_depth_index
    ]


    severity = get_severity(
        depth
    )


    flood_active = (
        depth >= 0.4
    )


    if (
        current_depth_index
        < len(flood_depths) - 1
    ):

        current_depth_index += 1


    return jsonify({

        "sensor_id":
            SENSOR_ID,

        "sensor_name":
            "Beach Channel Dr / Beach 59th St",

        "latitude":
            SENSOR_LAT,

        "longitude":
            SENSOR_LON,

        "depth_inches":
            depth,

        "severity":
            severity,

        "flood_active":
            flood_active

    })


@app.route("/reset")
def reset():

    global current_depth_index

    current_depth_index = 0


    return jsonify({

        "message":
            "Flood simulation reset"

    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )