from flask import Blueprint, jsonify, request
from database import (
    is_mongo_connected, 
    get_detections_col, 
    get_zones_col, 
    get_cameras_col,
    get_users_col,
    mem_detections, 
    mem_zones,
    mem_cameras,
    mem_users
)
from auth import token_required

dashboard_bp = Blueprint("dashboard_bp", __name__)

@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
def get_summary():
    # Camera Stats
    total_cameras = len(mem_cameras)
    online_cameras = sum(1 for c in mem_cameras if c.get("status") == "ONLINE")
    offline_cameras = total_cameras - online_cameras

    # Zone & Supervisor Stats
    total_zones = len(mem_zones)
    active_supervisors = sum(1 for u in mem_users if u.get("role") in ["ZONE_SUPERVISOR", "supervisor"] and u.get("active", True))
    if active_supervisors == 0:
        active_supervisors = sum(1 for z in mem_zones if z.get("supervisor"))

    if is_mongo_connected:
        try:
            d_col = get_detections_col()
            c_col = get_cameras_col()
            z_col = get_zones_col()
            u_col = get_users_col()

            if c_col is not None:
                total_cameras = c_col.count_documents({})
                online_cameras = c_col.count_documents({"status": "ONLINE"})
                offline_cameras = total_cameras - online_cameras

            if z_col is not None:
                total_zones = z_col.count_documents({"active": True})

            if u_col is not None:
                sup_count = u_col.count_documents({"role": {"$in": ["ZONE_SUPERVISOR", "supervisor"]}, "active": True})
                if sup_count > 0:
                    active_supervisors = sup_count

            total = d_col.count_documents({})
            compliant = d_col.count_documents({"complianceStatus": "COMPLIANT"})
            violations = d_col.count_documents({"complianceStatus": "VIOLATION"})
            uncertain = d_col.count_documents({"complianceStatus": "UNCERTAIN"})
            unack_violations = d_col.count_documents({"complianceStatus": "VIOLATION", "reviewStatus": {"$ne": "APPROVED"}})
            
            rate = round((compliant / total) * 100) if total > 0 else 100
            
            person_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$personCount"}}}]
            p_agg = list(d_col.aggregate(person_pipeline))
            monitored_persons = p_agg[0]["total"] if p_agg else total

            return jsonify({
                "totalEvents": total,
                "compliantEvents": compliant,
                "violationEvents": violations,
                "uncertainEvents": uncertain,
                "totalViolations": violations,
                "unacknowledgedViolations": unack_violations,
                "complianceRate": rate,
                "overallComplianceRate": rate,
                "monitoredPersons": monitored_persons,
                "totalCameras": total_cameras,
                "onlineCameras": online_cameras,
                "offlineCameras": offline_cameras,
                "totalZones": total_zones,
                "activeSupervisors": active_supervisors
            }), 200
        except Exception:
            pass

    # In-memory summary
    total = len(mem_detections)
    compliant = sum(1 for e in mem_detections if e.get("complianceStatus") == "COMPLIANT")
    violations = sum(1 for e in mem_detections if e.get("complianceStatus") == "VIOLATION")
    uncertain = sum(1 for e in mem_detections if e.get("complianceStatus") == "UNCERTAIN")
    unack_violations = sum(1 for e in mem_detections if e.get("complianceStatus") == "VIOLATION" and e.get("reviewStatus") != "APPROVED")
    rate = round((compliant / total) * 100) if total > 0 else 100
    monitored_persons = sum(e.get("personCount", 1) for e in mem_detections)

    return jsonify({
        "totalEvents": total,
        "compliantEvents": compliant,
        "violationEvents": violations,
        "uncertainEvents": uncertain,
        "totalViolations": violations,
        "unacknowledgedViolations": unack_violations,
        "complianceRate": rate,
        "overallComplianceRate": rate,
        "monitoredPersons": monitored_persons,
        "totalCameras": total_cameras,
        "onlineCameras": online_cameras,
        "offlineCameras": offline_cameras,
        "totalZones": total_zones,
        "activeSupervisors": active_supervisors
    }), 200

# Supervisor Zone Specific Dashboard Summary
@dashboard_bp.route("/api/dashboard/supervisor-summary", methods=["GET"])
@token_required
def get_supervisor_summary():
    curr = getattr(request, "current_user", {})
    zone_id = request.args.get("zoneId") or curr.get("assignedZoneId") or "zone_01"

    # Find zone
    zone = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            z_col = get_zones_col()
            zone = z_col.find_one({"$or": [{"_id": ObjectId(zone_id)}, {"_id": str(zone_id)}, {"code": zone_id}]})
            if zone:
                zone["_id"] = str(zone["_id"])
        except Exception:
            pass

    if not zone:
        zone = next((z for z in mem_zones if str(z.get("_id")) == str(zone_id) or z.get("code") == zone_id), None)
        if not zone and len(mem_zones) > 0:
            zone = mem_zones[0]

    zone_name = zone.get("name", "Assigned Safety Zone") if zone else "Facility Zone"

    # Zone cameras
    zone_cameras = [c for c in mem_cameras if str(c.get("zoneId")) == str(zone.get("_id")) or c.get("zoneName") == zone_name] if zone else []
    total_cameras = len(zone_cameras)
    online_cameras = sum(1 for c in zone_cameras if c.get("status") == "ONLINE")

    # Zone events & violations
    zone_events = [e for e in mem_detections if str(e.get("zoneId")) == str(zone.get("_id")) or e.get("zoneName") == zone_name] if zone else []
    total_events = len(zone_events)
    compliant_events = sum(1 for e in zone_events if e.get("complianceStatus") == "COMPLIANT")
    violation_events = sum(1 for e in zone_events if e.get("complianceStatus") == "VIOLATION")
    unack_events = sum(1 for e in zone_events if e.get("complianceStatus") == "VIOLATION" and e.get("reviewStatus") != "APPROVED")
    compliance_rate = round((compliant_events / total_events) * 100) if total_events > 0 else 100

    recent_violations = [e for e in zone_events if e.get("complianceStatus") == "VIOLATION"][:5]

    return jsonify({
        "zone": zone,
        "zoneId": zone.get("_id") if zone else zone_id,
        "zoneName": zone_name,
        "complianceRate": compliance_rate,
        "totalEvents": total_events,
        "totalViolations": violation_events,
        "unacknowledgedViolations": unack_events,
        "totalCameras": total_cameras,
        "onlineCameras": online_cameras,
        "cameras": zone_cameras,
        "buzzerEnabled": zone.get("buzzerEnabled", True) if zone else True,
        "buzzerSound": zone.get("buzzerSound", "siren") if zone else "siren",
        "supervisor": zone.get("supervisor", {}) if zone else {},
        "recentViolations": recent_violations
    }), 200


@dashboard_bp.route("/api/dashboard/trends", methods=["GET"])
def get_trends():
    seven_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

    if is_mongo_connected:
        try:
            col = get_detections_col()
            pipeline = [
                {"$match": {"createdAt": {"$gte": seven_days_ago}}},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                        "compliant": {"$sum": {"$cond": [{"$eq": ["$complianceStatus", "COMPLIANT"]}, 1, 0]}},
                        "violation": {"$sum": {"$cond": [{"$eq": ["$complianceStatus", "VIOLATION"]}, 1, 0]}},
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            agg = list(col.aggregate(pipeline))
            trends = [{"date": a["_id"], "compliant": a["compliant"], "violation": a["violation"]} for a in agg]
            return jsonify({"trends": trends}), 200
        except Exception:
            pass

    # In-memory trends
    trends_map = {}
    for i in range(7):
        day_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=6 - i)).strftime("%Y-%m-%d")
        trends_map[day_str] = {"date": day_str, "compliant": 0, "violation": 0}

    for e in mem_detections:
        created = e.get("createdAt")
        if created:
            if isinstance(created, datetime.datetime):
                d_str = created.strftime("%Y-%m-%d")
            else:
                d_str = str(created)[:10]
            if d_str in trends_map:
                if e.get("complianceStatus") == "COMPLIANT":
                    trends_map[d_str]["compliant"] += 1
                elif e.get("complianceStatus") == "VIOLATION":
                    trends_map[d_str]["violation"] += 1

    return jsonify({"trends": list(trends_map.values())}), 200

@dashboard_bp.route("/api/dashboard/zone-summary", methods=["GET"])
def get_zone_summary():
    zones_list = []
    if is_mongo_connected:
        try:
            z_col = get_zones_col()
            d_col = get_detections_col()
            zones = list(z_col.find({"active": True}))

            res = []
            for z in zones:
                z_name = z["name"]
                comp = d_col.count_documents({"zoneName": z_name, "complianceStatus": "COMPLIANT"})
                viol = d_col.count_documents({"zoneName": z_name, "complianceStatus": "VIOLATION"})
                res.append({
                    "id": str(z["_id"]),
                    "name": z_name,
                    "code": z.get("code", "ZN"),
                    "compliant": comp,
                    "violations": viol
                })
            return jsonify({"zones": res}), 200
        except Exception:
            pass

    # In-memory
    res = []
    for z in mem_zones:
        z_name = z["name"]
        comp = sum(1 for d in mem_detections if d.get("zoneName") == z_name and d.get("complianceStatus") == "COMPLIANT")
        viol = sum(1 for d in mem_detections if d.get("zoneName") == z_name and d.get("complianceStatus") == "VIOLATION")
        res.append({
            "id": str(z.get("_id")),
            "name": z_name,
            "code": z.get("code", "ZN"),
            "compliant": comp,
            "violations": viol
        })

    return jsonify({"zones": res}), 200
