"""Vehicle registry: name -> spec factory. build(name, lod) returns build-space objects:
{'body': obj, 'wheels': {name: (obj, centre)}, 'thrusters': {...}, 'lights': {...}, 'extra': {...}}"""
import vbike
import vcars
import vdamage
import vhover


def _wrecked():
    s = vcars.sedan_spec(paint="veh_paint_wrecked", name="CyberCar_Sedan_Wrecked")
    s["post_union"] = vdamage.wreck_shell
    s["builder"] = vdamage.wrecked_builder
    s["gh_zones"] = dict(s["gh_zones"], rail_mat="veh_metal", roof_mat="veh_paint_wrecked")
    s["wheel"] = {"style": "multi", "spokes": 7, "paint": "veh_metal"}
    return s


def _burnt():
    s = vcars.van_spec(paint="veh_burnt", name="CyberVan_Burnt", burnt=True)
    s["builder"] = vdamage.burnt_builder
    return s


SPECS = {
    "CyberCar_Coupe": lambda: vcars.coupe_spec(),
    "CyberCar_Sedan": lambda: vcars.sedan_spec(),
    "CyberCar_Taxi": lambda: vcars.taxi_spec(),
    "CyberVan": lambda: vcars.van_spec(),
    "CyberBike": lambda: vbike.bike_spec(),
    "HoverCar_A": lambda: vhover.hover_a_spec(),
    "HoverCar_B": lambda: vhover.hover_b_spec(),
    "HoverTruck": lambda: vhover.hover_truck_spec(),
    "CyberCar_Sedan_Wrecked": _wrecked,
    "CyberVan_Burnt": _burnt,
}

CATEGORY = {
    "CyberCar_Coupe": "car", "CyberCar_Sedan": "car", "CyberCar_Taxi": "car", "CyberVan": "van", "CyberBike": "bike",
    "HoverCar_A": "hover", "HoverCar_B": "hover", "HoverTruck": "hover", "CyberCar_Sedan_Wrecked": "wreck", "CyberVan_Burnt": "wreck",
}


def names():
    return list(SPECS.keys())


def spec(name):
    return SPECS[name]()


def build(name, lod):
    s = SPECS[name]()
    if "builder" in s:
        return s["builder"](s, lod)
    return vcars.build_car(s, lod)
