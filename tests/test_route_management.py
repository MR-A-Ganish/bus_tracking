import sys
from pathlib import Path
import unittest
from werkzeug.exceptions import BadRequest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from routes.route_management import validate_stops


class OrderedRouteTests(unittest.TestCase):
    def setUp(self):
        self.stops = [
            {"id":1,"stop_name":"Vadalur","latitude":11.55,"longitude":79.55,"distance_from_start_km":0},
            {"id":2,"stop_name":"College","latitude":11.92,"longitude":79.61,"distance_from_start_km":54.88}
        ]

    def test_ordered_route_is_accepted(self):
        self.assertEqual(validate_stops(self.stops),self.stops)

    def test_invalid_stops_are_rejected(self):
        for field,value in [("latitude",91),("longitude",float("nan")),("distance_from_start_km",-1),("id",True),("stop_name","")]:
            stops=[dict(stop) for stop in self.stops]
            stops[1][field]=value
            with self.subTest(field=field),self.assertRaises(BadRequest):
                validate_stops(stops)

    def test_duplicate_ids_and_invalid_origin_are_rejected(self):
        self.stops[1]["id"]=1
        with self.assertRaises(BadRequest):validate_stops(self.stops)
        self.stops[1]["id"]=2
        self.stops[0]["distance_from_start_km"]=2
        with self.assertRaises(BadRequest):validate_stops(self.stops)

    def test_new_stop_and_order_validation(self):
        new={"id":None,"stop_name":"Pickup","latitude":11.7,"longitude":79.6,"distance_from_start_km":20}
        self.assertEqual(len(validate_stops([self.stops[0],new,self.stops[1]])),3)
        new["distance_from_start_km"]=60
        with self.assertRaises(BadRequest):validate_stops([self.stops[0],new,self.stops[1]])


if __name__ == "__main__":unittest.main()
