-- Public map references locate the endpoints. Admins configure actual pickup stops.
-- Vadalur Bus Stand: OpenStreetMap node 4820805923.
-- Campus coordinate: https://smvmch.ac.in/files/ssrupdate/criteria_2/2_3_1/2_3_1_b.pdf
-- 54.88 km is an OSRM road-routing estimate, to be adjusted for the college bus path.
DO $$
DECLARE vadalur_route INTEGER;
BEGIN
 SELECT id INTO vadalur_route FROM routes WHERE route_name='Vadalur to IFET College' ORDER BY id LIMIT 1;
 IF vadalur_route IS NULL THEN
  INSERT INTO routes(route_name,start_point,end_point)
   VALUES ('Vadalur to IFET College','Vadalur Bus Stand','IFET College') RETURNING id INTO vadalur_route;
  INSERT INTO bus_stops(route_id,stop_name,sequence_order,distance_from_start_km,latitude,longitude)
   VALUES (vadalur_route,'Vadalur Bus Stand',0,0,11.555690,79.555400),
          (vadalur_route,'IFET College',1,54.88,11.921253,79.610378);
 END IF;
END $$;

-- Serialize assignment validation with bus route changes.
CREATE OR REPLACE FUNCTION validate_bus_assignment() RETURNS TRIGGER AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM buses b JOIN bus_stops s ON s.route_id=b.route_id
               WHERE b.id=NEW.bus_id AND s.id=NEW.stop_id FOR SHARE OF b) THEN
  RAISE EXCEPTION 'Stop must belong to assigned bus route' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
