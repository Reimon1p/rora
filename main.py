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

        profile = (
            "driving-car"
        )

    elif mode == "walking":

        profile = (
            "foot-walking"
        )

    else:

        return None


    url = (
        "https://api.heigit.org/"
        f"openrouteservice/v2/directions/"
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


        if len(avoid_polygons) == 1:

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
            timeout=20
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